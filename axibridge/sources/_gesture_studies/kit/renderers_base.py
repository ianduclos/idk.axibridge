# FROZEN from research commit 529a195: tools/gesture/gesture/kit/renderers_base.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Seed renderers — marks → plotter polylines (Ink).

- `wire` every mark is one open polyline at the pen width (channels ignored).
- `nib`  each mark becomes a research RegimeStroke from its channels
         (points, r, phi, W, M→mass) and is inked by `regime.render` with a
         `penrender.nib_style` (a outline | b+ concentric insets | c lanes
         along the stroke | e nib-point traces | c+e both). Masses keep
         regime's concentric fill in every style. A closed path running
         along the silhouette boundary comes back `filled=True` — in the
         research styles only `a` keeps outline rings as separate paths
         (b+/c/e chain them into their passes; the app's frozen copy
         separates them, a deliberate app-side change).
"""
from __future__ import annotations

import numpy as np

from ._research import penrender as pr
from ._research import regime as rg
from .core import Ink, P, renderer

STYLES = ("a", "b", "b+", "c", "e", "c+e", "b++c+e")


@renderer("wire", params=[P("pen", "float", 0.4, "pen width mm", min=0.05, max=3.0)],
          doc="one open polyline per mark", reach=lambda p: 0.5 * p["pen"])
def wire(ctx, marks, *, pen):
    return [Ink(m.points, closed=False, filled=False, pen=pen, meta={"voice": m.meta.get("voice_id")})
            for m in marks if len(m) >= 2]


def regime_stroke(mark) -> rg.RegimeStroke:
    """A research RegimeStroke from a Mark's channels (M is the mass width)."""
    c = mark.channels
    return rg.make(mark.points, c["r"], phi=c["phi"], W=c["W"], mass=c["M"])


def _nib_reach(p: dict) -> float:
    return 0.5 * p["pen"]


@renderer("nib", params=[
    P("style", "choice", "e", "a outline | b/b+ insets | c lanes | e nib traces | c+e both", choices=STYLES),
    P("pen", "float", 0.4, "pen width mm", min=0.05, max=3.0),
], doc="ink each mark as a broad nib / mass from its r, phi, W, M channels", reach=_nib_reach)
def nib(ctx, marks, *, style, pen):
    rend = pr.nib_style(style, seed=int(ctx.seed))
    out = []
    for m in marks:
        if len(m) < 2:
            continue
        st = regime_stroke(m)
        sil: list = []

        def hook(strokes, pen, paths, parts, _rend=rend, _sil=sil):
            _sil.append(parts["G"])
            return _rend(strokes, pen, paths=paths, parts=parts) if _rend is not None else paths

        paths = rg.render(st, pen, nib_renderer=hook)
        G = sil[0] if sil else None
        for p in paths:
            p = np.asarray(p, dtype=np.float64)
            if len(p) < 2:
                continue
            closed = len(p) >= 4 and bool(np.allclose(p[0], p[-1], atol=1e-9))
            out.append(Ink(p, closed=closed, filled=closed and _on_outline(p, G, pen), pen=pen,
                           meta={"voice": m.meta.get("voice_id"), "style": style}))
    return out


def _on_outline(p: np.ndarray, G, pen: float) -> bool:
    """A closed path is an outline ring (filled) when it runs along the
    silhouette's boundary (regime's rings are its exterior/interior rings;
    fill insets sit ≥ ~pen inside)."""
    if G is None or G.is_empty:
        return False
    import shapely  # noqa: PLC0415
    d = shapely.distance(shapely.points(p), G.boundary)
    return bool(np.max(d) <= 0.05 * pen)
