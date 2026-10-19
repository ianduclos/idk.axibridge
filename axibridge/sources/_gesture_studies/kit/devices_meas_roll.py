# FROZEN from research commit 9ab70ac: tools/gesture/gesture/kit/devices_meas_roll.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Device `meas_roll` (round 15, thread D `meas`): the drawing transcribed
as a roll, the way a player-piano roll transcribes a performance. Left to
right is the pen's order, each line given the width of the ink it laid
(cumulative mm); top to bottom are the sources it came from, one lane per
corpus family (or per hand). Each line sits in its lane as itself, shrunk
whole, in its own ink. It reads who spoke when and for how long, and how the
sheet alternated between them: things the finished drawing hides."""
from __future__ import annotations

import numpy as np

from . import devices_meas_read as R
from ._devices import device
from .core import P


def _stretched(polys, x, sw, cy, hh):
    """The unit's marks end to end, turned to their joint chord, stretched to
    the note box (x: along the chord → sw; y: sway → ±hh/2, one scale)."""
    cat = np.vstack(polys)
    q = R.chord_frame(cat)
    lo, hi = q.min(axis=0), q.max(axis=0)
    kx = sw / max(hi[0] - lo[0], 1e-9)
    ky = hh / max(hi[1] - lo[1], 1e-9)
    ky = min(ky, kx * 6.0)                       # a nearly straight line stays nearly straight
    mid = (lo[1] + hi[1]) / 2
    out, i = [], 0
    for p in polys:
        n = len(p)
        qq = q[i:i + n]
        out.append(np.column_stack([x + (qq[:, 0] - lo[0]) * kx, cy + (qq[:, 1] - mid) * ky]))
        i += n
    return out


@device("meas_roll", family="process", params=[
    P("by", "choice", "line", "the roll's notes: line (each line) | step (each arranger step)", choices=("line", "step")),
    P("lanes", "choice", "family", "one lane per corpus family | per hand", choices=("family", "hand")),
    P("shape", "choice", "stretched", "stretched: each line turned to its chord and stretched to its note "
      "(length → width, sway → lane height) | whole: each line shrunk whole, its own orientation and proportions",
      choices=("stretched", "whole")),
    P("fill", "float", 0.78, "how much of its lane a note may take (height)", min=0.2, max=1.0),
    P("gap", "float", 0.6, "air between notes, mm", min=0.0, max=6.0),
    P("label_h", "float", 1.6, "lane label cap height, mm", min=0.6, max=6.0),
    P("axis", "bool", True, "a baseline of drawn mm, ticked where the step changes"),
    P("pen", "float", 0.18, "pen, mm", min=0.05, max=1.5),
    P("ink", "str", "source", "Flexoki ink name, or 'source' (each note in its line's ink)"),
], doc="the drawing as a roll: pen order left to right (width = ink laid), one lane per source; each line "
       "shrunk whole into its lane")
def meas_roll(dctx, sheet, *, by, lanes, shape, fill, gap, label_h, axis, pen, ink):
    us = [u for u in R.units(sheet, by) if u.length > 0]
    if not us:
        return []
    key = (lambda u: u.family) if lanes == "family" else (lambda u: u.hands[0] if u.hands else u.family)
    names: list[str] = []
    for u in us:
        if key(u) not in names:
            names.append(key(u))
    x0, y0, w, h = dctx.region
    pad = min(2.0 + 0.04 * min(w, h), 5.0)
    labs = [R.short(n, 7) for n in names]
    gut = max(R.text_w(t, label_h) for t in labs) + 2.5
    ax_h = 2.6 * label_h if axis else 0.0
    xa, wa = x0 + pad + gut, w - 2 * pad - gut
    ya, ha = y0 + pad, h - 2 * pad - ax_h
    lh = ha / len(names)
    total = sum(u.length for u in us)
    usable = wa - gap * (len(us) - 1)
    if usable <= wa * 0.3:                        # too many notes for the gap: let them touch
        gap, usable = 0.0, wa
    k = usable / total
    out = []
    x = xa
    bounds = []
    for u in us:
        sw = u.length * k
        lane = names.index(key(u))
        cy = ya + (lane + 0.5) * lh
        polys = [p for p in u.points if len(p) >= 2]
        col = R.ink_for(ink, u)
        if sw < 0.5:
            out += R.inks([R.rule(x + sw / 2, cy - 0.15 * lh, x + sw / 2, cy + 0.15 * lh)], pen=pen, colour=col,
                          role="note")
        elif shape == "whole":
            sc, off = R.fit_into(polys, (x, cy - fill * lh / 2, sw, fill * lh))
            out += R.inks([p * sc + off for p in polys], pen=pen, colour=col, role="note")
        else:
            out += R.inks(_stretched(polys, x, sw, cy, fill * lh), pen=pen, colour=col, role="note")
        bounds.append((x, x + sw, u.step))
        x += sw + gap
    lab_polys = []
    for j, t in enumerate(labs):
        lab_polys += R.text(t, xa - 2.0, ya + (j + 0.5) * lh - label_h / 2, label_h, anchor="right")
    if axis:
        yb = ya + ha + 0.8 * label_h
        lab_polys.append(R.rule(xa, yb, xa + wa, yb))
        prev = None
        for a, b, st in bounds:
            if st != prev:
                lab_polys.append(R.rule(a, yb, a, yb + 0.7 * label_h))
                prev = st
        lab_polys.append(R.rule(xa + wa, yb, xa + wa, yb + 0.7 * label_h))
        lab_polys += R.text("0", xa, yb + 0.9 * label_h, 0.8 * label_h, anchor="centre")
        lab_polys += R.text(f"{total:.0f} MM", xa + wa, yb + 0.9 * label_h, 0.8 * label_h, anchor="right")
    out += R.inks(lab_polys, pen=pen, colour="black" if ink == "source" else ink, role="lane")
    return out
