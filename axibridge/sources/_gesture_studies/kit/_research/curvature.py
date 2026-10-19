# FROZEN from research commit ecd64f8: tools/gesture/gesture/curvature.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""The one curvature implementation (see ../README.md, "Curvature").

All functions take an (N, 2) polyline and return new arrays; inputs are never
mutated. Units follow the input (pixels in, 1/pixels out for κ).
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d


def _closed_loop(points: np.ndarray) -> np.ndarray:
    return np.vstack([points, points[:1]])


def arclength(points: np.ndarray) -> np.ndarray:
    """Cumulative arc length, s[0] = 0, same length as points."""
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(seg)])


def resample(points: np.ndarray, step: float, closed: bool = False) -> np.ndarray:
    """Uniform arc-length resampling at `step` spacing.

    Open strokes keep both endpoints (the spacing is spread evenly, so it is
    `step` only approximately). Closed strokes return points without
    repeating the first one.
    """
    p = np.asarray(points, dtype=np.float64)
    if closed:
        p = _closed_loop(p)
    s = arclength(p)
    total = s[-1]
    if total <= 0 or len(p) < 2:
        return p[:1].copy()
    n = max(int(round(total / step)), 2 if not closed else 3)
    t = np.linspace(0.0, total, n + 1)
    if closed:
        t = t[:-1]
    out = np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])
    return out


def smooth(points: np.ndarray, sigma: float, step: float, closed: bool = False) -> np.ndarray:
    """Gaussian smoothing of x(s), y(s). `points` must already be uniformly
    resampled at `step`; sigma is in the same units as the points."""
    if sigma <= 0:
        return np.array(points, dtype=np.float64)
    mode = "wrap" if closed else "nearest"
    sd = sigma / step
    return np.column_stack([
        gaussian_filter1d(points[:, 0], sd, mode=mode),
        gaussian_filter1d(points[:, 1], sd, mode=mode),
    ])


def curvature(points: np.ndarray, step: float, closed: bool = False) -> np.ndarray:
    """Signed curvature κ at each point of a uniformly resampled polyline.

    Positive = turning counter-clockwise in a y-up frame. (Scans are y-down;
    the sign flips consistently, which is fine for statistics that use |κ| or
    compare signs within a drawing.)
    """
    p = np.asarray(points, dtype=np.float64)
    if len(p) < 3:
        return np.zeros(len(p))
    if closed:
        pad = np.vstack([p[-1:], p, p[:1]])
        d1 = (pad[2:] - pad[:-2]) / (2 * step)
        d2 = (pad[2:] - 2 * pad[1:-1] + pad[:-2]) / step**2
    else:
        d1 = np.gradient(p, step, axis=0)
        d2 = np.gradient(d1, step, axis=0)
    num = d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]
    den = np.power(np.maximum(np.einsum("ij,ij->i", d1, d1), 1e-12), 1.5)
    return num / den


def kappa_s(points: np.ndarray, sigma: float, step: float | None = None,
            closed: bool = False, renormalise: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convenience: resample → smooth → κ. Returns (s, κ, smoothed_points).

    step defaults to sigma/4 (enough samples per smoothing kernel).

    By default s is arc length along the RAW polyline. On noisy input that
    stretches s by the noise's zig-zag (≈28% at 0.5 px jitter) and
    over-counts turning; `renormalise=True` re-parameterises by arc length
    along the SMOOTHED curve (renormalised curvature scale space). clothoid.py
    does its own equivalent correction; extracted strokes are already
    smoothed at ~1 px, where the difference is small.
    """
    step = step if step is not None else max(sigma / 4.0, 1e-6)
    r = resample(points, step, closed=closed)
    sm = smooth(r, sigma, step, closed=closed)
    if renormalise and len(sm) >= 3:
        sm = resample(sm, step, closed=closed)
        step = float(arclength(np.vstack([sm, sm[:1]]) if closed else sm)[-1]
                     / max(len(sm) - (0 if closed else 1), 1))
    k = curvature(sm, step, closed=closed)
    s = np.arange(len(sm)) * step
    return s, k, sm


def turning_angles(points: np.ndarray, closed: bool = False) -> np.ndarray:
    """Signed exterior angle at each interior vertex (radians, in (-π, π])."""
    p = np.asarray(points, dtype=np.float64)
    if closed:
        p = np.vstack([p[-1:], p, p[:1]])
    d = np.diff(p, axis=0)
    a = np.arctan2(d[:, 1], d[:, 0])
    t = np.diff(a)
    return (t + np.pi) % (2 * np.pi) - np.pi


def integrate_kappa(breaks: np.ndarray, kappas: np.ndarray, step: float,
                    start=(0.0, 0.0), heading: float = 0.0) -> np.ndarray:
    """Build a polyline from a piecewise-linear κ(s) — the exact inverse of
    the clothoid model, used for ground truth and for generation.

    breaks: (M+1,) increasing arc-length knots starting at 0.
    kappas: (M+1,) κ at each knot; κ is linear in between (line: both 0,
            arc: equal, clothoid: different).
    Returns (N, 2) points spaced `step` apart along s, starting at `start`.
    Heading is integrated exactly per sample (trapezoid on κ), position by
    midpoint rule, so error is O(step²).
    """
    breaks = np.asarray(breaks, dtype=np.float64)
    kappas = np.asarray(kappas, dtype=np.float64)
    total = breaks[-1]
    n = max(int(np.ceil(total / step)), 1)
    s = np.linspace(0.0, total, n + 1)
    k = np.interp(s, breaks, kappas)
    ds = np.diff(s)
    theta = heading + np.concatenate([[0.0], np.cumsum(0.5 * (k[1:] + k[:-1]) * ds)])
    mid = 0.5 * (theta[1:] + theta[:-1])
    steps = np.column_stack([np.cos(mid) * ds, np.sin(mid) * ds])
    return np.vstack([np.asarray(start, dtype=np.float64), np.asarray(start) + np.cumsum(steps, axis=0)])


def scale_space(points: np.ndarray, sigmas: list[float], closed: bool = False) -> list[dict]:
    """κ(s) at several smoothing scales (curvature scale space, coarse view).

    Returns one dict per sigma: {"sigma", "s", "kappa", "zero_crossings",
    "extrema"} where extrema are indices of local |κ| maxima.
    """
    out = []
    for sg in sigmas:
        s, k, _ = kappa_s(points, sg, closed=closed)
        sign = np.sign(k)
        zc = np.nonzero(sign[:-1] * sign[1:] < 0)[0]
        ak = np.abs(k)
        ext = np.nonzero((ak[1:-1] > ak[:-2]) & (ak[1:-1] >= ak[2:]))[0] + 1
        out.append({"sigma": sg, "s": s, "kappa": k, "zero_crossings": zc, "extrema": ext})
    return out
