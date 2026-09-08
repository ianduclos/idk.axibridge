"""Bounded acceptance coverage for the expandable Compose process bench.

These tests use the same real-server/browser harness as the established UI
suite.  They name the controls a person can operate, and keep API reads only
for proving that preview/watch gestures did not alter the project.
"""

from __future__ import annotations

import json

from test_acceptance_ui import (  # re-export fixtures for pytest discovery
    _get,
    add_layer,
    frontend_mode,
    reload_app,
    select_layer,
    server,
    ui,
)


def _choose_bench(page, source: str = "grammar") -> None:
    page.select_option("#gen-select", source)
    page.wait_for_selector("#btn-bench:not([hidden])", timeout=10_000)
    page.click("#btn-bench")
    page.wait_for_selector('#process-popup[role="dialog"]:not([hidden])', timeout=20_000)


def _inside_popup(page) -> bool:
    return page.evaluate("""() => {
      const dialog = document.querySelector('#process-popup[role="dialog"]');
      return !!dialog && dialog.contains(document.activeElement);
    }""")


def test_bench_is_a_modal_that_expands_and_restores_the_current_recipe(ui):
    _choose_bench(ui)
    popup = ui.locator("#process-popup")
    assert popup.get_attribute("aria-modal") == "true"
    assert ui.locator("#process-expand").inner_text() == "Expand"
    assert ui.locator("#process-close").inner_text() == "Close"

    # The scrub is the recipe's time-axis value.  Expand/restore is view state
    # only: it must retain the exact working value and the active editor.
    scrub = ui.locator("#process-scrub")
    scrub.evaluate("el => { el.value = el.max; el.dispatchEvent(new Event('input', {bubbles: true})); }")
    ui.wait_for_function("() => document.querySelector('#process-create')?.disabled === false", timeout=20_000)
    recipe_before = ui.locator("#process-readout").inner_text()
    ui.click("#process-expand")
    assert ui.locator("#process-expand").inner_text() == "Restore"
    assert ui.locator("#process-readout").inner_text() == recipe_before
    ui.click("#process-expand")
    assert ui.locator("#process-expand").inner_text() == "Expand"
    assert ui.locator("#process-readout").inner_text() == recipe_before
    assert not ui.errors


def test_modal_focus_stays_inside_and_escape_restores_watch_opener(ui):
    layer_id = add_layer(ui, "grammar", {"iterations": 3, "seed": 7})
    reload_app(ui)  # API setup changes the project, not this already-loaded UI.
    select_layer(ui)
    watch = ui.locator("#process-watch")
    watch.wait_for(state="visible", timeout=10_000)
    watch.click()
    ui.locator('#process-popup[role="dialog"]:not([hidden])').wait_for(timeout=20_000)

    # Cycling focus may use either direction, but must never reach the page
    # behind an open dialog.
    for _ in range(12):
        ui.keyboard.press("Tab")
        assert _inside_popup(ui)

    ui.keyboard.press("Escape")
    ui.locator("#process-popup").wait_for(state="hidden", timeout=10_000)
    assert ui.evaluate("() => document.activeElement?.id") == "process-watch"
    assert _get(f"{ui.base}/api/project")["layers"][0]["id"] == layer_id
    assert not ui.errors


def test_bench_preview_failure_shows_retry_and_never_enables_create_early(ui):
    # A local failure is recoverable.  It must remain local to the draft and
    # must not turn the committed action live before a successful preview.
    ui.route("**/api/generators/preview", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"detail":"preview unavailable"}'))
    _choose_bench(ui)
    ui.locator("#process-error[role=alert]").wait_for(state="visible", timeout=20_000)
    assert ui.locator("#process-retry").is_visible()
    assert ui.locator("#process-create").is_disabled()

    ui.unroute("**/api/generators/preview")
    ui.click("#process-retry")
    ui.wait_for_function("() => document.querySelector('#process-create')?.disabled === false", timeout=20_000)
    assert ui.locator("#process-error").is_hidden()
    # The one injected HTTP failure is expected; retain every unrelated browser
    # error collected by the shared harness.
    ui.errors[:] = [e for e in ui.errors if "503" not in e]
    assert not ui.errors


def test_compact_bench_has_a_controls_shelf_and_fit_actions(ui):
    ui.set_viewport_size({"width": 900, "height": 760})
    _choose_bench(ui, "second_reading")
    ui.locator("#process-controls-toggle").wait_for(state="visible", timeout=15_000)
    assert ui.locator("#process-controls-toggle").inner_text() == "Controls"
    ui.click("#process-controls-toggle")
    assert ui.locator("#process-controls-toggle").inner_text() == "Hide controls"

    # At the compact breakpoint the working actions remain reachable without
    # horizontal clipping, and the Layers rail makes room for the study.
    clipped = ui.evaluate("""() => {
      const modal = document.querySelector('#process-popup .preview-modal');
      const actions = document.querySelector('#process-popup .process-action-row');
      const dock = document.querySelector('#layers-dock');
      if (!modal || !actions || !dock) return true;
      const a = actions.getBoundingClientRect(), m = modal.getBoundingClientRect(), d = dock.getBoundingClientRect();
      return a.left < m.left || a.right > m.right || d.width > 290;
    }""")
    assert not clipped, "compact study clips its actions or leaves the desktop sidebar width"
    assert not ui.errors


def test_second_reading_keeps_its_exact_recipe_through_expand_and_escape_cancels_first(ui):
    _choose_bench(ui, "second_reading")
    ui.wait_for_function(
        "() => document.querySelector('#process-preview-state')?.textContent === 'rendered'",
        timeout=20_000)
    recipe = ui.locator("#process-recipe").text_content()

    ui.click("#process-expand")
    assert ui.locator("#process-recipe").text_content() == recipe
    ui.click("#process-expand")
    assert ui.locator("#process-recipe").text_content() == recipe

    ui.click("#process-your-turn")
    assert ui.locator("#process-your-turn").inner_text() == "Draw on the paper"
    ui.keyboard.press("Escape")
    assert ui.locator("#process-your-turn").inner_text() == "Your turn"
    assert not ui.locator("#process-popup").is_hidden(), "first Escape cancels the gesture"
    ui.keyboard.press("Escape")
    ui.locator("#process-popup").wait_for(state="hidden", timeout=10_000)
    assert ui.evaluate("() => document.activeElement?.id") == "btn-bench"
    assert not ui.errors


def test_generator_picker_groups_benches_and_layer_list_can_expand(ui):
    benches = ui.eval_on_selector_all(
        '#gen-select optgroup[label="Benches"] option', "els => els.map(e => e.value)")
    assert "second_reading" in benches
    assert "grammar" in benches, "declared time axes belong with benchable sources"

    toggle = ui.locator("#layers-dock-expand")
    assert toggle.inner_text() == "Expand list"
    ui.click("#layers-dock-expand")
    assert toggle.inner_text() == "Compact list"
    assert not ui.errors


def test_descriptor_declared_nonaxis_bench_creates_the_real_source(ui):
    """A bench declaration is discovery metadata, not a second generator API.

    Make Polygon benchable at the state boundary only; its preview and Create
    calls still go to the genuine server implementation.
    """
    def state_with_polygon_bench(route):
        response = route.fetch()
        state = response.json()
        polygon = next(m for m in state["modules"]["sources"] if m["id"] == "polygon")
        polygon["bench"] = {"adapter": "process", "version": 1, "modes": ["new"]}
        route.fulfill(response=response, body=json.dumps(state))

    ui.route("**/api/state", state_with_polygon_bench)
    reload_app(ui)
    ui.select_option("#gen-select", "polygon")
    ui.click("#btn-bench")
    ui.locator('#process-popup[role="dialog"]:not([hidden])').wait_for(timeout=15_000)
    assert ui.locator("#process-scrub").is_hidden(), "a non-axis bench has no invented time control"
    ui.wait_for_function("() => document.querySelector('#process-create')?.disabled === false", timeout=20_000)
    ui.click("#process-create")
    ui.locator("#process-popup").wait_for(state="hidden", timeout=15_000)
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)
    project = _get(f"{ui.base}/api/project")
    assert project["layers"][-1]["source"]["generator"] == "polygon"
    ui.unroute("**/api/state")
    assert not ui.errors


def test_second_reading_pinned_reference_shares_a_frame_and_capture_hides_it(ui):
    _choose_bench(ui, "second_reading")
    ui.wait_for_function(
        "() => document.querySelector('#process-preview-state')?.textContent === 'rendered'",
        timeout=20_000)
    ui.click("#process-pin-reference")
    pinned_recipe = ui.locator("#process-recipe").text_content()

    ui.click("#process-continue")
    ui.wait_for_function(
        "old => document.querySelector('#process-preview-state')?.textContent === 'rendered' && "
        "document.querySelector('#process-recipe')?.textContent !== old",
        arg=pinned_recipe, timeout=20_000)
    current_recipe = ui.locator("#process-recipe").text_content()
    ui.click("#process-compare")
    assert ui.locator("#process-compare").get_attribute("aria-pressed") == "true", \
        "Compare must enter comparison mode before its pinned drawing can be inspected"
    ui.locator("#process-reference").wait_for(state="visible", timeout=10_000)
    frames = ui.evaluate("""() => {
      const a = document.querySelector('#process-canvas');
      const b = document.querySelector('#process-reference');
      const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
      const aw = Number(a.viewBox.baseVal.width), bw = Number(b.viewBox.baseVal.width);
      return { viewBox: [a.getAttribute('viewBox'), b.getAttribute('viewBox')], scale: [ar.width / aw, br.width / bw] };
    }""")
    assert frames["viewBox"][0] == frames["viewBox"][1]
    assert abs(frames["scale"][0] - frames["scale"][1]) < 0.001
    assert ui.locator("#process-recipe").text_content() == current_recipe

    ui.click("#process-your-turn")
    assert ui.locator("#process-reference").is_hidden(), "capture gets one unambiguous working frame"
    assert not ui.errors


def test_stale_generic_preview_never_enables_create_before_current_preview(ui):
    # Hold the opening request, then hold the queued scrub request.  This
    # produces a deliberate stale response without timing sleeps or a fake
    # server result: both replies still come from the real preview endpoint.
    ui.evaluate("""() => {
      const original = window.fetch.bind(window);
      let count = 0;
      let releaseOne, releaseTwo;
      window.__benchPreviewCalls = () => count;
      window.__releaseBenchPreviewOne = () => releaseOne?.();
      window.__releaseBenchPreviewTwo = () => releaseTwo?.();
      window.fetch = (...args) => {
        if (!String(args[0]).includes('/api/generators/preview')) return original(...args);
        count += 1;
        if (count === 1) return new Promise(resolve => { releaseOne = resolve; }).then(() => original(...args));
        if (count === 2) return new Promise(resolve => { releaseTwo = resolve; }).then(() => original(...args));
        return original(...args);
      };
    }""")
    _choose_bench(ui, "grammar")
    ui.locator("#process-scrub").evaluate(
        "el => { el.value = String(Number(el.value) + 1); el.dispatchEvent(new Event('input', {bubbles: true})); }")
    ui.evaluate("() => window.__releaseBenchPreviewOne()")
    ui.wait_for_function("() => window.__benchPreviewCalls() >= 2", timeout=10_000)
    assert ui.locator("#process-create").is_disabled(), "a stale reply must not make Create live"
    ui.evaluate("() => window.__releaseBenchPreviewTwo()")
    ui.wait_for_function("() => document.querySelector('#process-create')?.disabled === false", timeout=20_000)
    assert not ui.errors


def test_late_create_completion_cannot_close_a_reopened_bench(ui):
    _choose_bench(ui, "grammar")
    ui.wait_for_function("() => document.querySelector('#process-create')?.disabled === false", timeout=20_000)
    # Pause the real write before it reaches the server.  This leaves the
    # request's promise outstanding while the user deliberately closes and
    # reopens the same bench.
    ui.evaluate("""() => {
      const original = window.fetch.bind(window);
      let release;
      window.__releaseLateBenchCreate = () => release?.();
      window.fetch = (...args) => String(args[0]).includes('/api/layers/generate')
        ? new Promise(resolve => { release = resolve; }).then(() => original(...args))
        : original(...args);
    }""")
    ui.click("#process-create")
    ui.click("#process-close")
    ui.locator("#process-popup").wait_for(state="hidden", timeout=10_000)

    ui.click("#btn-bench")
    ui.locator('#process-popup[role="dialog"]:not([hidden])').wait_for(timeout=15_000)
    ui.wait_for_function(
        "() => document.querySelector('#process-status')?.textContent.includes('Preview current')",
        timeout=20_000)
    ui.evaluate("() => window.__releaseLateBenchCreate()")

    # The earlier operation may refresh the project after completing, but it
    # belongs to the closed view and must not dismiss this newer working view.
    ui.locator('#process-popup[role="dialog"]:not([hidden])').wait_for(timeout=15_000)
    assert "grammar" in ui.locator("#process-title").inner_text().lower()
    assert not ui.errors


def test_shared_stop_follows_the_visible_machine_stop_control(ui):
    _choose_bench(ui, "grammar")
    stop = ui.locator("#process-stop")
    assert stop.is_disabled(), "a hidden machine control cannot make Stop plot available"
    ui.evaluate("""() => {
      const state = document.querySelector('#machine-state');
      const source = document.querySelector('#btn-stop');
      state.removeAttribute('hidden');
      source.disabled = false;
    }""")
    ui.wait_for_function("() => !document.querySelector('#process-stop')?.disabled", timeout=5_000)
    assert stop.is_enabled()
    assert not ui.errors
