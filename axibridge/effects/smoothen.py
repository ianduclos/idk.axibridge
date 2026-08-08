"""Smoothen: re-curve a flattened polyline through its own points.

The roughness you see on a plotted curve is almost never the machine — that
was settled (2026-07-31): motor resolution is already high, and a visibly
faceted arc is *geometry* that arrived pre-flattened, from an SVG importer,
a boolean op, or a generator that walked a field in straight steps. The
vertices are honest samples of a smooth curve; what is missing is the curve
between them.

So this is Catmull-Rom, not an averaging filter. A Catmull-Rom spline
interpolates — it passes exactly through every control point and only
invents the arc in between — which means smoothing a flattened circle
returns it to being round rather than shrinking it toward its centroid,
and a shape carefully placed by hand keeps every vertex the hand put there.
Averaging kernels (the ``[1,2,1]/4`` pass in ``sources/misremembered.py``
and friends) do the opposite job: they move the points. Both are useful,
which is what ``relax`` is for — it runs that same averaging first, for
input whose vertices are genuinely noisy rather than merely sparse.

``resolution`` is in paper millimetres, per the resolve-order invariant:
effects run after the layer transform, so a mm here is a mm on the sheet at
any layer scale.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ..model import Path, Point
from ..registry import EffectContext, EffectModule, register_effect

#: Per-path ceiling on generated points. A 300mm path at 0.1mm resolution is
#: 3000 points; a pathological stack of them is what makes a plot file take
#: minutes to plan. Clamping degrades the curve to coarser — still smooth,
#: just fewer samples — which is the right failure: honest and still plottable.
MAX_POINTS = 20_000


class SmoothenParams(BaseModel):
    resolution: float = Field(
        default=0.5, ge=0.1, le=5.0, title="Resolution (mm)",
        description="Spacing of the generated points along the curve — smaller is smoother and heavier")
    relax: float = Field(
        default=0.0, ge=0.0, le=1.0, title="Relax",
        description="Blend each vertex toward its neighbours before curving. 0 passes exactly through the original points; raise it only for genuinely noisy input")
    alpha: float = Field(
        default=0.5, ge=0.0, le=1.0, title="Parameterisation",
        description="0 uniform, 0.5 centripetal (no cusps or self-intersection), 1 chordal",
        json_schema_extra={"group": "Fine tuning"})
    relax_passes: int = Field(
        default=1, ge=1, le=4, title="Relax passes",
        description="How many times to run the relax blend (no effect at relax 0)",
        json_schema_extra={"group": "Fine tuning"})


def _dedupe(points: list[Point]) -> list[Point]:
    """Drop consecutive duplicates.

    Not hygiene — a requirement. Centripetal parameterisation raises the chord
    length to a power and divides by the result, so one repeated point is a
    division by zero. Duplicates arrive routinely from shapely ops and from
    resampling at a step longer than a segment.
    """
    out: list[Point] = [points[0]]
    for p in points[1:]:
        if p != out[-1]:
            out.append(p)
    return out


def _relax(points: list[Point], amount: float, passes: int, closed: bool) -> list[Point]:
    """The ``[1,2,1]/4`` binomial pass, blended by ``amount``.

    Endpoints of an open path are pinned; a closed ring wraps, so the seam
    relaxes like every other vertex.
    """
    for _ in range(passes):
        if len(points) < 3:
            return points
        nxt: list[Point] = []
        n = len(points)
        for i in range(n):
            if not closed and (i == 0 or i == n - 1):
                nxt.append(points[i])
                continue
            a = points[(i - 1) % n]
            b = points[i]
            c = points[(i + 1) % n]
            sx = (a[0] + 2 * b[0] + c[0]) / 4
            sy = (a[1] + 2 * b[1] + c[1]) / 4
            nxt.append((b[0] + (sx - b[0]) * amount, b[1] + (sy - b[1]) * amount))
        points = nxt
    return points


def _knots(p0: Point, p1: Point, p2: Point, p3: Point, alpha: float) -> tuple[float, float, float, float]:
    """Parameter values for the four control points. alpha=0 uniform,
    0.5 centripetal, 1 chordal."""
    t0 = 0.0
    t1 = t0 + max(math.dist(p0, p1), 1e-9) ** alpha
    t2 = t1 + max(math.dist(p1, p2), 1e-9) ** alpha
    t3 = t2 + max(math.dist(p2, p3), 1e-9) ** alpha
    return t0, t1, t2, t3


def _span(p0: Point, p1: Point, p2: Point, p3: Point, alpha: float, segs: int) -> list[Point]:
    """Sample the Catmull-Rom arc from p1 to p2, EXCLUDING p2.

    Barry-Goldman pyramidal form: three lerps down to one point. Excluding the
    far end is what lets spans be concatenated without duplicating the joins —
    the caller appends the final point once, at the end.
    """
    t0, t1, t2, t3 = _knots(p0, p1, p2, p3, alpha)
    out: list[Point] = []
    for i in range(segs):
        t = t1 + (t2 - t1) * (i / segs)

        def lerp(a: Point, b: Point, ta: float, tb: float) -> Point:
            f = (t - ta) / (tb - ta)
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)

        a1 = lerp(p0, p1, t0, t1)
        a2 = lerp(p1, p2, t1, t2)
        a3 = lerp(p2, p3, t2, t3)
        b1 = lerp(a1, a2, t0, t2)
        b2 = lerp(a2, a3, t1, t3)
        out.append(lerp(b1, b2, t1, t2))
    return out


def _catmull_rom(points: list[Point], resolution: float, alpha: float, closed: bool) -> list[Point]:
    """Spline through every point. Closed rings wrap; open paths get phantom
    endpoints by reflection, so the true endpoints survive bit-identical and
    the curve leaves them with a sane tangent."""
    n = len(points)
    if closed:
        ctrl = [points[-1]] + points + [points[0], points[1]]
        spans = n
    else:
        head = (2 * points[0][0] - points[1][0], 2 * points[0][1] - points[1][1])
        tail = (2 * points[-1][0] - points[-2][0], 2 * points[-1][1] - points[-2][1])
        ctrl = [head] + points + [tail]
        spans = n - 1

    # budget the sample count before generating any of it
    total = sum(
        max(1, math.ceil(math.dist(ctrl[i + 1], ctrl[i + 2]) / resolution))
        for i in range(spans)
    )
    scale = min(1.0, MAX_POINTS / total) if total > MAX_POINTS else 1.0

    out: list[Point] = []
    for i in range(spans):
        p0, p1, p2, p3 = ctrl[i], ctrl[i + 1], ctrl[i + 2], ctrl[i + 3]
        segs = max(1, int(math.ceil(math.dist(p1, p2) / resolution) * scale))
        out += _span(p0, p1, p2, p3, alpha, segs)
    # every span excluded its far end, so close the sequence once, exactly.
    # The first sample is p1 evaluated at t == t1, which is p1 only up to lerp
    # rounding — overwrite it so an open path's endpoints come back bit-identical.
    out.append(points[0] if closed else points[-1])
    out[0] = points[0]
    return out


@register_effect
class Smoothen(EffectModule):
    id = "smoothen"
    label = "Smoothen"
    description = "Re-curve flattened polylines through their own points (Catmull-Rom)."
    Params = SmoothenParams

    def apply(self, paths: list[Path], params: SmoothenParams, ctx: EffectContext) -> list[Path]:
        out: list[Path] = []
        for path in paths:
            closed = path.is_closed
            pts = list(path.points)
            if closed:
                pts = pts[:-1]      # work on the ring; the repeat is re-added below
            pts = _dedupe(pts)
            if closed and len(pts) > 1 and pts[-1] == pts[0]:
                pts.pop()       # a ring that also repeated its seam vertex
            # a dot, a single segment, or a ring that deduped down to nothing
            # to curve through: pass it on untouched rather than inventing shape
            if len(pts) < 3:
                out.append(Path(points=list(path.points), filled=path.filled))
                continue
            if params.relax > 0:
                pts = _relax(pts, params.relax, params.relax_passes, closed)
            curve = _catmull_rom(pts, params.resolution, params.alpha, closed)
            if closed:
                # exact closure — occlusion masks depend on first == last
                curve[-1] = curve[0]
            out.append(Path(points=curve, filled=path.filled))
        return out
