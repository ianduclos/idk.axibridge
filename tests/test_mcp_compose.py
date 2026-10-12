import json

from _mcp_harness import axb, call, http, srv, targets, text  # noqa: F401


def layers(axb):
    with http(axb) as h:
        return h.get("/api/project").json()["layers"]


def test_add_layer_with_name_and_params(srv, axb):
    r = call(srv, "add_layer", {"module": "polygon", "params": {"sides": 4}, "name": "square"})
    assert not r.is_error, text(r)
    [layer] = layers(axb)
    assert layer["name"] == "square"
    assert layer["source"]["params"]["sides"] == 4
    assert layer["id"] in text(r)


def test_edit_layer_patches_fields_and_regenerates_params(srv, axb):
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 5}})
    lid = layers(axb)[0]["id"]
    r = call(srv, "edit_layer", {"layer_id": lid, "patch": {"name": "renamed", "visible": False},
                                 "params": {"sides": 9}})
    assert not r.is_error, text(r)
    [layer] = layers(axb)
    assert layer["name"] == "renamed" and layer["visible"] is False
    assert layer["source"]["params"]["sides"] == 9


def test_edit_layer_needs_something_to_change(srv, axb):
    call(srv, "add_layer", {"module": "polygon", "params": {}})
    assert call(srv, "edit_layer", {"layer_id": layers(axb)[0]["id"]}).is_error


def test_undo_and_redo_report_how_far_they_got(srv, axb):
    call(srv, "add_layer", {"module": "polygon", "params": {}})
    out = text(call(srv, "undo", {"steps": 5}))
    assert "undid 1" in out and "nothing more" in out
    assert layers(axb) == []
    assert "redid 1" in text(call(srv, "redo"))
    assert len(layers(axb)) == 1


def test_delete_and_reorder(srv, axb):
    for n in (3, 4, 5):
        call(srv, "add_layer", {"module": "polygon", "params": {"sides": n}})
    ids = [l["id"] for l in layers(axb)]
    assert not call(srv, "reorder_layers", {"ids": list(reversed(ids))}).is_error
    assert [l["id"] for l in layers(axb)] == list(reversed(ids))
    assert not call(srv, "delete_layers", {"ids": ids[:2]}).is_error
    assert [l["id"] for l in layers(axb)] == [ids[2]]


def test_save_list_new_open_roundtrip(srv, axb):
    call(srv, "add_layer", {"module": "polygon", "params": {}})
    assert not call(srv, "save_project", {"name": "mcp-roundtrip"}).is_error
    assert "mcp-roundtrip" in text(call(srv, "project", {"action": "list"}))
    assert not call(srv, "project", {"action": "new"}).is_error
    assert layers(axb) == []
    assert not call(srv, "project", {"action": "open", "name": "mcp-roundtrip"}).is_error
    assert len(layers(axb)) == 1


def test_open_refuses_to_discard_unsaved_work(srv, axb):
    # Review Focus 3: never a silent discard of Ian's work
    call(srv, "add_layer", {"module": "polygon", "params": {}})
    call(srv, "save_project", {"name": "keep-me"})
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 7}})  # now dirty
    r = call(srv, "project", {"action": "new"})
    assert r.is_error and "unsaved work" in text(r)
    assert len(layers(axb)) == 2


def test_project_status_reports_name_dirty_and_recovery(srv):
    data = json.loads(text(call(srv, "project", {"action": "status"})))
    assert {"name", "dir", "dirty", "recovery"} <= set(data)


def test_open_needs_a_name(srv):
    assert call(srv, "project", {"action": "open"}).is_error
