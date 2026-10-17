"""Round 12, thread `oehlen_conduct`: the ink for the conduction voices.

`oehlen_conduct_ink` — each mark is cut into runs of constant pen (channel
`cw`, pen width in mm; a mark without it uses `pen`). One Ink per run, at
that pen width, so a line that changes weight is several pen passes that
meet end to end (the plotter changes pens between passes). Nothing is
filled; nothing is hatched. `scale` multiplies every pen (to try the same
drawing with a lighter or heavier set).
"""
from __future__ import annotations

import numpy as np

from .core import Ink, P, renderer


def runs_of(cw: np.ndarray) -> list[tuple[int, int, float]]:
    """(start, end inclusive, value) runs of a piecewise-constant channel;
    neighbouring runs share their boundary point so the line stays joined."""
    out = []
    a = 0
    for i in range(1, len(cw) + 1):
        if i == len(cw) or cw[i] != cw[a]:
            out.append((a, min(i, len(cw) - 1), float(cw[a])))
            a = i
    return out


@renderer("oehlen_conduct_ink", params=[
    P("pen", "float", 0.4, "pen for marks without a cw channel, mm", min=0.05, max=4.0),
    P("scale", "float", 1.0, "every pen × this", min=0.2, max=4.0),
    P("min_run", "float", 1.5, "a pen run shorter than this (mm) takes its neighbour's pen", min=0.0, max=30.0),
], reach=lambda p: 2.0 * p["scale"], doc="ink by the cw channel: one pen pass per run of constant pen width")
def oehlen_conduct_ink(ctx, marks, *, pen, scale, min_run):
    inks = []
    for m in marks:
        if len(m) < 2:
            continue
        cw = np.array(m.channels.get("cw", np.full(len(m), pen)), float)
        s = m.arclength()
        rs = runs_of(cw)
        if min_run > 0 and len(rs) > 1:                 # absorb flickers into the previous run
            for k in range(1, len(rs)):
                a, b, w = rs[k]
                if s[b] - s[a] < min_run:
                    cw[a:b + 1] = rs[k - 1][2]
                    rs[k] = (a, b, rs[k - 1][2])
            rs = runs_of(cw)
        for a, b, w in rs:
            if b - a < 1:
                continue
            inks.append(Ink(m.points[a:b + 1], closed=False, filled=False, pen=float(w) * scale,
                            meta={"role": int(m.channels["role"][a]) if "role" in m.channels else -1}))
    return inks
