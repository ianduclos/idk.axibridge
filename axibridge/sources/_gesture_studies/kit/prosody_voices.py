# FROZEN from research commit ecd64f8: tools/gesture/gesture/kit/prosody_voices.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Prosody thread (round 9): `drift_tokens`, the seed `drift` voice plus the
grammar's own syllables.

The seed `drift` voice keeps only the hand log (→ the `voice` channel); the
token list the grammar spoke is dropped, so a modulator cannot hear token
boundaries that leave no geometric trace (arc → clothoid, κ-continuous).
This voice grows the IDENTICAL line (same `hy.drift_line` call, same rng:
points and `voice` match `drift` exactly; tested) and adds:

- `token`    running index of the segment token drawn at each point ("nearest")
- `tok_turn` |angle| of the corner token(s) that open the segment (rad, 0 when
             the segment joins its predecessor smoothly; "nearest")

Proposed core change: let the seed `drift`/`hand` voices carry these two
channels and this file can go.
"""
from __future__ import annotations

import numpy as np

from ._research import hybrid as hy
from .core import P, channel_kind, fitted, voice
from .voices_base import _COMMON, RESEARCH_SIZE, _voice_channel

channel_kind("token", "nearest")
channel_kind("tok_turn", "nearest")


def token_channels(points: np.ndarray, toks: list, R: float) -> dict:
    """Per point: segment-token index and the corner angle opening it."""
    starts, turns, pend, s = [], [], 0.0, 0.0
    for t in toks:
        if t[0] == "corner":
            pend += abs(float(t[1]))
            continue
        starts.append(s)
        turns.append(pend)
        pend = 0.0
        s += float(t[1])
    seg = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))] / max(R, 1e-9)
    if not starts:
        return {"token": np.zeros(len(points)), "tok_turn": np.zeros(len(points))}
    j = np.clip(np.searchsorted(np.asarray(starts), seg, side="right") - 1, 0, len(starts) - 1)
    return {"token": j.astype(np.float64), "tok_turn": np.asarray(turns)[j]}


@voice("drift_tokens", params=[
    P("hands", "refs", ["matisse", "shikasta", "lichtenberg"], "the route, in order", kind="hand",
      min_len=1, max_len=6),
    P("blend", "choice", "mixture", "mixture | interp (as drift)", choices=("mixture", "interp")),
    P("plateau", "float", 0.12, "share each hand speaks pure (as drift)", min=0.0, max=0.6),
    *_COMMON], doc="the drift line, identical, plus token + tok_turn channels (the grammar's syllables)")
def drift_tokens(ctx, *, hands, blend, plateau, length, joins):
    grams = [ctx.use("hand", h) for h in hands]
    st, info = hy.drift_line(grams, np.random.default_rng(ctx.seed), total=float(length), mode=blend,
                             size=RESEARCH_SIZE, plateau=float(plateau),
                             context="chain" if joins == "chain" else "kappa")
    pts = st.points
    R = float(st.meta["ref_length"])
    ch = {"voice": _voice_channel(pts, st.meta["hand_log"], R), **token_channels(pts, st.meta["tokens"], R)}
    meta = {"voices": list(hands), "route": list(hands), "blend": blend, "joins": joins, "length_R": length,
            "ref_length_px": R, "tokens": int(info["tokens"]),
            "hand_share_by_decile": info["hand_share_by_decile"],
            "library": [{"kind": "hand", "id": h} for h in hands]}
    return fitted([pts], ctx.box, [ch], [meta])
