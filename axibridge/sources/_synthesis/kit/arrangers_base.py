# FROZEN from research commit a66c6a5: tools/gesture/gesture/kit/arrangers_base.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Seed arrangers — compose a sheet from parts.

- `single` every part fills the whole (inset) frame: one part = one drawing;
           several parts = several voices sharing ONE surface (polyphony),
           each fitted on its own.
- `grid`   one part per cell (the bench's lines / "each"): parts are grown,
           then placed in equal cells at ONE common scale (the layout with
           the largest common scale, ties → fewer rows), or each as large as
           its cell (`scale: "cell"`). Modulators run after placement, in
           final sheet mm.
"""
from __future__ import annotations

import numpy as np

from .core import P, arranger, native_bbox, refit


@arranger("single", doc="every part fills the frame (several parts share one surface)")
def single(ctx, parts):
    out = []
    for p in parts:
        out += p.run(ctx.box)
    return out


def best_grid(n: int, frame: tuple[float, float], boxes: list[tuple[float, float]]) -> tuple[int, int, float]:
    """(cols, rows, common scale) placing n boxes in equal cells of `frame`:
    the layout with the largest common scale (ties: fewer rows) — the Hand
    Drift bench's `_grid`."""
    W, H = frame
    best = None
    for cols in range(1, n + 1):
        rows = -(-n // cols)
        cw, ch = W / cols, H / rows
        s = min(min(cw / max(bw, 1e-9), ch / max(bh, 1e-9)) for bw, bh in boxes)
        if best is None or s > best[2] + 1e-12:
            best = (cols, rows, s)
    return best


@arranger("grid", params=[
    P("cols", "int", 0, "columns (0 = auto: largest common scale)", min=0, max=12),
    P("scale", "choice", "common", "common: one scale for every part (compare hands at the same size); "
      "cell: each part as large as its cell", choices=("common", "cell")),
    P("gap", "float", 0.0, "gap between cells, mm", min=0.0, max=40.0),
], doc="one part per cell, at one common scale (the bench's 'each')")
def grid(ctx, parts, *, cols, scale, gap):
    x0, y0, W, H = ctx.box
    grown = [p.voice(ctx.box) for p in parts]
    n = len(parts)
    nb = [native_bbox(m) for m in grown]
    natives = all(b is not None for b in nb)
    if natives:
        boxes = [tuple(b[1] - b[0]) for b in nb]
    else:
        boxes = [tuple(np.ptp(np.vstack([mk.points for mk in m]), axis=0)) if m else (1.0, 1.0) for m in grown]
    if cols == 0:
        cols, rows, s = best_grid(n, (W, H), boxes)
    else:
        rows = -(-n // cols)
        cw0, ch0 = W / cols, H / rows
        s = min(min(cw0 / max(bw, 1e-9), ch0 / max(bh, 1e-9)) for bw, bh in boxes)
    cw, ch = W / cols, H / rows
    out = []
    for i, (p, marks) in enumerate(zip(parts, grown)):
        r, c = divmod(i, cols)
        cell = (x0 + c * cw + gap / 2, y0 + r * ch + gap / 2, max(cw - gap, 1e-3), max(ch - gap, 1e-3))
        if scale == "common" and natives and gap == 0:
            placed = refit(marks, cell, scale=s)
        elif scale == "common" and natives:
            k = min(min((cw - gap) / max(bw, 1e-9), (ch - gap) / max(bh, 1e-9)) for bw, bh in boxes)
            placed = refit(marks, cell, scale=k)
        else:
            placed = refit(marks, cell)
        out += p.modulate(placed, cell)
    return out
