"""The chain fix: single continuous lines through a structure that keep the
structure and the hand. results/composite-chain-2026-10-16.md.

Library code lives in experiments/composite.py (`chain_paths` walk/connect/
max_paths, `restyle_chain`, `offset_return`, `to_svg`); this file measures it.

  ablation   conditions × Oehlen trees (+ the Matisse torso) × {Matisse, Hokusai}:
             structure fidelity, junction gaps, balloon count, retrace, pen
             lifts, and the panel pairwise hand test (M vs H) per condition.
  sheets     before/after sheets (trees, torso, variants) + 1200 px singles.
  plot       2–3 SVG plot candidates (A4 landscape, mm) + their stats.

    ../../.local/gesture/.venv/bin/python -m experiments.chain_study ablation
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

from experiments import composite as cp  # noqa: E402
from gesture import restyle as rs  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402
from gesture.curvature import resample  # noqa: E402

OUT = cp.OUTROOT / "composite_chain"
PLOT = cp.OUTROOT / "plot_candidates"
HANDS = ("matisse", "hokusai")
AMOUNT = 0.7
TORSO = ("matisse", "KKS1971-302")
FULL = dict(chain="before", pin="turns", retrace="offset", walk="min_turn")

# name → composite kwargs. run_sigmas=None = no per-run σ cap.
CONDITIONS = {
    "restyle":      dict(chain=False),
    "after":        dict(chain="after"),
    "after_p8":     dict(chain="after", max_paths=8),
    "raw":          dict(chain="before"),
    "tips":         dict(chain="before", pin="tips", run_sigmas=None),
    "turns":        dict(chain="before", pin="turns", run_sigmas=None),
    "turns_cap":    dict(chain="before", pin="turns"),
    "exact":        dict(chain="before", pin="turns", retrace="exact"),
    "offset":       dict(chain="before", pin="turns", retrace="offset"),
    "minturn_raw":  dict(chain="before", walk="min_turn"),
    "full":         FULL,
    "full_p8":      dict(**FULL, max_paths=8),
    "ln_raw":       dict(chain="before", model="lognormal"),
    "ln_full":      dict(**FULL, model="lognormal"),
}
DESC = {
    "restyle": "restyle only, not chained (round-3 reference; many paths)",
    "after": "chain after restyle: 1 path, exact retrace",
    "after_p8": "chain after restyle, ≤ 8 paths",
    "raw": "chain before, unpinned (round 3's dud)",
    "tips": "(a) pin reversals only",
    "turns": "(a) pin reversals + node turns ≥ 60°",
    "turns_cap": "(a) + σ_s ≤ run/3 (interior pins on short runs)",
    "exact": "(a)+cap, returns = exact retrace in the hand",
    "offset": "(b) (a)+cap, returns offset 1.5 w",
    "minturn_raw": "(c) min-turn walk alone, unpinned",
    "full": "(c)+(b)+(a): min-turn walk, pinned, capped, offset",
    "full_p8": "(d) full, ≤ 8 paths",
    "ln_raw": "(e) lognormal hand, unpinned",
    "ln_full": "(e) lognormal hand, full fix",
}


# ---------------------------------------------------------------------------
# measures
# ---------------------------------------------------------------------------

def _dense(d: Drawing, h: float) -> list[np.ndarray]:
    out = []
    for s in d.strokes:
        if len(s) < 2 or s.length() <= 0:
            continue
        p = np.vstack([s.points, s.points[:1]]) if s.closed else s.points
        r = resample(p, h, closed=False)
        out.append(r if len(r) >= 2 else p)
    return out


OFF_R, OFF_FRAC = 0.02, 0.3   # balloon: ≥ OFF_FRAC of the loop's boundary is > OFF_R·R from the structure


def loops(d: Drawing, R: float, *, skel: Drawing | None = None, dmin: float = 0.02, dmax: float = 0.25,
          qmin: float = 0.25, step: float = 0.002) -> list[dict]:
    """Round loops of a drawing's own paths: a path that crosses itself and
    closes a region with equivalent diameter √(4A/π) in [dmin, dmax]·R and
    isoperimetric quotient 4πA/P² ≥ qmin (round, not a sliver between two
    near-parallel passes). Nested/overlapping loops count once (largest
    first). With `skel`, each loop gets `off` = the share of its boundary
    farther than OFF_R·R from the structure; a **balloon** is a loop with
    off ≥ OFF_FRAC — a loop the structure does not have (a single line
    through crossing branches closes real cells too; those lie on the
    structure and are not balloons)."""
    import shapely
    from scipy.spatial import cKDTree
    kt = cKDTree(np.vstack(_dense(skel, step * R))) if skel is not None else None
    found = []
    for p in _dense(d, step * R):
        dist = kt.query(p)[0] / R if kt is not None else None
        n = len(p) - 1
        if n < 4:
            continue
        segs = shapely.linestrings(np.stack([p[:-1], p[1:]], axis=1))
        tree = shapely.STRtree(segs)
        I, J = tree.query(segs, predicate="intersects")
        m = J > I + 1
        I, J = I[m], J[m]
        if not len(I):
            continue
        a, b, c, e = p[I], p[I + 1], p[J], p[J + 1]
        r, s = b - a, e - c
        den = r[:, 0] * s[:, 1] - r[:, 1] * s[:, 0]
        ok = np.abs(den) > 1e-12
        I, J, a, r, c, s, den = I[ok], J[ok], a[ok], r[ok], c[ok], s[ok], den[ok]
        t = ((c - a)[:, 0] * s[:, 1] - (c - a)[:, 1] * s[:, 0]) / den
        X = a + t[:, None] * r
        cr = p[:-1, 0] * p[1:, 1] - p[1:, 0] * p[:-1, 1]
        C = np.concatenate([[0.0], np.cumsum(cr)])
        sl = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
        q0, q1 = p[I + 1], p[J]
        A = 0.5 * np.abs(C[J] - C[I + 1] + (q1[:, 0] * X[:, 1] - X[:, 0] * q1[:, 1])
                         + (X[:, 0] * q0[:, 1] - q0[:, 0] * X[:, 1]))
        P = sl[J] - sl[I + 1] + np.linalg.norm(q0 - X, axis=1) + np.linalg.norm(q1 - X, axis=1)
        deq = np.sqrt(4 * A / np.pi) / R
        Q = 4 * np.pi * A / np.maximum(P * P, 1e-12)
        keep = (deq >= dmin) & (deq <= dmax) & (Q >= qmin)
        cand = sorted(zip(A[keep], I[keep], J[keep], deq[keep], Q[keep], X[keep].tolist()), key=lambda z: -z[0])
        taken: list[tuple[int, int]] = []
        for area, i, j, dq, qq, x in cand:
            if any(not (j < u or i > v) for u, v in taken):
                continue
            taken.append((int(i), int(j)))
            off = float(np.mean(dist[i + 1:j + 1] > OFF_R)) if dist is not None else float("nan")
            found.append({"d_R": float(dq), "q": float(qq), "at": x, "off": off})
    return found


def balloons(d: Drawing, R: float, skel: Drawing) -> int:
    return sum(lp["off"] >= OFF_FRAC for lp in loops(d, R, skel=skel))


def split_at_hairpins(d: Drawing, R: float, angle: float = 120.0, dd: float = 0.01, step: float = 0.002) -> Drawing:
    """Cut every path where it turns back (direction over ±dd·R differs by
    > angle): the strokes 'between hairpins'. Real drawings have no exact
    out-and-back inside a stroke, so this is the condition-independent way to
    put a single line in the panel's domain (one rule for every condition)."""
    out = []
    for p in _dense(d, step * R):
        k = max(int(round(dd / step)), 1)
        if len(p) <= 2 * k + 2:
            out.append(Stroke(p))
            continue
        u = p[k:-k] - p[:-2 * k]
        v = p[2 * k:] - p[k:-k]
        cs = np.sum(u * v, 1) / np.maximum(np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1), 1e-12)
        bad = np.where(cs < np.cos(np.radians(angle)))[0] + k
        cuts, last = [], -10 ** 9
        for b in bad:                          # one cut per hairpin: the sharpest sample of each run
            if b - last > k:
                cuts.append([b])
            else:
                cuts[-1].append(b)
            last = b
        idx = [int(c[len(c) // 2]) for c in cuts]
        for a, b in zip([0] + idx, idx + [len(p) - 1]):
            if b - a >= 2:
                out.append(Stroke(p[a:b + 1]))
    return Drawing(out, source=f"{d.source}|split", size=d.size)


def fidelity(out: Drawing, skel: Drawing, R: float, step: float = 0.002) -> dict:
    """Output vs structure, in R: d_mean / d95 (output → skeleton: does the
    line stay on the structure?), cover95 / cover_max (skeleton → output: is
    every part of the structure drawn?), junction gap (each structure
    junction → nearest output point: max / median)."""
    from scipy.spatial import cKDTree
    o = np.vstack(_dense(out, step * R))
    k = np.vstack(_dense(skel, step * R))
    d1, _ = cKDTree(k).query(o)
    d2, _ = cKDTree(o).query(k)
    J = rs.find_junctions(skel, R)
    jp = np.array([skel.strokes[i].points[e] for i, e, _j, _u in J]) if J else np.zeros((0, 2))
    jg = cKDTree(o).query(jp)[0] / R if len(jp) else np.zeros(0)
    return {"d_mean": float(d1.mean() / R), "d95": float(np.quantile(d1, 0.95) / R),
            "cover95": float(np.quantile(d2, 0.95) / R), "cover_max": float(d2.max() / R),
            "junc_max": float(jg.max()) if len(jg) else 0.0, "junc_med": float(np.median(jg)) if len(jg) else 0.0,
            "n_junc": int(len(jg))}


# ---------------------------------------------------------------------------
# ablation
# ---------------------------------------------------------------------------

def structures(n_tree: int) -> dict[str, Drawing]:
    S = cp.pair_structures(n_tree, 0)
    S["torso"] = cp.real_structure(*TORSO)
    return S


def _job(args):
    name, st, hand, cond, seed = args
    kw = dict(CONDITIONS[cond])
    if name == "torso" and kw.get("chain"):
        kw["connect"] = True                      # 12 loose contours → one line needs connectors
    t0 = time.time()
    d = cp.composite(st, hand, np.random.default_rng([seed, 7]), amount=AMOUNT, **kw)
    sec = time.time() - t0
    R = st.ref_length()
    c = d.meta["composite"]
    cm = c["chain_meta"] or {}
    row = {"src": name, "hand": hand, "cond": cond, "sec": sec, "n_paths": len(d.strokes),
           "retrace": cm.get("retrace_R", 0.0) / max(cm.get("ink_R", 1.0), 1e-9) if cm else 0.0,
           "connector_R": cm.get("connector_R", 0.0), "anchors": cm.get("anchors"), "reversals": cm.get("reversals"),
           "ink_out_R": sum(s.length() for s in d.strokes) / R,
           "loops": len(loops(d, R)), "balloons": balloons(d, R, st), **fidelity(d, st, R)}
    t1 = time.time()
    row["feats"] = cp.feats(cp.with_width(d, cp.w_common()), clothoid=False)
    sp = split_at_hairpins(d, R)
    row["n_split"] = len(sp.strokes)
    row["feats_split"] = cp.feats(cp.with_width(sp, cp.w_common()), clothoid=False)
    row["sec_feats"] = time.time() - t1
    return row


def cmd_ablation(a):
    OUT.mkdir(parents=True, exist_ok=True)
    S = structures(a.n_tree)
    conds = a.conds.split(",") if a.conds else list(CONDITIONS)
    jobs = [(n, st, h, c, a.seed) for n, st in S.items() for h in HANDS for c in conds]
    cache = OUT / "rows.jsonl"
    done = {}
    if cache.exists():
        for line in cache.read_text().splitlines():
            try:
                r = json.loads(line)
                done[(r["src"], r["hand"], r["cond"])] = r
            except Exception:  # noqa: BLE001
                pass
    todo = [j for j in jobs if (j[0], j[2], j[3]) not in done]
    print(f"ablation: {len(S)} structures × {len(HANDS)} hands × {len(conds)} conditions; "
          f"{len(done)} cached, {len(todo)} to run", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(cp.JOBS) as ex, open(cache, "a") as fh:
        futs = [ex.submit(_job, j) for j in todo]
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            done[(r["src"], r["hand"], r["cond"])] = r
            if i % 20 == 0:
                print(f"  {i}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    report(done, conds, list(S))


def report(done: dict, conds: list, names: list):
    from scipy.stats import binomtest
    real = cp.real_feats()
    groups = ("k", "ext", "infl", "turn")                 # cl skipped: clothoid fit is minutes on one long line
    pc = cp.PairClassifier(real, "matisse", "hokusai", groups=groups)
    cv, cvp = pc.cv_pairwise()
    pc_cl = cp.PairClassifier(real, "matisse", "hokusai")
    cv_cl, cvp_cl = pc_cl.cv_pairwise()
    trees = [n for n in names if n.startswith("tree")]
    rows, pair = [], []
    for c in conds:
        rr = [done[(n, h, c)] for n in trees for h in HANDS if (n, h, c) in done]
        if not rr:
            continue
        med = {k: float(np.median([r[k] for r in rr])) for k in
               ("d_mean", "d95", "cover95", "junc_max", "retrace", "n_paths", "ink_out_R", "sec")}
        med["balloons"] = float(np.mean([r["balloons"] for r in rr]))
        med["balloons_max"] = int(max(r["balloons"] for r in rr))
        med["loops"] = float(np.mean([r.get("loops", 0) for r in rr]))
        tor = {h: done.get(("torso", h, c)) for h in HANDS}
        ent = {"cond": c}
        for fk in ("feats", "feats_split"):
            ok, n, marg, lm, lh = 0, 0, [], [], []
            for t in trees:
                ra, rb = done.get((t, "matisse", c)), done.get((t, "hokusai", c))
                if not ra or not rb or fk not in ra:
                    continue
                X = pc.pj.transform(pc.matrix([ra[fk], rb[fk]]))
                za, zb = pc.clf.decision_function(X)
                ok += int(za > zb)
                n += 1
                marg.append(float(za - zb))
                lm.append(float(za))
                lh.append(float(zb))
            ent[fk] = {"n": n, "acc": ok / n if n else float("nan"),
                       "p": float(binomtest(ok, n, 0.5, alternative="greater").pvalue) if n else float("nan"),
                       "margin_med": float(np.median(marg)) if marg else float("nan"),
                       "logit_M": float(np.median(lm)) if lm else float("nan"),
                       "logit_H": float(np.median(lh)) if lh else float("nan")}
        rows.append({"cond": c, **med, "n_split": float(np.median([r.get("n_split", 0) for r in rr])),
                     "torso": {h: ({k: tor[h].get(k) for k in ("balloons", "loops", "d_mean", "cover95",
                                                                "n_paths", "retrace", "connector_R")}
                                   if tor[h] else None) for h in HANDS}})
        pair.append(ent)
    reals = [r for r in real if r[0] in HANDS]
    zr = {h: float(np.median(pc.clf.decision_function(pc.pj.transform(pc.matrix([f for a_, _s, f in reals if a_ == h])))))
          for h in HANDS}
    rep = {"classifier": {"groups": groups, "cv_acc": cv, "cv_pairwise_real": cvp, "real_logit_median": zr,
                          "with_cl": {"cv_acc": cv_cl, "cv_pairwise_real": cvp_cl}},
           "n_trees": len(trees), "amount": AMOUNT, "rows": rows, "pairwise": pair}
    (OUT / "ablation.json").write_text(json.dumps(rep, indent=1))
    md = ablation_md(rep)
    (OUT / "ablation.md").write_text(md)
    print(md)


def ablation_md(rep) -> str:
    L = [f"Trees: n = {rep['n_trees']} Oehlen trees (round-3 pairwise structures), hands Matisse + Hokusai, "
         f"amount {rep['amount']}. Medians over tree × hand; balloons and (all round loops) = mean counts.", "",
         "| # | condition | balloons (loops) | d_mean/R | d95/R | cover95/R | junction gap max/R | retrace | paths | "
         "ink/R | s | torso balloons M/H | torso cover95 M/H |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rep["rows"], 1):
        t = r["torso"]
        tb = "/".join(str(t[h]["balloons"]) if t[h] else "–" for h in HANDS)
        tc = "/".join(f"{t[h]['cover95']:.3f}" if t[h] else "–" for h in HANDS)
        L.append(f"| A{i} | {r['cond']} — {DESC.get(r['cond'], '')} | {r['balloons']:.1f} ({r['loops']:.1f}) | "
                 f"{r['d_mean']:.4f} | {r['d95']:.3f} | {r['cover95']:.3f} | {r['junc_max']:.4f} | "
                 f"{r['retrace']:.0%} | {r['n_paths']:.0f} | {r['ink_out_R']:.1f} | {r['sec']:.1f} | {tb} | {tc} |")
    c = rep["classifier"]
    zr = c["real_logit_median"]
    L += ["", f"Pairwise Matisse vs Hokusai. Classifier: logistic regression on REAL drawings, groups "
              f"{', '.join(c['groups'])} (cl skipped: its clothoid fit takes minutes on one long line); "
              f"CV acc {c['cv_acc']:.2f}, real held-out pairwise {c['cv_pairwise_real']:.2f} (with cl "
              f"{c['with_cl']['cv_acc']:.2f} / {c['with_cl']['cv_pairwise_real']:.2f}). Panel position = median "
              f"logit (> 0 = Matisse side); real drawings: Matisse {zr['matisse']:+.2f}, Hokusai {zr['hokusai']:+.2f}.",
          "'as drawn' measures each pen path as one stroke; 'between hairpins' cuts every path where it turns "
          "back (> 120° over ±0.01 R) — the same rule for every condition.", "",
          "| # | condition | as drawn: acc | p | logit M hand / H hand | between hairpins: acc | p | logit M / H | "
          "strokes after cut |",
          "|---|---|---|---|---|---|---|---|---|"]
    for i, (r, row) in enumerate(zip(rep["pairwise"], rep["rows"]), 1):
        a, b = r["feats"], r["feats_split"]
        L.append(f"| H{i} | {r['cond']} | {a['acc']:.2f} | {a['p']:.3f} | {a['logit_M']:+.1f} / {a['logit_H']:+.1f} | "
                 f"{b['acc']:.2f} | {b['p']:.3f} | {b['logit_M']:+.1f} / {b['logit_H']:+.1f} | {row['n_split']:.0f} |")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# sheets
# ---------------------------------------------------------------------------

def _cell(args):
    spec, size = args
    from PIL import Image
    if spec["kind"] == "structure":
        d = spec["drawing"]
        lab = spec["label"]
        frame = d
    else:
        st = spec["structure"]
        d = cp.composite(st, spec["hand"], np.random.default_rng(spec["seed"]), amount=AMOUNT,
                         structure_params=spec.get("params"), **spec["kw"])
        frame = None
        c = d.meta["composite"]
        cm = c["chain_meta"] or {}
        sk = st if isinstance(st, Drawing) else _tree_structure(spec["seed"], spec["params"])
        R = sk.ref_length()
        nb = balloons(d, R, sk)
        lab = f"{spec['label']} [{len(d.strokes)} path{'s' if len(d.strokes) != 1 else ''}, {nb} balloons" + \
              (f", retrace {cm.get('retrace_R', 0) / max(cm.get('ink_R', 1), 1e-9):.0%}]" if cm else "]")
        if spec.get("big"):
            Image.fromarray(cp.render_cell(d, 1200, lw=1.8)).save(spec["big"], quality=88)
    return cp._label(cp.render_cell(d, size, lw=1.3, frame=frame), lab)


def grid(rows, path: Path, size: int, quality: int = 80):
    from PIL import Image
    flat = [s for r in rows for s in r]
    with ProcessPoolExecutor(cp.JOBS) as ex:
        imgs = list(ex.map(_cell, [(s, size) for s in flat], chunksize=1))
    ncol = max(len(r) for r in rows)
    sheet = np.full((size * len(rows), size * ncol), 255, np.uint8)
    k = 0
    for i, r in enumerate(rows):
        for j in range(len(r)):
            sheet[i * size:(i + 1) * size, j * size:(j + 1) * size] = imgs[k]
            sheet[i * size:(i + 1) * size, j * size] = 190
            k += 1
        sheet[i * size, :] = 190
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sheet).save(path, quality=quality, optimize=True)
    print("wrote", path, f"{path.stat().st_size / 1024:.0f} KB", flush=True)


def _tree_structure(seed: int, prm: dict) -> Drawing:
    """The structure composite(…, rng=default_rng(seed)) builds (round-3 sheet trees)."""
    s_seed = int(np.random.default_rng(seed).integers(0, 2 ** 31, 3)[0])
    return cp.structure_of("oehlen_tree", None, np.random.default_rng(s_seed), 1200, prm)


def cmd_sheets(a):
    sd = OUT / "sheets"
    sd.mkdir(parents=True, exist_ok=True)
    size = a.size
    which = set(a.which.split(","))
    cols = [("before (raw)", dict(chain="before")), ("fixed, 1 line", FULL), ("fixed, <=8 paths", dict(**FULL, max_paths=8))]
    if "trees" in which:
        rows = []
        for i, (lvl, prm) in enumerate(cp.TREE_LEVELS):
            seed = 100 + i
            r = [{"kind": "structure", "drawing": _tree_structure(seed, prm), "label": f"tree {lvl} (skeleton)"}]
            for h in HANDS:
                for lab, kw in cols:
                    r.append({"kind": "comp", "structure": "oehlen_tree", "params": prm, "hand": h, "seed": seed,
                              "kw": kw, "label": f"{h} {lab}",
                              "big": str(sd / f"big-{lvl}-{h}-{lab.split(',')[0].split(' ')[0]}.jpg")
                              if lvl == "medium" else None})
            rows.append(r)
        grid(rows, cp.RESULTS / "composite-chain-trees.jpg", size)
    if "torso" in which:
        st = cp.real_structure(*TORSO)
        r = [{"kind": "structure", "drawing": st, "label": "Matisse KKS1971-302 long strokes"}]
        rows = [r]
        for h in HANDS:
            row = [{"kind": "comp", "structure": st, "hand": h, "seed": 300, "kw": dict(chain=False),
                    "label": f"{h} restyle (not chained)"}]
            for lab, kw in cols:
                row.append({"kind": "comp", "structure": st, "hand": h, "seed": 300, "kw": {**kw, "connect": True},
                            "label": f"{h} {lab}", "big": str(sd / f"big-torso-{h}-{lab.split(',')[0].split(' ')[0]}.jpg")})
            rows.append(row)
        rows[0] += [{"kind": "comp", "structure": st, "hand": "matisse", "seed": 300,
                     "kw": dict(chain="after", connect=True), "label": "matisse chain after (exact retrace)"}]
        grid(rows, cp.RESULTS / "composite-chain-torso.jpg", size)
    if "variants" in which:
        prm = cp.TREE_LEVELS[1][1]
        rows = []
        for h in HANDS:
            rows.append([{"kind": "comp", "structure": "oehlen_tree", "params": prm, "hand": h, "seed": 101,
                          "kw": CONDITIONS[c], "label": f"{h} {c}"}
                         for c in ("raw", "tips", "turns", "turns_cap", "exact", "full", "ln_full")])
        grid(rows, cp.RESULTS / "composite-chain-variants.jpg", size)


# ---------------------------------------------------------------------------
# plot candidates
# ---------------------------------------------------------------------------

def cmd_plot(a):
    PLOT.mkdir(parents=True, exist_ok=True)
    prm = cp.TREE_LEVELS[1][1]
    torso = cp.real_structure(*TORSO)
    specs = [("tree-medium-matisse-1line", "oehlen_tree", "matisse", 101, dict(FULL)),
             ("tree-medium-hokusai-1line", "oehlen_tree", "hokusai", 101, dict(FULL)),
             ("torso-hokusai-1line", torso, "hokusai", 300, dict(FULL, connect=True))]
    log = {}
    for name, st, h, seed, kw in specs:
        d = cp.composite(st, h, np.random.default_rng(seed), amount=AMOUNT,
                         structure_params=prm if st == "oehlen_tree" else None, **kw)
        svg, stats = cp.to_svg(d, PLOT / f"{name}.svg", paper=a.paper, margin_mm=a.margin,
                               title=f"{name} (gesture composite, chain fix)")
        R = d.ref_length()
        c = d.meta["composite"]["chain_meta"]
        sk = st if isinstance(st, Drawing) else _tree_structure(seed, prm)
        stats.update(balloons=balloons(d, R, sk), **{k: round(v, 4) for k, v in fidelity(d, sk, R).items()
                                                      if k in ("d_mean", "cover95", "junc_max")}, retrace=c.get("retrace_R", 0) / max(c.get("ink_R", 1), 1e-9),
                     connector_R=c.get("connector_R", 0.0), kwargs={k: v for k, v in kw.items()}, seed=seed, hand=h,
                     amount=AMOUNT)
        from PIL import Image
        Image.fromarray(cp.render_cell(d, 1200, lw=1.8)).save(PLOT / f"{name}.jpg", quality=88)
        log[name] = stats
        print(name, stats, flush=True)
    (PLOT / "candidates.json").write_text(json.dumps(log, indent=1, default=str))


def main(argv=None):
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("ablation")
    q.add_argument("--n-tree", type=int, default=18)
    q.add_argument("--conds", default="")
    q.add_argument("--seed", type=int, default=1)
    s = sp.add_parser("sheets")
    s.add_argument("--size", type=int, default=400)
    s.add_argument("--which", default="trees,torso,variants")
    t = sp.add_parser("plot")
    t.add_argument("--paper", default="A4")
    t.add_argument("--margin", type=float, default=10.0)
    a = p.parse_args(argv)
    {"ablation": cmd_ablation, "sheets": cmd_sheets, "plot": cmd_plot}[a.cmd](a)


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    main()
