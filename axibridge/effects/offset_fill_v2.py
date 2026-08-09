"""Offset fill v2: everything ``offset_fill`` does, plus one unbroken stroke.

**Read ``effects/offset_fill.py`` first.** That module's docstring is the
canonical account of how this family of effects works, and none of it is
repeated here: erosion by a disk as the single operation, why every ring is
eroded from the ORIGINAL at ``k * spacing`` rather than iteratively, why the
even-odd (``symmetric_difference``) hole assembly has to run before eroding,
why ``round_center`` is a morphological *opening* and therefore rounds the
CONVEX corners, why inner rings must not be marked ``filled``, and why
topology needs no special-casing (shapely handing back a ``MultiPolygon`` or
an empty geometry IS the split / the death). All of that is inherited verbatim.

v1 stays shipped and unchanged. This is a sibling, not a replacement — stack
either one, and diff them on the same layer.

What v2 adds, and why:

* **the spiral** — v1's docstring names it as the deliberately-unbuilt thing,
  and it is the one measured shortfall: a 120 mm square at 1 mm spacing plots
  as *61 separate strokes*, i.e. 61 pen lifts. Sixty of those lifts are pure
  travel between rings that are one spacing apart. See ``_spiral``.
* **tolerance instead of a segment count** — ``smooth`` was scale-blind: 8
  segments per quarter is 0.005 mm of chord error at a 1 mm radius and
  0.53 mm at 110 mm, so it simultaneously wastes vertices on small corners and
  facets big ones past a pen width. v2 asks for the error directly and derives
  the segment count per call from the radius actually being offset.
* **an arc-native engine**, off by default — see ``_arcpoly.py``.

The idea list came from reading `cavalier-contours-js
<https://github.com/msurguy/cavalier-contours-js>`_ (a TypeScript port of the
Rust ``cavalier_contours`` crate) in August 2026. The library itself is not
usable here — our geometry is server-side Python behind the single-resolve
invariant, and the Pi has no Node — so nothing is vendored; only the ideas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import shapely
from pydantic import BaseModel, Field
from shapely.geometry import LinearRing, LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.prepared import prep

from ..model import Path, is_closed
from ..registry import EffectContext, EffectModule, register_effect

Pt = tuple[float, float]

#: shapely mitre ratio cap. A sharp reflex corner mitres to an arbitrarily long
#: spike as the angle closes; past this ratio shapely bevels it instead. Low
#: enough that a near-cusp cannot throw a spur across the shape, high enough
#: that ordinary corners (a star's points) still come to a real tip.
_MITRE_LIMIT = 3.0

#: bisection steps used to place a dying component's medial tail. Each step is
#: one buffer call on an already-small polygon, and 6 halvings put the tail
#: within ~1.5% of spacing — far finer than a pen can resolve.
_TAIL_STEPS = 6

#: a ring shorter than this (mm) is a numerical crumb from a cusp, not a mark.
_MIN_RING_LEN = 0.05

#: mm: below this a rounding radius is not worth a second pair of buffers, and
#: the ring is taken sharp. Also the floor the round_center back-off walks to.
_MIN_ROUND_R = 0.05

#: × spacing: how far a medial tail must sit from the ring it grew out of to be
#: worth drawing. A limb that dies just AFTER a ring lands its centreline right
#: on top of that ring — three lines inside one spacing, which plots as a band
#: of doubled ink rather than as fill. Under this gap the limb is already inked.
_MIN_TAIL_GAP = 0.5

#: ceiling on the vertices in one spiral. A full-bed fill at a fine spacing AND
#: a fine tolerance is a single very long polyline; per ``smoothen.MAX_POINTS``
#: the honest degradation is a coarser blend, not a file that will not plot.
_MAX_SPIRAL_POINTS = 20_000


#: halvings a blend backs off by when its lerp chord would leave the shape.
_BLEND_BACKOFF = 4

#: mm along a ring: below this two arc-length positions are the same position.
_EPS_U = 1e-9


class OffsetFillV2Params(BaseModel):
    spacing: float = Field(default=2.0, ge=0.2, le=20.0, title="Spacing (mm)",
                           description="Gap between consecutive rings. Below the "
                                       "pen width the fill reads as solid ink")
    max_rings: int = Field(default=24, ge=1, le=200, title="Max rings",
                           description="Hard cap — a large shape at a fine "
                                       "spacing is a lot of geometry")
    engine: Literal["shapely", "arc"] = Field(
        default="shapely", title="Engine",
        description="How the rings are computed. Shapely erodes the area (the "
                    "proven path); arc fits the outline to real arcs and offsets "
                    "them exactly, which keeps circles round instead of faceted. "
                    "Arc is newer \u2014 check the result before plotting it",
    )
    join_style: Literal["mitre", "round", "bevel"] = Field(
        default="mitre", title="Corners",
        description="How rings turn at a concave corner: mitre keeps the "
                    "shape's own corners sharp, round softens them into "
                    "contour lines. Convex-only shapes (a square) look "
                    "identical under all three",
    )
    round_center: float = Field(
        default=0.0, ge=0.0, le=1.0, title="Round the centre",
        description="Relaxes each ring's corners in proportion to how deep it "
                    "sits, so the outer rings still read as the shape while "
                    "the inner ones ease toward circles. 0 repeats the shape "
                    "unchanged all the way in",
    )
    outline: bool = Field(default=True, title="Keep outline",
                          description="Off also stops the shape occluding as a solid")
    medial_tail: bool = Field(
        default=True, title="Close thin areas",
        description="When a part of the shape is too narrow for another whole "
                    "ring, draw one last ring down its middle instead of "
                    "leaving it hollow",
    )
    spiral: bool = Field(
        default=True, title="Spiral",
        description="Join the rings into one continuous stroke wherever the "
                    "shape allows it, so the pen never lifts. Falls back to "
                    "separate rings where a part splits in two or has a hole",
    )
    blend: float = Field(
        default=0.5, ge=0.0, le=1.0, title="Seam blend",
        description="How much of each ring-to-ring step is spread around the "
                    "turn instead of taken in one go. 0 leaves a plain seam; "
                    "higher reads as a true spiral, but consecutive turns end "
                    "up (1 − this) × Spacing apart, so past 0.5 they crowd and "
                    "at 1.0 the innermost two touch",
    )
    simplify: float = Field(default=0.05, ge=0.0, le=1.0, title="Simplify (mm)",
                            description="Drop ring vertices closer than this to "
                                        "the line they sit on — keeps traced "
                                        "artwork from exploding into points. "
                                        "Keep it at or below Tolerance, or it "
                                        "undoes the precision you asked for there",
                            json_schema_extra={"group": "Fine tuning"})
    tolerance: float = Field(default=0.05, ge=0.005, le=1.0, title="Tolerance (mm)",
                             description="The most a curve may deviate from its "
                                         "true shape once flattened into line "
                                         "segments. Unlike a segment count this "
                                         "means the same thing at every radius",
                             json_schema_extra={"group": "Fine tuning"})
    pos_eq_eps: float = Field(
        default=1e-5, ge=1e-9, le=1e-2, title="Point epsilon (mm)",
        description="Below this two points are the same point. Raise it if "
                    "traced artwork arrives with near-duplicate vertices",
        json_schema_extra={"group": "Fine tuning"})
    offset_dist_eps: float = Field(
        default=1e-4, ge=1e-9, le=1e-2, title="Offset epsilon (mm)",
        description="Slack in the test that throws away the invalid parts of an "
                    "offset curve. Arc engine only — the shapely engine gets "
                    "this for free from the erosion",
        json_schema_extra={"group": "Fine tuning"})
    slice_join_eps: float = Field(
        default=1e-4, ge=1e-9, le=1e-2, title="Join epsilon (mm)",
        description="How far apart two ends of an offset curve may sit and "
                    "still be joined into one loop. Arc engine only",
        json_schema_extra={"group": "Fine tuning"})


#: hard ceiling on segments per quarter circle. At 110 mm radius a 0.005 mm
#: tolerance asks for ~600, which is vertex detonation for sub-pen-width gain.
#: Per `smoothen.MAX_POINTS`, degrading to coarser is the honest failure.
_MAX_QUAD_SEGS = 64


def _quad_segs(radius: float, tol: float) -> int:
    """Segments per quarter circle that keep a flattened arc within `tol` mm.

    This is the whole point of asking for a tolerance rather than a segment
    count. A chord subtending angle ``a`` on radius ``r`` sits ``r(1-cos(a/2))``
    from the true arc, so the largest admissible angle is
    ``a = 2·acos(1 − tol/r)`` and a quarter turn needs ``(π/2)/a`` of them.
    Because ``r`` is in there, the answer TRACKS SCALE: v1's fixed 8 spent
    vertices it did not need at a 1 mm corner (0.005 mm of error) and faceted a
    110 mm one past a pen width (0.53 mm). A radius at or under the tolerance
    cannot be resolved at all and collapses to a single segment.
    """
    if radius <= tol:
        return 1
    a = 2.0 * math.acos(1.0 - tol / radius)
    return max(1, min(_MAX_QUAD_SEGS, math.ceil((math.pi / 2.0) / a)))


def _erode(poly, distance: float, params: OffsetFillV2Params):
    """Erode by `distance` mm. Always from the caller's geometry, so the caller
    controls whether that is the original (rings) or a component (tails).

    The arcs a round join draws here have radius `distance`, which is what the
    segment count is derived from — see `_quad_segs`.
    """
    return poly.buffer(-distance, quad_segs=_quad_segs(distance, params.tolerance),
                       join_style=params.join_style, mitre_limit=_MITRE_LIMIT)


def _polygons(geom) -> list[Polygon]:
    """Flatten whatever buffer returned into the non-empty polygons in it."""
    if geom.is_empty:
        return []
    parts = geom.geoms if hasattr(geom, "geoms") else [geom]
    return [g for g in parts if isinstance(g, Polygon) and not g.is_empty]


def _arc_erode(geom, distance: float, params: OffsetFillV2Params):
    """`_erode`, done in arc space — see `_arcpoly`.

    Each ring is fitted to arcs, offset exactly, pruned, and flattened once at
    the end. Orientation carries the meaning: `orient(…, 1.0)` gives a CCW
    exterior and CW holes, and "left of travel" is into the material for both,
    so one positive distance erodes the shape and grows its holes at the same
    time. Holes are offset independently of the exterior and reconciled by a
    difference, which is what lets a hole grow through the outside or into
    another one without either offset having to know about the other.
    """
    from . import _arcpoly

    out = []
    for poly in _polygons(geom):
        poly = orient(poly, 1.0)
        parts = _arc_rings(poly.exterior, distance, params)
        if not parts:
            continue
        shape = unary_union(parts)
        holes = [h for ring in poly.interiors
                 for h in _arc_rings(ring, distance, params)]
        if holes:
            shape = shape.difference(unary_union(holes))
        out.extend(_polygons(shape))
    return unary_union(out) if out else Polygon()


def _arc_rings(ring, distance: float, params: OffsetFillV2Params) -> list[Polygon]:
    """One ring offset `distance` to the left of its travel, as polygons."""
    from . import _arcpoly

    if distance == 0.0:
        return [Polygon(ring)]
    fitted = _arcpoly.fit_contour([(x, y) for x, y in ring.coords], params.tolerance)
    out = []
    for loop in _arcpoly.offset_contour(fitted, distance, params.tolerance,
                                        params.offset_dist_eps, params.slice_join_eps):
        poly = Polygon(_arcpoly.flatten(loop, params.tolerance))
        if not poly.is_valid:
            poly = poly.buffer(0)
        out.extend(_polygons(poly))
    return out


def _level(region, depth: float, params: OffsetFillV2Params) -> list[Polygon]:
    """The components at `depth`, with `round_center` applied.

    Rounding is a morphological **opening**: erode an extra `r` past the depth
    we want, then dilate `r` back with round joins. That rounds the *convex*
    corners — the ones an inward offset otherwise keeps perfectly sharp, which
    is exactly what "the middle should go round" is asking for — while leaving
    straight runs where they already were, so ring spacing along an edge is
    untouched and the ring still cannot escape the shape (an opening of a set
    is contained in it).

    `r` grows with depth, which is what makes the family *morph*: the outermost
    ring is barely touched and each one after it relaxes further, so a square
    becomes a squircle becomes a circle on the way in.

    A large `r` can erode away a component that survives sharp, so the radius
    backs off by halves until the ring exists. Rounding is a finish, and it may
    not cost the fill a ring it would otherwise have drawn.
    """
    erode = _arc_erode if params.engine == "arc" else _erode
    if params.round_center <= 0.0:
        return _polygons(erode(region, depth, params))
    r = params.round_center * depth
    while r > _MIN_ROUND_R:
        eroded = erode(region, depth + r, params)
        if not eroded.is_empty:
            # the opening's dilation is the same operation run outward, which
            # under the arc engine is a negative offset rather than a buffer
            if params.engine == "arc":
                return _polygons(_arc_erode(eroded, -r, params))
            return _polygons(eroded.buffer(r, quad_segs=_quad_segs(r, params.tolerance),
                                           join_style="round"))
        r /= 2
    return _polygons(erode(region, depth, params))


def _rings(poly: Polygon, params: OffsetFillV2Params) -> list[list[Pt]]:
    """A polygon's exterior and every hole, as closed point lists.

    Simplification runs per ring rather than on the polygon so a tolerance
    large enough to thin a traced outline cannot delete a small hole. Adjacent
    levels simplify independently and could in principle cross by up to the
    tolerance — which is why the bound is well under any pen width.
    """
    out: list[list[Pt]] = []
    for ring in [poly.exterior, *poly.interiors]:
        line = ring.simplify(params.simplify) if params.simplify > 0 else ring
        pts = [(x, y) for x, y in line.coords]
        if len(pts) < 4 or line.length < _MIN_RING_LEN:
            continue  # a crumb, or too few vertices to be a loop at all
        if pts[0] != pts[-1]:
            pts.append(pts[0])  # simplify can drop the closing repeat
        out.append(pts)
    return out


def _medial_poly(poly: Polygon, params: OffsetFillV2Params) -> Polygon | None:
    """The sliver a component leaves at the depth it finally disappears.

    Split out of `_medial_tail` (which now just rings this) because the spiral
    wants the POLYGON: a dying limb's centreline is simply one more level down,
    so when it is a single hole-free loop the spiral can swallow it as its last
    turn rather than lifting the pen for it.

    `poly` survived its level but nothing survives the next one, so somewhere
    in (0, spacing) is the depth at which it finally vanishes. Bisect for a
    depth just short of that: the sliver there hugs the component's medial
    axis, and drawing it keeps a narrow limb from reading as a hollow outline.

    Eroding the component rather than the original region is exact, not an
    approximation — erosion by a disk is associative, so eroding a level-k
    component by t is the level-(k*spacing + t) geometry inside it. (Under
    ``round_center`` the parent is an opened level, so the tail inherits that
    rounding instead — which is what keeps it looking like the rings it ends.)

    The bisected depth doubles as the tail's own quality test: it IS the gap to
    the parent ring, so a tail that would land on top of that ring is dropped.
    """
    lo, hi = 0.0, params.spacing  # lo is known non-empty, hi known empty
    best: Polygon | None = None
    for _ in range(_TAIL_STEPS):
        mid = (lo + hi) / 2
        found = _polygons(_erode(poly, mid, params))
        if found:
            best = max(found, key=lambda g: g.area)
            lo = mid
        else:
            hi = mid
    if best is None or lo < _MIN_TAIL_GAP * params.spacing:
        return None
    return best


def _medial_tail(poly: Polygon, params: OffsetFillV2Params) -> list[list[Pt]]:
    """`_medial_poly` as closed point lists — v1's signature, unchanged."""
    best = _medial_poly(poly, params)
    return _rings(best, params) if best is not None else []


# -- the level forest ----------------------------------------------------------

@dataclass(eq=False)
class _Node:
    """One component at one depth, linked to the components it erodes into."""

    poly: Polygon
    depth: int
    children: list["_Node"] = field(default_factory=list)


def _forest(region, params: OffsetFillV2Params) -> list[list[_Node]]:
    """Every level, with each component linked to the components below it.

    v1 discovers this structure implicitly — its tail pass asks "did anything
    deeper intersect this?" — but a spiral needs it named, because "exactly one
    child and no holes, all the way down" is the condition under which a single
    unbroken stroke exists at all.

    A node's children are EVERY deeper component it intersects, which is v1's
    rule verbatim, so an empty list still means exactly "this component died in
    this step". Erosion never merges two components, so that list holds at most
    one entry in practice — but nothing here relies on it, and the spiral walk
    claims nodes by identity so even a numerical double-link cannot get one
    level inked twice.
    """
    levels: list[list[_Node]] = [[_Node(poly, 0) for poly in _polygons(region)]]
    for k in range(1, params.max_rings + 1):
        deeper = _level(region, k * params.spacing, params)
        deeper = _monotone(deeper, levels[-1], params)
        nodes = [_Node(poly, k) for poly in deeper]
        for parent in levels[-1]:
            parent.children = [n for n in nodes if n.poly.intersects(parent.poly)]
        if not nodes:
            break
        levels.append(nodes)
    return levels


def _monotone(deeper: list[Polygon], above: list[_Node],
              params: OffsetFillV2Params) -> list[Polygon]:
    """Clip a level to the one above it. Erosion cannot grow.

    A no-op for the shapely engine, which gets this from GEOS, and skipped
    entirely there so it costs nothing. The arc engine needs it: right at the
    depth a shape collapses, its raw offset crosses itself many times over and
    the noding invents faces in the tangle. Those faces pass the "at least |d|
    from the source" test honestly — near a star's centre there IS clearance —
    so the only thing that catches them is the invariant they violate, which is
    that the area at depth k+1 was 4 mm² when the area at depth k was 1.9 mm².

    The previous level is the natural place to enforce it and the only place it
    is cheap, because `_forest` is already holding it.
    """
    if params.engine != "arc" or params.round_center > 0.0 or not deeper:
        return deeper
    if not above:
        return []
    ceiling = unary_union([n.poly for n in above])
    out: list[Polygon] = []
    for poly in deeper:
        clipped = poly.intersection(ceiling)
        out.extend(g for g in _polygons(clipped) if g.area > params.tolerance ** 2)
    return out


def _chain(node: _Node) -> list[_Node]:
    """The maximal run of hole-free, single-child components below `node`.

    Stops at the first component that splits, dies, or grows a hole — precisely
    the events that make one stroke impossible. Below that point the subtree
    falls back to rings, which is what the ROADMAP means by building the spiral
    *on top of* the rings rather than instead of them.
    """
    if node.poly.interiors:
        return [node]
    chain = [node]
    while len(chain[-1].children) == 1:
        nxt = chain[-1].children[0]
        if nxt.poly.interiors:
            break
        chain.append(nxt)
    return chain


# -- the spiral ----------------------------------------------------------------

def _nearest(ring: LinearRing, pt: Pt) -> Pt:
    """The point on `ring` closest to `pt`."""
    p = ring.interpolate(ring.project(Point(pt)))
    return (p.x, p.y)


def _blend_steps(rings: list[LinearRing], params: OffsetFillV2Params) -> list[float]:
    """Per-lap sample spacing inside the blend region, capped by a vertex budget.

    The blend has to be resampled: a ring's own vertices are too sparse to carry
    a smooth inward drift, and on a square there are four of them. How sparse is
    too sparse is the same question `_quad_segs` answers — a chord of length `s`
    on radius `r` sits about `s²/8r` off the true curve, so `s = sqrt(8·tol·r)`
    — with `r` taken from the lap's own girth, because the tight inner laps
    curve fastest and deserve the finer sampling. That derivation is why this is
    *cheap*: a fixed fraction of the tolerance oversampled a full-bed square by
    an order of magnitude for no visible gain.

    A full-bed fill at a fine spacing is still one very long polyline, so if the
    estimate overruns the ceiling every step scales up together — coarser, per
    `smoothen`, being the honest failure rather than a file that will not plot.
    """
    if params.blend <= 0.0:
        return [0.0] * len(rings)
    steps = [math.sqrt(8.0 * params.tolerance
                       * max(r.length / (2.0 * math.pi), params.tolerance))
             for r in rings]
    budget = max(1, _MAX_SPIRAL_POINTS - sum(len(r.coords) for r in rings))
    est = sum(r.length * params.blend / s for r, s in zip(rings[:-1], steps[:-1]))
    if est > budget:
        steps = [s * (est / budget) for s in steps]
    return steps


def _ring_samples(ring: LinearRing, start: Pt, extra_from: float,
                  step: float) -> list[tuple[float, Pt]]:
    """One full loop of `ring` from `start`, as (arc length travelled, point).

    The ring's OWN vertices are always sampled. Resampling at a fixed arc-length
    interval would chord straight across a corner, and keeping the shape's
    corners is the entire point of an offset fill — so regular samples are added
    only past `extra_from`, inside the blend region, where a smooth inward drift
    needs points the ring simply does not have.
    """
    coords = list(ring.coords)
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    length = ring.length
    origin = ring.project(Point(start))
    out: list[tuple[float, Pt]] = [(0.0, start), (length, start)]
    run = 0.0
    for a, b in zip(coords, coords[1:]):
        u = (run - origin) % length
        if _EPS_U < u < length - _EPS_U:
            out.append((u, (a[0], a[1])))
        run += math.dist(a, b)
    if step > 0.0:
        n = int((length - _EPS_U - extra_from) / step)
        if n > 0:
            us = extra_from + step * np.arange(1, n + 1)
            xy = shapely.get_coordinates(
                shapely.line_interpolate_point(ring, (origin + us) % length))
            out.extend(zip(us.tolist(), (tuple(p) for p in xy.tolist())))
    out.sort(key=lambda s: s[0])
    return out


def _safe_lerp(p: Pt, q: Pt, w: float, cover) -> Pt:
    """Move `p` a fraction `w` toward `q`, but never outside the shape.

    A blend is a straight chord between corresponding points on two nested
    rings. Between convex rings it stays in the annulus between them; across a
    deep concavity it can cut the corner and leave the region altogether. Ink is
    permanent, so that is not a rounding error we get to accept — back the
    fraction off by halves until the point is inside, the same move `_level`
    makes rather than let `round_center` cost a ring.
    """
    for _ in range(_BLEND_BACKOFF):
        m = (p[0] + (q[0] - p[0]) * w, p[1] + (q[1] - p[1]) * w)
        if cover.covers(Point(m)):
            return m
        w /= 2.0
    return p


def _turn(ring: LinearRing, start: Pt, nxt: LinearRing | None, poly: Polygon,
          params: OffsetFillV2Params, step: float) -> list[Pt]:
    """One lap of `ring`, easing into `nxt` over the last `blend` of the lap.

    The easing runs through shapely's vectorised ufuncs rather than a
    point-at-a-time loop. That is not premature: this whole module sits on the
    preview path, where `session.resolved*()` re-runs the stack on every slider
    drag, and a per-point `project`/`covers` pair put a full-bed fill at 400 ms
    against v1's 3 ms. Only the points that fail the containment test fall back
    to the scalar back-off, and on ordinary shapes there are none.
    """
    length = ring.length
    if length <= 0.0:
        return []
    blend = params.blend if nxt is not None else 0.0
    start_at = length * (1.0 - blend)
    samples = _ring_samples(ring, start, start_at, step if blend > 0.0 else 0.0)
    if blend <= 0.0:
        # plain cut-and-join: the lap closes on itself and the NEXT lap opens on
        # its own start, so the join is one straight radial step of one spacing
        return [p for _, p in samples]
    head = [p for u, p in samples if u <= start_at]
    easing = [(u, p) for u, p in samples if u > start_at]
    if not easing:
        return head
    src = np.array([p for _, p in easing], dtype=float)
    # the easing covers `blend` OF THE STEP over `blend` of the lap, never all of
    # it — see the module docstring's "why a lap never reaches the next ring"
    w = np.array([blend * (u - start_at) / (length - start_at) for u, _ in easing])
    dst = shapely.get_coordinates(shapely.line_interpolate_point(
        nxt, shapely.line_locate_point(nxt, shapely.points(src))))
    moved = src + (dst - src) * w[:, None]
    outside = ~shapely.covers(poly, shapely.points(moved))
    if outside.any():
        cover = prep(poly)
        for i in np.flatnonzero(outside):
            moved[i] = _safe_lerp(tuple(src[i]), tuple(dst[i]), float(w[i]), cover)
    return head + [(float(x), float(y)) for x, y in moved.tolist()]


def _clean(pts: list[Pt], params: OffsetFillV2Params) -> list[Pt]:
    """Drop repeated points, then thin the stroke the way a ring is thinned."""
    out: list[Pt] = []
    for p in pts:
        eps = params.pos_eq_eps
        if not out or abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    if len(out) < 2:
        return []
    if params.simplify > 0.0:
        out = [(x, y) for x, y in LineString(out).simplify(params.simplify).coords]
    return out


def _spiral(polys: list[Polygon], params: OffsetFillV2Params) -> list[Pt]:
    """One unbroken stroke down a chain of nested, hole-free components.

    Turn k is the full lap of ring k from `s_k` back to `s_k`; over its last
    `blend` fraction every point eases toward its nearest neighbour on ring
    k+1, landing exactly on `s_{k+1}` — because that is how `s_{k+1}` was
    defined. So the laps concatenate with no duplicated vertex, no gap, and no
    lift. At `blend = 0` the easing collapses to a single radial step and the
    result is the plain cut-and-join.

    Correspondence between laps is by NEAREST POINT, not by matching arc-length
    fraction. Arc-length correspondence skews wherever the two rings differ in
    shape, which is exactly what a concave shape does as it erodes — and a
    skewed correspondence is what sends a blend chord outside the region.

    **Why a lap never quite reaches the next ring.** The easing covers `blend`
    of the STEP over `blend` of the lap, so a lap ends one short hop shy of the
    ring it is heading for and the hop closes the gap. Letting it arrive — the
    obvious reading of "a true spiral" — puts doubled ink down the middle of
    the fill, and the reason is worth keeping written down:

    Laps hold their spacing because they drift IN LOCKSTEP. Lap k at parameter
    u sits at inset ``(k + drift(u))·spacing`` and lap k+1 at
    ``(k + 1 + drift(u))·spacing``, so whatever `drift` does they stay exactly
    one spacing apart. The innermost lap is the exception: it has nothing to
    drift toward, so it sits still at its own inset while the lap above it
    slides down onto it. Full drift means they meet.

    Capping the drift at `blend` bounds that: along their parallel stretches two
    laps never come closer than ``(1 − blend) × spacing``, the last pair
    included. Which is why the parameter is not free — past 0.5 the turns run
    closer than half a spacing, and at 1.0 the innermost two touch.

    That bound is about parallel stretches and nothing else. At the seam a lap
    comes back to where it started before hopping inward, so it passes within
    ``blend × step`` of its own beginning no matter what — every spiral has one
    place where consecutive turns meet, and that place is the seam by
    definition. What matters is that the meeting stays a crossing rather than
    becoming a stretch of doubled ink, which is what the bound above buys.

    That collision does not show up on a square or a star, where the innermost
    laps are short next to the outer ones. It shows up badly on anything long
    and thin — a C, a bar — whose contours barely shorten as they erode, so the
    colliding pair is a large fraction of the whole fill. Measured on a 115 mm
    C at 4 mm spacing: 0.4% of the stroke plots as doubled ink at blend 0.5,
    12.6% at 0.7, 31.2% at 1.0.
    """
    rings = [orient(p, 1.0).exterior for p in polys]
    # deterministic seed: the contract test compares two runs vertex for vertex
    seed = min(list(rings[0].coords)[:-1], key=lambda c: (c[1], c[0]))
    starts: list[Pt] = [(seed[0], seed[1])]
    for ring in rings[1:]:
        starts.append(_nearest(ring, starts[-1]))
    steps = _blend_steps(rings, params)
    pts: list[Pt] = []
    for k, ring in enumerate(rings):
        nxt = rings[k + 1] if k + 1 < len(rings) else None
        pts.extend(_turn(ring, starts[k], nxt, polys[k], params, steps[k]))
    return _clean(pts, params)


# -- emission ------------------------------------------------------------------

def _emit_rings(levels: list[list[_Node]], params: OffsetFillV2Params,
                out: list[Path]) -> None:
    """v1's emission, depth-major, in its exact order.

    Kept byte-identical on purpose: `spiral` off is the control arm, and a test
    asserts that v2 with it off reproduces `offset_fill` path for path. Reorder
    this and that regression net becomes noise.
    """
    for k in range(1, params.max_rings + 1):
        if k - 1 >= len(levels):
            break
        if params.medial_tail:
            for node in levels[k - 1]:
                if not node.children:
                    for ring in _medial_tail(node.poly, params):
                        out.append(Path(points=ring, filled=False))
        if k >= len(levels):
            break
        for node in levels[k]:
            for ring in _rings(node.poly, params):
                out.append(Path(points=ring, filled=False))


def _emit_component(node: _Node, params: OffsetFillV2Params, out: list[Path],
                    claimed: set[int]) -> None:
    """Spiral this component's chain, then recurse into whatever it splits into."""
    if id(node) in claimed:
        return
    chain = _chain(node)
    claimed.update(id(n) for n in chain)
    terminus = chain[-1]
    polys = [n.poly for n in chain]
    tail_rings: list[list[Pt]] = []
    if params.medial_tail and not terminus.children:
        tail = _medial_poly(terminus.poly, params)
        if tail is not None and not tail.interiors:
            polys.append(tail)          # the spiral finishes down the centreline
        elif tail is not None:
            tail_rings = _rings(tail, params)

    if len(polys) >= 2:
        pts = _spiral(polys, params)
        if pts:
            out.append(Path(points=pts, filled=False))
    else:
        for ring in _rings(polys[0], params):
            out.append(Path(points=ring, filled=False))
    for ring in tail_rings:
        out.append(Path(points=ring, filled=False))
    for child in terminus.children:
        _emit_component(child, params, out, claimed)


def _emit_spirals(levels: list[list[_Node]], params: OffsetFillV2Params,
                  out: list[Path]) -> None:
    claimed: set[int] = set()
    for root in levels[0]:
        # depth 0 IS the original outline, which `outline` has already emitted as
        # a FILLED path carrying the layer's occlusion semantics. Folding it into
        # an unfilled spiral would either double the ink or lose that flag, so a
        # spiral starts one spacing in.
        if params.medial_tail and not root.children:
            for ring in _medial_tail(root.poly, params):
                out.append(Path(points=ring, filled=False))
        for child in root.children:
            _emit_component(child, params, out, claimed)


@register_effect
class OffsetFillV2(EffectModule):
    id = "offset_fill_v2"
    label = "Offset fill (v2)"
    description = ("Offset fill that plots as one continuous spiral wherever the "
                   "shape allows it, falling back to concentric rings where it "
                   "cannot. Same contour-map look as Offset fill, far fewer pen lifts.")
    Params = OffsetFillV2Params

    def apply(self, paths: list[Path], params: OffsetFillV2Params,
              ctx: EffectContext) -> list[Path]:
        out: list[Path] = []
        shapes: list[Polygon] = []
        for path in paths:
            pts = path.points
            if not (path.filled and is_closed(pts)):
                out.append(path)
                continue
            if params.outline:
                out.append(path)
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                shapes.append(poly)
        if not shapes:
            return out

        # even-odd assembly, same rule and same reason as hatch_fill: a closed
        # loop nested inside another is a HOLE, and XOR degenerates to union
        # for disjoint shapes so ordinary multi-shape layers are unaffected.
        region = shapes[0]
        for poly in shapes[1:]:
            region = region.symmetric_difference(poly)

        # XOR of shapes sharing an edge can leave stray lines in a collection;
        # reunite the polygon parts so what gets eroded is strictly areal
        level = _polygons(region)  # depth 0 — the outlines themselves
        if not level:
            return out
        levels = _forest(unary_union(level), params)
        if params.spiral:
            _emit_spirals(levels, params, out)
        else:
            _emit_rings(levels, params, out)
        return out
