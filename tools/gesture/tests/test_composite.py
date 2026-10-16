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


# ---------------------------------------------------------------------------
# chain fix (restyle_chain), walk / connect, SVG export
# ---------------------------------------------------------------------------

def _T():
    """Host 0→300 along x with a 150-long branch up at x = 100: the open
    postman retraces the 100-long left arm, so the walk reverses at (0, 0)."""
    host = Stroke(_line((0, 0), (300, 0), 301, bend=6))
    br = Stroke(_line(host.points[100], (100, 150), 151, bend=8))
    return Drawing([host, br], size=(400, 400))


def _turn_at(p, i, d):
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    a = int(np.searchsorted(s, s[i] - d))
    b = int(min(np.searchsorted(s, s[i] + d), len(p) - 1))
    u, v = p[i] - p[a], p[b] - p[i]
    return float(np.degrees(np.arccos(np.clip(u @ v / (np.linalg.norm(u) * np.linalg.norm(v)), -1, 1))))


@pytest.mark.parametrize("pin", ["tips", "turns"])
def test_restyle_chain_pins_reversals(g, pin):
    d = _T()
    R = d.ref_length()
    sk = cp.chain_paths(d)
    o = cp.restyle_chain(sk, g, amount=0.8, seed=3, ref_length=R, pin=pin, retrace="redraw")
    assert len(o.strokes) == 1 and o.meta["restyle_chain"]["reversals"] >= 1
    p = o.strokes[0].points
    an = o.strokes[0].meta["anchors"]
    tip = np.array([0.0, 0.0])
    hit = [i for i in an if np.linalg.norm(p[i] - tip) < 1e-9]
    assert hit, "the reversal tip is an exact anchor of the output line"
    assert _turn_at(p, hit[0], 0.01 * R) > 120            # and the line really turns back there
    # every anchor lands exactly on the chained skeleton (welded runs, no gaps)
    q = sk.strokes[0].points
    for i in an:
        assert np.min(np.linalg.norm(q - p[i], axis=1)) < 1e-9
    # unpinned, the single run smooths straight through the hairpin: the tip is not hit
    o0 = cp.restyle_chain(sk, g, amount=0.8, seed=3, ref_length=R, pin="none", retrace="redraw")
    assert np.min(np.linalg.norm(o0.strokes[0].points - tip, axis=1)) > 1e-6


def test_offset_return_distance():
    t = np.linspace(0, 1, 800)
    p = np.column_stack([600 * t, 40 * np.sin(5 * t)])
    q = cp.offset_return(p, 3.0, 20.0)
    assert np.allclose(q[0], p[0]) and np.allclose(q[-1], p[-1])
    from scipy.spatial import cKDTree
    dist, _ = cKDTree(p).query(q[100:-100])
    assert np.all(np.abs(dist - 3.0) < 0.5)


@pytest.mark.parametrize("retrace,lo,hi", [("exact", 0.0, 0.05), ("offset", 0.75, 2.25)])  # in line widths
def test_restyle_chain_return_pass(g, retrace, lo, hi):
    d = _T()
    R = d.ref_length()
    w = 2.0
    o = cp.restyle_chain(cp.chain_paths(d), g, amount=0.8, seed=3, ref_length=R, pin="turns",
                         retrace=retrace, offset_w=1.5, w=w)
    assert o.meta["restyle_chain"]["return_runs"] >= 1
    p = o.strokes[0].points
    an = [0] + o.strokes[0].meta["anchors"] + [len(p) - 1]
    k = next(j for j, i in enumerate(an) if np.linalg.norm(p[i]) < 1e-9)  # the tip anchor
    out_run, back_run = p[an[k - 1]:an[k] + 1], p[an[k]:an[k + 1] + 1]
    from scipy.spatial import cKDTree
    L = len(back_run)
    dist, _ = cKDTree(out_run).query(back_run[L // 4: 3 * L // 4])
    assert np.all(dist >= lo * w) and np.all(dist <= hi * w)       # offset_w = 1.5


def test_restyle_chain_deterministic_and_pure(g):
    sk = cp.chain_paths(_tree(), walk="min_turn")
    before = [s.points.copy() for s in sk.strokes]
    kw = dict(amount=0.7, seed=5, pin="turns", retrace="offset")
    a, b = cp.restyle_chain(sk, g, **kw), cp.restyle_chain(sk, g, **kw)
    for p, s in zip(before, sk.strokes):
        assert np.array_equal(p, s.points)
    for x, y in zip(a.strokes, b.strokes):
        assert np.array_equal(x.points, y.points) and np.all(np.isfinite(x.points))
    c = cp.composite(_tree(), g, np.random.default_rng(2), amount=0.7, chain="before", pin="turns",
                     retrace="offset", walk="min_turn")
    assert c.meta["composite"]["n_out"] == 1


def test_min_turn_walk_and_connect():
    d = _tree()
    R = d.ref_length()
    a, m = cp.chain_paths(d), cp.chain_paths(d, walk="min_turn")
    for c in (a, m):                                       # a valid single line over the same ink either way
        assert c.meta["chain"]["n_paths"] == 1
        assert _covered(d, c, rs.WELD_R * R) <= 1.0
    assert m.meta["chain"]["retrace_R"] == pytest.approx(a.meta["chain"]["retrace_R"])
    turns = lambda c: cp.node_turns(c.strokes[0].points, c.strokes[0].meta["chain_pieces"], 0.01 * R).sum()  # noqa: E731
    assert turns(m) <= turns(a) + 1e-6
    # two loose lines → one line with one straight connector across the gap
    two = Drawing([Stroke(_line((0, 0), (100, 0), 101)), Stroke(_line((130, 0), (230, 0), 101))], size=(300, 300))
    c = cp.chain_paths(two, connect=True)
    assert c.meta["chain"]["n_paths"] == 1
    assert c.meta["chain"]["connector_R"] * two.ref_length() == pytest.approx(30.0, rel=1e-6)
    assert cp.chain_paths(two, connect=True, max_paths=2).meta["chain"]["n_paths"] == 2


def test_svg_roundtrip():
    d = _tree()
    c = cp.chain_paths(d, max_retrace=0.0)
    svg, st = cp.to_svg(c, paper="A4", margin_mm=10.0)
    (W, H), paths = cp.read_svg_paths(svg)
    assert (W, H) == (297.0, 210.0)
    assert len(paths) == len(c.strokes) == st["paths"] and st["lifts"] == len(paths) - 1
    P = np.vstack(paths)
    assert P[:, 0].min() >= 10 - 1e-3 and P[:, 0].max() <= W - 10 + 1e-3
    assert P[:, 1].min() >= 10 - 1e-3 and P[:, 1].max() <= H - 10 + 1e-3
    # the fit touches the margin on the limiting axis (no wasted paper), and pen order is kept
    assert min(P[:, 1].min() - 10, H - 10 - P[:, 1].max()) < 1e-2 or min(P[:, 0].min() - 10, W - 10 - P[:, 0].max()) < 1e-2
    mm = cp.to_mm(c, paper="A4", margin_mm=10.0)
    for p, q in zip(paths, mm):
        assert np.allclose(p[0], q[0], atol=1e-3) and np.allclose(p[-1], q[-1], atol=1e-3)
    down = sum(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)) for p in paths)
    assert st["pen_down_mm"] == pytest.approx(down, abs=0.2) and st["est_min"] > 0
