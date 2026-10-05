"""Browser contracts for the portable Mosca 2 page and run history."""

from __future__ import annotations

from test_acceptance_ui import _get, frontend_mode, select_layer, server, ui


PIECE = {
    "id": "fixture-page", "title": "A small page",
    "parts": [
        {"id": "fixture-territory", "label": "Territory", "kind": "territory",
         "visible": True, "strokes": [[[20.125, 30.25], [40.5, 50.75]]],
         "provenance": "fixture territory"},
        {"id": "fixture-flow", "label": "Flowing", "kind": "flowing",
         "visible": True, "strokes": [[[100.0, 101.0], [110.5, 111.25]]],
         "provenance": "fixture flowing"},
    ],
}


def _open(ui):
    ui.route("**/api/mosca2/status", lambda route: route.fulfill(json={
        "available": True, "reason": ""}))
    ui.route("**/api/mosca2/materials", lambda route: route.fulfill(json={
        "materials": [], "pieces": [PIECE]}))
    ui.wait_for_function(
        "() => !!document.querySelector('#gen-select option[value=mosca2]')")
    ui.select_option("#gen-select", "mosca2")
    ui.click("#btn-bench")
    ui.wait_for_selector("#process-popup.mosca2-bench:not([hidden])")
    ui.wait_for_function(
        "() => document.querySelectorAll('#m2-parts .m2-part').length === 2")


def _paths(ui):
    return ui.locator("#mosca2-stage .m2-ink path").evaluate_all(
        "nodes => nodes.map(node => node.getAttribute('d'))")


def _keep(ui, server):
    before = len(_get(f"{server}/api/project")["layers"])
    ui.click("#m2-keep")
    ui.wait_for_function(
        "expected => document.querySelector('#m2-kept')?.textContent.includes('Kept') "
        "&& document.querySelectorAll('#layer-list .layer-row').length === expected",
        arg=before + 1, timeout=20_000)
    return _get(f"{server}/api/project")["layers"][-1]


def _resume(ui):
    ui.click("#process-close")
    select_layer(ui)
    ui.click("#process-resume")
    ui.wait_for_selector("#process-popup.mosca2-bench:not([hidden])")
    ui.wait_for_function(
        "() => document.querySelectorAll('#m2-parts .m2-part').length >= 2")


def test_default_page_keep_and_resume_preserve_geometry_and_history(ui, server):
    _open(ui)
    initial_paths = _paths(ui)
    assert len(initial_paths) == 2
    kept = _keep(ui, server)
    params = kept["source"]["params"]
    assert params["engine"] == "mosca2-v1"
    assert [(part["kind"], part["strokes"]) for part in params["parts"]] == [
        (part["kind"], part["strokes"]) for part in PIECE["parts"]]
    assert params["history"] == []
    resolved = _get(f"{server}/api/compose/resolved?stats=false")
    assert len(resolved["layers"][-1]["paths"]) == 2
    _resume(ui)
    assert _paths(ui) == initial_paths
    assert ui.locator("#m2-history option").count() == 1
    assert not ui.errors


def test_completed_run_keeps_full_history_and_undo_is_consistent(ui, server):
    _open(ui)
    provenance = "neural-metadata:" + "x" * 1200
    ui.route("**/api/mosca2/jobs", lambda route: route.fulfill(json={
        "id": "fixture-job", "status": "running"}))
    ui.route("**/api/mosca2/jobs/fixture-job", lambda route: route.fulfill(json={
        "id": "fixture-job", "status": "completed", "progress": 1,
        "result": {"strokes": [[[70.25, 80.5], [71.75, 82.0]]],
                   "events": [{"t_ms": 250, "kind": "contact", "detail": "near old ink"}],
                   "metrics": {"contact_samples": 1}, "provenance": provenance}}))
    ui.click("#m2-run")
    ui.wait_for_function(
        "() => document.querySelectorAll('#m2-parts .m2-part').length === 3 "
        "&& document.querySelectorAll('#m2-history option').length === 2",
        timeout=15_000)
    assert len(_paths(ui)) == 3
    ui.select_option("#m2-history", index=1)
    assert ui.locator("#m2-run").is_disabled()
    ui.select_option("#m2-history-view", "before")
    assert len(_paths(ui)) == 2
    ui.select_option("#m2-history-view", "added")
    assert len(_paths(ui)) == 1
    assert _paths(ui)[0] == "M70.25 80.5 L71.75 82"
    ui.select_option("#m2-history", "")
    assert ui.locator("#m2-run").is_enabled()
    first = _keep(ui, server)
    params = first["source"]["params"]
    assert params["history"][0]["provenance"] == provenance
    assert params["history"][0]["events"][0]["kind"] == "contact"
    assert len(params["parts"][-1]["provenance"]) <= 1000
    _resume(ui)
    assert ui.locator("#m2-history option").count() == 2
    assert len(_paths(ui)) == 3
    ui.click("#m2-undo-step")
    assert ui.locator("#m2-history option").count() == 1
    assert len(_paths(ui)) == 2
    ui.click("#m2-undo")
    assert ui.locator("#m2-history option").count() == 2
    assert len(_paths(ui)) == 3
    ui.click("#m2-undo-step")
    assert ui.locator("#m2-history option").count() == 1
    assert len(_paths(ui)) == 2
    second = _keep(ui, server)
    assert second["source"]["params"]["history"] == []
    assert len(second["source"]["params"]["parts"]) == 2
    assert not ui.errors


def test_cancelled_run_does_not_change_page(ui):
    _open(ui)
    ui.route("**/api/mosca2/jobs", lambda route: route.fulfill(json={
        "id": "fixture-cancel", "status": "running"}))
    ui.route("**/api/mosca2/jobs/fixture-cancel", lambda route: route.fulfill(json={
        "id": "fixture-cancel", "status": "running", "progress": .5,
        "state": "Drawing"}))
    before = _paths(ui)
    ui.click("#m2-run")
    ui.locator("#m2-cancel").wait_for(state="visible")
    ui.click("#m2-cancel")
    ui.wait_for_function("() => document.querySelector('#m2-status')?.textContent.includes('cancelled')")
    assert _paths(ui) == before
    assert ui.locator("#m2-history option").count() == 1
    assert ui.locator("#m2-parts .m2-part").count() == 2
    assert not ui.errors
