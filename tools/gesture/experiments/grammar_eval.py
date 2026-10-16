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
OUT = ROOT / ".local/gesture/out/grammar_v2"
ARTISTS = ("matisse", "hokusai", "ingres")
JOBS = max(1, min(10, (os.cpu_count() or 2) - 2))
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
    p = OUT / "prepared" / f"v3-sw{sigma_w:g}" / art / f"{stem}.json"
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


def learn_artist(art, P, sigma_w=gm.SIGMA_W, **kw):
    """Learn an artist's grammar, with the crossing gain from `calibrate` if present."""
    g = gm.learn(prepared=[pd for _, pd in P[art]], name=art, sigma_w=sigma_w, **kw)
    cg = OUT / "cross_gain.json"
    if cg.exists():
        g.relations["cross_gain"] = float(json.loads(cg.read_text()).get(art, 1.0))
    return g


def _calib_job(args):
    gpath, size, seed, gain = args
    g = gm.Grammar.load(gpath)
    d = gm.generate_drawing(g, np.random.default_rng(seed), size, cross_gain=gain)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _ = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W, clothoid=False)
    return f.get("rel_cross_per_len", np.nan)


def cmd_calibrate(a):
    """Tune each hand's crossing gain so generated drawings cross at the real
    long-stroke subsets' median rate (panel rel_cross_per_len)."""
    P = prepared(a.sigma_w)
    gains = {}
    for art in ARTISTS:
        g = gm.learn(prepared=[pd for _, pd in P[art]], name=art, sigma_w=a.sigma_w)
        gpath = OUT / f"grammar_{art}_calib.json"
        g.save(gpath)
        target = float(np.median([pd["relations"]["cross_per_ink"] for _, pd in P[art]
                                  if pd["relations"]["n"] >= 2]))
        sizes = [tuple(pd["size"]) for _, pd in P[art]][:12]
        gain = 1.0
        for it in range(3):
            with ProcessPoolExecutor(JOBS) as ex:
                v = list(ex.map(_calib_job, [(str(gpath), sz, 500 + i, gain) for i, sz in enumerate(sizes)]))
            got = float(np.nanmedian(v))
            print(f"{art} it{it}: gain {gain:.2f} → crossings/len {got:.3f} (real median {target:.3f})")
            if got <= 0:
                gain *= 2
            else:
                gain *= float(np.clip(target / got, 0.33, 3.0))
        gains[art] = round(gain, 3)
    (OUT / "cross_gain.json").write_text(json.dumps(gains, indent=1))
    print(gains)


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
    variants = [(f"v3_{rl}", "", rl) for rl in RELS]
    if a.baseline:
        variants += [(f"{a.baseline_name}_{rl}", str(Path(a.baseline).resolve()), rl) for rl in RELS]
    for art in ARTISTS:
        g = learn_artist(art, P, a.sigma_w)
        gpath = OUT / f"grammar_{art}.json"
        g.save(gpath)
        reals = [(stem, gm.long_drawing(d)) for stem, d in load(art)]
        reals = [(s, d) for s, d in reals if len(d.strokes) >= 2]
        items += [(art, "real", f"{art}/{s}", d) for s, d in reals]
        for vname, mpath, rl in variants:
            t0 = time.time()
            with ProcessPoolExecutor(JOBS) as ex:
                gens = list(ex.map(_gen_job, [(mpath, str(gpath), d.size, a.seed * 1000 + i, rl)
                                             for i, (_s, d) in enumerate(reals)]))
            print(f"{art}/{vname}: {len(reals)} real, generated in {time.time() - t0:.0f}s; "
                  f"gen strokes med {np.median([len(d.strokes) for d in gens])}, "
                  f"real strokes med {np.median([len(d.strokes) for _, d in reals])}")
            items += [(art, f"gen_{vname}", f"{art}/gen_{vname}{i}", d) for i, d in enumerate(gens)]
    with ProcessPoolExecutor(JOBS) as ex:
        feats = dict(ex.map(_feat_job, [(k, d) for _a, _c, k, d in items], chunksize=2))
    keys = [k for _a, _c, k, _d in items]
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
    L = ["| # | artist | relations | n real/gen | geometry: logreg / forest AUC | no rel_: logreg / forest |",
         "|---|---|---|---|---|---|"]
    i = 0
    for art, rr in rep["artists"].items():
        for rl, r in rr.items():
            i += 1
            g1, g2 = r["geometry"], r["geometry_no_rel"]
            L.append(f"| A{i} | {art} | {rl} | {r['n_real']}/{r['n_gen']} | {g1['logreg']['auc']:.3f} ± "
                     f"{g1['logreg']['auc_std']:.3f} / {g1['forest']['auc']:.3f} | "
                     f"{g2['logreg']['auc']:.3f} / {g2['forest']['auc']:.3f} |")
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
        gen = [gm.generate_tokens(g, rng, length=L)[0] for L in lens]
        ctl = [gm.generate_tokens(gc, rng, length=L)[0] for L in lens]
        tr_idx = rng.choice(len(g.strokes), n)
        quote = [gm.jitter_tokens(g, g.strokes[i], rng) for i in tr_idx]
        sets = {"generated": gen, "heldout_real": real, "shuffled_control": ctl, "jittered_training": quote}
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["scale", "prepare", "calibrate", "test1", "memo"])
    ap.add_argument("--sigma-w", type=float, default=gm.SIGMA_W)
    ap.add_argument("--n", type=int, default=150, help="scale: strokes per artist; memo: strokes per set")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--baseline", default="", help="test1: also evaluate a grammar module file (older version)")
    ap.add_argument("--baseline-name", default="v2")
    a = ap.parse_args(argv)
    {"scale": cmd_scale, "prepare": cmd_prepare, "calibrate": cmd_calibrate, "test1": cmd_test1,
     "memo": cmd_memo}[a.cmd](a)


if __name__ == "__main__":
    main()
