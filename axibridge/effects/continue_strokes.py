"""Continue strokes — autocomplete as intrusion.

Each open path in the layer is extended past its endpoint with a *sampled*
continuation: the effect learns the layer's own local stroke statistics
(an order-N Markov chain over quantized turning angles, plus a step-length
pool) and keeps drawing in that voice. The result is fluent but hollow —
plausible for a few millimetres, then noticeably wrong — with the seam
sitting exactly where the real stroke ends. No model, no network; the layer
is its own training data. (See docs/IDEAS-oehlen-pass.md §3.)

Mechanics, one line each:

* every path is resampled at a fixed step and its turning-angle sequence
  quantized on a grid *adapted to the layer* (bin width follows the pooled
  angle spread, so a wiry layer continues wiry and a straight one straight);
* an order-``order`` n-gram over those bins is pooled from the whole layer,
  with backoff to shorter contexts down to the global distribution;
* the continuation walks from the endpoint's trailing context, sampling a
  turn per step — ``temperature`` 0 always takes the most typical turn,
  1 samples the full empirical spread;
* step lengths are drawn from the layer's own segment-length pool (turning
  is scaled with step length so curvature stays honest);
* closed paths (first == last) pass through unchanged — you don't continue
  a closed thought.
"""

from __future__ import annotations

import math
import random

from pydantic import BaseModel, Field

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect


class ContinueStrokesParams(BaseModel):
    extension: float = Field(default=25.0, ge=1.0, le=150.0, title="Extension (mm)",
                             description="How far past its end each stroke is continued")
    temperature: float = Field(default=0.35, ge=0.0, le=1.0, title="Temperature",
                               description="Sampling spread — 0 = the most typical turn every "
                                           "time, 1 = the layer's full statistical spread")
    order: int = Field(default=2, ge=1, le=4, title="Context (order)",
                       description="How many previous turns condition the next one")
    both_ends: bool = Field(default=False, title="Both ends",
                            description="Also continue backwards from each stroke's start")
    step: float = Field(default=0.5, ge=0.2, le=2.0, title="Step (mm)",
                        description="Resampling interval the statistics are learned at",
                        json_schema_extra={"group": "Fine tuning"})
    seed: int = Field(default=0, ge=0, le=99999, title="Seed",
                      json_schema_extra={"group": "Fine tuning"})


def _resample(points: list[tuple[float, float]], step: float) -> list[tuple[float, float]]:
    if len(points) < 2:
        return list(points)
    out = [points[0]]
    carry = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        seg = math.dist((x0, y0), (x1, y1))
        if seg < 1e-12:
            continue
        d = step - carry
        while d <= seg:
            t = d / seg
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
            d += step
        carry = seg - (d - step)
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def _turning_angles(pts: list[tuple[float, float]]) -> list[float]:
    """Signed turn at each interior vertex, in radians."""
    out = []
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        h0 = math.atan2(b[1] - a[1], b[0] - a[0])
        h1 = math.atan2(c[1] - b[1], c[0] - b[0])
        d = h1 - h0
        while d > math.pi:
            d -= 2 * math.pi
        while d < -math.pi:
            d += 2 * math.pi
        out.append(d)
    return out


class _StrokeModel:
    """Order-N n-gram over quantized turning angles, pooled from one layer."""

    def __init__(self, sequences: list[list[float]], step_pool: list[float], order: int):
        angles = [a for seq in sequences for a in seq]
        # bin width follows the layer's own spread so quantization resolves
        # its character (a near-straight layer would otherwise collapse into
        # one central bin and continue dead straight)
        if angles:
            mean = sum(angles) / len(angles)
            var = sum((a - mean) ** 2 for a in angles) / len(angles)
            self.w = min(max(math.sqrt(var) / 1.5, 0.005), 0.35)
        else:
            self.w = 0.1
        self.order = order
        self.step_pool = step_pool or []
        # counts[context_tuple][bin] for every context length 0..order
        self.counts: dict[tuple[int, ...], dict[int, int]] = {}
        for seq in sequences:
            q = [self._quant(a) for a in seq]
            for i, k in enumerate(q):
                for n in range(order + 1):
                    if i < n:
                        continue
                    ctx = tuple(q[i - n:i])
                    self.counts.setdefault(ctx, {}).setdefault(k, 0)
                    self.counts[ctx][k] += 1

    def _quant(self, a: float) -> int:
        return max(-60, min(60, round(a / self.w)))

    def tail_context(self, seq: list[float]) -> list[int]:
        return [self._quant(a) for a in seq[-self.order:]]

    def sample_turn(self, ctx: list[int], temperature: float, rng: random.Random) -> float:
        table: dict[int, int] | None = None
        for n in range(min(self.order, len(ctx)), -1, -1):
            table = self.counts.get(tuple(ctx[len(ctx) - n:]))
            if table:
                break
        if not table:
            return 0.0  # no statistics at all: continue straight
        bins = sorted(table)
        exponent = 1.0 / (0.08 + 0.92 * temperature)
        weights = [table[k] ** exponent for k in bins]
        total = sum(weights)
        r = rng.random() * total
        k = bins[-1]
        for b, wgt in zip(bins, weights):
            r -= wgt
            if r <= 0:
                k = b
                break
        # dequantize inside the bin so the continuation isn't gridded
        return (k + (rng.random() - 0.5) * 0.9) * self.w

    def sample_step(self, base: float, rng: random.Random) -> float:
        if not self.step_pool:
            return base
        return self.step_pool[rng.randrange(len(self.step_pool))]


@register_effect
class ContinueStrokes(EffectModule):
    id = "continue_strokes"
    label = "Continue strokes (autocomplete)"
    description = ("Extends each open stroke past its endpoint with a continuation sampled "
                   "from the layer's own stroke statistics — fluent, hollow, visibly taken over.")
    Params = ContinueStrokesParams

    def apply(self, paths: list[Path], params: ContinueStrokesParams,
              ctx: EffectContext) -> list[Path]:
        base_seed = (params.seed * 31 + ctx.seed) & 0x7FFFFFFF
        model = self._fit(paths, params)
        out: list[Path] = []
        for idx, path in enumerate(paths):
            closed = len(path.points) > 2 and path.points[0] == path.points[-1]
            if closed or len(path.points) < 2 or model is None:
                out.append(Path(points=list(path.points), filled=path.filled))
                continue
            seed = (base_seed + idx * 7919) & 0x7FFFFFFF
            pts = list(path.points)
            tail = self._continue(pts, model, params, random.Random(seed))
            if params.both_ends:
                head = self._continue(pts[::-1], model, params, random.Random(seed ^ 0x5F3759DF))
                pts = head[::-1] + pts
            out.append(Path(points=pts + tail, filled=path.filled))
        return out

    def _fit(self, paths: list[Path], params: ContinueStrokesParams) -> _StrokeModel | None:
        sequences: list[list[float]] = []
        step_pool: list[float] = []
        for path in paths:
            res = _resample(path.points, params.step)
            if len(res) >= 3:
                sequences.append(_turning_angles(res))
            for a, b in zip(path.points, path.points[1:]):
                d = math.dist(a, b)
                if d > 1e-9:
                    step_pool.append(min(max(d, 0.1), 8.0))
        if not step_pool:
            return None
        return _StrokeModel(sequences, step_pool, params.order)

    def _continue(self, pts: list[tuple[float, float]], model: _StrokeModel,
                  params: ContinueStrokesParams, rng: random.Random) -> list[tuple[float, float]]:
        """Continuation points beyond ``pts[-1]`` (exclusive), total ~extension mm."""
        res = _resample(pts, params.step)
        heading = None
        for a, b in zip(res[::-1][1:], res[::-1]):  # last non-degenerate segment
            if math.dist(a, b) > 1e-9:
                heading = math.atan2(b[1] - a[1], b[0] - a[0])
                break
        if heading is None:
            return []
        ctx = model.tail_context(_turning_angles(res))
        x, y = pts[-1]
        out: list[tuple[float, float]] = []
        travelled = 0.0
        while travelled < params.extension:
            step = model.sample_step(params.step, rng)
            step = min(step, params.extension - travelled)
            turn = model.sample_turn(ctx, params.temperature, rng)
            # turning statistics live at the resample step; scale to this
            # step length so curvature stays honest, clamped to a half-turn
            heading += max(-math.pi / 2, min(math.pi / 2, turn * step / params.step))
            x += step * math.cos(heading)
            y += step * math.sin(heading)
            out.append((x, y))
            travelled += step
            ctx = (ctx + [model._quant(turn)])[-model.order:]
        return out
