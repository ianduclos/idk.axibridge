"""Magnetic bench user workflows, on the isolated real-server UI harness."""
import json
import os
from pathlib import Path

from test_acceptance_ui import (
    _get, frontend_mode, reload_app, select_layer, server, ui,
)


def open_magnetic(page):
    page.wait_for_function("() => !!document.querySelector('#gen-select option[value=magnetic_field]')", timeout=5000)
    page.select_option('#gen-select', 'magnetic_field')
    page.click('#btn-bench')
    ready(page)


def ready(page):
    page.wait_for_function("() => document.querySelector('#magnetic-keep')?.disabled === false", timeout=30000)


def recipe(page):
    return json.loads(page.locator('#process-canvas').get_attribute('data-rendered-recipe'))


def change(page, selector, value):
    page.fill(selector, str(value))
    page.locator(selector).dispatch_event('change')
    ready(page)


def test_magnetic_edit_keep_and_resume_preserve_original(ui, server):
    open_magnetic(ui)
    assert ui.locator('#magnetic-style').input_value() == 'continuous'
    assert ui.locator('#process-play').is_hidden()
    change(ui, '#magnetic-x', 83)
    ui.uncheck('#magnetic-show')
    ready(ui)
    ui.check('#magnetic-escaping')
    ready(ui)
    expected = recipe(ui)
    assert expected['magnets'][0]['x'] == 83
    assert not expected['show_magnets'] and expected['remove_escaping']
    assert not _get(f'{server}/api/project')['layers']
    ui.click('#magnetic-keep')
    ui.wait_for_function("() => document.querySelector('#magnetic-kept').textContent.includes('Kept')")
    first = _get(f'{server}/api/project')['layers'][0]
    assert first['source']['params'] == expected
    ui.click('#process-close')
    select_layer(ui)
    ui.click('#process-resume')
    ready(ui)
    assert recipe(ui) == expected
    ui.click('#magnetic-flip')
    ready(ui)
    ui.click('#magnetic-keep')
    ui.wait_for_function("() => document.querySelector('#magnetic-kept').textContent.includes('Kept')")
    layers = _get(f'{server}/api/project')['layers']
    assert len(layers) == 2 and layers[0] == first
    assert layers[1]['source']['params']['magnets'][0]['flipped']
    assert not ui.errors


def test_magnetic_scatter_replays_seed_and_undo_survives_close(ui):
    open_magnetic(ui)
    change(ui, '#magnetic-seed', 1234)
    ui.fill('#magnetic-count', '5')
    ui.select_option('#magnetic-scatter-type', 'both')
    ui.click('#magnetic-scatter')
    ready(ui)
    first = recipe(ui)
    assert len(first['magnets']) == 5
    assert {m['kind'] for m in first['magnets']} >= {'bar', 'north', 'south'}
    ui.click('#magnetic-reshuffle')
    ready(ui)
    assert recipe(ui)['magnets'] != first['magnets']
    ui.click('#magnetic-undo')
    ready(ui)
    assert recipe(ui) == first
    ui.click('#process-close')
    ui.click('#btn-bench')
    ready(ui)
    assert recipe(ui) == first
    ui.click('#magnetic-scatter')
    ready(ui)
    assert recipe(ui)['magnets'] == first['magnets']
    assert not ui.errors


def svg_point(page, x, y):
    return page.locator('#process-canvas').evaluate(
        '(el, p) => { const q = new DOMPoint(...p).matrixTransform(el.getScreenCTM()); return [q.x,q.y]; }', [x,y])


def shot(page, name):
    directory = os.environ.get('AXIBRIDGE_MAGNETIC_SHOTS')
    if directory:
        dest = Path(directory)
        dest.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(dest / f'{name}.png'))


def test_magnetic_drag_hidden_objects_cancel_and_keyboard_undo(ui, server):
    open_magnetic(ui)
    original = recipe(ui)
    shot(ui, 'default')
    start = svg_point(ui, 70, 85)
    end = svg_point(ui, 90, 95)
    ui.mouse.move(*start)
    ui.mouse.down()
    ui.mouse.move(*end, steps=5)
    assert ui.locator('#magnetic-keep').is_disabled()
    ui.mouse.up()
    ready(ui)
    assert abs(recipe(ui)['magnets'][0]['x']-90) < .1
    ui.locator('#magnetic-undo').focus()
    ui.keyboard.press('Meta+z')
    ready(ui)
    assert recipe(ui) == original
    # Escape during capture restores the magnet and leaves the popup open.
    ui.mouse.move(*start)
    ui.mouse.down()
    ui.mouse.move(*end, steps=3)
    ui.keyboard.press('Escape')
    ui.mouse.up()
    ready(ui)
    assert recipe(ui) == original
    assert ui.locator('#process-popup').is_visible()
    ui.uncheck('#magnetic-show')
    ready(ui)
    ui.select_option('#magnetic-selection','1')
    change(ui,'#magnetic-rotation',42)
    assert recipe(ui)['magnets'][1]['rotation'] == 42
    assert ui.locator('.magnetic-selected .magnetic-rotate').is_visible()
    shot(ui, 'hidden-editing')
    assert not _get(f'{server}/api/project')['layers']
    assert not ui.errors


def test_magnetic_latest_preview_wins_and_errors_retry(ui):
    open_magnetic(ui)
    held = []
    def intercept(route):
        if not held:
            held.append(route)
        else:
            route.continue_()
    ui.route('**/api/generators/preview', intercept)
    with ui.expect_request('**/api/generators/preview'):
        ui.uncheck('#magnetic-show')
    assert ui.locator('#magnetic-keep').is_disabled()
    assert held
    ui.check('#magnetic-escaping')
    route = held[0]
    route.fulfill(response=route.fetch())
    ready(ui)
    assert not recipe(ui)['show_magnets'] and recipe(ui)['remove_escaping']
    ui.unroute('**/api/generators/preview', intercept)
    ui.route('**/api/generators/preview', lambda route: route.fulfill(
        status=400,content_type='application/json',body='{"detail":"Preview test failure"}'), times=1)
    ui.select_option('#magnetic-style','chains')
    ui.locator('#process-error').wait_for(state='visible')
    assert ui.locator('#magnetic-keep').is_disabled()
    assert 'Preview test failure' in ui.locator('#process-error').inner_text()
    ui.click('#process-retry')
    ready(ui)
    assert recipe(ui)['style'] == 'chains'


def test_magnetic_small_frame_scatter_clear_and_other_bench_lifecycle(ui):
    open_magnetic(ui)
    ui.locator('#process-magnetic details').last.locator('summary').click()
    change(ui,'#magnetic-width',40)
    change(ui,'#magnetic-height',40)
    ui.fill('#magnetic-count','16')
    ui.select_option('#magnetic-scatter-type','both')
    ui.click('#magnetic-scatter')
    ready(ui)
    assert len(recipe(ui)['magnets']) == 16
    assert ui.locator('#magnetic-add-bar').is_disabled()
    ui.set_viewport_size({'width':850,'height':750})
    ui.click('#process-controls-toggle')
    assert ui.locator('#process-magnetic').is_visible()
    shot(ui,'narrow')
    ui.click('#magnetic-clear')
    ready(ui)
    assert recipe(ui)['magnets'] == []
    assert not ui.locator('.magnetic-ink polyline').count()
    ui.click('#process-close')
    ui.set_viewport_size({'width':1500,'height':950})
    ui.select_option('#gen-select','homeostat')
    ui.click('#btn-bench')
    ui.locator('#process-play').wait_for(state='visible')
    assert ui.locator('#process-magnetic').is_hidden()
    assert ui.locator('#process-telemetry-row').is_visible()
    assert not ui.errors


def test_magnetic_hidden_footprints_are_optional_and_saved(ui):
    open_magnetic(ui)
    ui.uncheck('#magnetic-show')
    ready(ui)
    ui.select_option('#magnetic-selection','-1')
    assert not ui.locator('.magnetic-selected').count()
    with_voids = ui.locator('.magnetic-ink').inner_html()
    shot(ui,'empty-silhouettes')
    ui.uncheck('#magnetic-silhouettes')
    ready(ui)
    assert not recipe(ui)['keep_silhouettes']
    assert ui.locator('.magnetic-ink').inner_html() != with_voids
    shot(ui,'filled-footprints')
    ui.check('#magnetic-escaping')
    ready(ui)
    shot(ui,'contained-no-silhouettes')
    ui.click('#process-close')
    ui.click('#btn-bench')
    ready(ui)
    assert not recipe(ui)['keep_silhouettes']
    assert recipe(ui)['remove_escaping']
    assert not ui.errors
