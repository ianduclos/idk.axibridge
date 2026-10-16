"""Blinded image pairs for a visual judge (plan item D2: "AI as critic").

Each pair image shows two crops side by side, A | B: one from a real drawing
(long-stroke subset, the grammar's training domain), one from a machine
drawing. Both are re-rendered from stroke geometry with the same renderer,
line width and canvas scale, so the judge sees line shape only.

Conditions (mixed and shuffled; filenames carry no information):
  test      real vs grammar-v3 generated (per artist)
  calib_pos real vs shuffled-segments null — a judge worth trusting finds these
  calib_neg real vs identity null (same κ, re-integrated) — should be chance;
            above chance means the judge reads pipeline artefacts

The answer key is written OUTSIDE the repo (default: $BLIND_KEY or
/tmp/gesture_blind_key.json) so the judge cannot read it.

  .local/gesture/.venv/bin/python tools/gesture/experiments/blind_pairs.py --per 16
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from gesture import nulls, synth  # noqa: E402
from gesture import grammar_v3_frozen as gm  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402
from gesture.curvature import resample, smooth  # noqa: E402

REPO = HERE.parents[2]
EXTRACT = REPO / ".local/gesture/out/extract_hybrid"
GRAMMARS = REPO / ".local/gesture/out/grammar_v2"
OUT = REPO / ".local/gesture/out/blind/pairs"
SIDE = 1200          # render canvas max side (px)
LW = 3.0             # rendered line width (px)
CROP = 480           # crop size (px)


SMOOTH = 5.0         # px at render scale ≈ the grammar's resolution (σ = 2 line widths):
                     # finer tremor is real but unrepresentable by construction, so not tested here


def fit_canvas(d: Drawing) -> Drawing:
    """Scale a drawing so its ink bbox fills a SIDE-px canvas (margin 40),
    then smooth every line identically (resample 1 px, Gaussian SMOOTH px)."""
    P = np.vstack([s.points for s in d.strokes])
    lo, hi = P.min(0), P.max(0)
    k = (SIDE - 80) / max((hi - lo).max(), 1e-9)
    st = []
    for s in d.strokes:
        q = (s.points - lo) * k + 40
        if len(q) >= 3:
            r = resample(q, 1.0, closed=s.closed)
            if len(r) >= 5:
                q = smooth(r, SMOOTH, 1.0, closed=s.closed)
        st.append(Stroke(q, closed=s.closed))
    st = _drop_plate_lines(st)
    st = _snap_ends(st)
    W, H = (np.ceil((hi - lo) * k) + 80).astype(int)
    return Drawing(st, source=d.source, size=(int(W), int(H)))


def _drop_plate_lines(st):
    """Ruler-straight long lines (plate marks, sheet edges) carry no hand and
    were a judge cue in round 1. Same rule for every drawing."""
    out = []
    for s in st:
        p = s.points
        L = float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1))) if len(p) > 1 else 0.0
        chord = float(np.linalg.norm(p[-1] - p[0])) if len(p) > 1 else 0.0
        if L > 0.25 * SIDE and chord > 0.995 * L:
            continue
        out.append(s)
    return out


def _snap_ends(st, tol: float = 3 * LW):
    """Move each open end that lies within tol of another stroke onto it, so
    'hairline gap at a join' (a round-1 judge cue) is the same everywhere."""
    from scipy.spatial import cKDTree
    if len(st) < 2:
        return st
    pts = [s.points.copy() for s in st]
    allp = np.vstack(pts)
    owner = np.concatenate([np.full(len(p), i) for i, p in enumerate(pts)])
    tree = cKDTree(allp)
    for i, p in enumerate(pts):
        if st[i].closed or len(p) < 2:
            continue
        for e in (0, -1):
            for j in tree.query_ball_point(p[e], tol):
                if owner[j] != i:
                    d = allp[j] - p[e]
                    if np.linalg.norm(d) < tol:
                        p[e] = allp[j]
                        break
    return [Stroke(p, closed=s.closed) for p, s in zip(pts, st)]


def render(d: Drawing, seed: int) -> np.ndarray:
    return synth.render(d, line_width=LW, use_stroke_width=False, paper_noise=0.0, blur_sigma=0.6, seed=seed)


def crop(img: np.ndarray, rng, min_ink=0.012, tries=200):
    H, W = img.shape
    best = None
    for _ in range(tries):
        y = int(rng.integers(0, max(H - CROP, 1)))
        x = int(rng.integers(0, max(W - CROP, 1)))
        c = img[y:y + CROP, x:x + CROP]
        ink = float((c < 128).mean())
        if c.shape == (CROP, CROP) and ink >= min_ink:
            return c
        if c.shape == (CROP, CROP) and (best is None or ink > best[0]):
            best = (ink, c)
    return best[1] if best else None


def pair_image(a: np.ndarray, b: np.ndarray) -> Image.Image:
    im = Image.new("L", (2 * CROP + 60, CROP + 40), 255)
    im.paste(Image.fromarray(a), (20, 30))
    im.paste(Image.fromarray(b), (CROP + 40, 30))
    d = ImageDraw.Draw(im)
    d.text((20 + CROP // 2, 8), "A", fill=0)
    d.text((CROP + 40 + CROP // 2, 8), "B", fill=0)
    d.line([(CROP + 30, 30), (CROP + 30, CROP + 30)], fill=180)
    return im


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=16, help="test pairs per artist")
    ap.add_argument("--calib", type=int, default=16, help="pairs per calibration condition")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--key", default=os.environ.get("BLIND_KEY", "/tmp/gesture_blind_key.json"))
    a = ap.parse_args(argv)
    rng = np.random.default_rng(a.seed)
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.png"):
        f.unlink()
    jobs = []   # (condition, artist, real_img, machine_img)
    for art in ("matisse", "hokusai", "ingres"):
        reals = []
        for p in sorted((EXTRACT / art).glob("*.json")):
            ld = gm.long_drawing(Drawing.load(p))
            if len(ld.strokes) >= 3:
                reals.append(ld)
        g = gm.Grammar.load(GRAMMARS / f"grammar_{art}.json")
        rimgs = [render(fit_canvas(d), 1) for d in reals]
        gimgs = []
        for i in range(a.per):
            gd = gm.generate_drawing(g, np.random.default_rng([a.seed, i]), (SIDE, SIDE))
            if gd.strokes:
                gimgs.append(render(fit_canvas(gd), 1))
        rq, gq = list(rng.permutation(len(rimgs))), list(rng.permutation(len(gimgs)))
        for i in range(a.per):
            if not rq:
                rq = list(rng.permutation(len(rimgs)))   # second pass: a different window
            if not gq:
                gq = list(rng.permutation(len(gimgs)))
            r = crop(rimgs[rq.pop()], rng)
            m = crop(gimgs[gq.pop()], rng)
            if r is not None and m is not None:
                jobs.append(("test", art, r, m))
        if art == "matisse":
            used = set()
            for cond, fn in (("calib_pos", nulls.shuffled_segments), ("calib_neg", nulls.identity)):
                for i in range(a.calib):
                    k = int(rng.integers(len(reals)))
                    nd = fn(reals[k], np.random.default_rng([a.seed, 99, i]))
                    free = [j for j in range(len(rimgs)) if j not in used and j != k] or list(range(len(rimgs)))
                    jr = int(rng.choice(free)); used.add(jr)
                    r = crop(rimgs[jr], rng)
                    m = crop(render(fit_canvas(nd), 1), rng)
                    if r is not None and m is not None:
                        jobs.append((cond, art, r, m))
    order = rng.permutation(len(jobs))
    key = {}
    for n, j in enumerate(order, 1):
        cond, art, r, m = jobs[j]
        real_left = bool(rng.integers(2))
        img = pair_image(r, m) if real_left else pair_image(m, r)
        name = f"pair_{n:03d}.png"
        img.save(OUT / name)
        key[name] = {"condition": cond, "artist": art, "real": "A" if real_left else "B"}
    Path(a.key).write_text(json.dumps(key, indent=1))
    from collections import Counter
    print(len(key), "pairs →", OUT, "| key →", a.key, "|", dict(Counter(v["condition"] for v in key.values())))


if __name__ == "__main__":
    main()
