"""Hand Drift bench user workflows, on the isolated real-server UI harness."""
import json
import os
from pathlib import Path

from test_acceptance_ui import _get, add_layer, frontend_mode, select_layer, server, ui  # noqa: F401
from test_live_sync_ui import wait_until_drawn


def open_hand_drift(page):
    """Hand Drift left the generator dropdown for the Gesture Studies bench (where
    it is the first study); a kept Hand Drift layer still resumes in its bench."""
    page.wait_for_function("() => !!document.querySelector('#gen-select option[value=gesture_studies]')",
                           timeout=5000)
    assert not page.locator('#gen-select option[value=hand_drift]').count()
    add_layer(page, 'hand_drift', {'seed': 7000})
    page.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 1")
    wait_until_drawn(page)     # don't race the seeded layer's own render (409 render_cancelled)
    resume(page, 0)


def resume(page, index):
    select_layer(page, index)
    page.click('#process-resume')
    ready(page)


def real_errors(page):
    """Console errors, minus 409 render_cancelled: resuming from a layer redraws
    the canvas, superseding an in-flight /api/plan, which the app absorbs by
    design (see test_live_sync_ui.wait_until_drawn) but Chromium still logs."""
    return [e for e in page.errors if 'status of 409' not in e]


def ready(page):
    page.wait_for_function("() => document.querySelector('#hand-drift-keep')?.disabled === false", timeout=60000)


def recipe(page):
    return json.loads(page.locator('#process-canvas').get_attribute('data-rendered-recipe'))


def ink(page):
    return page.eval_on_selector_all('#process-canvas .hand-drift-ink polyline',
                                     'els => els.map(e => e.getAttribute("points")).join("|")')


def shot(page, name):
    directory = os.environ.get('AXIBRIDGE_HAND_DRIFT_SHOTS')
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(directory) / f'{name}.png'))


def test_hand_drift_switches_change_the_preview_keep_and_resume(ui, server):
    open_hand_drift(ui)
    assert ui.locator('#process-title').text_content() == 'Hand Drift — working bench'
    assert ui.locator('#process-play').is_hidden()
    # the switches are visible controls, defaults pressed
    for button in ('#hd-blend-mixture', '#hd-joins-smooth', '#hd-route_per_line-same', '#hd-regimes-off'):
        assert ui.locator(button).get_attribute('aria-pressed') == 'true'
    first = ink(ui)
    assert first
    shot(ui, 'default')

    ui.click('#hd-joins-chain')
    ready(ui)
    assert recipe(ui)['joins'] == 'chain'
    assert ui.locator('#hd-joins-chain').get_attribute('aria-pressed') == 'true'
    assert ink(ui) != first

    ui.click('#hd-regimes-timing')
    ready(ui)
    assert recipe(ui)['regimes'] == 'timing'
    assert ui.locator('#hd-timing').is_visible()
    shot(ui, 'timing')

    expected = recipe(ui)
    assert len(_get(f'{server}/api/project')['layers']) == 1
    ui.click('#hand-drift-keep')
    ui.wait_for_function("() => document.querySelector('#hand-drift-kept').textContent.includes('Kept')")
    layers = _get(f'{server}/api/project')['layers']
    assert len(layers) == 2 and layers[1]['source']['generator'] == 'hand_drift'
    assert layers[1]['source']['params'] == expected

    # Resume copies the kept recipe; Keep makes another layer, the first is untouched.
    ui.click('#process-close')
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 2")
    resume(ui, 1)
    assert recipe(ui) == expected
    ui.click('#hd-route_per_line-each')
    ready(ui)
    ui.click('#hand-drift-keep')
    ui.wait_for_function("() => document.querySelector('#hand-drift-kept').textContent.includes('Kept')")
    layers = _get(f'{server}/api/project')['layers']
    assert len(layers) == 3 and layers[1]['source']['params'] == expected
    assert layers[2]['source']['params']['route_per_line'] == 'each'
    assert not real_errors(ui)


def test_hand_drift_undo_and_draft_survive_close(ui):
    open_hand_drift(ui)
    original = recipe(ui)
    ui.click('#hd-blend-interp')
    ready(ui)
    changed = recipe(ui)
    assert changed['blend'] == 'interp'
    ui.click('#hand-drift-undo')
    ready(ui)
    assert recipe(ui) == original
    ui.click('#hand-drift-redo')
    ready(ui)
    ui.click('#process-close')
    resume(ui, 0)
    assert recipe(ui) == changed
    assert not real_errors(ui)
