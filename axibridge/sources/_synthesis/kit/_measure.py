# FROZEN from research commit d5ccd75: tools/gesture/gesture/kit/_measure.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Measure a line against the library (S0′, lead-owned; lifted from round 16 B `hdist_measure`).

One shared answer to "which hand does this line read as?": the line is drawn
at its real pen width, cut into equal windows, read through the 74-feature
panel with the standard preprocessing (σ ≥ 7 line widths, the medium
projector fitted on the real drawings), keeping the shape groups only, and
compared with every library hand's own generated pages.

    from gesture.kit._measure import against_library
    r = against_library(points_mm, own="matisse")
    r["nearest"][:3]   # [("matisse", 0.81), ("trail_miner", 1.02), …]  distance in projected units
    r["own_rank"]      # 1 = the line reads as its own hand

Research-only: it needs the panel files under `.local/gesture/out/` (built by
`experiments/hybrid_hands.py` and `experiments/hands_trails.py`) and is never
frozen into the app. Imports are lazy so the kit stays importable without them.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
LIB_GEN = ROOT / ".local/gesture/out/hands_trails/panel_gen.json"      # library hands' own pages (read only)
REAL = ROOT / ".local/gesture/out/hybrid_hands/panel_real.json"        # real drawings: fits the projector
WINDOWS = 6
PEN = 0.45
PX = 10.0                  # px per mm for the panel drawing
# the line's shape only: curvature, extrema, inflections, turning, clothoid segments. Stroke counts,
# lengths, gaps and widths read the FORMAT (one cut line vs a page of strokes), not the hand.
SHAPE_GROUPS = ("k", "ext", "infl", "turn", "cl")
SIGMA_FRAC = 0.0           # σ from the floor alone: 7 pen widths, the finest scale the pen can show

_PROJ: dict = {}


def line_drawing(points_mm, pen: float = PEN, windows: int = WINDOWS):
    from ._research.core import Drawing, Stroke  # noqa: PLC0415
    p = np.asarray(points_mm, float) * PX
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    cuts = np.searchsorted(s, np.linspace(0, s[-1], windows + 1))
    cuts[-1] = len(p) - 1
    st = [Stroke(p[a:b + 1], np.full(b + 1 - a, pen * PX)) for a, b in zip(cuts[:-1], cuts[1:]) if b - a >= 3]
    hi = p.max(axis=0)
    return Drawing(st, "hdist", (int(hi[0]) + 10, int(hi[1]) + 10), {})


def line_features(points_mm, pen: float = PEN, windows: int = WINDOWS) -> dict:
    from ._research import medium, panel  # noqa: PLC0415
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _ = panel.features_with_info(line_drawing(points_mm, pen, windows), sigma_frac=SIGMA_FRAC,
                                        sigma_min_w=medium.SIGMA_MIN_W)
    return f


def projector():
    """(transform, feature names, library pages' features), loaded once."""
    if "tf" not in _PROJ:
        from ._research import hybrid as hy  # noqa: PLC0415
        tf, names, _, _ = hy.projector(json.loads(REAL.read_text()))
        _PROJ.update(tf=tf, names=names, lib=json.loads(LIB_GEN.read_text()))
    return _PROJ["tf"], _PROJ["names"], _PROJ["lib"]


def Z(feats: dict) -> tuple[list[str], np.ndarray]:
    """{key: features} → (sorted keys, projected shape-group coordinates)."""
    tf, names, _ = projector()
    keys = sorted(k for k in feats if feats[k])
    X = np.array([[feats[k].get(n, np.nan) for n in names] for k in keys], float)
    cols = [i for i, n in enumerate(names) if n.split("_", 1)[0] in SHAPE_GROUPS]
    return keys, tf(X)[:, cols]


def library_centroids(hands=None) -> dict:
    """hand → centroid of its own generated pages (every library hand when `hands` is None)."""
    _, _, lib = projector()
    if hands is None:
        hands = sorted({k.split("|")[0] for k in lib})
    k, z = Z({k: v for k, v in lib.items() if k.split("|")[0] in hands})
    g = np.array([x.split("|")[0] for x in k])
    return {h: z[g == h].mean(0) for h in hands if (g == h).any()}


def against_library(points_mm, *, pen: float = PEN, windows: int = WINDOWS, own: str | None = None,
                    hands=None) -> dict:
    """Where one line sits among the library hands: `nearest` [(hand, distance)] sorted, and
    `own_rank` (1-based) when `own` names the hand it was drawn in."""
    cen = library_centroids(hands)
    _, z = Z({"line": line_features(points_mm, pen, windows)})
    d = sorted(((h, float(np.linalg.norm(z[0] - c))) for h, c in cen.items()), key=lambda t: (t[1], t[0]))
    out = {"nearest": [(h, round(v, 4)) for h, v in d]}
    if own is not None:
        names = [h for h, _ in d]
        out["own_rank"] = names.index(own) + 1 if own in names else None
    return out
