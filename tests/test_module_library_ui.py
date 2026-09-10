"""Browser-level checks for the shared module-library components."""
import json
import urllib.error
import urllib.request

import pytest

from test_acceptance_ui import (_get, _post, add_layer, frontend_mode,
                                reload_app, select_layer, server, ui)


def _request(base, path, method, body=None):
    request = urllib.request.Request(base + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response) if response.length != 0 else None


@pytest.fixture(autouse=True)
def clean_library(server):
    def clear():
        data = _get(f"{server}/api/module-library")
        for preset in data["presets"]:
            _request(server, f"/api/module-library/presets/{preset['id']}", "DELETE")
        for pref in data["preferences"]:
            _request(server, f"/api/module-library/preferences/{pref['kind']}/{pref['module']}",
                     "PUT", {"starred": False, "tags": []})
    clear()
    yield
    clear()


def test_browser_nested_rename_and_delete_keep_browser_open(ui):
    preset = _post(f"{ui.base}/api/module-library/presets", {
        "kind": "source", "module": "polygon", "name": "Orphan", "params": {"sides": 5}})
    ui.click("#gen-browse")
    lissajous = ui.locator('.module-library-card[data-module="lissajous"]')
    lissajous.scroll_into_view_if_needed()
    ui.wait_for_function("() => document.querySelector('.module-library-card[data-module=lissajous] img')?.naturalWidth > 0")
    missing = ui.locator('.module-library-card[data-module="polygon"]')
    missing.scroll_into_view_if_needed()
    ui.wait_for_function("() => document.querySelector('.module-library-card[data-module=polygon] img')?.naturalWidth > 0")
    missing.click()
    ui.wait_for_function("""() => { const host = document.querySelector('.module-library-list').getBoundingClientRect(); return [...document.querySelectorAll('.module-library-card img')]
      .filter(img => { const r = img.getBoundingClientRect(); return r.bottom > host.top && r.top < host.bottom; })
      .every(img => img.hidden || img.naturalWidth > 0); }""")
    ui.screenshot(path="/tmp/module-library-generators.png")
    detail = ui.locator(".module-library-detail")
    detail.get_by_role("combobox", name="Preset", exact=True).select_option(preset["id"])
    detail.get_by_role("button", name="Rename", exact=True).click()
    name_dialog = ui.locator(".module-library-name-dialog")
    name_dialog.get_by_role("textbox", name="Preset name").fill("Still here")
    name_dialog.get_by_role("button", name="Rename", exact=True).click()
    ui.locator('.module-library-name-dialog').wait_for(state="detached")
    assert ui.locator('.module-library-browser').is_visible()
    assert detail.get_by_role("combobox", name="Preset", exact=True).locator("option:checked").inner_text() == "Still here"
    detail.get_by_role("button", name="Delete", exact=True).click()
    ui.locator('.module-library-name-dialog').get_by_role("button", name="Delete", exact=True).click()
    ui.locator('.module-library-preset-select option[value="%s"]' % preset["id"]).wait_for(state="detached")
    assert not _get(f"{ui.base}/api/module-library")["presets"]
    assert not ui.errors


def test_failed_save_keeps_dialog_name_and_does_not_duplicate(ui):
    _post(f"{ui.base}/api/module-library/presets", {
        "kind": "source", "module": "polygon", "name": "Taken", "params": {"sides": 3}})
    attempts = []
    def fail_save(route):
        if route.request.method == "POST":
            attempts.append(route.request.post_data)
            route.fulfill(status=503, content_type="application/json",
                          body=json.dumps({"detail": "Store unavailable"}))
        else:
            route.continue_()
    ui.route("**/api/module-library/presets", fail_save)
    add_layer(ui, "polygon", {"sides": 8})
    reload_app(ui)
    select_layer(ui)
    controls = ui.locator('#layer-detail .module-preset-controls[data-module="polygon"]')
    controls.wait_for()
    controls.get_by_role("button", name="Save as preset", exact=True).click()
    name = ui.get_by_role("textbox", name="Preset name")
    name.fill("Taken")
    ui.get_by_role("button", name="Save preset", exact=True).click()
    ui.locator('.module-library-name-dialog [role="alert"]').wait_for(state="visible")
    assert name.input_value() == "Taken"
    assert len(attempts) == 1
    assert len(_get(f"{ui.base}/api/module-library")["presets"]) == 1
    ui.get_by_role("button", name="Cancel", exact=True).click()
    assert all("503" in error for error in ui.errors)
