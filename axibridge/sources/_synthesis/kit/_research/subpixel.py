# FROZEN from research commit 6f96418: tools/gesture/gesture/subpixel.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Sub-pixel centreline refinement: a post-pass for ANY extractor's output.

Why: a skeleton (or any pixel-lattice trace) wanders ±½ px around the true
centre with a period of tens of pixels — the pixel staircase of a shallow
line and the noise of the mask boundary. That wobble survives the 1-px
de-staircase smoothing and sits exactly in the band the κ statistics read
(σ = 2w), so it dominates κ error. The ink itself knows where the centre is:
this module moves each point onto it.

    refine_centrelines(gray, drawing) -> Drawing

Per stroke:

1. resample at `step` px (≈ 0.5); normals from a copy smoothed at ~½w (the
   input's own wobble must not tilt the normals);
2. sample the darkness profile D = paper level − gray (paper = coarse
   90th-percentile map, gray lightly pre-blurred) along each normal with
   `scipy.ndimage.map_coordinates`;
3. `method="core"`: the contiguous half-maximum run around the peak nearest
   the point; the new centre is the centroid of its CORE — the darkest
   fraction `core` of the peak height (D − (1 − core)·peak). Whole-profile
   centroids are pulled by grain, halo and neighbouring ink; the core is not.
   `method="steger"`: one or more Newton steps t = −(∇I·n)/(nᵀHn) on the
   darkness image Gaussian-smoothed at σ ≈ 0.4w (Steger 1998), along the
   stroke's own normal;
4. points are SKIPPED (shift interpolated along s from their neighbours)
   where the half-max run is wider than `wide`·(running median run) — two
   lines overlapping at a crossing, a T bar, a blob — where the run touches
   the profile ends, where the peak is faint relative to the stroke, where
   the shift exceeds 1.5·max_shift, or within `skip_radius`·w of a point
   listed in `stroke.meta[skip_meta_key]` (e.g. extract's junction centres);
   other shifts are clamped to ±max_shift (≈ 0.5w);
5. light Gaussian smoothing (σ = `smooth_sigma` px; open ends reflection-
   padded so they stay put), resample at `out_step` px.

Closed flags, stroke order and meta are kept; widths are carried over by
arc-length fraction (or re-measured as the FWHM of the profile with
`remeasure_width=True`). Pure: inputs are never mutated. Deterministic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.ndimage import (gaussian_filter, gaussian_filter1d, map_coordinates,
                           median_filter, percentile_filter, zoom)

from .core import Drawing, Stroke

__all__ = ["refine_centrelines", "paper_level"]


# --------------------------------------------------------------------------
# image fields
# --------------------------------------------------------------------------

def paper_level(gray: np.ndarray, k: int = 8) -> np.ndarray:
    """Paper brightness: 90th percentile over k×k blocks (9×9 block window),
    smoothed and upsampled. Stains and uneven light drop out of D."""
    H, W = gray.shape
    k = max(1, min(k, H // 4, W // 4))
    h2, w2 = H // k, W // k
    if h2 < 2 or w2 < 2:
        return np.full_like(gray, float(np.percentile(gray, 90)))
    small = gray[:h2 * k, :w2 * k].reshape(h2, k, w2, k).mean(axis=(1, 3))
    bs = gaussian_filter(percentile_filter(small, 90, size=9, mode="nearest"), 2.0)
    bg = zoom(bs, (H / h2, W / w2), order=1)
    out = np.empty_like(gray)
    hh, ww = min(H, bg.shape[0]), min(W, bg.shape[1])
    out[:hh, :ww] = bg[:hh, :ww]
    out[hh:, :] = out[hh - 1:hh, :]
    out[:, ww:] = out[:, ww - 1:ww]
    return out


class _Field:
    """Darkness D = paper − gray (signed, float32) and its blurred copies.

    Blur scales are binned geometrically (ratio ≈ 1.19) and cached, so a
    scan with many line widths costs a handful of Gaussian passes. Each copy
    carries a robust noise level (1.4826·MAD of D over a fixed pixel sample —
    most pixels of a line drawing are paper) for the contrast gate."""

    def __init__(self, gray: np.ndarray):
        g0 = np.asarray(gray)
        if g0.ndim == 3:
            g0 = g0[..., :3].mean(axis=2)
        g = g0.astype(np.float64)
        if g0.dtype == np.uint8:
            g = g / 255.0
        self.D0 = (paper_level(g) - g).astype(np.float32)
        H, W = g.shape
        rng = np.random.default_rng(0)
        n = min(H * W, 200_000)
        self._sample = (rng.integers(0, H, n), rng.integers(0, W, n))
        self._blur: dict[float, tuple[np.ndarray, float]] = {}
        self._steger: dict[float, tuple] = {}

    @staticmethod
    def _bin(sigma: float) -> float:
        if sigma <= 0:
            return 0.0
        return round(float(2.0 ** (round(4 * np.log2(sigma)) / 4)), 3)

    def blur(self, sigma: float) -> tuple[np.ndarray, float]:
        key = self._bin(sigma)
        if key not in self._blur:
            Ds = gaussian_filter(self.D0, key, mode="nearest") if key > 0 else self.D0
            v = Ds[self._sample]
            noise = float(1.4826 * np.median(np.abs(v - np.median(v))))
            self._blur[key] = (Ds, max(noise, 1e-4))
        return self._blur[key]

    def steger(self, sigma: float):
        key = self._bin(max(sigma, 0.5))
        if key not in self._steger:
            g = lambda o: gaussian_filter(self.D0, key, order=o, mode="nearest")
            # (row, col) order: o=(0, 1) is d/dx
            self._steger[key] = (g((0, 1)), g((1, 0)), g((0, 2)), g((1, 1)), g((2, 0)))
        return self._steger[key]


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------

def _arclen(p: np.ndarray, closed: bool) -> np.ndarray:
    q = np.vstack([p, p[:1]]) if closed else p
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])


def _resample(p: np.ndarray, step: float, closed: bool) -> tuple[np.ndarray, np.ndarray]:
    """Uniform resampling; returns (points, fraction of total arc length)."""
    s = _arclen(p, closed)
    total = s[-1]
    q = np.vstack([p, p[:1]]) if closed else p
    n = max(int(round(total / step)), 3 if closed else 1)
    t = np.linspace(0.0, total, n + 1)
    if closed:
        t = t[:-1]
    out = np.column_stack([np.interp(t, s, q[:, 0]), np.interp(t, s, q[:, 1])])
    return out, t / max(total, 1e-12)


def _gsmooth(p: np.ndarray, sd: float, closed: bool) -> np.ndarray:
    """Gaussian smoothing in samples; open ends padded by point reflection so
    the endpoints stay put and the ends are not pulled inward."""
    if sd <= 0 or len(p) < 3:
        return p.copy()
    if closed:
        return np.column_stack([gaussian_filter1d(p[:, k], sd, mode="wrap") for k in (0, 1)])
    k = min(int(4 * sd) + 1, len(p) - 1)
    left = 2 * p[0] - p[1:k + 1][::-1]
    right = 2 * p[-1] - p[-k - 1:-1][::-1]
    pp = np.vstack([left, p, right])
    pp = np.column_stack([gaussian_filter1d(pp[:, j], sd, mode="nearest") for j in (0, 1)])
    return pp[k:k + len(p)]


def _normals(p: np.ndarray, sd: float, closed: bool) -> np.ndarray:
    sm = _gsmooth(p, sd, closed)
    if closed:
        d = np.roll(sm, -1, axis=0) - np.roll(sm, 1, axis=0)
    else:
        d = np.gradient(sm, axis=0)
    t = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
    return np.column_stack([-t[:, 1], t[:, 0]])


def _fill(shift: np.ndarray, valid: np.ndarray, closed: bool) -> np.ndarray:
    """Replace invalid shifts by linear interpolation along the stroke from
    valid neighbours (constant beyond the last valid one; periodic when
    closed). No valid point → zero shift."""
    n = len(shift)
    if valid.all():
        return shift
    if not valid.any():
        return np.zeros(n)
    idx = np.arange(n)
    vi = idx[valid]
    if closed:
        xp = np.concatenate([vi - n, vi, vi + n])
        fp = np.tile(shift[valid], 3)
        return np.interp(idx, xp, fp)
    return np.interp(idx, vi, shift[valid])


# --------------------------------------------------------------------------
# one stroke
# --------------------------------------------------------------------------

def _profiles(D, p, nrm, R, ostep=0.25):
    o = np.arange(-R, R + 1e-9, ostep)
    X = p[:, 0:1] + o[None, :] * nrm[:, 0:1]
    Y = p[:, 1:2] + o[None, :] * nrm[:, 1:2]
    v = map_coordinates(D, [Y.ravel(), X.ravel()], order=1, mode="nearest").reshape(X.shape)
    return o, v


def _analyse(o, v, wl, core):
    """Per row: peak near the centre, contiguous half-max run, core centroid.
    Returns (centroid offset, run width, peak, saturated)."""
    N, M = v.shape
    rows = np.arange(N)
    near = np.abs(o)[None, :] <= (0.5 * wl + 1.0)[:, None]
    pk = np.argmax(np.where(near, v, -1.0), axis=1)
    peak = v[rows, pk]
    j = np.arange(M)[None, :]
    half = 0.5 * peak[:, None]
    below = v < half
    left = np.max(np.where(below & (j < pk[:, None]), j, -1), axis=1) + 1
    right = np.min(np.where(below & (j > pk[:, None]), j, M), axis=1) - 1
    sat = (left <= 0) | (right >= M - 1)
    ostep = o[1] - o[0]
    run = (right - left + 1) * ostep
    inrun = (j >= left[:, None]) & (j <= right[:, None])
    wts = np.where(inrun, np.clip(v - (1.0 - core) * peak[:, None], 0.0, None), 0.0)
    sw = wts.sum(axis=1)
    cen = (wts * o[None, :]).sum(axis=1) / np.maximum(sw, 1e-12)
    cen = np.where(sw > 0, cen, 0.0)
    return cen, run, peak, sat


@dataclass(frozen=True)
class _Opts:
    method: str
    core: float
    max_shift: float          # fraction of local width
    iters: int
    smooth_sigma: float       # px
    step: float
    out_step: float
    wide: float
    min_contrast: float       # peak vs running median peak of the stroke
    min_snr: float            # peak vs image noise at the blur scale
    pre_sigma: float          # px floor of the per-stroke blur
    pre_frac: float           # per-stroke blur σ = max(pre_sigma, pre_frac·w)
    shift_median: float       # running median of shifts, window in w (0 = off)
    shift_sigma: float        # Gaussian of shifts, σ in w (0 = off)
    along: float              # profile averaging along s, σ in w (0 = off)
    narrow: float             # half-max run < this·w = grain, not the line
    reject: float             # |shift| > this·max_shift → skipped, not clamped
    grain_tol: float          # adaptive blur: centroid high-pass residual ≤ this·w (0 = off)
    skip_radius: float
    remeasure_width: bool
    steger_sigma: float
    steger_steps: int


def _refine_stroke(F: _Field, s: Stroke, o_: _Opts, w_default: float, skip_pts):
    pts0 = s.points
    closed = bool(s.closed) and len(pts0) >= 3
    step = o_.step
    L = _arclen(pts0, closed)[-1]
    if len(pts0) < 2 or L < 2 * step:
        return s, {"valid": 0.0, "n": 0}
    if s.width is not None and len(s.width) and np.all(np.isfinite(s.width)):
        w_s = float(np.median(s.width))
    else:
        w_s = float(w_default)
    w_s = max(w_s, 1.0)
    mode = "wrap" if closed else "nearest"
    p, frac = _resample(pts0, step, closed)
    if s.width is not None:
        sw0 = _arclen(pts0, closed)
        fr0 = sw0 / max(sw0[-1], 1e-12)
        wsrc = np.concatenate([s.width, s.width[:1]]) if closed else s.width
        width_in = np.interp(frac, fr0, wsrc)
    else:
        width_in = np.full(len(p), w_s)
    # local width for the peak search / clamp: the stroke's own width, tamed
    wl = np.clip(median_filter(width_in, size=max(3, int(4 * w_s / step) | 1), mode=mode),
                 0.6 * w_s, 1.6 * w_s)
    max_shift = o_.max_shift * wl + 0.25
    R = float(1.5 * wl.max() + 2.0)
    nsd = max(2.0, 0.5 * w_s) / step
    # blur scale: the finest at which the centre estimate is self-consistent
    # along the stroke — robust high-pass residual of the raw centroid
    # ≤ grain_tol·w (clean ink and the synthetic renders sit at ~0.03 w at
    # the floor; crayon / litho grain at 0.2 w+ chases specks). If even the
    # top of the ladder is noisy, the shifts are smoothed along s instead.
    nrm0 = _normals(p, nsd, closed)
    k1 = max(1, int(round(1.0 / step)))
    ladder = [max(o_.pre_sigma, o_.pre_frac * w_s)]
    if o_.grain_tol > 0:
        ladder += [f * w_s for f in (0.15, 0.25, 0.35, 0.5) if f * w_s > ladder[0] * 1.15]
    hp = 0.0
    for sg in ladder:
        D, noise = F.blur(sg)
        if o_.grain_tol <= 0 or len(p) < 4 * k1:
            break
        o, v = _profiles(D, p[::k1], nrm0[::k1], R)
        c0, _, _, sat0 = _analyse(o, v, wl[::k1], o_.core)
        r = c0 - gaussian_filter1d(c0, w_s, mode=mode)
        r = r[~sat0] if (~sat0).sum() >= 8 else r
        hp = float(1.4826 * np.median(np.abs(r - np.median(r)))) / w_s
        if hp <= o_.grain_tol:
            break
    blur_used = sg
    extra_sd = 0.0
    if o_.grain_tol > 0 and hp > o_.grain_tol:
        extra_sd = min(2.0 * w_s, (hp / o_.grain_tol) ** 2 / (2 * np.sqrt(np.pi))) / step
    win = max(5, int(10 * w_s / step) | 1)
    valid = 0.0
    wm = None
    for _ in range(max(1, o_.iters)):
        nrm = _normals(p, nsd, closed)
        o, v = _profiles(D, p, nrm, R)
        cen, run, peak, sat = _analyse(o, v, wl, o_.core)
        # wide = two lines overlapping (crossing, T bar, blob): compare with the
        # running median of the stroke's own half-max run
        run_ref = median_filter(run, size=win, mode=mode)
        pk_ref = median_filter(peak, size=win, mode=mode)
        ok = (~sat) & (run <= o_.wide * np.maximum(run_ref, 0.75 * wl)) \
            & (run >= o_.narrow * wl) \
            & (peak >= o_.min_contrast * np.maximum(pk_ref, 1e-6)) \
            & (peak >= o_.min_snr * noise)
        if o_.along > 0 and ok.any():
            # average the cross-sections of neighbouring samples (each in its
            # own frame, so this smooths the centring ERROR, not the curve):
            # grain averages out along the line, never across it; rows that
            # failed the wide/saturated test do not contribute
            sd = o_.along * w_s / step
            wt = gaussian_filter1d(ok.astype(np.float64), sd, mode=mode)
            va = gaussian_filter1d(v * ok[:, None], sd, axis=0, mode=mode) / np.maximum(wt, 1e-9)[:, None]
            cen2, _, pk2, sat2 = _analyse(o, va, wl, o_.core)
            ok &= ~sat2 & (wt > 0.3)
            cen = cen2
        if o_.method == "steger":
            Dx, Dy, Dxx, Dxy, Dyy = F.steger(o_.steger_sigma * w_s)
            t_acc = np.zeros(len(p))
            good = np.ones(len(p), bool)
            nx, ny = nrm[:, 0], nrm[:, 1]
            for _k in range(max(1, o_.steger_steps)):
                q = p + t_acc[:, None] * nrm
                c = [q[:, 1], q[:, 0]]
                at = lambda A: map_coordinates(A, c, order=1, mode="nearest")
                den = at(Dxx) * nx * nx + 2 * at(Dxy) * nx * ny + at(Dyy) * ny * ny
                num = at(Dx) * nx + at(Dy) * ny
                good &= den < 0
                dt = np.where(den < 0, -num / np.where(den < 0, den, -1.0), 0.0)
                t_acc = t_acc + np.clip(dt, -max_shift, max_shift)
            shift = t_acc
            ok &= good
        else:
            shift = cen
        ok &= np.abs(shift) <= o_.reject * max_shift
        if skip_pts is not None and len(skip_pts):
            dd = np.min(np.linalg.norm(p[:, None, :] - skip_pts[None, :, :], axis=2), axis=1)
            ok &= dd > o_.skip_radius * w_s
        shift = _fill(np.clip(shift, -max_shift, max_shift), ok, closed)
        if o_.shift_median > 0:
            k = max(3, int(o_.shift_median * w_s / step) | 1)
            if k < len(shift):
                shift = median_filter(shift, size=k, mode=mode)
        ssd = max(o_.shift_sigma * w_s / step, extra_sd)
        if ssd > 0:
            shift = gaussian_filter1d(shift, ssd, mode=mode)
        p = p + shift[:, None] * nrm
        valid = float(ok.mean())
        if o_.remeasure_width:
            wm = np.where(ok, run, np.nan)
    # final light smoothing and output spacing
    p = _gsmooth(p, o_.smooth_sigma / step, closed)
    wq = width_in
    if wm is not None and np.isfinite(wm).any():
        wq = median_filter(_fill(np.nan_to_num(wm), np.isfinite(wm), closed), size=5, mode=mode)
    out, frac2 = _resample(p, o_.out_step, closed)
    fr1 = _arclen(p, closed)
    fr1 = fr1 / max(fr1[-1], 1e-12)
    wsrc = np.concatenate([wq, wq[:1]]) if closed else wq
    width = np.interp(frac2, fr1, wsrc) if (s.width is not None or wm is not None) else None
    meta = dict(s.meta)
    meta["subpixel_valid"] = round(valid, 3)
    meta["subpixel_blur"] = round(float(blur_used), 2)
    meta["subpixel_grain"] = round(hp, 3)
    return Stroke(out, width=width, closed=closed, meta=meta), {"valid": valid, "n": len(p)}


# --------------------------------------------------------------------------
# public
# --------------------------------------------------------------------------

def _estimate_w(F: _Field, drawing: Drawing) -> float:
    for k in ("line_width_px", "w_px"):
        v = drawing.meta.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    ws = [np.median(s.width) for s in drawing.strokes if s.width is not None and len(s.width)]
    if ws:
        return float(np.median(ws))
    # measure: half-max runs across a sample of stroke points, wide window
    rng = np.random.default_rng(0)
    D, _ = F.blur(0.5)
    runs = []
    for s in drawing.strokes:
        if len(s) < 5:
            continue
        p, _ = _resample(s.points, 1.0, s.closed)
        nrm = _normals(p, 2.0, s.closed)
        sel = rng.choice(len(p), size=min(len(p), 20), replace=False)
        o, v = _profiles(D, p[sel], nrm[sel], 15.0)
        _, run, _, sat = _analyse(o, v, np.full(len(sel), 6.0), 0.4)
        runs.extend(run[~sat].tolist())
    return float(np.median(runs)) if runs else 3.0


def refine_centrelines(gray: np.ndarray, drawing: Drawing, *, method: str = "core",
                       w: float | None = None, core: float = 0.4,
                       max_shift: float | None = 0.35, iters: int = 1,
                       smooth_sigma: float = 1.0, skip_meta_key: str | None = None,
                       skip_radius: float = 1.0, step: float = 0.5, out_step: float = 1.0,
                       wide: float = 1.35, min_contrast: float = 0.3, min_snr: float = 0.0,
                       pre_sigma: float = 0.5, pre_frac: float = 0.0,
                       shift_median: float = 0.0, shift_sigma: float = 0.0,
                       remeasure_width: bool = False, steger_sigma: float = 0.4,
                       steger_steps: int = 2, along: float = 0.0,
                       narrow: float = 0.4, grain_tol: float = 0.06,
                       reject: float = 1.0) -> Drawing:
    """Move every stroke point onto the ink centre (see module docstring).

    gray: (H, W) float in [0, 1] (or uint8), ink dark, in the SAME pixel
        frame as the drawing's points (x = column, y = row). Never modified.
    method: "core" (core-of-profile centroid) or "steger" (Hessian step).
    w: typical full line width, px — only a fallback for strokes with no
        width (default: drawing meta / stroke widths / measured).
    core: darkest fraction of each cross-section's peak height used for the
        centroid (0.4 = top 40 %).
    max_shift: largest accepted normal move, as a FRACTION of the local
        width (+0.25 px); larger moves are skipped and interpolated (`reject`
        > 1 clamps them instead).
    iters: refinement passes (normals re-estimated each pass).
    smooth_sigma: final Gaussian along the stroke, px (0 = off).
    skip_meta_key: stroke meta key holding [[x, y], …] points (e.g.
        "junctions") within `skip_radius`·w of which points are interpolated.
    min_snr: skip points whose profile peak is < this × image noise.
    pre_sigma / pre_frac: darkness blur σ = max(pre_sigma, pre_frac·w) px,
        per stroke (averages crayon / litho grain before the centroid).
    shift_median / shift_sigma: running median / Gaussian on the normal
        shifts along the stroke, in units of w (0 = off).
    """
    if method not in ("core", "steger"):
        raise ValueError(f"method must be 'core' or 'steger', got {method!r}")
    F = _Field(gray)
    w_default = float(w) if w else _estimate_w(F, drawing)
    o_ = _Opts(method=method, core=float(core),
               max_shift=0.35 if max_shift is None else float(max_shift), iters=int(iters),
               smooth_sigma=float(smooth_sigma), step=float(step), out_step=float(out_step),
               wide=float(wide), min_contrast=float(min_contrast), min_snr=float(min_snr),
               pre_sigma=float(pre_sigma), pre_frac=float(pre_frac),
               shift_median=float(shift_median), shift_sigma=float(shift_sigma),
               skip_radius=float(skip_radius), remeasure_width=bool(remeasure_width),
               steger_sigma=float(steger_sigma), steger_steps=int(steger_steps),
               along=float(along), narrow=float(narrow),
               grain_tol=float(grain_tol), reject=float(reject))
    out, n_pts, n_valid = [], 0, 0.0
    for s in drawing.strokes:
        skip = None
        if skip_meta_key and s.meta.get(skip_meta_key):
            skip = np.asarray(s.meta[skip_meta_key], dtype=np.float64).reshape(-1, 2)
        r, info = _refine_stroke(F, s, o_, w_default, skip)
        out.append(r)
        n_pts += info["n"]
        n_valid += info["valid"] * info["n"]
    meta = dict(drawing.meta)
    sp = {k: v for k, v in asdict(o_).items()}
    sp.update(w_default=round(w_default, 3), valid_frac=round(n_valid / max(n_pts, 1), 4))
    meta["subpixel"] = sp
    return Drawing(out, source=drawing.source, size=drawing.size, meta=meta)
