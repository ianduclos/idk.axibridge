"""Visible Assets tab behavior through the real browser and server."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from test_acceptance_ui import frontend_mode, server, ui, _get, add_layer, reload_app, select_layer
from test_gallery_ui import empty_gallery, _seed_asset


def _open_assets(page):
    page.locator('#tabs button[data-tab="assets"]').click()
    page.locator("#tab-assets #btn-asset").wait_for(state="visible")


def _png(name="sample.png"):
    output = BytesIO()
    Image.new("RGB", (8, 8), (180, 90, 50)).save(output, format="PNG")
    return {"name": name, "mimeType": "image/png", "buffer": output.getvalue()}


def test_image_upload_and_clear_are_visible_in_assets(ui):
    _open_assets(ui)
    assert ui.locator("#tab-assets #assets-progress").count() == 1
    ui.locator("#asset-file").set_input_files(_png())
    with ui.expect_response("**/api/assets") as uploaded:
        ui.locator("#btn-asset").click()
    assert uploaded.value.ok
    ui.wait_for_function("() => document.querySelector('#asset-list')?.textContent.includes('sample.png')")
    assert any(a["name"] == "sample.png" for a in _get(f"{ui.base}/api/assets")["assets"])

    ui.on("dialog", lambda dialog: dialog.accept())
    ui.locator("#btn-clear-assets").click()
    ui.wait_for_function("() => !document.querySelector('#asset-list')?.textContent.includes('sample.png')")
    assert not _get(f"{ui.base}/api/assets")["assets"]
    assert "on" in ui.locator('#tabs button[data-tab="assets"]').get_attribute("class")
    assert not ui.errors


def test_svg_import_keeps_assets_tab_and_existing_selection(ui):
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    reload_app(ui)
    select_layer(ui)
    _open_assets(ui)
    before = len(_get(f"{ui.base}/api/project")["layers"])
    ui.locator("#svg-file").set_input_files({
        "name": "tiny.svg", "mimeType": "image/svg+xml",
        "buffer": b'<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="20mm" viewBox="0 0 20 20"><path d="M 1 1 L 19 19" stroke="black" fill="none"/></svg>',
    })
    ui.locator("#btn-upload").click()
    ui.wait_for_function(
        "(count) => document.querySelectorAll('#layer-list .layer-row').length > count",
        arg=before,
    )
    assert len(_get(f"{ui.base}/api/project")["layers"]) > before
    assert "on" in ui.locator('#tabs button[data-tab="assets"]').get_attribute("class")
    assert ui.locator("#layer-list .layer-row.selected").count() == 1
    assert not ui.errors


def test_gallery_add_returns_to_compose_with_inserted_layer_selected(ui):
    _, asset_id = _seed_asset(ui, "Assets tab seed")
    _open_assets(ui)
    ui.locator("#btn-gallery").click()
    ui.locator('.gallery-browser [role="dialog"]').wait_for()
    before = len(_get(f"{ui.base}/api/project")["layers"])
    ui.locator(".gallery-card").first.click()
    ui.locator(".gallery-detail-actions button", has_text="Add as layer").click()
    ui.locator(".gallery-browser").wait_for(state="detached")
    assert len(_get(f"{ui.base}/api/project")["layers"]) == before + 1
    assert "on" in ui.locator('#tabs button[data-tab="compose"]').get_attribute("class")
    assert ui.locator("#layer-list .layer-row.selected").count() == 1
    assert asset_id
    assert not ui.errors
