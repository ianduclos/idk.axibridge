"""Round 12 keeps — river belt with tighter curves (research only, one image).

Ian on round 11's river_belt specimens: "river could work nicely using
tighter curves like in the first one" — the first tile is the SOURCE, a
meander belt: tight bends strung along a valley. The learned hand drifts
anywhere and its bends open out once the sheet is fitted.

Variant: keep the hand's own curvature sequence κ(s) and re-integrate it with
two changes: a gain on κ (tighter bends) and a restoring pull of the heading
back to the valley axis (so the bends string along a belt instead of
wandering). θ'(s) = gain·κ̃(s) − pull·sin(θ − θ_valley), κ̃ = κ minus its
40 mm running mean (the hand's slow drift of heading). Nothing else is
invented: every bend is the hand's, in its order.

    .local/gesture/.venv/bin/python tools/gesture/experiments/keeps12_river_belt.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/gesture"))
from gesture import kit  # noqa: E402

OUT = ROOT / "tools/gesture/results/keeps12-river_belt_tight.jpg"
SEED = 12407                 # round 12: own seed (7000 is retired)
STEP = 0.25                  # mm


def hand_line(seed: int, length: float) -> np.ndarray:
    r = {"kit": 1, "frame": [130.0, 100.0], "seed": seed, "arranger": {"id": "single"},
         "parts": [{"voice": {"id": "hand", "hand": "river_belt", "length": length, "joins": "smooth"}}],
         "renderer": {"id": "wire", "pen": 0.35}}
    sh = kit.run(r)
    return np.vstack([np.asarray(i.points, float) for i in sh.inks]), r


def kappa_of(p: np.ndarray) -> np.ndarray:
    d = np.diff(p, axis=0)
    seg = np.linalg.norm(d, axis=1)
    keep = seg > 1e-9
    p = np.vstack([p[0], p[1:][keep]])
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    u = np.arange(0.0, s[-1], STEP)
    q = np.column_stack([np.interp(u, s, p[:, 0]), np.interp(u, s, p[:, 1])])
    th = np.unwrap(np.arctan2(*np.diff(q, axis=0).T[::-1]))
    return gaussian_filter1d(np.diff(th) / STEP, 2.0, mode="nearest")


def belt(kappa: np.ndarray, gain: float, pull: float) -> np.ndarray:
    # the hand's slow drift of heading is taken out (κ minus its 40 mm running
    # mean), so only its bends remain; the pull then holds them to the valley
    kappa = kappa - gaussian_filter1d(kappa, 40.0 / STEP, mode="nearest")
    th, x, y = 0.0, 0.0, 0.0
    pts = [(x, y)]
    for k in kappa:
        th += STEP * (gain * k - pull * np.sin(th))          # valley axis: θ = 0
        x += STEP * np.cos(th)
        y += STEP * np.sin(th)
        pts.append((x, y))
    return np.asarray(pts)


def fit(p: np.ndarray, box) -> np.ndarray:
    x0, y0, w, h = box
    lo, hi = p.min(axis=0), p.max(axis=0)
    k = min(w / max(hi[0] - lo[0], 1e-9), h / max(hi[1] - lo[1], 1e-9))
    return (p - (lo + hi) / 2) * k + np.array([x0 + w / 2, y0 + h / 2])


def main() -> None:
    from PIL import Image, ImageDraw  # noqa: PLC0415
    line, recipe = hand_line(SEED, 8.0)
    kap = kappa_of(line)
    variants = [("the hand as learned (river_belt, 8 R)", None, None),
                ("belt: gain 1.0, pull 0.15", 1.0, 0.15),
                ("belt: gain 1.8, pull 0.25 (tighter)", 1.8, 0.25),
                ("belt: gain 2.6, pull 0.35 (tightest)", 2.6, 0.35)]
    W, H, px = 300.0, 60.0, 8.0                               # one valley per row, 300 x 60 mm
    rows = []
    for label, g, pl in variants:
        p = line if g is None else belt(kap, g, pl)
        q = fit(p, (4.0, 4.0, W - 8.0, H - 8.0)) * px
        im = Image.new("RGB", (int(W * px), int(H * px + 40)), (255, 252, 240))
        dr = ImageDraw.Draw(im)
        dr.line([tuple(v) for v in q], fill=(16, 15, 15), width=3, joint="curve")
        dr.text((12, int(H * px) + 8), label, fill=(16, 15, 15))
        rows.append(im)
    sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows) + 10 * len(rows)), (242, 240, 229))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + 10
    sheet.thumbnail((2400, 2400))
    sheet.save(OUT, quality=88, optimize=True)
    OUT.with_suffix(".recipe.json").write_text(json.dumps(
        {"script": "tools/gesture/experiments/keeps12_river_belt.py", "hand_recipe": recipe, "step_mm": STEP,
         "variants": [{"label": lb, "gain": g, "pull": pl} for lb, g, pl in variants]}, indent=1) + "\n")
    print(OUT)


if __name__ == "__main__":
    main()
