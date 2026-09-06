"""An additive drawing whose future can be changed without rewriting its past.

Events belong to the saved recipe, not the UI session. Each turn owns an RNG
stream; neither inspecting a later turn nor adding an event in its future can
perturb an earlier decision. See docs/plans/second-reading.md for the artistic
hypothesis and the limits of this first vocabulary.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..model import Layer, Path, PathDocument
from ..process import ProcessModule, Step
from ..registry import register_source
from . import _second_reading as engine

MAX_SEED = 2_147_483_647


class StrokeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    kind: Literal["stroke"]
    turn: int = Field(ge=1, le=64)
    points: list[tuple[float, float]] = Field(min_length=2, max_length=20_000)
    smoothing: float = Field(default=0, ge=0, le=1)


class ControlsEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    kind: Literal["controls"]
    turn: int = Field(ge=1, le=64)
    persistence: float | None = Field(default=None, ge=0, le=1)
    reach: float | None = Field(default=None, ge=0, le=1)
    recurrence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def has_change(self):
        if self.persistence is None and self.reach is None and self.recurrence is None:
            raise ValueError("A controls event must specify persistence, reach or recurrence")
        return self


class BranchEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["branch"]
    turn: int = Field(ge=1, le=64)
    seed: int = Field(ge=0, le=MAX_SEED)


Event = Annotated[StrokeEvent | ControlsEvent | BranchEvent, Field(discriminator="kind")]


class SecondReadingParams(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    turns: int = Field(default=12, ge=0, le=64, title="Turns")
    width: float = Field(default=280, ge=40, le=300, title="Width (mm)")
    height: float = Field(default=198, ge=40, le=218, title="Height (mm)")
    persistence: float = Field(default=.5, ge=0, le=1, title="Persistence",
                               description="How long a passage keeps developing one relationship")
    reach: float = Field(default=.5, ge=0, le=1, title="Reach",
                         description="How far a passage extends or displaces earlier material")
    recurrence: float = Field(default=.5, ge=0, le=1, title="Recurrence",
                              description="Preference for returning to older passages")
    seed: int = Field(default=0, ge=0, le=MAX_SEED, title="Seed")
    events: list[Event] = Field(default_factory=list, max_length=128,
                                json_schema_extra={"hidden": True})

    @model_validator(mode="after")
    def validate_recipe(self):
        previous = 0
        seen = set()
        strokes = set()
        count = 0
        for event in self.events:
            if event.turn < previous:
                raise ValueError("Events must be ordered by turn; keep the earlier turn first")
            previous = event.turn
            key = event.turn, event.kind
            if key in seen:
                raise ValueError(f"Only one {event.kind} event is allowed at turn {event.turn}")
            seen.add(key)
            if event.turn in strokes:
                raise ValueError("Controls and branch events must precede the stroke at the same turn")
            if isinstance(event, StrokeEvent):
                strokes.add(event.turn)
                count += len(event.points)
                if count > 20_000:
                    raise ValueError("A recipe can contain at most 20,000 captured points; keep this drawing and start another")
                if any(not (math.isfinite(x) and math.isfinite(y) and
                            0 <= x <= self.width and 0 <= y <= self.height)
                       for x, y in event.points):
                    raise ValueError("Captured points must be finite and inside the drawing's width and height")
                if not any(a != b for a, b in zip(event.points, event.points[1:])):
                    raise ValueError("A stroke needs at least two distinct points; draw a short line")
        return self


@register_source
class SecondReading(ProcessModule):
    id = "second_reading"
    label = "Second Reading"
    description = "Develop passages, intervene with a stroke, and try another continuation."
    orientation = "geometry"
    time_axis = "turns"
    bench_capabilities = ("intervene", "branch")
    Params = SecondReadingParams

    def run(self, params: SecondReadingParams):
        p = params
        memory = engine.opening(p.width, p.height, engine.turn_rng(p.seed, 0, 0))
        controls = {key: getattr(p, key) for key in ("persistence", "reach", "recurrence")}
        events = {}
        for event in p.events:
            events.setdefault(event.turn, []).append(event)
        commitment = None
        branch = 0
        total_length = sum(x.length for x in memory)
        yield Step(paths=[path for item in memory for path in item.paths],
                   telemetry={"passages": 2.0, "ink_mm": total_length},
                   metadata={"action": "opening", "target_passage_ids": []})
        for turn in range(1, 65):
            human = None
            for event in events.get(turn, []):
                if isinstance(event, BranchEvent):
                    # A branch can change the currently pursued action, not
                    # merely jitter its next sample. No-op branch stays a no-op.
                    if event.seed != branch:
                        commitment = None
                    branch = event.seed
                elif isinstance(event, ControlsEvent):
                    changes = {k: v for k, v in event.model_dump().items()
                               if k in controls and v is not None}
                    if any(controls[k] != v for k, v in changes.items()
                           if k in ("persistence", "recurrence")):
                        commitment = None
                    controls.update(changes)
                else:
                    human = event
            rng = engine.turn_rng(p.seed, turn, branch)
            targets = ()
            if human is not None:
                from ._second_reading_gestures import smooth_capture
                paths = [Path(points=smooth_capture(human.points, human.smoothing))]
                action, construction = "human", "organic"
                commitment = None
            else:
                if commitment is None or commitment.remaining <= 0:
                    commitment = engine.choose(memory, controls["recurrence"], controls["persistence"], rng)
                elif commitment.iteration:
                    engine.reconsider(commitment, memory, rng)
                targets = commitment.target_ids
                action = commitment.action
                paths, construction = engine.make_action(commitment, memory, controls["reach"], p.width, p.height, rng)
                # A fully clipped proposal is not a passage. Search a bounded
                # three alternatives, then make an inward echo that is known
                # to fit. This avoids both blank turns and boundary bouncing.
                for _ in range(3):
                    if paths:
                        break
                    commitment = engine.choose(memory, controls["recurrence"], controls["persistence"], rng)
                    targets, action = commitment.target_ids, commitment.action
                    paths, construction = engine.make_action(commitment, memory, controls["reach"], p.width, p.height, rng)
                if not paths:
                    target = memory[-1]
                    paths = engine.echo(target, (0.0, 0.0), .9)
                    construction, action, targets = target.construction, "echo", (target.id,)
                    commitment = engine.Commitment(action, targets, 1, 1)
                targets = tuple(dict.fromkeys((*targets, *commitment.context_ids)))
                commitment.remaining -= 1
                commitment.iteration += 1
            if paths:
                ancestry = tuple(dict.fromkeys(a for item in memory if item.id in targets
                                                for a in (*item.ancestry, item.id)))
                passage = engine.describe(turn+1, paths, construction, action, targets, ancestry)
                memory.append(passage)
                total_length += passage.length
                if human is None and commitment.action == "extend":
                    commitment.target_ids = (passage.id,)
            else:
                # A continuation leaving the surface ends there. Reconsider
                # next turn; never draw a reflected trip along the boundary.
                commitment = None
            yield Step(paths=paths,
                       telemetry={"passages": float(len(memory)), "ink_mm": total_length,
                                  "commitment_remaining": float(commitment.remaining if commitment else 0)},
                       metadata={"action": action, "target_passage_ids": list(targets),
                                 "response": commitment.response if commitment else None,
                                 "passage_id": turn+1 if paths else None})

    def document(self, params: SecondReadingParams, paths: list[Path]) -> PathDocument:
        return PathDocument(layers=[Layer(id=1, name="Second Reading", color="#26241f", paths=list(paths))],
                            width=params.width, height=params.height,
                            source=f"second_reading @ {params.turns}")
