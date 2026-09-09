"""Browser coverage for the persistent geometry gallery."""

from __future__ import annotations

import urllib.request

import pytest

from test_acceptance_ui import (  # re-export fixtures for pytest discovery
    _get,
    _post,
    add_layer,
    frontend_mode,
    reload_app,
    select_layer,
    server,
    ui,
)


@pytest.fixture(autouse=True)
def empty_gallery(server):
    for item in _get(f"{server}/api/gallery")["items"]:
        req = urllib.request.Request(f"{server}/api/gallery/{item['id']}", method="DELETE")
        with urllib.request.urlopen(req, timeout=10):
            pass


def _seed_asset(page, name: str = "Five sides", tags: list[str] | None = None,
                sides: int = 5) -> tuple[str, str]:
    layer_id = add_layer(page, "polygon", {"sides": sides, "radius": 32})
    prepared = _post(f"{page.base}/api/gallery/prepare", {
        "kind": "layer", "layer_id": layer_id, "master_t": None,
    })
    asset = _post(f"{page.base}/api/gallery", {
        "capture_id": prepared["capture_id"], "name": name,
        "tags": tags or [], "note": "Seeded by the browser test",
    })
    return layer_id, asset["id"]


def _open_gallery(page) -> None:
    page.click("#btn-gallery")
    page.locator('.gallery-browser [role="dialog"]').wait_for(timeout=10_000)


def test_gallery_browses_filters_and_remembers_search(ui):
    _seed_asset(ui, "Five sides", ["angular", "study"])
    _seed_asset(ui, "Eight sides", ["angular"], sides=8)
    reload_app(ui)
    _open_gallery(ui)
    assert ui.locator(".gallery-card").count() == 2
    previews_fit = ui.evaluate("""() => [...document.querySelectorAll(
      '.gallery-card-preview, .gallery-detail-preview, .gallery-save-preview'
    )].every(preview => {
      const image = preview.querySelector('.gallery-preview-image');
      if (!image) return true;
      const p = preview.getBoundingClientRect(), i = image.getBoundingClientRect();
      return i.left >= p.left - .5 && i.top >= p.top - .5 &&
        i.right <= p.right + .5 && i.bottom <= p.bottom + .5;
    })""")
    assert previews_fit, "gallery preview images must remain within their paper frames"
    ui.screenshot(path="/tmp/axibridge-gallery.png", full_page=True)
    ui.fill(".gallery-search", "Five")
    ui.wait_for_function("() => document.querySelectorAll('.gallery-card').length === 1")
    assert ui.locator(".gallery-card-name").inner_text() == "Five sides"
    ui.click(".gallery-close")
    _open_gallery(ui)
    assert ui.locator(".gallery-search").input_value() == "Five"
    ui.wait_for_function("() => document.querySelectorAll('.gallery-card').length === 1")
    assert ui.locator(".gallery-card").count() == 1
    assert not ui.errors


def test_gallery_edits_metadata_and_inserts_an_independent_layer(ui):
    source_id, asset_id = _seed_asset(ui)
    reload_app(ui)
    _open_gallery(ui)
    ui.fill(".gallery-detail input[type=text]", "Pentagonal field")
    ui.fill(".gallery-detail textarea", "A revised note")
    ui.locator(".gallery-detail-actions button", has_text="Save details").click()
    ui.wait_for_function(
        "() => document.querySelector('.gallery-detail input[type=text]')?.value === 'Pentagonal field'")
    assert _get(f"{ui.base}/api/gallery/{asset_id}")["note"] == "A revised note"

    before = len(_get(f"{ui.base}/api/project")["layers"])
    ui.locator(".gallery-detail-actions button", has_text="Add as layer").click()
    ui.locator(".gallery-browser").wait_for(state="detached", timeout=15_000)
    project = _get(f"{ui.base}/api/project")
    assert len(project["layers"]) == before + 1
    inserted = project["layers"][-1]
    assert inserted["id"] != source_id
    assert inserted["source"]["type"] == "baked"
    assert ui.locator("#layer-list .layer-row.selected").count() == 1
    assert not ui.errors


def test_layer_save_failure_keeps_metadata_and_prevents_duplicate_submit(ui):
    add_layer(ui, "polygon", {"sides": 32, "radius": 24})
    reload_app(ui)
    select_layer(ui)
    calls = 0

    def fail_save(route):
        nonlocal calls
        if not (route.request.method == "POST" and route.request.url.endswith("/api/gallery")):
            route.continue_()
            return
        calls += 1
        route.fulfill(status=503, content_type="application/json",
                      body='{"detail":"gallery disk unavailable"}')

    ui.route("**/api/gallery", fail_save)
    ui.click("#btn-layer-gallery")
    ui.locator('.gallery-save [role="dialog"]').wait_for(timeout=15_000)
    ui.fill(".gallery-save-form input[type=text]", "Keep this exact name")
    ui.fill(".gallery-save-form textarea", "Do not lose this note")
    save = ui.locator('.gallery-save-form button[type="submit"]')
    save.click()
    ui.locator(".gallery-save-form [role=alert]").wait_for(state="visible", timeout=10_000)
    assert ui.locator(".gallery-save-form input[type=text]").first.input_value() == "Keep this exact name"
    assert ui.locator(".gallery-save-form textarea").input_value() == "Do not lose this note"
    assert calls == 1
    ui.errors[:] = [e for e in ui.errors if "503" not in e]
    assert not ui.errors


def test_gallery_delete_confirmation_leaves_inserted_copy(ui):
    _, asset_id = _seed_asset(ui, "Disposable original")
    _post(f"{ui.base}/api/gallery/{asset_id}/insert")
    reload_app(ui)
    ui.on("dialog", lambda dialog: dialog.accept())
    _open_gallery(ui)
    ui.locator(".gallery-detail-actions button", has_text="Delete").click()
    ui.wait_for_function("() => document.querySelectorAll('.gallery-card').length === 0")
    assert len(_get(f"{ui.base}/api/project")["layers"]) == 2
    assert not ui.errors
