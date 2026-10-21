# FROZEN from research commit 6f96418: tools/gesture/gesture/kit/devices_measg1.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Three geometric readings, in sheet mm, for the measuring-device layer.

No randomness or placement decisions live here. Density is the Gaussian-smoothed
raster coverage of the original ink (including its pen widths); headings measure
mark centrelines, with opposite directions identified. Text is stroke geometry.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d, map_coordinates

from ._devices import device
from .core import Ink, KitError, P
from .voices_machine_diagram import text, text_width

_PEN = P("pen", "float", 0.2, "device pen width, mm", min=0.15, max=0.3)
_RULER = [P("anchor", "choice", "drawing", "measure the drawing extent or the region",
            choices=("drawing", "region")),
          P("label_h", "float", 1.5, "stroke label cap height, mm", min=0.8, max=3.5), _PEN]
_DENSITY = [P("cell", "float", 1.5, "raster grid cell size, mm", min=1.0, max=2.0),
            P("sigma", "float", 3.0, "Gaussian blur sigma in drawing mm", min=0.5, max=12.0),
            P("levels", "int", 3, "contours at evenly spaced 20–80% of peak density", min=2, max=4),
            P("min_length", "float", 8.0, "minimum plotted contour length, mm", min=1.0, max=100.0),
            P("pen", "float", 0.18, "device pen width, mm", min=0.15, max=0.3)]
_ROSE = [P("bins", "int", 36, "axial heading bins over 180 degrees", min=8, max=180),
         P("smooth", "float", 1.0, "periodic Gaussian sigma in bins (0 = no blur)", min=0.0, max=4.0),
         _PEN]


def _check(params, values):
    """Also validate direct calls and NaN/choices, which the device adapter omits."""
    for p in params:
        v = values[p.name]
        if p.type == "choice":
            if v not in p.choices:
                raise KitError(f"{p.name} must be one of {p.choices}")
        else:
            try:
                n = float(v)
            except (TypeError, ValueError, OverflowError) as e:
                raise KitError(f"{p.name} must be a finite number") from e
            if (not math.isfinite(n) or n < p.min or n > p.max
                    or (p.type == "int" and n != int(n))):
                raise KitError(f"{p.name} outside [{p.min}, {p.max}]")


def _ink(points, pen, role, **meta):
    pts = np.asarray(points, dtype=float)
    return Ink(pts, closed=len(pts) > 2 and np.array_equal(pts[0], pts[-1]),
               filled=False, pen=pen, meta={"role": role, **meta})


@device("scale_ruler", params=_RULER, family="general",
        doc="True-mm ruler, measuring the drawing's projected extent or the region's long edge.")
def scale_ruler(dctx, sheet, *, anchor="drawing", label_h=1.5, pen=0.2):
    _check(_RULER, locals())
    x0, y0, w, h = dctx.region
    if min(w, h) <= 0:
        return []
    horizontal = w >= h
    axis = 0 if horizontal else 1
    start, available, cross = (x0, w, h) if horizontal else (y0, h, w)
    length = available
    if anchor == "drawing":
        length = dctx.drawing_box[axis + 2]
        if length > available + 1e-9:
            raise KitError("scale_ruler: drawing extent does not fit region at true millimetre scale")
        # Project onto a margin when possible. A detached panel can translate
        # the same physical extent, but never shrink it to suggest a false size.
        projected = dctx.drawing_box[axis]
        start = (projected if start - 1e-9 <= projected <= start + available - length + 1e-9
                 else start + (available - length) / 2)
    if length <= 1e-9:
        return []
    baseline = min(1.0, 0.08 * cross)
    tick = min(3.0, 0.28 * cross)

    def xy(u, v):
        return np.column_stack([start + np.asarray(u), y0 + np.asarray(v)]) if horizontal else np.column_stack(
            [x0 + np.asarray(v), start + np.asarray(u)])

    info = {"extent_mm": float(length), "axis": "x" if horizontal else "y", "anchor": anchor}
    out = [_ink(xy([0, length], [baseline, baseline]), pen, "baseline", **info)]
    for i in range(int(math.floor(length + 1e-9)) + 1):
        t = tick if i % 10 == 0 else tick * (0.65 if i % 5 == 0 else 0.35)
        out.append(_ink(xy([i, i], [baseline, baseline + t]), pen, "tick", value_mm=i))
    if not math.isclose(length, round(length), abs_tol=1e-9):
        out.append(_ink(xy([length, length], [baseline, baseline + tick]), pen, "end_tick", **info))
    cap = min(label_h, cross * 0.12)
    num_v = baseline + tick + min(0.8, cross * 0.06)
    spacing = 10 if length < 200 else 50

    def label(s, u, v, role):
        tw = text_width(s, cap)
        if tw > length or v + cap > cross:
            return
        left = max(0.0, min(u - tw / 2, length - tw))
        for p in text(s, left, v, cap):
            out.append(_ink(xy(p[:, 0], p[:, 1]), pen, role, **info))

    for i in range(0, int(math.floor(length)) + 1, spacing):
        label(str(i), i, num_v, "number")
    # The fractional endpoint is worth stating: the ten-mm ticks alone cannot
    # report a drawing that ends at, for example, 173.42 mm.
    label(f"{length:.2f} MM", length / 2, num_v + 2 * cap + 0.8, "extent")
    return out


def _density_grid(sheet, box, cell, sigma):
    """Raster coverage at grid nodes; spacing <= cell, blur in physical mm.

    Eight samples across a cell preserve thin source ink before averaging.
    A padded raster retains the ink and blur just outside the drawing box;
    only nodes inside that box are returned. This is a coverage measurement,
    so a retraced line does not become darker merely through extra vertices.
    """
    from PIL import Image, ImageDraw

    x0, y0, w, h = box
    nx, ny = max(2, math.ceil(w / cell) + 1), max(2, math.ceil(h / cell) + 1)
    xs, ys = np.linspace(x0, x0 + w, nx), np.linspace(y0, y0 + h, ny)
    if min(w, h) <= 0:
        return xs, ys, np.zeros((ny, nx), dtype=float)
    live = [k for k in sheet.inks if (k.meta or {}).get("layer") != "device" and len(k.points) >= 2]
    max_pen = max((float(k.pen) for k in live), default=0.0)
    # Rasterise on square physical cells, then sample at the requested box
    # nodes. This also keeps a nearly flat box from allocating millions of
    # padding columns or rows merely because its last interval is tiny.
    pad = math.ceil((4 * sigma + max_pen) / cell) + 1
    ss = 8
    image = Image.new("L", ((nx + 2 * pad) * ss, (ny + 2 * pad) * ss), 0)
    draw = ImageDraw.Draw(image)
    origin = np.array([x0, y0]) - (pad + 0.5) * cell
    px_scale = ss / cell
    for ink in live:
        pts = ink.points
        if not np.all(np.isfinite(pts)):
            continue
        if ink.closed and not np.array_equal(pts[0], pts[-1]):
            pts = np.vstack([pts, pts[0]])
        q = (pts - origin) * px_scale
        width = max(1, int(round(ink.pen * px_scale)))
        draw.line([tuple(p) for p in q], fill=255, width=width, joint="curve")
        # Round caps, like the kit preview. These are only the measuring
        # raster; the device's own output is entirely unfilled polylines.
        r = width / 2
        for p in (q[0], q[-1]):
            draw.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=255)
    coarse = image.resize((nx + 2 * pad, ny + 2 * pad), Image.Resampling.BOX)
    field = gaussian_filter(np.asarray(coarse, dtype=float) / 255.0,
                            sigma / cell, mode="constant")
    xx, yy = np.meshgrid(pad + (xs - x0) / cell, pad + (ys - y0) / cell)
    return xs, ys, map_coordinates(field, [yy, xx], order=1, mode="nearest")


def _marching_polylines(xs, ys, field, level):
    """Marching squares joined by shared grid-edge keys, without rounding.

    The bilinear asymptotic decider resolves saddle cells consistently. Open
    chains are walked first, then closed loops, in stable row/column order.
    """
    vertices, edges = {}, []
    rows, cols = field.shape
    for j in range(rows - 1):
        for i in range(cols - 1):
            corners = ((j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i))
            v = [float(field[r, c]) for r, c in corners]
            if not all(math.isfinite(a) for a in v):
                continue
            high = [a > level for a in v]
            if all(high) or not any(high):
                continue
            hits = {}
            # Always interpolate each shared edge in the same direction.
            pairs = ((0, 1, ("h", j, i)), (1, 2, ("v", j, i + 1)),
                     (3, 2, ("h", j + 1, i)), (0, 3, ("v", j, i)))
            for e, (a, b, key) in enumerate(pairs):
                if high[a] == high[b]:
                    continue
                t = (level - v[a]) / (v[b] - v[a])
                r0, c0 = corners[a]
                r1, c1 = corners[b]
                if t == 0:
                    key = ("p", r0, c0)
                elif t == 1:
                    key = ("p", r1, c1)
                vertices[key] = np.array([xs[c0] + t * (xs[c1] - xs[c0]),
                                          ys[r0] + t * (ys[r1] - ys[r0])])
                hits[e] = key
            if len(hits) == 2:
                a, b = hits.values()
                if a != b:
                    edges.append((a, b))
            elif len(hits) == 4:
                q = (v[0] - level) * (v[2] - level) - (v[1] - level) * (v[3] - level)
                for a, b in (((0, 1), (2, 3)) if q >= 0 else ((0, 3), (1, 2))):
                    if hits[a] != hits[b]:
                        edges.append((hits[a], hits[b]))
    adjacent = {}
    for e, (a, b) in enumerate(edges):
        adjacent.setdefault(a, []).append(e)
        adjacent.setdefault(b, []).append(e)
    used = np.zeros(len(edges), dtype=bool)
    out = []

    def walk(start, edge):
        chain, node = [vertices[start]], start
        while not used[edge]:
            used[edge] = True
            a, b = edges[edge]
            node = b if node == a else a
            chain.append(vertices[node])
            if node == start or len(adjacent[node]) != 2:
                break
            nxt = [e for e in adjacent[node] if not used[e]]
            if not nxt:
                break
            edge = nxt[0]
        p = np.array(chain)
        # Exact-level vertices can coincide; retain only actual moves.
        p = p[np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-12]]
        if len(p) >= 2:
            out.append(p)

    for node, incident in adjacent.items():
        if len(incident) != 2:
            for e in incident:
                if not used[e]:
                    walk(node, e)
    for e, (a, _) in enumerate(edges):
        if not used[e]:
            walk(a, e)
    return out


@device("density_isoline", params=_DENSITY, family="general",
        doc="Contours at 20–80% of peak blurred ink coverage; sigma in drawing mm, length filter in plotted mm.")
def density_isoline(dctx, sheet, *, cell=1.5, sigma=3.0, levels=3, min_length=8.0, pen=0.18):
    _check(_DENSITY, locals())
    x0, y0, w, h = dctx.region
    bx, by, bw, bh = dctx.drawing_box
    if min(w, h, bw, bh) <= 0:
        return []
    xs, ys, field = _density_grid(sheet, dctx.drawing_box, cell, sigma)
    peak = float(field.max())
    if peak <= 0:
        return []
    if dctx.place in ("over", "under"):
        scale, offset = 1.0, np.zeros(2)
    else:
        scale = min(w / bw, h / bh)
        offset = np.array([x0 + w / 2, y0 + h / 2]) - scale * np.array([bx + bw / 2, by + bh / 2])
    out = []
    for fraction in np.linspace(0.2, 0.8, int(levels)):
        level = float(fraction * peak)
        for path in _marching_polylines(xs, ys, field, level):
            p = path * scale + offset
            length = float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())
            if length + 1e-9 >= min_length:
                out.append(_ink(p, pen, "isoline", level=level, peak_fraction=float(fraction),
                                sigma_mm=sigma, length_mm=length, map_scale=scale))
    return out


@device("heading_rose", params=_ROSE, family="general",
        doc="Length-weighted axial mark headings; radius/outer-circle radius = share of the peak bin.")
def heading_rose(dctx, sheet, *, bins=36, smooth=1.0, pen=0.2):
    _check(_ROSE, locals())
    bins = int(bins)
    hist = np.zeros(bins)
    for mark in sheet.marks:
        delta = np.diff(mark.points, axis=0)
        length = np.linalg.norm(delta, axis=1)
        live = length > 1e-12
        if not np.any(live):
            continue
        theta = np.mod(np.arctan2(delta[live, 1], delta[live, 0]), np.pi)
        # Linear deposit into bins centred on k*pi/bins avoids a seam at 0.
        u = theta * bins / np.pi
        lo = np.floor(u).astype(int)
        f = u - lo
        np.add.at(hist, lo % bins, length[live] * (1 - f))
        np.add.at(hist, (lo + 1) % bins, length[live] * f)
    if hist.sum() <= 0:
        return []
    if smooth > 0:
        hist = gaussian_filter1d(hist, smooth, mode="wrap")
    x0, y0, w, h = dctx.region
    if min(w, h) <= 0:
        return []
    centre = np.array([x0 + w / 2, y0 + h / 2])
    radius = min(w, h) * 0.43
    # Densely sample the linear polar interpolation, avoiding long chords
    # across a narrow lobe; both halves represent the same axial histogram.
    n = max(360, bins * 8)
    angles = np.linspace(0, 2 * np.pi, n + 1)
    u = np.mod(angles, np.pi) * bins / np.pi
    values = np.interp(u, np.arange(bins + 1), np.r_[hist, hist[0]])
    directions = np.column_stack([np.cos(angles), np.sin(angles)])
    rose = centre + directions * (radius * values / hist.max())[:, None]
    rose[-1] = rose[0]
    circle = centre + radius * directions
    circle[-1] = circle[0]
    out = [_ink(rose, pen, "heading", bins=bins, smooth_bins=smooth,
                axial_period_rad=math.pi, total_length_mm=float(sum(m.length() for m in sheet.marks)),
                radial_scale="share_of_peak", histogram_mm=hist.tolist()),
           _ink(circle, pen, "reference", peak_bin_mm=float(hist.max()))]
    for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
        d = np.array([math.cos(a), math.sin(a)])
        out.append(_ink(centre + np.array([radius, radius * 1.09])[:, None] * d, pen, "tick"))
    return out
