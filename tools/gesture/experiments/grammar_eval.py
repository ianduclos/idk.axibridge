"""Grammar v2 evaluation (results/grammar-v2.md).

Subcommands (run from tools/gesture):

  scale     σ study on the long training strokes: segments per stroke and
            fit error at σ = 1.5/2/3/5 line widths and 0.005/0.01·ref
  prepare   fit + relations for every drawing (cached in
            .local/gesture/out/grammar_v2/prepared/), training-set table
  test1     stage-3 test 1: real long-stroke-only drawings vs as many
            generated drawings (same canvas sizes), panel features with the
            standard preprocessing, grouped-CV AUC + Cohen's d
  memo      memorisation on multi-segment strokes: generated vs held-out
            real vs segment-shuffled control vs jittered training copies

    ../../.local/gesture/.venv/bin/python -m experiments.grammar_eval scale
    ../../.local/gesture/.venv/bin/python -m experiments.grammar_eval prepare
    ../../.local/gesture/.venv/bin/python -m experiments.grammar_eval test1
    ../../.local/gesture/.venv/bin/python -m experiments.grammar_eval memo

Outputs: .local/gesture/out/grammar_v2/{scale,trainset,test1,memo}.{json,md}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import grammar as gm  # noqa: E402
from gesture import medium, panel  # noqa: E402
from gesture.clothoid import fit_stroke  # noqa: E402
from gesture.core import Drawing  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
EXTRACT = ROOT / ".local/gesture/out/extract_hybrid"
OUT = ROOT / ".local/gesture/out/grammar_v5"
PREP = ROOT / ".local/gesture/out/grammar_v2" / "prepared"   # fit cache shared with v2–v4 (unchanged)
ARTISTS = ("matisse", "hokusai", "ingres")
JOBS = int(os.environ.get("GESTURE_JOBS", "3"))     # shared machine: keep pools small
RELS = ("learned", "tree")


def load(artist: str) -> list[tuple[str, Drawing]]:
    return [(p.stem, Drawing.load(p)) for p in sorted((EXTRACT / artist).glob("*.json"))]


# ---------------------------------------------------------------------------
# 1. scale study
# ---------------------------------------------------------------------------

SCALES = (("1.5w", 1.5, None), ("2w", 2.0, None), ("3w", 3.0, None), ("5w", 5.0, None),
          ("0.005R", None, 0.005), ("0.01R", None, 0.01))


def _scale_job(args):
    pts, closed, w, R = args
    out = {}
    for name, sw, sf in SCALES:
        sg = sw * w if sw is not None else sf * R
        t = time.perf_counter()
        try:
            f = fit_stroke(pts, sigma=sg, closed=closed)
            toks = gm.fit_tokens(f, R)
            out[name] = {"nseg": gm.n_segments(toks), "ncorner": sum(1 for x in toks if x[0] == "corner"),
                         "err_w": float(f.rms_position_error / w), "err_sigma": float(f.rms_position_error / sg),
                         "sigma_w": float(sg / w), "t": time.perf_counter() - t}
        except Exception as e:  # noqa: BLE001
            out[name] = {"error": type(e).__name__}
    out["len_w"] = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)) / w)
    return out


def cmd_scale(a):
    rng = np.random.default_rng(0)
    jobs, who = [], []
    for art in ARTISTS:
        cand = []
        for stem, d in load(art):
            ld = gm.long_drawing(d)
            R = ld.ref_length()
            for st in ld.strokes:
                cand.append((st.points, st.closed, gm.stroke_width(st, ld), R))
        pick = rng.choice(len(cand), min(a.n, len(cand)), replace=False)
        jobs += [cand[i] for i in pick]
        who += [art] * len(pick)
    t0 = time.time()
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_scale_job, jobs, chunksize=4))
    print(f"scale study: {len(jobs)} strokes × {len(SCALES)} σ in {time.time() - t0:.0f}s")
    table = {}
    for art in ARTISTS:
        rr = [r for r, w in zip(res, who) if w == art]
        table[art] = {}
        for name, *_ in SCALES:
            ok = [r[name] for r in rr if "nseg" in r[name]]
            ns = np.array([o["nseg"] for o in ok])
            nc = np.array([o["ncorner"] for o in ok])
            lw = np.array([r["len_w"] for r in rr if "nseg" in r[name]])
            ew = np.array([o["err_w"] for o in ok])
            table[art][name] = {
                "n": len(ok), "sigma_w_median": float(np.median([o["sigma_w"] for o in ok])),
                "nseg_median": float(np.median(ns)), "nseg_q25_q75": [float(np.quantile(ns, .25)), float(np.quantile(ns, .75))],
                "share_single": float(np.mean(ns == 1)),
                "nseg_median_len_ge_100w": float(np.median(ns[lw >= 100])) if (lw >= 100).any() else None,
                "seg_len_w_median": float(np.median(lw / np.maximum(ns, 1))),
                "corners_per_stroke": float(nc.mean()),
                "err_w_median": float(np.median(ew)), "err_w_q90": float(np.quantile(ew, .9)),
                "err_sigma_median": float(np.median([o["err_sigma"] for o in ok])),
                "sec_per_fit": float(np.mean([o["t"] for o in ok]))}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scale.json").write_text(json.dumps(table, indent=1))
    L = ["| # | artist | σ | σ/w med | n | segs/stroke med (IQR) | single | segs ≥100w | seg len (w) | corners/stroke | err/w med (q90) | err/σ | s/fit |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    i = 0
    for art in ARTISTS:
        for name, *_ in SCALES:
            t = table[art][name]
            i += 1
            L.append(f"| S{i} | {art} | {name} | {t['sigma_w_median']:.1f} | {t['n']} | {t['nseg_median']:.0f} "
                     f"({t['nseg_q25_q75'][0]:.0f}–{t['nseg_q25_q75'][1]:.0f}) | {t['share_single']:.2f} | "
                     f"{t['nseg_median_len_ge_100w']} | {t['seg_len_w_median']:.0f} | {t['corners_per_stroke']:.2f} | "
                     f"{t['err_w_median']:.3f} ({t['err_w_q90']:.3f}) | {t['err_sigma_median']:.3f} | {t['sec_per_fit']:.3f} |")
    (OUT / "scale.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ---------------------------------------------------------------------------
# 2. prepare + training-set table
# ---------------------------------------------------------------------------

def _prep_job(args):
    art, stem, sigma_w = args
    p = PREP / f"v3-sw{sigma_w:g}" / art / f"{stem}.json"
    if p.exists():
        return art, stem, json.loads(p.read_text())
    d = Drawing.load(EXTRACT / art / f"{stem}.json")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pd = gm.prepare_drawing(d, sigma_w=sigma_w)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(pd))
    return art, stem, pd


def prepared(sigma_w=gm.SIGMA_W) -> dict[str, list[tuple[str, dict]]]:
    jobs = [(art, p.stem, sigma_w) for art in ARTISTS for p in sorted((EXTRACT / art).glob("*.json"))]
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_prep_job, jobs, chunksize=1))
    out = {a: [] for a in ARTISTS}
    for art, stem, pd in res:
        out[art].append((stem, pd))
    return out


def _topo_job(args):
    art, stem = args
    p = OUT / "topo" / art / f"{stem}.json"
    if p.exists():
        return art, stem, json.loads(p.read_text())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ts = gm.topology_summary(gm.long_drawing(Drawing.load(EXTRACT / art / f"{stem}.json")))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ts))
    return art, stem, ts


def topo_summaries() -> dict[str, dict[str, dict]]:
    """v5: per-drawing `topology_summary` of every real long subset (cached)."""
    jobs = [(art, p.stem) for art in ARTISTS for p in sorted((EXTRACT / art).glob("*.json"))]
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_topo_job, jobs, chunksize=2))
    out = {a: {} for a in ARTISTS}
    for art, stem, ts in res:
        out[art][stem] = ts
    return out


def learn_artist(art, P, sigma_w=gm.SIGMA_W, topo=None, **kw):
    """Learn an artist's grammar with the v5 topology targets, plus the
    crossing gain / double-contour rate from `calibrate` if present."""
    topo = topo_summaries() if topo is None else topo
    g = gm.learn(prepared=[pd for _, pd in P[art]], name=art, sigma_w=sigma_w,
                 topo=[topo[art][stem] for stem, _ in P[art] if stem in topo[art]], **kw)
    cg = OUT / "cross_gain.json"
    if cg.exists():
        g.relations["cross_gain"] = float(json.loads(cg.read_text()).get(art, 1.0))
    pdj = OUT / "p_double.json"
    if pdj.exists():
        g.relations["p_double"] = float(json.loads(pdj.read_text()).get(art, 0.0))
    egj = OUT / "end_gain.json"
    if egj.exists():
        g.relations["end_gain"] = json.loads(egj.read_text()).get(art, {})
    return g


def _calib_job(args):
    gpath, size, seed, gain, kw = args
    from gesture import topology as tp
    g = gm.Grammar.load(gpath)
    d = gm.generate_drawing(g, np.random.default_rng(seed), size, cross_gain=gain, **(kw or {}))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _ = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W, clothoid=False)
        t = tp.relation_graph(d)
    kinds = [e["kind"] for e in t.ends if e["kind"] != "self"]
    return {"cross": f.get("rel_cross_per_len", np.nan), "kinds": kinds, "par_ink": float(t.par_ink)}


def cmd_calibrate(a):
    """v5: per hand, tune (1) the crossing gain so generated drawings cross at
    the real long subsets' median rate (panel rel_cross_per_len), (2) gains
    on the planned start/end shares so the realised end-type shares (T / L /
    near / free, topology.relation_graph, pooled) match the real ones, and
    (3) the double-contour start rate so the median parallel-ink share
    matches. Damped (square-root) multiplicative updates; the round with the
    smallest summed |log ratio| error is kept."""
    P = prepared(a.sigma_w)
    TS = topo_summaries()
    out = {}
    for art in ARTISTS:
        g = learn_artist(art, P, a.sigma_w, topo=TS)
        for k in ("cross_gain", "p_double", "end_gain"):
            g.relations.pop(k, None)
        topo = g.relations["topo"]
        tgt_x = float(np.median([pd["relations"]["cross_per_ink"] for _, pd in P[art]
                                 if pd["relations"]["n"] >= 2]))
        tgt_e = topo["end_p"]
        tgt_p = topo["par_ink"]
        sizes = ([tuple(pd["size"]) for _, pd in P[art]] * 2)[:a.calib_n]
        gain, eg, pdbl = 1.0, {k: 1.0 for k in ("T", "L", "near", "free")}, 0.05
        tried = []
        for it in range(a.calib_rounds):
            g.relations.update(cross_gain=gain, end_gain=dict(eg), p_double=pdbl)
            gpath = OUT / f"grammar_{art}_calib.json"
            g.save(gpath)
            with ProcessPoolExecutor(JOBS) as ex:
                v = list(ex.map(_calib_job, [(str(gpath), sz, 500 + 37 * it + i, gain, None)
                                             for i, sz in enumerate(sizes)]))
            got_x = float(np.nanmedian([x["cross"] for x in v]))
            kinds = [k for x in v for k in x["kinds"]]
            got_e = {k: kinds.count(k) / max(len(kinds), 1) for k in tgt_e}
            got_p = float(np.median([x["par_ink"] for x in v]))
            lr = lambda t, g_: abs(np.log(max(g_, 1e-3) / max(t, 1e-3)))  # noqa: E731
            err = lr(tgt_x, got_x) + sum(lr(tgt_e[k], got_e[k]) for k in tgt_e) + lr(tgt_p, got_p)
            tried.append((err, it, {"cross_gain": gain, "end_gain": dict(eg), "p_double": pdbl,
                                    "got": {"cross": got_x, "ends": got_e, "par_ink": got_p}}))
            print(f"{art} it{it}: err {err:.2f} | cross gain {gain:.2f} → {got_x:.3f} (real {tgt_x:.3f}) | "
                  + " ".join(f"{k} {got_e[k]:.3f}/{tgt_e[k]:.3f}×{eg[k]:.2f}" for k in tgt_e)
                  + f" | par_ink {got_p:.3f}/{tgt_p:.3f} p_double {pdbl:.3f}", flush=True)
            gain *= 2.0 if got_x <= 0 else float(np.clip(np.sqrt(tgt_x / got_x), 0.5, 2.0))
            for k in eg:
                eg[k] = float(np.clip(eg[k] * np.clip(np.sqrt(max(tgt_e[k], 1e-3) / max(got_e[k], 1e-3)),
                                                       0.5, 2.0), 0.05, 6.0))
            pdbl = float(np.clip(pdbl + 0.5 * (tgt_p - got_p), 0.0, 0.4))
        # the crossing count is far noisier than the end shares: pick each
        # knob from the round where its own error was smallest
        def _ex(t):
            return abs(np.log(max(t[2]["got"]["cross"], 1e-3) / max(tgt_x, 1e-3)))
        bx = min(tried, key=_ex)
        be = min(tried, key=lambda t: t[0] - _ex(t))
        out[art] = {"err_cross": _ex(bx), "round_cross": bx[1], "err_ends_par": be[0] - _ex(be),
                    "round_ends_par": be[1], "cross_gain": bx[2]["cross_gain"],
                    "end_gain": be[2]["end_gain"], "p_double": be[2]["p_double"],
                    "got_cross": bx[2]["got"]["cross"], "got_ends_par": be[2]["got"]}
    (OUT / "calibration.json").write_text(json.dumps(out, indent=1))
    (OUT / "cross_gain.json").write_text(json.dumps({k: round(v["cross_gain"], 3) for k, v in out.items()}))
    (OUT / "p_double.json").write_text(json.dumps({k: round(v["p_double"], 3) for k, v in out.items()}))
    (OUT / "end_gain.json").write_text(json.dumps({k: v["end_gain"] for k, v in out.items()}))
    print(json.dumps(out, indent=1))


def cmd_prepare(a):
    t0 = time.time()
    P = prepared(a.sigma_w)
    print(f"prepared in {time.time() - t0:.0f}s")
    rows = {}
    for art in ARTISTS:
        S = [pd["select"] for _, pd in P[art]]
        rel = [pd["relations"] for _, pd in P[art]]
        nseg = [gm.n_segments(s["tokens"]) for _, pd in P[art] for s in pd["strokes"]]
        lw = [s["length"] * pd["R"] / pd["w"] for _, pd in P[art] for s in pd["strokes"]]
        att = [x for r in rel for x in r["attached"]]
        rows[art] = {
            "drawings": len(S), "with_long": sum(1 for s in S if s["n_long"] > 0),
            "n_all": sum(s["n_all"] for s in S), "n_hatch": sum(s["n_hatch"] for s in S),
            "n_long": sum(s["n_long"] for s in S), "n_fitted": len(nseg),
            "ink_long_share": sum(s["ink_long"] for s in S) / sum(s["ink_all"] for s in S),
            "ink_hatch_share": sum(s["ink_hatch"] for s in S) / sum(s["ink_all"] for s in S),
            "long_per_drawing_median": float(np.median([s["n_long"] for s in S])),
            "ink_long_R_median": float(np.median([r["ink"] for r in rel])),
            "len_w_median": float(np.median(lw)), "len_w_q90": float(np.quantile(lw, .9)),
            "nseg_median": float(np.median(nseg)), "share_single": float(np.mean(np.array(nseg) == 1)),
            "attached_share": float(np.mean(np.array(att) > 0)),
            "branch_angle_median_deg": float(np.degrees(np.median([x for r in rel for x in r["angle"]]))),
            "cross_per_ink_median": float(np.median([r["cross_per_ink"] for r in rel])),
            "selfcross_median": float(np.median([r["selfcross_frac"] for r in rel])),
            "fit_err_w_median": float(np.median([s["fit_err_w"] for _, pd in P[art] for s in pd["strokes"]])),
        }
    (OUT / "trainset.json").write_text(json.dumps(rows, indent=1))
    L = ["| # | artist | drawings | strokes all | hatching | long kept | fitted | long ink share | hatch ink share | long/drawing | long ink (R) | len (w) med/q90 | segs med | single | attached | branch ∠ | X/ink | self-X |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, (art, r) in enumerate(rows.items(), 1):
        L.append(f"| T{i} | {art} | {r['drawings']} | {r['n_all']} | {r['n_hatch']} | {r['n_long']} | {r['n_fitted']} | "
                 f"{r['ink_long_share']:.2f} | {r['ink_hatch_share']:.2f} | {r['long_per_drawing_median']:.0f} | "
                 f"{r['ink_long_R_median']:.1f} | {r['len_w_median']:.0f}/{r['len_w_q90']:.0f} | {r['nseg_median']:.0f} | "
                 f"{r['share_single']:.2f} | {r['attached_share']:.2f} | {r['branch_angle_median_deg']:.0f}° | "
                 f"{r['cross_per_ink_median']:.2f} | {r['selfcross_median']:.2f} |")
    (OUT / "trainset.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ---------------------------------------------------------------------------
# 3. test 1
# ---------------------------------------------------------------------------

def _feat_job(args):
    key, d = args
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _info = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W)
    return key, f


def _topo_feat_job(args):
    key, d = args
    from gesture import topology as tp
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return key, tp.topology_features(d)
        except Exception:  # noqa: BLE001 — degenerate drawing: all NaN
            return key, {}


TOPO_KEY = ("top_end_T", "top_end_L", "top_end_near", "top_end_free", "top_L_defl", "top_near_aim",
            "top_kiss_per_ink", "top_par_pairs", "top_par_ink", "top_isolated", "top_x_per_ink", "top_T_angle")


def topo_auc(tfeats: dict, real_keys, gen_keys, repeats, seed, models) -> dict:
    """Real vs generated AUC on topology features only (topology_study's
    classifier: all non-descriptive FEATURES, no medium projection)."""
    from gesture import topology as tp
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from discriminate import effect_sizes, pair_auc
    names = [k for k in tp.FEATURES if k not in tp.DESCRIPTIVE]
    keys = list(real_keys) + list(gen_keys)
    X = np.array([[tfeats[k].get(n, np.nan) if tfeats[k].get(n) is not None else np.nan for n in names]
                  for k in keys], dtype=float)
    ok = ~np.all(np.isnan(X), axis=0)
    X, names = X[:, ok], [n for n, o in zip(names, ok) if o]
    y = np.array(["real"] * len(real_keys) + ["gen"] * len(gen_keys))
    out = {mn: pair_auc(mk, X, y, "real", "gen", repeats, seed)["auc"] for mn, mk in models.items()}
    out["top_d"] = effect_sizes(X, y, names, "real", "gen", top=6)
    return out


def _module(path: str):
    """The grammar module: this one, or a baseline loaded from a file (e.g.
    an older version extracted with `git show`, imports made absolute)."""
    if not path:
        return gm
    import importlib.util
    if "grammar_baseline" in sys.modules:
        return sys.modules["grammar_baseline"]
    spec = importlib.util.spec_from_file_location("grammar_baseline", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["grammar_baseline"] = mod
    spec.loader.exec_module(mod)
    return mod


def _gen_job(args):
    mpath, gpath, size, seed, relations = args
    mod = _module(mpath)
    g = mod.Grammar.load(gpath)
    return mod.generate_drawing(g, np.random.default_rng(seed), size, relations=relations)


KEY = ("len_q10", "len_q50", "len_q90", "rel_touch_rate", "rel_near_rate", "rel_gap_log_q50",
       "rel_cross_per_len", "rel_selfcross_frac", "cl_segs_per_stroke", "cl_corner_rate")


def cmd_test1(a):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from discriminate import _models, effect_sizes, pair_auc
    P = prepared(a.sigma_w)
    OUT.mkdir(parents=True, exist_ok=True)
    lut = medium.load_media()
    items = []      # (artist, cls, key, drawing)
    variants = [(f"{a.current_name}_{rl}", "", rl) for rl in RELS]
    if a.baseline:
        variants += [(f"{a.baseline_name}_{rl}", str(Path(a.baseline).resolve()), rl) for rl in RELS]
    TS = topo_summaries()
    for art in ARTISTS:
        g = learn_artist(art, P, a.sigma_w, topo=TS)
        gpath = OUT / f"grammar_{art}.json"
        g.save(gpath)
        reals = [(stem, gm.long_drawing(d)) for stem, d in load(art)]
        reals = [(s, d) for s, d in reals if len(d.strokes) >= 2]
        items += [(art, "real", f"{art}/{s}", d) for s, d in reals]
        # v5: the identity floor in the same run (real strokes re-drawn from their own tokens)
        with ProcessPoolExecutor(JOBS) as ex:
            ids = list(ex.map(_identity_job, [(art, s, 0.0) for s, _ in reals]))
        items += [(art, "gen_floor", f"{art}/floor{i}", d) for i, d in enumerate(ids)]
        gpath_b = OUT / f"grammar_{art}_baseline.json"
        if a.baseline:       # the baseline with its own calibrated crossing gain, no v5 fields
            gb = gm.Grammar.from_json(g.to_json())
            gb.relations = {k: v for k, v in g.relations.items()
                            if k not in ("topo", "end_gain", "p_double", "corner_rate")}
            cgb = Path(a.baseline_gain) if a.baseline_gain else None
            if cgb and cgb.exists():
                gb.relations["cross_gain"] = float(json.loads(cgb.read_text()).get(art, 1.0))
            gb.save(gpath_b)
        for vname, mpath, rl in variants:
            t0 = time.time()
            gp_ = gpath_b if mpath else gpath
            with ProcessPoolExecutor(JOBS) as ex:
                gens = list(ex.map(_gen_job, [(mpath, str(gp_), d.size, a.seed * 1000 + i, rl)
                                             for i, (_s, d) in enumerate(reals)]))
            print(f"{art}/{vname}: {len(reals)} real, generated in {time.time() - t0:.0f}s; "
                  f"gen strokes med {np.median([len(d.strokes) for d in gens])}, "
                  f"real strokes med {np.median([len(d.strokes) for _, d in reals])}")
            items += [(art, f"gen_{vname}", f"{art}/gen_{vname}{i}", d) for i, d in enumerate(gens)]
    with ProcessPoolExecutor(JOBS) as ex:
        feats = dict(ex.map(_feat_job, [(k, d) for _a, _c, k, d in items], chunksize=2))
        tfeats = dict(ex.map(_topo_feat_job, [(k, d) for _a, _c, k, d in items], chunksize=2))
    keys = [k for _a, _c, k, _d in items]
    variants = [("floor", "", "")] + variants
    allk = sorted(set().union(*[feats[k] for k in keys]))
    names = [n for n in allk if all(n in feats[k] for k in keys)
             and panel.group_of(n) not in panel.WIDTH_GROUPS]
    X = np.array([[feats[k][n] for n in names] for k in keys], dtype=float)
    ok = ~np.all(np.isnan(X), axis=0)
    X, names = X[:, ok], [n for n, o in zip(names, ok) if o]
    art_lab = np.array([x[0] for x in items])
    cls = np.array([x[1] for x in items])
    med = np.array([lut.get((x[0], x[2].split("/")[1]), "unknown") if x[1] == "real" else "generated"
                    for x in items])
    pj = medium.MediumProjector(medium.load_pairs()).fit(X, art_lab, med)
    Xp = pj.transform(X)
    models = _models(a.seed)
    rep = {"sigma_w": a.sigma_w, "n_features": len(names), "artists": {}}
    for art in ARTISTS:
        rep["artists"][art] = {}
        for rl, _mp, _r in variants:
            m = (art_lab == art) & np.isin(cls, ["real", f"gen_{rl}"])
            y = np.where(cls[m] == "real", "real", "gen")
            grp = np.arange(m.sum())
            res = {}
            for tag, cols in (("geometry", list(range(len(names)))),
                              ("geometry_no_rel", [i for i, n in enumerate(names) if panel.group_of(n) != "rel"])):
                res[tag] = {mn: pair_auc(mk, Xp[m][:, cols], y, "real", "gen", a.repeats, a.seed, grp)
                            for mn, mk in models.items()}
            res["top_d"] = effect_sizes(X[m], y, names, "real", "gen", top=12)
            rk = [k for (aa, cc, k, _d) in items if aa == art and cc == "real"]
            gk = [k for (aa, cc, k, _d) in items if aa == art and cc == f"gen_{rl}"]
            res["topology"] = topo_auc(tfeats, rk, gk, a.repeats, a.seed, models)
            res["n_real"], res["n_gen"] = int((y == "real").sum()), int((y == "gen").sum())
            rep["artists"][art][rl] = res
            print(art, rl, {t: {mn: round(v["auc"], 3) for mn, v in r.items()} for t, r in res.items()
                            if t.startswith("geometry")})
    # key features: medians, real vs each variant
    rep["key"] = {}
    for art in ARTISTS:
        rep["key"][art] = {}
        for c in ["real"] + [f"gen_{v}" for v, _m, _r in variants]:
            m = (art_lab == art) & (cls == c)
            rep["key"][art][c] = {n: (float(np.nanmedian(X[m, names.index(n)])) if n in names else None)
                                  for n in KEY}
    (OUT / "test1.json").write_text(json.dumps(rep, indent=1))
    K = ["| # | artist | set | " + " | ".join(KEY) + " |", "|---|---|---|" + "---|" * len(KEY)]
    i = 0
    for art, rows in rep["key"].items():
        for c, v in rows.items():
            i += 1
            K.append(f"| F{i} | {art} | {c} | " + " | ".join("—" if v[n] is None else f"{v[n]:.3g}" for n in KEY) + " |")
    (OUT / "test1_key.md").write_text("\n".join(K) + "\n")
    print("\n".join(K))
    rep["topo_key"] = {}
    for art in ARTISTS:
        rep["topo_key"][art] = {}
        for c in ["real"] + [f"gen_{v}" for v, _m, _r in variants]:
            ck = [k for (aa, cc, k, _d) in items if aa == art and cc == c]
            rep["topo_key"][art][c] = {}
            for n in TOPO_KEY:
                v = [tfeats[k].get(n, np.nan) for k in ck]
                v = [x for x in v if x is not None and np.isfinite(x)]
                rep["topo_key"][art][c][n] = float(np.median(v)) if v else None
    (OUT / "test1.json").write_text(json.dumps(rep, indent=1))
    K = ["| # | artist | set | " + " | ".join(TOPO_KEY) + " |", "|---|---|---|" + "---|" * len(TOPO_KEY)]
    i = 0
    for art, rows in rep["topo_key"].items():
        for c, v in rows.items():
            i += 1
            K.append(f"| G{i} | {art} | {c} | " + " | ".join("—" if v[n] is None else f"{v[n]:.3g}" for n in TOPO_KEY) + " |")
    (OUT / "test1_topo_key.md").write_text("\n".join(K) + "\n")
    L = ["| # | artist | relations | n real/gen | geometry: logreg / forest AUC | no rel_: logreg / forest | topology: logreg / forest |",
         "|---|---|---|---|---|---|---|"]
    i = 0
    for art, rr in rep["artists"].items():
        for rl, r in rr.items():
            i += 1
            g1, g2 = r["geometry"], r["geometry_no_rel"]
            L.append(f"| A{i} | {art} | {rl} | {r['n_real']}/{r['n_gen']} | {g1['logreg']['auc']:.3f} ± "
                     f"{g1['logreg']['auc_std']:.3f} / {g1['forest']['auc']:.3f} | "
                     f"{g2['logreg']['auc']:.3f} / {g2['forest']['auc']:.3f} | "
                     f"{r['topology']['logreg']:.3f} / {r['topology']['forest']:.3f} |")
    L += ["", "Top separating features (Cohen's d, gen − real; medians real → gen):", ""]
    for art, rr in rep["artists"].items():
        for rl, r in rr.items():
            L.append(f"- **{art} / {rl}**: " + "; ".join(
                f"`{x['feature']}` {x['d']:+.1f} ({x['a']:.3g} → {x['b']:.3g})" for x in r["top_d"][:8]))
    (OUT / "test1.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ---------------------------------------------------------------------------
# 4. memorisation
# ---------------------------------------------------------------------------

def cmd_memo(a):
    P = prepared(a.sigma_w)
    rng = np.random.default_rng(a.seed)
    rep = {}
    for art in ARTISTS:
        pds = [pd for _, pd in P[art]]
        held = pds[::5]
        train = [pd for i, pd in enumerate(pds) if i % 5]
        g = gm.learn(prepared=train, name=art, sigma_w=a.sigma_w)
        gc = gm.learn(prepared=train, name=art + "_shuffled", sigma_w=a.sigma_w, shuffle=True, seed=a.seed)
        real = [s["tokens"] for pd in held for s in pd["strokes"]]
        Lr = [gm.stroke_length(t) for t in real]
        n = a.n
        lens = [float(rng.choice(Lr)) for _ in range(n)]    # same length mix as held-out real
        gen = [gm.generate_tokens(g, rng, length=L, p_follow=gm.P_FOLLOW)[0] for L in lens]
        gen_k = [gm.generate_tokens(g, rng, length=L, p_follow=gm.P_FOLLOW, kmatch=1.0)[0] for L in lens]
        # v5: strokes as drawn (steering, joins, end plans) by full v5 contiguous drawings
        TS = topo_summaries()
        g.relations["topo"] = gm.pool_topology([TS[art][st] for i, (st, _) in enumerate(P[art]) if i % 5])
        for k in ("cross_gain", "p_double", "end_gain"):
            f_ = OUT / {"cross_gain": "cross_gain.json", "p_double": "p_double.json", "end_gain": "end_gain.json"}[k]
            if f_.exists():
                g.relations[k] = json.loads(f_.read_text()).get(art)
        gpath = OUT / f"grammar_{art}_memo.json"
        g.save(gpath)
        with ProcessPoolExecutor(JOBS) as ex:
            dd = list(ex.map(_abl_gen_job, [(str(gpath), tuple(held[i % len(held)]["size"]), a.seed + 77 * i, {})
                                            for i in range(a.memo_drawings)]))
        drawn = [st.meta["tokens"] for d in dd for st in d.strokes]
        ctl = [gm.generate_tokens(gc, rng, length=L, p_follow=gm.P_FOLLOW)[0] for L in lens]
        tr_idx = rng.choice(len(g.strokes), n)
        quote = [gm.jitter_tokens(g, g.strokes[i], rng) for i in tr_idx]
        sets = {"generated": gen, "generated_kmatch": gen_k, "drawn_v5": drawn, "heldout_real": real,
                "shuffled_control": ctl, "jittered_training": quote}
        res = {}
        for min_seg in (2, 4):
            row = {}
            ref = None
            for nm, S in sets.items():
                S2 = [t for t in S if gm.n_segments(t) >= min_seg]
                d = gm.nearest_training_distance(S2, g)
                if nm == "heldout_real":
                    ref = d
                row[nm] = {"n": int(len(d)), "q10": float(np.quantile(d, .1)) if len(d) else None,
                           "median": float(np.median(d)) if len(d) else None, "_d": d}
            for nm in row:
                d = row[nm].pop("_d")
                row[nm]["share_below_heldout_p10"] = float(np.mean(d < np.quantile(ref, .1))) if len(d) and len(ref) else None
            res[f"nseg_ge_{min_seg}"] = row
        rep[art] = res
        print(art, json.dumps(res))
    (OUT / "memo.json").write_text(json.dumps(rep, indent=1))
    L = ["| # | artist | strokes | set | n | NN dist q10 | median | share < held-out q10 |", "|---|---|---|---|---|---|---|---|"]
    i = 0
    for art, res in rep.items():
        for k, row in res.items():
            for nm, v in row.items():
                i += 1
                L.append(f"| M{i} | {art} | {k.replace('nseg_ge_', '≥')} seg | {nm} | {v['n']} | "
                         f"{v['q10']:.3f} | {v['median']:.3f} | {v['share_below_heldout_p10']:.2f} |")
    (OUT / "memo.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ---------------------------------------------------------------------------
# 5. v4 ablations: where does the along-line texture come from?
# ---------------------------------------------------------------------------

TEXTURE = ("cl_corner_rate", "cl_segs_per_stroke", "turn_tcorr_05", "turn_tcorr_10", "turn_net_ratio",
           "ext_turn_q50", "len_q10", "len_q50", "rel_touch_rate", "rel_cross_per_len")


def _identity_job(args):
    """A real long-stroke subset re-drawn from its own σ = 2 w clothoid
    tokens (each stroke rigidly aligned onto the original), corners sharp
    or rounded over round_w line widths."""
    art, stem, round_w = args
    d = gm.long_drawing(Drawing.load(EXTRACT / art / f"{stem}.json"))
    R, fitted = gm.fit_drawing(d, select=False)
    out = []
    for st, _f, toks in fitted:
        w = gm.stroke_width(st, d)
        tk = gm.round_corners(toks, round_w * w / R)
        p, _, _ = gm.tokens_to_points(tk, R, step=max(0.5, w / 2))
        ref = gm.resample(st.points, max(0.5, w / 2))
        n = min(len(p), len(ref))
        if n < 3:
            continue
        ub = np.linspace(0, len(p) - 1, n).astype(int)
        ui = np.linspace(0, len(ref) - 1, n).astype(int)
        q = gm._kabsch(p[ub], ref[ui])(p)
        out.append(gm.Stroke(q, width=np.full(len(q), w)))
    return Drawing(out, source=d.source, size=d.size)


def _abl_gen_job(args):
    gpath, size, seed, kw = args
    g = gm.Grammar.load(gpath)
    return gm.generate_drawing(g, np.random.default_rng(seed), size, **kw)


V4 = {"ends": "v4", "kmatch": 0.0, "corner_budget": 0.0}
ABLATIONS = {
    "v4": dict(V4),                                                  # v4 behaviour inside the v5 module
    "kmatch": {**V4, "kmatch": 1.0},                                 # corners: κ-matched splices
    "budget": {**V4, "corner_budget": 1.0},                          # corners: corner-aware steering
    "budget05": {**V4, "corner_budget": 0.5},
    "look2": {**V4, "look_mult": 2.0},                               # corners: longer look-ahead
    "ends": {"kmatch": 0.0, "corner_budget": 0.0},                   # joins: topology relations layer
    "ends_smooth": {"kmatch": 0.0, "corner_budget": 0.0, "join": "smooth"},
    "v5": {},                                                        # everything (defaults)
    "v5_b05": {"corner_budget": 0.5},
    "v5_look2": {"look_mult": 2.0},
}


def cmd_ablate(a):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from discriminate import _models, effect_sizes, pair_auc
    P = prepared(a.sigma_w)
    lut = medium.load_media()
    names_sel = a.only.split(",") if a.only else None
    abl = {k: v for k, v in ABLATIONS.items() if not names_sel or k in names_sel}
    if a.extra:
        abl.update(json.loads(a.extra))
    ident = [0.0, 4.0, 8.0] if not names_sel else []
    rep = {"ablations": {k: v for k, v in abl.items()}, "identity_round_w": ident, "artists": {}}
    for art in ARTISTS:
        t0 = time.time()
        g = learn_artist(art, P, a.sigma_w)
        gpath = OUT / f"grammar_{art}_abl.json"
        g.save(gpath)
        stems = [stem for stem, _ in P[art]]
        if a.max_real:
            stems = stems[:a.max_real]
        reals = [(st, gm.long_drawing(Drawing.load(EXTRACT / art / f"{st}.json"))) for st in stems]
        reals = [(st, d) for st, d in reals if len(d.strokes) >= 2]
        items = [("real", f"real/{st}", d, st) for st, d in reals]
        with ProcessPoolExecutor(JOBS) as ex:
            for rw in ident:
                ds = list(ex.map(_identity_job, [(art, st, rw) for st, _ in reals]))
                items += [(f"identity_r{rw:g}", f"id{rw:g}/{i}", d, None) for i, d in enumerate(ds)]
            for nm, kw in abl.items():
                ds = list(ex.map(_abl_gen_job, [(str(gpath), d.size, a.seed * 1000 + i, kw)
                                               for i, (_s, d) in enumerate(reals)]))
                items += [(nm, f"{nm}/{i}", d, None) for i, d in enumerate(ds)]
            feats = dict(ex.map(_feat_job, [(k, d) for _c, k, d, _s in items], chunksize=2))
            tfeats = dict(ex.map(_topo_feat_job, [(k, d) for _c, k, d, _s in items], chunksize=2))
        keys = [k for _c, k, _d, _s in items]
        allk = sorted(set().union(*[feats[k] for k in keys]))
        names = [n for n in allk if all(n in feats[k] for k in keys) and panel.group_of(n) not in panel.WIDTH_GROUPS]
        X = np.array([[feats[k][n] for n in names] for k in keys], dtype=float)
        okc = ~np.all(np.isnan(X), axis=0)
        X, names = X[:, okc], [n for n, o in zip(names, okc) if o]
        cls = np.array([c for c, _k, _d, _s in items])
        med = np.array([lut.get((art, st), "unknown") if c == "real" else "generated" for c, _k, _d, st in items])
        artl = np.array([art] * len(items))
        models = _models(a.seed)
        res = {}
        stats = {}
        for c in dict.fromkeys(cls.tolist()):
            m = cls == c
            row = {n: float(np.nanmedian(X[m, names.index(n)])) for n in TEXTURE if n in names}
            ck = [k for (cc, k, _d, _s) in items if cc == c]
            for n in TOPO_KEY:
                v = [tfeats[k].get(n, np.nan) for k in ck]
                v = [x for x in v if x is not None and np.isfinite(x)]
                row[n] = float(np.median(v)) if v else None
            if c != "real":
                rk = [k for (cc, k, _d, _s) in items if cc == "real"]
                ta = topo_auc(tfeats, rk, ck, a.repeats, a.seed, models)
                row["auc_topo"], row["auc_topo_forest"], row["top_d_topo"] = ta["logreg"], ta["forest"], ta["top_d"]
                mm = np.isin(cls, ["real", c])
                pj = medium.MediumProjector(medium.load_pairs()).fit(X[mm], artl[mm], med[mm])
                Xp = pj.transform(X[mm])
                y = np.where(cls[mm] == "real", "real", "gen")
                grp = np.arange(mm.sum())
                norel = [i for i, n in enumerate(names) if panel.group_of(n) != "rel"]
                row["auc"] = pair_auc(models["logreg"], Xp, y, "real", "gen", a.repeats, a.seed, grp)["auc"]
                row["auc_forest"] = pair_auc(models["forest"], Xp, y, "real", "gen", a.repeats, a.seed, grp)["auc"]
                row["auc_norel"] = pair_auc(models["logreg"], Xp[:, norel], y, "real", "gen", a.repeats, a.seed, grp)["auc"]
                row["top_d"] = effect_sizes(X[mm], y, names, "real", "gen", top=6)
                gs = [d.meta.get("grow_stats") for cc, _k, d, _s in items if cc == c and d.meta.get("grow_stats")]
                if gs:
                    tot = {k: sum(x[k] for x in gs) for k in gs[0]}
                    stats[c] = {"steered_share": tot["steered"] / max(tot["steps"], 1),
                                "corner_share_chosen": tot["corners"] / max(tot["steps"], 1),
                                "corner_share_first_proposal": tot["corners_proposed_first"] / max(tot["steps"], 1),
                                "followed_share": tot["followed"] / max(tot["steps"], 1),
                                "past_share": tot.get("past_steps", 0) / max(tot["steps"], 1)}
                    row.update(stats[c])
            res[c] = row
        rep["artists"][art] = res
        print(f"[{time.time() - t0:.0f}s] {art}")
        for c, r in res.items():
            print(f"  {c:16s} " + " ".join(f"{k}={v:.3g}" for k, v in r.items() if isinstance(v, float)))
    tag = a.tag or "ablate"
    (OUT / f"{tag}.json").write_text(json.dumps(rep, indent=1))
    cols = ["cl_corner_rate", "turn_tcorr_10", "turn_net_ratio", "ext_turn_q50", "len_q10", "rel_touch_rate",
            "rel_cross_per_len", "auc", "auc_forest", "auc_norel", "auc_topo", "auc_topo_forest",
            "steered_share", "corner_share_chosen", "followed_share"] + [k for k in TOPO_KEY]
    L = ["| # | artist | set | " + " | ".join(cols) + " |", "|---|---|---|" + "---|" * len(cols)]
    i = 0
    for art, res in rep["artists"].items():
        for c, r in res.items():
            i += 1
            L.append(f"| B{i} | {art} | {c} | " + " | ".join(
                ("—" if r.get(k) is None else f"{r[k]:.3g}") for k in cols) + " |")
    (OUT / f"{tag}.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["scale", "prepare", "calibrate", "test1", "memo", "ablate"])
    ap.add_argument("--sigma-w", type=float, default=gm.SIGMA_W)
    ap.add_argument("--n", type=int, default=150, help="scale: strokes per artist; memo: strokes per set")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--baseline", default="", help="test1: also evaluate a grammar module file (older version)")
    ap.add_argument("--baseline-name", default="v4")
    ap.add_argument("--baseline-gain", default=str(ROOT / ".local/gesture/out/grammar_v2/cross_gain.json"),
                    help="test1: crossing gains JSON for the baseline")
    ap.add_argument("--current-name", default="v5", help="test1: label of this module's variants")
    ap.add_argument("--only", default="", help="ablate: comma list of ablation names (skips identity)")
    ap.add_argument("--extra", default="", help='ablate: JSON {name: generate_drawing kwargs}')
    ap.add_argument("--tag", default="", help="ablate: output name")
    ap.add_argument("--calib-n", type=int, default=15, help="calibrate: drawings per round")
    ap.add_argument("--max-real", type=int, default=0, help="ablate: at most this many real drawings per artist")
    ap.add_argument("--memo-drawings", type=int, default=9, help="memo: v5 drawings whose strokes are checked")
    ap.add_argument("--calib-rounds", type=int, default=4)
    a = ap.parse_args(argv)
    {"scale": cmd_scale, "prepare": cmd_prepare, "calibrate": cmd_calibrate, "test1": cmd_test1,
     "memo": cmd_memo, "ablate": cmd_ablate}[a.cmd](a)


if __name__ == "__main__":
    main()
