"""Real-browser checks for the shared seed and preset controls."""

import json
import urllib.request

from test_acceptance_ui import (_get, add_layer, frontend_mode, reload_app,
                                select_layer, server, ui)


def _seed_field(page, host="#regen-form"):
    return page.locator(f"{host} .field").filter(has=page.locator("label", has_text="Seed")).first


def _request(base, path, method, body):
    request = urllib.request.Request(base + path, method=method,
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def test_seed_dice_commits_once_and_render_does_not_reroll(ui):
    layer_id = add_layer(ui, "flowfield", {"width": 20, "height": 20,
        "separation": 10, "max_length": 10, "seed": 50})
    reload_app(ui); select_layer(ui)
    field = _seed_field(ui)
    number = field.locator('input[type="number"]')
    dice = field.get_by_role("button", name="Reroll Seed")
    assert number.input_value() == "50"
    assert dice.get_attribute("title") == "Reroll Seed"
    assert _get(f"{ui.base}/api/project")["layers"][0]["source"]["params"]["seed"] == 50
    reload_app(ui); select_layer(ui)
    assert _seed_field(ui).locator('input[type="number"]').input_value() == "50"
    ui.evaluate("Math.random = () => 0.999999999")
    calls = []
    ui.on("request", lambda request: calls.append(request.url) if
          request.method == "POST" and request.url.endswith(f"/layers/{layer_id}/regenerate") else None)
    with ui.expect_response(lambda response: response.request.method == "POST" and
            response.url.endswith(f"/layers/{layer_id}/regenerate")):
        _seed_field(ui).get_by_role("button", name="Reroll Seed").click()
    ui.wait_for_function("() => [...document.querySelectorAll('#regen-form .field')].find(f => f.querySelector('label')?.textContent === 'Seed')?.querySelector('input[type=number]')?.value === '99999'")
    assert len(calls) == 1
    assert _get(f"{ui.base}/api/project")["layers"][0]["source"]["params"]["seed"] == 99999
    assert not ui.errors


def test_seed_dice_respects_lower_bound(ui):
    ui.select_option("#gen-select", "flowfield")
    field = _seed_field(ui, "#gen-form")
    number = field.locator('input[type="number"]')
    assert number.get_attribute("min") == "0"
    ui.evaluate("Math.random = () => 0")
    field.get_by_role("button", name="Reroll Seed").click()
    assert number.input_value() == "0"
    assert not ui.errors


def test_preset_management_disclosure_save_update_and_apply(ui):
    layer_id = add_layer(ui, "polygon", {"sides": 4, "radius": 18})
    reload_app(ui); select_layer(ui)
    controls = ui.locator('#layer-detail .module-preset-controls[data-module="polygon"]')
    controls.wait_for()
    disclosure = controls.locator("details")
    assert disclosure.locator("summary").inner_text() == "Manage presets"
    assert not disclosure.evaluate("node => node.open")
    assert controls.locator(".module-preset-select").is_visible()
    assert controls.locator(".module-preset-apply").is_visible()
    assert not controls.locator(".module-preset-save").is_visible()
    disclosure.locator("summary").click()
    assert controls.locator(".module-preset-save").is_visible()
    assert controls.locator(".module-preset-update").is_disabled()
    controls.locator(".module-preset-save").click()
    ui.get_by_role("textbox", name="Preset name").fill("Compact")
    ui.get_by_role("button", name="Save preset", exact=True).click()
    ui.locator(".module-library-name-dialog").wait_for(state="detached")
    ui.wait_for_function("() => document.querySelector('#layer-detail .module-preset-update')?.disabled === false")
    preset = next(p for p in _get(f"{ui.base}/api/module-library")["presets"] if p["name"] == "Compact")
    assert controls.locator(".module-preset-select").input_value() == preset["id"]
    _request(ui.base, f"/api/layers/{layer_id}/regenerate", "POST",
             {"params": {"sides": 8, "radius": 18}})
    reload_app(ui); select_layer(ui)
    controls = ui.locator('#layer-detail .module-preset-controls[data-module="polygon"]')
    controls.locator(".module-preset-select").select_option(preset["id"])
    controls.locator("details summary").click()
    controls.locator(".module-preset-update").click()
    ui.wait_for_function("() => document.querySelector('#layer-detail .module-preset-update')?.disabled === false")
    updated = next(p for p in _get(f"{ui.base}/api/module-library")["presets"] if p["id"] == preset["id"])
    assert updated["params"]["sides"] == 8
    _request(ui.base, f"/api/layers/{layer_id}/regenerate", "POST",
             {"params": {"sides": 4, "radius": 18}})
    reload_app(ui); select_layer(ui)
    controls = ui.locator('#layer-detail .module-preset-controls[data-module="polygon"]')
    controls.locator(".module-preset-select").select_option(preset["id"])
    with ui.expect_response(lambda response: response.request.method == "POST" and
            response.url.endswith(f"/layers/{layer_id}/regenerate")):
        controls.locator(".module-preset-apply").click()
    assert _get(f"{ui.base}/api/project")["layers"][0]["source"]["params"]["sides"] == 8
    assert not ui.errors
