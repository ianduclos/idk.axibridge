"""Portable frozen geometry for the Mosca 2 drawing bench.

The interactive engine lives in the bench. A kept layer stores its exact
placed strokes and interaction record, so resolving it needs no engine or
external recording.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source


BED_WIDTH = 300.0
BED_HEIGHT = 218.0
MAX_STROKES = 50_000
MAX_POINTS = 500_000
_HIDDEN = {"hidden": True}

X = Annotated[float, Field(ge=0.0, le=BED_WIDTH, allow_inf_nan=False)]
Y = Annotated[float, Field(ge=0.0, le=BED_HEIGHT, allow_inf_nan=False)]
StrokePoint = tuple[X, Y]
Strokes = list[list[StrokePoint]]


class RunSettings(BaseModel):
    """A bounded recipe for reopening a run in the browser engine."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    seed: int = Field(default=31, ge=1, le=999_999)
    duration_s: float = Field(default=6.0, ge=1.0, le=12.0)
    gesture_scale: float = Field(default=1.0, ge=0.5, le=2.0)
    contact_hz: float = Field(default=25.0, ge=0.0, le=100.0)
    start_x: float = Field(default=150.0, ge=2.0, le=298.0)
    start_y: float = Field(default=109.0, ge=2.0, le=216.0)
    heading_deg: float = Field(default=0.0, ge=-180.0, le=180.0)


class Mosca2Part(BaseModel):
    """One ordered, optionally visible part of the completed drawing."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    id: str = Field(min_length=1, max_length=80)
    label: str = Field(max_length=120)
    kind: Literal["territory", "flowing", "response"]
    visible: bool = True
    strokes: Strokes = Field(default_factory=list)
    provenance: str = Field(default="", max_length=1000)


class Mosca2Event(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    t_ms: float = Field(ge=0.0, le=12_000.0)
    kind: str = Field(max_length=40)
    detail: str = Field(default="", max_length=200)


class Mosca2History(BaseModel):
    """A recorded before/added exchange; retained for Resume, never redrawn."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    id: str = Field(min_length=1, max_length=80)
    label: str = Field(max_length=120)
    before: Strokes = Field(default_factory=list)
    added: Strokes = Field(default_factory=list)
    settings: RunSettings = Field(default_factory=RunSettings)
    summary: str = Field(default="", max_length=1000)
    provenance: str = Field(default="", max_length=10_000)
    events: list[Mosca2Event] = Field(default_factory=list, max_length=2000)


class Mosca2Params(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    parts: list[Mosca2Part] = Field(
        default_factory=list, max_length=32, json_schema_extra=_HIDDEN,
        title="Parts", description="Frozen placed strokes in drawing order",
    )
    history: list[Mosca2History] = Field(
        default_factory=list, max_length=12, json_schema_extra=_HIDDEN,
        title="History", description="Recorded exchanges for Resume",
    )
    settings: RunSettings = Field(
        default_factory=RunSettings, json_schema_extra=_HIDDEN,
        title="Settings", description="Settings for the next run",
    )
    engine: Literal["mosca2-v1"] = Field(
        default="mosca2-v1", json_schema_extra=_HIDDEN,
        title="Engine", description="Version of the browser drawing engine",
    )

    @model_validator(mode="after")
    def check_geometry_budget(self) -> "Mosca2Params":
        stroke_count = 0
        point_count = 0
        groups = (part.strokes for part in self.parts)
        historical = (strokes for record in self.history
                      for strokes in (record.before, record.added))
        for strokes in (*groups, *historical):
            stroke_count += len(strokes)
            if stroke_count > MAX_STROKES:
                raise ValueError(f"stroke budget exceeded ({MAX_STROKES})")
            point_count += sum(len(stroke) for stroke in strokes)
            if point_count > MAX_POINTS:
                raise ValueError(f"point budget exceeded ({MAX_POINTS})")
        return self


@register_source
class Mosca2Source(SourceModule):
    id = "mosca2"
    label = "Mosca 2"
    description = "Replay exact drawings kept from the Mosca 2 bench."
    orientation = "none"
    Params = Mosca2Params
    bench = {"adapter": "mosca2", "version": 1, "modes": ["new", "resume"]}
    library_bench = True

    def generate(self, params: Mosca2Params) -> PathDocument:
        layers = []
        for part in params.parts:
            if not part.visible:
                continue
            paths = [Path(points=list(stroke)) for stroke in part.strokes if stroke]
            layers.append(Layer(id=len(layers) + 1, name=part.label, paths=paths))
        return PathDocument(layers=layers, width=BED_WIDTH, height=BED_HEIGHT,
                            source=self.id)
