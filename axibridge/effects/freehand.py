"""Freehand re-execution — the Cohen "intentional line" as an effect.

The input paths are treated as *intentions*: an eye marches along each path
and a simulated hand chases it — an under-damped spring-damper with noise in
the control loop, not in the output. Errors are therefore correlated the way
human errors are: long lines drift and get corrected, corners overshoot,
closure points miss and are visibly patched. Contrast `coherent_jitter`,
which displaces geometry; this re-*draws* it. (See docs/IDEAS-generators.md.)

Mechanics, one line each:

* the eye runs `confidence` mm ahead of the hand, so high confidence cuts
  corners the way a sure hand does;
* the hand's spatial response scale is tied to `confidence` (ω = 2π/lookahead)
  and `correction` sets the damping ratio — low correction under-damps into
  overshoot and slow recovery;
* `tremor` feeds smooth 1-D noise into the steering *acceleration*;
* `fatigue` grows the tremor and weakens the correction with distance drawn
  since the pen went down (each path is one stroke);
* closed paths are closed by *seeking* the start point — the correction is
  drawn — then snapped exactly so occlusion masks stay valid.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect


class FreehandParams(BaseModel):
    confidence: float = Field(default=4.0, ge=0.5, le=30.0, title="Confidence (mm)",
                              description="How far the eye leads the hand — high values cut corners")
    correction: float = Field(default=0.5, ge=0.0, le=1.0, title="Correction",
                              description="How firmly the hand is steered back — low = sloppy overshoot")
    impulsiveness: float = Field(default=0.3, ge=0.0, le=1.0, title="Impulsiveness",
                                 description="Uneven pace: lunges and hesitations along the stroke")
    tremor: float = Field(default=0.6, ge=0.0, le=5.0, title="Tremor (mm)",
                          description="Steering noise amplitude — displacement stays near this scale")
    fatigue: float = Field(default=0.2, ge=0.0, le=1.0, title="Fatigue",
                           description="Error growth and weakening correction along each stroke")
    step: float = Field(default=0.4, ge=0.1, le=2.0, title="Step (mm)",
                        description="Simulation march interval (output point spacing)",
                        json_schema_extra={"group": "Fine tuning"})
    seed: int = Field(default=0, ge=0, le=99999, title="Seed",
                      json_schema_extra={"group": "Fine tuning"})


def _hash01(i: int, seed: int) -> float:
    h = (i * 374761393 + seed * 668265263) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / 0xFFFFFF


def _noise1(x: float, seed: int) -> float:
    """Smooth 1-D value noise in [-1, 1] (quintic fade)."""
    ix = math.floor(x)
    f = x - ix
    s = f * f * f * (f * (f * 6 - 15) + 10)
    a, b = _hash01(ix, seed), _hash01(ix + 1, seed)
    return 2.0 * (a + (b - a) * s) - 1.0


def _tremor2(s_mm: float, seed: int) -> tuple[float, float]:
    """Two-octave steering noise, one channel per axis, in [-1, 1]-ish."""
    nx = _noise1(s_mm / 8.0, seed) + 0.5 * _noise1(s_mm / 2.4, seed + 101)
    ny = _noise1(s_mm / 8.0 + 53.7, seed + 7) + 0.5 * _noise1(s_mm / 2.4, seed + 211)
    return nx / 1.5, ny / 1.5


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


@register_effect
class Freehand(EffectModule):
    id = "freehand"
    label = "Freehand (intentional line)"
    description = ("Redraws the layer as a hand chasing an intention — lag, overshoot, "
                   "tremor and fatigue, with errors correlated like a person's.")
    Params = FreehandParams

    def apply(self, paths: list[Path], params: FreehandParams, ctx: EffectContext) -> list[Path]:
        base_seed = (params.seed * 31 + ctx.seed) & 0x7FFFFFFF
        out: list[Path] = []
        for idx, path in enumerate(paths):
            out.append(self._draw(path, params, (base_seed + idx * 7919) & 0x7FFFFFFF))
        return out

    def _draw(self, path: Path, params: FreehandParams, seed: int) -> Path:
        closed = len(path.points) > 2 and path.points[0] == path.points[-1]
        # explicit-Euler stability: keep the march well under the response scale
        ds = min(params.step, params.confidence / 8.0)
        intent = _resample(path.points, ds)
        if len(intent) < 3:
            return Path(points=list(path.points), filled=path.filled)

        # cumulative arclength of the intention, for eye lookups
        cum = [0.0]
        for a, b in zip(intent, intent[1:]):
            cum.append(cum[-1] + math.dist(a, b))
        total = cum[-1]
        if total < 2 * ds:
            return Path(points=list(path.points), filled=path.filled)

        # spring-damper tuned in mm, converted to per-tick at march speed ds
        omega = 2.0 * math.pi / max(params.confidence, 0.5)     # rad/mm
        zeta = 0.5 + 0.6 * params.correction                    # under-damped at low correction
        seg = 0  # advancing pointer into `intent` (eye arclength is monotonic)

        def point_at(s: float) -> tuple[float, float]:
            nonlocal seg
            while seg < len(cum) - 2 and cum[seg + 1] < s:
                seg += 1
            span = cum[seg + 1] - cum[seg]
            t = 0.0 if span < 1e-12 else (s - cum[seg]) / span
            (x0, y0), (x1, y1) = intent[seg], intent[seg + 1]
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)

        px, py = intent[0]
        vx = vy = 0.0
        drawn = [(px, py)]
        s_eye = 0.0
        s_hand = 0.0  # distance the hand has drawn: drives tremor phase + fatigue

        def tick(tx: float, ty: float, speed: float) -> None:
            nonlocal px, py, vx, vy, s_hand
            # per-tick natural frequency, clamped into the semi-implicit-Euler
            # stable region (with zeta<=1.1, wt<=0.8 keeps damping < 2/tick) —
            # a hand mid-lunge can only correct so fast
            wt = min(omega * speed, 0.8)
            tired = params.fatigue * min(s_hand / 150.0, 1.5)
            g = wt * wt / (1.0 + 0.6 * tired)
            d = 2.0 * zeta * wt
            nx, ny = _tremor2(s_hand, seed)
            amp = params.tremor * (1.0 + 3.0 * tired)
            vx += g * (tx - px + nx * amp) - d * vx
            vy += g * (ty - py + ny * amp) - d * vy
            step_len = math.hypot(vx, vy)
            px += vx
            py += vy
            s_hand += max(step_len, 0.05 * speed)           # phase advances even when hesitating
            drawn.append((px, py))

        # main pursuit: the eye marches (unevenly, if impulsive) to the end
        while s_eye < total:
            pace = 1.0 + 1.2 * params.impulsiveness * _noise1(s_eye / 13.0, seed + 977)
            speed = ds * min(max(pace, 0.15), 2.5)
            s_eye = min(s_eye + speed, total)
            tx, ty = point_at(min(s_eye + params.confidence, total))
            tick(tx, ty, speed)

        # settle onto the endpoint: for closed paths that is the *drawn* start,
        # so the closing correction is visible on paper
        gx, gy = drawn[0] if closed else intent[-1]
        tol = max(0.1, 0.25 * params.tremor)
        for _ in range(int(3.0 * params.confidence / ds) + 40):
            if math.dist((px, py), (gx, gy)) <= tol:
                break
            tick(gx, gy, ds)

        if closed:
            drawn.append(drawn[0])  # exact closure — occlusion masks depend on it
        return Path(points=drawn, filled=path.filled)
