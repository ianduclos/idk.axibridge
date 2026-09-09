"""Browser contracts for animation families in the layers dock.

The acceptance harness's ``ui`` fixture creates both a fresh project and a
fresh browser per test.  These tests deliberately seed through the API, then
assert the dock and inspector a person actually uses.
"""

from __future__ import annotations

from test_acceptance_ui import _get, _post, frontend_mode, reload_app, server, ui


def _animated_polygon(page):
    layer = _post(f"{page.base}/api/layers/generate", {
        "module": "polygon", "params": {"sides": 5, "radius": 20},
    })
    master = _post(f"{page.base}/api/layers/{layer['id']}/animate")
    project = _get(f"{page.base}/api/project")
    children = [l for l in project["layers"] if l.get("animation_owner_id") == master["id"]]
    assert len(children) == 2, "Animate must persist explicit keyframe ownership"
    return master, children


def test_owned_keyframes_render_under_their_master_and_hide_occlusion_controls(ui):
    master, children = _animated_polygon(ui)
    reload_app(ui)
    ui.wait_for_function(
        "(id) => document.querySelector(`#layer-list .layer-row[data-layer-id=\"${id}\"]`)",
        arg=master["id"], timeout=10_000)

    rows = ui.locator("#layer-list .layer-row")
    ids = rows.evaluate_all("els => els.map(el => el.dataset.layerId)")
    master_at = ids.index(master["id"])
    assert ids[master_at + 1:master_at + 3] == [
        master["source"]["params"]["a"], master["source"]["params"]["b"],
    ], "keyframes follow the animation's temporal order, not their old flat z-order"
    assert rows.nth(master_at + 1).locator("button.occ").count() == 0
    assert rows.nth(master_at + 2).locator("button.occ").count() == 0

    rows.nth(master_at + 1).locator(".lname").click()
    ui.wait_for_selector("#layer-detail-panel:not([hidden])", timeout=10_000)
    assert ui.locator("#ld-pen").count() == 1, "keyframes still choose their pen"
    assert ui.locator("#ld-occluder, #ld-receives, #ld-margin, .ld-og, .ld-rg").count() == 0
    assert not ui.errors


def test_collapsed_master_keeps_its_owned_keyframes_out_of_the_flat_stack(ui):
    master, children = _animated_polygon(ui)
    other = _post(f"{ui.base}/api/layers/generate", {
        "module": "polygon", "params": {"sides": 3, "radius": 12},
    })
    reload_app(ui)
    master_row = ui.locator(f'#layer-list .layer-row[data-layer-id="{master["id"]}"]')
    master_row.locator(".fold").click()
    ui.wait_for_function(
        "(ids) => ids.every(id => !document.querySelector(`#layer-list .layer-row[data-layer-id=\"${id}\"]`))",
        arg=[child["id"] for child in children], timeout=10_000)
    visible = ui.locator("#layer-list .layer-row").evaluate_all("els => els.map(el => el.dataset.layerId)")
    assert master["id"] in visible and other["id"] in visible
    assert not ui.errors


def test_dragging_a_collapsed_master_moves_its_whole_family(ui):
    master, children = _animated_polygon(ui)
    other = _post(f"{ui.base}/api/layers/generate", {
        "module": "polygon", "params": {"sides": 3, "radius": 12},
    })
    reload_app(ui)
    master_row = ui.locator(f'#layer-list .layer-row[data-layer-id="{master["id"]}"]')
    master_row.locator(".fold").click()
    other_row = ui.locator(f'#layer-list .layer-row[data-layer-id="{other["id"]}"]')
    master_row.drag_to(other_row, target_position={"x": 8, "y": 2})
    ui.wait_for_function(
        "(id) => document.querySelector('#layer-list .layer-row')?.dataset.layerId === id",
        arg=master["id"], timeout=10_000)
    assert all(not ui.locator(f'#layer-list .layer-row[data-layer-id="{child["id"]}"]').count()
               for child in children), "a collapsed move must not spill keyframes into the flat stack"
    project = _get(f"{ui.base}/api/project")
    ordered = [layer["id"] for layer in project["layers"]]
    family = [master["source"]["params"]["b"], master["source"]["params"]["a"], master["id"]]
    family_at = min(ordered.index(layer_id) for layer_id in family)
    assert ordered[family_at:family_at + len(family)] == family
    assert not ui.errors


def test_deleting_a_keyframe_keeps_its_sibling_and_undo_restores_the_family(ui):
    master, children = _animated_polygon(ui)
    reload_app(ui)
    child = children[0]
    child_row = ui.locator(f'#layer-list .layer-row[data-layer-id="{child["id"]}"]')
    delete = child_row.get_by_role("button", name="delete keyframe (click twice)")
    delete.click()
    delete.click()
    ui.wait_for_function(
        "(id) => !document.querySelector(`#layer-list .layer-row[data-layer-id=\"${id}\"]`)",
        arg=child["id"], timeout=10_000)
    project = _get(f"{ui.base}/api/project")
    assert master["id"] not in {layer["id"] for layer in project["layers"]}
    sibling = next(layer for layer in project["layers"] if layer["id"] == children[1]["id"])
    assert sibling["animation_owner_id"] is None

    _post(f"{ui.base}/api/undo")
    reload_app(ui)
    project = _get(f"{ui.base}/api/project")
    restored = [layer for layer in project["layers"] if layer.get("animation_owner_id") == master["id"]]
    assert {layer["id"] for layer in restored} == {child["id"] for child in children}
    assert not ui.errors


def test_master_unanimate_and_delete_are_distinct_actions(ui):
    master, _ = _animated_polygon(ui)
    reload_app(ui)
    ui.locator(f'#layer-list .layer-row[data-layer-id="{master["id"]}"] .lname').click()
    ui.locator('#tw-unanimate').click()
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 1")
    restored = _get(f"{ui.base}/api/project")["layers"]
    assert restored[0]["id"] == master["source"]["params"]["a"]
    assert restored[0]["animation_owner_id"] is None
    _post(f"{ui.base}/api/undo")
    reload_app(ui)
    delete = ui.locator(f'#layer-list .layer-row[data-layer-id="{master["id"]}"] button[aria-label^="delete animation"]')
    delete.click()
    delete.click()
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 0")
    assert not _get(f"{ui.base}/api/project")["layers"]
    assert not ui.errors
