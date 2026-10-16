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
    W, H = (np.ceil((hi - lo) * k) + 80).astype(int)
    return Drawing(st, source=d.source, size=(int(W), int(H)))


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
        for i in range(max(6, a.per // 2)):
            gd = gm.generate_drawing(g, np.random.default_rng([a.seed, i]), (SIDE, SIDE))
            if gd.strokes:
                gimgs.append(render(fit_canvas(gd), 1))
        for i in range(a.per):
            r = crop(rimgs[int(rng.integers(len(rimgs)))], rng)
            m = crop(gimgs[int(rng.integers(len(gimgs)))], rng)
            if r is not None and m is not None:
                jobs.append(("test", art, r, m))
        if art == "matisse":
            for cond, fn in (("calib_pos", nulls.shuffled_segments), ("calib_neg", nulls.identity)):
                for i in range(a.calib):
                    k = int(rng.integers(len(reals)))
                    nd = fn(reals[k], np.random.default_rng([a.seed, 99, i]))
                    r = crop(rimgs[int(rng.integers(len(rimgs)))], rng)
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
