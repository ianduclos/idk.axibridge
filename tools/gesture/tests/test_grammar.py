"""Tests for gesture.grammar — learn a clothoid-alphabet hand, generate with it.

Synthetic training drawings only (synth.scene_*, hand-built lines and arcs),
so the suite stays fast and hardware/corpus-free.
"""
from __future__ import annotations

import numpy as np
import pytest

from gesture import synth
from gesture.clothoid import fit_stroke
from gesture.core import Drawing, Stroke
from gesture.curvature import integrate_kappa, kappa_s
from gesture.grammar import (Grammar, code_switch, generate_drawing, generate_stroke, learn,
                             nearest_training_distance, restyle, translate)


@pytest.fixture(scope="module")
def g_matisse():
    rng = np.random.default_rng(1)
    ds = [synth.scene_matisse_like(rng, 600, n_strokes=4) for _ in range(4)]
    return learn(ds, name="synth_m")


@pytest.fixture(scope="module")
def g_random():
    rng = np.random.default_rng(2)
    ds = [synth.scene_random(rng, 600, n_strokes=6) for _ in range(3)]
    return learn(ds, name="synth_r")


def _frame(strokes):
    """A drawing whose bounding box is pinned by two corner dots-strokes."""
    return Drawing(strokes, source="test", size=(1000, 1000))


def test_learn_basic(g_matisse):
    P = g_matisse.transition()
    assert np.allclose(P.sum(axis=1), 1.0)
    assert g_matisse.meta["n_strokes"] >= 10
    c = g_matisse.segment_counts()
    assert c["arc"] + c["clothoid"] > 0


def test_generation_deterministic_and_finite(g_matisse):
    a = generate_stroke(g_matisse, np.random.default_rng(5), ref_length=800, start=(10, 20))
    b = generate_stroke(g_matisse, np.random.default_rng(5), ref_length=800, start=(10, 20))
    assert np.array_equal(a.points, b.points)
    assert np.all(np.isfinite(a.points)) and len(a) >= 2
    assert np.allclose(a.points[0], [10, 20])
    d1 = generate_drawing(g_matisse, np.random.default_rng(3), (500, 400))
    d2 = generate_drawing(g_matisse, np.random.default_rng(3), (500, 400))
    assert len(d1.strokes) == len(d2.strokes) >= 1
    for s1, s2 in zip(d1.strokes, d2.strokes):
        assert np.array_equal(s1.points, s2.points)
        assert np.all(np.isfinite(s1.points))


def test_json_round_trip(g_random, tmp_path):
    p = tmp_path / "g.json"
    g_random.save(p)
    g2 = Grammar.load(p)
    assert g2.to_json() == g_random.to_json()
    a = generate_stroke(g_random, np.random.default_rng(9), ref_length=700)
    b = generate_stroke(g2, np.random.default_rng(9), ref_length=700)
    assert np.array_equal(a.points, b.points)


def test_lines_make_straight_strokes():
    rng = np.random.default_rng(0)
    strokes = []
    for i in range(8):
        a = rng.uniform(0, 2 * np.pi)
        L = rng.uniform(150, 400)
        p0 = np.array([500, 500]) + rng.uniform(-200, 200, 2)
        t = np.linspace(0, L, int(L) + 1)[:, None]
        strokes.append(Stroke(p0 + t * [np.cos(a), np.sin(a)]))
    g = learn([_frame(strokes)], name="lines")
    assert g.segment_counts()["line"] >= 8
    gen = np.random.default_rng(1)
    for _ in range(20):
        st = generate_stroke(g, gen, ref_length=1000)
        assert all(s["kind"] == "line" for s in st.meta["segments"])
        p = st.points
        chord = np.linalg.norm(p[-1] - p[0])
        assert chord > 0.999 * st.length()


def test_arcs_make_arcs():
    kappa = 1.0 / 150.0
    strokes = []
    for i in range(6):
        p = integrate_kappa(np.array([0, 320.0]), np.array([kappa, kappa]), 1.0,
                            start=(100 + 120 * i, 100 + 100 * i), heading=0.4 * i)
        strokes.append(Stroke(p))
    d = _frame(strokes)
    R = d.ref_length()
    g = learn([d], name="arcs")
    assert g.segment_counts()["arc"] >= 6
    gen = np.random.default_rng(2)
    for _ in range(20):
        st = generate_stroke(g, gen, ref_length=R)
        for s in st.meta["segments"]:
            assert s["kind"] == "arc"
            assert abs(abs(s["k0"]) - kappa) < 0.2 * kappa
        # measured curvature of the generated polyline agrees
        if st.length() > 100:
            _s, k, _ = kappa_s(st.points, sigma=3.0)
            mid = np.abs(k[len(k) // 4: 3 * len(k) // 4])
            assert abs(np.median(mid) - kappa) < 0.2 * kappa


def test_kappa_continuity(g_matisse, g_random):
    rng = np.random.default_rng(4)
    n_joints = 0
    for g in (g_matisse, g_random):
        for _ in range(60):
            st = generate_stroke(g, rng, ref_length=900)
            segs = st.meta["segments"]
            cs = [c["s"] for c in st.meta["corners"]]
            for a, b in zip(segs[:-1], segs[1:]):
                if any(abs(b["s0"] - c) < 1e-9 for c in cs):
                    continue
                n_joints += 1
                assert b["k0"] == pytest.approx(a["k1"], abs=1e-12)
                if b["kind"] == "line":
                    assert a["k1"] == 0.0
    assert n_joints > 0


def test_juxtaposition_ops(g_matisse, g_random):
    rng = np.random.default_rng(6)
    cs = code_switch(g_matisse, g_random, rng, 0.5, ref_length=800)
    assert np.all(np.isfinite(cs.points))
    si = cs.meta["switch_index"]
    toks = cs.meta["tokens"]
    if 0 < si < len(toks) and toks[si - 1][0] != "corner" and toks[si][0] != "corner":
        assert toks[si][2] == pytest.approx(toks[si - 1][3])        # κ-continuous switch
    # translate a synthetic stroke
    st = synth.random_clothoid_stroke(np.random.default_rng(1), 400, 4, 0.01)
    f = fit_stroke(st.points, sigma=6.0)
    tr = translate(f, g_matisse, g_random, ref_length=800)
    assert np.all(np.isfinite(tr.points))
    assert len(tr.meta["segments"]) == sum(1 for t in tr.meta["source_tokens"] if t[0] != "corner")
    # restyle keeps endpoints and coarse shape
    t = np.linspace(0, np.pi, 400)
    path = np.column_stack([300 + 200 * np.cos(t), 300 + 200 * np.sin(t)])
    rs = restyle(path, g_random, np.random.default_rng(3), ref_length=800)
    assert np.all(np.isfinite(rs.points))
    assert np.linalg.norm(rs.points[-1] - path[-1]) < 5.0
    assert np.linalg.norm(rs.points[0] - path[0]) < 5.0


def test_memorisation_distance(g_random):
    # a training stroke is at distance 0 from itself (either direction)
    d0 = nearest_training_distance([g_random.strokes[0]], g_random)
    assert d0[0] == pytest.approx(0.0, abs=1e-6)
    from gesture.grammar import reverse_tokens
    d1 = nearest_training_distance([reverse_tokens(g_random.strokes[1])], g_random)
    assert d1[0] == pytest.approx(0.0, abs=1e-6)
    gen = [generate_stroke(g_random, np.random.default_rng(i), ref_length=600) for i in range(10)]
    d = nearest_training_distance(gen, g_random)
    assert len(d) == 10 and np.all(np.isfinite(d)) and np.all(d >= 0)
