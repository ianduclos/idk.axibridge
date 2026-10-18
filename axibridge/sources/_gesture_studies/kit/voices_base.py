# FROZEN from research commit efce219: tools/gesture/gesture/kit/voices_base.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Seed voices: `hand` (one grammar speaks the whole line) and `drift` (a
line whose hand drifts along a route of grammars) — the research
`hybrid.drift_line` (round 8), exactly as the Hand Drift bench runs it.

Lines grow in the research frame (1000×1200 px) and are fitted into
ctx.box (uniform scale, centred; meta["fit"] records it so the grid
arranger can put several lines at one common scale, as the bench does).
Seeding: `np.random.default_rng(ctx.seed)` — the part seed, bench-compatible
(a recipe with seed s reproduces the bench at seed s; part i ↔ bench line i).

Channels added: `voice` (index into meta["voices"] of the hand that drew the
token at each point, from the drift's hand log).
"""
from __future__ import annotations

import numpy as np

from ._research import hybrid as hy
from .core import P, fitted, voice

RESEARCH_SIZE = (1000.0, 1200.0)


def _voice_channel(points: np.ndarray, hand_log: list, R: float) -> np.ndarray:
    """Per point: the hand index of the last logged token drawn at or before
    that point's arc length (hand log s is in R units)."""
    seg = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))] / max(R, 1e-9)
    if not hand_log:
        return np.zeros(len(points))
    s = np.array([float(e[0]) for e in hand_log])
    h = np.array([int(e[1]) for e in hand_log], dtype=np.float64)
    order = np.argsort(s, kind="stable")
    s, h = s[order], h[order]
    j = np.clip(np.searchsorted(s, seg, side="right") - 1, 0, len(h) - 1)
    return h[j]


def grow(ctx, hands: list[str], *, length: float, blend: str, joins: str, plateau: float):
    """The research drift line in px: (points, meta). Hands come through the
    library policy gate."""
    grams = [ctx.use("hand", h) for h in hands]
    st, info = hy.drift_line(grams, np.random.default_rng(ctx.seed), total=float(length), mode=blend,
                             size=RESEARCH_SIZE, plateau=float(plateau),
                             context="chain" if joins == "chain" else "kappa")
    pts = st.points
    meta = {"voices": list(hands), "route": list(hands), "blend": blend, "joins": joins, "length_R": length,
            "ref_length_px": float(st.meta["ref_length"]), "tokens": int(info["tokens"]),
            "hand_share_by_decile": info["hand_share_by_decile"],
            "library": [{"kind": "hand", "id": h} for h in hands]}
    vc = _voice_channel(pts, st.meta["hand_log"], st.meta["ref_length"])
    return pts, {"voice": vc}, meta


_COMMON = [
    P("length", "float", 6.0, "line length in reference lengths of the research frame", min=0.2, max=12.0),
    P("joins", "choice", "smooth", "smooth: chunks start fresh, κ continuous; chain: chunks continue the "
      "previous context (straight runs and corners break in)", choices=("smooth", "chain")),
]


@voice("hand", params=[P("hand", "ref", "matisse", "the grammar that speaks", kind="hand"), *_COMMON],
       doc="one learned hand, whole (the bench's 'each')")
def hand(ctx, *, hand: str, length: float, joins: str):
    pts, ch, meta = grow(ctx, [hand], length=length, blend="mixture", joins=joins, plateau=0.12)
    return fitted([pts], ctx.box, [ch], [meta])


@voice("drift", params=[
    P("hands", "refs", ["matisse", "shikasta", "lichtenberg"], "the route, in order", kind="hand",
      min_len=1, max_len=6),
    P("blend", "choice", "mixture", "mixture: each token from one hand by weight; interp: tokens moved toward "
      "the other hand's nearest token", choices=("mixture", "interp")),
    P("plateau", "float", 0.12, "share of the line each hand speaks pure before it cross-fades",
      min=0.0, max=0.6),
    *_COMMON], doc="one line whose hand drifts along a route of hands")
def drift(ctx, *, hands: list[str], blend: str, plateau: float, length: float, joins: str):
    pts, ch, meta = grow(ctx, hands, length=length, blend=blend, joins=joins, plateau=plateau)
    return fitted([pts], ctx.box, [ch], [meta])
