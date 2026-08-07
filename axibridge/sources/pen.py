"""Pen (Bezier anchors) — click/drag anchors on the canvas become a cubic-
Bezier subpath, flattened server-side into a generator layer's source
geometry (docs/plans/pen-brush-tools.md Part 1).

Same geometry-as-params shape as sources/drawing.py: the param model carries
CAPTURED anchors directly (already machine-frame mm), and generate() is pure
flattening with nothing to seed — see docs/MODULES.md "Geometry-as-params
sources".
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source

# Bed bounds mirror axibridge.compose.BED_WIDTH/BED_HEIGHT (not imported to
# avoid a sources -> compose dependency; compose never imports sources).
BED_WIDTH = 300.0
BED_HEIGHT = 218.0

# geometry-as-params: bounded like drawing.py's _MAX_POINTS — a regenerate
# must never hang on a stray huge paste of anchors. A few hundred anchors is
# a normal pen path; a few thousand is already absurd.
_MAX_ANCHORS = 2000

# de Casteljau adaptive flattening: bail to a straight p0->p3 segment past
# this depth rather than recursing forever on a degenerate curve.
_MAX_FLATTEN_DEPTH = 16

XY = tuple[float, float]


class PenAnchor(BaseModel):
    x: float
    y: float
    in_handle: tuple[float, float] | None = None   # delta from (x,y); None = no incoming curve
    out_handle: tuple[float, float] | None = None  # delta from (x,y); None = no outgoing curve


class PenSubpath(BaseModel):
    anchors: list[PenAnchor] = Field(default_factory=list)
    closed: bool = False


class PenParams(BaseModel):
    subpaths: list[PenSubpath] = Field(
        default_factory=list,
        title="Subpaths",
        description="Captured pen anchors, one PenSubpath per shape",
        json_schema_extra={"hidden": True},
    )
    flatten_tol: float = Field(
        default=0.2, ge=0.05, le=2.0, title="Flatten tolerance (mm)",
        description="Max deviation of the flattened polyline from the true curve",
    )


def _clamp_xy(x: float, y: float) -> XY:
    return (min(BED_WIDTH, max(0.0, float(x))), min(BED_HEIGHT, max(0.0, float(y))))


def _prepare_subpaths(subpaths: list[PenSubpath]) -> list[PenSubpath]:
    """Bed-clamp every anchor position (never trust the client, mirroring
    drawing.py's _prepare_strokes) and cap total anchor count."""
    total = sum(len(sp.anchors) for sp in subpaths)
    if total > _MAX_ANCHORS:
        raise ValueError(f"pen path too dense: {total} anchors (max {_MAX_ANCHORS})")
    out = []
    for sp in subpaths:
        anchors = []
        for a in sp.anchors:
            x, y = _clamp_xy(a.x, a.y)
            anchors.append(PenAnchor(x=x, y=y, in_handle=a.in_handle, out_handle=a.out_handle))
        out.append(PenSubpath(anchors=anchors, closed=sp.closed))
    return out


def _lerp(a: XY, b: XY, t: float) -> XY:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _point_line_dist(p: XY, a: XY, b: XY) -> float:
    """Perpendicular distance of `p` from the line through a->b; falls back
    to point-to-point distance from `a` when a==b (degenerate chord)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    if d < 1e-12:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    return abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / d


def _subdivide(p0: XY, p1: XY, p2: XY, p3: XY, t: float = 0.5):
    p01, p12, p23 = _lerp(p0, p1, t), _lerp(p1, p2, t), _lerp(p2, p3, t)
    p012, p123 = _lerp(p01, p12, t), _lerp(p12, p23, t)
    p0123 = _lerp(p012, p123, t)
    return (p0, p01, p012, p0123), (p0123, p123, p23, p3)


def _flatten_cubic(p0: XY, p1: XY, p2: XY, p3: XY, tol: float, depth: int = 0) -> list[XY]:
    """Recursive de Casteljau subdivision. Returns points AFTER p0, ending at
    p3 — callers concatenate segment flattenings anchor-to-anchor without
    duplicating the shared endpoint (the standard flatness test: max
    deviation of the two inner control points from the p0-p3 chord)."""
    flat = max(_point_line_dist(p1, p0, p3), _point_line_dist(p2, p0, p3)) <= tol
    if flat or depth >= _MAX_FLATTEN_DEPTH:
        return [p3]
    left, right = _subdivide(p0, p1, p2, p3)
    return _flatten_cubic(*left, tol, depth + 1) + _flatten_cubic(*right, tol, depth + 1)


def _flatten_subpath(sp: PenSubpath, tol: float) -> list[XY]:
    anchors = sp.anchors
    pairs = list(zip(anchors, anchors[1:]))
    if sp.closed and len(anchors) >= 2:
        pairs.append((anchors[-1], anchors[0]))
    if not pairs:
        return [(a.x, a.y) for a in anchors]
    points = [(anchors[0].x, anchors[0].y)]
    for a, b in pairs:
        p0 = (a.x, a.y)
        p1 = (a.x + a.out_handle[0], a.y + a.out_handle[1]) if a.out_handle else p0
        p2 = (b.x + b.in_handle[0], b.y + b.in_handle[1]) if b.in_handle else (b.x, b.y)
        p3 = (b.x, b.y)
        points.extend(_flatten_cubic(p0, p1, p2, p3, tol))
    return points


@register_source
class PenSource(SourceModule):
    id = "pen"
    orientation = "none"  # the anchors are where the user put them, already in their frame
    label = "Pen (anchors)"
    description = "Bezier anchor/handle paths drawn with the pen tool."
    Params = PenParams

    def generate(self, params: PenParams) -> PathDocument:
        subpaths = _prepare_subpaths(params.subpaths)
        if not subpaths:
            # an empty layer is a deliberate state ("＋ empty layer" button):
            # a blank target the pen tool appends subpaths into
            return PathDocument(layers=[], width=BED_WIDTH, height=BED_HEIGHT,
                                source="pen (empty)")
        paths: list[Path] = []
        for sp in subpaths:
            pts = _flatten_subpath(sp, params.flatten_tol)
            if sp.closed and pts:
                pts = pts[:-1] + [pts[0]]  # snap don't rely on float equality
                paths.append(Path(points=pts, filled=True))
            else:
                paths.append(Path(points=pts, filled=False))
        return PathDocument(
            layers=[Layer(id=1, name="pen", paths=paths)],
            width=BED_WIDTH, height=BED_HEIGHT,
            source=f"pen {len(paths)} subpath(s)",
        )
