"""Topology layer: relation detection on scenes with known relations,
determinism, purity, generator invariants."""
import copy

import numpy as np
import pytest

from gesture import topology as tp
from gesture.core import Drawing, Stroke


def _line(a, b, n=200):
    a, b = np.asarray(a, float), np.asarray(b, float)
    t = np.linspace(0, 1, n)[:, None]
    return Stroke(a + t * (b - a))


def _arc(c, r, a0, a1, n=300, closed=False):
    t = np.linspace(a0, a1, n, endpoint=not closed)
    return Stroke(np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)]), closed=closed)


def _d(*strokes, size=(1200, 1200)):
    return Drawing(list(strokes), size=size, meta={"line_width_px": 3.0})


def test_t_junction():
    t = tp.relation_graph(_d(_line((100, 600), (1100, 600)), _line((700, 100), (700, 600))))
    ends = [e for e in t.ends if e["stroke"] == 1]
    kinds = sorted(e["kind"] for e in ends)
    assert "T" in kinds
    e = next(e for e in ends if e["kind"] == "T")
    assert e["host"] == 0
    assert abs(e["u"] - 0.6) < 0.03
    assert abs(e["angle"] - np.pi / 2) < 0.1
    assert not t.crosses


def test_x_crossing_and_angle():
    t = tp.relation_graph(_d(_line((100, 100), (1100, 1100)), _line((100, 1100), (1100, 100))))
    assert len(t.crosses) == 1
    assert abs(t.crosses[0]["angle"] - np.pi / 2) < 0.05
    assert all(e["kind"] in ("free", "near") for e in t.ends)


def test_join_end_to_end():
    t = tp.relation_graph(_d(_line((100, 600), (600, 600)), _line((600, 600), (600, 100))))
    kinds = [e["kind"] for e in t.ends]
    assert kinds.count("L") == 2
    defl = [e["defl"] for e in t.ends if e["kind"] == "L"]
    assert all(abs(x - np.pi / 2) < 0.15 for x in defl)


def test_near_meeting_gap():
    # stem stops 0.01 R short of the host, pointing at it
    host = _line((100, 600), (1100, 600))
    R = np.hypot(1000, 500)
    stem = _line((600, 100), (600, 600 - 0.01 * R))
    t = tp.relation_graph(_d(host, stem))
    e = next(e for e in t.ends if e["stroke"] == 1 and e["kind"] != "free")
    assert e["kind"] == "near"
    assert abs(e["gap"] - 0.01) < 0.002
    assert e["aim"] < 0.2


def test_parallel_run_offset():
    a = _arc((600, 900), 400, np.pi * 1.1, np.pi * 1.9)
    b = _arc((600, 900), 430, np.pi * 1.2, np.pi * 1.8)     # nested, 30 px outside
    t = tp.relation_graph(_d(a, b))
    assert t.parallels
    R = t.R
    off = np.median([p["offset"] for p in t.parallels]) * R
    assert abs(off - 30) < 4
    assert max(p["cv"] for p in t.parallels) < 0.2
    assert not t.crosses
    f = tp.features_from(t)
    assert f["top_par_pairs"] == pytest.approx(0.5)


def test_nested_closed_forms():
    rings = [_arc((600, 600), r, 0, 2 * np.pi, closed=True) for r in (450, 300, 150)]
    t = tp.relation_graph(_d(*rings))
    assert sorted(f["depth"] for f in t.forms) == [1, 2, 3]
    f = tp.features_from(t)
    assert f["top_closed"] == 1.0 and f["top_nest_max"] == 3
    assert t.cells["n"] == 3                     # disc + two annuli


def test_kiss_is_not_a_crossing():
    a = _arc((400, 600), 200, 0, 2 * np.pi, closed=True)
    b = _arc((800, 600), 200, 0, 2 * np.pi, closed=True)  # external tangency at (600, 600)
    t = tp.relation_graph(_d(a, b))
    assert len(t.kisses) == 1 and not t.crosses


def test_measure_is_pure_and_deterministic():
    d = _d(_line((100, 600), (1100, 600)), _line((700, 100), (700, 600)), _arc((600, 900), 300, 3.4, 6.0))
    before = copy.deepcopy(d.to_json())
    f1, f2 = tp.topology_features(d), tp.topology_features(d)
    assert d.to_json() == before
    assert {k: (None if np.isnan(v) else v) for k, v in f1.items()} == \
           {k: (None if np.isnan(v) else v) for k, v in f2.items()}


@pytest.mark.parametrize("kind", ["learned", "oehlen_tree"])
def test_generator_contiguous_deterministic(kind):
    m = tp.TopologyModel()
    d1 = tp.generate_structure(m, np.random.default_rng(3), (600, 700), kind=kind)
    d2 = tp.generate_structure(m, np.random.default_rng(3), (600, 700), kind=kind)
    assert len(d1.strokes) == len(d2.strokes) >= 3
    assert all(np.array_equal(a.points, b.points) for a, b in zip(d1.strokes, d2.strokes))
    R = d1.meta["ref_length_gen"]
    lens = np.array([s.length() for s in d1.strokes])
    assert lens.min() >= 0.019 * R              # no confetti
    assert np.median(lens) >= 0.05 * R          # long lines
    for s in d1.strokes:                         # contiguous: no jumps inside a line
        steps = np.linalg.norm(np.diff(s.points, axis=0), axis=1)
        assert steps.max() < 0.03 * R
        assert np.all((s.points >= 0) & (s.points <= np.array(d1.size)))


def test_tree_is_connected_and_model_roundtrip(tmp_path):
    d = tp.generate_structure(None, np.random.default_rng(5), (700, 700), kind="oehlen_tree", trunks=1)
    t = tp.relation_graph(d)
    f = tp.features_from(t)
    assert f["top_comp_largest"] > 0.8          # one tree, not scattered marks
    m = tp.learn_model([d], name="x")
    m.save(tmp_path / "m.json")
    m2 = tp.TopologyModel.load(tmp_path / "m.json")
    assert m2.to_json() == m.to_json()
