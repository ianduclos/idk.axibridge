import numpy as np

from gesture.core import Drawing, Stroke
from gesture.curvature import kappa_s, resample, turning_angles


def circle(r, n=400):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([r * np.cos(t), r * np.sin(t)])


def test_circle_curvature_is_one_over_r():
    for r in (20.0, 80.0, 300.0):
        _, k, _ = kappa_s(circle(r), sigma=r / 20, closed=True)
        assert np.allclose(np.abs(k), 1 / r, rtol=0.02)


def test_straight_line_has_zero_curvature():
    pts = np.column_stack([np.linspace(0, 100, 50), np.linspace(0, 30, 50)])
    _, k, _ = kappa_s(pts, sigma=3.0)
    assert np.max(np.abs(k)) < 1e-9


def test_resample_spacing_is_uniform():
    pts = np.array([[0, 0], [10, 0], [10, 7], [3, 7]], float)
    r = resample(pts, 0.5)
    d = np.linalg.norm(np.diff(r, axis=0), axis=1)
    assert np.allclose(d, d.mean(), rtol=1e-6) or np.ptp(d) < 0.5


def test_inputs_not_mutated():
    pts = circle(10.0)
    before = pts.copy()
    kappa_s(pts, sigma=1.0, closed=True)
    turning_angles(pts, closed=True)
    assert np.array_equal(pts, before)


def test_drawing_round_trip(tmp_path):
    d = Drawing([Stroke(circle(5.0), width=np.full(400, 2.0), closed=True, meta={"k": 1})],
                source="t", size=(100, 100))
    d.save(tmp_path / "d.json")
    e = Drawing.load(tmp_path / "d.json")
    assert e.strokes[0].closed and e.strokes[0].meta == {"k": 1}
    assert np.allclose(e.strokes[0].points, d.strokes[0].points, atol=1e-3)
    assert abs(e.ref_length() - d.ref_length()) < 1e-2


def test_integrate_kappa_round_trips_through_kappa_s():
    from gesture.curvature import integrate_kappa
    breaks = np.array([0, 100, 250, 400.0])
    kap = np.array([0.0, 0.02, 0.02, -0.015])   # clothoid, arc, clothoid
    pts = integrate_kappa(breaks, kap, step=0.5)
    s, k, _ = kappa_s(pts, sigma=2.0, step=0.5)
    truth = np.interp(s, breaks, kap)
    inner = slice(20, -20)  # ends are biased by smoothing
    assert np.max(np.abs(k[inner] - truth[inner])) < 1e-3
