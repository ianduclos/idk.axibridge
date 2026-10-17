"""Texture of writing, measured the same way on scans and on generated rows.

Measure, never form: nothing here keeps a shape — only densities, run
counts and lengths relative to the line's own band height. Used by
`experiments/script_solid.py` to set the solid-script rows against real
calligraphy pages (measure-only sheets included: statistics only, per the
library policy) and to find where a row starts to read as writing.

Two units. W, the nib: the p80 stroke width (2·EDT on the skeleton) — the
calligrapher's own unit (nuqta, nib widths per x-height). Hb (older fields), the line's core-band height (the FWHM of the
line's row-ink profile — an x-height proxy that works for hanging and
baseline scripts alike). A mask is a bool array, ink True, lines horizontal.

Per line:
  cov_core   ink share inside the core band, over the line's ink extent
  cov_slab   ink share over the whole line slab (one line spacing tall)
  freq       ink runs crossed per Hb along rows through the core band
             (stroke frequency)
  run        mean ink run length along those rows (horizontal stroke body)
  contrast   p90 / p10 of stroke width (2·EDT on the skeleton)
  weight     median stroke width / Hb
  words_10   word count per 10 Hb (words: ink separated by ≥ gap_thr·Hb of
             empty columns in the slab)
  word_med, word_cv   word length median (Hb) and coefficient of variation
  gap_med, gap_cv     word space median (Hb) and CV
  colfill    share of the extent's columns holding ink
  freq_W     ink runs crossed per 10 W along core rows
  Hb_W       core band height in nib widths (inverse weight)
  word_W, gap_W   word length / word space medians in W (words split at ≥ 2 W of
             empty columns)
The texture distance uses FEATURES (the W-unit set + coverage + contrast).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi
from scipy.signal import find_peaks

FEATURES = ("cov_core", "freq_W", "Hb_W", "word_W", "word_cv", "gap_W", "contrast", "colfill")
REPORT = FEATURES + ("cov_slab", "freq", "run", "weight", "words_10", "word_med", "gap_med", "gap_cv", "spacing_Hb")


def rotate_mask(mask: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate so writing at page angle `angle_deg` (seen CCW from rightward)
    becomes horizontal."""
    if abs(angle_deg) < 1e-6:
        return np.asarray(mask, bool)
    r = ndi.rotate(np.asarray(mask, np.uint8) * 255, -angle_deg, reshape=True, order=1, cval=0)
    return r > 127


def stroke_widths(mask: np.ndarray) -> np.ndarray:
    from skimage.morphology import skeletonize  # noqa: PLC0415
    m = np.asarray(mask, bool)
    if not m.any():
        return np.zeros(0)
    edt = ndi.distance_transform_edt(m)
    return 2.0 * edt[skeletonize(m)]


def line_rows(mask: np.ndarray, *, min_sep_px: float = 8.0) -> tuple[np.ndarray, float]:
    """Line centres (row indices of the profile peaks) and the line spacing."""
    prof = mask.sum(axis=1).astype(float)
    w = np.median(stroke_widths(mask)) if mask.any() else 2.0
    hs = ndi.gaussian_filter1d(prof, max(w, 1.0))
    z = hs - hs.mean()
    ac = np.correlate(z, z, mode="full")[len(z) - 1:]
    lo = int(max(4 * w, min_sep_px))
    sp = None
    if len(ac) > lo + 3:
        pk, _ = find_peaks(ac[lo:])
        pk = pk[ac[lo:][pk] > 0]
        if len(pk):
            v = ac[lo:][pk]
            sp = float(pk[np.nonzero(v >= 0.5 * v.max())[0][0]] + lo)
    if sp is None:
        sp = float(len(prof))
    hs2 = ndi.gaussian_filter1d(prof, max(0.1 * sp, w))
    pk, _ = find_peaks(hs2, distance=max(int(0.55 * sp), 2), prominence=0.1 * hs2.max())
    if not len(pk):
        pk = np.array([int(np.argmax(hs2))])
    return pk, sp


def _runs(b: np.ndarray) -> list[tuple[int, int]]:
    d = np.diff(np.r_[0, b.astype(np.int8), 0])
    a, e = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    return list(zip(a.tolist(), e.tolist()))


def measure_line(mask: np.ndarray, centre: int, spacing: float, *, gap_thr: float = 0.5) -> dict | None:
    H = mask.shape[0]
    a, b = int(max(centre - 0.5 * spacing, 0)), int(min(centre + 0.5 * spacing, H))
    slab = mask[a:b]
    if slab.sum() < 50:
        return None
    prof = ndi.gaussian_filter1d(slab.sum(axis=1).astype(float), 1.0)
    pk = int(np.argmax(prof))
    half = 0.5 * prof[pk]
    lo = pk
    while lo > 0 and prof[lo - 1] >= half:
        lo -= 1
    hi = pk
    while hi < len(prof) - 1 and prof[hi + 1] >= half:
        hi += 1
    Hb = float(hi - lo + 1)
    cols = np.nonzero(slab.any(axis=0))[0]
    if len(cols) < 5 or Hb < 3:
        return None
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    ext = x1 - x0
    core = slab[lo:hi + 1, x0:x1]
    rows = np.unique(np.linspace(lo, hi, 5).round().astype(int))
    nruns, rl = [], []
    for r in rows:
        rr = _runs(slab[r, x0:x1])
        nruns.append(len(rr))
        rl += [e - s for s, e in rr]
    colink = slab[:, x0:x1].any(axis=0)
    # words: ink separated by ≥ gap_thr·Hb of empty columns
    gaps = [(s, e) for s, e in _runs(~colink)]
    big = [(s, e) for s, e in gaps if (e - s) >= gap_thr * Hb]
    edges = [0] + [v for g in big for v in g] + [ext]
    words = [(edges[i], edges[i + 1]) for i in range(0, len(edges) - 1, 2)]
    wl = np.array([e - s for s, e in words if e > s], float) / Hb
    gl = np.array([e - s for s, e in big], float) / Hb
    sw = stroke_widths(slab[:, x0:x1])
    sw = sw[sw > 0]
    Wn = float(np.percentile(sw, 80)) if len(sw) > 20 else float("nan")
    bigW = [(s, e) for s, e in gaps if np.isfinite(Wn) and (e - s) >= 2.0 * Wn]
    edW = [0] + [v for g in bigW for v in g] + [ext]
    wW = np.array([edW[i + 1] - edW[i] for i in range(0, len(edW) - 1, 2) if edW[i + 1] > edW[i]], float) / Wn
    gW = np.array([e - s for s, e in bigW], float) / Wn
    return {
        "Hb_px": Hb, "extent_Hb": ext / Hb,
        "cov_core": float(core.mean()),
        "cov_slab": float(slab[:, x0:x1].mean()),
        "freq": float(np.mean(nruns) / (ext / Hb)),
        "run": float(np.mean(rl) / Hb) if rl else 0.0,
        "contrast": float(np.percentile(sw, 90) / max(np.percentile(sw, 10), 1.0)) if len(sw) > 20 else np.nan,
        "weight": float(np.median(sw) / Hb) if len(sw) else np.nan,
        "words_10": float(len(wl) / (ext / Hb) * 10.0),
        "word_med": float(np.median(wl)) if len(wl) else np.nan,
        "word_cv_Hb": float(wl.std() / wl.mean()) if len(wl) > 2 else np.nan,
        "gap_med": float(np.median(gl)) if len(gl) else np.nan,
        "gap_cv": float(gl.std() / gl.mean()) if len(gl) > 2 else np.nan,
        "colfill": float(colink.mean()),
        "W_px": Wn,
        "freq_W": float(np.mean(nruns) / (ext / Wn) * 10.0) if np.isfinite(Wn) else np.nan,
        "Hb_W": float(Hb / Wn) if np.isfinite(Wn) else np.nan,
        "word_W": float(np.median(wW)) if len(wW) else np.nan,
        "word_cv": float(wW.std() / wW.mean()) if len(wW) > 2 else np.nan,
        "gap_W": float(np.median(gW)) if len(gW) else np.nan,
    }


def measure(mask: np.ndarray, *, angle: float = 0.0, min_extent_Hb: float = 6.0) -> list[dict]:
    """Every line of a mask → texture records (lines shorter than
    `min_extent_Hb` are dropped: fragments, folio numbers, catchwords)."""
    m = rotate_mask(mask, angle)
    cs, sp = line_rows(m)
    out = []
    for c in cs:
        r = measure_line(m, int(c), sp)
        if r is not None and r["extent_Hb"] >= min_extent_Hb:
            r["spacing_Hb"] = float(sp / r["Hb_px"])
            out.append(r)
    return out


def summarize(recs: list[dict]) -> dict:
    out = {"lines": len(recs)}
    for k in REPORT:
        v = np.array([r.get(k, np.nan) for r in recs], float)
        v = v[np.isfinite(v)]
        out[k] = [float(np.median(v)), float(np.percentile(v, 25)), float(np.percentile(v, 75))] if len(v) else None
    return out


def distance(rec: dict, ref: dict, feats=FEATURES) -> float:
    """Texture distance of one summary (medians) to a reference summary:
    RMS over features of (value − ref median) / ref IQR."""
    d = []
    for k in feats:
        a, b = rec.get(k), ref.get(k)
        if not a or not b:
            continue
        iqr = max(b[2] - b[1], 0.15 * abs(b[0]) + 1e-6)
        d.append(((a[0] if isinstance(a, list) else a) - b[0]) / iqr)
    return float(np.sqrt(np.mean(np.square(d)))) if d else float("nan")
