"""Solid rectangle generator."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source


class RectangleParams(BaseModel):
    width: float = Field(default=100.0, ge=1.0, le=400.0, title="Width (mm)")
    height: float = Field(default=70.0, ge=1.0, le=400.0, title="Height (mm)")
    margin: float = Field(default=0.0, ge=0.0, le=100.0, title="Margin (mm)")
    filled: bool = Field(default=True, title="Filled (solid occlusion mask)",
                         description="Off = outline only; masks as a stroke band when occluding")


@register_source
class RectangleSource(SourceModule):
    id = "rectangle"
    orientation = "geometry"  # width x height, and width should mean the width you see
    label = "Rectangle"
    description = "Closed rectangle, filled by default for solid masks and simple blocks."
    Params = RectangleParams

    def generate(self, params: RectangleParams) -> PathDocument:
        p = params
        x0 = y0 = p.margin
        x1 = x0 + p.width
        y1 = y0 + p.height
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        return PathDocument(
            layers=[Layer(id=1, name="rectangle", color="#26241f",
                          paths=[Path(points=pts, filled=p.filled)])],
            width=p.width + 2 * p.margin,
            height=p.height + 2 * p.margin,
            source=f"rectangle {p.width:g}x{p.height:g}",
        )
