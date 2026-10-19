"""Device `meas_air` (round 15, thread D `meas`): the pen's travel through
the air. Between one line and the next the plotter lifts and moves; that
route is the drawing's process and is never seen. Laid over the drawing it
is a fine straight-line constellation from each pen-up to the next pen-down
(rings at the pen-downs, numbered every n-th, in order); beside it, the air
route alone, scaled into the panel: the drawing's negative, with the total
air distance and the number of lifts."""
from __future__ import annotations

import numpy as np

from . import devices_meas_read as R
from ._devices import device
from .core import P


def air_moves(sheet, level: str, min_gap: float):
    """[(from, to, unit index of the 'to' line)] in the pen's order.
    level: ink (every plotted polyline), line or step (lifts between units)."""
    if level == "ink":
        segs = [(np.asarray(k.points[0], float), np.asarray(k.points[-1], float))
                for k in sheet.inks if (k.meta or {}).get("layer") != "device" and len(k.points) >= 2]
        ix = list(range(len(segs)))
    else:
        us = R.units(sheet, level)
        segs = [(np.asarray(u.marks[0].points[0], float), np.asarray(u.marks[-1].points[-1], float)) for u in us]
        ix = [u.index for u in us]
    out = []
    for (a0, a1), (b0, b1), i in zip(segs[:-1], segs[1:], ix[1:]):
        if float(np.linalg.norm(b0 - a1)) >= min_gap:
            out.append((a1, b0, i))
    return out, segs, (segs[0][0] if segs else None)


@device("meas_air", family="process", params=[
    P("level", "choice", "line", "which lifts: ink (every plotted polyline) | line | step", choices=("ink", "line", "step")),
    P("min_gap", "float", 1.0, "lifts shorter than this are not drawn, mm", min=0.0, max=50.0),
    P("ring", "float", 0.5, "pen-down ring radius, mm (0 = none)", min=0.0, max=4.0),
    P("number_every", "int", 1, "number every n-th pen-down (0 = none)", min=0, max=200),
    P("label_h", "float", 1.3, "label cap height, mm", min=0.6, max=6.0),
    P("pen", "float", 0.12, "pen, mm", min=0.05, max=1.5),
    P("ink", "str", "red", "Flexoki ink name"),
], doc="the pen's travel through the air between lines (pen-up → pen-down), over the drawing or as its own "
       "negative beside it")
def meas_air(dctx, sheet, *, level, min_gap, ring, number_every, label_h, pen, ink):
    moves, segs, first = air_moves(sheet, level, min_gap)
    if not moves:
        return []
    polys = [np.array([a, b]) for a, b, _ in moves]
    downs = [b for _, b, _ in moves]
    total = float(sum(np.linalg.norm(b - a) for a, b, _ in moves))
    if dctx.place in ("over", "under"):
        allp = np.vstack([np.asarray(m.points, float) for m in R.drawing_marks(sheet)])
        out_polys = list(polys)
        # numbers: the line/step landed on, in drawing order (the same numbers as
        # meas_inventory and meas_ledger at the same level); ink level: the lift's own count
        downs_n = [(first, np.array([0.0, -1.0]), 1)] + [
            (b, (lambda d: np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-12))(b - a),
             (i + 1) if level != "ink" else (j + 2)) for j, (a, b, i) in enumerate(moves)]
        for j, (b, nrm, num) in enumerate(downs_n):
            if ring > 0:
                out_polys.append(R.circle(b, ring))
            if number_every and (j % number_every == 0):
                out_polys += R.side_label(b, nrm, f"{num:02d}", label_h, allp, gap=ring + 0.8)
        return R.inks(out_polys, pen=pen, colour=ink, role="air")
    x0, y0, w, h = dctx.region
    pad = min(3.0 + 0.04 * min(w, h), 8.0)
    bx = dctx.drawing_box
    frame = [np.array([[bx[0], bx[1]], [bx[0] + bx[2], bx[1] + bx[3]]])]
    k, off = R.fit_into(frame, (x0 + pad, y0 + pad, w - 2 * pad, h - 2 * pad - 2.5 * label_h))
    out_polys = [p * k + off for p in polys]
    if ring > 0:
        out_polys += [R.circle(b * k + off, max(ring * 0.7, 0.3)) for b in downs]
    out_polys += R.text(f"AIR {total / 1000:.2f} M  {len(moves)} LIFTS", x0 + pad, y0 + h - pad - label_h, label_h)
    return R.inks(out_polys, pen=pen, colour=ink, role="air")
