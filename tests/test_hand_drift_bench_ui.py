"""Hand Drift bench user workflows, on the isolated real-server UI harness."""
import json
import os
from pathlib import Path

from test_acceptance_ui import _get, frontend_mode, select_layer, server, ui  # noqa: F401


def open_hand_drift(page):
    page.wait_for_function("() => !!document.querySelector('#gen-select option[value=hand_drift]')", timeout=5000)
    page.select_option('#gen-select', 'hand_drift')
    page.click('#btn-bench')
    ready(page)


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
    assert not _get(f'{server}/api/project')['layers']
    ui.click('#hand-drift-keep')
    ui.wait_for_function("() => document.querySelector('#hand-drift-kept').textContent.includes('Kept')")
    layers = _get(f'{server}/api/project')['layers']
    assert len(layers) == 1 and layers[0]['source']['generator'] == 'hand_drift'
    assert layers[0]['source']['params'] == expected

    # Resume copies the kept recipe; Keep makes another layer, the first is untouched.
    ui.click('#process-close')
    select_layer(ui)
    ui.click('#process-resume')
    ready(ui)
    assert recipe(ui) == expected
    ui.click('#hd-route_per_line-each')
    ready(ui)
    ui.click('#hand-drift-keep')
    ui.wait_for_function("() => document.querySelector('#hand-drift-kept').textContent.includes('Kept')")
    layers = _get(f'{server}/api/project')['layers']
    assert len(layers) == 2 and layers[0]['source']['params'] == expected
    assert layers[1]['source']['params']['route_per_line'] == 'each'
    assert not ui.errors


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
    ui.click('#btn-bench')
    ready(ui)
    assert recipe(ui) == changed
    assert not ui.errors
