"""Hatch fill: turn ``filled`` shapes into plottable line fill.

The preview can paint a fill; a pen cannot — hatching is how a plotter says
"solid". Every closed+filled path in the layer grows a set of parallel lines
clipped to its interior (optionally crosshatched, optionally inset so wet ink
doesn't bleed past the outline). Open / unfilled paths pass through untouched.

The original outlines are kept by default and keep their ``filled`` flag —
occlusion masks are built from filled outlines downstream of the effect
stack, so removing them (``outline`` off) also stops the layer occluding as
a solid. That is sometimes exactly what you want; now you know.

Hatch geometry via shapely (already the occlusion engine): rotate the shape
so hatches are horizontal scanlines, clip, rotate back. Scanlines alternate
direction so the pen serpentines instead of always homing to one side.

``connect_strokes`` (off by default) goes one step further: adjacent
scanlines still lift the pen between them normally, since each is its own
``Path`` — turning it on merges them into one continuous stroke wherever a
connector between them can stay inside the shape. The rule the whole join
turns on is that **ink is permanent and a pen lift is invisible**, so a
connector may only draw where the drawing already is:

* a *short* straight hop is free — it reads as the fill turning at the edge;
* anything longer has to ride the shape's own boundary ("boundary hugging"),
  walking the ring between the two endpoints so the ink lands on the
  outline. This is also the answer at a concave notch or a cusp, where the
  straight hop leaves the shape entirely and the old straight-only join gave
  up (leaving the loose ends v1 was reported for);
* if even the hug would be a real detour — circling a hole, say — the pen
  lifts, exactly as before.

The search is greedy rather than strictly in scan order: each stroke absorbs
the nearest reachable line within a short window ahead of it (either end
first, so a line may be walked in reverse), which recovers the joins that
strict order misses around a notch. A crosshatch's two angle passes are
never joined to each other.
"""

from __future__ import annotations

import bisect
import math

from pydantic import BaseModel, Field
from shapely import affinity
from shapely.geometry import LineString, LinearRing, Point, Polygon
from shapely.prepared import prep

from ..model import Path, is_closed
from ..registry import EffectContext, EffectModule, register_effect

Pt = tuple[float, float]


class HatchFillParams(BaseModel):
    spacing: float = Field(default=2.0, ge=0.2, le=20.0, title="Spacing (mm)")
    angle_deg: float = Field(default=45.0, ge=0.0, le=180.0, title="Angle (degrees)",
                             json_schema_extra={"viewAngle": 180})
    cross: bool = Field(default=False, title="Crosshatch",
                        description="Second pass at 90° to the first")
    inset: float = Field(default=0.3, ge=0.0, le=10.0, title="Inset (mm)",
                         description="Pull hatching in from the outline")
    outline: bool = Field(default=True, title="Keep outline",
                          description="Off also stops the shape occluding as a solid")
    connect_strokes: bool = Field(
        default=False, title="Connect strokes",
        description="Join hatch lines into one continuous stroke wherever a "
                    "connector can stay inside the shape — straight if it "
                    "fits, otherwise hugging the boundary for a short hop. "
                    "Cuts pen lifts. A crosshatch's two passes never join "
                    "to each other.",
    )
    min_stroke: float = Field(
        default=0.0, ge=0.0, le=5.0, title="Min stroke (mm)",
        description="Drop hatch fragments shorter than this — the slivers a "
                    "sharp cusp leaves behind, each otherwise its own pen lift. "
                    "0 keeps every fragment.",
    )


def _hatch(poly: Polygon, spacing: float, angle_deg: float,
           min_length: float = 0.0) -> list[list[Pt]]:
    """Parallel lines at `angle_deg`, clipped to `poly`, serpentine-ordered."""
    cx, cy = poly.centroid.x, poly.centroid.y
    flat = affinity.rotate(poly, -angle_deg, origin=(cx, cy))
    minx, miny, maxx, maxy = flat.bounds
    keep = max(min_length, 1e-9)
    segments: list[LineString] = []
    y = miny + spacing / 2
    flip = False
    while y < maxy:
        scan = LineString([(minx - 1, y), (maxx + 1, y)])
        clipped = flat.intersection(scan)
        # MultiLineString or GeometryCollection (tangencies add Points)
        parts = getattr(clipped, "geoms", [clipped])
        row = [g for g in parts if isinstance(g, LineString) and g.length > keep]
        row.sort(key=lambda g: g.bounds[0], reverse=flip)
        segments.extend(LineString(g.coords[::-1]) if flip else g for g in row)
        flip = not flip
        y += spacing
    out = []
    for seg in segments:
        back = affinity.rotate(seg, angle_deg, origin=(cx, cy))
        out.append([(x, y) for x, y in back.coords])
    return out


#: containment tolerance for the connect-strokes join test — float noise from
#: the rotate/intersection round-trip, never a real geometric distance
_JOIN_EPS = 1e-6

#: how far off a boundary ring an endpoint may sit and still count as "on" it.
#: Hatch endpoints are clipped against that very boundary, so this only has to
#: absorb the rotate round-trip's float noise — it is not a search radius.
_ON_RING_TOL = 1e-4

#: × spacing: the most EXTRA inked travel a boundary hug may add over the
#: straight hop it replaces. A pen lift costs a roughly fixed amount of time,
#: so a hug that adds a couple of hatch spacings is a clear win — while one
#: that adds far more (walking the whole way around a hole, say) is not, and
#: those still fall back to a real lift. Additive rather than a ratio: the
#: gaps worth hugging across are often tiny (cusp slivers), where any ratio
#: cutoff either rejects everything or licenses an arbitrarily long tour.
_DETOUR_EXTRA = 2.0

#: × spacing: how long a straight connector may be before it has to justify
#: itself as a boundary walk instead. Under this it reads as the fill turning
#: at the edge; over it, a chord across the interior is a visible stray line —
#: and since ink is permanent while a pen LIFT is invisible, such a hop has to
#: earn its place by riding the boundary (where an empty hug arc means the
#: straight line IS the edge and it is taken as-is). Generous, because a hatch
#: angle close to an edge's own angle legitimately spaces consecutive rows far
#: apart along that edge.
_STRAIGHT_SPAN = 4.0

#: how many not-yet-joined lines ahead in scan order the greedy join may
#: consider. Strict scan order misses joins near a notch or hole, where the
#: nearest reachable line is not the next one; an unbounded search would
#: instead scatter the fill's stroke order (and cost O(n²) containment tests).
_JOIN_WINDOW = 8


class _Ring:
    """A boundary ring with its vertices indexed by arc length, so a hug can
    slice the stretch between two points by bisection instead of re-walking
    the whole ring — the fill's hot loop asks this thousands of times."""

    def __init__(self, ring: LinearRing) -> None:
        self.ring = ring
        verts = list(ring.coords)  # closed ring: last vertex repeats the first
        self.verts: list[Pt] = [(float(x), float(y)) for x, y in verts[:-1]]
        self.cum: list[float] = []
        run = 0.0
        for a, b in zip(verts, verts[1:]):
            self.cum.append(run)
            run += math.dist(a, b)
        self.total = run
        self.minx, self.miny, self.maxx, self.maxy = ring.bounds

    def holds(self, pt: Point) -> bool:
        # bbox first: `distance` walks the whole ring, and a hole's box rejects
        # most of the shape's endpoints outright
        if not (self.minx - _ON_RING_TOL <= pt.x <= self.maxx + _ON_RING_TOL
                and self.miny - _ON_RING_TOL <= pt.y <= self.maxy + _ON_RING_TOL):
            return False
        return self.ring.distance(pt) <= _ON_RING_TOL

    def _forward(self, start: float, span: float) -> list[Pt]:
        """Vertices strictly between arc-length `start` and `start + span`,
        wrapping past the ring's seam."""
        lo, hi = start + _JOIN_EPS, start + span - _JOIN_EPS
        if hi <= self.total:
            i, j = bisect.bisect_left(self.cum, lo), bisect.bisect_right(self.cum, hi)
            return self.verts[i:j]
        i = bisect.bisect_left(self.cum, lo)
        j = bisect.bisect_right(self.cum, hi - self.total)
        return self.verts[i:] + self.verts[:j]

    def arcs(self, p0: Pt, p1: Pt, max_span: float) -> list[list[Pt]]:
        """Walks between the ring points nearest `p0` and `p1` that are no
        longer than `max_span`, shorter first, as interior-vertex lists
        (endpoints excluded — the caller has them already). The span is the
        arc's own length, so this rejects a too-long detour without ever
        materialising it."""
        if self.total <= _JOIN_EPS:
            return []
        d0 = self.ring.project(Point(p0))
        d1 = self.ring.project(Point(p1))
        span = (d1 - d0) % self.total
        # the far arc is walked from p1's end, so its vertices come out backwards
        both = sorted([(span, d0, False), (self.total - span, d1, True)])
        out = []
        for length, start, rev in both:
            if length > max_span:
                continue
            walk = self._forward(start, length)
            out.append(list(reversed(walk)) if rev else walk)
        return out


def _connector(cover, rings: list[_Ring], p0: Pt, p1: Pt,
               spacing: float) -> list[Pt] | None:
    """Interior points of a connector from `p0` to `p1` that stays inside the
    shape, or None if the pen has to lift. Empty list = a straight hop works."""
    straight = LineString([p0, p1])
    if straight.length <= _JOIN_EPS:
        return []
    shared: _Ring | None = None
    looked = False

    def shared_ring() -> _Ring | None:
        """The ring both endpoints sit on, found at most once (each miss walks
        a ring's whole vertex list)."""
        nonlocal shared, looked
        if not looked:
            looked = True
            a, b = Point(p0), Point(p1)
            shared = next((r for r in rings if r.holds(a) and r.holds(b)), None)
        return shared

    if straight.length <= _STRAIGHT_SPAN * spacing and cover.covers(straight):
        return []  # a short hop reads as the fill turning, not a stray line
    # Either the straight left the shape (a notch, a cusp, a hole) or it is long
    # enough that cutting across the fill would ink a line the design never
    # asked for. Both are better served by walking the boundary the endpoints
    # sit on — that ink lands on the outline. Endpoints on different rings
    # can't be walked between at all.
    ring = shared_ring()
    if ring is None:
        return None
    budget = straight.length + _DETOUR_EXTRA * spacing
    for arc in ring.arcs(p0, p1, budget):
        # an empty arc means no vertex lies between the two: the boundary here
        # IS the straight line, so the long hop rides the edge after all
        hug = LineString([p0, *arc, p1])
        if hug.length > budget:
            continue  # a detour that long is worse than the lift it saves
        if cover.covers(hug):
            return arc
    return None


def _join_where_possible(
    sub: Polygon, lines: list[list[Pt]], spacing: float
) -> list[list[Pt]]:
    """Merge serpentine-ordered scanlines into continuous polylines wherever a
    connector between them can stay inside `sub` — turning an otherwise
    unavoidable pen lift into inked travel where the geometry allows it.

    Greedy: each stroke keeps absorbing the nearest reachable line within a
    short window ahead of it (either end first, so a line may be walked in
    reverse), and only starts a new stroke — a real lift — when nothing in
    that window is reachable at all."""
    if not lines:
        return lines
    # +eps absorbs the rotate/clip round-trip's float noise; it also shrinks
    # holes by eps, so a connector riding exactly along a hole edge counts as
    # inside. Prepared: the greedy search runs many containment tests.
    cover = prep(sub.buffer(_JOIN_EPS))
    rings = [_Ring(sub.exterior), *(_Ring(r) for r in sub.interiors)]
    remaining = [list(line) for line in lines]
    out: list[list[Pt]] = []
    while remaining:
        stroke = remaining.pop(0)
        while remaining:
            tail = stroke[-1]
            # nearest endpoint first; (index, reversed) keeps ties deterministic
            candidates = sorted(
                (math.dist(tail, line[-1] if rev else line[0]), i, rev)
                for i, line in enumerate(remaining[:_JOIN_WINDOW])
                for rev in (False, True)
            )
            joined = False
            for _, i, rev in candidates:
                line = remaining[i]
                conn = _connector(cover, rings, tail, line[-1] if rev else line[0], spacing)
                if conn is None:
                    continue
                remaining.pop(i)
                stroke.extend(conn)
                stroke.extend(reversed(line) if rev else line)
                joined = True
                break
            if not joined:
                break
        out.append(stroke)
    return out


@register_effect
class HatchFill(EffectModule):
    id = "hatch_fill"
    label = "Hatch fill"
    description = "Fill closed filled shapes with clipped parallel/cross hatching."
    Params = HatchFillParams

    def apply(self, paths: list[Path], params: HatchFillParams, ctx: EffectContext) -> list[Path]:
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
        # even-odd assembly: a closed loop nested inside another is a HOLE
        # (image-threshold traces holes as their own loops) — XOR is the
        # standard even-odd fill rule and degenerates to union for disjoint
        # shapes, so plain multi-shape layers behave as before
        region = shapes[0]
        for poly in shapes[1:]:
            region = region.symmetric_difference(poly)
        if params.inset > 0:
            region = region.buffer(-params.inset)
        polys = region.geoms if hasattr(region, "geoms") else [region]
        angles = [params.angle_deg]
        if params.cross:
            angles.append(math.fmod(params.angle_deg + 90.0, 180.0))
        for sub in polys:
            if not isinstance(sub, Polygon) or sub.is_empty:
                continue
            for a in angles:
                lines = _hatch(sub, params.spacing, a, params.min_stroke)
                if params.connect_strokes:
                    # per (sub, angle) pass only — a crosshatch's two passes
                    # never join to each other, they're unrelated directions
                    lines = _join_where_possible(sub, lines, params.spacing)
                for line in lines:
                    if len(line) >= 2:
                        out.append(Path(points=line, filled=False))
        return out
