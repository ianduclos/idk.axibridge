"""The homeostat — a wandering pen that rerolls its own handwriting when the
drawing gets into trouble.

Ashby's homeostat held an essential variable inside a viable range and, pushed
outside it, RANDOMLY REWIRED ITSELF until it found a configuration that worked.
Blindly: it rerolls, it does not reason. That blindness is the point. The
reconfiguration is not a search for a better drawing, so the seam it leaves
lands exactly where the system was in trouble — which is Oehlen's regime
collision with a reason the sheet can show.

Design notes, including the two alternatives rejected (a bank of named regimes;
a coupled population of agents, which is what Ashby's machine actually was):
``docs/plans/homeostat.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator

import numpy as np
from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..process import ProcessModule, Step
from ..registry import register_source
from ._homeostasis import MEASURES, Measures

BED_WIDTH = 300.0
BED_HEIGHT = 218.0


@dataclass(frozen=True)
class Genome:
    """One hand. A flat vector of bounded numbers on purpose: a coupled
    population is N of these plus a coupling matrix, and a regime bank is this
    with a discrete gene — both rejected alternatives stay one refactor away."""

    turn_bias: float     # degrees per step, signed — a drift that spirals
    wander: float        # degrees, the random component
    persistence: float   # 0..1, how much of the previous turn carries over
    step_scale: float    # multiplier on the base step length
    dwell: int           # steps between fresh random turns


#: (low, high) for each gene. `variety` samples a band of this width around the
#: middle, so variety=0 is the centre hand and variety=1 is the whole range.
GENE_RANGES: dict[str, tuple[float, float]] = {
    "turn_bias": (-12.0, 12.0),
    "wander": (0.0, 45.0),
    "persistence": (0.0, 0.95),
    "step_scale": (0.4, 2.0),
    "dwell": (1.0, 8.0),
}


def sample_genome(rng: np.random.Generator, variety: float,
                  centre: Genome | None = None) -> Genome:
    """A fresh hand. ``centre`` is the memory path: with it, the band is drawn
    around a genome that previously held instead of around the range middle."""
    genes: dict[str, float] = {}
    for name, (lo, hi) in GENE_RANGES.items():
        mid = getattr(centre, name) if centre is not None else (lo + hi) / 2.0
        half = (hi - lo) / 2.0 * variety
        genes[name] = float(np.clip(rng.uniform(mid - half, mid + half), lo, hi))
    genes["dwell"] = int(round(genes["dwell"]))
    return Genome(**genes)  # type: ignore[arg-type]


def advance(x: float, y: float, heading: float, prev_turn: float,
            g: Genome, step_len: float, i: int, w: float, h: float,
            rng: np.random.Generator) -> tuple[float, float, float, float]:
    """One pen step. Returns ``(x, y, heading, turn)``.

    Edges REFLECT rather than clamp: a clamped pen slides along the wall and
    piles up ink there, which the crowding measure would read as a crisis
    caused by the boundary rather than by the drawing.
    """
    wander = float(rng.normal(0.0, g.wander)) if i % max(1, g.dwell) == 0 else 0.0
    turn = g.persistence * prev_turn + g.turn_bias + wander
    heading = heading + math.radians(turn)

    step = step_len * g.step_scale
    nx = x + math.cos(heading) * step
    ny = y + math.sin(heading) * step
    if nx < 0.0 or nx > w:
        heading = math.pi - heading
        nx = min(max(nx, 0.0), w)
    if ny < 0.0 or ny > h:
        heading = -heading
        ny = min(max(ny, 0.0), h)
    return nx, ny, heading, turn


class HomeostatParams(BaseModel):
    steps: int = Field(default=300, ge=0, le=1200, title="Steps",
                       description="How far the pen has walked. This is the time "
                                   "axis — bind it to the master timeline and the "
                                   "hunt becomes an animation")
    width: float = Field(default=200.0, ge=20.0, le=290.0, title="Width (mm)")
    height: float = Field(default=160.0, ge=20.0, le=210.0, title="Height (mm)")
    step_len: float = Field(default=2.0, ge=0.3, le=8.0, title="Step length (mm)",
                            description="Base pen advance per step; the hand scales it")
    measure: str = Field(default="crowding", title="Essential variable",
                         json_schema_extra={"enum": list(MEASURES)},
                         description="What the system is trying not to lose. "
                                     "Crowding is local (am I in a corner?), "
                                     "coverage is global, tangle is how much "
                                     "ground it is retracing")
    target: float = Field(default=0.25, ge=0.0, le=1.0, title="Target",
                          description="Where the variable wants to sit")
    tolerance: float = Field(default=0.12, ge=0.01, le=1.0, title="Tolerance",
                             description="Half-width of the viable range. Narrow "
                                         "gives constant crisis and visible "
                                         "thrash; wide gives long stable passages "
                                         "punctuated by lurches")
    patience: int = Field(default=8, ge=1, le=60, title="Patience (steps)",
                          description="Consecutive steps out of range before the "
                                      "hand is rerolled")
    variety: float = Field(default=0.8, ge=0.0, le=1.0, title="Variety",
                           description="How wide a reroll samples. 0 rerolls to "
                                       "nearly the same hand")
    memory: float = Field(default=0.0, ge=0.0, le=1.0, title="Memory",
                          description="Bias a reroll toward hands that held "
                                      "before. Ashby had none, and adding it "
                                      "makes the system converge — which is "
                                      "another word for finished")
    lift_on_reroll: bool = Field(default=False, title="Lift on reroll",
                                 description="Off: the hand changes mid-stroke "
                                             "and the seam is a change of "
                                             "character. On: the pen lifts and "
                                             "the seam is two marks")
    seed: int = Field(default=0, ge=0, le=99999, title="Seed")


def _stitch(paths: list[Path]) -> list[Path]:
    """Join consecutive paths that share an endpoint into single polylines.

    The trajectory stores per-step increments — that is what makes state at
    step N a prefix slice — so an unstitched state is one two-point path per
    step, which the plotter would draw as one pen lift per step. Stitching
    here, at document time, keeps the increments intact and still gives the
    plotter the continuous line the module's whole premise rests on.
    """
    out: list[Path] = []
    for p in paths:
        if out and out[-1].points[-1] == p.points[0]:
            out[-1] = Path(points=out[-1].points + list(p.points[1:]), filled=False)
        else:
            out.append(Path(points=list(p.points), filled=False))
    return out


@register_source
class Homeostat(ProcessModule):
    id = "homeostat"
    orientation = "geometry"  # a width x height field
    label = "Homeostat (hunting)"
    description = ("A pen that rerolls its own handwriting, blindly, whenever "
                   "the drawing leaves its viable range.")
    Params = HomeostatParams
    time_axis = "steps"
    accumulative = True

    def run(self, params: HomeostatParams) -> Iterator[Step]:
        p = params
        rng = np.random.default_rng(p.seed)
        w = min(p.width, BED_WIDTH - 4.0)
        h = min(p.height, BED_HEIGHT - 4.0)
        ox, oy = 2.0, 2.0

        field = Measures(w, h)
        hand = sample_genome(rng, p.variety)
        held: list[Genome] = []

        x, y = w / 2.0, h / 2.0
        heading, turn = 0.0, 0.0
        out_of_range = 0
        in_range_run = 0
        rerolls = 0.0
        i = 0

        while True:
            nx, ny, heading, turn = advance(x, y, heading, turn, hand,
                                            p.step_len, i, w, h, rng)
            field.add(x, y, nx, ny)
            seg = Path(points=[(ox + x, oy + y), (ox + nx, oy + ny)], filled=False)
            x, y = nx, ny
            i += 1

            v = field.read(p.measure, x, y)
            strain = (v - p.target) / p.tolerance

            if abs(strain) > 1.0:
                if in_range_run > p.patience:
                    # This hand kept the system viable for a while. Remembered
                    # only so `memory` has a pool to bias toward; with memory
                    # at its default 0 the list is never read.
                    held.append(hand)
                in_range_run = 0
                out_of_range += 1
            else:
                out_of_range = 0
                in_range_run += 1

            if out_of_range >= p.patience:
                centre = None
                if p.memory > 0.0 and held and rng.random() < p.memory:
                    centre = held[int(rng.integers(len(held)))]
                hand = sample_genome(rng, p.variety, centre=centre)
                out_of_range = 0
                rerolls += 1.0
                if p.lift_on_reroll:
                    # Break the stitch: a segment starting somewhere else is a
                    # new stroke, and `_stitch` only joins shared endpoints.
                    x, y = float(rng.uniform(0.0, w)), float(rng.uniform(0.0, h))

            yield Step(paths=[seg],
                       telemetry={"variable": v, "strain": strain,
                                  "rerolls": rerolls})

    def document(self, params: HomeostatParams, paths: list[Path]) -> PathDocument:
        return PathDocument(
            layers=[Layer(id=1, name="homeostat", color="#26241f",
                          paths=_stitch(paths))],
            width=params.width,
            height=params.height,
            source=f"homeostat {params.seed} @ {params.steps}",
        )
