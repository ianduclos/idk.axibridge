# FROZEN from research commit 071aea1: tools/gesture/gesture/kit/relations_mdoc.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 16 thread D (`mdoc`): a TEST relation, so the process documents can
be built and checked against every crossing outcome before thread A's
`crossing` and `sympathy` relations land. It is a test bench, not a
technique: the geometry it makes is plain on purpose.

`mdoc_outcomes` (contact): at each crossing between src and dst it draws one
outcome from `weights` (with `streak`: the chance the previous outcome simply
repeats) and acts it out, logging the shared outcome names of
`_relations.py`:
- gap_under: the dst breaks around the src (passes under);
- gap_over:  the src breaks around the dst;
- cross:     both run through;
- stop:      the dst ends at the src and resumes `stop_mm` later (one side
             only, so it reads as arriving and stopping);
- sympathy:  the dst, over `reach` mm either side of the crossing, leans
             toward the src's course (a Hann window × `gain` × the local
             distance, capped at 2 mm). Events carry `s` (the stretch on the
             dst mark), `mark`, and `max_mm`, the largest displacement.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from ._relations import RelOut, crossings, gap_marks, pick, relation
from .core import P

OUTCOMES = ("gap_under", "gap_over", "cross", "stop", "sympathy")


def _nearest_on(points: np.ndarray, polys: list[np.ndarray], step: float = 0.05) -> np.ndarray:
    """For each point, the nearest point on any of the polylines (sampled
    every `step` mm, searched with a k-d tree)."""
    dense = []
    for q in polys:
        q = np.asarray(q, float)
        if len(q) < 2:
            continue
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
        t = np.linspace(0, s[-1], max(int(s[-1] / step), 1) + 1)
        dense.append(np.column_stack([np.interp(t, s, q[:, 0]), np.interp(t, s, q[:, 1])]))
    if not dense:
        return points.copy()
    allq = np.vstack(dense)
    return allq[cKDTree(allq).query(points)[1]]


@relation("mdoc_outcomes", phase="contact", params=[
    P("w_under", "float", 0.3, "weight: the dst passes under", min=0.0, max=1.0),
    P("w_over", "float", 0.2, "weight: the src breaks (dst over)", min=0.0, max=1.0),
    P("w_cross", "float", 0.2, "weight: both run through", min=0.0, max=1.0),
    P("w_stop", "float", 0.1, "weight: the dst stops at the src", min=0.0, max=1.0),
    P("w_sympathy", "float", 0.2, "weight: the dst leans with the src", min=0.0, max=1.0),
    P("streak", "float", 0.4, "chance the previous outcome repeats", min=0.0, max=0.95),
    P("gap", "float", 1.2, "gap either side beyond the pen's half width, mm", min=0.0, max=6.0),
    P("pen", "float", 0.35, "the other line's pen width, mm", min=0.05, max=3.0),
    P("stop_mm", "float", 5.0, "stop: how long the dst stays away after arriving, mm", min=1.0, max=30.0),
    P("reach", "float", 9.0, "sympathy: half-length of the stretch that leans, mm", min=2.0, max=40.0),
    P("gain", "float", 0.35, "sympathy: share of the local distance taken up", min=0.0, max=1.0),
    P("min_sep", "float", 3.0, "crossings closer than this along a line count once, mm", min=0.0, max=20.0),
], doc="TEST relation (thread D): every crossing outcome, drawn per crossing, so documents can read them")
def mdoc_outcomes(rctx, src, dst, *, w_under, w_over, w_cross, w_stop, w_sympathy, streak, gap, pen, stop_mm,
                  reach, gain, min_sep):
    xs = crossings(src, dst, min_sep=min_sep)
    if not xs:
        return RelOut()
    weights = {"gap_under": w_under, "gap_over": w_over, "cross": w_cross, "stop": w_stop, "sympathy": w_sympathy}
    rng = rctx.rng("outcomes")
    half = pen / 2 + gap
    cut_dst: dict[int, list] = {}
    cut_src: dict[int, list] = {}
    lean: dict[int, list] = {}
    events = []
    prev = None
    for c in xs:
        o = prev if prev is not None and rng.random() < streak else pick(rng, weights)
        prev = o
        ev = {"outcome": o, "at": c.at, "mark": c.i_dst, "s_src": [c.s_src, c.s_src]}
        if o == "gap_under":
            cut_dst.setdefault(c.i_dst, []).append((c.s_dst - half, c.s_dst + half))
            ev["s"] = [c.s_dst - half, c.s_dst + half]
        elif o == "gap_over":
            cut_src.setdefault(c.i_src, []).append((c.s_src - half, c.s_src + half))
            ev["s"] = [c.s_dst, c.s_dst]
            ev["s_src"] = [c.s_src - half, c.s_src + half]
        elif o == "stop":
            cut_dst.setdefault(c.i_dst, []).append((c.s_dst + pen / 2, c.s_dst + pen / 2 + stop_mm))
            ev["s"] = [c.s_dst, c.s_dst + pen / 2 + stop_mm]
        elif o == "sympathy":
            lean.setdefault(c.i_dst, []).append(c.s_dst)
            ev["s"] = [c.s_dst - reach, c.s_dst + reach]
        else:
            ev["s"] = [c.s_dst, c.s_dst]
        events.append(ev)

    src_polys = [np.asarray(m.points, float) for m in src]
    new_dst = list(dst)
    for i, centres in lean.items():
        m = dst[i].resampled(0.4)
        s = m.arclength()
        p = np.asarray(m.points, float)
        w = np.zeros(len(p))
        for sc in centres:
            u = np.clip((s - sc) / reach, -1, 1)
            w = np.maximum(w, 0.5 * (1 + np.cos(np.pi * u)) * (np.abs(s - sc) < reach))
        tgt = _nearest_on(p, src_polys)
        d = tgt - p
        dn = np.linalg.norm(d, axis=1, keepdims=True)
        d = d * np.minimum(1.0, 2.0 / np.maximum(dn * gain, 1e-9))
        q = p + gain * w[:, None] * d
        new_dst[i] = m.remap(s, points=q)
        for ev in events:
            if ev["outcome"] == "sympathy" and ev["mark"] == i:
                a, b = ev["s"]
                sel = (s >= a) & (s <= b)
                ev["max_mm"] = round(float(np.max(np.linalg.norm(q[sel] - p[sel], axis=1))) if sel.any() else 0.0, 3)
    new_dst = gap_marks(new_dst, cut_dst)
    new_src = gap_marks(list(src), cut_src) if cut_src else None
    return RelOut(dst=new_dst, src=new_src, events=events)
