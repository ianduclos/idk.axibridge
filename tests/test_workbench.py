"""Generation workbench: stateless preview + global scrap library."""

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


RECIPE = {"module": "polygon", "params": {"sides": 6, "radius": 25}}


def test_preview_is_stateless(client):
    before = client.get("/api/project").json()
    r = client.post("/api/workbench/preview", json=RECIPE)
    assert r.status_code == 200
    body = r.json()
    assert body["lines"] and body["points"] > 0
    # no layer, no undo checkpoint, nothing touched
    assert client.get("/api/project").json() == before


def test_preview_applies_effect_stack(client):
    plain = client.post("/api/workbench/preview", json=RECIPE).json()
    shaped = client.post("/api/workbench/preview", json={
        **RECIPE,
        "effects": [{"effect": "freehand", "params": {"tremor": 1.5}}],
    }).json()
    assert plain["lines"] != shaped["lines"]
    # disabled steps are skipped
    disabled = client.post("/api/workbench/preview", json={
        **RECIPE,
        "effects": [{"effect": "freehand", "enabled": False, "params": {}}],
    }).json()
    assert disabled["lines"] == plain["lines"]


def test_preview_errors(client):
    assert client.post("/api/workbench/preview",
                       json={"module": "nope"}).status_code == 404
    assert client.post("/api/workbench/preview", json={
        **RECIPE, "effects": [{"effect": "nope"}]}).status_code == 404
    assert client.post("/api/workbench/preview", json={
        "module": "polygon", "params": {"sides": -3}}).status_code == 400


def test_scrap_roundtrip(client):
    saved = client.post("/api/scraps", json={**RECIPE, "name": "hexes"}).json()
    assert saved["name"] == "hexes" and saved["points"] > 0

    listed = client.get("/api/scraps").json()["scraps"]
    assert [s["id"] for s in listed] == [saved["id"]]
    assert listed[0]["module"] == "polygon"  # recipe kept as metadata

    svg = client.get(f"/api/scraps/{saved['id']}.svg")
    assert svg.status_code == 200 and "<svg" in svg.text

    # import inserts the frozen SVG as baked project layers (checkpointed)
    r = client.post(f"/api/scraps/{saved['id']}/import")
    assert r.status_code == 200
    layers = client.get("/api/project").json()["layers"]
    assert len(layers) == 1 and layers[0]["source"]["type"] == "svg"
    assert layers[0]["name"] == "hexes"  # library name beats SVG round-trip ids
    assert client.post("/api/undo").status_code == 200
    assert client.get("/api/project").json()["layers"] == []

    # the scrap outlives the project — it's a machine-level library
    client.delete(f"/api/scraps/{saved['id']}")
    assert client.get("/api/scraps").json()["scraps"] == []
    assert client.get(f"/api/scraps/{saved['id']}.svg").status_code == 404
    assert client.post(f"/api/scraps/{saved['id']}/import").status_code == 404


def test_scrap_save_validates(client):
    assert client.post("/api/scraps", json={"module": "nope"}).status_code == 404


DRAWING = {"module": "drawing", "params": {},
           "paths": [[[50.0, 50.0], [80.0, 52.0], [110.0, 48.0]],
                     [[60.0, 90.0], [100.0, 90.0]]]}


def test_drawing_preview_uses_paths_verbatim(client):
    body = client.post("/api/workbench/preview", json=DRAWING).json()
    assert body["lines"] == [p for p in DRAWING["paths"]]
    assert body["width"] == 300.0 and body["height"] == 218.0
    # the effect stack still applies on top of a drawing base
    shaped = client.post("/api/workbench/preview", json={
        **DRAWING, "effects": [{"effect": "freehand", "params": {"tremor": 1.5}}],
    }).json()
    assert shaped["lines"] != body["lines"]


def test_drawing_bounds_and_budget_enforced(client):
    off_bed = {**DRAWING, "paths": [[[301.0, 10.0], [305.0, 10.0]]]}
    assert client.post("/api/workbench/preview", json=off_bed).status_code == 400
    dense = {**DRAWING, "paths": [[[float(i % 290), 10.0] for i in range(50_001)]]}
    assert client.post("/api/workbench/preview", json=dense).status_code == 400
    # module "drawing" without paths is not a generator
    assert client.post("/api/workbench/preview",
                       json={"module": "drawing"}).status_code == 404


def test_drawing_scrap_freezes_given_geometry(client):
    saved = client.post("/api/scraps", json={**DRAWING, "name": "doodle"}).json()
    assert saved["module"] == "drawing" and saved["params"] == {}
    assert client.get(f"/api/scraps/{saved['id']}.svg").status_code == 200
    r = client.post(f"/api/scraps/{saved['id']}/import")
    assert r.status_code == 200
    layers = client.get("/api/project").json()["layers"]
    assert len(layers) == 1 and layers[0]["source"]["type"] == "svg"
    assert layers[0]["name"] == "doodle"
    # the frozen geometry round-trips: resolved layer ≈ the drawn mm points
    res = client.get("/api/compose/resolved").json()
    [layer] = res["layers"]
    got = sorted((p["points"] for p in layer["paths"]), key=len, reverse=True)
    want = sorted(DRAWING["paths"], key=len, reverse=True)
    assert len(got) == len(want)
    for gp, wp in zip(got, want):
        assert len(gp) == len(wp)
        for (gx, gy), (wx, wy) in zip(gp, wp):
            assert abs(gx - wx) < 0.05 and abs(gy - wy) < 0.05
