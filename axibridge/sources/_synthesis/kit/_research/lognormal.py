# FROZEN from research commit d5ccd75: tools/gesture/gesture/lognormal.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Kinematic hand model: sigma-lognormal pulses (results/lognormal-2026-10-16.md).

An alternative to the clothoid alphabet (representation A). The Kinematic
Theory (Plamondon) models a skilled pen trajectory as a sum of overlapping
**lognormal velocity pulses**. Pulse j has onset t0, log-time delay μ,
log-response time σ, amplitude D (the distance it travels) and a direction
that rotates linearly with its own progress from θs to θe, so a lone pulse
draws a circular arc of length D turning by θe − θs:

    |v_j(t)| = D · Λ'(t; t0, μ, σ)          (lognormal pdf in t − t0)
    φ_j(t)   = θs + (θe − θs) · Λ(t; t0, μ, σ)   (Λ = lognormal cdf)
    v(t)     = Σ_j |v_j(t)| · (cos φ_j, sin φ_j)

Overlap between successive pulses is what turns a chain of arcs into a
smooth line — corners appear only when one pulse ends before the next one
starts in a different direction.

**Kinematics from a static trace.** A scan has no timing, so `reconstruct_timing`
assumes the 2/3 power law (speed ∝ (|κ|·R + κ0)^(−1/3), κ0 = `KAPPA0`
regularising straight runs), with a start/end ramp, after smoothing the
polyline at σ (the grammar's 2 line widths). Speed minima then sit at
curvature maxima — the landmark placement of Berio, Leymarie & Plamondon
(*Kinematics reconstruction of static calligraphic traces from curvilinear
shape features*) — and `fit_stroke` puts one pulse per speed-peak segment,
refines all six parameters per pulse by least squares on velocity and
position (analytic Jacobian), and greedily adds a pulse where the residual is
largest while the velocity SNR is below `SNR_TARGET`.

**A hand** (`learn`) is the per-artist distribution over pulse sequences, in
a rotation- and time-scale-free relative form per pulse (Berio's Δt
parametrisation): ``[lD, dth, sig, dt, lT, jump]`` = log(D/R), θe − θs, σ,
onset delay ÷ previous pulse duration, log duration ratio to the previous
pulse, θs − previous θe (wrapped). Duration T is the ±3σ span, so
μ = 3σ − ln((e^{6σ} − 1)/T). The sequence model is a non-parametric order-2
chain: the next pulse is drawn from the K nearest training transitions in a
context of (previous pulse, the one before it, position u along the stroke).

**Generation** (`generate_drawing`): lines are grown pulse by pulse from the
chain (`_Line`: incremental synthesis — appending a pulse only changes the
trajectory after its onset), K proposals per step, the first in draw order
that stays on the sheet and clear of other ink is kept (rejection sampling,
as grammar v3 does with tokens). Layout reuses grammar v3's learned
relations (attach share, branch angle, free-start gaps, crossing rate) via
`grammar_v3_frozen`. ``mode="single"`` draws one line with backtracking.

Pure and deterministic: inputs never mutated; randomness via np.random.Generator.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from scipy.signal import find_peaks
from scipy.spatial import cKDTree
from scipy.special import erf

from . import grammar_v3_frozen as g3
from .core import Drawing, Stroke
from .curvature import arclength, curvature, resample, smooth

COLS = ("t0", "mu", "sigma", "D", "theta_s", "theta_e")
REL = ("lD", "dth", "sig", "dt", "lT", "jump")
SIGMA_MIN, SIGMA_MAX = 0.08, 0.7
SUPPORT_Z = 3.0          # pulse support / duration T = the ±3σ span
KAPPA0 = 2.0             # power-law regulariser, in κ·R units
BETA = 1.0 / 3.0         # 2/3 power law: speed ∝ κ^(−1/3)
SNR_TARGET = 20.0        # dB, velocity SNR at which pulse adding stops
SIGMA_W = g3.SIGMA_W     # fit smoothing, line widths (same as the grammar)
POS_WEIGHT = 1.0         # position residual weight (relative to velocity)
KNN = 10
JITTER = 0.05            # chain jitter, fraction of each relative dim's std
CLEAR_W = g3.CLEAR_W
MAX_PULSES_LINE = 600
SQ2PI = np.sqrt(2 * np.pi)


# ---------------------------------------------------------------------------
# the model: pulses → velocity → trajectory
# ---------------------------------------------------------------------------

def _P(P) -> np.ndarray:
    P = np.array(P, dtype=np.float64, copy=True)
    return P.reshape(-1, 6)


def duration(P) -> np.ndarray:
    """±3σ time span of each pulse."""
    P = _P(P)
    return np.exp(P[:, 1]) * (np.exp(SUPPORT_Z * P[:, 2]) - np.exp(-SUPPORT_Z * P[:, 2]))


def mu_from(T, sigma):
    """μ such that the ±3σ span is T."""
    sigma = np.asarray(sigma, float)
    return SUPPORT_Z * sigma - np.log(np.expm1(2 * SUPPORT_Z * sigma) / np.asarray(T, float))


def support(P) -> np.ndarray:
    """(n, 2) start / end time of each pulse's ±3σ span."""
    P = _P(P)
    return np.column_stack([P[:, 0] + np.exp(P[:, 1] - SUPPORT_Z * P[:, 2]),
                            P[:, 0] + np.exp(P[:, 1] + SUPPORT_Z * P[:, 2])])


def peak_speed(P) -> np.ndarray:
    P = _P(P)
    return P[:, 3] * np.exp(-0.5 * P[:, 2] ** 2) / (P[:, 2] * SQ2PI * np.exp(P[:, 1] - P[:, 2] ** 2))


def _terms(P, t):
    tau = t[None, :] - P[:, 0:1]
    pos = tau > 0
    ts = np.where(pos, tau, 1.0)
    z = (np.log(ts) - P[:, 1:2]) / P[:, 2:3]
    g = np.where(pos, np.exp(-0.5 * z * z) / (P[:, 2:3] * SQ2PI * ts), 0.0)
    Phi = np.where(pos, 0.5 * (1.0 + erf(z / np.sqrt(2.0))), 0.0)
    return pos, ts, z, g, Phi


def velocity(P, t) -> np.ndarray:
    """(M, 2) velocity at times t (dense; fine for a few dozen pulses)."""
    P = _P(P)
    t = np.asarray(t, float)
    if not len(P):
        return np.zeros((len(t), 2))
    _pos, _ts, _z, g, Phi = _terms(P, t)
    phi = P[:, 4:5] + (P[:, 5:6] - P[:, 4:5]) * Phi
    sp = P[:, 3:4] * g
    return np.column_stack([(sp * np.cos(phi)).sum(0), (sp * np.sin(phi)).sum(0)])


def velocity_sparse(P, t) -> np.ndarray:
    """velocity() evaluated per pulse on its own support only (t sorted)."""
    P = _P(P)
    t = np.asarray(t, float)
    v = np.zeros((len(t), 2))
    sup = support(P)
    for j in range(len(P)):
        a, b = np.searchsorted(t, sup[j, 0]), np.searchsorted(t, sup[j, 1], side="right")
        if b > a:
            v[a:b] += velocity(P[j:j + 1], t[a:b])
    return v


def _cumtrapz(v: np.ndarray, t: np.ndarray) -> np.ndarray:
    dt = np.diff(t)
    inc = 0.5 * (v[1:] + v[:-1]) * dt[:, None]
    return np.vstack([np.zeros((1, v.shape[1])), np.cumsum(inc, axis=0)])


def trajectory(P, t, start=(0.0, 0.0)) -> np.ndarray:
    """Positions at times t, x(t[0]) = start."""
    return np.asarray(start, float)[None, :] + _cumtrapz(velocity_sparse(P, t), np.asarray(t, float))


def time_grid(P, step: float, t_from: float | None = None, t_to: float | None = None,
              max_n: int = 60_000) -> np.ndarray:
    """Uniform time grid fine enough that no pulse moves more than step/2
    per sample and every pulse gets ≥ 60 samples over its span."""
    P = _P(P)
    P = P[np.all(np.isfinite(P), axis=1) & np.isfinite(duration(P)) & (duration(P) > 0)]
    sup = support(P)
    a = float(sup[:, 0].min()) if t_from is None else t_from
    b = float(sup[:, 1].max()) if t_to is None else t_to
    dt = min(float(np.min(0.5 * step / np.maximum(peak_speed(P), 1e-12))),
             float(np.min(duration(P))) / 60.0)
    n = int(np.clip(np.ceil((b - a) / max(dt, 1e-12)), 2, max_n)) + 1
    return np.linspace(a, b, n)


def synthesize(P, step: float, start=(0.0, 0.0)) -> np.ndarray:
    """Pulses → (N, 2) polyline at ~uniform arc-length spacing `step`."""
    P = _P(P)
    if not len(P):
        return np.asarray(start, float)[None, :].copy()
    t = time_grid(P, step)
    x = trajectory(P, t, start)
    return _uniform(x, step)


def _uniform(x: np.ndarray, step: float) -> np.ndarray:
    s = arclength(x)
    if s[-1] <= step:
        return x[[0, -1]].copy() if len(x) > 1 else x.copy()
    return resample(x, step)


def random_pulses(rng, n: int, *, D=(40.0, 160.0), T=(0.25, 0.6), sigma=(0.15, 0.45),
                  dt=(0.25, 0.6), dth=(-1.4, 1.4), jump=(-0.6, 0.6)) -> np.ndarray:
    """Known pulses for ground truth (relative-parameter ranges)."""
    rows = []
    for j in range(n):
        rows.append([np.log(rng.uniform(*D)), rng.uniform(*dth), rng.uniform(*sigma),
                     rng.uniform(*dt) if j else 0.0, np.log(rng.uniform(*T)) if j else 0.0,
                     rng.uniform(*jump) if j else 0.0])
    rows = np.array(rows)
    rows[0, 4] = np.log(rng.uniform(*T))
    rows[1:, 4] = rows[0, 4] + np.cumsum(rows[1:, 4])
    return rows_to_pulses(rows, 1.0, theta0=float(rng.uniform(0, 2 * np.pi)))


# ---------------------------------------------------------------------------
# relative (hand) form
# ---------------------------------------------------------------------------

def _wrap(a):
    return (np.asarray(a) + np.pi) % (2 * np.pi) - np.pi


def pulses_to_rows(P, R: float) -> np.ndarray:
    """Absolute pulses (sorted by onset) → relative rows REL. Row 0 has
    dt = jump = 0. lT is log(T / the stroke's median T): stationary, so a
    generated chain does not drift in time scale."""
    P = _P(P)
    P = P[np.argsort(P[:, 0], kind="stable")]
    T = duration(P)
    rows = np.zeros((len(P), 6))
    rows[:, 0] = np.log(np.maximum(P[:, 3], 1e-12) / R)
    rows[:, 1] = P[:, 5] - P[:, 4]
    rows[:, 2] = P[:, 2]
    if len(P) > 1:
        rows[1:, 3] = (P[1:, 0] - P[:-1, 0]) / T[:-1]
        rows[1:, 5] = _wrap(P[1:, 4] - P[:-1, 5])
    rows[:, 4] = np.log(T / np.median(T))
    return rows


def next_pulse(prev: np.ndarray, row, R: float) -> np.ndarray:
    """The absolute pulse that follows `prev` under relative row `row`."""
    lD, dth, sig, dt, lT, jump = row
    Tp = float(duration(prev)[0])
    T = float(np.exp(lT))
    sig = float(np.clip(sig, SIGMA_MIN, SIGMA_MAX))
    mu = float(mu_from(T, sig))
    ths = float(prev[5] + jump)
    return np.array([prev[0] + dt * Tp, mu, sig, R * np.exp(lD), ths, ths + dth])


def first_pulse(row, R: float, theta0: float) -> np.ndarray:
    sig = float(np.clip(row[2], SIGMA_MIN, SIGMA_MAX))
    return np.array([0.0, float(mu_from(np.exp(row[4]), sig)), sig, R * np.exp(row[0]), theta0, theta0 + row[1]])


def rows_to_pulses(rows, R: float, theta0: float = 0.0) -> np.ndarray:
    rows = np.asarray(rows, float)
    out = []
    for j, r in enumerate(rows):
        out.append(first_pulse(r, R, theta0) if j == 0 else next_pulse(out[-1], r, R))
    return np.array(out).reshape(-1, 6)


# ---------------------------------------------------------------------------
# kinematics from a static trace + fitting
# ---------------------------------------------------------------------------

def reconstruct_timing(points, *, sigma: float, R: float, kappa0: float = KAPPA0,
                       beta: float = BETA, ramp: float | None = None):
    """Smooth at σ, then assign speed by the power law and integrate time.
    Returns (t, smoothed points, speed) on a uniform arc-length grid."""
    step = max(sigma / 4.0, 1e-6)
    r = resample(np.asarray(points, float), step)
    sm = smooth(r, sigma, step) if len(r) >= 3 else r
    k = curvature(sm, step) if len(sm) >= 3 else np.zeros(len(sm))
    s = arclength(sm)
    L = s[-1]
    v = R * (np.abs(k) * R + kappa0) ** (-beta)
    ell = min(0.1 * L, 3.0 * sigma) if ramp is None else ramp
    if ell > 0:
        f = np.minimum(np.minimum(s, L - s) / ell, 1.0)
        v = v * (0.15 + 0.85 * np.sin(0.5 * np.pi * f) ** 2)
    dt = np.diff(s) / (0.5 * (v[1:] + v[:-1]))
    t = np.concatenate([[0.0], np.cumsum(dt)])
    return t, sm, v


@dataclass(frozen=True)
class LognormalFit:
    pulses: np.ndarray        # (n, 6) COLS, absolute (px, time units of the timing model)
    t: np.ndarray             # (M,) uniform time samples of the target
    target: np.ndarray        # (M, 2) target positions
    fitted: np.ndarray        # (M, 2) fitted positions
    snr_v: float              # velocity SNR, dB
    err_mean: float           # mean symmetric nearest distance fitted ↔ target, px
    err_max: float            # max of the same, px
    length: float             # target arc length, px

    @property
    def n(self) -> int:
        return len(self.pulses)


def _sig_of(q):
    return SIGMA_MIN + (SIGMA_MAX - SIGMA_MIN) / (1.0 + np.exp(-np.clip(q, -40, 40)))


def _q_of(sig):
    f = np.clip((np.asarray(sig, float) - SIGMA_MIN) / (SIGMA_MAX - SIGMA_MIN), 1e-6, 1 - 1e-6)
    return np.log(f / (1 - f))


def _x_to_P(x):
    X = x.reshape(-1, 6)
    return np.column_stack([X[:, 0], X[:, 1], _sig_of(X[:, 2]), np.exp(X[:, 3]), X[:, 4], X[:, 5]])


def _P_to_x(P):
    P = _P(P)
    return np.column_stack([P[:, 0], P[:, 1], _q_of(P[:, 2]), np.log(np.maximum(P[:, 3], 1e-9)),
                            P[:, 4], P[:, 5]]).ravel()


def _residual_and_jac(x, t, v_tgt, x_tgt, vs, xs, wpos, L, wD):
    P = _x_to_P(x)
    n, M = len(P), len(t)
    pos, ts, z, g, Phi = _terms(P, t)
    dPhi = np.where(pos, np.exp(-0.5 * z * z) / SQ2PI, 0.0)    # n(z)
    Dl = P[:, 5:6] - P[:, 4:5]
    phi = P[:, 4:5] + Dl * Phi
    sp = P[:, 3:4] * g
    c, s = np.cos(phi), np.sin(phi)
    vx, vy = (sp * c).sum(0), (sp * s).sum(0)
    sig = P[:, 2:3]
    dsig = (sig - SIGMA_MIN) * (SIGMA_MAX - sig) / (SIGMA_MAX - SIGMA_MIN)
    # d ln g and dφ per parameter (t0, μ, q[σ], logD, θs, θe)
    dlng = [np.where(pos, z / (sig * ts) + 1.0 / ts, 0.0), np.where(pos, z / sig, 0.0),
            np.where(pos, (z * z - 1.0) / sig * dsig, 0.0), np.where(pos, 1.0, 0.0), None, None]
    dphi = [Dl * dPhi * (-1.0 / (sig * ts)), Dl * dPhi * (-1.0 / sig), Dl * dPhi * (-z / sig * dsig),
            None, np.where(pos, 1.0 - Phi, 0.0), np.where(pos, Phi, 0.0)]
    Jx = np.zeros((M, n * 6))
    Jy = np.zeros((M, n * 6))
    for k in range(6):
        a = sp * dlng[k] if dlng[k] is not None else 0.0
        b = sp * dphi[k] if dphi[k] is not None else 0.0
        Jx[:, k::6] = (a * c - b * s).T
        Jy[:, k::6] = (a * s + b * c).T
    v = np.column_stack([vx, vy])
    X = x_tgt[0] + _cumtrapz(v, t)
    # ΣD ≥ path length always; the excess is pulses cancelling each other
    rD = wD * (P[:, 3].sum() - L) / L
    r = np.concatenate([(vx - v_tgt[:, 0]) / vs, (vy - v_tgt[:, 1]) / vs,
                        wpos * (X[:, 0] - x_tgt[:, 0]) / xs, wpos * (X[:, 1] - x_tgt[:, 1]) / xs, [rD]])
    JX = _cumtrapz(Jx, t)
    JY = _cumtrapz(Jy, t)
    jD = np.zeros((1, n * 6))
    jD[0, 3::6] = wD * P[:, 3] / L
    J = np.vstack([Jx / vs, Jy / vs, wpos * JX / xs, wpos * JY / xs, jD])
    return r, J


def _init_pulses(t, x, v, *, prominence=0.03):
    """One pulse per speed-peak segment between speed minima (landmarks)."""
    sp = np.linalg.norm(v, axis=1)
    mins, _ = find_peaks(-sp, prominence=prominence * float(sp.max() + 1e-12))
    b = [0] + [int(i) for i in mins] + [len(t) - 1]
    b = [b[0]] + [i for i, j in zip(b[1:-1], b[:-2]) if i - j >= 3] + [b[-1]]
    ang = np.unwrap(np.arctan2(v[:, 1], v[:, 0]))
    pulses = []
    for a, e in zip(b[:-1], b[1:]):
        if e - a < 2:
            continue
        seg = slice(a, e + 1)
        tp = t[a + int(np.argmax(sp[seg]))]
        span = max(2.0 * (t[e] - t[a]), 1e-6)
        sig = 0.35
        mu = float(mu_from(span, sig))
        t0 = tp - np.exp(mu - sig * sig)
        D = float(np.sum(np.linalg.norm(np.diff(x[seg], axis=0), axis=1)))
        ia, ie = min(a + 1, e), max(e - 1, a)
        pulses.append([t0, mu, sig, max(D, 1e-6), ang[ia], ang[ie]])
    if not pulses:
        D = float(np.sum(np.linalg.norm(np.diff(x, axis=0), axis=1)))
        span = 2.0 * (t[-1] - t[0])
        mu = float(mu_from(span, 0.35))
        pulses = [[t[0] + 0.5 * (t[-1] - t[0]) - np.exp(mu - 0.35 ** 2), mu, 0.35, D, ang[0], ang[-1]]]
    return np.array(pulses)


def _shape_err(a: np.ndarray, b: np.ndarray, step: float) -> tuple[float, float]:
    A, B = _uniform(a, step), _uniform(b, step)
    da = cKDTree(B).query(A)[0]
    db = cKDTree(A).query(B)[0]
    d = np.concatenate([da, db])
    return float(d.mean()), float(d.max())


def fit_velocity(t, x, *, init=None, prominences=(0.03,), snr_target: float = SNR_TARGET,
                 **kw) -> tuple[np.ndarray, dict]:
    """Fit pulses to a timed trajectory (uniform t). Multi-start over the
    landmark prominence: of the starts that reach `snr_target`, the one with
    the fewest pulses (then highest SNR) wins; else the highest SNR."""
    if init is not None:
        return _fit_velocity(t, x, init=init, snr_target=snr_target, **kw)
    best = None
    for pr in prominences:
        P, info = _fit_velocity(t, x, prominence=pr, snr_target=snr_target, **kw)
        key = (info["snr_v"] >= snr_target, -len(P), info["snr_v"])
        if best is None or key > best[0]:
            best = (key, P, {**info, "prominence": pr})
    return best[1], best[2]


def _fit_velocity(t, x, *, init=None, prominence: float = 0.03, snr_target: float = SNR_TARGET,
                  max_pulses: int = 80,
                 max_add: int = 4, max_nfev: int = 40, wpos: float = POS_WEIGHT, wD: float = 1.0,
                 prune: float = 0.005) -> tuple[np.ndarray, dict]:
    """Fit pulses to a timed trajectory (uniform t). Returns (pulses, info)."""
    t = np.asarray(t, float)
    x = np.asarray(x, float)
    v = np.gradient(x, t, axis=0)
    P = _init_pulses(t, x, v, prominence=prominence) if init is None else _P(init)
    L = float(np.sum(np.linalg.norm(np.diff(x, axis=0), axis=1)))
    vs = float(np.sqrt(np.mean(np.sum(v * v, axis=1)))) + 1e-12
    xs = max(0.02 * L, 1e-9)
    info = {"rounds": 0}

    def solve(P):
        x0 = _P_to_x(P)
        cache = {}

        def fun(xx):
            r, J = _residual_and_jac(xx, t, v, x, vs, xs, wpos, L, wD)
            cache["J"], cache["x"] = J, xx.copy()
            return r

        def jac(xx):
            if "x" in cache and np.array_equal(cache["x"], xx):
                return cache["J"]
            return _residual_and_jac(xx, t, v, x, vs, xs, wpos, L, wD)[1]

        res = least_squares(fun, x0, jac=jac, method="lm", x_scale="jac", max_nfev=max_nfev)
        Pn = _x_to_P(res.x)
        keep = Pn[:, 3] >= prune * L
        return Pn[keep] if keep.any() else Pn

    P = solve(P)
    for _ in range(max_add):
        vh = velocity(P, t)
        snr = 10 * np.log10(np.sum(v * v) / max(np.sum((vh - v) ** 2), 1e-300))
        if snr >= snr_target or len(P) >= max_pulses:
            break
        info["rounds"] += 1
        e = vh - v
        en = np.linalg.norm(e, axis=1)
        k = max(len(t) // max(4 * len(P), 8), 2)
        en_s = np.convolve(en, np.ones(k) / k, mode="same")
        pk, _ = find_peaks(en_s, distance=4 * k)
        pk = pk[np.argsort(en_s[pk])[::-1]][:3] if len(pk) else [int(np.argmax(en_s))]
        dtg = np.gradient(t)
        new = []
        for i in pk:
            a, b = max(i - 2 * k, 0), min(i + 2 * k, len(t) - 1)
            D = float(np.sum(np.linalg.norm(e[a:b], axis=1) * dtg[a:b]))
            ang = float(np.arctan2(-e[i, 1], -e[i, 0]))
            span = max(2.0 * (t[b] - t[a]), 1e-6)
            mu = float(mu_from(span, 0.35))
            new.append([t[i] - np.exp(mu - 0.35 ** 2), mu, 0.35, max(D, 1e-6), ang, ang])
        P = solve(np.vstack([P, np.array(new)]))
    vh = velocity(P, t)
    info["snr_v"] = float(10 * np.log10(np.sum(v * v) / max(np.sum((vh - v) ** 2), 1e-300)))
    return P[np.argsort(P[:, 0], kind="stable")], info


def fit_stroke(points, *, sigma: float, R: float, M: int | None = None, **kw) -> LognormalFit:
    """Static polyline (px) → sigma-lognormal pulses. σ: smoothing (px);
    R: the drawing's reference length (power-law units)."""
    t, sm, _v = reconstruct_timing(points, sigma=sigma, R=R)
    L = float(arclength(sm)[-1])
    if M is None:
        M = int(np.clip(L / max(sigma, 1e-9), 60, 500))
    tu = np.linspace(0.0, t[-1], M)
    xu = np.column_stack([np.interp(tu, t, sm[:, 0]), np.interp(tu, t, sm[:, 1])])
    P, info = fit_velocity(tu, xu, **kw)
    fitted = xu[0] + _cumtrapz(velocity(P, tu), tu)
    em, ex = _shape_err(fitted, xu, max(sigma / 4.0, 0.25))
    return LognormalFit(pulses=P, t=tu, target=xu, fitted=fitted, snr_v=info["snr_v"],
                        err_mean=em, err_max=ex, length=L)


def fit_drawing(drawing: Drawing, *, sigma_w: float = SIGMA_W, select: bool = True,
                min_len_sigma: float = 4.0, max_strokes: int | None = None, seed: int = 0) -> dict:
    """Fit every long stroke (grammar v3's selection) of a drawing. JSON-native
    result: R, w, per-stroke pulses + fit metrics + start/heading, relations."""
    d = g3.long_drawing(drawing) if select else drawing
    R = d.ref_length()
    w = g3.drawing_width(d) if d.strokes else 1.0
    out = {"source": drawing.source, "size": list(drawing.size), "R": float(R), "w": float(w),
           "sigma_w": sigma_w, "strokes": []}
    if not d.strokes:
        out["relations"] = g3.relations([], R, w)
        return out
    allp = np.vstack([s.points for s in d.strokes])
    lo, span = allp.min(axis=0), np.maximum(np.ptp(allp, axis=0), 1e-9)
    order = list(range(len(d.strokes)))
    if max_strokes is not None and len(order) > max_strokes:     # unbiased random subset
        order = sorted(np.random.default_rng(seed).choice(len(order), max_strokes, replace=False).tolist())
    out["n_long"] = len(d.strokes)
    for idx in order:
        st = d.strokes[idx]
        sw = g3.stroke_width(st, d)
        sg = sigma_w * sw
        if len(st) < 3 or st.length() < min_len_sigma * sg:
            continue
        pts = np.vstack([st.points, st.points[:1]]) if st.closed else st.points
        try:
            f = fit_stroke(pts, sigma=sg, R=R)
        except Exception:  # noqa: BLE001 — a failed fit drops the stroke
            continue
        if not np.all(np.isfinite(f.pulses)):
            continue
        out["strokes"].append({
            "pulses": f.pulses.round(7).tolist(), "rows": pulses_to_rows(f.pulses, R).round(6).tolist(),
            "length": f.length / R, "n": f.n, "snr_v": round(f.snr_v, 3),
            "err_w": round(f.err_mean / max(sw, 1e-9), 4), "err_rel": f.err_mean / max(f.length, 1e-9),
            "errmax_w": round(f.err_max / max(sw, 1e-9), 4), "w": sw,
            "start": [round(float(v), 4) for v in (st.points[0] - lo) / span], "idx": int(idx)})
    out["relations"] = g3.relations(d.strokes, R, w)
    return out


# ---------------------------------------------------------------------------
# the hand
# ---------------------------------------------------------------------------

@dataclass
class Hand:
    """A learned kinematic hand. All fields JSON-native.

    strokes: per training stroke, its relative pulse rows (REL columns).
    stroke_lengths: arc length / R. drawings: per drawing {ink, n, w_over_R}.
    relations: grammar-v3 style pooled relations. scale: std per REL dim.
    """
    name: str = ""
    strokes: list = field(default_factory=list)
    stroke_lengths: list = field(default_factory=list)
    drawings: list = field(default_factory=list)
    relations: dict = field(default_factory=dict)
    start_pos: list = field(default_factory=list)
    scale: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self._cache: dict = {}

    _FIELDS = ("name", "strokes", "stroke_lengths", "drawings", "relations", "start_pos", "scale", "meta")

    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in self._FIELDS}

    @staticmethod
    def from_json(d: dict) -> "Hand":
        return Hand(**{k: d[k] for k in Hand._FIELDS if k in d})

    def save(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_json()))

    @staticmethod
    def load(path) -> "Hand":
        return Hand.from_json(json.loads(Path(path).read_text()))

    # -- the chain ----------------------------------------------------------
    def _index(self):
        if "tree" in self._cache:
            return self._cache
        sc = np.maximum(np.asarray(self.scale or [1.0] * 6, float), 1e-3)
        ctx, nxt, firsts = [], [], []
        for rows in self.strokes:
            R_ = np.asarray(rows, float)
            if not len(R_):
                continue
            firsts.append(R_[0])
            tot = float(np.exp(R_[:, 0]).sum())
            cum = np.concatenate([[0.0], np.cumsum(np.exp(R_[:, 0]))])
            for j in range(1, len(R_)):
                ctx.append(self._ctx(R_[j - 1], R_[j - 2] if j >= 2 else None, cum[j] / tot, sc))
                nxt.append(R_[j])
        self._cache.update(sc=sc, firsts=np.array(firsts).reshape(-1, 6),
                           ctx=np.array(ctx).reshape(-1, 9), nxt=np.array(nxt).reshape(-1, 6))
        self._cache["tree"] = cKDTree(self._cache["ctx"]) if len(ctx) else None
        return self._cache

    @staticmethod
    def _ctx(p1, p2, u, sc):
        a = np.asarray(p1, float) / sc
        b = np.array([0.0, 0.0]) if p2 is None else np.asarray(p2, float)[[1, 5]] / sc[[1, 5]]
        return np.concatenate([a, 0.5 * b, [2.0 * u]])

    def first(self, rng) -> np.ndarray:
        c = self._index()
        r = c["firsts"][int(rng.integers(len(c["firsts"])))].copy()
        r[:3] += rng.normal(0, JITTER, 3) * c["sc"][:3]
        return r

    def draw(self, p1, p2, u: float, rng, k: int = KNN) -> np.ndarray:
        c = self._index()
        if c["tree"] is None:
            return self.first(rng)
        q = self._ctx(p1, p2, u, c["sc"])
        k = min(k, len(c["nxt"]))
        _d, ii = c["tree"].query(q, k=k)
        ii = np.atleast_1d(ii)
        r = c["nxt"][int(ii[int(rng.integers(len(ii)))])].copy()
        r += rng.normal(0, JITTER, 6) * c["sc"]
        r[3] = max(r[3], 0.0)
        return r

    @property
    def min_length(self) -> float:
        L = np.asarray(self.stroke_lengths or [0.05])
        return float(np.quantile(L, 0.05))


def shuffle_rows(rows, rng) -> np.ndarray:
    """Control: the stroke's pulses (shape: D, Δθ, σ, T) in random order,
    the timing/jump sequence (dt, jump) left in place."""
    R_ = np.array(rows, float)
    if len(R_) < 2:
        return R_
    perm = rng.permutation(len(R_))
    out = R_.copy()
    out[:, [0, 1, 2, 4]] = R_[perm][:, [0, 1, 2, 4]]
    return out


def learn(fitted: list[dict], *, name: str = "", shuffle: bool = False, seed: int = 0,
          max_snr_drop: float | None = None) -> Hand:
    """A Hand from `fit_drawing` outputs. shuffle=True: control hand trained
    on pulse-shuffled strokes. max_snr_drop: drop fits with SNR below it."""
    rng = np.random.default_rng(seed)
    strokes, lengths, spos, per = [], [], [], []
    rel = {"n": 0, "n_attached": 0, "u": [], "angle": [], "cross": [], "gap_free": [],
           "n_ends": 0, "n_ends_attached": 0, "selfcross": []}
    for fd in fitted:
        sts = [s for s in fd["strokes"] if max_snr_drop is None or s["snr_v"] >= max_snr_drop]
        rows = [pulses_to_rows(np.asarray(s["pulses"], float), fd["R"]) for s in sts]
        okr = [bool(np.all(np.isfinite(r))) for r in rows]        # degenerate fits (T → 0) dropped
        sts = [s_ for s_, o in zip(sts, okr) if o]
        rows = [r for r, o in zip(rows, okr) if o]
        if shuffle:
            rows = [shuffle_rows(r, rng) for r in rows]
        per.append({"ink": float(fd["relations"].get("ink", sum(s["length"] for s in fd["strokes"]))),
                    "n": int(fd.get("n_long", len(fd["strokes"]))),
                    "w_over_R": fd["w"] / fd["R"] if fd["R"] > 0 else 0.0})
        for s, r in zip(sts, rows):
            strokes.append(np.round(r, 6).tolist())
            lengths.append(float(s["length"]))
            spos.append(s["start"])
        r = fd["relations"]
        rel["n"] += r["n"]
        rel["n_attached"] += int(sum(1 for a in r["attached"] if a > 0))
        rel["u"] += r["u"]
        rel["angle"] += r["angle"]
        rel["cross"].append(r["cross_per_ink"])
        rel["selfcross"].append(r["selfcross_frac"])
        thr = r.get("attach_w_over_R", 0.0)
        gaps = r.get("gap", [])
        rel["n_ends"] += len(gaps)
        rel["n_ends_attached"] += int(sum(1 for x in gaps if x <= thr))
        rel["gap_free"] += [x for x in gaps if x > thr]
    allr = np.vstack([np.asarray(r) for r in strokes if len(r)]) if strokes else np.ones((1, 6))
    later = np.vstack([np.asarray(r)[1:] for r in strokes if len(r) > 1]) if strokes else allr
    scale = [float(np.std(allr[:, i])) for i in range(3)] + [float(np.std(later[:, i])) for i in range(3, 6)]
    relations = {
        "p_end_attached": rel["n_ends_attached"] / rel["n_ends"] if rel["n_ends"] else 0.0,
        "u": [round(x, 4) for x in rel["u"]], "angle": [round(x, 4) for x in rel["angle"]],
        "gap_free": [round(x, 5) for x in rel["gap_free"]],
        "cross_per_ink_median": float(np.median(rel["cross"])) if rel["cross"] else 0.0,
        "selfcross_frac": float(np.mean(rel["selfcross"])) if rel["selfcross"] else 0.0,
    }
    return Hand(name=name, strokes=strokes, stroke_lengths=lengths, drawings=per, relations=relations,
                start_pos=spos, scale=scale,
                meta={"shuffle": shuffle, "n_drawings": len(fitted), "n_strokes": len(strokes)})


def signature(fitted: list[dict]) -> dict:
    """Interpretable kinematic descriptors of a hand (from fit_drawing outputs)."""
    fitted = [{**fd, "strokes": [s for s in fd["strokes"]
                                 if np.all(np.isfinite(pulses_to_rows(np.asarray(s["pulses"], float), fd["R"])))]}
              for fd in fitted]
    rows = [pulses_to_rows(np.asarray(s["pulses"], float), fd["R"]) for fd in fitted for s in fd["strokes"]]
    L = np.array([s["length"] for fd in fitted for s in fd["strokes"]])
    W = np.array([s["length"] * fd["R"] / max(s["w"], 1e-9) for fd in fitted for s in fd["strokes"]])
    if not rows:
        return {}
    n = np.array([len(r) for r in rows])
    allr = np.vstack(rows)
    later = np.vstack([r[1:] for r in rows if len(r) > 1])
    snr = np.array([s["snr_v"] for fd in fitted for s in fd["strokes"]])
    err = np.array([s["err_w"] for fd in fitted for s in fd["strokes"]])
    errr = np.array([s["err_rel"] for fd in fitted for s in fd["strokes"]])
    return {
        "n_strokes": int(len(rows)),
        "pulses_per_R": float(n.sum() / L.sum()),
        "pulses_per_100w": float(100 * n.sum() / W.sum()),
        "pulses_per_stroke_q50": float(np.median(n)),
        "D_over_R_q50": float(np.median(np.exp(allr[:, 0]))),
        "abs_dth_q50": float(np.median(np.abs(allr[:, 1]))),
        "abs_dth_q90": float(np.quantile(np.abs(allr[:, 1]), 0.9)),
        "dth_pos_share": float(np.mean(allr[:, 1] > 0)),
        "sigma_q50": float(np.median(allr[:, 2])),
        "onset_dt_q50": float(np.median(later[:, 3])),
        "overlap_share": float(np.mean(later[:, 3] < 1.0)),
        "abs_jump_q50": float(np.median(np.abs(later[:, 5]))),
        "lT_sd": float(np.std(allr[:, 4])),
        "snr_q10": float(np.quantile(snr, 0.1)), "snr_q50": float(np.median(snr)),
        "share_snr_ge_20": float(np.mean(snr >= 20)),
        "err_w_q50": float(np.median(err)), "err_w_q90": float(np.quantile(err, 0.9)),
        "err_rel_q50": float(np.median(errr)),
    }


# ---------------------------------------------------------------------------
# generation: incremental lines
# ---------------------------------------------------------------------------

class _Line:
    """A line under construction: committed pulses and the trajectory they
    define (dense time grid). Appending pulses only changes the trajectory
    after the earliest new onset t_a; `propose` returns that window."""

    def __init__(self, start, step):
        self.start = np.asarray(start, float)
        self.step = step
        self.P = np.zeros((0, 6))
        self.T = np.zeros(1)
        self.X = self.start[None, :].copy()
        self.rows: list = []
        self.s = np.zeros(1)

    def length(self) -> float:
        return float(self.s[-1])

    def propose(self, newP):
        newP = _P(newP)
        if not len(self.P):
            t_a = float(support(newP)[:, 0].min())
            t0 = t_a
            x_a = self.start
        else:
            t_a = max(float(support(newP)[:, 0].min()), float(self.T[0]))
            if t_a >= self.T[-1]:
                x_a = self.X[-1]
            else:
                x_a = np.array([np.interp(t_a, self.T, self.X[:, 0]), np.interp(t_a, self.T, self.X[:, 1])])
            t0 = t_a
        act = self.P[support(self.P)[:, 1] > t_a] if len(self.P) else np.zeros((0, 6))
        allP = np.vstack([act, newP])
        t_b = float(support(allP)[:, 1].max())
        tg = time_grid(allP, self.step, t0, max(t_b, t0 + 1e-9))
        Xw = x_a[None, :] + _cumtrapz(velocity_sparse(allP, tg), tg)
        return t_a, tg, Xw

    def old_part(self, t_a):
        k = int(np.searchsorted(self.T, t_a))
        return self.T[:k], self.X[:k], self.s[:k]

    def commit(self, newP, rows, t_a, tg, Xw):
        Tk, Xk, sk = self.old_part(t_a)
        self.P = np.vstack([self.P, _P(newP)])
        self.rows = self.rows + [list(r) for r in rows]
        self.T = np.concatenate([Tk, tg])
        self.X = np.vstack([Xk, Xw])
        s0 = sk[-1] + (np.linalg.norm(Xw[0] - Xk[-1]) if len(Xk) else 0.0) if len(sk) else 0.0
        self.s = np.concatenate([sk, s0 + arclength(Xw)])

    def snapshot(self):
        return (self.P.copy(), list(self.rows), self.T.copy(), self.X.copy(), self.s.copy())

    def restore(self, snap):
        self.P, self.rows, self.T, self.X, self.s = snap[0].copy(), list(snap[1]), snap[2].copy(), \
            snap[3].copy(), snap[4].copy()

    def points(self) -> np.ndarray:
        return _uniform(self.X, self.step)


def _thin(X: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """Points of a dense polyline about `step` apart, plus their arc positions."""
    s = arclength(X)
    if s[-1] <= 0:
        return X[:1], s[:1]
    idx = np.unique(np.searchsorted(s, np.arange(0.0, s[-1], step)))
    idx = np.unique(np.concatenate([idx, [len(X) - 1]]))
    return X[idx], s[idx]


class _Grower:
    """Grows a line pulse by pulse with the chain's own proposals; the first
    proposal (draw order) that stays inside, clear of other ink (crossings
    allowed under budget) and of the line's own earlier part is kept,
    preferring those with a clear look-ahead ray."""

    def __init__(self, hand: Hand, rng, sheet, R, step, clr, look, K=8):
        self.h, self.rng, self.sheet, self.R, self.step = hand, rng, sheet, R, step
        self.clr, self.look, self.K = clr, look, K

    def _row(self, line: _Line, u: float):
        if not line.rows:
            return self.h.first(self.rng)
        p1 = line.rows[-1]
        p2 = line.rows[-2] if len(line.rows) >= 2 else None
        return self.h.draw(p1, p2, u, self.rng)

    def step_line(self, line: _Line, length: float, *, heading=None, s_skip=0.0, host=None,
                  self_ok=False, cross_ok=False):
        """Try to append one pulse. Returns (ok, n_crossings)."""
        sheet, clr = self.sheet, self.clr
        u = min(line.length() / max(length, 1e-9), 1.0)
        found = {"pref": None, "ok": None, "x": None}
        for _k in range(self.K):
            row = self._row(line, u)
            if len(line.P):
                newP = next_pulse(line.P[-1], row, self.R)
            else:
                newP = first_pulse(row, self.R, heading if heading is not None
                                   else float(self.rng.uniform(0, 2 * np.pi)))
            t_a, tg, Xw = line.propose(newP)
            Pc, sc = _thin(Xw, self.step)
            if not sheet.inside(Pc).all():
                continue
            Tk, Xk, sk = line.old_part(t_a)
            s_base = sk[-1] if len(sk) else 0.0
            sg = s_base + sc
            d_o, own = sheet.dist_own(Pc)
            hit_o = (d_o < clr) & ~((sg < s_skip) & (own == (-2 if host is None else host)))
            old = Xk[sk < s_base - 2 * clr] if len(sk) else np.zeros((0, 2))
            d_s = cKDTree(old).query(Pc)[0] if len(old) else np.full(len(Pc), np.inf)
            hit_s = d_s < clr
            end_clear = d_o[-1] >= clr and d_s[-1] >= clr
            dv = Xw[-1] - Xw[max(len(Xw) - 8, 0)]
            if np.linalg.norm(dv) > 0:
                dv = dv / np.linalg.norm(dv)
                ray = Pc[-1] + np.outer(np.linspace(self.look / 4, self.look, 4), dv)
                rd = sheet.dist(ray)
                if len(old):
                    rd = np.minimum(rd, cKDTree(np.vstack([old, Pc])).query(ray)[0])
                room = sheet.inside(ray).all() and (rd >= clr).all()
            else:
                room = False
            item = (newP, row, t_a, tg, Xw, g3._bands(hit_o))
            if not hit_o.any() and not hit_s.any():
                key = "pref" if room else "ok"
            elif not hit_s.any() and end_clear and cross_ok:
                key = "pref" if room else "ok"
            elif hit_s.any() and end_clear and self_ok and not hit_o.any():
                key = "x"
            else:
                continue
            if found[key] is None:
                found[key] = item
            if found["pref"] is not None:
                break
        item = found["pref"] or found["ok"] or found["x"]
        if item is None:
            return False, 0
        newP, row, t_a, tg, Xw, nb = item
        line.commit(newP, [row], t_a, tg, Xw)
        return True, nb

    def grow(self, start, heading, length, **kw):
        line = _Line(start, self.step)
        crosses, status = 0, "full"
        cross_ok = kw.pop("cross_ok", lambda s: False)
        while line.length() < length and len(line.P) < MAX_PULSES_LINE:
            ok, nb = self.step_line(line, length, heading=heading, cross_ok=cross_ok(line.length()), **kw)
            if not ok:
                status = "blocked"
                break
            crosses += nb
        return line, status, crosses


def _sample(xs, rng, default):
    return float(xs[int(rng.integers(len(xs)))]) if len(xs) else default


def generate_stroke(hand: Hand, rng, *, length: float, R: float = 1.0, step: float = 0.002,
                    start=(0.0, 0.0), heading: float = 0.0) -> Stroke:
    """One free stroke (no sheet): `length` and `step` in R units, pulses
    until the length is reached."""
    line = _Line(start, step * R)
    while line.length() < length * R and len(line.P) < MAX_PULSES_LINE:
        u = min(line.length() / (length * R), 1.0)
        row = hand.first(rng) if not line.rows else hand.draw(
            line.rows[-1], line.rows[-2] if len(line.rows) >= 2 else None, u, rng)
        newP = next_pulse(line.P[-1], row, R) if len(line.P) else first_pulse(row, R, heading)
        t_a, tg, Xw = line.propose(newP)
        line.commit(newP, [row], t_a, tg, Xw)
    return Stroke(line.points(), meta={"hand": hand.name, "pulses": line.P.tolist(), "rows": line.rows})


def generate_drawing(hand: Hand, rng, size, *, mode: str = "contiguous", ink: float | None = None,
                     margin: float = 20.0, ref_frac: float = 0.95, step: float | None = None,
                     line_width: float | None = None, tries: int = 6, K: int = 8,
                     clearance_w: float = CLEAR_W, max_strokes: int = 300,
                     cross_gain: float = 1.0) -> Drawing:
    """A drawing in the hand on a (W, H) px canvas. Same conventions as
    grammar v3 (R = ref_frac × margin-box diagonal, line width = learned
    w/R × R, ink budget = a training drawing's long-stroke ink). Lines start
    attached (probability 2 × learned share of attached ends: on an existing
    line at a learned angle) or free at a learned gap from existing ink.
    mode="single": one line of the whole ink budget, with backtracking."""
    W, H = (int(size), int(size)) if np.isscalar(size) else (int(size[0]), int(size[1]))
    R = ref_frac * float(np.hypot(W - 2 * margin, H - 2 * margin))
    if line_width is None:
        wr = [d["w_over_R"] for d in hand.drawings if d.get("w_over_R")]
        line_width = (float(np.median(wr)) if wr else 0.002) * R
    lw = float(line_width)
    step = float(step) if step is not None else max(0.5, 0.5 * lw)
    clr = max(clearance_w * lw, 2 * step)
    Dm = np.median([np.exp(r[0]) for rows in hand.strokes[:3000] for r in rows]) if hand.strokes else 0.03
    look = max(4 * clr, float(Dm) * R)
    sheet = g3._Sheet(W, H, margin, clr)
    if ink is None:
        ink = _sample([d["ink"] for d in hand.drawings if d["ink"] > 0], rng, 2.0)
    rel = hand.relations or {}
    cross_rate = cross_gain * rel.get("cross_per_ink_median", 0.0)
    meta = {"ref_length_gen": R, "hand": hand.name, "mode": mode, "line_width_px": lw,
            "ink_budget": float(ink), "clearance_px": clr}
    grower = _Grower(hand, rng, sheet, R, step, clr, look, K)
    lengths = hand.stroke_lengths or [0.1]
    if mode == "single":
        st = _single(hand, rng, grower, sheet, R, float(ink), margin, W, H, lw)
        return Drawing([st] if len(st) >= 2 else [], source=f"lognormal:{hand.name}:single",
                       size=(W, H), meta={**meta, **{k: v for k, v in st.meta.items() if k != "pulses"}})
    if mode != "contiguous":
        raise ValueError(f"unknown mode {mode!r}")
    pb = min(1.0, 2.0 * rel.get("p_end_attached", 0.15))
    gaps = rel.get("gap_free") or []
    min_len = hand.min_length
    placed: list[Stroke] = []
    state = {"ink": 0.0, "crosses": 0}
    fails = 0

    def free_start():
        g = _sample(gaps, rng, 1.0) * R
        if sheet.tree is not None and g < 0.1 * R:
            for _ in range(30):
                q = sheet.allp[int(rng.integers(len(sheet.allp)))]
                a = rng.uniform(0, 2 * np.pi)
                c = q + max(g, 1.2 * clr) * np.array([np.cos(a), np.sin(a)])
                if not sheet.inside(c[None])[0]:
                    continue
                d = float(sheet.dist(c[None])[0])
                if 0.7 * g <= d <= 1.4 * max(g, 1.2 * clr) and d >= clr:
                    return c, rng.uniform(0, 2 * np.pi), 0.0, {"relation": "free", "gap": d / R}
        sp = (np.array([hand.start_pos[int(rng.integers(len(hand.start_pos)))] for _ in range(8)])
              if hand.start_pos else rng.random((8, 2)))
        sp = np.clip(sp + rng.normal(0, 0.08, sp.shape), 0, 1)
        cand = margin + sp * (np.array([W, H]) - 2 * margin)
        return sheet.free_point(rng, cand), rng.uniform(0, 2 * np.pi), 0.0, {"relation": "free"}

    def attach():
        Ls = np.array([p.length() for p in placed])
        hi = int(rng.choice(len(placed), p=Ls / Ls.sum()))
        hp = placed[hi].points
        hs = arclength(hp)
        u = float(np.clip(_sample(rel.get("u") or [], rng, float(rng.random())), 0.0, 1.0))
        j = int(np.clip(np.searchsorted(hs, u * hs[-1]), 0, len(hp) - 1))
        tan = g3._tangent(hp, hs, j, 3 * lw)
        a = abs(_sample(rel.get("angle") or [], rng, 0.6) + rng.normal(0, 0.05))
        if j in (0, len(hp) - 1):        # at an end: continue outward
            base = np.arctan2(tan[1], tan[0]) + (np.pi if j == 0 else 0.0)
        else:
            base = np.arctan2(tan[1], tan[0]) + (np.pi if rng.random() < 0.5 else 0.0)
        heading = float(base + (a if rng.random() < 0.5 else -a))
        s_skip = clr * (2.0 + 1.0 / max(np.sin(a), 0.2))
        return hp[j], heading, s_skip, {"relation": "attach", "host": hi, "angle": float(a), "u": u}

    while len(placed) < max_strokes and fails < 4 * tries and state["ink"] < ink:
        target = _sample(lengths, rng, 0.1) * R
        best = None
        for _t in range(tries):
            if placed and rng.random() < pb:
                start, heading, s_skip, rm = attach()
            else:
                start, heading, s_skip, rm = free_start()
            c0, ink0 = state["crosses"], state["ink"]
            line, how, nc = grower.grow(
                start, heading, target, s_skip=s_skip, host=rm.get("host"),
                cross_ok=lambda s, c0=c0, ink0=ink0: c0 < cross_rate * (ink0 + s / R))
            L = line.length()
            if best is None or L > best[0]:
                best = (L, line, how, nc, rm)
            if L >= 0.9 * target:
                break
        if best is None or best[0] < min_len * R:
            fails += 1
            continue
        L, line, how, nc, rm = best
        pts = line.points()
        st = Stroke(pts, width=np.full(len(pts), lw),
                    meta={"hand": hand.name, "end": how, "crosses": nc, "target": target / R,
                          "n_pulses": len(line.P), "pulses": line.P.round(6).tolist(), **rm})
        placed.append(st)
        sheet.add(pts, len(placed) - 1)
        state["ink"] += st.length() / R
        state["crosses"] += nc
    meta.update(crosses=state["crosses"], ink=state["ink"], p_attach=pb, cross_rate=cross_rate)
    return Drawing(placed, source=f"lognormal:{hand.name}", size=(W, H), meta=meta)


def _single(hand, rng, grower: _Grower, sheet, R, ink, margin, W, H, lw) -> Stroke:
    sp = (np.clip(np.array(hand.start_pos[int(rng.integers(len(hand.start_pos)))]), 0.2, 0.8)
          if hand.start_pos else rng.uniform(0.3, 0.7, 2))
    start = margin + sp * (np.array([W, H]) - 2 * margin)
    line = _Line(start, grower.step)
    heading = float(rng.uniform(0, 2 * np.pi))
    snaps: list = []
    backtracks, fails, crosses, total = 0, 0, 0, ink * R
    K0 = grower.K
    while line.length() < total and len(line.P) < 4 * MAX_PULSES_LINE and fails < 150:
        grower.K = K0 if fails == 0 or not snaps else 3 * K0       # widen the search when stuck
        ok, nb = grower.step_line(line, total, heading=heading, self_ok=backtracks >= 40)
        grower.K = K0
        if ok:
            snaps.append(line.snapshot())
            snaps = snaps[-16:]
            crosses += nb
            fails = max(fails - 1, 0)
            continue
        fails += 1
        depth = min(1 + backtracks % 4, len(snaps) - 1)
        if depth >= 1 and backtracks < 80:      # boxed in: back up 1–4 pulses, regrow
            for _ in range(depth):
                snaps.pop()
            line.restore(snaps[-1])
            backtracks += 1
        elif backtracks >= 80:
            break
    pts = line.points()
    return Stroke(pts, width=np.full(len(pts), lw),
                  meta={"hand": hand.name, "mode": "single", "n_pulses": len(line.P),
                        "backtracks": backtracks, "crosses": crosses, "length_R": line.length() / R})


# ---------------------------------------------------------------------------
# memorisation measure (polyline turning signature)
# ---------------------------------------------------------------------------

SIG_N = g3.SIG_N
SIG_LEN_W = g3.SIG_LEN_W


def turning_signature(points, R: float, sigma: float) -> np.ndarray | None:
    """θ(u) at SIG_N points (smoothed at σ, mean removed, /√SIG_N) plus
    SIG_LEN_W·log(length/R) — grammar v3's signature, computed on a polyline."""
    p = np.asarray(points, float)
    if len(p) < 3:
        return None
    step = max(sigma / 4, 1e-6)
    r = resample(p, step)
    if len(r) < 4:
        return None
    sm = smooth(r, sigma, step)
    s = arclength(sm)
    L = s[-1]
    if L <= 0:
        return None
    d = np.diff(sm, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    sm_mid = 0.5 * (s[1:] + s[:-1])
    u = (np.arange(SIG_N) + 0.5) / SIG_N * L
    tu = np.interp(u, sm_mid, th)
    tu -= tu.mean()
    return np.concatenate([tu / np.sqrt(SIG_N), [SIG_LEN_W * np.log(L / R)]])


def nearest_distance(query: list[np.ndarray], train: list[np.ndarray]) -> np.ndarray:
    Q = np.array([q for q in query if q is not None])
    T = np.array([t for t in train if t is not None])
    if not len(Q) or not len(T):
        return np.zeros(0)
    return g3._min_dist(Q, T)
