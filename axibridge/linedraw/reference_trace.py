"""Native-pixel learned-map tracing for the frozen Light research recipe.

The caller supplies an already inferred whiteness map. This module performs no
model inference or file access; coordinates are returned in source pixels.
"""

from __future__ import annotations

import heapq
import math

import numpy as np
from scipy.ndimage import binary_propagation, gaussian_filter, gaussian_filter1d, label
from shapely import affinity
from shapely.geometry import LineString, Point

from ..sources._lineart import thin_mask
from .geometry import arc, samples, simplify


def _tangent(path, end, reach=5.0):
    points = path if end == 0 else path[::-1]
    origin = points[0]
    distance = 0.0
    for a, b in zip(points[:-1], points[1:]):
        step = float(np.linalg.norm(b - a))
        if not step:
            continue
        target = a + (b - a) * min(1, (reach - distance) / step)
        if distance + step >= reach:
            break
        distance += step
    else:
        target = points[-1]
    direction = target - origin
    norm = float(np.linalg.norm(direction))
    return direction / norm if norm else None


def _join_paths(paths):
    """Research endpoint pairing: smallest turn, then gap; retain all points."""
    active = {i: np.asarray(q, float).copy() for i, q in enumerate(paths)}
    next_id = len(active)
    buckets, endpoints, candidates = {}, {}, []

    def cell(point):
        return tuple(np.floor(point / 1.5).astype(int))

    def register(path_id):
        path = active[path_id]
        if np.array_equal(path[0], path[-1]):
            return
        for end in (0, -1):
            tangent = _tangent(path, end)
            if tangent is None:
                continue
            handle, point = (path_id, end), path[end]
            cx, cy = cell(point)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other in buckets.get((cx + dx, cy + dy), ()):
                        if other[0] == path_id:
                            continue
                        old_point, old_tangent = endpoints[other]
                        gap = float(np.linalg.norm(point - old_point))
                        if gap > 1.5:
                            continue
                        angle = math.degrees(math.acos(float(np.clip(-np.dot(tangent, old_tangent), -1, 1))))
                        if angle <= 50:
                            a, b = sorted((handle, other))
                            heapq.heappush(candidates, (angle, gap, a, b))
            endpoints[handle] = (point, tangent)
            buckets.setdefault((cx, cy), set()).add(handle)

    def unregister(path_id):
        for end in (0, -1):
            handle = (path_id, end)
            old = endpoints.pop(handle, None)
            if old is not None:
                buckets[cell(old[0])].remove(handle)

    for path_id in active:
        register(path_id)
    while candidates:
        _, _, (id_a, end_a), (id_b, end_b) = heapq.heappop(candidates)
        if id_a not in active or id_b not in active:
            continue
        unregister(id_a)
        unregister(id_b)
        a, b = active.pop(id_a), active.pop(id_b)
        if end_a == 0:
            a = a[::-1]
        if end_b == -1:
            b = b[::-1]
        active[next_id] = np.concatenate((a, b))
        register(next_id)
        next_id += 1
    return list(active.values())


def _graph(mask, checkpoint):
    yy, xx = np.nonzero(thin_mask(mask))
    if len(xx) > 500_000:
        raise ValueError("Too much line evidence; reduce image detail")
    nodes = set(zip(xx.tolist(), yy.tolist()))
    adj = {}
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    for i, (x, y) in enumerate(sorted(nodes)):
        if i % 2048 == 0:
            checkpoint()
        near = []
        for dx, dy in offsets:
            q = x + dx, y + dy
            if q in nodes and not (dx and dy and ((x + dx, y) in nodes or (x, y + dy) in nodes)):
                near.append(q)
        adj[x, y] = near
    used, lines = set(), []

    def walk(a, b):
        path, prev, cur = [a], a, b
        used.add(tuple(sorted((a, b))))
        while True:
            path.append(cur)
            if len(adj[cur]) != 2:
                break
            nxt = next(q for q in adj[cur] if q != prev)
            edge = tuple(sorted((cur, nxt)))
            if edge in used:
                break
            used.add(edge)
            prev, cur = cur, nxt
        if len(path) >= 2:
            lines.append(path)

    for i, a in enumerate(sorted(nodes, key=lambda q: (len(adj[q]) == 2, q))):
        if i % 1024 == 0:
            checkpoint()
        for b in adj[a]:
            if tuple(sorted((a, b))) not in used:
                walk(a, b)
    return [q for q in _join_paths(lines) if arc(q) >= 2]


def trace_candidates(whiteness: np.ndarray, bounds: tuple[int, int, int, int],
                     source_size: tuple[int, int], prefix: str = "line",
                     checkpoint=lambda: None) -> list[dict]:
    """Trace research candidates with native uint8 map quantization."""
    return _trace_candidates(whiteness, bounds, source_size, prefix, checkpoint, True)


def _trace_candidates(whiteness, bounds, source_size, prefix, checkpoint, round_points):
    image = np.asarray(whiteness, dtype=float)
    if image.ndim != 2 or not np.isfinite(image).all() or np.any((image < 0) | (image > 1)):
        raise ValueError("whiteness must be finite HxW values in [0,1]")
    if min(image.shape) < 2:
        return []
    gray = np.uint8(np.rint(np.clip(image * 255, 0, 255)))
    dark = 1.0 - gray.astype(np.float32) / 255.0
    local = dark - gaussian_filter(dark, 3)
    low = (dark > .035) & ((local > .015) | (dark > .20))
    seed = (dark > .10) | (local > .055)
    mask = binary_propagation(seed & low, mask=low, structure=np.ones((3, 3)))
    labs, _ = label(mask, np.ones((3, 3)))
    counts = np.bincount(labs.ravel())
    mask &= counts[labs] >= 3
    sx, sy = (bounds[2] - bounds[0]) / image.shape[1], (bounds[3] - bounds[1]) / image.shape[0]
    result = []
    for index, path in enumerate(_graph(mask, checkpoint)):
        if index % 128 == 0:
            checkpoint()
        sampled = samples(path, .65)
        smooth = gaussian_filter1d(sampled, .65, axis=0, mode="nearest")
        smooth[0], smooth[-1] = sampled[0], sampled[-1]
        simplified = simplify(smooth, .23)
        if len(simplified) < 2 or arc(simplified) < 2.5:
            continue
        source = simplified * [sx, sy] + list(bounds[:2])
        if not np.isfinite(source).all():
            raise ValueError(f"Nonfinite transformed candidate in {prefix}")
        source[:, 0] = np.clip(source[:, 0], 0, source_size[0])
        source[:, 1] = np.clip(source[:, 1], 0, source_size[1])
        length = arc(source)
        if length < 2.5:
            continue
        dense = samples(simplified, .65)
        ix = np.clip(dense[:, 0].astype(int), 0, image.shape[1] - 1)
        iy = np.clip(dense[:, 1].astype(int), 0, image.shape[0] - 1)
        confidence = float(np.mean(dark[iy, ix]))
        score = length ** .67 * (.22 + confidence) ** .5
        result.append({"id": f"{prefix}-{index:05d}",
                       "points": [[round(float(x), 6), round(float(y), 6)] for x, y in source]
                       if round_points else source.tolist(),
                       "length": round(length, 4), "confidence": round(confidence, 6),
                       "score": round(score, 6)})
        if len(result) > 20_000:
            raise ValueError("Too many contours; reduce image detail")
    result.sort(key=lambda q: (-q["score"], q["id"]))
    return result


def trace_face_candidates(whiteness: np.ndarray, bounds: tuple[int, int, int, int],
                          source_size: tuple[int, int], face_id: str,
                          ellipse: tuple[float, float, float, float],
                          checkpoint=lambda: None) -> list[dict]:
    """Trace then clip to the source ellipse, scoring each surviving fragment.

    The caller applies its face budget after this stable ranking. Confidence
    comes from the original quantized crop map, not from a resized preview.
    """
    image = np.asarray(whiteness, dtype=float)
    raw = _trace_candidates(image, bounds, source_size, face_id + "-crop", checkpoint, False)
    if not raw:
        return []
    cx, cy, rx, ry = map(float, ellipse)
    if not all(np.isfinite(v) for v in (cx, cy, rx, ry)) or rx <= 0 or ry <= 0:
        raise ValueError("ellipse must be finite with positive radii")
    region = affinity.translate(affinity.scale(Point(0, 0).buffer(1, quad_segs=96),
                                             xfact=rx, yfact=ry), xoff=cx, yoff=cy)
    gray = np.uint8(np.rint(np.clip(image * 255, 0, 255)))
    dark = 1.0 - gray.astype(np.float32) / 255.0
    sx = (bounds[2] - bounds[0]) / image.shape[1]
    sy = (bounds[3] - bounds[1]) / image.shape[0]
    clipped = []
    for index, candidate in enumerate(raw):
        if index % 128 == 0:
            checkpoint()
        line = LineString(candidate["points"])
        geometry = line.intersection(region)
        fragments = getattr(geometry, "geoms", [geometry])
        for fi, fragment in enumerate(fragments):
            if fragment.geom_type != "LineString" or fragment.length < 2.5:
                continue
            points = np.asarray(fragment.coords, dtype=float)
            if line.project(Point(points[0])) > line.project(Point(points[-1])):
                points = points[::-1]
            length = arc(points)
            dense = samples(points, min(sx, sy) * .65)
            ix = np.clip(((dense[:, 0] - bounds[0]) / sx).astype(int), 0, image.shape[1] - 1)
            iy = np.clip(((dense[:, 1] - bounds[1]) / sy).astype(int), 0, image.shape[0] - 1)
            confidence = float(np.mean(dark[iy, ix]))
            clipped.append({"id": candidate["id"] + f"-{fi:02d}",
                            "points": [[round(float(x), 6), round(float(y), 6)] for x, y in points],
                            "length": round(length, 4), "confidence": round(confidence, 6),
                            "score": round(length ** .67 * (.22 + confidence) ** .5, 6)})
    clipped.sort(key=lambda q: (-q["score"], q["id"]))
    return clipped
