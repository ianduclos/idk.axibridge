"""Dance → structure, drawn in hands (round 8). Library: gesture/dance.py.
Write-up: results/dance_structure-2026-10-16.md.

    ../../.local/gesture/.venv/bin/python -m experiments.dance_structure structures
    ../../.local/gesture/.venv/bin/python -m experiments.dance_structure measure
    ../../.local/gesture/.venv/bin/python -m experiments.dance_structure hands
    ../../.local/gesture/.venv/bin/python -m experiments.dance_structure regimes
    ../../.local/gesture/.venv/bin/python -m experiments.dance_structure limb

  structures  raw dance structures: trails / strobe / relative / graft /
              chimera / impossible tree, several sources → sheet
  measure     topology features of dance structures vs real drawings
              (topology/real.json) vs oehlen_tree vs learned structures
  hands       one structure per row: raw | Matisse | Hokusai | shikasta
  regimes     compose(structure=<dance Drawing>) with authored / noise
              fields and with the body's own kinematic field
  limb        the mantis (CMU 55_13) and friends in the shikasta hand,
              regimes from the body (stillness → mass, acc → nib, speed → wire)
  chimera     the limb, larger: two-animal chimera lines, shikasta, body regimes
  fieldview   diagnostic: the kinematic regime coloured along raw trails
Run from tools/gesture. ≤ 2 worker processes.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import dance as D  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / ".local/gesture/corpus/dance"
OUT = ROOT / ".local/gesture/out/dance_structure"
RESULTS = Path(__file__).resolve().parents[1] / "results"
JOBS = 2
SIZE = (840, 1200)
PAPER = (0xFF, 0xFC, 0xF0)
INK = (0x10, 0x0F, 0x0F)
BLUE, RED, GREEN, ORANGE = (0x43, 0x85, 0xBE), (0xD1, 0x4D, 0x41), (0x87, 0x9A, 0x39), (0xDA, 0x70, 0x2C)

SRC = {
    "mantis": ("cmu-55/55_13.amc", 20, 50),
    "hummingbird": ("cmu-55/55_05.amc", 0, 23),
    "dragon": ("cmu-55/55_19.amc", 5, 35),
    "hippo_ballerina": ("cmu-55/55_20.amc", 0, 30),
    "penguin": ("cmu-55/55_18.amc", 0, 30),
    "modern05": ("cmu-05/05_02.amc", 0, None),
    "modern49": ("cmu-49/49_09.amc", 0, 40),
    "levitation": ("e2-stocos/Levitation_FullBody_Take1_proc.bvh", 30, 70),
    "staccato": ("e2-stocos/Staccato_FullBody_Take1_proc.bvh", 30, 70),
    "outofbalance": ("e2-stocos/OutOfBalance_FullBody_Take1_proc.bvh", 20, 60),
    "particles": ("e2-stocos/Particles_FullBody_Take1_proc.bvh", 30, 70),
    "unusual_anna": ("e2mb-unusual/Anna_Raiola.bvh", 60, 100),
    "unusual_zachary": ("e2mb-unusual/Zachary_Chant_Take2.bvh", 60, 100),
}


def motion(key: str, fps_out: float = 60.0) -> D.Motion:
    rel, t0, t1 = SRC[key]
    m = D.load(CORPUS / rel, t0, t1, fps_out=fps_out)
    return D.Motion(m.names, m.parents, m.pos, m.fps, key, m.meta)


# ---------------------------------------------------------------------------
# structures
# ---------------------------------------------------------------------------

WIN = 15.0      # seconds per trail structure: longer windows overdraw into scribble (hatching by another route)


def structure(kind: str, key: str, seed: int = 0, key2: str | None = None) -> Drawing:
    m = motion(key)
    if kind in ("trails", "trails_top", "trails_hands", "relative"):
        m = m.window(0, WIN)
    if kind == "trails":
        return D.trails(m, view="front")
    if kind == "trails_top":
        return D.trails(m, view="top")
    if kind == "trails_hands":
        return D.trails(m, ("lhand", "rhand"), view="pca")
    if kind == "strobe":
        return D.strobe(m, n=9, spread=0.32)
    if kind == "relative":
        return D.relative(m, (("lhand", "rfoot"), ("rhand", "lfoot"), ("head", "lhand")))
    if kind == "graft":
        return D.graft(motion(key2 or "levitation"), m)
    if kind == "chimera":
        rng = np.random.default_rng(seed)
        pieces = []
        for k in ([key] + ([key2] if key2 else [])):
            pieces += D.pieces_at_minima(D.trails(motion(k), view="front", cut="none"), min_frac=0.03)
        return D.chimera(pieces, rng, n_lines=3, per_line=9)
    if kind == "tree":
        return D.impossible_tree(m.window(0, 12), depth=4, branching=2, seed=seed, gain=0.15, spread=0.5,
                                 n_tips=6)
    if kind == "tree_strobe":
        return D.impossible_tree(m.window(0, 6), depth=4, branching=2, seed=seed, gain=0.15, spread=0.5,
                                 strobe_n=4, n_tips=4, cut="none")
    raise ValueError(kind)


def render(d: Drawing, scale: float = 0.5, ss: int = 2, lw: float = 1.6, color=INK, img=None, field=None):
    """Polylines on paper (numpy RGB). Optional per-point colour field: a
    function (stroke) → (N,) r values, coloured line/nib/mass by Flexoki."""
    from PIL import Image, ImageDraw
    W, H = d.size
    w, h = int(W * scale), int(H * scale)
    im = Image.new("RGB", (w * ss, h * ss), PAPER) if img is None else img
    dr = ImageDraw.Draw(im)
    for s in d.strokes:
        p = s.points
        if s.closed:
            p = np.vstack([p, p[:1]])
        q = [tuple(v) for v in p * scale * ss]
        if field is None:
            dr.line(q, fill=color, width=max(int(lw * ss), 1), joint="curve")
        else:
            r = field(s)
            cols = [INK if x < 0.5 else (BLUE if x < 1.5 else RED) for x in r]
            for i in range(len(q) - 1):
                wv = lw * (1 + 1.5 * r[i])
                dr.line([q[i], q[i + 1]], fill=cols[i], width=max(int(wv * ss), 1))
    return im


def finish(im, scale=0.5):
    from PIL import Image
    w, h = im.size
    return np.asarray(im.resize((w // 2, h // 2), Image.Resampling.LANCZOS))


def label(arr, text, size=13):
    from PIL import Image, ImageDraw
    im = Image.fromarray(arr)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, im.width, size + 6], fill="#F2F0E5")
    d.text((4, 3), text, fill=INK)
    return np.asarray(im)


def grid(cells, ncol: int, path: Path, quality: int = 82, max_kb: int = 900, title: str | None = None):
    from PIL import Image, ImageDraw
    h = max(c.shape[0] for c in cells)
    w = max(c.shape[1] for c in cells)
    nrow = (len(cells) + ncol - 1) // ncol
    top = 26 if title else 0
    sheet = np.full((h * nrow + top, w * ncol, 3), 200, np.uint8)
    for k, im in enumerate(cells):
        i, j = divmod(k, ncol)
        y = top + i * h
        sheet[y:y + im.shape[0], j * w:j * w + im.shape[1]] = im
        sheet[y:y + h, j * w] = 160
        sheet[y, j * w:(j + 1) * w] = 160
    img = Image.fromarray(sheet)
    if title:
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, img.width, top], fill="#E6E4D9")
        d.text((6, 6), title, fill=INK)
    path.parent.mkdir(parents=True, exist_ok=True)
    q = quality
    while True:
        img.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024 or q <= 40:
            break
        q -= 8
    print("wrote", path, f"{path.stat().st_size / 1024:.0f} KB (q{q})", flush=True)


def _structure_cell(spec):
    kind, key, seed, key2 = spec
    t = time.perf_counter()
    d = structure(kind, key, seed, key2)
    OUT.mkdir(parents=True, exist_ok=True)
    tag = f"{kind}-{key}" + (f"+{key2}" if key2 else "") + f"-s{seed}"
    d.save(OUT / "structures" / f"{tag}.json")
    img = finish(render(d, 0.4, lw=1.4))
    txt = f"{kind} · {key}" + (f" + {key2}" if key2 else "") + f" · {len(d.strokes)} lines"
    return label(img, txt), tag, round(time.perf_counter() - t, 2)


STRUCT_SPECS = [
    ("trails", "levitation", 0, None), ("trails", "staccato", 0, None), ("trails", "unusual_anna", 0, None),
    ("trails", "mantis", 0, None), ("trails_top", "outofbalance", 0, None), ("trails_hands", "hummingbird", 0, None),
    ("strobe", "modern05", 0, None), ("strobe", "mantis", 0, None), ("relative", "particles", 0, None),
    ("relative", "dragon", 0, None), ("graft", "mantis", 0, "levitation"), ("graft", "hummingbird", 0, "unusual_zachary"),
    ("chimera", "mantis", 1, "staccato"), ("chimera", "hippo_ballerina", 2, "modern49"),
    ("tree", "levitation", 3, None), ("tree", "mantis", 4, None), ("tree_strobe", "staccato", 5, None),
    ("tree", "unusual_anna", 6, None),
]


def cmd_structures(a):
    specs = STRUCT_SPECS if not a.only else [s for s in STRUCT_SPECS if s[0] in a.only.split(",")]
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_structure_cell, specs))
    for _, tag, sec in res:
        print(f"  {tag}: {sec}s")
    grid([r[0] for r in res], 6, RESULTS / "dance_structure-structures.jpg",
         title="Dance -> structure (raw, no hand). Rows: M1 trails | strobe / relative / graft | "
               "chimera / impossible tree. CMU 55 = human miming animals; Stocos/E2 = contemporary.")


# ---------------------------------------------------------------------------
# measure
# ---------------------------------------------------------------------------

def _feat_job(spec):
    from gesture import topology as tp
    kind, key, seed, key2 = spec
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if kind == "oehlen_tree":
            d = tp.generate_structure(None, np.random.default_rng(seed), SIZE, kind="oehlen_tree", trunks=1 + seed % 3)
        else:
            d = structure(kind, key, seed, key2)
        return {"kind": kind, "key": key, "key2": key2, "seed": seed, "f": tp.topology_features(d)}


MEASURE_SPECS = (
    [("trails", k, 0, None) for k in ("levitation", "staccato", "outofbalance", "particles", "unusual_anna",
                                       "unusual_zachary", "modern05", "modern49")]
    + [("trails", k, 0, None) for k in ("mantis", "hummingbird", "dragon", "hippo_ballerina", "penguin")]
    + [("strobe", k, 0, None) for k in ("levitation", "modern05", "mantis", "dragon")]
    + [("relative", k, 0, None) for k in ("particles", "dragon", "staccato", "mantis")]
    + [("graft", "mantis", 0, "levitation"), ("graft", "hummingbird", 0, "unusual_zachary"),
       ("graft", "dragon", 0, "staccato"), ("graft", "penguin", 0, "outofbalance")]
    + [("chimera", k, s, k2) for k, s, k2 in (("mantis", 1, "staccato"), ("hippo_ballerina", 2, "modern49"),
                                              ("levitation", 3, "dragon"), ("particles", 4, None))]
    + [("tree", k, s, None) for k, s in (("levitation", 3), ("mantis", 4), ("unusual_anna", 6), ("staccato", 7))]
    + [("oehlen_tree", "-", s, None) for s in range(8)]
)

GROUP = {"trails": "dance trails", "strobe": "strobe", "relative": "relative", "graft": "non-human ops",
         "chimera": "non-human ops", "tree": "non-human ops", "oehlen_tree": "oehlen tree"}
ANIMAL = {"mantis", "hummingbird", "dragon", "hippo_ballerina", "penguin"}


def cmd_measure(a):
    OUT.mkdir(parents=True, exist_ok=True)
    if a.only == "report":
        report(json.loads((OUT / "features.json").read_text()))
        return
    with ProcessPoolExecutor(JOBS) as ex:
        rows = list(ex.map(_feat_job, MEASURE_SPECS))
    real = json.loads((ROOT / ".local/gesture/out/topology/real.json").read_text())
    gen = json.loads((ROOT / ".local/gesture/out/topology/gen_features.json").read_text())
    for r in real:
        rows.append({"kind": "real", "key": r["artist"], "seed": 0, "f": r["f"]})
    for r in gen:
        rows.append({"kind": "gen:" + str(r["which"]), "key": r["artist"], "seed": r["seed"], "f": r["f"]})
    (OUT / "features.json").write_text(json.dumps(rows))
    print("rows", len(rows))
    report(rows)


def _group(r):
    if r["kind"] == "real":
        return "real " + r["key"]
    if r["kind"].startswith("gen:"):
        return "gen " + r["kind"][4:]
    if r["kind"] == "trails":
        return "trails animal-mime" if r["key"] in ANIMAL else "trails dance"
    return GROUP[r["kind"]]


def report(rows):
    from gesture import topology as tp
    names = [k for k in tp.FEATURES if k not in tp.DESCRIPTIVE and k not in ("top_n_strokes", "top_ink")]
    X = np.array([[r["f"].get(k, np.nan) for k in names] for r in rows], float)
    g = np.array([_group(r) for r in rows])
    # impute NaN by column median, standardise on the real drawings
    med = np.nanmedian(X, axis=0)
    X = np.where(np.isfinite(X), X, med)
    realm = np.array([s.startswith("real") for s in g])
    # centre on the real drawings, scale by the POOLED spread (several features
    # are constant on real drawings, e.g. self-crossings = 0, and would explode)
    mu, sd = X[realm].mean(0), X.std(0) + 1e-6
    Z = (X - mu) / sd
    groups = list(dict.fromkeys(g))
    cent = {k: Z[g == k].mean(0) for k in groups}
    lines = ["# dance_structure — topology features (centred on real drawings, pooled-sd units)", "",
             "| # | group | n | dist to real centroid | nearest other group |", "|---|---|---|---|---|"]
    rc = Z[realm].mean(0)
    for i, k in enumerate(groups, 1):
        others = sorted(((np.linalg.norm(cent[k] - cent[o]), o) for o in groups if o != k))
        lines.append(f"| {i} | {k} | {int(np.sum(g == k))} | {np.linalg.norm(cent[k] - rc):.2f} | "
                     f"{others[0][1]} ({others[0][0]:.2f}) |")
    # PCA on real + dance + oehlen
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    pca = PCA(2).fit(Z)
    P = pca.transform(Z)
    # separability: dance (all non-real, non-gen, non-oehlen) vs real; vs oehlen
    dance = np.array([not (s.startswith("real") or s.startswith("gen") or s == "oehlen tree") for s in g])
    oeh = g == "oehlen tree"
    out = {}
    for nm, other in (("real", realm), ("oehlen", oeh)):
        m = dance | other
        y = dance[m].astype(int)
        clf = LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced")
        cv = min(5, int(min(y.sum(), (1 - y).sum())))
        out[nm] = float(np.mean(cross_val_score(clf, Z[m], y, cv=cv, scoring="roc_auc")))
    lines += ["", f"logreg AUC dance-structures vs real drawings: {out['real']:.2f}; vs oehlen trees: {out['oehlen']:.2f}",
              "", "## Feature medians (raw units)", "",
              "| feature | " + " | ".join(groups) + " |", "|---|" + "---|" * len(groups)]
    Xr = np.array([[r["f"].get(k, np.nan) for k in names] for r in rows], float)
    for j, k in enumerate(names):
        vals = [np.nanmedian(Xr[g == q, j]) if np.any(np.isfinite(Xr[g == q, j])) else np.nan for q in groups]
        lines.append(f"| {k} | " + " | ".join(f"{v:.3g}" for v in vals) + " |")
    # most distinctive features dance vs real (|z| of centroid)
    dz = Z[dance].mean(0) - Z[realm].mean(0)
    top = np.argsort(-np.abs(dz))[:10]
    lines += ["", "## Dance vs real: largest centroid shifts (pooled-sd units)", ""]
    lines += [f"{i + 1}. {names[j]}: {dz[j]:+.2f}" for i, j in enumerate(top)]
    (OUT / "measure.md").write_text("\n".join(lines))
    print("\n".join(lines[:40]))
    scatter(P, g, groups, pca)


def scatter(P, g, groups, pca):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    col = {"real matisse": "#100F0F", "real hokusai": "#6F6E69", "real ingres": "#B7B5AC",
           "oehlen tree": "#879A39", "trails dance": "#4385BE", "trails animal-mime": "#DA702C",
           "strobe": "#8B7EC8", "relative": "#3AA99F", "non-human ops": "#D14D41"}
    fig, ax = plt.subplots(figsize=(7.5, 6), dpi=110)
    fig.patch.set_facecolor("#FFFCF0")
    ax.set_facecolor("#FFFCF0")
    for k in groups:
        m = g == k
        c = col.get(k, "#CECDC3")
        if k.startswith("gen"):
            ax.scatter(P[m, 0], P[m, 1], s=8, c="#DAD8CE", marker="x", label=k)
        else:
            ax.scatter(P[m, 0], P[m, 1], s=26 if not k.startswith("real") else 14, c=c, label=k,
                       edgecolors="none", alpha=0.9)
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.0%})")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.0%})")
    ax.set_title("Structure space: 40 topology features, PCA (centred on real drawings, pooled sd)", fontsize=10)
    ax.legend(fontsize=7, frameon=False, loc="best")
    fig.tight_layout()
    p = RESULTS / "dance_structure-space.jpg"
    fig.savefig(p, dpi=110, facecolor=fig.get_facecolor(), pil_kwargs={"quality": 85})
    print("wrote", p)


# ---------------------------------------------------------------------------
# hands
# ---------------------------------------------------------------------------

def in_hand(d: Drawing, hand: str, seed: int = 0, amount: float = 0.6) -> Drawing:
    from gesture import regime_field as rf
    from gesture import restyle as rs
    g = rf.load_hand(hand)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return rs.restyle_drawing(d, g, amount=amount, seed=seed)


def _thin(d: Drawing, max_pts: int = 900) -> Drawing:
    """Resample long strokes to ≤ max_pts points (restyle cost)."""
    st = []
    for s in d.strokes:
        p = s.points
        if len(p) > max_pts:
            sl = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
            t = np.linspace(0, sl[-1], max_pts)
            idx = np.searchsorted(sl, t).clip(0, len(p) - 1)
            meta = dict(s.meta)
            for k in ("speed", "acc"):
                if k in meta and len(meta[k]) == len(p):
                    meta[k] = np.interp(t, sl, np.asarray(meta[k], float)).round(4).tolist()
            p = np.column_stack([np.interp(t, sl, p[:, 0]), np.interp(t, sl, p[:, 1])])
            _ = idx
            st.append(Stroke(p, meta=meta))
        else:
            st.append(s)
    return Drawing(st, d.source, d.size, d.meta)


def _hand_cell(spec):
    kind, key, seed, key2, hand = spec
    t = time.perf_counter()
    d = _thin(structure(kind, key, seed, key2))
    if hand != "raw":
        d = in_hand(d, hand, seed)
    img = finish(render(d, 0.4, lw=1.4))
    return label(img, f"{kind} · {key}{' + ' + key2 if key2 else ''} · {hand}"), round(time.perf_counter() - t, 1)


HAND_ROWS = [("trails", "levitation", 0, None), ("strobe", "mantis", 0, None),
             ("chimera", "mantis", 1, "staccato"), ("tree", "levitation", 3, None)]


def cmd_hands(a):
    specs = [(*r, h) for r in HAND_ROWS for h in ("raw", "matisse", "hokusai", "shikasta")]
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_hand_cell, specs))
    for s, (_, sec) in zip(specs, res):
        print(" ", s, sec, "s")
    grid([r[0] for r in res], 4, RESULTS / "dance_structure-hands.jpg",
         title="One dance structure per row: raw | Matisse | Hokusai | shikasta (restyle.py gauss/chain, amount 0.6)")


# ---------------------------------------------------------------------------
# regimes
# ---------------------------------------------------------------------------

def _compose_cell(spec):
    from gesture import regime_field as rf
    from experiments import regime_compose as rc
    kind, key, seed, key2, field, hands, lab = spec
    t = time.perf_counter()
    d = _thin(structure(kind, key, seed, key2))
    if field == "kinematic":
        fobj = D.kinematic_field(d)
    elif field == "kinematic+":          # stiller threshold, wider knots
        fobj = D.kinematic_field(d, still=0.25, dilate_r=0.022)
    else:
        fobj = field
    hf = rc.HANDS.get(hands, hands)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        c = rf.compose(seed, SIZE, structure=d, field=fobj, hands=hf, signs=6, echo=2, drip=3, label=lab)
    img = rc.render(c, 0.4)
    sh = c.meta["regime_share"]
    txt = f"{lab} · line {sh['line']:.0%} nib {sh['nib']:.0%} mass {sh['shape']:.0%}"
    return rc.label(img, txt), c.meta, round(time.perf_counter() - t, 1)


def cmd_regimes(a):
    specs = []
    for kind, key, seed, key2 in (("trails", "levitation", 0, None), ("chimera", "mantis", 1, "staccato"),
                                  ("tree", "levitation", 3, None)):
        for field, hands in (("noise", "hokusai"), ("axis", "by_regime"), ("kinematic", "by_regime")):
            specs.append((kind, key, seed, key2, field, hands, f"{kind}:{key} · field {field} · hands {hands}"))
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_compose_cell, specs))
    for s, (_, meta, sec) in zip(specs, res):
        print(" ", s[-1], sec, "s", meta["regime_share"], "signs", meta["n_signs"])
    grid([r[0] for r in res], 3, RESULTS / "dance_structure-regimes.jpg",
         title="compose(structure=<dance Drawing>): columns = noise field / authored axis / the body's own "
               "kinematic field (still -> mass, accel -> nib, fast -> wire)")


def cmd_limb(a):
    """Animals mimed by a person, drawn by a calligrapher's hand, regimes
    taken from the body."""
    specs = []
    for key in ("mantis", "hummingbird", "dragon", "hippo_ballerina", "penguin"):
        specs.append(("trails", key, 0, None, "kinematic+", "shikasta", f"{key} trails · shikasta · body regimes"))
    specs.append(("chimera", "mantis", 11, "hummingbird", "kinematic+", "shikasta",
                  "mantis+hummingbird chimera · shikasta · body regimes"))
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_compose_cell, specs))
    for s, (_, meta, sec) in zip(specs, res):
        print(" ", s[-1], sec, "s", meta["regime_share"], "signs", meta["n_signs"])
    grid([r[0] for r in res], 3, RESULTS / "dance_structure-limb-mantis.jpg",
         title="Limb: a person miming animals (CMU 55), drawn in the shikasta hand, line/nib/mass from the body's "
               "own stillness / acceleration / speed")


def cmd_chimera(a):
    """The limb, larger: chimeras of two mimed animals in the shikasta hand,
    body regimes (one process; ~40 s)."""
    from gesture import regime_field as rf
    from experiments import regime_compose as rc
    cells = []
    for seed, (k1, k2) in [(11, ("mantis", "hummingbird")), (12, ("mantis", "dragon")), (13, ("penguin", "levitation"))]:
        d = _thin(structure("chimera", k1, seed, k2))
        f = D.kinematic_field(d, still=0.25, dilate_r=0.022)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            c = rf.compose(seed, SIZE, structure=d, field=f, hands="shikasta", signs=6, echo=2, drip=3)
        sh = c.meta["regime_share"]
        cells.append(rc.label(rc.render(c, 0.62), f"chimera {k1}+{k2} s{seed} · shikasta · body regimes · "
                                                   f"line {sh['line']:.0%} nib {sh['nib']:.0%} mass {sh['shape']:.0%}"))
    grid(cells, 3, RESULTS / "dance_structure-chimera-shikasta.jpg",
         title="Limb, larger: gesture pieces cut at velocity minima from two mimed animals, re-attached at sharp "
               "angles (one contiguous line each), shikasta hand, regimes from the body")


def cmd_fieldview(a):
    """Diagnostic: the kinematic regime along the raw trails (ink = wire,
    blue = nib, red = mass)."""
    cells = []
    for key in ("mantis", "levitation", "staccato", "hummingbird"):
        d = _thin(structure("trails", key))
        P, r = D.kinematic_samples(d)
        f = D.kinematic_field(d)
        img = finish(render(d, 0.4, lw=1.0, field=lambda s: f.at_px(s.points, d.size)))
        cells.append(label(img, f"{key}: kinematic r (ink wire / blue nib / red mass) "
                                f"nib {np.mean((r >= .5) & (r < 1.5)):.0%} mass {np.mean(r >= 1.5):.0%}"))
    grid(cells, 4, RESULTS / "dance_structure-kinematic-field.jpg")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    {"structures": cmd_structures, "measure": cmd_measure, "hands": cmd_hands, "regimes": cmd_regimes,
     "limb": cmd_limb, "fieldview": cmd_fieldview, "chimera": cmd_chimera}[a.cmd](a)


if __name__ == "__main__":
    main()
