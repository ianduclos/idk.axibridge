"""Tests for gesture.grammar (v2) — learn a clothoid-alphabet hand from long
strokes, generate contiguous / single-line drawings with it.

Synthetic training drawings only (synth.scene_*, hand-built lines, arcs and
hatching), so the suite stays fast and corpus-free.
"""
from __future__ import annotations

import numpy as np
import pytest

from gesture import synth
from gesture.clothoid import fit_stroke
from gesture.core import Drawing, Stroke
from gesture.curvature import integrate_kappa, kappa_s
from gesture.grammar import (Grammar, code_switch, generate_drawing, generate_stroke,
                             generate_tokens, hatch_mask, learn, nearest_training_distance,
                             restyle, reverse_tokens, select_long, shuffle_tokens, translate,
                             truncate_tokens)


@pytest.fixture(scope="module")
def g_matisse():
    rng = np.random.default_rng(1)
    ds = [synth.scene_matisse_like(rng, 600, n_strokes=5) for _ in range(4)]
    return learn(ds, name="synth_m")


@pytest.fixture(scope="module")
def g_random():
    rng = np.random.default_rng(2)
    ds = [synth.scene_random(rng, 600, n_strokes=6) for _ in range(3)]
    return learn(ds, name="synth_r")


@pytest.fixture(scope="module")
def g_fine():
    """A hand at a realistic scale: many moderate strokes, thin line."""
    rng = np.random.default_rng(7)
    ds = [synth.scene_random(rng, 1500, n_strokes=10, length_frac=(0.08, 0.25), n_segments=(3, 6))
          for _ in range(3)]
    return learn(ds, name="synth_f")


def _frame(strokes):
    return Drawing(strokes, source="test", size=(1000, 1000))


def _assert_kappa_continuous(st):
    segs = st.meta["segments"]
    cs = [c["s"] for c in st.meta["corners"]]
    n = 0
    for a, b in zip(segs[:-1], segs[1:]):
        if any(abs(b["s0"] - c) < 1e-9 for c in cs):
            continue
        n += 1
        assert b["k0"] == pytest.approx(a["k1"], abs=1e-9)
    return n


def test_learn_basic(g_matisse):
    P = g_matisse.transition()
    assert np.allclose(P[P.sum(axis=1) > 0].sum(axis=1), 1.0)
    assert g_matisse.meta["n_strokes"] >= 10
    c = g_matisse.segment_counts()
    assert c["arc"] + c["clothoid"] > 0
    assert len(g_matisse.trans["nx"]) > 2 * g_matisse.meta["n_strokes"]   # reversal-augmented
    assert g_matisse.min_length > 0


def test_hatching_and_long_selection():
    """Ten short parallel strokes are hatching; a long winding line is kept."""
    hatch = [Stroke(np.column_stack([np.linspace(100, 160, 61), np.full(61, 200.0 + 8 * i)]),
                    width=np.full(61, 1.5)) for i in range(10)]
    p = integrate_kappa(np.array([0, 300.0, 600.0]), np.array([0.01, -0.01, 0.005]), 1.0,
                        start=(300, 500))
    long_ = Stroke(p, width=np.full(len(p), 1.5))
    d = Drawing(hatch + [long_], size=(1000, 1000))
    hm = hatch_mask(d)
    assert hm[:10].sum() >= 8 and not hm[10]
    keep, info = select_long(d)
    assert keep == [10] and info["n_hatch"] >= 8


def test_generation_deterministic_and_finite(g_matisse, g_fine):
    a = generate_stroke(g_matisse, np.random.default_rng(5), ref_length=800, start=(10, 20))
    b = generate_stroke(g_matisse, np.random.default_rng(5), ref_length=800, start=(10, 20))
    assert np.array_equal(a.points, b.points)
    assert np.all(np.isfinite(a.points)) and len(a) >= 2
    assert np.allclose(a.points[0], [10, 20])
    for mode in ("contiguous", "single"):
        d1 = generate_drawing(g_fine, np.random.default_rng(3), (900, 800), mode=mode)
        d2 = generate_drawing(g_fine, np.random.default_rng(3), (900, 800), mode=mode)
        assert len(d1.strokes) == len(d2.strokes) >= 1
        for s1, s2 in zip(d1.strokes, d2.strokes):
            assert np.array_equal(s1.points, s2.points)
            assert np.all(np.isfinite(s1.points))


def test_json_round_trip(g_random, tmp_path):
    p = tmp_path / "g.json"
    g_random.save(p)
    g2 = Grammar.load(p)
    assert g2.to_json() == g_random.to_json()
    a = generate_drawing(g_random, np.random.default_rng(9), (600, 600))
    b = generate_drawing(g2, np.random.default_rng(9), (600, 600))
    assert [len(s) for s in a.strokes] == [len(s) for s in b.strokes]
    for s1, s2 in zip(a.strokes, b.strokes):
        assert np.array_equal(s1.points, s2.points)


def test_lines_make_straight_strokes():
    rng = np.random.default_rng(0)
    strokes = []
    for i in range(8):
        a = rng.uniform(0, 2 * np.pi)
        L = rng.uniform(150, 400)
        p0 = np.array([500, 500]) + rng.uniform(-200, 200, 2)
        t = np.linspace(0, L, int(L) + 1)[:, None]
        strokes.append(Stroke(p0 + t * [np.cos(a), np.sin(a)], width=np.full(len(t), 2.0)))
    g = learn([_frame(strokes)], name="lines", len_quantile=0.0)
    assert g.segment_counts()["line"] >= 8
    gen = np.random.default_rng(1)
    for _ in range(20):
        st = generate_stroke(g, gen, ref_length=1000)
        assert all(s["kind"] == "line" for s in st.meta["segments"])
        p = st.points
        assert np.linalg.norm(p[-1] - p[0]) > 0.999 * st.length()


def test_arcs_make_arcs():
    kappa = 1.0 / 150.0
    strokes = []
    for i in range(6):
        p = integrate_kappa(np.array([0, 320.0]), np.array([kappa, kappa]), 1.0,
                            start=(100 + 120 * i, 100 + 100 * i), heading=0.4 * i)
        strokes.append(Stroke(p, width=np.full(len(p), 2.0)))
    d = _frame(strokes)
    g = learn([d], name="arcs", len_quantile=0.0)
    R = d.ref_length()
    assert g.segment_counts()["arc"] >= 6
    gen = np.random.default_rng(2)
    for _ in range(20):
        st = generate_stroke(g, gen, ref_length=R)
        for s in st.meta["segments"]:
            assert s["kind"] == "arc"
            assert abs(abs(s["k0"]) - kappa) < 0.2 * kappa
        if st.length() > 100:
            _s, k, _ = kappa_s(st.points, sigma=3.0)
            mid = np.abs(k[len(k) // 4: 3 * len(k) // 4])
            assert abs(np.median(mid) - kappa) < 0.2 * kappa


def test_kappa_continuity(g_matisse, g_random, g_fine):
    rng = np.random.default_rng(4)
    n = 0
    for g in (g_matisse, g_random):
        for _ in range(40):
            n += _assert_kappa_continuous(generate_stroke(g, rng, ref_length=900))
    for st in generate_drawing(g_fine, rng, (900, 900)).strokes:      # steered strokes
        n += _assert_kappa_continuous(st)
    st = generate_drawing(g_fine, rng, (900, 900), mode="single").strokes[0]   # chunk joints
    n += _assert_kappa_continuous(st)
    assert n > 20


def test_contiguous_few_long_strokes(g_matisse):
    d = generate_drawing(g_matisse, np.random.default_rng(11), (900, 700))
    R = d.meta["ref_length_gen"]
    assert 1 <= len(d.strokes) <= 60
    L = np.array([s.length() for s in d.strokes]) / R
    assert L.min() >= 0.98 * g_matisse.min_length           # no fragments
    assert d.meta["ink"] >= 0.5 * d.meta["ink_budget"] or len(d.strokes) >= 3
    for s in d.strokes:
        assert s.width is not None and np.allclose(s.width, d.meta["line_width_px"])


def test_branching_starts_on_existing_strokes(g_matisse):
    d = generate_drawing(g_matisse, np.random.default_rng(12), (900, 900), p_branch=0.9)
    br = [(i, s) for i, s in enumerate(d.strokes) if s.meta.get("relation") == "branch"]
    assert br, "no branches generated"
    for i, s in br:
        h = d.strokes[s.meta["host"]]
        assert s.meta["host"] < i
        dist = np.min(np.linalg.norm(h.points - s.points[0], axis=1))
        assert dist < 1e-6


def test_single_mode_one_stroke(g_matisse, g_random, g_fine):
    d = generate_drawing(g_fine, np.random.default_rng(13), (800, 800), mode="single", ink=3.0,
                         chain_budget=0.0)
    assert len(d.strokes) == 1
    st = d.strokes[0]
    assert st.length() / d.meta["ref_length_gen"] > 0.8
    # v6 budget on: toy-hand single lines stall as often as without it (median over seeds;
    # v7: 30 seeds — the 8-seed median swung .43–.52 with the rng stream alone)
    ls = []
    for sd in range(10, 40):
        db = generate_drawing(g_fine, np.random.default_rng(sd), (800, 800), mode="single", ink=3.0)
        assert len(db.strokes) == 1
        ls.append(db.strokes[0].length() / db.meta["ref_length_gen"])
    assert np.median(ls) > 0.45
    # two hands along one line
    rng = np.random.default_rng(8)
    g_fine2 = learn([synth.scene_random(rng, 1500, n_strokes=10, length_frac=(0.08, 0.25),
                                        n_segments=(2, 4), kappa_max_frac=4.0) for _ in range(3)],
                    name="synth_f2")
    d2 = generate_drawing(g_fine, np.random.default_rng(14), (800, 800), mode="single", ink=3.0,
                          hands=(g_fine, g_fine2), switch_every=0.5)
    assert len(d2.strokes) == 1
    spans = d2.strokes[0].meta["spans"]
    assert spans and spans[0][2] == "synth_f"
    assert {sp[2] for sp in spans} <= {"synth_f", "synth_f2"}
    # (v4: on these toy hands the line can stall before its first switch, so
    # both hands appearing is not asserted; the real-corpus juxtaposition
    # sheet shows the switch — and stalling is a known gap, grammar-v4.md)


def test_tokens_helpers(g_random):
    rng = np.random.default_rng(3)
    t = g_random.strokes[0]
    sh = shuffle_tokens(t, rng)
    assert sorted(map(str, sh)) == sorted(map(str, t))
    assert sh[0][0] != "corner" and sh[-1][0] != "corner"
    toks, _ = generate_tokens(g_random, rng, length=0.3)
    tr = truncate_tokens(toks, 0.1)
    assert sum(x[1] for x in tr if x[0] != "corner") == pytest.approx(min(0.1, sum(
        x[1] for x in toks if x[0] != "corner")))


def test_juxtaposition_ops(g_matisse, g_random):
    rng = np.random.default_rng(6)
    cs = code_switch(g_matisse, g_random, rng, 0.5, ref_length=800)
    assert np.all(np.isfinite(cs.points))
    si = cs.meta["switch_index"]
    toks = cs.meta["tokens"]
    if 0 < si < len(toks) and toks[si - 1][0] != "corner" and toks[si][0] != "corner":
        assert toks[si][2] == pytest.approx(toks[si - 1][3])
    st = synth.random_clothoid_stroke(np.random.default_rng(1), 400, 4, 0.01)
    f = fit_stroke(st.points, sigma=6.0)
    tr = translate(f, g_matisse, g_random, ref_length=800)
    assert np.all(np.isfinite(tr.points))
    t = np.linspace(0, np.pi, 400)
    path = np.column_stack([300 + 200 * np.cos(t), 300 + 200 * np.sin(t)])
    rs = restyle(path, g_random, np.random.default_rng(3), ref_length=800)
    assert np.linalg.norm(rs.points[-1] - path[-1]) < 5.0
    assert np.linalg.norm(rs.points[0] - path[0]) < 5.0


def test_memorisation_distance(g_random):
    d0 = nearest_training_distance([g_random.strokes[0]], g_random)
    assert d0[0] == pytest.approx(0.0, abs=1e-6)
    d1 = nearest_training_distance([reverse_tokens(g_random.strokes[1])], g_random)
    assert d1[0] == pytest.approx(0.0, abs=1e-6)
    gen = [generate_stroke(g_random, np.random.default_rng(i), ref_length=600) for i in range(10)]
    d = nearest_training_distance(gen, g_random)
    assert len(d) == 10 and np.all(np.isfinite(d)) and np.all(d >= 0)
    gc = learn(prepared=None, drawings=[], name="empty")
    assert gc.meta["n_strokes"] == 0


# ---------------------------------------------------------------------------
# v5: topology targets, sharp joins, end plans
# ---------------------------------------------------------------------------

def _hand_set(g, **end_p):
    """A copy of g whose topology targets are hand-set (end shares etc.)."""
    h = Grammar.from_json(g.to_json())
    topo = dict(h.relations["topo"])
    topo["end_p"] = {k: float(end_p.get(k, 0.0)) for k in ("T", "L", "near", "free")}
    topo.setdefault("l_defl", [1.2])
    h.relations = {**h.relations, "topo": topo, "end_gain": {}, "p_double": 0.0}
    return h


def test_topology_targets_learned(g_fine):
    topo = g_fine.relations["topo"]
    assert sum(topo["end_p"].values()) == pytest.approx(1.0)
    assert topo["n_drawings"] == 3
    assert g_fine.relations["corner_rate"] >= 0.0
    assert g_fine.version == 6


def test_joins_are_sharp(g_fine):
    g = _hand_set(g_fine, L=0.45, free=0.55)
    g.relations["topo"]["l_defl"] = [1.2]
    d = generate_drawing(g, np.random.default_rng(21), (900, 900))
    joins = [s for s in d.strokes if s.meta.get("relation") == "join"]
    assert joins, "no joins generated"
    for s in joins:
        assert abs(abs(s.meta["branch_angle"]) - 1.2) < 0.25       # learned deflection, not smooth
        h = d.strokes[s.meta["host"]].points
        e = h[0] if s.meta["host_end"] == 0 else h[-1]
        assert np.linalg.norm(s.points[0] - e) < 1e-6                # starts exactly at the host's end
    # v4 (smooth continuation) for comparison
    d4 = generate_drawing(g, np.random.default_rng(21), (900, 900), join="smooth")
    a4 = [abs(s.meta["branch_angle"]) for s in d4.strokes if s.meta.get("relation") == "join"]
    assert not a4 or np.median(a4) < 0.6


def test_end_plans_reach_ink(g_fine, monkeypatch):
    import gesture.grammar as gmod
    monkeypatch.setattr(gmod, "SEEK_FROM", 0.5)          # seek earlier so the toy hand arrives often
    monkeypatch.setattr(gmod, "SEEK_WIN", 0.5)           # (v6: the seek window around the plan)
    g = _hand_set(g_fine, T=0.6, near=0.4)
    # (v6: a sheet takes ONE training drawing's ink — 5 toy strokes — so ask for more)
    d = generate_drawing(g, np.random.default_rng(22), (900, 900), ink=3.0)
    st = d.meta["grow_stats"]
    assert st["end_T"] + st["end_near"] > 0
    R = d.meta["ref_length_gen"]
    for i, s in enumerate(d.strokes):
        if s.meta["end"] not in ("T", "near"):
            continue
        others = np.vstack([o.points for j, o in enumerate(d.strokes) if j != i])
        gap = np.min(np.linalg.norm(others - s.points[-1], axis=1))
        if s.meta["end"] == "T":
            assert gap <= 0.005 * R + 1.0
        else:
            assert d.meta["clearance_px"] * 0.9 <= gap <= 0.02 * R * 1.5


def test_v4_mode_and_old_grammars(g_matisse):
    d = generate_drawing(g_matisse, np.random.default_rng(23), (800, 800), ends="v4", kmatch=0.0,
                         corner_budget=0.0)
    assert d.meta["ends"] == "v4" and len(d.strokes) >= 1
    g = Grammar.from_json({k: v for k, v in g_matisse.to_json().items()})
    g.relations = {k: v for k, v in g.relations.items() if k != "topo"}   # a pre-v5 grammar
    d2 = generate_drawing(g, np.random.default_rng(23), (800, 800))
    assert d2.meta["ends"] == "v4"


# v7: smoothed plans, the drawing's segment scale, no end stubs, long lines first

def test_v7_plans_and_segment_scale(g_fine):
    from gesture.grammar import plan_line
    rng = np.random.default_rng(3)
    lens = {round(x, 9) for x in g_fine.stroke_lengths}
    p6 = [plan_line(g_fine, rng, drawing=0) for _ in range(20)]
    p7 = [plan_line(g_fine, rng, drawing=0, mode="v7") for _ in range(20)]
    assert all(round(p["length"], 9) in lens for p in p6)          # v6 copies a training length
    assert sum(round(p["length"], 9) in lens for p in p7) <= 2     # v7 smooths it
    assert all(np.isfinite(p["dscale"]) and np.isfinite(p["rho_c"]) for p in p7)
    sd, ds = g_fine.drawing_scales()
    assert len(sd) == len(g_fine.strokes) and (sd >= 0).all() and np.isfinite(ds).all()
    # the segment-scale context and end fit keep tokens valid and lengths on target
    for sd_ in range(5):
        toks, _ = generate_tokens(g_fine, np.random.default_rng(sd_), length=0.15, budget=1.0,
                                  seg_scale=4.0, plan_mode="v7", end_fit=0.5)
        assert toks and toks[-1][0] != "corner"
        assert abs(sum(t[1] for t in toks if t[0] != "corner") - 0.15) < 1e-6


def test_v7_drawing_flags(g_fine):
    kw6 = dict(plans="v6", seg_scale=0.0, order="draw", end_fit=0.0)
    for kw in ({}, kw6):
        d = generate_drawing(g_fine, np.random.default_rng(21), (900, 900), **kw)
        assert d.strokes and all(np.isfinite(s.points).all() for s in d.strokes)
        assert d.meta["order"] == kw.get("order", "long")
    d = generate_drawing(g_fine, np.random.default_rng(22), (900, 900), mode="single", ink=2.0)
    assert len(d.strokes) == 1
