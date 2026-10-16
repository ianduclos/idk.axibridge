"""Scoring for raster → strokes extractors (the stage-1 bake-off).

Every extraction technique is a module exposing

    extract(gray: np.ndarray, **kw) -> Drawing

with `gray` float64 (H, W) in [0, 1], **ink dark, paper light** (the bench
inverts white-on-black sources before calling), stroke points in pixels
(x = column, y = row), per the contract in ../README.md.

Two kinds of score:

* `score_gt` — synthetic renders with known strokes (`synth`): coverage,
  precision, continuity, fragmentation, centreline error, κ error.
* `score_real` — museum scans, no ground truth: agreement with a reference
  ink mask/skeleton plus continuity and smoothness proxies.

All lengths in scores are dimensionless (÷ line width w or ÷ ref_length)
unless the key says `_px`.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree
from skimage.filters import threshold_sauvola
from skimage.morphology import remove_small_objects, skeletonize

from .core import Drawing
from .curvature import kappa_s, resample


def _dense(drawing: Drawing, step: float = 1.0):
    """All stroke points resampled at `step` px. Returns (points, stroke_id)."""
    pts, ids = [], []
    for i, s in enumerate(drawing.strokes):
        if len(s) < 2:
            continue
        r = resample(s.points, step, closed=s.closed)
        pts.append(r)
        ids.append(np.full(len(r), i))
    if not pts:
        return np.zeros((0, 2)), np.zeros(0, int)
    return np.vstack(pts), np.concatenate(ids)


def _kappa_dense(drawing: Drawing, sigma: float, trim: float):
    """κ samples (unsigned) with positions, excluding `trim` px at open ends."""
    P, K = [], []
    for s in drawing.strokes:
        if len(s) < 3 or s.length() < 2 * trim + 4 * sigma:
            continue
        sv, k, sm = kappa_s(s.points, sigma, step=1.0, closed=s.closed)
        keep = np.ones(len(sv), bool) if s.closed else (sv > trim) & (sv < sv[-1] - trim)
        P.append(sm[keep])
        K.append(np.abs(k[keep]))
    if not P:
        return np.zeros((0, 2)), np.zeros(0)
    return np.vstack(P), np.concatenate(K)


def score_gt(truth: Drawing, found: Drawing, line_width: float) -> dict:
    """Score an extraction against the strokes that were rendered.

    tol = max(1.5 px, 0.5 w) for coverage/precision.
    continuity: for each truth stroke, the fraction of its length covered by
    the single best extracted stroke (1.0 = never broken), length-weighted.
    fragments: mean number of extracted strokes covering ≥10% of a truth stroke.
    kappa_err: median | |κ_found| − |κ_truth| | · ref_length, interior only,
    both at σ = 2w.
    """
    w = float(line_width)
    tol = max(1.5, 0.5 * w)
    T, Tid = _dense(truth)
    F, Fid = _dense(found)
    out = {"n_truth": len(truth.strokes), "n_found": len(found.strokes)}
    if len(F) == 0:
        out.update(coverage=0.0, precision=0.0, continuity=0.0, fragments=0.0,
                   centre_err_px=float("nan"), kappa_err=float("nan"))
        return out
    tf = cKDTree(F)
    d_tf, j_tf = tf.query(T)
    covered = d_tf <= tol
    out["coverage"] = float(covered.mean())
    out["precision"] = float((cKDTree(T).query(F)[0] <= tol).mean())
    out["centre_err_px"] = float(np.median(d_tf[covered])) if covered.any() else float("nan")
    cont, frags, wts = [], [], []
    for i in range(len(truth.strokes)):
        m = Tid == i
        if not m.any():
            continue
        owners = Fid[j_tf[m]][covered[m]]
        n = m.sum()
        if len(owners) == 0:
            cont.append(0.0); frags.append(0); wts.append(n); continue
        counts = np.bincount(owners)
        cont.append(counts.max() / n)
        frags.append(int((counts >= 0.1 * n).sum()))
        wts.append(n)
    wts = np.asarray(wts, float)
    out["continuity"] = float(np.average(cont, weights=wts)) if len(wts) else 0.0
    out["fragments"] = float(np.mean(frags)) if frags else 0.0
    sig = 2 * w
    TP, TK = _kappa_dense(truth, sig, trim=3 * w)
    FP, FK = _kappa_dense(found, sig, trim=3 * w)
    if len(TP) and len(FP):
        d, j = cKDTree(TP).query(FP)
        ok = d <= tol
        ref = truth.ref_length()
        out["kappa_err"] = float(np.median(np.abs(FK[ok] - TK[j[ok]])) * ref) if ok.any() else float("nan")
        out["kappa_truth_median"] = float(np.median(TK) * ref)
    else:
        out["kappa_err"] = float("nan")
    return out


def reference_ink(gray: np.ndarray, window: int | None = None, min_area: int = 30):
    """A deliberately plain reference: Sauvola ink mask, its skeleton and the
    median line width w (px). Used only to SCORE real scans, never to extract."""
    H, W = gray.shape
    win = window or max(15, (min(H, W) // 60) | 1)
    mask = gray < threshold_sauvola(gray, window_size=win, k=0.2)
    mask = remove_small_objects(mask, max_size=min_area)
    skel = skeletonize(mask)
    dt = distance_transform_edt(mask)
    w = float(np.median(2 * dt[skel])) if skel.any() else 3.0
    return mask, skel, max(w, 1.0)


def score_real(gray: np.ndarray, found: Drawing, ref=None) -> dict:
    """Proxies without ground truth. `ref` = reference_ink(gray) (cache it
    across methods: it is the same for every technique on one scan).

    ink_coverage: fraction of reference-skeleton pixels within 1.5 w of a stroke.
    ink_precision: fraction of stroke points within 1 w of reference ink.
    mean_len: length-weighted mean stroke length ÷ ref_length (continuity proxy).
    short_frac: fraction of strokes shorter than 6 w (fragments, spurs, specks).
    roughness: median over strokes of RMS dκ/ds · ref_length² at σ = 2 w —
               high = jittery centrelines (staircasing, junction kinks).
    """
    mask, skel, w = ref if ref is not None else reference_ink(gray)
    F, Fid = _dense(found)
    out = {"w_px": w, "n_strokes": len(found.strokes)}
    if len(F) == 0:
        out.update(ink_coverage=0.0, ink_precision=0.0, mean_len=0.0, short_frac=1.0,
                   roughness=float("nan"))
        return out
    sk = np.column_stack(np.nonzero(skel))[:, ::-1].astype(float)  # (x, y)
    if len(sk):
        out["ink_coverage"] = float((cKDTree(F).query(sk)[0] <= 1.5 * w).mean())
    else:
        out["ink_coverage"] = float("nan")
    dist_to_ink = distance_transform_edt(~mask)
    xi = np.clip(np.round(F[:, 0]).astype(int), 0, gray.shape[1] - 1)
    yi = np.clip(np.round(F[:, 1]).astype(int), 0, gray.shape[0] - 1)
    out["ink_precision"] = float((dist_to_ink[yi, xi] <= w).mean())
    lens = np.array([s.length() for s in found.strokes])
    ref_len = found.ref_length()
    out["mean_len"] = float((lens**2).sum() / max(lens.sum(), 1e-9) / ref_len)
    out["short_frac"] = float((lens < 6 * w).mean())
    rough = []
    for s in found.strokes:
        if s.length() < 12 * w:
            continue
        sv, k, _ = kappa_s(s.points, 2 * w, step=1.0, closed=s.closed)
        if len(k) > 5:
            rough.append(np.sqrt(np.mean(np.gradient(k, 1.0) ** 2)) * ref_len**2)
    out["roughness"] = float(np.median(rough)) if rough else float("nan")
    return out
