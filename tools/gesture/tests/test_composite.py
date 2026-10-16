"""Tests for the composite pipeline (experiments/composite.py) and the
junction welding it relies on (gesture/restyle.py). A tiny v4 grammar
learned from synthetic drawings keeps the suite corpus-free and fast."""
from __future__ import annotations

import numpy as np
import pytest

from experiments import composite as cp
from gesture import restyle as rs
from gesture import synth
from gesture.core import Drawing, Stroke
from gesture.grammar_v4_frozen import learn


@pytest.fixture(scope="module")
def g():
    rng = np.random.default_rng(1)
    ds = [synth.scene_matisse_like(rng, 600, n_strokes=5) for _ in range(3)]
    return learn(ds, name="synth_m")


def _line(p0, p1, n=200, bend=0.0):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = p1 - p0
    nrm = np.array([-d[1], d[0]]) / max(np.linalg.norm(d), 1e-9)
    return p0 + t * d + bend * np.sin(np.pi * t) * nrm


def _tree() -> Drawing:
    """A trunk with two branches starting on it and a twig on a branch
    (T-junctions at the branch starts)."""
    trunk = _line((300, 580), (300, 80), 400, bend=25)
    b1 = _line(trunk[150], (120, 250), 200, bend=-20)
    b2 = _line(trunk[260], (480, 160), 200, bend=15)
    tw = _line(b1[100], (180, 120), 120, bend=10)
    return Drawing([Stroke(trunk), Stroke(b1), Stroke(b2), Stroke(tw)], source="t", size=(600, 600))


def _gap(p, q):
    """Distance from point p to polyline q (segments, not just vertices)."""
    a, b = q[:-1], q[1:]
    ab = b - a
    t = np.clip(np.sum((p - a) * ab, 1) / np.maximum(np.sum(ab * ab, 1), 1e-12), 0, 1)
    return float(np.min(np.linalg.norm(a + t[:, None] * ab - p, axis=1)))


def test_junctions_found():
    d = _tree()
    J = rs.find_junctions(d, d.ref_length())
    assert sorted((i, e, j) for i, e, j, _u in J) == [(1, 0, 0), (2, 0, 0), (3, 0, 1)]


@pytest.mark.parametrize("source", ["trace", "chain"])
def test_weld_keeps_junctions(g, source):
    d = _tree()
    R = d.ref_length()
    o = rs.restyle_drawing(d, g, amount=0.8, seed=2, source=source)
    o0 = rs.restyle_drawing(d, g, amount=0.8, seed=2, source=source, weld=False)
    J = rs.find_junctions(d, R)
    gaps = [_gap(o.strokes[i].points[e], o.strokes[j].points) for i, e, j, _u in J]
    gaps0 = [_gap(o0.strokes[i].points[e], o0.strokes[j].points) for i, e, j, _u in J]
    assert max(gaps) < 1e-6 * R
    assert max(gaps0) > 100 * max(max(gaps), 1e-9)  # without the weld the ends float off their hosts
    assert o.meta["restyle"]["welds"] == 3
    # the far end of a welded branch is untouched by its weld
    assert np.allclose(o.strokes[2].points[-1], o0.strokes[2].points[-1])


def test_composite_deterministic_and_pure(g):
    d = _tree()
    before = [s.points.copy() for s in d.strokes]
    a = cp.composite(d, g, np.random.default_rng(4), amount=0.6, chain=True)
    b = cp.composite(d, g, np.random.default_rng(4), amount=0.6, chain=True)
    for p, s in zip(before, d.strokes):
        assert np.array_equal(p, s.points)
    assert len(a.strokes) == len(b.strokes)
    for x, y in zip(a.strokes, b.strokes):
        assert np.array_equal(x.points, y.points) and np.all(np.isfinite(x.points))
    c = cp.composite(d, g, np.random.default_rng(5), amount=0.6, chain=True)
    assert not np.array_equal(a.strokes[0].points, c.strokes[0].points)


def test_composite_generated_structure(g):
    a = cp.composite("oehlen_tree", g, np.random.default_rng(3), size=500, amount=0.5,
                     structure_params={"depth": 2, "trunks": 1, "fill": 0.3})
    b = cp.composite("oehlen_tree", g, np.random.default_rng(3), size=500, amount=0.5,
                     structure_params={"depth": 2, "trunks": 1, "fill": 0.3})
    assert len(a.strokes) == a.meta["composite"]["n_structure"] >= 2
    for x, y in zip(a.strokes, b.strokes):
        assert np.array_equal(x.points, y.points)


def _covered(src: Drawing, out: Drawing, tol: float) -> float:
    q = np.vstack([s.points for s in out.strokes])
    from scipy.spatial import cKDTree
    t = cKDTree(q)
    p = np.vstack([s.points for s in src.strokes])
    d, _ = t.query(p)
    return float(np.max(d)) / tol


def test_chain_single_path_covers_same_ink():
    d = _tree()
    R = d.ref_length()
    c = cp.chain_paths(d)
    m = c.meta["chain"]
    assert m["n_in"] == 4 and m["n_paths"] == 1 == len(c.strokes)
    assert _covered(d, c, rs.WELD_R * R) <= 1.0           # every source point is on the path
    ink_in = sum(s.length() for s in d.strokes)
    ink_out = sum(s.length() for s in c.strokes)
    assert ink_out == pytest.approx(ink_in + m["retrace_R"] * R, rel=0.01)
    # a trunk with three side limbs: the open postman retraces exactly the two shortest limbs'
    # worth — here every limb ends free, so at least some retrace is needed but less than half the ink
    assert 0 < m["retrace_R"] * R < 0.5 * ink_in


def test_chain_retrace_is_minimal_on_a_T():
    a, b, c = 100.0, 200.0, 150.0
    host = Stroke(np.array([[0.0, 0.0], [a, 0.0], [a + b, 0.0]]))
    host = Stroke(_line((0, 0), (a + b, 0), 301))
    br = Stroke(_line((a, 0), (a, c), 151))
    d = Drawing([host, br], size=(400, 400))
    out = cp.chain_paths(d)
    R = d.ref_length()
    assert out.meta["chain"]["n_paths"] == 1
    assert out.meta["chain"]["retrace_R"] * R == pytest.approx(min(a, b, c), rel=0.02)


def test_chain_max_retrace_trades_paths():
    d = _tree()
    full = cp.chain_paths(d)
    none = cp.chain_paths(d, max_retrace=0.0)
    assert none.meta["chain"]["retrace_R"] == 0.0
    assert full.meta["chain"]["n_paths"] < none.meta["chain"]["n_paths"] <= 4
    R = d.ref_length()
    assert _covered(d, none, rs.WELD_R * R) <= 1.0


def test_chain_after_restyle_keeps_welded_tree_one_line(g):
    d = _tree()
    o = cp.composite(d, g, np.random.default_rng(1), amount=0.8, chain=True)
    assert o.meta["composite"]["n_out"] == 1
