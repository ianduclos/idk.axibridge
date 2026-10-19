# FROZEN from research commit ecd64f8: tools/gesture/gesture/kit/prosody_arrangers.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Prosody thread (round 9) — the limb: call and response between voices.

`call_response` places its parts (one shared surface, or one row each), lets
every part run its own chain, then re-decides the stresses of every part but
the leader so they fall where the LEADER IS SILENT — a line that answers
another line. Each part must end its modulator chain with `prosody` (its
events, rhythm settings and stress shape are re-used from meta["prosody"]).

- listen_by = "time":  both lines are heard along their own course (share u of
  arc length, as if drawn at once by two hands); a follower stress needs the
  leader quiet around the same u, and events just after a leader's call get
  the `answer` bonus (the reply).
- listen_by = "space": the follower hears whatever of the leader passes within
  `radius` mm on the sheet; it stays wire where the leader is heard nearby and
  prefers events where the leader passes close but quiet (it speaks into the
  other's silence).
A follower stress is allowed only if the leader stays below emphasis 0.15
over the WHOLE stretch it would ink (quiet stresses count as speech too).
Roundtable: with 3+ parts, part k answers part k−1 (a chain of replies), the
leader answering no one.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.spatial import cKDTree

from .core import KitError, P, arranger
from .prosody_modulators import _greedy, apply_stress, with_ends

SILENT = 0.15      # the other voice counts as silent below this emphasis


def _need(m):
    pm = m.meta.get("prosody")
    if pm is None:
        raise KitError("call_response: every part must end its modulators with 'prosody'")
    return pm


def _u(m):
    s = m.arclength()
    return s / max(s[-1], 1e-9)


def answer_mark(m, lead_marks, *, listen_by: str, radius: float, answer: float, delay: float, window: float):
    pm = _need(m)
    prm = pm["params"]
    L = float(pm["length"])
    evs = [(float(a), float(b), tuple(c.split("+"))) for a, b, c in pm["events"]]
    if not evs:
        return m, {"kept": 0}
    s = m.arclength()
    cands = []

    def extent(sk):
        """The arc-length range the stress would ink (lead applied)."""
        if prm["unit"] == "pulse":
            return sk + prm["lead"] - prm["span"], sk + prm["lead"] + prm["span"]
        e = with_ends([(sk, 1.0)], evs, L, unit="segment", span=prm["span"])[0][2]
        return sk + prm["lead"] - 2.0, e + prm["lead"] + 2.0

    if listen_by == "time":
        uu = np.linspace(0, 1, 2001)
        loud = np.zeros_like(uu)
        for lm in lead_marks:
            loud = np.maximum(loud, np.interp(uu, _u(lm), lm["emphasis"]))
        k = max(int(window * 2000), 0)
        kd = max(int(delay * 2000), 1)
        for sk, sal, kinds in evs:
            a, b = extent(sk)
            j0 = int(np.clip(round(a / max(L, 1e-9) * 2000), 0, 2000))
            j1 = int(np.clip(round(b / max(L, 1e-9) * 2000), 0, 2000))
            ld = float(loud[max(0, j0 - k):min(2001, j1 + k + 1)].max())
            if ld > SILENT:
                continue
            call = bool((loud[max(0, j0 - kd):j0] >= 0.99).any()) if j0 else False
            cands.append((sal * (1 - ld) * (1 + answer * call), sk))
    else:
        P_ = np.vstack([lm.points for lm in lead_marks])
        E_ = np.concatenate([lm["emphasis"] for lm in lead_marks])
        tree = cKDTree(P_)
        for sk, sal, kinds in evs:
            a, b = extent(sk)
            ss = np.linspace(max(a, 0.0), min(b, s[-1]), 12)
            pts = np.column_stack([np.interp(ss, s, m.points[:, 0]), np.interp(ss, s, m.points[:, 1])])
            idx = sorted({i for row in tree.query_ball_point(pts, radius) for i in row})
            ld = float(E_[idx].max()) if idx else 0.0
            if ld > SILENT:
                continue
            cands.append((sal * (1 - ld) * (1 + answer * float(bool(idx))), sk))
    cap = max(1, int(math.ceil(prm["density"] * L / 100.0)))
    acc = _greedy(cands, prm["gap"], cap)
    nl = max(1, int(round(prm["primary"] * len(acc)))) if acc else 0
    st = sorted((a[1], 1.0 if i < nl else prm["quiet"]) for i, a in enumerate(acc))
    st = with_ends(st, evs, L, unit=prm["unit"], span=prm["span"])
    base = m.evolve(channels={})
    out = apply_stress(base, st, prm)
    info = {"by": listen_by, "stresses_before": len(pm["stresses"]), "stresses_after": len(st),
            "candidates": len(cands)}
    return out.evolve(meta={"prosody": {**pm, "stresses": [[round(v, 3) for v in x] for x in st],
                                        "answer": info}}), info


@arranger("call_response", params=[
    P("listen_by", "choice", "time", "time: answer along the course (share of arc length) | space: answer "
      "what passes near on the sheet", choices=("time", "space")),
    P("radius", "float", 15.0, "space: how near the other voice is heard, mm", min=0.5, max=200.0),
    P("answer", "float", 0.8, "bonus for an event right after a call (time) / beside a quiet passage (space)",
      min=0.0, max=5.0),
    P("delay", "float", 0.05, "time: how long after a call the reply may come, share of the line",
      min=0.0, max=0.5),
    P("window", "float", 0.012, "time: how far either side of u the leader must be quiet, share of the line",
      min=0.0, max=0.2),
    P("layout", "choice", "single", "single: one shared surface | rows: one band per part", choices=("single", "rows")),
], doc="call and response: every part after the first re-decides its stresses to fall where the part "
       "before it is silent")
def call_response(ctx, parts, *, listen_by, radius, answer, delay, window, layout):
    x0, y0, W, H = ctx.box
    n = len(parts)
    placed = []
    for i, p in enumerate(parts):
        box = ctx.box if layout == "single" else (x0, y0 + i * H / n, W, H / n)
        placed.append(p.run(box))
    out = list(placed[0])
    for i in range(1, n):
        lead = placed[i - 1]
        for m in lead:
            _need(m)
        new = []
        for m in placed[i]:
            q, _ = answer_mark(m, lead, listen_by=listen_by, radius=radius, answer=answer, delay=delay,
                               window=window)
            new.append(q)
        placed[i] = new
        out += new
    return out
