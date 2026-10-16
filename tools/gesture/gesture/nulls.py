"""Null drawings: statistically matched non-artist drawings (stage 0).

A style statistic only means something if it separates the artist from these.
Every null keeps the source's canvas size, stroke count and per-stroke arc
length (px), starts each stroke at the source stroke's start point and
initial heading, carries the source's width profile over by arc-length
fraction, and is then placed inside the canvas (`_place`).

Null strokes are always open (`closed=False`); `meta["source_closed"]`
records the original. κ measurements use `curvature.kappa_s` at
σ = KAPPA_SIGMA_FRAC · drawing.ref_length(), step σ/4.

Placement: translate the whole stroke back inside the canvas (minimal shift);
if its bounding box is bigger than the canvas, rotate it (smallest rotation
that fits); if no rotation fits, centre it on the canvas and accept the
overflow (`stroke.meta["overflow"] = True`, counted in
`drawing.meta["overflow"]`). Length is never scaled.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .core import Drawing, Stroke
from .curvature import arclength, integrate_kappa, kappa_s, resample, turning_angles

KAPPA_SIGMA_FRAC = 0.01  # κ smoothing scale, fraction of drawing.ref_length()
OUT_STEP = 1.0           # px; max point spacing of re-integrated null strokes


def kappa_sigma(drawing: Drawing) -> float:
    """The κ smoothing σ (px) the nulls use for this drawing."""
    return KAPPA_SIGMA_FRAC * drawing.ref_length()


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

def _closed_pts(st: Stroke) -> np.ndarray:
    return np.vstack([st.points, st.points[:1]]) if st.closed and len(st) > 1 else st.points


def _start_heading(st: Stroke) -> float:
    p = _closed_pts(st)
    s = arclength(p)
    if s[-1] <= 0:
        return 0.0
    # direction over the first ~2% of the stroke (robust to pixel jitter)
    j = int(np.searchsorted(s, min(0.02 * s[-1], s[-1])))
    j = max(j, 1)
    d = p[j] - p[0]
    return float(np.arctan2(d[1], d[0]))


def _carry_width(src: Stroke, pts: np.ndarray) -> np.ndarray | None:
    if src.width is None:
        return None
    ps = _closed_pts(src)
    ws = np.concatenate([src.width, src.width[:1]]) if src.closed and len(src) > 1 else src.width
    ss = arclength(ps)
    sn = arclength(pts)
    if ss[-1] <= 0 or sn[-1] <= 0:
        return np.full(len(pts), float(ws[0]))
    return np.interp(sn / sn[-1], ss / ss[-1], ws)


def _place(points: np.ndarray, size) -> tuple[np.ndarray, bool]:
    """Fit a polyline inside [0, W-1]×[0, H-1] without changing its shape or
    length. Returns (points, overflow)."""
    W, H = int(size[0]), int(size[1])
    box = np.array([W - 1.0, H - 1.0])

    def shift_into(p):
        lo, hi = p.min(axis=0), p.max(axis=0)
        if np.any(hi - lo > box):
            return None
        d = np.where(lo < 0, -lo, 0.0) + np.where(hi > box, box - hi, 0.0)
        return p + d

    out = shift_into(points)
    if out is not None:
        return out, False
    c = points.mean(axis=0)
    for a in sorted(np.linspace(-np.pi / 2, np.pi / 2, 73), key=abs):
        R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        out = shift_into((points - c) @ R.T + c)
        if out is not None:
            return out, False
    lo, hi = points.min(axis=0), points.max(axis=0)
    return points + (box / 2 - (lo + hi) / 2), True


def _assemble(drawing: Drawing, name: str, polylines: list[np.ndarray], params: dict) -> Drawing:
    strokes, n_over = [], 0
    for i, (src, pts) in enumerate(zip(drawing.strokes, polylines)):
        placed, over = _place(pts, drawing.size)
        n_over += int(over)
        strokes.append(Stroke(placed, width=_carry_width(src, placed), closed=False,
                              meta={"null": name, "source": drawing.source, "source_index": i,
                                    "source_closed": src.closed, "overflow": over}))
    return Drawing(strokes, source=f"null:{name}:{drawing.source}", size=tuple(drawing.size),
                   meta={"null": name, "source": drawing.source, "overflow": n_over, **params})


def _integrate_samples(kappa: np.ndarray, length: float, start, heading: float) -> np.ndarray:
    """Polyline of exactly `length` px whose κ follows the given samples,
    spread uniformly over [0, length]."""
    n = len(kappa)
    if n < 2 or length <= 0:
        return np.asarray([start], dtype=np.float64)
    breaks = np.linspace(0.0, length, n)
    step = min(OUT_STEP, length / (n - 1))
    return integrate_kappa(breaks, kappa, step, start=start, heading=heading)


def _measure(drawing: Drawing) -> tuple[float, float, list[np.ndarray]]:
    """(σ, step, per-stroke κ samples) at the null measurement scale."""
    sigma = kappa_sigma(drawing)
    step = sigma / 4.0
    ks = [kappa_s(st.points, sigma, step=step, closed=st.closed)[1] for st in drawing.strokes]
    return sigma, step, ks


# --------------------------------------------------------------------------
# nulls
# --------------------------------------------------------------------------

def random_walk(drawing: Drawing, rng: np.random.Generator, step: float | None = None,
                match: str = "rms") -> Drawing:
    """Correlated random walk per stroke: fixed step length (px, default
    0.5% of ref_length, ≥ 1 px), i.i.d. zero-mean Gaussian turning angles
    whose spread matches the source stroke's turning angles after resampling
    at `step`.

    match="rms" (default) matches √mean(θ²), i.e. how much the source turns
    per step; match="std" matches the std about the stroke's mean turn, which
    makes the null of a circle (constant turn, std ≈ 0) a straight line.
    """
    if match not in ("rms", "std"):
        raise ValueError("match must be 'rms' or 'std'")
    h = step if step is not None else max(0.005 * drawing.ref_length(), 1.0)
    out, stds = [], []
    for st in drawing.strokes:
        L = st.length()
        r = resample(st.points, h, closed=st.closed)
        ta = turning_angles(r, closed=st.closed)
        if not len(ta):
            sd = 0.0
        elif match == "rms":
            sd = float(np.sqrt(np.mean(ta ** 2)))
        else:
            sd = float(np.std(ta))
        stds.append(sd)
        n = max(int(round(L / h)), 1)
        ds = L / n
        theta = _start_heading(st) + np.concatenate([[0.0], np.cumsum(rng.normal(0, sd, n - 1))])
        steps = np.column_stack([np.cos(theta), np.sin(theta)]) * ds
        out.append(np.vstack([st.points[0], st.points[0] + np.cumsum(steps, axis=0)]))
    return _assemble(drawing, "random_walk", out, {"step": h, "match": match, "turn_sd": stds})


def smooth_noise(drawing: Drawing, rng: np.random.Generator, sigma_frac: float = 0.05) -> Drawing:
    """Freehand-like line with no structure: κ(s) is zero-mean white noise
    low-pass filtered with σ = sigma_frac · stroke length, scaled so its RMS
    equals the source stroke's RMS κ (measured at the null κ scale). Heading,
    its integral, is then smooth noise too."""
    _, step, ks = _measure(drawing)
    out, rms = [], []
    for st, k in zip(drawing.strokes, ks):
        L = st.length()
        target = float(np.sqrt(np.mean(k ** 2))) if len(k) else 0.0
        rms.append(target)
        n = max(int(np.ceil(L / step)) + 1, 2)
        z = gaussian_filter1d(rng.standard_normal(n), max(sigma_frac * L / step, 0.5), mode="reflect")
        zr = float(np.sqrt(np.mean(z ** 2)))
        kap = z * (target / zr) if zr > 0 else z * 0.0
        out.append(_integrate_samples(kap, L, st.points[0], _start_heading(st)))
    return _assemble(drawing, "smooth_noise", out, {"sigma_frac": sigma_frac, "kappa_rms": rms})


def shuffled_segments(drawing: Drawing, rng: np.random.Generator, seg_frac: float = 0.1) -> Drawing:
    """Real local curvature, wrong order. Every stroke's κ(s) (σ = 1% of
    ref_length) is cut into pieces of ~seg_frac of that stroke's length; all
    pieces of the drawing are shuffled together, concatenated, and dealt back
    out to the strokes at their original sample counts (so the pooled κ
    multiset is exactly preserved), then re-integrated at the original
    lengths."""
    sigma, step, ks = _measure(drawing)
    pieces = []
    for k in ks:
        n = len(k)
        m = max(int(round(seg_frac * n)), 1)
        pieces.extend(k[i:i + m] for i in range(0, n, m))
    order = rng.permutation(len(pieces))
    pool = np.concatenate([pieces[i] for i in order]) if pieces else np.zeros(0)
    out, at = [], 0
    for st, k in zip(drawing.strokes, ks):
        kk = pool[at:at + len(k)]
        at += len(k)
        out.append(_integrate_samples(kk, st.length(), st.points[0], _start_heading(st)))
    return _assemble(drawing, "shuffled_segments", out,
                     {"seg_frac": seg_frac, "kappa_sigma": sigma, "n_pieces": len(pieces)})


def kappa_permuted(drawing: Drawing, rng: np.random.Generator, smooth_samples: float = 1.0) -> Drawing:
    """Same κ histogram per stroke, no correlation along s: κ samples are
    pointwise permuted, lightly smoothed (Gaussian, `smooth_samples` samples
    of σ/4 each), then rank-remapped onto the original values so the
    per-stroke histogram stays exact while neighbouring samples are mildly
    correlated (no single-sample kinks)."""
    sigma, step, ks = _measure(drawing)
    out = []
    for st, k in zip(drawing.strokes, ks):
        p = rng.permutation(k)
        if smooth_samples > 0 and len(p) > 2:
            sm = gaussian_filter1d(p, smooth_samples, mode="reflect")
            p = np.empty_like(k)
            p[np.argsort(sm, kind="stable")] = np.sort(k)
        out.append(_integrate_samples(p, st.length(), st.points[0], _start_heading(st)))
    return _assemble(drawing, "kappa_permuted", out,
                     {"kappa_sigma": sigma, "smooth_samples": smooth_samples})


def identity(drawing: Drawing, rng: np.random.Generator) -> Drawing:
    """Pipeline control, not a null: the source's own κ(s), measured and
    re-integrated exactly as the other nulls are, with nothing shuffled.
    Every null differs from the real drawing partly through this band-limiting
    pipeline; comparing nulls against `identity` isolates what the shuffle or
    noise itself destroyed (review finding 2026-10-16)."""
    sigma, step, ks = _measure(drawing)
    out = [_integrate_samples(k, st.length(), st.points[0], _start_heading(st))
           for st, k in zip(drawing.strokes, ks)]
    return _assemble(drawing, "identity", out, {"kappa_sigma": sigma})


NULLS = {
    "identity": identity,
    "random_walk": random_walk,
    "smooth_noise": smooth_noise,
    "shuffled_segments": shuffled_segments,
    "kappa_permuted": kappa_permuted,
}
