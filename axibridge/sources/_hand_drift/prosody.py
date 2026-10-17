"""Frozen: where the regimes come from — a dancer's timing, or a field
(research `gesture/gesture_timing.py` and `gesture/regime_field.py` at c897f28).

timing — the pen travels the lines at the dancer's speed and ink is
deposited per unit TIME, so stillness pools ink (r → 2, a mass whose
diameter grows with √dwell), steady flow leaves a nib ribbon held at the
dancer's wrist angle, and speed leaves a dry monoline; the hand's
high-frequency lateral residual becomes the line's tremor. Six tempo
profiles are frozen in `hands/timing.npz` (the research windows), so this
works without the mocap corpus. Signs at jolts are not in v1.

field — `noise_fronts`: smooth noise through soft thresholds whose bleed
itself varies over the sheet (fronts both gradual and abrupt). A spatial
preset that needs no structure, so it works on bare lines.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d, map_coordinates

from . import regime as rg

GRID = 160


# ---------------------------------------------------------------------------
# timing → line (gesture_timing.ink_profile / line_profiles / danced_strokes)
# ---------------------------------------------------------------------------

def _unwrap_pi(phi: np.ndarray) -> np.ndarray:
    return np.unwrap(2 * phi) / 2


def ink_profile(tm: dict, s_grid: np.ndarray, *, sigma_ink: float, v_floor: float = 0.5) -> dict:
    """The pen travels a line of length L = s_grid[-1] in the window's time
    at a speed ∝ the dancer's (with a crawl floor so stillness still
    advances); every frame deposits the same ink, spread by a Gaussian of
    σ = sigma_ink. Returns ink per length / its median (q), time per s, and
    per-s φ and jitter."""
    fps = tm["fps"]
    sp = np.maximum(tm["speed"], v_floor)
    dist = np.concatenate([[0.0], np.cumsum(0.5 * (sp[1:] + sp[:-1]) / fps)])
    L = float(s_grid[-1])
    s_t = dist / max(dist[-1], 1e-9) * L
    step = float(np.median(np.diff(s_grid)))
    hist = np.bincount(np.clip(np.round(s_t / step).astype(int), 0, len(s_grid) - 1),
                       minlength=len(s_grid)).astype(float)
    ink = gaussian_filter1d(hist, sigma_ink / step, mode="nearest")
    q = ink / max(float(np.median(ink)), 1e-12)
    t_s = np.interp(s_grid, s_t, tm["t"])
    return {"q": q, "t": t_s, "phi": np.mod(np.interp(t_s, tm["t"], _unwrap_pi(tm["phi"])), np.pi),
            "jitter": np.interp(t_s, tm["t"], tm["jitter"])}


def line_profiles(tm: dict, s_grid: np.ndarray, *, W: float, shape_w: float, pen: float,
                  q_line: float = 1.0, q_mass: float = 6.0, jitter_gain: float = 1.0) -> dict:
    """r(s): 0 at q ≤ q_line, 2 at q ≥ q_mass, log-linear between. mass(s):
    shape_w·√(q / q_mass), floored at the nib, capped at 1.6·shape_w. φ: the
    wrist. jitter: lateral offset = gain × the residual rescaled so its p95
    is one pen width."""
    ip = ink_profile(tm, s_grid, sigma_ink=0.6 * W)
    lq = np.log(np.maximum(ip["q"], 1e-6))
    r = np.clip(2.0 * (lq - math.log(q_line)) / (math.log(q_mass) - math.log(q_line)), 0.0, 2.0)
    mass = np.maximum(shape_w * np.sqrt(np.maximum(ip["q"], 0) / q_mass), W)
    mass = np.minimum(mass, 1.6 * shape_w)
    sc = np.percentile(np.abs(tm["jitter"]), 95) + 1e-9
    jit = jitter_gain * pen * ip["jitter"] / sc
    return {"r": r, "mass": mass, "phi": ip["phi"], "jitter": jit}


def _resample_line(p: np.ndarray, step: float) -> np.ndarray:
    """Uniform arc-length resampling (research `curvature.resample`)."""
    p = np.asarray(p, dtype=np.float64)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    L = s[-1]
    if L <= 0 or len(p) < 2:
        return p[:1].copy()
    n = max(int(round(L / step)), 2)
    t = np.linspace(0.0, L, n + 1)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def danced(lines: list[np.ndarray], tm: dict, *, W: float, shape_w: float, pen: float,
           q_line: float = 1.0, jitter_gain: float = 1.0, amount: float = 1.0) -> list[rg.RegimeStroke]:
    """RegimeStrokes for `lines` drawn in sequence through one dance window:
    the lines' total length is mapped onto the window, so a long line gets a
    long stretch of the dance. `amount` (app:) scales r."""
    step = max(W / 4.0, 0.05)
    arrs = [_resample_line(q, step) for q in lines if len(q) >= 2]
    arrs = [a for a in arrs if len(a) >= 2]
    lens = [float(np.sum(np.linalg.norm(np.diff(a, axis=0), axis=1))) for a in arrs]
    Ltot = sum(lens)
    if Ltot <= 0:
        return []
    n = max(int(round(Ltot / step)), 2)
    s_grid = np.linspace(0, Ltot, n + 1)
    pr = line_profiles(tm, s_grid, W=W, shape_w=shape_w, pen=pen, q_line=q_line, jitter_gain=jitter_gain)
    out, off = [], 0.0
    for a, L in zip(arrs, lens):
        sl = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(a, axis=0), axis=1))])
        sg = sl + off
        r = np.clip(amount * np.interp(sg, s_grid, pr["r"]), 0.0, 2.0)
        ms = np.interp(sg, s_grid, pr["mass"])
        jit = np.interp(sg, s_grid, pr["jitter"])
        tg = np.gradient(a, axis=0)
        tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
        nrm = np.column_stack([-tg[:, 1], tg[:, 0]])
        phi = np.mod(np.interp(sg, s_grid, _unwrap_pi(pr["phi"])), np.pi)
        out.append(rg.make(a + nrm * jit[:, None], r, phi=phi, W=W, mass=ms))
        off += L
    return out


# ---------------------------------------------------------------------------
# field (regime_field.noise_fronts)
# ---------------------------------------------------------------------------

def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _soft_levels(d: np.ndarray, edges, values, bleed) -> np.ndarray:
    values = list(values)
    out = np.full(np.shape(d), float(values[0]))
    b = np.maximum(np.asarray(bleed, float), 1e-6)
    for e, v0, v1 in zip(edges, values[:-1], values[1:]):
        out = out + (v1 - v0) * smoothstep((d - e) / b + 0.5)
    return out


def _noise_grid(seed, shape, sigma: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pad = int(3 * sigma) + 2
    n = rng.standard_normal((shape[0] + 2 * pad, shape[1] + 2 * pad))
    n = gaussian_filter(n, sigma, mode="wrap")[pad:pad + shape[0], pad:pad + shape[1]]
    n = n - n.mean()
    return n / max(float(n.std()), 1e-12)


def _grid_shape(aspect: float, n: int = GRID) -> tuple[int, int]:
    if aspect >= 1:
        return n, max(int(round(n / aspect)), 8)
    return max(int(round(n * aspect)), 8), n


def noise_fronts(seed: int, *, scale: float = 0.13, thresholds=(-0.35, 0.55), values=(0.0, 1.0, 2.0),
                 bleed_lo: float = 0.03, bleed_hi: float = 0.6, aspect: float = 1.0) -> np.ndarray:
    """The field raster (rows, cols) over the unit sheet, r ∈ [0, 2]."""
    shape = _grid_shape(aspect)
    cell = 1.0 / max(shape[1], 1)
    n = _noise_grid((seed, 0), shape, scale / cell / 2.0)
    b = smoothstep(0.5 + 0.5 * _noise_grid((seed, 1), shape, 1.5 * scale / cell / 2.0))
    bleed = bleed_lo + (bleed_hi - bleed_lo) * b
    return np.clip(_soft_levels(n, list(thresholds), list(values), bleed), 0.0, 2.0)


def field_sampler(grid: np.ndarray, size: tuple[float, float]):
    """(x, y) in a sheet of `size` = (W, H) → r, bilinear on the raster."""
    W, H = size
    rows, cols = grid.shape

    def fn(x, y):
        u = np.clip(np.column_stack([np.asarray(x) / W, np.asarray(y) / H]), 0.0, 1.0)
        r = map_coordinates(grid, [u[:, 1] * rows - 0.5, u[:, 0] * cols - 0.5], order=1, mode="nearest")
        return np.clip(np.nan_to_num(r, nan=0.0), 0.0, 2.0)
    return fn
