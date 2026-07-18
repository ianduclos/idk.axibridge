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
