import numpy as np
import pytest

from gesture import synth
from gesture.core import Drawing, Stroke
from gesture.extract_eval import score_gt
from gesture.extract_flow import extract

SIZE = (400, 400)
LW = 4.0


def _gray(d: Drawing, seed=3, noise=0.03):
    return synth.render(d, line_width=LW, paper_noise=noise, use_stroke_width=False,
                        seed=seed).astype(np.float64) / 255.0


def _long(drawing, frac=0.1):
    L = max(s.length() for s in drawing.strokes)
    return [s for s in drawing.strokes if s.length() >= frac * L]


def test_circle_is_one_closed_stroke():
    R = 120.0
    t = np.linspace(0, 2 * np.pi, 1500, endpoint=False)
    pts = np.column_stack([200 + R * np.cos(t), 200 + R * np.sin(t)])
    truth = Drawing([Stroke(pts, closed=True)], size=SIZE)
    d = extract(_gray(truth))
    assert len(d.strokes) == 1
    s = d.strokes[0]
    assert s.closed
    assert not np.allclose(s.points[0], s.points[-1])        # no repeated point 0
    r = np.hypot(*(s.points - 200).T)
    assert np.abs(r - R).max() < 1.5
    assert abs(s.length() - 2 * np.pi * R) < 0.03 * 2 * np.pi * R
    assert s.width is not None and abs(np.median(s.width) - LW) < 2.0


def test_x_crossing_passes_straight_through():
    truth = synth.scene_x_crossing(SIZE)
    d = extract(_gray(truth))
    assert len(d.strokes) == 2
    sc = score_gt(truth, d, LW)
    assert sc["continuity"] > 0.97
    assert sc["fragments"] == 1.0
    assert sc["coverage"] > 0.99 and sc["precision"] > 0.99


def test_t_junction_bar_unbroken():
    truth = synth.scene_t_junction(SIZE)
    d = extract(_gray(truth))
    sc = score_gt(truth, d, LW)
    assert sc["coverage"] > 0.98
    # the bar (stroke 0) is covered by a single extracted stroke end to end
    bar = truth.strokes[0]
    best = max(d.strokes, key=lambda s: s.length())
    assert best.length() > 0.95 * bar.length()
    from scipy.spatial import cKDTree
    dist = cKDTree(best.points).query(bar.points[::10])[0]
    assert (dist < 2.0).mean() > 0.97
    assert len(_long(d)) == 2                       # bar + stem, no spurs


def test_pure_and_deterministic():
    truth = synth.scene_random(np.random.default_rng(5), SIZE, 4)
    g = _gray(truth, noise=0.08)
    g0 = g.copy()
    a = extract(g)
    assert np.array_equal(g, g0)
    b = extract(g)
    assert len(a.strokes) == len(b.strokes)
    for s, t in zip(a.strokes, b.strokes):
        assert np.array_equal(s.points, t.points) and s.closed == t.closed
    assert a.size == (SIZE[0], SIZE[1])


def test_blank_page_gives_no_strokes():
    rng = np.random.default_rng(0)
    g = np.clip(0.95 + 0.01 * rng.standard_normal((200, 300)), 0, 1)
    d = extract(g)
    assert d.size == (300, 200)
    assert len(d.strokes) <= 2      # paper grain: at most a stray speck


@pytest.mark.parametrize("mask", ["bg", "sauvola"])
def test_points_in_bounds_and_contract(mask):
    truth = synth.scene_x_crossing(SIZE)
    d = extract(_gray(truth), mask=mask)
    for s in d.strokes:
        assert s.points.shape[1] == 2 and len(s) >= 3
        assert (s.points >= 0).all() and (s.points[:, 0] <= SIZE[0] - 1).all()
        assert (s.points[:, 1] <= SIZE[1] - 1).all()
        assert s.width.shape == (len(s),)
