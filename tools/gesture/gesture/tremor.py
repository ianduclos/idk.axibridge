"""Tremor layer: fine-scale lateral line character below the grammar's σ = 2 w.

The grammar (and every generator built on it) draws geometry smoothed at
σ = 2 line widths, so anything finer — wavering, micro-hesitation,
pressure wobble — is absent by construction. This module measures that
missing band on real strokes, models it per artist, and adds it back.

**Residual.** A stroke is resampled at `STEP_W`·w (w = its median full line
width), smoothed at `lo_w`·w (P) and at `hi_w`·w with twicing (C, the
centreline — twicing removes the κσ²/2 shrinkage bias of a plain Gaussian,
which otherwise dominates the residual on curves); ends
are odd-reflection padded so the smoothing does not drag them. The lateral
residual is r(s) = (P − C)·n_C / w — a signed offset in line widths along s
(also in line widths). Corners (|κ_C|·w > `corner_kw`, dilated by 1.5·hi_w)
are excluded from statistics: a sharp turn rounded by C is structure, not
tremor.

**Model** (`TremorModel`, `fit_model`). A stationary Gaussian process given
by its one-sided PSD over spatial frequency (cycles per w), estimated by
Welch on corner-free runs; with a noise floor (extractor residual on
rendered smooth strokes) the floor PSD is subtracted per frequency, then
the measurement's own band-pass (`band_response`) is deconvolved (power
gain capped at 1/H2_MIN), so that measuring a drawing with modelled tremor
gives back the real residual. A
multiplicative envelope: gain per |κ|·w bin and per distance-from-end bin
(normalised so the mean squared gain is 1), and a per-stroke log-normal gain.
Synthesis is FFT filtering of white noise; nothing is resampled from real
strokes, so nothing can be memorised.

**Apply** (`apply_tremor`). Each stroke is resampled at `STEP_W`·w; the
synthetic residual (× amount) is added along the normal of the stroke
smoothed at 1 w. Open ends are pinned (residual ramped to 0 over
`END_PIN_W` w), and every open end that touched another stroke (within
`contact_w` w) is re-snapped: it follows the host's displacement at the
contact, ramped back over `SNAP_RAMP_W` w. Closed strokes get a periodic
residual.

Pure and deterministic: inputs never mutated; randomness via np.random.Generator.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import welch
from scipy.spatial import cKDTree

from .core import Drawing, Stroke
from .curvature import arclength, curvature, resample

__all__ = ["TremorModel", "lateral_residual", "residual_stats", "fit_model", "synth_residual",
           "apply_tremor", "detremor", "calibrate", "stroke_w", "LO_W", "HI_W", "STEP_W"]

LO_W = 0.3          # inner smoothing (w): finer than this is extraction territory
HI_W = 2.0          # centreline smoothing (w) — the grammar's resolution
STEP_W = 0.25       # sampling step (w); Nyquist wavelength 0.5 w
CORNER_KW = 0.18    # |κ_C|·w above this = a corner, not tremor
NSEG = 64           # Welch segment (samples) = 16 w → Δf = 1/16 cycles per w
END_PIN_W = 1.0     # open ends: residual ramps to 0 over this many w
SNAP_RAMP_W = 3.0   # re-snapped contacts: host displacement ramps out over this many w
KAPPA_EDGES = (0.0, 0.02, 0.05, 0.1, CORNER_KW)    # |κ|·w bins of the envelope
END_EDGES = (0.0, 3.0, 10.0, 30.0, np.inf)         # distance-from-end bins (w)
H2_MIN = 0.2        # deconvolution: largest power gain is 1 / H2_MIN


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def stroke_w(st: Stroke, default: float | None = None) -> float:
    if st.width is not None and len(st.width):
        return float(np.median(st.width))
    if default is None:
        raise ValueError("stroke has no width and no default given")
    return float(default)


def _smooth(p: np.ndarray, sd: float, closed: bool) -> np.ndarray:
    """Gaussian along the polyline (sd in samples). Open: odd reflection about
    each endpoint, so ends stay put and a straight end stays straight."""
    if sd <= 0 or len(p) < 3:
        return p.copy()
    if closed:
        return np.column_stack([gaussian_filter1d(p[:, i], sd, mode="wrap") for i in range(2)])
    k = int(min(len(p) - 1, np.ceil(4 * sd)))
    head = 2 * p[0] - p[k:0:-1]
    tail = 2 * p[-1] - p[-2:-k - 2:-1]
    q = np.vstack([head, p, tail])
    out = np.column_stack([gaussian_filter1d(q[:, i], sd, mode="nearest") for i in range(2)])
    return out[k:k + len(p)]


def _centreline(p: np.ndarray, sd: float, closed: bool) -> np.ndarray:
    """Gaussian smoothing with Tukey twicing, C = G·p + G·(p − G·p): the
    equivalent kernel 2G − G∗G has no second-order bias, so a curve is not
    pulled toward its centre of curvature (plain Gaussian smoothing shifts it
    by ≈ κσ²/2 — at σ = 2 w and κ·w = 0.05 that is 0.1 w, as big as tremor)."""
    g = _smooth(p, sd, closed)
    return g + _smooth(p - g, sd, closed)


def _normals(p: np.ndarray, closed: bool) -> np.ndarray:
    if closed:
        d = np.roll(p, -1, axis=0) - np.roll(p, 1, axis=0)
    else:
        d = np.gradient(p, axis=0)
    t = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
    return np.column_stack([-t[:, 1], t[:, 0]])


def _dilate(mask: np.ndarray, r: int, closed: bool) -> np.ndarray:
    if r <= 0 or not mask.any():
        return mask.copy()
    k = np.ones(2 * r + 1)
    if closed:
        m = np.concatenate([mask[-r:], mask, mask[:r]]).astype(float)
        return np.convolve(m, k, mode="same")[r:r + len(mask)] > 0
    return np.convolve(mask.astype(float), k, mode="same") > 0


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous True runs as (start, stop)."""
    m = np.concatenate([[False], mask, [False]]).astype(int)
    d = np.diff(m)
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------

def lateral_residual(points: np.ndarray, w: float, *, closed: bool = False, lo_w: float = LO_W,
                     hi_w: float = HI_W, step_w: float = STEP_W,
                     corner_kw: float = CORNER_KW) -> dict:
    """Band-passed lateral residual of one stroke, in line widths.

    Returns {"r": (n,) residual / w, "s": (n,) arc length / w, "kappa": (n,)
    |κ_C|·w, "dist_end": (n,) distance to the nearest open end / w (inf if
    closed), "corner": (n,) bool, "P": resampled points (px), "C": centreline
    (px), "n": normals of C, "step": px, "w": w, "closed": closed}."""
    step = step_w * w
    P0 = resample(np.asarray(points, float), step, closed=closed)
    n = len(P0)
    if n < 8:
        return {"r": np.zeros(0), "s": np.zeros(0), "kappa": np.zeros(0), "dist_end": np.zeros(0),
                "corner": np.zeros(0, bool), "P": P0, "C": P0, "n": np.zeros((n, 2)),
                "step": step, "w": w, "closed": closed}
    step = float(arclength(np.vstack([P0, P0[:1]]) if closed else P0)[-1] / (n if closed else n - 1))
    P = _smooth(P0, lo_w * w / step, closed)
    C = _centreline(P0, hi_w * w / step, closed)
    nrm = _normals(C, closed)
    r = np.einsum("ij,ij->i", P - C, nrm) / w
    k = np.abs(curvature(C, step, closed=closed)) * w
    corner = _dilate(k > corner_kw, int(np.ceil(1.5 * hi_w * w / step)), closed)
    s = np.arange(n) * step / w
    de = np.full(n, np.inf) if closed else np.minimum(s, s[-1] - s)
    return {"r": r, "s": s, "kappa": k, "dist_end": de, "corner": corner, "P": P, "C": C,
            "n": nrm, "step": step, "w": w, "closed": closed}


def drawing_residuals(drawing: Drawing, *, min_len_w: float = 20.0, **kw) -> list[dict]:
    """lateral_residual for every stroke ≥ min_len_w line widths long."""
    dw = drawing.meta.get("line_width_px")
    out = []
    for st in drawing.strokes:
        if len(st) < 3:
            continue
        w = stroke_w(st, dw if dw else None) if (st.width is not None or dw) else None
        if not w or w <= 0 or st.length() < min_len_w * w:
            continue
        res = lateral_residual(st.points, w, closed=st.closed, **kw)
        if len(res["r"]):
            res["length_w"] = st.length() / w
            out.append(res)
    return out


def _robust_rms(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    if x.size < 4:
        return float("nan")
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def _welch_runs(res: list[dict], nseg: int = NSEG, skip_end_w: float = 0.0) -> tuple[np.ndarray, np.ndarray, int]:
    """Pooled one-sided PSD (w² per cycle-per-w) over corner-free runs ≥ nseg."""
    acc, cnt = None, 0
    f = None
    for d in res:
        ok = ~d["corner"] & (d["dist_end"] >= skip_end_w)
        for a, b in _runs(ok):
            if b - a < nseg:
                continue
            f, p = welch(d["r"][a:b], fs=1.0 / STEP_W, nperseg=nseg, noverlap=nseg // 2,
                         detrend="constant", window="hann")
            nn = (b - a - nseg) // (nseg // 2) + 1
            acc = p * nn if acc is None else acc + p * nn
            cnt += nn
    if acc is None:
        f = np.fft.rfftfreq(nseg, STEP_W)
        return f, np.zeros_like(f), 0
    return f, acc / cnt, cnt


def _acf_length(res: list[dict], max_lag_w: float = 8.0) -> float:
    """Correlation length (w): first lag where the pooled ACF of corner-free
    interiors drops below 1/e."""
    L = int(max_lag_w / STEP_W)
    num = np.zeros(L + 1)
    den = np.zeros(L + 1)
    for d in res:
        ok = ~d["corner"]
        for a, b in _runs(ok):
            x = d["r"][a:b] - d["r"][a:b].mean()
            m = len(x)
            if m < 2 * L:
                continue
            for lag in range(L + 1):
                num[lag] += float(np.dot(x[:m - lag], x[lag:]))
                den[lag] += m - lag
    if den[0] == 0:
        return float("nan")
    acf = (num / np.maximum(den, 1)) / (num[0] / den[0])
    below = np.flatnonzero(acf < np.exp(-1))
    if not len(below):
        return float(max_lag_w)
    i = below[0]
    # linear interpolation between i-1 and i
    a0, a1 = acf[i - 1], acf[i]
    t = (a0 - np.exp(-1)) / max(a0 - a1, 1e-12)
    return float((i - 1 + t) * STEP_W)


def residual_stats(res: list[dict]) -> dict:
    """Summary statistics of a set of residuals (all in line widths)."""
    if not res:
        return {"n_strokes": 0}
    r_all = np.concatenate([d["r"][~d["corner"]] for d in res])
    k_all = np.concatenate([d["kappa"][~d["corner"]] for d in res])
    e_all = np.concatenate([d["dist_end"][~d["corner"]] for d in res])
    f, psd, nseg = _welch_runs(res)
    out = {
        "n_strokes": len(res), "n_samples": int(r_all.size),
        "corner_frac": float(1 - r_all.size / max(sum(len(d["r"]) for d in res), 1)),
        "rms": float(np.sqrt(np.mean(r_all ** 2))) if r_all.size else float("nan"),
        "rms_robust": _robust_rms(r_all),
        "q50_abs": float(np.median(np.abs(r_all))) if r_all.size else float("nan"),
        "q90_abs": float(np.quantile(np.abs(r_all), 0.9)) if r_all.size else float("nan"),
        "q99_abs": float(np.quantile(np.abs(r_all), 0.99)) if r_all.size else float("nan"),
        "kurtosis": float(np.mean(r_all ** 4) / max(np.mean(r_all ** 2) ** 2, 1e-30)) if r_all.size else float("nan"),
        "corr_len_w": _acf_length(res),
        "freqs": f.tolist(), "psd": psd.tolist(), "n_welch": nseg,
    }
    # band powers (as rms contributions): wavelength bands in w
    df = f[1] - f[0] if len(f) > 1 else 1.0
    for lo, hi in ((1.0, 2.0), (2.0, 4.0), (4.0, 8.0), (8.0, 16.0)):
        sel = (f > 1.0 / hi) & (f <= 1.0 / lo)
        out[f"rms_lambda_{lo:g}_{hi:g}w"] = float(np.sqrt(np.sum(psd[sel]) * df))
    kb = []
    for lo, hi in zip(KAPPA_EDGES[:-1], KAPPA_EDGES[1:]):
        sel = (k_all >= lo) & (k_all < hi)
        kb.append(float(np.sqrt(np.mean(r_all[sel] ** 2))) if sel.sum() > 50 else float("nan"))
    out["rms_by_kappa"] = kb
    eb = []
    for lo, hi in zip(END_EDGES[:-1], END_EDGES[1:]):
        sel = (e_all >= lo) & (e_all < hi)
        eb.append(float(np.sqrt(np.mean(r_all[sel] ** 2))) if sel.sum() > 50 else float("nan"))
    out["rms_by_end"] = eb
    per = []
    for d in res:
        x = d["r"][~d["corner"] & (d["dist_end"] >= 3)]
        if x.size >= 40:
            per.append((d.get("length_w", d["s"][-1]), float(np.sqrt(np.mean(x ** 2)))))
    if per:
        per = np.array(per)
        out["stroke_rms_q"] = [float(v) for v in np.quantile(per[:, 1], [0.1, 0.5, 0.9])]
        out["stroke_log_rms_sd"] = float(np.std(np.log(np.maximum(per[:, 1], 1e-6))))
        lb = []
        for lo, hi in ((0, 60), (60, 150), (150, 400), (400, np.inf)):
            sel = (per[:, 0] >= lo) & (per[:, 0] < hi)
            lb.append(float(np.median(per[sel, 1])) if sel.sum() >= 3 else float("nan"))
        out["stroke_rms_by_len"] = lb   # length bins (w): <60, 60–150, 150–400, ≥400
        if len(per) > 5:
            out["len_rms_spearman"] = float(_spearman(per[:, 0], per[:, 1]))
    return out


def _spearman(a, b) -> float:
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

@dataclass
class TremorModel:
    name: str
    freqs: list            # cycles per w
    psd: list              # one-sided PSD of the lateral DISPLACEMENT (w² per cycle-per-w):
                           # measured residual PSD − floor, deconvolved by band_response²
    rms: float             # √∫psd df — stationary displacement rms (w) before envelope
    kappa_edges: list = field(default_factory=lambda: list(KAPPA_EDGES))
    kappa_gain: list = field(default_factory=lambda: [1.0] * (len(KAPPA_EDGES) - 1))
    end_edges: list = field(default_factory=lambda: [float(x) for x in END_EDGES])
    end_gain: list = field(default_factory=lambda: [1.0] * (len(END_EDGES) - 1))
    stroke_log_sd: float = 0.0
    lo_w: float = LO_W
    hi_w: float = HI_W
    step_w: float = STEP_W
    info: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        d = asdict(self)
        d["end_edges"] = [None if not np.isfinite(x) else x for x in d["end_edges"]]
        return d

    @staticmethod
    def from_json(d: dict) -> "TremorModel":
        d = dict(d)
        d["end_edges"] = [np.inf if x is None else float(x) for x in d["end_edges"]]
        return TremorModel(**d)

    def save(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_json()))

    @staticmethod
    def load(path) -> "TremorModel":
        return TremorModel.from_json(json.loads(Path(path).read_text()))


def _gain_table(res: list[dict], key: str, edges, floor_var: float, tot_var: float) -> list[float]:
    r = np.concatenate([d["r"][~d["corner"]] for d in res])
    v = np.concatenate([d[key][~d["corner"]] for d in res])
    g = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (v >= lo) & (v < hi)
        if sel.sum() < 200 or tot_var <= 0:
            g.append(float("nan"))
            continue
        g.append(float(np.sqrt(max(np.mean(r[sel] ** 2) - floor_var, 0.0) / tot_var)))
    g = np.array(g)
    g[~np.isfinite(g)] = 1.0 if not np.isfinite(g).any() else float(np.nanmean(g))
    return [float(x) for x in g]


def band_response(f, lo_w: float = LO_W, hi_w: float = HI_W) -> np.ndarray:
    """Transfer function of `lateral_residual` at spatial frequency f
    (cycles per w): Gaussian at lo_w minus the twiced Gaussian at hi_w."""
    f = np.asarray(f, float)
    g_lo = np.exp(-2 * np.pi ** 2 * lo_w ** 2 * f ** 2)
    g_hi = np.exp(-2 * np.pi ** 2 * hi_w ** 2 * f ** 2)
    return g_lo - (1 - (1 - g_hi) ** 2)


def fit_model(res: list[dict], floor: list[dict] | None = None, *, name: str = "") -> TremorModel:
    """Fit a TremorModel to real residuals, subtracting the floor's PSD (and
    variance, in the envelope bins) when given."""
    f, psd, n = _welch_runs(res)
    if n == 0:
        raise ValueError("no corner-free run long enough to estimate a spectrum")
    floor_var = 0.0
    psd_floor = np.zeros_like(psd)
    if floor:
        f2, pf, nf = _welch_runs(floor)
        if nf:
            psd_floor = np.interp(f, f2, pf)
            floor_var = float(np.mean(np.concatenate([d["r"][~d["corner"]] for d in floor]) ** 2))
    p = np.maximum(psd - psd_floor, 0.0)
    # the measured residual is the displacement seen through the band-pass
    # H(f) = G_lo − T_hi; deconvolve (power gain capped at 1/H2_MIN) so that
    # MEASURING a drawing with modelled tremor reproduces the real residual
    p = p / np.maximum(band_response(f) ** 2, H2_MIN)
    p[0] = 0.0   # no DC: the residual is about the stroke's own centreline
    df = float(f[1] - f[0])
    rms = float(np.sqrt(np.sum(p) * df))
    tot_var = max(float(np.mean(np.concatenate([d["r"][~d["corner"]] for d in res]) ** 2)) - floor_var, 1e-12)
    kg = _gain_table(res, "kappa", KAPPA_EDGES, floor_var, tot_var)
    eg = _gain_table(res, "dist_end", END_EDGES, floor_var, tot_var)
    per = []
    for d in res:
        x = d["r"][~d["corner"] & (d["dist_end"] >= 3)]
        if x.size >= 80:
            per.append(np.mean(x ** 2))
    sd = 0.0
    if len(per) >= 5:
        per = np.array(per)
        tv = np.maximum(per - floor_var, 0.05 * per)
        # observed spread of log-rms includes sampling noise; keep 70 %
        sd = 0.7 * float(np.std(0.5 * np.log(tv)))
    return TremorModel(name=name, freqs=[float(x) for x in f], psd=[float(x) for x in p], rms=rms,
                       kappa_gain=kg, end_gain=eg, stroke_log_sd=sd,
                       info={"n_strokes": len(res), "n_welch": int(n),
                             "floor_var": floor_var, "real_var": tot_var + floor_var,
                             "psd_real": [float(x) for x in psd], "psd_floor": [float(x) for x in psd_floor]})


def synth_residual(model: TremorModel, n: int, rng: np.random.Generator, *, closed: bool = False) -> np.ndarray:
    """n samples (spacing model.step_w) of the stationary residual, in w."""
    if n <= 0:
        return np.zeros(0)
    f_m = np.asarray(model.freqs, float)
    S_m = np.asarray(model.psd, float)
    if model.rms <= 0 or not np.any(S_m > 0):
        return np.zeros(n)
    N = n if closed else int(2 ** np.ceil(np.log2(n + 2 * NSEG)))
    f = np.fft.rfftfreq(N, model.step_w)
    S = np.interp(f, f_m, S_m, right=0.0)
    S[0] = 0.0
    full = S[0] + 2 * S[1:].sum() - (S[-1] if N % 2 == 0 else 0.0)
    mean2 = full / N
    if mean2 <= 0:
        return np.zeros(n)
    A = np.sqrt(S / mean2) * model.rms
    e = rng.standard_normal(N)
    y = np.fft.irfft(np.fft.rfft(e) * A, n=N)
    if closed:
        return y
    o = int(rng.integers(0, N - n + 1))
    return y[o:o + n]


def _envelope(model: TremorModel, kappa: np.ndarray, dist_end: np.ndarray) -> np.ndarray:
    ke = np.asarray(model.kappa_edges, float)
    ki = np.clip(np.searchsorted(ke, kappa, side="right") - 1, 0, len(model.kappa_gain) - 1)
    ee = np.asarray(model.end_edges, float)
    ei = np.clip(np.searchsorted(ee, dist_end, side="right") - 1, 0, len(model.end_gain) - 1)
    return np.asarray(model.kappa_gain)[ki] * np.asarray(model.end_gain)[ei]


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _perturb_stroke(st: Stroke, w: float, model: TremorModel, rng, amount: float):
    """Returns (new_points, resampled_base, displacement) for one stroke."""
    step = model.step_w * w
    P = resample(st.points, step, closed=st.closed)
    n = len(P)
    if n < 4:
        return P, P, np.zeros_like(P)
    step = float(arclength(np.vstack([P, P[:1]]) if st.closed else P)[-1] / (n if st.closed else n - 1))
    nrm = _normals(_smooth(P, 1.0 * w / step, st.closed), st.closed)
    C = _centreline(P, model.hi_w * w / step, st.closed)
    k = np.abs(curvature(C, step, closed=st.closed)) * w
    s = np.arange(n) * step / w
    de = np.full(n, np.inf) if st.closed else np.minimum(s, s[-1] - s)
    r = synth_residual(model, n, rng, closed=st.closed)
    gain = float(np.exp(model.stroke_log_sd * rng.standard_normal())) if model.stroke_log_sd > 0 else 1.0
    r = r * _envelope(model, k, de) * gain * amount
    if not st.closed:
        r = r * _smoothstep(de / END_PIN_W)
    disp = nrm * (r * w)[:, None]
    return P + disp, P, disp


def apply_tremor(drawing: Drawing, model: TremorModel, rng: np.random.Generator, amount: float = 1.0, *,
                 w: float | None = None, contact_w: float = 2.0) -> Drawing:
    """Add modelled tremor to every stroke of a (smooth) drawing.

    w: line width (px) for strokes without widths (default: drawing
    meta["line_width_px"]). amount scales the residual (0 = identity).
    Open ends are pinned; ends that touched another stroke within
    contact_w·w follow that stroke's displacement at the contact."""
    if amount == 0 or not drawing.strokes:
        return Drawing([Stroke(s.points.copy(), None if s.width is None else s.width.copy(), s.closed,
                               dict(s.meta)) for s in drawing.strokes],
                       source=drawing.source, size=drawing.size, meta=dict(drawing.meta))
    dw = w if w is not None else drawing.meta.get("line_width_px")
    base, disp, new, ws = [], [], [], []
    for st in drawing.strokes:
        wi = stroke_w(st, dw) if (st.width is not None or dw) else None
        if wi is None or len(st) < 3 or st.length() < 4 * wi:
            base.append(st.points.copy())
            disp.append(np.zeros_like(st.points))
            new.append(st.points.copy())
            ws.append(wi)
            continue
        q, P, d = _perturb_stroke(st, wi, model, rng, amount)
        base.append(P)
        disp.append(d)
        new.append(q)
        ws.append(wi)
    # re-snap open ends that touched another stroke
    if len(new) > 1:
        allp = np.vstack(base)
        owner = np.concatenate([np.full(len(p), i) for i, p in enumerate(base)])
        idx = np.concatenate([np.arange(len(p)) for p in base])
        tree = cKDTree(allp)
        for i, st in enumerate(drawing.strokes):
            if st.closed or len(base[i]) < 2 or ws[i] is None:
                continue
            q = new[i].copy()
            s = arclength(base[i]) / ws[i]
            for e in (0, -1):
                cand = [j for j in tree.query_ball_point(base[i][e], contact_w * ws[i]) if owner[j] != i]
                if not cand:
                    continue
                dd = np.linalg.norm(allp[cand] - base[i][e], axis=1)
                j = cand[int(np.argmin(dd))]
                delta = disp[owner[j]][idx[j]] - disp[i][e]
                de = s if e == 0 else s[-1] - s
                q = q + delta[None, :] * (1 - _smoothstep(de / SNAP_RAMP_W))[:, None]
            new[i] = q
    out = []
    for st, q, P in zip(drawing.strokes, new, base):
        width = None
        if st.width is not None:
            if len(q) == len(st.points):
                width = st.width.copy()
            else:
                s0 = arclength(np.vstack([st.points, st.points[:1]]) if st.closed else st.points)
                s0 = s0[:len(st.points)] / max(s0[-1], 1e-12)
                s1 = arclength(np.vstack([P, P[:1]]) if st.closed else P)[:len(P)]
                s1 = s1 / max(s1[-1], 1e-12)
                width = np.interp(s1, s0, st.width)
        meta = dict(st.meta)
        meta["tremor"] = {"model": model.name, "amount": float(amount)}
        out.append(Stroke(q, width=width, closed=st.closed, meta=meta))
    meta = dict(drawing.meta)
    meta["tremor"] = {"model": model.name, "amount": float(amount)}
    return Drawing(out, source=drawing.source, size=drawing.size, meta=meta)


def detremor(drawing: Drawing, *, hi_w: float = HI_W, w: float | None = None,
             corner_kw: float = CORNER_KW) -> Drawing:
    """Remove each stroke's own fine-scale lateral residual (below hi_w), but
    keep corners (|κ|·w > corner_kw, soft-dilated) as drawn. Endpoints kept."""
    dw = w if w is not None else drawing.meta.get("line_width_px")
    out = []
    for st in drawing.strokes:
        wi = stroke_w(st, dw) if (st.width is not None or dw) else None
        if wi is None or len(st) < 8 or st.length() < 4 * wi:
            out.append(Stroke(st.points.copy(), None if st.width is None else st.width.copy(),
                              st.closed, dict(st.meta)))
            continue
        res = lateral_residual(st.points, wi, closed=st.closed, lo_w=0.0, hi_w=hi_w, corner_kw=corner_kw)
        P = res["P"]
        if len(res["r"]) == 0:
            out.append(Stroke(st.points.copy(), None if st.width is None else st.width.copy(),
                              st.closed, dict(st.meta)))
            continue
        keep = gaussian_filter1d(res["corner"].astype(float), 1.0 / STEP_W,
                                 mode="wrap" if st.closed else "nearest")
        keep = np.clip(keep * 1.5, 0, 1)
        q = P - res["n"] * (res["r"] * wi * (1 - keep))[:, None]
        if not st.closed:
            q[0], q[-1] = P[0], P[-1]
        width = None
        if st.width is not None:
            s0 = arclength(np.vstack([st.points, st.points[:1]]) if st.closed else st.points)[:len(st.points)]
            s1 = arclength(np.vstack([P, P[:1]]) if st.closed else P)[:len(P)]
            width = np.interp(s1 / max(s1[-1], 1e-12), s0 / max(s0[-1], 1e-12), st.width)
        out.append(Stroke(q, width=width, closed=st.closed, meta={**st.meta, "detremor": True}))
    return Drawing(out, source=drawing.source, size=drawing.size, meta={**drawing.meta, "detremor": True})


def calibrate(model: TremorModel, smooth: list[Drawing], target_rms: float, rng: np.random.Generator,
              iters: int = 2) -> TremorModel:
    """Scale the model so that MEASURING `smooth` drawings with tremor added
    gives a corner-free residual rms of target_rms (in w; the drawings' own
    residual is subtracted in variance). Envelope, pinned ends and the capped
    deconvolution all lose a little amplitude; this puts it back."""
    def meas(ds):
        res = [r for d in ds for r in drawing_residuals(d)]
        x = np.concatenate([r["r"][~r["corner"]] for r in res]) if res else np.zeros(1)
        return float(np.mean(x ** 2))
    base = meas(smooth)
    m = model
    for _ in range(iters):
        got = meas([apply_tremor(d, m, rng) for d in smooth]) - base
        if got <= 0:
            break
        k2 = float(np.clip(target_rms ** 2 / got, 0.25, 4.0))
        m = TremorModel(**{**m.__dict__, "psd": [p * k2 for p in m.psd], "rms": m.rms * np.sqrt(k2),
                           "info": {**m.info, "calibration": m.info.get("calibration", 1.0) * float(np.sqrt(k2))}})
    return m
