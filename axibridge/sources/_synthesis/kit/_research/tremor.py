# FROZEN from research commit c712045: tools/gesture/gesture/tremor.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
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
HI_W2 = 4.0         # v2 measurement band: 0.3–4 w (λ up to ≈ 20 w)
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


def drawing_residuals(drawing: Drawing, *, min_len_w: float = 20.0, context: Drawing | None = None,
                      **kw) -> list[dict]:
    """lateral_residual for every stroke ≥ min_len_w line widths long.

    context: the full drawing the strokes come from (strokes matched by
    identity, e.g. `long_drawing(d)` against `d`). When given, every residual
    also carries "jdist": distance (w) from each sample to the nearest point of
    any OTHER stroke of the context — proximity to junctions and crossings."""
    dw = drawing.meta.get("line_width_px")
    out = []
    tree = None
    for st in drawing.strokes:
        if len(st) < 3:
            continue
        w = stroke_w(st, dw if dw else None) if (st.width is not None or dw) else None
        if not w or w <= 0 or st.length() < min_len_w * w:
            continue
        res = lateral_residual(st.points, w, closed=st.closed, **kw)
        if len(res["r"]):
            res["length_w"] = st.length() / w
            if context is not None:
                if tree is None:
                    tree, owner = _context_tree(context, w)
                own = next((i for i, c in enumerate(context.strokes) if c is st), -1)
                res["jdist"] = _junction_distance(tree, owner, own, res["C"]) / w
            out.append(res)
    return out


def _context_tree(context: Drawing, w: float):
    pts, own = [], []
    for i, c in enumerate(context.strokes):
        if len(c) < 2:
            q = c.points
        else:
            q = resample(c.points, 0.5 * w, closed=c.closed)
        pts.append(q)
        own.append(np.full(len(q), i))
    return cKDTree(np.vstack(pts)), np.concatenate(own)


def _junction_distance(tree, owner, own: int, P: np.ndarray, k: int = 96) -> np.ndarray:
    k = min(k, len(owner))
    dd, ii = tree.query(P, k=k)
    dd, ii = np.atleast_2d(dd), np.atleast_2d(ii)
    other = owner[np.minimum(ii, len(owner) - 1)] != own
    out = np.where(other.any(1), np.where(other, dd, np.inf).min(1), dd[:, -1])
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
    # v2 (bursty) — absent / None in v1 models, ignored by apply_tremor(mode="v1")
    version: int = 1
    regime: dict | None = None     # {"kind": "lognormal", "sigma", "corr_w"} or
                                   # {"kind": "markov2", "gain_lo", "gain_hi", "dwell_lo_w", "dwell_hi_w"}
    kinks: dict | None = None      # {"rate_per_100w", "amp_w", "amp_log_sd", "tau_w"}

    def to_json(self) -> dict:
        d = asdict(self)
        d["end_edges"] = [None if not np.isfinite(x) else x for x in d["end_edges"]]
        return d

    @staticmethod
    def from_json(d: dict) -> "TremorModel":
        d = {k: v for k, v in d.items() if k in TremorModel.__dataclass_fields__}
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


def _perturb_stroke(st: Stroke, w: float, model: TremorModel, rng, amount: float, v2: bool = False):
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
    r = r * _envelope(model, k, de) * gain
    if v2:
        if model.regime:
            r = r * synth_regime(model.regime, n, rng, closed=st.closed)
        if model.kinks:
            r = r + synth_kinks(model.kinks, n, rng, closed=st.closed)
    r = r * amount
    if not st.closed:
        r = r * _smoothstep(de / END_PIN_W)
    disp = nrm * (r * w)[:, None]
    return P + disp, P, disp


def apply_tremor(drawing: Drawing, model: TremorModel, rng: np.random.Generator, amount: float = 1.0, *,
                 w: float | None = None, contact_w: float = 2.0, mode: str = "auto") -> Drawing:
    """Add modelled tremor to every stroke of a (smooth) drawing.

    mode: "auto" uses everything the model has (v2 regime + kinks when
    present); "v1" forces the stationary round-3 layer (regime and kinks
    ignored, identical output to v1 for the same rng).

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
        q, P, d = _perturb_stroke(st, wi, model, rng, amount,
                                  v2=(mode != "v1" and model.version >= 2))
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
        meta["tremor"] = {"model": model.name, "amount": float(amount), "mode": mode}
        out.append(Stroke(q, width=width, closed=st.closed, meta=meta))
    meta = dict(drawing.meta)
    meta["tremor"] = {"model": model.name, "amount": float(amount), "mode": mode}
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
              iters: int = 2, hi_w: float = HI_W) -> TremorModel:
    """Scale the model so that MEASURING `smooth` drawings with tremor added
    gives a corner-free residual rms of target_rms (in w; the drawings' own
    residual is subtracted in variance). Envelope, pinned ends and the capped
    deconvolution all lose a little amplitude; this puts it back."""
    def meas(ds):
        res = [r for d in ds for r in drawing_residuals(d, hi_w=hi_w)]
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


# ---------------------------------------------------------------------------
# v2: burstiness measurement
# ---------------------------------------------------------------------------

ENV_WIN_W = 2.0      # envelope: Gaussian-weighted local rms, σ = 2 w (window ≈ 5 w)
SHAKY_LOG = np.log(1.5)   # shaky = local rms > 1.5 × the set's median local rms
KINK_K = 3.5         # kink = excursion |r| > KINK_K × the set's rms
MIN_RUN = 32         # corner-free runs ≥ 8 w


def _phase_surrogate(x: np.ndarray, rng) -> np.ndarray:
    """Same periodogram, random phases: the stationary Gaussian null."""
    X = np.fft.rfft(x - x.mean())
    ph = rng.uniform(0, 2 * np.pi, len(X))
    ph[0] = 0.0
    if len(x) % 2 == 0:
        ph[-1] = 0.0
    return np.fft.irfft(np.abs(X) * np.exp(1j * ph), n=len(x))


def _log_env(x: np.ndarray, win_w: float = ENV_WIN_W) -> np.ndarray:
    e2 = gaussian_filter1d(x ** 2, win_w / STEP_W, mode="reflect")
    return 0.5 * np.log(np.maximum(e2, 1e-12))


def _acf_len(xs: list[np.ndarray], max_lag: int) -> float:
    num = np.zeros(max_lag + 1)
    den = np.zeros(max_lag + 1)
    for x in xs:
        x = x - x.mean()
        m = len(x)
        for lag in range(min(max_lag, m - 1) + 1):
            num[lag] += float(np.dot(x[:m - lag], x[lag:]))
            den[lag] += m - lag
    if den[0] == 0 or num[0] <= 0:
        return float("nan")
    acf = (num / np.maximum(den, 1)) / (num[0] / den[0])
    below = np.flatnonzero(acf < np.exp(-1))
    if not len(below):
        return float(max_lag * STEP_W)
    i = below[0]
    t = (acf[i - 1] - np.exp(-1)) / max(acf[i - 1] - acf[i], 1e-12)
    return float((i - 1 + t) * STEP_W)


def _dwells(mask: np.ndarray) -> tuple[list[float], list[float]]:
    """Interior (uncensored) run lengths (w) of True and of False."""
    on, off = [], []
    n = len(mask)
    for a, b in _runs(mask):
        if a > 0 and b < n:
            on.append((b - a) * STEP_W)
    for a, b in _runs(~mask):
        if a > 0 and b < n:
            off.append((b - a) * STEP_W)
    return on, off


def _bimodal_dbic(x: np.ndarray) -> float:
    """(BIC₁ − BIC₂)/n for 1- vs 2-component Gaussian mixtures (>0 favours two)."""
    try:
        from sklearn.mixture import GaussianMixture
    except Exception:  # noqa: BLE001
        return float("nan")
    x = np.asarray(x, float).reshape(-1, 1)
    if len(x) < 50:
        return float("nan")
    b1 = GaussianMixture(1, random_state=0).fit(x).bic(x)
    b2 = GaussianMixture(2, random_state=0, n_init=2).fit(x).bic(x)
    return float((b1 - b2) / len(x))


def _burst_core(runs: list[dict], scale: float, med_env: float, bimodal: bool = True) -> dict:
    """Statistics of a list of runs {"x", "kappa", "dist_end", "jdist", "len"}."""
    xs = [r["x"] for r in runs]
    L = np.concatenate([_log_env(x) for x in xs])
    allx = np.concatenate(xs)
    within = np.concatenate([_log_env(x) - _log_env(x).mean() for x in xs])
    shaky = L > med_env + SHAKY_LOG
    on, off = [], []
    kinks, kd2, total = 0, 0, 0.0
    d2s = np.concatenate([np.diff(x, 2) for x in xs])
    d2_sc = float(np.sqrt(np.mean(d2s ** 2))) if d2s.size else 1.0
    o = 0
    for x in xs:
        m = shaky[o:o + len(x)]
        o += len(x)
        a, b = _dwells(m)
        on += a
        off += b
        kinks += len(_runs(np.abs(x) > KINK_K * scale))
        kd2 += len(_runs(np.abs(np.diff(x, 2)) > 5.0 * d2_sc))
        total += len(x) * STEP_W
    sub = slice(None, None, max(int(ENV_WIN_W / STEP_W), 1))
    return {
        "rms": float(np.sqrt(np.mean(allx ** 2))),
        "kurtosis": float(np.mean(allx ** 4) / max(np.mean(allx ** 2) ** 2, 1e-30)),
        "env_lsd": float(np.std(L)), "env_lsd_within": float(np.std(within)),
        "env_skew": float(np.mean((L - L.mean()) ** 3) / max(np.std(L) ** 3, 1e-12)),
        "env_corr_w": _acf_len([_log_env(x) for x in xs], int(30 / STEP_W)),
        "shaky_frac": float(shaky.mean()),
        "dwell_shaky_w": float(np.mean(on)) if on else float("nan"),
        "dwell_calm_w": float(np.mean(off)) if off else float("nan"),
        "dwell_shaky_cv": float(np.std(on) / np.mean(on)) if len(on) > 3 else float("nan"),
        "dwell_calm_cv": float(np.std(off) / np.mean(off)) if len(off) > 3 else float("nan"),
        "n_dwell": [len(on), len(off)],
        "kink_rate": 100.0 * kinks / max(total, 1e-9),
        "kink_d2_rate": 100.0 * kd2 / max(total, 1e-9),
        "bimodal_dbic": _bimodal_dbic(within[sub]) if bimodal else float("nan"),
        "L": L, "shaky": shaky,
    }


def burst_runs(res: list[dict], *, skip_end_w: float = 2.0, min_jdist: float = 0.0) -> list[dict]:
    """Corner-free interior runs (≥ MIN_RUN samples) with their context;
    min_jdist > 0 also cuts out samples that close (w) to another stroke."""
    runs = []
    for d in res:
        ok = ~d["corner"] & (d["dist_end"] >= skip_end_w)
        if min_jdist > 0 and d.get("jdist") is not None:
            ok &= d["jdist"] >= min_jdist
        for a, b in _runs(ok):
            if b - a < MIN_RUN:
                continue
            jd = d.get("jdist")
            runs.append({"x": d["r"][a:b], "kappa": d["kappa"][a:b], "dist_end": d["dist_end"][a:b],
                         "jdist": jd[a:b] if jd is not None else np.full(b - a, np.inf),
                         "len": float(d.get("length_w", d["s"][-1]))})
    return runs


def kappa_normalise(runs: list[dict]) -> list[dict]:
    """Divide out the set's own rms-by-|κ| profile (normalised to rms 1): what
    is left is burstiness that curvature does not explain."""
    k_all = np.concatenate([r["kappa"] for r in runs])
    x_all = np.concatenate([r["x"] for r in runs])
    prof = []
    for lo, hi in zip(KAPPA_EDGES[:-1], KAPPA_EDGES[1:]):
        sel = (k_all >= lo) & (k_all < hi)
        prof.append(np.sqrt(np.mean(x_all[sel] ** 2)) if sel.sum() > 50 else np.nan)
    prof = np.asarray(prof)
    prof[~np.isfinite(prof)] = np.nanmean(prof) if np.isfinite(prof).any() else 1.0
    prof = prof / max(np.sqrt(np.mean(x_all ** 2)), 1e-12)
    e = np.asarray(KAPPA_EDGES, float)
    mid = 0.5 * (e[:-1] + e[1:])
    return [{**r, "x": r["x"] / np.interp(r["kappa"], mid, prof)} for r in runs]


def burst_stats(res: list[dict], rng: np.random.Generator, *, ref_scale: float | None = None,
                surrogate: bool = True, kappa_norm: bool = False, min_jdist: float = 0.0,
                bimodal: bool = True) -> dict:
    """Burstiness of a set of residuals (band as measured), against the
    phase-randomised surrogate of every run (same spectrum per run, so same
    per-stroke level; stationary within the run).

    env = log local rms (Gaussian window σ = ENV_WIN_W); shaky = env above
    median + log 1.5; kinks = excursions above KINK_K × rms; triggers =
    Spearman ρ of env with |κ|, distance from end, junction distance, and of
    a stroke's mean env with its length."""
    runs = burst_runs(res, min_jdist=min_jdist)
    if not runs:
        return {"n_strokes": 0}
    if kappa_norm:
        runs = kappa_normalise(runs)
    allx = np.concatenate([r["x"] for r in runs])
    scale = ref_scale if ref_scale is not None else float(np.sqrt(np.mean(allx ** 2)))
    L0 = np.concatenate([_log_env(r["x"]) for r in runs])
    med = float(np.median(L0))
    core = _burst_core(runs, scale, med, bimodal)
    out = {k: v for k, v in core.items() if k not in ("L", "shaky")}
    out["n_strokes"] = len(res)
    out["n_runs"] = len(runs)
    out["run_w"] = float(sum(len(r["x"]) for r in runs) * STEP_W)
    L, sh = core["L"], core["shaky"]
    k = np.concatenate([r["kappa"] for r in runs])
    de = np.concatenate([r["dist_end"] for r in runs])
    jd = np.concatenate([r["jdist"] for r in runs])
    out["env_lsd_excess"] = float("nan")
    out["trig_kappa"] = _spearman(k, L)
    out["trig_end"] = _spearman(np.minimum(de, 1e6), L)
    out["trig_junction"] = _spearman(np.minimum(jd, 1e6), L) if np.isfinite(jd).any() else float("nan")
    lens = np.array([r["len"] for r in runs])
    means = np.array([_log_env(r["x"]).mean() for r in runs])
    out["trig_len"] = _spearman(lens, means) if len(runs) > 5 else float("nan")
    # shaky fraction / mean env by context bin
    def binned(v, edges):
        rows = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            s = (v >= lo) & (v < hi)
            rows.append([float(sh[s].mean()) if s.sum() > 100 else float("nan"),
                         float(L[s].mean() - med) if s.sum() > 100 else float("nan"), int(s.sum())])
        return rows
    out["by_kappa"] = binned(k, KAPPA_EDGES)
    out["by_end"] = binned(de, (2.0, 5.0, 10.0, 30.0, np.inf))
    out["by_junction"] = binned(jd, (0.0, 2.0, 5.0, 10.0, np.inf))
    # kink location: fraction of kinks within 3 w of another stroke vs base rate
    near = jd < 3.0
    kk = np.concatenate([np.abs(r["x"]) > KINK_K * scale for r in runs])
    out["kink_near_junction"] = [float(near[kk].mean()) if kk.any() else float("nan"), float(near.mean())]
    out["kink_kappa_mean"] = [float(k[kk].mean()) if kk.any() else float("nan"), float(k.mean())]
    if surrogate:
        sr = [{**r, "x": _phase_surrogate(r["x"], rng)} for r in runs]
        sc = _burst_core(sr, scale, med, bimodal)
        out["surr"] = {kk_: v for kk_, v in sc.items() if kk_ not in ("L", "shaky")}
        out["env_lsd_excess"] = float(np.sqrt(max(out["env_lsd"] ** 2 - out["surr"]["env_lsd"] ** 2, 0.0)))
        out["env_lsd_within_excess"] = float(np.sqrt(max(out["env_lsd_within"] ** 2
                                                          - out["surr"]["env_lsd_within"] ** 2, 0.0)))
    return out


# ---------------------------------------------------------------------------
# v2: regime and kink synthesis, and fitting
# ---------------------------------------------------------------------------

def synth_regime(regime: dict, n: int, rng: np.random.Generator, *, closed: bool = False) -> np.ndarray:
    """Multiplicative gain g(s) (n samples at STEP_W, E[g²] = 1).

    lognormal: g = exp(σ·h − σ²), h a unit-variance Gaussian process with a
    Gaussian ACF of scale corr_w — continuous calm↔shaky modulation.
    markov2: a two-state Markov chain (geometric dwells, means dwell_lo_w /
    dwell_hi_w) switching between gain_lo and gain_hi, edges eased over ≈ 1 w."""
    if n <= 0:
        return np.ones(0)
    kind = regime.get("kind", "lognormal")
    if kind == "lognormal":
        sig = float(regime["sigma"])
        if sig <= 0:
            return np.ones(n)
        sd = max(float(regime["corr_w"]) / STEP_W / np.sqrt(2), 0.5)
        pad = 0 if closed else int(4 * sd)
        e = rng.standard_normal(n + 2 * pad)
        h = gaussian_filter1d(e, sd, mode="wrap" if closed else "reflect")[pad:pad + n]
        h = h / max(np.sqrt(1.0 / (2 * np.sqrt(np.pi) * sd)), 1e-12)   # theoretical sd of filtered white noise
        return np.exp(sig * h - sig ** 2)
    if kind == "markov2":
        glo, ghi = float(regime["gain_lo"]), float(regime["gain_hi"])
        p_up = min(STEP_W / float(regime["dwell_lo_w"]), 1.0)
        p_dn = min(STEP_W / float(regime["dwell_hi_w"]), 1.0)
        pi_hi = p_up / (p_up + p_dn)
        state = np.empty(n, bool)
        st = rng.random() < pi_hi
        u = rng.random(n)
        for i in range(n):
            state[i] = st
            st = (u[i] >= p_dn) if st else (u[i] < p_up)
        g2 = np.where(state, ghi, glo) ** 2
        g2 = gaussian_filter1d(g2, 0.5 / STEP_W, mode="wrap" if closed else "nearest")
        return np.sqrt(g2)
    raise ValueError(f"unknown regime kind {kind!r}")


def markov2_normalised(ratio: float, dwell_lo_w: float, dwell_hi_w: float) -> dict:
    """markov2 regime with gain_hi / gain_lo = ratio and E[g²] = 1."""
    pi_hi = dwell_hi_w / (dwell_lo_w + dwell_hi_w)
    glo = 1.0 / np.sqrt((1 - pi_hi) + pi_hi * ratio ** 2)
    return {"kind": "markov2", "gain_lo": float(glo), "gain_hi": float(glo * ratio),
            "dwell_lo_w": float(dwell_lo_w), "dwell_hi_w": float(dwell_hi_w)}


def synth_kinks(kinks: dict, n: int, rng: np.random.Generator, *, closed: bool = False) -> np.ndarray:
    """Sparse kinks: Poisson positions, random sign, log-normal amplitude
    (w), cusp shape exp(−|s − s0|/τ) — a sudden sideways jog that relaxes."""
    rate = float(kinks.get("rate_per_100w", 0.0))
    out = np.zeros(n)
    if rate <= 0 or n <= 0:
        return out
    k = rng.poisson(rate / 100.0 * n * STEP_W)
    if k == 0:
        return out
    pos = rng.uniform(0, n, k)
    amp = float(kinks["amp_w"]) * np.exp(float(kinks.get("amp_log_sd", 0.0)) * rng.standard_normal(k))
    amp = amp * rng.choice([-1.0, 1.0], k)
    tau = float(kinks.get("tau_w", 0.75)) / STEP_W
    i = np.arange(n)
    for p, a in zip(pos, amp):
        d = np.abs(i - p)
        if closed:
            d = np.minimum(d, n - d)
        out += a * np.exp(-d / tau)
    return out


REGIME_TARGETS = ("env_lsd_within", "env_corr_w", "kink_d2_rate", "kurtosis")


def _sim_stats(runs, regime, kinks, rng, keys):
    sim = []
    for r in runs:
        x = _phase_surrogate(r["x"], rng)
        if regime:
            x = x * synth_regime(regime, len(x), rng)
        if kinks:
            x = x + synth_kinks(kinks, len(x), rng)
        sim.append({**r, "x": x})
    allx = np.concatenate([r["x"] for r in sim])
    L0 = np.concatenate([_log_env(r["x"]) for r in sim])
    c = _burst_core(sim, float(np.sqrt(np.mean(allx ** 2))), float(np.median(L0)), bimodal=False)
    return {k: c[k] for k in keys}


def _loss(got, tgt, keys, wts=None):
    wts = wts or {}
    return float(sum(wts.get(k, 1.0) * ((got[k] - tgt[k]) / max(abs(tgt[k]), 1e-6)) ** 2
                     for k in keys if np.isfinite(got[k]) and np.isfinite(tgt[k])))


def fit_regime(res: list[dict], rng_seed: int = 0, *, kind: str = "lognormal", kappa_norm: bool = True,
               min_jdist: float = 0.0, grid: dict | None = None, fit_kinks: bool = True) -> dict:
    """Fit a regime (and kinks) by simulation: every real run is replaced by
    its phase-randomised surrogate (same spectrum, same level) times a
    candidate regime gain (plus candidate kinks), and measured exactly like
    the real runs. The candidate whose burst statistics are closest to the
    real ones wins. Returns {"regime", "kinks", "target", "fit", "loss"}."""
    runs = burst_runs(res, min_jdist=min_jdist)
    if kappa_norm:
        runs = kappa_normalise(runs)
    if len(runs) > 300:
        sel = np.random.default_rng(rng_seed).choice(len(runs), 300, replace=False)
        runs = [runs[i] for i in sorted(sel)]
    allx = np.concatenate([r["x"] for r in runs])
    L0 = np.concatenate([_log_env(r["x"]) for r in runs])
    rms = float(np.sqrt(np.mean(allx ** 2)))
    tgt_core = _burst_core(runs, rms, float(np.median(L0)), bimodal=False)
    if kind == "lognormal":
        keys = ("env_lsd_within", "env_corr_w")
        g = grid or {"sigma": [0.0, 0.2, 0.3, 0.4, 0.5, 0.65, 0.8], "corr_w": [2.0, 4.0, 8.0, 16.0]}
        cands = [{"kind": "lognormal", "sigma": a, "corr_w": b} for a in g["sigma"] for b in g["corr_w"]]
    else:
        keys = ("env_lsd_within", "env_corr_w", "shaky_frac", "dwell_shaky_w", "dwell_calm_w")
        g = grid or {"ratio": [1.5, 2.0, 3.0, 4.0], "dwell_lo_w": [8.0, 16.0, 32.0], "dwell_hi_w": [4.0, 8.0, 16.0]}
        cands = [markov2_normalised(a, b, c) for a in g["ratio"] for b in g["dwell_lo_w"] for c in g["dwell_hi_w"]]
    tgt = {k: tgt_core[k] for k in set(keys) | set(REGIME_TARGETS) | {"shaky_frac", "dwell_shaky_w", "dwell_calm_w", "kink_rate"}}
    best = None
    for c in cands:
        got = _sim_stats(runs, c, None, np.random.default_rng(rng_seed), keys)
        L = _loss(got, tgt, keys)
        if best is None or L < best[0]:
            best = (L, c, got)
    out = {"regime": best[1], "kinks": None, "target": tgt, "fit": best[2], "loss": best[0]}
    if fit_kinks:
        kk = ("kink_d2_rate", "kurtosis", "env_lsd_within")
        base = _sim_stats(runs, best[1], None, np.random.default_rng(rng_seed), kk)
        bestk = (_loss(base, tgt, kk, {"env_lsd_within": 0.5}), None, base)
        for rate in (0.25, 0.5, 1.0, 2.0):
            for amp in (1.5, 2.5, 4.0):
                kn = {"rate_per_100w": rate, "amp_w": amp * rms, "amp_log_sd": 0.4, "tau_w": 0.75}
                got = _sim_stats(runs, best[1], kn, np.random.default_rng(rng_seed), kk)
                L = _loss(got, tgt, kk, {"env_lsd_within": 0.5})
                if L < bestk[0]:
                    bestk = (L, kn, got)
        out["kinks"] = bestk[1]
        out["kinks_fit"] = bestk[2]
        out["kinks_amp_in_rms"] = None if bestk[1] is None else bestk[1]["amp_w"] / rms
        out["rms_fit_set"] = rms
    return out
