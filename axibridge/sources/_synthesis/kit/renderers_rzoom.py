# FROZEN from research commit 071aea1: tools/gesture/gesture/kit/renderers_rzoom.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 14, thread c1 (`rzoom`): ink the zooming river by its zoom.

`rzoom_ink` splits each mark into runs by zoom band and gives each band its
own pen width (and optionally its own Flexoki ink): the far view's dense
twists in a fine pen, the opened bends in a heavier one, as if nearer. The
line stays geometrically contiguous (consecutive runs share their boundary
point); on the plotter each band is a pen pass. Marks without a `zoom`
channel are inked as one wire at the first pen.

Bands: b = floor(N · ln z / ln z_top), N = len(pens), z_top = the largest
zoom over all the marks inked together; runs shorter than `min_run` mm are merged into their
neighbour so no crumb of another pen appears.
"""
from __future__ import annotations

import numpy as np

from .core import Ink, P, arclength, renderer
from .dev_chorus import parse_inks


def bands(z: np.ndarray, n_bands: int, s: np.ndarray, min_run: float, top: float | None = None) -> np.ndarray:
    """Band index per point (0 = far), short runs merged; top: the zoom of
    the last band's upper edge (default: this line's largest zoom)."""
    z = np.asarray(z, float)
    top = max(float(z.max() if top is None else top), 1.0 + 1e-9)
    g = np.log(np.maximum(z, 1.0)) / np.log(top)
    b = np.minimum((g * n_bands).astype(int), n_bands - 1)
    for _ in range(8):                                     # merge short runs into the longer neighbour
        cuts = np.flatnonzero(np.diff(b)) + 1
        starts, ends = np.r_[0, cuts], np.r_[cuts, len(b)]
        lens = s[np.minimum(ends, len(s) - 1)] - s[starts]
        short = np.flatnonzero(lens < min_run)
        if not len(short) or len(starts) == 1:
            break
        i = int(short[np.argmin(lens[short])])
        left = b[starts[i - 1]] if i > 0 else None
        right = b[starts[i + 1]] if i + 1 < len(starts) else None
        if left is None:
            b[starts[i]:ends[i]] = right
        elif right is None:
            b[starts[i]:ends[i]] = left
        else:
            ll = lens[i - 1]
            rl = lens[i + 1]
            b[starts[i]:ends[i]] = left if ll >= rl else right
    return b


@renderer("rzoom_ink", params=[
    P("pens", "floats", [0.25, 0.4, 0.6], "pen width per zoom band, far → near, mm"),
    P("inks", "str", "black", "Flexoki ink per band, comma-separated (one name: every band)"),
    P("min_run", "float", 4.0, "shortest run in one band, mm (shorter runs join a neighbour)", min=0.0, max=100.0),
], doc="the zooming river inked by zoom band: fine far, heavier near (contiguous runs)",
    reach=lambda p: max(p.get("pens") or [0.6]) / 2)
def rzoom_ink(ctx, marks, *, pens, inks, min_run):
    pens = [float(min(max(v, 0.05), 3.0)) for v in (pens or [0.4])]
    names = parse_inks(inks)
    out = []
    zs = [float(np.max(m["zoom"])) for m in marks if "zoom" in m.channels and len(m)]
    top = max(zs) if zs else None
    for m in marks:
        if "zoom" not in m.channels or len(m) < 2:
            out.append(Ink(m.points, pen=pens[0], meta={"colour": names[0], "band": 0}))
            continue
        s = arclength(m.points)
        b = bands(m["zoom"], len(pens), s, min_run, top)
        cuts = np.flatnonzero(np.diff(b)) + 1
        for a, e in zip(np.r_[0, cuts], np.r_[cuts, len(b)]):
            k = int(b[a])
            seg = m.points[a:min(e + 1, len(m))]               # share the boundary point with the next run
            if len(seg) >= 2:
                out.append(Ink(seg, pen=pens[k], meta={"colour": names[min(k, len(names) - 1)], "band": k}))
    return out
