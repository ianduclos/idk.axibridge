"""Linedraw component controls and frozen-layer action, using synthetic paths."""

from test_linedraw_ui import _upload_image, open_bench
from test_acceptance_ui import frontend_mode, server, ui


def test_components_smoothing_preview_and_separate_layers(ui):
    _upload_image(ui, "components.png")
    ui.route("**/api/linedraw/status", lambda route: route.fulfill(json={
        "available": True, "faces": True, "detail": "Synthetic models",
    }))
    submitted = []

    def complete(route):
        body = route.request.post_data_json
        submitted.append(body)
        route.fulfill(json={"id": "component-job", "state": "complete", "result": {
            "params": body["params"], "warnings": [],
            "preview": {"width": 40, "height": 60, "lines": [
                [[0, 0], [10, 0]], [[0, 4], [10, 4]],
            ], "components": [
                {"id": "contours", "label": "Contours", "lines": [[[0, 0], [10, 0]]], "count": 1},
                {"id": "form", "label": "Form shading", "lines": [[[0, 4], [10, 4]]], "count": 1},
            ]},
        }})

    ui.route("**/api/linedraw/jobs", complete)
    detach_requests = []

    def detached(route):
        detach_requests.append(route.request.post_data_json)
        route.fulfill(json={"layers": [{"id": "frozen-1"}]})

    ui.route("**/api/linedraw/jobs/component-job/detach", detached)
    open_bench(ui)
    assert [section.locator("h3").text_content() for section in ui.locator("#linedraw-panel > section").all()] == ["Image", "Drawing", "Guides"]
    assert not ui.locator("#linedraw-image-options").evaluate("details => details.open")
    assert not ui.get_by_text("Precise face coordinates", exact=True).locator("xpath=..").get_attribute("open")
    assert ui.get_by_role("button", name="Keep separate layers").is_disabled()
    ui.locator('#linedraw-image-form select:has(option[value="components.png"])').select_option("components.png")
    ui.get_by_label("Automatic redraw", exact=True).uncheck()
    ui.get_by_label("Drawing style", exact=True).select_option("face_form")
    ui.locator('[data-component="cores"]').uncheck()
    smooth = ui.locator('#linedraw-drawing-form .field:has-text("Smoothen (mm)") input[type="number"]')
    smooth.fill("0.4")
    smooth.press("Tab")
    ui.get_by_role("button", name="Redraw", exact=True).click()
    ui.wait_for_function("document.getElementById('linedraw-message').textContent.startsWith('Drawing ready.')")
    assert submitted[-1]["params"]["ink_components"] == ["contours", "form"]
    assert submitted[-1]["params"]["smoothing_mm"] == 0.4
    assert ui.locator('#linedraw-drawing path[data-component="contours"]').count() == 1
    assert ui.locator('#linedraw-drawing path[data-component="form"]').count() == 1
    assert ui.locator('#linedraw-drawing').evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(255, 255, 255)"
    assert ui.get_by_role("button", name="Keep separate layers").is_enabled()
    with ui.expect_request("**/api/linedraw/jobs/component-job/detach"):
        ui.get_by_role("button", name="Keep separate layers").click()
    ui.wait_for_function("document.getElementById('linedraw-message').textContent.startsWith('Kept frozen')")
    assert detach_requests == [{"revision": submitted[-1]["revision"], "source_layer_id": None}]
    assert not ui.errors


def test_style_relevance_and_legacy_controls(ui):
    open_bench(ui)
    form = ui.locator("#linedraw-drawing-form")
    treatment = ui.locator("#linedraw-treatment")
    style = ui.get_by_label("Drawing style", exact=True)
    style.select_option("contours")
    assert form.get_by_text("Strokes per face").count() == 1
    assert treatment.is_hidden()
    assert ui.locator('[data-component="form"]').is_hidden()
    assert ui.locator('[data-component="cores"]').is_hidden()
    assert ui.locator('#linedraw-edit-mode option[value="people"]').evaluate("option => option.disabled")
    style.select_option("light_form")
    assert form.get_by_text("Shadow reading").count() == 1
    assert form.get_by_text("Shadow strength").count() == 1
    assert treatment.is_visible()
    assert treatment.get_by_text("Dark core strength").count() == 0
    style.select_option("face_form")
    assert form.get_by_text("Shadow fill spacing (mm)").count() == 1
    style.select_option("light_support")
    assert ui.locator("#linedraw-guides").is_hidden()
    assert "whole-image and crop evidence" in ui.locator("#linedraw-style-hint").inner_text()
    style.select_option("regional_form")
    assert ui.locator("#linedraw-guides").is_visible()
    assert not ui.locator('#linedraw-edit-mode option[value="people"]').evaluate("option => option.disabled")
    assert treatment.get_by_text("Hair direction from image").count() == 0
    ui.get_by_role("button", name="Add detail region").click()
    ui.get_by_label("Detail category").select_option("hair")
    assert treatment.get_by_text("Hair direction from image").count() == 1
    assert not ui.errors
