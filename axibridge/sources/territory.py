"""Territory — the meander drawing bench (tools/territory-prototype, Version 10).

The engine is JavaScript and runs in the bench (axibridge/static/js/territory/);
Keep sends the drawn polylines here together with the recipe that made them.
This source only replays those frozen strokes: it is pure and never recomputes,
so a kept layer resolves identically on any machine, including the Pi. The
recipe travels with the layer so the bench can reopen it with every dial live
(the engine is deterministic: the same recipe redraws the same sheet).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source

BED_WIDTH = 300.0   # the engine draws on the bed's own 300 × 218 mm frame
BED_HEIGHT = 218.0
_MAX_POINTS = 250_000   # a 100 m sheet simplified at 0.05 mm stays well under this

StrokePoint = tuple[float, float]


class TerritoryRecipe(BaseModel):
    """The bench's dials; ranges mirror the bench (and the prototype page)."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    seed: int = Field(default=22, ge=1, le=999_999)
    complexity: float = Field(default=0.5, ge=0, le=1)
    drift: float = Field(default=0.6, ge=0.2, le=1)
    band: float = Field(default=1.0, ge=0.5, le=2)
    chaos: float = Field(default=0.5, ge=0, le=1)
    accents: float = Field(default=0.5, ge=0, le=1)
    bridges: float = Field(default=0.5, ge=0, le=1)
    history: float = Field(default=0.6, ge=0, le=1)
    density: float = Field(default=0.0, ge=0, le=1.5)
    cont: float = Field(default=0.5, ge=0, le=2, alias="continue")
    cover: float = Field(default=0.45, ge=0, le=1)
    planes: float = Field(default=0.15, ge=0, le=1)
    mutate: float = Field(default=1.0, ge=0, le=1.5)
    slash: float = Field(default=0.5, ge=0, le=2)
    surprise: float = Field(default=0.5, ge=0, le=2)
    ink: float = Field(default=40, ge=5, le=100)


class TerritoryParams(BaseModel):
    recipe: TerritoryRecipe = Field(
        default_factory=TerritoryRecipe, title="Recipe",
        description="Seed and dials that drew the strokes (reopened by the bench)",
        json_schema_extra={"hidden": True},
    )
    strokes: list[list[StrokePoint]] = Field(
        default_factory=list, title="Strokes",
        description="The drawn polylines, [x_mm, y_mm] per point, frozen at Keep",
        json_schema_extra={"hidden": True},
    )
    engine: str = Field(default="", max_length=40, title="Engine",
                        json_schema_extra={"hidden": True})


def _frozen_paths(strokes: list[list[StrokePoint]]) -> list[Path]:
    paths: list[Path] = []
    budget = _MAX_POINTS
    for stroke in strokes:
        if budget <= 0:
            break
        pts = [(min(max(float(x), 0.0), BED_WIDTH), min(max(float(y), 0.0), BED_HEIGHT))
               for x, y in stroke[:budget]]
        budget -= len(pts)
        if len(pts) >= 2:
            paths.append(Path(points=pts, filled=False))
    return paths


@register_source
class TerritorySource(SourceModule):
    id = "territory"
    label = "Territory"
    description = "Meandering channels, grown fields and cuts; drawn and kept from the Territory bench."
    orientation = "none"  # strokes are already in the bed's frame
    Params = TerritoryParams
    bench = {"adapter": "territory", "version": 1, "modes": ["new", "resume"]}
    library_bench = True

    def generate(self, params: TerritoryParams) -> PathDocument:
        paths = _frozen_paths(params.strokes)
        layers = [Layer(id=1, name="Territory", paths=paths)] if paths else []
        return PathDocument(layers=layers, width=BED_WIDTH, height=BED_HEIGHT, source="territory")
