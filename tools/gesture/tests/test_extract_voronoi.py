"""Fast checks for the Voronoi medial-axis extractor (synthetic scenes)."""
import numpy as np
import pytest

from gesture import synth
from gesture.extract_eval import score_gt
from gesture.extract_voronoi import extract

SIZE = (400, 400)


def _render(d, lw=4.0):
    return synth.render(d, line_width=lw, paper_noise=0.03, use_stroke_width=False, seed=3) / 255.0


@pytest.fixture(scope="module")
def loop_case():
    d = synth.scene_closed_loop(SIZE)
    return d, _render(d)


@pytest.fixture(scope="module")
def x_case():
    d = synth.scene_x_crossing(SIZE)
    return d, _render(d)


def test_circle_is_one_closed_stroke(loop_case):
    truth, g = loop_case
    out = extract(g)
    assert len(out.strokes) == 1
    st = out.strokes[0]
    assert st.closed
    assert not np.allclose(st.points[0], st.points[-1])
    sc = score_gt(truth, out, 4.0)
    assert sc["coverage"] > 0.99 and sc["precision"] > 0.99
    assert sc["centre_err_px"] < 0.6
    assert st.width is not None and abs(np.median(st.width) - 4.0) < 1.5


def test_x_crossing_is_two_continuous_strokes(x_case):
    truth, g = x_case
    out = extract(g)
    assert len(out.strokes) == 2
    sc = score_gt(truth, out, 4.0)
    assert sc["continuity"] > 0.98
    assert sc["fragments"] == 1.0


def test_t_junction_stem_ends_bar_continues():
    truth = synth.scene_t_junction(SIZE)
    out = extract(_render(truth))
    sc = score_gt(truth, out, 4.0)
    assert len(out.strokes) == 2 and sc["continuity"] > 0.98


def test_pure_and_deterministic(x_case):
    _, g = x_case
    g0 = g.copy()
    a = extract(g)
    b = extract(g)
    assert np.array_equal(g, g0)
    assert len(a.strokes) == len(b.strokes)
    for s, t in zip(a.strokes, b.strokes):
        assert np.array_equal(s.points, t.points) and np.array_equal(s.width, t.width)


def test_blank_page_is_empty():
    g = np.full((120, 160), 0.97)
    out = extract(g)
    assert out.strokes == [] and out.size == (160, 120)
