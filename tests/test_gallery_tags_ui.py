"""Acceptance coverage for gallery tag chips and popular suggestions."""

from __future__ import annotations

from test_acceptance_ui import _get, add_layer, frontend_mode, reload_app, select_layer, server, ui
from test_gallery_ui import _open_gallery, _seed_asset, empty_gallery


def _chip_labels(page, scope: str) -> list[str]:
    return page.locator(f"{scope} .gallery-tag-chip > span").all_inner_texts()


def _open_layer_save(page):
    add_layer(page, "polygon", {"sides": 6, "radius": 22})
    reload_app(page)
    select_layer(page)
    page.click("#btn-layer-gallery")
    page.locator('.gallery-save [role="dialog"]').wait_for(timeout=15_000)
    page.locator('.gallery-save button[type="submit"]:not([disabled])').wait_for(timeout=15_000)


def test_enter_commits_tag_chip_without_submitting_and_dedupes(ui):
    _open_layer_save(ui)
    draft = ui.locator(".gallery-save .gallery-tag-draft")
    draft.fill("Study")
    draft.press("Enter")
    assert _chip_labels(ui, ".gallery-save") == ["Study"]
    assert not ui.locator(".gallery-save").is_hidden()
    assert _get(f"{ui.base}/api/gallery")["items"] == []

    draft.fill("study, angular,ANGULAR,")
    assert ui.locator(".gallery-save .gallery-tag-chip").count() == 2
    assert _chip_labels(ui, ".gallery-save") == ["Study", "angular"]
    assert not ui.errors


def test_save_includes_unfinished_tag_draft(ui):
    _open_layer_save(ui)
    ui.locator(".gallery-save .gallery-tag-draft").fill("unfinished")
    ui.locator('.gallery-save button[type="submit"]').click()
    ui.locator(".gallery-save").wait_for(state="detached", timeout=15_000)
    items = _get(f"{ui.base}/api/gallery")["items"]
    assert len(items) == 1
    assert items[0]["tags"] == ["unfinished"]
    assert not ui.errors


def test_detail_tags_remove_backspace_dedupe_and_roundtrip(ui):
    _, asset_id = _seed_asset(ui, "Tagged", ["alpha", "beta"])
    reload_app(ui)
    _open_gallery(ui)
    ui.get_by_role("button", name="Remove tag alpha").click()
    draft = ui.locator(".gallery-detail .gallery-tag-draft")
    draft.fill("BETA, gamma,")
    assert _chip_labels(ui, ".gallery-detail") == ["beta", "gamma"]
    draft.press("Backspace")
    assert _chip_labels(ui, ".gallery-detail") == ["beta"]
    ui.locator(".gallery-detail-actions button", has_text="Save details").click()
    ui.wait_for_function("() => !document.querySelector('.gallery-detail-actions button')?.disabled")
    assert _get(f"{ui.base}/api/gallery/{asset_id}")["tags"] == ["beta"]
    assert not ui.errors


def test_popular_tag_suggestion_is_clickable_and_hides_when_selected(ui):
    _seed_asset(ui, "One", ["common", "first"])
    _seed_asset(ui, "Two", ["common"])
    _seed_asset(ui, "Three", ["other"])
    reload_app(ui)
    _open_gallery(ui)
    suggestion = ui.locator(".gallery-detail .gallery-tag-suggestion", has_text="common 2")
    suggestion.wait_for(state="visible", timeout=10_000)
    suggestion.click()
    assert ui.locator(".gallery-detail .gallery-tag-chip", has_text="common").count() == 1
    assert suggestion.count() == 0
    ui.screenshot(path="/tmp/gallery-tags.png", full_page=True)
    assert not ui.errors


def test_stale_server_prepare_405_is_actionable_and_keeps_draft(ui):
    add_layer(ui, "polygon", {"sides": 5, "radius": 18})
    reload_app(ui)
    select_layer(ui)
    ui.route("**/api/gallery/prepare", lambda route: route.fulfill(
        status=405, content_type="application/json", body='{"detail":"Method Not Allowed"}'))
    ui.click("#btn-layer-gallery")
    ui.locator('.gallery-save [role="dialog"]').wait_for(timeout=10_000)
    ui.locator(".gallery-save-form input[type=text]").first.fill("Keep after restart")
    ui.locator(".gallery-save .gallery-tag-draft").fill("waiting")
    alert = ui.locator(".gallery-save [role=alert]")
    alert.wait_for(state="visible", timeout=10_000)
    assert alert.inner_text() == (
        "The running server does not have this gallery endpoint. Restart the "
        "AxiBridge backend, then reopen this dialog."
    )
    assert ui.locator(".gallery-save-form input[type=text]").first.input_value() == "Keep after restart"
    assert ui.locator(".gallery-save .gallery-tag-draft").input_value() == "waiting"
    assert ui.locator('.gallery-save button[type="submit"]').is_disabled()
    ui.errors[:] = [error for error in ui.errors if "405" not in error]
    assert not ui.errors
