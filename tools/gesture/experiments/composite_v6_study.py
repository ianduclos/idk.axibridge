"""Composite on grammar v6 + tremor v2: results/composite-v6-2026-10-16.md.

Library code is in experiments/composite.py (`grammar(art, version)`,
`composite(grammar_version=, budget=, tremor=, tremor_which=, tremor_returns=)`,
`tremor_chain`) and gesture/restyle.py (v6 budget inside `trace`); the
measures (balloons, fidelity, hairpin cut) come from experiments/chain_study.py.

  ablation   structures (30 Oehlen trees + the Matisse torso; + learned
             topologies for the final pipeline) × hands (M, H, I) ×
             conditions: v4 vs v6 restyle and chain fix, budget gain 2, tremor
             (follow / independent returns). Rows: fidelity, balloons,
             return-pass spacing, panel features (restyle as drawn; single
             lines between hairpins). Resumable (rows.jsonl).
  report     v4-vs-v6 texture table, tremor table, pairwise M–H / M–I / H–I.
  sheets     composite-v6-*.jpg (≤ 600 KB each).
  plot       plot candidates v2 → .local/gesture/out/plot_candidates_v2/.

    ../../.local/gesture/.venv/bin/python -m experiments.composite_v6_study ablation
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments import chain_study as cs  # noqa: E402
from experiments import composite as cp  # noqa: E402
from gesture import topology  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

OUT = cp.OUTROOT / "composite_v6"
PLOT = cp.OUTROOT / "plot_candidates_v2"
HANDS = cp.ARTISTS
PAIRS = (("matisse", "hokusai"), ("matisse", "ingres"), ("hokusai", "ingres"))
AMOUNT = 0.7
TREMOR = 1.0
FULL = cs.FULL                                     # chain="before", pin="turns", retrace="offset", walk="min_turn"

CONDITIONS = {
    "skel":   dict(),                                               # the structure itself (corner floor)
    "r4":     dict(chain=False, grammar_version="v4"),
    "r6":     dict(chain=False, grammar_version="v6"),
    "r6b2":   dict(chain=False, grammar_version="v6", budget=2.0),
    "r6b05":  dict(chain=False, grammar_version="v6", budget=0.5),
    "f4":     dict(**FULL, grammar_version="v4"),
    "f6":     dict(**FULL, grammar_version="v6"),
    "f6b2":   dict(**FULL, grammar_version="v6", budget=2.0),
    "f6b05":  dict(**FULL, grammar_version="v6", budget=0.5),
    "f6t":    dict(**FULL, grammar_version="v6", tremor=TREMOR),
    "f6ti":   dict(**FULL, grammar_version="v6", tremor=TREMOR, tremor_returns="independent"),
    "f4t":    dict(**FULL, grammar_version="v4", tremor=TREMOR),
    "r6t":    dict(chain=False, grammar_version="v6", tremor=TREMOR),
}
DESC = {
    "skel": "structure alone (no hand)",
    "r4": "restyle, v4 grammar (rounds 3–4)",
    "r6": "restyle, v6 grammar + budget (gain 1)",
    "r6b2": "restyle, v6, budget gain 2",
    "r6b05": "restyle, v6, budget gain 0.5",
    "f4": "single line (chain fix), v4",
    "f6": "single line, v6",
    "f6b2": "single line, v6, budget gain 2",
    "f6b05": "single line, v6, budget gain 0.5",
    "f6t": "single line, v6 + tremor (per-hand default, returns follow)",
    "f6ti": "single line, v6 + tremor, returns independent",
    "f4t": "single line, v4 + tremor (follow)",
    "r6t": "restyle, v6 + tremor (apply_tremor, contacts re-snapped)",
}
LEARNED_CONDS = ("f6", "f6t")
KEYS = ("cl_corner_rate", "turn_tcorr_10", "k_q50", "turn_abs", "turn_net_ratio")


# ---------------------------------------------------------------------------
# measures
# ---------------------------------------------------------------------------

def structures(n_tree: int, n_learned: int) -> dict[str, Drawing]:
    S = cp.pair_structures(n_tree, n_learned)
    S["torso"] = cp.real_structure(*cs.TORSO)
    return S


def _job(args):
    name, st, hand, cond, seed = args
    kw = dict(CONDITIONS[cond])
    R = st.ref_length()
    t0 = time.time()
    if cond == "skel":
        d = st
    else:
        if (name == "torso" or name.startswith("learned")) and kw.get("chain"):
            kw["connect"] = True
        d = cp.composite(st, hand, np.random.default_rng([seed, 7]), amount=AMOUNT, **kw)
    sec = time.time() - t0
    row = {"src": name, "hand": hand, "cond": cond, "sec": sec, "n_paths": len(d.strokes)}
    if cond != "skel":
        c = d.meta["composite"]
        cm = c["chain_meta"] or {}
        tm = c.get("tremor_meta") or {}
        row.update(retrace=cm.get("retrace_R", 0.0) / max(cm.get("ink_R", 1.0), 1e-9) if cm else 0.0,
                   balloons=cs.balloons(d, R, st), tremor_note=c.get("tremor_note", ""),
                   tremor_rms_w=tm.get("disp_rms_px", np.nan) / max(cp.hand_w(hand) * R, 1e-9) if tm else None,
                   **cs.fidelity(d, st, R), **cp.return_spacing(d, cp.hand_w(hand) * R, R))
    chained = bool(kw.get("chain")) and kw.get("chain") != "after"
    m = cs.split_at_hairpins(d, R) if chained else d
    row["n_meas"] = len(m.strokes)
    row["feats"] = cp.feats(cp.with_width(m, cp.w_common()), clothoid=True)
    row["sec_total"] = time.time() - t0
    return row


def _load(path: Path) -> dict:
    done = {}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                r = json.loads(line)
                done[(r["src"], r["hand"], r["cond"])] = r
            except Exception:  # noqa: BLE001
                pass
    return done


def cmd_ablation(a):
    OUT.mkdir(parents=True, exist_ok=True)
    S = structures(a.n_tree, a.n_learned)
    conds = a.conds.split(",") if a.conds else list(CONDITIONS)
    jobs = []
    for n, st in S.items():
        for h in HANDS:
            for c in conds:
                if n.startswith("learned") and c not in LEARNED_CONDS:
                    continue
                if c == "skel" and h != HANDS[0]:
                    continue
                jobs.append((n, st, h, c, a.seed))
    cache = OUT / "rows.jsonl"
    done = _load(cache)
    todo = [j for j in jobs if (j[0], j[2], j[3]) not in done]
    print(f"ablation: {len(S)} structures; {len(done)} cached, {len(todo)} to run", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(cp.JOBS) as ex, open(cache, "a") as fh:
        futs = [ex.submit(_job, j) for j in todo]
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            if i % 50 == 0:
                print(f"  {i}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    cmd_report(a)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _med(rr, k):
    v = [r[k] for r in rr if r.get(k) is not None and np.isfinite(r[k])]
    return float(np.median(v)) if v else float("nan")


def cmd_report(a):
    from scipy.stats import binomtest
    done = _load(OUT / "rows.jsonl")
    real = cp.real_feats()
    rep = {"texture": [], "tremor": [], "pairwise": [], "real": {}}
    for h in HANDS:
        rep["real"][h] = {k: float(np.nanmedian([f.get(k, np.nan) for a_, _s, f in real if a_ == h])) for k in KEYS}
    trees = sorted({k[0] for k in done if k[0].startswith("tree")})
    learned = sorted({k[0] for k in done if k[0].startswith("learned")})
    conds = [c for c in CONDITIONS if any(k[2] == c for k in done)]
    # texture + fidelity per condition × hand (trees)
    for c in conds:
        for h in (HANDS if c != "skel" else (HANDS[0],)):
            rr = [done[(t, h, c)] for t in trees if (t, h, c) in done]
            if not rr:
                continue
            ent = {"cond": c, "hand": h if c != "skel" else "—", "n": len(rr),
                   **{k: float(np.nanmedian([r["feats"].get(k, np.nan) for r in rr])) for k in KEYS}}
            for k in ("d_mean", "cover95", "junc_max", "retrace", "n_paths", "sec", "sp_min", "sp_q01", "sp_q50",
                      "sp_lt1", "sp_lt05", "tremor_rms_w"):
                ent[k] = _med(rr, k)
            ent["junc_max_max"] = float(max((r.get("junc_max", 0) for r in rr), default=np.nan))
            ent["sp_min_min"] = float(min((r.get("sp_min", np.inf) for r in rr), default=np.nan))
            ent["balloons"] = float(np.mean([r.get("balloons", 0) for r in rr]))
            tor = done.get(("torso", h, c))
            ent["torso"] = {k: tor.get(k) for k in ("balloons", "d_mean", "cover95", "sp_min", "sp_lt1", "n_paths",
                                                    "cl_corner")} if tor else None
            if tor:
                ent["torso"]["cl_corner"] = tor["feats"].get("cl_corner_rate")
            rep["texture"].append(ent)
    # pairwise per hand pair × condition, trees (and learned where present)
    for groups, gtag in ((cp.TEXTURE_GROUPS, "all"), (("k", "ext", "infl", "turn"), "no_cl")):
        for A, B in PAIRS:
            pc = cp.PairClassifier(real, A, B, groups=groups)
            cv, cvp = pc.cv_pairwise()
            zr = {h: float(np.median(pc.clf.decision_function(pc.pj.transform(
                pc.matrix([f for a_, _s, f in real if a_ == h]))))) for h in (A, B)}
            for c in conds:
                if c == "skel":
                    continue
                for sset, names in (("trees", trees), ("learned", learned)):
                    ok, n, lA, lB = 0, 0, [], []
                    for t in names:
                        ra, rb = done.get((t, A, c)), done.get((t, B, c))
                        if not ra or not rb:
                            continue
                        za, zb = pc.clf.decision_function(pc.pj.transform(pc.matrix([ra["feats"], rb["feats"]])))
                        ok += int(za > zb)
                        n += 1
                        lA.append(float(za))
                        lB.append(float(zb))
                    if not n:
                        continue
                    rep["pairwise"].append({"groups": gtag, "pair": f"{A[0].upper()}–{B[0].upper()}", "cond": c,
                                            "set": sset, "n": n, "acc": ok / n,
                                            "p": float(binomtest(ok, n, 0.5, alternative="greater").pvalue),
                                            "logit_A": float(np.median(lA)), "logit_B": float(np.median(lB)),
                                            "cv": cv, "cv_pair": cvp, "real_A": zr[A], "real_B": zr[B]})
    (OUT / "report.json").write_text(json.dumps(rep, indent=1))
    md = report_md(rep)
    (OUT / "report.md").write_text(md)
    print(md)


def report_md(rep) -> str:
    L = ["Texture and fidelity (30 Oehlen trees, amount 0.7; medians; single lines measured between hairpins).", "",
         "| # | condition | hand | corners/R | turn_tcorr_10 | k_q50 | turn_abs | d_mean/R | junc max/R (worst) | "
         "balloons | paths | torso corners / d_mean / balloons |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(rep["texture"], 1):
        t = e.get("torso")
        ts = f"{t['cl_corner']:.2f} / {t['d_mean']:.4f} / {t['balloons']}" if t and t.get("d_mean") is not None else "–"
        L.append(f"| T{i} | {e['cond']} — {DESC[e['cond']]} | {e['hand']} | {e['cl_corner_rate']:.2f} | "
                 f"{e['turn_tcorr_10']:.2f} | {e['k_q50']:.1f} | {e['turn_abs']:.2f} | {e['d_mean']:.4f} | "
                 f"{e['junc_max']:.4f} ({e['junc_max_max']:.4f}) | {e['balloons']:.1f} | {e['n_paths']:.0f} | {ts} |")
    L.append("")
    L.append("Real (median): " + "; ".join(f"{h}: corners {v['cl_corner_rate']:.2f}, tcorr {v['turn_tcorr_10']:.2f}, "
                                           f"k_q50 {v['k_q50']:.1f}, turn_abs {v['turn_abs']:.2f}"
                                           for h, v in rep["real"].items()))
    L += ["", "Return-pass spacing (single lines, central part of every offset return, in line widths; offset 1.5 w).", "",
          "| # | condition | hand | tremor rms (w) | spacing min (worst tree) | q01 | median | share < 1 w | share < 0.5 w |",
          "|---|---|---|---|---|---|---|---|---|"]
    k = 0
    for e in rep["texture"]:
        if not np.isfinite(e.get("sp_q50", np.nan)):
            continue
        k += 1
        L.append(f"| S{k} | {e['cond']} | {e['hand']} | {e['tremor_rms_w']:.3f} | {e['sp_min']:.2f} ({e['sp_min_min']:.2f}) | "
                 f"{e['sp_q01']:.2f} | {e['sp_q50']:.2f} | {e['sp_lt1']:.3%} | {e['sp_lt05']:.3%} |")
    for gtag in ("all", "no_cl"):
        rows = [r for r in rep["pairwise"] if r["groups"] == gtag]
        if not rows:
            continue
        L += ["", f"Pairwise hand test, texture groups {'k, ext, infl, turn, cl' if gtag == 'all' else 'k, ext, infl, turn'}"
                  " (classifier on REAL drawings of A vs B; correct when the A-hand drawing scores more A than the "
                  "B-hand drawing of the same structure).", "",
              "| # | pair | condition | set | n | acc | p | logit A-hand / B-hand | real A / B | real CV / pairwise |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(rows, 1):
            L.append(f"| P{i} | {r['pair']} | {r['cond']} | {r['set']} | {r['n']} | {r['acc']:.2f} | {r['p']:.3f} | "
                     f"{r['logit_A']:+.1f} / {r['logit_B']:+.1f} | {r['real_A']:+.1f} / {r['real_B']:+.1f} | "
                     f"{r['cv']:.2f} / {r['cv_pair']:.2f} |")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# structures for the sheets / plots
# ---------------------------------------------------------------------------

DENSE = {"depth": 5, "trunks": 3, "fill": 0.95, "p_cross": 0.35, "wind": 6.0, "clearance_r": 0.007,
         "max_strokes": 300}


def dense_tree(seed: int = 7) -> Drawing:
    """'More complex than the trees': a crossing, winding, dense Oehlen network."""
    return topology.generate_structure(None, np.random.default_rng([41, seed]), 1200, kind="oehlen_tree", **DENSE)


def torso_in_tree(seed: int = 3) -> Drawing:
    """Regime collision: the Matisse torso's long strokes and a medium Oehlen
    tree on one sheet (same canvas), to be drawn as one line."""
    tor = cp.real_structure(*cs.TORSO)
    tree = cs._tree_structure(101 + seed, {"depth": 4, "trunks": 2, "fill": 0.6})
    return Drawing([Stroke(s.points.copy(), closed=s.closed) for s in tor.strokes + tree.strokes],
                   source="torso+tree", size=(1200, 1200))


def learned_structure(art: str, i: int = 0) -> Drawing:
    return topology.generate_structure(cp.topo_model(art), np.random.default_rng([33, i]), 1200, kind="learned")


def _spec(st, hand, kw, label, seed=101, big=None):
    return {"kind": "comp", "structure": st, "hand": hand, "seed": seed, "kw": kw, "label": label, "big": big}


def cmd_sheets(a):
    sd = OUT / "sheets"
    sd.mkdir(parents=True, exist_ok=True)
    size = a.size
    which = set(a.which.split(","))
    one, p8 = dict(FULL), dict(FULL, max_paths=8)
    trem = dict(tremor=TREMOR)
    if "trees" in which:
        rows = []
        for lvl, prm in cp.TREE_LEVELS[1:]:
            seed = 101 if lvl == "medium" else 102
            st = cs._tree_structure(seed, prm)
            r = [{"kind": "structure", "drawing": st, "label": f"{lvl} tree"}]
            for h in HANDS:
                for lab, kw in (("v4", dict(one, grammar_version="v4")), ("v6", dict(one)),
                                ("v6+tremor", dict(one, **trem))):
                    if h == "ingres" and lab == "v4":
                        continue
                    r.append(_spec(st, h, kw, f"{h[:3]} {lab}", seed,
                                   str(sd / f"big-{lvl}-{h}-{lab.replace('+', '_')}.jpg") if lvl == "medium" else None))
            rows.append(r)
        cs.grid(rows, cp.RESULTS / "composite-v6-trees.jpg", size, quality=a.quality)
    if "paths" in which:
        rows = []
        for lvl, prm in cp.TREE_LEVELS[1:]:
            seed = 101 if lvl == "medium" else 102
            st = cs._tree_structure(seed, prm)
            rows.append([_spec(st, h, dict(p8, **trem), f"{lvl} {h[:3]} v6+tr <=8") for h in HANDS] +
                        [_spec(st, "hokusai", dict(p8, grammar_version="v4"), f"{lvl} hok v4 <=8")])
        r = []
        for h in HANDS:
            st = learned_structure(h)
            r.append(_spec(st, h, dict(one, connect=True, **trem), f"learned {h[:3]} 1 line"))
        r.append(_spec(learned_structure("hokusai"), "hokusai", dict(p8, connect=True, **trem), "learned hok <=8"))
        rows.append(r)
        cs.grid(rows, cp.RESULTS / "composite-v6-paths.jpg", size, quality=a.quality)
    if "torso" in which:
        st = cp.real_structure(*cs.TORSO)
        rows = [[{"kind": "structure", "drawing": st, "label": "Matisse KKS1971-302 long strokes"}] +
                [_spec(st, h, dict(one, connect=True, grammar_version="v4"), f"{h[:3]} v4 1 line", 300) for h in HANDS]]
        rows.append([_spec(st, h, dict(one, connect=True, **trem), f"{h[:3]} v6+tr 1 line", 300,
                           str(sd / f"big-torso-{h}.jpg")) for h in HANDS] +
                    [_spec(st, "hokusai", dict(p8, connect=True, **trem), "hok v6+tr <=8", 300)])
        cs.grid(rows, cp.RESULTS / "composite-v6-torso.jpg", size, quality=a.quality)
    if "complex" in which:
        dn, tt = dense_tree(), torso_in_tree()
        rows = [[{"kind": "structure", "drawing": dn, "label": "dense crossing network"}] +
                [_spec(dn, h, dict(one, at_crossings=True, **trem), f"{h[:3]} v6+tr 1 line", 500,
                       str(sd / f"big-dense-{h}.jpg")) for h in HANDS],
                [{"kind": "structure", "drawing": tt, "label": "torso + tree (regime collision)"}] +
                [_spec(tt, h, dict(one, connect=True, **trem), f"{h[:3]} v6+tr 1 line", 500,
                       str(sd / f"big-torsotree-{h}.jpg")) for h in HANDS]]
        cs.grid(rows, cp.RESULTS / "composite-v6-complex.jpg", size, quality=a.quality)


# ---------------------------------------------------------------------------
# plot candidates v2
# ---------------------------------------------------------------------------

def plot_specs() -> list:
    prm = cp.TREE_LEVELS[1][1]
    one = dict(FULL, tremor=TREMOR)
    torso = cp.real_structure(*cs.TORSO)
    return [("tree-medium-matisse-1line", "oehlen_tree", "matisse", 101, dict(one), prm),
            ("tree-medium-hokusai-1line", "oehlen_tree", "hokusai", 101, dict(one), prm),
            ("torso-matisse-1line", torso, "matisse", 300, dict(one, connect=True), None),
            ("torso-hokusai-1line", torso, "hokusai", 300, dict(one, connect=True), None),
            ("dense-hokusai-1line", dense_tree(), "hokusai", 500, dict(one, at_crossings=True, connect=True), None),
            ("torso-tree-matisse-1line", torso_in_tree(), "matisse", 500, dict(one, connect=True), None)]


def cmd_plot(a):
    from PIL import Image
    PLOT.mkdir(parents=True, exist_ok=True)
    log = {}
    for name, st, h, seed, kw, prm in plot_specs():
        d = cp.composite(st, h, np.random.default_rng(seed), amount=AMOUNT, structure_params=prm, **kw)
        svg, stats = cp.to_svg(d, PLOT / f"{name}.svg", paper=a.paper, margin_mm=a.margin,
                               title=f"{name} (gesture composite v6 + tremor)")
        R = d.ref_length()
        sk = st if isinstance(st, Drawing) else cs._tree_structure(seed, prm)
        c = d.meta["composite"]
        cm = c["chain_meta"] or {}
        P = np.vstack([s.points for s in d.strokes])
        mm_per_px = float(np.ptp(np.vstack(cp.to_mm(d, paper=a.paper, margin_mm=a.margin, simplify_mm=0)), 0).max()
                          / max(np.ptp(P, 0).max(), 1e-9))
        w_px = cp.hand_w(h) * R
        tm = c.get("tremor_meta") or {}
        sp = cp.return_spacing(d, w_px, R)
        stats.update(hand=h, seed=seed, amount=AMOUNT, grammar=c.get("grammar"), tremor=c.get("tremor_note"),
                     tremor_rms_mm=round(tm.get("disp_rms_px", 0.0) * mm_per_px, 4),
                     line_width_mm=round(w_px * mm_per_px, 3), offset_mm=round(cp.OFFSET_W * w_px * mm_per_px, 3),
                     return_spacing_min_mm=round(sp.get("sp_min", np.nan) * w_px * mm_per_px, 3) if sp else None,
                     return_spacing_q01_mm=round(sp.get("sp_q01", np.nan) * w_px * mm_per_px, 3) if sp else None,
                     balloons=cs.balloons(d, R, sk),
                     **{k: round(v, 4) for k, v in cs.fidelity(d, sk, R).items() if k in ("d_mean", "cover95", "junc_max")},
                     retrace=round(cm.get("retrace_R", 0) / max(cm.get("ink_R", 1), 1e-9), 3),
                     connector_R=round(cm.get("connector_R", 0.0), 3),
                     kwargs={k: v for k, v in kw.items()})
        Image.fromarray(cp.render_cell(d, 1200, lw=1.8)).save(PLOT / f"{name}.jpg", quality=88)
        log[name] = stats
        print(name, json.dumps(stats, default=str), flush=True)
    (PLOT / "candidates.json").write_text(json.dumps(log, indent=1, default=str))


def main(argv=None):
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("ablation")
    q.add_argument("--n-tree", type=int, default=30)
    q.add_argument("--n-learned", type=int, default=12)
    q.add_argument("--conds", default="")
    q.add_argument("--seed", type=int, default=1)
    sp.add_parser("report")
    s = sp.add_parser("sheets")
    s.add_argument("--size", type=int, default=360)
    s.add_argument("--quality", type=int, default=72)
    s.add_argument("--which", default="trees,paths,torso,complex")
    t = sp.add_parser("plot")
    t.add_argument("--paper", default="A4")
    t.add_argument("--margin", type=float, default=10.0)
    a = p.parse_args(argv)
    {"ablation": cmd_ablation, "report": cmd_report, "sheets": cmd_sheets, "plot": cmd_plot}[a.cmd](a)


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    main()
