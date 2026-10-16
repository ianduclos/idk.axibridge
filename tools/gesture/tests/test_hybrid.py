"""Tests for gesture.hybrid — hybrid hands over two learned grammars.

Two synthetic parents with nothing in common: a hand of straight lines and a
hand of tight arcs, so which parent spoke is readable from each token."""
from __future__ import annotations

import numpy as np
import pytest

from gesture import hybrid as hy
from gesture.core import Drawing, Stroke
from gesture.curvature import integrate_kappa
from gesture.grammar import generate_drawing, generate_tokens, learn

KAPPA = 1.0 / 120.0


def _frame(strokes):
    return Drawing(strokes, source="test", size=(1000, 1000))


@pytest.fixture(scope="module")
def g_lines():
    rng = np.random.default_rng(0)
    ds = []
    for _ in range(2):
        strokes = []
        for _ in range(8):
            a = rng.uniform(0, 2 * np.pi)
            L = rng.uniform(150, 400)
            p0 = np.array([500, 500]) + rng.uniform(-200, 200, 2)
            t = np.linspace(0, L, int(L) + 1)[:, None]
            strokes.append(Stroke(p0 + t * [np.cos(a), np.sin(a)], width=np.full(len(t), 2.0)))
        ds.append(_frame(strokes))
    return learn(ds, name="lines", len_quantile=0.0)


@pytest.fixture(scope="module")
def g_arcs():
    strokes = []
    for i in range(8):
        p = integrate_kappa(np.array([0, 300.0]), np.array([KAPPA, KAPPA]), 1.0,
                            start=(100 + 90 * i, 100 + 80 * i), heading=0.4 * i)
        strokes.append(Stroke(p, width=np.full(len(p), 2.0)))
    return learn([_frame(strokes)], name="arcs", len_quantile=0.0)


def _kinds(toks):
    return [t[0] for t in toks if t[0] != "corner"]


def test_merge_keeps_parents_and_reindexes(g_lines, g_arcs):
    h = hy.make_hybrid(g_lines, g_arcs, "mixture")
    nA, nB = len(g_lines.trans["p1"]), len(g_arcs.trans["p1"])
    assert len(h.trans["p1"]) == nA + nB
    assert len(h.strokes) == len(g_lines.strokes) + len(g_arcs.strokes)
    # B's stroke ids are re-based past A's strokes; drawings' stroke ranges too
    assert min(h.trans["sid"][nA:]) >= 2 * len(g_lines.strokes)
    for d in h.drawings:
        assert 0 <= d["i0"] < d["i1"] <= len(h.strokes)
    # parents untouched (purity)
    assert len(g_lines.trans["p1"]) == nA and len(g_arcs.trans["p1"]) == nB


def test_drawing_shares_follow_weights(g_lines, g_arcs):
    h = hy.make_hybrid(g_lines, g_arcs, "mixture", t=0.5)
    hands = [d["hand"] for d in h.drawings]
    share = hands.count("arcs") / len(hands)
    assert 0.3 <= share <= 0.7


@pytest.mark.parametrize("t,lo,hi", [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.5, 0.3, 0.7)])
def test_mixture_share(g_lines, g_arcs, t, lo, hi):
    h = hy.make_hybrid(g_lines, g_arcs, "mixture", t=t)
    h.log = []
    rng = np.random.default_rng(3)
    for _ in range(30):
        generate_tokens(h, rng, length=0.4)
    share = np.mean([x[1] for x in h.log])
    assert lo - 1e-9 <= share <= hi + 1e-9


def test_parent_tokens_survive_in_pure_hybrid(g_lines, g_arcs):
    rng = np.random.default_rng(5)
    hA = hy.make_hybrid(g_lines, g_arcs, "mixture", t=0.0)
    hB = hy.make_hybrid(g_lines, g_arcs, "mixture", t=1.0)
    ka = [k for _ in range(20) for k in _kinds(generate_tokens(hA, rng, length=0.4)[0])]
    kb = [k for _ in range(20) for k in _kinds(generate_tokens(hB, rng, length=0.4)[0])]
    assert set(ka) == {"line"}
    assert ka and kb and kb.count("line") < len(kb)


def test_crossover_blocks_are_single_handed(g_lines, g_arcs):
    h = hy.make_hybrid(g_lines, g_arcs, "crossover", t=0.5, period=0.05)
    h.log = []
    generate_tokens(h, np.random.default_rng(1), length=1.0)
    blocks = {}
    for s, k in h.log:
        blocks.setdefault(int(s // 0.05), set()).add(k)
    assert all(len(v) == 1 for v in blocks.values())
    assert {k for v in blocks.values() for k in v} == {0, 1}


def test_interp_moves_parameters_between_parents(g_lines, g_arcs):
    par = [0.05, 0.0, 0.0]
    out0 = hy.interp_params("arc", [0.05, 2.0, 2.0], g_arcs, g_arcs, 0.0)
    assert out0 == [0.05, 2.0, 2.0]
    nb = hy.interp_params("line", par, g_lines, g_lines, 1.0)
    assert nb[1] == nb[2] == 0.0
    arc_k = [t[2] for s in g_arcs.strokes for t in s if t[0] == "arc"]
    mid = hy.interp_params("arc", [0.05, 0.0, 0.0], g_lines, g_arcs, 0.5)
    assert 0.0 < abs(mid[1]) < max(abs(np.array(arc_k)))


def test_hybrid_generates_sheets_deterministically(g_lines, g_arcs):
    for m in hy.METHODS:
        h1 = hy.make_hybrid(g_lines, g_arcs, m)
        h2 = hy.make_hybrid(g_lines, g_arcs, m)
        d1 = generate_drawing(h1, np.random.default_rng(9), (600, 600), n_strokes=4)
        d2 = generate_drawing(h2, np.random.default_rng(9), (600, 600), n_strokes=4)
        assert len(d1.strokes) == len(d2.strokes) >= 1
        for a, b in zip(d1.strokes, d2.strokes):
            assert np.allclose(a.points, b.points)
            assert np.all(np.isfinite(a.points))


def test_route_weights():
    assert np.allclose(hy.route_weights(0.0, 3), [1, 0, 0])
    assert np.allclose(hy.route_weights(0.5, 3), [0, 1, 0])
    assert np.allclose(hy.route_weights(1.0, 3), [0, 0, 1])
    w = hy.route_weights(0.25, 3)
    assert w.sum() == pytest.approx(1.0) and 0 < w[0] < 1 and w[2] == 0


def test_drift_line_moves_from_parent_to_parent(g_lines, g_arcs):
    st, info = hy.drift_line([g_lines, g_arcs], np.random.default_rng(2), total=2.0, size=(600, 600), K=3, chunk=0.1)
    sh = np.array(info["hand_share_by_decile"])
    sh = sh[sh.sum(1) > 0]                     # deciles that received a token (synthetic tokens are long)
    assert sh[0, 0] > 0.9 and sh[-1, 1] > 0.9
    assert np.all(np.isfinite(st.points)) and len(st.meta["u"]) == len(st.points)


def test_tile_drawing():
    strokes = [Stroke(np.array([[x, y], [x + 5, y + 5]], float)) for x in (10, 600) for y in (10, 600)
               for _ in range(5)]
    tiles = hy.tile_drawing(_frame(strokes), 2, 2)
    assert len(tiles) == 4 and all(len(t.strokes) == 5 for t in tiles)


def test_axis_position():
    rng = np.random.default_rng(0)
    A = rng.normal(0, 0.1, (20, 5))
    B = rng.normal(0, 0.1, (20, 5)) + [1, 0, 0, 0, 0]
    mid = rng.normal(0, 0.1, (20, 5)) + [0.5, 0, 0, 0, 0]
    off = rng.normal(0, 0.1, (20, 5)) + [0.5, 2, 0, 0, 0]
    p = hy.axis_position(mid, A, B)
    assert abs(p["t_q50"] - 0.5) < 0.1 and p["off_ratio"] < 2
    assert hy.axis_position(off, A, B)["off_ratio"] > 5
