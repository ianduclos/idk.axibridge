# FROZEN from research commit 071aea1: tools/gesture/gesture/kit/arrangers_contagion.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 13, thread I-c `contagion`: a line that CATCHES a regime's grammar.

Ian on found ground (2026-10-18): "the way the line in front becomes the
river, and becomes the above graph, and then does some other thing by itself
in another place."

Found ground (`arrangers_oehlen_found`) has RIDE: the line travels 0.9 mm
beside a found contour and leaves. Here the ride is only the moment of
contact. After it the line CATCHES the regime: it keeps the regime's grammar,
whole, along its OWN path, far from the source, and the grammar then wears off.

    contact   the line, listening, meets a found contour of a regime (near and
              aligned, found ground's test) and rides it for a short stretch
    onset     where it leaves, the infection starts at full strength: the
              line's own path is redrawn in the caught grammar, generated
              fresh from that regime's measured statistics (never a pasted
              piece of the source)
    duration  `full_*` mm of the line's own path (log-normal)
    way out   the grammar is shed in whole elements, never faded: the share
              of the line in the caught grammar falls to 0 over `decay_*` mm,
              so the last bends / rules are rarer, each still whole; a plate
              infection loses its ruling first and its ticks last
              (`tick_linger`)
    second    a line still carrying one regime can catch the other; while
              both are active their elements interleave (a river bend, a
              ruled run, a river bend), each whole

Grammars (measured on the found layer as pasted, so the scale is the sheet's):

    river     Langbein & Leopold's sine-generated curve, with its parameters
              measured on the far river: per half-bend, the heading's extremum
              about the valley axis and the arc length to the next one, fit as
              a bivariate log-normal. A carried river is a NEW bend sequence
              drawn from it, integrated in a valley frame whose axis is the
              line's own path. Elements are bends (axis crossing to crossing).
    plate     the plate's rules: dead straight at the plate's ruling angle (or
              at right angles to it, the leaders') when the line's own chord
              is within `snap` degrees of one; then an elbow back onto the own
              path. Ticks (out and back, the plate's 1.7 mm leader length) at
              `tick_pitch`. Elements are ruled runs.

Channel written: `catch` (nearest) on the late line, per point:
0 own, 1 riding the river, 2 riding the plate, 3 carried river, 4 carried
rule, 5 tick. The arranger's log (`marks[0].meta["contagion"]`) lists every
infection: where contact was made, onset, full-to-decay and end points.
"""
from __future__ import annotations

import math

import numpy as np

from .arrangers_oehlen_found import (FLEXOKI, Ground, arclen, clip_rect, frac_boxes, make_mark, rect_polygon,
                                     resample, ride_along, rotate, tangents)
from .core import Mark, P, arranger, channel_kind

channel_kind("catch", "nearest")
OWN, RIDE_RIVER, RIDE_PLATE, RIVER, RULE, TICK = 0, 1, 2, 3, 4, 5
REGIMES = ("river", "plate")


# ---------------------------------------------------------------------------
# grammars, measured on the found layer
# ---------------------------------------------------------------------------

def _heading(p: np.ndarray) -> np.ndarray:
    d = np.diff(p, axis=0)
    return np.unwrap(np.arctan2(d[:, 1], d[:, 0]))


def river_grammar(lines, *, step: float = 0.2, axis_mm: float = 10.0, smooth_mm: float = 0.6,
                  calibrate: bool = True, omega_max: float = 120.0) -> dict:
    """The river's bend grammar, after Langbein & Leopold's sine-generated curve: its heading about the
    valley axis (Gaussian, `axis_mm`) swings between alternating extrema. Per half-bend: the extremum
    ω (deg) and the arc length to the next extremum (mm), fit as a bivariate log-normal (they are
    correlated: wider swings take longer). Measured on the found river as pasted (sheet mm)."""
    from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415
    om, ln, prof = [], [], []
    meas = 0.0
    u17 = np.linspace(0.0, 1.0, 17)
    for l in lines:
        p = resample(np.asarray(l, float), step)
        if len(p) < 4 * axis_mm / step:
            continue
        th = _heading(p)
        r = gaussian_filter1d(th - gaussian_filter1d(th, axis_mm / step, mode="nearest"), smooth_mm / step)
        zc = np.flatnonzero(np.diff(np.sign(r)) != 0)
        ext = [int(a + np.argmax(np.abs(r[a:b + 1]))) for a, b in zip(zc[:-1], zc[1:])]
        for k0, k1 in zip(ext[:-1], ext[1:]):
            om.append(abs(float(r[k0])))
            ln.append((k1 - k0) * step)
            seg = r[k0:k1 + 1]
            if len(seg) >= 5:                          # the swing's shape, normalised 0 → 1
                prof.append(np.interp(u17, np.linspace(0.0, 1.0, len(seg)), (seg - seg[0]) / (seg[-1] - seg[0])))
        meas += len(p) * step
    if len(om) < 8:
        raise ValueError("contagion: the found river is too short to measure its bends")
    X = np.log(np.c_[om, ln])
    g = {"model": "sine-generated", "axis_mm": axis_mm, "mu": X.mean(axis=0).tolist(),
         "cov": np.cov(X.T).tolist(), "n_bends": len(om),
         "profile": np.round(np.mean(prof, axis=0), 4).tolist(),
         "omega_deg_p50": round(math.degrees(float(np.median(om))), 1),
         "halfbend_mm_p50": round(float(np.median(ln)), 2), "measured_mm": round(meas, 1)}
    if calibrate:
        # measuring about a smoothed axis under-reads a swing; so a generated river, measured the same
        # way, must read like the found one: shift the log-means until it does (fixed seed, 3 rounds)
        mu = np.array(g["mu"])
        for _ in range(3):
            xy = gen_meander(np.random.default_rng(0), {**g, "mu": mu.tolist()}, 1500.0, omega_max=omega_max)
            m = river_grammar([xy], step=step, axis_mm=axis_mm, smooth_mm=smooth_mm, calibrate=False)
            mu = mu + [math.log(g["omega_deg_p50"] / max(m["omega_deg_p50"], 1e-6)),
                       math.log(g["halfbend_mm_p50"] / max(m["halfbend_mm_p50"], 1e-6))]
        g["mu"] = mu.tolist()
        g["calibrated"] = True
    return g


def plate_grammar(rules, labels=()) -> dict:
    """The plate's ruling: its angle (median of the rules', mod 180), rule lengths, and the leader length
    (the label strokes standing at right angles to the rules)."""
    ang, lens = [], []
    for l in rules:
        l = np.asarray(l, float)
        d = l[-1] - l[0]
        L = float(np.linalg.norm(d))
        if L > 3.0:
            ang.append(math.degrees(math.atan2(d[1], d[0])) % 180.0)
            lens.append(L)
    if not ang:
        raise ValueError("contagion: no plate rules to measure")
    a = float(np.median([((x + 90.0) % 180.0) - 90.0 for x in ang]))
    lead = []
    for l in labels:
        l = np.asarray(l, float)
        if len(l) == 2:
            d = l[-1] - l[0]
            L = float(np.linalg.norm(d))
            dev = abs(((math.degrees(math.atan2(d[1], d[0])) - a - 90.0 + 90.0) % 180.0) - 90.0)
            if 1.0 <= L <= 4.0 and dev < 10.0:
                lead.append(L)
    return {"angle_deg": round(a, 2), "rule_mm": round(float(np.median(lens)), 1),
            "rule_range_mm": [round(float(min(lens)), 1), round(float(max(lens)), 1)],
            "tick_mm": round(float(np.median(lead)), 2) if lead else 1.7}


def gen_meander(rng: np.random.Generator, g: dict, length_x: float, *, step: float = 0.2,
                omega_max: float = 130.0) -> np.ndarray:
    """A fresh river from its bend grammar: alternating heading extrema ω_k and half-bend lengths drawn
    from the measured log-normal, the heading swung between them along the river's measured mean swing
    profile (nearer a straight ramp than the sine-generated cosine: its bends are rounder arcs), integrated at unit speed in a valley frame (x along the axis). ω is capped at `omega_max`
    (beyond ~130° a sine-generated bend crosses itself). Starts at an axis crossing; x runs 0 → ≥ length_x."""
    from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415
    mu, cov = np.asarray(g["mu"]), np.asarray(g["cov"])
    u17 = np.linspace(0.0, 1.0, 17)
    prof = np.asarray(g.get("profile") or (1 - np.cos(np.pi * u17)) / 2)
    th = [np.zeros(1)]
    prev = 0.0
    sign = 1.0 if rng.random() < 0.5 else -1.0
    x_est, lim = 0.0, length_x * 4.0 + 60.0
    while x_est < lim:
        lo, ll = rng.multivariate_normal(mu, cov)
        w = min(max(math.exp(lo), math.radians(8.0)), math.radians(omega_max)) * sign
        L = min(max(math.exp(ll), 4 * step), 30.0)
        m = max(int(round(L / step)), 2)
        u = np.arange(1, m + 1) / m
        th.append(prev + (w - prev) * np.interp(u, u17, prof))
        prev, sign = w, -sign
        x_est += L
    th = np.concatenate(th)
    xy = np.r_[[[0.0, 0.0]], np.cumsum(np.c_[np.cos(th), np.sin(th)] * step, axis=0)]
    xy[:, 1] -= gaussian_filter1d(xy[:, 1], 3 * g["axis_mm"] / step, mode="nearest")
    zc = np.flatnonzero(np.diff(np.sign(xy[:, 1])) != 0)
    a = int(zc[min(2, len(zc) - 1)]) + 1 if len(zc) else 0
    xy = xy[a:] - [xy[a, 0], 0.0]
    xy[0, 1] = 0.0
    k = np.flatnonzero(xy[:, 0] >= length_x)
    return xy[: int(k[0]) + 1] if len(k) else xy


def bends(xy: np.ndarray) -> list[tuple[int, int]]:
    """Index ranges of whole bends (axis crossing to axis crossing; tiny crossings merged)."""
    zc = np.flatnonzero(np.diff(np.sign(xy[:, 1])) != 0) + 1
    cuts = [0] + [int(z) for z in zc] + [len(xy) - 1]
    out = []
    a = 0
    for c in cuts[1:]:
        if c - a >= 3:
            out.append((a, c))
            a = c
    return out


# ---------------------------------------------------------------------------
# the carrier: the line's own path (plus the swim back after a ride)
# ---------------------------------------------------------------------------

class Carrier:
    def __init__(self, pts: np.ndarray, step: float):
        self.p = np.asarray(pts, float)
        self.step = step
        self.t = tangents(self.p, max(int(round(3.0 / step)), 2))
        self.n = np.c_[-self.t[:, 1], self.t[:, 0]]

    def at(self, fi: np.ndarray):
        fi = np.clip(np.asarray(fi, float), 0, len(self.p) - 1)
        i0 = np.floor(fi).astype(int)
        i1 = np.minimum(i0 + 1, len(self.p) - 1)
        w = (fi - i0)[:, None]
        P = self.p[i0] * (1 - w) + self.p[i1] * w
        N = self.n[i0] * (1 - w) + self.n[i1] * w
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        return P, N

    def map(self, i0: float, xy: np.ndarray) -> np.ndarray:
        P, N = self.at(i0 + xy[:, 0] / self.step)
        return P + N * xy[:, 1:2]


def _smooth(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


class Infection:
    def __init__(self, regime, on, full, decay, linger, step, meta):
        self.regime, self.on, self.full, self.decay, self.linger = regime, on, full, decay, linger
        self.step, self.meta = step, meta
        self.xy = None
        self.bends: list[tuple[int, int]] = []

    def strength(self, i: float, tail: float = 1.0) -> float:
        s = (i - self.on) * self.step
        if s < 0:
            return 0.0
        if s < self.full:
            return 1.0
        return 1.0 - _smooth((s - self.full) / max(self.decay * tail, 1e-6))

    @property
    def end(self) -> float:
        return self.on + (self.full + self.decay * max(self.linger, 1.0)) / self.step


# ---------------------------------------------------------------------------
# the walk
# ---------------------------------------------------------------------------

def _lognorm(rng, mean, sd):
    return float(mean * math.exp(rng.normal(0, sd) - sd ** 2 / 2))


def _cat(pieces):
    """Concatenate (points, codes) pieces end to end (a repeated junction point is dropped)."""
    P, C = [], []
    for p, c in pieces:
        p = np.asarray(p, float)
        c = np.asarray(c, float)
        if not len(p):
            continue
        if P and np.linalg.norm(P[-1][-1] - p[0]) < 1e-9:
            p, c = p[1:], c[1:]
        if len(p):
            P.append(p)
            C.append(c)
    if not P:
        return np.empty((0, 2)), np.empty(0)
    return np.vstack(P), np.concatenate(C)


def _join(pieces, ramp, step):
    """found ground's tangent join (`arrangers_oehlen_found.join`), carrying per-point codes."""
    from .arrangers_oehlen_found import bridge  # noqa: PLC0415
    pieces = [(np.asarray(p, float), np.asarray(c, float)) for p, c in pieces if len(p) >= 2]
    if not pieces:
        return np.empty((0, 2)), np.empty(0)
    k = max(int(round(ramp / step)), 0)
    tr = []
    for i, (p, c) in enumerate(pieces):
        a = k if i > 0 else 0
        b = len(p) - (k if i < len(pieces) - 1 else 0)
        if b - a < 2:
            m = len(p) // 2
            a, b = max(m - 1, 0), min(m + 1, len(p))
        tr.append((p[a:b], c[a:b]))
    pts, cs = [tr[0][0]], [tr[0][1]]
    for (pa, ca), (pb, cb) in zip(tr[:-1], tr[1:]):
        br = bridge(pa[-1], tangents(pa, 3)[-1], pb[0], tangents(pb, 3)[0], step)
        pts += [br, pb]
        cs += [np.full(len(br), OWN, float), cb]
    return np.vstack(pts), np.concatenate(cs)


def contagion_walk(M, grounds: dict, grammars: dict, rng: np.random.Generator, *, step, capture, align, listen,
                   ignore, ride, ride_sd, min_ride, ride_gap, return_mm, ramp, max_offset, catches, full, decay,
                   tick_linger, own_mm, rule_tol, snap, tick_pitch, immune_mm, omega_max=130.0, rule_shared=9.0,
                   regimes=REGIMES, carry=True, gate=None):
    """M (sheet mm) walked against the found regimes. Returns (points, catch codes, log). carry=False is
    the control: the same contacts and rides, nothing caught.

    Beyond the river and the plate, a regime may be any key of `grounds` whose grammar has a `gen`
    (rng, length_mm) -> valley-frame xy (x along the own path, starting at an axis crossing, as
    `gen_meander`): it is carried like the river, in whole bends, with per-point code `code` and ride
    code `ride_code`. `gate(i, regime, j, i0, cos)` (optional) may refuse a contact candidate at own
    index i (e.g. only a curving stretch listens)."""
    M = resample(np.asarray(M, float), step)
    tM = tangents(M, max(int(2.0 / step), 2))
    n = len(M)

    # listening windows (found ground's ignore / listen)
    windows, s, s_tot = [], 0.0, (n - 1) * step
    mode = "ignore" if rng.random() < 0.5 else "listen"
    while s < s_tot:
        L = max(_lognorm(rng, ignore if mode == "ignore" else listen, ride_sd), step)
        windows.append((s, s + L, mode))
        s += L
        mode = "listen" if mode == "ignore" else "ignore"

    def listening(ii):
        si = ii * step
        return any(a <= si < b and m == "listen" for a, b, m in windows)

    # ---- phase A: contacts and rides on the own path; the carrier is M + the swim back
    D = np.zeros((n, 2))
    visited = np.zeros(n, bool)
    rides = []                         # (index where the carrier stops, index where it resumes, seg, regime)
    infections: list[Infection] = []
    d0, i_leave = np.zeros(2), 0
    i = 0
    cool = 0
    n_contacts = 0
    last_end = {r: -1e9 for r in (*REGIMES, *regimes)}
    contacts = []

    def disp(ii):
        if not np.any(d0):
            return np.zeros(2)
        u = (ii - i_leave) * step / max(return_mm, 1e-6)
        return np.zeros(2) if u >= 1 else d0 * (1 - (3 * u * u - 2 * u ** 3))

    while i < n:
        D[i] = disp(i)
        visited[i] = True
        p = M[i] + D[i]
        if cool > 0:
            cool -= 1
        elif n_contacts < catches and listening(i):
            best = None
            for reg in regimes:
                G = grounds.get(reg)
                if G is None or G.tree is None:
                    continue
                act = [f for f in infections if f.regime == reg and f.end > i]
                if act or (i - last_end[reg]) * step < immune_mm:
                    continue                       # already carrying it, or immune for a while after
                for k in G.near(p, capture):
                    j, ii = G.ids[k]
                    c = float(np.dot(G.tan[j][ii], tM[i]))
                    if abs(c) < align:
                        continue
                    if gate is not None and not gate(i, reg, int(j), int(ii), c):
                        continue
                    dist = float(np.linalg.norm(G.pts[k] - p))
                    sc = dist - 2.0 * abs(c)
                    if best is None or sc < best[0]:
                        best = (sc, reg, G, int(j), int(ii), 1 if c > 0 else -1)
            if best is not None:
                _, reg, G, j, i0, direc = best
                avail = (len(G.lines[j]) - 1 - i0) if direc > 0 else i0
                L = min(_lognorm(rng, ride, ride_sd), avail * step)
                seg = ride_along(G, j, i0, direc, L, step) if L >= min_ride else None
                if seg is not None and len(seg) >= 3:
                    jj = np.minimum(i + np.arange(len(seg)), n - 1)
                    off = np.linalg.norm(seg - M[jj], axis=1)
                    ok = np.flatnonzero(off <= max_offset)
                    seg = seg[: ok[-1] + 1] if len(ok) else seg[:0]
                if seg is not None and len(seg) >= max(int(min_ride / step), 3):
                    if ride_gap > 0:
                        t = tangents(seg, 3)
                        nrm = np.c_[-t[:, 1], t[:, 0]]
                        side = 1.0 if float(np.dot(p - seg[0], nrm[0])) >= 0 else -1.0
                        seg = seg + side * ride_gap * nrm
                    i_new = min(i + len(seg), n - 1)
                    rides.append((i, i_new, seg, reg))
                    d0 = seg[-1] - M[i_new]
                    i_leave = i_new
                    fl = _lognorm(rng, full[reg], ride_sd)
                    dc = _lognorm(rng, decay[reg], ride_sd)
                    f = Infection(reg, i_new, fl, dc, tick_linger if reg == "plate" else 1.0, step,
                                  {"contact": np.round(p, 2).tolist(), "ride_mm": round(len(seg) * step, 1)})
                    n_contacts += 1
                    if carry:
                        infections.append(f)
                        last_end[reg] = f.end
                    else:
                        last_end[reg] = f.on
                        contacts.append({"regime": reg, **f.meta})
                    i = i_new
                    cool = int(round(max(2 * ramp, 4.0) / step))
                    continue
        i += 1

    C = Carrier(M + D, step)
    for f in infections:
        if f.regime == "river":
            f.xy = gen_meander(rng, grammars["river"], (f.end - f.on) * step + 5.0, omega_max=omega_max)
            f.bends = bends(f.xy)
        elif "gen" in grammars.get(f.regime, {}):
            f.xy = grammars[f.regime]["gen"](rng, (f.end - f.on) * step + 5.0)
            f.bends = bends(f.xy)

    # ---- phase B: the carrier segments between rides, element by element
    pl = grammars.get("plate") or {}
    a_pl = math.radians(pl.get("angle_deg", 0.0))
    axes = [np.array([math.cos(a_pl + q * math.pi / 2), math.sin(a_pl + q * math.pi / 2)]) for q in range(4)]
    tick_mm = pl.get("tick_mm", 1.7)
    counts = {"river_bends": 0, "rules": 0, "ticks": 0, "own": 0}

    def own_piece(i0, i1, tick_w):
        i1 = min(float(i1), len(C.p) - 1.0)
        mid = np.arange(math.floor(i0) + 1, math.ceil(i1))
        q = np.vstack([C.at(np.array([i0]))[0], C.p[mid.astype(int)], C.at(np.array([i1]))[0]])
        i0 = int(i0)
        c = np.full(len(q), OWN, float)
        if tick_w <= 1e-3 or len(q) < 3:
            return q, c
        # the plate's habit lingers: ticks on the own line, rarer as it wears off (each tick whole)
        pitch = tick_pitch / max(tick_w, 0.15)
        out, oc = [q[0]], [OWN]
        acc = float(rng.uniform(0, pitch))
        for k in range(1, len(q)):
            acc += float(np.linalg.norm(q[k] - q[k - 1]))
            out.append(q[k])
            oc.append(OWN)
            if acc >= pitch and rng.random() < tick_w:
                acc = 0.0
                nn = C.n[min(i0 + k, len(C.n) - 1)]
                out += [q[k] + nn * tick_mm, q[k]]
                oc += [TICK, TICK]
                counts["ticks"] += 1
            elif acc >= pitch:
                acc = 0.0
        return np.array(out), np.array(oc, float)

    def rule_piece(i0, i1, tick_w):
        a, b = C.at(np.array([i0]))[0][0], C.at(np.array([i1]))[0][0]
        d = b - a
        L = float(np.linalg.norm(d))
        u = d / max(L, 1e-9)
        best = max(range(4), key=lambda q: float(np.dot(axes[q], u)))
        ax = axes[best]
        dev = math.degrees(math.acos(min(max(float(np.dot(ax, u)), -1.0), 1.0)))
        run = float(np.dot(d, ax))
        corner = a + ax * run
        lead = float(np.linalg.norm(b - corner))
        if dev <= snap and 2.0 <= lead <= 0.3 * run:      # a leader shorter than 2 mm would read as a notch
            # the ruled run at the plate's angle, then a short leader back onto the own path
            pts = [a, corner, b] if np.linalg.norm(b - corner) > 0.3 else [a, b]
        else:
            pts = [a, b]
        pts = resample(np.array(pts), step)
        codes = np.full(len(pts), RULE, float)
        # ticks on the ruled run (out and back, the plate's leader length), on the left of travel
        out, oc = [pts[0]], [RULE]
        acc = float(rng.uniform(0.3, 0.8)) * tick_pitch
        tn = None
        for k in range(1, len(pts)):
            seg = pts[k] - pts[k - 1]
            sl = float(np.linalg.norm(seg))
            acc += sl
            out.append(pts[k])
            oc.append(RULE)
            if acc >= tick_pitch and k < len(pts) - 2 and rng.random() < tick_w:
                acc = 0.0
                tt = seg / max(sl, 1e-9)
                tn = np.array([tt[1], -tt[0]])
                out += [pts[k] + tn * tick_mm, pts[k]]
                oc += [TICK, TICK]
                counts["ticks"] += 1
        counts["rules"] += 1
        return np.array(out), np.array(oc, float)

    def rule_len(i0, i_max):
        """The longest straight run from i0 the own path allows (deviation ≤ rule_tol), drawn from the
        plate's rule lengths."""
        want = _lognorm(rng, pl.get("rule_mm", 28.0), 0.45)
        k1 = int(min(i0 + want / step, i_max))
        while k1 > i0 + 2:
            q = C.p[int(i0):k1 + 1]
            d = q[-1] - q[0]
            L = float(np.linalg.norm(d))
            if L > 1e-6:
                nn = np.array([-d[1], d[0]]) / L
                if float(np.max(np.abs((q - q[0]) @ nn))) <= rule_tol:
                    return k1
            k1 -= max(int(1.0 / step), 1)
        return int(i0)

    # carrier segments = maximal runs of visited indices, in order, interleaved with the rides
    segs = []
    k = 0
    while k < n:
        if not visited[k]:
            k += 1
            continue
        k0 = k
        while k < n and visited[k]:
            k += 1
        segs.append((k0, k - 1))
    ride_at = {r[0]: r for r in rides}
    top = []
    for (a, b) in segs:
        pieces = []
        i = float(a)
        while i < b - 1:
            act = [f for f in infections if f.on <= i < f.end]
            sr = {f: f.strength(i) for f in act}
            st = {f: (f.strength(i, f.linger) if f.regime == "plate" else 0.0) for f in act}
            tick_w = max(st.values(), default=0.0)
            if not act or max(sr.values()) <= 1e-3:
                nxt = min([f.on for f in infections if f.on > i] + [b])
                L = _lognorm(rng, own_mm, 0.5) / step
                i1 = min(nxt if not act or tick_w <= 1e-3 else i + L, b)
                if i1 <= i:
                    i1 = min(i + L, b)
                pieces.append(own_piece(i, i1, tick_w))
                counts["own"] += 1
                i = max(float(i1), i + 1.0)
                continue
            opts = [("own", max(1.0 - max(sr.values()), 0.0), None)] + [(f.regime, sr[f], f) for f in act]
            w = np.array([o[1] for o in opts])
            pick = opts[int(rng.choice(len(opts), p=w / w.sum()))] if w.sum() > 0 else opts[0]
            def next_bend(f):
                xi = (i - f.on) * step
                for b0, b1 in f.bends:
                    if f.xy[b0, 0] >= xi - 1e-6:
                        return b0, b1, f.on + f.xy[b0, 0] / step, f.on + f.xy[b1, 0] / step
                return None

            rivers = [f for f in act if f.xy is not None]          # bend-carried regimes (the river, a `gen`)
            bent = pick[2] is not None and pick[2].xy is not None
            if bent or (pick[0] == "own" and rivers and len(act) == 1):
                # elements of a river infection are whole bends: a bend is drawn, or shed whole (the own
                # path runs through its span), never shrunk
                f = pick[2] if bent else rivers[0]
                nb = next_bend(f)
                if nb is not None and nb[3] <= b:
                    b0, b1, s0, s1 = nb
                    amp = float(np.max(np.abs(f.xy[b0:b1 + 1, 1])))
                    # the own path's mean curvature over the bend's span (± half a bend) × the bend's amplitude:
                    # above 0.35 the mapped bend would fold into a knot, so it is shed instead
                    pad = 0.5 * (s1 - s0)
                    ka, kb = int(max(s0 - pad, 0)), int(min(s1 + pad, len(C.t) - 1))
                    hd = np.unwrap(np.arctan2(C.t[ka:kb + 1, 1], C.t[ka:kb + 1, 0]))
                    curv = float(np.sum(np.abs(np.diff(hd)))) / max((kb - ka) * step, 1e-6) if kb - ka > 2 else 0.0
                    tight = curv * amp > 0.35
                    if bent and not tight:
                        if s0 > i + 0.5:
                            pieces.append(own_piece(i, s0, tick_w))
                        q = C.map(f.on, f.xy[b0:b1 + 1])
                        q[0] = C.at(np.array([s0]))[0][0]
                        q[-1] = C.at(np.array([s1]))[0][0]
                        pieces.append((q, np.full(len(q), grammars.get(f.regime, {}).get("code", RIVER), float)))
                        counts["river_bends"] += 1
                    else:
                        pieces.append(own_piece(i, s1, tick_w))
                        counts["own"] += 1
                    i = max(float(s1), i + 1.0)
                    continue
                L = _lognorm(rng, own_mm, 0.5) / step
                pieces.append(own_piece(i, min(i + L, b), tick_w))
                i = max(float(min(i + L, b)), i + 1.0)
                continue
            if pick[0] == "plate":
                # while a second regime is carried too, a ruled run is one element among others: it is
                # cut to `rule_shared` mm, so the two grammars alternate instead of one swallowing the other
                cap = b if len(act) == 1 else min(b, i + rule_shared / step)
                k1 = rule_len(i, cap)
                if (k1 - i) * step >= 6.0:
                    pieces.append(rule_piece(i, k1, max(tick_w, 0.0)))
                    i = max(float(k1), i + 1.0)
                    continue
            L = _lognorm(rng, own_mm, 0.5) / step
            pieces.append(own_piece(i, min(i + L, b), tick_w))
            counts["own"] += 1
            i = max(float(min(i + L, b)), i + 1.0)
        if b - i > 0.05:
            pieces.append(own_piece(i, b, 0.0))
        seg_pts, seg_c = _cat(pieces)
        top.append((seg_pts, seg_c))
        r = ride_at.get(b)
        if r is not None:
            rc = grammars.get(r[3], {}).get("ride_code", RIDE_RIVER if r[3] == "river" else RIDE_PLATE)
            top.append((r[2], np.full(len(r[2]), rc, float)))
    pts, codes = _join(top, ramp, step)

    def where(fi):
        return np.round(C.at(np.array([fi]))[0][0], 2).tolist()
    log = {"infections": [{"regime": f.regime, **f.meta, "onset": where(f.on),
                           "on_mm": round(f.on * step, 1), "end_mm": round(min(f.end, n - 1) * step, 1),
                           "full_mm": round(f.full, 1), "decay_mm": round(f.decay, 1),
                           "full_end": where(f.on + f.full / step), "end": where(min(f.end, n - 1)),
                           "carried_mm": round((min(f.end, n - 1) - f.on) * step, 1)} for f in infections],
           "counts": counts, "contacts_only": contacts}
    return pts, codes, log


# ---------------------------------------------------------------------------
# the arranger
# ---------------------------------------------------------------------------

def _regime_of(md: dict) -> str | None:
    if str(md.get("found", "")).startswith("grwl"):
        return "river"
    if md.get("plate_role") == "rule":
        return "plate"
    return None


@arranger("contagion", params=[
    P("found", "int", 2, "the first n parts are found layers (plate, river), the rest are late lines", min=0, max=6),
    P("found_boxes", "floats", [0.5, 0.5, 0.9, 0.9, 0.0],
      "per found part: cx, cy, w, h (shares of the frame) and angle (deg) of its pasted rectangle"),
    P("crop", "float", 1.0, "found content grown to fill its rectangle ÷ crop, then cut to it", min=0.6, max=2.5),
    P("late_box", "floats", [], "late lines' box: cx, cy, w, h shares (empty = the sheet box)"),
    P("regimes", "choice", "both", "which regimes can be caught", choices=("both", "river", "plate", "none")),
    P("catch", "choice", "catch", "catch: contact, then the grammar is carried | ride: found ground's ride only, "
      "nothing carried (the control)", choices=("catch", "ride")),
    P("step", "float", 0.3, "resampling step, mm", min=0.1, max=1.0),
    P("capture", "float", 4.0, "a found contour this near (mm) and aligned can infect the line", min=0.2, max=30.0),
    P("align", "float", 0.5, "|cos| between headings needed for contact", min=0.0, max=1.0),
    P("listen", "float", 60.0, "mean listening window, mm of own line", min=1.0, max=500.0),
    P("ignore", "float", 60.0, "mean ignoring window, mm of own line", min=0.0, max=1000.0),
    P("ride", "float", 14.0, "mean contact ride, mm", min=1.0, max=200.0),
    P("ride_sd", "float", 0.4, "log-normal spread of rides, windows, durations", min=0.0, max=1.5),
    P("min_ride", "float", 6.0, "shorter contacts are refused, mm", min=0.5, max=100.0),
    P("ride_gap", "float", 0.9, "the contact ride traces this far beside the found contour, mm", min=0.0, max=5.0),
    P("return_mm", "float", 30.0, "after the contact, the line swims back to its own path over this, mm",
      min=1.0, max=400.0),
    P("ramp", "float", 2.0, "tangent bridge into and out of a contact, mm", min=0.0, max=20.0),
    P("max_offset", "float", 18.0, "a contact ride ends before it carries the line this far from its path, mm",
      min=1.0, max=300.0),
    P("catches", "int", 3, "most infections per line", min=0, max=20),
    P("full_river", "float", 45.0, "river infection at full strength, mm of own path", min=0.0, max=600.0),
    P("decay_river", "float", 80.0, "river infection wearing off, mm of own path", min=1.0, max=600.0),
    P("full_plate", "float", 35.0, "plate infection at full strength, mm of own path", min=0.0, max=600.0),
    P("decay_plate", "float", 40.0, "plate infection wearing off (the ruling), mm", min=1.0, max=600.0),
    P("tick_linger", "float", 2.0, "the plate's ticks outlast its ruling by this factor", min=1.0, max=5.0),
    P("immune_mm", "float", 60.0, "after an infection ends the line cannot re-catch that regime for this long, mm",
      min=0.0, max=500.0),
    P("own_mm", "float", 6.0, "own stretches between caught elements while wearing off, mean mm", min=1.0, max=60.0),
    P("rule_tol", "float", 3.5, "a ruled run may straighten the own path by this much, mm", min=0.2, max=20.0),
    P("snap", "float", 20.0, "a ruled run within this many degrees of the plate's ruling (or its leaders') is "
      "drawn at that angle, then an elbow back", min=0.0, max=45.0),
    P("rule_shared", "float", 9.0, "while two regimes are carried, a ruled run is at most this long, mm",
      min=6.0, max=200.0),
    P("tick_pitch", "float", 6.3, "ticks on a ruled run, mm apart (a quarter of the plate's column pitch)",
      min=1.0, max=60.0),
    P("omega_max", "float", 120.0, "a carried river's bends swing at most this far from its axis, deg",
      min=30.0, max=160.0),
    P("river_axis", "float", 10.0, "valley scale the river's heading is measured about, mm", min=3.0, max=60.0),
    P("found_ink", "str", "blue", "Flexoki pen for the found layer"),
    P("found_pen", "float", 0.3, "found pen, mm", min=0.05, max=3.0),
    P("late_ink", "str", "black", "Flexoki pen for the late line"),
    P("late_pen", "float", 0.7, "late pen, mm", min=0.05, max=3.0),
], doc="I-c contagion: touching a found regime infects the line with that regime's grammar, carried whole along "
        "its own path, then shed; a second regime can be caught while carrying the first")
def contagion(ctx, parts, *, found, found_boxes, crop, late_box, regimes, catch, step, capture, align, listen,
              ignore, ride, ride_sd, min_ride, ride_gap, return_mm, ramp, max_offset, catches, full_river,
              decay_river, full_plate, decay_plate, tick_linger, immune_mm, own_mm, rule_tol, snap, tick_pitch,
              rule_shared, omega_max, river_axis, found_ink, found_pen, late_ink, late_pen):
    for nm in (found_ink, late_ink):
        if nm not in FLEXOKI:
            raise ValueError(f"contagion: unknown ink {nm!r}; choose from {sorted(FLEXOKI)}")
    W, H = ctx.frame
    found = min(found, len(parts))
    f_parts, l_parts = parts[:found], parts[found:]
    boxes = frac_boxes(found_boxes, ctx.frame, 5)
    out: list[Mark] = []
    found_lines = []
    for k, p in enumerate(f_parts):
        cx, cy, bw, bh, ang = boxes[min(k, len(boxes) - 1)] if boxes else (0.5, 0.5, 0.9, 0.9, 0.0)
        cx, cy, bw, bh = cx * W, cy * H, bw * W, bh * H
        ms = p.run((cx - bw * crop / 2, cy - bh * crop / 2, bw * crop, bh * crop))
        rect = rect_polygon(cx, cy, bw, bh, ang)
        for m in ms:
            q = rotate(m.points, np.array([cx, cy]), ang)
            md = {kk: m.meta[kk] for kk in ("plate_role", "measure_role", "found") if kk in m.meta}
            for piece in clip_rect([q], rect, 4.0):
                found_lines.append((p.index, piece, md))
    for pi, l, md in found_lines:
        out.append(make_mark(l, "found", found_ink, found_pen, pi, md))

    by = {r: [l for _, l, md in found_lines if _regime_of(md) == r] for r in REGIMES}
    grammars = {}
    if by["river"]:
        grammars["river"] = river_grammar(by["river"], axis_mm=river_axis, omega_max=omega_max)
    if by["plate"]:
        grammars["plate"] = plate_grammar(by["plate"], [l for _, l, md in found_lines
                                                        if md.get("plate_role") == "label"])
    use = {"both": REGIMES, "river": ("river",), "plate": ("plate",), "none": ()}[regimes]
    grounds = {r: Ground(by[r], step, tag=1 + REGIMES.index(r)) for r in use if by[r]}
    log = {"grammars": grammars, "lines": []}
    if late_box and len(late_box) >= 4:
        cx, cy, bw, bh = late_box[:4]
        lbox = (cx * W - bw * W / 2, cy * H - bh * H / 2, bw * W, bh * H)
    else:
        lbox = ctx.box
    for p in l_parts:
        for mi, m in enumerate(p.run(lbox)):
            rng = ctx.rng("contagion", p.index, mi)
            fl = {"river": full_river, "plate": full_plate}
            dc = {"river": decay_river, "plate": decay_plate}
            pts, codes, lg = contagion_walk(
                m.points, grounds, grammars, rng, step=step, capture=capture, align=align, listen=listen,
                ignore=ignore, ride=ride, ride_sd=ride_sd, min_ride=min_ride, ride_gap=ride_gap,
                return_mm=return_mm, ramp=ramp, max_offset=max_offset, catches=catches, full=fl, decay=dc,
                tick_linger=tick_linger, own_mm=own_mm, rule_tol=rule_tol, snap=snap, tick_pitch=tick_pitch,
                immune_mm=immune_mm, omega_max=omega_max, rule_shared=rule_shared,
                regimes=tuple(grounds), carry=(catch == "catch"))
            lg.update(part=p.index, mark=mi, own=np.round(resample(m.points, 1.0), 2).tolist())
            log["lines"].append(lg)
            out.append(Mark(pts, {"catch": codes}, {"part": p.index, "of_role": "late", "ink": late_ink,
                                                     "pen": late_pen}))
    if out:
        out[0] = out[0].evolve(meta={"contagion": log})
    return out
