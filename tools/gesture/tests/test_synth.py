import time

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter1d
from shapely.geometry import LineString, Point

from gesture import synth
from gesture.core import Drawing, Stroke
from gesture.curvature import kappa_s


def _line(st: Stroke) -> LineString:
    p = np.vstack([st.points, st.points[:1]]) if st.closed else st.points
    return LineString(p)


# ---------------------------------------------------------------- strokes

@pytest.mark.parametrize("seed", [0, 1, 2])
def test_clothoid_stroke_kappa_matches_model(seed):
    rng = np.random.default_rng(seed)
    st = synth.random_clothoid_stroke(rng, 600.0, 5, 0.01, start=(100, 100), heading=0.3)
    m = st.meta
    assert m["step"] <= 0.5
    assert len(m["breaks"]) == len(m["kappas"]) == 6 == len(m["types"]) + 1
    assert abs(st.length() - 600.0) < 0.5
    sigma, step = 3.0, 0.75
    s, k, _ = kappa_s(st.points, sigma, step=step)
    model = np.interp(s, m["breaks"], m["kappas"])
    expected = gaussian_filter1d(model, sigma / step, mode="nearest")  # same blur as measurement
    interior = (s > 4 * sigma) & (s < s[-1] - 4 * sigma)
    err = np.abs(k - expected)[interior]
    assert err.max() < 0.01 * 0.01, err.max()  # < 1% of kappa_max


def test_clothoid_stroke_never_self_intersects():
    rng = np.random.default_rng(7)
    for _ in range(15):
        st = synth.random_clothoid_stroke(rng, 800.0, 6, 0.05)  # tight curls: forces rejection
        assert LineString(st.points).is_simple


def test_segment_types_cover_lines_arcs_clothoids():
    rng = np.random.default_rng(0)
    types = set()
    for _ in range(20):
        types.update(synth.random_clothoid_stroke(rng, 400.0, 6, 0.01).meta["types"])
    assert {"line", "arc", "clothoid"} <= types


# ---------------------------------------------------------------- scenes

def test_x_crossing_intersects_once():
    d = synth.scene_x_crossing((600, 500))
    assert d.size == (600, 500) and len(d.strokes) == 2
    inter = _line(d.strokes[0]).intersection(_line(d.strokes[1]))
    assert inter.geom_type == "Point"


def test_t_junction_endpoint_on_interior():
    d = synth.scene_t_junction(500)
    a, b = d.strokes
    la = _line(a)
    end = Point(*b.points[-1])
    assert la.distance(end) <= 1.0
    # it lands in A's interior, not at A's ends
    assert min(np.linalg.norm(a.points[[0, -1]] - b.points[-1], axis=1)) > 0.1 * a.length()
    # B touches A only at that end
    assert LineString(b.points[:-20]).distance(la) > 2.0


def test_closed_loop_is_closed_and_simple():
    d = synth.scene_closed_loop((400, 400))
    (st,) = d.strokes
    assert st.closed
    assert not np.allclose(st.points[0], st.points[-1])
    assert np.linalg.norm(st.points[-1] - st.points[0]) < 1.0
    assert _line(st).is_simple and _line(st).is_ring


def _inside(d: Drawing):
    W, H = d.size
    for st in d.strokes:
        assert st.points.min() >= 0
        assert st.points[:, 0].max() <= W - 1 and st.points[:, 1].max() <= H - 1


def test_scene_random_invariants():
    d = synth.scene_random(np.random.default_rng(3), (800, 600), 12)
    assert len(d.strokes) == 12
    _inside(d)
    assert all(LineString(s.points).is_simple for s in d.strokes)


def test_scene_matisse_like_invariants():
    for seed in range(4):
        d = synth.scene_matisse_like(np.random.default_rng(seed), (1000, 800))
        assert 3 <= len(d.strokes) <= 6
        _inside(d)
        assert all(s.width is not None for s in d.strokes)
        assert all(LineString(s.points).is_simple for s in d.strokes)
        for i, j, gap in d.meta["near_pairs"]:
            dist = _line(d.strokes[i]).distance(_line(d.strokes[j]))
            assert 0.8 * gap <= dist <= gap + 1.0


def test_scenes_deterministic():
    a = synth.scene_matisse_like(np.random.default_rng(5), 700)
    b = synth.scene_matisse_like(np.random.default_rng(5), 700)
    assert all(np.array_equal(x.points, y.points) for x, y in zip(a.strokes, b.strokes))


# ---------------------------------------------------------------- width

def test_with_width_taper_pool_and_purity():
    st = synth.random_clothoid_stroke(np.random.default_rng(0), 500.0, 3, 0.005)
    before = st.points.copy()
    w = synth.with_width(st, 6.0, np.random.default_rng(1), taper=True, pool=True)
    assert np.array_equal(st.points, before) and st.width is None
    assert "width_model" not in st.meta
    n = len(w)
    assert w.width.shape == (n,)
    assert w.width[-1] < 0.5 * np.median(w.width)       # taper
    assert w.width[0] > 1.3 * np.median(w.width)        # pool
    assert 5.0 < np.median(w.width) < 7.0


# ---------------------------------------------------------------- render

@pytest.fixture(scope="module")
def random_scene():
    return synth.scene_random(np.random.default_rng(11), (400, 300), 6)


def test_render_shape_dtype_range(random_scene):
    img = synth.render(random_scene)
    assert img.shape == (300, 400) and img.dtype == np.uint8
    assert img.min() < 40 and img.max() > 240


def test_render_deterministic_and_seeded(random_scene):
    a = synth.render(random_scene, seed=3, width_jitter=0.2, ink_noise=0.2)
    b = synth.render(random_scene, seed=3, width_jitter=0.2, ink_noise=0.2)
    c = synth.render(random_scene, seed=4, width_jitter=0.2, ink_noise=0.2)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_render_ink_on_strokes_paper_elsewhere(random_scene):
    img = synth.render(random_scene, line_width=4.0)
    for st in random_scene.strokes:
        p = st.points[::10]
        vals = img[np.round(p[:, 1]).astype(int), np.round(p[:, 0]).astype(int)]
        assert np.all(vals < 90), vals.max()
    clean = synth.render(random_scene, paper_noise=0.0)
    far = clean == 255
    assert far.mean() > 0.5
    assert img[far].min() > 180 and img[far].mean() > 240


def test_render_closed_stroke_draws_closing_segment():
    pts = np.array([[50, 50], [150, 50], [150, 150], [50, 150]], float)
    d = Drawing([Stroke(pts, closed=True)], size=(200, 200))
    img = synth.render(d, paper_noise=0.0)
    assert img[100, 50] < 60       # midpoint of the closing edge (50,150)->(50,50)
    assert img[100, 100] == 255


def test_render_uses_stroke_width():
    st = Stroke(np.column_stack([np.linspace(20, 180, 200), np.full(200, 50.0)]))
    thin = Drawing([Stroke(st.points, width=np.full(200, 3.0))], size=(200, 100))
    fat = Drawing([Stroke(st.points, width=np.full(200, 12.0))], size=(200, 100))
    ink = lambda d, **k: (synth.render(d, paper_noise=0.0, **k) < 128).sum(axis=0)[100]  # noqa: E731
    assert abs(ink(thin) - 3) <= 1 and abs(ink(fat) - 12) <= 1
    assert abs(ink(fat, use_stroke_width=False, line_width=5.0) - 5) <= 1


def test_render_speed_2000px_20_strokes():
    d = synth.scene_random(np.random.default_rng(0), (2000, 2000), 20)
    t = time.perf_counter()
    synth.render(d, width_jitter=0.2, ink_noise=0.1)
    assert time.perf_counter() - t < 8.0  # ~0.3 s idle; slack for a loaded machine
