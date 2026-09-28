"""Deterministic evidence tracing, never landmark templates."""

import numpy as np
from scipy.ndimage import (
    binary_propagation,
    gaussian_filter,
    gaussian_filter1d,
    label,
    sobel,
)
from ..sources._lineart import thin_mask
from .contracts import Candidate
from .geometry import arc, samples, simplify


def graph(mask, checkpoint=lambda: None):
    checkpoint()
    yy, xx = np.nonzero(thin_mask(mask))
    if len(xx) > 500_000:
        raise ValueError("Too much line evidence; reduce image detail")
    nodes = set(zip(xx.tolist(), yy.tolist()))
    adj = {}
    for i, (x, y) in enumerate(sorted(nodes)):
        if i % 2048 == 0:
            checkpoint()
        near = []
        for dx, dy in [
            (-1, 0),
            (1, 0),
            (0, -1),
            (0, 1),
            (-1, -1),
            (-1, 1),
            (1, -1),
            (1, 1),
        ]:
            q = x + dx, y + dy
            if q not in nodes:
                continue
            if dx and dy and ((x + dx, y) in nodes or (x, y + dy) in nodes):
                continue
            near.append(q)
        adj[x, y] = near
    used = set()
    lines = []
    for i, a in enumerate(sorted(nodes, key=lambda a: (len(adj[a]) == 2, a))):
        if i % 1024 == 0:
            checkpoint()
        for b in adj[a]:
            edge = tuple(sorted((a, b)))
            if edge in used:
                continue
            p = [a]
            prev, cur = a, b
            used.add(edge)
            while True:
                p.append(cur)
                if len(adj[cur]) != 2:
                    break
                nxt = next(q for q in adj[cur] if q != prev)
                edge = tuple(sorted((cur, nxt)))
                if edge in used:
                    break
                used.add(edge)
                prev, cur = cur, nxt
            if len(p) > 2:
                lines.append(np.asarray(p, float))
    return lines


def trace_map(whiteness, prefix="line", checkpoint=lambda: None):
    dark = 1 - np.asarray(whiteness, dtype=float)
    local = dark - gaussian_filter(dark, 3)
    low = (dark > 0.035) & ((local > 0.015) | (dark > 0.2))
    seed = (dark > 0.1) | (local > 0.055)
    mask = binary_propagation(seed & low, mask=low, structure=np.ones((3, 3)))
    labs, _ = label(mask, np.ones((3, 3)))
    counts = np.bincount(labs.ravel())
    mask &= counts[labs] >= 3
    out = []
    for i, q in enumerate(graph(mask, checkpoint)):
        if i % 128 == 0:
            checkpoint()
        q = samples(q, 0.8)
        smooth = gaussian_filter1d(q, 0.65, axis=0, mode="nearest")
        smooth[0], smooth[-1] = q[0], q[-1]
        q = simplify(smooth, 0.3)
        if arc(q) < 2.5:
            continue
        dense = samples(q, 1)
        ix = np.clip(dense[:, 0].astype(int), 0, dark.shape[1] - 1)
        iy = np.clip(dense[:, 1].astype(int), 0, dark.shape[0] - 1)
        out.append(Candidate(q, float(dark[iy, ix].mean()), f"{prefix}-{i}"))
        if len(out) > 20000:
            raise ValueError("Too many contours; reduce image detail")
    return out


def photographic_map(rgb):
    lum = gaussian_filter(rgb @ np.array([0.2126, 0.7152, 0.0722]), 1.2)
    magnitude = np.hypot(sobel(lum, axis=0), sobel(lum, axis=1))
    peak = float(magnitude.max())
    if peak < 0.03:
        return np.ones_like(lum)
    return 1 - np.clip(magnitude / peak, 0, 1)
