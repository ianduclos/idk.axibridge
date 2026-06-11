"""Worked example of an Effect module: coherent (noise-field) jitter.

Unlike per-point random jitter, displacement here is sampled from a smooth
2-D value-noise field, so neighbouring points move *together* — the line
wanders like a hand stroke instead of buzzing. Pure Python, no numpy needed
at these point counts.

Demonstrates the three contract points every effect should honour:

* paper-space units (amplitude and wavelength in mm on the sheet);
* layer-anchored sampling — the field is evaluated at ``point − layer
  translation``, so dragging the layer around the canvas keeps its wobble;
* seed stability — the seed mixes the user seed with the layer's stable
  ``ctx.seed``, so two overlapping layers get distinct fields, and re-resolve
  is reproducible.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect


class CoherentJitterParams(BaseModel):
    amplitude: float = Field(default=1.0, ge=0.0, le=20.0, title="Amplitude (mm)",
                             description="Maximum displacement on the sheet")
    wavelength: float = Field(default=25.0, ge=1.0, le=300.0, title="Wavelength (mm)",
                              description="Size of the noise features — bigger = lazier wander")
    detail: int = Field(default=2, ge=1, le=4, title="Detail (octaves)",
                        description="Extra octaves add finer tremor on top of the wander")
    step: float = Field(default=1.0, ge=0.1, le=20.0, title="Resample step (mm)",
                        description="Paths are resampled at this interval before displacement")
    seed: int = Field(default=0, ge=0, le=99999, title="Seed")


def _hash01(ix: int, iy: int, seed: int) -> float:
    """Deterministic lattice hash -> [0, 1). Cheap integer scramble."""
    h = (ix * 374761393 + iy * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / 0xFFFFFF


def _smooth(t: float) -> float:
    """Quintic fade (Perlin) — C2-continuous interpolation."""
    return t * t * t * (t * (t * 6 - 15) + 10)


def _value_noise(x: float, y: float, seed: int) -> float:
    """Smooth value noise in [-1, 1]."""
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    v00 = _hash01(ix, iy, seed)
    v10 = _hash01(ix + 1, iy, seed)
    v01 = _hash01(ix, iy + 1, seed)
    v11 = _hash01(ix + 1, iy + 1, seed)
    sx, sy = _smooth(fx), _smooth(fy)
    top = v00 + (v10 - v00) * sx
    bot = v01 + (v11 - v01) * sx
    return 2.0 * (top + (bot - top) * sy) - 1.0


def _fbm(x: float, y: float, seed: int, octaves: int) -> float:
    """Fractal sum of value noise, normalised to [-1, 1]."""
    total, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        total += amp * _value_noise(x * (2**o), y * (2**o), seed + o * 7919)
        norm += amp
        amp *= 0.5
    return total / norm


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
class CoherentJitter(EffectModule):
    id = "coherent_jitter"
    label = "Coherent jitter"
    description = "Smooth noise-field displacement — hand-drawn wander, not per-point buzz."
    Params = CoherentJitterParams

    def apply(self, paths: list[Path], params: CoherentJitterParams, ctx: EffectContext) -> list[Path]:
        seed = (params.seed * 31 + ctx.seed) & 0x7FFFFFFF
        tx, ty = ctx.translation
        inv_wl = 1.0 / params.wavelength
        out: list[Path] = []
        for path in paths:
            closed = len(path.points) > 2 and path.points[0] == path.points[-1]
            pts = _resample(path.points, params.step)

            def disp(p: tuple[float, float]) -> tuple[float, float]:
                # layer-anchored sampling: field rides along when the layer moves
                nx, ny = (p[0] - tx) * inv_wl, (p[1] - ty) * inv_wl
                dx = _fbm(nx, ny, seed, params.detail)
                dy = _fbm(nx + 117.7, ny - 41.3, seed + 1, params.detail)
                return (p[0] + dx * params.amplitude, p[1] + dy * params.amplitude)

            moved = [disp(p) for p in pts]
            if closed and len(moved) > 1:
                moved[-1] = moved[0]  # keep closed paths closed (mask validity)
            out.append(Path(points=moved, filled=path.filled))
        return out
