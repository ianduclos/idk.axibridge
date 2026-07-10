"""Bitmap — quantize a layer onto a coarse pixel grid, hard 90° corners.

The Oehlen regime effect (docs/IDEAS-oehlen-pass.md §1), two styles:

``lines`` (default) keeps every path's identity: each vertex snaps to the
nearest grid node (anchored at the layer translation) and consecutive nodes
are joined by axis-aligned staircase segments only — a freehand square comes
back as the same drawing forced onto graph paper, wobble turned into steps.
One input path → one output path, ``filled`` and closure carried through.

``blocks`` is the original raster treatment: paths are rasterized onto the
grid and re-emitted as the *merged filled staircase regions* of the lit
cells. Filled closed inputs also light their interior cells (``solid``) so
masses stay masses; output rings are closed with ``filled=True`` — holes
rely on the compositor's even-odd parity.

Contract notes: the grid is anchored to the layer's translation (dragging
the layer keeps its cells registered, same trick as coherent_jitter's noise
field), and staircase corner order is chosen from the underlying segment's
direction, so re-resolves are stable.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field
from shapely.geometry import Point as ShPoint, Polygon, box
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.validation import make_valid

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect

# interior fill stops above this many candidate cells per shape — a 0.5 mm
# cell over a bed-sized filled polygon is ~260k shapely queries; the strokes
# still bitmap, only the flood fill bows out
_MAX_FILL_CELLS = 150_000


class BitmapParams(BaseModel):
    style: Literal["lines", "blocks"] = Field(
        default="lines", title="Style",
        description="Lines: each path keeps its identity, snapped to hard "
                    "90° grid steps. Blocks: merged filled staircase regions "
                    "of the lit cells")
    cell: float = Field(default=2.0, ge=0.5, le=25.0, title="Cell (mm)",
                        description="Pixel size on the sheet — the aliasing step")
    solid: bool = Field(default=True, title="Fill solid shapes",
                        description="Blocks style only: filled closed paths "
                                    "light their interior cells too")


def _march(points: list[tuple[float, float]], step: float):
    """Yield points along the polyline at ≤ step spacing (endpoints included)."""
    if not points:
        return
    yield points[0]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        seg = math.dist((x0, y0), (x1, y1))
        n = max(1, math.ceil(seg / step))
        for k in range(1, n + 1):
            t = k / n
            yield (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)


@register_effect
class Bitmap(EffectModule):
    id = "bitmap"
    label = "Bitmap"
    description = ("Quantizes the layer onto a coarse pixel grid — lines "
                   "keep their identity but move only in hard 90° steps "
                   "(or blocks: merged filled staircase regions).")
    Params = BitmapParams

    def apply(self, paths: list[Path], params: BitmapParams, ctx: EffectContext) -> list[Path]:
        if params.style == "blocks":
            return self._blocks(paths, params, ctx)
        return self._lines(paths, params, ctx)

    # ---- lines: per-path Manhattan quantization ---------------------------------

    def _lines(self, paths: list[Path], params: BitmapParams, ctx: EffectContext) -> list[Path]:
        cell = params.cell
        ox, oy = ctx.translation

        def snap(x: float, y: float) -> tuple[float, float]:
            return (ox + round((x - ox) / cell) * cell,
                    oy + round((y - oy) / cell) * cell)

        out: list[Path] = []
        for path in paths:
            pts: list[tuple[float, float]] = [snap(*path.points[0])]

            def push(pt: tuple[float, float]) -> None:
                if pts[-1] != pt:
                    pts.append(pt)

            for (ax, ay), (bx, by) in zip(path.points, path.points[1:]):
                # corner order from the segment's own direction: a mostly-
                # horizontal segment routes x-first — deterministic, so
                # re-resolves are byte-stable
                x_first = abs(bx - ax) >= abs(by - ay)
                seg = math.dist((ax, ay), (bx, by))
                n = max(1, math.ceil(seg / (cell / 3.0)))
                for k in range(1, n + 1):
                    t = k / n
                    qx, qy = snap(ax + (bx - ax) * t, ay + (by - ay) * t)
                    px, py = pts[-1]
                    if (qx, qy) == (px, py):
                        continue
                    if qx != px and qy != py:  # diagonal hop → hard 90° step
                        push((qx, py) if x_first else (px, qy))
                    push((qx, qy))
            out.append(Path(points=pts, filled=path.filled))
        return out

    # ---- blocks: the original merged-raster treatment ---------------------------

    def _blocks(self, paths: list[Path], params: BitmapParams, ctx: EffectContext) -> list[Path]:
        cell = params.cell
        ox, oy = ctx.translation

        def cell_of(x: float, y: float) -> tuple[int, int]:
            return (math.floor((x - ox) / cell), math.floor((y - oy) / cell))

        lit: set[tuple[int, int]] = set()
        for path in paths:
            for x, y in _march(path.points, cell / 3.0):
                lit.add(cell_of(x, y))
            closed = len(path.points) > 3 and path.points[0] == path.points[-1]
            if not (params.solid and path.filled and closed):
                continue
            shape = Polygon(path.points)
            if not shape.is_valid:
                shape = make_valid(shape)
            minx, miny, maxx, maxy = shape.bounds
            i0, j0 = cell_of(minx, miny)
            i1, j1 = cell_of(maxx, maxy)
            if (i1 - i0 + 1) * (j1 - j0 + 1) > _MAX_FILL_CELLS:
                continue
            fast = prep(shape)
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    if (i, j) in lit:
                        continue
                    if fast.contains(ShPoint(ox + (i + 0.5) * cell, oy + (j + 0.5) * cell)):
                        lit.add((i, j))

        if not lit:
            return []
        merged = unary_union([
            box(ox + i * cell, oy + j * cell, ox + (i + 1) * cell, oy + (j + 1) * cell)
            for i, j in lit
        ])
        geoms = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
        geoms.sort(key=lambda g: (g.bounds[1], g.bounds[0]))  # stable draw order
        out: list[Path] = []
        for geom in geoms:
            out.append(Path(points=[(x, y) for x, y in geom.exterior.coords], filled=True))
            for ring in geom.interiors:
                out.append(Path(points=[(x, y) for x, y in ring.coords], filled=True))
        return out
