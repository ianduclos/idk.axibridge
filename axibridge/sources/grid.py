"""Grid generator: ruled lines for registration sheets, graph paper, distortion
targets (pair it with an effect stack), or as raw material for moiré stacks.

Two plotter-specific knobs:

* ``border`` — drop the outermost lines of the grid while the remaining
  lines still span the full area, so the frame stays open.
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
    border: bool = Field(
        default=True, title="Outermost lines",
        description="Off: skip the first and last line of each direction — open frame",
    )
    overshoot_mm: float = Field(
        default=0.0, ge=0.0, le=30.0, title="Overshoot (mm)",
        description="Extend every line past the grid so pen-down starts land outside the figure",
    )
    margin: float = Field(default=15, ge=0, le=100, title="Margin (mm)")


@register_source
class Grid(SourceModule):
    id = "grid"
    label = "Grid"
    description = "Ruled grid with open-frame and overshoot options."
    Params = GridParams

    def generate(self, params: GridParams) -> PathDocument:
        p = params
        x0 = y0 = p.margin + p.overshoot_mm
        ov = p.overshoot_mm
        inner = range(1, p.cells_x) if not p.border else range(p.cells_x + 1)
        paths: list[Path] = []
        flip = False
        for i in inner:  # vertical lines, serpentine ordering
            x = x0 + p.width * i / p.cells_x
            ys = (y0 + p.height + ov, y0 - ov) if flip else (y0 - ov, y0 + p.height + ov)
            paths.append(Path(points=[(x, ys[0]), (x, ys[1])]))
            flip = not flip
        inner = range(1, p.cells_y) if not p.border else range(p.cells_y + 1)
        flip = False
        for j in inner:  # horizontal lines
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
