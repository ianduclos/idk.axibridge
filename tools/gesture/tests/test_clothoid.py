"""Tests for gesture.clothoid — the piecewise-linear κ(s) fit.

Ground truth comes from curvature.integrate_kappa (the exact inverse of the
model). Tolerances, stated once:

- break positions on clean strokes: within 2σ of the truth (σ = the
  smoothing scale; a kink in κ is blurred over ~±2σ, and a join between
  two clothoids is only as sharp as their slope change);
- clean strokes: every kind right, rms_position_error < 0.2 % of length;
- noisy strokes (0.3–1 px Gaussian jitter on every 1 px point): kinds right
  on ≥ 75 % of true segments (judged at each segment's midpoint), segment
  count within ±2 on ≥ 90 % of strokes, rms_position_error < 1 px, length
  within 3 % of the true arc length (residual wiggle inflates it slightly).
"""
from __future__ import annotations

import json
import time

import numpy as np
import pytest

from gesture.clothoid import Fit, Segment, fit_stroke, reconstruct, segment_stats
from gesture.curvature import integrate_kappa, resample


# ---------------------------------------------------------------------------
# ground truth
# ---------------------------------------------------------------------------

def random_spec(rng: np.random.Generator, nseg: int):
    """A random G2 sequence of identifiable segments.

    Returns (breaks, kappas, kinds) for integrate_kappa. Identifiability
    rules (otherwise the "truth" is not recoverable even in principle):
    arcs turn ≥ 0.15 rad with |κ| ≥ 0.004; clothoids change κ by ≥ 0.35 rad
    worth (|Δκ|·L); consecutive clothoids change slope visibly; the last
    segment is long enough to be measured past the end zone.
    """
    b, ks, kinds = [0.0], [0.0], []
    kmax = rng.uniform(0.01, 0.03)
    slope_prev = None
    for i in range(nseg):
        cur = ks[-1]
        opts = ["clothoid"]
        if cur == 0.0 and (not kinds or kinds[-1] != "line"):
            opts.append("line")
        if cur != 0.0 and (not kinds or kinds[-1] != "arc"):
            opts.append("arc")
        kd = str(rng.choice(opts))
        L = rng.uniform(60, 130) if i < nseg - 1 else rng.uniform(90, 130)
        if kd == "line":
            nk = 0.0
        elif kd == "arc":
            nk = cur
            if abs(cur) * L < 0.15:
                L = 0.15 / abs(cur) * 1.05
        else:
            for _ in range(50):
                nk = 0.0 if (cur != 0.0 and rng.random() < 0.3) else rng.uniform(-kmax, kmax)
                slope = (nk - cur) / L
                ok = abs(nk - cur) * L >= 0.35
                if nk != 0.0:
                    ok &= abs(nk) >= 0.004
                if kinds and kinds[-1] == "clothoid" and slope_prev is not None:
                    ok &= abs(slope - slope_prev) * L >= 0.004
                if ok:
                    break
            else:
                nk = cur + np.sign(rng.normal() or 1) * 0.4 / L
        slope_prev = (nk - cur) / L if kd == "clothoid" else None
        b.append(b[-1] + L)
        ks.append(float(nk))
        kinds.append(kd)
    return np.array(b), np.array(ks), kinds


def stroke(breaks, kappas, noise=0.0, seed=0):
    pts = integrate_kappa(np.asarray(breaks, float), np.asarray(kappas, float), 1.0)
    if noise:
        pts = pts + np.random.default_rng(seed).normal(0.0, noise, pts.shape)
    return pts


def kind_at(fit: Fit, s: float) -> str | None:
    for g in fit.segments:
        if g.s0 <= s <= g.s1:
            return g.kind
    return None


# ---------------------------------------------------------------------------
# single primitives
# ---------------------------------------------------------------------------

def test_straight_line_is_one_line():
    pts = np.column_stack([np.linspace(0, 300, 301), np.linspace(0, 120, 301)])
    f = fit_stroke(pts, sigma=3.0)
    assert f.kinds() == ["line"]
    assert f.corners == []
    assert abs(f.length - np.hypot(300, 120)) < 1.0
    assert f.rms_position_error < 0.05


@pytest.mark.parametrize("r", [40.0, 150.0, 600.0])
def test_closed_circle_is_one_arc(r):
    n = int(2 * np.pi * r)
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts = np.column_stack([r * np.cos(t), r * np.sin(t)])
    f = fit_stroke(pts, sigma=4.0, closed=True)
    assert f.kinds() == ["arc"]
    assert abs(abs(f.segments[0].k0) - 1 / r) < 0.01 / r
    assert abs(f.segments[0].length - 2 * np.pi * r) < 0.01 * 2 * np.pi * r
    assert f.corners == []


def test_open_arc_and_single_clothoid():
    f = fit_stroke(stroke([0, 300], [0.01, 0.01]), sigma=3.0)
    assert f.kinds() == ["arc"] and abs(f.segments[0].k0 - 0.01) < 2e-4
    f = fit_stroke(stroke([0, 300], [-0.004, 0.02]), sigma=3.0)
    assert f.kinds() == ["clothoid"]
    assert abs(f.segments[0].slope - 0.024 / 300) < 0.05 * 0.024 / 300


# ---------------------------------------------------------------------------
# sequences
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("breaks,kappas,kinds", [
    ([0, 100, 200, 350], [0, 0.02, 0.02, -0.01], ["clothoid", "arc", "clothoid"]),
    ([0, 80, 150, 260, 330, 420, 500], [0, 0, 0.025, 0.025, -0.015, -0.015, 0],
     ["line", "clothoid", "arc", "clothoid", "arc", "clothoid"]),
    ([0, 150, 230, 480, 560, 700], [0, 0, 0.004, 0.004, 0, 0],      # gentle κ
     ["line", "clothoid", "arc", "clothoid", "line"]),
    ([0, 60, 90, 160, 190, 260], [0.05, 0.05, -0.03, -0.03, 0.04, 0.04],  # tight κ
     ["arc", "clothoid", "arc", "clothoid", "arc"]),
])
def test_hand_built_sequences(breaks, kappas, kinds):
    sigma = 3.0 if max(np.abs(kappas)) < 0.04 else 2.0
    f = fit_stroke(stroke(breaks, kappas), sigma=sigma)
    assert f.kinds() == kinds
    assert np.max(np.abs(np.array(f.breaks()) - np.array(breaks[1:-1]))) <= 2 * sigma
    assert f.rms_position_error < 0.002 * breaks[-1]


def test_random_clean_sequences_recover_breaks_and_kinds():
    rng = np.random.default_rng(7)
    sigma = 3.0
    worst = 0.0
    for _ in range(25):
        b, k, kinds = random_spec(rng, int(rng.integers(3, 9)))
        f = fit_stroke(stroke(b, k), sigma=sigma)
        assert f.kinds() == kinds, (kinds, f.kinds(), b.round(1))
        err = np.max(np.abs(np.array(f.breaks()) - b[1:-1]))
        worst = max(worst, err)
        assert err <= 2 * sigma, (b.round(1), np.round(f.breaks(), 1))
        assert f.rms_position_error < 0.002 * b[-1]
    assert worst > 0.0         # sanity: we did measure something


@pytest.mark.parametrize("noise,sigma", [(0.3, 4.0), (0.5, 5.0), (1.0, 8.0)])
def test_noisy_sequences_degrade_gracefully(noise, sigma):
    rng = np.random.default_rng(11)
    ok = tot = count_ok = 0
    trials = 15
    for t in range(trials):
        b, k, kinds = random_spec(rng, int(rng.integers(3, 9)))
        f = fit_stroke(stroke(b, k, noise, seed=t), sigma=sigma)
        for i, kd in enumerate(kinds):
            tot += 1
            ok += kind_at(f, 0.5 * (b[i] + b[i + 1])) == kd
        count_ok += abs(len(f.segments) - len(kinds)) <= 2
        assert f.rms_position_error < 1.0
        assert abs(f.length - b[-1]) < 0.03 * b[-1]      # true arc length, not jitter
    assert ok / tot >= 0.75, ok / tot
    assert count_ok >= 0.9 * trials


def test_noise_alone_does_not_split():
    splits = 0
    for seed in range(10):
        for kap in (0.0, 0.006):
            f = fit_stroke(stroke([0, 400], [kap, kap], 0.5, seed), sigma=5.0)
            splits += len(f.segments) > 1
            assert kind_at(f, 200) == ("line" if kap == 0 else "arc")
    assert splits <= 2


# ---------------------------------------------------------------------------
# corners
# ---------------------------------------------------------------------------

def test_sharp_90_degree_corner():
    pts = resample(np.array([[0, 0], [200, 0], [200, 150]], float), 1.0)
    f = fit_stroke(pts, sigma=3.0)
    assert len(f.corners) == 1
    assert abs(f.corners[0] - 200.0) <= 2.0
    assert abs(abs(np.rad2deg(f.corner_angles[0])) - 90.0) < 2.0
    assert f.kinds() == ["line", "line"]
    assert f.rms_position_error < 0.5


def test_closed_square_has_four_corners():
    sq = np.array([[0, 0], [200, 0], [200, 200], [0, 200]], float)
    f = fit_stroke(resample(sq, 1.0, closed=True), sigma=3.0, closed=True)
    assert f.kinds() == ["line"] * 4
    assert len(f.corners) == 4
    assert np.allclose(np.abs(np.rad2deg(f.corner_angles)), 90.0, atol=2.0)
    assert abs(f.length - 800.0) < 4.0


def test_corner_between_arcs_does_not_need_kappa_continuity():
    a = integrate_kappa(np.array([0, 150.0]), np.array([0.01, 0.01]), 1.0)
    h = np.arctan2(*(a[-1] - a[-2])[::-1]) + np.deg2rad(100)
    b = integrate_kappa(np.array([0, 150.0]), np.array([-0.012, -0.012]), 1.0,
                        start=a[-1], heading=h)
    f = fit_stroke(np.vstack([a, b[1:]]), sigma=3.0)
    assert len(f.corners) == 1 and abs(f.corners[0] - 150) <= 2.0
    assert f.kinds() == ["arc", "arc"]
    assert abs(f.segments[0].k0 - 0.01) < 5e-4 and abs(f.segments[1].k0 + 0.012) < 5e-4


# ---------------------------------------------------------------------------
# contract: purity, determinism, speed, reconstruction, JSON
# ---------------------------------------------------------------------------

def test_inputs_not_mutated():
    pts = stroke([0, 100, 250], [0, 0.02, -0.01], 0.3)
    before = pts.copy()
    f = fit_stroke(pts, sigma=4.0)
    assert np.array_equal(pts, before)
    segs = list(f.segments)
    reconstruct(f, (1.0, 2.0), 0.3)
    segment_stats([f], 500.0)
    assert f.segments == segs


def test_deterministic():
    pts = stroke([0, 100, 250, 330], [0, 0.02, -0.01, 0.0], 0.5, seed=3)
    a = fit_stroke(pts, sigma=4.0).to_json()
    b = fit_stroke(pts, sigma=4.0).to_json()
    assert json.dumps(a) == json.dumps(b)


def test_speed_2000_samples():
    rng = np.random.default_rng(5)
    br = np.cumsum(np.r_[0, rng.uniform(60, 140, 10)])
    kp = rng.uniform(-0.02, 0.02, 11)
    pts = stroke(br, kp, 0.2)
    sigma = 2.0                                     # step σ/4 → ~2000 samples
    t = time.perf_counter()
    f = fit_stroke(pts, sigma=sigma)
    dt = time.perf_counter() - t
    assert f.length / f.step > 1700
    assert dt < 1.0, dt


def test_reconstruct_matches_truth():
    b, k = [0, 100, 200, 350], [0, 0.02, 0.02, -0.01]
    pts = stroke(b, k)
    f = fit_stroke(pts, sigma=3.0)
    h0 = np.arctan2(*(pts[1] - pts[0])[::-1])
    rec = reconstruct(f, pts[0], h0, step=1.0)
    assert len(rec) == pytest.approx(len(pts), abs=3)
    m = min(len(rec), len(pts))
    assert np.sqrt(np.mean(np.sum((rec[:m] - pts[:m]) ** 2, axis=1))) < 1.5


def test_reconstruct_applies_corners():
    pts = resample(np.array([[0, 0], [100, 0], [100, 100], [0, 100]], float), 1.0)
    f = fit_stroke(pts, sigma=2.0)
    rec = reconstruct(f, pts[0], 0.0)
    assert np.linalg.norm(rec[-1] - pts[-1]) < 3.0


def test_json_round_trip():
    f = fit_stroke(stroke([0, 100, 250], [0, 0.02, -0.01]), sigma=3.0)
    g = Fit.from_json(json.loads(json.dumps(f.to_json())))
    assert g.segments == [Segment.from_json(s.to_json()) for s in f.segments]
    assert g.kinds() == f.kinds() and g.sigma == f.sigma


def test_overrides():
    pts = stroke([0, 100, 200, 350], [0, 0.02, 0.02, -0.01])
    assert fit_stroke(pts, sigma=3.0, kappa_tol=1.0).kinds() == ["line"]
    assert len(fit_stroke(pts, sigma=3.0, penalty=1e9).segments) == 1
    f = fit_stroke(pts, sigma=3.0, slope_tol=1.0)
    assert set(f.kinds()) <= {"line", "arc"}


# ---------------------------------------------------------------------------
# segment_stats
# ---------------------------------------------------------------------------

def test_segment_stats_shape_and_invariance():
    specs = [([0, 80, 150, 260, 330], [0, 0, 0.025, 0.025, -0.01]),
             ([0, 120, 220, 300], [0.01, 0.01, -0.012, -0.012])]
    sq = resample(np.array([[0, 0], [150, 0], [150, 150], [0, 150]], float), 1.0, closed=True)

    def fits(scale: float):
        out = [fit_stroke(stroke(np.array(b) * scale, np.array(k) / scale), sigma=3.0 * scale)
               for b, k in specs]
        out.append(fit_stroke(sq * scale, sigma=3.0 * scale, closed=True))
        return out

    st = segment_stats(fits(1.0), ref_length=400.0)
    json.dumps(st)                                  # plain JSON
    assert st["n_strokes"] == 3 and st["n_corners"] == 4
    assert st["n_segments"] == sum(st["counts"].values())
    assert sum(len(v) for v in st["length"].values()) == st["n_segments"]
    tc = np.array(st["transition_counts"])
    # open strokes: n_seg - 1 joints; closed: n_seg joints
    assert tc.sum() == (4 - 1) + (3 - 1) + 4
    for row, cnt in zip(st["transition_matrix"], tc):
        assert (abs(sum(row) - 1) < 1e-9) if cnt.sum() else sum(row) == 0
    assert np.array(st["transition_counts_at_corners"]).sum() == 4
    assert st["inflection_rate"] > 0 and st["corner_rate"] > 0

    st2 = segment_stats(fits(2.0), ref_length=800.0)   # same drawing, twice the size
    assert st2["counts"] == st["counts"]
    assert st2["transition_counts"] == st["transition_counts"]
    for key in ("total_length", "corner_rate", "inflection_rate"):
        assert st2[key] == pytest.approx(st[key], rel=0.02)
    for kd in ("arc", "clothoid"):
        assert np.allclose(sorted(st2["kappa"][kd]), sorted(st["kappa"][kd]), rtol=0.05)


# ---------------------------------------------------------------------------
# ill-posed pieces (regression: corpus fits returned corner angles of 3e4°
# and −2e9°, κ·ref ≈ 1e9). A piece lying wholly inside end/corner zones has
# no trusted samples, and the near-singular stage-2 solve handed back
# ±1e5/px for its knots; corner-angle windows also reached past neighbouring
# corners, and heavily smoothed small loops collapsed toward their centroid.
# ---------------------------------------------------------------------------

def _sane(f: Fit, sigma: float) -> float:
    """Assert the invariants every fit must keep; return max |κ|."""
    vals = [f.length, f.rms_position_error, f.rms_kappa_error, *f.corner_angles]
    vals += [v for g in f.segments for v in (g.s0, g.s1, g.k0, g.k1)]
    assert np.all(np.isfinite(vals))
    assert all(-np.pi < a <= np.pi for a in f.corner_angles)
    kmax = max(max(abs(g.k0), abs(g.k1)) for g in f.segments)
    assert kmax <= 2.0 / sigma                 # κ beyond ~1/σ is not measurable at σ
    return kmax


@pytest.mark.parametrize("stub", [2.0, 3.0, 4.0, 5.0])
@pytest.mark.parametrize("deg", [100.0, 150.0])
def test_corner_near_open_end_is_finite(stub, deg):
    """Corner < 6σ from an open end: the stub after it is all end/corner
    zone. Used to give |angle| ~ 1e6 rad and κ ~ 1e6/px."""
    sigma, a = 6.0, np.deg2rad(deg)
    L2 = stub * sigma
    pts = resample(np.array([[0, 0], [300, 0], [300 + L2 * np.cos(a), L2 * np.sin(a)]]), 1.0)
    pts = pts + np.random.default_rng(1).normal(0.0, 0.3, pts.shape)
    f = fit_stroke(pts, sigma=sigma)
    _sane(f, sigma)
    assert len(f.corner_angles) == 1
    assert abs(f.corner_angles[0] - a) < 0.15
    assert all(abs(g.turning) < 0.2 for g in f.segments)


@pytest.mark.parametrize("gap", [3.5, 4.5])
def test_close_corners_measure_their_own_turn(gap):
    """Two ±90° corners a few σ apart (an untrusted middle piece): each angle
    is its own turn, not the sum of both (≈ 0) nor a blown-up solve."""
    sigma = 6.0
    g = gap * sigma
    pts = resample(np.array([[0, 0], [200, 0], [200, g], [400, g]], float), 1.0)
    pts = pts + np.random.default_rng(2).normal(0.0, 0.3, pts.shape)
    f = fit_stroke(pts, sigma=sigma)
    _sane(f, sigma)
    assert len(f.corner_angles) == 2
    assert abs(f.corner_angles[0] - np.pi / 2) < 0.1
    assert abs(f.corner_angles[1] + np.pi / 2) < 0.1


@pytest.mark.parametrize("frac", [0.15, 0.3, 0.6, 2.0])
def test_small_loop_heavy_smoothing_is_one_circle(frac):
    """σ comparable to a closed loop's length shrinks the smoothed loop to
    its centroid; the fit must still say 'one circle of this length'
    (was κ ≈ 3.7e4/px at σ = 2L)."""
    r = 20.0
    n = int(2 * np.pi * r)
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts = np.column_stack([r * np.cos(t), r * np.sin(t)])
    f = fit_stroke(pts, sigma=frac * 2 * np.pi * r, closed=True)
    vals = [v for g in f.segments for v in (g.k0, g.k1)]
    assert np.all(np.isfinite(vals))
    assert f.kinds() == ["arc"]
    assert abs(f.segments[0].k0 - 1 / r) < 0.02 / r
    assert abs(f.length - 2 * np.pi * r) < 0.02 * 2 * np.pi * r


def test_short_open_stroke_turning_is_bounded():
    """Below ~9σ an open stroke gets one line/arc; its turning must not exceed
    the stroke's own (mean κ of the shrunken smoothed curve times the raw
    length over-counted it)."""
    for sigma in (8.0, 15.0, 40.0):
        f = fit_stroke(stroke([0, 60], [np.pi / 2 / 60, np.pi / 2 / 60]), sigma=sigma)
        assert len(f.segments) == 1
        assert 0.0 <= f.segments[0].turning <= np.pi / 2 + 0.05


def test_random_corners_near_ends_keep_invariants():
    """Property sweep: polylines with corners anywhere (including within a
    few σ of the ends and of each other), jittered."""
    rng = np.random.default_rng(7)
    for _ in range(25):
        sigma = float(rng.uniform(2.0, 6.0))
        m = int(rng.integers(2, 6))
        lens = rng.uniform(1.5, 12.0, m) * sigma
        heads = np.cumsum(rng.uniform(-2.8, 2.8, m))
        steps = np.column_stack([lens * np.cos(heads), lens * np.sin(heads)])
        pts = np.vstack([[0.0, 0.0], np.cumsum(steps, axis=0)])
        pts = resample(pts, 1.0) + rng.normal(0.0, 0.3, (len(resample(pts, 1.0)), 2))
        _sane(fit_stroke(pts, sigma=sigma), sigma)
