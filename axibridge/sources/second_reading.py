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
from . import _second_reading as encounter_engine

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
    reading: Literal["responsive", "first", "shapes", "relations", "encounters"] | None = None
    attention: float | None = Field(default=None, ge=0, le=1)
    departure: float | None = Field(default=None, ge=0, le=1)
    scale: float | None = Field(default=None, ge=0, le=1)
    persistence: float | None = Field(default=None, ge=0, le=1)
    reach: float | None = Field(default=None, ge=0, le=1)
    recurrence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def has_change(self):
        if all(getattr(self, k) is None for k in ("persistence", "reach", "recurrence", "attention", "departure", "scale", "reading")):
            raise ValueError("A controls event must specify a reading or a control")
        return self


class BranchEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["branch"]
    turn: int = Field(ge=1, le=64)
    seed: int = Field(ge=0, le=MAX_SEED)


Event = Annotated[StrokeEvent | ControlsEvent | BranchEvent, Field(discriminator="kind")]


class SecondReadingParams(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    reading: Literal["responsive", "first", "shapes", "relations", "encounters"] = Field(default="responsive", title="Reading")
    historical_stacks: bool = Field(default=False, json_schema_extra={"hidden": True})
    boundary: Literal["clip", "contain", "fit"] = Field(default="clip", title="Boundary", description="Clip; turn inside the edge; or overshoot and fit the whole element")
    attention: float = Field(default=.5, ge=0, le=1, title="Attention", description="Relations: current passage to wider drawing")
    departure: float = Field(default=.5, ge=0, le=1, title="Departure", description="Shape experiment: close relation to substantial transformation")
    scale: float = Field(default=.5, ge=0, le=1, title="Scale", description="Shape experiment: local to broad answer")
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
                            (-self.width*.5 if self.boundary == "fit" else 0) <= x <= self.width*(1.5 if self.boundary == "fit" else 1) and
                            (-self.height*.5 if self.boundary == "fit" else 0) <= y <= self.height*(1.5 if self.boundary == "fit" else 1))
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
        from . import _second_reading_experiment as experiment
        from . import _second_reading_first
        engine = _second_reading_first if p.reading != "encounters" else encounter_engine
        memory = engine.opening(p.width, p.height, engine.turn_rng(p.seed, 0, 0))
        # Shared descriptors let a recorded reading switch use older passages
        # without changing their geometry or ancestry.
        memory = [encounter_engine.describe(item.id,item.paths,item.construction,item.action,
                  item.targets,item.ancestry) for item in memory]
        controls = {key: getattr(p, key) for key in ("persistence", "reach", "recurrence", "attention", "departure", "scale", "reading")}
        events = {}
        for event in p.events:
            events.setdefault(event.turn, []).append(event)
        commitment = None
        branch = 0
        all_paths = [path for item in memory for path in item.paths]
        def view_metadata():
            if p.boundary != "fit":
                return {}
            return {"element_transform": experiment.fit_transform(all_paths,p.width,p.height),
                    "work_frame": experiment.frame(p.width,p.height,p.boundary)}
        total_length = sum(x.length for x in memory)
        yield Step(paths=[path for item in memory for path in item.paths],
                   telemetry={"passages": 2.0, "ink_mm": total_length},
                   metadata={"action": "opening", "target_passage_ids": [], **view_metadata()})
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
                    if any(controls[k] != v for k,v in changes.items() if k in ("reading", "attention")):
                        commitment = None
                    if controls["reading"] == "encounters" and any(controls[k] != v for k, v in changes.items()
                           if k in ("persistence", "recurrence")):
                        commitment = None
                    controls.update(changes)
                else:
                    human = event
            reading = controls["reading"]
            engine = encounter_engine if reading == "encounters" else _second_reading_first
            rng = engine.turn_rng(p.seed, turn, branch)
            shape_rng = engine.turn_rng(p.seed, turn, branch+2_147_483_648)
            def choose():
                if reading in ("responsive", "shapes", "relations"):
                    c = experiment.choose(memory,controls,rng,reading in ("responsive", "relations"))
                else:
                    c = engine.choose(memory,controls["recurrence"],controls["persistence"],rng)
                if not p.historical_stacks:
                    # Reinforcement used to mean four/six parallel passes,
                    # repeated for several turns. Ordinary use now offers a
                    # departure instead; transfers/bridges happen once.
                    if c.action == "concentrate":
                        c.action = "extend"
                        c.target_ids = c.target_ids[:1]
                    if c.action in ("echo", "traverse"):
                        c.remaining = 1
                return c
            def make():
                if reading in ("responsive", "shapes", "relations"):
                    return experiment.make_action(commitment,memory,controls,p.width,p.height,shape_rng,p.boundary,reading in ("responsive", "relations"))
                return engine.make_action(commitment,memory,controls["reach"],p.width,p.height,rng,
                    boundary=(lambda paths: experiment.contain(paths,p.width,p.height,p.boundary)) if p.boundary != "clip" else None)
            targets = ()
            if human is not None:
                from ._second_reading_gestures import smooth_capture
                paths = [Path(points=smooth_capture(human.points, human.smoothing))]
                action, construction = "human", ("organic" if reading == "encounters" else "angular")
                commitment = None
            else:
                if commitment is None or commitment.remaining <= 0:
                    commitment = choose()
                elif reading == "encounters" and commitment.iteration:
                    engine.reconsider(commitment, memory, rng)
                    if not p.historical_stacks:
                        if commitment.action == "concentrate":
                            commitment.action = "extend"
                            commitment.target_ids = commitment.target_ids[:1]
                        if commitment.action in ("echo", "traverse"):
                            commitment.remaining = 1
                targets = commitment.target_ids
                action = commitment.action
                paths, construction = make()
                # A fully clipped proposal is not a passage. Search a bounded
                # three alternatives, then make an inward echo that is known
                # to fit. This avoids both blank turns and boundary bouncing.
                for _ in range(3):
                    if paths:
                        break
                    commitment = choose()
                    targets, action = commitment.target_ids, commitment.action
                    paths, construction = make()
                if not paths:
                    target = memory[-1]
                    paths = engine.echo(target, (0.0, 0.0), .9)
                    construction, action, targets = target.construction, "echo", (target.id,)
                    commitment = engine.Commitment(action, targets, 1, 1)
                targets = tuple(dict.fromkeys((*targets, *getattr(commitment, "context_ids", ()))))
                commitment.remaining -= 1
                commitment.iteration += 1
            if paths:
                ancestry = tuple(dict.fromkeys(a for item in memory if item.id in targets
                                                for a in (*item.ancestry, item.id)))
                passage = encounter_engine.describe(turn+1, paths, construction, action, targets, ancestry)
                memory.append(passage)
                all_paths.extend(paths)
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
                                 "response": getattr(commitment, "response", None),
                                 "passage_id": turn+1 if paths else None, **view_metadata()})

    def placement_frame(self, params: dict) -> tuple[float, float] | None:
        return float(params.get("width", 280)), float(params.get("height", 198))

    def document(self, params: SecondReadingParams, paths: list[Path]) -> PathDocument:
        if params.boundary == "fit":
            from ._second_reading_experiment import fit_transform, transformed
            paths = transformed(paths, fit_transform(paths,params.width,params.height))
        return PathDocument(layers=[Layer(id=1, name="Second Reading", color="#26241f", paths=list(paths))],
                            width=params.width, height=params.height,
                            source=f"second_reading @ {params.turns}")
