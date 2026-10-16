"""Bursty tremor (tremor v2) study — results/tremor-v2-2026-10-16.md.

Stages (each caches into .local/gesture/out/tremor_v2/):

  floor   per scan, band 0.3–4 w (HI = 4): real long-stroke residuals with
          context (junction distance), and the extraction floor (the scan's
          own long strokes smoothed at 8 w, rendered with matched noise,
          re-extracted). Same procedure as tremor_study.floor, wider band.
  burst   burstiness measurements per artist / Matisse medium: local-rms
          envelope vs phase-randomised surrogates, bimodality, dwell lengths,
          kinks, triggers → burst.json
  model   fit v2 models (stationary spectrum + regime + kinks) → models/*.json
  eval    real vs v4+v1 vs v4+v2: tremor + burst features (per-feature AUC,
          classifier) and the 7 w standard panel → eval.json
  pairs   blinded judge pairs (three conditions), key → /tmp
  sheets  v1 vs v2 at amount 1 and 2 next to real

  .local/gesture/.venv/bin/python tools/gesture/experiments/tremor_v2_study.py floor burst model eval pairs sheets
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from gesture import grammar_v4_frozen as gm  # noqa: E402
from gesture import tremor as tr  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402
import tremor_study as t1  # noqa: E402

REPO = HERE.parents[2]
EXTRACT = REPO / ".local/gesture/out/extract_hybrid"
OUT = REPO / ".local/gesture/out/tremor_v2"
V1MODELS = REPO / ".local/gesture/out/tremor/models"
ARTISTS = ("matisse", "hokusai", "ingres")
WORKERS = 3
HI = tr.HI_W2          # 4 w


def _slim(res):
    return [{k: v for k, v in d.items() if k not in ("P", "C", "n")} for d in res]


# ---------------------------------------------------------------------------
# floor (band 0.3–4 w)
# ---------------------------------------------------------------------------

def floor_one(args) -> dict:
    path, artist, med, pn_factor = args
    from gesture import extract_hybrid
    from gesture.extract import load_image
    from scipy.ndimage import gaussian_filter1d
    t0 = time.perf_counter()
    d = Drawing.load(path)
    ld = gm.long_drawing(d)
    run = d.meta.get("run", {})
    gray, scale = load_image(REPO / d.source, invert=bool(run.get("invert")), max_side=run.get("max_side", 2500))
    H, W = gray.shape
    w = gm.drawing_width(ld) * scale
    real = tr.drawing_residuals(ld, hi_w=HI, context=d)
    cps = np.vstack([(s.points + 0.5) * scale - 0.5 for s in d.strokes])
    sig, paper, ink = t1._hp_noise(gray, cps, w)
    noise_rel = sig / max(paper - ink, 1e-3)
    pn = float(np.clip(noise_rel / pn_factor, 0.0, 0.6))
    gt = []
    for s in ld.strokes:
        q = (s.points + 0.5) * scale - 0.5
        ws = s.width * scale if s.width is not None else np.full(len(q), w)
        r = tr.lateral_residual(q, float(np.median(ws)), closed=s.closed, lo_w=0.0, hi_w=8.0)
        C = r["C"]
        if len(C) < 4:
            continue
        wv = np.interp(np.linspace(0, 1, len(C)), np.linspace(0, 1, len(ws)), ws)
        wv = gaussian_filter1d(wv, 8.0 / tr.STEP_W, mode="nearest")
        gt.append(Stroke(C, width=wv, closed=s.closed))
    gtd = Drawing(gt, source="floor", size=(W, H), meta={"line_width_px": w})
    img = t1._render_noisy(gtd, pn, 1, w, False)
    ex = extract_hybrid.extract(img, line_width_hint=w)
    exl = gm.long_drawing(ex)
    out = {"path": str(path), "artist": artist, "medium": med, "w_work": w, "noise_rel": noise_rel,
           "real": _slim(real), "floor": _slim(tr.drawing_residuals(exl, hi_w=HI, context=ex)),
           "gt": _slim(tr.drawing_residuals(gtd, hi_w=HI))}
    out["secs"] = round(time.perf_counter() - t0, 1)
    return out


def stage_floor(a):
    pnf = t1._calibrate()
    md = t1.media()
    jobs = []
    for art in ARTISTS:
        files = sorted((EXTRACT / art).glob("*.json"))
        if art != "matisse":
            files = files[:10]
        for f in files:
            m = md.get((art, f.stem), "?")
            if art == "matisse" and m not in ("etching", "lithograph"):
                continue
            jobs.append((f, art, m, pnf))
    (OUT / "floor").mkdir(parents=True, exist_ok=True)
    todo = [j for j in jobs if not (OUT / "floor" / f"{j[1]}_{j[0].stem}.pkl").exists()]
    print(len(jobs), "scans,", len(todo), "to do", flush=True)
    with ProcessPoolExecutor(WORKERS) as ex:
        for r in ex.map(floor_one, todo):
            name = f"{r['artist']}_{Path(r['path']).stem}.pkl"
            (OUT / "floor" / name).write_bytes(pickle.dumps(r))
            print(f"  {name}: real={len(r['real'])} floor={len(r['floor'])} {r['secs']}s", flush=True)


def load_floor():
    return [pickle.loads(p.read_bytes()) for p in sorted((OUT / "floor").glob("*.pkl"))]


def groups_of(F, split_media=True):
    g = {}
    for r in F:
        keys = [r["artist"]] + ([f"{r['artist']}_{r['medium']}"] if split_media and r["artist"] == "matisse" else [])
        for k in keys:
            x = g.setdefault(k, {"real": [], "floor": [], "gt": [], "paths": []})
            x["real"] += r["real"]
            x["floor"] += r["floor"]
            x["gt"] += r["gt"]
            x["paths"].append(r["path"])
    return g


# ---------------------------------------------------------------------------
# burst
# ---------------------------------------------------------------------------

BURST_KEYS = ("rms", "kurtosis", "env_lsd_within", "env_lsd_within_excess", "env_corr_w", "shaky_frac",
              "dwell_shaky_w", "dwell_calm_w", "dwell_shaky_cv", "dwell_calm_cv", "kink_rate", "kink_d2_rate",
              "bimodal_dbic", "env_skew", "trig_kappa", "trig_end", "trig_junction", "trig_len")


def _res_real(path, hi):
    d = Drawing.load(path)
    return tr.drawing_residuals(gm.long_drawing(d), hi_w=hi, context=d)


def burst_sets(a, hi: float) -> dict:
    """{group: {cond: residual list}} at band 0.3–hi w."""
    F = load_floor()
    old = {Path(p).stem: pickle.loads(p.read_bytes()) for p in (REPO / ".local/gesture/out/tremor/floor").glob("*.pkl")}
    G = {}
    for r in F:
        keys = [r["artist"]] + ([f"{r['artist']}_{r['medium']}"] if r["artist"] == "matisse" else [])
        real = _slim(_res_real(r["path"], hi))
        if hi == HI:
            floor = r["floor"]
        else:
            floor = old.get(f"{r['artist']}_{Path(r['path']).stem}", {}).get("floor", [])
        for k in keys:
            x = G.setdefault(k, {"real": [], "floor": []})
            x["real"] += real
            x["floor"] += floor
    return G


def add_generated(G, a, hi, models: dict | None = None):
    for art in ARTISTS:
        gens = t1.generated(art, a.n_gen)
        G[art]["v4"] = [r for d in gens for r in tr.drawing_residuals(d, hi_w=hi, context=d)]
        for tag, m in (models or {}).get(art, {}).items():
            out = []
            for i, d in enumerate(gens):
                dt = tr.apply_tremor(d, m, np.random.default_rng([5, i]))
                out += tr.drawing_residuals(dt, hi_w=hi, context=dt)
            G[art][tag] = out


def print_burst(key, rep):
    print(key, flush=True)
    for cond, b in rep.items():
        s = b["surr"]
        print(f"   {cond:7s} n={b['n_strokes']:4d} rms={b['rms']:.3f} kurt={b['kurtosis']:.1f}/{s['kurtosis']:.1f} "
              f"lsdW={b['env_lsd_within']:.3f}/{s['env_lsd_within']:.3f} exc={b['env_lsd_within_excess']:.3f} "
              f"envL={b['env_corr_w']:.1f}/{s['env_corr_w']:.1f} shaky={b['shaky_frac']:.2f}/{s['shaky_frac']:.2f} "
              f"dwell s/c={b['dwell_shaky_w']:.1f}/{b['dwell_calm_w']:.1f} (surr {s['dwell_shaky_w']:.1f}/{s['dwell_calm_w']:.1f}) "
              f"cv {b['dwell_shaky_cv']:.2f}/{b['dwell_calm_cv']:.2f} kinks={b['kink_rate']:.2f}/{s['kink_rate']:.2f} "
              f"d2k={b['kink_d2_rate']:.2f}/{s['kink_d2_rate']:.2f} bim={b['bimodal_dbic']:.3f}/{s['bimodal_dbic']:.3f} "
              f"skew={b['env_skew']:.2f}/{s['env_skew']:.2f} trig κ={b['trig_kappa']:.2f} end={b['trig_end']:.2f} "
              f"junc={b['trig_junction']:.2f} len={b['trig_len']:.2f} kink@junc={np.round(b['kink_near_junction'], 2).tolist()}",
              flush=True)


def stage_burst(a):
    rep = {}
    for hi in (2.0, HI):
        G = burst_sets(a, hi)
        m1 = {art: {"v4+v1": tr.TremorModel.load(V1MODELS / f"{art}.json")} for art in ARTISTS}
        add_generated(G, a, hi, m1)
        for norm in (False, True):
            tag = f"hi{hi:g}" + ("_knorm" if norm else "")
            print("=====", tag)
            rep[tag] = {}
            for key in sorted(G):
                rep[tag][key] = {}
                for cond, res in G[key].items():
                    if res:
                        rep[tag][key][cond] = tr.burst_stats(res, np.random.default_rng(0), kappa_norm=norm)
                print_burst(key, rep[tag][key])
    (OUT / "burst.json").write_text(json.dumps(rep, indent=1, default=float))


def _var(res):
    x = np.concatenate([d["r"][~d["corner"]] for d in res])
    return float(np.mean(x ** 2))


def _fit_one(args):
    key, paths, a_ngen = args
    real2 = [r for p in paths for r in _res_real(p, 2.0)]
    out = {"key": key}
    for kind in ("lognormal", "markov2"):
        out[kind] = tr.fit_regime(real2, 0, kind=kind, fit_kinks=(kind == "lognormal"))
    out["lognormal_nojunction"] = tr.fit_regime(real2, 0, kind="lognormal", min_jdist=5.0, fit_kinks=False)
    return out


def stage_model(a):
    F = load_floor()
    G = groups_of(F)
    (OUT / "models").mkdir(parents=True, exist_ok=True)
    jobs = [(k, G[k]["paths"], a.n_gen) for k in sorted(G)]
    with ProcessPoolExecutor(WORKERS) as ex:
        fits = {r["key"]: r for r in ex.map(_fit_one, jobs)}
    summary = {}
    for key in sorted(G):
        art = key.split("_")[0]
        f = fits[key]
        m1 = tr.TremorModel.load(V1MODELS / f"{key}.json")
        gens = t1.generated(art, a.n_gen)
        v4res = [r for d in gens for r in tr.drawing_residuals(d, hi_w=HI)]
        nseg = 128
        fr, pr, _ = tr._welch_runs(G[key]["real"], nseg)
        _, pf, _ = tr._welch_runs(G[key]["floor"], nseg)
        _, pv, _ = tr._welch_runs(v4res, nseg)
        p = np.maximum(pr - pf - pv, 0.0) / np.maximum(tr.band_response(fr, tr.LO_W, HI) ** 2, tr.H2_MIN)
        p[0] = 0.0
        df = float(fr[1] - fr[0])
        target = float(np.sqrt(max(_var(G[key]["real"]) - _var(G[key]["floor"]) - _var(v4res), 1e-6)))
        m2 = tr.TremorModel(**{**m1.__dict__, "name": f"{key}_v2", "freqs": [float(x) for x in fr],
                               "psd": [float(x) for x in p], "rms": float(np.sqrt(np.sum(p) * df)),
                               "version": 2, "regime": f["lognormal"]["regime"], "kinks": f["lognormal"]["kinks"],
                               "info": {"band_hi_w": HI, "v1_rms": m1.rms, "target_rms_hi4": target,
                                        "psd_real": pr.tolist(), "psd_floor": pf.tolist(), "psd_v4": pv.tolist(),
                                        "fit": {k: {kk: vv for kk, vv in f[k].items()} for k in f if k != "key"}}})
        m2 = tr.calibrate(m2, gens[:8], target, np.random.default_rng(0), hi_w=HI)
        m2.save(OUT / "models" / f"{key}.json")
        y = tr.synth_residual(m2, 400000, np.random.default_rng(0))
        g = tr.synth_regime(m2.regime, 400000, np.random.default_rng(1)) if m2.regime else 1.0
        yk = y * g + (tr.synth_kinks(m2.kinks, 400000, np.random.default_rng(2)) if m2.kinks else 0)
        summary[key] = {"rms_base_w": m2.rms, "rms_total_w": float(np.std(yk)), "q99_w": float(np.quantile(np.abs(yk), .99)),
                        "v1_rms_w": m1.rms, "calibration": m2.info.get("calibration"), "target_rms_hi4": target,
                        "regime": m2.regime, "kinks": m2.kinks,
                        "fit_lognormal": {k: f["lognormal"][k] for k in ("target", "fit", "loss", "kinks_fit")},
                        "fit_markov2": {k: f["markov2"][k] for k in ("regime", "fit", "loss")},
                        "fit_nojunction": {k: f["lognormal_nojunction"][k] for k in ("regime", "target", "fit")}}
        print(key, json.dumps({k: (np.round(v, 3).tolist() if isinstance(v, (float, list)) else v)
                               for k, v in summary[key].items()}, default=lambda o: round(o, 3) if isinstance(o, float) else str(o)), flush=True)
    (OUT / "models" / "summary.json").write_text(json.dumps(summary, indent=1, default=float))


def load_v2(key):
    return tr.TremorModel.load(OUT / "models" / f"{key}.json")


BURST_FEATS = ("env_lsd_within", "env_corr_w", "kink_d2_rate", "kink_rate", "kurtosis", "shaky_frac",
               "dwell_shaky_w", "dwell_calm_w", "env_skew")


def burst_features(d: Drawing) -> dict:
    f = t1.tremor_features(d)
    for hi, tag in ((2.0, "b2"), (HI, "b4")):
        res = tr.drawing_residuals(d, hi_w=hi)
        b = tr.burst_stats(res, np.random.default_rng(0), surrogate=False, kappa_norm=True, bimodal=False)
        for k in BURST_FEATS:
            f[f"{tag}_{k}"] = float(b.get(k, np.nan))
        if hi == HI:
            st = tr.residual_stats(res)
            for k in ("rms", "corr_len_w", "rms_lambda_4_8w", "rms_lambda_8_16w"):
                f[f"b4_{k}_spec"] = float(st.get(k, np.nan))
    return f


def _feat_job(args):
    d, smw = args
    import warnings
    warnings.simplefilter("ignore")
    return burst_features(d), t1._panel_job((d, smw))


def stage_eval(a):
    feats = {}
    conds = ("real", "v4", "v4+v1", "v4+v2")
    with ProcessPoolExecutor(WORKERS) as ex:
        for art in ARTISTS:
            m1 = tr.TremorModel.load(V1MODELS / f"{art}.json")
            m2 = load_v2(art)
            R = t1.reals(art)
            Gd = t1.generated(art, a.n_gen)
            S = {"real": R, "v4": Gd,
                 "v4+v1": [tr.apply_tremor(d, m1, np.random.default_rng([5, i])) for i, d in enumerate(Gd)],
                 "v4+v2": [tr.apply_tremor(d, m2, np.random.default_rng([5, i])) for i, d in enumerate(Gd)]}
            for c in conds:
                out = list(ex.map(_feat_job, [(d, 7.0) for d in S[c]]))
                feats[(art, c)] = {"burst": [o[0] for o in out], "std": [o[1] for o in out]}
                print(art, c, len(S[c]), flush=True)
    (OUT / "eval_feats.pkl").write_bytes(pickle.dumps(feats))
    report = {}
    for art in ARTISTS:
        rep = {}
        for fam in ("burst", "std"):
            names = sorted(set().union(*[set(f) for f in feats[(art, "real")][fam]]))
            if fam == "std":
                names = [n for n in names if not n.startswith(("w_", "end_"))]
            mat = {c: np.array([[f.get(n, np.nan) for n in names] for f in feats[(art, c)][fam]]) for c in conds}
            res = {}
            fams = {"all": names}
            if fam == "burst":
                fams["burst_only"] = [n for n in names if n.startswith(("b2_", "b4_")) and not n.endswith("_spec")]
                fams["v1_tremor_only"] = [n for n in names if n.startswith("tr_")]
            for sub, nn in fams.items():
                idx = [names.index(n) for n in nn]
                for c1, c2 in (("real", "v4"), ("real", "v4+v1"), ("real", "v4+v2"), ("v4+v1", "v4+v2")):
                    X = np.vstack([mat[c1][:, idx], mat[c2][:, idx]])
                    y = np.r_[np.zeros(len(mat[c1])), np.ones(len(mat[c2]))]
                    res[f"{sub}:{c1}|{c2}"] = t1._clf_auc(X, y)
            pf = []
            for j, n in enumerate(names):
                def au(c1, c2):
                    return t1._auc(np.r_[mat[c1][:, j], mat[c2][:, j]], np.r_[np.zeros(len(mat[c1])), np.ones(len(mat[c2]))])
                pf.append({"f": n, "real|v4+v1": au("real", "v4+v1"), "real|v4+v2": au("real", "v4+v2"),
                           "v4+v1|v4+v2": au("v4+v1", "v4+v2"),
                           **{f"med_{c}": float(np.nanmedian(mat[c][:, j])) for c in conds}})
            res["per_feature"] = pf
            for c in ("v4+v1", "v4+v2"):
                res[f"mean_abs_dev_real|{c}"] = float(np.nanmean([abs(p[f"real|{c}"] - .5) for p in pf]))
            res["mean_abs_dev_v4+v1|v4+v2"] = float(np.nanmean([abs(p["v4+v1|v4+v2"] - .5) for p in pf]))
            rep[fam] = res
            print(art, fam, {k: round(v, 3) for k, v in res.items() if k != "per_feature"}, flush=True)
            if fam == "burst":
                for p_ in pf:
                    print(f"    {p_['f']:28s} r|v1 {p_['real|v4+v1']:.2f} r|v2 {p_['real|v4+v2']:.2f}  med real {p_['med_real']:.3g} "
                          f"v4+v1 {p_['med_v4+v1']:.3g} v4+v2 {p_['med_v4+v2']:.3g}", flush=True)
        report[art] = rep
    (OUT / "eval.json").write_text(json.dumps(report, indent=1, default=float))


PAIRS = REPO / ".local/gesture/out/blind_tremor2/pairs"
KEY = Path("/tmp/gesture_tremor2_key.json")


def full_band_v2(m2: tr.TremorModel) -> tr.TremorModel:
    """v2 with the WHOLE real band (real − floor, not minus v4's share): what
    replaces a real drawing's own tremor after detremor at the v2 band."""
    f = np.asarray(m2.freqs)
    pr, pf = np.asarray(m2.info["psd_real"]), np.asarray(m2.info["psd_floor"])
    k2 = float(m2.info.get("calibration", 1.0)) ** 2
    p = np.maximum(pr - pf, 0) / np.maximum(tr.band_response(f, tr.LO_W, HI) ** 2, tr.H2_MIN) * k2
    p[0] = 0.0
    return tr.TremorModel(**{**m2.__dict__, "name": m2.name + "_fullband", "psd": p.tolist(),
                             "rms": float(np.sqrt(np.sum(p) * (f[1] - f[0])))})


def _crop_xy(img, rng, min_ink=0.012, tries=200, size=t1.CROP):
    H, W = img.shape
    best = None
    for _ in range(tries):
        y = int(rng.integers(0, max(H - size, 1)))
        x = int(rng.integers(0, max(W - size, 1)))
        c = img[y:y + size, x:x + size]
        ink = float((c < 128).mean())
        if c.shape == (size, size) and ink >= min_ink:
            return y, x
        if c.shape == (size, size) and (best is None or ink > best[0]):
            best = (ink, (y, x))
    return best[1] if best else None


def stage_pairs(a):
    rng = np.random.default_rng(a.pair_seed)
    PAIRS.mkdir(parents=True, exist_ok=True)
    for f in PAIRS.glob("*.png"):
        f.unlink()
    jobs = []
    per = a.pairs_per
    S = t1.CROP
    for art in ARTISTS:
        m1 = tr.TremorModel.load(V1MODELS / f"{art}.json")
        m2 = load_v2(art)
        mfull = full_band_v2(m2)
        R = t1.reals(art)
        gens = t1.generated(art, 2 * per + 4, seed=21)[:per + 2]
        rimg = [t1.render_lines(t1.fit_canvas(d)) for d in R]
        v1i = [t1.render_lines(t1.fit_canvas(tr.apply_tremor(d, m1, np.random.default_rng([a.pair_seed, i]))))
               for i, d in enumerate(gens)]
        v2i = [t1.render_lines(t1.fit_canvas(tr.apply_tremor(d, m2, np.random.default_rng([a.pair_seed, i]))))
               for i, d in enumerate(gens)]
        order = list(rng.permutation(len(R)))

        def next_real(exclude=None):
            nonlocal order
            for _ in range(len(order) + 1):
                if not order:
                    order = list(rng.permutation(len(R)))
                j = order.pop()
                if j != exclude:
                    return j
            return int(rng.integers(len(R)))

        def rcrop(img):
            yx = _crop_xy(img, rng)
            return None if yx is None else img[yx[0]:yx[0] + S, yx[1]:yx[1] + S]

        for i in range(per):
            k = i % len(gens)
            yx = _crop_xy(v1i[k], rng)      # same window on the v1 and v2 versions of one drawing
            for cond, im in (("test_v4_v1", v1i[k]), ("test_v4_v2", v2i[k])):
                r = rcrop(rimg[next_real()])
                g = im[yx[0]:yx[0] + S, yx[1]:yx[1] + S] if yx else None
                if r is not None and g is not None and g.shape == (S, S):
                    jobs.append((cond, art, r, g, k))
            jr = next_real()
            jc = next_real(exclude=jr)
            cal = tr.apply_tremor(tr.detremor(R[jc], hi_w=HI), mfull, np.random.default_rng([a.pair_seed, 99, i]))
            r = rcrop(rimg[jr])
            g = rcrop(t1.render_lines(t1.fit_canvas(cal)))
            if r is not None and g is not None:
                jobs.append(("calib_v2", art, r, g, jc))
        print(art, "pairs so far", len(jobs), flush=True)
    order = rng.permutation(len(jobs))
    key = {}
    for n, j in enumerate(order, 1):
        cond, art, r, g, src = jobs[j]
        real_left = bool(rng.integers(2))
        img = t1.pair_image(r, g) if real_left else t1.pair_image(g, r)
        name = f"pair_{n:03d}.png"
        img.save(PAIRS / name)
        key[name] = {"condition": cond, "artist": art, "real": "A" if real_left else "B", "machine_src": int(src)}
    KEY.write_text(json.dumps(key, indent=1))
    from collections import Counter
    print(len(key), "pairs ->", PAIRS, "| key ->", KEY, "|", dict(Counter(v["condition"] for v in key.values())))


def stage_sheets(a):
    from PIL import Image
    res_dir = HERE.parent / "results"
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    lw = 1.5
    for art in ARTISTS:
        m1 = tr.TremorModel.load(V1MODELS / f"{art}.json")
        m2 = load_v2(art)
        R = t1.reals(art)
        gens = t1.generated(art, a.n_gen)
        gd = max(gens, key=lambda d: sum(s.length() for s in d.strokes) / d.ref_length())
        rd = sorted(R, key=lambda d: -sum(s.length() for s in d.strokes) / d.ref_length())[len(R) // 4]
        panels = [("real", rd)]
        for amt in (1.0, 2.0):
            panels += [(f"v4 + v1 x{amt:g}", tr.apply_tremor(gd, m1, np.random.default_rng(3), amt)),
                       (f"v4 + v2 x{amt:g}", tr.apply_tremor(gd, m2, np.random.default_rng(3), amt))]
        imgs = [(t, t1.render_lines(t1.fit_canvas(d, lw=lw), lw=lw)) for t, d in panels]

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
            top.append(t1._label(f2, f"{art}: {t}"))
            bot.append(t1._label(z, "1:1 detail"))
        sheet = np.vstack([np.hstack(top), np.hstack(bot)])
        Image.fromarray(sheet).save(OUT / "sheets" / f"tremor-v2-{art}.png")
        q = 85
        while True:
            Image.fromarray(sheet).convert("L").save(res_dir / f"tremor-v2-{art}.jpg", quality=q)
            if (res_dir / f"tremor-v2-{art}.jpg").stat().st_size <= 600_000 or q <= 40:
                break
            q -= 10
        print(art, "sheet", res_dir / f"tremor-v2-{art}.jpg", (res_dir / f"tremor-v2-{art}.jpg").stat().st_size)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stages", nargs="+")
    ap.add_argument("--n-gen", type=int, default=16)
    ap.add_argument("--pairs-per", type=int, default=10)
    ap.add_argument("--pair-seed", type=int, default=23)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    for s in a.stages:
        globals()[f"stage_{s}"](a)


if __name__ == "__main__":
    main()
