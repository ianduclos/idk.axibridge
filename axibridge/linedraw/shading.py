"""Small, deterministic raster-to-ink helpers for opt-in tonal treatment."""

import numpy as np


def scanline_mask(mask, spacing, checkpoint=lambda: None, *, min_length=3, limit=2000):
    """Horizontal runs inside a supplied mask; false pixels remain white gaps."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("mask and spacing must be finite and positive")
    h, _ = mask.shape
    out = []
    for y in np.arange(spacing / 2, h, max(1., spacing)):
        checkpoint()
        row = mask[min(int(y), h - 1)]
        starts = np.flatnonzero(np.diff(np.r_[False, row, False].astype(np.int8)) == 1)
        ends = np.flatnonzero(np.diff(np.r_[False, row, False].astype(np.int8)) == -1)
        for x0, x1 in zip(starts, ends):
            if x1 - x0 >= min_length:
                out.append(np.array([[float(x0), y], [float(x1), y]]))
                if len(out) >= limit:
                    return out
    return out
