"""Bezier curve fitting: a sampled stroke -> editable pen anchors.

Schneider's algorithm ("An Algorithm for Automatically Fitting Digitized
Curves", Graphics Gems I): chord-length parameterisation, a least-squares
cubic with its end tangents held fixed, Newton reparameterisation, and a
split at the worst point when the fit is still too far off. Two things are
added around it because the input is hand sketches and found fill outlines,
not clean samples:

- consecutive duplicate points are dropped first, and non-finite input is
  refused (an open-loop machine must never see a NaN anchor);
- sharp turns are found up front and become hard breaks (``join="corner"``)
  with one-sided tangents, so a square stays square instead of being rounded
  off by a tangent-continuous fit.

The output is a list of dicts shaped exactly like ``PenAnchor.model_dump()``
(handles relative to their anchor), ready to drop into a ``PenSubpath``. A
closed fit is a loop: no duplicate closing anchor, because the pen source
draws the anchors[-1] -> anchors[0] segment itself.

Pure numpy, no state; used by ``POST /api/geometry/fit``.
"""

from __future__ import annotations

import bisect
import math
from typing import Sequence

import numpy as np

# detail 0 -> 2.0 mm (fewest anchors), detail 1 -> 0.05 mm (closest);
# log-interpolated so the slider's middle is a useful 0.32 mm.
TOL_COARSE = 2.0
TOL_FINE = 0.05

# A sample whose turn angle exceeds this becomes a corner anchor.
CORNER_ANGLE = math.radians(60.0)

# Turn angles are measured on chords reaching this far along the stroke
# (by arc length, interpolating between samples) rather than to the
# neighbouring sample. That is the light smoothing: hand jitter of a tenth
# of a millimetre between dense samples swings sample-to-sample directions
# wildly, but barely moves a 2 mm chord, and a corner whose tip fell
# between two samples (cut off by a short chamfer) still reads as one turn.
# Sparse input is unaffected, since the chord then lies on the polyline's
# own edge. The cost: bends tighter than about a 2 mm radius read as
# corners, which at plotter scale they nearly are.
CORNER_WINDOW_MM = 2.0
# End tangents use a shorter chord: long enough to ride over jitter, short
# enough that a one-sided chord on a curve (error ~ chord / 2r) stays small.
TANGENT_WINDOW_MM = 1.0

# The pen source refuses a path with more anchors than this (pen._MAX_ANCHORS;
# a test pins the two together). A fit must always come back editable, so
# past it the tolerance is coarsened, and past THAT the weakest corners go.
MAX_ANCHORS = 2000
_TOL_CEILING = 64.0     # mm; coarser than this, just fit one cubic per span
_TOL_BISECT_STEPS = 5   # log-bisection steps between tolerance and ceiling (~25%)

# A "smooth" join promises collinear, opposed handles; anything further off
# than this (cosine of the angle between in and out handle) says "corner".
_SMOOTH_COS = -0.9995

_DUP_EPS = 1e-6         # mm; consecutive points closer than this are one point
_NEWTON_PASSES = 4      # Schneider's maxIterations
_REPARAM_FACTOR = 3.0   # try reparameterising only when within this x tolerance
MAX_HANDLE_MM = 400.0   # mirrors pen.js's cap on a handle's length


def detail_tolerance(detail: float) -> float:
    """Fit tolerance (mm) for a detail value in [0, 1]."""
    d = min(1.0, max(0.0, float(detail)))
    return math.exp(math.log(TOL_COARSE) + (math.log(TOL_FINE) - math.log(TOL_COARSE)) * d)


# ---------------------------------------------------------------- polyline


class _Line:
    """The working polyline: points plus cumulative arc length. For a closed
    stroke the first point is repeated at the end (index n), so segment
    ranges never wrap; ``at`` wraps arc length instead."""

    def __init__(self, pts: np.ndarray, closed: bool):
        self.closed = closed
        self.n = len(pts)  # distinct points
        self.q = np.vstack([pts, pts[:1]]) if closed else pts
        seg = np.hypot(*np.diff(self.q, axis=0).T)
        self.s = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(self.s[-1])

    def at(self, s):
        """Point(s) at arc length ``s`` (wrapped when closed, clipped when open)."""
        s = np.asarray(s, dtype=float)
        if self.closed and self.length > 0:
            s = np.mod(s, self.length)
        else:
            s = np.clip(s, 0.0, self.length)
        return np.stack([np.interp(s, self.s, self.q[:, 0]),
                         np.interp(s, self.s, self.q[:, 1])], axis=-1)


def _unit(v: np.ndarray) -> np.ndarray | None:
    n = float(np.hypot(v[0], v[1]))
    if not math.isfinite(n) or n < 1e-12:
        return None
    return v / n


def _turn(back: np.ndarray, fwd: np.ndarray) -> np.ndarray:
    """Turn angle (0..pi) between incoming and outgoing direction vectors."""
    cross = back[:, 0] * fwd[:, 1] - back[:, 1] * fwd[:, 0]
    dot = (back * fwd).sum(axis=1)
    ok = (np.hypot(*back.T) > 1e-9) & (np.hypot(*fwd.T) > 1e-9)
    return np.where(ok, np.arctan2(np.abs(cross), dot), 0.0)


def _find_corners(line: _Line) -> list[int]:
    """Indices (into the distinct points) whose turn angle exceeds
    CORNER_ANGLE, one per bend: the sharpest sample wins and suppresses any
    other candidate within the window of it. Strongest corner first."""
    n = line.n
    if n < 3 or line.length <= 0:
        return []
    w = min(CORNER_WINDOW_MM, line.length / 8.0)
    s = line.s[:n]
    p = line.q[:n]

    def turn_at(win: float) -> np.ndarray:
        return _turn(p - line.at(s - win), line.at(s + win) - p)

    angle = turn_at(w)
    # Which sample IS the corner: near a sharp bend every sample within the
    # window turns nearly as much at the coarse scale (at a cusp, exactly
    # as much), so rank candidates by the turn summed over finer scales down
    # to the neighbouring samples. Only the coarse angle decides WHETHER.
    q = line.q
    prev = np.vstack([q[-2:-1] if line.closed else q[:1], q[:n - 1]])
    nxt = q[1:n + 1] if line.closed else np.vstack([q[1:n], q[n - 1:n]])
    rank = angle + turn_at(w / 2) + turn_at(w / 4) + _turn(p - prev, nxt - p)
    if not line.closed:
        # an open stroke's ends are anchors already; a "corner" a hair from
        # one (a pen-landing hook) would only make a sliver segment
        angle[(s < w) | (s > line.length - w)] = 0.0
    cand = np.flatnonzero(angle > CORNER_ANGLE)
    accepted: list[int] = []
    taken: list[float] = []  # arc lengths of accepted corners, kept sorted
    for i in cand[np.argsort(-rank[cand], kind="stable")]:
        si = float(s[i])
        k = bisect.bisect_left(taken, si)
        near = [taken[j] for j in (k - 1, k) if 0 <= j < len(taken)]
        if line.closed and taken:  # the loop wraps: the far ends are neighbours too
            near += [taken[0] + line.length, taken[-1] - line.length]
        if all(abs(si - t) >= w for t in near):
            bisect.insort(taken, si)
            accepted.append(int(i))
    return accepted


# ---------------------------------------------------------------- Schneider


def _bez(ctrl: np.ndarray, u: np.ndarray) -> np.ndarray:
    mu = 1.0 - u
    b = np.stack([mu ** 3, 3 * u * mu ** 2, 3 * u ** 2 * mu, u ** 3], axis=1)
    return b @ ctrl


def _bez_d1(ctrl: np.ndarray, u: np.ndarray) -> np.ndarray:
    d = 3.0 * np.diff(ctrl, axis=0)
    mu = 1.0 - u
    b = np.stack([mu ** 2, 2 * u * mu, u ** 2], axis=1)
    return b @ d


def _bez_d2(ctrl: np.ndarray, u: np.ndarray) -> np.ndarray:
    d = 6.0 * np.diff(ctrl, n=2, axis=0)
    b = np.stack([1.0 - u, u], axis=1)
    return b @ d


def _generate(pts: np.ndarray, u: np.ndarray, t1: np.ndarray, t2: np.ndarray,
              arclen: float) -> np.ndarray:
    """Least-squares cubic through pts[0], pts[-1] with handle directions
    t1 (out of the start) and t2 (into the end, pointing back)."""
    p0, p3 = pts[0], pts[-1]
    mu = 1.0 - u
    b0, b1, b2, b3 = mu ** 3, 3 * u * mu ** 2, 3 * u ** 2 * mu, u ** 3
    a1 = t1[None, :] * b1[:, None]
    a2 = t2[None, :] * b2[:, None]
    c00 = float((a1 * a1).sum())
    c01 = float((a1 * a2).sum())
    c11 = float((a2 * a2).sum())
    tmp = pts - (np.outer(b0 + b1, p0) + np.outer(b2 + b3, p3))
    x0 = float((a1 * tmp).sum())
    x1 = float((a2 * tmp).sum())
    det = c00 * c11 - c01 * c01
    chord = float(np.hypot(*(p3 - p0)))
    eps = 1e-6 * max(chord, arclen)
    al = ar = float("nan")
    if abs(det) > 1e-12:
        al = (x0 * c11 - x1 * c01) / det
        ar = (c00 * x1 - c01 * x0) / det
    if not (math.isfinite(al) and math.isfinite(ar)) or al < eps or ar < eps:
        # Schneider's fallback (Wu/Barsky heuristic): a third of the chord,
        # or of the arc when the segment nearly closes on itself
        al = ar = (chord if chord > 1e-3 * arclen else arclen) / 3.0
    # a handle longer than the arc it shapes is the least squares running away
    cap = min(max(arclen, 1e-9), MAX_HANDLE_MM)
    al, ar = min(al, cap), min(ar, cap)
    return np.array([p0, p0 + t1 * al, p3 + t2 * ar, p3])


def _max_error(pts: np.ndarray, ctrl: np.ndarray, u: np.ndarray) -> tuple[float, int]:
    d = np.hypot(*(_bez(ctrl, u) - pts).T)
    d[0] = d[-1] = 0.0
    i = int(np.argmax(d))
    return float(d[i]), i


def _newton(pts: np.ndarray, ctrl: np.ndarray, u: np.ndarray) -> np.ndarray:
    diff = _bez(ctrl, u) - pts
    d1 = _bez_d1(ctrl, u)
    d2 = _bez_d2(ctrl, u)
    num = (diff * d1).sum(axis=1)
    den = (d1 * d1).sum(axis=1) + (diff * d2).sum(axis=1)
    safe = np.abs(den) > 1e-12
    step = np.divide(num, den, out=np.zeros_like(num), where=safe)
    out = np.clip(u - step, 0.0, 1.0)
    out[0], out[-1] = 0.0, 1.0
    return out


def _center_tangent(line: _Line, i: int, lo: int, hi: int) -> np.ndarray | None:
    """Direction through point i, measured on a chord kept inside [lo, hi]
    (so it never reaches across a corner). Points backward, Schneider's
    convention for a split's tHatCenter."""
    s = line.s
    d = min(TANGENT_WINDOW_MM, s[i] - s[lo], s[hi] - s[i])
    if d > 1e-9:
        t = _unit(line.at(s[i] - d) - line.at(s[i] + d))
        if t is not None:
            return t
    return _unit(line.q[max(lo, i - 1)] - line.q[min(hi, i + 1)])


def _loop_tangent(line: _Line, i: int) -> np.ndarray | None:
    """Backward-pointing tangent through a smooth breakpoint of a loop;
    at the seam (q[0] == q[n]) the chord wraps around it."""
    if i in (0, line.n):
        d = min(TANGENT_WINDOW_MM, line.length / 4.0)
        return _unit(line.at(line.s[i] - d) - line.at(line.s[i] + d))
    return _center_tangent(line, i, 0, line.n)


def _one_sided_tangent(line: _Line, i: int, toward: int) -> np.ndarray | None:
    """Unit direction leaving q[i] along the stroke toward index ``toward``,
    on a chord that stays within the first third of that span."""
    s = line.s
    step = 1 if toward > i else -1
    d = min(TANGENT_WINDOW_MM, abs(s[toward] - s[i]) / 3.0)
    t = _unit(line.at(s[i] + step * d) - line.q[i]) if d > 1e-9 else None
    return t if t is not None else _unit(line.q[i + step] - line.q[i])


def _fit_range(line: _Line, i0: int, i1: int, t1: np.ndarray, t2: np.ndarray,
               tol: float, limit: int) -> list[np.ndarray] | None:
    """Fit q[i0..i1] with cubics; returns their control points in order, or
    None as soon as more than ``limit`` are needed (a doomed pass stops
    early). Iterative (an explicit stack) so a 20000-point stroke can't hit
    the recursion limit."""
    out: list[np.ndarray] = []
    stack = [(i0, i1, t1, t2)]
    q, s = line.q, line.s
    while stack:
        a, b, ta, tb = stack.pop()
        pts = q[a:b + 1]
        arclen = float(s[b] - s[a])
        if len(pts) == 2:
            out.append(_generate(pts, np.array([0.0, 1.0]), ta, tb, arclen))
            if len(out) > limit:
                return None
            continue
        u = (s[a:b + 1] - s[a]) / arclen if arclen > 0 else np.linspace(0.0, 1.0, len(pts))
        ctrl = _generate(pts, u, ta, tb, arclen)
        err, split = _max_error(pts, ctrl, u)
        if err > tol and err <= tol * _REPARAM_FACTOR:
            for _ in range(_NEWTON_PASSES):
                u = _newton(pts, ctrl, u)
                cand = _generate(pts, u, ta, tb, arclen)
                cerr, csplit = _max_error(pts, cand, u)
                if cerr < err:
                    ctrl, err, split = cand, cerr, csplit
                if err <= tol:
                    break
        if err <= tol:
            out.append(ctrl)
            if len(out) > limit:
                return None
            continue
        k = a + min(max(split, 1), len(pts) - 2)
        tc = _center_tangent(line, k, a, b)
        if tc is None:  # only if q[k-1] == q[k+1]: use the span's chord
            tc = _unit(q[a] - q[b])
        if tc is None:
            tc = np.array([-1.0, 0.0])
        # LIFO: push the right half first so the left half is fitted (and
        # emitted) first
        stack.append((k, b, -tc, tb))
        stack.append((a, k, ta, tc))
    return out


# ---------------------------------------------------------------- public


def _anchor(p, in_h, out_h, join) -> dict:
    """One PenAnchor-shaped dict. Non-finite numbers raise: they would mean
    a fitter bug, and an anchor must never quietly lose a handle over one."""
    def xy(v):
        x, y = float(v[0]), float(v[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError(f"curve fit produced a non-finite value: {(x, y)}")
        return (x, y)
    x, y = xy(p)
    in_h = None if in_h is None else xy(in_h)
    out_h = None if out_h is None else xy(out_h)
    if join == "smooth" and in_h is not None and out_h is not None:
        li, lo = math.hypot(*in_h), math.hypot(*out_h)
        if li > 0 and lo > 0 and (in_h[0] * out_h[0] + in_h[1] * out_h[1]) / (li * lo) > _SMOOTH_COS:
            join = "corner"  # e.g. a two-point loop retracing itself: a cusp
    return {"x": x, "y": y, "in_handle": in_h, "out_handle": out_h, "join": join}


def _clean(points: Sequence[Sequence[float]], closed: bool) -> np.ndarray:
    arr = np.asarray(points, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 2 or len(arr) == 0:
        raise ValueError("points must be a non-empty list of [x, y] pairs")
    if not np.all(np.isfinite(arr)):
        raise ValueError("points must be finite")
    keep = [0]
    for i in range(1, len(arr)):
        if math.hypot(arr[i, 0] - arr[keep[-1], 0], arr[i, 1] - arr[keep[-1], 1]) > _DUP_EPS:
            keep.append(i)
    arr = arr[keep]
    if closed and len(arr) > 1 and math.hypot(*(arr[-1] - arr[0])) <= _DUP_EPS:
        arr = arr[:-1]
    return arr


def fit_bezier(points: Sequence[Sequence[float]], closed: bool, detail: float) -> list[dict]:
    """Fit a sampled stroke with cubic Beziers; return pen anchors.

    ``detail`` in [0, 1] picks the tolerance (see ``detail_tolerance``).
    Interior joins between fitted cubics are ``"smooth"``, sharp turns
    ``"corner"``; an open fit's end anchors carry ``join=None`` and no
    outward handle. Always returns at least two anchors and never more than
    MAX_ANCHORS: past that the tolerance is coarsened, then the weakest
    corners are dropped, so the result is always an editable pen path.
    """
    tol = detail_tolerance(detail)
    pts = _clean(points, closed)
    if len(pts) == 1:
        # a dot: two coincident anchors, the smallest drawable pen subpath
        p = pts[0]
        return [_anchor(p, None, None, None), _anchor(p, None, None, None)]

    line = _Line(pts, closed)
    n = line.n
    # Corners don't depend on the tolerance, so coarsening can't remove them:
    # keep only as many (strongest first) as the cap has room for, leaving
    # an open stroke its two end anchors.
    corners = sorted(_find_corners(line)[:MAX_ANCHORS - (0 if closed else 2)])
    if closed and corners and corners[0] != 0:
        # start the loop on a corner so no segment runs through the seam
        pts = np.roll(pts, -corners[0], axis=0)
        corners = [(c - corners[0]) % n for c in corners]
        line = _Line(pts, closed)

    # breakpoints: (index into line.q, is_corner). Segments run between
    # consecutive breakpoints and are fitted independently.
    if closed:
        breaks = [(c, True) for c in corners]
        if not breaks or breaks[0][0] != 0:
            breaks.insert(0, (0, False))
        if len(breaks) < 2:
            # a loop needs two anchors: add a smooth one halfway round
            mid = int(np.searchsorted(line.s, line.length / 2.0))
            mid = min(max(mid, 1), n - 1)
            breaks.append((mid, False))
        breaks.append((n, breaks[0][1]))  # q[n] is q[0] again
    else:
        breaks = [(0, False)] + [(c, True) for c in corners] + [(n - 1, False)]

    spans = []  # (start, end, start is corner, tangent out of start, tangent into end)
    for (a, ca), (b, cb) in zip(breaks, breaks[1:]):
        # Smooth breakpoints only occur on loops (an open stroke's ends are
        # one-sided); both segments meeting there share one tangent, so the
        # join is G1 by construction.
        t_out = t_in = None
        if closed and not ca:
            t = _loop_tangent(line, a)
            t_out = -t if t is not None else None
        if closed and not cb:
            t_in = _loop_tangent(line, b)
        t_out = t_out if t_out is not None else _one_sided_tangent(line, a, b)
        t_in = t_in if t_in is not None else _one_sided_tangent(line, b, a)
        if t_out is None or t_in is None:  # unreachable after de-duplication
            t_out, t_in = np.array([1.0, 0.0]), np.array([-1.0, 0.0])
        spans.append((a, b, ca, t_out, t_in))

    # an open fit has one more anchor than cubics; a loop has as many
    budget = MAX_ANCHORS - (0 if closed else 1)

    def fit_all(tol: float):
        cubics: list[np.ndarray] = []
        joins: list[str | None] = []  # join of each cubic's START anchor
        for a, b, ca, t_out, t_in in spans:
            segs = _fit_range(line, a, b, t_out, t_in, tol, budget - len(cubics))
            if segs is None:
                return None
            for j, ctrl in enumerate(segs):
                cubics.append(ctrl)
                joins.append(("corner" if ca else "smooth") if j == 0 else "smooth")
        return cubics, joins

    # Over the pen source's cap at the asked tolerance: find (roughly) the
    # finest tolerance that fits, by log-bisection up to the ceiling. Past
    # the ceiling every span is one cubic, which the corner cap above keeps
    # within budget. When the corners alone fill the cap, go straight there.
    fit = fit_all(tol)
    if fit is None:
        fit = fit_all(_TOL_CEILING) if len(spans) < budget else None
        if fit is None:
            fit = fit_all(math.inf)
        else:
            lo, hi = math.log(tol), math.log(_TOL_CEILING)
            for _ in range(_TOL_BISECT_STEPS):
                mid = (lo + hi) / 2.0
                got = fit_all(math.exp(mid))
                if got is None:
                    lo = mid
                else:
                    hi, fit = mid, got
    if fit is None:  # unreachable: one cubic per span always fits
        raise ValueError("curve fit cannot meet the anchor cap")
    cubics, joins = fit

    if not closed:
        anchors = [_anchor(cubics[0][0], None, cubics[0][1] - cubics[0][0], None)]
        for k in range(1, len(cubics)):
            prev, cur = cubics[k - 1], cubics[k]
            anchors.append(_anchor(cur[0], prev[2] - cur[0], cur[1] - cur[0], joins[k]))
        last = cubics[-1]
        anchors.append(_anchor(last[3], last[2] - last[3], None, None))
    else:
        anchors = []
        for k, cur in enumerate(cubics):
            prev = cubics[k - 1]  # k=0 -> the closing cubic, which ends at q[0]
            anchors.append(_anchor(cur[0], prev[2] - cur[0], cur[1] - cur[0], joins[k]))
    return anchors
