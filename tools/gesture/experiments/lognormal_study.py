"""Sigma-lognormal kinematic hand: study (results/lognormal-2026-10-16.md).

Subcommands (run from the repo root):

  synth   recovery on synthetic strokes from known pulses: timed fit (true
          timing) and static fit (geometry only, power-law timing)
  fit     fit every long stroke of every drawing (cached per drawing in
          .local/gesture/out/lognormal/fits/), fit-quality + signature tables
  test1   stage-3 test 1: real long-stroke subsets vs lognormal-generated vs
          grammar v3 (frozen) vs lognormal-reconstructed real, panel features
          with standard preprocessing, grouped-CV AUC, texture features
  memo    memorisation: generated vs held-out real vs shuffled-pulse control
          vs jittered training copies (polyline turning signature)
  sheets  per artist: 6 lognormal drawings, 3 single lines, 2 v3, 1 real

    .local/gesture/.venv/bin/python -m tools.gesture.experiments.lognormal_study fit
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gesture import grammar_v3_frozen as g3  # noqa: E402
from gesture import lognormal as ln  # noqa: E402
from gesture import medium, panel  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
EXTRACT = ROOT / ".local/gesture/out/extract_hybrid"
OUT = ROOT / ".local/gesture/out/lognormal"
V3G = OUT / "v3_grammars"        # frozen copies of .local/gesture/out/grammar_v2/grammar_{art}.json
RESULTS = Path(__file__).resolve().parents[1] / "results"
ARTISTS = ("matisse", "hokusai", "ingres")
MAX_FIT = 12          # long strokes fitted per drawing (random subset; CPU budget)
JOBS = int(os.environ.get("LN_JOBS", max(1, min(8, (os.cpu_count() or 2) - 4))))
TEXTURE = ("cl_corner_rate", "cl_segs_per_stroke", "turn_tcorr_05", "turn_tcorr_10", "turn_net_ratio",
           "turn_abs", "ext_rate", "ext_turn_q50", "ext_h_q50", "ext_w_q50", "infl_rate",
           "len_q10", "len_q50", "rel_touch_rate", "rel_cross_per_len")


def load(artist: str) -> list[tuple[str, Drawing]]:
    return [(p.stem, Drawing.load(p)) for p in sorted((EXTRACT / artist).glob("*.json"))]


# ---------------------------------------------------------------------------
# synth: recovery
# ---------------------------------------------------------------------------

def _match(Pt, Pf):
    """Match fitted to true pulses by peak time (Hungarian)."""
    from scipy.optimize import linear_sum_assignment
    tp = lambda P: P[:, 0] + np.exp(P[:, 1] - P[:, 2] ** 2)  # noqa: E731
    C = np.abs(tp(Pt)[:, None] - tp(Pf)[None, :])
    i, j = linear_sum_assignment(C)
    return i, j


def _synth_job(args):
    n, seed = args
    rng = np.random.default_rng(seed)
    P = ln.random_pulses(rng, n)
    t = ln.time_grid(P, 0.5)
    x = ln.trajectory(P, t)
    tu = np.linspace(t[0], t[-1], 400)
    xu = np.column_stack([np.interp(tu, t, x[:, 0]), np.interp(tu, t, x[:, 1])])
    out = {"n": n}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        Pf, info = ln.fit_velocity(tu, xu)
        i, j = _match(P, Pf)
        out["timed"] = {"n": len(Pf), "snr": info["snr_v"],
                        "D_rel_err": float(np.median(np.abs(Pf[j, 3] / P[i, 3] - 1))),
                        "dth_err": float(np.median(np.abs((Pf[j, 5] - Pf[j, 4]) - (P[i, 5] - P[i, 4])))),
                        "sig_err": float(np.median(np.abs(Pf[j, 2] - P[i, 2])))}
        pts = ln.synthesize(P, 0.5)
        L = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
        f = ln.fit_stroke(pts, sigma=1.0, R=4 * L)
        i, j = _match(P, f.pulses)
        out["static"] = {"n": f.n, "snr": f.snr_v, "err_rel": f.err_mean / f.length,
                         "D_rel_err": float(np.median(np.abs(f.pulses[j, 3] / P[i, 3] - 1))),
                         "dth_err": float(np.median(np.abs((f.pulses[j, 5] - f.pulses[j, 4]) - (P[i, 5] - P[i, 4]))))}
    return out


def cmd_synth(a):
    jobs = [(n, 1000 * n + s) for n in (1, 2, 4, 8) for s in range(a.n)]
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_synth_job, jobs))
    L = ["| # | true pulses | mode | fitted n (median) | exact n | within ±1 | SNR dB | D rel err | Δθ err (rad) | shape err ÷ L |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    i = 0
    rep = {}
    for n in (1, 2, 4, 8):
        for mode in ("timed", "static"):
            R = [r[mode] for r in res if r["n"] == n]
            nn = np.array([r["n"] for r in R])
            i += 1
            row = {"n_med": float(np.median(nn)), "exact": float(np.mean(nn == n)),
                   "pm1": float(np.mean(np.abs(nn - n) <= 1)), "snr": float(np.median([r["snr"] for r in R])),
                   "D": float(np.median([r["D_rel_err"] for r in R])),
                   "dth": float(np.median([r["dth_err"] for r in R])),
                   "err": float(np.median([r.get("err_rel", np.nan) for r in R]))}
            rep[f"{n}_{mode}"] = row
            L.append(f"| S{i} | {n} | {mode} | {row['n_med']:.0f} | {row['exact']:.2f} | {row['pm1']:.2f} | "
                     f"{row['snr']:.1f} | {row['D']:.2f} | {row['dth']:.2f} | "
                     + ("—" if mode == "timed" else f"{row['err']:.4f}") + " |")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "synth.json").write_text(json.dumps(rep, indent=1))
    (OUT / "synth.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ---------------------------------------------------------------------------
# fit: cache + quality + signatures
# ---------------------------------------------------------------------------

def _fit_job(args):
    art, stem = args
    p = OUT / "fits" / art / f"{stem}.json"
    if p.exists():
        return art, stem, json.loads(p.read_text())
    d = Drawing.load(EXTRACT / art / f"{stem}.json")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fd = ln.fit_drawing(d, max_strokes=MAX_FIT, seed=0)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fd))
    return art, stem, fd


def fits() -> dict[str, list[tuple[str, dict]]]:
    jobs = [(art, p.stem) for art in ARTISTS for p in sorted((EXTRACT / art).glob("*.json"))]
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_fit_job, jobs, chunksize=1))
    out = {a: [] for a in ARTISTS}
    for art, stem, fd in res:
        out[art].append((stem, fd))
    return out


def hand(art, F, **kw) -> ln.Hand:
    return ln.learn([fd for _, fd in F[art]], name=art, **kw)


SIG_KEYS = ("n_strokes", "pulses_per_100w", "pulses_per_R", "pulses_per_stroke_q50", "D_over_R_q50",
            "abs_dth_q50", "abs_dth_q90", "dth_pos_share", "sigma_q50", "onset_dt_q50", "overlap_share",
            "abs_jump_q50", "lT_sd", "snr_q10", "snr_q50", "err_w_q50", "err_w_q90", "err_rel_q50")


def cmd_fit(a):
    t0 = time.time()
    F = fits()
    print(f"fitted in {time.time() - t0:.0f}s")
    rep = {art: ln.signature([fd for _, fd in F[art]]) for art in ARTISTS}
    # per-drawing signatures → do they separate artists? (interpretability check)
    per = {art: [ln.signature([fd]) for _, fd in F[art] if fd["strokes"]] for art in ARTISTS}
    rep["_per_drawing_iqr"] = {art: {k: [float(np.quantile([s[k] for s in per[art]], q)) for q in (.25, .75)]
                                     for k in ("pulses_per_100w", "abs_dth_q50", "onset_dt_q50", "sigma_q50",
                                               "abs_jump_q50")} for art in ARTISTS}
    # pulse count vs SNR target sensitivity on a sample
    (OUT / "signature.json").write_text(json.dumps(rep, indent=1))
    L = ["| # | descriptor | " + " | ".join(ARTISTS) + " |", "|---|---|" + "---|" * len(ARTISTS)]
    for i, k in enumerate(SIG_KEYS, 1):
        L.append(f"| K{i} | {k} | " + " | ".join(f"{rep[art][k]:.3g}" for art in ARTISTS) + " |")
    L += ["", "Per-drawing IQR:", ""]
    for k in ("pulses_per_100w", "abs_dth_q50", "onset_dt_q50", "sigma_q50", "abs_jump_q50"):
        L.append(f"- `{k}`: " + "; ".join(
            f"{art} {rep['_per_drawing_iqr'][art][k][0]:.3g}–{rep['_per_drawing_iqr'][art][k][1]:.3g}" for art in ARTISTS))
    (OUT / "signature.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    for art in ARTISTS:
        hand(art, F).save(OUT / f"hand_{art}.json")


# ---------------------------------------------------------------------------
# test 1
# ---------------------------------------------------------------------------

def _feat_job(args):
    key, d = args
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _info = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W)
    return key, f


def _gen_ln(args):
    hpath, size, seed, mode = args
    h = ln.Hand.load(hpath)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ln.generate_drawing(h, np.random.default_rng(seed), size, mode=mode)


def _gen_v3(args):
    gpath, size, seed, mode = args
    g = g3.Grammar.load(gpath)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return g3.generate_drawing(g, np.random.default_rng(seed), size, mode=mode, relations="learned")


def _recon(fd: dict, d: Drawing) -> Drawing:
    """Real long strokes replaced by their lognormal fits (synthesised from
    the fitted pulses over the fitted window, placed at the real start)."""
    out = []
    for s in fd["strokes"]:
        P = np.asarray(s["pulses"])
        pts = None
        # synthesise only over the target's time window: integrate from the first point
        t_hi = ln.support(P)[:, 1].max()
        t = ln.time_grid(P, 0.5 * s["w"], min(0.0, ln.support(P)[:, 0].min()), t_hi)
        x = ln.trajectory(P, t)
        pts = ln._uniform(x, 0.5 * s["w"])
        out.append(Stroke(pts, width=np.full(len(pts), s["w"])))
    # align each reconstruction to its real stroke by start point
    long = g3.long_drawing(d)
    allp = np.vstack([q.points for q in long.strokes]) if long.strokes else np.zeros((1, 2))
    lo, span = allp.min(axis=0), np.maximum(np.ptp(allp, axis=0), 1e-9)
    res = []
    for s, st in zip(fd["strokes"], out):
        p0 = lo + np.asarray(s["start"]) * span
        res.append(Stroke(st.points - st.points[0] + p0, width=st.width))
    return Drawing(res, source=d.source + ":recon", size=d.size)


def _recon_job(args):
    """(lognormal reconstruction of the fitted strokes, the same real strokes)."""
    art, stem = args
    fd = json.loads((OUT / "fits" / art / f"{stem}.json").read_text())
    fd["strokes"] = [s for s in fd["strokes"]          # degenerate fits (a T → 0 pulse) dropped
                     if np.all(np.isfinite(ln.pulses_to_rows(np.asarray(s["pulses"]), fd["R"])))]
    d = Drawing.load(EXTRACT / art / f"{stem}.json")
    long = g3.long_drawing(d)
    real = Drawing([long.strokes[s["idx"]] for s in fd["strokes"]], source=d.source, size=d.size)
    return _recon(fd, d), real


def cmd_test1(a):
    from discriminate import _models, effect_sizes, pair_auc
    F = fits()
    lut = medium.load_media()
    items = []
    for art in ARTISTS:
        hp = OUT / f"hand_{art}.json"
        if not hp.exists():
            hand(art, F).save(hp)
        reals = [(stem, g3.long_drawing(d)) for stem, d in load(art)]
        reals = [(s, d) for s, d in reals if len(d.strokes) >= 2]
        items += [(art, "real", f"{art}/{s}", d) for s, d in reals]
        variants = [("lognormal", _gen_ln, str(hp)), ("v3", _gen_v3, str(V3G / f"grammar_{art}.json"))]
        for vname, fn, path in variants:
            t0 = time.time()
            with ProcessPoolExecutor(JOBS) as ex:
                gens = list(ex.map(fn, [(path, d.size, a.seed * 1000 + i, "contiguous")
                                        for i, (_s, d) in enumerate(reals)]))
            print(f"{art}/{vname}: {len(gens)} in {time.time() - t0:.0f}s; strokes med "
                  f"{np.median([len(g.strokes) for g in gens])} (real {np.median([len(d.strokes) for _, d in reals])})")
            items += [(art, f"gen_{vname}", f"{art}/{vname}{i}", g) for i, g in enumerate(gens)]
            for i, g in enumerate(gens[:4]):
                g.save(OUT / "test1_gen" / art / f"{vname}{i}.json")
        with ProcessPoolExecutor(JOBS) as ex:
            recs = list(ex.map(_recon_job, [(art, s) for s, _d in reals]))
        for i, (g, r) in enumerate(recs):
            if len(g.strokes) >= 2:
                items += [(art, "gen_recon", f"{art}/recon{i}", g), (art, "real_fit", f"{art}/{reals[i][0]}#fit", r)]
    with ProcessPoolExecutor(JOBS) as ex:
        feats = dict(ex.map(_feat_job, [(k, d) for _a, _c, k, d in items], chunksize=2))
    keys = [k for _a, _c, k, _d in items]
    allk = sorted(set().union(*[feats[k] for k in keys]))
    names = [n for n in allk if all(n in feats[k] for k in keys) and panel.group_of(n) not in panel.WIDTH_GROUPS]
    X = np.array([[feats[k][n] for n in names] for k in keys], dtype=float)
    ok = ~np.all(np.isnan(X), axis=0)
    X, names = X[:, ok], [n for n, o in zip(names, ok) if o]
    art_lab = np.array([x[0] for x in items])
    cls = np.array([x[1] for x in items])
    med = np.array([lut.get((x[0], x[2].split("/")[1].split("#")[0]), "unknown") if x[1].startswith("real") else "generated"
                    for x in items])
    pj = medium.MediumProjector(medium.load_pairs()).fit(X, art_lab, med)
    Xp = pj.transform(X)
    models = _models(a.seed)
    variants = ("lognormal", "v3", "recon")
    rep = {"n_features": len(names), "artists": {}, "texture": {}}
    for art in ARTISTS:
        rep["artists"][art] = {}
        for v in variants:
            rc = "real_fit" if v == "recon" else "real"
            m = (art_lab == art) & np.isin(cls, [rc, f"gen_{v}"])
            y = np.where(cls[m] == rc, "real", "gen")
            grp = np.arange(m.sum())
            res = {}
            for tag, cols in (("geometry", list(range(len(names)))),
                              ("geometry_no_rel", [i for i, n in enumerate(names) if panel.group_of(n) != "rel"]),
                              ("texture_only", [i for i, n in enumerate(names) if n in TEXTURE
                                                and panel.group_of(n) not in ("rel", "len")])):
                res[tag] = {mn: pair_auc(mk, Xp[m][:, cols], y, "real", "gen", a.repeats, a.seed, grp)
                            for mn, mk in models.items()}
            res["top_d"] = effect_sizes(X[m], y, names, "real", "gen", top=10)
            res["n_real"], res["n_gen"] = int((y == "real").sum()), int((y == "gen").sum())
            rep["artists"][art][v] = res
            print(art, v, {t: {mn: round(r2["auc"], 3) for mn, r2 in r.items()} for t, r in res.items()
                           if t.startswith(("geometry", "texture"))})
        rep["texture"][art] = {}
        for c in ["real"] + [f"gen_{v}" for v in variants] + ["real_fit"]:
            m = (art_lab == art) & (cls == c)
            rep["texture"][art][c] = {n: (float(np.nanmedian(X[m, names.index(n)])) if n in names else None)
                                      for n in TEXTURE}
    (OUT / "test1.json").write_text(json.dumps(rep, indent=1))
    L = ["| # | artist | generator | n real/gen | geometry: logreg / forest | no rel_: logreg / forest | texture only: logreg / forest |",
         "|---|---|---|---|---|---|---|"]
    i = 0
    for art, rr in rep["artists"].items():
        for v, r in rr.items():
            i += 1
            g1, g2, g4 = r["geometry"], r["geometry_no_rel"], r["texture_only"]
            L.append(f"| A{i} | {art} | {v} | {r['n_real']}/{r['n_gen']} | {g1['logreg']['auc']:.3f} / {g1['forest']['auc']:.3f} | "
                     f"{g2['logreg']['auc']:.3f} / {g2['forest']['auc']:.3f} | {g4['logreg']['auc']:.3f} / {g4['forest']['auc']:.3f} |")
    L += ["", "| # | artist | set | " + " | ".join(TEXTURE) + " |", "|---|---|---|" + "---|" * len(TEXTURE)]
    i = 0
    for art, rows in rep["texture"].items():
        for c, v in rows.items():
            i += 1
            L.append(f"| T{i} | {art} | {c} | " + " | ".join("—" if v[n] is None else f"{v[n]:.3g}" for n in TEXTURE) + " |")
    L += ["", "Top separating features (Cohen's d, gen − real; medians real → gen):", ""]
    for art, rr in rep["artists"].items():
        for v, r in rr.items():
            L.append(f"- **{art} / {v}**: " + "; ".join(
                f"`{x['feature']}` {x['d']:+.1f} ({x['a']:.3g} → {x['b']:.3g})" for x in r["top_d"][:6]))
    (OUT / "test1.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ---------------------------------------------------------------------------
# memorisation
# ---------------------------------------------------------------------------

def _sigs(strokes_R_sigma):
    return [ln.turning_signature(p, R, sg) for p, R, sg in strokes_R_sigma]


def _memo_gen(args):
    hjson, seed, lengths, R = args
    h = ln.Hand.from_json(hjson)
    rng = np.random.default_rng(seed)
    out = []
    for L in lengths:
        st = ln.generate_stroke(h, rng, length=L, R=R, step=2.0 / R)
        out.append(st.points)
    return out


def cmd_memo(a):
    F = fits()
    rng = np.random.default_rng(a.seed)
    rep = {}
    R0 = 4000.0          # generation scale (px) for free strokes; signatures are scale-free
    for art in ARTISTS:
        fds = [fd for _, fd in F[art]]
        held = fds[::5]
        train = [fd for i, fd in enumerate(fds) if i % 5]
        h = ln.learn(train, name=art)
        hc = ln.learn(train, name=art + "_shuffled", shuffle=True, seed=a.seed)

        def real_set(fdl):
            S = []
            for fd in fdl:
                for s in fd["strokes"]:
                    P = np.asarray(s["pulses"])
                    if np.all(np.isfinite(ln.pulses_to_rows(P, fd["R"]))):
                        S.append((P, fd["R"], s["w"]))
            return S

        def recon_sig(S):
            out = []
            for P, R, w in S:
                pts = ln.synthesize(P, 0.5 * w)
                out.append(ln.turning_signature(pts, R, 2 * w))
            return out
        # training and held-out strokes as their (smooth) lognormal reconstructions,
        # so every set shares the representation's smoothing
        tr = real_set(train)
        ho = real_set(held)
        T = recon_sig(tr)
        Hs = recon_sig(ho)
        lens = [float(np.exp(rng.normal(0, 0)) * s["length"]) for fd in held for s in fd["strokes"]]
        n = a.n
        lens = list(rng.choice(lens, n))          # same length mix as held-out real
        chunks = [lens[i::JOBS] for i in range(JOBS)]
        with ProcessPoolExecutor(JOBS) as ex:
            gen = [p for part in ex.map(_memo_gen, [(h.to_json(), a.seed + k, c, R0) for k, c in enumerate(chunks)])
                   for p in part]
            ctl = [p for part in ex.map(_memo_gen, [(hc.to_json(), a.seed + 50 + k, c, R0) for k, c in enumerate(chunks)])
                   for p in part]
        w0 = float(np.median([w for _P, _R, w in tr]))
        R_med = float(np.median([R for _P, R, _w in tr]))
        sg = 2 * w0 * R0 / R_med
        G = [ln.turning_signature(p, R0, sg) for p in gen]
        C = [ln.turning_signature(p, R0, sg) for p in ctl]
        # quote floor: training strokes with pulse jitter, re-synthesised
        Q = []
        for k in rng.choice(len(tr), n):
            P, R, w = tr[k]
            P2 = P.copy()
            P2[:, 3] *= np.exp(rng.normal(0, 0.08, len(P)))
            P2[:, 5] += rng.normal(0, 0.05, len(P))
            Q.append(ln.turning_signature(ln.synthesize(P2, 0.5 * w), R, 2 * w))
        sets = {"generated": G, "heldout_real": Hs, "shuffled_control": C, "jittered_training": Q}
        dref = ln.nearest_distance(Hs, T)
        row = {}
        for nm, S in sets.items():
            d = ln.nearest_distance(S, T)
            row[nm] = {"n": int(len(d)), "q10": float(np.quantile(d, .1)), "median": float(np.median(d)),
                       "share_below_heldout_p10": float(np.mean(d < np.quantile(dref, .1)))}
        rep[art] = row
        print(art, json.dumps(row))
    (OUT / "memo.json").write_text(json.dumps(rep, indent=1))
    L = ["| # | artist | set | n | NN dist q10 | median | share < held-out q10 |", "|---|---|---|---|---|---|---|"]
    i = 0
    for art, row in rep.items():
        for nm, v in row.items():
            i += 1
            L.append(f"| M{i} | {art} | {nm} | {v['n']} | {v['q10']:.3f} | {v['median']:.3f} | "
                     f"{v['share_below_heldout_p10']:.2f} |")
    (OUT / "memo.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ---------------------------------------------------------------------------
# sheets
# ---------------------------------------------------------------------------

def _render_job(args):
    from gesture import synth
    d, px = args
    W, H = d.size
    sc = px / max(W, H)
    dd = Drawing([Stroke(s.points * sc, width=None if s.width is None else np.maximum(s.width * sc, 1.2))
                  for s in d.strokes], size=(max(int(W * sc), 1), max(int(H * sc), 1)))
    return synth.render(dd, line_width=1.6, paper_noise=0.0, blur_sigma=0.4)


def cmd_sheets(a):
    from PIL import Image, ImageDraw
    F = fits()
    out = OUT / "sheets"
    out.mkdir(parents=True, exist_ok=True)
    for art in ARTISTS:
        hp = OUT / f"hand_{art}.json"
        if not hp.exists():
            hand(art, F).save(hp)
        reals = [(s, g3.long_drawing(d)) for s, d in load(art)]
        reals = [(s, d) for s, d in reals if len(d.strokes) >= 4]
        size = (1400, 1000)
        jobs = [(_gen_ln, (str(hp), size, a.seed + i, "contiguous"), f"lognormal {i + 1}") for i in range(6)]
        jobs += [(_gen_ln, (str(hp), size, a.seed + 100 + i, "single"), f"lognormal single {i + 1}") for i in range(3)]
        jobs += [(_gen_v3, (str(V3G / f"grammar_{art}.json"), size, a.seed + i, "contiguous"), f"v3 clothoid {i + 1}")
                 for i in range(2)]
        t0 = time.time()
        with ProcessPoolExecutor(JOBS) as ex:
            futs = [ex.submit(fn, arg) for fn, arg, _l in jobs]
            draws = [f.result() for f in futs]
        print(f"{art}: generated {len(draws)} in {time.time() - t0:.0f}s; ink "
              + ", ".join(f"{d.meta.get('ink', d.meta.get('length_R', 0)):.1f}/{d.meta.get('ink_budget', 0):.1f}"
                          for d in draws))
        labels = [l for _f, _a, l in jobs]
        rs, rd = reals[int(np.random.default_rng(a.seed).integers(len(reals)))]
        draws.append(rd)
        labels.append(f"real long strokes {rs}")
        for d, l in zip(draws, labels):
            d.save(out / art / (l.replace(" ", "_") + ".json"))
        with ProcessPoolExecutor(JOBS) as ex:
            imgs = list(ex.map(_render_job, [(d, 400) for d in draws]))
        cw, ch, pad, lab = 400, 300, 10, 22
        sheet = Image.new("L", (4 * (cw + pad) + pad, 3 * (ch + pad + lab) + pad), 255)
        dr = ImageDraw.Draw(sheet)
        for k, (im, l) in enumerate(zip(imgs, labels)):
            r, c = divmod(k, 4)
            x0, y0 = pad + c * (cw + pad), pad + r * (ch + pad + lab)
            img = Image.fromarray(im)
            img.thumbnail((cw, ch))
            sheet.paste(img, (x0, y0 + lab))
            dr.rectangle([x0, y0 + lab, x0 + cw - 1, y0 + lab + ch - 1], outline=200)
            dr.text((x0 + 2, y0 + 4), l, fill=0)
        sheet.save(out / f"sheet_{art}.png")
        sheet.convert("RGB").save(out / f"sheet_{art}.jpg", quality=85)
        # big single views for looking closely
        with ProcessPoolExecutor(JOBS) as ex:
            big = list(ex.map(_render_job, [(draws[0], 1200), (draws[6], 1200), (draws[9], 1200), (draws[-1], 1200)]))
        for im, nm in zip(big, ("lognormal1", "single1", "v3_1", "real")):
            Image.fromarray(im).convert("RGB").save(out / f"{art}_{nm}_1200.jpg", quality=85)
        print("sheet", out / f"sheet_{art}.jpg")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("synth", "fit", "test1", "memo", "sheets"))
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=5)
    a = ap.parse_args(argv)
    {"synth": cmd_synth, "fit": cmd_fit, "test1": cmd_test1, "memo": cmd_memo, "sheets": cmd_sheets}[a.cmd](a)


if __name__ == "__main__":
    main()
