"""Offset fill: fill a shape with concentric copies of itself, marching inward.

The other answer to "a pen cannot paint a solid". Where ``hatch_fill`` lays
parallel scanlines that ignore the outline's shape, this repeats the outline
*as* the fill — rings at a fixed mm spacing, each one the shape eroded a
little further. Circles fill with circles, squares with squares, and an
arbitrary blob fills with contour lines that read like a topographic map.

The whole effect is one operation: **erosion by a disk**. The ring at depth
``d`` is the boundary of the set of points at least ``d`` from the outline,
which shapely gives directly as ``buffer(-d)``. Ring ``k`` is the region
buffered by ``-k * spacing`` — computed from the ORIGINAL region every time,
never by eroding the previous ring, because iterative buffering accumulates
vertex noise and would progressively round the corners this effect exists to
preserve.

Topology is not a special case, which is the pleasant surprise here. Erosion
is defined for any shape of any genus; it simply does not always return one
closed curve. As the depth grows a component can **split** (a dumbbell pinches
at the waist), it can **vanish** (depth passes its inradius), and holes
**grow and merge** with each other or with the outside, opening a ring into a
strip. It can never do anything else: erosion never invents a hole and never
merges two components (erosion of a set is the complement of a dilation of its
complement, and dilation only ever merges), so the levels form a monotone
forest — one tree per starting component, branches only splitting or dying.
Nothing here has to *detect* those events: shapely handing back a
``MultiPolygon`` or an empty geometry IS the event.

Corners: for an INWARD offset it is the **reflex** (concave) vertices that
need a join decision, the mirror of the usual case. So an all-convex shape —
a square, Ian's easy case — comes out identical under every ``join_style``,
and the setting only bites where a shape turns back on itself (a star's inner
points). ``mitre`` keeps those sharp, which is what "repeats the shape" means.

Two things this shares with ``hatch_fill`` and must not diverge from:

* the fill is assembled **layer-wide**, not per path. A donut is two nested
  ``filled=True`` loops in the IPR, so the even-odd (``symmetric_difference``)
  pass that turns nesting into holes has to run BEFORE eroding — otherwise the
  hole cheerfully fills with rings. (``contract_expand`` offsets each path
  independently and is right to; its semantics are per-path.)
* inner rings are emitted ``filled=False``. They are closed, but marking them
  filled would let occlusion's depth-parity read the stack of rings as
  alternating solid/hole and the layer would occlude as *stripes*. The
  original outlines carry the layer's fill semantics, exactly as they do under
  hatching, and ``outline`` off gives up occluding as a solid the same way.

Not built yet, deliberately: a continuous **spiral**. One unbroken stroke only
exists for a component with no holes that never splits before it dies — a
topological disk that stays a disk. Anywhere else the pen must lift, which is
the ``connect_strokes`` problem over again (ink is permanent, a lift is
invisible). Rings first; the spiral rides on top of them later.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from shapely.geometry import Polygon
from shapely.ops import unary_union

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

#: × spacing: how far a medial tail must sit from the ring it grew out of to be
#: worth drawing. A limb that dies just AFTER a ring lands its centreline right
#: on top of that ring — three lines inside one spacing, which plots as a band
#: of doubled ink rather than as fill. Under this gap the limb is already inked.
_MIN_TAIL_GAP = 0.5


class OffsetFillParams(BaseModel):
    spacing: float = Field(default=2.0, ge=0.2, le=20.0, title="Spacing (mm)",
                           description="Gap between consecutive rings. Below the "
                                       "pen width the fill reads as solid ink")
    max_rings: int = Field(default=24, ge=1, le=200, title="Max rings",
                           description="Hard cap — a large shape at a fine "
                                       "spacing is a lot of geometry")
    join_style: Literal["mitre", "round", "bevel"] = Field(
        default="mitre", title="Corners",
        description="How rings turn at a concave corner: mitre keeps the "
                    "shape's own corners sharp, round softens them into "
                    "contour lines. Convex-only shapes (a square) look "
                    "identical under all three",
    )
    outline: bool = Field(default=True, title="Keep outline",
                          description="Off also stops the shape occluding as a solid")
    medial_tail: bool = Field(
        default=True, title="Close thin areas",
        description="When a part of the shape is too narrow for another whole "
                    "ring, draw one last ring down its middle instead of "
                    "leaving it hollow",
    )
    simplify: float = Field(default=0.05, ge=0.0, le=1.0, title="Simplify (mm)",
                            description="Drop ring vertices closer than this to "
                                        "the line they sit on — keeps traced "
                                        "artwork from exploding into points",
                            json_schema_extra={"group": "Fine tuning"})
    smooth: int = Field(default=8, ge=2, le=16, title="Corner detail",
                        description="Arc segments per quarter circle on rounded joins",
                        json_schema_extra={"group": "Fine tuning"})


def _erode(poly, distance: float, params: OffsetFillParams):
    """Erode by `distance` mm. Always from the caller's geometry, so the caller
    controls whether that is the original (rings) or a component (tails)."""
    return poly.buffer(-distance, quad_segs=params.smooth,
                       join_style=params.join_style, mitre_limit=_MITRE_LIMIT)


def _polygons(geom) -> list[Polygon]:
    """Flatten whatever buffer returned into the non-empty polygons in it."""
    if geom.is_empty:
        return []
    parts = geom.geoms if hasattr(geom, "geoms") else [geom]
    return [g for g in parts if isinstance(g, Polygon) and not g.is_empty]


def _rings(poly: Polygon, params: OffsetFillParams) -> list[list[Pt]]:
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


def _medial_tail(poly: Polygon, params: OffsetFillParams) -> list[list[Pt]]:
    """One last ring down the middle of a component about to disappear.

    `poly` survived its level but nothing survives the next one, so somewhere
    in (0, spacing) is the depth at which it finally vanishes. Bisect for a
    depth just short of that: the sliver there hugs the component's medial
    axis, and drawing it keeps a narrow limb from reading as a hollow outline.

    Eroding the component rather than the original region is exact, not an
    approximation — erosion by a disk is associative, so eroding a level-k
    component by t is the level-(k*spacing + t) geometry inside it.

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
        return []
    return _rings(best, params)


@register_effect
class OffsetFill(EffectModule):
    id = "offset_fill"
    label = "Offset fill"
    description = ("Fills closed filled shapes with concentric copies of their "
                   "own outline, stepping inward — contour lines instead of "
                   "hatching. Splits and holes are handled as they arise.")
    Params = OffsetFillParams

    def apply(self, paths: list[Path], params: OffsetFillParams,
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
        region = unary_union(level)
        for k in range(1, params.max_rings + 1):
            deeper = _polygons(_erode(region, k * params.spacing, params))
            if params.medial_tail:
                # a component of the previous level with nothing under it died
                # somewhere in this step; give it a centreline before moving on
                for poly in level:
                    if not any(d.intersects(poly) for d in deeper):
                        for ring in _medial_tail(poly, params):
                            out.append(Path(points=ring, filled=False))
            if not deeper:
                break
            for poly in deeper:
                for ring in _rings(poly, params):
                    out.append(Path(points=ring, filled=False))
            level = deeper
        return out
