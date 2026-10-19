# FROZEN from research commit c712045: tools/gesture/gesture/kit/devices_meas_inventory.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Device `meas_inventory` (round 15, thread D `meas`): the numbered atlas,
third version. Round 10 cut ONE line into specimens at its inflections; a
round-14 sheet is many lines from many sources, so this takes the sheet
apart into what it was made of: each step (a ccolour object, a cimpro
move, a score layer, a part) laid out alone, in the order it was drawn, at
one common scale, numbered and named by the hand that drew it. On the
drawing, a small ring marks where the pen first touched for that step, with
the same number. The pairing that Ian kept in round 10, at sheet scale."""
from __future__ import annotations

import math

import numpy as np

from . import devices_meas_read as R
from ._devices import device
from .core import P


@device("meas_inventory", family="process", params=[
    P("by", "choice", "step", "what is inventoried: step (what the arranger did) | line", choices=("step", "line")),
    P("name", "choice", "hand", "the label under each item: hand | role | both", choices=("hand", "role", "both")),
    P("cols", "int", 0, "columns (0 = from the region's shape)", min=0, max=40),
    P("scale", "float", 0.8, "common scale percentile: items larger than this share are shrunk to fit and marked "
      "with their own scale", min=0.3, max=1.0),
    P("index", "bool", True, "number each item's first touch on the drawing"),
    P("max_items", "int", 40, "most items shown (evenly sampled over the order)", min=2, max=200),
    P("label_h", "float", 1.6, "label cap height, mm", min=0.6, max=6.0),
    P("pen", "float", 0.18, "pen, mm", min=0.05, max=1.5),
    P("ink", "str", "source", "Flexoki ink name, or 'source' (each item in its own ink)"),
], doc="the sheet taken apart into its steps, in drawing order, one common scale, numbered on the drawing at "
       "the pen's first touch")
def meas_inventory(dctx, sheet, *, by, name, cols, scale, index, max_items, label_h, pen, ink):
    us = [u for u in R.units(sheet, by) if u.length > 0]
    if not us:
        return []
    if len(us) > max_items:
        pick = np.round(np.linspace(0, len(us) - 1, max_items)).astype(int)
        us = [us[i] for i in pick]
    x0, y0, w, h = dctx.region
    pad = min(2.0 + 0.03 * min(w, h), 5.0)
    n = len(us)
    if cols <= 0:
        cols = max(int(round(math.sqrt(n * (w - 2 * pad) / max(h - 2 * pad, 1e-9)))), 1)
    rows = -(-n // cols)
    cw, ch = (w - 2 * pad) / cols, (h - 2 * pad) / rows
    lab_h = min(label_h, 0.16 * ch)
    bw, bh = 0.86 * cw, ch - 2.4 * lab_h - 0.6
    ext = [np.ptp(np.vstack(u.points), axis=0) for u in us]
    fits = [min(bw / max(e[0], 1e-9), bh / max(e[1], 1e-9)) for e in ext]
    common = float(np.quantile(fits, 1.0 - scale)) if n > 1 else fits[0]
    out = []
    allp = np.vstack([np.vstack(u.points) for u in R.units(sheet, by)])
    for i, u in enumerate(us):
        r, c = divmod(i, cols)
        cx0, cy0 = x0 + pad + c * cw, y0 + pad + r * ch
        k = min(common, fits[i])
        pts = u.points
        cat = np.vstack(pts)
        mid = (cat.min(axis=0) + cat.max(axis=0)) / 2
        centre = np.array([cx0 + cw / 2, cy0 + 0.3 + bh / 2])
        col = R.ink_for(ink, u)
        out += R.inks([(p - mid) * k + centre for p in pts], pen=pen, colour=col, role="item")
        nm = {"hand": u.label(7), "role": u.verb[:7].upper(),
              "both": f"{u.verb[:5].upper()} {u.label(6)}"}[name]
        lab = f"{i + 1:02d} {nm}"
        if k < common * 0.67:
            lab += f" /{common / k:.0f}"
        out += R.inks(R.text(lab, cx0 + cw / 2, cy0 + bh + 1.0, lab_h, anchor="centre"), pen=pen,
                      colour="black" if ink == "source" else ink, role="label")
        if index:
            p0 = u.start
            nrm = R.normal_at(pts[0], 0)
            polys = [R.circle(p0, 0.55)] + R.side_label(p0, nrm, f"{i + 1:02d}", 0.8 * label_h, allp, gap=1.2)
            out += R.inks(polys, pen=pen, colour=col, role="index")
    return out
