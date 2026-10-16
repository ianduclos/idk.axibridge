"""Lower-bound extractor for the bake-off: Sauvola → skeleton → every
skeleton-graph edge is a stroke (no spur pruning, no junction pairing).
Any real technique has to beat this."""
from __future__ import annotations

import numpy as np
import sknw
from scipy.ndimage import distance_transform_edt
from skimage.filters import threshold_sauvola
from skimage.morphology import remove_small_objects, skeletonize

from .core import Drawing, Stroke


def extract(gray: np.ndarray, *, min_area: int = 30, min_len: float = 3.0) -> Drawing:
    H, W = gray.shape
    win = max(15, (min(H, W) // 60) | 1)
    mask = remove_small_objects(gray < threshold_sauvola(gray, window_size=win, k=0.2), max_size=min_area)
    skel = skeletonize(mask)
    dt = distance_transform_edt(mask)
    g = sknw.build_sknw(skel.astype(np.uint8))
    strokes = []
    for a, b in g.edges():
        for e in (g[a][b].values() if g.is_multigraph() else [g[a][b]]):
            rc = np.asarray(e["pts"], float)
            if len(rc) < 2:
                continue
            pts = rc[:, ::-1]
            if np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)) < min_len:
                continue
            width = 2 * dt[rc[:, 0].astype(int), rc[:, 1].astype(int)]
            strokes.append(Stroke(pts, width=width))
    return Drawing(strokes, source="", size=(W, H), meta={"method": "naive"})
