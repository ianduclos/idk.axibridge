"""Hessian ridge extractor: contract, junction behaviour, purity, determinism.

Small synthetic canvases so the whole file runs in a few seconds."""
import numpy as np
import pytest

from gesture import synth
from gesture.core import Drawing, Stroke
from gesture.extract_eval import score_gt
from gesture.extract_ridge import estimate_width, extract

SIZE = (500, 500)


def _gray(drawing, lw=4.0, noise=0.03):
    return synth.render(drawing, line_width=lw, paper_noise=noise,
                        use_stroke_width=False, seed=3).astype(np.float64) / 255.0


@pytest.fixture(scope="module")
def loop():
    d = synth.scene_closed_loop(SIZE)
    g = _gray(d)
    return d, g, extract(g)


@pytest.fixture(scope="module")
def cross():
    d = synth.scene_x_crossing(SIZE)
    g = _gray(d)
    return d, g, extract(g)


def test_contract_types(loop):
    _, g, found = loop
    assert isinstance(found, Drawing)
    assert found.size == (g.shape[1], g.shape[0])
    for s in found.strokes:
        assert isinstance(s, Stroke)
        assert s.points.ndim == 2 and s.points.shape[1] == 2
        assert s.width is not None and s.width.shape == (len(s),)
        assert np.all(s.width > 0)
        if s.closed:   # closed strokes do not repeat point 0
            assert np.linalg.norm(s.points[0] - s.points[-1]) > 0.1


def test_closed_loop_is_one_closed_stroke(loop):
    truth, _, found = loop
    assert len(found.strokes) == 1
    assert found.strokes[0].closed
    sc = score_gt(truth, found, 4.0)
    assert sc["coverage"] > 0.99 and sc["precision"] > 0.99
    assert sc["centre_err_px"] < 0.6


def test_x_crossing_continues_through(cross):
    truth, _, found = cross
    assert len(found.strokes) == 2
    sc = score_gt(truth, found, 4.0)
    assert sc["continuity"] > 0.97
    assert sc["fragments"] == 1.0


def test_t_junction_stem_stays_an_end():
    d = synth.scene_t_junction(SIZE)
    found = extract(_gray(d))
    sc = score_gt(d, found, 4.0)
    assert len(found.strokes) == 2          # bar unbroken, stem separate
    assert sc["continuity"] > 0.95


def test_xy_convention():
    """A horizontal bar at row 120 → points with y ≈ 120 (x = column)."""
    g = np.ones((240, 300))
    g[118:123, 40:260] = 0.0           # 5 px bar centred on row 120
    found = extract(g)
    assert len(found.strokes) == 1
    p = found.strokes[0].points
    assert abs(np.median(p[:, 1]) - 120.0) < 0.3
    assert p[:, 0].min() < 60 and p[:, 0].max() > 240
    assert abs(np.median(found.strokes[0].width) - 5.0) < 1.5


def test_width_estimate_tracks_line_width():
    d = synth.scene_closed_loop(SIZE)
    w3, w8 = estimate_width(_gray(d, lw=3.0)), estimate_width(_gray(d, lw=8.0))
    assert 2.5 < w3 < 5.0 and 7.0 < w8 < 10.0


def test_purity_and_determinism(cross):
    _, g, found = cross
    g2 = g.copy()
    again = extract(g2)
    np.testing.assert_array_equal(g, g2)
    assert len(again.strokes) == len(found.strokes)
    for a, b in zip(found.strokes, again.strokes):
        np.testing.assert_array_equal(a.points, b.points)
        np.testing.assert_array_equal(a.width, b.width)


def test_blank_page_gives_nothing():
    g = np.full((200, 200), 0.95) + 0.01 * np.random.default_rng(0).standard_normal((200, 200))
    assert len(extract(g).strokes) == 0
