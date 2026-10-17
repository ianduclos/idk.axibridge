# FROZEN from research commit 4aa0ed1: tools/gesture/gesture/clothoid.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Piecewise-linear κ(s) fit: a stroke as lines, arcs and clothoids.

Representation "A. Clothoid alphabet" of docs/IDEAS-gesture-bank.md. A stroke
is decomposed into segments whose curvature is linear in arc length:

- **line**      κ ≡ 0
- **arc**       κ constant ≠ 0
- **clothoid**  κ linear in s, non-zero slope

plus **corners**: turns too sharp for the smoothing scale σ to resolve as a
curve. Corners split the stroke into independent pieces; κ need not be
continuous across a corner, and each corner carries its own turning angle.

Pipeline (McCrae & Singh 2008, "Sketching piecewise clothoid curves", plus a
smoothing-aware, whitened refinement):

1. κ(s) from `curvature.kappa_s` (the one implementation), then
   **re-parametrised by true arc length of the smoothed curve**: kappa_s
   resamples the raw polyline, whose length is inflated by jitter (≈10–25 %
   at 0.5 px noise on 1 px spacing), so κ integrated over that parameter
   over-counts turning and stretches every length. Speed inside end/corner
   zones is replaced by the median speed (there its drop is the smoothing,
   not geometry). All s values in a Fit are along the smoothed stroke.
2. Corners: greedy maxima of the turning over a ±2σ window above
   `corner_angle`, ≥ 3σ apart, ≥ 3σ from open ends.
3. **Stage 1 — McCrae DP** per corner-free piece: Σ SSE(least-squares line
   to κ) + λ₁ per segment over candidate breaks every σ/2 (closed-form SSE
   from prefix sums; O(C²), C capped at 600 so long strokes coarsen the
   grid). κ is pre-smoothed further only if it is too noisy for the DP
   (per-sample noise > 10 % of the κ scale). This is only an initialiser.
4. **Stage 2 — continuous, smoothing-aware, whitened refinement.** Model: a
   *continuous* linear spline in κ per piece (G2 inside a piece; hat basis
   with continuity built in — continuous free-knot least squares, not
   discontinuous + projection), **convolved with the same Gaussian that
   smoothed the stroke** (measured κ ≈ G_σ * κ_true to O((κσ)²)), so the
   rounding smoothing puts at every kink costs no knots. The least squares
   runs on y = ∫∫κ ds² (px): κ-noise from positional jitter is strongly
   high-pass (∝ ω⁴), y-noise is ~white below 1/σ, so the double integral is
   the whitening transform (per-sample κ noise can exceed the signal while
   segment-scale κ is still well determined). Free nuisance columns absorb
   the integration constants and, per corner, the θ and y jumps. Smoothed
   ramp primitives have closed forms (Φ, φ), tabulated once, so a model
   evaluation is a few array slices + a small solve. Greedy moves under
   the per-knot penalty λ: integer hill-climbing of knot positions;
   removal of a knot (after re-optimising its neighbours) if SSE rises by
   < λ; insertion at the best grid position if SSE falls by > λ.
5. Classification (thresholds below) on the stretch of each segment where κ
   was measured (zones only extrapolate); line/arc labels that a
   κ-continuous spline cannot realise (a line touching an arc) are
   relabelled; then a **constrained refit** — lines pinned to κ = 0, arcs
   tied to one κ — so returned segments are exactly in the alphabet.
   With the default thresholds the labels are checked against the data:
   if the constrained fit costs more than _VERIFY_K·λ_v per pinned/tied
   value (λ_v = λ with a 0.05σ floor), the knots are re-polished under the
   constraints and, if still too costly, the line/arc label whose release
   helps most becomes "clothoid" (repeat). Neighbours that the constraints
   made identical are merged.
6. Corner angle = jump of (measured θ − ∫ fitted κ) across the corner, each
   side averaged over ≤ 10σ of trusted samples and never past halfway to
   the neighbouring corner (else measured θ at the window ends); reported
   in (−π, π] — a corner is an instantaneous turn, only its angle mod 2π
   acts.

Ill-posed pieces. A piece lying wholly inside end/corner zones (a corner
within ~6σ of an open end, two corners within ~5σ) has no trusted samples:
its knot values are seen only through Gaussian tails. Stage 2 therefore
carries a weak κ prior (ridge, _KAPPA_PRIOR: a knot at κ = 1/σ costs one
σ_y² of SSE), negligible wherever data determine a knot, which keeps such a
piece at κ ≈ 0 (a line; its turning goes to the corner angles) instead of
the ±1e5/px a near-singular solve returns. Strokes too short to analyse
(open: < ~9σ; closed: < _CLOSED_MIN_LEN·σ, where smoothing shrinks the loop
toward its centroid) get one line/arc carrying the stroke's own turning
(open: end-to-end tangent change of the smoothed curve; closed: turning
number of the raw polygon) over its raw length.

Residual tangent wiggle after smoothing lengthens the curve by ≈ 1 + σ_θ²/2;
lengths are divided by that factor (and κ multiplied) before fitting.

Penalty (BIC-like). σ_y = robust lateral noise (MAD of the lag-3σ fourth
difference of y, which annihilates the cubic model away from knots, /√70),
floored at 0.02σ so clean synthetic strokes do not split on model error
(a knot must move the stroke by ≳ 1/50 of σ RMS to pay for itself).
λ = C · 2 · σ_y² · (σ/step) · ln(n_eff), n_eff = trusted samples·step/σ:
two parameters per knot (position, value); samples are correlated over ~σ,
so each independent observation is counted ~σ/step times. C = 1.5 was
calibrated so that noise-only lines and arcs (0.3–1 px jitter) split in
≲ 5 % of trials; C = 1 is plain BIC and over-splits ~10 %.

Classification thresholds (explicit, recorded in the Fit, overridable).
Default rules are in **turning** (rad), the natural noise-scaled unit: the
error of a segment's mean κ is ≈ σ_θ/length, so κ·length has an error ≈ σ_θ
independent of length.

- line     if ∫|κ| ds ≤ turn_tol            (total absolute turning)
- arc      if ∫|κ − κ̄| ds = |k1 − k0|·length/4 ≤ turn_tol
                                          (turning away from the best arc)
- otherwise clothoid. Both integrals use length ≥ 10σ, so a short segment
  cannot pass as straight or constant merely by being short.
- turn_tol = max(3 · σ_θ, 2°), σ_θ = robust tangent-angle noise (MAD of the
  lag-3σ third difference of θ = ∫κ, /√20). The 2° floor absorbs the
  model's systematic error on clean strokes.
- `turn_tol` (rad) overrides the default; `kappa_tol` (1/px) replaces both
  rules with absolute ones (line if max|κ| ≤ kappa_tol, arc if
  |Δκ| ≤ kappa_tol); `slope_tol` (1/px²) replaces the arc rule with
  |dκ/ds| ≤ slope_tol. Explicit overrides are applied as given (no data
  check of the labels).

Units: s and lengths in the stroke's units (pixels); κ in 1/px; slope in
1/px²; angles in rad.

Closed strokes: segments are cyclic and start at the first corner (or the
first knot); s values run from `segments[0].s0` to `segments[0].s0 + length`
and may exceed `length` — read them modulo `length`. The first corner of a
closed stroke sits at segments[0].s0 and its angle closes the loop.
"""
from __future__ import annotations

import copy
import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from math import comb

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.special import erfc
from scipy.spatial import cKDTree

from .curvature import integrate_kappa, kappa_s

KINDS = ("line", "arc", "clothoid")

# --- tuning constants (documented in the module docstring) -----------------
_MAX_CANDIDATES = 600      # DP candidate cap per piece (O(C²) time)
_MAX_SAMPLES = 4000        # arc-length grid cap (longer strokes: coarser step)
_MAX_GRID = 80             # stage-2 insertion grid cap per sweep
_CORNER_HALF = 2.0         # corner turning window half-width, in σ
_CORNER_SUPPRESS = 3.0     # non-max suppression radius between corners, in σ
_CORNER_CONC = 0.7         # corner: |T(±2σ)| ≥ this · |T(±4σ)| (concentrated turning)
_ZONE_CORNER = 2.5         # exclusion around corners, in σ
_ZONE_END = 3.5            # exclusion at open ends (κ biased by the smoothing pad), in σ
_MIN_SEG = 1.5             # minimum segment length, in σ
_FLOOR_REL_1 = 0.02        # stage-1 κ-noise floor, fraction of κ_scale
_FLOOR_ABS = 1e-4          # stage-1 absolute κ-noise floor, in units of 1/σ
_FLOOR_Y = 0.02            # stage-2 lateral-noise floor, in units of σ
_PEN_C = 1.5               # stage-2 BIC multiplier (calibrated on pure noise)
_TURN_Z = 3.0              # turn_tol = _TURN_Z · σ_θ ...
_TURN_FLOOR = np.deg2rad(2.0)  # ... but never below 2°
_MAX_ITERS = 60            # stage-2 greedy move cap
_VERIFY_K = 4.0            # label check: each pinned/tied κ value may cost ≤ this · λ_v
_FLOOR_Y_VERIFY = 0.05     # λ_v uses this lateral floor (σ units): constraints moving
                           # the stroke < 1/20 σ RMS are always acceptable
_TURN_MIN_LEN = 10.0       # turning rules judge segments over ≥ this many σ
_CORNER_AVG = 10.0         # corner angle: averaging window per side, in σ
_CLOSED_MIN_LEN = 8.0      # closed strokes shorter than this many σ get the tiny fit
                           # (smoothing shrinks the loop by ≤ 26 % at 8σ)
_KAPPA_PRIOR = 1.0         # stage-2 κ prior scale, in units of 1/σ: a knot at
                           # κ = this/σ costs one σ_y² of SSE (vanishing next to
                           # the data for any knot the trusted samples determine)


@dataclass(frozen=True)
class Segment:
    """One alphabet letter. s0 < s1 arc-length positions (px); k0, k1 the
    curvature (1/px) at s0 and s1, linear in between."""
    kind: str          # "line" | "arc" | "clothoid"
    s0: float
    s1: float
    k0: float
    k1: float

    @property
    def length(self) -> float:
        """Segment arc length (px)."""
        return self.s1 - self.s0

    @property
    def slope(self) -> float:
        """dκ/ds (1/px²); 0 for lines and arcs."""
        L = self.length
        return (self.k1 - self.k0) / L if L > 0 else 0.0

    @property
    def turning(self) -> float:
        """Total tangent turning over the segment (rad), ∫κ ds."""
        return 0.5 * (self.k0 + self.k1) * self.length

    def to_json(self) -> dict:
        return {"kind": self.kind, "s0": float(self.s0), "s1": float(self.s1),
                "k0": float(self.k0), "k1": float(self.k1)}

    @staticmethod
    def from_json(d: dict) -> "Segment":
        return Segment(d["kind"], float(d["s0"]), float(d["s1"]),
                       float(d["k0"]), float(d["k1"]))


@dataclass(frozen=True)
class Fit:
    """A stroke's κ(s) decomposition.

    segments: ordered along the stroke (cyclic for closed strokes).
    corners: arc-length positions (px) of detected corners; corner_angles:
        the matching signed turning (rad) concentrated at each corner.
    sigma: smoothing scale used (px).
    rms_kappa_error: RMS of measured κ minus the fitted κ convolved with the
        smoothing kernel (1/px), over samples ≥ 3.5σ from open ends and
        ≥ 2.5σ from corners.
    rms_position_error: RMS distance (px) from the smoothed input polyline
        to the polyline re-integrated from the fit (curvature.integrate_kappa),
        after the least-squares rigid alignment (start point + heading;
        correspondence by arc length, distance to the nearest point).
    The remaining fields record what the fit used: length (px), closed,
    step (px), noise_kappa (σ_n, 1/px), noise_turn (σ_θ, rad), noise_lateral
    (σ_y, px), turn_tol (rad), kappa_tol (1/px, 0 when the turning rule was
    used), penalty (λ per knot, px²·samples).
    """
    segments: list[Segment]
    corners: list[float]
    sigma: float
    rms_kappa_error: float
    rms_position_error: float
    corner_angles: list[float] = field(default_factory=list)
    length: float = 0.0
    closed: bool = False
    step: float = 0.0
    noise_kappa: float = 0.0
    noise_turn: float = 0.0
    noise_lateral: float = 0.0
    turn_tol: float = 0.0
    kappa_tol: float = 0.0
    penalty: float = 0.0

    def kinds(self) -> list[str]:
        return [g.kind for g in self.segments]

    def breaks(self) -> list[float]:
        """Interior segment boundaries (px), corners included."""
        return [g.s0 for g in self.segments[1:]]

    def to_json(self) -> dict:
        d = {k: getattr(self, k) for k in (
            "sigma", "rms_kappa_error", "rms_position_error", "length", "step",
            "noise_kappa", "noise_turn", "noise_lateral", "turn_tol", "kappa_tol",
            "penalty")}
        d = {k: float(v) for k, v in d.items()}
        d.update(segments=[g.to_json() for g in self.segments],
                 corners=[float(c) for c in self.corners],
                 corner_angles=[float(a) for a in self.corner_angles],
                 closed=bool(self.closed))
        return d

    @staticmethod
    def from_json(d: dict) -> "Fit":
        num = {k: float(d.get(k, 0.0)) for k in (
            "rms_kappa_error", "rms_position_error", "length", "step",
            "noise_kappa", "noise_turn", "noise_lateral", "turn_tol", "kappa_tol",
            "penalty")}
        return Fit(segments=[Segment.from_json(g) for g in d["segments"]],
                   corners=[float(c) for c in d.get("corners", [])],
                   sigma=float(d["sigma"]),
                   corner_angles=[float(a) for a in d.get("corner_angles", [])],
                   closed=bool(d.get("closed", False)), **num)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def _theta(sm: np.ndarray, closed: bool) -> np.ndarray:
    """Unwrapped tangent angle per sample (rad), length n."""
    if closed:
        d = np.roll(sm, -1, axis=0) - np.roll(sm, 1, axis=0)
    else:
        d = np.gradient(sm, axis=0)
    return np.unwrap(np.arctan2(d[:, 1], d[:, 0]))


def _detect_corners(theta: np.ndarray, kappa: np.ndarray, closed: bool, h: int,
                    suppress: int, corner_angle: float, total: float,
                    edge: int = 0) -> list[int]:
    """Indices of corners.

    T_w(i) = θ(i+w) − θ(i−w). A corner is a greedy maximum of |T_h| ≥
    corner_angle (h = 2σ) whose turning is *concentrated*: |T_h| ≥
    _CORNER_CONC·|T_2h| (a smoothed corner keeps ~95 % of its turning
    within ±2σ, an arc only half of what it turns within ±4σ), or T_2h has
    the opposite sign (zig-zag). So arcs longer than ~6σ stay arcs however
    tight. Each corner blocks its whole above-threshold plateau and
    `suppress` samples around it; peaks within `edge` of an open end are
    ignored (the smoothing pad distorts θ there). Snapped to the |κ| peak.
    """
    n = len(theta)
    if not closed and n <= 2 * h + 1:
        return []
    i = np.arange(n)

    def T(w: int) -> np.ndarray:
        if closed:
            hi, lo = i + w, i - w
            return (theta[hi % n] + (hi // n) * total) - (theta[lo % n] + (lo // n) * total)
        return theta[np.minimum(i + w, n - 1)] - theta[np.maximum(i - w, 0)]

    t1, t2 = T(h), T(2 * h)
    mag = np.abs(t1)
    conc = (mag >= _CORNER_CONC * np.abs(t2)) | (np.sign(t1) != np.sign(t2))
    if not closed:
        mag[:max(edge, h)] = 0.0
        mag[n - max(edge, h):] = 0.0
    order = np.argsort(-mag, kind="stable")
    taken: list[int] = []
    blocked = np.zeros(n, dtype=bool)

    def block(lo: int, hi: int) -> None:
        bl = np.arange(lo, hi + 1)
        if closed:
            blocked[bl % n] = True
        else:
            blocked[bl[(bl >= 0) & (bl < n)]] = True

    for k in order:
        if mag[k] < corner_angle:
            break
        if blocked[k]:
            continue
        # the plateau of above-threshold turning around k is one event
        lo = hi = int(k)
        while hi - lo < n and mag[(lo - 1) % n if closed else max(lo - 1, 0)] >= corner_angle \
                and (closed or lo > 0):
            lo -= 1
        while hi - lo < n and mag[(hi + 1) % n if closed else min(hi + 1, n - 1)] >= corner_angle \
                and (closed or hi < n - 1):
            hi += 1
        block(lo - suppress, hi + suppress)
        if not conc[k]:
            continue
        idx = np.arange(k - h, k + h + 1)
        idx = idx % n if closed else idx[(idx >= 0) & (idx < n)]
        taken.append(int(idx[np.argmax(np.abs(kappa[idx]))]))
    return sorted(set(taken))


def _mad_std(v: np.ndarray) -> float:
    if len(v) == 0:
        return 0.0
    return float(1.4826 * np.median(np.abs(v - np.median(v))))


def _diff_noise(x: np.ndarray, mask: np.ndarray, lag: int, order: int) -> float:
    """Robust noise std of x from its lag-`lag` finite difference of the
    given order (which annihilates the noiseless model away from knots):
    MAD / sqrt(Σ binomial²)."""
    n = len(x)
    if n <= order * lag + 1:
        return 0.0
    coef = [(-1) ** (order - k) * comb(order, k) for k in range(order + 1)]
    m = n - order * lag
    d = np.zeros(m)
    ok = np.ones(m, dtype=bool)
    for k, c in enumerate(coef):
        d += c * x[k * lag:k * lag + m]
        ok &= mask[k * lag:k * lag + m]
    v = d[ok] if ok.sum() >= 8 else d
    return _mad_std(v) / np.sqrt(float(sum(c * c for c in coef)))


def _dp_breaks(x: np.ndarray, y: np.ndarray, lam: float, stride: int,
               min_samples: int) -> list[int]:
    """McCrae-style DP: optimal partition of samples 0..m-1 into segments
    [c_i, c_j) on a candidate grid, each fitted by a least-squares line
    (closed form from prefix sums), minimising Σ SSE + lam per segment.
    Returns interior fence indices (first sample of each later segment)."""
    m = len(y)
    if m < 2 * max(min_samples, 2):
        return []
    xc = (x - x[0]) / max(x[-1] - x[0], 1e-12)       # conditioning
    z = np.zeros(1)
    P0 = np.concatenate([z, np.arange(1, m + 1, dtype=np.float64)])
    P1 = np.concatenate([z, np.cumsum(xc)])
    P2 = np.concatenate([z, np.cumsum(xc * xc)])
    Py = np.concatenate([z, np.cumsum(y)])
    Pxy = np.concatenate([z, np.cumsum(xc * y)])
    Pyy = np.concatenate([z, np.cumsum(y * y)])
    cand = np.unique(np.concatenate([np.arange(0, m, stride), [m]]))
    C = len(cand)
    F = np.full(C, np.inf)
    F[0] = 0.0
    back = np.zeros(C, dtype=int)
    for j in range(1, C):
        cj = cand[j]
        ok = np.nonzero((cj - cand[:j]) >= min_samples)[0]
        if len(ok) == 0:
            continue
        ci = cand[ok]
        S0 = P0[cj] - P0[ci]
        S1 = P1[cj] - P1[ci]
        S2 = P2[cj] - P2[ci]
        Sy = Py[cj] - Py[ci]
        Sxy = Pxy[cj] - Pxy[ci]
        Syy = Pyy[cj] - Pyy[ci]
        det = S0 * S2 - S1 * S1
        good = np.abs(det) > 1e-18
        expl = np.where(good, (Sy * Sy * S2 - 2 * Sy * S1 * Sxy + S0 * Sxy * Sxy)
                        / np.where(good, det, 1.0), Sy * Sy / np.maximum(S0, 1e-12))
        tot = F[ok] + np.maximum(Syy - expl, 0.0) + lam
        k = int(np.argmin(tot))
        F[j] = tot[k]
        back[j] = int(ok[k])
    fences = []
    j = C - 1
    while j > 0:
        i = back[j]
        if i > 0:
            fences.append(int(cand[i]))
        j = i
    return sorted(fences)


def _cumtrapz(v: np.ndarray, step: float) -> np.ndarray:
    """Cumulative trapezoid integral along axis 0, starting at 0."""
    out = np.zeros_like(v, dtype=np.float64)
    out[1:] = np.cumsum(0.5 * (v[1:] + v[:-1]) * step, axis=0)
    return out


def _i2(v: np.ndarray, step: float) -> np.ndarray:
    """Double cumulative integral along axis 0 (κ → θ → lateral offset)."""
    return _cumtrapz(_cumtrapz(v, step), step)


class _Model:
    """Stage-2 linear model on integer sample knots.

    Parameters: one κ value per knot of each piece's linear spline (hat
    basis: κ continuous inside a piece, zero outside it), plus free nuisance
    columns. The κ prediction is the spline convolved with the smoothing
    Gaussian. Least squares runs on the doubly integrated signal
    y = ∫∫κ ds² (px): κ-noise from positional jitter is strongly high-pass
    (∝ ω⁴), y-noise is ~white below 1/σ, so the double integral is the
    whitening transform that makes plain least squares efficient.

    A hat is a sum of value jumps H(s−t) and slope changes (s−t)₊; their
    Gaussian-smoothed double integrals have closed forms in Φ, φ and are
    tabulated once per fit on the integer offset grid, so a design column
    costs a few array slices (no convolution per evaluation). Periodic
    pieces add copies at ±n, ±2n samples. Free columns: θ₀, y₀ (integration
    constants) and, per interior corner, a smoothed θ jump and y jump.
    """

    def __init__(self, kappa: np.ndarray, w: np.ndarray,
                 pieces: list[tuple[int, int, bool]], corner_idx: list[int],
                 sd: float, step: float, prior: float = 0.0):
        n = len(kappa)
        self.n, self.step, self.pieces = n, step, pieces
        self.prior = float(prior)
        D = 5 * n + 2
        self.D = D
        x = np.arange(-D, D + 1) / sd
        Phi = 0.5 * erfc(-x / np.sqrt(2.0))
        phi = np.exp(-0.5 * x * x) / np.sqrt(2.0 * np.pi)
        sg = sd * step
        self.T0 = Phi                                                   # G*H
        self.T1 = sg * (x * Phi + phi)                                  # G*x₊
        self.T2 = sg ** 2 / 2.0 * ((x * x + 1.0) * Phi + x * phi)       # G*x₊²/2
        self.T3 = sg ** 3 / 6.0 * ((x ** 3 + 3.0 * x) * Phi + (x * x + 2.0) * phi)
        self.sw = np.sqrt(w)
        self.y = _i2(kappa, step)
        self.yw = self.y * self.sw
        cols = [np.ones(n), (np.arange(n) - 0.5 * n) * step]
        for c in corner_idx:
            cols += [self._sh(self.T1, c), self._sh(self.T0, c)]
        fw = np.column_stack(cols) * self.sw[:, None]
        fs = np.sqrt(np.einsum("ij,ij->j", fw, fw))
        fs[fs == 0] = 1.0
        self.fixed_n, self.fixed_s = fw / fs, fs
        self.cache: dict = {}
        # speed only (2026-10-17, exact): the knot list of each piece and the
        # SSE of each whole knot configuration, memoised. A configuration
        # always solves to the same bits, and the greedy re-visits ~35 % of
        # them (hill-climb polish steps back onto known positions, removals
        # are re-tried every iteration), so a hit returns what a re-solve
        # would have returned.
        self.piece_cache: dict = {}
        self.sse_cache: dict = {}
        self.n_eval = 0

    def _sh(self, table: np.ndarray, t: int) -> np.ndarray:
        s = self.D - t
        return table[s:s + self.n]

    def _ramps(self, p: int, K: np.ndarray, j: int) -> tuple:
        """(kind, position, coef) terms of hat j of piece p; kind 2 = value
        jump, 3 = slope change."""
        a, b, per = self.pieces[p]
        n, st = self.n, self.step
        L = len(K)
        if per:
            left = int(K[j - 1]) if j > 0 else int(K[-1]) - n
            right = int(K[j + 1]) if j < L - 1 else int(K[0]) + n
            hl, hr = (K[j] - left) * st, (right - K[j]) * st
            base = ((3, left, 1 / hl), (3, int(K[j]), -1 / hl - 1 / hr), (3, right, 1 / hr))
            return tuple((k, t + c * n, v) for c in (-2, -1, 0, 1, 2) for (k, t, v) in base)
        if L == 1:
            return ((2, a, 1.0), (2, b, -1.0))
        if j == 0:
            h = (K[1] - K[0]) * st
            return ((2, int(K[0]), 1.0), (3, int(K[0]), -1 / h), (3, int(K[1]), 1 / h))
        if j == L - 1:
            h = (K[-1] - K[-2]) * st
            return ((3, int(K[-2]), 1 / h), (3, int(K[-1]), -1 / h), (2, int(K[-1]), -1.0))
        hl, hr = (K[j] - K[j - 1]) * st, (K[j + 1] - K[j]) * st
        return ((3, int(K[j - 1]), 1 / hl), (3, int(K[j]), -1 / hl - 1 / hr),
                (3, int(K[j + 1]), 1 / hr))

    def _col(self, p: int, K: np.ndarray, j: int, domain: str,
             Kt: list[int] | None = None) -> tuple[np.ndarray, float]:
        """(unit-norm column, its norm) for hat j of piece p; cached by the
        knots it depends on. Kt: K as Python ints (the key only)."""
        if Kt is None:
            Kt = K.tolist()
        L = len(Kt)
        per = self.pieces[p][2]
        key = (domain, p, L == 1, j == 0, j == L - 1, Kt[max(j - 1, 0)], Kt[j], Kt[min(j + 1, L - 1)],
               Kt[-1] if (per and j == 0) else -1, Kt[0] if (per and j == L - 1) else -1)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        tabs = {2: self.T2, 3: self.T3} if domain == "y" else {2: self.T0, 3: self.T1}
        col = np.zeros(self.n)
        for k, t, v in self._ramps(p, K, j):
            col += v * self._sh(tabs[k], t)
        if domain == "y":
            col *= self.sw
        nrm = float(np.sqrt(col @ col))
        out = (col / nrm if nrm > 0 else col, nrm if nrm > 0 else 1.0)
        if len(self.cache) > 20000:
            self.cache.clear()
        self.cache[key] = out
        return out

    def _cols(self, knots: list[np.ndarray], domain: str) -> list[tuple[np.ndarray, float]]:
        """Every hat column of every piece, in order (each piece's list
        cached by its whole knot vector; columns by the knots they depend on)."""
        out: list[tuple[np.ndarray, float]] = []
        for p, K in enumerate(knots):
            Kt = K.tolist()
            pk = (domain, p, *Kt)
            hit = self.piece_cache.get(pk)
            if hit is None:
                hit = [self._col(p, K, j, domain, Kt) for j in range(len(Kt))]
                if len(self.piece_cache) > 20000:
                    self.piece_cache.clear()
                self.piece_cache[pk] = hit
            out += hit
        return out

    def design(self, knots: list[np.ndarray], domain: str = "y") -> np.ndarray:
        """Design matrix (unnormalised; y-domain columns are weighted)."""
        cols = self._cols(knots, domain)
        return np.column_stack([c * s for c, s in cols])

    def solve(self, knots: list[np.ndarray], P: np.ndarray | None = None):
        """Weighted LS on y. P maps reduced κ params → knot values
        (constraints). Returns (sse, knot_values, fixed_coefs)."""
        self.n_eval += 1
        nf = self.fixed_n.shape[1]
        cols = self._cols(knots, "y")
        if P is None:
            m = len(cols)
            A = np.empty((self.n, m + nf))
            scale = np.empty(m + nf)
            A[:, :m] = np.array([c for c, _ in cols]).reshape(m, self.n).T   # the same copies, one call
            scale[:m] = [s for _, s in cols]
        else:
            # P is a 0/1 grouping (each knot value → at most one free
            # parameter): sum the member columns instead of a dense H @ P
            m = P.shape[1]
            H = np.zeros((self.n, m))
            for r, g in zip(*np.nonzero(P)):
                c, s = cols[r]
                H[:, g] += c * (s * P[r, g])
            A = np.empty((self.n, m + nf))
            scale = np.empty(m + nf)
            hs = np.sqrt(np.einsum("ij,ij->j", H, H))
            hs[hs == 0] = 1.0
            A[:, :m] = H / hs
            scale[:m] = hs
        A[:, m:] = self.fixed_n
        scale[m:] = self.fixed_s
        # κ prior (ridge) in physical units: prior·Σ κ_knot². Columns are
        # unit-normalised, so it enters as prior·(knots in group)/scale².
        # Negligible for any knot the trusted samples determine; it keeps a
        # knot they do not determine (a piece lying wholly inside end/corner
        # zones, seen only through Gaussian tails) at ~0 instead of the
        # ±1e5/px a near-singular solve hands back.
        mult = np.ones(m) if P is None else (P * P).sum(axis=0)
        pd = np.zeros(m + nf)
        pd[:m] = self.prior * mult / scale[:m] ** 2
        G = A.T @ A
        rhs = A.T @ self.yw
        try:
            c = np.linalg.solve(G + np.diag(pd + 1e-13), rhs)
            if not np.all(np.isfinite(c)):
                raise np.linalg.LinAlgError
        except np.linalg.LinAlgError:
            Aa = np.vstack([A, np.diag(np.sqrt(pd))])
            c = np.linalg.lstsq(Aa, np.concatenate([self.yw, np.zeros(m + nf)]),
                                rcond=1e-12)[0]
        r = self.yw - A @ c
        e = float(r @ r + np.sum(pd * c * c))
        c = c / scale
        h = c[:m]
        vals = h if P is None else P @ h
        return e, vals, c[m:]

    def sse(self, knots: list[np.ndarray]) -> float:
        key = tuple(tuple(K.tolist()) for K in knots)
        e = self.sse_cache.get(key)
        if e is None:
            e = self.solve(knots)[0]
            if len(self.sse_cache) > 200000:
                self.sse_cache.clear()
            self.sse_cache[key] = e
        return e

    def kappa_pred(self, knots: list[np.ndarray], vals: np.ndarray) -> np.ndarray:
        """Fitted κ convolved with the smoothing kernel, per sample (1/px)."""
        return self.design(knots, "k") @ vals


def _segments_from(knots: list[np.ndarray], vals: np.ndarray,
                   pieces: list[tuple[int, int, bool]], n: int):
    """Raw (i0, i1, k0, k1, piece) tuples in unrolled sample indices."""
    out, off = [], 0
    for p, (a, b, per) in enumerate(pieces):
        K = knots[p]
        v = vals[off:off + len(K)]
        off += len(K)
        if per:
            Kx = np.concatenate([K, [K[0] + n]])
            vx = np.concatenate([v, [v[0]]])
        elif len(K) == 1:
            Kx, vx = np.array([a, b]), np.array([v[0], v[0]])
        else:
            Kx, vx = K, v
        for i in range(len(Kx) - 1):
            out.append((int(Kx[i]), int(Kx[i + 1]), float(vx[i]), float(vx[i + 1]), p))
    return out


def _classify(k0: float, k1: float, length: float, turn_tol: float,
              kappa_tol: float | None, slope_tol: float | None,
              min_len: float = 0.0) -> str:
    """line / arc / clothoid by the explicit thresholds (module docstring).
    Turning is judged over at least min_len (px), so a short segment cannot
    pass as straight or constant merely by being short."""
    L = max(length, min_len, 1e-12)
    if kappa_tol is not None:
        is_line = max(abs(k0), abs(k1)) <= kappa_tol
    else:   # total absolute turning ∫|κ| ds
        is_line = _abs_mean(k0, k1) * L <= turn_tol
    if is_line:
        return "line"
    if slope_tol is not None:
        is_arc = abs(k1 - k0) / L <= slope_tol
    elif kappa_tol is not None:
        is_arc = abs(k1 - k0) <= kappa_tol
    else:   # turning away from the best arc ∫|κ − κ̄| ds = |Δκ|·L/4
        is_arc = abs(k1 - k0) * L / 4.0 <= turn_tol
    return "arc" if is_arc else "clothoid"


def _abs_mean(a: float, b: float) -> float:
    """Mean of |κ| over a segment where κ runs linearly from a to b."""
    if a * b >= 0:
        return 0.5 * (abs(a) + abs(b))
    return 0.5 * (a * a + b * b) / (abs(a) + abs(b))


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def _zone_weights(n: int, corners: list[int], closed: bool, sd: float) -> np.ndarray:
    """1 where κ is trusted, 0 within _ZONE_CORNER·σ of a corner and (open
    strokes) within _ZONE_END·σ of an end. sd = σ in samples."""
    i = np.arange(n)
    w = np.ones(n)
    for c in corners:
        d = np.abs(i - c)
        if closed:
            d = np.minimum(d, n - d)
        w[d < _ZONE_CORNER * sd] = 0.0
    if not closed:
        w[(i < _ZONE_END * sd) | (i > n - 1 - _ZONE_END * sd)] = 0.0
    return w


def _true_arclength_grid(kappa, theta, sm, corners, closed, step, sd, total_turn):
    """Reparametrise per-sample arrays onto a uniform grid of arc length
    *along the smoothed curve*.

    kappa_s resamples the raw polyline, whose length is inflated by jitter
    (≈ 10–25 % at 0.5 px noise on 1 px spacing) before smoothing; κ is the
    geometric curvature of the smoothed curve, so integrating it over the raw
    parameter over-counts turning and stretches every length. Here the speed
    |dsm/du| is measured, replaced by its median inside end and corner zones
    (where the drop in speed is the smoothing cutting a corner or the end pad,
    not geometry), integrated to true arc length S, and κ, θ, sm are
    interpolated onto a uniform S grid of at most _MAX_SAMPLES points (long
    strokes get a coarser grid: the stage-2 cost is ~linear in samples
    times knots, so this bounds run time). Returns (kappa, theta, sm, corners,
    step, speed_ratio).
    """
    n = len(kappa)
    if closed:
        d = (np.roll(sm, -1, axis=0) - np.roll(sm, 1, axis=0)) / (2 * step)
    else:
        d = np.gradient(sm, step, axis=0)
    v = np.linalg.norm(d, axis=1)
    w = _zone_weights(n, corners, closed, sd)
    vmed = float(np.median(v[w > 0])) if (w > 0).sum() >= 4 else float(np.median(v))
    vmed = max(vmed, 1e-6)
    v = np.where(w > 0, v, vmed)
    if closed:
        ve = np.append(v, v[0])
        S = _cumtrapz(ve, step)
        L = float(S[-1])
        n2 = min(max(int(round(L / step)), 8), _MAX_SAMPLES)
        step2 = L / n2
        g = np.arange(n2) * step2
        ke = np.append(kappa, kappa[0])
        te = np.append(theta, theta[0] + total_turn)
        se = np.vstack([sm, sm[:1]])
    else:
        S = _cumtrapz(v, step)
        L = float(S[-1])
        n2 = min(max(int(round(L / step)), 1) + 1, _MAX_SAMPLES)
        step2 = L / (n2 - 1)
        g = np.linspace(0.0, L, n2)
        ke, te, se = kappa, theta, sm
        S = S.copy()
    k2 = np.interp(g, S, ke)
    t2 = np.interp(g, S, te)
    s2 = np.column_stack([np.interp(g, S, se[:, 0]), np.interp(g, S, se[:, 1])])
    c2 = sorted({int(round(S[c] / step2)) % n2 if closed else
                 int(min(round(S[c] / step2), n2 - 1)) for c in corners})
    return k2, t2, s2, c2, step2, vmed


_FIT_MEMO: "OrderedDict[bytes, Fit]" = OrderedDict()
_FIT_MEMO_MAX = 4096
_FIT_MEMO_LOCK = threading.Lock()


def fit_stroke(points, *, sigma: float, step: float | None = None, closed: bool = False,
               penalty: float | None = None, kappa_tol: float | None = None,
               corner_angle: float = float(np.deg2rad(35)),
               turn_tol: float | None = None, slope_tol: float | None = None) -> Fit:
    """Fit a stroke's κ(s) with line / arc / clothoid segments and corners
    (see `_fit_stroke`). Memoised per process on the exact input bytes and
    arguments (speed only: a fit is deterministic, so a hit is the fit a
    re-run would return; a chart redrawn through another hand, or with
    another `amount`, refits the very same polylines). Returns a fresh copy."""
    pts = np.ascontiguousarray(np.asarray(points, dtype=np.float64))
    key = hashlib.sha256(pts.tobytes() + repr((pts.shape, float(sigma), step, bool(closed), penalty, kappa_tol,
                                               float(corner_angle), turn_tol, slope_tol)).encode()).digest()
    with _FIT_MEMO_LOCK:
        hit = _FIT_MEMO.get(key)
        if hit is not None:
            _FIT_MEMO.move_to_end(key)
            return copy.deepcopy(hit)
    fit = _fit_stroke(points, sigma=sigma, step=step, closed=closed, penalty=penalty, kappa_tol=kappa_tol,
                      corner_angle=corner_angle, turn_tol=turn_tol, slope_tol=slope_tol)
    with _FIT_MEMO_LOCK:
        _FIT_MEMO[key] = copy.deepcopy(fit)
        while len(_FIT_MEMO) > _FIT_MEMO_MAX:
            _FIT_MEMO.popitem(last=False)
    return fit


def _fit_stroke(points, *, sigma: float, step: float | None = None, closed: bool = False,
                penalty: float | None = None, kappa_tol: float | None = None,
                corner_angle: float = float(np.deg2rad(35)),
                turn_tol: float | None = None, slope_tol: float | None = None) -> Fit:
    """Fit a stroke's κ(s) with line / arc / clothoid segments and corners.

    points: (N, 2) polyline (px), never mutated. sigma: smoothing scale
    (px, along the raw polyline) for curvature.kappa_s. step: resampling
    step (px), default σ/4. closed: closed stroke (points do not repeat the
    first one). penalty: λ per knot (stage-2 SSE units: px² summed over
    samples); default BIC-like (module docstring). corner_angle: turning
    (rad) within ±2σ that makes a corner.
    Classification (module docstring): by default a segment is a line if
    ∫|κ|ds ≤ turn_tol and an arc if |Δκ|·length/4 ≤ turn_tol; turn_tol
    (rad) defaults to max(3·σ_θ, 2°). kappa_tol (1/px) switches to absolute
    rules: line if max|κ| ≤ kappa_tol, arc if |Δκ| ≤ kappa_tol. slope_tol
    (1/px²) overrides the arc rule with |dκ/ds| ≤ slope_tol.
    Arc-length positions in the result are along the smoothed stroke.
    Deterministic; returns a Fit.
    """
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    step = float(step) if step is not None else max(sigma / 4.0, 1e-6)
    pts = np.array(points, dtype=np.float64, copy=True)
    _s, kappa0, sm0 = kappa_s(pts, sigma, step=step, closed=closed)
    n0 = len(kappa0)
    sd0 = sigma / step
    # too short to analyse: open strokes need trusted samples between the end
    # zones; a closed loop shorter than _CLOSED_MIN_LEN·σ is shrunk by the
    # smoothing toward its centroid (fundamental attenuated by
    # exp(−½(2πσ/L)²)), so its measured κ and length are meaningless
    if n0 < 8 or (not closed and n0 < 2 * _ZONE_END * sd0 + 8) \
            or (closed and n0 < _CLOSED_MIN_LEN * sd0):
        T0 = n0 * step if closed else max(n0 - 1, 0) * step
        return _tiny_fit(pts, sm0, sigma, step, T0, closed)

    theta0 = _theta(sm0, closed)
    total_turn = float(theta0[-1] - theta0[0] + _wrap(theta0[0] - theta0[-1])) if closed else 0.0
    ns0 = (lambda x: max(int(round(x * sd0)), 1))
    cidx0 = _detect_corners(theta0, kappa0, closed, ns0(_CORNER_HALF), ns0(_CORNER_SUPPRESS),
                            float(corner_angle), total_turn, ns0(_ZONE_CORNER + 0.5))

    # --- true arc length of the smoothed curve -------------------------------
    kappa, theta, sm, cidx, step, ratio = _true_arclength_grid(
        kappa0, theta0, sm0, cidx0, closed, step, sd0, total_turn)
    sig = sigma * ratio                      # smoothing scale in true arc length
    n = len(kappa)
    T = n * step if closed else float((n - 1) * step)
    sd = sig / step

    def ns(x: float) -> int:  # σ multiples → samples
        return max(int(round(x * sd)), 1)

    # --- unroll (closed: start at the first corner, or at sample 0) --------
    roll = cidx[0] if (closed and cidx) else 0
    kap_u = np.roll(kappa, -roll)
    cu = sorted((c - roll) % n for c in cidx) if closed else list(cidx)
    if closed and not cu:
        pieces = [(0, n, True)]
    else:
        bnd = cu + [n] if closed else [0] + cu + [n - 1]
        pieces = [(bnd[i], bnd[i + 1], False) for i in range(len(bnd) - 1)
                  if bnd[i + 1] > bnd[i]]
    interior_corners = cu[1:] if closed else cu    # closed: cu[0] is the seam
    # interior knots keep clear of the untrusted zones at piece bounds
    m_end, m_cor = ns(_ZONE_END + 1.0), ns(_ZONE_CORNER + 1.0)
    margins = []
    for (a, b, per) in pieces:
        ma = m_end if (not closed and a == 0) else m_cor
        mb = m_end if (not closed and b == n - 1) else m_cor
        margins.append((ma, mb))

    w = _zone_weights(n, cu, closed, sd)
    if w.sum() < 8:
        return _tiny_fit(pts, sm0, sigma, step, T, closed)
    valid = w > 0
    n_eff = max(w.sum() / sd, np.e)

    # --- noise estimates -----------------------------------------------------
    sigma_t = _diff_noise(_cumtrapz(kap_u, step), valid, ns(3.0), 3)   # θ (rad)
    # residual tangent wiggle lengthens the smoothed curve by ≈ (1 + σ_θ²/2);
    # undo it so lengths (and κ = turning / length) are those of the stroke
    infl = 1.0 + 0.5 * sigma_t ** 2
    step, sig, T = float(step / infl), float(sig / infl), float(T / infl)
    kap_u = kap_u * infl
    theta_m = _cumtrapz(kap_u, step)
    y_m = _cumtrapz(theta_m, step)
    sigma_n = _diff_noise(kap_u, valid, ns(2.0), 2)       # κ (1/px)
    sigma_y = _diff_noise(y_m, valid, ns(3.0), 4)         # lateral (px)
    s_y = max(sigma_y, _FLOOR_Y * sig)
    lam = float(penalty) if penalty is not None else \
        _PEN_C * 2.0 * s_y ** 2 * sd * np.log(n_eff)
    ttol = float(turn_tol) if turn_tol is not None else max(_TURN_Z * sigma_t, _TURN_FLOOR)
    min_k = ns(_MIN_SEG)                            # minimum knot spacing (samples)

    # --- stage 1: McCrae DP on (adaptively pre-smoothed) κ ------------------
    mode = "wrap" if closed else "nearest"
    abs_floor = _FLOOR_ABS / sig
    for mult in (0.0, 0.5, 1.0, 2.0, 4.0):
        kk = gaussian_filter1d(kap_u, mult * sd, mode=mode) if mult > 0 else kap_u
        stot = float(np.hypot(1.0, mult))
        sn1 = _diff_noise(kk, valid, ns(2.0 * stot), 2)
        ks1 = float(np.percentile(np.abs(kk[valid]), 90))
        if sn1 <= 0.1 * ks1 or sn1 <= abs_floor:
            break
    s_eff1 = max(sn1, _FLOOR_REL_1 * ks1, abs_floor)
    lam1 = 2.0 * s_eff1 ** 2 * sd * stot * np.log(n_eff)
    stride0 = max(int(round(0.5 * sd)), 1)
    idx_all = np.arange(n)
    knots: list[np.ndarray] = []
    for (a, b, per), (ma, mb) in zip(pieces, margins):
        idx = np.nonzero((idx_all >= a) & (idx_all <= b) & valid)[0]
        interior: list[int] = []
        if len(idx) >= 2 * min_k:
            stride = max(stride0, int(np.ceil(len(idx) / _MAX_CANDIDATES)))
            f = _dp_breaks(idx * step, kk[idx], lam1, stride, max(min_k, ns(mult)))
            interior = [int(idx[k]) for k in f]
        if per:
            K = np.array(sorted(set([0] + interior)), dtype=int)
        else:
            K = np.array([a] + [x for x in interior if a + ma <= x <= b - mb] + [b],
                         dtype=int)
        knots.append(K)

    # --- stage 2: greedy refinement on the whitened, smoothing-aware model -
    model = _Model(kap_u, w, pieces, interior_corners, sd, step,
                   prior=s_y ** 2 * (sig / _KAPPA_PRIOR) ** 2)
    knots, cur = _greedy(model, knots, pieces, margins, n, min_k, lam,
                         max(ns(1.0), int(np.ceil(n / _MAX_GRID))), valid)

    # --- classify, constrain, refit ----------------------------------------
    _, vals, _ = model.solve(knots)
    raw = _segments_from(knots, vals, pieces, n)
    kinds = []
    for (a, b, k0, k1, _p) in raw:
        # judge each segment on the stretch where κ was actually measured
        # (end and corner zones only extrapolate the spline)
        ii = np.arange(a, b + 1) % n
        good = np.nonzero(valid[ii])[0]
        if len(good) >= 2 and b > a:
            fa, fb = good[0] / (b - a), good[-1] / (b - a)
            k0c, k1c = k0 + (k1 - k0) * fa, k0 + (k1 - k0) * fb
            kinds.append(_classify(k0c, k1c, (good[-1] - good[0]) * step, ttol,
                                   kappa_tol, slope_tol, _TURN_MIN_LEN * sig))
        else:
            kinds.append(_classify(k0, k1, (b - a) * step, ttol, kappa_tol, slope_tol,
                                   _TURN_MIN_LEN * sig))
    kinds = _resolve_conflicts(raw, kinds, pieces, step, ttol, kappa_tol, _TURN_MIN_LEN * sig)
    if kappa_tol is None and slope_tol is None and turn_tol is None:
        # default thresholds: check them against the data (explicit
        # overrides are taken as given)
        s_v = max(sigma_y, _FLOOR_Y_VERIFY * sig)
        lam_v = _PEN_C * 2.0 * s_v ** 2 * sd * np.log(n_eff)
        knots, kinds, vals_c = _verify_labels(model, knots, pieces, margins, n, min_k, kinds,
                                              model.sse(knots), lam_v)
    else:
        _, vals_c, _ = model.solve(knots, _constraint_map(knots, pieces, kinds))
    raw_c = _segments_from(knots, vals_c, pieces, n)

    merged: list[list] = []
    for (a, b, k0, k1, p), kd in zip(raw_c, kinds):
        if kd == "line":
            k0 = k1 = 0.0
        elif kd == "arc":
            k0 = k1 = 0.5 * (k0 + k1)
        if (merged and merged[-1][4] == p and merged[-1][5] == kd and kd != "clothoid"
                and abs(merged[-1][3] - k0) <= 1e-12 + 1e-9 * abs(k0)):
            merged[-1][1] = b
        else:
            merged.append([a, b, k0, k1, p, kd])
    if pieces[0][2] and len(merged) > 1:           # periodic: merge across the seam
        f0, fl = merged[0], merged[-1]
        if f0[5] == fl[5] != "clothoid" and abs(f0[2] - fl[3]) <= 1e-12 + 1e-9 * abs(f0[2]):
            merged[-1] = [fl[0], f0[1] + n, fl[2], f0[3], fl[4], fl[5]]
            merged.pop(0)
    segments = [Segment(kd, float((a + roll) * step), float((b + roll) * step),
                        float(k0), float(k1)) for (a, b, k0, k1, _p, kd) in merged]

    # --- corner angles: jump of (measured θ − fitted ∫κ) across each corner,
    # each side averaged over up to _CORNER_AVG·σ of trusted samples ---------
    corners_s = [float((c + roll) * step) for c in cu]
    th_u = np.array([theta[(i + roll) % n] + ((i + roll) // n) * total_turn
                     for i in range(n)]) if closed else theta.copy()
    kfit = np.zeros(n)
    for (a, b, k0, k1, _p, _kd) in merged:
        ii = np.arange(a, b)
        kfit[ii % n] = k0 + (k1 - k0) * (ii - a) / max(b - a, 1)
    if not closed:
        kfit[n - 1] = merged[-1][3]
    big_theta = _cumtrapz(kfit, step)
    fit_total = float(big_theta[-1] + (0.5 * (kfit[-1] + kfit[0]) * step if closed else 0.0))
    resid = th_u - big_theta
    W = ns(_CORNER_AVG)
    hw = ns(4.0)
    angles = []
    for j, c in enumerate(cu):
        # each side stops halfway to the neighbouring corner: resid jumps at
        # every corner, so a window reaching past the next one measures the
        # sum of both turns (a zig-zag's two ±90° corners came out ≈ 0)
        if closed:
            pc = cu[j - 1] - (n if j == 0 else 0)
            nc = cu[j + 1] if j + 1 < len(cu) else cu[0] + n
        else:
            pc = cu[j - 1] if j > 0 else c - 2 * W - 2
            nc = cu[j + 1] if j + 1 < len(cu) else c + 2 * W + 2
        lo_lim, hi_lim = (pc + c) // 2, (c + nc + 1) // 2
        bi = np.arange(max(c - W, lo_lim + 1), c)
        ai = np.arange(c + 1, min(c + W, hi_lim - 1) + 1)
        if closed:
            bv, av = bi % n, ai % n
            b_off = np.where(bi < 0, -(total_turn - fit_total), 0.0)
        else:
            keep_b, keep_a = bi >= 0, ai < n
            bi, ai = bi[keep_b], ai[keep_a]
            bv, av, b_off = bi, ai, np.zeros(len(bi))
        mb, ma = valid[bv], valid[av]
        if mb.sum() >= 2 and ma.sum() >= 2:
            ang = np.mean(resid[av][ma]) - np.mean((resid[bv] + b_off)[mb])
        else:                                # fall back to the window ends
            lo, hi = max(c - hw, lo_lim), min(c + hw, hi_lim)
            if not closed:
                lo, hi = max(lo, 0), min(hi, n - 1)
            ft = _integrate_segments(segments, (lo + roll) * step, (hi + roll) * step,
                                     T if closed else None)
            ang = (_theta_at(theta, hi + roll, n, closed, total_turn)
                   - _theta_at(theta, lo + roll, n, closed, total_turn) - ft)
        # a corner is an instantaneous turn: only its angle mod 2π acts on
        # the geometry, so report it in (−π, π]
        angles.append(float(-_wrap(-ang)))

    pred = model.kappa_pred(knots, vals_c)
    rms_k = float(np.sqrt(np.mean((kap_u[valid] - pred[valid]) ** 2)))
    fit = Fit(segments, corners_s, float(sigma), rms_k, 0.0, angles, float(T),
              bool(closed), float(step), float(sigma_n), float(sigma_t), float(sigma_y),
              float(ttol), float(kappa_tol) if kappa_tol is not None else 0.0, float(lam))
    start_idx = (merged[0][0] + roll) % n if closed else 0
    pos_err = _position_error(fit, np.roll(sm, -start_idx, axis=0), step)
    return replace(fit, rms_position_error=pos_err)


def _greedy(model: _Model, knots: list[np.ndarray], pieces: list[tuple[int, int, bool]],
            margins: list[tuple[int, int]], n: int, min_k: int, lam: float, gstride: int,
            valid: np.ndarray):
    """Stage 2: knot position hill-climbing, removal (with neighbour
    re-optimisation) when it costs < lam, insertion on a grid when it gains
    > lam. Knots stay ≥ min_k apart and ≥ margins from piece bounds.
    Returns (knots, sse)."""

    def movable(cfg, p: int) -> range:
        return range(len(cfg[p])) if pieces[p][2] else range(1, len(cfg[p]) - 1)

    def limits(cfg, p: int, i: int) -> tuple[int, int]:
        K = cfg[p]
        if pieces[p][2]:
            if len(K) == 1:
                return int(K[0]) - n // 2, int(K[0]) + n // 2
            lo = K[i - 1] if i > 0 else K[-1] - n
            hi = K[i + 1] if i < len(K) - 1 else K[0] + n
            return int(lo) + min_k, int(hi) - min_k
        lo = K[i - 1] + (margins[p][0] if i == 1 else min_k)
        hi = K[i + 1] - (margins[p][1] if i == len(K) - 2 else min_k)
        return int(lo), int(hi)

    def put(cfg, p: int, K) -> list[np.ndarray]:
        out = list(cfg)
        K = np.asarray(K, dtype=int)
        out[p] = np.sort(np.mod(K, n)) if pieces[p][2] else np.sort(K)
        return out

    def move(cfg, e0: float, p: int, i: int):
        """Integer hill-climb of knot i (expanding steps, then ±1 polish)."""
        lo, hi = limits(cfg, p, i)
        x0 = int(cfg[p][i])
        if hi < lo:
            return cfg, e0, False

        def f(x: int):
            K2 = cfg[p].copy()
            K2[i] = x
            tr = put(cfg, p, K2)
            return model.sse(tr), tr

        bx, bf, bt = x0, e0, None
        for d in (1, -1):
            h = 1
            while lo <= bx + d * h <= hi:
                e, tr = f(bx + d * h)
                if e < bf:
                    bx, bf, bt = bx + d * h, e, tr
                    h *= 2
                else:
                    break
            if bt is not None:
                break
        if bt is None:
            return cfg, e0, False
        improved = True
        while improved:
            improved = False
            for d in (1, -1):
                if lo <= bx + d <= hi:
                    e, tr = f(bx + d)
                    if e < bf:
                        bx, bf, bt, improved = bx + d, e, tr, True
        # keep the index stable for the caller: knots stay sorted because
        # moves are bounded by the neighbours
        return bt, bf, True

    def sweep(cfg, e0: float, max_sweeps: int = 8, only=None):
        for _ in range(max_sweeps):
            moved = False
            for p in range(len(pieces)):
                for i in movable(cfg, p):
                    if only is not None and (p, i) not in only:
                        continue
                    if i < len(cfg[p]):
                        cfg, e0, m = move(cfg, e0, p, i)
                        moved |= m
            if not moved:
                break
        return cfg, e0

    cur = model.sse(knots)
    knots, cur = sweep(knots, cur)
    for _ in range(_MAX_ITERS):
        # removal: drop each knot, re-optimise its two neighbours, keep the
        # cheapest; accept if it costs less than λ
        best = (np.inf, None)
        for p in range(len(pieces)):
            if pieces[p][2] and len(knots[p]) <= 1:
                continue
            for i in movable(knots, p):
                tr = put(knots, p, np.delete(knots[p], i))
                e = model.sse(tr)
                if e - cur < 4 * lam:          # only polish plausible removals
                    L = len(tr[p])
                    nb = {(p, (i - 1) % L), (p, i % L)} if pieces[p][2] else {(p, i - 1), (p, i)}
                    tr, e = sweep(tr, e, 2, only=nb)
                if e < best[0]:
                    best = (e, tr)
        if best[1] is not None and best[0] - cur < lam:
            knots, cur = best[1], best[0]
            knots, cur = sweep(knots, cur, 2)
            continue
        # insertion: the best grid position, if it is worth more than λ
        best = (cur, None)
        for x in range(gstride // 2, n, gstride):
            if not valid[x]:
                continue
            p = next(q for q, (a, b, _per) in enumerate(pieces)
                     if a <= x < b or (q == len(pieces) - 1 and x <= b))
            K = knots[p]
            a, b, per = pieces[p]
            d = np.abs(K - x)
            if per:
                d = np.minimum(d, n - d)
            elif x - a < margins[p][0] or b - x < margins[p][1]:
                continue
            if d.min() < min_k:
                continue
            tr = put(knots, p, np.append(K, x))
            e = model.sse(tr)
            if e < best[0]:
                best = (e, tr)
        if best[1] is not None and cur - best[0] > lam:
            knots, cur = sweep(best[1], best[0], 3)
            continue
        break
    return knots, cur


def _resolve_conflicts(raw: list, kinds: list[str], pieces: list[tuple[int, int, bool]],
                       step: float, ttol: float, kappa_tol: float | None,
                       min_len: float = 0.0) -> list[str]:
    """Make the labels realisable by a κ-continuous spline.

    A line pins its end knots to κ = 0 and an arc ties its two knots, so a
    line sharing a knot with an arc would force the arc to κ = 0 (a G2
    spline cannot jump from 0 to an arc's κ). The turning-based line rule
    can produce this for a short stretch of an arc. Each such line is
    relabelled "arc" when its κ is within tolerance of the arc's (it is a
    piece of that arc) and "clothoid" otherwise; repeat until no conflict.
    """
    kinds = list(kinds)
    order = list(range(len(raw)))
    pairs = []
    for i in order[:-1]:
        if raw[i][4] == raw[i + 1][4]:
            pairs.append((i, i + 1))
    for p, (_a, _b, per) in enumerate(pieces):
        if per:
            idx = [i for i in order if raw[i][4] == p]
            if len(idx) > 1:
                pairs.append((idx[-1], idx[0]))

    def close(i: int, k: float) -> bool:
        a, b, k0, k1, _p = raw[i]
        if kappa_tol is not None:
            return max(abs(k0 - k), abs(k1 - k)) <= kappa_tol
        return _abs_mean(k0 - k, k1 - k) * max((b - a) * step, min_len) <= ttol

    changed = True
    while changed:
        changed = False
        for i, j in pairs:
            if {kinds[i], kinds[j]} == {"line", "arc"}:
                li, ai = (i, j) if kinds[i] == "line" else (j, i)
                ka = 0.5 * (raw[ai][2] + raw[ai][3])
                kinds[li] = "arc" if close(li, ka) else "clothoid"
                changed = True
    return kinds


def _polish(model: "_Model", knots: list[np.ndarray], pieces: list[tuple[int, int, bool]],
            margins: list[tuple[int, int]], n: int, min_k: int, P: np.ndarray,
            sweeps: int = 2) -> tuple[list[np.ndarray], float]:
    """Integer hill-climb of every movable knot under constraint map P
    (labels fixed). Returns (knots, sse)."""
    knots = [K.copy() for K in knots]
    e0 = model.solve(knots, P)[0]
    for _ in range(sweeps):
        moved = False
        for p, (a, b, per) in enumerate(pieces):
            K = knots[p]
            idx = range(len(K)) if per else range(1, len(K) - 1)
            for i in idx:
                if per:
                    if len(K) < 2:
                        continue
                    lo = (K[i - 1] if i > 0 else K[-1] - n) + min_k
                    hi = (K[i + 1] if i < len(K) - 1 else K[0] + n) - min_k
                else:
                    lo = K[i - 1] + (margins[p][0] if i == 1 else min_k)
                    hi = K[i + 1] - (margins[p][1] if i == len(K) - 2 else min_k)
                for d in (1, -1):
                    while lo <= K[i] + d <= hi:
                        K2 = K.copy()
                        K2[i] += d
                        if per and (K2[i] < 0 or K2[i] >= n):
                            break           # keep periodic order simple
                        trial = knots[:p] + [K2] + knots[p + 1:]
                        e = model.solve(trial, P)[0]
                        if e < e0:
                            knots, e0, K, moved = trial, e, K2, True
                        else:
                            break
        if not moved:
            break
    return knots, e0


def _verify_labels(model: "_Model", knots: list[np.ndarray],
                   pieces: list[tuple[int, int, bool]], margins: list[tuple[int, int]],
                   n: int, min_k: int, kinds: list[str], sse_free: float,
                   lam: float) -> tuple[list[np.ndarray], list[str], np.ndarray]:
    """Constrained refit with a check of the labels against the data.

    The threshold rules judge each segment alone, but a constraint couples
    neighbours (pinning a short "line" to κ = 0 drags both adjacent
    clothoids). Under the labels' constraints the knots are re-polished;
    then, while the constrained fit costs more than _VERIFY_K·λ_v per
    removed parameter (a pinned or tied knot value) over the free fit, the
    single line/arc label whose release recovers the most SSE becomes
    "clothoid". `lam` is λ_v (the knot penalty with a coarser floor).
    Returns (knots, kinds, constrained knot values)."""
    kinds = list(kinds)
    m = sum(len(K) for K in knots)

    def cost(kn, kd):
        P = _constraint_map(kn, pieces, kd)
        return model.solve(kn, P)[0], m - P.shape[1], P

    def bad(e, removed):
        return removed > 0 and e - sse_free > removed * lam * _VERIFY_K

    e, removed, P = cost(knots, kinds)
    if bad(e, removed):                  # first let the knots settle under the labels
        knots, e = _polish(model, knots, pieces, margins, n, min_k, P)
        relaxed = False
        while bad(e, removed):
            best = None
            for i, kd in enumerate(kinds):
                if kd == "clothoid":
                    continue
                trial = kinds[:i] + ["clothoid"] + kinds[i + 1:]
                e2, r2, P2 = cost(knots, trial)
                if best is None or e2 < best[0]:
                    best = (e2, r2, P2, trial)
            if best is None:
                break
            e, removed, P, kinds = best
            relaxed = True
        if relaxed:
            knots, e = _polish(model, knots, pieces, margins, n, min_k, P)
    _, v, _ = model.solve(knots, P)
    return knots, kinds, v


def _theta_at(theta: np.ndarray, j: int, n: int, closed: bool, total: float) -> float:
    """Unwrapped tangent angle at any integer sample index (closed strokes
    continue by whole turns)."""
    if not closed:
        return float(theta[min(max(j, 0), n - 1)])
    return float(theta[j % n] + (j // n) * total)


def _constraint_map(knots: list[np.ndarray], pieces: list[tuple[int, int, bool]],
                    kinds: list[str]) -> np.ndarray:
    """Matrix P (knots × free params): lines pin both end values to 0, arcs
    tie their two end values (union-find over knot values)."""
    offs, m = [], 0
    for K in knots:
        offs.append(m)
        m += len(K)
    ends = []
    for p, (_a, _b, per) in enumerate(pieces):
        L = len(knots[p])
        if per:
            ends += [(offs[p] + i, offs[p] + (i + 1) % L) for i in range(L)]
        elif L == 1:
            ends.append((offs[p], offs[p]))
        else:
            ends += [(offs[p] + i, offs[p] + i + 1) for i in range(L - 1)]
    parent = list(range(m))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    zero = set()
    for (i0, i1), kd in zip(ends, kinds):
        if kd == "line":
            zero.update((i0, i1))
        elif kd == "arc":
            parent[find(i0)] = find(i1)
    zero_roots = {find(i) for i in zero}
    roots = sorted({find(i) for i in range(m)} - zero_roots)
    col = {r: j for j, r in enumerate(roots)}
    P = np.zeros((m, max(len(roots), 1)))
    for i in range(m):
        r = find(i)
        if r in col:
            P[i, col[r]] = 1.0
    return P


def _tiny_fit(pts, sm, sigma, step, T, closed) -> Fit:
    """Strokes too short to analyse at this σ: one arc or line with the
    stroke's own turning spread over its length T.

    The turning is taken from geometry that heavy smoothing cannot inflate:
    open strokes use the end-to-end tangent change of the smoothed curve;
    closed strokes use the turning number of the raw polygon (sum of its
    wrapped exterior angles, an integer number of turns whatever the
    jitter), since smoothing a loop with σ comparable to its length shrinks
    it toward its centroid and blows its measured κ up without bound. (The
    mean measured κ, which this used to return, is per unit of RAW length
    on a shrunken curve: κ·T then over-counts the turning arbitrarily.)
    """
    p = np.asarray(pts, dtype=np.float64)
    e = np.diff(np.vstack([p, p[:1]]) if closed else p, axis=0)
    el = np.hypot(e[:, 0], e[:, 1])
    if el.sum() > 0:                  # the stroke's own length (the analysis
        T = float(el.sum())           # grid rounds it to whole steps of σ/4)
    T = max(float(T), 0.0)
    turn = 0.0
    if closed:
        e = e[el > 1e-12]
        if len(e) >= 3:
            h = np.arctan2(e[:, 1], e[:, 0])
            turn = 2 * np.pi * round(float(np.sum(_wrap(np.roll(h, -1) - h))) / (2 * np.pi))
    elif len(sm) >= 3:
        th = _theta(sm, False)
        turn = float(th[-1] - th[0])
    k = turn / T if T > 0 else 0.0
    kd = "line" if abs(turn) <= _TURN_FLOOR else "arc"
    kv = k if kd == "arc" else 0.0
    seg = Segment(kd, 0.0, T, kv, kv)
    fit = Fit([seg], [], float(sigma), 0.0, 0.0, [], T, bool(closed),
              float(step), turn_tol=float(_TURN_FLOOR))
    if len(sm) >= 2 and T > 0:
        fit = replace(fit, rms_position_error=_position_error(fit, sm, step))
    return fit


def _integrate_segments(segments: list[Segment], lo: float, hi: float,
                        period: float | None) -> float:
    """∫ κ ds of the fitted (corner-free) κ over [lo, hi] (rad)."""
    tot = 0.0
    shifts = [0.0] if period is None else [-period, 0.0, period]
    for g in segments:
        for sh in shifts:
            a, b = max(g.s0 + sh, lo), min(g.s1 + sh, hi)
            if b <= a:
                continue
            ka = g.k0 + g.slope * (a - g.s0 - sh)
            kb = g.k0 + g.slope * (b - g.s0 - sh)
            tot += 0.5 * (ka + kb) * (b - a)
    return tot


def _runs(fit: Fit) -> list[tuple[list[Segment], float]]:
    """Split segments into corner-free runs; each run paired with the corner
    angle applied *before* it (0 for the first run)."""
    tol = max(fit.step, 1e-9) * 0.5
    L = fit.length
    def at_corner(x: float) -> int | None:
        for j, c in enumerate(fit.corners):
            d = abs(x - c)
            if fit.closed and L > 0:
                d = min(d % L, L - d % L)
            if d <= tol:
                return j
        return None
    runs: list[tuple[list[Segment], float]] = []
    cur: list[Segment] = []
    turn = 0.0
    for i, g in enumerate(fit.segments):
        j = at_corner(g.s0) if i > 0 else None
        if j is not None and cur:
            runs.append((cur, turn))
            cur, turn = [], fit.corner_angles[j] if j < len(fit.corner_angles) else 0.0
        cur.append(g)
    if cur:
        runs.append((cur, turn))
    return runs


def reconstruct(fit: Fit, start=(0.0, 0.0), heading: float = 0.0,
                step: float | None = None) -> np.ndarray:
    """Re-integrate a fit into a polyline with curvature.integrate_kappa.

    start: (x, y) of the first point (px); heading: initial tangent angle
    (rad); step: point spacing (px), default the fit's analysis step.
    Corners apply their turning angle instantaneously. For a closed fit the
    traversal starts at segments[0].s0 and the last point approximately
    coincides with the first (drop it for a contract-style closed Stroke).
    Returns (N, 2) float64.
    """
    step = float(step) if step is not None else (fit.step or fit.sigma / 4.0)
    pos = np.asarray(start, dtype=np.float64)
    h = float(heading)
    out = [pos[None, :]]
    for run, turn in _runs(fit):
        h += turn
        b = [run[0].s0]
        k = [run[0].k0]
        for g in run:
            # κ may jump between segments only at corners; inside a run the
            # constrained fit is continuous, so k1 of g == k0 of the next.
            b.append(g.s1)
            k.append(g.k1)
        b = np.asarray(b) - b[0]
        if b[-1] <= 0:
            continue
        pts = integrate_kappa(b, np.asarray(k), step, start=pos, heading=h)
        out.append(pts[1:])
        pos = pts[-1]
        h += float(np.sum(0.5 * (np.asarray(k)[1:] + np.asarray(k)[:-1]) * np.diff(b)))
    return np.vstack(out)


def _position_error(fit: Fit, sm: np.ndarray, step: float) -> float:
    """RMS distance (px) from each smoothed point to the reconstructed
    polyline after the least-squares rigid alignment (rotation + translation,
    correspondence by arc length)."""
    rec = reconstruct(fit, (0.0, 0.0), 0.0, step)
    if len(rec) < 2 or len(sm) < 2:
        return 0.0
    seg = np.linalg.norm(np.diff(rec, axis=0), axis=1)
    srec = np.concatenate([[0.0], np.cumsum(seg)])
    u = np.arange(len(sm)) * step
    u = np.clip(u, 0, srec[-1])
    corr = np.column_stack([np.interp(u, srec, rec[:, 0]), np.interp(u, srec, rec[:, 1])])
    # Kabsch: rotate corr onto sm
    mc, ms = corr.mean(axis=0), sm.mean(axis=0)
    H = (corr - mc).T @ (sm - ms)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, d]) @ U.T
    rec_al = (rec - mc) @ R.T + ms
    # dense point-to-polyline distance
    dense_n = max(int(np.ceil(srec[-1] / (step / 4))), 2)
    t = np.linspace(0, srec[-1], dense_n + 1)
    dense = np.column_stack([np.interp(t, srec, rec_al[:, 0]), np.interp(t, srec, rec_al[:, 1])])
    dist, _ = cKDTree(dense).query(sm)
    return float(np.sqrt(np.mean(dist ** 2)))


# ---------------------------------------------------------------------------
# statistics for the measurement panel
# ---------------------------------------------------------------------------

def _mean_abs_kappa(g: Segment) -> float:
    """∫|κ| ds / length for a linear κ (exact, handles a sign change)."""
    a, b, L = g.k0, g.k1, g.length
    if L <= 0:
        return abs(a)
    if a * b >= 0:
        return 0.5 * (abs(a) + abs(b))
    # zero crossing at fraction f
    f = a / (a - b)
    return 0.5 * (abs(a) * f + abs(b) * (1 - f))


def segment_stats(fits: list[Fit], ref_length: float) -> dict:
    """Dimensionless summary of many fits (one drawing) for the panel.

    ref_length: Drawing.ref_length() (px). Rates are per unit of
    stroke length measured in ref_lengths. Keys:

    - n_strokes, total_length (Σ length / ref_length), n_segments, n_corners
    - counts[kind]; rate[kind]: segments of that kind per unit length;
      corner_rate; corner_angle: list of |corner turning| (rad);
      inflection_rate (sign changes of κ within corner-free runs, both inside
      clothoids and across joints, lines skipped)
    - length[kind]: list of segment length / ref_length
    - kappa[kind]: list of mean |κ| · ref_length (arcs, clothoids)
    - slope[kind]: list of |dκ/ds| · ref_length² (clothoids)
    - transition_counts: 3×3 raw counts kind→kind over consecutive segments
      (order KINDS; closed strokes include the wrap joint);
      transition_matrix: row-normalised (rows with no data are zeros);
      transition_counts_at_corners: the subset of joints that are corners.
    All values are plain floats / ints / lists (JSON-serialisable).
    """
    R = float(ref_length) if ref_length > 0 else 1.0
    idx = {k: i for i, k in enumerate(KINDS)}
    counts = {k: 0 for k in KINDS}
    lengths = {k: [] for k in KINDS}
    kap = {k: [] for k in KINDS}
    slp = {k: [] for k in KINDS}
    trans = np.zeros((3, 3), dtype=int)
    trans_c = np.zeros((3, 3), dtype=int)
    total = 0.0
    n_corners = 0
    n_infl = 0
    corner_abs: list[float] = []
    for f in fits:
        total += f.length
        n_corners += len(f.corners)
        corner_abs += [float(abs(a)) for a in f.corner_angles]
        for g in f.segments:
            counts[g.kind] += 1
            lengths[g.kind].append(float(g.length / R))
            if g.kind != "line":
                kap[g.kind].append(float(_mean_abs_kappa(g) * R))
            if g.kind == "clothoid":
                slp[g.kind].append(float(abs(g.slope) * R * R))
        runs = _runs(f)
        corner_joint = set()
        k = 0
        for ri, (run, _t) in enumerate(runs):
            if ri > 0:
                corner_joint.add(k)                 # joint before segment k
            # inflections inside this run
            seq = []
            tol = 1e-12
            for g in run:
                for v in (g.k0, g.k1):
                    if abs(v) > tol:
                        seq.append(np.sign(v))
            n_infl += int(np.sum(np.array(seq[1:]) != np.array(seq[:-1]))) if len(seq) > 1 else 0
            if f.closed and not f.corners and len(seq) > 1 and seq[0] != seq[-1]:
                n_infl += 1                         # the loop closes through the seam
            k += len(run)
        segs = f.segments
        pairs = [(i, i + 1) for i in range(len(segs) - 1)]
        if f.closed and len(segs) > 1:
            pairs.append((len(segs) - 1, 0))
        for i, j in pairs:
            a, b = idx[segs[i].kind], idx[segs[j].kind]
            trans[a, b] += 1
            is_corner = (j in corner_joint) if j != 0 else bool(f.corners) and _starts_at_corner(f)
            if is_corner:
                trans_c[a, b] += 1
    T = total / R if total > 0 else 0.0
    rows = trans.sum(axis=1, keepdims=True)
    mat = np.where(rows > 0, trans / np.maximum(rows, 1), 0.0)
    per = (lambda c: float(c / T) if T > 0 else 0.0)
    return {
        "n_strokes": len(fits),
        "total_length": float(T),
        "n_segments": int(sum(counts.values())),
        "n_corners": int(n_corners),
        "counts": {k: int(v) for k, v in counts.items()},
        "rate": {k: per(v) for k, v in counts.items()},
        "corner_rate": per(n_corners),
        "corner_angle": corner_abs,
        "inflection_rate": per(n_infl),
        "length": lengths,
        "kappa": {k: v for k, v in kap.items() if k != "line"},
        "slope": {"clothoid": slp["clothoid"]},
        "kinds": list(KINDS),
        "transition_counts": trans.tolist(),
        "transition_matrix": mat.tolist(),
        "transition_counts_at_corners": trans_c.tolist(),
    }


def _starts_at_corner(f: Fit) -> bool:
    if not f.segments or not f.corners:
        return False
    s0 = f.segments[0].s0
    L = f.length
    for c in f.corners:
        d = abs(s0 - c)
        if f.closed and L > 0:
            d = min(d % L, L - d % L)
        if d <= max(f.step, 1e-9) * 0.5:
            return True
    return False
