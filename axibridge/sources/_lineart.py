"""Lineart v2 engine: numpy/scipy primitives behind the (future) flow-field
generators — edge-tangent-flow direction fields, XDoG/Sobel edge maps,
scan-vectorized tracing, Jobard-Lefer flow-aligned hatching, and a "hand"
wobble pass. This is the first module in the codebase allowed to depend on
numpy/scipy.ndimage (both pinned in ``.venv``); every other source stays
plain-Python so the dependency stays contained here.

Pure functions over numpy arrays, px-space in and out — like
``_pixelgen.ImageSampler``, mm conversion is the caller's job via
``_pixelgen.pixel_doc``. The image convention matches ``_pixelgen.luma_grid``:
``luma`` is a float64 (h, w) array, 0..255, 255 = white. "Darkness" is
``255 - luma`` throughout, and every polyline is ``[(x, y), ...]`` in px,
x right / y down — the same point convention as ``linedraw.py``.

Nothing here is bounded (no ``ge=``/``le=`` — there's no Pydantic model at
this layer); callers own that. Functions must still degrade gracefully on
degenerate input (empty arrays, all-white images, all-False edge maps) —
return empty rather than raise, since a generator built on top of this may
legitimately hand over a blank band or a mask with nothing in it.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import (
    distance_transform_edt,
    gaussian_filter,
    gaussian_filter1d,
)

from ..registry import report_progress

Pt = tuple[float, float]
Line = list[Pt]


def _wrap_half_pi(a: np.ndarray) -> np.ndarray:
    """Fold an angle array into [-pi/2, pi/2) — the direction-field convention
    used throughout this module (angles are mod pi: a line has no "which way"
    along it, only an orientation)."""
    return np.mod(a + np.pi / 2.0, np.pi) - np.pi / 2.0


# -- 1. flow_field ---------------------------------------------------------


def flow_field(luma: np.ndarray, smooth_px: float) -> np.ndarray:
    """Edge-tangent-flow direction field: at every pixel, the direction
    running ALONG local structure (perpendicular to the brightness gradient),
    as an angle in radians, mod pi (an (h, w) array, values in
    [-pi/2, pi/2)).

    Standard ETF construction (Kang/Lee/Chui): build the 2x2 structure
    tensor J = [[gx*gx, gx*gy], [gx*gy, gy*gy]] per pixel from the raw
    gradient, then smooth each of its three independent components with a
    Gaussian (this is what makes it a *flow* field rather than a noisy
    per-pixel gradient — smoothing the tensor lets nearby edges "vote" on a
    consistent direction instead of averaging angles directly, which
    would cancel across a wrap-around discontinuity).

    The eigenvector of the LARGER eigenvalue points along the dominant
    gradient (the edge normal); its angle has the closed form
    ``0.5 * atan2(2*Jxy, Jxx - Jyy)`` (no need to build the matrix and call
    an eigensolver per pixel). The tangent — the direction we want — is that
    angle rotated by pi/2. Flat regions (zero tensor energy, e.g. a
    constant-luma image) have no defined orientation; those pixels are
    pinned to angle 0 rather than left to whatever atan2(0, 0) resolves to.
    """
    if luma.size == 0 or min(luma.shape) < 2:
        return np.zeros_like(luma, dtype=np.float64)
    luma = luma.astype(np.float64, copy=False)
    gy, gx = np.gradient(luma)
    report_progress(0.1, "Structure tensor")
    jxx = gaussian_filter(gx * gx, sigma=smooth_px)
    jxy = gaussian_filter(gx * gy, sigma=smooth_px)
    jyy = gaussian_filter(gy * gy, sigma=smooth_px)
    report_progress(0.4, "Flow direction")
    grad_angle = 0.5 * np.arctan2(2.0 * jxy, jxx - jyy)
    tangent = _wrap_half_pi(grad_angle + np.pi / 2.0)
    energy = jxx + jyy
    tangent = np.where(energy < 1e-9, 0.0, tangent)
    return tangent


# -- 2. edge maps: xdog / sobel_edges ---------------------------------------


def xdog(
    luma: np.ndarray,
    sigma: float,
    k: float = 1.6,
    tau: float = 0.98,
    sharpness: float = 20.0,
    threshold: float = 0.5,
) -> np.ndarray:
    """Extended difference-of-Gaussians edge map (Winnemoeller et al.),
    returning a bool (h, w) ink mask.

    D = gaussian(sigma) - tau * gaussian(k*sigma), normalized to the same
    0..1 scale as ``luma``/255 so ``sharpness`` behaves the same regardless
    of image contrast. The classic XDoG soft-threshold folds D through
    ``1 + tanh(sharpness * D)`` where D < 0 (flat/light regions always land
    on the D >= 0 branch and evaluate to 1, i.e. "definitely not ink" —
    this is what keeps uniform regions clean regardless of their absolute
    brightness). The response is in roughly (0, 1], falling toward 0 at
    strong edges.

    ``threshold`` (0..1) is a cut on that response, inverted so the
    parameter reads the way a caller expects a "threshold" slider to read:
    threshold=0 keeps almost everything below the flat-region ceiling of 1
    (maximally permissive -> most ink), threshold=1 requires the response to
    be pinned near 0 (a very strong edge) -> least ink. Higher threshold is
    therefore always fewer ink pixels, monotonically.
    """
    if luma.size == 0:
        return np.zeros(luma.shape, dtype=bool)
    sigma = max(float(sigma), 1e-3)
    luma = luma.astype(np.float64, copy=False)
    g1 = gaussian_filter(luma, sigma=sigma)
    g2 = gaussian_filter(luma, sigma=sigma * k)
    d = (g1 - tau * g2) / 255.0
    response = np.where(d < 0.0, 1.0 + np.tanh(sharpness * d), 1.0)
    cutoff = 1.0 - float(threshold)
    return response < cutoff


def sobel_edges(luma: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Plain gradient-magnitude edge map, same bool-mask contract as
    ``xdog`` so callers can swap modes without touching downstream code.
    ``threshold`` is a fraction of the map's own peak magnitude — scaling to
    the local max (rather than a fixed constant) is what keeps the knob
    meaningful across wildly different-contrast source images. A perfectly
    flat image (peak magnitude 0) returns an all-False map rather than
    dividing by zero."""
    if luma.size == 0:
        return np.zeros(luma.shape, dtype=bool)
    luma = luma.astype(np.float64, copy=False)
    gy, gx = np.gradient(luma)
    mag = np.hypot(gx, gy)
    peak = mag.max()
    if peak <= 0:
        return np.zeros(luma.shape, dtype=bool)
    return mag > float(threshold) * peak


# -- 3. trace: bool edge map -> polylines -----------------------------------


def _dots(edge_map: np.ndarray, vertical: bool) -> list[list[int]]:
    """Midpoints of True-runs along each scan line — the core of the
    plotterfun/linedraw vectorizer (``linedraw._get_dots``), reimplemented
    over a numpy bool array instead of column-major int lists.

    ``vertical=True`` scans row by row, walking columns, so a run collapses
    to a single x per row — this is the pass that follows edges running
    roughly VERTICALLY (successive rows chain in y). ``vertical=False``
    scans column by column, walking rows, collapsing to a y per column —
    the pass that follows roughly HORIZONTAL edges. Running both (see
    ``trace``) is what "both scan directions" means; each one is blind to
    structure aligned with its own scan axis.
    """
    h, w = edge_map.shape
    outer, inner = (h, w) if vertical else (w, h)
    dots: list[list[int]] = []
    for s in range(outer):
        row: list[int] = []
        i = 0
        while i < inner:
            on = edge_map[s, i] if vertical else edge_map[i, s]
            if on:
                i0 = i
                while i < inner and (edge_map[s, i] if vertical else edge_map[i, s]):
                    i += 1
                row.append((i0 + i - 1) // 2)
            else:
                i += 1
        dots.append(row)
    return dots


def _connect(dots: list[list[int]], vertical: bool, tol: int = 2) -> list[Line]:
    """Chain same-scan-line dots into polylines: each dot links to the
    nearest dot in the previous scan line if within ``tol``, via an
    end-point index (dict lookup) rather than an O(dots x contours) search —
    same trick as ``linedraw._connect_dots``."""
    contours: list[Line] = []
    open_ends: dict[tuple[int, int], int] = {}
    for s, row in enumerate(dots):
        prev = dots[s - 1] if s > 0 else []
        for c in row:
            closest, cdist = None, tol + 1
            for c0 in prev:
                d = abs(c - c0)
                if d < cdist:
                    closest, cdist = c0, d
            pt: Pt = (float(c), float(s)) if vertical else (float(s), float(c))
            idx = open_ends.get((s - 1, closest)) if closest is not None and cdist <= tol else None
            if idx is None:
                contours.append([pt])
                idx = len(contours) - 1
            else:
                contours[idx].append(pt)
            open_ends[(s, c)] = idx
    return contours


def _dedupe_v_against_h(h_lines: list[Line], v_lines: list[Line], w: int, h: int,
                         radius: float = 1.5, coverage: float = 0.6) -> list[Line]:
    """Drop V-scan strokes that mostly retrace an H-scan stroke already
    covering the same edge (both scans see the same edge pixels from
    different axes; without this every roughly-diagonal edge gets drawn
    twice). Not exact — a distance-transform occupancy test against the
    H-scan stroke pixels, "mostly" meaning >= ``coverage`` of the
    candidate's points fall within ``radius`` px of one. Good enough;
    doubled lines are the bug this guards against, not sub-pixel purity."""
    if not h_lines or not v_lines:
        return v_lines
    occ = np.zeros((h, w), dtype=bool)
    for line in h_lines:
        for x, y in line:
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < w and 0 <= yi < h:
                occ[yi, xi] = True
    if not occ.any():
        return v_lines
    dist = distance_transform_edt(~occ)
    kept = []
    for line in v_lines:
        if not line:
            continue
        near = 0
        for x, y in line:
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < w and 0 <= yi < h and dist[yi, xi] <= radius:
                near += 1
        if near / len(line) < coverage:
            kept.append(line)
    return kept


def _unit(dx: float, dy: float) -> tuple[float, float] | None:
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-9 else None


def _fwd_end(pts: Line, k: int = 4) -> tuple[float, float] | None:
    a = pts[max(0, len(pts) - k)]
    b = pts[-1]
    return _unit(b[0] - a[0], b[1] - a[1])


def _fwd_start(pts: Line, k: int = 4) -> tuple[float, float] | None:
    a = pts[0]
    b = pts[min(len(pts) - 1, k - 1)]
    return _unit(b[0] - a[0], b[1] - a[1])


def _angle_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    dot = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))
    return math.degrees(math.acos(dot))


def _join_ends(strokes: list[Line], join_angle_deg: float, tol_px: float = 4.0) -> list[Line]:
    """Merge stroke pairs where one's end sits near the other's end/start AND
    the tangent estimated from the last/first few points agrees within
    ``join_angle_deg`` — a stricter, direction-aware version of linedraw's
    "any two ends within N px" join, needed because the H/V dual scan hands
    back a lot more fragment pairs than linedraw's single-scan case. A
    single greedy pass (mirrors linedraw's own one-shot join loop): each
    stroke's end looks for the closest, angle-compatible open end among the
    others, trying both "as-is" (end -> start) and "reversed" (end -> end,
    flip the other stroke) orientations."""
    strokes = [list(s) for s in strokes if s]
    n = len(strokes)
    used = [False] * n
    for i in range(n):
        if used[i]:
            continue
        di = _fwd_end(strokes[i])
        if di is None:
            continue
        ei = strokes[i][-1]
        best_j, best_rev, best_d = -1, False, tol_px
        for j in range(n):
            if j == i or used[j]:
                continue
            sj = strokes[j][0]
            dj = _fwd_start(strokes[j])
            if dj is not None:
                d = math.hypot(ei[0] - sj[0], ei[1] - sj[1])
                if d <= best_d and _angle_deg(di, dj) <= join_angle_deg:
                    best_j, best_rev, best_d = j, False, d
            ej = strokes[j][-1]
            dje = _fwd_end(strokes[j])
            if dje is not None:
                d = math.hypot(ei[0] - ej[0], ei[1] - ej[1])
                if d <= best_d and _angle_deg(di, (-dje[0], -dje[1])) <= join_angle_deg:
                    best_j, best_rev, best_d = j, True, d
        if best_j >= 0:
            tail = list(reversed(strokes[best_j])) if best_rev else strokes[best_j]
            strokes[i] = strokes[i] + tail
            used[best_j] = True
    return [s for i, s in enumerate(strokes) if not used[i]]


def _smooth_line(pts: Line, smooth: float) -> Line:
    """Moving-average smoothing, endpoints pinned exactly (a smoothed stroke
    that drifts off its traced endpoint reads as wrong, not hand-drawn)."""
    n = len(pts)
    if smooth <= 0.0 or n < 3:
        return pts
    window = max(1, min(int(round(smooth * 5)), (n - 1) // 2))
    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    kernel = np.ones(2 * window + 1) / (2 * window + 1)
    xs_p = np.pad(xs, window, mode="edge")
    ys_p = np.pad(ys, window, mode="edge")
    xs_s = np.convolve(xs_p, kernel, mode="valid")
    ys_s = np.convolve(ys_p, kernel, mode="valid")
    xs_s[0], ys_s[0] = xs[0], ys[0]
    xs_s[-1], ys_s[-1] = xs[-1], ys[-1]
    return list(zip(xs_s.tolist(), ys_s.tolist()))


def _arc_len(pts: Line) -> float:
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
               for i in range(len(pts) - 1))


def trace(
    edge_map: np.ndarray,
    join_angle_deg: float = 50.0,
    min_len_px: float = 6.0,
    smooth: float = 0.5,
) -> list[Line]:
    """Vectorize a bool edge map into polylines, px space (x, y).

    Pipeline: run-midpoint scan in both directions (``_dots``/``_connect``,
    ported from linedraw's H/V dual scan) -> drop V-scan strokes that
    duplicate an H-scan stroke already covering the same pixels
    (``_dedupe_v_against_h``) -> tangent-aware end-joining
    (``_join_ends``) -> per-stroke smoothing -> drop anything shorter than
    ``min_len_px`` of arc length (culls scan noise: single-pixel edge specks
    that survive as 1-3 point stubs).
    """
    if edge_map is None or edge_map.size == 0 or not edge_map.any():
        return []
    h, w = edge_map.shape
    h_lines = [c for c in _connect(_dots(edge_map, vertical=False), False) if len(c) >= 2]
    v_lines = [c for c in _connect(_dots(edge_map, vertical=True), True) if len(c) >= 2]
    report_progress(0.3, "Tracing edges")
    v_lines = _dedupe_v_against_h(h_lines, v_lines, w, h)
    strokes = _join_ends(h_lines + v_lines, join_angle_deg)
    report_progress(0.6, "Joining strokes")
    strokes = [_smooth_line(s, smooth) for s in strokes]
    out = [s for s in strokes if _arc_len(s) >= min_len_px]
    report_progress(0.9, "Tracing edges")
    return out


# -- 4. streamlines: flow-aligned hatching -----------------------------------


class _Occupancy:
    """Sparse spatial hash for "closest existing line point" queries —
    the density control at the heart of Jobard-Lefer placement. Bucketed at
    ``cell`` px (~ half the base spacing, per the algorithm) so a query only
    has to look at a handful of neighbouring buckets instead of every point
    placed so far."""

    def __init__(self, cell: float):
        self.cell = max(cell, 1e-3)
        self.buckets: dict[tuple[int, int], list[Pt]] = {}

    def _key(self, x: float, y: float) -> tuple[int, int]:
        return (int(x // self.cell), int(y // self.cell))

    def near(self, x: float, y: float, radius: float) -> float:
        kx, ky = self._key(x, y)
        r = int(math.ceil(radius / self.cell)) + 1
        best = math.inf
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for px, py in self.buckets.get((kx + dx, ky + dy), ()):
                    d = math.hypot(px - x, py - y)
                    if d < best:
                        best = d
        return best

    def add(self, x: float, y: float) -> None:
        self.buckets.setdefault(self._key(x, y), []).append((x, y))


def _sample(grid: np.ndarray, x: float, y: float) -> float | None:
    """Nearest-pixel (floor) lookup; None outside bounds."""
    hh, ww = grid.shape
    xi, yi = int(math.floor(x)), int(math.floor(y))
    if 0 <= xi < ww and 0 <= yi < hh:
        return float(grid[yi, xi])
    return None


def _integrate(
    sx: float, sy: float, field: np.ndarray | None, norm: np.ndarray,
    band: tuple[float, float], spacing_fn, occ: _Occupancy, max_len_px: float,
    is_flow: bool, fixed_angle: float, w: int, h: int, step: float = 1.0,
) -> Line:
    """Grow one streamline both directions from a seed via RK2 along the
    (possibly undirected, mod-pi) direction field. The mod-pi ambiguity is
    resolved by continuity: each new sample direction is flipped if needed
    so it has positive dot product with the previous step's direction —
    that's what keeps an integrated line from zig-zagging every step even
    though the underlying field can't tell "north" from "south"."""
    lo, hi = band

    def local_spacing(x: float, y: float) -> float:
        v = _sample(norm, x, y)
        if v is None:
            return spacing_fn(1.0)
        t = 0.0 if hi <= lo else max(0.0, min(1.0, (v - lo) / (hi - lo)))
        return spacing_fn(t)

    def grow(sign: float) -> Line:
        pts: Line = []
        x, y = sx, sy
        prev_dir: np.ndarray | None = None
        length = 0.0
        limit = max_len_px / 2.0
        while length < limit:
            if not (0 <= x < w and 0 <= y < h):
                break
            v = _sample(norm, x, y)
            if v is None or not (lo <= v <= hi):
                break
            sp = local_spacing(x, y)
            if occ.near(x, y, sp) < sp:
                break
            pts.append((x, y))
            ang = fixed_angle if not is_flow else _sample(field, x, y)
            if ang is None:
                break
            raw = np.array((math.cos(ang), math.sin(ang)))
            if prev_dir is None:
                vdir = raw * sign
            else:
                vdir = raw if float(raw @ prev_dir) >= 0 else -raw
            mx, my = x + 0.5 * step * vdir[0], y + 0.5 * step * vdir[1]
            ang2 = None
            if 0 <= mx < w and 0 <= my < h:
                ang2 = fixed_angle if not is_flow else _sample(field, mx, my)
            if ang2 is None:
                vdir2 = vdir
            else:
                raw2 = np.array((math.cos(ang2), math.sin(ang2)))
                vdir2 = raw2 if float(raw2 @ vdir) >= 0 else -raw2
            nx, ny = x + step * vdir2[0], y + step * vdir2[1]
            length += math.hypot(nx - x, ny - y)
            norm_v = np.linalg.norm(vdir2)
            prev_dir = vdir2 / norm_v if norm_v > 1e-12 else vdir2
            x, y = nx, ny
        return pts

    fwd = grow(1.0)
    bwd = grow(-1.0)
    if bwd:
        bwd = bwd[1:]
    return list(reversed(bwd)) + fwd


def _grow_pass(
    norm: np.ndarray, field: np.ndarray | None, band: tuple[float, float],
    spacing_px: float, spacing_fn, max_len_px: float, rng: np.random.Generator,
    occ: _Occupancy, is_flow: bool, fixed_angle: float, w: int, h: int,
) -> list[Line]:
    """Jittered-grid candidate seeding + sequential growth. Seeds are visited
    in fixed (row-major grid) order so the whole pass is deterministic given
    ``rng``; each accepted line is stamped into ``occ`` immediately so later
    seeds in the same pass see it (this is what enforces the spacing, not
    just the check inside ``_integrate``)."""
    lo, hi = band
    grid = max(spacing_px, 1.0)
    lines: list[Line] = []
    y = 0.0
    while y < h:
        x = 0.0
        while x < w:
            jx = float(x + rng.uniform(-grid / 2.0, grid / 2.0))
            jy = float(y + rng.uniform(-grid / 2.0, grid / 2.0))
            v = _sample(norm, jx, jy)
            if v is not None and lo <= v <= hi:
                t = 0.0 if hi <= lo else max(0.0, min(1.0, (v - lo) / (hi - lo)))
                sp = spacing_fn(t)
                if occ.near(jx, jy, sp) >= sp:
                    line = _integrate(jx, jy, field, norm, band, spacing_fn, occ,
                                       max_len_px, is_flow, fixed_angle, w, h)
                    if len(line) >= 2:
                        lines.append(line)
                        for px, py in line:
                            occ.add(px, py)
            x += grid
        y += grid
    return lines


def _dash_line(pts: Line, dash: float, rng: np.random.Generator) -> list[Line]:
    """Probabilistically break one polyline into dash segments. Segment
    length is drawn uniformly up to a ``dash``-scaled ceiling (higher dash ->
    lower ceiling -> shorter segments); the gap between segments scales the
    same way. Segments under 3 points are dropped rather than emitted."""
    n = len(pts)
    min_seg = 3
    if dash <= 0.0 or n < 2 * min_seg:
        return [pts]
    segments: list[Line] = []
    i = 0
    max_seg = max(min_seg, int(round(n * (1.0 - dash))))
    while i < n:
        seg_len = int(rng.integers(min_seg, max_seg + 1)) if max_seg > min_seg else min_seg
        j = min(n, i + seg_len)
        if j - i >= min_seg:
            segments.append(pts[i:j])
        gap = int(rng.integers(1, max(2, int(round(seg_len * dash)) + 2)))
        i = j + gap
    return segments if segments else [pts]


def streamlines(
    darkness: np.ndarray,
    field: np.ndarray,
    band: tuple[float, float],
    spacing_px: float,
    max_len_px: float,
    seed: int,
    direction: str = "flow",
    angle_deg: float = 45.0,
    cross_hatch: bool = False,
    dash: float = 0.0,
) -> list[Line]:
    """Flow-aligned hatching for one tonal band (Jobard-Lefer placement):
    jittered candidate seeds where ``darkness/255`` falls in ``band``, each
    grown into a streamline both directions along ``field`` (or a constant
    ``angle_deg`` if ``direction="fixed"``, in which case ``field`` is
    ignored) with RK2 integration at ~1 px steps. A line stops at the image
    edge, on leaving the band, at ``max_len_px``, or on nearing another
    already-placed line closer than the LOCAL allowed spacing — which itself
    shrinks from ``spacing_px`` at the lightest darkness in the band to
    ``spacing_px / 2.5`` at the darkest, so denser bands self-densify rather
    than using one flat spacing for the whole band.

    ``cross_hatch=True`` runs a second independent pass along the
    perpendicular field (its own occupancy grid, so the two populations
    don't block each other and can actually cross). ``dash`` (0..1)
    post-processes every line into shorter dashed segments — 0 leaves lines
    solid.

    Deterministic per ``seed``: one ``np.random.default_rng(seed)`` drives
    seed jitter and dashing, consumed in a fixed grid-scan order.
    """
    if darkness.size == 0:
        return []
    h, w = darkness.shape
    lo, hi = float(min(band)), float(max(band))
    lo, hi = max(0.0, min(1.0, lo)), max(0.0, min(1.0, hi))
    norm = darkness.astype(np.float64, copy=False) / 255.0
    spacing_px = max(float(spacing_px), 0.5)

    def spacing_fn(t: float) -> float:
        return spacing_px * (1.0 - t) + (spacing_px / 2.5) * t

    rng = np.random.default_rng(seed)
    is_flow = direction != "fixed"
    fixed_angle = math.radians(angle_deg)
    if is_flow and (field is None or field.size == 0):
        return []

    occ = _Occupancy(cell=max(spacing_px / 2.0, 1.0))
    lines = _grow_pass(norm, field, (lo, hi), spacing_px, spacing_fn, max_len_px,
                        rng, occ, is_flow, fixed_angle, w, h)
    report_progress(0.6 if cross_hatch else 0.9, "Streamlines")

    if cross_hatch:
        occ2 = _Occupancy(cell=max(spacing_px / 2.0, 1.0))
        if is_flow:
            perp_field = _wrap_half_pi(field + math.pi / 2.0)
            lines += _grow_pass(norm, perp_field, (lo, hi), spacing_px, spacing_fn,
                                 max_len_px, rng, occ2, True, fixed_angle, w, h)
        else:
            lines += _grow_pass(norm, None, (lo, hi), spacing_px, spacing_fn,
                                 max_len_px, rng, occ2, False,
                                 fixed_angle + math.pi / 2.0, w, h)
        report_progress(0.9, "Streamlines")

    if dash > 0.0:
        dashed: list[Line] = []
        for ln in lines:
            dashed += _dash_line(ln, dash, rng)
        lines = dashed
    report_progress(1.0, "Streamlines")
    return lines


# -- 5. hand: carefulness wobble ---------------------------------------------


def hand(
    lines: list[Line],
    edge_map: np.ndarray | None,
    tight: float,
    loose: float,
    wobble_scale: float,
    seed: int,
) -> list[Line]:
    """Displace every line with coherent low-frequency "hand" wobble — the
    amplitude at each point interpolates from ``tight`` px right on an edge
    to ``loose`` px by about 30 px away from one (``distance_transform_edt``
    over ``~edge_map`` gives that per-pixel distance in one shot). The idea:
    a careful hand draws tight, controlled strokes near a contour it's
    tracking and loosens up in open space — the opposite of a fixed jitter
    amplitude, which reads as noise rather than a drawing style.

    The displacement itself is white noise, Gaussian-smoothed along each
    line's point sequence and rescaled to unit peak before the per-point
    amplitude is applied — smoothing (rather than raw per-point noise) is
    what makes neighbouring points move together instead of buzzing
    independently. ``wobble_scale`` scales the whole effect; 0 returns
    copies of the input unchanged. Deterministic per ``seed``: one RNG
    drives every line in order.
    """
    if wobble_scale == 0:
        return [list(line) for line in lines]
    if not lines:
        return []
    dist = None
    if edge_map is not None and edge_map.size:
        dist = distance_transform_edt(~edge_map)
    rng = np.random.default_rng(seed)
    out: list[Line] = []
    for line in lines:
        n = len(line)
        if n < 2:
            out.append(list(line))
            continue
        xs = np.array([p[0] for p in line])
        ys = np.array([p[1] for p in line])
        if dist is not None:
            hh, ww = dist.shape
            amp = np.empty(n)
            for i in range(n):
                xi = min(max(int(round(xs[i])), 0), ww - 1)
                yi = min(max(int(round(ys[i])), 0), hh - 1)
                t = min(dist[yi, xi] / 30.0, 1.0)
                amp[i] = tight + (loose - tight) * t
        else:
            amp = np.full(n, loose)
        amp = amp * wobble_scale
        sigma = max(n / 8.0, 2.0)
        noise_x = gaussian_filter1d(rng.standard_normal(n), sigma=sigma)
        noise_y = gaussian_filter1d(rng.standard_normal(n), sigma=sigma)

        def _peak_norm(a: np.ndarray) -> np.ndarray:
            m = np.abs(a).max()
            return a / m if m > 1e-9 else a

        noise_x, noise_y = _peak_norm(noise_x), _peak_norm(noise_y)
        nx = xs + noise_x * amp
        ny = ys + noise_y * amp
        out.append(list(zip(nx.tolist(), ny.tolist())))
    return out
