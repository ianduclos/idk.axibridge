# FROZEN from research commit 6f96418: tools/gesture/gesture/kit/devices_meas_turning.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Device `meas_turning` (round 15, thread D `meas`): a new version of the
κ(s) chart, which Ian likes separate but which has become a cliché inside
compositions. Not κ against s in rows: every line of the sheet drawn from
one common origin as its accumulated turning — x = arc length (mm, one
scale for all), y = how many whole turns it has made so far (up = clockwise
on the paper). A river hand stays near the axis and wanders; an oxbow or a
coil climbs steadily; a dance zigzags; a machine stair steps. The fan of
all of them, each in its own ink, compares the sources by how they turn,
and the longest few are named at their ends with their final count."""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from . import devices_meas_read as R
from ._devices import device
from .core import P


def turning(p: np.ndarray, step: float = 0.5, smooth_mm: float = 1.0):
    """(s, turns) of one polyline: accumulated heading change in whole turns."""
    p = np.asarray(p, float)
    d = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.r_[0.0, np.cumsum(d)]
    if s[-1] < 2 * step:
        return None
    t = np.arange(0.0, s[-1], step)
    q = np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])
    sig = max(smooth_mm / step, 0.5)
    q = np.column_stack([gaussian_filter1d(q[:, 0], sig, mode="nearest"),
                         gaussian_filter1d(q[:, 1], sig, mode="nearest")])
    dq = np.diff(q, axis=0)
    th = np.unwrap(np.arctan2(dq[:, 1], dq[:, 0]))
    return t[1:], (th - th[0]) / (2 * math.pi)


@device("meas_turning", family="process", params=[
    P("min_len", "float", 6.0, "shortest line drawn, mm", min=0.5, max=200.0),
    P("max_lines", "int", 120, "most lines (the longest kept)", min=2, max=600),
    P("name", "int", 6, "how many lines are named at their ends (the longest)", min=0, max=40),
    P("exclude", "str", "chart", "families left out, comma-separated (a found chart is a measurement, not a gesture)"),
    P("x", "choice", "mm", "mm: one arc-length scale for every line | share: each line across the full width "
      "(compares how, not how long)", choices=("mm", "share")),
    P("smooth", "float", 1.0, "heading smoothing, mm (the pen's tremor is not turning)", min=0.0, max=20.0),
    P("label_h", "float", 1.5, "label cap height, mm", min=0.6, max=6.0),
    P("pen", "float", 0.15, "pen, mm", min=0.05, max=1.5),
    P("ink", "str", "source", "Flexoki ink name, or 'source' (each line in its own ink)"),
], doc="a new κ version: every line from one origin as its accumulated turning (whole turns) against arc length; "
       "the fan compares how the sources turn")
def meas_turning(dctx, sheet, *, min_len, max_lines, name, exclude, x, smooth, label_h, pen, ink):
    curves = []
    skip = {f.strip() for f in str(exclude).split(",") if f.strip()}
    for u in R.units(sheet, "line"):
        if u.family in skip:
            continue
        for m in u.marks:
            if m.length() >= min_len:
                tr = turning(np.asarray(m.points, float), step=0.5, smooth_mm=smooth)
                if tr is not None:
                    curves.append((m.length(), tr, u))
    if not curves:
        return []
    curves.sort(key=lambda c: -c[0])
    curves = curves[:max_lines]
    x0, y0, w, h = dctx.region
    pad = min(3.0 + 0.04 * min(w, h), 8.0)
    lab_w = R.text_w("MEANDE +00.0", label_h) + 2.0 if name else 0.0
    gut = R.text_w("-00", label_h) + 2.5
    xa, wa = x0 + pad + gut, w - 2 * pad - gut - lab_w
    smax = max(c[1][0][-1] for c in curves)
    tmax = max(float(np.max(np.abs(c[1][1]))) for c in curves)
    tmax = max(tmax, 0.5)
    yc = y0 + h / 2
    ky = (h / 2 - pad - label_h) / tmax
    kx = wa / smax
    if x == "share":
        curves = [(L, (s / s[-1] * smax, tt), u) for L, (s, tt), u in curves]
    out = []
    for L, (s, tt), u in curves:
        out += R.inks([np.column_stack([xa + s * kx, yc - tt * ky])], pen=pen, colour=R.ink_for(ink, u), role="fan")
    axes = [R.rule(xa, yc, xa + wa, yc)]
    stepT = R.nice(tmax / 4)
    v = stepT
    while v <= tmax + 1e-9:
        for sg in (1, -1):
            y = yc - sg * v * ky
            axes.append(R.rule(xa - 1.0, y, xa, y))
            axes += R.text(f"{sg * v:+g}", xa - 1.6, y - 0.4 * label_h, 0.8 * label_h, anchor="right")
        v += stepT
    axes += R.text("TURNS", xa - 1.6, y0 + pad, 0.8 * label_h, anchor="right")
    stepS = R.nice(smax / 5)
    v = stepS
    while x == "mm" and v <= smax + 1e-9:
        axes.append(R.rule(xa + v * kx, yc, xa + v * kx, yc + 0.8))
        v += stepS
    if x == "mm":
        axes += R.text(f"{stepS:g} MM", xa + stepS * kx, yc + 1.4, 0.8 * label_h, anchor="centre")
    out += R.inks(axes, pen=pen, colour="black" if ink == "source" else ink, role="axis")
    named = []
    for L, (s, tt), u in curves[:name]:
        y = yc - tt[-1] * ky
        for yy in named:
            if abs(y - yy) < 1.2 * label_h:
                y = yy + 1.2 * label_h * (1 if y >= yy else -1)
        named.append(y)
        lab = f"{u.label(6)} {tt[-1]:+.1f}"
        out += R.inks(R.text(lab, xa + s[-1] * kx + 1.2, y - 0.4 * label_h, 0.8 * label_h), pen=pen,
                      colour=R.ink_for(ink, u), role="name")
    return out
