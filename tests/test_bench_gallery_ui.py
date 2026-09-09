"""Gallery capture from working benches uses the exact accepted recipe."""

import json

from test_acceptance_ui import _get, frontend_mode, select_layer, server, ui
from test_bench_ui import _choose_bench
from test_magnetic_bench_ui import open_magnetic, ready, recipe


def cancel_save(page):
    page.locator(".gallery-save").wait_for(state="visible", timeout=20_000)
    page.get_by_role("button", name="Cancel", exact=True).click()


def test_homeostat_gallery_save_uses_current_full_recipe_and_does_not_create_layer(ui, server):
    _choose_bench(ui, "homeostat")
    ui.wait_for_function(
        "() => document.querySelector('#process-generic-save-gallery')?.disabled === false",
        timeout=20_000,
    )
    ui.locator("#process-scrub").evaluate(
        "el => { el.value = String(Number(el.value) + 1); el.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    ui.wait_for_function(
        "() => document.querySelector('#process-generic-save-gallery')?.disabled === false",
        timeout=20_000,
    )
    expected_step = float(ui.locator("#process-scrub").input_value())
    with ui.expect_request("**/api/gallery/prepare") as request:
        ui.click("#process-generic-save-gallery")
    source = request.value.post_data_json
    assert source["kind"] == "generator"
    assert source["module"] == "homeostat"
    assert source["params"]["steps"] == expected_step
    ui.locator(".gallery-save").wait_for(state="visible", timeout=20_000)
    ui.locator(".gallery-save input[type=text]").first.fill("Homeostat bench capture")
    ui.locator(".gallery-save button.primary").wait_for(state="visible", timeout=20_000)
    ui.locator(".gallery-save button.primary").click()
    ui.locator(".gallery-save").wait_for(state="detached", timeout=20_000)
    assets = _get(f"{server}/api/gallery")["items"]
    assert any(item["name"] == "Homeostat bench capture" for item in assets)
    assert not _get(f"{server}/api/project")["layers"]
    assert not ui.errors


def test_watch_mode_does_not_offer_generator_gallery_capture(ui, server):
    _choose_bench(ui, "homeostat")
    ui.wait_for_function("() => document.querySelector('#process-create')?.disabled === false", timeout=20_000)
    ui.click("#process-create")
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)
    select_layer(ui)
    ui.click("#process-watch")
    ui.locator('#process-popup[role="dialog"]:not([hidden])').wait_for(timeout=10_000)
    assert ui.locator("#process-generic-save-gallery").is_hidden()
    assert not ui.errors


def test_magnetic_gallery_save_is_blocked_during_updates_and_uses_rendered_recipe(ui, server):
    open_magnetic(ui)
    held = []

    def intercept(route):
        held.append(route)

    ui.route("**/api/generators/preview", intercept)
    ui.uncheck("#magnetic-show")
    assert ui.locator("#magnetic-save-gallery").is_disabled()
    assert held
    route = held.pop()
    route.fulfill(response=route.fetch())
    ui.unroute("**/api/generators/preview", intercept)
    ready(ui)
    expected = recipe(ui)
    with ui.expect_request("**/api/gallery/prepare") as request:
        ui.click("#magnetic-save-gallery")
    assert request.value.post_data_json == {
        "kind": "generator", "module": "magnetic_field", "params": expected,
    }
    assert not _get(f"{server}/api/project")["layers"]
    cancel_save(ui)
    assert not ui.errors


def test_second_reading_gallery_save_captures_only_current_working_branch(ui, server):
    _choose_bench(ui, "second_reading")
    ui.wait_for_function(
        "() => document.querySelector('#process-save-gallery')?.disabled === false",
        timeout=20_000,
    )
    ui.click("#process-pin-reference")
    ui.click("#process-try-another")
    ui.wait_for_function(
        "() => document.querySelector('#process-save-gallery')?.disabled === false",
        timeout=20_000,
    )
    current = json.loads(ui.locator("#process-recipe").text_content())
    with ui.expect_request("**/api/gallery/prepare") as request:
        ui.click("#process-save-gallery")
    assert request.value.post_data_json == {
        "kind": "generator", "module": "second_reading", "params": current,
    }
    assert not _get(f"{server}/api/project")["layers"]
    cancel_save(ui)
    assert not ui.errors
