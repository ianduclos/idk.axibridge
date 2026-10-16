"""Tests for gesture/regime_field.py: regime fields, hand fields, the
composition pipeline, the hatching detector and SVG export. Corpus-free: the
hand is a tiny v4 grammar learned from synthetic drawings (as in
test_composite.py)."""
from __future__ import annotations

import numpy as np
import pytest

from experiments import composite as cp
from gesture import regime_field as rf
from gesture import synth
from gesture.core import Drawing, Stroke
from gesture.grammar_v4_frozen import learn

SIZE = (300, 420)


@pytest.fixture(scope="module")
def hand():
    rng = np.random.default_rng(1)
    ds = [synth.scene_matisse_like(rng, 600, n_strokes=5) for _ in range(3)]
    rf.register_hand("synth", learn(ds, name="synth_m"))
    return "synth"


def _tree() -> Drawing:
    """trunk (0) with two leaf branches (1, 2) and a twig on branch 1 (3)."""
    t = np.linspace(0, 1, 60)
    trunk = np.column_stack([150 + 5 * np.sin(6 * t), 400 - 360 * t])
    b1 = np.column_stack([150 + 100 * t, 250 - 80 * t])
    b2 = np.column_stack([150 - 90 * t, 180 - 60 * t])
    tw = np.column_stack([200 + 30 * t, 225 + 40 * t])
    return Drawing([Stroke(trunk, meta={"order": 0, "host": None}), Stroke(b1, meta={"order": 1, "host": 0}),
                    Stroke(b2, meta={"order": 1, "host": 0}), Stroke(tw, meta={"order": 2, "host": 1})],
                   size=SIZE)


def _fields(seed: int):
    d = _tree()
    a = SIZE[1] / SIZE[0]
    base = [rf.axis(0.5, seed=seed, aspect=a), rf.bands(seed=seed, aspect=a), rf.margins(seed=seed, aspect=a),
            rf.radial(seed=seed, aspect=a, lobes=3, lobe_amp=0.3), rf.noise_fronts(seed, aspect=a),
            rf.structure_field(d, "strahler"), rf.structure_field(d, "order"),
            rf.structure_field(d, "density"), rf.structure_field(d, "trunk")]
    mixed = [rf.mix(base[0], base[4], base[1]), rf.maximum(*base[:3]), rf.minimum(base[3], base[4]),
             rf.warp(base[0], seed), rf.levels(base[4]), rf.offset(base[2], 0.7), rf.scale(base[1], 1.8)]
    return base + mixed + [p(d, seed, a) for p in rf.PRESETS.values()]


def test_fields_deterministic_and_in_range():
    u = np.random.default_rng(0).uniform(-0.2, 1.2, size=(500, 2))   # includes points off the sheet
    A = [f(u) for f in _fields(4)]
    B = [f(u) for f in _fields(4)]
    for f, a, b in zip(_fields(4), A, B):
        assert a.shape == (500,) and np.all(np.isfinite(a)), f.name
        assert a.min() >= 0.0 and a.max() <= 2.0, f.name
        assert np.array_equal(a, b), f.name
    # a seeded field changes with the seed; authored fields cover more than one regime
    assert not np.array_equal(rf.noise_fronts(4)(u), rf.noise_fronts(5)(u))
    assert np.ptp(rf.axis(0.5)(u)) > 1.5


def test_strahler_and_structure_field():
    d = _tree()
    assert rf.strahler(d).tolist() == [2, 1, 1, 1]
    f = rf.structure_field(d, "strahler", sigma=0.02)
    on_trunk = f.at_px(np.array([[150.0, 380.0]]), SIZE)[0]
    on_twig = f.at_px(np.array([[225.0, 258.0]]), SIZE)[0]
    assert on_trunk > on_twig


def test_hand_fields_and_runs(hand):
    hf = rf.hand_zones(["a", "b", "c"], 2, aspect=1.4)
    w = hf.weights(np.random.default_rng(1).uniform(0, 1, (200, 2)))
    assert np.allclose(w.sum(axis=1), 1) and w.min() >= 0
    hb = rf.hand_bands(["a", "b"], [0.5])
    assert hb.dominant(np.array([[0.1, 0.5], [0.9, 0.5]])) == ["a", "b"]
    line = np.column_stack([np.linspace(10, 290, 300), np.full(300, 200.0)])
    runs = rf.hand_runs(line, hb, SIZE, np.random.default_rng(0), piece=20)
    assert runs[0][0] == 0 and runs[-1][1] == len(line) - 1
    assert {h for _, _, h in runs} == {"a", "b"}
    # a line that changes hand stays one continuous line (cross-faded runs)
    rf.register_hand("a", rf.load_hand(hand))
    rf.register_hand("b", rf.load_hand(hand))
    out = rf.restyle_line(line, runs, np.random.default_rng(3), amount=0.5, R=500.0, overlap=10.0)
    assert np.all(np.isfinite(out)) and len(out) > 50
    assert np.max(np.linalg.norm(np.diff(out, axis=0), axis=1)) < 15.0


@pytest.mark.parametrize("eng", ["auto", "standin"])
def test_pipeline_polylines_only_no_hatching(hand, eng):
    c = rf.compose(5, SIZE, structure="tree", field="sense", hands=hand, signs=4, echo=1, drip=3,
                   amount=0.5, engine_name=eng, structure_params={"max_strokes": 25})
    assert c.polylines, "nothing drawn"
    W, H = SIZE
    for q in c.polylines:
        assert isinstance(q, np.ndarray) and q.ndim == 2 and q.shape[1] == 2 and len(q) >= 2
        assert np.all(np.isfinite(q))
        assert q[:, 0].min() >= 0 and q[:, 0].max() <= W and q[:, 1].min() >= 0 and q[:, 1].max() <= H
    hat = rf.hatching_families(c.polylines, max_len=0.06 * H, solid_gap=1.25 * c.meta["pen_px"])
    assert hat["families"] == 0, hat
    assert sum(c.meta["regime_share"].values()) == pytest.approx(1.0)


def test_compose_deterministic(hand):
    kw = dict(structure="tree", field="noise", hands=hand, signs=3, engine_name="standin", amount=0.4,
              structure_params={"max_strokes": 15})
    a = rf.compose(9, SIZE, **kw)
    b = rf.compose(9, SIZE, **kw)
    assert len(a.polylines) == len(b.polylines)
    assert all(np.array_equal(x, y) for x, y in zip(a.polylines, b.polylines))


def test_hatching_detector():
    hatch = [np.array([[10.0 + 4 * i, 10.0], [14.0 + 4 * i, 30.0]]) for i in range(8)]
    assert rf.hatching_families(hatch, max_len=40)["families"] >= 1
    zig = np.array([[10.0 + 3 * i, 10.0 if i % 2 == 0 else 30.0] for i in range(12)])
    assert rf.hatching_families([zig], max_len=40)["flagged"] >= 4
    t = np.linspace(0, 2 * np.pi, 60)
    rings = [np.column_stack([50 + r * np.cos(t), 50 + r * np.sin(t)]) for r in (4, 6, 8, 10)]
    for r in rings:
        r[-1] = r[0]
    curve = [np.column_stack([np.linspace(0, 200, 100), 50 + 20 * np.sin(np.linspace(0, 6, 100))])]
    assert rf.hatching_families(rings + curve, max_len=40)["families"] == 0
    # pen-spaced parallel strokes ink solid: fill, not hatching
    fill = [np.array([[10.0 + 1.0 * i, 10.0], [12.0 + 1.0 * i, 30.0]]) for i in range(8)]
    h = rf.hatching_families(fill, max_len=40, solid_gap=1.25)
    assert h["families"] == 0 and h["solid"] == 1
    assert rf.hatching_families(hatch, max_len=40, solid_gap=1.25)["families"] >= 1


def test_svg_bounds(hand):
    c = rf.compose(2, SIZE, structure="tree", field="axis", hands=hand, signs=2, amount=0.4,
                   engine_name="standin", structure_params={"max_strokes": 15})
    svg, st = cp.to_svg(c.drawing(), None, paper="A4", portrait=True, margin_mm=10.0)
    (W, H), paths = cp.read_svg_paths(svg)
    assert (W, H) == (210.0, 297.0)
    P = np.vstack(paths)
    assert P[:, 0].min() >= 10 - 0.5 and P[:, 0].max() <= W - 10 + 0.5
    assert P[:, 1].min() >= 10 - 0.5 and P[:, 1].max() <= H - 10 + 0.5
    assert st["paths"] == len(paths) and st["pen_down_mm"] > 0
