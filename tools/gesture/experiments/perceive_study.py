"""Perceived lines study (results/perceive-2026-10-16.md).

Subcommands (run from tools/gesture):

  synth      synthetic ground truth: known strokes broken on purpose (clean
             gaps, faint-ink gaps, breaks at crossings, corners with a spur,
             T stems) → render → extract_hybrid → perceive; merge precision /
             recall and continuity before/after
  corpus     perceive every extracted drawing → .local/gesture/out/perceived/
             {artist}/*.json; before/after table
  overlays   scans with fragments coloured by perceived line
  prepare    grammar_v4_frozen.prepare_drawing on perceived drawings (cached)
  calibrate  crossing gain for the perceived grammars
  test1      fair test 1: perceived grammar (and the frozen v4 grammar) vs real
             perceived and real original long subsets, identity floors
  memo       memorisation check for the perceived grammar
  sheets     generated drawings from the perceived grammar (contiguous + single)

    P=../../.local/gesture/.venv/bin/python
    $P -m experiments.perceive_study synth
    $P -m experiments.perceive_study corpus
    ...

Outputs: .local/gesture/out/perceive/, .local/gesture/out/perceived/,
.local/gesture/out/grammar_perceived/.
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

from gesture import extract_hybrid, synth  # noqa: E402
from gesture import grammar_v4_frozen as gm  # noqa: E402
from gesture import medium, panel  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402
from gesture.curvature import arclength, resample  # noqa: E402
from gesture.extract_eval import score_gt  # noqa: E402
from gesture.perceive import MERGE_KINDS, perceive  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
EXTRACT = ROOT / ".local/gesture/out/extract_hybrid"
PERC = ROOT / ".local/gesture/out/perceived"
OUT = ROOT / ".local/gesture/out/perceive"
GOUT = ROOT / ".local/gesture/out/grammar_perceived"
FROZEN = ROOT / ".local/gesture/out/grammar_v4_frozen"
CORPUS = ROOT / ".local/gesture/corpus"
RESULTS = Path(__file__).resolve().parents[1] / "results"
ARTISTS = ("matisse", "hokusai", "ingres")
JOBS = 3


# ---------------------------------------------------------------------------
# 1. synthetic ground truth
# ---------------------------------------------------------------------------

def _cut(st: Stroke, centres: list[float], gaps: list[float],
         offsets: list[float] | None = None) -> tuple[list[Stroke], list[np.ndarray]]:
    """Remove arc-length windows from a stroke: (pieces, removed bits). Each
    piece after a break is shifted sideways by that break's offset (px),
    cumulatively — a pen put down again slightly off the line."""
    p = resample(st.points, 0.5)
    s = arclength(p)
    t = np.gradient(p, axis=0)
    nrm = np.column_stack([-t[:, 1], t[:, 0]]) / np.maximum(np.linalg.norm(t, axis=1), 1e-9)[:, None]
    order = np.argsort(centres)
    shift = np.zeros(len(p))
    keep = np.ones(len(p), bool)
    removed = []
    for o in order:
        c, g = centres[o], gaps[o]
        m = (s >= c - g / 2) & (s <= c + g / 2)
        keep &= ~m
        if offsets is not None:
            shift[s > c + g / 2] += offsets[o]
        if m.sum() >= 2:
            removed.append(p[m])
    p = p + nrm * shift[:, None]
    pieces, cur = [], []
    for i in range(len(p)):
        if keep[i]:
            cur.append(i)
        elif cur:
            pieces.append(p[cur]); cur = []
    if cur:
        pieces.append(p[cur])
    return [Stroke(q) for q in pieces if len(q) >= 2], removed


def broken_scene(seed: int, kind: str, w: float, size: int = 900):
    """(truth Drawing, pieces Drawing, faint Drawing, break log)."""
    from shapely.geometry import LineString
    rng = np.random.default_rng(seed)
    m = size
    if kind == "random":
        base = synth.scene_random(rng, size, n_strokes=6, length_frac=(0.3, 0.7), kappa_max_frac=6.0)
    else:
        base = synth.scene_matisse_like(rng, size, line_width=w)
    truth = [Stroke(s.points) for s in base.strokes]
    log = []
    # T stems: start on a host interior, heading 40–90° off its tangent
    n_stem = 0
    for _ in range(12):
        if n_stem >= 2:
            break
        h = int(rng.integers(len(truth)))
        q = resample(truth[h].points, 0.5)
        i = int(rng.uniform(0.3, 0.7) * (len(q) - 1))
        t = q[min(i + 4, len(q) - 1)] - q[max(i - 4, 0)]
        a = np.arctan2(t[1], t[0]) + rng.choice([-1, 1]) * np.radians(rng.uniform(40, 90))
        L = rng.uniform(0.12, 0.25) * m
        st = synth.random_clothoid_stroke(rng, L, 2, 2.0 / m, start=q[i], heading=a)
        lo, hi = st.points.min(0), st.points.max(0)
        k0 = int(np.searchsorted(arclength(st.points), 6 * w))
        ls = LineString(st.points[k0:])
        if lo.min() < 10 or hi[0] > size - 10 or hi[1] > size - 10:
            continue
        if any(ls.distance(LineString(o.points)) < 3 * w for o in truth):
            continue
        n_stem += 1
        truth.append(Stroke(st.points, meta={"role": "stem", "host": h}))
        log.append(("stem", len(truth) - 1))
    # a corner with a spur at its apex
    n_corner = 0
    for _ in range(12):
        if n_corner >= 1:
            break
        start = rng.uniform(0.2, 0.8, 2) * m
        h0 = rng.uniform(0, 2 * np.pi)
        defl = np.radians(rng.uniform(50, 75)) * rng.choice([-1, 1])
        L1, L2 = rng.uniform(0.15, 0.3, 2) * m
        a1 = synth.random_clothoid_stroke(rng, L1, 2, 2.0 / m, start=start, heading=h0)
        e = a1.points[-1]
        hd = np.arctan2(*(a1.points[-1] - a1.points[-3])[::-1])
        a2 = synth.random_clothoid_stroke(rng, L2, 2, 2.0 / m, start=e, heading=hd + defl)
        V = np.vstack([a1.points, a2.points[1:]])
        # spur on the outer side, far from both arms' directions
        # spur into the V's interior (a T-like third branch at the apex)
        out_dir = hd + defl / 2 + np.sign(defl) * np.pi / 2 + rng.uniform(-0.4, 0.4)
        sp = synth.random_clothoid_stroke(rng, rng.uniform(12, 30) * w, 1, 0.0, start=e, heading=out_dir)
        allp = np.vstack([V, sp.points])
        if allp.min() < 10 or allp.max(0)[0] > size - 10 or allp.max(0)[1] > size - 10:
            continue
        lsV = LineString(allp)
        if any(lsV.distance(LineString(o.points)) < 3 * w for o in truth):
            continue
        n_corner += 1
        truth.append(Stroke(V, meta={"role": "corner", "defl": float(defl)}))
        truth.append(Stroke(sp.points, meta={"role": "spur"}))
        log.append(("corner", len(truth) - 2))
    # breaks
    pieces, faint = [], []
    lines = [LineString(t.points) for t in truth]
    for ti, t in enumerate(truth):
        L = t.length()
        role = t.meta.get("role", "")
        if role in ("spur",) or L < 30 * w:
            pieces.append(t); continue
        cents, gaps, kinds, offs = [], [], [], []
        # break at a crossing with another truth stroke
        for oj, o in enumerate(lines):
            if oj == ti:
                continue
            inter = lines[ti].intersection(o)
            for g in getattr(inter, "geoms", [inter]):
                if g.geom_type == "Point" and rng.random() < 0.5:
                    c = lines[ti].project(g)
                    if 10 * w < c < L - 10 * w:
                        cents.append(c); gaps.append(rng.uniform(2.0, 5.0) * w); kinds.append("cross")
                        offs.append(0.0)
        n = int(rng.integers(0, 3)) if role != "corner" else 0
        for _ in range(n):
            c = rng.uniform(0.15, 0.85) * L
            if all(abs(c - x) > 15 * w for x in cents):
                if rng.random() < 0.5:
                    cents.append(c); gaps.append(rng.uniform(2.0, 8.0) * w); kinds.append("clean")
                else:
                    cents.append(c); gaps.append(rng.uniform(4.0, 12.0) * w); kinds.append("faint")
                offs.append(rng.uniform(-0.5, 0.5) * w)
        ps, rem = _cut(t, cents, gaps, offs)
        pieces += ps
        for (c, g, k), r in zip(zip(cents, gaps, kinds), rem):
            if k == "faint":
                faint.append(Stroke(r))
        log += [(k, ti, float(g / w)) for k, g in zip(kinds, gaps)]
    sz = (size, size)
    return (Drawing(truth, size=sz), Drawing(pieces, size=sz), Drawing(faint, size=sz), log)


def _owner(d: Drawing, truth: Drawing, tol: float) -> np.ndarray:
    from scipy.spatial import cKDTree
    TP, TI = [], []
    for i, t in enumerate(truth.strokes):
        q = resample(t.points, 1.0)
        TP.append(q); TI.append(np.full(len(q), i))
    tree, ti = cKDTree(np.vstack(TP)), np.concatenate(TI)
    out = []
    for st in d.strokes:
        q = resample(st.points, 1.0, closed=st.closed) if len(st) >= 2 else st.points
        dd, jj = tree.query(q)
        ok = dd <= tol
        out.append(int(np.bincount(ti[jj[ok]]).argmax()) if ok.mean() > 0.5 else -1)
    return np.array(out)


def _synth_job(args):
    seed, kind, w, noise, params = args
    truth, pieces, faint, log = broken_scene(seed, kind, w)
    img = synth.render(pieces, line_width=w, paper_noise=noise, use_stroke_width=False, seed=seed)
    if faint.strokes:
        fi = synth.render(faint, line_width=w, paper_noise=0.0, use_stroke_width=False, seed=seed)
        dark = 0.15
        img = np.minimum(img, (255 - dark * (255 - fi.astype(float))).astype(np.uint8))
    g = img.astype(np.float64) / 255.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ex = extract_hybrid.extract(g)
    per = perceive(ex, **params)
    tol = max(1.5, 0.5 * w)
    own = _owner(ex, truth, 3 * tol)
    res = {"seed": seed, "kind": kind, "w": w, "log": log,
           "before": score_gt(truth, ex, w), "after": score_gt(truth, per, w),
           "n_frag": len(ex.strokes), "n_perc": len(per.strokes)}
    # needed joins: fragments per truth − 1
    cnt = np.bincount(own[own >= 0], minlength=len(truth.strokes))
    res["needed"] = int(np.maximum(cnt - 1, 0).sum())
    merges = []
    for st in per.strokes:
        fr = st.meta.get("fragments", [])
        for j, jn in enumerate(st.meta.get("joins", [])):
            if jn.get("closes"):
                a, b = fr[-1][0], fr[0][0]
            else:
                a, b = fr[j][0], fr[j + 1][0]
            oa, ob = int(own[a]), int(own[b])
            role_a = truth.strokes[oa].meta.get("role", "") if oa >= 0 else "?"
            role_b = truth.strokes[ob].meta.get("role", "") if ob >= 0 else "?"
            merges.append({"kind": jn["kind"], "ok": bool(oa == ob and oa >= 0), "gap_w": jn["gap_w"],
                           "defl": jn["defl"], "roles": [role_a, role_b]})
    res["merges"] = merges
    # extractor's own handling of X: crossings broken? (truth crossings kept intact)
    return res


def cmd_synth(a):
    params = json.loads(a.params) if a.params else {}
    jobs = [(s, k, w, nz, params) for s in range(a.n) for k in ("random", "matisse")
            for w, nz in ((3.0, 0.03), (5.0, 0.08))]
    t0 = time.time()
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_synth_job, jobs))
    print(f"{len(res)} scenes in {time.time() - t0:.0f}s")
    rep = summarise_synth(res)
    OUT.mkdir(parents=True, exist_ok=True)
    tag = a.tag or "synth"
    (OUT / f"{tag}.json").write_text(json.dumps({"params": params, "summary": rep, "scenes": res}, indent=1))
    print(json.dumps(rep, indent=1))


def summarise_synth(res):
    rep = {}
    for k in ("random", "matisse", "all"):
        rr = [r for r in res if k == "all" or r["kind"] == k]
        M = [m for r in rr for m in r["merges"]]
        ok = sum(m["ok"] for m in M)
        need = sum(r["needed"] for r in rr)
        row = {"scenes": len(rr), "merges": len(M), "correct": ok,
               "precision": ok / max(len(M), 1), "needed": need, "recall": ok / max(need, 1),
               "cont_before": float(np.mean([r["before"]["continuity"] for r in rr])),
               "cont_after": float(np.mean([r["after"]["continuity"] for r in rr])),
               "frags_before": float(np.mean([r["before"]["fragments"] for r in rr])),
               "frags_after": float(np.mean([r["after"]["fragments"] for r in rr])),
               "prec_before": float(np.mean([r["before"]["precision"] for r in rr])),
               "prec_after": float(np.mean([r["after"]["precision"] for r in rr]))}
        for kind in MERGE_KINDS:
            mk = [m for m in M if m["kind"] == kind]
            row[f"{kind}_n"] = len(mk)
            row[f"{kind}_prec"] = (sum(m["ok"] for m in mk) / len(mk)) if mk else None
        bad = [m for m in M if not m["ok"]]
        row["false_roles"] = {}
        for m in bad:
            key = "+".join(sorted(x or "plain" for x in m["roles"]))
            row["false_roles"][key] = row["false_roles"].get(key, 0) + 1
        stems = [m for m in M if "stem" in m["roles"] and not m["ok"]]
        spurs = [m for m in M if "spur" in m["roles"] and not m["ok"]]
        row["stem_false"] = len(stems)
        row["spur_false"] = len(spurs)
        rep[k] = row
    return rep


# ---------------------------------------------------------------------------
# 2. real corpus
# ---------------------------------------------------------------------------

def _corpus_job(args):
    art, stem, params = args
    d = Drawing.load(EXTRACT / art / f"{stem}.json")
    p = perceive(d, **params)
    PERC.joinpath(art).mkdir(parents=True, exist_ok=True)
    p.save(PERC / art / f"{stem}.json")
    return art, stem, _stats(d), _stats(p), p.meta["perceive"]["counts"]


def _stats(d: Drawing) -> dict:
    L = np.array([s.length() for s in d.strokes])
    R = d.ref_length()
    w = gm.drawing_width(d)
    keep, info = gm.select_long(d)
    ld = Drawing([d.strokes[i] for i in keep], size=d.size)
    Rl = ld.ref_length() if keep else R
    Ll = L[keep] / Rl if keep else np.zeros(0)
    return {"n": len(L), "ink_R": float(L.sum() / R), "len_w_q50": float(np.median(L / w)),
            "len_w_q90": float(np.quantile(L / w, .9)),
            "ink_ge_100w": float(L[L >= 100 * w].sum() / max(L.sum(), 1e-9)),
            "ink_ge_10pctR": float(L[L >= 0.1 * R].sum() / max(L.sum(), 1e-9)),
            "n_long": len(keep), "ink_long_share": info["ink_long"] / max(info["ink_all"], 1e-9),
            "long_len_q10": float(np.quantile(Ll, .1)) if len(Ll) else np.nan,
            "long_len_q50": float(np.median(Ll)) if len(Ll) else np.nan,
            "n_hatch": info["n_hatch"]}


def cmd_corpus(a):
    params = json.loads(a.params) if a.params else {}
    jobs = [(art, p.stem, params) for art in ARTISTS for p in sorted((EXTRACT / art).glob("*.json"))]
    t0 = time.time()
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_corpus_job, jobs))
    print(f"{len(res)} drawings in {time.time() - t0:.0f}s")
    rows = {}
    for art in ARTISTS:
        rr = [r for r in res if r[0] == art]
        row = {}
        for side, idx in (("before", 2), ("after", 3)):
            for k in rr[0][idx]:
                row[f"{k}_{side}"] = float(np.nanmedian([r[idx][k] for r in rr]))
        for k in MERGE_KINDS:
            row[f"merges_{k}"] = int(sum(r[4][k] for r in rr))
        row["n_total_before"] = int(sum(r[2]["n"] for r in rr))
        row["n_total_after"] = int(sum(r[3]["n"] for r in rr))
        rows[art] = row
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "corpus.json").write_text(json.dumps({"params": params, "rows": rows,
                                                 "per_drawing": [list(r) for r in res]}, indent=1))
    print(json.dumps(rows, indent=1))


# ---------------------------------------------------------------------------
# 3. overlays
# ---------------------------------------------------------------------------

def _scan_path(art: str, d: Drawing) -> Path | None:
    p = ROOT / d.source if d.source else None
    if p and p.exists():
        return p
    return None


PALETTE = ["#AF3029", "#205EA6", "#66800B", "#BC5215", "#5E409D", "#24837B", "#A02F6F", "#AD8301",
           "#D14D41", "#4385BE", "#879A39", "#DA702C", "#8B7EC8", "#3AA99F", "#CE5D97", "#D0A215"]


def overlay(art: str, stem: str, crop=None, max_side: int = 1400):
    """RGB image: faded scan; every perceived line in its own colour (merged
    lines thicker), bridges black, line ends as dots and fragment boundaries
    inside a merged line as black ticks — so a break that was NOT merged
    shows as two dots, and a merge as one colour running through a tick."""
    from PIL import Image, ImageDraw
    d0 = Drawing.load(EXTRACT / art / f"{stem}.json")
    dp = Drawing.load(PERC / art / f"{stem}.json")
    sp = _scan_path(art, d0)
    W, H = d0.size
    if sp is not None:
        im = Image.open(sp).convert("L")
        if im.size != (W, H):
            im = im.resize((W, H))
    else:
        im = Image.new("L", (W, H), 255)
    x0, y0, x1, y1 = crop if crop else (0, 0, W, H)
    im = im.crop((x0, y0, x1, y1))
    sc = min(1.0, max_side / max(im.size))
    im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))))
    bg = Image.eval(im, lambda v: 200 + v // 5).convert("RGB")
    dr = ImageDraw.Draw(bg)
    lw = max(2, int(round(sc * max(gm.drawing_width(d0), 1.0) * 0.6)))

    def xy(q):
        return [((x - x0) * sc, (y - y0) * sc) for x, y in q]

    def dot(pt, r, col):
        x, y = (pt[0] - x0) * sc, (pt[1] - y0) * sc
        dr.ellipse((x - r, y - r, x + r, y + r), fill=col)
    for k, s in enumerate(dp.strokes):
        multi = len(s.meta.get("fragments", [])) > 1
        col = PALETTE[k % len(PALETTE)]
        q = s.points if not s.closed else np.vstack([s.points, s.points[:1]])
        br = s.meta.get("bridges", [])
        dr.line(xy(q), fill=col, width=lw + (2 if multi else 0))
        for b0, b1 in br:
            seg = q[max(b0 - 1, 0):min(b1 + 1, len(q))]
            if len(seg) >= 2:
                dr.line(xy(seg), fill=(16, 15, 15), width=lw + 2)
        if multi:
            # fragment boundaries: the fragment ends inside the merged line
            for f, _rev in s.meta["fragments"]:
                fp = d0.strokes[f].points
                for e in (fp[0], fp[-1]):
                    dot(e, lw * 0.9 + 1, (16, 15, 15))
        if not s.closed:
            dot(q[0], lw + 1, col)
            dot(q[-1], lw + 1, col)
    return bg


def cmd_overlays(a):
    from PIL import Image
    OUT.joinpath("overlays").mkdir(parents=True, exist_ok=True)
    for art in ARTISTS:
        stems = [p.stem for p in sorted((PERC / art).glob("*.json"))]
        for stem in stems[:: max(1, len(stems) // a.per_artist)][: a.per_artist]:
            im = overlay(art, stem, max_side=a.max_side)
            im.save(OUT / "overlays" / f"{art}_{stem}.jpg", quality=85)
            print(OUT / "overlays" / f"{art}_{stem}.jpg")


# ---------------------------------------------------------------------------
# 4. grammar: prepare / calibrate / test1 / memo
# ---------------------------------------------------------------------------

def _prep_job(args):
    src, art, stem = args
    base = PERC if src == "perceived" else EXTRACT
    p = GOUT / "prepared" / src / art / f"{stem}.json"
    if p.exists():
        return src, art, stem, json.loads(p.read_text())
    d = Drawing.load(base / art / f"{stem}.json")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pd = gm.prepare_drawing(d)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(pd))
    return src, art, stem, pd


def prepared(src="perceived"):
    base = PERC if src == "perceived" else EXTRACT
    jobs = [(src, art, p.stem) for art in ARTISTS for p in sorted((base / art).glob("*.json"))]
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_prep_job, jobs, chunksize=1))
    out = {a: [] for a in ARTISTS}
    for _s, art, stem, pd in res:
        out[art].append((stem, pd))
    return out


def cmd_prepare(a):
    t0 = time.time()
    P = prepared("perceived")
    print(f"prepared in {time.time() - t0:.0f}s")
    for art in ARTISTS:
        g = gm.learn(prepared=[pd for _, pd in P[art]], name=art + "_perceived")
        GOUT.mkdir(parents=True, exist_ok=True)
        g.save(GOUT / f"grammar_{art}.json")
        nseg = [gm.n_segments(s["tokens"]) for _, pd in P[art] for s in pd["strokes"]]
        print(art, "long strokes", len(nseg), "segs med", np.median(nseg))


def _calib_job(args):
    gpath, size, seed, gain = args
    g = gm.Grammar.load(gpath)
    d = gm.generate_drawing(g, np.random.default_rng(seed), size, cross_gain=gain)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _ = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W, clothoid=False)
    return f.get("rel_cross_per_len", np.nan)


def cmd_calibrate(a):
    P = prepared("perceived")
    gains = {}
    for art in ARTISTS:
        gpath = GOUT / f"grammar_{art}.json"
        target = float(np.median([pd["relations"]["cross_per_ink"] for _, pd in P[art]
                                  if pd["relations"]["n"] >= 2]))
        sizes = ([tuple(pd["size"]) for _, pd in P[art]] * 2)[:24]
        gain, tried = 1.0, []
        for it in range(4):
            with ProcessPoolExecutor(JOBS) as ex:
                v = list(ex.map(_calib_job, [(str(gpath), sz, 500 + 37 * it + i, gain)
                                             for i, sz in enumerate(sizes)]))
            got = float(np.nanmedian(v))
            tried.append((abs(np.log(max(got, 1e-6) / target)), gain, got))
            print(f"{art} it{it}: gain {gain:.2f} → {got:.3f} (real {target:.3f})")
            gain *= 2.0 if got <= 0 else float(np.clip(np.sqrt(target / got), 0.5, 2.0))
        gains[art] = round(min(tried)[1], 3)
    (GOUT / "cross_gain.json").write_text(json.dumps(gains, indent=1))
    for art in ARTISTS:
        g = gm.Grammar.load(GOUT / f"grammar_{art}.json")
        g.relations["cross_gain"] = gains[art]
        g.save(GOUT / f"grammar_{art}.json")
    print(gains)


def _feat_job(args):
    key, d = args
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _ = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W)
    return key, f


def _gen_job(args):
    gpath, size, seed, kw = args
    g = gm.Grammar.load(gpath)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return gm.generate_drawing(g, np.random.default_rng(seed), size, **kw)


def _identity_job(args):
    src, art, stem = args
    base = PERC if src == "perceived" else EXTRACT
    d = gm.long_drawing(Drawing.load(base / art / f"{stem}.json"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        R, fitted = gm.fit_drawing(d, select=False)
    out = []
    for st, _f, toks in fitted:
        w = gm.stroke_width(st, d)
        pts, _, _ = gm.tokens_to_points(toks, R, step=max(0.5, w / 2))
        ref = resample(st.points, max(0.5, w / 2))
        n = min(len(pts), len(ref))
        if n < 3:
            continue
        ub = np.linspace(0, len(pts) - 1, n).astype(int)
        ui = np.linspace(0, len(ref) - 1, n).astype(int)
        q = gm._kabsch(pts[ub], ref[ui])(pts)
        out.append(Stroke(q, width=np.full(len(q), w)))
    return Drawing(out, source=d.source, size=d.size)


KEY = ("len_q10", "len_q50", "len_q90", "cl_corner_rate", "turn_tcorr_10", "cl_segs_per_stroke",
       "rel_touch_rate", "rel_cross_per_len")


def cmd_test1(a):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from discriminate import _models, effect_sizes, pair_auc
    lut = medium.load_media()
    models = _models(a.seed)
    rep = {"artists": {}, "key": {}}
    for art in ARTISTS:
        t0 = time.time()
        stems = [p.stem for p in sorted((PERC / art).glob("*.json"))]
        items = []        # (cls, key, drawing, stem)
        sizes = []
        for src, base in (("perc", PERC), ("orig", EXTRACT)):
            for st in stems:
                d = gm.long_drawing(Drawing.load(base / art / f"{st}.json"))
                if len(d.strokes) >= 2:
                    items.append((f"real_{src}", f"real_{src}/{st}", d, st))
                    if src == "perc":
                        sizes.append(d.size)
        gp = str(GOUT / f"grammar_{art}.json")
        g0 = str(FROZEN / f"grammar_{art}.json")
        with ProcessPoolExecutor(JOBS) as ex:
            for nm, gpath in (("gen_perc", gp), ("gen_v4", g0)):
                ds = list(ex.map(_gen_job, [(gpath, sz, a.seed * 1000 + i, {}) for i, sz in enumerate(sizes)]))
                items += [(nm, f"{nm}/{i}", d, None) for i, d in enumerate(ds)]
            for src in ("perc", "orig"):
                ds = list(ex.map(_identity_job, [("perceived" if src == "perc" else "orig", art, st)
                                                 for st in stems]))
                items += [(f"ident_{src}", f"ident_{src}/{i}", d, None) for i, d in enumerate(ds)
                          if len(d.strokes) >= 2]
            feats = dict(ex.map(_feat_job, [(k, d) for _c, k, d, _s in items], chunksize=2))
        keys = [k for _c, k, _d, _s in items]
        allk = sorted(set().union(*[feats[k] for k in keys]))
        names = [n for n in allk if all(n in feats[k] for k in keys) and panel.group_of(n) not in panel.WIDTH_GROUPS]
        X = np.array([[feats[k][n] for n in names] for k in keys], dtype=float)
        okc = ~np.all(np.isnan(X), axis=0)
        X, names = X[:, okc], [n for n, o in zip(names, okc) if o]
        cls = np.array([c for c, _k, _d, _s in items])
        med = np.array([lut.get((art, st), "unknown") if c.startswith("real") else "generated"
                        for c, _k, _d, st in items])
        artl = np.array([art] * len(items))
        res = {}
        pairs = [("real_perc", "gen_perc"), ("real_orig", "gen_perc"), ("real_perc", "gen_v4"),
                 ("real_orig", "gen_v4"), ("real_perc", "ident_perc"), ("real_orig", "ident_orig"),
                 ("real_orig", "real_perc")]
        for ra, gb in pairs:
            mm = np.isin(cls, [ra, gb])
            pj = medium.MediumProjector(medium.load_pairs()).fit(X[mm], artl[mm], med[mm])
            Xp = pj.transform(X[mm])
            y = np.where(cls[mm] == ra, "real", "gen")
            grp = np.arange(mm.sum())
            r = {mn: pair_auc(mk, Xp, y, "real", "gen", a.repeats, a.seed, grp)["auc"] for mn, mk in models.items()}
            r["top_d"] = effect_sizes(X[mm], y, names, "real", "gen", top=6)
            r["n"] = [int((y == "real").sum()), int((y == "gen").sum())]
            res[f"{ra}|{gb}"] = r
            print(f"  {art} {ra} vs {gb}: logreg {r['logreg']:.3f} forest {r['forest']:.3f}")
        rep["artists"][art] = res
        rep["key"][art] = {c: {n: (float(np.nanmedian(X[cls == c, names.index(n)])) if n in names else None)
                               for n in KEY} for c in dict.fromkeys(cls.tolist())}
        print(f"[{time.time() - t0:.0f}s] {art}", json.dumps(rep["key"][art]))
    GOUT.mkdir(parents=True, exist_ok=True)
    (GOUT / "test1.json").write_text(json.dumps(rep, indent=1))


def cmd_memo(a):
    P = prepared("perceived")
    rng = np.random.default_rng(a.seed)
    rep = {}
    for art in ARTISTS:
        pds = [pd for _, pd in P[art]]
        held = pds[::5]
        train = [pd for i, pd in enumerate(pds) if i % 5]
        g = gm.learn(prepared=train, name=art)
        real = [s["tokens"] for pd in held for s in pd["strokes"]]
        Lr = [gm.stroke_length(t) for t in real]
        lens = [float(rng.choice(Lr)) for _ in range(a.n)]
        gen = [gm.generate_tokens(g, rng, length=L, p_follow=gm.P_FOLLOW)[0] for L in lens]
        tr_idx = rng.choice(len(g.strokes), a.n)
        quote = [gm.jitter_tokens(g, g.strokes[i], rng) for i in tr_idx]
        sets = {"generated": gen, "heldout_real": real, "jittered_training": quote}
        res = {}
        for min_seg in (2, 4):
            row, ref = {}, None
            ds = {}
            for nm, S in sets.items():
                S2 = [t for t in S if gm.n_segments(t) >= min_seg]
                ds[nm] = gm.nearest_training_distance(S2, g)
            ref = ds["heldout_real"]
            for nm, d in ds.items():
                row[nm] = {"n": int(len(d)), "median": float(np.median(d)) if len(d) else None,
                           "share_below_heldout_p10": float(np.mean(d < np.quantile(ref, .1))) if len(d) and len(ref) else None}
            res[f"nseg_ge_{min_seg}"] = row
        rep[art] = res
        print(art, json.dumps(res))
    (GOUT / "memo.json").write_text(json.dumps(rep, indent=1))


# ---------------------------------------------------------------------------
# 5. sheets
# ---------------------------------------------------------------------------

def _render_drawing(d: Drawing, size_px: int, ink=(16, 15, 15)):
    from PIL import Image, ImageDraw
    W, H = d.size
    sc = size_px / max(W, H)
    im = Image.new("RGB", (int(W * sc), int(H * sc)), (255, 252, 240))
    dr = ImageDraw.Draw(im)
    for s in d.strokes:
        q = s.points * sc
        if s.closed:
            q = np.vstack([q, q[:1]])
        if len(q) >= 2:
            dr.line([tuple(v) for v in q], fill=ink, width=2)
    return im


def cmd_sheets(a):
    from PIL import Image, ImageDraw
    cell = 420
    rows = []
    for art in ARTISTS:
        gp = str(GOUT / f"grammar_{art}.json")
        g0 = str(FROZEN / f"grammar_{art}.json")
        jobs = [(gp, (1200, 1200), 70 + i, {}) for i in range(2)] + \
               [(gp, (1200, 1200), 90 + i, {"mode": "single"}) for i in range(2)] + \
               [(g0, (1200, 1200), 70, {})]
        with ProcessPoolExecutor(JOBS) as ex:
            ds = list(ex.map(_gen_job, jobs))
        stem = sorted((PERC / art).glob("*.json"))[3].stem
        real = gm.long_drawing(Drawing.load(PERC / art / f"{stem}.json"))
        rows.append((art, ds + [real]))
        for i, d in enumerate(ds):
            d.save(GOUT / "gen" / f"{art}_{i}.json")
    labels = ["perceived · contiguous", "perceived · contiguous", "perceived · single", "perceived · single",
              "frozen v4 · contiguous", "real perceived long subset"]
    sheet = Image.new("RGB", (cell * 6 + 70, (cell + 24) * 3 + 10), (255, 252, 240))
    dr = ImageDraw.Draw(sheet)
    for r, (art, ds) in enumerate(rows):
        dr.text((6, r * (cell + 24) + cell // 2), art, fill=(16, 15, 15))
        for c, d in enumerate(ds):
            im = _render_drawing(d, cell)
            sheet.paste(im, (70 + c * cell + (cell - im.width) // 2, r * (cell + 24) + 18))
            if r == 0:
                dr.text((70 + c * cell + 6, 2), labels[c], fill=(111, 110, 105))
    out = OUT / "perceive-generated.jpg"
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=82)
    print(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["synth", "corpus", "overlays", "prepare", "calibrate", "test1", "memo", "sheets"])
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--params", default="", help="JSON perceive params")
    ap.add_argument("--tag", default="")
    ap.add_argument("--per-artist", type=int, default=4)
    ap.add_argument("--max-side", type=int, default=1400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=5)
    a = ap.parse_args(argv)
    if a.cmd == "memo" and a.n == 10:
        a.n = 600
    {"synth": cmd_synth, "corpus": cmd_corpus, "overlays": cmd_overlays, "prepare": cmd_prepare,
     "calibrate": cmd_calibrate, "test1": cmd_test1, "memo": cmd_memo, "sheets": cmd_sheets}[a.cmd](a)


if __name__ == "__main__":
    main()
