"""Brush (● circle brush) — painted and erased blobs become a filled shape.

The third canvas tool, beside ``drawing`` (a stroke IS the line) and ``pen``
(anchors and handles). Here a stroke is a *mass*: drag a circle of a chosen
radius over the sheet and the swept area becomes one closed ``filled=True``
region. Painting again merges into it, erasing bites out of it. The brief is
``docs/plans/pen-brush-tools.md`` Part 2.

Geometry-as-params, exactly like its two siblings: the captured strokes live
in a hidden param, ``generate()`` is a pure function of them, and everything
downstream — occlusion, pens, estimates, undo, regions, A/B capture, tweening,
the master timeline — treats the result as an ordinary layer for free.

**The one correctness trap** (and the reason this is a fold, not a batch):
erasing must be applied **per stroke in chronological order**, never as
"union everything painted, then subtract everything erased". Those differ the
moment a later paint stroke re-covers an earlier erased spot — batching would
erase the re-paint too, because the subtraction has no idea it came second.
The fold gives the answer a person expects from history: paint, take a bite
out, paint back over it, and it is back. ``test_brush_source.py`` pins this
against a deliberately-wrong batched implementation.

Output is **every ring, exterior and interior, as its own closed
``filled=True`` path**. Nesting alone marks a hole — ``compose.build_mask``'s
even-odd depth-parity pass reassembles it, so a donut painted here occludes
as a ring with its hole open, and ``hatch_fill``/``offset_fill`` fill it as a
ring too. There is no hole flag to set and none is wanted (see ARCHITECTURE.md
and the IPR note in ROADMAP's documentation debts).

A brush layer is a *shape*, not ink: it plots as an outline until you stack a
fill on it. ``offset_fill`` is usually the better partner here —
concentric rings following the blob's own contour read as a painted mass,
where hatching reads as engraving — but both work and neither is assumed.

Per-point timestamps are captured and deliberately unused, the same bet
``drawing.py`` made before ``velocity_tube`` existed: a tapered brush (radius
driven by drawing speed, so a flick thins and a dwell swells) wants them, and
capturing now means that lands as a pure addition instead of a data migration.
Radius is stored **per stroke** rather than as one layer-wide dial for the
same reason a paint program does it: resizing the live cursor must not
retroactively rewrite strokes already committed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from shapely.geometry import LineString, Point, Polygon

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source

# Bed bounds mirror axibridge.compose.BED_WIDTH/BED_HEIGHT (not imported to
# avoid a sources -> compose dependency; compose never imports sources).
BED_WIDTH = 300.0
BED_HEIGHT = 218.0

# geometry-as-params: bounded like drawing.py's _MAX_POINTS. Each stroke costs
# a shapely buffer plus a union/difference against the accumulator, so this
# caps the fold's work, not just memory.
_MAX_POINTS = 30_000

#: a ring shorter than this (mm) is a numerical crumb from a boolean op.
_MIN_RING_LEN = 0.05

StrokePoint = tuple[float, float, float]


class BrushStroke(BaseModel):
    points: list[StrokePoint] = Field(default_factory=list)
    mode: Literal["paint", "erase"] = "paint"
    radius: float = Field(default=5.0, ge=0.3, le=50.0)


class BrushParams(BaseModel):
    strokes: list[BrushStroke] = Field(
        default_factory=list,
        title="Strokes",
        description="Captured brush strokes: [x_mm, y_mm, t_s] per point, "
                    "plus that stroke's own radius and paint/erase mode",
        json_schema_extra={"hidden": True},
    )
    grow: float = Field(
        default=0.0, ge=-10.0, le=10.0, title="Grow / shrink (mm)",
        description="Fatten (+) or thin (−) the finished mass. Applies once to "
                    "the merged result, so it never reopens seams between "
                    "overlapping strokes the way re-buffering each one would",
    )
    simplify: float = Field(
        default=0.1, ge=0.0, le=1.0, title="Simplify (mm)",
        description="Drop boundary vertices closer than this to the line they "
                    "sit on — a wide brush buffers to a lot of points",
        json_schema_extra={"group": "Fine tuning"},
    )
    smooth: int = Field(
        default=8, ge=2, le=16, title="Roundness detail",
        description="Arc segments per quarter circle on the brush's round cap",
        json_schema_extra={"group": "Fine tuning"},
    )


def _prepare_strokes(strokes: list[BrushStroke]) -> list[BrushStroke]:
    """Cap total density (raise) and clamp every point into the bed (never
    raise for a stray off-bed point — a regenerate must always succeed).
    Mirrors drawing.py's ``_prepare_strokes``."""
    total = sum(len(s.points) for s in strokes)
    if total > _MAX_POINTS:
        raise ValueError(f"brush too dense: {total} points (max {_MAX_POINTS})")
    out: list[BrushStroke] = []
    for s in strokes:
        if not s.points:
            continue
        out.append(BrushStroke(
            mode=s.mode,
            radius=s.radius,
            points=[
                (min(BED_WIDTH, max(0.0, float(x))),
                 min(BED_HEIGHT, max(0.0, float(y))),
                 max(0.0, float(t)))
                for x, y, t in s.points
            ],
        ))
    return out


def _stamp(stroke: BrushStroke, smooth: int):
    """The area one stroke sweeps: a disc for a click, a round-capped sausage
    for a drag. A single point is buffered as a ``Point`` rather than a
    zero-length ``LineString`` — shapely tolerates the latter, but a dab is a
    dot, and saying so keeps the degenerate case honest."""
    xy = [(x, y) for x, y, _ in stroke.points]
    if len(xy) == 1:
        return Point(xy[0]).buffer(stroke.radius, quad_segs=smooth)
    return LineString(xy).buffer(stroke.radius, quad_segs=smooth,
                                 cap_style="round", join_style="round")


def _fold(strokes: list[BrushStroke], smooth: int):
    """Replay the strokes in order. See the module docstring: this ordering is
    the whole correctness story, and batching the erases breaks it."""
    acc = None
    for stroke in strokes:
        stamp = _stamp(stroke, smooth)
        if stroke.mode == "paint":
            acc = stamp if acc is None else acc.union(stamp)
        elif acc is not None:
            acc = acc.difference(stamp)  # erase before any paint is a no-op
    return acc


def _rings(geom, simplify: float) -> list[list[tuple[float, float]]]:
    """Every ring of the folded region — exteriors and holes alike — as closed
    point lists. Holes stay implicit in the nesting; see the module docstring."""
    if geom is None or geom.is_empty:
        return []
    parts = geom.geoms if hasattr(geom, "geoms") else [geom]
    out: list[list[tuple[float, float]]] = []
    for poly in parts:
        if not isinstance(poly, Polygon) or poly.is_empty:
            continue
        for ring in [poly.exterior, *poly.interiors]:
            line = ring.simplify(simplify) if simplify > 0 else ring
            pts = [(x, y) for x, y in line.coords]
            if len(pts) < 4 or line.length < _MIN_RING_LEN:
                continue
            if pts[0] != pts[-1]:
                pts.append(pts[0])  # simplify can drop the closing repeat
            out.append(pts)
    return out


@register_source
class BrushSource(SourceModule):
    id = "brush"
    label = "Brush (painted mass)"
    description = "Painted and erased circle-brush strokes merged into filled shapes."
    Params = BrushParams

    def generate(self, params: BrushParams) -> PathDocument:
        strokes = _prepare_strokes(params.strokes)
        if not strokes:
            # a layer that exists with nothing captured is a client bug — but
            # painting everything and then erasing it all is a legitimate (if
            # useless) state, handled below by an empty fold, NOT by raising
            raise ValueError("paint a stroke first")
        region = _fold(strokes, params.smooth)
        if region is not None and not region.is_empty and params.grow != 0.0:
            region = region.buffer(params.grow, quad_segs=params.smooth,
                                   join_style="round")
        paths = [Path(points=ring, filled=True)
                 for ring in _rings(region, params.simplify)]
        return PathDocument(
            layers=[Layer(id=1, name="brush", paths=paths)],
            width=BED_WIDTH, height=BED_HEIGHT,
            source=f"brush {len(strokes)} stroke(s)",
        )
