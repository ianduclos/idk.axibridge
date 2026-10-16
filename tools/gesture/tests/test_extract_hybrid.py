"""extract topology + sub-pixel refinement: contract, crossings, κ accuracy
vs the plain extractor, purity, determinism."""
import numpy as np
import pytest

from gesture import extract as plain
from gesture import synth
from gesture.core import Drawing, Stroke
from gesture.extract_eval import score_gt
from gesture.extract_hybrid import extract

SIZE = (500, 500)
LW = 3.0


def _gray(d, lw=LW, noise=0.03):
    return synth.render(d, line_width=lw, paper_noise=noise, use_stroke_width=False,
                        seed=7).astype(np.float64) / 255.0


@pytest.fixture(scope="module")
def loop():
    d = synth.scene_closed_loop(SIZE)
    g = _gray(d)
    return d, g, extract(g)


def test_contract(loop):
    _, g, found = loop
    assert isinstance(found, Drawing)
    assert found.size == (g.shape[1], g.shape[0])
    assert found.meta["method"].startswith("hybrid:extract")
    assert len(found.strokes) == 1 and found.strokes[0].closed
    for s in found.strokes:
        assert isinstance(s, Stroke) and s.points.shape[1] == 2
        assert s.width is not None and s.width.shape == (len(s),)


def test_kappa_better_than_plain(loop):
    truth, g, found = loop
    base = plain.extract(g)
    a = score_gt(truth, base, LW)
    b = score_gt(truth, found, LW)
    assert b["coverage"] >= a["coverage"] - 0.01
    assert b["kappa_err"] < 0.5 * a["kappa_err"], (a["kappa_err"], b["kappa_err"])


def test_x_crossing_two_strokes():
    truth = synth.scene_x_crossing(SIZE)
    g = _gray(truth)
    d = extract(g)
    sc = score_gt(truth, d, LW)
    assert len(d.strokes) == 2
    assert sc["continuity"] > 0.95 and sc["coverage"] > 0.98


def test_refine_false_is_plain(loop):
    _, g, _ = loop
    a = extract(g, refine=False)
    b = plain.extract(g)
    assert len(a.strokes) == len(b.strokes)
    assert all(np.array_equal(x.points, y.points) for x, y in zip(a.strokes, b.strokes))


def test_scale_frame():
    """With scale ≠ 1 the output is in ORIGINAL px, like extract's."""
    truth = synth.scene_closed_loop(SIZE)
    g = _gray(truth)
    d1 = extract(g)
    d2 = extract(g, scale=0.5)
    p1, p2 = d1.strokes[0].points, d2.strokes[0].points
    c1 = p1.mean(axis=0)
    c2 = (p2.mean(axis=0) + 0.5) * 0.5 - 0.5
    assert np.allclose(c1, c2, atol=0.5)


def test_purity_determinism(loop):
    _, g, found = loop
    g0 = g.copy()
    again = extract(g)
    assert np.array_equal(g, g0)
    assert all(np.array_equal(x.points, y.points) for x, y in zip(found.strokes, again.strokes))


def test_ridge_base():
    truth = synth.scene_closed_loop(SIZE)
    g = _gray(truth)
    d = extract(g, base="ridge")
    assert d.meta["method"] == "hybrid:ridge+subpixel"
    assert score_gt(truth, d, LW)["kappa_err"] < 0.3
    with pytest.raises(ValueError):
        extract(g, base="nope")
