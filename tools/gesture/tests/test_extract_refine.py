"""Fast synthetic checks for gesture.extract_refine (the careful skeleton
pipeline). Small canvases so the whole file runs in a few seconds."""
import numpy as np
import pytest
from scipy.spatial import cKDTree

from gesture import synth
from gesture.extract_eval import score_gt
from gesture.extract_refine import extract

SIZE = (360, 360)
LW = 4.0


def _render(d, lw=LW, noise=0.03):
    return synth.render(d, line_width=lw, paper_noise=noise, use_stroke_width=False,
                        seed=3).astype(np.float64) / 255.0


@pytest.fixture(scope="module")
def scenes():
    out = {}
    for name, d in (("loop", synth.scene_closed_loop(SIZE)),
                    ("x", synth.scene_x_crossing(SIZE)),
                    ("t", synth.scene_t_junction(SIZE))):
        g = _render(d)
        out[name] = (d, g, extract(g))
    return out


def test_circle_is_one_closed_stroke(scenes):
    truth, g, d = scenes["loop"]
    assert len(d.strokes) == 1
    s = d.strokes[0]
    assert s.closed
    assert not np.allclose(s.points[0], s.points[-1])  # no repeated first point
    sc = score_gt(truth, d, LW)
    assert sc["coverage"] > 0.99 and sc["precision"] > 0.99
    assert sc["centre_err_px"] < 0.6


def test_x_crossing_gives_two_unbroken_strokes(scenes):
    truth, g, d = scenes["x"]
    assert len(d.strokes) == 2
    sc = score_gt(truth, d, LW)
    assert sc["continuity"] > 0.98
    assert sc["fragments"] == 1.0


def test_t_junction_bar_unbroken_stem_ends(scenes):
    truth, g, d = scenes["t"]
    sc = score_gt(truth, d, LW)
    assert len(d.strokes) == 2
    assert sc["continuity"] > 0.98
    # the stem ends at the junction on the bar: one of its tips lies within
    # ~one line width of the bar's centreline
    bar = truth.strokes[0].points
    junction = np.asarray(truth.strokes[1].meta["junction"])
    tree = cKDTree(bar)
    stem = max(d.strokes, key=lambda s: tree.query(s.points)[0].mean())  # off the bar
    tips = np.array([stem.points[0], stem.points[-1]])
    assert np.min(np.linalg.norm(tips - junction, axis=1)) < 2.5 * LW


def test_contract_shapes_and_width(scenes):
    for _, g, d in scenes.values():
        assert d.size == (g.shape[1], g.shape[0])
        for s in d.strokes:
            assert s.points.ndim == 2 and s.points.shape[1] == 2
            assert s.width is not None and s.width.shape == (len(s),)
            # full width, not radius: within a factor ~2 of the rendered width
            assert 0.5 * LW < np.median(s.width) < 2.0 * LW


def test_purity_and_determinism(scenes):
    _, g, d1 = scenes["x"]
    g0 = g.copy()
    d2 = extract(g)
    assert np.array_equal(g, g0)
    assert len(d1.strokes) == len(d2.strokes)
    for a, b in zip(d1.strokes, d2.strokes):
        assert np.array_equal(a.points, b.points) and a.closed == b.closed


def test_ablation_flags_run(scenes):
    _, g, _ = scenes["x"]
    for kw in ({"thin_method": "lee"}, {"match": False}, {"refine": False},
               {"hermite": False}, {"morph": "none", "bridge_gaps": False}):
        d = extract(g, **kw)
        assert len(d.strokes) >= 2
    # without junction matching an X is four edges
    assert len(extract(g, match=False).strokes) == 4


def test_blank_page_returns_empty_drawing():
    g = np.ones((80, 90))
    d = extract(g)
    assert d.strokes == [] and d.size == (90, 80)
