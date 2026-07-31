"""Shape (add/subtract) source: the tool-agnostic boolean-mass layer.

Same test philosophy as test_brush_source.py: pin the chronological fold
against the deliberately-wrong batched implementation, and pin the op
geometries (pen silhouette implicit close, brush stamp) plus the empty
layer contract."""

import pytest
from shapely.geometry import Point, Polygon

from axibridge.registry import get_source, sources


def _gen(**params):
    src = get_source("shape")
    return src.generate(src.Params(**params))


def _paths(doc):
    return [p for layer in doc.layers for p in layer.paths]


def _region(doc):
    """The emitted rings reassembled into a shapely region: exteriors minus
    whatever their nesting holes cover (rings are unordered; a hole is any
    ring strictly inside another)."""
    rings = [Polygon(p.points) for p in _paths(doc)]
    out = []
    for i, r in enumerate(rings):
        if any(i != j and o.contains(r) for j, o in enumerate(rings)):
            continue  # a hole, subtracted via its parent below
        holes = [o for j, o in enumerate(rings) if i != j and r.contains(o)]
        acc = r
        for h in holes:
            acc = acc.difference(h)
        out.append(acc)
    return out


def _area(doc):
    return sum(r.area for r in _region(doc))


def _pen_square(x0=40.0, y0=40.0, side=60.0, mode="add", closed=True):
    return {"kind": "pen", "mode": mode, "closed": closed,
            "anchors": [{"x": x0, "y": y0},
                        {"x": x0 + side, "y": y0},
                        {"x": x0 + side, "y": y0 + side},
                        {"x": x0, "y": y0 + side}]}


def _brush_dab(x, y, radius=10.0, mode="add"):
    return {"kind": "brush", "mode": mode, "radius": radius,
            "points": [[x, y, 0.0]]}


def test_registered():
    assert "shape" in sources()
    assert get_source("shape").label == "Shape (add/subtract)"


def test_empty_ops_is_an_empty_doc():
    doc = _gen(ops=[])
    assert doc.layers == [] or all(not layer.paths for layer in doc.layers)


def test_pen_op_implicit_close_makes_a_silhouette():
    # closed=False, yet the region is the closed square — implicit close
    doc = _gen(ops=[_pen_square(closed=False)])
    assert _area(doc) == pytest.approx(60.0 * 60.0, rel=0.02)
    assert all(p.filled and p.points[0] == p.points[-1] for p in _paths(doc))


def test_brush_op_dab_is_a_disc():
    doc = _gen(ops=[_brush_dab(100.0, 100.0, radius=10.0)])
    assert _area(doc) == pytest.approx(100.0 * 3.14159, rel=0.05)


def test_subtract_bites_a_hole():
    doc = _gen(ops=[_pen_square(), _brush_dab(70.0, 70.0, radius=8.0, mode="subtract")])
    assert _area(doc) == pytest.approx(3600.0 - 64.0 * 3.14159, rel=0.05)
    assert not _region(doc)[0].contains(Point(70, 70))


def test_subtract_before_any_add_is_a_noop():
    doc = _gen(ops=[_brush_dab(70.0, 70.0, mode="subtract"), _pen_square()])
    assert _area(doc) == pytest.approx(3600.0, rel=0.02)


def test_fold_is_chronological_not_batched():
    # add square, bite a disc off its centre, dab the disc back — the repaint
    # must survive. A batched "union adds, subtract subtracts" would erase it.
    ops = [_pen_square(),
           _brush_dab(70.0, 70.0, radius=12.0, mode="subtract"),
           _brush_dab(70.0, 70.0, radius=12.0, mode="add")]
    assert _area(_gen(ops=ops)) == pytest.approx(3600.0, rel=0.02)


def test_mixed_pen_and_brush_adds_merge():
    # square spans x 40-100; the dab (centre 110, r 20) laps over its right edge
    doc = _gen(ops=[_pen_square(), _brush_dab(110.0, 70.0, radius=20.0)])
    region = _region(doc)
    assert len(region) == 1  # overlapping masses fold into one silhouette
    assert region[0].contains(Point(60, 60)) and region[0].contains(Point(110, 70))


def test_deterministic():
    ops = [_pen_square(), _brush_dab(70.0, 70.0, radius=9.0, mode="subtract"),
           {"kind": "brush", "points": [[20, 200, 0], [60, 180, 1]], "radius": 6.0}]
    a, b = _gen(ops=ops), _gen(ops=ops)
    assert [p.points for p in _paths(a)] == [p.points for p in _paths(b)]


def test_degenerate_ops_are_skipped_not_fatal():
    doc = _gen(ops=[{"kind": "pen", "anchors": [{"x": 10, "y": 10}]},  # <3 points
                    {"kind": "brush", "points": [], "radius": 5.0},
                    _pen_square()])
    assert _area(doc) == pytest.approx(3600.0, rel=0.02)


def test_params_not_mutated():
    src = get_source("shape")
    params = src.Params(ops=[_pen_square()])
    before = params.model_dump()
    src.generate(params)
    assert params.model_dump() == before
