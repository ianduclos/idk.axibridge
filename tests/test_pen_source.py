"""Pen (Bezier anchors) source: docs/plans/pen-brush-tools.md Part 1 contract."""

import pytest

from axibridge.registry import get_source, sources


def _gen(**params):
    src = get_source("pen")
    return src.generate(src.Params(**params))


def _corner(x, y):
    return {"x": x, "y": y}


def _smooth(x, y, out_handle, in_handle=None):
    return {
        "x": x, "y": y,
        "out_handle": out_handle,
        "in_handle": in_handle if in_handle is not None else (-out_handle[0], -out_handle[1]),
    }


def test_registered():
    assert "pen" in sources()
    m = get_source("pen")
    assert m.label == "Pen (anchors)"


def test_empty_subpaths_raises():
    with pytest.raises(ValueError, match="draw a path first"):
        _gen(subpaths=[])


def test_straight_segment_two_corner_anchors():
    doc = _gen(subpaths=[{"anchors": [_corner(0, 0), _corner(10, 0)], "closed": False}])
    path = doc.layers[0].paths[0]
    assert path.points == [(0.0, 0.0), (10.0, 0.0)]
    assert path.filled is False


def test_collinear_handles_flatten_near_straight():
    # handles pointing straight along the chord: the "curve" degenerates to
    # a straight line, so the flattened polyline shouldn't deviate from it.
    doc = _gen(subpaths=[{
        "anchors": [
            {"x": 0.0, "y": 0.0, "out_handle": (3.0, 0.0)},
            {"x": 10.0, "y": 0.0, "in_handle": (-3.0, 0.0)},
        ],
        "closed": False,
    }])
    pts = doc.layers[0].paths[0].points
    for x, y in pts:
        assert abs(y) < 1e-6


def test_symmetric_smooth_anchor_produces_curve():
    # a smooth anchor at the midpoint between two corners bows the curve;
    # sample the middle of the flattened output and confirm real deviation
    # from the straight chord (not ~0, not some wild multiple of handle len).
    doc = _gen(subpaths=[{
        "anchors": [
            _corner(0, 0),
            _smooth(10, 5, out_handle=(4.0, 0.0)),
            _corner(20, 0),
        ],
        "closed": False,
    }], flatten_tol=0.05)
    pts = doc.layers[0].paths[0].points
    mid = pts[len(pts) // 2]
    # chord from (0,0) to (20,0) is the x-axis; the curve should bow toward
    # y=5 (the smooth anchor) by a real amount, bounded by the anchor's own y.
    assert 1.0 < mid[1] <= 5.0


def test_closed_output_exact_closure_and_filled():
    doc = _gen(subpaths=[{
        "anchors": [_corner(0, 0), _corner(10, 0), _corner(10, 10), _corner(0, 10)],
        "closed": True,
    }])
    path = doc.layers[0].paths[0]
    assert path.points[0] == path.points[-1]
    assert path.filled is True


def test_open_output_not_filled_no_wrap():
    doc = _gen(subpaths=[{
        "anchors": [_corner(0, 0), _corner(10, 0), _corner(10, 10)],
        "closed": False,
    }])
    path = doc.layers[0].paths[0]
    assert path.filled is False
    assert path.points[0] != path.points[-1]
    assert path.points == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]


def test_deterministic():
    subpaths = [{
        "anchors": [
            _corner(0, 0),
            _smooth(10, 5, out_handle=(4.0, 2.0)),
            _corner(20, 0),
        ],
        "closed": False,
    }]
    d1 = _gen(subpaths=subpaths)
    d2 = _gen(subpaths=subpaths)
    assert [p.points for p in d1.layers[0].paths] == [p.points for p in d2.layers[0].paths]


def test_flatten_tol_bounds_point_density():
    subpaths = [{
        "anchors": [
            _corner(0, 0),
            _smooth(10, 8, out_handle=(5.0, 0.0)),
            _corner(20, 0),
        ],
        "closed": False,
    }]
    fine = _gen(subpaths=subpaths, flatten_tol=0.05)
    coarse = _gen(subpaths=subpaths, flatten_tol=1.5)
    assert len(fine.layers[0].paths[0].points) > len(coarse.layers[0].paths[0].points)


def test_absurd_anchor_count_raises():
    huge = [_corner(float(i % 300), float(i % 218)) for i in range(2001)]
    with pytest.raises(ValueError, match="too dense"):
        _gen(subpaths=[{"anchors": huge, "closed": False}])


def test_degenerate_coincident_anchors_does_not_hang():
    doc = _gen(subpaths=[{
        "anchors": [_corner(5, 5), _corner(5, 5)],
        "closed": False,
    }])
    path = doc.layers[0].paths[0]
    assert all(pt == (5.0, 5.0) for pt in path.points)


def test_bed_clamp_on_anchor_positions():
    doc = _gen(subpaths=[{
        "anchors": [_corner(-50, -50), _corner(1000, 1000)],
        "closed": False,
    }])
    pts = doc.layers[0].paths[0].points
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (300.0, 218.0)
