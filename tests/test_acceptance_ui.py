"""Acceptance harness: the real UI, in a real browser, against a real server.

These are the contract a UI restructure must not break. They deliberately
assert **what the user sees** — a layer row appears, the swatch takes the
pen's colour, the Plot button is dead until the machine is connected — and
never how it is built. Tests that know about class names and call signatures
fight a redesign; tests that know about outcomes protect one.

Backend-only machines (the Pi) skip the whole module cleanly: no playwright,
or no browser binary, means skip, not fail.

Running them:

    .venv/bin/python -m pytest tests/test_acceptance_ui.py -q

The browser comes from `.venv/bin/python -m playwright install chromium`
(once per machine). One suite, one command — there is no second ecosystem
here on purpose.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sync_playwright = pytest.importorskip(
    "playwright.sync_api", reason="playwright not installed (backend-only machine)"
).sync_playwright

REPO = Path(__file__).resolve().parent.parent
BOOT_TIMEOUT_S = 30.0


# -- the real server ------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def _post(url: str, payload: dict | None = None):
    body = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


@pytest.fixture(scope="session")
def server():
    """A real axibridge on a temp port, with its own config dir — never the
    machine's stores, never port 2942 (Ian's app may be running)."""
    port = _free_port()
    env = {
        **os.environ,
        "AXIBRIDGE_CONFIG_DIR": tempfile.mkdtemp(prefix="axibridge-acceptance-"),
        "AXIBRIDGE_NO_AUTOCONNECT": "1",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "axibridge.app:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + BOOT_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            out = (proc.stdout.read() or b"").decode()[-2000:]
            pytest.fail(f"server exited before it answered:\n{out}")
        try:
            _get(f"{base}/api/state", timeout=1.0)
            break
        except Exception:
            time.sleep(0.15)
    else:
        proc.kill()
        pytest.fail("server never answered /api/state")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def ui(server):
    """A fresh browser and page on an empty project, with console errors
    collected.

    Fresh per test on purpose, twice over. The page, because the headless
    shell ghosts repaints across tab switches and has already produced
    screenshots that looked like real bugs. The BROWSER, because playwright's
    sync API keeps an asyncio loop running on the main thread for as long as
    its context is open — a session-scoped one makes every later
    `asyncio.run()` in the suite raise "cannot be called from a running event
    loop" (it broke tests/test_events_shutdown.py). Launch costs ~0.3 s; a
    suite that only fails when you run all of it costs much more."""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:  # no browser binary on this machine
            pytest.skip(f"no chromium: {str(e)[:120]}")
        _post(f"{server}/api/project/new")
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        # domcontentloaded, never networkidle: the SSE stream never goes idle
        page.goto(server, wait_until="domcontentloaded")
        _wait_ready(page)
        page.errors = errors          # type: ignore[attr-defined]
        page.base = server            # type: ignore[attr-defined]
        yield page
        page.close()
        browser.close()


def _wait_ready(page) -> None:
    """The app has booted when the generator picker has been filled from
    /api/state. `wait_for_selector` can't be used: <option> is never
    "visible" to Playwright."""
    page.wait_for_function(
        "() => document.querySelectorAll('#gen-select option').length > 0",
        timeout=20_000)


def reload_app(page) -> None:
    """Reload and wait for the app to boot again.

    A reload aborts whatever fetches the OLD page had in flight, and an
    aborted fetch surfaces as an unhandled "TypeError: Failed to fetch" —
    the navigation, not the app. Those entries are dropped here and only
    here, narrowly by message, so every other console error (including one
    raised while the NEW page boots) still fails its test."""
    page.reload(wait_until="domcontentloaded")
    _wait_ready(page)
    page.errors[:] = [e for e in page.errors if "Failed to fetch" not in e]


def rows(page) -> int:
    return page.locator("#layer-list .layer-row").count()


def add_layer(page, module: str, params: dict) -> str:
    """Seed geometry through the API — setup, not the thing under test."""
    return _post(f"{page.base}/api/layers/generate",
                 {"module": module, "params": params})["id"]


def select_layer(page, index: int = 0) -> None:
    """Click a row into selection, unless the app already selected it (it does
    that for a freshly created layer) — clicking a selected row deselects it."""
    row = page.locator("#layer-list .layer-row").nth(index)
    if "selected" not in (row.get_attribute("class") or ""):
        row.locator(".lname").click()
    page.wait_for_selector("#layer-detail-panel:not([hidden])", timeout=10_000)
    page.wait_for_function(
        "() => document.querySelectorAll('#layer-detail [id]').length > 0", timeout=10_000)


def canvas_ink(page) -> str:
    """What is actually drawn: every path's `d`, in order."""
    return page.eval_on_selector_all(
        "#canvas path", "els => els.map(e => e.getAttribute('d') || '').join('|')")


def wait_for_ink(page) -> str:
    """A layer row appears as soon as the project loads; the drawing appears
    one resolve later. Asserting on ink without waiting for that is a flake,
    and was one."""
    page.wait_for_function(
        "() => document.querySelectorAll('#canvas path').length > 0", timeout=20_000)
    return canvas_ink(page)


# -- the flows ------------------------------------------------------------

def test_app_loads_with_tabs_and_an_empty_layer_list(ui):
    # case-insensitive: the tabs are uppercased in CSS today and Slice 4's
    # typography pass may sentence-case them. That is a look, not a contract.
    assert [b.inner_text().lower() for b in ui.locator("#tabs button").all()] == \
        ["compose", "plot", "pens", "settings"]
    assert ui.locator("#tabs button.on").inner_text().lower() == "compose"
    assert rows(ui) == 0
    assert ui.locator("#canvas").is_visible()
    assert not ui.errors


def test_layer_list_populates_from_the_project(ui):
    add_layer(ui, "polygon", {"sides": 5, "radius": 25, "filled": True})
    reload_app(ui)
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)
    assert rows(ui) == 1
    assert "Polygon" in ui.locator("#layer-list .layer-row .lname").first.inner_text()
    assert wait_for_ink(ui), "the layer must actually draw something"
    assert not ui.errors


def test_create_select_and_edit_a_generated_layer(ui):
    """The core loop: pick a generator, create it, select it, change a param,
    and see the drawing change."""
    ui.select_option("#gen-select", "polygon")
    ui.wait_for_selector("#gen-form input", timeout=10_000)
    ui.click("#btn-generate")
    ui.wait_for_selector("#layer-list .layer-row", timeout=20_000)
    assert rows(ui) == 1
    before = wait_for_ink(ui)

    select_layer(ui)
    assert ui.locator("#layer-list .layer-row.selected").count() == 1

    # A layer made from the Generate panel stays LATCHED there — its params
    # keep one editor, in the panel, rather than a second copy in the layer
    # detail that would drift. So the edit goes where the user's does.
    assert ui.locator("#regen-form").count() == 0, "latched: no second param editor"
    radius = ui.locator('#gen-form input[type="number"]').nth(1)
    radius.fill(str(float(radius.input_value() or 20) + 18))
    radius.press("Enter")
    ui.wait_for_function(
        "([sel, old]) => Array.from(document.querySelectorAll(sel))"
        ".map(e => e.getAttribute('d') || '').join('|') !== old",
        arg=["#canvas path", before], timeout=20_000)
    assert canvas_ink(ui) != before, "editing a param must change the preview"
    assert rows(ui) == 1, "a latched edit regenerates the layer, never adds one"
    assert not ui.errors


def test_edit_a_param_on_a_layer_loaded_from_a_project(ui):
    """The other half of the loop: a layer that was NOT just created from the
    bench edits through its own detail form."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 20, "filled": True})
    reload_app(ui)
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)
    before = wait_for_ink(ui)
    select_layer(ui)

    ui.wait_for_selector("#regen-form", timeout=10_000)
    field = ui.locator('#regen-form input[type="number"]').nth(1)
    field.fill(str(float(field.input_value() or 20) + 18))
    field.press("Enter")
    ui.click("#btn-regen")
    ui.wait_for_function(
        "([sel, old]) => Array.from(document.querySelectorAll(sel))"
        ".map(e => e.getAttribute('d') || '').join('|') !== old",
        arg=["#canvas path", before], timeout=20_000)
    assert rows(ui) == 1
    assert not ui.errors


def test_pen_assignment_shows_on_the_layer_row(ui):
    """The swatch is how you tell, at a glance, which pen a layer will draw
    with — it has to follow the assignment."""
    pen = _post(f"{ui.base}/api/pens", {
        "name": "acceptance red", "color": "#cc2200",
        "barrel_diameter_mm": 9.0, "line_diameter_mm": 0.5})
    pen_id = pen["id"] if isinstance(pen, dict) and "id" in pen else pen[0]["id"]
    add_layer(ui, "polygon", {"sides": 4, "radius": 20})
    reload_app(ui)
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)

    select_layer(ui)
    ui.wait_for_selector("#ld-pen", timeout=10_000)
    ui.select_option("#ld-pen", pen_id)
    ui.wait_for_function(
        "() => { const s = document.querySelector('#layer-list .layer-row .swatch');"
        "return s && /204|cc2200/i.test(getComputedStyle(s).backgroundColor + s.style.background); }",
        timeout=15_000)
    swatch = ui.locator("#layer-list .layer-row .swatch").first
    assert "204, 34, 0" in swatch.evaluate("e => getComputedStyle(e).backgroundColor")
    assert not ui.errors


def test_plot_button_is_dead_until_the_machine_is_connected(ui):
    """The most expensive lie this UI could tell is an enabled Plot button on
    a machine that isn't there."""
    add_layer(ui, "polygon", {"sides": 6, "radius": 30})
    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_selector("#btn-plot", timeout=10_000)
    assert ui.locator("#btn-plot").is_disabled(), "disconnected: Plot must be dead"

    assert ui.locator("#plot-target option").count() >= 1
    ui.click("#btn-connect")
    ui.wait_for_function(
        "() => !document.querySelector('#btn-plot').disabled", timeout=20_000)
    assert ui.locator("#btn-plot").is_enabled(), "connected + idle: Plot must be live"
    assert not ui.errors


def test_plot_target_lists_the_whole_document_and_each_layer(ui):
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    add_layer(ui, "lissajous", {"size": 80, "margin": 5})
    reload_app(ui)
    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_function(
        "() => document.querySelectorAll('#plot-target option').length > 0",
        timeout=10_000)
    labels = ui.eval_on_selector_all(
        "#plot-target option", "els => els.map(e => e.textContent.trim())")
    assert any("all" in t.lower() for t in labels), labels
    assert len(labels) >= 3, f"whole document + one entry per layer: {labels}"
    assert not ui.errors


def test_panel_collapse_survives_a_reload(ui):
    head = ui.locator("#tab-compose .panel > h2").first
    title = head.inner_text()
    assert "collapsed" not in (head.evaluate("e => e.parentElement.className") or "")
    head.click()
    ui.wait_for_function(
        "t => [...document.querySelectorAll('#tab-compose .panel > h2')]"
        ".find(h => h.innerText === t)?.parentElement.classList.contains('collapsed')",
        arg=title, timeout=5_000)

    reload_app(ui)
    still = ui.evaluate(
        "t => [...document.querySelectorAll('#tab-compose .panel > h2')]"
        ".find(h => h.innerText === t)?.parentElement.classList.contains('collapsed')",
        title)
    assert still, "a collapsed panel must stay collapsed across a reload"
    assert not ui.errors


def test_view_toggle_changes_the_display_only(ui):
    """View rotation is display-only — the invariant the whole orientation
    design rests on. The drawing turns; the geometry does not."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 30, "filled": True})
    reload_app(ui)
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)
    resolved_before = _get(f"{ui.base}/api/compose/resolved")["layers"]
    ink_before = wait_for_ink(ui)

    ui.click('.menu[data-menu="view"] .menu-trigger')
    ui.click('#view-toggle button[data-view="landscape"]')
    ui.wait_for_function(
        "() => document.querySelector('#canvas g')?.getAttribute('transform') === null",
        timeout=15_000)

    assert _get(f"{ui.base}/api/compose/resolved")["layers"] == resolved_before, \
        "the view toggle must not touch resolved geometry"
    assert canvas_ink(ui) == ink_before, "same paths, drawn through a different frame"
    assert not ui.errors


def test_no_console_errors_on_any_tab(ui):
    """A JS error on a tab you rarely open is a bug you find mid-plot."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    reload_app(ui)
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)
    for tab in ("compose", "plot", "pens", "settings"):
        ui.click(f'#tabs button[data-tab="{tab}"]')
        ui.wait_for_timeout(700)
        assert ui.locator(f"#tab-{tab}").is_visible(), f"{tab} tab must render"
    assert not ui.errors, f"console errors: {ui.errors[:5]}"
