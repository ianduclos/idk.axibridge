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
import re
import shutil
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


@pytest.fixture(scope="session")
def frontend_mode() -> str:
    """Build the frontend before anything starts, so these tests exercise the
    BUNDLE and not the source.

    This is the point of running them at all after the Vite port: the
    works-in-dev-broken-in-build class only shows up against real bundled
    output. Without a node toolchain (the Pi) the server falls back to the
    source and the tests still run — they just cover less, and
    ``test_the_acceptance_suite_runs_against_the_built_frontend`` says so."""
    if shutil.which("npm") is None or not (REPO / "node_modules").is_dir():
        return "source"
    r = subprocess.run(["npm", "run", "build"], cwd=REPO,
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"npm run build failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return "built"


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


def _patch(url: str, payload: dict):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="PATCH",
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _put(url: str, payload: dict):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="PUT",
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


@pytest.fixture(scope="session")
def server(frontend_mode):
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


def select_layer_named(page, text: str) -> None:
    """Like select_layer, but by row text — for keyframe sublayers
    ('… ▸ A' / '… ▸ B'), which aren't at a fixed list index."""
    row = page.locator("#layer-list .layer-row", has_text=text)
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


def animate_and_follow(page, layer_id: str, b_radius: float = 60) -> None:
    """Turn a plain layer into a follow_master A/B animation whose two
    keyframes actually differ (B's radius moves), so scrubbing has visible
    geometry to prove it changed. Setup via the API, not the UI — the UI is
    the thing under test."""
    _post(f"{page.base}/api/layers/{layer_id}/animate")
    project = _get(f"{page.base}/api/project")
    tw = next(l for l in project["layers"] if l["source"]["type"] == "tween")
    b_id = tw["source"]["params"]["b"]
    _post(f"{page.base}/api/layers/{b_id}/regenerate",
          {"params": {"sides": 5, "radius": b_radius}, "coalesce": False})
    _put(f"{page.base}/api/layers/{tw['id']}/tween", {"follow_master": True})


def timeline_bar_scrub_to(page, t: float) -> None:
    """Drag the bar's scrub track to `t` the way a user would: set the
    range input's value and fire the same events the browser fires on a
    real drag (input while moving, change on release)."""
    page.eval_on_selector(
        "#tl-scrub",
        "(el, t) => { el.value = String(t); "
        "el.dispatchEvent(new Event('input', {bubbles: true})); }",
        t)


# -- what is actually under test ------------------------------------------

def test_the_acceptance_suite_runs_against_the_built_frontend(ui, frontend_mode):
    """Proof, not assumption: the served index must be the bundled one."""
    html = urllib.request.urlopen(ui.base, timeout=10).read().decode()
    if frontend_mode != "built":
        pytest.skip("no node toolchain here — the server is serving the source")
    assert "/assets/index-" in html, "expected Vite's hashed entry"
    assert "/js/main.js" not in html, "unbundled source leaked into the build"
    # and the one URL that must survive bundling untouched: it is a server
    # route, not an asset
    assert "/api/doc/all/svg" in html


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


def test_dragging_a_generator_slider_repaints_live_and_lands_one_undo_entry(ui):
    """E4: generator params on an EXISTING (non-latched) layer must update the
    canvas live the way effect params already do — no #btn-regen click in
    this test at all — and the whole multi-release drag run coalesces into
    ONE undo entry, exactly like the bench latch."""
    add_layer(ui, "polygon", {"sides": 3, "radius": 20, "filled": True})
    reload_app(ui)
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)
    before = wait_for_ink(ui)
    select_layer(ui)
    ui.wait_for_selector("#regen-form", timeout=10_000)

    def drag(target):
        # a few 'input' frames (ghost only) then one 'change' (release, the
        # real regenerate) — what forms.js's range control actually fires
        # while the mouse is down and then let go.
        slider = ui.locator('#regen-form input[type="range"]').nth(1)  # radius
        for v in range(30, target, 15):
            slider.evaluate(
                "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); }", v)
        slider.evaluate(
            "(el, v) => { el.value = v; el.dispatchEvent(new Event('change', {bubbles: true})); }", target)

    drag(60)
    ui.wait_for_function(
        "([sel, old]) => Array.from(document.querySelectorAll(sel))"
        ".map(e => e.getAttribute('d') || '').join('|') !== old",
        arg=["#canvas path", before], timeout=20_000)
    assert rows(ui) == 1, "auto-apply regenerates the layer, never adds one"
    mid = canvas_ink(ui)

    # a second, separate drag/release in the same editing session — the
    # coalesce key folds this into the SAME undo entry as the first drag
    drag(120)
    ui.wait_for_function(
        "([sel, old]) => Array.from(document.querySelectorAll(sel))"
        ".map(e => e.getAttribute('d') || '').join('|') !== old",
        arg=["#canvas path", mid], timeout=20_000)

    # ONE undo restores all the way back to the pre-drag radius (20), not to
    # the first drag's intermediate 60 — proof the whole run is one entry.
    ui.click('.menu[data-menu="edit"] .menu-trigger')
    ui.click("#btn-undo")
    ui.wait_for_function(
        "() => { const n = document.querySelectorAll('#regen-form input[type=\"number\"]')[1];"
        " return n && Number(n.value) === 20; }", timeout=10_000)
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


def test_every_native_menu_item_hits_exactly_one_live_control(ui):
    """The system menu bar is built from selectors parsed out of the markup —
    so a selector that parses but matches nothing is a menu row that does
    nothing, and only the app shell would ever show it.

    This is the half `tests/test_menu_spec.py` cannot do: it checks the
    markup's shape, this checks the shape against a running page."""
    from axibridge.menu_spec import menu_spec

    dead, ambiguous = [], []
    for menu in menu_spec():
        for item in menu.actions:
            n = ui.eval_on_selector_all(item.selector, "els => els.length")
            if n == 0:
                dead.append(f"{menu.title} > {item.label} ({item.selector})")
            elif n > 1:
                ambiguous.append(f"{menu.title} > {item.label} matches {n}")
    assert not dead, f"menu items addressing nothing: {dead}"
    assert not ambiguous, f"menu items addressing more than one control: {ambiguous}"
    assert not ui.errors


def test_the_generated_state_probe_runs_and_tells_the_truth(ui):
    """The app shell ticks its native menu from a JS expression GENERATED in
    Python (`menu_spec.state_probe_js`). Generated code that is subtly wrong
    fails in a window with no console, so it gets run against a real page
    here, and checked against a state the test actually changes."""
    from axibridge.menu_spec import item_index, state_probe_js

    add_layer(ui, "polygon", {"sides": 3, "radius": 20})
    reload_app(ui)
    wait_for_ink(ui)

    states = ui.evaluate(f"() => ({state_probe_js()})")
    assert set(states) == set(item_index()), "the probe reports every menu item"
    assert all(set(v) == {"on", "enabled"} for v in states.values())

    portrait = '#view-toggle button[data-view="portrait"]'
    landscape = '#view-toggle button[data-view="landscape"]'

    def group(states, prefix):
        return sum(bool(v["on"]) for k, v in states.items() if k.startswith(prefix))

    # a radio group has exactly one on; the overlay checkboxes are free
    assert group(states, "#view-toggle") == 1, f"one orientation: {states}"
    assert group(states, "#mode-toggle") == 1, f"one render mode: {states}"
    assert states["#show-guide"]["on"] is True, "paper guide ships on"
    assert states["#btn-undo"]["on"] is None, "an action has no tick to report"

    # Availability is the half that makes the Machine menu honest: its buttons
    # are disabled until the plotter is connected, and the menu must say so.
    # Asserted against the LIVE elements rather than against an expected
    # machine state — the server fixture is session-scoped, so whether
    # anything is connected depends on which tests ran first, and a test that
    # depends on that tests the order rather than the probe.
    truth = ui.evaluate(
        "(sels) => Object.fromEntries(sels.map(s =>"
        " [s, !document.querySelector(s).disabled]))",
        list(states))
    assert {k: v["enabled"] for k, v in states.items()} == truth, \
        "the probe's availability must be the elements' own"

    was = states[portrait]["on"]
    ui.click('.menu[data-menu="view"] .menu-trigger')
    ui.click(landscape if was else portrait)
    ui.wait_for_timeout(600)

    after = ui.evaluate(f"() => ({state_probe_js()})")
    assert after[portrait]["on"] != was, "the probe follows the control it names"
    assert group(after, "#view-toggle") == 1
    assert not ui.errors


def test_the_page_reports_menu_state_to_the_shell(ui):
    """The app shell's native checkmarks come from the page calling
    `menu_changed(states)`. That call only happens where `window.pywebview`
    exists, so it is invisible to every other test here — and it has already
    shipped once doing nothing at all.

    So the bridge is faked exactly as pywebview installs it, and the probe is
    injected exactly as the shell injects it. What is asserted is the payload
    the shell would receive: it must arrive at boot (a menu opened before you
    touch anything still has to be right) and it must follow the control."""
    from axibridge.menu_spec import item_index, state_probe_js

    add_layer(ui, "polygon", {"sides": 6, "radius": 25})
    ui.add_init_script(
        "window.__pings = [];"
        "window.pywebview = { api: { menu_changed: (s) => window.__pings.push(s) } };"
        f"window.__axbMenuProbe = () => ({state_probe_js()});")
    reload_app(ui)
    wait_for_ink(ui)

    pings = ui.evaluate("() => window.__pings")
    assert pings, "the page never told the shell anything — no ticks would ever appear"
    assert set(pings[0]) == set(item_index())
    assert sum(bool(v["on"]) for k, v in pings[0].items()
               if k.startswith("#view-toggle")) == 1, f"one orientation on: {pings[0]}"

    portrait = '#view-toggle button[data-view="portrait"]'
    was = pings[0][portrait]["on"]
    ui.click('.menu[data-menu="view"] .menu-trigger')
    ui.click('#view-toggle button[data-view="landscape"]' if was else portrait)
    ui.wait_for_function("() => window.__pings.length > 1", timeout=15_000)

    assert ui.evaluate("() => window.__pings.at(-1)")[portrait]["on"] != was, \
        "the report followed the click"
    assert not ui.errors


def test_view_menu_overlays_drive_the_canvas(ui):
    """The canvas overlays live in the View menu now, not the toolbar — and
    ticking one still changes what is on the sheet.

    This asserts the OUTCOME (travel moves appear over the drawing), not that
    a checkbox flipped, because the interesting failure when a control is
    moved is precisely that its face still works and its wiring no longer
    does. Paper guide is checked at rest, which is what proves the tick
    reflects the control's real state rather than clicks it has seen."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 30})
    reload_app(ui)
    wait_for_ink(ui)

    ui.click('.menu[data-menu="view"] .menu-trigger')
    assert ui.is_checked("#show-guide"), "paper guide is on at rest"
    assert not ui.is_checked("#show-travel")

    travel = "#canvas g polyline"
    before = ui.locator(travel).count()
    ui.click('.menu[data-menu="view"] label:has(#show-travel)')
    ui.wait_for_function(
        f"() => document.querySelectorAll('{travel}').length > {before}", timeout=15_000)

    ui.click('.menu[data-menu="view"] .menu-trigger')
    assert ui.is_checked("#show-travel"), "the menu row drives the real control"
    assert not ui.errors


def test_view_menu_render_mode_is_a_radio_choice(ui):
    """Schematic/Ink moved into the same menu as a two-item radio group: one
    is always marked, never both, and the mark follows the click."""
    add_layer(ui, "polygon", {"sides": 4, "radius": 25})
    reload_app(ui)
    wait_for_ink(ui)

    marked = lambda: ui.eval_on_selector_all(
        "#mode-toggle .menu-item",
        "els => els.filter(e => e.classList.contains('on')).map(e => e.dataset.mode)")

    ui.click('.menu[data-menu="view"] .menu-trigger')
    assert marked() == ["schematic"]
    ui.click('.menu[data-menu="view"] [data-mode="ink"]')
    ui.click('.menu[data-menu="view"] .menu-trigger')
    assert marked() == ["ink"], "exactly one mode is marked, and it is the one clicked"
    assert not ui.errors


def test_ab_capture_series_still_works_from_the_plot_tab(ui):
    """The A/B/⇄ cluster left the canvas toolbar for Plot › Staging, where the
    rest of staging lives. It carries a live step count, so by the menu rule
    it belongs in a panel and not in a menu.

    The move is the risk: `#tab-plot` is rebuilt by innerHTML on every project
    refresh, and A/B is browser-side state naming two staging groups on the
    server. If the rebuild lost the binding or the lit letters, the flow would
    look fine right up to the point where ⇄ stayed dead."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 30})
    reload_app(ui)
    wait_for_ink(ui)

    assert ui.query_selector("#canvas-toolbar #ab-capture") is None, "left the toolbar"
    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_selector("#tab-plot #ab-capture", timeout=10_000)
    assert ui.is_disabled("#ab-series"), "dead until both captures exist"

    ui.click("#cap-a")
    ui.wait_for_function(
        "() => document.querySelector('#cap-a')?.classList.contains('on')", timeout=20_000)
    assert ui.is_disabled("#ab-series"), "still dead with only A"

    add_layer(ui, "rectangle", {})          # change something between captures
    ui.click("#cap-b")
    ui.wait_for_function(
        "() => !document.querySelector('#ab-series')?.disabled", timeout=20_000)
    assert "on" in (ui.get_attribute("#cap-a", "class") or ""), \
        "A survived the tab rebuild that capturing B triggers"

    before = len(_get(f"{ui.base}/api/state")["project"]["staging"])
    ui.fill("#ab-steps", "4")
    ui.click("#ab-series")
    deadline = time.time() + 30
    sheets = []
    while time.time() < deadline:
        groups = _get(f"{ui.base}/api/state")["project"]["staging"]
        sheets = [len(g.get("sheets", [])) for g in groups]
        if len(groups) > before and 4 in sheets:
            break
        time.sleep(0.3)
    assert 4 in sheets, f"⇄ never produced a 4-sheet series; sheet counts {sheets}"
    assert not ui.errors


def test_the_toolbar_shows_only_the_active_tool_s_controls(ui):
    """The brush and pen bars are contextual: they belong to a tool, and
    offering an Erase width while Select is active describes a tool you are
    not holding.

    They carry `hidden`, and carried it all along — but `.seg` sets `display`,
    and a class rule outranks the UA's `[hidden] { display: none }`, so they
    showed anyway. Asserting on VISIBILITY rather than on the attribute is the
    whole point: the attribute was always right."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 25})
    reload_app(ui)
    wait_for_ink(ui)

    assert not ui.is_visible("#brush-bar"), "no brush controls without the brush tool"
    assert not ui.is_visible("#pen-bar")
    assert not ui.is_visible("#pen-commit")

    ui.click('#tool-toggle button[data-tool="brush"]')
    ui.wait_for_selector("#brush-bar:not([hidden])", timeout=10_000)
    assert ui.is_visible("#brush-bar"), "the brush tool brings its own controls"
    assert not ui.is_visible("#pen-bar"), "and only its own"

    ui.click('#tool-toggle button[data-tool="select"]')
    ui.wait_for_function(
        "() => !document.querySelector('#brush-bar')?.offsetParent", timeout=10_000)
    assert not ui.is_visible("#brush-bar"), "and takes them away again"
    assert not ui.errors


def test_playback_appears_only_when_there_is_a_job_to_replay(ui):
    """Animate + speed left the tool row for a strip under the sheet it
    replays, and it is absent when there is nothing to play.

    The gate is `plan.moves.length` — the same condition
    `canvas.startAnimation` guards on — so the strip can never offer a play the
    canvas would decline. Asserted from both ends: an empty project, and a
    project whose every layer has been hidden."""
    reload_app(ui)
    ui.wait_for_selector("#playback", state="attached", timeout=10_000)
    assert ui.query_selector("#canvas-toolbar #btn-animate") is None, "left the toolbar"
    assert not ui.is_visible("#playback"), "nothing to replay in an empty project"

    add_layer(ui, "polygon", {"sides": 5, "radius": 30})
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#playback:not([hidden])", timeout=20_000)

    ui.fill("#anim-speed", "1")          # ×20 finishes a pentagon before you can look
    ui.click("#btn-animate")
    ui.wait_for_function(
        "() => document.querySelector('#btn-animate').textContent.includes('Stop')",
        timeout=15_000)
    ui.click("#btn-animate")
    ui.wait_for_function(
        "() => document.querySelector('#btn-animate').textContent.includes('Animate')",
        timeout=15_000)

    ui.eval_on_selector_all(".layer-row .eye", "els => els.forEach(e => e.click())")
    ui.wait_for_function(
        "() => document.querySelector('#playback')?.hidden === true", timeout=20_000)
    assert not ui.errors


def test_the_canvas_top_edge_does_not_move_when_the_window_resizes(ui):
    """The reason the toolbar was emptied. It used to wrap to three rows, and
    every row it wrapped to pushed the sheet down while you resized.

    Measured, not asserted structurally: the toolbar's height and the canvas
    well's top are read at each width. Stops at 900px — below that the header
    itself wraps (a separate control, and by then the canvas is ~260px and
    unusable), which is a known residual rather than something this hides."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 30})
    reload_app(ui)
    wait_for_ink(ui)

    heights, tops = set(), set()
    for width in (1600, 1400, 1200, 1100, 1000, 900):
        ui.set_viewport_size({"width": width, "height": 900})
        ui.wait_for_timeout(250)
        heights.add(round(ui.eval_on_selector(
            "#canvas-toolbar", "el => el.getBoundingClientRect().height")))
        tops.add(round(ui.eval_on_selector(
            "#canvas-wrap", "el => el.getBoundingClientRect().top")))

    assert len(heights) == 1, f"the toolbar changed height: {sorted(heights)}"
    assert len(tops) == 1, f"the canvas top edge moved: {sorted(tops)}"
    assert not ui.errors


def test_the_machine_panels_left_the_plot_tab(ui):
    """Plot had ten panels and five of them were about the machine rather than
    about running a plot, which buried Staging five deep. They are in Settings
    now — built by plot.js, whose handlers they are, but appended there.

    The ordering this depends on is the fragile part: `initSettingsTab` must
    run BEFORE `initPlotTab`, or Settings' own innerHTML overwrites the
    appended panels and every machine control silently disappears. Counting
    both tabs is what catches that."""
    reload_app(ui)
    # attached, not visible: an inactive tab body is `hidden`, and the panels
    # are built into it whether or not you are looking at it (same family as
    # the <option>-is-never-visible gotcha in CLAUDE.md)
    ui.wait_for_selector("#tab-settings .panel", state="attached", timeout=15_000)

    def panels(tab):
        return ui.eval_on_selector_all(
            f"#{tab} .panel > h2", "els => els.map(e => e.firstChild.textContent.trim())")

    plot, settings = panels("tab-plot"), panels("tab-settings")
    assert len(plot) == 5, f"Plot should hold only plotting: {plot}"
    assert "Staging" in plot
    for name in ("Motion parameters", "Pen & origin", "Raw EBB", "Soft limits",
                 "Holder calibration"):
        assert any(name in p for p in settings), f"{name} lost on the way: {settings}"
    assert not ui.errors


def test_the_machine_menu_drives_the_real_controls(ui):
    """Every Machine item names a button that lives in Settings › Pen & origin
    (`data-target`), and clicking the item clicks that button.

    Without the forward it would click itself — a menu that appears to work and
    drives nothing. The targets are disabled with no machine connected and a
    disabled button swallows `.click()`, so they are enabled here: what is
    under test is the wiring, not the plotter."""
    reload_app(ui)
    ui.wait_for_selector('.menu[data-menu="machine"]', timeout=15_000)

    ui.evaluate("""() => {
        window.__hit = [];
        for (const id of ['btn-pen-up', 'btn-goto-origin']) {
          const el = document.getElementById(id);
          el.disabled = false;
          el.addEventListener('click', (e) => { e.stopPropagation(); window.__hit.push(id); },
                              { capture: true });
        }
    }""")
    for target in ("#btn-pen-up", "#btn-goto-origin"):
        ui.click('.menu[data-menu="machine"] .menu-trigger')
        ui.click(f'.menu[data-menu="machine"] [data-target="{target}"]')
        ui.wait_for_timeout(200)

    assert ui.evaluate("() => window.__hit") == ["btn-pen-up", "btn-goto-origin"]


def test_machine_state_is_visible_without_opening_a_tab(ui):
    """Position, pen, progress, time left and Stop, in the status line that is
    always on screen — previously all of it needed the Plot tab open, which is
    the wrong place to go looking when a machine is moving.

    Runs a real job on the simulator rather than asserting the wiring: the
    interesting failure is a readout that never updates. Disconnects at the
    end because the server fixture is session-scoped."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 60})
    # establish the precondition rather than assume it: the server fixture is
    # session-scoped, so whether anything is connected depends on which tests
    # ran first, and asserting on that tests the ordering
    _post(f"{ui.base}/api/disconnect", {})
    reload_app(ui)
    wait_for_ink(ui)

    assert not ui.is_visible("#machine-state"), "nothing to report while disconnected"
    # the estimate arrives on a debounced /api/plan, one beat after the ink
    ui.wait_for_function(
        "() => document.querySelector('#estimate').textContent.includes('est.')",
        timeout=20_000)
    estimate = ui.inner_text("#estimate")

    try:
        _post(f"{ui.base}/api/backend/select", {"backend": "simulator"})
        _post(f"{ui.base}/api/connect", {})
        ui.wait_for_function(
            "() => !document.querySelector('#machine-state').hidden", timeout=20_000)
        assert ui.is_visible("#btn-stop"), "stop is reachable from any tab"

        _post(f"{ui.base}/api/plot/start", {"target": "all"})
        ui.wait_for_function(
            "() => (document.querySelector('#job-progress').textContent || '')"
            ".includes('%')", timeout=30_000)

        assert "left" in ui.inner_text("#job-remaining")
        assert ui.inner_text("#pos-xy").startswith("X ")
        assert ui.inner_text("#pen-state") in ("pen up", "pen down")

        # the bug this slice names: `remaining` used to be written OVER the
        # est/ink/lifts readout, which is a fact about the job you asked for
        # and stays true while it runs — and it was never restored afterwards
        assert ui.inner_text("#estimate") == estimate, \
            "the job estimate must survive the job"

        ui.click("#btn-stop")
        ui.wait_for_function(
            "() => document.querySelector('#job-progress').textContent.trim() === ''",
            timeout=20_000)
    finally:
        _post(f"{ui.base}/api/disconnect", {})

    assert not ui.errors


def _layer_names(page):
    """Draw order, bottom-first — the server's own order, not the screen's."""
    return [l["name"] for l in _get(f"{page.base}/api/state")["project"]["layers"]]


def _rename(page, index, to):
    page.locator("#layer-list .layer-row .lname").nth(index).dblclick()
    page.wait_for_selector(".lname-edit", timeout=10_000)
    page.fill(".lname-edit", to)
    page.keyboard.press("Enter")
    page.wait_for_function(
        f"() => !document.querySelector('.lname-edit')", timeout=10_000)


def test_renaming_a_layer_happens_in_place(ui):
    """Was a native `prompt()`: modal, blockable by the browser (a rename that
    silently does nothing), and it loses the row you were looking at.

    The interesting part is that it is driven by the click COUNTER, not by
    `dblclick`. The first click selects the layer, which starts an async
    refresh that rebuilds the row — so the second click lands on a different
    element and the browser never pairs them into a dblclick. Escape must
    leave the old name alone."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    reload_app(ui)
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)

    _rename(ui, 0, "outline")
    ui.wait_for_function(
        "() => [...document.querySelectorAll('#layer-list .lname')]"
        ".some(e => e.textContent === 'outline')", timeout=15_000)
    assert "outline" in _layer_names(ui)

    ui.locator("#layer-list .layer-row .lname").nth(0).dblclick()
    ui.wait_for_selector(".lname-edit", timeout=10_000)
    ui.fill(".lname-edit", "discard me")
    ui.keyboard.press("Escape")
    ui.wait_for_function("() => !document.querySelector('.lname-edit')", timeout=10_000)
    assert "discard me" not in _layer_names(ui), "Escape must not commit"
    assert not ui.errors


def test_dragging_a_layer_reorders_it(ui):
    """Replaces the per-row ↑ ↓: moving a layer across fifteen cost fourteen
    clicks and fourteen resolves, because each was its own reorder round-trip.

    The list is drawn TOP-FIRST (the topmost layer draws last and occludes),
    so screen order is the reverse of the server's. Dragging the top row below
    the bottom one must land it FIRST in draw order — getting that reversal
    wrong is the whole risk, and asserting "the order changed" would not catch
    it."""
    for _ in range(3):
        add_layer(ui, "polygon", {"sides": 4, "radius": 20})
    reload_app(ui)
    ui.wait_for_function(
        "() => document.querySelectorAll('#layer-list .layer-row').length === 3",
        timeout=15_000)

    for i, name in enumerate(("A", "B", "C")):     # A is topmost on screen
        _rename(ui, i, name)
    assert _layer_names(ui) == ["C", "B", "A"], "draw order is the screen's reverse"

    rows = ui.locator("#layer-list .layer-row")
    height = rows.nth(2).bounding_box()["height"]
    # Playwright's raw mouse events do not drive HTML5 drag-and-drop; drag_to
    # does. Landing low in the last row means "drop below it".
    rows.nth(0).drag_to(rows.nth(2), target_position={"x": 40, "y": height - 3})

    ui.wait_for_function(
        "() => [...document.querySelectorAll('#layer-list .lname')]"
        ".map(e => e.textContent).join() === 'B,C,A'", timeout=15_000)
    assert _layer_names(ui) == ["A", "C", "B"], "A moved to the bottom of the screen list"
    assert not ui.errors


def test_the_layer_list_belongs_to_the_compose_tab(ui):
    """The dock is Compose furniture (Ian, 2026-08-08): visible while you are
    composing, out of the way on the three tabs where you are not. It was
    reachable from all four for a while and that just cost 240px of sidebar.

    Two things it must NOT do while changing scope: live inside a tab body
    (innerHTML rebuilds on project load would eat it), and exist twice. Two
    lists is the drift bug this repo spent a day removing from the menus; the
    same mistake here would be a layer list that disagrees with itself."""
    for _ in range(3):
        add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    reload_app(ui)
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)

    assert ui.eval_on_selector_all("#layer-list", "els => els.length") == 1
    assert ui.eval_on_selector("#layer-list", "el => !el.closest('.tab-body')"), \
        "the list must not live inside a tab body"
    assert ui.eval_on_selector("#btn-empty-layer", "el => !!el.closest('#tab-compose')"), \
        "making a layer stays a Compose act"

    assert ui.is_visible("#layers-dock"), "Compose is the default tab; the dock shows"
    assert ui.locator("#layer-list .layer-row").count() == 3

    for tab in ("plot", "pens", "settings"):
        ui.click(f'#tabs button[data-tab="{tab}"]')
        assert not ui.is_visible("#layers-dock"), f"the dock followed you to {tab}"

    # and it comes back, with the list still in it and still selectable
    ui.click('#tabs button[data-tab="compose"]')
    assert ui.is_visible("#layers-dock")
    ui.locator("#layer-list .layer-row .lname").first.click()
    ui.wait_for_function(
        "() => document.querySelectorAll('#layer-list .layer-row.selected').length === 1",
        timeout=10_000)
    assert not ui.errors


def test_the_layers_dock_remembers_how_you_left_it(ui):
    """Collapse and height are per-machine preferences: they belong in
    localStorage, never in the project, and they must survive a reload or the
    dock is furniture you have to rearrange every time."""
    add_layer(ui, "polygon", {"sides": 4, "radius": 20})
    reload_app(ui)
    ui.wait_for_selector("#layers-dock", timeout=15_000)

    ui.click("#layers-dock-title")
    ui.wait_for_function(
        "() => document.querySelector('#layers-dock').classList.contains('collapsed')",
        timeout=10_000)
    assert not ui.is_visible("#layers-dock-body")

    reload_app(ui)
    ui.wait_for_selector("#layers-dock", timeout=15_000)
    assert not ui.is_visible("#layers-dock-body"), "collapsed state was forgotten"

    ui.click("#layers-dock-title")
    ui.wait_for_selector("#layers-dock-body", timeout=10_000)
    assert ui.is_visible("#layer-list"), "and it comes back with the list in it"
    assert not ui.errors


def test_keyframe_sublayers_share_collapse_state_and_scroll_on_ab_switch(ui):
    """E5: an "⏱ Animate" A/B pair reads as ONE editable thing — expand a
    param subsection and scroll on A, switch to B, and both must already
    match. Sets the same effect on the layer BEFORE animating so A and B
    start with an identical effects list at the same index (the family-keyed
    state — compose.js's familyKey() — is exercised the same way either
    keyframe is picked first)."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20, "filled": True})
    effect_mod = next(m for m in _get(f"{ui.base}/api/state")["modules"]["effects"]
                       if m["id"] == "smoothen")
    _patch(f"{ui.base}/api/layers/{layer_id}",
           {"effects": [{"effect": "smoothen", "enabled": True, "params": effect_mod["defaults"]}]})
    _post(f"{ui.base}/api/layers/{layer_id}/animate")
    reload_app(ui)
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)

    select_layer_named(ui, "▸ A")
    ui.wait_for_selector("#fx-steps .step", timeout=10_000)
    ui.locator("#fx-steps .step .name").first.click()  # expand the smoothen step
    ui.wait_for_selector("#fx-steps .form-group summary", timeout=10_000)
    ui.locator("#fx-steps .form-group summary").first.click()  # expand "Fine tuning"
    ui.wait_for_function(
        "() => document.querySelector('#fx-steps .form-group')?.open === true", timeout=5_000)

    ui.evaluate("() => { document.getElementById('tab-compose').scrollTop = 600; }")
    scroll_pos = ui.evaluate("() => document.getElementById('tab-compose').scrollTop")
    assert scroll_pos > 0, "the panel isn't tall enough to scroll — test doesn't prove anything"

    select_layer_named(ui, "▸ B")
    ui.wait_for_selector("#fx-steps .step", timeout=10_000)
    # same family, different layer id: both must already match — no clicks
    ui.wait_for_function(
        "() => document.querySelector('#fx-steps .form-group')?.open === true", timeout=5_000)
    ui.wait_for_function(
        "(want) => document.getElementById('tab-compose').scrollTop === want",
        arg=scroll_pos, timeout=5_000)
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


# -- S4: the bottom timeline bar --------------------------------------------

def test_timeline_bar_absent_on_a_fresh_static_project(ui):
    """A project nothing follows gets no bar — hidden (zero height), not just
    empty, so a static drawing never pays for a control it can't use."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 30})
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar", state="attached", timeout=10_000)
    assert not ui.is_visible("#timeline-bar"), "bar shows for a project nothing follows"
    assert not ui.errors


def test_timeline_bar_appears_once_a_tween_follows_the_master_timeline(ui):
    """The strict predicate (F5): the bar tracks `follow_master`, in both
    directions — ⏱ Animate defaults a fresh tween to following (so the bar
    is there right away), and unchecking it must hide the bar again."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    _post(f"{ui.base}/api/layers/{layer_id}/animate")
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)
    assert ui.is_visible("#timeline-bar"), "⏱ Animate follows the timeline by default"

    project = _get(f"{ui.base}/api/project")
    tw = next(l for l in project["layers"] if l["source"]["type"] == "tween")
    _put(f"{ui.base}/api/layers/{tw['id']}/tween", {"follow_master": False})
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar", state="attached", timeout=10_000)
    assert not ui.is_visible("#timeline-bar"), "unchecking follow timeline must hide the bar"

    _put(f"{ui.base}/api/layers/{tw['id']}/tween", {"follow_master": True})
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)
    assert ui.is_visible("#timeline-bar")
    assert not ui.errors


def test_timeline_bar_scrub_changes_geometry_without_patching_the_project(ui):
    """Dragging the bar's scrub track re-resolves the canvas (A/B actually
    differ, so t=0 and t=1 must draw differently) while never writing the
    project — the same no-PATCH discipline the old Compose-tab slider had."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)

    timeline_bar_scrub_to(ui, 0)
    ui.wait_for_timeout(300)
    ink_start = wait_for_ink(ui)
    project_before = _get(f"{ui.base}/api/project")

    timeline_bar_scrub_to(ui, 1)
    ui.wait_for_function(
        "(prev) => { const cur = [...document.querySelectorAll('#canvas path')]"
        ".map(e => e.getAttribute('d') || '').join('|'); "
        "return cur.length > 0 && cur !== prev; }",
        arg=ink_start, timeout=10_000)

    project_after = _get(f"{ui.base}/api/project")
    assert project_after == project_before, "scrubbing must never write the project (no PATCH)"
    assert not ui.errors


def test_timeline_bar_frame_steppers_step_the_readout(ui):
    """Next/previous frame reuse plot.js's own frame grid (F6) — clicking
    them must move the bar's own readout, not just the Animation panel's."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)

    ui.click("#tl-next")
    ui.wait_for_function(
        "() => document.getElementById('tl-frame-val').textContent.startsWith('frame 2/')",
        timeout=10_000)
    ui.click("#tl-next")
    ui.wait_for_function(
        "() => document.getElementById('tl-frame-val').textContent.startsWith('frame 3/')",
        timeout=10_000)
    ui.click("#tl-prev")
    ui.wait_for_function(
        "() => document.getElementById('tl-frame-val').textContent.startsWith('frame 2/')",
        timeout=10_000)
    assert not ui.errors


def test_timeline_bar_checkpoint_buttons_degrade_to_none_then_appear_for_a_chain(ui):
    """A classic A/B tween (no `keys`, or `keys` at its 2-endpoint default)
    gets no checkpoint buttons — the bar degrades to just the two ends.
    Growing the tween into a 3-key chain (POST .../chain/keyframe) must make
    exactly one jump button per key appear."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)
    assert not ui.is_visible("#tl-checkpoints"), "a plain A/B tween has no checkpoints to jump to"

    project = _get(f"{ui.base}/api/project")
    tw = next(l for l in project["layers"] if l["source"]["type"] == "tween")
    _post(f"{ui.base}/api/layers/{tw['id']}/chain/keyframe")
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#tl-checkpoints:not([hidden]) button", timeout=10_000)
    assert ui.locator("#tl-checkpoints button").count() == 3, "3 keys → 3 checkpoint buttons"
    assert not ui.errors


# -- S5: frame-grid quantization + cached-frame ticks -------------------------

def test_timeline_bar_scrub_snaps_to_the_frame_grid_by_default(ui):
    """Q3(b)/Q4(a): dragging the bar snaps to the frame grid. The default
    Animation-panel grid is 8 frames over t=0..1 (plot.js's `anim` defaults),
    so the step is 1/7 and frame index 1 (the 2nd frame) sits at t≈0.143 —
    docs/plans/timeline-v2.md's own worked example. A drag that lands near
    but not on that point must snap there exactly, both in the readout and
    in the slider's own committed value."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)

    timeline_bar_scrub_to(ui, 0.16)  # nearest grid point (k=1) is 1/7 ≈ 0.143
    ui.wait_for_function(
        "() => document.getElementById('tl-t-val').textContent === 't = 0.143'",
        timeout=10_000)
    # the slider's own committed value snaps too, not just the readout — bounded
    # by #tl-scrub's own step="0.001" attribute (native to <input type=range>,
    # unrelated to the frame grid's much coarser 1/7 spacing here)
    snapped = float(ui.eval_on_selector("#tl-scrub", "el => el.value"))
    assert abs(snapped - 1 / 7) < 0.001, f"the slider's own value must snap too, got {snapped}"
    assert not ui.errors


def test_timeline_bar_shift_drag_escapes_to_continuous(ui):
    """Q3(b): holding ⇧ during the drag must escape the snap — the one place
    quantization would hide a between-frames morph artefact. t=0.5 is not on
    the default 8-frame/1-7-step grid (0.5*7 = 3.5), so landing there exactly
    proves no snapping happened."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)

    ui.keyboard.down("Shift")
    try:
        timeline_bar_scrub_to(ui, 0.5)
        ui.wait_for_function(
            "() => document.getElementById('tl-t-val').textContent === 't = 0.500'",
            timeout=10_000)
    finally:
        ui.keyboard.up("Shift")
    assert not ui.errors


def test_timeline_bar_shades_the_active_t_from_t_to_range(ui):
    """Q4(a): the bar always spans 0..1; the frame grid's own [tFrom, tTo]
    sub-range is shaded on top of it, so a non-default range stays visible
    and inspectable rather than the (b) option the doc rejected (the bar
    spanning exactly the range, making anything outside it unreachable)."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)

    left0, width0 = ui.eval_on_selector("#tl-shade", "el => [el.style.left, el.style.width]")
    assert (left0, width0) == ("0%", "100%"), "default t-from/t-to (0..1) spans the whole bar"

    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_selector("#anim-panel", timeout=10_000)
    if "collapsed" in (ui.locator("#anim-panel").get_attribute("class") or ""):
        ui.click("#anim-panel > h2")  # collapsed by default (data-collapse-default)
    ui.wait_for_selector("#anim-t-from", timeout=10_000)
    ui.fill("#anim-t-from", "0.2")
    ui.fill("#anim-t-to", "0.8")
    ui.locator("#anim-t-to").dispatch_event("change")

    ui.wait_for_function(
        "() => document.getElementById('tl-shade').style.left === '20%'", timeout=10_000)
    left1, width1 = ui.eval_on_selector("#tl-shade", "el => [el.style.left, el.style.width]")
    assert (left1, width1) == ("20%", "60%")
    assert not ui.errors


def test_timeline_bar_ticks_light_up_for_frames_fetched_this_session(ui):
    """S5: a brighter tick marks a frame whose geometry has been fetched at
    least once this session — a hint (the server's caches evict randomly
    under a point budget), not a guarantee, but it should track real fetches.
    Stepping the bar's own next-frame button three times fetches three
    distinct frames (frame 0 is never itself re-fetched by stepping away
    from it), so at least that many ticks must light."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)
    ui.wait_for_function(
        "() => document.querySelectorAll('#tl-ticks .tick').length > 0", timeout=10_000)
    assert ui.locator("#tl-ticks .tick.fetched").count() == 0, "nothing fetched yet this session"

    for _ in range(3):
        ui.click("#tl-next")
    ui.wait_for_function(
        "() => document.querySelectorAll('#tl-ticks .tick.fetched').length >= 3", timeout=10_000)
    assert not ui.errors


def test_timeline_bar_arrow_keys_step_one_frame(ui):
    """Q3(b): plain arrow keys on the focused slider step one frame — the
    same grid math as the prev/next buttons (F6), not the native 0.001
    per-keypress the input's own `step` attribute would otherwise give."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)

    ui.locator("#tl-scrub").focus()
    ui.locator("#tl-scrub").press("ArrowRight")
    ui.wait_for_function(
        "() => document.getElementById('tl-frame-val').textContent.startsWith('frame 2/')",
        timeout=10_000)
    ui.locator("#tl-scrub").press("ArrowRight")
    ui.wait_for_function(
        "() => document.getElementById('tl-frame-val').textContent.startsWith('frame 3/')",
        timeout=10_000)
    ui.locator("#tl-scrub").press("ArrowLeft")
    ui.wait_for_function(
        "() => document.getElementById('tl-frame-val').textContent.startsWith('frame 2/')",
        timeout=10_000)
    assert not ui.errors


# -- S3: chain UI in the layer detail -----------------------------------------
# docs/plans/timeline-v2.md S3. Screenshots land in the scratchpad dir this
# session used for temp files, named after the test that took them.
_SHOT_DIR = Path("/private/tmp/claude-501/-Users-ianduclos--SecondBrain-02-Areas--Coding-idk-axibridge"
                  "/104f5af6-cb90-4e9e-adfd-fafc78733d09/scratchpad")


def _shoot(page, name: str) -> None:
    _SHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(_SHOT_DIR / name))


# -- render popup (docs/plans/timeline-v2.md §2c, 2026-08-11 bench fixes) ----

def test_render_popup_opens_from_the_compose_tab(ui):
    """THE acceptance case for the §2c popup fix: the popup used to live
    inside the Plot tab's own DOM (built into `#tab-plot`'s innerHTML by
    initPlotTab), so it only ever showed while that tab was active — `hidden`
    on a tab body computes to `display:none` on every descendant, which took
    a `position:fixed` modal down with it. It's now static top-level markup
    in index.html, and the timeline bar's Render-popup button (#tl-render,
    live on every tab once anything follows the master timeline) must open
    it regardless of which tab is showing — Compose is the tab Ian actually
    hit it from on the bench."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)

    assert ui.locator("#tabs button.on").inner_text().lower() == "compose", \
        "Compose is the default tab — the acceptance case starts here"
    assert ui.locator("#tab-compose").is_visible()

    ui.click("#tl-render")
    ui.wait_for_selector("#anim-preview-modal:not([hidden])", timeout=10_000)
    assert ui.is_visible("#anim-preview-modal"), \
        "the render popup must open over the Compose tab, not just the Plot tab"
    # underneath, Compose is still the active tab — the popup is an overlay
    # on top of it, not a tab switch
    assert ui.locator("#tabs button.on").inner_text().lower() == "compose"

    ui.wait_for_function(
        "() => !document.getElementById('anim-preview-img').hidden", timeout=30_000)
    _shoot(ui, "render-popup-over-compose-tab.png")

    ui.click("#anim-preview-close")
    ui.wait_for_function(
        "() => document.getElementById('anim-preview-modal').hidden", timeout=5_000)
    assert not ui.errors


def test_render_popup_resolution_change_rerenders_and_labels_actual_size(ui):
    """2026-08-11 ruling: picking a resolution must re-render (not just wait
    for the next manual click) and the label must state the ACTUAL on-screen
    resolution — the exact decoded pixel size of the PNG that came back, not
    a recomputed guess — so going 1x -> 2x must exactly double both the
    label's width and height. Doesn't assume landscape vs portrait (the
    default project view is portrait, which rotates the render 90°): it
    reads whatever pair of numbers the label prints and checks the ratio."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)

    ui.click("#tl-render")
    ui.wait_for_selector("#anim-preview-modal:not([hidden])", timeout=10_000)
    ui.wait_for_function(
        "() => !document.getElementById('anim-preview-img').hidden", timeout=30_000)
    label_1x = ui.locator("#anim-preview-popup-label").text_content()
    m1 = re.search(r"(\d+)\D(\d+) @1×", label_1x)
    assert m1, f"expected a WxH @1× resolution readout, got: {label_1x!r}"
    w1, h1 = int(m1.group(1)), int(m1.group(2))

    ui.select_option("#anim-preview-scale", "2")
    ui.wait_for_function(
        "(prev) => document.getElementById('anim-preview-popup-label')"
        ".textContent !== prev",
        arg=label_1x, timeout=30_000)
    label_2x = ui.locator("#anim-preview-popup-label").text_content()
    m2 = re.search(r"(\d+)\D(\d+) @2×", label_2x)
    assert m2, f"expected a WxH @2× resolution readout, got: {label_2x!r}"
    w2, h2 = int(m2.group(1)), int(m2.group(2))
    assert (w2, h2) == (w1 * 2, h1 * 2), (label_1x, label_2x)
    assert not ui.errors


def test_render_popup_fps_is_independent_of_the_animation_panel_fps(ui):
    """§2c: fps moved INTO the popup (drives popup playback + GIF/MP4 export)
    as its own field, separate from the Animation panel's #anim-preview-fps
    (which still drives in-canvas Live play speed). Changing one must not
    move the other, and the popup's own control must be the one that lands
    in the export links."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_selector("#anim-panel", timeout=10_000)
    if "collapsed" in (ui.locator("#anim-panel").get_attribute("class") or ""):
        ui.click("#anim-panel > h2")  # collapsed by default (data-collapse-default)
    ui.wait_for_selector("#anim-preview-fps", timeout=10_000)
    live_fps_before = ui.locator("#anim-preview-fps").input_value()

    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)
    ui.click("#tl-render")
    ui.wait_for_selector("#anim-preview-modal:not([hidden])", timeout=10_000)
    ui.wait_for_selector("#anim-preview-popup-fps", timeout=10_000)

    ui.fill("#anim-preview-popup-fps", "3")
    ui.locator("#anim-preview-popup-fps").dispatch_event("change")
    ui.wait_for_function(
        "() => document.getElementById('anim-preview-export-gif').href.includes('fps=3')",
        timeout=10_000)

    assert ui.locator("#anim-preview-fps").input_value() == live_fps_before, \
        "the Animation panel's Live-play fps must not move with the popup's"
    assert not ui.errors


def test_render_popup_pan_tracks_the_cursor_1_to_1_at_1x_2x_and_4x(ui):
    """2026-08-11 bench report: "the CSS-transform pan doesn't compensate for
    zoom scale — drags feel wrong at high zoom." The fix put `scale()`
    outer and `translate()` inner (applyZoomTransform, plot.js) and divides
    the on-screen mouse delta by the current zoom before folding it into
    panX/panY, which now live in that pre-scale coordinate system — so a
    given screen-pixel drag must move the rendered image by the SAME number
    of screen pixels regardless of zoom. Reads the inline `style.transform`
    string plot.js writes (not rendered geometry, which would drag in
    Playwright/OS scroll-position noise) so the assertion is exact rather
    than pixel-fuzzy."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)
    ui.click("#tl-render")
    ui.wait_for_selector("#anim-preview-modal:not([hidden])", timeout=10_000)
    ui.wait_for_function(
        "() => !document.getElementById('anim-preview-img').hidden", timeout=30_000)

    stage = ui.locator("#anim-preview-stage").bounding_box()
    cx, cy = stage["x"] + stage["width"] / 2, stage["y"] + stage["height"] / 2

    def pan_xy():
        t = ui.evaluate("() => document.getElementById('anim-preview-img').style.transform")
        m = re.search(r"translate\(([-\d.]+)px, ([-\d.]+)px\)", t)
        assert m, t
        return float(m.group(1)), float(m.group(2))

    for ticks, want_zoom in ((5, 2), (15, 4)):  # +0.2 per tick from 1.0
        # double-click resets zoom=1, pan=0,0 before each level
        ui.mouse.move(cx, cy)
        ui.mouse.dblclick(cx, cy)
        ui.wait_for_function(
            "() => document.getElementById('anim-preview-img').style.transform.includes('scale(1)')",
            timeout=5_000)
        for _ in range(ticks):
            ui.locator("#anim-preview-stage").dispatch_event(
                "wheel", {"deltaY": -100, "bubbles": True, "cancelable": True})
        ui.wait_for_function(
            "(z) => document.getElementById('anim-preview-img').style.transform"
            f".includes(`scale(${{z}})`)",
            arg=want_zoom, timeout=5_000)

        pan_before = pan_xy()
        dx, dy = 40, -25
        ui.mouse.move(cx, cy)
        ui.mouse.down()
        # single hop, not `steps=N`: multi-step moves only fired ONE
        # intermediate mousemove in this Playwright/Chromium combo (verified
        # with a throwaway debug script) rather than N, which read as a
        # pan-math bug here but was a test-harness artifact, not the app's.
        ui.mouse.move(cx + dx, cy + dy)
        ui.mouse.up()
        pan_after = pan_xy()

        # the pre-scale translate delta, scaled back UP by zoom, must equal
        # the literal screen-pixel drag — i.e. the image tracked the cursor
        # 1:1 in screen space at this zoom level.
        screen_dx = (pan_after[0] - pan_before[0]) * want_zoom
        screen_dy = (pan_after[1] - pan_before[1]) * want_zoom
        assert abs(screen_dx - dx) < 1.0, (want_zoom, screen_dx, dx)
        assert abs(screen_dy - dy) < 1.0, (want_zoom, screen_dy, dy)
    assert not ui.errors


def test_chain_keyframe_list_appears_and_selecting_a_key_moves_the_timeline(ui):
    """S3, build item 1: the ONLY way a chain is born is the "＋ keyframe"
    button on a plain A/B animation (Q6a) — clicking it twice must grow the
    classic two-button form into a 3-row keyframe list, in place (selection
    stays on the tween, not the new duplicate — the list you just grew is
    what you look at next). Picking the third row must jump the master
    timeline the same way the classic edit A/B buttons already do."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)

    ui.locator("#layer-list .layer-row.tween-row").first.click()
    ui.wait_for_selector("#tw-explode", timeout=10_000)  # the Interpolation section rendered
    assert ui.locator(".kf-row").count() == 0, "a plain A/B tween keeps the classic two-button form"
    assert ui.locator("#layer-detail button", has_text="edit A").count() == 1
    assert ui.locator("#layer-detail button", has_text="edit B").count() == 1

    ui.locator("#layer-detail button", has_text="＋ keyframe").first.click()
    ui.wait_for_function("() => document.querySelectorAll('.kf-row').length === 3", timeout=10_000)
    assert ui.locator(".kf-row").count() == 3, "one row per keyframe once it's a chain"
    _shoot(ui, "s3-keyframe-list.png")

    t_before = ui.locator("#tl-t-val").text_content()
    ui.locator(".kf-row .kf-select").nth(2).click()
    ui.wait_for_function(
        "(prev) => document.getElementById('tl-t-val').textContent !== prev",
        arg=t_before, timeout=10_000)
    assert not ui.errors


def test_keyframe_copy_paste_state_via_context_menu(ui):
    """Q6 ruling: right-click a keyframe row for Copy state / Paste state
    (whole-checkpoint: generator params, effects, placement — per-parameter
    copy/paste is deferred, not built here). Copy from the first keyframe
    (radius 20), paste onto the third (which duplicated the second, radius
    80) and assert — via the API, what the project actually holds — that the
    third keyframe's generator params now match the first's."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)

    ui.locator("#layer-list .layer-row.tween-row").first.click()
    ui.wait_for_selector("#tw-explode", timeout=10_000)
    ui.locator("#layer-detail button", has_text="＋ keyframe").first.click()
    ui.wait_for_function("() => document.querySelectorAll('.kf-row').length === 3", timeout=10_000)

    rows = ui.locator(".kf-row .kf-select")
    rows.nth(0).click(button="right")
    ui.wait_for_selector(".ctx-menu", timeout=5_000)
    _shoot(ui, "s3-context-menu.png")
    ui.locator(".ctx-menu-item", has_text="Copy state").click()
    ui.wait_for_selector(".ctx-menu", state="detached", timeout=5_000)

    rows.nth(2).click(button="right")
    ui.wait_for_selector(".ctx-menu", timeout=5_000)
    paste_item = ui.locator(".ctx-menu-item", has_text="Paste state")
    assert paste_item.is_enabled(), "clipboard was populated by the Copy state click above"
    paste_item.click()
    ui.wait_for_selector(".ctx-menu", state="detached", timeout=5_000)

    project = _get(f"{ui.base}/api/project")
    tw = next(l for l in project["layers"] if l["source"]["type"] == "tween")
    keys = tw["source"]["params"]["keys"]
    assert len(keys) == 3
    a = next(l for l in project["layers"] if l["id"] == keys[0])
    c = next(l for l in project["layers"] if l["id"] == keys[2])
    assert a["source"]["params"]["radius"] == 20
    assert c["source"]["params"]["radius"] == 20, \
        "paste onto C must apply A's generator params (radius), not keep C's own"
    assert c["source"]["params"]["sides"] == a["source"]["params"]["sides"]
    assert not ui.errors


# -- S6: start-from-sheet, Reset-vs-true-beginning, plotted-this-session ------
# docs/plans/timeline-v2.md §S6/P5/P6. Plot stepper markup lives inside the
# Animation panel (collapsed by default: click its <h2>) and the "Plot
# stepper" <details> (collapsed by default: click its <summary>) — both must
# be opened before their contents are interactable, same rule that governs
# every other <details data-fold> section in this tab.

def _open_anim_stepper(ui) -> None:
    ui.click('#tabs button[data-tab="plot"]')
    ui.click("#anim-panel > h2")
    ui.wait_for_selector("#anim-cols", state="visible", timeout=10_000)
    ui.click('details[data-fold="plot-stepper"] summary')
    ui.wait_for_selector("#anim-plot-frame", state="visible", timeout=10_000)


def _set_grid(ui, cols, rows) -> None:
    """Fill the cols/rows number inputs directly — the 1/2/4/8/16 preset
    buttons (#anim-presets) were removed 2026-08-11 in favour of the two
    bounded inputs already backing them (docs/plans/timeline-v2.md §2c
    "Sheet grid"). fill() alone doesn't reliably fire the onchange handler
    the panel relies on, so dispatch it explicitly (same pattern as the
    t-from/t-to fills above)."""
    ui.fill("#anim-cols", str(cols))
    ui.fill("#anim-rows", str(rows))
    ui.locator("#anim-rows").dispatch_event("change")


def test_start_from_sheet_updates_stepper_label_and_canvas_preview(ui):
    """Punch a sheet number into the stepper and press Start here: the label
    jumps straight to it (no more pressing Skip N times) and the canvas
    preview banner (sheetPreviewLabel) names the same sheet."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    _open_anim_stepper(ui)

    # default 8 frames over a 2×1 grid -> 4 sheets, so sheet 3 is reachable
    # and distinct from sheet 1.
    _set_grid(ui, 2, 1)
    ui.wait_for_function(
        "() => document.getElementById('anim-start-sheet-n').textContent === '4'",
        timeout=10_000)
    assert ui.is_visible("#anim-start-sheet-row")
    assert not ui.is_visible("#anim-start-frame-row")

    ui.fill("#anim-start-sheet", "3")
    ui.click("#anim-start-sheet-go")
    ui.wait_for_function(
        "() => (document.getElementById('anim-frame-label')?.textContent || '').startsWith('sheet 3/4')",
        timeout=10_000)

    ui.wait_for_function(
        "() => (document.getElementById('doc-preview-label')?.textContent || '').includes('sheet 3/4')",
        timeout=10_000)
    assert not ui.errors


def test_start_from_frame_updates_the_single_frame_stepper(ui):
    """Same affordance, single-frame stepper (gridCells() <= 1): the frame
    box + Start here jumps the stepper directly to frame N."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    _open_anim_stepper(ui)
    assert ui.is_visible("#anim-start-frame-row")
    assert not ui.is_visible("#anim-start-sheet-row")

    ui.fill("#anim-start-frame", "5")
    ui.click("#anim-start-frame-go")
    ui.wait_for_function(
        "() => (document.getElementById('anim-frame-label')?.textContent || '').startsWith('frame 5 of')",
        timeout=10_000)
    assert not ui.errors


def test_reset_returns_to_chosen_start_not_zero_and_true_beginning_is_separate(ui):
    """P5: Reset must mean 'back to where I chose to start', never a silent
    'back to sheet 0' mid-run — a from-sheet-7 plotter reaching for Reset
    should not accidentally re-cost sheet 1. The distinct ⤒1 control is the
    only thing that reaches the true beginning."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    _open_anim_stepper(ui)

    _set_grid(ui, 2, 1)
    ui.wait_for_function(
        "() => document.getElementById('anim-start-sheet-n').textContent === '4'",
        timeout=10_000)

    ui.fill("#anim-start-sheet", "3")
    ui.click("#anim-start-sheet-go")
    ui.wait_for_function(
        "() => (document.getElementById('anim-frame-label')?.textContent || '').startsWith('sheet 3/4')",
        timeout=10_000)

    # advance away from the chosen start, then Reset — must land back on 3
    ui.click("#anim-skip")
    ui.wait_for_function(
        "() => !(document.getElementById('anim-frame-label')?.textContent || '').startsWith('sheet 3/4')",
        timeout=10_000)
    ui.click("#anim-reset")
    ui.wait_for_function(
        "() => (document.getElementById('anim-frame-label')?.textContent || '').startsWith('sheet 3/4')",
        timeout=10_000)

    # only the true-beginning control reaches sheet 1
    ui.click("#anim-reset-true")
    ui.wait_for_function(
        "() => (document.getElementById('anim-frame-label')?.textContent || '').startsWith('sheet 1/4')",
        timeout=10_000)
    assert not ui.errors


def test_tray_groups_born_from_one_animation_setup_read_apart_from_loose_captures(ui):
    """P6 amendment: a multi-sheet grid capture (kind 'sheet') reads as one
    animation-derived group, visually distinct from a standalone loose
    capture (kind 'plot') — and P9 lands as a side effect: the group header
    shows groupLabel()'s richer text instead of the bare kind + count."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    _post(f"{ui.base}/api/staging/capture",
          {"kind": "sheet", "target": "all", "cols": 2, "rows": 1, "frames": 4,
           "name": "4f · 2×1 · fixed"})
    _post(f"{ui.base}/api/staging/capture",
          {"kind": "plot", "target": "all", "name": "loose plot"})
    reload_app(ui)
    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_selector(".stage-group", timeout=10_000)

    assert ui.locator(".stage-group").count() == 2
    anim_groups = ui.locator(".stage-group.stage-group-anim")
    assert anim_groups.count() == 1, "only the sheet capture should read as an animation set"
    assert "animation set" in anim_groups.locator(".stage-head .tag").text_content()
    # P9, delivered en passant: the header text is groupLabel()'s name ·
    # detail · sheet-count, not the old bare "sheet · 2 sheets".
    assert "sheet" in anim_groups.locator(".stage-head strong").text_content()

    loose = ui.locator(".stage-group", has_text="loose plot")
    assert "stage-group-anim" not in (loose.get_attribute("class") or "")
    assert not ui.errors


# -- tray round (docs/plans/timeline-v2.md §2c "Trays") ----------------------

def test_view_label_names_what_the_canvas_shows_across_view_switches(ui):
    """7a: an always-visible label says what the canvas currently shows —
    nothing for the ordinary single-frame live view, "live · sheet n/N" for
    the live grid-sheet preview, 'tray "name" · sheet n/N' for a frozen
    staged sheet — driven by the SAME S.docPreview every view-changing path
    (sheet preview, tray preview, the exit-to-live banner button) already
    writes, so it can't say something the canvas doesn't back up."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    assert ui.eval_on_selector("#view-label", "el => el.textContent") == ""

    _open_anim_stepper(ui)
    _set_grid(ui, 2, 1)
    ui.wait_for_function(
        "() => (document.getElementById('view-label')?.textContent || '') === 'live · sheet 1/4'",
        timeout=10_000)

    group = _post(f"{ui.base}/api/staging/capture", {"kind": "plot", "name": "frozen"})["group"]
    reload_app(ui)
    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_selector(".stage-group", timeout=10_000)
    ui.click(f'[data-stage-preview="{group["id"]}:{group["sheets"][0]["id"]}"]')
    ui.wait_for_function(
        "() => (document.getElementById('view-label')?.textContent || '').includes('frozen')",
        timeout=10_000)
    assert "tray" in ui.eval_on_selector("#view-label", "el => el.textContent")
    assert "sheet 1/1" in ui.eval_on_selector("#view-label", "el => el.textContent")

    ui.click("#doc-preview-exit")
    ui.wait_for_function(
        "() => (document.getElementById('view-label')?.textContent || '') === ''",
        timeout=10_000)
    assert not ui.errors


def test_live_sheet_view_stays_sticky_across_a_param_edit(ui):
    """8a: editing a layer param while the canvas shows the LIVE grid-sheet
    preview used to drop the canvas back to single-frame (Ian's bench
    report); it must re-render the sheet in place instead. A staged/tray
    preview is a different story — those stay non-sticky (9a's re-bake is
    the only way to update one), covered separately."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    reload_app(ui)
    _open_anim_stepper(ui)
    _set_grid(ui, 2, 1)
    ui.wait_for_function(
        "() => (document.getElementById('view-label')?.textContent || '').includes('sheet 1/4')",
        timeout=10_000)
    before = wait_for_ink(ui)

    ui.click('#tabs button[data-tab="compose"]')
    select_layer(ui)
    ui.wait_for_selector("#regen-form", timeout=10_000)
    # sides (field 0), not radius: this sheet uses "timeline" crop, which
    # fits the (single, unanimated) shape's shared window to each cell — a
    # uniform radius change re-normalizes away to the same rendered points,
    # a red herring here. Changing the point count is unambiguous.
    field = ui.locator('#regen-form input[type="number"]').nth(0)
    field.fill(str(int(field.input_value() or 5) + 3))
    field.press("Enter")
    ui.click("#btn-regen")

    ui.wait_for_function(
        "([sel, old]) => Array.from(document.querySelectorAll(sel))"
        ".map(e => e.getAttribute('d') || '').join('|') !== old",
        arg=["#canvas path", before], timeout=20_000)
    # the edit round-tripped (ink changed) AND the sheet view is still up —
    # this is exactly the bug: it used to snap back to single-frame here.
    assert "sheet 1/4" in ui.eval_on_selector("#view-label", "el => el.textContent")
    assert ui.eval_on_selector("#doc-preview-banner", "el => el.hidden") is False
    assert not ui.errors


def test_selecting_a_tray_group_shows_selection_state_and_previews_it(ui):
    """Item 4 ("Sheet grid": plot targets the currently selected tray):
    clicking a group's header — not one of its buttons — selects it, with a
    visible selection state, and previews it (canvas + 7a's label), the same
    effect a sheet's own Preview button already had."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    _post(f"{ui.base}/api/staging/capture", {"kind": "plot", "name": "tray A"})
    b = _post(f"{ui.base}/api/staging/capture", {"kind": "plot", "name": "tray B"})["group"]
    reload_app(ui)
    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_selector(".stage-group", timeout=10_000)
    assert ui.locator(".stage-group.selected").count() == 0

    ui.click(f'[data-stage-select="{b["id"]}"] strong')
    ui.wait_for_selector(".stage-group.selected", timeout=10_000)
    assert "tray B" in ui.locator(".stage-group.selected").text_content()
    assert ui.locator(".stage-group.selected").count() == 1
    ui.wait_for_function(
        "() => (document.getElementById('view-label')?.textContent || '').includes('tray B')",
        timeout=10_000)
    assert not ui.errors


def test_rebake_updates_a_trays_geometry_and_is_disabled_for_batch_groups(ui):
    """9a: a frozen tray's re-bake button re-runs its capture against the
    CURRENT project, replacing its sheets in place — and is disabled, with a
    reason tooltip, for a "batch" (A⇄B interpolated) group, which is derived
    from two OTHER captures' frozen snapshots, not the live project."""
    layer_id = add_layer(ui, "polygon", {"sides": 6, "radius": 15})
    group = _post(f"{ui.base}/api/staging/capture", {"kind": "plot", "name": "live tray"})["group"]
    reload_app(ui)
    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_selector(".stage-group", timeout=10_000)

    btn = ui.locator(f'[data-stage-rebake="{group["id"]}"]')
    assert btn.is_enabled()
    old_sheet_key = ui.eval_on_selector(
        f'[data-stage-select="{group["id"]}"]',
        "h => h.closest('.stage-group').querySelector('[data-stage-preview]').dataset.stagePreview")

    _post(f"{ui.base}/api/layers/{layer_id}/regenerate", {"params": {"sides": 6, "radius": 55}})
    btn.click()
    ui.wait_for_function(
        "([gid, old]) => { const h = document.querySelector(`[data-stage-select=\"${gid}\"]`);"
        " const b = h && h.closest('.stage-group').querySelector('[data-stage-preview]');"
        " return b && b.dataset.stagePreview !== old; }",
        arg=[group["id"], old_sheet_key], timeout=10_000)

    # a batch group is a different capture kind — refused, disabled, explained
    a = _post(f"{ui.base}/api/staging/capture",
              {"kind": "sheet", "name": "sA", "cols": 2, "rows": 1, "frames": 4})["group"]
    b2 = _post(f"{ui.base}/api/staging/capture",
              {"kind": "sheet", "name": "sB", "cols": 2, "rows": 1, "frames": 4})["group"]
    batch = _post(f"{ui.base}/api/staging/interpolate",
                  {"a": a["id"], "b": b2["id"], "steps": 2})["group"]
    reload_app(ui)
    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_selector(".stage-group", timeout=10_000)
    batch_btn = ui.locator(f'[data-stage-rebake="{batch["id"]}"]')
    assert batch_btn.is_disabled()
    assert "derived from other captures" in (batch_btn.get_attribute("title") or "")
    assert not ui.errors


# -- plot flow: ▶ Plot obeys the view label + the guided pass queue ----------
# docs/plans/timeline-v2.md §2c "Plot flow" (ruled 2026-08-11). These assert
# WHAT GOES TO THE MACHINE — the POST /api/plot/start bodies the UI actually
# sends — because that is the only honest way to test a routing change on a
# tool that puts ink on paper. Nothing here reaches into how the routing is
# implemented; it reads the request the plotter would have executed.


def _plot_calls(page) -> list[dict]:
    """Start recording every POST /api/plot/start body this page sends."""
    calls: list[dict] = []

    def on_request(req):
        if req.method == "POST" and req.url.endswith("/api/plot/start"):
            try:
                calls.append(json.loads(req.post_data or "{}"))
            except Exception:
                calls.append({})

    page.on("request", on_request)
    return calls


def _wait_calls(page, calls: list, n: int, timeout_ms: int = 25_000) -> None:
    """Poll through the driver (never a bare sleep — sync-playwright only
    dispatches events while it is inside an API call)."""
    waited = 0
    while len(calls) < n and waited < timeout_ms:
        page.wait_for_timeout(50)
        waited += 50
    assert len(calls) >= n, f"expected {n} plot calls, saw {len(calls)}: {calls}"


def _connect_simulator(page) -> None:
    """Plot tab open, simulator connected, Plot live. Idempotent: the server
    is session-scoped, so it may already be connected from an earlier test."""
    page.click('#tabs button[data-tab="plot"]')
    page.wait_for_selector("#btn-plot", timeout=10_000)
    if page.locator("#btn-plot").is_disabled():
        page.click("#btn-connect")
    page.wait_for_function(
        "() => !document.querySelector('#btn-plot').disabled", timeout=20_000)


def _two_pen_project(page) -> None:
    """Two layers on two pens — the shape every multi-pass case needs. Pens are
    machine-level (they outlive /api/project/new), so fixed ids keep repeated
    upserts from breeding duplicates across tests."""
    _post(f"{page.base}/api/pens", {"id": "qpen-red", "name": "Queue Red", "color": "#c0392b"})
    _post(f"{page.base}/api/pens", {"id": "qpen-blue", "name": "Queue Blue", "color": "#2980b9"})
    a = add_layer(page, "polygon", {"sides": 5, "radius": 20})
    b = add_layer(page, "polygon", {"sides": 3, "radius": 30})
    _patch(f"{page.base}/api/layers/{a}", {"pen_id": "qpen-red"})
    _patch(f"{page.base}/api/layers/{b}", {"pen_id": "qpen-blue"})


def _idle_machine(page) -> None:
    """Leave the shared machine idle for the next test."""
    _post(f"{page.base}/api/plot/stop", {"return_home": False})
    page.wait_for_function(
        "() => document.querySelector('#status-pill').textContent.includes('idle')",
        timeout=20_000)


def test_plot_from_the_plain_live_view_is_unchanged(ui):
    """The whole routing change must be invisible on the ordinary live view:
    one job for the picked target, target picker live, no pass queue — even
    with two pens in the project (target 'all' has always plotted every pen in
    a single job and deliberately still does)."""
    _two_pen_project(ui)
    _connect_simulator(ui)
    assert ui.locator("#plot-target").is_enabled()
    assert ui.eval_on_selector("#plot-view-target", "el => el.textContent") == ""

    calls = _plot_calls(ui)
    ui.click("#btn-plot")
    _wait_calls(ui, calls, 1)
    assert calls[0] == {"target": "all"}, calls
    assert ui.eval_on_selector("#plot-queue-status", "el => el.textContent") == ""
    _idle_machine(ui)
    assert len(calls) == 1, f"a plain live plot is one job, never a queue: {calls}"
    assert not ui.errors


def test_plot_obeys_the_view_label_and_fires_the_tray_sheets_first_pass(ui):
    """With a tray sheet on the canvas, ▶ Plot plots THAT sheet — its first pen
    pass — not the live project. The view label is the contract."""
    _two_pen_project(ui)
    group = _post(f"{ui.base}/api/staging/capture",
                  {"kind": "plot", "target": "all", "name": "two pens"})["group"]
    assert len(group["sheets"][0]["passes"]) == 2, "setup: the tray sheet needs two passes"
    reload_app(ui)
    _connect_simulator(ui)
    ui.wait_for_selector(".stage-group", timeout=10_000)
    sheet_id = group["sheets"][0]["id"]
    ui.click(f'[data-stage-preview="{group["id"]}:{sheet_id}"]')
    ui.wait_for_function(
        "() => (document.getElementById('view-label')?.textContent || '').includes('two pens')",
        timeout=10_000)
    # 5: what will plot is stated in words before the press
    assert "2 passes" in ui.eval_on_selector("#plot-view-target", "el => el.textContent")
    assert 'tray "two pens"' in ui.eval_on_selector("#plot-view-target", "el => el.textContent")

    calls = _plot_calls(ui)
    ui.click("#btn-plot")
    _wait_calls(ui, calls, 1)
    assert "staged" in calls[0], f"a tray view must plot the tray sheet: {calls}"
    assert calls[0]["staged"]["group_id"] == group["id"]
    assert calls[0]["staged"]["sheet_id"] == sheet_id
    assert calls[0]["staged"]["pen_id"] == group["sheets"][0]["passes"][0]["pen_id"]
    _idle_machine(ui)
    assert not ui.errors


def test_plot_on_the_live_sheet_view_plots_that_sheets_passes(ui):
    """Same contract, other view: while the canvas shows the LIVE grid sheet,
    ▶ Plot plots that page's pen passes (a `sheet=` job), not the plain
    target."""
    _two_pen_project(ui)
    _connect_simulator(ui)
    _open_anim_stepper(ui)
    _set_grid(ui, 2, 1)
    ui.wait_for_function(
        "() => (document.getElementById('view-label')?.textContent || '') === 'live · sheet 1/4'",
        timeout=10_000)

    calls = _plot_calls(ui)
    ui.click("#btn-plot")
    _wait_calls(ui, calls, 1)
    assert "sheet" in calls[0], f"a live sheet view must plot the sheet: {calls}"
    assert calls[0]["sheet"]["cols"] == 2 and calls[0]["sheet"]["rows"] == 1
    assert calls[0]["sheet"]["page"] == 0
    assert calls[0]["sheet"]["pen_id"] in ("qpen-red", "qpen-blue")
    _idle_machine(ui)
    assert not ui.errors


def test_the_pass_queue_holds_for_a_pen_swap_then_continue_fires_the_next_pass(ui):
    """The guided queue: one press starts pass 1; when it finishes the machine
    HOLDS and the status line names the pen to swap in; the Plot button becomes
    the continue and fires pass 2. Nothing auto-advances."""
    _two_pen_project(ui)
    group = _post(f"{ui.base}/api/staging/capture",
                  {"kind": "plot", "target": "all", "name": "swap me"})["group"]
    passes = group["sheets"][0]["passes"]
    reload_app(ui)
    _connect_simulator(ui)
    ui.wait_for_selector(".stage-group", timeout=10_000)
    ui.click(f'[data-stage-preview="{group["id"]}:{group["sheets"][0]["id"]}"]')
    ui.wait_for_function(
        "() => (document.getElementById('view-label')?.textContent || '').includes('swap me')",
        timeout=10_000)

    calls = _plot_calls(ui)
    ui.click("#btn-plot")
    _wait_calls(ui, calls, 1)

    # pass 1 finishes -> hold, with the NEXT pen named in the always-visible
    # status line and on the button itself
    ui.wait_for_function(
        "(pen) => (document.getElementById('plot-queue-status')?.textContent || '')"
        ".includes(`swap to ${pen}`)",
        arg=passes[1]["name"], timeout=30_000)
    assert "1/2" in ui.eval_on_selector("#plot-queue-status", "el => el.textContent")
    assert passes[1]["name"] in ui.eval_on_selector("#btn-plot", "el => el.textContent")
    assert len(calls) == 1, f"the queue must not auto-advance: {calls}"
    _shoot(ui, "pass_queue_swap_prompt.png")

    ui.wait_for_function("() => !document.querySelector('#btn-plot').disabled", timeout=20_000)
    ui.click("#btn-plot")
    _wait_calls(ui, calls, 2)
    assert calls[1]["staged"]["pen_id"] == passes[1]["pen_id"], calls
    # last pass done -> the queue is over, nothing left holding
    ui.wait_for_function(
        "() => (document.getElementById('plot-queue-status')?.textContent || '') === ''",
        timeout=30_000)
    assert ui.eval_on_selector("#btn-plot", "el => el.textContent").strip() == "Plot"
    _idle_machine(ui)
    assert not ui.errors


def test_stop_mid_queue_clears_the_queue(ui):
    """Existing Stop semantics, extended by exactly one rule: no queue state
    survives a stop. After stopping, the button is Plot again and pressing it
    starts pass 1 — never pass 2 of a ghost queue."""
    _two_pen_project(ui)
    group = _post(f"{ui.base}/api/staging/capture",
                  {"kind": "plot", "target": "all", "name": "stop me"})["group"]
    first_pen = group["sheets"][0]["passes"][0]["pen_id"]
    # slow the simulator right down so pass 1 is still running when Stop lands
    _put(f"{ui.base}/api/params/simulator", {"time_scale": 0.5})
    try:
        reload_app(ui)
        _connect_simulator(ui)
        ui.wait_for_selector(".stage-group", timeout=10_000)
        ui.click(f'[data-stage-preview="{group["id"]}:{group["sheets"][0]["id"]}"]')
        ui.wait_for_function(
            "() => (document.getElementById('view-label')?.textContent || '').includes('stop me')",
            timeout=10_000)

        calls = _plot_calls(ui)
        ui.click("#btn-plot")
        _wait_calls(ui, calls, 1)
        ui.wait_for_function(
            "() => (document.getElementById('plot-queue-status')?.textContent || '')"
            ".includes('plotting')", timeout=20_000)

        ui.click("#btn-stop")
        ui.wait_for_function(
            "() => (document.getElementById('plot-queue-status')?.textContent || '') === ''",
            timeout=30_000)
        assert ui.eval_on_selector("#btn-plot", "el => el.textContent").strip() == "Plot"

        # and the next press starts over at pass 1, not at the abandoned pass 2
        ui.wait_for_function("() => !document.querySelector('#btn-plot').disabled", timeout=30_000)
        ui.click("#btn-plot")
        _wait_calls(ui, calls, 2)
        assert calls[1]["staged"]["pen_id"] == first_pen, calls
        ui.click("#btn-stop")
    finally:
        _put(f"{ui.base}/api/params/simulator", {"time_scale": 10.0})
        _idle_machine(ui)
    assert not ui.errors


def test_a_held_queue_can_be_abandoned_with_stop(ui):
    """A hold sits on an IDLE machine, and Stop is normally dead while idle —
    so without this the only exit from a pen-swap hold would be plotting the
    rest of it. Stop stays live for as long as a queue does."""
    _two_pen_project(ui)
    group = _post(f"{ui.base}/api/staging/capture",
                  {"kind": "plot", "target": "all", "name": "abandon me"})["group"]
    first_pen = group["sheets"][0]["passes"][0]["pen_id"]
    reload_app(ui)
    _connect_simulator(ui)
    ui.wait_for_selector(".stage-group", timeout=10_000)
    ui.click(f'[data-stage-preview="{group["id"]}:{group["sheets"][0]["id"]}"]')
    ui.wait_for_function(
        "() => (document.getElementById('view-label')?.textContent || '').includes('abandon me')",
        timeout=10_000)

    calls = _plot_calls(ui)
    ui.click("#btn-plot")
    _wait_calls(ui, calls, 1)
    ui.wait_for_function(
        "() => (document.getElementById('plot-queue-status')?.textContent || '')"
        ".includes('swap to')", timeout=30_000)
    assert ui.locator("#btn-stop").is_enabled(), "a held queue must stay abandonable"

    ui.click("#btn-stop")
    ui.wait_for_function(
        "() => (document.getElementById('plot-queue-status')?.textContent || '') === ''",
        timeout=20_000)
    assert ui.locator("#btn-stop").is_disabled(), "queue gone, machine idle: Stop is dead again"
    # the abandoned pass 2 is not resumed by the next press — it starts over
    ui.click("#btn-plot")
    _wait_calls(ui, calls, 2)
    assert calls[1]["staged"]["pen_id"] == first_pen, calls
    _idle_machine(ui)
    assert not ui.errors


def test_target_picker_greys_out_on_sheet_and_tray_views(ui):
    """4: the all/layer/pen picker belongs to the plain live view. On a sheet
    or tray view the passes carry their own pens, and the picker says so."""
    _two_pen_project(ui)
    group = _post(f"{ui.base}/api/staging/capture",
                  {"kind": "plot", "target": "all", "name": "picker tray"})["group"]
    reload_app(ui)
    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_selector(".stage-group", timeout=10_000)
    assert ui.locator("#plot-target").is_enabled(), "plain live view: the picker applies"

    ui.click(f'[data-stage-preview="{group["id"]}:{group["sheets"][0]["id"]}"]')
    ui.wait_for_function(
        "() => document.querySelector('#plot-target').disabled === true", timeout=10_000)
    assert ui.locator("#plot-target").get_attribute("title") == "sheet passes carry their pens"
    ui.locator("#plot-target").scroll_into_view_if_needed()
    _shoot(ui, "pass_queue_greyed_target_picker.png")

    # back to the live project — and it comes back
    ui.click("#doc-preview-exit")
    ui.wait_for_function(
        "() => document.querySelector('#plot-target').disabled === false", timeout=10_000)

    # the live SHEET view greys it too (same rule, other view)
    _open_anim_stepper(ui)
    _set_grid(ui, 2, 1)
    ui.wait_for_function(
        "() => document.querySelector('#plot-target').disabled === true", timeout=10_000)
    assert not ui.errors


# -- final sweep (docs/plans/timeline-v2.md S7, P2, P8, P10) -----------------

def test_narrow_tween_warning_appears_and_clears_with_frame_count(ui):
    """P2: a follow_master tween whose window is narrower than one frame
    step can be skipped by every output (export/sheets/popup sample the same
    grid) — the hint under the frame count turns that from a mystifying
    blank sheet into a number to raise. It must also clear once frames is
    raised past the number it names."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    project = _get(f"{ui.base}/api/project")
    tw = next(l for l in project["layers"] if l["source"]["type"] == "tween")
    # default 8-frame grid over 0..1 steps at 1/7 ≈ 0.143 — this window
    # (width 0.01) is well inside one step, so it can fall between samples.
    _put(f"{ui.base}/api/layers/{tw['id']}/tween",
         {"window_from": 0.50, "window_to": 0.51})
    reload_app(ui)
    wait_for_ink(ui)
    _open_anim_stepper(ui)

    ui.wait_for_selector("#anim-narrow-tween-hint:not([hidden])", timeout=10_000)
    text = ui.locator("#anim-narrow-tween-hint").text_content()
    assert "narrower than one frame" in text
    m = re.search(r"raise frames to ≥ (\d+)", text)
    assert m, f"expected an M in the hint, got: {text!r}"
    _shoot(ui, "p2-narrow-tween-warning.png")

    # M frames puts a grid step exactly on the window's width — no longer
    # narrower than it — and the hint clears
    ui.fill("#anim-frames", m.group(1))
    ui.locator("#anim-frames").dispatch_event("change")
    ui.wait_for_function(
        "() => document.getElementById('anim-narrow-tween-hint').hidden === true",
        timeout=10_000)
    assert not ui.errors


def test_interpolate_blocker_reason_is_visible_before_the_click(ui):
    """P8: interpolateBlocker's reason was already computed but sat
    invisibly in the button's title — it now also renders as a hint line
    under the A/B row. Exercised via the S7 chain fence (Q5 narrow ruling:
    chains refuse, video still blends) so one screenshot covers both."""
    layer_id = add_layer(ui, "polygon", {"sides": 6, "radius": 15})
    animate_and_follow(ui, layer_id, b_radius=40)
    project = _get(f"{ui.base}/api/project")
    tw = next(l for l in project["layers"] if l["source"]["type"] == "tween")
    _post(f"{ui.base}/api/layers/{tw['id']}/chain/keyframe")  # A/B -> a 3-key chain
    _post(f"{ui.base}/api/staging/capture", {"kind": "plot", "name": "capA"})
    _post(f"{ui.base}/api/staging/capture", {"kind": "plot", "name": "capB"})
    reload_app(ui)
    wait_for_ink(ui)

    ui.click('#tabs button[data-tab="plot"]')
    ui.wait_for_selector("#stage-a", state="visible", timeout=10_000)
    ui.wait_for_function(
        "() => document.querySelectorAll('#stage-a option').length >= 2", timeout=10_000)
    ui.evaluate("""() => {
      const pick = (id, text) => {
        const sel = document.getElementById(id);
        const opt = [...sel.options].find((o) => o.textContent.includes(text));
        sel.value = opt.value;
        sel.dispatchEvent(new Event('change', {bubbles: true}));
      };
      pick('stage-a', 'capA');
      pick('stage-b', 'capB');
    }""")

    ui.wait_for_selector("#stage-interp-hint:not([hidden])", timeout=10_000)
    text = ui.locator("#stage-interp-hint").text_content()
    assert "keyframe chain" in text
    assert ui.is_disabled("#stage-interp")
    ui.locator("#stage-interp-hint").scroll_into_view_if_needed()
    _shoot(ui, "p8-interpolate-blocker-visible.png")
    assert not ui.errors


def test_render_popup_close_leaves_master_timeline_on_the_shown_frame(ui):
    """P10: the popup and the bar shouldn't disagree about "which frame" once
    the popup stops owning the screen — closing it must leave the master
    timeline reading the exact frame that was on screen, not wherever it
    happened to be before the popup opened."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)

    ui.click("#tl-render")
    ui.wait_for_selector("#anim-preview-modal:not([hidden])", timeout=10_000)
    ui.wait_for_function(
        "() => !document.getElementById('anim-preview-popup-next').disabled", timeout=30_000)

    # step to a frame — this also stops the auto-started playback (P10 cares
    # about a STILL frame, not a moving target), so whatever frame it lands
    # on is deterministic from here.
    ui.click("#anim-preview-popup-next")
    ui.click("#anim-preview-popup-next")
    label = ui.locator("#anim-preview-popup-label").text_content()
    m = re.search(r"t=(\d\.\d+)", label)
    assert m, f"expected a t= readout in the popup label, got: {label!r}"
    shown_t = f"t = {m.group(1)}"

    ui.click("#anim-preview-close")
    ui.wait_for_function(
        "() => document.getElementById('anim-preview-modal').hidden", timeout=5_000)
    ui.wait_for_function(
        "(want) => document.getElementById('tl-t-val').textContent === want",
        arg=shown_t, timeout=10_000)
    _shoot(ui, "p10-popup-close-master-readout.png")
    assert not ui.errors


# -- colour separation ---------------------------------------------------------


def _upload_colour_asset(page, name="sep-test.png"):
    """Put a two-colour image in the store through the real upload endpoint.

    Multipart by hand rather than through a helper: the app has no JSON asset
    upload, and the point of an acceptance test is the path the browser takes.
    """
    import io as _io
    from PIL import Image

    img = Image.new("RGB", (48, 36))
    img.putdata([(255, 40, 40) if (i % 48) < 24 else (40, 200, 255)
                 for i in range(48 * 36)])
    buf = _io.BytesIO()
    img.save(buf, "PNG")

    boundary = "----axibridge-sep-test"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + buf.getvalue() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{page.base}/api/assets", data=body, method="POST",
        headers={"content-type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        json.loads(r.read())
    return name


def test_separation_row_appears_only_for_channel_generators(ui):
    """The row is gated on the generator declaring a channel, so it must be
    absent for a procedural source and present for an image-driven one."""
    ui.select_option("#gen-select", "polygon")
    ui.wait_for_function(
        "() => document.getElementById('separate-row').hidden", timeout=5_000)

    ui.select_option("#gen-select", "halftone")
    ui.wait_for_function(
        "() => !document.getElementById('separate-row').hidden", timeout=5_000)
    # ...but not usable until there is an image, and it says why out loud
    assert ui.locator("#btn-separate").is_disabled()
    assert "image" in ui.locator("#separate-why").text_content()
    assert not ui.errors


def test_separation_creates_one_layer_per_plate(ui):
    """The whole feature, through the UI the user actually touches: pick a
    generator, choose an image, press one button, get four plates — and one
    ⌘Z takes all four away again."""
    name = _upload_colour_asset(ui)
    reload_app(ui)  # the asset list is fetched at boot; this page predates it
    ui.select_option("#gen-select", "halftone")
    ui.wait_for_function(
        "() => !document.getElementById('separate-row').hidden", timeout=5_000)
    ui.wait_for_function(
        "(n) => [...document.querySelectorAll('#gen-form select option')]"
        "        .some((o) => o.value === n)", arg=name, timeout=10_000)

    # pick the asset in the generator form's image field
    ui.evaluate(
        """(n) => {
            const sel = [...document.querySelectorAll('#gen-form select')]
                .find((s) => [...s.options].some((o) => o.value === n));
            sel.value = n;
            sel.dispatchEvent(new Event('change', { bubbles: true }));
        }""", name)
    ui.wait_for_function(
        "() => !document.getElementById('btn-separate').disabled", timeout=10_000)

    assert ui.locator("#separate-plates .sep-plate").count() == 4  # CMYK default
    before = rows(ui)
    ui.click("#btn-separate")
    ui.wait_for_function("(n) => document.querySelectorAll('#layer-list .layer-row')"
                         ".length === n + 4", arg=before, timeout=60_000)

    _shoot(ui, "separation-row.png")
    names = ui.locator("#layer-list .layer-row").all_text_contents()
    joined = " ".join(names).lower()
    for plate in ("cyan", "magenta", "yellow", "black"):
        assert plate in joined, f"no {plate} plate in the layer list: {names}"

    _post(f"{ui.base}/api/undo")
    ui.reload(wait_until="domcontentloaded")
    _wait_ready(ui)
    ui.wait_for_function("(n) => document.querySelectorAll('#layer-list .layer-row')"
                         ".length === n", arg=before, timeout=20_000)
    assert not ui.errors


def test_separation_mode_switch_rebuilds_the_plate_list(ui):
    ui.select_option("#gen-select", "halftone")
    ui.wait_for_function(
        "() => !document.getElementById('separate-row').hidden", timeout=5_000)
    assert ui.locator("#separate-plates .sep-plate").count() == 4

    ui.select_option("#separate-mode", "rgb")
    ui.wait_for_function(
        "() => document.querySelectorAll('#separate-plates .sep-plate').length === 3",
        timeout=5_000)
    labels = " ".join(ui.locator("#separate-plates .sep-plate").all_text_contents())
    assert "red" in labels and "blue" in labels

    ui.select_option("#separate-mode", "tone")
    ui.wait_for_function(
        "() => [...document.querySelectorAll('#separate-plates .sep-plate')]"
        "        .some((r) => r.dataset.name === 'lights')", timeout=5_000)
    assert not ui.errors

