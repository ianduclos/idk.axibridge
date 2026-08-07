"""Grid generator: ruled lines for registration sheets, graph paper, distortion
targets (pair it with an effect stack), or as raw material for moiré stacks.

Two plotter-specific knobs:

* ``trim`` — drop the N outermost lines from each side of each direction
  while the remaining lines still span the full area, so the frame opens up
  progressively (1 reproduces the old "no border" look).
* ``overshoot_mm`` — extend every line past the grid area, putting the
  pen-down start (where ink blobs and servo wobble live) outside the figure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source


class GridParams(BaseModel):
    width: float = Field(default=160, ge=5, le=400, title="Width (mm)")
    height: float = Field(default=120, ge=5, le=400, title="Height (mm)")
    cells_x: int = Field(default=8, ge=1, le=200, title="Columns")
    cells_y: int = Field(default=6, ge=1, le=200, title="Rows")
    trim: int = Field(
        default=0, ge=0, le=40, title="Trim outer lines",
        description="Drop this many lines from each side of each direction — 1 opens the frame",
    )
    overshoot_mm: float = Field(
        default=0.0, ge=0.0, le=30.0, title="Overshoot (mm)",
        description="Extend every line past the grid so pen-down starts land outside the figure",
    )
    margin: float = Field(default=15, ge=0, le=100, title="Margin (mm)")


@register_source
class Grid(SourceModule):
    id = "grid"
    orientation = "geometry"  # a width x height ruled field: 'width' should mean the width you see
    label = "Grid"
    description = "Ruled grid with open-frame and overshoot options."
    Params = GridParams

    def generate(self, params: GridParams) -> PathDocument:
        p = params
        x0 = y0 = p.margin + p.overshoot_mm
        ov = p.overshoot_mm
        paths: list[Path] = []
        flip = False
        for i in range(p.trim, p.cells_x + 1 - p.trim):  # vertical lines, serpentine
            x = x0 + p.width * i / p.cells_x
            ys = (y0 + p.height + ov, y0 - ov) if flip else (y0 - ov, y0 + p.height + ov)
            paths.append(Path(points=[(x, ys[0]), (x, ys[1])]))
            flip = not flip
        flip = False
        for j in range(p.trim, p.cells_y + 1 - p.trim):  # horizontal lines
            y = y0 + p.height * j / p.cells_y
            xs = (x0 + p.width + ov, x0 - ov) if flip else (x0 - ov, x0 + p.width + ov)
            paths.append(Path(points=[(xs[0], y), (xs[1], y)]))
            flip = not flip
        return PathDocument(
            layers=[Layer(id=1, name="grid", color="#444444", paths=paths)],
            width=p.width + 2 * (p.margin + ov),
            height=p.height + 2 * (p.margin + ov),
            source=f"grid {p.cells_x}x{p.cells_y}",
        )
