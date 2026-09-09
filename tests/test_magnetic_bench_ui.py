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


def test_scatter_strengths_locks_and_preset_topology(ui):
    open_magnetic(ui)
    assert ui.locator('#magnetic-lock').count() == 1
    ui.check('#magnetic-lock')
    ready(ui)
    anchor = recipe(ui)['magnets'][0]
    change(ui, '#magnetic-strength-min', .3)
    change(ui, '#magnetic-strength-max', 2.5)
    ui.fill('#magnetic-count', '5')
    ui.click('#magnetic-reshuffle')
    ready(ui)
    first = recipe(ui)
    assert first['magnets'][0] == anchor
    strengths = [m['strength'] for m in first['magnets'][1:]]
    assert len(set(strengths)) > 1 and all(.3 <= s <= 2.5 for s in strengths)
    ui.click('#magnetic-scatter')
    ready(ui)
    assert recipe(ui)['magnets'] == first['magnets']
    ui.click('#magnetic-store-0')
    ready(ui)
    assert ui.locator('#magnetic-count').is_disabled()
    assert ui.locator('#magnetic-add-bar').is_disabled()
    before = recipe(ui)['magnets']
    ui.click('#magnetic-reshuffle')
    ready(ui)
    after = recipe(ui)['magnets']
    assert after[0] == anchor and after[1:] != before[1:]
    assert [m['kind'] for m in before] == [m['kind'] for m in after]
    ui.click('#magnetic-clear-presets')
    ready(ui)
    assert ui.locator('#magnetic-count').is_enabled()
    assert not ui.errors


def test_four_corner_blend_undo_and_keep_resume(ui, server):
    open_magnetic(ui)
    assert ui.locator('#magnetic-mix-x').count() == 1
    assert ui.locator('#magnetic-mix-x').is_disabled()
    # A/B/C/D on a rectangle. Angles cross the +/-180 seam.
    for i, (x, y, angle, strength) in enumerate([
        (60, 60, 170, .5), (100, 60, -170, 1.5),
        (60, 100, 170, 1.5), (100, 100, -170, 2.5),
    ]):
        for field, value in [('x', x), ('y', y), ('rotation', angle), ('strength', strength)]:
            change(ui, f'#magnetic-{field}', value)
        ui.click(f'#magnetic-store-{i}')
        ready(ui)
    assert ui.locator('#magnetic-mix-x').is_enabled()
    assert ui.locator('#magnetic-count').input_value() == '2'
    change(ui, '#magnetic-mix-x', .5)
    change(ui, '#magnetic-mix-y', .5)
    center = recipe(ui)
    m = center['magnets'][0]
    assert (m['x'], m['y'], m['strength']) == (80, 80, 1.5)
    assert abs(m['rotation']) == 180
    assert center['mix_active']
    # Multiple input events make one history entry when released.
    ui.locator('#magnetic-mix-x').evaluate("el => { for (const x of [.6,.7,.8]) { el.value=x; el.dispatchEvent(new Event('input')); } el.dispatchEvent(new Event('change')); }")
    ready(ui)
    assert recipe(ui)['magnets'][0]['x'] == 92
    ui.click('#magnetic-undo')
    ready(ui)
    assert recipe(ui) == center
    ui.click('#magnetic-recall-0')
    ready(ui)
    recalled = recipe(ui)
    assert recalled['magnets'][0]['x'] == 60
    assert recalled['magnets'][0]['rotation'] == 170
    assert recalled['mix_x'] == recalled['mix_y'] == 0
    ui.click('#magnetic-keep')
    ui.wait_for_function("() => document.querySelector('#magnetic-kept').textContent.includes('Kept')")
    assert _get(f'{server}/api/project')['layers'][0]['source']['params'] == recalled
    ui.click('#process-close')
    select_layer(ui)
    ui.click('#process-resume')
    ready(ui)
    assert recipe(ui) == recalled
    assert ui.locator('#magnetic-mix-x').is_enabled()
    shot(ui, 'four-corners')
    assert not ui.errors


def test_mix_cancel_and_latest_preview_cannot_keep_stale_geometry(ui):
    open_magnetic(ui)
    for i in range(4):
        change(ui, '#magnetic-x', 60+i*15)
        ui.click(f'#magnetic-store-{i}')
        ready(ui)
    before = recipe(ui)
    held = []
    def intercept(route):
        if not held:
            held.append(route)
        else:
            route.continue_()
    ui.route('**/api/generators/preview', intercept)
    with ui.expect_request('**/api/generators/preview'):
        ui.locator('#magnetic-mix-x').evaluate("el => {el.value=.2; el.dispatchEvent(new Event('input'));}")
    assert ui.locator('#magnetic-keep').is_disabled()
    ui.locator('#magnetic-mix-x').focus()
    ui.keyboard.press('Escape')
    held[0].fulfill(response=held[0].fetch())
    ready(ui)
    assert recipe(ui) == before
    assert ui.locator('#process-popup').is_visible()
    ui.unroute('**/api/generators/preview', intercept)
    change(ui, '#magnetic-mix-x', .25)
    change(ui, '#magnetic-mix-y', .75)
    assert recipe(ui)['magnets'][0]['x'] == 86.25
    change(ui, '#magnetic-pole-spacing', .3)
    assert recipe(ui)['pole_spacing'] == .3
    shot(ui, 'mixed')
    ui.set_viewport_size({'width':850,'height':750})
    ui.click('#process-controls-toggle')
    ui.locator('#magnetic-mix-x').scroll_into_view_if_needed()
    shot(ui, 'corners-narrow')
    assert not ui.errors
