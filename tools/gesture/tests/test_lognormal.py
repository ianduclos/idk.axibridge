"""Tests for gesture.lognormal — sigma-lognormal synthesis, fitting from
static traces, the kinematic hand and its generator. Synthetic only."""
from __future__ import annotations

import numpy as np
import pytest

from gesture import lognormal as ln
from gesture.core import Drawing, Stroke


def test_single_pulse_is_circular_arc():
    # one pulse: length D, heading turns linearly from θs to θe
    P = np.array([[0.0, float(ln.mu_from(1.0, 0.3)), 0.3, 100.0, 0.0, 1.0]])
    pts = ln.synthesize(P, 0.25)
    L = np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1))
    assert L == pytest.approx(100.0 * 0.997, rel=0.01)       # ±3σ span holds 99.7 %
    d = np.diff(pts, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    assert th[-1] - th[0] == pytest.approx(1.0, abs=0.05)
    # constant curvature: radius = D/Δθ
    chord = np.linalg.norm(pts[-1] - pts[0])
    assert chord == pytest.approx(2 * (L / 1.0) * np.sin(0.5), rel=0.02)


def test_duration_mu_roundtrip():
    sig = np.array([0.1, 0.3, 0.6])
    T = np.array([0.2, 1.0, 3.0])
    P = np.column_stack([np.zeros(3), ln.mu_from(T, sig), sig, np.ones(3), np.zeros(3), np.zeros(3)])
    assert np.allclose(ln.duration(P), T)


def test_rows_roundtrip():
    rng = np.random.default_rng(3)
    P = ln.random_pulses(rng, 5)
    rows = ln.pulses_to_rows(P, 1.0)
    P2 = ln.rows_to_pulses(rows, 1.0, theta0=P[0, 4])
    # same pulses up to a global time scale: identical geometry
    assert np.allclose(P2[:, 2:], P[:, 2:], atol=1e-9)
    assert np.allclose(ln.synthesize(P2, 0.5), ln.synthesize(P, 0.5), atol=1e-3 * P[:, 3].sum())


def test_timed_fit_recovers_known_pulses():
    rng = np.random.default_rng(11)
    P = ln.random_pulses(rng, 2, dt=(0.45, 0.6))
    t = ln.time_grid(P, 0.5)
    x = ln.trajectory(P, t)
    tu = np.linspace(t[0], t[-1], 300)
    xu = np.column_stack([np.interp(tu, t, x[:, 0]), np.interp(tu, t, x[:, 1])])
    Pf, info = ln.fit_velocity(tu, xu)
    assert info["snr_v"] >= ln.SNR_TARGET
    assert len(Pf) == 2
    assert np.allclose(np.sort(Pf[:, 3]), np.sort(P[:, 3]), rtol=0.25)


def test_static_fit_geometry_and_purity():
    rng = np.random.default_rng(5)
    P = ln.random_pulses(rng, 4)
    pts = ln.synthesize(P, 0.5)
    before = pts.copy()
    f = ln.fit_stroke(pts, sigma=1.0, R=2000.0)
    assert np.array_equal(pts, before)                       # input untouched
    assert f.snr_v >= 18
    assert f.err_mean / f.length < 0.003                     # geometry reproduced
    assert 2 <= f.n <= 12


def _toy_drawings(seed=0, n=2):
    rng = np.random.default_rng(seed)
    ds = []
    for k in range(n):
        strokes = []
        for j in range(4):
            P = ln.random_pulses(rng, int(rng.integers(3, 6)), D=(60, 140))
            pts = ln.synthesize(P, 0.5) + rng.uniform(150, 650, 2)
            strokes.append(Stroke(pts, width=np.full(len(pts), 2.0)))
        ds.append(Drawing(strokes, source=f"toy{k}", size=(800, 800)))
    return ds


@pytest.fixture(scope="module")
def toy_hand():
    fitted = [ln.fit_drawing(d, select=False) for d in _toy_drawings()]
    return ln.learn(fitted, name="toy"), fitted


def test_learn_and_signature(toy_hand):
    h, fitted = toy_hand
    assert h.meta["n_strokes"] >= 6
    sig = ln.signature(fitted)
    assert sig["pulses_per_R"] > 0 and 0 <= sig["overlap_share"] <= 1
    h2 = ln.Hand.from_json(h.to_json())
    assert h2.strokes == h.strokes


def test_generation_deterministic(toy_hand):
    h, _ = toy_hand
    a = ln.generate_drawing(h, np.random.default_rng(4), (500, 400), ink=1.0)
    b = ln.generate_drawing(h, np.random.default_rng(4), (500, 400), ink=1.0)
    assert len(a.strokes) >= 1
    assert len(a.strokes) == len(b.strokes)
    for s, t in zip(a.strokes, b.strokes):
        assert np.array_equal(s.points, t.points)
    for s in a.strokes:                                      # stays on the sheet
        assert (s.points >= 20 - 1e-6).all() and (s.points[:, 0] <= 480 + 1e-6).all()


def test_single_line_mode(toy_hand):
    h, _ = toy_hand
    d = ln.generate_drawing(h, np.random.default_rng(1), (500, 400), mode="single", ink=1.0)
    assert len(d.strokes) == 1
    assert d.strokes[0].length() > 0.3 * d.meta["ref_length_gen"]


def test_shuffle_control_keeps_pulses():
    rng = np.random.default_rng(2)
    rows = ln.pulses_to_rows(ln.random_pulses(rng, 6), 1.0)
    sh = ln.shuffle_rows(rows, np.random.default_rng(0))
    assert np.allclose(np.sort(sh[:, 0]), np.sort(rows[:, 0]))
    assert np.allclose(sh[1:, 3], rows[1:, 3]) and np.allclose(sh[1:, 5], rows[1:, 5])
    assert np.allclose(np.sort(sh[:, 4]), np.sort(rows[:, 4]))
