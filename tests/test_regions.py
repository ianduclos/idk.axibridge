"""Region layers ("affects below"): silhouette masks + effect stack on lower layers."""

import math

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.compose import (
    Affine, CanvasLayer, EffectStep, LayerSource, Project, resolve_project,
)
from axibridge.model import Path


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _line_layer():
    return CanvasLayer(name="line", source=LayerSource(type="svg", file="x")), \
        [Path(points=[(10.0, 50.0), (190.0, 50.0)], filled=False)]


def _region_layer(x0=80.0, y0=30.0, side=40.0, effects=None):
    sq = [(0.0, 0.0), (side, 0.0), (side, side), (0.0, side), (0.0, 0.0)]
    layer = CanvasLayer(
        name="rgn", region=True,
        source=LayerSource(type="svg", file="x"),
        transform=Affine(e=x0, f=y0),
        effects=effects or [],
    )
    return layer, [Path(points=sq, filled=True)]


def _resolve(layers_and_src):
    project = Project(name="t", layers=[l for l, _ in layers_and_src])
    geo = {l.id: src for l, src in layers_and_src}
    return resolve_project(project, geo, pens={}), project


def test_region_splits_and_effects_inside_only():
    line, line_src = _line_layer()
    rgn, rgn_src = _region_layer(effects=[EffectStep(effect="bitmap", params={"cell": 4.0})])
    resolved, _ = _resolve([(line, line_src), (rgn, rgn_src)])

    assert resolved[rgn.id] == []  # regions are never drawn
    pieces = resolved[line.id]
    assert len(pieces) > 2  # outside-left, outside-right, bitmapped inside
    inside = [p for p in pieces if p.filled]      # bitmap emits filled blocks
    outside = [p for p in pieces if not p.filled]
    assert inside, "the segment inside the region was bitmapped"
    for p in outside:  # untouched halves stay exactly on the original line
        assert all(abs(y - 50.0) < 1e-6 for _, y in p.points)
        for x, _ in p.points:
            assert x <= 80.0 + 1e-6 or x >= 120.0 - 1e-6
    for p in inside:   # bitmap output stays within the region (one cell of slack)
        for x, y in p.points:
            assert 80.0 - 4.0 <= x <= 120.0 + 4.0 and 30.0 - 4.0 <= y <= 70.0 + 4.0


def test_region_with_no_effects_preserves_geometry():
    line, line_src = _line_layer()
    rgn, rgn_src = _region_layer()
    resolved, _ = _resolve([(line, line_src), (rgn, rgn_src)])
    total = sum(p.length() for p in resolved[line.id])
    assert math.isclose(total, 180.0, abs_tol=0.01)  # split, not altered


def test_region_only_affects_layers_below():
    rgn, rgn_src = _region_layer(effects=[EffectStep(effect="bitmap", params={"cell": 4.0})])
    line, line_src = _line_layer()
    # region at the BOTTOM: the line above it must be untouched
    resolved, _ = _resolve([(rgn, rgn_src), (line, line_src)])
    assert [p.points for p in resolved[line.id]] == [line_src[0].points]


def test_hidden_region_is_inert():
    line, line_src = _line_layer()
    rgn, rgn_src = _region_layer(effects=[EffectStep(effect="bitmap", params={"cell": 4.0})])
    rgn.visible = False
    resolved, _ = _resolve([(line, line_src), (rgn, rgn_src)])
    assert [p.points for p in resolved[line.id]] == [line_src[0].points]


def test_region_output_still_occludes():
    # region bitmaps a filled square; an occluder above must still mask it
    base, base_src = _region_layer(x0=40, y0=40)  # reuse builder for a filled square…
    base.region = False                            # …but as a normal drawn layer
    rgn, rgn_src = _region_layer(x0=30, y0=30, side=60.0,
                                 effects=[EffectStep(effect="bitmap", params={"cell": 5.0})])
    occ, occ_src = _region_layer(x0=50, y0=50)
    occ.region = False
    occ.occluder = True
    resolved, _ = _resolve([(base, base_src), (rgn, rgn_src), (occ, occ_src)])
    # every surviving point of the bitmapped base stays clear of the occluder's interior
    for p in resolved[base.id]:
        for x, y in p.points:
            assert not (50.0 + 1e-6 < x < 90.0 - 1e-6 and 50.0 + 1e-6 < y < 90.0 - 1e-6)


def test_region_via_api_undo_and_display(client):
    line = client.post("/api/layers/generate",
                       json={"module": "polygon", "params": {"sides": 4, "radius": 40}}).json()
    rgn = client.post("/api/layers/generate",
                      json={"module": "rectangle", "params": {}}).json()
    r = client.patch(f"/api/layers/{rgn['id']}",
                     json={"region": True,
                           "effects": [{"effect": "freehand", "params": {"tremor": 1.0}}]})
    assert r.status_code == 200 and r.json()["region"] is True

    res = client.get("/api/compose/resolved").json()
    by_id = {l["id"]: l for l in res["layers"]}
    assert by_id[rgn["id"]]["region"] is True
    assert by_id[rgn["id"]]["paths"], "canvas still gets the silhouette to drag"
    assert by_id[rgn["id"]]["stats"]["paths"] == 0, "but nothing plottable"
    assert by_id[line["id"]]["paths"]

    # the plot document never contains the region layer
    doc = client.get("/api/doc/all/svg")
    assert doc.status_code == 200

    # undo unwinds the region toggle
    client.post("/api/undo")
    res2 = client.get("/api/compose/resolved").json()
    assert {l["id"]: l for l in res2["layers"]}[rgn["id"]]["region"] is False
