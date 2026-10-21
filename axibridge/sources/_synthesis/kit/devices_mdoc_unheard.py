# FROZEN from research commit d5ccd75: tools/gesture/gesture/kit/devices_mdoc_unheard.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Device `mdoc_unheard` (round 16, thread D `mdoc`, its own): the drawing
as it would have been had no line listened.

Only an executable score can show this: the device replays the sheet's
written score through the public executor with every relation taken out
(or only the kinds named in `drop`), and draws that unheard drawing small,
beside the real one. On it, the stretches that the listening changed — the
unheard line where the played line no longer runs within `tol` mm of it
(a gap cut, a stop, a lean, a detour) — are drawn in a second ink, so the
panel reads as the drawing's negative of awareness: everything the
relations took away or moved, in place. The header gives the share.

A v1 sheet has no score to replay; the panel says so.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from . import devices_mdoc_read as D
from . import devices_meas_read as R
from ._devices import device
from .core import P


def _dense(p, step):
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    if s[-1] <= step:
        return p
    t = np.linspace(0, s[-1], int(s[-1] / step) + 1)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def changed(sheet, *, drop_kinds: set | None = None, tol: float = 0.15):
    """(unheard sheet, [(layer id, polyline, changed mask)], changed mm, total mm) or None."""
    w = D.written(sheet)
    if w is None:
        return None
    rels = w.get("relations", [])
    keep = [] if not drop_kinds else [r["kind"] for r in rels if r["kind"] not in drop_kinds]
    un = D.replay(sheet, keep_only_kinds=set(keep))
    Lp, Lu = D.layers(sheet), D.layers(un)
    out, ch_mm, tot = [], 0.0, 0.0
    for lid, v in Lu.items():
        if not v["visible"]:
            continue
        played = [_dense(np.asarray(m.points, float), 0.08) for m in Lp.get(lid, {}).get("marks", [])]
        tree = cKDTree(np.vstack(played)) if played else None
        for m in v["marks"]:
            p = _dense(np.asarray(m.points, float), 0.25)
            d = tree.query(p)[0] if tree is not None else np.full(len(p), np.inf)
            mask = d > tol
            seg = np.r_[np.linalg.norm(np.diff(p, axis=0), axis=1), 0.0]
            ch_mm += float(seg[mask].sum())
            tot += float(seg.sum())
            out.append((lid, p, mask))
    return un, out, ch_mm, tot


def _runs(mask):
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            yield max(i - 1, 0), min(j + 1, n)
            i = j
        else:
            i += 1


@device("mdoc_unheard", family="process", params=[
    P("drop", "str", "", "only take out relations of these kinds, comma-separated (empty = all)"),
    P("tol", "float", 0.15, "a played line within this of the unheard one counts as unchanged, mm", min=0.02, max=2.0),
    P("ring", "float", 1.2, "ring around each changed stretch in the panel, mm (0 = none)", min=0.0, max=5.0),
    P("label_h", "float", 1.4, "lettering cap height, mm", min=0.6, max=6.0),
    P("pen", "float", 0.15, "pen, mm", min=0.05, max=1.0),
    P("ink", "str", "black", "ink for the unheard drawing"),
    P("changed_ink", "str", "auto", "ink for what listening changed: Flexoki name, 'auto' or 'source' (the layer's ink)"),
], doc="the drawing replayed with no relations, small beside the real one; in a second ink, every stretch the "
       "listening cut, stopped, bent or moved")
def mdoc_unheard(dctx, sheet, *, drop, tol, ring, label_h, pen, ink, changed_ink):
    x0, y0, w, h = dctx.region
    pad = min(3.0 + 0.04 * min(w, h), 8.0)
    x0, y0, w, h = x0 + pad, y0 + pad, w - 2 * pad, h - 2 * pad
    kinds = {k.strip() for k in drop.split(",") if k.strip()} or None
    got = changed(sheet, drop_kinds=kinds, tol=tol)
    head = R.text("UNHEARD", x0, y0, label_h)
    if got is None:
        return R.inks(head + R.text("NO SCORE TO REPLAY ON THIS SHEET", x0, y0 + 2 * label_h, 0.7 * label_h),
                      pen=pen, colour=ink, role="unheard")
    un, lines, ch_mm, tot = got
    cink = D.free_ink(sheet, changed_ink) if changed_ink != "source" else changed_ink
    what = "WITH NO RELATIONS" if not kinds else "WITHOUT " + " ".join(sorted(kinds)).upper()
    head += R.text(f"THE SCORE REPLAYED {what}", x0, y0 + 1.7 * label_h, 0.7 * label_h)
    head += R.text(f"LISTENING CHANGED {ch_mm:.0f} OF {tot:.0f} MM ({100 * ch_mm / max(tot, 1e-9):.1f}%)",
                   x0, y0 + 2.9 * label_h, 0.7 * label_h)
    box = (x0, y0 + 4.6 * label_h, w, h - 4.6 * label_h)
    W, H = un.frame
    k = min(box[2] / W, box[3] / H)
    off = np.array([box[0] + (box[2] - W * k) / 2, box[1]])
    plain, hot = [], []
    L = D.layers(sheet)
    for lid, p, mask in lines:
        q = p * k + off
        plain.append(q)
        col = (L[lid]["colour"] if lid in L else "black") if cink == "source" else cink
        for a, b in _runs(mask):
            if b - a >= 2:
                hot.append((q[a:b], col))
                c = q[a:b].mean(axis=0)                     # a ring so a short change can be found
                if ring > 0:
                    hot.append((R.circle(c, ring, 12), col))
    out = R.inks(head, pen=pen, colour="black", role="unheard")
    out += R.inks(plain, pen=pen, colour=ink, role="unheard-line")
    for q, c in hot:
        out += R.inks([q], pen=max(pen, 0.3), colour=c, role="unheard-changed")
    return out
