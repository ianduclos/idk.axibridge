# FROZEN from research commit c712045: tools/gesture/gesture/broadnib.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Broad-nib width model: a centreline swept by a flat nib (calligraphy).

A reed/broad pen is a straight edge of length W held at a (nearly) constant
angle φ. Moving in direction θ it lays down a band whose width across the
path is the projection of the edge onto the path normal; a little ink
spread / nib thickness adds a hairline w_min:

    width(θ) = W · |sin(θ − φ)| + w_min          (Minkowski: segment ⊕ disc)

|sin| has period π, so the unknown stroke DIRECTION (a scan cannot tell)
does not matter. Angles are PAGE angles: counter-clockwise from the
rightward horizontal as the sheet is seen (image y points down, so
θ = atan2(−dy, dx)). φ is reported in [0°, 180°): the direction of the nib
EDGE; the thickest strokes run at φ + 90°, the hairlines at φ.

Contents
- synthesis: `synth_centreline`, `sweep_polygon` (shapely), `render_mask`
  (anti-aliased raster, ink dark) — ground truth for the fitter.
- measurement: `width_samples` (θ, width) along a Stroke's interior, away
  from ends and junctions; `fit_nib` (grid over φ + closed-form W, w_min,
  Huber IRLS; R², a θ-permutation null R²); `fit_drawing` (pooled sheet fit
  + per-stroke fits).
- plotter rendering of width with a constant-width pen (the "thickness
  gap"): (a) `outline_paths` — the swept outline as closed contours;
  (b) `concentric_paths` — hatch-free fill by inward offsets of the outline;
  (c) `multipass_paths` — parallel passes along the centreline, as many as
  the local width needs. `paths_stats`, `draw_paths`, `fidelity` compare them.

Pure and deterministic; inputs are never mutated. Units: whatever the
points are in (pixels for scans, mm for plotter geometry).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import gaussian_filter1d

__all__ = [
    "nib_width", "page_angle", "synth_centreline", "sweep_polygon", "render_mask",
    "width_samples", "NibFit", "fit_nib", "fit_drawing",
    "outline_paths", "concentric_paths", "multipass_paths", "paths_stats",
    "draw_paths", "fidelity", "model_widths",
]


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def nib_width(theta, phi, W, w_min=0.0):
    """Model width for page direction(s) θ (rad) — see module docstring."""
    return W * np.abs(np.sin(np.asarray(theta) - phi)) + w_min


def _arclen(p: np.ndarray) -> np.ndarray:
    if len(p) < 2:
        return np.zeros(len(p))
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def _resample(p: np.ndarray, step: float, extra: np.ndarray | None = None):
    s = _arclen(p)
    if s[-1] <= 0:
        return p.copy(), (None if extra is None else extra.copy()), s
    n = max(int(np.ceil(s[-1] / step)) + 1, 2)
    t = np.linspace(0.0, s[-1], n)
    q = np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])
    e = None if extra is None else np.interp(t, s, extra)
    return q, e, t


def page_angle(points: np.ndarray, sigma: float = 0.0, step: float | None = None) -> np.ndarray:
    """Tangent page angle θ (rad) at each point of a polyline (image coords,
    y down). σ (same units as points) smooths the coordinates first; the
    polyline should be roughly uniformly sampled at `step`."""
    p = np.asarray(points, dtype=np.float64)
    if step is None:
        d = np.linalg.norm(np.diff(p, axis=0), axis=1)
        step = float(np.median(d)) if len(d) else 1.0
    if sigma > 0 and len(p) > 3:
        sd = sigma / max(step, 1e-9)
        p = np.column_stack([gaussian_filter1d(p[:, 0], sd, mode="nearest"),
                             gaussian_filter1d(p[:, 1], sd, mode="nearest")])
    g = np.gradient(p, axis=0)
    return np.arctan2(-g[:, 1], g[:, 0])


def synth_centreline(rng: np.random.Generator, *, length: float = 600.0, step: float = 1.0,
                     kappa_sd: float = 0.012, corr: float = 60.0, start=(0.0, 0.0),
                     heading: float | None = None) -> np.ndarray:
    """A smooth random centreline (image coords): κ(s) = Gaussian-smoothed
    noise (correlation `corr`, sd `kappa_sd` 1/units), integrated."""
    n = int(length / step) + 1
    k = gaussian_filter1d(rng.normal(size=n), corr / step, mode="wrap")
    k = k / (k.std() + 1e-12) * kappa_sd
    h0 = rng.uniform(0, 2 * np.pi) if heading is None else heading
    th = h0 + np.cumsum(k) * step
    p = np.column_stack([np.cumsum(np.cos(th)), np.cumsum(-np.sin(th))]) * step
    return p - p[0] + np.asarray(start, dtype=np.float64)


# ---------------------------------------------------------------------------
# synthesis
# ---------------------------------------------------------------------------

def sweep_polygon(points: np.ndarray, phi: float, W: float, w_min: float = 0.0, *,
                  twist: float = 0.0, pressure: np.ndarray | None = None, step: float | None = None):
    """Shapely geometry of a flat nib (edge length W at page angle φ, rad)
    dragged along `points` (image coords), dilated by w_min/2.

    twist: total change of φ along the stroke (rad, linear in s, centred).
    pressure: optional (N,) multiplier on W per input point."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    p = np.asarray(points, dtype=np.float64)
    if step is None:
        step = max(W / 8.0, 0.25)
    q, pr, s = _resample(p, step, None if pressure is None else np.asarray(pressure, float))
    L = max(s[-1], 1e-9)
    ph = phi + twist * (s / L - 0.5)
    Wl = W * (np.ones(len(q)) if pr is None else pr)
    h = 0.5 * Wl[:, None] * np.column_stack([np.cos(ph), -np.sin(ph)])
    a, b = q - h, q + h
    quads = []
    for i in range(len(q) - 1):
        poly = Polygon([a[i], b[i], b[i + 1], a[i + 1]])
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.area > 0:
            quads.append(poly)
    # the nib itself at both ends (zero-length motion still leaves a mark)
    for i in (0, len(q) - 1):
        quads.append(Polygon([a[i], b[i], b[i] + 1e-3, a[i] + 1e-3]).buffer(0))
    g = unary_union(quads)
    if w_min > 0:
        g = g.buffer(w_min / 2.0, quad_segs=8)
    return g


def _polys(geom):
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    out = []
    for g in getattr(geom, "geoms", []):
        out += _polys(g)
    return out


def render_mask(geoms, size: tuple[int, int], *, ss: int = 4) -> np.ndarray:
    """Anti-aliased raster of shapely polygon(s): float (H, W) in [0, 1],
    paper 1, ink 0 (the extractor's convention). size = (width, height)."""
    from PIL import Image, ImageDraw

    Wd, Hd = size
    img = Image.new("L", (Wd * ss, Hd * ss), 0)
    dr = ImageDraw.Draw(img)
    gl = geoms if isinstance(geoms, (list, tuple)) else [geoms]
    for g in gl:
        for poly in _polys(g):
            ext = (np.asarray(poly.exterior.coords) + 0.5) * ss - 0.5
            dr.polygon([tuple(v) for v in ext], fill=255)
            for ring in poly.interiors:
                r = (np.asarray(ring.coords) + 0.5) * ss - 0.5
                dr.polygon([tuple(v) for v in r], fill=0)
    small = img.resize((Wd, Hd), Image.Resampling.BOX)
    return 1.0 - np.asarray(small, dtype=np.float64) / 255.0


# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------

def width_samples(stroke, *, w_ref: float | None = None, sigma_w: float = 1.0,
                  trim_w: float = 1.5, junction_w: float = 1.5, max_kw: float = 0.35,
                  step_w: float = 0.5) -> dict:
    """(θ, width) samples along a Stroke's interior.

    Excluded: the first/last trim_w·w of open strokes (terminals are wedges
    and blobs, not motion), anything within junction_w·w of a junction in
    stroke.meta["junctions"] (widths at crossings are sums), and points of
    high curvature |κ|·w > max_kw (the swept band's inner side folds there,
    so the straight-motion projection does not hold). w = w_ref or the
    stroke's median width. Tangents at σ = sigma_w·w. Returns dict with
    theta, width, weight (arc length per sample), s."""
    if stroke.width is None or len(stroke) < 4:
        return {"theta": np.zeros(0), "width": np.zeros(0), "weight": np.zeros(0), "s": np.zeros(0)}
    p = np.asarray(stroke.points, dtype=np.float64)
    wv = np.asarray(stroke.width, dtype=np.float64)
    if stroke.closed:
        p = np.vstack([p, p[:1]])
        wv = np.concatenate([wv, wv[:1]])
    w = float(w_ref if w_ref is not None else np.median(wv))
    w = max(w, 1e-6)
    step = max(step_w * w, 0.5)
    q, ww, s = _resample(p, step, wv)
    if len(q) < 4:
        return {"theta": np.zeros(0), "width": np.zeros(0), "weight": np.zeros(0), "s": np.zeros(0)}
    sd = sigma_w * w / step
    qs = np.column_stack([gaussian_filter1d(q[:, 0], sd, mode="wrap" if stroke.closed else "nearest"),
                          gaussian_filter1d(q[:, 1], sd, mode="wrap" if stroke.closed else "nearest")])
    d1 = np.gradient(qs, axis=0) / step
    d2 = np.gradient(d1, axis=0) / step
    sp = np.linalg.norm(d1, axis=1) + 1e-12
    kap = (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / sp ** 3
    theta = np.arctan2(-d1[:, 1], d1[:, 0])
    keep = np.ones(len(q), bool)
    if not stroke.closed:
        keep &= (s >= trim_w * w) & (s <= s[-1] - trim_w * w)
    js = stroke.meta.get("junctions", []) if isinstance(stroke.meta, dict) else []
    if js:
        J = np.asarray(js, dtype=np.float64).reshape(-1, 2)
        dmin = np.min(np.linalg.norm(q[:, None, :] - J[None, :, :], axis=2), axis=1)
        keep &= dmin > junction_w * np.maximum(ww, w)
    keep &= np.abs(kap) * w <= max_kw
    keep &= np.isfinite(ww) & (ww > 0)
    return {"theta": theta[keep], "width": ww[keep], "weight": np.full(int(keep.sum()), step),
            "s": s[keep]}


@dataclass
class NibFit:
    phi: float                 # nib edge page angle, rad, [0, π)
    W: float                   # nib edge length (width units)
    w_min: float               # hairline
    r2: float                  # weighted R² of the |sin| model
    r2_null: float             # same fit with θ permuted (no direction dependence)
    rmse: float
    n: int
    span: float                # circular spread of 2θ in [0, 1] (0 = one direction only)
    extra: dict = field(default_factory=dict)

    @property
    def phi_deg(self) -> float:
        return float(np.rad2deg(self.phi))

    @property
    def contrast(self) -> float:
        return float(self.W / max(self.W + self.w_min, 1e-9))

    def as_dict(self) -> dict:
        return {"phi_deg": round(self.phi_deg, 2), "W": round(float(self.W), 4),
                "w_min": round(float(self.w_min), 4), "contrast": round(self.contrast, 3),
                "r2": round(float(self.r2), 4), "r2_null": round(float(self.r2_null), 4),
                "rmse": round(float(self.rmse), 4), "n": int(self.n), "span": round(float(self.span), 3),
                **self.extra}


def _ls_all(A: np.ndarray, y: np.ndarray, wt: np.ndarray):
    """Weighted LS of y ≈ W·A + c for every row of A (n_phi, n) at once,
    with W ≥ 0 and c ≥ 0 enforced by refitting on the boundary."""
    sw = wt.sum()
    Sa = (A * wt).sum(1)
    Saa = (A * A * wt).sum(1)
    Sy = (y * wt).sum()
    Say = (A * y * wt).sum(1)
    det = sw * Saa - Sa * Sa
    W = np.where(np.abs(det) > 1e-12, (sw * Say - Sa * Sy) / np.where(det == 0, 1, det), 0.0)
    c = (Sy - W * Sa) / sw
    # boundaries
    neg_c = c < 0
    if neg_c.any():
        W = np.where(neg_c, Say / np.maximum(Saa, 1e-12), W)
        c = np.where(neg_c, 0.0, c)
    neg_W = W < 0
    if neg_W.any():
        W = np.where(neg_W, 0.0, W)
        c = np.where(neg_W, Sy / sw, c)
    return W, c


def _fit_core(theta, y, wt, phis):
    A = np.abs(np.sin(theta[None, :] - phis[:, None]))
    W, c = _ls_all(A, y, wt)
    res = y[None, :] - (W[:, None] * A + c[:, None])
    sse = (res * res * wt).sum(1)
    i = int(np.argmin(sse))
    return phis[i], W[i], c[i], sse[i]


def fit_nib(theta, width, weights=None, *, phi_step_deg: float = 1.0, robust: bool = True,
            max_samples: int = 20000, seed: int = 0) -> NibFit:
    """Fit width = W·|sin(θ − φ)| + w_min. Grid over φ (closed-form W, w_min
    per φ), then a fine grid ±phi_step around the best, then (robust) Huber
    IRLS reweighting at the chosen φ (3 rounds, φ re-searched each round).
    r2_null: the same model fitted after permuting θ (what direction-free
    width variation alone scores). span: |mean(e^{2iθ})| complement —
    1 − R̄ of the doubled angles (0 = every sample at one direction, so φ is
    unidentifiable; > 0.3 is comfortable)."""
    theta = np.asarray(theta, dtype=np.float64)
    y = np.asarray(width, dtype=np.float64)
    wt = np.ones_like(y) if weights is None else np.asarray(weights, dtype=np.float64)
    ok = np.isfinite(theta) & np.isfinite(y) & (wt > 0)
    theta, y, wt = theta[ok], y[ok], wt[ok]
    n = len(y)
    if n < 8:
        return NibFit(float("nan"), float("nan"), float("nan"), float("nan"), float("nan"),
                      float("nan"), n, 0.0)
    rng = np.random.default_rng(seed)
    if n > max_samples:
        idx = rng.choice(n, max_samples, replace=False)
        theta, y, wt = theta[idx], y[idx], wt[idx]
    span = float(1.0 - np.abs(np.sum(wt * np.exp(2j * theta)) / wt.sum()))
    coarse = np.deg2rad(np.arange(0.0, 180.0, phi_step_deg))
    rw = np.ones_like(y)
    phi, W, c = 0.0, 0.0, float(np.average(y, weights=wt))
    for it in range(4 if robust else 1):
        ww = wt * rw
        phi, W, c, _ = _fit_core(theta, y, ww, coarse)
        fine = phi + np.deg2rad(np.linspace(-phi_step_deg, phi_step_deg, 21))
        phi, W, c, _ = _fit_core(theta, y, ww, fine)
        if not robust:
            break
        r = y - nib_width(theta, phi, W, c)
        mad = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-9
        k = 1.345 * mad
        rw = np.where(np.abs(r) <= k, 1.0, k / np.abs(r))
    fitw = wt * rw
    r = y - nib_width(theta, phi, W, c)
    ybar = np.average(y, weights=fitw)
    sst = float(np.sum(fitw * (y - ybar) ** 2)) + 1e-12
    r2 = 1.0 - float(np.sum(fitw * r * r)) / sst
    rmse = float(np.sqrt(np.average(r * r, weights=fitw)))
    # null: θ permuted (keeps the width distribution, breaks direction dependence)
    tp = rng.permutation(theta)
    p0, W0, c0, _ = _fit_core(tp, y, fitw, coarse)
    r0 = y - nib_width(tp, p0, W0, c0)
    r2_null = 1.0 - float(np.sum(fitw * r0 * r0)) / sst
    return NibFit(float(phi % np.pi), float(W), float(c), r2, r2_null, rmse, int(n), span)


def fit_drawing(drawing, *, min_len_w: float = 8.0, min_samples: int = 30,
                min_span: float = 0.25, per_stroke: bool = True, min_rel_width: float = 0.0,
                **sample_kw) -> dict:
    """Pooled sheet fit + per-stroke fits. Width units are normalised by the
    drawing's median stroke width (so W, w_min read in median widths).
    min_rel_width: skip strokes whose median width is below this fraction of
    the ink-weighted 75th-percentile stroke width (drops illumination
    hairlines and ruling remnants that are not pen strokes of the hand).
    Returns {"sheet": NibFit, "strokes": [dict], "w_med": float,
    "phi_spread_deg": circular sd of per-stroke φ (doubled-angle stats)}."""
    ws = [float(np.median(st.width)) for st in drawing.strokes if st.width is not None and len(st.width)]
    w_med = float(np.median(ws)) if ws else 1.0
    w_floor = 0.0
    if min_rel_width > 0 and ws:
        sw = [(float(np.median(st.width)), st.length()) for st in drawing.strokes
              if st.width is not None and len(st.width)]
        v = np.array([a for a, _ in sw]); L = np.array([b for _, b in sw])
        o = np.argsort(v); c = np.cumsum(L[o]) / L.sum()
        w_floor = min_rel_width * float(v[o][np.searchsorted(c, 0.75)])
    TH, WI, WT = [], [], []
    per = []
    for i, st in enumerate(drawing.strokes):
        if st.width is None or st.length() < min_len_w * w_med:
            continue
        if w_floor > 0 and float(np.median(st.width)) < w_floor:
            continue
        smp = width_samples(st, w_ref=w_med, **sample_kw)
        if len(smp["theta"]) == 0:
            continue
        TH.append(smp["theta"]); WI.append(smp["width"] / w_med); WT.append(smp["weight"])
        if per_stroke and len(smp["theta"]) >= min_samples:
            f = fit_nib(smp["theta"], smp["width"] / w_med, smp["weight"], phi_step_deg=2.0)
            if f.span >= min_span:
                per.append({"i": i, "len_w": st.length() / w_med, **f.as_dict()})
    if not TH:
        return {"sheet": fit_nib([], []), "strokes": [], "w_med": w_med, "phi_spread_deg": float("nan")}
    sheet = fit_nib(np.concatenate(TH), np.concatenate(WI), np.concatenate(WT))
    if per:
        ph = np.deg2rad([d["phi_deg"] for d in per])
        wts = np.array([d["len_w"] for d in per])
        Rb = np.abs(np.sum(wts * np.exp(2j * ph)) / wts.sum())
        spread = float(np.rad2deg(np.sqrt(max(-2.0 * np.log(max(Rb, 1e-12)), 0.0)) / 2.0))
    else:
        spread = float("nan")
    return {"sheet": sheet, "strokes": per, "w_med": w_med, "phi_spread_deg": spread,
            "samples": (np.concatenate(TH), np.concatenate(WI))}


def model_widths(points: np.ndarray, phi: float, W: float, w_min: float, *, sigma: float = 0.0) -> np.ndarray:
    """Width the nib model assigns to each point of a centreline."""
    return nib_width(page_angle(points, sigma=sigma), phi, W, w_min)


# ---------------------------------------------------------------------------
# plotter rendering (constant-width pen)
# ---------------------------------------------------------------------------

def outline_paths(geom, *, min_area: float = 0.0) -> list[np.ndarray]:
    """(a) The swept outline as closed contours (exteriors + holes): one
    contiguous closed line per connected ribbon. Rings repeat no point."""
    out = []
    for poly in _polys(geom):
        if poly.area < min_area:
            continue
        for ring in [poly.exterior, *poly.interiors]:
            c = np.asarray(ring.coords)[:-1]
            if len(c) >= 3:
                out.append(c)
    return out


def concentric_paths(geom, pen: float, *, max_rings: int = 200) -> list[np.ndarray]:
    """(b) Hatch-free fill: the outline inset by pen/2, then again every
    `pen` until nothing is left. Every path is a closed ring (contiguous,
    no hatching); ribbons thinner than one pen collapse to their outline."""
    out = []
    g = geom.buffer(-pen / 2.0, join_style="round") if geom is not None else None
    k = 0
    if g is None or g.is_empty:   # thinner than the pen everywhere: keep the outline
        return outline_paths(geom)
    while g is not None and not g.is_empty and k < max_rings:
        out += outline_paths(g)
        g = g.buffer(-pen, join_style="round")
        k += 1
    return out


def multipass_paths(points: np.ndarray, width: np.ndarray, pen: float, *, sigma: float | None = None,
                    min_run: float | None = None) -> list[np.ndarray]:
    """(c) Parallel passes along the centreline: pass k sits at normal offset
    o_k = (k − (n−1)/2)·pen and is drawn only where the local width covers it
    (|o_k| ≤ (width − pen)/2, the centre pass always). Passes split into runs
    where the width drops, so thick/thin becomes 1…n strands."""
    p = np.asarray(points, dtype=np.float64)
    w = np.asarray(width, dtype=np.float64)
    if len(p) < 2:
        return []
    step = max(pen / 2.0, 1e-3)
    q, wq, _ = _resample(p, step, w)
    sd = (sigma if sigma is not None else 2.0 * pen) / step
    qs = np.column_stack([gaussian_filter1d(q[:, 0], sd, mode="nearest"),
                          gaussian_filter1d(q[:, 1], sd, mode="nearest")])
    t = np.gradient(qs, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    nrm = np.column_stack([-t[:, 1], t[:, 0]])
    n = max(int(np.ceil(np.max(wq) / pen)), 1)
    min_run = 2.0 * pen if min_run is None else min_run
    out = []
    for k in range(n):
        o = (k - (n - 1) / 2.0) * pen
        on = (np.abs(o) <= np.maximum((wq - pen) / 2.0, 0.0) + 1e-9) | (abs(o) < pen / 2)
        if abs(o) < pen / 2:
            on[:] = True
        idx = np.flatnonzero(on)
        if not len(idx):
            continue
        cuts = np.flatnonzero(np.diff(idx) > 1)
        for seg in np.split(idx, cuts + 1):
            if len(seg) * step < min_run and abs(o) >= pen / 2:
                continue
            out.append(q[seg] + o * nrm[seg])
    return out


def paths_stats(paths: list[np.ndarray], closed: bool | list[bool] = False) -> dict:
    """Pen-down length, number of paths (= pen lifts + 1), points."""
    if isinstance(closed, bool):
        closed = [closed] * len(paths)
    L = 0.0
    for p, c in zip(paths, closed):
        pp = np.vstack([p, p[:1]]) if c else p
        L += float(np.sum(np.linalg.norm(np.diff(pp, axis=0), axis=1)))
    return {"paths": len(paths), "length": L, "points": int(sum(len(p) for p in paths))}


def draw_paths(paths, size: tuple[int, int], pen_px: float, *, closed: bool | list[bool] = False,
               ss: int = 2) -> np.ndarray:
    """Raster of pen paths drawn with a round pen of diameter pen_px:
    float (H, W), paper 1, ink 0."""
    from PIL import Image, ImageDraw

    if isinstance(closed, bool):
        closed = [closed] * len(paths)
    Wd, Hd = size
    img = Image.new("L", (Wd * ss, Hd * ss), 0)
    dr = ImageDraw.Draw(img)
    r = pen_px * ss / 2.0
    lw = max(int(round(pen_px * ss)), 1)
    for p, c in zip(paths, closed):
        q = (np.asarray(p) + 0.5) * ss - 0.5
        if c:
            q = np.vstack([q, q[:1]])
        if len(q) >= 2:
            dr.line([tuple(v) for v in q], fill=255, width=lw, joint="curve")
        for v in (q[0], q[-1]):
            dr.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=255)
    small = img.resize((Wd, Hd), Image.Resampling.BOX)
    return 1.0 - np.asarray(small, dtype=np.float64) / 255.0


def fidelity(drawn: np.ndarray, target: np.ndarray, thr: float = 0.5) -> dict:
    """Compare a pen raster with the target ribbon raster (both paper 1 /
    ink 0): IoU, coverage (target ink covered), spill (pen ink outside)."""
    a = drawn < thr
    b = target < thr
    inter = float(np.sum(a & b))
    uni = float(np.sum(a | b)) + 1e-9
    return {"iou": inter / uni, "coverage": inter / (float(b.sum()) + 1e-9),
            "spill": float(np.sum(a & ~b)) / (float(a.sum()) + 1e-9)}
