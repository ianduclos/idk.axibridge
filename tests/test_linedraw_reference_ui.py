"""Regional Linedraw controls with synthetic jobs; no model weights or private images."""

from test_linedraw_ui import _upload_image, open_bench
from test_acceptance_ui import frontend_mode, server, ui
from axibridge.linedraw.contracts import LinedrawV3Params


def test_regional_draft_edit_and_image_reset(ui):
    _upload_image(ui, "regions.png")
    _upload_image(ui, "other.png")
    ui.route("**/api/linedraw/status", lambda route: route.fulfill(json={
        "available": True, "faces": True, "detail": "Synthetic models",
    }))
    requests = []

    def complete(route):
        params = route.request.post_data_json["params"]
        requests.append(params)
        params.update(image_identity="synthetic", model_identity="synthetic")
        route.fulfill(json={"id": "synthetic", "state": "complete", "result": {
            "params": params, "warnings": [],
            "preview": {"width": 40, "height": 60, "lines": [[[0, 0], [10, 0]]]},
        }})

    ui.route("**/api/linedraw/jobs", complete)
    open_bench(ui)
    image = ui.locator('#linedraw-form select:has(option[value="regions.png"])')
    image.select_option("regions.png")
    ui.get_by_label("Drawing style", exact=True).select_option("light_support")
    assert ui.get_by_text("Light form support", exact=True).count() == 1
    assert ui.locator('#linedraw-form').get_by_text("Contour strokes").count() == 1
    assert ui.locator('#linedraw-form').get_by_text("Shadow strength").count() == 0
    ui.get_by_label("Drawing style", exact=True).select_option("regional_form")
    assert ui.locator('#linedraw-form').get_by_text("Detail strokes per person").count() == 1
    ui.get_by_role("button", name="Add detail region").click()
    assert ui.locator('#linedraw-person-select option').count() == 1
    assert ui.locator('#linedraw-detail-select option').count() == 1
    ui.get_by_label("Detail category").select_option("hair")
    ui.get_by_label("Detail vertices (normalized x,y per line)").fill("0.1,0.1\n0.8,0.1\n0.8,0.9\n0.1,0.9")
    ui.get_by_label("Detail vertices (normalized x,y per line)").press("Tab")
    ui.get_by_label("Excluded polygons (JSON normalized coordinates)").fill("[[[0.2,0.2],[0.3,0.2],[0.3,0.3]]]")
    ui.get_by_label("Excluded polygons (JSON normalized coordinates)").press("Tab")
    ui.get_by_label("Include hair").uncheck()
    ui.get_by_label("Include hair").check()
    ui.get_by_role("button", name="Redraw", exact=True).click()
    ui.wait_for_function("document.getElementById('linedraw-message').textContent.startsWith('Drawing ready.')")
    assert requests[-1]["detail_regions"][0]["category"] == "hair"
    assert requests[-1]["people"][0]["polygon"] == [[0, 0], [1, 0], [1, 1], [0, 1]]
    assert requests[-1]["detail_regions"][0]["polygon"][0] == [0.1, 0.1]
    assert requests[-1]["detail_regions"][0]["exclude_polygons"][0][0] == [0.2, 0.2]
    assert "hair" in requests[-1]["detail_categories"]
    LinedrawV3Params.model_validate(requests[-1])
    image = ui.locator('#linedraw-form select:has(option[value="other.png"])')
    image.select_option("other.png")
    assert ui.locator('#linedraw-detail-select option').count() == 0
    assert ui.locator('#linedraw-person-select option').count() == 0
    assert ui.get_by_role("button", name="Keep as layer", exact=True).is_disabled()
    assert not ui.errors


def test_category_edit_redraws_and_updates_status(ui):
    _upload_image(ui, "automatic.png")
    ui.route("**/api/linedraw/status", lambda route: route.fulfill(json={
        "available": True, "faces": True, "detail": "Synthetic models",
    }))
    requests = []

    def complete(route):
        params = route.request.post_data_json["params"]
        requests.append(params)
        params.update(image_identity="synthetic", model_identity="synthetic")
        route.fulfill(json={"id": "synthetic", "state": "complete", "result": {
            "params": params, "warnings": [],
            "preview": {"width": 40, "height": 60, "lines": [[[0, 0], [10, 0]]]},
        }})

    ui.route("**/api/linedraw/jobs", complete)
    ui.route("**/api/linedraw/jobs/synthetic", lambda route: route.fulfill(json={}))
    open_bench(ui)
    ui.locator('#linedraw-form select:has(option[value="automatic.png"])').select_option("automatic.png")
    ui.evaluate('''() => {
      const original = window.fetch.bind(window);
      window.__heldRegional = false;
      window.__releaseRegional = null;
      window.fetch = async (url, opts) => {
        const response = await original(url, opts);
        if (String(url).endsWith('/api/linedraw/jobs') && opts?.method === 'POST' && !window.__heldRegional) {
          window.__heldRegional = true;
          return new Promise(resolve => { window.__releaseRegional = () => resolve(response); });
        }
        return response;
      };
    }''')
    ui.get_by_label("Drawing style", exact=True).select_option("regional_form")
    ui.wait_for_function("window.__releaseRegional !== null")
    assert requests[0]["style"] == "regional_form"
    ui.get_by_label("Include body").check()
    ui.wait_for_function("document.getElementById('process-status').textContent.startsWith('Drawing current')")
    assert len(requests) == 2
    assert "body" in requests[-1]["detail_categories"]
    ui.evaluate("window.__releaseRegional()")
    assert ui.get_by_label("Include body").is_checked()
    assert ui.get_by_role("button", name="Keep as layer", exact=True).is_enabled()
    assert not ui.errors


def test_manual_redraw_and_region_creation_pause_automatic_updates(ui):
    _upload_image(ui, "manual.png")
    ui.route("**/api/linedraw/status", lambda route: route.fulfill(json={
        "available": True, "faces": True, "detail": "Synthetic models",
    }))
    requests = []

    def complete(route):
        params = route.request.post_data_json["params"]
        requests.append(params)
        route.fulfill(json={"id": "synthetic", "state": "complete", "result": {
            "params": params, "warnings": [],
            "preview": {"width": 40, "height": 60, "lines": [[[0, 0], [10, 0]]]},
        }})

    ui.route("**/api/linedraw/jobs", complete)
    open_bench(ui)
    ui.locator('#linedraw-form select:has(option[value="manual.png"])').select_option("manual.png")
    auto = ui.get_by_label("Automatic redraw", exact=True)
    auto.uncheck()
    ui.get_by_label("Drawing style", exact=True).select_option("regional_form")
    ui.wait_for_timeout(550)  # Beyond the debounce: no inference in manual mode.
    assert requests == []
    ui.get_by_role("button", name="Redraw", exact=True).click()
    ui.wait_for_function("document.getElementById('linedraw-message').textContent.startsWith('Drawing ready.')")
    assert len(requests) == 1
    auto.check()
    # Queue an update, then immediately begin adding a guide: cancel the timer.
    ui.get_by_label("Include body").check()
    ui.get_by_role("button", name="Add detail region", exact=True).click()
    assert not auto.is_checked()
    ui.get_by_label("Detail category").select_option("hair")
    ui.get_by_role("button", name="Draw detail polygon", exact=True).click()
    assert auto.is_disabled()
    ui.wait_for_timeout(550)
    assert len(requests) == 1
    assert ui.get_by_role("button", name="Keep as layer", exact=True).is_disabled()
    # Escape cancels the unfinished polygon without re-enabling automatic work.
    ui.keyboard.press("Escape")
    assert auto.is_enabled()
    assert not auto.is_checked()
    auto.check()
    ui.wait_for_function("document.getElementById('linedraw-message').textContent.startsWith('Drawing ready.')")
    assert len(requests) == 2
    assert requests[-1]["detail_regions"][0]["category"] == "hair"
    assert not ui.errors
