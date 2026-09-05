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
from dataclasses import dataclass, field as dataclass_field
from typing import Iterator, Literal

import numpy as np
from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..process import ProcessModule, Step
from ..registry import register_source
from ._homeostasis import Measures

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


@dataclass
class _Unit:
    """One pen of an ensemble: a hand, where it is, and how long it has been in
    trouble. Mutable and strictly local to a single ``run()`` — the module
    stays a pure function of its params because nothing here outlives the
    call."""

    hand: Genome
    rng: "np.random.Generator | None" = None
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    turn: float = 0.0
    out_of_range: int = 0
    in_range_run: int = 0
    held: list[Genome] = dataclass_field(default_factory=list)


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

    Edges REFLECT — both the heading AND the position, the overshoot mirrored
    back into the sheet. Clamping the position instead (which this function
    used to do, while its docstring claimed otherwise) leaves the pen sitting
    on the wall: at a shallow angle of incidence it then bounces ALONG the
    boundary for many steps, drawing long straight runs that read as a frame
    around the drawing rather than as anything the system decided. A step is
    at most 16 mm against a sheet of at least 20 mm, so one mirror always
    suffices; the clamp that follows is a guard, not the mechanism.
    """
    wander = float(rng.normal(0.0, g.wander)) if i % max(1, g.dwell) == 0 else 0.0
    turn = g.persistence * prev_turn + g.turn_bias + wander
    heading = heading + math.radians(turn)

    step = step_len * g.step_scale
    nx = x + math.cos(heading) * step
    ny = y + math.sin(heading) * step
    if nx < 0.0:
        nx = -nx
        heading = math.pi - heading
    elif nx > w:
        nx = 2.0 * w - nx
        heading = math.pi - heading
    if ny < 0.0:
        ny = -ny
        heading = -heading
    elif ny > h:
        ny = 2.0 * h - ny
        heading = -heading
    return min(max(nx, 0.0), w), min(max(ny, 0.0), h), heading, turn


class HomeostatParams(BaseModel):
    steps: int = Field(default=300, ge=0, le=1200, title="Steps",
                       description="How far the pen has walked. This is the time "
                                   "axis — bind it to the master timeline and the "
                                   "hunt becomes an animation")
    width: float = Field(default=200.0, ge=20.0, le=290.0, title="Width (mm)")
    height: float = Field(default=160.0, ge=20.0, le=210.0, title="Height (mm)")
    step_len: float = Field(default=2.0, ge=0.3, le=8.0, title="Step length (mm)",
                            description="Base pen advance per step; the hand scales it")
    measure: Literal["crowding", "coverage", "tangle"] = Field(
                         default="crowding", title="Essential variable",
                         description="What the system is trying not to lose. "
                                     "Crowding is local (am I in a corner?), "
                                     "coverage is global, tangle is how much "
                                     "ground it is retracing. THE BANDS DIFFER: "
                                     "crowding lives around 0.12, coverage "
                                     "around 0.05 (one pen inks under a tenth "
                                     "of a sheet), tangle around 0.27 — set "
                                     "Target near the band or the system never "
                                     "leaves crisis")
    target: float = Field(default=0.12, ge=0.0, le=1.0, title="Target",
                          description="Where the variable wants to sit. Each "
                                      "measure has its own reachable band — see "
                                      "Essential variable")
    tolerance: float = Field(default=0.08, ge=0.01, le=1.0, title="Tolerance",
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
    pens: int = Field(default=1, ge=1, le=6, title="Pens",
                      description="Units sharing one sheet. Ashby's machine was "
                                  "four coupled units seeking a JOINT "
                                  "equilibrium: each has its own hand and its "
                                  "own crises, none has any concept of another "
                                  "— they meet only in the ink, which they all "
                                  "measure")
    unit: int = Field(default=-1, ge=-1, le=5, title="Draw unit",
                      description="-1 draws every unit in this layer. 0-5 draws "
                                  "only that one, so duplicating the layer at "
                                  "the same seed and giving each copy a "
                                  "different unit and pen plots the ensemble in "
                                  "several colours")
    lift_on_reroll: bool = Field(default=False, title="Lift on reroll",
                                 description="Off: the hand changes mid-stroke "
                                             "and the seam is a change of "
                                             "character. On: the pen lifts and "
                                             "the seam is two marks")
    seed: int = Field(default=0, ge=0, le=99999, title="Seed")


def _stitch(paths: list[Path], pens: int = 1, unit: int = -1) -> list[Path]:
    """Join each unit's segments into single polylines.

    With N units every step contributes N segments in a fixed index order, so
    the accumulated list INTERLEAVES them and a naive endpoint stitch joins
    nothing — the drawing comes back as thousands of two-point fragments.
    De-interleaving by ``index % pens`` is exact precisely because every unit
    emits exactly one segment on every step, lifts included (a lift moves where
    the segment starts, it does not skip a turn).

    The trajectory stores per-step increments — that is what makes state at
    step N a prefix slice — so an unstitched state is one two-point path per
    step, which the plotter would draw as one pen lift per step. Stitching
    here, at document time, keeps the increments intact and still gives the
    plotter the continuous line the module's whole premise rests on.

    Accumulates into plain lists and builds each ``Path`` once. The obvious
    version — ``out[-1] = Path(points=out[-1].points + ...)`` per segment —
    is O(N^2), because it rebuilds AND re-validates the whole growing point
    list every step: 40 ms at the axis bound against 0.2 ms here, for
    byte-identical output, and it lands on every frame of a scrub rather than
    once. Same cost shape ``_homeostasis.py`` exists to avoid, one layer down.
    """
    out: list[Path] = []
    for u in range(pens):
        if unit >= 0 and u != unit:
            continue
        runs: list[list[tuple[float, float]]] = []
        for p in paths[u::pens]:
            if runs and runs[-1][-1] == p.points[0]:
                runs[-1].extend(p.points[1:])
            else:
                runs.append(list(p.points))
        out.extend(Path(points=r, filled=False) for r in runs)
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

        # ONE grid for every unit. A pen has no concept of another pen; it only
        # ever sees ink, so one unit's knot can throw another into crisis
        # without either knowing why. That is the whole coupling.
        field = Measures(w, h)

        # EVERY UNIT GETS ITS OWN RNG STREAM, and this is not a detail. Drawing
        # all of them from one generator would interleave the streams, so unit
        # 0's hand would change merely because two other pens exist — and then
        # "the units are coupled" could not be told apart from "the random
        # numbers moved". With one stream each, the ONLY channel between units
        # is the ink they share, which is the claim this module is making.
        # Unit 0 keeps the master stream, and starts at the centre without
        # drawing a position, so `pens=1` is byte-identical to the single-pen
        # module this grew out of.
        units: list[_Unit] = []
        for n in range(p.pens):
            urng = rng if n == 0 else np.random.default_rng(p.seed + 7919 * n)
            units.append(_Unit(hand=sample_genome(urng, p.variety), rng=urng))
        units[0].x, units[0].y = w / 2.0, h / 2.0
        for u in units[1:]:
            u.x = float(u.rng.uniform(0.0, w))
            u.y = float(u.rng.uniform(0.0, h))

        rerolls = 0.0
        i = 0

        while True:
            segs: list[Path] = []
            strains: list[float] = []
            values: list[float] = []

            for u in units:
                nx, ny, u.heading, u.turn = advance(u.x, u.y, u.heading, u.turn,
                                                    u.hand, p.step_len, i, w, h, u.rng)
                field.add(u.x, u.y, nx, ny)
                segs.append(Path(points=[(ox + u.x, oy + u.y), (ox + nx, oy + ny)],
                                 filled=False))
                u.x, u.y = nx, ny

                v = field.read(p.measure, u.x, u.y)
                strain = (v - p.target) / p.tolerance
                values.append(v)
                strains.append(strain)

                if abs(strain) > 1.0:
                    if u.in_range_run > p.patience:
                        # This hand kept the unit viable for a while. Remembered
                        # only so `memory` has a pool to bias toward; with memory
                        # at its default 0 the list is never read.
                        u.held.append(u.hand)
                    u.in_range_run = 0
                    u.out_of_range += 1
                else:
                    u.out_of_range = 0
                    u.in_range_run += 1

                if u.out_of_range >= p.patience:
                    centre = None
                    if p.memory > 0.0 and u.held and u.rng.random() < p.memory:
                        centre = u.held[int(u.rng.integers(len(u.held)))]
                    u.hand = sample_genome(u.rng, p.variety, centre=centre)
                    u.out_of_range = 0
                    rerolls += 1.0
                    if p.lift_on_reroll:
                        # Break the stitch: a segment starting somewhere else is
                        # a new stroke, and `_stitch` only joins shared endpoints.
                        u.x = float(u.rng.uniform(0.0, w))
                        u.y = float(u.rng.uniform(0.0, h))

            i += 1
            worst = max(strains, key=abs)
            telemetry = {"variable": sum(values) / len(values),
                         "strain": worst, "rerolls": rerolls}
            if p.pens > 1:
                # One trace per unit, so the bench plots each one hunting —
                # "you cannot tune a homeostat you cannot watch" does not get
                # easier when there are six of them.
                telemetry.update({f"strain_{n}": s for n, s in enumerate(strains)})
            yield Step(paths=segs, telemetry=telemetry)

    def document(self, params: HomeostatParams, paths: list[Path]) -> PathDocument:
        return PathDocument(
            layers=[Layer(id=1, name="homeostat", color="#26241f",
                          paths=_stitch(paths, params.pens, params.unit))],
            width=params.width,
            height=params.height,
            source=f"homeostat {params.seed} @ {params.steps}",
        )
