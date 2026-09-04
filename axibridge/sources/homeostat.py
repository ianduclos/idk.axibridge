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
