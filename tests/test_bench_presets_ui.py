"""The shared preset row loads only working-bench drafts."""

import json
import urllib.request

import pytest

from test_acceptance_ui import _get, _post, _put, add_layer, frontend_mode, reload_app, select_layer, server, ui
from test_bench_ui import _choose_bench
from test_magnetic_bench_ui import open_magnetic, ready, recipe


def _apply_preset(page, preset_id=""):
    controls = page.locator("#process-popup .module-preset-controls")
    controls.locator(".module-preset-select").select_option(preset_id)
    controls.locator(".module-preset-apply").click()


def _wait_for_preset(page):
    page.wait_for_function(
        "() => !document.querySelector('#process-popup .module-preset-apply')?.disabled",
        timeout=30_000)


@pytest.fixture(autouse=True)
def clean_module_library(server):
    original = _get(f"{server}/api/module-library")
    before = {item["id"] for item in original["presets"]}
    preferences = {(item["kind"], item["module"]): item for item in original["preferences"]}
    yield
    for item in _get(f"{server}/api/module-library")["presets"]:
        if item["id"] not in before:
            request = urllib.request.Request(
                f"{server}/api/module-library/presets/{item['id']}", method="DELETE")
            with urllib.request.urlopen(request, timeout=20):
                pass
    for (kind, module), item in preferences.items():
        _put(f"{server}/api/module-library/preferences/{kind}/{module}", {
            "starred": item["starred"], "tags": item["tags"],
        })


@pytest.mark.parametrize("module", ["venation", "homeostat"])
def test_generic_bench_preset_replaces_the_draft_and_reset_the_axis(ui, server, module):
    descriptor = next(source for source in _get(f"{server}/api/state")["modules"]["sources"]
                      if source["id"] == module)
    axis = descriptor["time_axis"]
    params = dict(descriptor["defaults"])
    params[axis] = descriptor["schema"]["properties"][axis]["minimum"]
    created = _post(f"{server}/api/module-library/presets", {
        "kind": "source", "module": module, "name": f"{module} bench start", "params": params,
    })
    _choose_bench(ui, module)
    before = _get(f"{server}/api/project")
    scrub = ui.locator("#process-scrub")
    scrub.evaluate("el => { el.value = el.max; el.dispatchEvent(new Event('input', {bubbles: true})); }")
    ui.wait_for_function("() => document.querySelector('#process-create')?.disabled === false", timeout=30_000)
    _apply_preset(ui, created["id"])
    _wait_for_preset(ui)
    ui.wait_for_function("() => document.querySelector('#process-create')?.disabled === false", timeout=30_000)
    assert ui.locator("#process-popup .module-preset-error").is_hidden()
    assert float(scrub.input_value()) == pytest.approx(float(params[axis]))
    assert _get(f"{server}/api/project") == before
    assert not ui.errors


def test_magnetic_and_second_reading_preset_loads_clear_local_interaction_state(ui, server):
    open_magnetic(ui)
    ui.click("#magnetic-scatter")
    ready(ui)
    current = recipe(ui)
    saved = _post(f"{server}/api/module-library/presets", {
        "kind": "source", "module": "magnetic_field", "name": "Field settings", "params": current,
    })
    excluded = {"magnets", "presets", "preset_sizes", "mix_x", "mix_y", "mix_active"}
    assert not (excluded & saved["params"].keys())
    assert saved["params"]["seed"] == current["seed"]
    before = _get(f"{server}/api/project")
    ui.click("#process-close")
    open_magnetic(ui)  # a real reopen reloads the library row after the save
    with ui.expect_request("**/api/module-library/resolve") as applied:
        _apply_preset(ui, saved["id"])
    _wait_for_preset(ui)
    applied_recipe = json.loads(applied.value.post_data)
    assert applied_recipe["preset_id"] == saved["id"]
    ready(ui)
    loaded_magnetic = recipe(ui)
    assert loaded_magnetic["seed"] == saved["params"]["seed"] == current["seed"]
    assert loaded_magnetic["magnets"] != current["magnets"]
    assert ui.locator("#magnetic-undo").is_disabled()
    assert _get(f"{server}/api/project") == before
    ui.click("#process-close")

    _choose_bench(ui, "second_reading")
    ui.wait_for_function("() => document.querySelector('#process-preview-state')?.textContent === 'rendered'", timeout=30_000)
    ui.click("#process-continue")
    ui.wait_for_function("() => document.querySelector('#process-preview-state')?.textContent === 'rendered' && JSON.parse(document.querySelector('#process-recipe').textContent).turns > 0", timeout=30_000)
    before = _get(f"{server}/api/project")
    _apply_preset(ui)
    _wait_for_preset(ui)
    ui.wait_for_function("() => document.querySelector('#process-preview-state')?.textContent === 'rendered'", timeout=30_000)
    loaded = json.loads(ui.locator("#process-recipe").text_content())
    assert loaded["events"] == []
    assert ui.locator("#process-undo").is_disabled()
    assert _get(f"{server}/api/project") == before
    assert not ui.errors


def test_watch_mode_has_no_preset_controls(ui):
    add_layer(ui, "homeostat", {"steps": 4, "seed": 9})
    reload_app(ui)
    select_layer(ui)
    ui.click("#process-watch")
    ui.locator('#process-popup[role="dialog"]:not([hidden])').wait_for(timeout=20_000)
    assert not ui.locator("#process-popup .module-preset-controls").count()
    assert not ui.errors
