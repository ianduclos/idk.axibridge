# FROZEN from research commit 6f96418: tools/gesture/gesture/extract_hybrid.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Bake-off hybrid: one extractor's TOPOLOGY + sub-pixel centre refinement.

    extract(gray, **kw) -> Drawing

Default base = `extract` (hysteresis ink detection, skeleton graph,
junction pairing, gap joins — the most robust stroke topology on real
scans). Its centrelines, though, are skeleton pixels de-staircased at 1 px,
and the residual ±½ px wobble (period tens of px) is what dominated its κ
error on ground truth. `subpixel.refine_centrelines` moves every point onto
the core-of-profile centroid of the ink (crossings / T bars interpolated),
which is where the other entrants got their κ accuracy.

`base="ridge"` runs the same post-pass on `extract_ridge` topology instead.

kw: `base`; `refine` = dict of `refine_centrelines` options (or False to
skip, for ablations); everything else goes to the base extractor.
"""
from __future__ import annotations

import numpy as np

from . import extract as _extract
from . import extract_ridge as _ridge
from .core import Drawing, Stroke
from .subpixel import refine_centrelines

__all__ = ["extract", "REFINE_DEFAULTS"]

REFINE_DEFAULTS: dict = {}   # refine_centrelines' own defaults (bench-picked there)


def _to_frame(d: Drawing, f, w_scale: float) -> Drawing:
    out = [Stroke(f(s.points), width=None if s.width is None else s.width * w_scale,
                  closed=s.closed, meta=s.meta) for s in d.strokes]
    return Drawing(out, source=d.source, size=d.size, meta=d.meta)


def extract(gray: np.ndarray, *, base: str = "extract", refine: dict | bool | None = None,
            **kw) -> Drawing:
    """gray float (H, W) in [0, 1], ink dark → Drawing (points in the base
    extractor's output frame; for `extract` with `scale` ≠ 1 that is the
    ORIGINAL raster, and refinement runs in `gray`'s frame in between)."""
    if base == "extract":
        d = _extract.extract(gray, **kw)
    elif base == "ridge":
        d = _ridge.extract(gray, **kw)
    else:
        raise ValueError(f"unknown base {base!r} (extract | ridge)")
    if refine is False:
        return d
    opts = dict(REFINE_DEFAULTS)
    opts.update(refine or {})
    scale = float(kw.get("scale", 1.0)) if base == "extract" else 1.0
    if scale != 1.0:   # extract reports ORIGINAL px; gray is at `scale`
        fwd = lambda p: (p + 0.5) * scale - 0.5
        back = lambda p: (p + 0.5) / scale - 0.5
        r = refine_centrelines(gray, _to_frame(d, fwd, scale), **opts)
        r = _to_frame(r, back, 1.0 / scale)
    else:
        r = refine_centrelines(gray, d, **opts)
    meta = dict(r.meta)
    meta["method"] = f"hybrid:{base}+subpixel"
    return Drawing(r.strokes, source=r.source, size=r.size, meta=meta)
