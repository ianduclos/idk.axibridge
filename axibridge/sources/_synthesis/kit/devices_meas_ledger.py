# FROZEN from research commit 6f96418: tools/gesture/gesture/kit/devices_meas_ledger.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Device `meas_ledger` (round 15, thread D `meas`): the ledger, third
version. Round 10's ledger tabulated one line by deciles of its length; this
one keeps the books of the sheet's making: one row per step in the order it
was done — what the step was (the arranger's verb or the score's role), who
drew it (hand), from which corpus, how much ink it laid (mm, and a bar of
that length's share in the step's own ink), and its pen width. The rules
can be drawn by a hand with the frame and the lettering kept straight
(Ian, round 11: "keep the lines inside stylized; top and bottom straight")."""
from __future__ import annotations

import numpy as np

from . import devices_meas_read as R
from . import voices_machine_diagram as vd
from ._devices import device
from .core import P

HEAD = ("NO", "DID", "WHO", "FROM", "MM", "", "PEN")
COLX = (0.0, 0.06, 0.24, 0.42, 0.56, 0.65, 0.92)


@device("meas_ledger", family="process", params=[
    P("by", "choice", "step", "rows: step | line", choices=("step", "line")),
    P("max_rows", "int", 30, "most rows (later steps folded into a last 'more' row)", min=3, max=80),
    P("drawn_by", "str", "matisse", "hand that draws the rules ('' = machine-straight)"),
    P("straight", "choice", "frame+text", "with drawn_by: which lines stay straight", choices=vd.STRAIGHT),
    P("amount", "float", 1.2, "with drawn_by: how much fine turning the hand owns", min=0.0, max=3.0),
    P("index", "bool", False, "ring each row's first pen-down on the drawing with its row number"),
    P("label_h", "float", 1.7, "lettering cap height, mm", min=0.6, max=6.0),
    P("pen", "float", 0.18, "pen, mm", min=0.05, max=1.5),
    P("ink", "str", "black", "ink for the table (bars always take their step's own ink when 'source')"),
    P("bars", "str", "source", "ink for the bars: a Flexoki name or 'source'"),
], doc="the books of the sheet's making: one row per step — what it did, who drew it, from which corpus, "
       "how much ink, which pen")
def meas_ledger(dctx, sheet, *, by, max_rows, drawn_by, straight, amount, index, label_h, pen, ink, bars):
    us = [u for u in R.units(sheet, by) if u.length > 0]
    if not us:
        return []
    more = None
    if len(us) > max_rows:
        more = us[max_rows - 1:]
        us = us[:max_rows - 1]
    x0, y0, w, h = dctx.region
    pad = min(3.0 + 0.04 * min(w, h), 8.0)
    x0, y0, w, h = x0 + pad, y0 + pad, w - 2 * pad, h - 2 * pad
    nrow = len(us) + (1 if more else 0)
    rh = h / (nrow + 1.8)
    th = min(label_h, 0.55 * rh)
    rules, letters, bar_polys = [], [], []
    for j, t in enumerate(HEAD):
        letters += R.text(t, x0 + COLX[j] * w, y0, th)
    yh = y0 + 1.25 * rh
    rules.append(R.rule(x0, yh, x0 + w, yh))
    Lmax = max(u.length for u in us + (more or []))
    for i, u in enumerate(us + ([None] if more else [])):
        yt = y0 + (1.6 + i) * rh
        if u is None:
            L = sum(v.length for v in more)
            row = (f"{len(us) + 1:02d}", f"+{len(more)} MORE", "", "", f"{L:.0f}", None, "")
        else:
            who = "/".join(R.short(x, 5) for x in u.hands[:2]) or "-"
            pens = sorted({float(m.meta.get("pen", 0) or 0) for m in u.marks} - {0.0})
            pen_s = "/".join(f"{x:.2g}" for x in (pens[:1] + pens[-1:] if len(pens) > 1 else pens)) or "-"
            row = (f"{i + 1:02d}", u.verb[:8].upper(), who[:11], u.family[:7].upper(), f"{u.length:.0f}", u, pen_s)
        for j, cell in enumerate(row):
            if j == 5 or not cell:
                continue
            letters += R.text(cell, x0 + COLX[j] * w, yt, th)
        if u is not None:
            bx, bw = x0 + COLX[5] * w, (COLX[6] - COLX[5] - 0.03) * w
            yc = yt + 0.5 * th
            bar_polys.append((R.rule(bx, yc, bx + max(u.length / Lmax * bw, 0.4), yc), R.ink_for(bars, u)))
        if i < nrow - 1:
            yr = yt + 1.0 * rh - 0.22 * rh
            rules.append(R.rule(x0 + COLX[1] * w, yr, x0 + (COLX[6] - 0.02) * w, yr))   # < a frame rule
    rules.append(R.rule(x0, y0 + (1.6 + nrow) * rh - 0.3 * rh, x0 + w, y0 + (1.6 + nrow) * rh - 0.3 * rh))
    polys = rules + letters
    if drawn_by:
        from . import library  # noqa: PLC0415
        g = library.load("hand", drawn_by)
        flags = vd.straight_flags(polys, th, straight, 0.0, dctx.rng("straight"))
        polys = vd.hand_drawn(polys, g, dctx.rng("drawn_by", drawn_by), amount=amount, keep=0.006, straight=flags)
    out = R.inks(polys, pen=pen, colour=ink, role="ledger")
    for p, c in bar_polys:
        out += R.inks([p], pen=max(pen, 0.5), colour=c, role="bar")
    if index:
        allp = np.vstack([np.asarray(m.points, float) for m in R.drawing_marks(sheet)])
        for i, u in enumerate(us):
            nrm = R.normal_at(u.points[0], 0)
            out += R.inks([R.circle(u.start, 0.55)] + R.side_label(u.start, nrm, f"{i + 1:02d}", 0.8 * label_h, allp,
                                                                   gap=1.2),
                          pen=pen, colour=R.ink_for(bars, u), role="index")
    return out
