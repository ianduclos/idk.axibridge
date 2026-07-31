"""Shape-op commit + auto-conversion: session.append_shape_op turns plain
pen/brush layers into shape layers when a gesture needs region semantics,
as one undo step (POST /api/layers/{id}/shape_op)."""

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point, Polygon

from axibridge.app import create_app
from axibridge.session import session


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _pen_layer():
    sub = {"anchors": [{"x": 40.0, "y": 40.0}, {"x": 100.0, "y": 40.0},
                       {"x": 100.0, "y": 100.0}, {"x": 40.0, "y": 100.0}],
           "closed": True}
    return session.add_generated_layer("pen", {"subpaths": [sub]})


def _brush_layer():
    return session.add_generated_layer(
        "brush", {"strokes": [{"points": [[150.0, 70.0, 0.0]], "mode": "paint",
                               "radius": 20.0}]})


def _erase_op(x=70.0, y=70.0, radius=10.0):
    return {"kind": "brush", "mode": "subtract",
            "points": [[x, y, 0.0]], "radius": radius}


def _region_paths(layer):
    return session.source_geometry[layer.id]


def _ink_area(paths):
    """Exterior ring areas minus the holes nested inside them."""
    rings = [Polygon(p.points) for p in paths]
    total = 0.0
    for i, r in enumerate(rings):
        if any(i != j and o.contains(r) for j, o in enumerate(rings)):
            continue
        total += r.area - sum(o.area for j, o in enumerate(rings)
                              if i != j and r.contains(o))
    return total


def test_pen_layer_converts_and_keeps_its_shape():
    layer = _pen_layer()
    before_area = _ink_area(_region_paths(layer))
    session.append_shape_op(layer.id, _erase_op())
    assert layer.source.generator == "shape"
    ops = layer.source.params["ops"]
    assert [o["kind"] for o in ops] == ["pen", "brush"]
    assert ops[0]["mode"] == "add" and ops[1]["mode"] == "subtract"
    # the committed square survives, minus the bite
    after = _ink_area(_region_paths(layer))
    assert after == pytest.approx(before_area - 100 * 3.14159, rel=0.05)
    exterior = Polygon(_region_paths(layer)[0].points)
    assert not exterior.contains(Point(70, 70)) or after < before_area


def test_brush_layer_converts_preserving_paint_and_erase_modes():
    layer = session.add_generated_layer(
        "brush", {"strokes": [
            {"points": [[150.0, 70.0, 0.0]], "mode": "paint", "radius": 20.0},
            {"points": [[145.0, 70.0, 0.0]], "mode": "erase", "radius": 8.0}]})
    session.append_shape_op(layer.id, {"kind": "pen", "mode": "subtract",
                                       "anchors": [{"x": 160.0, "y": 60.0},
                                                   {"x": 175.0, "y": 60.0},
                                                   {"x": 175.0, "y": 80.0},
                                                   {"x": 160.0, "y": 80.0}]})
    modes = [o["mode"] for o in layer.source.params["ops"]]
    assert modes == ["add", "subtract", "subtract"]


def test_shape_layer_appends_without_reconverting():
    layer = _pen_layer()
    session.append_shape_op(layer.id, _erase_op())
    session.append_shape_op(layer.id, _erase_op(x=85.0, y=85.0))
    assert len(layer.source.params["ops"]) == 3
    assert layer.source.generator == "shape"


def test_convert_commit_is_one_undo_step():
    layer = _pen_layer()
    session.append_shape_op(layer.id, _erase_op())
    session.undo()
    restored = session.project.layer(layer.id)  # undo swaps in a deep copy
    assert restored.source.generator == "pen"  # back to the pre-conversion layer
    assert "subpaths" in (restored.source.params or {})


def test_other_generators_refuse():
    layer = session.add_generated_layer("polygon", {"sides": 5, "radius": 12})
    with pytest.raises(RuntimeError, match="shape ops"):
        session.append_shape_op(layer.id, _erase_op())


def test_invalid_op_fails_before_mutating():
    layer = _pen_layer()
    with pytest.raises(Exception):
        session.append_shape_op(layer.id, {"kind": "nonsense"})
    assert layer.source.generator == "pen"  # untouched


def test_api_roundtrip(client):
    layer = _brush_layer()
    r = client.post(f"/api/layers/{layer.id}/shape_op",
                    json={"op": {"kind": "pen", "mode": "subtract",
                                 "anchors": [{"x": 140.0, "y": 60.0},
                                             {"x": 160.0, "y": 60.0},
                                             {"x": 160.0, "y": 80.0},
                                             {"x": 140.0, "y": 80.0}]}})
    assert r.status_code == 200
    assert r.json()["source"]["generator"] == "shape"


def test_api_missing_layer_404(client):
    r = client.post("/api/layers/nope/shape_op", json={"op": _erase_op()})
    assert r.status_code == 404


def test_api_bad_layer_400(client):
    layer = session.add_generated_layer("polygon", {"sides": 5, "radius": 12})
    r = client.post(f"/api/layers/{layer.id}/shape_op", json={"op": _erase_op()})
    assert r.status_code == 400
