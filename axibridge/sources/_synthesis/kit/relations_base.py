# FROZEN from research commit a66c6a5: tools/gesture/gesture/kit/relations_base.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Reference relations for the v2 score (round 16 phase 0, lead-owned):
the control and the round-15 behaviour, so the contract is tested end to end.

- `cross`: no awareness. Lines run through each other; every crossing is
  logged (outcome "cross"), so devices can count them.
- `yield`: listen's yield, as a relation. At every crossing the dst (the
  later line, by the executor's pairing) gives way: a gap of pen/2 + gap mm.
"""
from __future__ import annotations

from ._relations import RelOut, crossings, gap_marks, relation
from .core import P


@relation("cross", phase="contact", params=[
    P("min_sep", "float", 0.0, "crossings closer than this along a line count once, mm", min=0.0, max=20.0),
], doc="no awareness: lines simply cross (the control); every crossing is logged")
def cross(rctx, src, dst, *, min_sep):
    xs = crossings(src, dst, min_sep=min_sep)
    return RelOut(events=[{"outcome": "cross", "at": c.at, "s": [c.s_dst, c.s_dst], "mark": c.i_dst,
                           "s_src": [c.s_src, c.s_src]} for c in xs])


@relation("yield", phase="contact", params=[
    P("gap", "float", 1.2, "gap either side of the crossing beyond the pen's half width, mm", min=0.0, max=6.0),
    P("pen", "float", 0.35, "the other line's pen width, mm", min=0.05, max=3.0),
    P("min_sep", "float", 0.0, "crossings closer than this along a line count once, mm", min=0.0, max=20.0),
], doc="the later line gives way at every crossing (round 15 listen's yield)")
def yield_(rctx, src, dst, *, gap, pen, min_sep):
    xs = crossings(src, dst, min_sep=min_sep)
    if not xs:
        return RelOut()
    half = pen / 2 + gap
    cuts: dict[int, list] = {}
    events = []
    for c in xs:
        cuts.setdefault(c.i_dst, []).append((c.s_dst - half, c.s_dst + half))
        events.append({"outcome": "gap_under", "at": c.at, "s": [c.s_dst - half, c.s_dst + half], "mark": c.i_dst})
    return RelOut(dst=gap_marks(dst, cuts), events=events)
