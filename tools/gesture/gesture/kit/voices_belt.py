"""A hand's own bends strung along a valley: the river belt, tighter (round-12 keeps, 2026-10-18).

Ian on round 11's river_belt specimens: "river could work nicely using
tighter curves like in the first one"; on the keeps12 side image of this
procedure (`experiments/keeps12_river_belt.py`, gains 1.0 / 1.8 / 2.6):
"loving this kinda stuff, line that morphs gesture type. I'd love to explore
this concept more."

voice `belt`: one learned hand's line, drawn whole (the `hand` voice's drift
line) into `read_box` mm; its curvature κ(s) read at `step` mm and smoothed;
the hand's slow drift of heading removed (κ minus its `drift_mm` running
mean); then re-integrated with a gain and a restoring pull of the heading
back to a valley axis:

    θ'(s) = g(s)·κ̃(s) − pull·sin(θ),   g(s) = gain + (gain_end − gain)·s/L

So every bend is the hand's, in its order; `gain` tightens them and `pull`
strings them along a belt instead of letting them wander. `gain_end` (null =
`gain`) ramps the gain along the line: the line morphs from one gesture type
into another — loose hand bends into a tight meander belt, or back.

Defaults reproduce the keeps12 experiment exactly (its `hand_line`,
`kappa_of`, `belt` and seed), row 3 (gain 1.8, pull 0.25) — tested in
tests/test_kit_keeps13.py.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .core import P, fit, fitted, voice
from .voices_base import grow

# the keeps12 sheet: a 130 x 100 mm frame inset by a 0.35 mm wire's half width
READ_BOX = [0.175, 0.175, 129.65, 99.65]


def kappa_of(p: np.ndarray, step: float) -> np.ndarray:
    """κ(s) of a polyline (mm) at `step` mm, smoothed over 2 samples."""
    d = np.diff(p, axis=0)
    seg = np.linalg.norm(d, axis=1)
    keep = seg > 1e-9
    p = np.vstack([p[0], p[1:][keep]])
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    u = np.arange(0.0, s[-1], step)
    q = np.column_stack([np.interp(u, s, p[:, 0]), np.interp(u, s, p[:, 1])])
    th = np.unwrap(np.arctan2(*np.diff(q, axis=0).T[::-1]))
    return gaussian_filter1d(np.diff(th) / step, 2.0, mode="nearest")


def belt_line(kappa: np.ndarray, *, gain: float, pull: float, step: float, drift_mm: float,
              gain_end: float | None = None) -> np.ndarray:
    """Re-integrate κ with the slow drift removed, a gain (ramped to
    gain_end along the line) and a pull to the valley axis θ = 0."""
    kappa = kappa - gaussian_filter1d(kappa, drift_mm / step, mode="nearest")
    n = len(kappa)
    if gain_end is None:
        g = [gain] * n
    else:
        g = gain + (gain_end - gain) * (np.arange(n) / max(n - 1, 1))
    th, x, y = 0.0, 0.0, 0.0
    pts = [(x, y)]
    for k, gk in zip(kappa, g):
        th += step * (gk * k - pull * np.sin(th))
        x += step * np.cos(th)
        y += step * np.sin(th)
        pts.append((x, y))
    return np.asarray(pts)


@voice("belt", params=[
    P("hand", "ref", "river_belt", "the hand whose bends are strung along the valley", kind="hand"),
    P("length", "float", 8.0, "the hand's line length, in reference lengths of the research frame",
      min=0.5, max=12.0),
    P("joins", "choice", "smooth", "the hand's joins (as the `hand` voice)", choices=("smooth", "chain")),
    P("gain", "float", 1.8, "curvature gain: > 1 tightens every bend", min=0.0, max=4.0),
    P("gain_end", "float", None, "gain at the line's end, ramped linearly from `gain` (null = constant): "
      "the line morphs from one gesture type into another", min=0.0, max=4.0, optional=True),
    P("pull", "float", 0.25, "pull of the heading back to the valley axis, per mm (0 = the hand wanders)",
      min=0.0, max=1.5),
    P("drift_mm", "float", 40.0, "the hand's slow drift of heading (κ's running mean over this many mm) is "
      "taken out", min=5.0, max=200.0),
    P("step", "float", 0.25, "curvature sampling and integration step, mm", min=0.1, max=1.0),
    P("read_box", "floats", READ_BOX, "x0, y0, w, h (mm) the hand's line is drawn into before its curvature is "
      "read (κ in mm depends on this size): the keeps12 sheet's"),
], doc="a hand's own bends, its drift taken out, re-integrated tighter and pulled along a valley: the river belt")
def belt(ctx, *, hand, length, joins, gain, gain_end, pull, drift_mm, step, read_box):
    if len(read_box) != 4 or read_box[2] <= 0 or read_box[3] <= 0:
        raise ValueError("belt: read_box is x0, y0, w, h with w, h > 0")
    pts, _ch, meta = grow(ctx, [hand], length=length, blend="mixture", joins=joins, plateau=0.12)
    s, off = fit([pts], read_box)
    line = np.asarray(pts, float) * s + off
    p = belt_line(kappa_of(line, step), gain=gain, pull=pull, step=step, drift_mm=drift_mm, gain_end=gain_end)
    md = {**meta, "belt": {"gain": gain, "gain_end": gain_end, "pull": pull, "drift_mm": drift_mm}}
    return fitted([p], ctx.box, None, [md])
