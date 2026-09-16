"""Browser contracts for the Mosca recording bench.

The module starts an otherwise normal AxiBridge server with one tiny local
recording.  That keeps the browser journey portable: it never relies on the
developer's mosca-draw checkout or on a prepared asset surviving a process.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import numpy as np
import pytest

from test_acceptance_ui import _get, _post, frontend_mode, select_layer, ui


REPO = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def server(frontend_mode):
    """A real server with the one recording the UI is expected to find."""
    root = Path(tempfile.mkdtemp(prefix="axibridge-mosca-ui-"))
    history = root / "recordings" / "out" / "flight-a"
    history.mkdir(parents=True)
    np.savez(history / "loop.npz",
             path=np.array([[0., 0.], [10., 0.], [20., 10.], [30., 10.]]),
             pen_down=np.array([True, True, True, True]), dt=np.array(100.0))
    port = _free_port()
    env = {**os.environ, "AXIBRIDGE_CONFIG_DIR": str(root / "config"),
           "AXIBRIDGE_MOSCA_DIR": str(root / "recordings"),
           "AXIBRIDGE_NO_AUTOCONNECT": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "axibridge.app:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            output = (proc.stdout.read() or b"").decode()[-2000:]
            pytest.fail(f"Mosca UI server exited before it answered:\n{output}")
        try:
            _get(f"{base}/api/state", timeout=1)
            break
        except Exception:
            time.sleep(.15)
    else:
        proc.kill()
        pytest.fail("Mosca UI server never answered /api/state")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(root, ignore_errors=True)


def _open(page) -> None:
    page.wait_for_function("() => !!document.querySelector('#gen-select option[value=mosca]')")
    page.select_option("#gen-select", "mosca")
    page.click("#btn-bench")
    page.wait_for_function("() => document.querySelectorAll('.mosca-recording').length === 1",
                           timeout=15_000)


def _select(page) -> None:
    _open(page)
    page.locator("#mosca-recordings summary").click()
    page.locator(".mosca-recording", has_text="loop").click()
    page.wait_for_function(
        "() => document.querySelector('#mosca-keep')?.disabled === false", timeout=20_000)


def _recipe(page) -> dict:
    return json.loads(page.locator("#process-canvas").get_attribute("data-rendered-recipe"))


def test_mosca_beginning_is_empty_and_full_cutoff_enables_keep(ui, server):
    _select(ui)
    assert _recipe(ui)["progress"] == 1
    scrub = ui.locator("#mosca-scrub")
    scrub.evaluate("el => { el.value = 0; el.dispatchEvent(new Event('input', {bubbles: true})); }")
    ui.wait_for_function("""() => {
      const recipe = document.querySelector('#process-canvas')?.dataset.renderedRecipe;
      return recipe && JSON.parse(recipe).progress === 0;
    }""")
    assert ui.locator("#mosca-keep").is_disabled()
    assert ui.locator("#process-canvas .draw-line").count() == 0
    scrub.evaluate("el => { el.value = 1; el.dispatchEvent(new Event('input', {bubbles: true})); }")
    ui.wait_for_function("() => document.querySelector('#mosca-keep')?.disabled === false")
    assert _recipe(ui)["progress"] == 1
    assert ui.locator("#process-canvas .draw-line").count() == 1
    assert not ui.errors


def test_mosca_keep_stays_open_creates_layers_and_resume_restores_recipe(ui, server):
    _select(ui)
    ui.locator("#mosca-scrub").evaluate(
        "el => { el.value = .5; el.dispatchEvent(new Event('input', {bubbles: true})); }")
    ui.wait_for_function("() => document.querySelector('#mosca-keep')?.disabled === false")
    first_recipe = _recipe(ui)
    assert first_recipe["progress"] == .5
    ui.click("#mosca-keep")
    ui.locator("#mosca-kept", has_text="Kept as a new layer").wait_for()
    first = _get(f"{server}/api/project")["layers"][0]
    assert ui.locator("#process-popup").is_visible()
    ui.locator("#mosca-scrub").evaluate(
        "el => { el.value = 1; el.dispatchEvent(new Event('input', {bubbles: true})); }")
    ui.wait_for_function("() => document.querySelector('#mosca-keep')?.disabled === false")
    ui.click("#mosca-keep")
    ui.locator("#mosca-kept", has_text="Kept as a new layer").wait_for()
    layers = _get(f"{server}/api/project")["layers"]
    assert len(layers) == 2 and layers[0] == first
    assert layers[0]["source"]["params"] == first_recipe
    ui.click("#process-close")
    # The dock presents the topmost layer first; the project keeps creation
    # order, so the first kept layer is the second visible row here.
    select_layer(ui, len(layers) - 1)
    ui.click("#process-resume")
    ui.wait_for_function("""() => {
      const recipe = document.querySelector('#process-canvas')?.dataset.renderedRecipe;
      return document.querySelector('#process-popup')?.classList.contains('mosca-bench')
        && recipe && JSON.parse(recipe).progress === .5;
    }""", timeout=20_000)
    assert _recipe(ui) == first_recipe
    assert not ui.errors


def test_mosca_latest_preview_wins_and_preview_error_retries(ui):
    _open(ui)
    held = []

    def intercept(route):
        if not held:
            held.append(route)
        else:
            route.continue_()

    ui.route("**/api/mosca/preview", intercept)
    ui.locator("#mosca-recordings summary").click()
    with ui.expect_request("**/api/mosca/preview"):
        ui.locator(".mosca-recording", has_text="loop").click()
    for _ in range(100):
        if held:
            break
        ui.wait_for_timeout(50)
    assert held, "the first preview was not intercepted"
    ui.fill("#mosca-tolerance", "0")
    ui.locator("#mosca-tolerance").dispatch_event("change")
    held[0].fulfill(response=held[0].fetch())
    ui.wait_for_function("() => document.querySelector('#mosca-keep')?.disabled === false", timeout=20_000)
    assert _recipe(ui)["tolerance"] == 0
    ui.unroute("**/api/mosca/preview", intercept)
    ui.route("**/api/mosca/preview", lambda route: route.fulfill(
        status=400, content_type="application/json", body='{"detail":"preview test failure"}'), times=1)
    ui.fill("#mosca-tolerance", "0.2")
    ui.locator("#mosca-tolerance").dispatch_event("change")
    ui.locator("#process-error").wait_for(state="visible", timeout=15_000)
    assert ui.locator("#mosca-keep").is_disabled()
    assert "preview test failure" in ui.locator("#process-error").inner_text()
    ui.click("#process-retry")
    ui.wait_for_function("() => document.querySelector('#mosca-keep')?.disabled === false")
    assert _recipe(ui)["tolerance"] == .2
    ui.errors[:] = [error for error in ui.errors if "400" not in error]
    assert not ui.errors
