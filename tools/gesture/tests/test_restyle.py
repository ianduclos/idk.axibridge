"""Tests for gesture.restyle — restyle as translation (structure kept, hand
replaced). A tiny grammar learned from synthetic drawings keeps the suite
corpus-free and fast."""
from __future__ import annotations

import numpy as np
import pytest

from gesture import restyle as rs
from gesture import synth
from gesture.core import Drawing, Stroke
from gesture.grammar_v4_frozen import learn


@pytest.fixture(scope="module")
def g():
    rng = np.random.default_rng(1)
    ds = [synth.scene_matisse_like(rng, 600, n_strokes=5) for _ in range(3)]
    return learn(ds, name="synth_m")


def _circle(n=300, r=200.0, c=(300.0, 300.0)):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return Stroke(np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)]), closed=True)


def _wave():
    x = np.linspace(50, 550, 600)
    return Stroke(np.column_stack([x, 300 + 60 * np.sin(x / 45.0) + 20 * np.sin(x / 13.0)]))


def _drawing():
    return Drawing([_circle(), _wave()], source="t", size=(600, 600))


def test_sigma_of_monotone():
    a = np.linspace(0, 1, 11)
    s = [rs.sigma_of(x) for x in a]
    assert s[0] == 0 and np.all(np.diff(s) > 0) and s[-1] == pytest.approx(rs.SIGMA_HI)


def test_amount_zero_is_identity(g):
    d = _drawing()
    o = rs.restyle_drawing(d, g, amount=0.0, seed=3)
    for a, b in zip(d.strokes, o.strokes):
        assert np.array_equal(a.points, b.points) and a.closed == b.closed


@pytest.mark.parametrize("method,source", [("gauss", "chain"), ("anchors", "chain"),
                                           ("gauss", "trace"), ("clothoid", "transplant")])
def test_deterministic_and_pure(g, method, source):
    d = _drawing()
    before = [s.points.copy() for s in d.strokes]
    o1 = rs.restyle_drawing(d, g, amount=0.6, seed=5, method=method, source=source)
    o2 = rs.restyle_drawing(d, g, amount=0.6, seed=5, method=method, source=source)
    for p, s in zip(before, d.strokes):
        assert np.array_equal(p, s.points)
    for a, b in zip(o1.strokes, o2.strokes):
        assert np.array_equal(a.points, b.points)
        assert np.all(np.isfinite(a.points))


def test_seed_changes_output(g):
    d = _drawing()
    o1 = rs.restyle_drawing(d, g, amount=0.8, seed=1)
    o2 = rs.restyle_drawing(d, g, amount=0.8, seed=2)
    assert np.max(np.abs(o1.strokes[1].points - o2.strokes[1].points)) > 0.1


@pytest.mark.parametrize("method", rs.METHODS)
@pytest.mark.parametrize("source", rs.SOURCES)
def test_closed_stays_closed(g, method, source):
    c = _circle()
    R = 600 * np.sqrt(2)
    st = rs.restyle_stroke(c, g, np.random.default_rng(0), amount=0.7, ref_length=R,
                           method=method, source=source)
    assert st.closed
    step = rs.STEP * R * st.meta["restyle"]["stretch"]
    # the last point is one step before the start (closed strokes do not repeat it)
    assert np.linalg.norm(st.points[-1] - st.points[0]) < 4 * step + 0.02 * rs.sigma_of(0.7) * R


def test_pins_hold(g):
    d = _drawing()
    for amt in (0.3, 0.7, 1.0):
        o = rs.restyle_drawing(d, g, amount=amt, seed=4)
        for s in o.strokes:
            info = s.meta["restyle"]
            assert info["pin_err"] <= 0.1 * info["sigma_s"]


@pytest.mark.parametrize("source", ["chain", "trace"])
def test_structure_distance_monotone_in_amount(g, source):
    d = Drawing([_wave()], size=(600, 600))
    ds = [rs.structure_distance(d, rs.restyle_drawing(d, g, amount=a, seed=7, source=source))["mean"]
          for a in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert ds[0] == 0.0
    assert all(b >= a - 1e-4 for a, b in zip(ds, ds[1:])), ds
    assert ds[-1] > ds[1]


def test_max_sigma_caps_structure_scale(g):
    """A short line at a large amount: without the cap it only gets its two end
    pins; capped at length/3 it gets interior pins and stays near the source."""
    st = _wave()
    R = 4000.0                                   # the line is short relative to R
    L = st.length()
    _, info = rs.restyle_points(st.points, g, np.random.default_rng(1), amount=0.9, ref_length=R, source="trace")
    out, info_c = rs.restyle_points(st.points, g, np.random.default_rng(1), amount=0.9, ref_length=R,
                                    source="trace", max_sigma=L / 3)
    assert info["sigma_s"] > L / 3 and info_c["sigma_s"] == pytest.approx(L / 3)
    assert info_c["n_pins"] > info["n_pins"] >= 2
    assert np.all(np.isfinite(out))
