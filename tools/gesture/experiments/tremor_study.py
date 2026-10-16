"""Tremor layer study (results/tremor-2026-10-16.md).

Stages (each caches into .local/gesture/out/tremor/):

  floor   per scan: measure paper noise / ink contrast, render the drawing's
          own long strokes smoothed at 2 w (known-smooth ground truth) at the
          scan's working resolution, widths and matched noise, re-extract with
          extract_hybrid, and keep the residuals of real and re-extracted
          strokes. Matisse lithographs also get a "grain" render (ragged
          crayon edges) as a bracket for the medium check.
  stats   per-artist / per-medium tables: real vs floor
  model   fit TremorModel per artist (floor-subtracted) → models/*.json
  eval    fine-scale + standard-panel evaluation: real vs v4 vs v4+tremor
  pairs   blinded judge pairs (three conditions), key → /tmp
  sheets  visual sheets

  .local/gesture/.venv/bin/python tools/gesture/experiments/tremor_study.py floor stats model eval pairs sheets
"""
from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from gesture import synth  # noqa: E402
from gesture import grammar_v4_frozen as gm  # noqa: E402
from gesture import tremor as tr  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

REPO = HERE.parents[2]
EXTRACT = REPO / ".local/gesture/out/extract_hybrid"
GRAMMARS = REPO / ".local/gesture/out/grammar_v4_frozen"
OUT = REPO / ".local/gesture/out/tremor"
MEDIA = REPO / "docs/research/gesture-corpus/media.csv"
ARTISTS = ("matisse", "hokusai", "ingres")
WORKERS = 3


def media() -> dict:
    return {(r["artist"], r["stem"]): r["medium"] for r in csv.DictReader(open(MEDIA))}


# ---------------------------------------------------------------------------
# floor
# ---------------------------------------------------------------------------

def _hp_noise(gray: np.ndarray, centre_px: np.ndarray, w: float) -> tuple[float, float, float]:
    """(high-pass paper noise σ, paper level, ink level) — paper = pixels
    farther than 4 w from any centreline point; ink = gray at centreline."""
    from scipy.ndimage import distance_transform_edt, gaussian_filter
    H, W = gray.shape
    m = np.ones((H, W), bool)
    ij = np.round(centre_px).astype(int)
    ok = (ij[:, 0] >= 0) & (ij[:, 0] < W) & (ij[:, 1] >= 0) & (ij[:, 1] < H)
    m[ij[ok, 1], ij[ok, 0]] = False
    far = distance_transform_edt(m) > 4 * w
    # stay inside the drawn area (plate / sheet margins can be blank card)
    lo, hi = centre_px[ok].min(0).astype(int), centre_px[ok].max(0).astype(int)
    box = np.zeros_like(far)
    box[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1] = True
    far &= box
    hp = gray - gaussian_filter(gray, 2.0)
    x = hp[far]
    sig = float(1.4826 * np.median(np.abs(x - np.median(x)))) if x.size > 100 else float("nan")
    paper = float(np.median(gray[far])) if x.size > 100 else float(np.median(gray))
    ink = float(np.median(gray[ij[ok, 1], ij[ok, 0]]))
    return sig, paper, ink


def _grain(img_clean: np.ndarray, rng, w: float, amp: float = 0.35) -> np.ndarray:
    """Ragged crayon edges: stochastic threshold on coverage, grain σ ≈ 0.15 w."""
    cov = 1.0 - img_clean.astype(np.float32) / 255.0
    g = synth._norm_field(rng, cov.shape, max(0.15 * w, 0.5))
    t = np.clip(0.5 + amp * g, 0.05, 0.95)
    return (cov > t).astype(np.float32) * np.clip(cov * 1.6, 0, 1)


def _render_noisy(d: Drawing, pn: float, seed: int, w: float, grain: bool) -> np.ndarray:
    from scipy.ndimage import gaussian_filter
    rng = np.random.default_rng(seed)
    if not grain:
        return synth.render(d, paper_noise=pn, blur_sigma=0.6, seed=seed).astype(np.float64) / 255.0
    clean = synth.render(d, paper_noise=0.0, blur_sigma=0.0, seed=seed)
    cov = gaussian_filter(_grain(clean, rng, w), 0.6)
    tex = 0.6 * synth._norm_field(rng, cov.shape, 0.0) + 0.8 * synth._norm_field(rng, cov.shape, 3.0)
    paper = np.clip(1.0 - pn * (1.0 + 0.5 * tex), 0, 1)
    return np.clip(paper * (1 - np.clip(cov, 0, 1)), 0, 1).astype(np.float64)


PN_FACTOR = None   # filled by _calibrate: noise_rel = PN_FACTOR · paper_noise


def _calibrate() -> float:
    rng = np.random.default_rng(0)
    d = synth.scene_matisse_like(rng, 600, n_strokes=4, line_width=4.0)
    img = _render_noisy(d, 0.1, 0, 4.0, False)
    pts = np.vstack([s.points for s in d.strokes])
    sig, paper, ink = _hp_noise(img, pts, 4.0)
    return sig / max(paper - ink, 1e-9) / 0.1


def floor_one(args) -> dict:
    """One scan → real and floor residuals (pickled by the caller)."""
    path, artist, med, pn_factor, grain = args
    from gesture import extract_hybrid
    from gesture.extract import load_image
    t0 = time.perf_counter()
    d = Drawing.load(path)
    ld = gm.long_drawing(d)
    run = d.meta.get("run", {})
    gray, scale = load_image(REPO / d.source, invert=bool(run.get("invert")), max_side=run.get("max_side", 2500))
    H, W = gray.shape
    w_orig = gm.drawing_width(ld)
    w = w_orig * scale
    # real residuals (original frame)
    real = tr.drawing_residuals(ld)
    # noise of the scan
    cps = np.vstack([(s.points + 0.5) * scale - 0.5 for s in d.strokes])
    sig, paper, ink = _hp_noise(gray, cps, w)
    contrast = max(paper - ink, 1e-3)
    noise_rel = sig / contrast
    pn = float(np.clip(noise_rel / pn_factor, 0.0, 0.6))
    # ground truth: long strokes at working scale, smoothed at 4 w (twicing: no band-2w leakage), widths smoothed
    gt = []
    for s in ld.strokes:
        q = (s.points + 0.5) * scale - 0.5
        ws = s.width * scale if s.width is not None else np.full(len(q), w)
        r = tr.lateral_residual(q, float(np.median(ws)), closed=s.closed, lo_w=0.0, hi_w=4.0)
        C = r["C"]
        if len(C) < 4:
            continue
        frac = np.linspace(0, 1, len(C))
        wv = np.interp(frac, np.linspace(0, 1, len(ws)), ws)
        from scipy.ndimage import gaussian_filter1d
        wv = gaussian_filter1d(wv, 8.0 / tr.STEP_W, mode="nearest")
        gt.append(Stroke(C, width=wv, closed=s.closed))
    gtd = Drawing(gt, source="floor", size=(W, H), meta={"line_width_px": w})
    out = {"path": str(path), "artist": artist, "medium": med, "scale": scale, "w_work": w,
           "noise_rel": noise_rel, "paper_noise": pn, "contrast": contrast, "real": real}
    for tag, gr in (("floor", False),) + ((("grain", True),) if grain else ()):
        img = _render_noisy(gtd, pn, 1, w, gr)
        ex = extract_hybrid.extract(img, line_width_hint=w)
        exl = gm.long_drawing(ex)
        out[tag] = tr.drawing_residuals(exl)
        out[f"{tag}_n_strokes"] = len(exl.strokes)
    # truth check: GT strokes have zero residual by construction (twice-smoothed)
    out["gt"] = tr.drawing_residuals(gtd)
    out["secs"] = round(time.perf_counter() - t0, 1)
    return out


def _slim(res: list[dict]) -> list[dict]:
    return [{k: v for k, v in d.items() if k not in ("P", "C", "n")} for d in res]


def stage_floor(a):
    global PN_FACTOR
    PN_FACTOR = _calibrate()
    print(f"paper_noise calibration: noise_rel = {PN_FACTOR:.4f} × paper_noise")
    md = media()
    jobs = []
    for art in ARTISTS:
        files = sorted((EXTRACT / art).glob("*.json"))
        if art != "matisse":
            files = files[:a.per_artist]
        for f in files:
            m = md.get((art, f.stem), "?")
            if art == "matisse" and m not in ("etching", "lithograph"):
                continue
            jobs.append((f, art, m, PN_FACTOR, art == "matisse" and m == "lithograph"))
    (OUT / "floor").mkdir(parents=True, exist_ok=True)
    todo = [j for j in jobs if not (OUT / "floor" / f"{j[1]}_{j[0].stem}.pkl").exists()]
    print(len(jobs), "scans,", len(todo), "to do")
    with ProcessPoolExecutor(WORKERS) as ex:
        for r in ex.map(floor_one, todo):
            for k in ("real", "floor", "grain", "gt"):
                if k in r:
                    r[k] = _slim(r[k])
            name = f"{r['artist']}_{Path(r['path']).stem}.pkl"
            (OUT / "floor" / name).write_bytes(pickle.dumps(r))
            print(f"  {name}: w={r['w_work']:.2f}px noise_rel={r['noise_rel']:.3f} pn={r['paper_noise']:.3f} "
                  f"real={len(r['real'])} floor={len(r['floor'])} {r['secs']}s", flush=True)


def load_floor() -> list[dict]:
    return [pickle.loads(p.read_bytes()) for p in sorted((OUT / "floor").glob("*.pkl"))]


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

KEYS = ("rms", "rms_robust", "q90_abs", "corr_len_w", "rms_lambda_1_2w", "rms_lambda_2_4w",
        "rms_lambda_4_8w", "rms_lambda_8_16w")


def _row(st: dict) -> dict:
    return {k: st.get(k) for k in KEYS} | {"rms_by_kappa": st.get("rms_by_kappa"),
                                           "rms_by_end": st.get("rms_by_end"),
                                           "stroke_rms_by_len": st.get("stroke_rms_by_len"),
                                           "n": st.get("n_strokes"), "kurtosis": st.get("kurtosis"),
                                           "len_rms_spearman": st.get("len_rms_spearman"),
                                           "stroke_log_rms_sd": st.get("stroke_log_rms_sd")}


def _excess(real: float, floor: float) -> float:
    return float(np.sqrt(max(real ** 2 - floor ** 2, 0.0)))


def stage_stats(a):
    F = load_floor()
    groups = {}
    for r in F:
        for key in (r["artist"], f"{r['artist']}:{r['medium']}"):
            g = groups.setdefault(key, {"real": [], "floor": [], "grain": [], "noise": [], "w": [], "gt": []})
            g["real"] += r["real"]
            g["floor"] += r["floor"]
            g["grain"] += r.get("grain", [])
            g["gt"] += r.get("gt", [])
            g["noise"].append(r["noise_rel"])
            g["w"].append(r["w_work"])
    table = {}
    for key, g in groups.items():
        rs, fs = tr.residual_stats(g["real"]), tr.residual_stats(g["floor"])
        gs = tr.residual_stats(g["grain"]) if g["grain"] else None
        ts = tr.residual_stats(g["gt"]) if g["gt"] else None
        table[key] = {"n_scans": len(g["noise"]), "noise_rel_med": float(np.median(g["noise"])),
                      "w_work_med": float(np.median(g["w"])), "real": _row(rs), "floor": _row(fs),
                      "grain": _row(gs) if gs else None, "gt": _row(ts) if ts else None,
                      "excess_rms": _excess(rs["rms"], fs["rms"]),
                      "ratio_rms": rs["rms"] / max(fs["rms"], 1e-9),
                      "psd_real": rs["psd"], "psd_floor": fs["psd"], "freqs": rs["freqs"]}
    # per-scan: real rms vs floor rms
    per = [{"scan": Path(r["path"]).stem, "artist": r["artist"], "medium": r["medium"],
            "noise_rel": r["noise_rel"], "w_work": r["w_work"],
            "real": tr.residual_stats(r["real"]).get("rms"), "floor": tr.residual_stats(r["floor"]).get("rms")}
           for r in F]
    (OUT / "stats.json").write_text(json.dumps({"groups": table, "per_scan": per}, indent=1, default=float))
    f3 = lambda x: "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.3f}"
    print("| group | scans | w px (work) | noise/contrast | real rms | floor rms | ratio | excess rms | real corr len | floor corr len | real λ4–8 | floor λ4–8 | real λ8–16 | floor λ8–16 |")
    for key in sorted(table):
        t = table[key]
        print(f"| {key} | {t['n_scans']} | {t['w_work_med']:.2f} | {t['noise_rel_med']:.3f} | {f3(t['real']['rms'])} | "
              f"{f3(t['floor']['rms'])} | {t['ratio_rms']:.2f} | {f3(t['excess_rms'])} | {f3(t['real']['corr_len_w'])} | "
              f"{f3(t['floor']['corr_len_w'])} | {f3(t['real']['rms_lambda_4_8w'])} | {f3(t['floor']['rms_lambda_4_8w'])} | "
              f"{f3(t['real']['rms_lambda_8_16w'])} | {f3(t['floor']['rms_lambda_8_16w'])} |")
    for key in sorted(table):
        t = table[key]
        print(key, "κ bins real", [f3(x) for x in t["real"]["rms_by_kappa"]], "floor", [f3(x) for x in t["floor"]["rms_by_kappa"]],
              "| end real", [f3(x) for x in t["real"]["rms_by_end"]], "floor", [f3(x) for x in t["floor"]["rms_by_end"]],
              "| len", [f3(x) for x in t["real"]["stroke_rms_by_len"] or []], "ρ", f3(t["real"]["len_rms_spearman"]),
              "| kurt", f3(t["real"]["kurtosis"]), f3(t["floor"]["kurtosis"]),
              "| grain rms", f3(t["grain"]["rms"]) if t["grain"] else "—", "| gt rms", f3(t["gt"]["rms"]) if t["gt"] else "—")


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

def stage_model(a):
    F = load_floor()
    (OUT / "models").mkdir(parents=True, exist_ok=True)
    groups = {}
    for r in F:
        for key in (r["artist"],) + ((f"{r['artist']}_{r['medium']}",) if r["artist"] == "matisse" else ()):
            g = groups.setdefault(key, {"real": [], "floor": []})
            g["real"] += r["real"]
            g["floor"] += r["floor"]
    rep = {}
    paths = {}
    for r in F:
        for key in (r["artist"],) + ((f"{r['artist']}_{r['medium']}",) if r["artist"] == "matisse" else ()):
            paths.setdefault(key, []).append(r["path"])
    for key, g in sorted(groups.items()):
        m = tr.fit_model(g["real"], g["floor"], name=key)
        # round-trip calibration on the same scans with their own tremor removed
        smooth = [tr.detremor(gm.long_drawing(Drawing.load(p))) for p in paths[key][:8]]
        m = tr.calibrate(m, smooth, float(np.sqrt(max(m.info["real_var"] - m.info["floor_var"], 0))),
                         np.random.default_rng(0))
        m.save(OUT / "models" / f"{key}.json")
        y = tr.synth_residual(m, 400000, np.random.default_rng(0))
        f = np.asarray(m.freqs)
        pk = float(1 / f[1:][np.argmax(np.asarray(m.psd)[1:])])
        rep[key] = {"rms_displacement_w": m.rms, "q99_abs_w": float(np.quantile(np.abs(y), 0.99)),
                    "peak_wavelength_w": pk, "kappa_gain": m.kappa_gain, "end_gain": m.end_gain,
                    "stroke_log_sd": m.stroke_log_sd, "calibration": m.info.get("calibration", 1.0), "floor_var": m.info["floor_var"], "real_var": m.info["real_var"]}
        print(key, {k: (np.round(v, 3).tolist() if isinstance(v, list) else round(v, 4)) for k, v in rep[key].items()})
    (OUT / "models" / "summary.json").write_text(json.dumps(rep, indent=1))


def load_model(art: str) -> tr.TremorModel:
    return tr.TremorModel.load(OUT / "models" / f"{art}.json")


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------

def reals(art: str) -> list[Drawing]:
    out = []
    for p in sorted((EXTRACT / art).glob("*.json")):
        ld = gm.long_drawing(Drawing.load(p))
        if len(ld.strokes) >= 3:
            out.append(ld)
    return out


def generated(art: str, n: int, seed: int = 11) -> list[Drawing]:
    cache = OUT / "gen" / f"{art}_{n}_{seed}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    g = gm.Grammar.load(GRAMMARS / f"grammar_{art}.json")
    out = []
    for i in range(n):
        d = gm.generate_drawing(g, np.random.default_rng([seed, i]), (1200, 1200))
        if len(d.strokes) >= 3:
            out.append(d)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(out))
    return out


TREM_FEATS = ("rms", "rms_robust", "q90_abs", "kurtosis", "corr_len_w", "rms_lambda_2_4w",
              "rms_lambda_4_8w", "rms_lambda_8_16w")


def tremor_features(d: Drawing) -> dict:
    st = tr.residual_stats(tr.drawing_residuals(d))
    f = {f"tr_{k}": float(st.get(k, np.nan)) for k in TREM_FEATS}
    e = st.get("rms_by_end") or [np.nan] * 4
    f["tr_end_ratio"] = float(e[0] / e[-1]) if e[-1] and np.isfinite(e[-1]) else np.nan
    return f


def _panel_job(args):
    d, smw = args
    import warnings
    from gesture import panel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _ = panel.features_with_info(d, sigma_frac=1e-4 if smw < 2 else 0.01, clothoid=False,
                                        sigma_min_w=smw)
    return f


def _auc(x, y):
    from sklearn.metrics import roc_auc_score
    ok = np.isfinite(x)
    if ok.sum() < 6 or len(set(y[ok])) < 2:
        return np.nan
    return float(roc_auc_score(y[ok], x[ok]))


def _clf_auc(X, y, seed=0):
    """5-fold CV logistic-regression AUC (median-imputed, standardised)."""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score
    X = np.where(np.isfinite(X), X, np.nan)
    keep = ~np.all(np.isnan(X), axis=0)
    X = X[:, keep]
    pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=5000))
    aucs = []
    for rep in range(5):
        cv = StratifiedKFold(5, shuffle=True, random_state=seed + rep)
        p = cross_val_predict(pipe, X, y, cv=cv, method="predict_proba")[:, 1]
        aucs.append(roc_auc_score(y, p))
    return float(np.mean(aucs))


def stage_eval(a):
    rows = []
    sets = {}
    for art in ARTISTS:
        m = load_model(art)
        R = reals(art)
        Gd = generated(art, a.n_gen)
        rng = np.random.default_rng(5)
        GT = [tr.apply_tremor(d, m, np.random.default_rng([5, i])) for i, d in enumerate(Gd)]
        sets[art] = {"real": R, "v4": Gd, "v4+tremor": GT}
    feats = {}
    with ProcessPoolExecutor(WORKERS) as ex:
        for art, S in sets.items():
            for cond, ds in S.items():
                tf = [tremor_features(d) for d in ds]
                fine = list(ex.map(_panel_job, [(d, a.fine_w) for d in ds]))
                std = list(ex.map(_panel_job, [(d, 7.0) for d in ds]))
                feats[(art, cond)] = {"tremor": tf, "fine": fine, "std": std}
                print(art, cond, len(ds), "drawings", flush=True)
    (OUT / "eval_feats.pkl").write_bytes(pickle.dumps(feats))
    report = {}
    for art in ARTISTS:
        rep = {}
        for fam in ("tremor", "fine", "std"):
            names = sorted(set().union(*[set(f) for f in feats[(art, "real")][fam]]) &
                           set().union(*[set(f) for f in feats[(art, "v4")][fam]]))
            names = [n for n in names if not n.startswith(("w_", "end_"))]   # geometry only
            mat = {c: np.array([[f.get(n, np.nan) for n in names] for f in feats[(art, c)][fam]])
                   for c in ("real", "v4", "v4+tremor")}
            res = {}
            for c1, c2 in (("real", "v4"), ("real", "v4+tremor"), ("v4", "v4+tremor")):
                X = np.vstack([mat[c1], mat[c2]])
                y = np.r_[np.zeros(len(mat[c1])), np.ones(len(mat[c2]))]
                res[f"{c1}|{c2}"] = _clf_auc(X, y)
            # per-feature AUC real vs v4 and real vs v4+tremor (|AUC−.5| shown)
            pf = []
            for j, n in enumerate(names):
                y = lambda A, B: (np.r_[A[:, j], B[:, j]], np.r_[np.zeros(len(A)), np.ones(len(B))])
                a1 = _auc(*y(mat["real"], mat["v4"]))
                a2 = _auc(*y(mat["real"], mat["v4+tremor"]))
                a3 = _auc(*y(mat["v4"], mat["v4+tremor"]))
                pf.append((n, a1, a2, a3, float(np.nanmedian(mat["real"][:, j])), float(np.nanmedian(mat["v4"][:, j])),
                           float(np.nanmedian(mat["v4+tremor"][:, j]))))
            res["n_features"] = len(names)
            res["mean_abs_dev_real_v4"] = float(np.nanmean([abs(p[1] - .5) for p in pf]))
            res["mean_abs_dev_real_v4t"] = float(np.nanmean([abs(p[2] - .5) for p in pf]))
            res["mean_abs_dev_v4_v4t"] = float(np.nanmean([abs(p[3] - .5) for p in pf]))
            res["per_feature"] = pf
            rep[fam] = res
            print(f"{art} {fam}: n_feat={len(names)} clf AUC real|v4 {res['real|v4']:.3f}  real|v4+t {res['real|v4+tremor']:.3f}  "
                  f"v4|v4+t {res['v4|v4+tremor']:.3f} | mean|AUC−.5| per feature {res['mean_abs_dev_real_v4']:.3f} → "
                  f"{res['mean_abs_dev_real_v4t']:.3f} (v4 vs v4+t {res['mean_abs_dev_v4_v4t']:.3f})")
            if fam != "std":
                top = sorted(pf, key=lambda p: -abs(p[1] - .5))[:8]
                for p in top:
                    print(f"     {p[0]:28s} AUC r|v4 {p[1]:.2f} r|v4t {p[2]:.2f}  med real {p[4]:.4g} v4 {p[5]:.4g} v4t {p[6]:.4g}")
        report[art] = rep
    (OUT / "eval.json").write_text(json.dumps(report, indent=1, default=float))


# ---------------------------------------------------------------------------
# blinded pairs (logic copied from experiments/blind_pairs.py; smoothing 1 px)
# ---------------------------------------------------------------------------

SIDE, LW, CROP = 1200, 3.0, 480
PAIR_SMOOTH = 1.0      # px at render scale (blind_pairs used 5 px ≈ 2 w, hiding tremor)
PAIRS = REPO / ".local/gesture/out/blind_tremor/pairs"
KEY = Path("/tmp/gesture_tremor_key.json")


def fit_canvas(d: Drawing, side: int = SIDE, smooth_px: float = PAIR_SMOOTH, lw: float = LW) -> Drawing:
    from gesture.curvature import resample, smooth
    P = np.vstack([s.points for s in d.strokes])
    lo, hi = P.min(0), P.max(0)
    k = (side - 80) / max((hi - lo).max(), 1e-9)
    st = []
    for s in d.strokes:
        q = (s.points - lo) * k + 40
        if len(q) >= 3:
            r = resample(q, 0.5, closed=s.closed)
            if len(r) >= 5:
                q = smooth(r, smooth_px, 0.5, closed=s.closed)
        st.append(Stroke(q, closed=s.closed))
    st = _drop_plate_lines(st, side)
    st = _snap_ends(st, 3 * lw)
    W, H = (np.ceil((hi - lo) * k) + 80).astype(int)
    return Drawing(st, source=d.source, size=(int(W), int(H)))


def _drop_plate_lines(st, side):
    out = []
    for s in st:
        p = s.points
        L = float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1))) if len(p) > 1 else 0.0
        chord = float(np.linalg.norm(p[-1] - p[0])) if len(p) > 1 else 0.0
        if L > 0.25 * side and chord > 0.995 * L:
            continue
        out.append(s)
    return out


def _snap_ends(st, tol):
    from scipy.spatial import cKDTree
    if len(st) < 2:
        return st
    pts = [s.points.copy() for s in st]
    allp = np.vstack(pts)
    owner = np.concatenate([np.full(len(p), i) for i, p in enumerate(pts)])
    tree = cKDTree(allp)
    for i, p in enumerate(pts):
        if st[i].closed or len(p) < 2:
            continue
        for e in (0, -1):
            for j in tree.query_ball_point(p[e], tol):
                if owner[j] != i and np.linalg.norm(allp[j] - p[e]) < tol:
                    p[e] = allp[j]
                    break
    return [Stroke(p, closed=s.closed) for p, s in zip(pts, st)]


def render_lines(d: Drawing, lw: float = LW, seed: int = 1) -> np.ndarray:
    return synth.render(d, line_width=lw, use_stroke_width=False, paper_noise=0.0, blur_sigma=0.6, seed=seed)


def crop(img, rng, min_ink=0.012, tries=200, size=CROP):
    H, W = img.shape
    best = None
    for _ in range(tries):
        y = int(rng.integers(0, max(H - size, 1)))
        x = int(rng.integers(0, max(W - size, 1)))
        c = img[y:y + size, x:x + size]
        ink = float((c < 128).mean())
        if c.shape == (size, size) and ink >= min_ink:
            return c
        if c.shape == (size, size) and (best is None or ink > best[0]):
            best = (ink, c)
    return best[1] if best else None


def pair_image(a, b):
    from PIL import Image, ImageDraw
    im = Image.new("L", (2 * CROP + 60, CROP + 40), 255)
    im.paste(Image.fromarray(a), (20, 30))
    im.paste(Image.fromarray(b), (CROP + 40, 30))
    d = ImageDraw.Draw(im)
    d.text((20 + CROP // 2, 8), "A", fill=0)
    d.text((CROP + 40 + CROP // 2, 8), "B", fill=0)
    d.line([(CROP + 30, 30), (CROP + 30, CROP + 30)], fill=180)
    return im


def stage_pairs(a):
    rng = np.random.default_rng(a.pair_seed)
    PAIRS.mkdir(parents=True, exist_ok=True)
    for f in PAIRS.glob("*.png"):
        f.unlink()
    jobs = []
    per = a.pairs_per
    for art in ARTISTS:
        m = load_model(art)
        R = reals(art)
        gens = generated(art, 2 * per + 4, seed=21)
        gA, gB = gens[:len(gens) // 2], gens[len(gens) // 2:]
        rimg = [render_lines(fit_canvas(d)) for d in R]
        v4 = [render_lines(fit_canvas(d)) for d in gA]
        v4t = [render_lines(fit_canvas(tr.apply_tremor(d, m, np.random.default_rng([a.pair_seed, i]))))
               for i, d in enumerate(gB)]
        order = list(rng.permutation(len(R)))
        used = 0

        def next_real(exclude=None):
            nonlocal used, order
            for _ in range(len(order) + 1):
                if not order:
                    order = list(rng.permutation(len(R)))
                j = order.pop()
                if j != exclude:
                    used += 1
                    return j
            return int(rng.integers(len(R)))

        for i in range(per):
            r = crop(rimg[next_real()], rng)
            g = crop(v4[i % len(v4)], rng)
            if r is not None and g is not None:
                jobs.append(("test_v4", art, r, g))
            r = crop(rimg[next_real()], rng)
            g = crop(v4t[i % len(v4t)], rng)
            if r is not None and g is not None:
                jobs.append(("test_v4_tremor", art, r, g))
            jr = next_real()
            jc = next_real(exclude=jr)
            cal = tr.apply_tremor(tr.detremor(R[jc]), m, np.random.default_rng([a.pair_seed, 99, i]))
            r = crop(rimg[jr], rng)
            g = crop(render_lines(fit_canvas(cal)), rng)
            if r is not None and g is not None:
                jobs.append(("calib_retremor", art, r, g))
        print(art, "pairs so far", len(jobs), flush=True)
    order = rng.permutation(len(jobs))
    key = {}
    for n, j in enumerate(order, 1):
        cond, art, r, g = jobs[j]
        real_left = bool(rng.integers(2))
        img = pair_image(r, g) if real_left else pair_image(g, r)
        name = f"pair_{n:03d}.png"
        img.save(PAIRS / name)
        key[name] = {"condition": cond, "artist": art, "real": "A" if real_left else "B"}
    KEY.write_text(json.dumps(key, indent=1))
    from collections import Counter
    print(len(key), "pairs →", PAIRS, "| key →", KEY, "|", dict(Counter(v["condition"] for v in key.values())))


# ---------------------------------------------------------------------------
# sheets
# ---------------------------------------------------------------------------

def _label(img, text):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img).convert("RGB")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 * len(text) + 10, 18], fill=(255, 252, 240))
    d.text((5, 3), text, fill=(16, 15, 15))
    return np.asarray(im)


def stage_sheets(a):
    from PIL import Image
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    lw = 1.5
    for art in ARTISTS:
        m = load_model(art)
        R = reals(art)
        gens = generated(art, a.n_gen)
        # the generated drawing with the most ink; the real drawing with the most long-stroke ink
        gd = max(gens, key=lambda d: sum(s.length() for s in d.strokes) / d.ref_length())
        rd = sorted(R, key=lambda d: -sum(s.length() for s in d.strokes) / d.ref_length())[len(R) // 4]
        panels = [("real", rd), ("v4", gd),
                  ("v4 + tremor 0.5", tr.apply_tremor(gd, m, np.random.default_rng(3), 0.5)),
                  ("v4 + tremor 1.0", tr.apply_tremor(gd, m, np.random.default_rng(3), 1.0)),
                  ("v4 + tremor 3.0", tr.apply_tremor(gd, m, np.random.default_rng(3), 3.0))]
        imgs = [(t, render_lines(fit_canvas(d, lw=lw), lw=lw)) for t, d in panels]
        # common zoom window on the generated ones (most ink), separate one on the real
        def window(img, size=500):
            H, W = img.shape
            best, bxy = -1, (0, 0)
            for y in range(0, max(H - size, 1), 50):
                for x in range(0, max(W - size, 1), 50):
                    ink = float((img[y:y + size, x:x + size] < 128).mean())
                    if ink > best:
                        best, bxy = ink, (y, x)
            return bxy
        yg, xg = window(imgs[1][1])
        yr, xr = window(imgs[0][1])
        top, bot = [], []
        for i, (t, im) in enumerate(imgs):
            y, x = (yr, xr) if i == 0 else (yg, xg)
            z = im[y:y + 500, x:x + 500]
            z = np.pad(z, ((0, 500 - z.shape[0]), (0, 500 - z.shape[1])), constant_values=255)
            full = np.asarray(Image.fromarray(im).resize((500, int(500 * im.shape[0] / im.shape[1]))
                                                         if im.shape[1] >= im.shape[0] else
                                                         (int(500 * im.shape[1] / im.shape[0]), 500)))
            f2 = np.full((500, 500), 255, np.uint8)
            f2[:full.shape[0], :full.shape[1]] = full
            top.append(_label(f2, f"{art}: {t}"))
            bot.append(_label(z, "1:1 detail"))
        sheet = np.vstack([np.hstack(top), np.hstack(bot)])
        Image.fromarray(sheet).save(OUT / "sheets" / f"tremor-{art}.png")
        Image.fromarray(sheet).save(OUT / "sheets" / f"tremor-{art}.jpg", quality=85)
        print(art, "sheet", OUT / "sheets" / f"tremor-{art}.png")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stages", nargs="+")
    ap.add_argument("--per-artist", type=int, default=10)
    ap.add_argument("--n-gen", type=int, default=16)
    ap.add_argument("--fine-w", type=float, default=0.75)
    ap.add_argument("--pairs-per", type=int, default=10, help="pairs per condition per artist")
    ap.add_argument("--pair-seed", type=int, default=17)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    for s in a.stages:
        globals()[f"stage_{s}"](a)


if __name__ == "__main__":
    main()
