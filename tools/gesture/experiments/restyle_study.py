"""Restyle-as-translation study (results/restyle-2026-10-16.md).

Subcommands (run from tools/gesture):

  grid     every source × decomposition × re-synthesis × amount × hand:
           structure distance + panel features of the output; a hand
           classifier trained on real long-stroke drawings scores which hand
           each output reads as. Writes grid.json / grid.md / tradeoff.jpg.
  sheets   population sheets for the chosen method (rows = sources,
           columns = original then each hand at 2 amounts), a slider sheet
           and a method-comparison sheet.
  topo     restyle a few gesture.topology outputs, if that module exists.

    ../../.local/gesture/.venv/bin/python -m experiments.restyle_study grid
    ../../.local/gesture/.venv/bin/python -m experiments.restyle_study sheets

  delta    v4 vs v3: re-run a few cells with the FROZEN v4 grammar and compare
           to the v3 rows of the grid cache (key texture features, structure
           distance, junction gaps). Writes delta_v4.md / delta_v4.json.

Outputs: .local/gesture/out/restyle/. Grammars: since the composite round the
frozen v4 JSONs in .local/gesture/out/grammar_v4_frozen/ (the v3 grid in
grid_rows.jsonl was made with grammar_v3_frozen + grammar_v2/).
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

from gesture import grammar_v4_frozen as gm  # noqa: E402
from gesture import medium, panel, synth  # noqa: E402
from gesture import restyle as rs  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
EXTRACT = ROOT / ".local/gesture/out/extract_hybrid"
GRAMMARS = ROOT / ".local/gesture/out/grammar_v4_frozen"
OUT = ROOT / ".local/gesture/out/restyle"
ARTISTS = ("matisse", "hokusai", "ingres")
AMOUNTS = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
JOBS = max(1, min(3, (os.cpu_count() or 2) - 2))   # shared machine
TEXTURE_GROUPS = ("k", "ext", "infl", "turn", "cl")   # len_/rel_ belong to the structure
KEY = ("cl_corner_rate", "cl_segs_per_stroke", "k_q50", "k_q90", "ext_rate", "infl_rate",
       "turn_tcorr_10", "turn_net_ratio")

_G: dict = {}


def grammar(art: str):
    if art not in _G:
        _G[art] = gm.Grammar.load(GRAMMARS / f"grammar_{art}.json")
    return _G[art]


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------

def _arc(p, h, L, k, step=1.0):
    n = max(int(L / step), 2)
    s = np.linspace(0, L, n + 1)
    th = h + k * s
    ds = np.diff(s)
    mid = 0.5 * (th[1:] + th[:-1])
    pts = np.vstack([p, p + np.cumsum(np.column_stack([np.cos(mid), np.sin(mid)]) * ds[:, None], axis=0)])
    return pts, th[-1]


def src_primitives() -> Drawing:
    t = np.linspace(0, 2 * np.pi, 500, endpoint=False)
    circle = Stroke(np.column_stack([270 + 190 * np.cos(t), 280 + 190 * np.sin(t)]), closed=True)
    ell = Stroke(np.column_stack([730 + 210 * np.cos(t), 270 + 110 * np.sin(t)]), closed=True)
    ts = np.linspace(0, 5 * np.pi, 2000)
    rr = 20 + 160 * ts / (5 * np.pi)
    spiral = Stroke(np.column_stack([520 + rr * np.cos(ts), 720 + rr * np.sin(ts)]))
    return Drawing([circle, ell, spiral], source="primitives", size=(1000, 1000))


def src_tree(seed: int = 4) -> Drawing:
    """Oehlen-ish tree: a trunk forks recursively; the main line carries on
    through every fork (one contiguous stroke), each side branch is its own
    stroke starting on its parent (T-junction)."""
    rng = np.random.default_rng(seed)
    strokes: list[Stroke] = []

    def limb(p, h, L, depth):
        pts = [np.asarray(p, float)[None, :]]
        cur, head = np.asarray(p, float), h
        while True:
            seg, head = _arc(cur, head, L, rng.normal(0, 1.2 / L))
            pts.append(seg[1:])
            cur = seg[-1]
            if depth == 0:
                break
            side = rng.choice([-1, 1])
            limb(cur, head + side * rng.uniform(0.45, 0.9), 0.72 * L, depth - 1)
            head -= side * rng.uniform(0.1, 0.35)
            L *= 0.78
            depth -= 1
        strokes.append(Stroke(np.vstack(pts)))

    limb((500, 960), -np.pi / 2, 230, 5)
    return Drawing(strokes[::-1], source="tree", size=(1000, 1000))


def src_dense(seed: int = 9) -> Drawing:
    """Dense multi-line: 12 nested wobbly closed contours (a topographic knot)."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 2 * np.pi, 900, endpoint=False)
    out = []
    for i in range(12):
        r0 = 50 + 34 * i
        wob = sum(rng.normal(0, 0.06) * np.cos(m * t + rng.uniform(0, 2 * np.pi)) for m in (2, 3, 5))
        r = r0 * (1 + wob)
        c = np.array([500, 500]) + rng.normal(0, 6, 2)
        out.append(Stroke(np.column_stack([c[0] + r * np.cos(t), c[1] + 0.85 * r * np.sin(t)]),
                          closed=True))
    return Drawing(out, source="dense", size=(1000, 1000))


def src_synth() -> Drawing:
    return synth.scene_matisse_like(np.random.default_rng(5), 1000, n_strokes=6)


def real_sources(per_artist: int = 2) -> dict[str, Drawing]:
    out = {}
    for art in ARTISTS:
        cands = []
        for p in sorted((EXTRACT / art).glob("*.json")):
            d = gm.long_drawing(Drawing.load(p))
            if 8 <= len(d.strokes) <= 45:
                cands.append((abs(len(d.strokes) - 18), p.stem, d))
        cands.sort(key=lambda x: (x[0], x[1]))
        for _, stem, d in cands[:per_artist]:
            out[f"{art}:{stem}"] = d
    return out


def sources() -> dict[str, Drawing]:
    s = {"primitives": src_primitives(), "synth_matisse_like": src_synth(), "tree": src_tree(),
         "dense": src_dense()}
    s.update(real_sources())
    return s


# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------

def w_common() -> float:
    """One line width (R units) for every measured output, so the panel's σ
    floor does not depend on the target hand (the σ/w confound)."""
    ws = []
    for art in ARTISTS:
        ws += [d["w_over_R"] for d in grammar(art).drawings if d["w_over_R"] > 0]
    return float(np.median(ws))


def with_width(d: Drawing, wr: float) -> Drawing:
    R = d.ref_length()
    return Drawing([Stroke(s.points, width=np.full(len(s), wr * R), closed=s.closed) for s in d.strokes
                    if len(s) >= 2], source=d.source, size=d.size)


def feats(d: Drawing) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _ = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W)
    return f


def _junction_gap(src: Drawing, out: Drawing) -> float:
    """Max distance (/R) from a source junction end's restyled position to its
    restyled host (0 = every junction welded)."""
    R = src.ref_length()
    J = rs.find_junctions(src, R)
    if not J:
        return 0.0
    g = []
    for i, e, j, _u in J:
        p = out.strokes[i].points[e]
        q = out.strokes[j].points
        g.append(float(np.min(np.linalg.norm(q - p, axis=1))))
    return max(g) / R


def _real_job(args):
    art, path = args
    d = gm.long_drawing(Drawing.load(path))
    if len(d.strokes) < 2:
        return None
    return art, Path(path).stem, feats(d)


def _grid_job(args):
    name, d, method, source, amount, hand, seed, wr = args
    t0 = time.time()
    o = rs.restyle_drawing(d, grammar(hand), amount=amount, seed=seed, method=method, source=source)
    dt = time.time() - t0
    sd = rs.structure_distance(d, o)
    pe = [s.meta.get("restyle", {}).get("pin_err", 0.0) for s in o.strokes]
    return {"src": name, "method": method, "source": source, "amount": amount, "hand": hand,
            "seed": seed, "d_mean": sd["mean"], "d_frechet": sd["frechet"], "time": dt,
            "junction_gap_R": _junction_gap(d, o),
            "pin_err_max_R": float(max(pe) / d.ref_length()) if pe else 0.0,
            "feats": feats(with_width(o, wr))}


def _gen_job(args):
    hand, seed, wr = args
    g = grammar(hand)
    d = gm.generate_drawing(g, np.random.default_rng(seed), (1000, 1000))
    return hand, feats(with_width(d, wr))


def _key(j) -> str:
    name, _d, m, so, amt, hand, seed, _wr = j
    return f"{name}|{m}|{so}|{amt:g}|{hand}|{seed}"


def run_cached(jobs, path: Path) -> list[dict]:
    """Run grid jobs in a process pool, appending each finished row to a
    JSONL cache so an interrupted run resumes where it stopped."""
    from concurrent.futures import as_completed
    done = {}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                r = json.loads(line)
                done[r["key"]] = r
            except Exception:  # noqa: BLE001 — a torn last line
                pass
    todo = [j for j in jobs if _key(j) not in done]
    print(f"grid: {len(done)} cached, {len(todo)} to run", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(JOBS) as ex, open(path, "a") as fh:
        futs = {ex.submit(_grid_job, j): _key(j) for j in todo}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            r["key"] = futs[f]
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            done[r["key"]] = r
            if i % 50 == 0:
                print(f"  {i}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    return [done[_key(j)] for j in jobs]


class HandClassifier:
    """Logistic regression on texture-group panel features of real
    long-stroke drawings, standard preprocessing (σ ≥ 7 w + medium
    projection), geometry only."""

    def __init__(self, real: list[tuple[str, str, dict]], seed: int = 0):
        from sklearn.linear_model import LogisticRegression
        allk = set.intersection(*[set(f) for _a, _s, f in real])
        self.names = sorted(n for n in allk if panel.group_of(n) in TEXTURE_GROUPS)
        X = self.matrix([f for _a, _s, f in real])
        ok = ~np.all(np.isnan(X), axis=0)
        self.names = [n for n, o in zip(self.names, ok) if o]
        X = X[:, ok]
        art = np.array([a for a, _s, _f in real])
        lut = medium.load_media()
        med = np.array([lut.get((a, s), "unknown") for a, s, _f in real])
        self.pj = medium.MediumProjector(medium.load_pairs(), seed=seed).fit(X, art, med)
        self.Z, self.y = self.pj.transform(X), art
        self.clf = LogisticRegression(C=0.3, max_iter=5000).fit(self.Z, self.y)
        self.classes = list(self.clf.classes_)

    def matrix(self, fs: list[dict]) -> np.ndarray:
        return np.array([[f.get(n, np.nan) for n in self.names] for f in fs], dtype=float)

    def proba(self, fs: list[dict]) -> np.ndarray:
        return self.clf.predict_proba(self.pj.transform(self.matrix(fs)))

    def cv_accuracy(self, seed=0) -> float:
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import StratifiedKFold, cross_val_predict
        p = cross_val_predict(LogisticRegression(C=0.3, max_iter=5000), self.Z, self.y,
                              cv=StratifiedKFold(5, shuffle=True, random_state=seed))
        return float(np.mean(p == self.y))


def _auc_block(rows, P, classes):
    from sklearn.metrics import roc_auc_score
    tgt = np.array([r["hand"] for r in rows])
    aucs = {}
    for j, c in enumerate(classes):
        y = tgt == c
        aucs[c] = float(roc_auc_score(y, P[:, j])) if 0 < y.sum() < len(y) else float("nan")
    acc = float(np.mean(np.array(classes)[P.argmax(axis=1)] == tgt))
    srcart = np.array([r["src"].split(":")[0] for r in rows])
    cross = np.isin(srcart, ARTISTS) & (srcart != tgt)
    xacc = float(np.mean(np.array(classes)[P[cross].argmax(axis=1)] == tgt[cross])) if cross.any() else float("nan")
    return aucs, acc, xacc


def cmd_grid(a):
    OUT.mkdir(parents=True, exist_ok=True)
    wr = w_common()
    t0 = time.time()
    with ProcessPoolExecutor(JOBS) as ex:
        real = [r for r in ex.map(_real_job, [(art, str(p)) for art in ARTISTS
                                              for p in sorted((EXTRACT / art).glob("*.json"))]) if r]
    hc = HandClassifier(real)
    cv = hc.cv_accuracy()
    print(f"classifier: {len(real)} real, {len(hc.names)} texture features, CV acc {cv:.3f} "
          f"({time.time() - t0:.0f}s)")
    S = sources()
    methods = a.methods.split(",")
    srcs = a.sources.split(",")
    jobs = []
    for name, d in S.items():
        jobs.append((name, d, "gauss", "chain", 0.0, ARTISTS[0], a.seed, wr))
        for m in methods:
            for so in srcs:
                for amt in AMOUNTS[1:]:
                    for hand in ARTISTS:
                        jobs.append((name, d, m, so, amt, hand, a.seed, wr))
    jobs.sort(key=lambda j: -len(j[1].strokes))
    rows = run_cached(jobs, OUT / "grid_rows.jsonl")
    with ProcessPoolExecutor(JOBS) as ex:
        gens = list(ex.map(_gen_job, [(h, 100 + i, wr) for h in ARTISTS for i in range(a.n_gen)]))
    # amount 0 is target-independent: replicate for each hand
    base = [r for r in rows if r["amount"] == 0.0]
    rows = [r for r in rows if r["amount"] > 0]
    for r in base:
        for m in methods:
            for so in srcs:
                for hand in ARTISTS:
                    rows.append({**r, "method": m, "source": so, "hand": hand})
    P = hc.proba([r["feats"] for r in rows])
    for r, p in zip(rows, P):
        r["p"] = {c: float(v) for c, v in zip(hc.classes, p)}
    Pg = hc.proba([f for _h, f in gens])
    gen_rows = [{"hand": h, "src": "generated"} for h, _f in gens]
    g_auc, g_acc, _ = _auc_block(gen_rows, Pg, hc.classes)
    rep = {"w_common": wr, "classifier": {"n_real": len(real), "n_features": len(hc.names),
                                          "cv_acc": cv, "classes": hc.classes},
           "ceiling_generated": {"auc": g_auc, "acc": g_acc, "n": len(gens)},
           "sources": {k: len(v.strokes) for k, v in S.items()}, "cells": []}
    for m in methods:
        for so in srcs:
            for amt in AMOUNTS:
                sel = [i for i, r in enumerate(rows) if r["method"] == m and r["source"] == so
                       and r["amount"] == amt]
                rr = [rows[i] for i in sel]
                aucs, acc, xacc = _auc_block(rr, P[sel], hc.classes)
                cell = {"method": m, "source": so, "amount": amt,
                        "d_mean": float(np.median([r["d_mean"] for r in rr])),
                        "d_frechet": float(np.median([r["d_frechet"] for r in rr])),
                        "pin_err_max_R": float(np.max([r["pin_err_max_R"] for r in rr])),
                        "time_med": float(np.median([r["time"] for r in rr])),
                        "auc": aucs, "auc_macro": float(np.nanmean(list(aucs.values()))),
                        "acc": acc, "cross_acc": xacc, "key": {}}
                for hand in ARTISTS:
                    fs = [r["feats"] for r in rr if r["hand"] == hand]
                    cell["key"][hand] = {k: float(np.nanmedian([f.get(k, np.nan) for f in fs])) for k in KEY}
                rep["cells"].append(cell)
    rep["real_key"] = {art: {k: float(np.nanmedian([f.get(k, np.nan) for a_, _s, f in real if a_ == art]))
                             for k in KEY} for art in ARTISTS}
    rep["per_source"] = [{k: r[k] for k in ("src", "method", "source", "amount", "hand", "d_mean",
                                            "d_frechet", "p")} for r in rows]
    (OUT / "grid.json").write_text(json.dumps(rep, indent=1))
    md = grid_markdown(rep)
    (OUT / "grid.md").write_text(md)
    print(md)
    tradeoff_plot(rep, OUT / "tradeoff.jpg")


def grid_markdown(rep) -> str:
    L = [f"Classifier: {rep['classifier']['n_real']} real long-stroke drawings, "
         f"{rep['classifier']['n_features']} texture features, 5-fold CV acc "
         f"{rep['classifier']['cv_acc']:.3f} (chance 0.33). Ceiling (grammar's own drawings): "
         f"AUC M / H / I " + " / ".join(f"{rep['ceiling_generated']['auc'][h]:.2f}" for h in ARTISTS)
         + f", acc {rep['ceiling_generated']['acc']:.2f}.", "",
         "| # | method | resynth | amount | d_mean/R | Fréchet/R | AUC M / H / I | macro | acc | cross acc | s/drawing |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, c in enumerate(rep["cells"], 1):
        au = c["auc"]
        L.append(f"| T{i} | {c['method']} | {c['source']} | {c['amount']:.1f} | {c['d_mean']:.4f} | "
                 f"{c['d_frechet']:.4f} | {au.get('matisse', np.nan):.2f} / {au.get('hokusai', np.nan):.2f} / "
                 f"{au.get('ingres', np.nan):.2f} | {c['auc_macro']:.2f} | {c['acc']:.2f} | "
                 f"{c['cross_acc']:.2f} | {c['time_med']:.2f} |")
    return "\n".join(L) + "\n"


def tradeoff_plot(rep, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cols = {"chain": "#205EA6", "transplant": "#AD8301", "trace": "#AF3029"}
    ls = {"gauss": "-", "clothoid": "--", "anchors": ":"}
    fig, axes = plt.subplots(1, 4, figsize=(17, 4.4), sharey=True)
    for ax, hand in zip(axes, ("macro",) + ARTISTS):
        for m in ls:
            for so in cols:
                cs = [c for c in rep["cells"] if c["method"] == m and c["source"] == so]
                if not cs:
                    continue
                x = [c["d_mean"] for c in cs]
                y = [c["auc_macro"] if hand == "macro" else c["auc"][hand] for c in cs]
                ax.plot(x, y, ls[m], color=cols[so], marker="o", ms=3, label=f"{m}/{so}")
                for c, xi, yi in zip(cs, x, y):
                    if c["amount"] in (0.4, 1.0):
                        ax.annotate(f"{c['amount']:.1f}", (xi, yi), fontsize=6, alpha=0.6)
        ax.set_xscale("symlog", linthresh=1e-3)
        ax.axhline(0.5, color="#878580", lw=0.6)
        ax.set_title(f"hand AUC: {hand}")
        ax.set_xlabel("structure distance (mean, /R)")
    axes[0].set_ylabel("AUC (target hand vs others)")
    axes[-1].legend(fontsize=6, ncol=1, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=110, pil_kwargs={"quality": 85})
    plt.close(fig)


# ---------------------------------------------------------------------------
# sheets
# ---------------------------------------------------------------------------

def cell_image(d: Drawing, size: int, lw: float = 1.3) -> np.ndarray:
    pts = np.vstack([s.points for s in d.strokes if len(s)])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    m = 0.06 * size
    sc = (size - 2 * m) / max(float(np.max(hi - lo)), 1e-9)
    off = m + 0.5 * ((size - 2 * m) - (hi - lo) * sc)
    ss = [Stroke((s.points - lo) * sc + off, closed=s.closed) for s in d.strokes if len(s) >= 2]
    return synth.render(Drawing(ss, size=(size, size)), line_width=lw, paper_noise=0.0,
                        blur_sigma=0.4, use_stroke_width=False)


def _label(img: np.ndarray, text: str) -> np.ndarray:
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    ImageDraw.Draw(im).text((6, 4), text, fill=90)
    return np.asarray(im)


def _sheet_job(args):
    d, hand, amount, method, source, seed, size, label = args
    o = d if amount == 0 or hand is None else rs.restyle_drawing(
        d, grammar(hand), amount=amount, seed=seed, method=method, source=source)
    return _label(cell_image(o, size), label)


def _grid_sheet(rows_spec, path, size):
    """rows_spec: list of rows, each a list of job tuples."""
    from PIL import Image
    flat = [j for r in rows_spec for j in r]
    with ProcessPoolExecutor(JOBS) as ex:
        imgs = list(ex.map(_sheet_job, flat, chunksize=1))
    ncol = max(len(r) for r in rows_spec)
    sheet = np.full((size * len(rows_spec), size * ncol), 255, np.uint8)
    k = 0
    for i, r in enumerate(rows_spec):
        for j in range(len(r)):
            sheet[i * size:(i + 1) * size, j * size:(j + 1) * size] = imgs[k]
            sheet[i * size:(i + 1) * size, j * size] = 200
            k += 1
        sheet[i * size, :] = 200
    Image.fromarray(sheet).save(path, quality=88)
    print("wrote", path)


def cmd_sheets(a):
    OUT.mkdir(parents=True, exist_ok=True)
    S = sources()
    m, so, size = a.method, a.source, a.size
    amts = [float(x) for x in a.amounts.split(",")]
    names = [n for n in S if not n.endswith(tuple("0123456789"))] if False else list(S)
    groups = {"synthetic": [n for n in names if ":" not in n],
              "real": [n for n in names if ":" in n]}
    for gname, ns in groups.items():
        rows = []
        for n in ns:
            r = [(S[n], None, 0.0, m, so, a.seed, size, f"{n} (source)")]
            for hand in ARTISTS:
                for amt in amts:
                    r.append((S[n], hand, amt, m, so, a.seed, size, f"{hand} {amt:g}"))
            rows.append(r)
        _grid_sheet(rows, OUT / f"sheet-{gname}-{m}-{so}.jpg", size)
    # slider: two sources, each hand, amounts 0..1
    rows = []
    for n in a.slider.split(","):
        for hand in ARTISTS:
            rows.append([(S[n], hand, amt, m, so, a.seed, size, f"{hand} {amt:g}") for amt in AMOUNTS])
    _grid_sheet(rows, OUT / f"sheet-slider-{m}-{so}.jpg", size)
    # methods: one source into one hand at one amount
    rows = []
    for src_name, hand in ((a.slider.split(",")[0], "hokusai"), ("primitives", "matisse")):
        for meth in rs.METHODS:
            rows.append([(S[src_name], None, 0.0, meth, "chain", a.seed, size, f"{src_name}")] +
                        [(S[src_name], hand, 0.7, meth, sx, a.seed, size, f"{meth}/{sx} -> {hand} 0.7")
                         for sx in rs.SOURCES])
    _grid_sheet(rows, OUT / "sheet-methods.jpg", size)


def cmd_topo(a):
    try:
        from gesture import topology
    except Exception as e:  # noqa: BLE001
        print("no topology module:", e)
        return
    S = {}
    for i, kind in enumerate(("oehlen_tree", "learned")):
        try:
            S[f"topo_{kind}"] = topology.generate_structure(None, np.random.default_rng(11 + i), 1000,
                                                            kind=kind)
        except Exception as e:  # noqa: BLE001 — the module is someone else's work in progress
            print(f"topology {kind} failed: {e}")
    if not S:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, d in S.items():
        print(n, len(d.strokes), "strokes")
        r = [(d, None, 0.0, a.method, a.source, a.seed, a.size, f"{n} (structure)")]
        r += [(d, hand, amt, a.method, a.source, a.seed, a.size, f"{hand} {amt:g}")
              for hand in ARTISTS for amt in (0.5, 0.8)]
        rows.append(r)
    _grid_sheet(rows, OUT / f"sheet-topology-{a.method}-{a.source}.jpg", a.size)


def cmd_delta(a):
    """v4 re-run of a few grid cells, compared with the cached v3 rows."""
    OUT.mkdir(parents=True, exist_ok=True)
    wr = w_common()
    S = sources()
    names = [n for n in S if n in a.srcs.split(",")]
    amts = [float(x) for x in a.amounts.split(",")]
    jobs = [(n, S[n], "gauss", so, amt, h, a.seed, wr) for n in names for so in a.sources.split(",")
            for amt in amts for h in ARTISTS]
    rows4 = run_cached(jobs, OUT / "grid_rows_v4.jsonl")
    rows3 = [json.loads(x) for x in (OUT / "grid_rows.jsonl").read_text().splitlines() if x.strip()]
    rows3 = [r for r in rows3 if r["src"] in names and r["method"] == "gauss"]
    keys = ("cl_corner_rate", "k_q50", "turn_tcorr_10", "ext_rate")
    out = {"cells": []}
    L = ["| # | resynth | amount | grammar | d_mean/R | junction gap max /R | " + " | ".join(keys) + " | s/drawing |",
         "|---|---|---|---|---|---|" + "---|" * len(keys) + "---|"]
    k = 0
    for so in a.sources.split(","):
        for amt in amts:
            for tag, rr in (("v3", rows3), ("v4", rows4)):
                sel = [r for r in rr if r["source"] == so and abs(r["amount"] - amt) < 1e-9]
                if not sel:
                    continue
                k += 1
                med = {kk: float(np.nanmedian([r["feats"].get(kk, np.nan) for r in sel])) for kk in keys}
                cell = {"source": so, "amount": amt, "grammar": tag, "n": len(sel),
                        "d_mean": float(np.median([r["d_mean"] for r in sel])),
                        "gap": float(np.max([r.get("junction_gap_R", np.nan) for r in sel])),
                        "time": float(np.median([r["time"] for r in sel])), **med}
                out["cells"].append(cell)
                L.append(f"| D{k} | {so} | {amt:g} | {tag} | {cell['d_mean']:.4f} | {cell['gap']:.4f} | "
                         + " | ".join(f"{med[kk]:.2f}" for kk in keys) + f" | {cell['time']:.2f} |")
    real = json.loads((ROOT / ".local/gesture/out/composite/real_feats.json").read_text()) \
        if (ROOT / ".local/gesture/out/composite/real_feats.json").exists() else []
    if real:
        L.append("")
        for art in ARTISTS:
            L.append(f"real {art}: " + ", ".join(
                f"{kk} {np.nanmedian([f.get(kk, np.nan) for a_, _s, f in real if a_ == art]):.2f}" for kk in keys))
    md = f"Sources: {', '.join(names)}; gauss decomposition; medians over sources × hands; v4 rows weld junctions.\n\n" \
        + "\n".join(L) + "\n"
    (OUT / "delta_v4.md").write_text(md)
    (OUT / "delta_v4.json").write_text(json.dumps(out, indent=1))
    print(md)


def main(argv=None):
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    g = sp.add_parser("grid")
    g.add_argument("--methods", default=",".join(rs.METHODS))
    g.add_argument("--sources", default=",".join(rs.SOURCES))
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--n-gen", type=int, default=8)
    s = sp.add_parser("sheets")
    s.add_argument("--method", default="gauss")
    s.add_argument("--source", default="trace")
    s.add_argument("--amounts", default="0.5,0.8")
    s.add_argument("--slider", default="matisse:KKS1966-158,primitives")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--size", type=int, default=260)
    t = sp.add_parser("topo")
    t.add_argument("--method", default="gauss")
    t.add_argument("--source", default="trace")
    t.add_argument("--seed", type=int, default=1)
    t.add_argument("--size", type=int, default=260)
    dl = sp.add_parser("delta")
    dl.add_argument("--srcs", default="tree,dense,primitives,matisse:KKS1971-302,hokusai:57262")
    dl.add_argument("--sources", default="trace,chain")
    dl.add_argument("--amounts", default="0.4,0.6,0.8")
    dl.add_argument("--seed", type=int, default=1)
    a = p.parse_args(argv)
    {"grid": cmd_grid, "sheets": cmd_sheets, "topo": cmd_topo, "delta": cmd_delta}[a.cmd](a)


if __name__ == "__main__":
    main()
