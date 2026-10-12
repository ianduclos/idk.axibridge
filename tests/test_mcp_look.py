import io
import json

from PIL import Image

from _mcp_harness import axb, call, http, images, srv, targets, text  # noqa: F401

POLY = {"module": "polygon", "params": {"sides": 5, "radius": 20}}


def test_see_returns_a_png_of_the_canvas_with_a_caption(srv, axb):
    with http(axb) as h:
        h.post("/api/layers/generate", json=POLY)
    r = call(srv, "see", {"size": 600})
    assert not r.is_error, text(r)
    [png] = images(r)
    img = Image.open(io.BytesIO(png))
    assert max(img.size) == 600
    assert "1 layer" in text(r)


def test_see_follows_the_project_view(srv, axb):
    with http(axb) as h:
        h.put("/api/project", json={"view": "portrait"})
    [png] = images(call(srv, "see", {"size": 600}))
    w, h_ = Image.open(io.BytesIO(png)).size
    assert h_ > w
    [png] = images(call(srv, "see", {"size": 600, "orient": "machine"}))
    w, h_ = Image.open(io.BytesIO(png)).size
    assert w > h_


def test_see_rejects_out_of_range_sizes(srv):
    assert call(srv, "see", {"size": 50}).is_error


def test_try_generator_returns_one_contact_sheet_and_leaves_the_project_alone(srv, axb):
    r = call(srv, "try_generator", {"module": "polygon",
                                    "param_sets": [{"sides": 3}, {"sides": 8}], "tile": 200})
    assert not r.is_error, text(r)
    [png] = images(r)
    assert Image.open(io.BytesIO(png)).size[0] == 400
    with http(axb) as h:
        assert h.get("/api/project").json()["layers"] == []


def test_try_generator_reports_a_bad_set_without_losing_the_good_ones(srv):
    r = call(srv, "try_generator", {"module": "polygon",
                                    "param_sets": [{"sides": 3}, {"sides": "many"}], "tile": 200})
    assert not r.is_error
    assert "2: error" in text(r)
    assert len(images(r)) == 1


def test_try_effects_previews_chains_on_an_existing_layer(srv, axb):
    with http(axb) as h:
        lid = h.post("/api/layers/generate", json=POLY).json()["id"]
    r = call(srv, "try_effects", {"layer_id": lid, "tile": 200, "chains": [
        [], [{"effect": "freehand", "params": {}}]]})
    assert not r.is_error, text(r)
    assert len(images(r)) == 1
    with http(axb) as h:
        assert h.get(f"/api/project").json()["layers"][0]["effects"] == []


def test_modules_lists_and_filters(srv):
    out = text(call(srv, "modules", {"kind": "sources", "query": "polygon"}))
    assert "polygon" in out
    assert "freehand" not in out


def test_module_schema_returns_schema_and_defaults(srv):
    data = json.loads(text(call(srv, "module_schema", {"module_id": "polygon"})))
    assert data["kind"] == "sources"
    assert "sides" in data["schema"]["properties"]
    assert "sides" in data["defaults"]


def test_module_schema_names_unknown_modules(srv):
    r = call(srv, "module_schema", {"module_id": "nope"})
    assert r.is_error and "nope" in text(r)
