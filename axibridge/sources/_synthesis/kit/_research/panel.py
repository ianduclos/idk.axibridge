# FROZEN from research commit 6f96418: tools/gesture/gesture/panel.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""The measurement panel: one dimensionless feature vector per Drawing (stage 2).

`features(drawing)` returns a flat ``dict[str, float]``. Every name carries a
group prefix so ablation can drop whole groups (`GROUPS`, `group_of`):

    k_     curvature distribution (+ curvature-scale-space ratios)
    ext_   curvature extrema (Attneave points): rate, height, width, spacing
    infl_  inflections (κ sign changes with hysteresis)
    turn_  turning: κ / tangent autocorrelation along s, net vs absolute turn
    len_   stroke lengths, count, economy, closure
    end_   stroke endings from the width profile (only when widths exist)
    w_     line width (the cue a pen plotter cannot reproduce)
    cl_    clothoid segment statistics (gesture/clothoid.py, optional)
    rel_   inter-stroke relations: gaps, near-touches, crossings

Units (README "Contract"): κ is reported as κ·ref, lengths as length/ref,
with ref = ``Drawing.ref_length()``. Curvature comes from
``curvature.kappa_s`` only, at σ = sigma_frac·ref (step σ/4). Every
threshold below is stated in ref or σ units, so scaling or rotating a drawing
leaves the vector unchanged (up to resampling error).

Stroke eligibility: κ-based groups (k_, ext_, infl_, turn_, cl_) use strokes
at least ``MIN_LEN_SIGMA``·σ long, and for open strokes only their interior
(``TRIM_SIGMA``·σ trimmed at each end, where the smoothing is biased). len_,
rel_, w_ and end_ use every stroke.

NaN means "genuinely undefined" and is listed per feature in FEATURE_DOCS
(e.g. a height quantile of curvature extrema when there are none). The
discrimination experiment imputes NaN inside its CV folds.

Pure and deterministic: inputs are never mutated, nothing is random.
"""
from __future__ import annotations

import warnings

import numpy as np
from scipy.signal import find_peaks
from scipy.spatial import cKDTree

from .core import Drawing, Stroke
from .curvature import arclength, kappa_s

# ---------------------------------------------------------------------------
# constants (all dimensionless: σ units or ref units or κ·ref units)
# ---------------------------------------------------------------------------

MIN_LEN_SIGMA = 6.0        # strokes shorter than this many σ skip κ groups
TRIM_SIGMA = 2.0           # open-stroke ends trimmed from κ statistics (σ)
CSS_MULTIPLES = (2.0, 4.0)  # curvature scale space: σ multiples compared to σ
EXT_PROMINENCE = 3.0       # min prominence of a |κ|·ref peak to count as extremum
INFL_HYST = 1.5            # κ·ref hysteresis band for counting inflections
TURN_LAGS = (0.02, 0.05, 0.1, 0.2)  # autocorrelation lags, in ref units
END_FRAC = 0.05            # ending window: first/last 5% of a stroke's length
END_MIN_SIGMA = 1.0        # ... but at least this many σ
CLOSE_GAP = 0.02           # endpoints within this·ref count as a closed stroke
REL_TOUCH = 0.005          # endpoint within this·ref of another stroke = touching
REL_NEAR = 0.03            # ... within this·ref = near-touch
REL_END_EPS = 0.01         # a crossing this close (ref) to an endpoint is a T, not an X
KAPPA_EPS = 1e-6           # |κ|·ref below this is numerically zero (straight)

GROUPS = ("k", "ext", "infl", "turn", "len", "end", "w", "cl", "rel")
WIDTH_GROUPS = ("w", "end")          # excluded for "geometry only"
CL_KINDS = ("line", "arc", "clothoid")


def group_of(name: str) -> str:
    return name.split("_", 1)[0]


def _lag_tag(lag: float) -> str:
    return f"{int(round(lag * 100)):02d}"


def _q(v, q) -> float:
    v = np.asarray(v, dtype=np.float64)
    return float(np.quantile(v, q)) if v.size else float("nan")


def _cv(v) -> float:
    v = np.asarray(v, dtype=np.float64)
    if v.size < 2:
        return float("nan")
    m = float(np.mean(v))
    return float(np.std(v) / m) if m > 0 else float("nan")


# ---------------------------------------------------------------------------
# feature documentation (name → one line). Every key features() can emit.
# ---------------------------------------------------------------------------

FEATURE_DOCS: dict[str, str] = {
    # k_
    "k_q10": "10th percentile of |κ|·ref over eligible stroke interiors (σ); NaN if no eligible stroke",
    "k_q50": "median |κ|·ref over interiors",
    "k_q90": "90th percentile |κ|·ref over interiors",
    "k_mean": "mean |κ|·ref over interiors (= mean turning per unit length, rad/ref)",
    "k_cv": "std/mean of |κ| over interiors; NaN if mean is 0 (all straight)",
    "k_css_r2": "mean|κ| at 2σ ÷ mean|κ| at σ (curvature-scale-space decay; 1 = smooth, ≪1 = fine wiggle); NaN if no curvature",
    "k_css_r4": "mean|κ| at 4σ ÷ mean|κ| at σ; NaN as above",
    "k_css_zc2": "inflection rate at 2σ ÷ inflection rate at σ (how many sign changes survive coarsening); NaN if none at σ",
    # ext_
    "ext_rate": "curvature extrema (|κ|·ref peaks with prominence ≥ EXT_PROMINENCE) per unit length (per ref)",
    "ext_h_q50": "median extremum height |κ|·ref; NaN if no extrema",
    "ext_h_q90": "90th percentile extremum height |κ|·ref; NaN if no extrema",
    "ext_w_q50": "median extremum width at half prominence, in σ (sharpness: ~1–2 = corner-like); NaN if no extrema",
    "ext_turn_q50": "median turning angle (rad) accumulated across each extremum's half-prominence width; NaN if no extrema",
    "ext_spacing_cv": "CV of arc-length spacing between consecutive extrema within strokes; NaN if < 2 spacings",
    # infl_
    "infl_rate": "κ sign changes (hysteresis ±INFL_HYST in κ·ref) per unit length (per ref)",
    "infl_stroke_frac": "length-weighted fraction of eligible strokes with ≥ 1 inflection; NaN if no eligible stroke",
    # turn_
    **{f"turn_kcorr_{_lag_tag(l)}": f"uncentred κ autocorrelation at lag {l} ref (1 = same bend persists, <0 = S-wiggle); NaN if no κ energy or no pairs"
       for l in TURN_LAGS},
    **{f"turn_tcorr_{_lag_tag(l)}": f"mean cos(tangent change) over lag {l} ref (heading persistence; 1 = straight); NaN if no pairs"
       for l in TURN_LAGS},
    "turn_abs": "total absolute turning (rad) per unit length (per ref), whole strokes incl. ends; NaN if no eligible stroke",
    "turn_net_ratio": "length-weighted mean over strokes of |∫κ ds| / ∫|κ| ds (1 = turns one way only); NaN if no curvature",
    # len_
    "len_count": "number of strokes",
    "len_q10": "10th percentile stroke length / ref",
    "len_q50": "median stroke length / ref",
    "len_q90": "90th percentile stroke length / ref",
    "len_ink": "total ink length / ref (economy)",
    "len_top_share": "share of total ink in the longest stroke (1 = one-line drawing)",
    "len_closure": "fraction of strokes closed, or open with endpoints within CLOSE_GAP·ref",
    # end_
    "end_thin_q50": "median over open strokes of min(start, end) width ÷ stroke median width (taper; direction-free)",
    "end_thick_q50": "median over open strokes of max(start, end) width ÷ stroke median width (blob; direction-free)",
    "end_asym_q50": "median |start − end| width ÷ stroke median width",
    "end_taper_frac": "fraction of open strokes whose thinner end is < 0.6 × median width",
    "end_blob_frac": "fraction of open strokes whose thicker end is > 1.3 × median width",
    # w_
    "w_med": "length-weighted median line width / ref",
    "w_cv_along": "median over strokes of width std/mean along the stroke",
    "w_cv_between": "CV of per-stroke median widths; NaN if < 2 strokes",
    "w_q90_q10": "pooled width 90th ÷ 10th percentile (length-weighted samples)",
    # cl_
    "cl_segs_per_stroke": "clothoid-fit segments per fitted stroke",
    **{f"cl_rate_{k}": f"{k} segments per unit length (per ref)" for k in CL_KINDS},
    **{f"cl_frac_{k}": f"fraction of fitted length that is {k}" for k in CL_KINDS},
    **{f"cl_len_{k}": f"median {k} segment length / ref; NaN if none" for k in CL_KINDS},
    "cl_kappa_arc": "median arc |κ|·ref; NaN if no arcs",
    "cl_kappa_clothoid": "median clothoid mean|κ|·ref; NaN if no clothoids",
    "cl_slope_clothoid": "median clothoid |dκ/ds|·ref²; NaN if no clothoids",
    "cl_corner_rate": "corners per unit length (per ref) from the clothoid fit",
    "cl_infl_rate": "inflections per unit length (per ref) from the clothoid fit",
    "cl_fit_err": "median rms κ error of the fit × ref (how well clothoids explain the line)",
    **{f"cl_T_{a}_{b}": f"P(next segment is {b} | {a}) over consecutive segments; 0 if no {a} transitions"
       for a in CL_KINDS for b in CL_KINDS},
    # rel_
    "rel_gap_log_q50": "median log10(endpoint→nearest other stroke distance / ref) over open-stroke endpoints; NaN if < 2 strokes",
    "rel_touch_rate": "fraction of endpoints within REL_TOUCH·ref of another stroke (T-junctions, joins); NaN if < 2 strokes",
    "rel_near_rate": "fraction of endpoints within REL_NEAR·ref of another stroke (near-touches + touches); NaN if < 2 strokes",
    "rel_cross_per_stroke": "proper X crossings between different strokes ÷ number of strokes",
    "rel_cross_per_len": "proper X crossings per unit ink length (per ref)",
    "rel_cross_angle": "mean acute crossing angle (rad, 0..π/2); NaN if no crossings",
    "rel_selfcross_frac": "fraction of open strokes that cross themselves",
}


# ---------------------------------------------------------------------------
# per-stroke curvature
# ---------------------------------------------------------------------------

class _Kappa:
    """κ(s) of one stroke at one σ, with its interior mask."""
    __slots__ = ("k", "step", "interior", "sm", "closed")

    def __init__(self, st: Stroke, sigma: float):
        step = sigma / 4.0
        _, k, sm = kappa_s(st.points, sigma, step=step, closed=st.closed)
        self.k, self.step, self.sm, self.closed = k, step, sm, st.closed
        n = len(k)
        if st.closed:
            self.interior = np.ones(n, dtype=bool)
        else:
            t = int(np.ceil(TRIM_SIGMA * sigma / step))
            m = np.zeros(n, dtype=bool)
            if n > 2 * t:
                m[t:n - t] = True
            self.interior = m


def _hyst_changes(k: np.ndarray, h: float, cyclic: bool = False) -> int:
    """Sign changes of k with hysteresis band ±h (a flip needs |k| > h on the
    new side)."""
    state = 0
    first = 0
    n = 0
    for v in k[np.abs(k) > h]:
        sgn = 1 if v > 0 else -1
        if state == 0:
            state = first = sgn
        elif sgn != state:
            n += 1
            state = sgn
    if cyclic and n and state != first:
        n += 1
    return n


def _k_group(kps: list[_Kappa], R: float) -> dict:
    out = {k: float("nan") for k in ("k_q10", "k_q50", "k_q90", "k_mean", "k_cv")}
    ak = [np.abs(kp.k[kp.interior]) * R for kp in kps]
    ak = np.concatenate(ak) if ak else np.zeros(0)
    if ak.size:
        out.update(k_q10=_q(ak, .1), k_q50=_q(ak, .5), k_q90=_q(ak, .9), k_mean=float(ak.mean()))
        out["k_cv"] = float(ak.std() / ak.mean()) if ak.mean() > KAPPA_EPS else float("nan")
    return out


def _ext_group(kps: list[_Kappa], R: float, sigma: float) -> dict:
    heights, widths, turns, spacings = [], [], [], []
    total = 0.0
    for kp in kps:
        k = kp.k[kp.interior]
        if len(k) < 3:
            continue
        total += len(k) * kp.step
        ak = np.abs(k) * R
        if kp.closed:
            # unroll cyclically so peaks at the seam are found once
            n = len(ak)
            ext = np.concatenate([ak, ak, ak])
            pk, pr = find_peaks(ext, prominence=EXT_PROMINENCE, width=0, rel_height=0.5)
            sel = (pk >= n) & (pk < 2 * n)
            pk = pk[sel]
            pr = {key: v[sel] for key, v in pr.items()}
            base = ext
        else:
            pk, pr = find_peaks(ak, prominence=EXT_PROMINENCE, width=0, rel_height=0.5)
            base = ak
        if not len(pk):
            continue
        heights.extend(base[pk].tolist())
        widths.extend((pr["widths"] * kp.step / sigma).tolist())
        for lo, hi in zip(pr["left_ips"], pr["right_ips"]):
            a, b = int(np.floor(lo)), int(np.ceil(hi)) + 1
            turns.append(float(np.sum(base[a:b]) / R * kp.step))
        if len(pk) >= 2:
            sp = np.diff(pk) * kp.step
            spacings.extend(sp.tolist())
    out = {
        "ext_rate": len(heights) / (total / R) if total > 0 else float("nan"),
        "ext_h_q50": _q(heights, .5), "ext_h_q90": _q(heights, .9),
        "ext_w_q50": _q(widths, .5), "ext_turn_q50": _q(turns, .5),
        "ext_spacing_cv": _cv(spacings),
    }
    return out


def _infl_group(kps: list[_Kappa], R: float) -> dict:
    n_tot, total, with_infl, wl = 0, 0.0, 0.0, 0.0
    for kp in kps:
        k = kp.k[kp.interior] * R
        if not len(k):
            continue
        L = len(k) * kp.step
        c = _hyst_changes(k, INFL_HYST, cyclic=kp.closed)
        n_tot += c
        total += L
        wl += L
        with_infl += L if c else 0.0
    return {
        "infl_rate": n_tot / (total / R) if total > 0 else float("nan"),
        "infl_stroke_frac": with_infl / wl if wl > 0 else float("nan"),
    }


def _css_group(strokes: list[Stroke], kps0: list[_Kappa], R: float, sigma: float) -> dict:
    base = np.concatenate([np.abs(kp.k[kp.interior]) for kp in kps0]) if kps0 else np.zeros(0)
    m0 = float(base.mean()) if base.size else 0.0
    m0 = m0 if m0 * R > KAPPA_EPS else 0.0
    z0 = sum(_hyst_changes(kp.k[kp.interior] * R, INFL_HYST, kp.closed) for kp in kps0)
    L0 = sum(kp.interior.sum() * kp.step for kp in kps0)
    out = {}
    for mult in CSS_MULTIPLES:
        sg = sigma * mult
        kps = [_Kappa(st, sg) for st in strokes if st.length() >= MIN_LEN_SIGMA * sg]
        ak = np.concatenate([np.abs(kp.k[kp.interior]) for kp in kps]) if kps else np.zeros(0)
        tag = f"{int(mult)}"
        out[f"k_css_r{tag}"] = float(ak.mean() / m0) if (ak.size and m0 > 0) else float("nan")
        if mult == CSS_MULTIPLES[0]:
            z = sum(_hyst_changes(kp.k[kp.interior] * R, INFL_HYST, kp.closed) for kp in kps)
            L = sum(kp.interior.sum() * kp.step for kp in kps)
            r0 = z0 / L0 if L0 > 0 else 0.0
            out[f"k_css_zc{tag}"] = float((z / L) / r0) if (r0 > 0 and L > 0) else float("nan")
    return out


def _turn_group(strokes: list[Stroke], kps: list[_Kappa], R: float) -> dict:
    out = {}
    for lag in TURN_LAGS:
        num = den_a = den_b = 0.0
        cos_sum, cos_n = 0.0, 0
        for kp in kps:
            k = kp.k[kp.interior]
            m = int(round(lag * R / kp.step))
            if m < 1:
                m = 1
            n = len(k)
            if kp.closed:
                if n < 2:
                    continue
                a, b = k, np.roll(k, -(m % n))
            else:
                if n <= m:
                    continue
                a, b = k[:-m], k[m:]
            num += float(np.dot(a, b))
            den_a += float(np.dot(a, a))
            den_b += float(np.dot(b, b))
            # heading change over the lag = ∫κ ds across it
            if kp.closed:
                c = np.concatenate([[0.0], np.cumsum(np.concatenate([k, k]))]) * kp.step
                dth = c[m % n:m % n + n] - c[:n]
            else:
                c = np.concatenate([[0.0], np.cumsum(k)]) * kp.step
                dth = c[m:n] - c[: n - m]
            cos_sum += float(np.sum(np.cos(dth)))
            cos_n += len(dth)
        tag = _lag_tag(lag)
        den = np.sqrt(den_a * den_b)
        energy = np.sqrt(den / max(cos_n, 1)) * R          # ~ rms κ·ref
        out[f"turn_kcorr_{tag}"] = num / den if energy > KAPPA_EPS else float("nan")
        out[f"turn_tcorr_{tag}"] = cos_sum / cos_n if cos_n else float("nan")
    tot_abs = tot_len = 0.0
    net_w = net_l = 0.0
    for kp in kps:
        L = len(kp.k) * kp.step
        a = float(np.sum(np.abs(kp.k)) * kp.step)
        tot_abs += a
        tot_len += L
        if a > KAPPA_EPS * L / R:
            net_w += abs(float(np.sum(kp.k) * kp.step)) / a * L
            net_l += L
    out["turn_abs"] = tot_abs / (tot_len / R) if tot_len > 0 else float("nan")
    out["turn_net_ratio"] = net_w / net_l if net_l > 0 else float("nan")
    return out


# ---------------------------------------------------------------------------
# lengths, endings, width
# ---------------------------------------------------------------------------

def _len_group(strokes: list[Stroke], R: float) -> dict:
    L = np.array([st.length() for st in strokes]) / R
    tot = float(L.sum())
    closed = 0
    for st in strokes:
        if st.closed:
            closed += 1
        elif len(st) > 2 and np.hypot(*(st.points[-1] - st.points[0])) <= CLOSE_GAP * R \
                and st.length() > 4 * CLOSE_GAP * R:
            closed += 1
    return {
        "len_count": float(len(strokes)),
        "len_q10": _q(L, .1), "len_q50": _q(L, .5), "len_q90": _q(L, .9),
        "len_ink": tot,
        "len_top_share": float(L.max() / tot) if tot > 0 else float("nan"),
        "len_closure": closed / len(strokes) if strokes else float("nan"),
    }


def _stroke_s(st: Stroke) -> np.ndarray:
    return arclength(st.points)


def _wmedian(values: np.ndarray, weights: np.ndarray) -> float:
    o = np.argsort(values)
    v, w = values[o], weights[o]
    c = np.cumsum(w)
    if c[-1] <= 0:
        return float(np.median(values))
    return float(v[np.searchsorted(c, 0.5 * c[-1])])


def _sample_weights(s: np.ndarray, closed_len: float | None = None) -> np.ndarray:
    """Arc-length weight of each vertex (half the adjacent segments)."""
    d = np.diff(s)
    w = np.zeros(len(s))
    w[:-1] += 0.5 * d
    w[1:] += 0.5 * d
    if closed_len is not None and len(s):
        gap = closed_len - s[-1]
        w[0] += 0.5 * gap
        w[-1] += 0.5 * gap
    return w


def _w_group(strokes: list[Stroke], R: float) -> dict:
    vals, wts, meds, cvs = [], [], [], []
    for st in strokes:
        s = _stroke_s(st)
        sw = _sample_weights(s, st.length() if st.closed else None)
        if sw.sum() <= 0:
            sw = np.ones(len(s))
        vals.append(st.width)
        wts.append(sw)
        meds.append(_wmedian(st.width, sw))
        m = float(np.average(st.width, weights=sw))
        if m > 0:
            cvs.append(float(np.sqrt(np.average((st.width - m) ** 2, weights=sw)) / m))
    v, w = np.concatenate(vals), np.concatenate(wts)
    o = np.argsort(v)
    c = np.cumsum(w[o]) / w.sum()
    q10 = v[o][np.searchsorted(c, 0.1)]
    q90 = v[o][min(np.searchsorted(c, 0.9), len(v) - 1)]
    return {
        "w_med": _wmedian(v, w) / R,
        "w_cv_along": _q(cvs, .5),
        "w_cv_between": _cv(meds),
        "w_q90_q10": float(q90 / q10) if q10 > 0 else float("nan"),
    }


def _end_group(strokes: list[Stroke], sigma: float) -> dict:
    thin, thick, asym = [], [], []
    for st in strokes:
        if st.closed or len(st) < 2:
            continue
        s = _stroke_s(st)
        L = s[-1]
        if L <= 0:
            continue
        win = max(END_FRAC * L, END_MIN_SIGMA * sigma)
        if 2 * win >= L:
            continue
        med = _wmedian(st.width, np.maximum(_sample_weights(s), 1e-12))
        if med <= 0:
            continue
        # mean width over the window, by arc length (resample densely)
        t0 = np.linspace(0, win, 16)
        a = float(np.mean(np.interp(t0, s, st.width)))
        b = float(np.mean(np.interp(L - t0, s, st.width)))
        thin.append(min(a, b) / med)
        thick.append(max(a, b) / med)
        asym.append(abs(a - b) / med)
    thin_a, thick_a = np.array(thin), np.array(thick)
    return {
        "end_thin_q50": _q(thin, .5), "end_thick_q50": _q(thick, .5),
        "end_asym_q50": _q(asym, .5),
        "end_taper_frac": float(np.mean(thin_a < 0.6)) if thin else float("nan"),
        "end_blob_frac": float(np.mean(thick_a > 1.3)) if thick else float("nan"),
    }


# ---------------------------------------------------------------------------
# clothoid group (optional dependency on a module still in flux)
# ---------------------------------------------------------------------------

def _cl_group(strokes: list[Stroke], R: float, sigma: float) -> tuple[dict, str]:
    try:
        from . import clothoid  # lazy: module may be absent or mid-rewrite
    except Exception as e:      # noqa: BLE001
        return {}, f"import failed: {type(e).__name__}: {e}"
    try:
        fits = [clothoid.fit_stroke(st.points, sigma=sigma, closed=st.closed)
                for st in strokes if st.length() >= MIN_LEN_SIGMA * sigma]
        if not fits:
            return {}, "no eligible strokes"
        st_ = clothoid.segment_stats(fits, R)
    except Exception as e:      # noqa: BLE001
        return {}, f"fit/stats failed: {type(e).__name__}: {e}"
    try:
        out: dict[str, float] = {}
        nseg = sum(len(f.segments) for f in fits)
        out["cl_segs_per_stroke"] = nseg / len(fits)
        rate = st_.get("rate", {})
        lens = st_.get("length", {})
        tot = sum(sum(lens.get(k, [])) for k in CL_KINDS)
        for k in CL_KINDS:
            out[f"cl_rate_{k}"] = float(rate.get(k, 0.0))
            out[f"cl_frac_{k}"] = float(sum(lens.get(k, [])) / tot) if tot > 0 else float("nan")
            out[f"cl_len_{k}"] = _q(lens.get(k, []), .5)
        kap = st_.get("kappa", {})
        out["cl_kappa_arc"] = _q(kap.get("arc", []), .5)
        out["cl_kappa_clothoid"] = _q(kap.get("clothoid", []), .5)
        out["cl_slope_clothoid"] = _q(st_.get("slope", {}).get("clothoid", []), .5)
        out["cl_corner_rate"] = float(st_.get("corner_rate", float("nan")))
        out["cl_infl_rate"] = float(st_.get("inflection_rate", float("nan")))
        out["cl_fit_err"] = _q([f.rms_kappa_error * R for f in fits], .5)
        kinds = list(st_.get("kinds", CL_KINDS))
        mat = np.asarray(st_.get("transition_matrix"), dtype=np.float64)
        for i, a in enumerate(CL_KINDS):
            for j, b in enumerate(CL_KINDS):
                out[f"cl_T_{a}_{b}"] = float(mat[kinds.index(a), kinds.index(b)])
    except Exception as e:      # noqa: BLE001
        return {}, f"segment_stats format changed: {type(e).__name__}: {e}"
    return out, "ok"


# ---------------------------------------------------------------------------
# inter-stroke relations
# ---------------------------------------------------------------------------

def _rel_group(strokes: list[Stroke], R: float) -> dict:
    import shapely
    from shapely.geometry import LineString, Point

    n = len(strokes)
    step = 0.0025 * R
    polys = []
    for st in strokes:
        p = st.points
        if st.closed and len(p) > 1:
            p = np.vstack([p, p[:1]])
        polys.append(p)
    out = {k: float("nan") for k in ("rel_gap_log_q50", "rel_touch_rate", "rel_near_rate")}
    if n >= 2:
        # dense samples of every stroke, labelled by stroke
        samp, lab = [], []
        for i, p in enumerate(polys):
            s = arclength(p)
            if s[-1] <= 0:
                q = p[:1]
            else:
                t = np.linspace(0, s[-1], max(int(np.ceil(s[-1] / step)), 1) + 1)
                q = np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])
            samp.append(q)
            lab.append(np.full(len(q), i))
        samp, lab = np.vstack(samp), np.concatenate(lab)
        tree = cKDTree(samp)
        dists = []
        for i, st in enumerate(strokes):
            if st.closed:
                continue
            for e in (st.points[0], st.points[-1]):
                k = min(len(samp), 64)
                d, j = tree.query(e, k=k)
                d, j = np.atleast_1d(d), np.atleast_1d(j)
                other = lab[j] != i
                if other.any():
                    dists.append(float(d[other][0]))
                else:
                    mask = lab != i
                    dists.append(float(np.min(np.linalg.norm(samp[mask] - e, axis=1))))
        if dists:
            d = np.array(dists) / R
            out["rel_gap_log_q50"] = _q(np.log10(np.maximum(d, 1e-6)), .5)
            out["rel_touch_rate"] = float(np.mean(d <= REL_TOUCH))
            out["rel_near_rate"] = float(np.mean(d <= REL_NEAR))
    # crossings
    lines = [LineString(p) if len(p) >= 2 else None for p in polys]
    eps = REL_END_EPS * R
    n_cross, angles = 0, []
    valid = [i for i, l in enumerate(lines) if l is not None and l.length > 0]
    if len(valid) >= 2:
        tree = shapely.STRtree([lines[i] for i in valid])
        for a_idx, i in enumerate(valid):
            cand = tree.query(lines[i], predicate="intersects")
            for b_idx in cand:
                if b_idx <= a_idx:
                    continue
                j = valid[b_idx]
                inter = lines[i].intersection(lines[j])
                pts = [g for g in getattr(inter, "geoms", [inter]) if g.geom_type == "Point"]
                for pt in pts:
                    if any(not strokes[m].closed and (
                            Point(polys[m][0]).distance(pt) < eps or Point(polys[m][-1]).distance(pt) < eps)
                           for m in (i, j)):
                        continue
                    n_cross += 1
                    tang = []
                    for m in (i, j):
                        L = lines[m]
                        u = L.project(pt)
                        d = min(eps, 0.5 * L.length)
                        p0 = L.interpolate(max(u - d, 0.0))
                        p1 = L.interpolate(min(u + d, L.length))
                        tang.append(np.array([p1.x - p0.x, p1.y - p0.y]))
                    na, nb = np.linalg.norm(tang[0]), np.linalg.norm(tang[1])
                    if na > 0 and nb > 0:
                        c = abs(float(np.dot(tang[0], tang[1]) / (na * nb)))
                        angles.append(float(np.arccos(min(c, 1.0))))
    ink = sum(st.length() for st in strokes) / R
    out["rel_cross_per_stroke"] = n_cross / n if n else float("nan")
    out["rel_cross_per_len"] = n_cross / ink if ink > 0 else float("nan")
    out["rel_cross_angle"] = float(np.mean(angles)) if angles else float("nan")
    opens = [lines[i] for i in valid if not strokes[i].closed]
    out["rel_selfcross_frac"] = float(np.mean([not l.is_simple for l in opens])) if opens else float("nan")
    return out


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------

def features_with_info(drawing: Drawing, *, sigma_frac: float = 0.01,
                       width_available: bool = True,
                       clothoid: bool = True,
                       sigma_min_w: float = 0.0) -> tuple[dict[str, float], dict]:
    """Like `features`, plus an info dict: {"sigma", "ref", "n_eligible",
    "groups": [...present...], "clothoid": "ok" | reason it was skipped,
    "width": bool}."""
    strokes = [st for st in drawing.strokes if len(st) >= 2 and st.length() > 0]
    R = drawing.ref_length()
    sigma = sigma_frac * R
    if sigma_min_w > 0:
        # Floor σ at a multiple of the drawing's median line width so that a
        # collection scanned at fewer px per line is not measured at a finer
        # scale relative to its own line (σ/w was a per-artist confound).
        ws = [float(np.median(st.width)) for st in strokes if st.width is not None and len(st.width)]
        if ws:
            sigma = max(sigma, sigma_min_w * float(np.median(ws)))
    info: dict = {"sigma": sigma, "ref": R, "n_strokes": len(strokes)}
    feats: dict[str, float] = {}
    if not strokes:
        info.update(n_eligible=0, groups=[], clothoid="no strokes", width=False)
        return feats, info

    elig = [st for st in strokes if st.length() >= MIN_LEN_SIGMA * sigma]
    kps = [_Kappa(st, sigma) for st in elig]
    info["n_eligible"] = len(elig)

    feats.update(_k_group(kps, R))
    feats.update(_css_group(elig, kps, R, sigma))
    feats.update(_ext_group(kps, R, sigma))
    feats.update(_infl_group(kps, R))
    feats.update(_turn_group(elig, kps, R))
    feats.update(_len_group(strokes, R))

    has_w = width_available and all(st.width is not None for st in strokes)
    info["width"] = has_w
    if has_w:
        feats.update(_w_group(strokes, R))
        feats.update(_end_group(strokes, sigma))

    if clothoid:
        cl, why = _cl_group(strokes, R, sigma)
        feats.update(cl)
        info["clothoid"] = why
        if why != "ok":
            warnings.warn(f"panel: clothoid group skipped ({why})", RuntimeWarning, stacklevel=2)
    else:
        info["clothoid"] = "disabled"

    feats.update(_rel_group(strokes, R))
    feats = {k: float(v) for k, v in sorted(feats.items())}
    info["groups"] = sorted({group_of(k) for k in feats})
    return feats, info


def features(drawing: Drawing, *, sigma_frac: float = 0.01,
             width_available: bool = True, sigma_min_w: float = 0.0) -> dict[str, float]:
    """The panel: dimensionless, named features of one drawing (see module
    docstring and FEATURE_DOCS). w_ and end_ are present only when every
    stroke carries a width and `width_available` is True; cl_ is present only
    when gesture/clothoid.py imports and fits (a RuntimeWarning says why not)."""
    return features_with_info(drawing, sigma_frac=sigma_frac, width_available=width_available,
                              sigma_min_w=sigma_min_w)[0]
