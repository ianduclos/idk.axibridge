"""Topology study (results/topology-2026-10-16.md).

Subcommands (run from tools/gesture):

  measure   relation graph + topology features of every real long-stroke
            subset; per-artist TopologyModel → .local/gesture/out/topology/
  compare   per-artist signatures (medians), what distinguishes artists
            (grouped CV, raw and medium-projected; per-feature effect sizes)
  evaluate  generated structures (learned per artist, oehlen_tree) and
            grammar v3 (frozen, saved grammars) vs the real subsets:
            effect sizes + real-vs-generated AUC on topology features only
  sheets    population sheets (structures, trees, structures in a hand)

    ../../.local/gesture/.venv/bin/python -m experiments.topology_study measure
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

from gesture import grammar_v3_frozen as gm  # noqa: E402
from gesture import medium, synth  # noqa: E402
from gesture import topology as tp  # noqa: E402
from gesture.core import Drawing  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
EXTRACT = ROOT / ".local/gesture/out/extract_hybrid"
GRAMMARS = ROOT / ".local/gesture/out/grammar_v2"
OUT = ROOT / ".local/gesture/out/topology"
RESULTS = Path(__file__).resolve().parents[1] / "results"
ARTISTS = ("matisse", "hokusai", "ingres")
JOBS = max(1, min(10, (os.cpu_count() or 2) - 2))
GEN_SIDE = 1600          # generated canvases: the real sheet's aspect, this long side


def load(artist: str) -> list[tuple[str, Drawing]]:
    return [(p.stem, Drawing.load(p)) for p in sorted((EXTRACT / artist).glob("*.json"))]


def _feat(d: Drawing) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return tp.topology_features(d)


def _real_job(args):
    art, stem, path = args
    d = gm.long_drawing(Drawing.load(path))
    if len(d.strokes) < 2:
        return art, stem, None
    return art, stem, _feat(d)


def _model_job(art):
    ds = [gm.long_drawing(d) for _s, d in load(art)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = tp.learn_model([d for d in ds if len(d.strokes) >= 2], name=art)
    m.save(OUT / f"model_{art}.json")
    return art


def cmd_measure(a):
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(art, p.stem, str(p)) for art in ARTISTS for p in sorted((EXTRACT / art).glob("*.json"))]
    t0 = time.time()
    with ProcessPoolExecutor(JOBS) as ex:
        rows = [r for r in ex.map(_real_job, jobs) if r[2] is not None]
        list(ex.map(_model_job, ARTISTS))
    (OUT / "real.json").write_text(json.dumps([{"artist": r[0], "stem": r[1], "f": r[2]} for r in rows]))
    print(f"measured {len(rows)} drawings in {time.time() - t0:.0f}s; models saved")


def _load_real():
    rows = json.loads((OUT / "real.json").read_text())
    return rows


NAMES = [k for k in tp.FEATURES if k not in tp.DESCRIPTIVE]


def _matrix(rows, names=NAMES):
    return np.array([[r["f"].get(n, np.nan) if r["f"].get(n) is not None else np.nan for n in names]
                     for r in rows], dtype=float)


def _fmt(v):
    return "—" if v is None or not np.isfinite(v) else (f"{v:.3g}")


def cmd_compare(a):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from discriminate import _models, cv_score, effect_sizes, pair_auc
    rows = _load_real()
    X = _matrix(rows)
    art = np.array([r["artist"] for r in rows])
    lut = medium.load_media()
    med = np.array([lut.get((r["artist"], r["stem"]), "unknown") for r in rows])
    # drop all-NaN columns
    ok = ~np.all(np.isnan(X), axis=0)
    names = [n for n, o in zip(NAMES, ok) if o]
    X = X[:, ok]
    pj = medium.MediumProjector(medium.load_pairs()).fit(X, art, med)
    Xp = pj.transform(X)
    models = _models(a.seed)
    rep = {"n": {x: int((art == x).sum()) for x in ARTISTS}, "features": names}
    rep["medians"] = {x: {n: float(np.nanmedian(X[art == x, i])) if np.any(np.isfinite(X[art == x, i])) else None
                          for i, n in enumerate(names)} for x in ARTISTS}
    rep["iqr"] = {x: {n: [float(np.nanquantile(X[art == x, i], .25)), float(np.nanquantile(X[art == x, i], .75))]
                      if np.any(np.isfinite(X[art == x, i])) else None for i, n in enumerate(names)} for x in ARTISTS}
    rep["cv3"] = {}
    for tag, M in (("raw", X), ("projected", Xp)):
        rep["cv3"][tag] = {mn: cv_score(mk, M, art, 5, a.repeats, a.seed, 1) for mn, mk in models.items()}
    rep["pairs"] = {}
    for i, x in enumerate(ARTISTS):
        for y in ARTISTS[i + 1:]:
            key = f"{x}_vs_{y}"
            rep["pairs"][key] = {tag: {mn: pair_auc(mk, M, art, x, y, a.repeats, a.seed) for mn, mk in models.items()}
                                 for tag, M in (("raw", X), ("projected", Xp))}
            rep["pairs"][key]["top_d"] = effect_sizes(X, art, names, x, y, top=8)
    # medium control on topology features: is etching vs litho recoverable?
    rep["medium_heldout"] = {p: medium.heldout_medium_auc(X, art, med, medium.load_pairs(), reps=20, probe=pr)
                             for p, pr in (("linear", "linear"), ("forest", "forest"))}
    # single-feature 3-way separability: Kruskal–Wallis H
    from scipy.stats import kruskal
    kw = []
    for i, n in enumerate(names):
        g = [X[art == x, i][np.isfinite(X[art == x, i])] for x in ARTISTS]
        if min(len(v) for v in g) >= 3 and np.ptp(np.concatenate(g)) > 0:
            h, p = kruskal(*g)
            kw.append({"feature": n, "H": float(h), "p": float(p)})
    kw.sort(key=lambda r: -r["H"])
    rep["kruskal"] = kw
    # permutation importance (forest, projected)
    from discriminate import perm_importance
    rep["perm"] = perm_importance(models["forest"], Xp, art, names, 5, a.seed, top=12)
    (OUT / "compare.json").write_text(json.dumps(rep, indent=1))
    # markdown
    L = ["| # | feature | Matisse | Hokusai | Ingres | KW H | meaning |", "|---|---|---|---|---|---|---|"]
    H = {r["feature"]: r["H"] for r in kw}
    order = sorted(names, key=lambda n: -H.get(n, 0))
    for k, n in enumerate(order, 1):
        cells = []
        for x in ARTISTS:
            md, q = rep["medians"][x][n], rep["iqr"][x][n]
            cells.append(f"{_fmt(md)} ({_fmt(q[0])}–{_fmt(q[1])})" if q else "—")
        L.append(f"| S{k} | `{n}` | " + " | ".join(cells) + f" | {H.get(n, float('nan')):.1f} | {tp.FEATURES[n]} |")
    L += ["", "3-way balanced accuracy (chance .33), grouped 5-fold × repeats:", ""]
    for tag, r in rep["cv3"].items():
        L.append(f"- {tag}: " + ", ".join(f"{mn} {v['bacc']:.3f} ± {v['std']:.3f}" for mn, v in r.items()))
    L += ["", "| pair | raw logreg / forest AUC | projected logreg / forest | top features (d, medians a → b) |",
          "|---|---|---|---|"]
    for key, r in rep["pairs"].items():
        L.append(f"| {key} | {r['raw']['logreg']['auc']:.3f} / {r['raw']['forest']['auc']:.3f} | "
                 f"{r['projected']['logreg']['auc']:.3f} / {r['projected']['forest']['auc']:.3f} | " +
                 "; ".join(f"`{t['feature']}` {t['d']:+.1f} ({t['a']:.3g}→{t['b']:.3g})" for t in r["top_d"][:5]) + " |")
    L += ["", "Medium control (Matisse etching vs litho, held-out AUC raw → projected): " +
          json.dumps({p: {k: {kk: round(vv[0], 3) for kk, vv in v.items()} for k, v in r.items()}
                      for p, r in rep["medium_heldout"].items()})]
    L += ["", "Permutation importance (forest, projected): " +
          ", ".join(f"`{r['feature']}` {r['importance']:.3f}" for r in rep["perm"][:10])]
    (OUT / "compare.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------

def _gen_size(size):
    w, h = size
    s = GEN_SIDE / max(w, h)
    return (int(round(w * s)), int(round(h * s)))


def _gen_job(args):
    which, art, size, seed = args
    rng = np.random.default_rng(seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if which == "learned":
            m = tp.TopologyModel.load(OUT / f"model_{art}.json")
            d = tp.generate_structure(m, rng, size, kind="learned")
        elif which == "tree":
            d = tp.generate_structure(None, rng, size, kind="oehlen_tree")
        elif which == "v3":
            g = gm.Grammar.load(GRAMMARS / f"grammar_{art}.json")
            d = gm.generate_drawing(g, rng, size, relations="learned")
        else:
            raise ValueError(which)
        return which, art, seed, d.to_json(), _feat(d)


def cmd_evaluate(a):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from discriminate import _models, effect_sizes, pair_auc
    rows = _load_real()
    sizes = {}
    for art in ARTISTS:
        for p in sorted((EXTRACT / art).glob("*.json")):
            sizes[(art, p.stem)] = tuple(json.loads(p.read_text())["size"])
    jobs = []
    for art in ARTISTS:
        rr = [r for r in rows if r["artist"] == art]
        for i, r in enumerate(rr):
            sz = _gen_size(sizes[(art, r["stem"])])
            for which in ("learned", "v3", "tree"):
                if which == "tree" and art != "matisse":
                    continue                       # one tree population, compared to every artist
                jobs.append((which, art, sz, a.seed * 10000 + i))
    t0 = time.time()
    gen = []
    with ProcessPoolExecutor(JOBS) as ex:
        for which, art, seed, dj, f in ex.map(_gen_job, jobs, chunksize=1):
            gen.append({"which": which, "artist": art, "seed": seed, "f": f})
            if a.keep:
                p = OUT / "gen" / f"{which}_{art}_{seed}.json"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(dj))
    print(f"generated + measured {len(gen)} in {time.time() - t0:.0f}s")
    (OUT / "gen_features.json").write_text(json.dumps(gen))
    Xr = _matrix(rows)
    Xg = _matrix(gen)
    ok = ~np.all(np.isnan(np.vstack([Xr, Xg])), axis=0)
    names = [n for n, o in zip(NAMES, ok) if o]
    Xr, Xg = Xr[:, ok], Xg[:, ok]
    models = _models(a.seed)
    rep = {"auc": {}, "top_d": {}, "medians": {}}
    for art in ARTISTS:
        mr = np.array([r["artist"] == art for r in rows])
        rep["medians"][art] = {"real": {n: float(np.nanmedian(Xr[mr, i])) for i, n in enumerate(names)}}
        for which in ("learned", "v3", "tree"):
            mg = np.array([g["which"] == which and (g["artist"] == art or which == "tree") for g in gen])
            if not mg.any():
                continue
            X = np.vstack([Xr[mr], Xg[mg]])
            y = np.array(["real"] * int(mr.sum()) + ["gen"] * int(mg.sum()))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                rep["auc"][f"{art}/{which}"] = {mn: pair_auc(mk, X, y, "real", "gen", a.repeats, a.seed)
                                                for mn, mk in models.items()}
                rep["top_d"][f"{art}/{which}"] = effect_sizes(X, y, names, "real", "gen", top=10)
            rep["medians"][art][which] = {n: float(np.nanmedian(Xg[mg, i])) if np.any(np.isfinite(Xg[mg, i]))
                                          else None for i, n in enumerate(names)}
    (OUT / "evaluate.json").write_text(json.dumps(rep, indent=1))
    L = ["| # | real vs | logreg AUC | forest AUC | top separating (d gen − real; medians real → gen) |",
         "|---|---|---|---|---|"]
    for k, (key, r) in enumerate(rep["auc"].items(), 1):
        L.append(f"| E{k} | {key} | {r['logreg']['auc']:.3f} | {r['forest']['auc']:.3f} | " +
                 "; ".join(f"`{t['feature']}` {t['d']:+.1f} ({t['a']:.3g}→{t['b']:.3g})"
                           for t in rep["top_d"][key][:6]) + " |")
    KEYS = ["top_end_T", "top_end_L", "top_end_near", "top_end_free", "top_x_per_ink", "top_par_pairs",
            "top_par_ink", "top_kiss_per_ink", "top_closed", "top_cells_per_ink", "top_deg_contact",
            "top_isolated", "top_comp_largest", "top_len_max_frac", "top_cover", "top_entropy", "top_centre"]
    L += ["", "| # | artist | set | " + " | ".join(k.replace("top_", "") for k in KEYS) + " |",
          "|---|---|---|" + "---|" * len(KEYS)]
    k = 0
    for art, sets in rep["medians"].items():
        for sname, med in sets.items():
            k += 1
            L.append(f"| K{k} | {art} | {sname} | " + " | ".join(_fmt(med.get(n)) for n in KEYS) + " |")
    (OUT / "evaluate.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ---------------------------------------------------------------------------
# sheets
# ---------------------------------------------------------------------------

def _render(d: Drawing, side: int, lw: float = 2.0) -> np.ndarray:
    W, H = d.size
    s = side / max(W, H)
    from gesture.core import Stroke
    dd = Drawing([Stroke(st.points * s) for st in d.strokes], size=(max(int(W * s), 1), max(int(H * s), 1)))
    return synth.render(dd, line_width=lw, paper_noise=0.0, blur_sigma=0.5, use_stroke_width=False)


def _sheet(drawings, path: Path, cols: int, cell: int, labels=None, lw=2.0):
    from PIL import Image, ImageDraw
    rows = (len(drawings) + cols - 1) // cols
    canvas = Image.new("L", (cols * cell, rows * cell), 255)
    dr = ImageDraw.Draw(canvas)
    for i, d in enumerate(drawings):
        img = Image.fromarray(_render(d, cell - 16, lw))
        x, y = (i % cols) * cell, (i // cols) * cell
        canvas.paste(img, (x + (cell - img.width) // 2, y + (cell - img.height) // 2))
        dr.rectangle([x, y, x + cell - 1, y + cell - 1], outline=200)
        if labels:
            dr.text((x + 6, y + 4), labels[i], fill=90)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(path, quality=88)
    return path


def _in_hand(d: Drawing, g, rng, amount: float = 0.5) -> tuple[Drawing, str]:
    """Each structural line redrawn in hand g, at the structure's own R.
    restyle.py (another module, possibly in flux) when it imports and runs,
    else grammar_v3_frozen.restyle (ends pinned, so T-junctions survive)."""
    from gesture.core import Stroke
    R = d.meta.get("ref_length_gen") or d.ref_length()
    try:
        from gesture import restyle as rs
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = rs.restyle_drawing(d, g, amount=amount, seed=int(rng.integers(1 << 30)), ref_length=R)
        return out, f"restyle.py gauss/chain amount {amount}"
    except Exception as e:  # noqa: BLE001 — fall back to the frozen grammar's restyle
        print("restyle.py unavailable:", type(e).__name__, e)
    out = []
    for st in d.strokes:
        if st.length() < 0.03 * R:
            out.append(st)
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ns = gm.restyle(st.points, g, rng, ref_length=R)
            out.append(Stroke(ns.points, meta=st.meta))
        except Exception:  # noqa: BLE001 — a failed restyle keeps the skeleton line
            out.append(st)
    return Drawing(out, source=d.source + ":hand", size=d.size, meta=d.meta), "grammar_v3_frozen.restyle"


def cmd_sheets(a):
    from PIL import Image
    S = OUT / "sheets"
    side = 1200
    # 1. learned structures per artist (3 × 4)
    ds, lab = [], []
    for art in ARTISTS:
        m = tp.TopologyModel.load(OUT / f"model_{art}.json")
        for i in range(4):
            rng = np.random.default_rng(a.seed * 100 + i + 17 * ARTISTS.index(art))
            ds.append(tp.generate_structure(m, rng, (1000, 1250), kind="learned"))
            lab.append(f"{art} learned #{i}")
    p1 = _sheet(ds, S / "learned.jpg", 4, side // 4 * 2 // 2 * 1, lab)
    # 2. oehlen trees, complexity sweep (rows: depth 3 / 4 / 5; cols: fill .6 / .75 / .9 + 1 seed)
    ds, lab = [], []
    for depth in (3, 4, 5):
        for j, (fill, trunks) in enumerate(((0.7, 1), (0.85, 1), (0.95, 2), (0.95, 3))):
            rng = np.random.default_rng(a.seed * 1000 + depth * 10 + j)
            ds.append(tp.generate_structure(None, rng, (1100, 1100), kind="oehlen_tree",
                                            depth=depth, fill=fill, trunks=trunks))
            lab.append(f"depth {depth} fill {fill} trunks {trunks}")
    p2 = _sheet(ds, S / "trees.jpg", 4, 300, lab)
    # 3. in a hand: tree + learned structure, skeleton vs Matisse vs Hokusai hand
    gM = gm.Grammar.load(GRAMMARS / "grammar_matisse.json")
    gH = gm.Grammar.load(GRAMMARS / "grammar_hokusai.json")
    ds, lab = [], []
    bases = [tp.generate_structure(None, np.random.default_rng(a.seed + 5), (1100, 1100), kind="oehlen_tree",
                                   depth=4, fill=0.8, trunks=1),
             tp.generate_structure(tp.TopologyModel.load(OUT / "model_matisse.json"),
                                   np.random.default_rng(a.seed + 6), (1000, 1250), kind="learned")]
    for bi, b in enumerate(bases):
        hm, how = _in_hand(b, gM, np.random.default_rng(1))
        hh, _ = _in_hand(b, gH, np.random.default_rng(2))
        print("hand via", how)
        ds += [b, hm, hh]
        lab += [f"structure {bi}", f"structure {bi} · Matisse hand", f"structure {bi} · Hokusai hand"]
    p3 = _sheet(ds, S / "in_hand.jpg", 3, 400, lab, lw=1.6)
    # big single views for LOOK
    for name, d in (("tree_big", bases[0]), ("tree_big_matisse", ds[1]), ("learned_big", bases[1])):
        Image.fromarray(_render(d, side)).save(S / f"{name}.png")
    print(p1, p2, p3)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["measure", "compare", "evaluate", "sheets"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--keep", action="store_true", help="evaluate: save generated drawings")
    a = ap.parse_args(argv)
    {"measure": cmd_measure, "compare": cmd_compare, "evaluate": cmd_evaluate, "sheets": cmd_sheets}[a.cmd](a)


if __name__ == "__main__":
    main()
