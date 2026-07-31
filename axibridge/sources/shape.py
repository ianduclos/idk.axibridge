"""Shape (add/subtract) — the tool-agnostic boolean-mass layer.

The fourth canvas-tool source and the convergence point of its three
siblings. ``drawing``/``pen``/``brush`` layers each capture one tool's
gestures; a shape layer captures *operations on one shared ink mass*:
every op is a brush stroke (a swept disc-sausage) or a pen subpath (a
bézier silhouette, implicitly closed) with a mode — ``add`` unions it
onto the mass, ``subtract`` bites it out. The pen and brush tools both
append here, so you can erase out of a pen shape, or pen a clean cut
into a brushed blob, without the layer changing type under you.

This module is what plain pen/brush layers CONVERT into the moment you do
something their storage can't say (``Session.append_shape_op``): the
existing content becomes the leading ``add`` ops, the new gesture is the
next op, and from then on the layer speaks ops. Plain pen layers keep
their anchor re-editing, plain brush layers stay lightweight — conversion
only happens on demand.

Like brush.py, the fold replays ops **in chronological order** — never
"union all adds, then subtract all subtracts": a later add must be able
to re-cover an earlier bite (the correctness trap brush.py's docstring
details; the same test philosophy pins it here).

Geometry-as-params, same contract as its siblings: the ops live in a
hidden param, ``generate()`` is a pure re-fold, and undo/ occlusion /
pens / estimates / tweening all treat the result as an ordinary layer.
Because the ops are data (not a baked bitmap of the region), re-editing
an op later — pen anchors included — is a re-fold away, not a migration.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field
from shapely.geometry import Polygon

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source
from .brush import BED_HEIGHT, BED_WIDTH, StrokePoint, _prepare_strokes, _rings, _stamp
from .brush import BrushStroke as _BrushStroke
from .pen import PenAnchor, PenSubpath, _flatten_subpath, _prepare_subpaths


class BrushOp(BaseModel):
    """One swept brush stroke — the same geometry brush.py captures."""
    kind: Literal["brush"] = "brush"
    mode: Literal["add", "subtract"] = "add"
    points: list[StrokePoint] = Field(default_factory=list)
    radius: float = Field(default=5.0, ge=0.3, le=50.0)


class PenOp(BaseModel):
    """One pen subpath used as a silhouette. ``closed`` records how the
    gesture ended, but the region semantics always close it — an open path
    is its own implicit silhouette (last anchor straight back to first,
    honouring the first anchor's in-handle, exactly like a closed pen
    subpath flattens)."""
    kind: Literal["pen"] = "pen"
    mode: Literal["add", "subtract"] = "add"
    anchors: list[PenAnchor] = Field(default_factory=list)
    closed: bool = False


ShapeOp = Annotated[BrushOp | PenOp, Field(discriminator="kind")]


class ShapeParams(BaseModel):
    ops: list[ShapeOp] = Field(
        default_factory=list,
        title="Ops",
        description="Chronological add/subtract operations (brush strokes and "
                    "pen silhouettes) folded into one ink mass",
        json_schema_extra={"hidden": True},
    )
    grow: float = Field(
        default=0.0, ge=-10.0, le=10.0, title="Grow / shrink (mm)",
        description="Fatten (+) or thin (−) the finished mass. Applies once to "
                    "the merged result, so it never reopens seams between "
                    "overlapping ops the way re-buffering each one would",
    )
    simplify: float = Field(
        default=0.1, ge=0.0, le=1.0, title="Simplify (mm)",
        description="Drop boundary vertices closer than this to the line they sit on",
        json_schema_extra={"group": "Fine tuning"},
    )
    smooth: int = Field(
        default=8, ge=2, le=16, title="Roundness detail",
        description="Arc segments per quarter circle on brush caps and joins",
        json_schema_extra={"group": "Fine tuning"},
    )
    flatten_tol: float = Field(
        default=0.2, ge=0.05, le=2.0, title="Pen flatten tolerance (mm)",
        description="Max deviation of flattened pen silhouettes from the true curve",
        json_schema_extra={"group": "Fine tuning"},
    )


def _op_geometry(op: ShapeOp, p: ShapeParams):
    """The shapely region one op contributes, before folding."""
    if isinstance(op, BrushOp):
        # run through brush.py's preparation for bed-clamping and the shared
        # density cap — mode is irrelevant to the stamp, the fold owns modes
        [stroke] = _prepare_strokes(
            [_BrushStroke(points=op.points, radius=op.radius)]) or [None]
        if stroke is None:
            return None
        return _stamp(stroke, p.smooth)
    [sp] = _prepare_subpaths(
        [PenSubpath(anchors=op.anchors, closed=True)]) or [None]
    if sp is None:
        return None
    pts = _flatten_subpath(sp, p.flatten_tol)
    if len(pts) < 3:
        return None
    poly = Polygon(pts)
    if not poly.is_valid:  # self-intersecting silhouette — take its even-odd core
        poly = poly.buffer(0)
    return poly if not poly.is_empty else None


def _fold_ops(ops: list[ShapeOp], p: ShapeParams):
    """Replay the ops in order. See the module docstring: this ordering is
    the whole correctness story, and batching the subtracts breaks it."""
    acc = None
    for op in ops:
        geom = _op_geometry(op, p)
        if geom is None or geom.is_empty:
            continue
        if op.mode == "add":
            acc = geom if acc is None else acc.union(geom)
        elif acc is not None:
            acc = acc.difference(geom)  # subtract before any add is a no-op
    return acc


@register_source
class ShapeSource(SourceModule):
    id = "shape"
    label = "Shape (add/subtract)"
    description = ("One ink mass the pen and brush tools both add to and "
                   "subtract from — chronological boolean ops, folded.")
    Params = ShapeParams

    def generate(self, params: ShapeParams) -> PathDocument:
        if not params.ops:
            # an empty layer is a deliberate state ("＋ empty layer" button):
            # the tool-agnostic blank target both tools commit ops into
            return PathDocument(layers=[], width=BED_WIDTH, height=BED_HEIGHT,
                                source="shape (empty)")
        region = _fold_ops(params.ops, params)
        if region is not None and not region.is_empty and params.grow != 0.0:
            region = region.buffer(params.grow, quad_segs=params.smooth,
                                   join_style="round")
        paths = [Path(points=ring, filled=True)
                 for ring in _rings(region, params.simplify)]
        return PathDocument(
            layers=[Layer(id=1, name="shape", paths=paths)],
            width=BED_WIDTH, height=BED_HEIGHT,
            source=f"shape {len(params.ops)} op(s)",
        )
