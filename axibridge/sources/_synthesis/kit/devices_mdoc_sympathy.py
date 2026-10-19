# FROZEN from research commit 071aea1: tools/gesture/gesture/kit/devices_mdoc_sympathy.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Device `mdoc_sympathy` (round 16, thread D `mdoc`): the displacement a
line took from another, drawn beside it.

Sympathy leaves no break, so the drawing alone can't show it. This device
reads the played log for the events whose outcome is "sympathy", then
replays the score through the public executor with that relation taken out:
the dst layer as it would have been. The displacement at every point of the
played line is its distance to that unheard line; a stretch where it is
non-zero, near a logged sympathy, is what the line took from the other.
(Gaps the replay lacks are bridged first, so a break is never read as a
lean.) Readings:
- over/under: a hairline that hugs the line along each stretch, `hug` mm
  off it, swelling away from it by the displacement × `gain` — a trace
  running beside the line, flat where it didn't move; optionally the
  unheard course as dashes;
- beside/margin: one specimen per stretch, largest first: the stretch as
  played (its own ink) over the unheard course (dashes), turned to its
  chord, and under it the displacement against arc length, its largest
  value in mm, and who heard whom.
On a sheet with no log, or no sympathy in it, it says so, small.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree

from . import devices_mdoc_read as D
from . import devices_meas_read as R
from ._devices import device
from .core import P


def _near(points: np.ndarray, polys: list[np.ndarray], step: float = 0.04):
    """(distance, nearest point) from each point to the polylines: the
    lines sampled every `step` mm and searched with a k-d tree (error
    <= step / 2)."""
    dense = [_resample(np.asarray(q, float), step) for q in polys if len(q) >= 2]
    if not dense:
        return np.full(len(points), np.inf), points.copy()
    allq = np.vstack(dense)
    d, j = cKDTree(allq).query(points)
    return d, allq[j]


def _bridged(marks, max_gap: float = 8.0) -> list[np.ndarray]:
    """The layer's lines with short breaks between consecutive pieces closed
    (a replay may lack a gap the played sheet has, or have one it lacks)."""
    out: list[np.ndarray] = []
    for m in marks:
        p = np.asarray(m.points, float)
        if out and float(np.linalg.norm(out[-1][-1] - p[0])) <= max_gap:
            out[-1] = np.vstack([out[-1], p])
        else:
            out.append(p)
    return out


def _resample(p: np.ndarray, step: float) -> np.ndarray:
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    if s[-1] <= step:
        return p
    t = np.linspace(0, s[-1], int(s[-1] / step) + 1)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def stretches(sheet, *, eps: float = 0.03, pad: float = 3.0):
    """Every stretch where a played line stands off its unheard course near a
    logged sympathy. Returns (list, why): each item {relation, src, dst,
    points (played, with `pad` mm of context), ghost (unheard, same span),
    d (displacement per point), core (bool per point: inside the stretch),
    max, at}. `why` says what was missing when the list is empty."""
    pl = D.played(sheet)
    if not pl:
        return [], "NO PLAYED LOG - SYMPATHY IS KNOWN ONLY FROM A SCORE"
    evs = [e for e in pl["log"] if e.get("outcome") == "sympathy" and e.get("at")]
    if not evs:
        return [], "NO SYMPATHY IN THIS SCORE"
    out = []
    played_L = D.layers(sheet)
    for rid in sorted({e["relation"] for e in evs}):
        mine = [e for e in evs if e["relation"] == rid]
        cf = D.replay(sheet, drop={rid})
        if cf is None:
            continue
        cf_L = D.layers(cf)
        for dst in sorted({e["dst"] for e in mine}):
            if dst not in played_L or dst not in cf_L:
                continue
            ghost_polys = _bridged(cf_L[dst]["marks"])
            ats = np.array([e["at"] for e in mine if e["dst"] == dst], float)
            reach = max([abs(e["s"][1] - e["s"][0]) / 2 for e in mine if e["dst"] == dst and e.get("s")] + [3.0])
            for m in played_L[dst]["marks"]:
                p = _resample(np.asarray(m.points, float), 0.3)
                if len(p) < 3:
                    continue
                d, nearp = _near(p, ghost_polys)
                on = d > eps
                hole = int(2.0 / 0.3)                       # one stretch: holes under 2 mm closed
                i = 0
                while i < len(on):
                    if not on[i]:
                        j = i
                        while j < len(on) and not on[j]:
                            j += 1
                        if 0 < i and j < len(on) and j - i < hole:
                            on[i:j] = True
                        i = j
                    else:
                        i += 1
                i = 0
                while i < len(p):
                    if not on[i]:
                        i += 1
                        continue
                    j = i
                    while j < len(p) and on[j]:
                        j += 1
                    seg = p[i:j]
                    dist_at = np.min(np.linalg.norm(seg[:, None, :] - ats[None], axis=2)) if len(seg) else 1e9
                    if j - i >= 3 and dist_at <= reach + 2.0 and d[i:j].max() >= 2 * eps:
                        k = int(np.argmin(np.linalg.norm(ats - seg[np.argmax(d[i:j])], axis=1)))
                        e = [x for x in mine if x["dst"] == dst][k]
                        n_pad = int(pad / 0.3)
                        a, b = max(i - n_pad, 0), min(j + n_pad, len(p))
                        core = np.zeros(b - a, bool)
                        core[i - a:j - a] = True
                        out.append({"relation": rid, "kind": e.get("kind"), "src": e["src"], "dst": dst,
                                    "points": p[a:b], "ghost": nearp[a:b], "d": d[a:b], "core": core,
                                    "max": float(d[i:j].max()), "at": np.asarray(e["at"], float)})
                    i = j
    if not out:
        return [], "SYMPATHY LOGGED BUT NO LINE MOVED"
    return out, ""


@device("mdoc_sympathy", family="process", params=[
    P("style", "choice", "auto", "auto (trace over/under, specimens beside/margin) | trace | specimens",
      choices=("auto", "trace", "specimens")),
    P("hug", "float", 1.3, "trace: how far off the line the trace runs where nothing moved, mm", min=0.3, max=6.0),
    P("gain", "float", 3.0, "trace: displacement magnified by", min=0.5, max=20.0),
    P("ghost", "bool", False, "trace: also draw the unheard course as dashes"),
    P("max_items", "int", 8, "specimens: most stretches shown (largest first)", min=1, max=30),
    P("label_h", "float", 1.4, "lettering cap height, mm", min=0.6, max=6.0),
    P("pen", "float", 0.15, "pen, mm", min=0.05, max=1.0),
    P("ink", "str", "auto", "trace ink: Flexoki name, 'auto' (an accent the drawing lacks) or 'source' (the dst's ink)"),
], doc="the displacement a line took from another (sympathy), read against a replay of the score without that "
       "relation: a trace hugging the line, or specimens beside it")
def mdoc_sympathy(dctx, sheet, *, style, hug, gain, ghost, max_items, label_h, pen, ink):
    items, why = stretches(sheet)
    if style == "auto":
        style = "trace" if dctx.place in ("over", "under") else "specimens"
    L = D.layers(sheet)
    ink = D.free_ink(sheet, ink) if ink != "source" else ink
    if not items:
        if style == "trace":
            return R.inks(D.free_corner(sheet, dctx.region, why, h=0.8 * label_h), pen=pen,
                          colour="black" if ink == "source" else ink, role="sympathy-note")
        x0, y0, w, h = dctx.region
        return R.inks(R.text("SYMPATHY", x0 + 5, y0 + 5, label_h) + R.text(why, x0 + 5, y0 + 5 + 2 * label_h,
                                                                             0.7 * label_h),
                      pen=pen, colour="black", role="sympathy-note")
    if style == "trace":
        return _trace(sheet, dctx, items, L, hug=hug, gain=gain, ghost=ghost, pen=pen, ink=ink, label_h=label_h)
    return _specimens(dctx, items, L, max_items=max_items, label_h=label_h, pen=pen)


def _normals(p):
    t = np.gradient(p, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    return np.column_stack([-t[:, 1], t[:, 0]])


def _trace(sheet, dctx, items, L, *, hug, gain, ghost, pen, ink, label_h):
    out = []
    for it in items:
        p, d, core = it["points"], it["d"], it["core"]
        q = p[core]
        dd = gaussian_filter1d(d[core], 5.0, mode="nearest")
        n = _normals(q)
        # the trace runs on the side away from the way the line moved
        mv = it["ghost"][core] - q
        side = -1.0 if float(np.sum((mv * n).sum(1))) > 0 else 1.0
        tr = q + side * n * (hug + gain * dd)[:, None]
        ends = [np.array([q[0] + side * n[0] * 0.4 * hug, tr[0]]), np.array([q[-1] + side * n[-1] * 0.4 * hug, tr[-1]])]
        col = L[it["dst"]]["colour"] if ink == "source" and it["dst"] in L else ink
        polys = [tr] + ends
        if ghost:
            polys += D.dashed_poly(it["ghost"][core], dash=0.5, gap=0.5)
        out += R.inks(polys, pen=pen, colour=col, role="sympathy", meta={"relation": it["relation"]})
    msg = f"SYMPATHY: {len(items)} STRETCHES / MOST {max(i['max'] for i in items):.2f} MM / TRACE X{gain:g}"
    out += R.inks(D.free_corner(sheet, dctx.region, msg, h=0.8 * label_h), pen=pen,
                  colour="black" if ink == "source" else ink, role="sympathy-note")
    return out


def _specimens(dctx, items, L, *, max_items, label_h, pen):
    x0, y0, w, h = dctx.region
    pad = min(3.0 + 0.04 * min(w, h), 8.0)
    x0, y0, w, h = x0 + pad, y0 + pad, w - 2 * pad, h - 2 * pad
    items = sorted(items, key=lambda it: -it["max"])
    shown = items[:max_items]
    head = R.text("SYMPATHY", x0, y0, label_h)
    head += R.text(f"{len(items)} STRETCHES MOVED / AGAINST A REPLAY WITHOUT THE RELATION", x0, y0 + 1.6 * label_h,
                   0.7 * label_h)
    top = y0 + 3.6 * label_h
    rows = len(shown)
    rh = (h - (top - y0)) / max(rows, 1)
    dmax = max(it["max"] for it in shown)
    out = []
    blk = []
    for k, it in enumerate(shown):
        yr = top + k * rh
        col = L[it["dst"]]["colour"] if it["dst"] in L else "black"
        blk += R.text(f"{D.layer_tag(L, it['dst'])} HEARS {D.layer_tag(L, it['src'])}", x0, yr, 0.75 * label_h)
        blk += R.text(f"{it['max']:.2f} MM", x0 + w, yr, 0.75 * label_h, anchor="right")
        # the stretch, turned to its chord, both courses in one frame
        p, g = it["points"], it["ghost"]
        a = p[0]
        v = p[-1] - p[0]
        ang = math.atan2(v[1], v[0]) if np.hypot(*v) > 1e-9 else 0.0
        c, s = math.cos(-ang), math.sin(-ang)
        rot = np.array([[c, -s], [s, c]])
        P_, G_ = (p - a) @ rot.T, (g - a) @ rot.T
        box = (x0, yr + 1.4 * label_h, 0.58 * w, rh - 2.4 * label_h)
        k_, off = R.fit_into([P_, G_], box, pad=0.5)
        out += R.inks([P_ * k_ + off], pen=max(pen, 0.2), colour=col, role="sympathy-played")
        blk += D.dashed_poly(G_ * k_ + off, dash=0.5, gap=0.45)
        # the displacement against arc length
        sx = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
        gx0, gw = x0 + 0.64 * w, 0.36 * w
        gy1 = yr + rh - 1.2 * label_h
        gh = rh - 3.0 * label_h
        X = gx0 + sx / max(sx[-1], 1e-9) * gw
        Y = gy1 - it["d"] / max(dmax, 1e-9) * gh
        blk.append(R.rule(gx0, gy1, gx0 + gw, gy1))
        out += R.inks([np.column_stack([X, Y])], pen=pen, colour=col, role="sympathy-d")
    if len(items) > len(shown):
        blk += R.text(f"+{len(items) - len(shown)} SMALLER", x0, y0 + h - label_h, 0.7 * label_h)
    out += R.inks(blk + head, pen=pen, colour="black", role="sympathy")
    return out
