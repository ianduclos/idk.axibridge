"""Drawing (pointer) source: docs/plans/draw-mode.md Part 1 contract."""

import pytest

from axibridge.registry import get_source, sources
from axibridge.session import session


def _gen(**params):
    src = get_source("drawing")
    return src.generate(src.Params(**params))


def _stroke(n=5, x0=10.0, y0=10.0, dx=1.0, dy=0.0):
    return [[x0 + i * dx, y0 + i * dy, i * 0.1] for i in range(n)]


def test_registered():
    assert "drawing" in sources()
    m = get_source("drawing")
    assert m.label == "Drawing (pointer)"


def test_empty_strokes_raises():
    with pytest.raises(ValueError, match="draw a stroke first"):
        _gen(strokes=[])


def test_deterministic():
    strokes = [_stroke(20)]
    d1 = _gen(strokes=strokes, resample_mm=1.0, smooth=2)
    d2 = _gen(strokes=strokes, resample_mm=1.0, smooth=2)
    assert [p.points for p in d1.layers[0].paths] == [p.points for p in d2.layers[0].paths]


def test_point_cap_raises():
    # one dense stroke over the 50k cap
    huge = [[float(i % 300), float(i % 218), 0.0] for i in range(50_001)]
    with pytest.raises(ValueError, match="too dense"):
        _gen(strokes=[huge])


def test_off_bed_points_clamped_not_raised():
    stroke = [[-10.0, -5.0, 0.0], [310.0, 300.0, 1.0]]
    doc = _gen(strokes=[stroke], resample_mm=0.2, smooth=0)
    pts = doc.layers[0].paths[0].points
    for x, y in pts:
        assert 0.0 <= x <= 300.0
        assert 0.0 <= y <= 218.0
    # endpoints clamp to the exact bed corners
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (300.0, 218.0)


def test_resample_changes_vertex_count_but_not_endpoints():
    stroke = _stroke(50, x0=10, y0=10, dx=0.5, dy=0.0)  # ~24.5mm straight line
    coarse = _gen(strokes=[stroke], resample_mm=5.0, smooth=0).layers[0].paths[0].points
    fine = _gen(strokes=[stroke], resample_mm=0.2, smooth=0).layers[0].paths[0].points
    assert len(coarse) != len(fine)
    assert coarse[0] == fine[0] == (10.0, 10.0)
    expected_end = (10.0 + 49 * 0.5, 10.0)
    assert coarse[-1] == pytest.approx(expected_end)
    assert fine[-1] == pytest.approx(expected_end)


def test_two_strokes_two_paths():
    doc = _gen(strokes=[_stroke(4), _stroke(4, x0=50, y0=50)])
    assert len(doc.layers[0].paths) == 2


def test_paths_open_and_unfilled():
    doc = _gen(strokes=[_stroke(6)])
    for p in doc.layers[0].paths:
        assert p.filled is False
        assert p.points[0] != p.points[-1] or len(p.points) == 1


def test_generate_bounds_reject_invalid_params():
    src = get_source("drawing")
    with pytest.raises(Exception):
        src.Params(strokes=[_stroke(3)], resample_mm=0.01)  # below ge=0.2
    with pytest.raises(Exception):
        src.Params(strokes=[_stroke(3)], smooth=5)  # above le=4


def test_regenerate_round_trip():
    layer = session.add_generated_layer("drawing", {"strokes": [_stroke(8)]})
    assert layer.source.generator == "drawing"
    n1 = len(session.source_geometry[layer.id])
    updated = session.regenerate_layer(
        layer.id, {"strokes": [_stroke(8), _stroke(6, x0=100, y0=100)]}
    )
    n2 = len(session.source_geometry[updated.id])
    assert n2 == n1 + 1


# -- velocity_tube (docs/plans/response-brushes.md Part 2) -----------------


def _dwell_then_flick_stroke(x0=20.0, y0=100.0):
    """A stroke that lingers (small dx per dt) then flicks away (large dx
    per dt) — the brief's eye-check gesture, synthesized with real timing."""
    pts = []
    t = 0.0
    x, y = x0, y0
    for _ in range(30):  # slow: little travel per big time step
        x += 0.3
        t += 0.08
        pts.append([x, y, t])
    for _ in range(30):  # fast: lots of travel per tiny time step
        x += 3.0
        t += 0.01
        pts.append([x, y, t])
    return pts


def test_centerline_byte_identical_when_render_default():
    # extending DrawingParams must not perturb the existing centerline path
    stroke = _stroke(20)
    a = _gen(strokes=[stroke], resample_mm=1.0, smooth=2)
    b = _gen(strokes=[stroke], resample_mm=1.0, smooth=2, render="centerline")
    assert [p.points for p in a.layers[0].paths] == [p.points for p in b.layers[0].paths]


def test_velocity_tube_outline_closed():
    doc = _gen(strokes=[_dwell_then_flick_stroke()], render="velocity_tube", resample_mm=0.5)
    outlines = [p for p in doc.layers[0].paths if p.points[0] == p.points[-1]]
    assert len(outlines) == 1
    assert outlines[0].filled is False


def test_velocity_tube_keep_centerline_toggle():
    with_center = _gen(strokes=[_dwell_then_flick_stroke()], render="velocity_tube",
                        resample_mm=0.5, keep_centerline=True)
    without_center = _gen(strokes=[_dwell_then_flick_stroke()], render="velocity_tube",
                           resample_mm=0.5, keep_centerline=False)
    assert len(with_center.layers[0].paths) == len(without_center.layers[0].paths) + 1
    open_paths = [p for p in without_center.layers[0].paths if p.points[0] != p.points[-1]]
    assert open_paths == []  # only the closed outline remains


def test_velocity_tube_dwell_wider_than_flick():
    # the synthesized stroke's slow phase only spans x in [20, 29] (30 tiny
    # 0.3mm steps at 0.08s each); the fast phase spans x in [29, 119] (30
    # 3mm steps at 0.01s each) — probe well inside each phase, not by
    # percentage of the outline's bounding box (which is skewed by the end
    # caps bulging past the data extents).
    doc = _gen(strokes=[_dwell_then_flick_stroke()], render="velocity_tube",
                resample_mm=0.5, width_min=1.0, width_max=6.0, speed_smooth_mm=2.0)
    outline = [p for p in doc.layers[0].paths if p.points[0] == p.points[-1]][0]

    def width_near_x(target_x):
        ys = [y for x, y in outline.points if abs(x - target_x) < 1.0]
        return (max(ys) - min(ys)) if ys else 0.0

    assert width_near_x(24.0) > width_near_x(80.0)


def test_velocity_tube_deterministic():
    stroke = _dwell_then_flick_stroke()
    a = _gen(strokes=[stroke], render="velocity_tube", resample_mm=0.5)
    b = _gen(strokes=[stroke], render="velocity_tube", resample_mm=0.5)
    assert [p.points for p in a.layers[0].paths] == [p.points for p in b.layers[0].paths]


def test_velocity_tube_equal_timestamps_uses_midpoint_width():
    flat_t = [[x, 100.0, 0.0] for x, _y, _t in _dwell_then_flick_stroke()]
    doc = _gen(strokes=[flat_t], render="velocity_tube", resample_mm=0.5,
                width_min=1.0, width_max=7.0, keep_centerline=False)
    outline = doc.layers[0].paths[0]
    ys = [y for _x, y in outline.points]
    # constant mid-width (4.0mm) everywhere -> spread stays close to that,
    # not swinging out toward width_max or collapsing toward width_min
    assert 3.0 < (max(ys) - min(ys)) < 5.5


def test_velocity_tube_two_point_stroke_does_not_crash():
    doc = _gen(strokes=[[[10.0, 10.0, 0.0], [20.0, 10.0, 1.0]]],
                render="velocity_tube", resample_mm=0.5)
    assert len(doc.layers[0].paths) >= 1


def test_velocity_tube_params_bounded():
    src = get_source("drawing")
    with pytest.raises(Exception):
        src.Params(strokes=[], width_min=0.1)  # below ge=0.3
    with pytest.raises(Exception):
        src.Params(strokes=[], width_max=30.0)  # above le=25
    with pytest.raises(Exception):
        src.Params(strokes=[], speed_smooth_mm=0.0)  # below ge=1.0
