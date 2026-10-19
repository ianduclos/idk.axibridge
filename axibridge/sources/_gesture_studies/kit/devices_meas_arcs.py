# FROZEN from research commit 9ab70ac: tools/gesture/gesture/kit/devices_meas_arcs.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Device `meas_arcs` (round 15, thread D `meas`): which relations fired.
It reads the score (`notes["score"]`) the composer wrote, or, for a
round-14 sheet, the score derived from its arranger's own log
(`devices_meas_read.process_score`). Two readings:
- in a margin or beside: an arc diagram. The layers stand along a line in
  the order they were laid, each named; every relation is an arc from the
  layer that acted to the layer it acted on, with its kind (cross, echo,
  mask, carry, spill, cover, …) at the arc's crown;
- over or under the drawing: each relation where it happened — a ring at
  its `at`, its kind beside it, and, when it names an arc-length range `s`
  on the layer it acted on, a hairline that runs alongside that stretch of
  the line, so you can see exactly which part was crossed, masked, ridden."""
from __future__ import annotations

import math

import numpy as np

from . import devices_meas_read as R
from ._devices import device
from .core import P


def _layer_name(lay: dict) -> str:
    hands = (lay.get("params") or {}).get("hands")
    if lay.get("label"):
        return str(lay["label"])[:8].upper()
    if hands:
        return R.short(hands[0], 7)
    for k in ("hand", "trail", "stems"):
        v = (lay.get("params") or {}).get(k)
        if v:
            return R.short(v, 7)
    return str(lay.get("technique") or lay.get("role") or lay["id"])[:8].upper()


def _arc(a: float, b: float, base: float, height: float, *, vertical: bool, n: int = 40):
    t = np.linspace(0, math.pi, n)
    mid, r = (a + b) / 2, (b - a) / 2
    u = mid - r * np.cos(t)
    v = base - height * np.sin(t)
    return np.column_stack([v, u]) if vertical else np.column_stack([u, v])


def _offset_stretch(marks, s0: float, s1: float, off: float):
    """The stretch [s0, s1] of the marks laid end to end, offset to one side by off mm."""
    out, acc = [], 0.0
    for m in marks:
        p = np.asarray(m.points, float)
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))] + acc
        acc = s[-1]
        sel = (s >= s0) & (s <= s1)
        if sel.sum() >= 2:
            q = p[sel]
            tg = np.gradient(q, axis=0)
            tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
            out.append(q + np.column_stack([-tg[:, 1], tg[:, 0]]) * off)
    return out


@device("meas_arcs", family="process", params=[
    P("style", "choice", "auto", "auto (arcs in a margin/beside, places on the drawing over/under) | arcs | places",
      choices=("auto", "arcs", "places")),
    P("kinds", "str", "", "only these relation kinds, comma-separated (empty = all)"),
    P("crown", "float", 0.9, "arcs: tallest arc as a share of the region", min=0.2, max=1.0),
    P("ring", "float", 1.1, "places: ring radius, mm", min=0.2, max=6.0),
    P("hug", "float", 1.4, "places: how far the hairline runs beside the stretch it names, mm", min=0.3, max=8.0),
    P("label_h", "float", 1.5, "label cap height, mm", min=0.6, max=6.0),
    P("pen", "float", 0.15, "pen, mm", min=0.05, max=1.5),
    P("ink", "str", "black", "Flexoki ink name, or 'source' (each relation in its dst layer's ink)"),
], doc="which relations fired between the layers (the score, or the arranger's own log): an arc diagram beside, "
       "or each relation where it happened")
def meas_arcs(dctx, sheet, *, style, kinds, crown, ring, hug, label_h, pen, ink):
    sc = R.process_score(sheet)
    if not sc or not sc.get("layers"):
        return []
    rels = [r for r in sc.get("relations", []) if r.get("src") and r.get("dst")]
    if kinds:
        keep = {k.strip() for k in kinds.split(",") if k.strip()}
        rels = [r for r in rels if r["kind"] in keep]
    if style == "auto":
        style = "places" if dctx.place in ("over", "under") else "arcs"
    lm = R.layer_marks(sheet, sc)
    colours = {}
    us = {id(m): u for u in R.units(sheet, "line") for m in u.marks}
    for lid, ms in lm.items():
        cs = [us[id(m)].colour for m in ms if id(m) in us]
        colours[lid] = max(set(cs), key=cs.count) if cs else "black"
    col = (lambda lid: colours.get(lid, "black")) if ink == "source" else (lambda lid: ink)
    if style == "places":
        return _places(dctx, sheet, rels, lm, col, ring=ring, hug=hug, label_h=label_h, pen=pen)
    return _arcs(dctx, sc, rels, col, crown=crown, label_h=label_h, pen=pen)


def _places(dctx, sheet, rels, lm, col, *, ring, hug, label_h, pen):
    allp = np.vstack([np.asarray(m.points, float) for m in R.drawing_marks(sheet)])
    out = []
    for r in rels:
        polys = []
        if r.get("s") and lm.get(r["dst"]):
            polys += _offset_stretch(lm[r["dst"]], r["s"][0], r["s"][1], hug)
        if r.get("at"):
            c = np.asarray(r["at"], float)
            polys.append(R.circle(c, ring))
            polys += R.side_label(c, np.array([0.0, -1.0]), r["kind"].upper(), label_h, allp, gap=ring + 0.6)
        out += R.inks(polys, pen=pen, colour=col(r["dst"]), role="relation", meta={"kind": r["kind"]})
    return out


def _arcs(dctx, sc, rels, col, *, crown, label_h, pen):
    x0, y0, w, h = dctx.region
    vertical = h > 1.3 * w
    pad = min(3.0 + 0.04 * min(w, h), 8.0)
    layers = sc["layers"]
    ids = [lay["id"] for lay in layers]
    n = len(ids)
    names = [f"{i + 1} {_layer_name(lay)}" for i, lay in enumerate(layers)]
    lab_room = max(R.text_w(t, label_h) for t in names) + 2.0 if vertical else 2.6 * label_h
    span = (h if vertical else w) - 2 * pad
    pos = {lid: (pad + (i + 0.5) * span / n) for i, lid in enumerate(ids)}
    if vertical:
        base = x0 + pad + lab_room
        room = w - 2 * pad - lab_room - label_h
    else:
        base = y0 + h - pad - lab_room
        room = h - 2 * pad - lab_room - 1.6 * label_h
    out = []
    polys = []
    for i, lid in enumerate(ids):
        p = (y0 if vertical else x0) + pos[lid]
        if vertical:
            polys.append(R.rule(base - 0.8, p, base, p))
            polys += R.text(names[i], base - 1.5, p - label_h / 2, label_h, anchor="right")
        else:
            polys.append(R.rule(p, base, p, base + 0.8))
            polys += R.text(names[i], p, base + 1.3, 0.85 * label_h, anchor="centre")
    out += R.inks(polys, pen=pen, colour="black" if col("") == "black" else col(""), role="layer")
    dmax = max((abs(pos[r["src"]] - pos[r["dst"]]) for r in rels if r["src"] in pos and r["dst"] in pos), default=1.0)
    seen: dict[tuple, int] = {}
    for r in rels:
        if r["src"] not in pos or r["dst"] not in pos:
            continue
        a, b = sorted((pos[r["src"]], pos[r["dst"]]))
        o = (y0 if vertical else x0)
        k = (r["src"], r["dst"], r["kind"])
        rep = seen.get((min(a, b), max(a, b)), 0)
        seen[(min(a, b), max(a, b))] = rep + 1
        if b - a < 1e-6:                                        # a layer acting on itself: a small loop
            hgt = 0.12 * room
            a, b = a - 0.25 * span / n, a + 0.25 * span / n
        else:
            hgt = crown * room * math.sqrt((b - a) / dmax)
        hgt *= 1.0 - 0.12 * rep
        sign = 1.0 if not vertical else -1.0
        arc = _arc(o + a, o + b, base, hgt * sign, vertical=vertical)
        polys = [arc]
        dst = o + pos[r["dst"]]
        foot = np.array([base, dst]) if vertical else np.array([dst, base])
        # the arc lands on the layer it acted on: a short bar across the foot
        polys.append(np.array([foot + ([0.0, -0.9] if vertical else [-0.9, 0.0]),
                               foot + ([0.0, 0.9] if vertical else [0.9, 0.0])]) +
                     (np.array([1.2, 0.0]) if vertical else np.array([0.0, -1.2])))
        top = arc[len(arc) // 2]
        if vertical:
            polys += R.text(r["kind"].upper(), top[0] + 1.0, top[1] - 0.4 * label_h, 0.8 * label_h)
        else:
            polys += R.text(r["kind"].upper(), top[0], top[1] - 1.2 * label_h, 0.8 * label_h, anchor="centre")
        out += R.inks(polys, pen=pen, colour=col(r["dst"]), role="relation", meta={"kind": r["kind"], "key": list(k)})
    return out
