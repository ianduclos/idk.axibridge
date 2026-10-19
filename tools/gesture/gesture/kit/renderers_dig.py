"""Round 16 C `dig`: the round-7 wet edge as a renderer the v2 score can name.

`dig_wet` is the kit's `nib` renderer with round 7's measured wet mass edges
switched on (`regime.render(wet=…)`): lines and nibs are untouched (the wet
process is weighted by massness), masses get low-order lumpiness and cusped
bays from a measured profile (Ian's reference image, Marden, Hokusai, or the
generative-allowed calligraphy sheets). Pair it with `dig_pool`, which puts a
mass where two layers cross. Fill: concentric (round 6) or spiral (round 7:
40–65 % fewer lifts).
"""
from __future__ import annotations

import numpy as np

from .. import penrender as pr
from .. import regime as rg
from .core import Ink, P, renderer
from .renderers_base import STYLES, _on_outline, regime_stroke

WET = ("none", "reference", "marden", "hokusai", "calligraphy")


@renderer("dig_wet", params=[
    P("style", "choice", "e", "nib style: a outline | b/b+ insets | c lanes | e nib traces | c+e", choices=STYLES),
    P("pen", "float", 0.4, "pen width mm", min=0.05, max=3.0),
    P("wet", "choice", "marden", "mass edge profile (round 7, measured): none | reference | marden | hokusai | "
      "calligraphy", choices=WET),
    P("fill", "choice", "concentric", "mass fill: concentric | spiral (fewer lifts)",
      choices=("concentric", "spiral")),
], doc="nib + mass with round 7's wet, irregular mass edges", reach=lambda p: 0.5 * p["pen"])
def dig_wet(ctx, marks, *, style, pen, wet, fill):
    rend = pr.nib_style(style, seed=int(ctx.seed))
    out = []
    for k, m in enumerate(marks):
        if len(m) < 2:
            continue
        st = regime_stroke(m)
        sil: list = []

        def hook(strokes, pen, paths, parts, _rend=rend, _sil=sil):
            _sil.append(parts["G"])
            return _rend(strokes, pen, paths=paths, parts=parts) if _rend is not None else paths

        seed = int(ctx.rng("wet", k).integers(2 ** 31 - 1))
        paths = rg.render(st, pen, wet=None if wet == "none" else wet, seed=seed, fill_style=fill,
                          nib_renderer=hook)
        G = sil[0] if sil else None
        for p in paths:
            p = np.asarray(p, dtype=np.float64)
            if len(p) < 2:
                continue
            closed = len(p) >= 4 and bool(np.allclose(p[0], p[-1], atol=1e-9))
            out.append(Ink(p, closed=closed, filled=closed and _on_outline(p, G, pen), pen=pen,
                           meta={"voice": m.meta.get("voice_id"), "style": style, "wet": wet}))
    return out
