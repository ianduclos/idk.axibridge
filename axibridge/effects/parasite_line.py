"""Parasite line — a companion that walks with each stroke the way a dog
circles a walker: offset to one side, drifting laterally at low frequency,
crossing the skeleton now and then, occasionally looping.

The demo's dotted wanderer. Input paths pass through UNCHANGED; parasite
paths are ADDED alongside them (see docs/plans/response-brushes.md).

Mechanics, one line each:

* the base line is resampled at a fixed ~0.5mm step so lateral offset can be
  sampled smoothly along arc length, independent of input vertex density;
* at each resampled point the parasite sits `side*offset + wander(s)` along
  the local normal — `wander` is 2-3 incommensurate sines (quasi-periodic,
  never exactly repeating) so when `|wander| > offset` the parasite swings
  past the skeleton onto the other side: a crossing, not a bug;
  `wavelength`/`wander` amplitude are jittered per path from the seed so a
  multi-stroke drawing doesn't read as one stamped recipe;
* `loopiness` fires small hand-drawn loops at seeded, minimum-spaced trigger
  points: a ~1.5-3mm circle is grafted onto the parasite's own direction of
  travel at that point (parametrized in the local tangent/normal frame, so
  it departs and returns tangentially — no seam) — the demo's scallops;
* `dash_mm`/`gap_mm` chop the finished wander into dotted segments; 0 dash
  keeps it solid.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect

_STEP = 0.5  # mm, internal resample step for wander/loop sampling


class ParasiteLineParams(BaseModel):
    offset: float = Field(default=3.0, ge=0.5, le=15.0, title="Offset (mm)",
                          description="Base lateral distance from the skeleton")
    wavelength: float = Field(default=35.0, ge=5.0, le=120.0, title="Wavelength (mm)",
                              description="Low-frequency drift period along the stroke")
    wander: float = Field(default=4.0, ge=0.0, le=12.0, title="Wander (mm)",
                          description="Lateral drift amplitude — past the offset, the parasite crosses the line")
    loopiness: float = Field(default=0.25, ge=0.0, le=1.0, title="Loopiness",
                             description="Chance of small hand-drawn loops along the way")
    side: Literal["left", "right", "alternate"] = Field(
        default="alternate", title="Side",
        description="Which side of the stroke the parasite favors")
    dash_mm: float = Field(default=1.2, ge=0.0, le=10.0, title="Dash (mm)",
                           description="Dash length — 0 draws one solid line",
                           json_schema_extra={"group": "Fine tuning"})
    gap_mm: float = Field(default=1.0, ge=0.0, le=10.0, title="Gap (mm)",
                          description="Gap between dashes",
                          json_schema_extra={"group": "Fine tuning"})
    min_length: float = Field(default=8.0, ge=0.0, le=100.0, title="Min length (mm)",
                              description="Skip strokes shorter than this",
                              json_schema_extra={"group": "Fine tuning"})
    on_closed: bool = Field(default=True, title="On closed paths",
                            description="Also orbit closed paths — off targets open "
                                        "strokes only (a tube outline stays bare)",
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


def _tangents(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Unit tangent per point (central difference; forward/backward at ends)."""
    n = len(pts)
    out = []
    for i in range(n):
        a = pts[i - 1] if i > 0 else pts[i]
        b = pts[i + 1] if i < n - 1 else pts[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        out.append((dx / d, dy / d) if d > 1e-12 else (1.0, 0.0))
    return out


class _PathRNG:
    """Per-path deterministic wander/loop generator: frequency, amplitude and
    phase are all jittered from the seed so no two strokes wander alike."""

    def __init__(self, seed: int):
        self.seed = seed
        self.wl_jitter = 0.7 + 0.7 * _hash01(1, seed)     # 0.70 - 1.40
        self.amp_jitter = 0.65 + 0.7 * _hash01(2, seed)    # 0.65 - 1.35
        self.phase = [_hash01(10 + k, seed) * math.tau for k in range(3)]
        # wander octaves: incommensurate ratios so the sum never repeats over
        # any drawable stroke length. Weights deliberately do NOT favor one
        # dominant low-frequency term — a single strong sine reads as "a
        # slow parallel wave" (the constant-offset-contour failure mode);
        # keeping the three components closer in weight makes the path look
        # genuinely distracted rather than smoothly rippled, and the summed
        # amplitude clears +-amp often enough that crossings (|wander| >
        # offset, at the module's default offset/wander balance) actually
        # happen rather than being a rare edge case.
        self.ratios = (1.0, 0.41, 2.7)
        self.weights = (0.5, 0.38, 0.24)

    def wander(self, s: float, wavelength: float, amp: float) -> float:
        wl = wavelength * self.wl_jitter
        a = amp * self.amp_jitter
        total = 0.0
        for ratio, weight, phase in zip(self.ratios, self.weights, self.phase):
            total += weight * math.sin(math.tau * s / (wl * ratio) + phase)
        return a * total

    def loop_sites(self, total_length: float, min_spacing: float) -> list[float]:
        """Precompute candidate loop arc-length positions, each independently
        jittered off a min_spacing grid and each with its own fire/no-fire
        hash draw — this (not a live per-sample re-check) is what keeps
        fired loops spaced apart instead of chattering for several samples
        in a row once a bucket happens to hash true."""
        n = max(1, int(total_length / min_spacing))
        sites = []
        for k in range(n):
            jitter = (_hash01(k, self.seed + 4001) - 0.5) * 0.6 * min_spacing
            sites.append((k + 0.5) * min_spacing + jitter)
        return sites

    def loop_fires(self, site_index: int, loopiness: float) -> bool:
        return _hash01(site_index, self.seed + 4501) < loopiness

    def loop_radius(self, site_index: int) -> float:
        return 1.5 + 1.5 * _hash01(site_index, self.seed + 8003)  # 1.5 - 3.0 mm

    def loop_sign(self, site_index: int) -> float:
        return 1.0 if _hash01(site_index, self.seed + 9007) < 0.5 else -1.0


def _dashes(points: list[tuple[float, float]], dash_mm: float, gap_mm: float) -> list[list[tuple[float, float]]]:
    """Chop a polyline into dash segments by arc length. dash_mm == 0 keeps
    it as one solid segment."""
    if dash_mm <= 0 or len(points) < 2:
        return [points] if len(points) >= 2 else []
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    remaining = dash_mm
    drawing = True
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        seg_len = math.dist((x0, y0), (x1, y1))
        if seg_len < 1e-12:
            continue
        pos = 0.0
        if drawing and not current:
            current.append((x0, y0))
        while pos < seg_len:
            step = min(remaining, seg_len - pos)
            pos += step
            remaining -= step
            t = pos / seg_len
            pt = (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
            if drawing:
                current.append(pt)
            if remaining <= 1e-9:
                if drawing:
                    if len(current) >= 2:
                        segments.append(current)
                    current = []
                    drawing = False
                    remaining = gap_mm if gap_mm > 0 else 1e-9
                else:
                    drawing = True
                    remaining = dash_mm
                    current = [pt]
    if drawing and len(current) >= 2:
        segments.append(current)
    return segments


@register_effect
class ParasiteLine(EffectModule):
    id = "parasite_line"
    label = "Parasite line"
    description = ("Adds a wandering, occasionally looping companion line beside each "
                   "stroke — attached but not obedient. Originals pass through unchanged.")
    Params = ParasiteLineParams

    def apply(self, paths: list[Path], params: ParasiteLineParams, ctx: EffectContext) -> list[Path]:
        base_seed = (params.seed * 31 + ctx.seed) & 0x7FFFFFFF
        out: list[Path] = list(paths)  # originals verbatim, untouched
        for idx, path in enumerate(paths):
            if path.length() < params.min_length:
                continue
            closed = len(path.points) > 2 and path.points[0] == path.points[-1]
            if closed and not params.on_closed:
                continue  # response-brush targeting: tube outlines stay bare
            seed = (base_seed + idx * 7919) & 0x7FFFFFFF
            out.extend(self._parasites(path, params, seed, idx))
        return out

    def _side_sign(self, params: ParasiteLineParams, idx: int) -> float:
        if params.side == "left":
            return -1.0
        if params.side == "right":
            return 1.0
        return 1.0 if idx % 2 == 0 else -1.0

    def _parasites(self, path: Path, params: ParasiteLineParams, seed: int, idx: int) -> list[Path]:
        pts = _resample(path.points, _STEP)
        if len(pts) < 3:
            return []
        tans = _tangents(pts)
        rng = _PathRNG(seed)
        side_sign = self._side_sign(params, idx)
        min_spacing = 12.0  # loop candidate grid spacing (mm); each site independently jittered+rolled
        total_length = _STEP * (len(pts) - 1)
        sites = rng.loop_sites(total_length, min_spacing) if params.loopiness > 0 else []
        next_site = 0

        wander_pts: list[tuple[float, float]] = []
        s = 0.0
        for i, ((x, y), (tx, ty)) in enumerate(zip(pts, tans)):
            if i > 0:
                s += math.dist(pts[i - 1], pts[i])
            nx, ny = -ty, tx  # unit normal, 90deg CCW of tangent
            offset_amt = side_sign * params.offset + rng.wander(s, params.wavelength, params.wander)
            px, py = x + nx * offset_amt, y + ny * offset_amt
            wander_pts.append((px, py))

            # each candidate site fires at most once, the moment the march
            # reaches it — no re-checking within a window, so loops land as
            # isolated scallops instead of chattering back-to-back
            while next_site < len(sites) and s >= sites[next_site]:
                if rng.loop_fires(next_site, params.loopiness):
                    radius = rng.loop_radius(next_site)
                    loop_side = rng.loop_sign(next_site)
                    n_steps = 14
                    for k in range(1, n_steps + 1):
                        u = math.tau * k / n_steps
                        # circle in the local tangent/normal frame: starts and
                        # ends AT (px,py) with initial derivative along
                        # (tx,ty) — the loop departs and rejoins tangentially,
                        # no visible seam
                        lx = px + radius * loop_side * nx * (math.cos(u) - 1.0) + radius * tx * math.sin(u)
                        ly = py + radius * loop_side * ny * (math.cos(u) - 1.0) + radius * ty * math.sin(u)
                        wander_pts.append((lx, ly))
                next_site += 1

        segments = _dashes(wander_pts, params.dash_mm, params.gap_mm)
        return [Path(points=seg, filled=False) for seg in segments]
