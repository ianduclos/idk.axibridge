# FROZEN from research commit 6f96418: tools/gesture/gesture/kit/renderers_lcorp.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 15, thread B (`lcorp`): constant-width ink, coloured as structure.

Renderer `lcorp_ink`: one pen width everywhere (Ian on river_zoom: "the line
width should remain the same"). Colour is optional structure: by the hand
speaking (`voice` channel, a relay's hands) or by part (lines of a lens
sheet). Runs split where the colour changes and share their end points, so
the line stays contiguous across a change of ink. Colours are Flexoki names
(Ink.meta["colour"]; `arrangers_oehlen_found.render_colour` previews them).
"""
from __future__ import annotations

import numpy as np

from .core import Ink, P, renderer


@renderer("lcorp_ink", params=[
    P("pen", "float", 0.3, "pen width, mm (constant)", min=0.05, max=3.0),
    P("by", "choice", "none", "colour by: none (all `inks[0]`), voice (the hand speaking), part (one ink per "
      "line)", choices=("none", "voice", "part")),
    P("inks", "str", "black,blue,red,green", "Flexoki ink names, comma-separated, in voice / part order"),
    P("min_run", "float", 3.0, "runs shorter than this (mm) keep the previous ink", min=0.0, max=50.0),
], doc="constant-width wire, optionally coloured by voice or part", reach=lambda p: p["pen"] / 2)
def lcorp_ink(ctx, marks, *, pen, by, inks, min_run):
    names = [s.strip() for s in inks.split(",") if s.strip()] or ["black"]
    out = []
    for m in marks:
        if by == "part":
            out.append(Ink(m.points, closed=False, filled=False, pen=pen,
                           meta={"colour": names[int(m.meta.get("part", 0)) % len(names)]}))
            continue
        v = m.channel("voice") if by == "voice" else None
        if v is None:
            out.append(Ink(m.points, closed=False, filled=False, pen=pen, meta={"colour": names[0]}))
            continue
        v = np.asarray(v).round().astype(int)
        s = m.arclength()
        cuts = [0] + [i for i in range(1, len(v)) if v[i] != v[i - 1]] + [len(v) - 1]
        runs, a = [], 0
        for b in cuts[1:]:
            if b - a < 1:
                continue
            if runs and s[b] - s[a] < min_run:
                runs[-1] = (runs[-1][0], b, runs[-1][2])
            else:
                runs.append((a, b, int(v[a])))
            a = b
        for a, b, k in runs:
            out.append(Ink(m.points[a:b + 1], closed=False, filled=False, pen=pen,
                           meta={"colour": names[k % len(names)], "voice": k}))
    return out
