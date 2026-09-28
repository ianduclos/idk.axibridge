"""Source-pixel rendering of the private structure-probe Light recipe.

No inferred body parts, local repairs, reference assets, or file access occur
here. All distances are source pixels, as in the research image (height 768).
"""

from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import (binary_dilation, binary_propagation, distance_transform_edt,
                           gaussian_filter, map_coordinates)
from scipy.spatial import cKDTree
from shapely.geometry import LineString
from shapely.ops import unary_union

from .flow_hatch import flow_hatch
from .geometry import arc, samples, simplify
from .reference_trace import _graph
from .shadows import line_components, shapes


def _inside(mask, point):
    x, y = point
    ix, iy = math.floor(x), math.floor(y)
    return 0 <= iy < mask.shape[0] and 0 <= ix < mask.shape[1] and bool(mask[iy, ix])


def _clip_path(points, mask):
    """Split at exact raster-cell crossings, including one-pixel holes."""
    points = np.asarray(points, float)
    if len(points) < 2:
        return []
    result, current = [], []
    for a, b in zip(points[:-1], points[1:]):
        delta = b - a
        if np.linalg.norm(delta) <= 1e-9:
            continue
        fractions = [0., 1.]
        for coordinate in (0, 1):
            if abs(delta[coordinate]) <= 1e-12:
                continue
            low, high = sorted((a[coordinate], b[coordinate]))
            for boundary in range(math.floor(low) + 1, math.ceil(high)):
                t = (boundary - a[coordinate]) / delta[coordinate]
                if 1e-12 < t < 1 - 1e-12:
                    fractions.append(t)
        fractions = sorted(set(fractions))
        for t0, t1 in zip(fractions[:-1], fractions[1:]):
            if t1 - t0 < 1e-12:
                continue
            if _inside(mask, a + delta * ((t0 + t1) / 2)):
                start, end = (a + delta * t0).tolist(), (a + delta * t1).tolist()
                if not current:
                    current = [start]
                elif np.linalg.norm(np.asarray(current[-1]) - start) > 1e-6:
                    current.append(start)
                current.append(end)
            elif len(current) > 1:
                result.append(current)
                current = []
    if len(current) > 1:
        result.append(current)
    simplified = []
    for path in result:
        clean = [path[0]]
        for point in path[1:]:
            if np.linalg.norm(np.asarray(point) - clean[-1]) < 1e-6:
                continue
            while len(clean) > 1:
                a, b, c = map(np.asarray, (clean[-2], clean[-1], point))
                if abs(np.cross(b - a, c - b)) > 1e-7 or np.dot(b - a, c - b) < 0:
                    break
                clean.pop()
            clean.append(point)
        if len(clean) > 1 and arc(np.asarray(clean)) > 1e-6:
            simplified.append(clean)
    return simplified


def _sample_even(points, spacing=1.0):
    p = np.asarray(points, float)
    lengths = np.linalg.norm(np.diff(p, axis=0), axis=1)
    cumulative = np.concatenate(([0.], np.cumsum(lengths)))
    if cumulative[-1] <= 0:
        return p[:1]
    distances = np.linspace(0, cumulative[-1], max(2, math.ceil(cumulative[-1] / spacing - 1e-6) + 1))
    index = np.minimum(np.searchsorted(cumulative, distances, side="right") - 1, len(p) - 2)
    fraction = (distances - cumulative[index]) / np.maximum(lengths[index], 1e-12)
    return p[index] + (p[index + 1] - p[index]) * fraction[:, None]


def _duplicate(a, b, threshold):
    ratio = a["length"] / max(b["length"], 1e-12)
    if not .6 <= ratio <= 1.6:
        return False
    pa, pb = _sample_even(a["points"]), _sample_even(b["points"])
    return (cKDTree(pb).query(pa)[0].mean() <= threshold and
            cKDTree(pa).query(pb)[0].mean() <= threshold)


def _deduplicate(paths, threshold=1.):
    kept, boxes = [], []
    for path in sorted(paths, key=lambda q: (-q["score"], q["id"])):
        p = np.asarray(path["points"])
        box = (p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max())
        if not any(box[0] <= oldbox[2] + threshold and oldbox[0] <= box[2] + threshold and
                   box[1] <= oldbox[3] + threshold and oldbox[1] <= box[3] + threshold and
                   _duplicate(path, old, threshold) for old, oldbox in zip(kept, boxes)):
            kept.append(path)
            boxes.append(box)
    return kept


def _clip_candidates(raw, fg, checkpoint):
    out = []
    for index, a in enumerate(raw):
        if index % 128 == 0:
            checkpoint()
        for i, pts in enumerate(_clip_path(a["points"], fg)):
            length = arc(np.asarray(pts))
            if length < 2.5:
                continue
            out.append({**a, "id": a["id"] + ":" + str(i), "points": pts,
                        "length": length, "score": length ** .67 * (.22 + a["confidence"]) ** .5})
    return _deduplicate(out, 1.)


def _select(pool, budget, fg):
    """Foreground weighted, deterministic 3x3 fair allocation."""
    h, w = fg.shape
    weights, cells = {}, {}
    for y in range(3):
        for x in range(3):
            weights[y * 3 + x] = max(1, np.sqrt(fg[round(y * h / 3):round((y + 1) * h / 3),
                                                round(x * w / 3):round((x + 1) * w / 3)].sum()))
    for q in pool:
        mid = LineString(q["points"]).interpolate(.5, normalized=True)
        k = min(2, int(mid.y / h * 3)) * 3 + min(2, int(mid.x / w * 3))
        cells.setdefault(k, []).append(q)
    for choices in cells.values():
        choices.sort(key=lambda q: (-q["score"], q["id"]))
    counts, out = {k: 0 for k in cells}, []
    for _ in range(budget):
        active = [k for k, choices in cells.items() if counts[k] < len(choices)]
        if not active:
            break
        k = min(active, key=lambda key: ((counts[key] + 1) / weights[key], key))
        out.append(cells[k][counts[k]])
        counts[k] += 1
    return out


def _photo_edges(lum, fg, checkpoint):
    h, w = fg.shape
    y, x = np.mgrid[:h, :w]

    def edge(sigma):
        checkpoint()
        smooth = gaussian_filter(lum, sigma)
        dy, dx = np.gradient(smooth)
        mag = np.hypot(dx, dy)
        ux, uy = dx / (mag + 1e-9), dy / (mag + 1e-9)
        peaks = ((mag >= map_coordinates(mag, [y + uy, x + ux], order=1, mode="nearest")) &
                 (mag >= map_coordinates(mag, [y - uy, x - ux], order=1, mode="nearest")))
        low, high = np.quantile(mag[fg], [.68, .88])
        m = binary_propagation(peaks & (mag > high), mask=peaks & (mag > low),
                               structure=np.ones((3, 3)))
        m[:2] = False
        m[-2:] = False
        m[:, :2] = False
        m[:, -2:] = False
        return m

    fine, coarse = edge(.9), edge(1.8)
    return fine & (distance_transform_edt(~coarse) < 2.5) & binary_dilation(fg, iterations=1)


def _revision_line(q):
    """Read back the study's 0.01 px SVG polyline at its 1.25 px step."""
    p = np.round(np.asarray(q.coords), 2)
    dense = [p[0]]
    for a, b in zip(p[:-1], p[1:]):
        n = max(1, math.ceil(float(np.linalg.norm(b - a)) / 1.25))
        dense.extend(a + (b - a) * (i / n) for i in range(1, n + 1))
    return LineString(dense)


def render_light(evidence, params, checkpoint=lambda: None) -> list[np.ndarray]:
    """Select exact hybrid contours and add sparse, cleared shadow hatching."""
    rgb = np.asarray(evidence.rgb, float)
    fg = np.asarray(evidence.foreground) > .35
    if rgb.ndim != 3 or rgb.shape[:2] != fg.shape or rgb.shape[2] != 3:
        raise ValueError("rgb and foreground source arrays must have matching dimensions")
    h, w = fg.shape
    if not fg.any() or params.contour_budget <= 0:
        return []
    normals = np.asarray(evidence.normals)
    if normals.shape[:2] != (h, w) or normals.ndim != 3 or normals.shape[2] < 2:
        raise ValueError("Light requires source-sized normals")
    lum = rgb @ np.array([.2126, .7152, .0722])
    stable = _photo_edges(lum, fg, checkpoint)
    classic = []
    for i, pts in enumerate(_graph(stable, checkpoint)):
        q = LineString(simplify(samples(pts, .7), .25))
        if q.length < 6:
            continue
        classic.append({"id": f"photo-{i}", "points": list(q.coords), "length": q.length,
                        "confidence": .6, "score": q.length ** .67 * (.22 + .6) ** .5})
    classic = _clip_candidates(classic, fg, checkpoint)
    whole = _clip_candidates(evidence.reference_whole or [], fg, checkpoint)
    tiles = _clip_candidates(evidence.reference_tiles or [], fg, checkpoint)
    pool = _deduplicate(whole + tiles + classic, 1.)
    detail = [LineString(q["points"]) for q in _select(pool, params.contour_budget, fg)]
    if not detail:
        return []
    checkpoint()
    base = gaussian_filter(lum * fg, 24) / np.maximum(gaussian_filter(fg.astype(float), 24), 1e-5)
    field = np.clip(1 - lum / np.maximum(base, .05), 0, 1) * fg
    _, shadow = shapes(field, fg, 2.5, 24, 24, .10, checkpoint=checkpoint)
    stroke = h * .001
    # The study packed contours as two-decimal SVG paths before the Light
    # revision read them back. Retain original selected paths in the output,
    # but use those packed coordinates for the revision's clearance geometry.
    revision_detail = [_revision_line(q) for q in detail]
    protected = unary_union(revision_detail).buffer(stroke * 3)
    # Raster clearance before tracing, then exact vector clearance afterward.
    from PIL import Image, ImageDraw
    ink = Image.new("1", (w, h))
    draw = ImageDraw.Draw(ink)
    for q in revision_detail:
        draw.line(list(q.coords), fill=1, width=1)
    room = (distance_transform_edt(~np.asarray(ink, bool)) > stroke * 3) & (distance_transform_edt(shadow) > 2)
    candidates = []
    for i, q in enumerate(flow_hatch(room, normals, 6., checkpoint)):
        if i % 64 == 0:
            checkpoint()
        curve = LineString(simplify(q, .25))
        candidates.extend(part for part in line_components(curve.difference(protected)) if part.length >= 12)
    cells = {}
    for q in sorted(candidates, key=lambda line: (-line.length, line.bounds)):
        p = q.interpolate(.5, normalized=True)
        key = (int(p.x / w * 3), int(p.y / h * 3))
        cells.setdefault(key, []).append(q)
    selected, counts = [], {key: 0 for key in cells}
    while len(selected) < 60:
        active = [key for key in cells if counts[key] < len(cells[key])]
        if not active:
            break
        key = min(active, key=lambda cell: (counts[cell], -cells[cell][counts[cell]].length, cell))
        selected.append(cells[key][counts[key]])
        counts[key] += 1
    return [np.asarray(q.coords, float) for q in detail + selected]
