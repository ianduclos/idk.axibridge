# FROZEN from research commit c712045: tools/gesture/gesture/kit/devices_measg2.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Three geometric readings of finished ink; all distances are sheet mm.

Device layers never measure themselves. Closed paths include their closing
segment once. Arc distances and the survey's continuous line moments are exact
on the plotted polylines. The grid integrates Gaussian density by midpoint
quadrature (at most 1 mm per sample); its clearance uses exact line capsules.
Positive grid strength attracts, negative strength repels. No random stream is
needed. Placement is entirely supplied by the device context.
"""
from __future__ import annotations

import math

import numpy as np

from ._devices import device
from .core import Ink, KitError, P, arclength
from .voices_machine_diagram import text, text_width


ARC_PARAMS = (
    P("which", "choice", "longest", "Which ink polylines to read", choices=("longest", "all_over")),
    P("min_length", "float", 20.0, "Minimum line length for all_over, mm", min=0, max=10000),
    P("every", "float", 12.0, "Arc distance between ticks, mm", min=1, max=100),
    P("major_every", "int", 5, "Number of ticks between numbered long ticks", min=1, max=20),
    P("tick", "float", 1.2, "Minor tick length, mm; major ticks are twice as long", min=0.3, max=4),
    P("offset", "float", 0.7, "Minimum gap from line to tick, mm; the clear side is preferred", min=0.2, max=5),
    P("label_h", "float", 1.7, "Stroke numeral height, mm", min=0.8, max=4),
    P("pen", "float", 0.18, "Pen width, mm", min=0.15, max=0.3),
)
SURVEY_PARAMS = (
    P("cross", "float", 2.0, "Crosshair half-span, mm", min=0.8, max=6),
    P("label_h", "float", 1.6, "Coordinate lettering height, mm", min=0.8, max=4),
    P("principal_axis", "bool", False, "Show the continuous length-weighted principal axis"),
    P("dash", "float", 3.0, "Axis dash length, mm", min=1, max=8),
    P("gap", "float", 2.0, "Gap between axis dashes, mm", min=0.5, max=8),
    P("pen", "float", 0.18, "Pen width, mm", min=0.15, max=0.3),
)
GRID_PARAMS = (
    P("pitch", "float", 12.0, "Undeformed grid spacing, mm (never below 6)", min=6, max=60),
    P("blur", "float", 8.0, "Gaussian ink-density blur sigma, mm", min=2, max=30),
    P("strength", "float", 4.0, "Displacement bound, mm: positive toward ink, negative away", min=-12, max=12),
    P("clear", "float", 1.0, "Centreline clearance from ink, mm; 0 leaves lines unbroken", min=0, max=6),
    P("min_stub", "float", 2.0, "Drop grid fragments shorter than this, mm", min=0.5, max=12),
    P("pen", "float", 0.15, "Pen width, mm", min=0.15, max=0.3),
)


def _validate(params, values):
    # apply_devices bounds numeric params, but also validate direct calls,
    # choices, booleans and NaN (comparisons alone do not reject NaN).
    for p in params:
        v = values[p.name]
        if p.type in ("float", "int") and not math.isfinite(float(v)):
            raise KitError(f"{p.name} must be finite")
        p.validate(v)


def _lines(sheet):
    out = []
    for index, ink in enumerate(sheet.inks):
        if ink.meta.get("layer") == "device":
            continue
        p = ink.points
        if len(p) < 2 or not np.isfinite(p).all():
            continue
        if ink.closed and not np.array_equal(p[0], p[-1]):
            p = np.vstack([p, p[0]])
        p = p[np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-12]]
        s = arclength(p)
        if len(p) > 1:
            out.append((index, p, s))
    return out


def _view(dctx, points):
    """The supplied region's view of source geometry; no placement choice.

    Over/under have region == drawing_box, hence preserve sheet coordinates.
    A different region gets a uniformly fitted view. Labels still report
    original sheet coordinates and original arc lengths, not view distances.
    """
    if tuple(dctx.region) == tuple(dctx.drawing_box):
        return np.asarray(points)
    x, y, w, h = dctx.region
    bx, by, bw, bh = dctx.drawing_box
    scales = [a / b for a, b in ((w, bw), (h, bh)) if b > 1e-12]
    scale = min(scales) if scales else 1.0
    return ((np.asarray(points) - [bx + bw / 2, by + bh / 2]) * scale
            + [x + w / 2, y + h / 2])


def _ink(points, pen, role, **meta):
    return Ink(points, pen=pen, meta={"role": role, **meta})


def _tick_site(at, normal, length, offset, tick, a, b, clearance):
    # At a sharp corner the incoming normal can lie ON the outgoing segment.
    # Prefer the nominal side, then the opposite one. If both are crowded,
    # find the nearest full tick-length gap within two minor ticks of offset.
    reach = offset + length + 2 * tick
    candidates = []
    for side in (1, -1):
        direction = side * normal
        start, end = at + offset * direction, at + reach * direction
        previous = 0.0
        for lo, hi in [*_blocked_intervals(start, end, a, b, clearance), (1.0, 1.0)]:
            if (lo - previous) * (reach - offset) >= length - 1e-9:
                gap = offset + previous * (reach - offset) + 1e-8
                candidates.append((gap, side, direction))
                break
            previous = hi
    if not candidates:
        return None  # no local tick is preferable to drawing a tick on ink
    gap, side, direction = min(candidates, key=lambda c: (c[0], -c[1]))
    return at + gap * direction, at + (gap + length) * direction, direction, gap


@device("arc_ticks", params=ARC_PARAMS, family="general",
        doc="Perpendicular offset ticks measure cumulative plotted arc length per ink line; crowded sites with no nearby clear interval are omitted.")
def arc_ticks(dctx, sheet, *, which="longest", min_length=20.0, every=12.0,
              major_every=5, tick=1.2, offset=0.7, label_h=1.7, pen=0.18):
    _validate(ARC_PARAMS, locals())
    lines = _lines(sheet)
    if not lines:
        return []
    chosen = ([max(lines, key=lambda line: line[2][-1])] if which == "longest" else
              [line for line in lines if line[2][-1] >= min_length])
    viewed = [(i, _view(dctx, p), s) for i, p, s in lines]
    a, b, _ = _segments(viewed)
    clearance = (pen + max(sheet.inks[i].pen for i, _, _ in lines)) / 2 + 0.02
    out = []
    for index, p, s in chosen:
        q = _view(dctx, p)
        for nth in range(1, int(math.floor((s[-1] + 1e-9) / every)) + 1):
            distance = min(nth * every, float(s[-1]))
            j = min(int(np.searchsorted(s, distance, side="left")), len(s) - 1)
            j = max(j, 1)
            f = (distance - s[j - 1]) / (s[j] - s[j - 1])
            at = q[j - 1] + f * (q[j] - q[j - 1])
            tangent = q[j] - q[j - 1]
            tangent /= max(float(np.linalg.norm(tangent)), 1e-12)
            normal = np.array([-tangent[1], tangent[0]])
            major = nth % major_every == 0
            length = tick * (2 if major else 1)
            site = _tick_site(at, normal, length, offset, tick, a, b, clearance)
            if site is None:
                continue
            start, end, normal, actual_offset = site
            provenance = {"source_ink": index, "arc_mm": distance,
                          "source_length": float(s[-1])}
            out.append(_ink([start, end], pen, "tick", major=major,
                            offset_mm=actual_offset, **provenance))
            if major:
                label = f"{distance:g}"
                centre = end + (0.8 + label_h / 2) * normal
                for stroke in text(label, centre[0], centre[1] - label_h / 2,
                                   label_h, anchor="centre"):
                    out.append(_ink(stroke, pen, "arc_label", text=label, **provenance))
    return out


def _segments(lines):
    a = np.concatenate([p[:-1] for _, p, _ in lines])
    b = np.concatenate([p[1:] for _, p, _ in lines])
    return a, b, np.linalg.norm(b - a, axis=1)


def _moments(a, b, lengths):
    """Exact first and second moments of uniformly inked line segments."""
    mid = (a + b) / 2
    centre = np.sum(mid * lengths[:, None], axis=0) / lengths.sum()
    delta = b - a
    centred = mid - centre
    covariance = (np.einsum("n,ni,nj->ij", lengths, centred, centred)
                  + np.einsum("n,ni,nj->ij", lengths / 12, delta, delta)) / lengths.sum()
    return centre, covariance


def _axis_limits(centre, direction, region):
    x, y, w, h = region
    low, high = -math.inf, math.inf
    for c, v, lo, hi in zip(centre, direction, (x, y), (x + w, y + h)):
        if abs(v) < 1e-12:
            if c < lo - 1e-9 or c > hi + 1e-9:
                return None
        else:
            ta, tb = sorted(((lo - c) / v, (hi - c) / v))
            low, high = max(low, ta), min(high, tb)
    return (low, high) if high > low else None


@device("survey_marks", params=SURVEY_PARAMS, family="general",
        doc="Drawing bounds and exact length-weighted ink centroid, with sheet-origin coordinates and optional principal axis.")
def survey_marks(dctx, sheet, *, cross=2.0, label_h=1.6, principal_axis=False,
                 dash=3.0, gap=2.0, pen=0.18):
    _validate(SURVEY_PARAMS, locals())
    lines = _lines(sheet)
    if not lines:
        return []
    a, b, lengths = _segments(lines)
    centre, covariance = _moments(a, b, lengths)
    x, y, w, h = dctx.drawing_box
    sites = [(np.array([x, y]), "corner_cross"), (np.array([x + w, y]), "corner_cross"),
             (np.array([x, y + h]), "corner_cross"), (np.array([x + w, y + h]), "corner_cross"),
             (centre, "centroid_cross")]
    out = []
    for source, role in sites:
        pos = _view(dctx, source)
        for vector in (np.array([cross, 0]), np.array([0, cross])):
            out.append(_ink([pos - vector, pos + vector], pen, role,
                            coordinate_mm=source.tolist()))
        if role == "centroid_cross":
            t = np.linspace(0, 2 * math.pi, 49)
            ring = pos + cross * 0.85 * np.column_stack([np.cos(t), np.sin(t)])
            ring[-1] = ring[0]
            out.append(Ink(ring, closed=True, pen=pen,
                           meta={"role": "centroid_ring", "coordinate_mm": source.tolist()}))
        label = f"X{source[0]:.1f} Y{source[1]:.1f}"
        # Put lettering outside corner crosses; keep it within the sheet when
        # possible. The measured location itself is never nudged for legibility.
        label_x = pos[0] + cross + 0.8
        label_y = pos[1] - cross - label_h - 0.8
        if label_x + text_width(label, label_h) > dctx.frame[0] - 1:
            label_x = pos[0] - cross - 0.8 - text_width(label, label_h)
        if label_y < 1:
            label_y = pos[1] + cross + 0.8
        for stroke in text(label, label_x, label_y, label_h):
            out.append(_ink(stroke, pen, "coordinate_label", text=label,
                            coordinate_mm=source.tolist()))
    if principal_axis:
        values, vectors = np.linalg.eigh(covariance)
        # Isotropic ink has no distinguished principal axis: do not invent one.
        if values[-1] - values[0] > 1e-10 * max(1.0, values[-1]):
            direction = vectors[:, -1]
            if direction[int(np.argmax(np.abs(direction)))] < 0:
                direction = -direction
            pos = _view(dctx, centre)
            limits = _axis_limits(pos, direction, dctx.region)
            if limits is not None:
                lo, hi = limits
                period = dash + gap
                for i in range(math.floor((lo - dash / 2) / period),
                               math.ceil((hi + dash / 2) / period) + 1):
                    ta, tb = max(lo, i * period - dash / 2), min(hi, i * period + dash / 2)
                    if tb - ta > 1e-9:
                        out.append(_ink([pos + ta * direction, pos + tb * direction], pen,
                                        "principal_axis", centroid_mm=centre.tolist()))
    return out


def _density_samples(a, b, lengths, step):
    points, weights = [], []
    for start, end, length in zip(a, b, lengths):
        n = max(1, math.ceil(float(length) / step))
        t = (np.arange(n) + 0.5) / n
        points.append(start + t[:, None] * (end - start))
        weights.append(np.full(n, length / n))
    return np.concatenate(points), np.concatenate(weights)


def _displace(points, samples, weights, blur, strength, pitch):
    out = points.copy()
    if strength == 0:
        return out
    # rho = sum(dl * Gaussian)/(sqrt(2*pi)*sigma). Thus an isolated
    # infinite straight line has peak density one. blur*grad(rho) is
    # dimensionless. Saturation bounds the displacement without discarding
    # the field's direction or introducing an attraction unrelated to ink.
    amplitude = math.copysign(min(abs(strength), pitch * 0.45), strength)
    for start in range(0, len(points), 128):
        block = points[start:start + 128]
        delta = samples[None, :, :] - block[:, None, :]
        kernel = np.exp(-np.sum(delta * delta, axis=2) / (2 * blur * blur)) * weights
        gradient = np.einsum("nm,nmk->nk", kernel, delta) / (math.sqrt(2 * math.pi) * blur**2)
        norm = np.linalg.norm(gradient, axis=1)
        out[start:start + len(block)] += amplitude * gradient / (1 + norm[:, None])
    return out


def _band_intervals(position, velocity, low, high):
    parallel = np.abs(velocity) < 1e-12
    divisor = np.where(parallel, 1, velocity)
    u, v = (low - position) / divisor, (high - position) / divisor
    begin, end = np.minimum(u, v), np.maximum(u, v)
    inside = (position >= low) & (position <= high)
    return (np.where(parallel, np.where(inside, -np.inf, np.inf), begin),
            np.where(parallel, np.where(inside, np.inf, -np.inf), end))


def _blocked_intervals(start, end, a, b, clear):
    """Parameter intervals where a grid segment intersects ink capsules."""
    v = end - start
    vv = float(v @ v)
    if vv < 1e-24:
        return []
    # Broad phase is only a rejection, never the distance measurement.
    mask = np.all(np.maximum(a, b) + clear >= np.minimum(start, end), axis=1) & np.all(
        np.minimum(a, b) - clear <= np.maximum(start, end), axis=1)
    a, b = a[mask], b[mask]
    if not len(a):
        return []
    intervals = []
    # Round ends of the capsules.
    delta = start - np.concatenate([a, b])
    linear = delta @ v
    disc = linear * linear - vv * (np.sum(delta * delta, axis=1) - clear**2)
    live = disc > 0
    root = np.sqrt(np.maximum(disc[live], 0))
    for lo, hi in zip((-linear[live] - root) / vv, (-linear[live] + root) / vv):
        if min(hi, 1) > max(lo, 0):
            intervals.append((max(float(lo), 0), min(float(hi), 1)))
    # Rectangular middle, expressed in each ink segment's tangent frame.
    d = b - a
    lengths = np.linalg.norm(d, axis=1)
    unit = d / lengths[:, None]
    relative = start - a
    along = np.sum(relative * unit, axis=1)
    across = unit[:, 0] * relative[:, 1] - unit[:, 1] * relative[:, 0]
    speed_along = unit @ v
    speed_across = unit[:, 0] * v[1] - unit[:, 1] * v[0]
    lo1, hi1 = _band_intervals(along, speed_along, 0, lengths)
    lo2, hi2 = _band_intervals(across, speed_across, -clear, clear)
    lo, hi = np.maximum(np.maximum(lo1, lo2), 0), np.minimum(np.minimum(hi1, hi2), 1)
    intervals.extend((float(u), float(v)) for u, v in zip(lo, hi) if v > u)
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1] + 1e-12:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return merged


def _clear_parts(points, a, b, clear, min_stub):
    if clear == 0:
        return [points] if arclength(points)[-1] >= min_stub else []
    out, current = [], []

    def flush():
        if len(current) > 1:
            p = np.asarray(current)
            if arclength(p)[-1] >= min_stub:
                out.append(p)
        current.clear()

    for start, end in zip(points[:-1], points[1:]):
        blocked = _blocked_intervals(start, end, a, b, clear + 1e-9)
        allowed, previous = [], 0.0
        for lo, hi in blocked:
            if lo > previous:
                allowed.append((previous, lo))
            previous = hi
        if previous < 1:
            allowed.append((previous, 1.0))
        if not allowed:
            flush()
        for lo, hi in allowed:
            pa, pb = start + lo * (end - start), start + hi * (end - start)
            if current and np.linalg.norm(current[-1] - pa) > 1e-8:
                flush()
            if not current:
                current.append(pa)
            current.append(pb)
            if hi < 1:
                flush()
    flush()
    return out


@device("misfit_grid", params=GRID_PARAMS, family="general",
        doc="A sparse coordinate grid displaced by the Gaussian blurred length density gradient of finished ink.")
def misfit_grid(dctx, sheet, *, pitch=12.0, blur=8.0, strength=4.0,
                clear=1.0, min_stub=2.0, pen=0.15):
    _validate(GRID_PARAMS, locals())
    lines = _lines(sheet)
    if not lines:
        return []
    viewed = [(i, _view(dctx, p), s) for i, p, s in lines]
    a, b, lengths = _segments(viewed)
    live = lengths > 1e-12
    a, b, lengths = a[live], b[live], lengths[live]
    if not len(a):
        return []
    samples, weights = _density_samples(a, b, lengths, min(1.0, blur / 4))
    x, y, w, h = dctx.region
    if w < 0 or h < 0:
        raise KitError("misfit_grid region must have nonnegative dimensions")
    step = min(1.0, blur / 4, pitch / 8)
    out = []
    for axis, origin, extent, across, span in (("x", x, w, y, h), ("y", y, h, x, w)):
        if span <= 0:
            continue
        varying = np.linspace(across, across + span, max(2, math.ceil(span / step) + 1))
        for i in range(math.floor((extent + 1e-9) / pitch) + 1):
            coordinate = origin + i * pitch
            constant = np.full_like(varying, coordinate)
            points = np.column_stack([constant, varying] if axis == "x" else [varying, constant])
            points = _displace(points, samples, weights, blur, strength, pitch)
            # Keep the supplied region as a true boundary after displacement.
            points = np.clip(points, [x, y], [x + w, y + h])
            keep = np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > 1e-12]
            points = points[keep]
            if len(points) < 2:
                continue
            for piece, part in enumerate(_clear_parts(points, a, b, clear, min_stub)):
                out.append(_ink(part, pen, "grid_line", axis=axis, coordinate=float(coordinate),
                                grid_index=i, piece=piece, pitch=pitch, blur=blur, strength=strength))
    return out
