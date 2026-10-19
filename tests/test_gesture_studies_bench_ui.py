"""Gesture Studies bench user workflows, on the isolated real-server UI harness."""
import json
import os
from pathlib import Path

import pytest
from test_acceptance_ui import _get, _post, frontend_mode, reload_app, select_layer, server, ui  # noqa: F401


def open_bench(page):
    page.wait_for_function("() => !!document.querySelector('#gen-select option[value=gesture_studies]')",
                           timeout=5000)
    assert not page.locator('#gen-select option[value=hand_drift]').count()   # the study replaces it
    page.select_option('#gen-select', 'gesture_studies')
    page.click('#btn-bench')
    ready(page)


def ready(page):
    page.wait_for_function("() => document.querySelector('#gesture-studies-keep')?.disabled === false",
                           timeout=90000)


def recipe(page):
    return json.loads(page.locator('#process-canvas').get_attribute('data-rendered-recipe'))


def ink(page):
    return page.eval_on_selector_all('#process-canvas .gesture-studies-ink polyline',
                                     'els => els.map(e => e.getAttribute("points")).join("|")')


def shot(page, name):
    directory = os.environ.get('AXIBRIDGE_GESTURE_STUDIES_SHOTS')
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(directory) / f'{name}.png'))


def control(page, key):
    return page.locator(f'#process-gesture-studies [data-control-key="{key}"]')


def advanced(page, summary):
    """Presets, Save as new study and Edit recipe live under Advanced (collapsed)."""
    if not page.locator('#gs-advanced').evaluate('d => d.open'):
        page.click('#gs-advanced > summary')
    page.click(f'{summary} summary')


def test_study_dropdown_controls_preview_keep_and_save(ui, server):
    open_bench(ui)
    assert ui.locator('#process-title').text_content() == 'Gesture Studies — working bench'
    assert ui.locator('#gs-study').input_value() == 'hand_drift'
    labels = ui.eval_on_selector_all('#gs-study option', 'os => os.map(o => o.value)')
    assert labels[:8] == ['hand_drift', 'danced_chain', 'two_voices', 'drawing_and_measure', 'shape_atlas',
                          'conversation', 'annotated_page', 'three_voices']
    assert control(ui, 'hand_1').is_visible() and recipe(ui)['study']['id'] == 'hand_drift'
    first = ink(ui)
    assert first
    shot(ui, 'hand-drift')

    # switching the study swaps the controls and the drawing
    ui.select_option('#gs-study', 'drawing_and_measure')
    ready(ui)
    assert recipe(ui)['study']['id'] == 'drawing_and_measure'
    assert control(ui, 'parts.0.modulators.1.chart').is_visible()
    assert not control(ui, 'hand_1').count()
    before = ink(ui)
    assert before and before != first

    # a control changes the preview
    control(ui, 'parts.0.modulators.1.chart').locator('button', has_text='route').click()
    ready(ui)
    assert recipe(ui)['values']['parts.0.modulators.1.chart'] == 'route'
    assert ink(ui) != before
    # hand controls list every library hand (more than the Hand Drift generator's eight)
    route = control(ui, 'parts.0.voice.hands').locator('select').first
    assert route.locator('option').count() >= 24
    shot(ui, 'drawing-and-measure')

    # Keep makes a layer that carries the study snapshot and pins the library
    expected = recipe(ui)
    assert not _get(f'{server}/api/project')['layers']
    ui.click('#gesture-studies-keep')
    ui.wait_for_function("() => document.querySelector('#gesture-studies-kept').textContent.includes('Kept')")
    layers = _get(f'{server}/api/project')['layers']
    assert len(layers) == 1 and layers[0]['source']['generator'] == 'gesture_studies'
    kept = layers[0]['source']['params']
    assert kept['study'] == expected['study'] and kept['values'] == expected['values']
    assert kept['library'] and {p['id'] for p in kept['pins']} >= {'matisse', 'shikasta', 'lichtenberg'}

    # Save as new study appears in the dropdown (and in the store)
    advanced(ui, '#gs-save-group')
    ui.fill('#gs-save-name', 'Route chart')
    ui.click('#gs-save')
    ui.wait_for_function("() => document.querySelector('#gs-save-status').textContent.startsWith('Saved')")
    ready(ui)
    selected = ui.locator('#gs-study option:checked').text_content()
    assert selected == 'Route chart'
    saved = [s for s in _get(f'{server}/api/gesture-studies')['studies'] if s['label'] == 'Route chart']
    assert len(saved) == 1 and saved[0]['parent'] == {'id': 'drawing_and_measure', 'version': 1}
    assert saved[0]['recipe']['parts'][0]['modulators'][1]['chart'] == 'route'
    assert recipe(ui)['study']['id'] == saved[0]['id']
    shot(ui, 'saved')

    # Resume a kept layer: its recipe (and pins) in a fresh draft. (Closing hands the
    # draft back to the Generate panel, which live-edits the layer it last made.)
    ui.click('#process-close')
    ui.wait_for_timeout(500)
    kept = _get(f'{server}/api/project')['layers'][0]['source']['params']
    select_layer(ui)
    ui.click('#process-resume')
    ready(ui)
    assert recipe(ui) == kept and kept['library'] and kept['pins']
    assert not ui.errors


def test_edit_recipe_drawer_validates(ui):
    open_bench(ui)
    ui.select_option('#gs-study', 'drawing_and_measure')
    ready(ui)
    advanced(ui, '#gs-recipe-group')
    ui.wait_for_function("() => document.querySelector('#gs-recipe').value.includes('handover')")
    edited = json.loads(ui.locator('#gs-recipe').input_value())
    ui.fill('#gs-recipe', '{ not json')
    ui.click('#gs-recipe-apply')
    assert 'Not valid JSON' in ui.locator('#gs-recipe-error').text_content()
    edited['parts'][0]['voice']['length'] = 99
    ui.fill('#gs-recipe', json.dumps(edited))
    ui.click('#gs-recipe-apply')
    ui.wait_for_function("() => !document.querySelector('#gs-recipe-error').hidden")
    assert 'length' in ui.locator('#gs-recipe-error').text_content()
    edited['parts'][0]['voice']['length'] = 3.0
    ui.fill('#gs-recipe', json.dumps(edited))
    ui.click('#gs-recipe-apply')
    ui.wait_for_function("() => JSON.parse(document.querySelector('#process-canvas').dataset.renderedRecipe || '{}')"
                         ".study?.recipe?.parts?.[0]?.voice?.length === 3", timeout=90000)
    assert ui.locator('#gs-study').input_value() == '__draft__'
    # the only console noise is the refused (400) recipe above
    assert all('status of 400' in e for e in ui.errors), ui.errors


# ---------------------------------------------------------------------------
# Studies v2
# ---------------------------------------------------------------------------

def test_new_studies_follow_the_eight(ui):
    open_bench(ui)
    labels = ui.eval_on_selector_all('#gs-study option', 'os => os.map(o => o.value)')
    assert labels[8:15] == ['numbered_atlas', 'dance_atlas', 'margin_chart', 'merged_shadow', 'chorus', 'sampler',
                            'ledger_straight']
    # the numbered atlas exposes the drawing's route only, never layout or numbering
    ui.select_option('#gs-study', 'numbered_atlas')
    ready(ui)
    keys = ui.eval_on_selector_all('#process-gesture-studies [data-control-key]',
                                   'els => els.map(e => e.dataset.controlKey)')
    assert set(keys) == {'parts.0.voice.hands', 'parts.0.voice.blend', 'parts.0.voice.joins', 'seed'}
    # the margin chart offers every layout but the wrap
    ui.select_option('#gs-study', 'margin_chart')
    ready(ui)
    layouts = control(ui, 'parts.0.modulators.0.layout').locator('.gs-switch button').all_text_contents()
    assert layouts == ['margin', 'diptych', 'under']
    # the sampler names the combination its seed picked, and the next seed picks another
    ui.select_option('#gs-study', 'sampler')
    ready(ui)
    ui.wait_for_function("() => document.querySelector('#gs-summary .gs-summary-text')?.textContent.includes(' x ')",
                         timeout=30000)
    first = ui.locator('#gs-summary .gs-summary-text').text_content()
    shot(ui, 'sampler')
    control(ui, 'seed').locator('.gs-next-seed').click()
    ready(ui)
    ui.wait_for_function("(a) => { const t = document.querySelector('#gs-summary .gs-summary-text')?.textContent;"
                         " return t && t !== a; }", arg=first, timeout=30000)
    assert not ui.errors


def test_chorus_keeps_as_a_group_with_one_layer_per_voice_on_its_own_pen(ui, server):
    open_bench(ui)
    ui.select_option('#gs-study', 'chorus')
    ready(ui)
    inks = ui.eval_on_selector_all('#process-canvas .gs-voice', 'gs => gs.map(g => g.style.getPropertyValue("--gs-voice"))')
    assert len(inks) == 4 and len(set(inks)) == 4                  # every voice in its own ink
    ui.wait_for_function("() => document.querySelectorAll('#gs-summary .gs-voices li').length === 4")
    assert ui.locator('#gesture-studies-keep').text_content() == 'Keep as group'
    shot(ui, 'chorus')
    # three voices: the first three of the four
    control(ui, 'arranger.voices').locator('input').evaluate(
        "el => { el.value = '3'; el.dispatchEvent(new Event('change')); }")
    ready(ui)
    ui.wait_for_function("() => document.querySelectorAll('#process-canvas .gs-voice').length === 3")
    ui.click('#gesture-studies-keep')
    ui.wait_for_function("() => document.querySelector('#gesture-studies-kept').textContent.includes('group')",
                         timeout=90000)
    assert '3 layers on 3 pens' in ui.locator('#gesture-studies-kept').text_content()
    project = _get(f'{server}/api/project')
    groups = [g for g in project['groups'] if g['name'] == 'Chorus, several pens']
    assert len(groups) == 1
    members = [l for l in project['layers'] if l['group_id'] == groups[0]['id']]
    assert [l['source']['params']['voice'] for l in members] == [0, 1, 2]
    assert len({l['pen_id'] for l in members}) == 3 and all(l['pen_id'] for l in members)
    assert len({l['source']['params']['library'] for l in members}) == 1

    # resume one voice: the bench reopens the whole chorus
    ui.click('#process-close')
    ui.wait_for_timeout(500)
    ui.get_by_role('button', name='Enter Chorus, several pens').click()
    row = ui.locator('#layer-list .layer-row', has_text='Chorus, several pens · red')
    row.locator('.lname').click()
    ui.wait_for_selector('#layer-detail-panel:not([hidden])', timeout=10000)
    ui.click('#process-resume')
    ready(ui)
    resumed = recipe(ui)
    assert 'voice' not in resumed and resumed['study']['id'] == 'chorus'
    ui.wait_for_function("() => document.querySelectorAll('#process-canvas .gs-voice').length === 3")
    assert not ui.errors


def test_a_resumed_layer_stays_pinned_until_updated_on_purpose(ui, server):
    from axibridge.sources._gesture_studies import frozen_library as FL
    from axibridge.sources._gesture_studies import studies as ST

    history = FL.index()['history']
    if len(history) < 2:
        pytest.skip('the frozen library has a single snapshot')
    old, current = history[0], FL.current_snapshot()
    study = ST.builtin('three_voices').model_dump(mode='json')
    made = _post(f'{server}/api/layers/generate', {'module': 'gesture_studies',
                                                   'params': {'study': study, 'values': {}, 'library': old}})
    assert made['source']['params']['library'] == old
    reload_app(ui)
    # seeding behind the page's back supersedes the OLD page's in-flight render (409 render_cancelled)
    ui.errors[:] = [e for e in ui.errors if 'status of 409' not in e]
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 1", timeout=10000)
    select_layer(ui)
    ui.click('#process-resume')
    ready(ui)
    assert ui.locator('#gs-pinned').is_visible()
    assert old in ui.locator('#gs-pinned-text').text_content()
    hands_old = len(FL.options('hand', old))
    voice = control(ui, 'parts.1.voice.hand').locator('select')
    assert voice.locator('option').count() == hands_old         # the hands of ITS snapshot
    # an edit keeps the snapshot …
    control(ui, 'seed').locator('.gs-next-seed').click()
    ready(ui)
    assert recipe(ui)['library'] == old
    ui.click('#gesture-studies-keep')
    ui.wait_for_function("() => document.querySelector('#gesture-studies-kept').textContent.includes('Kept')")
    layers = _get(f'{server}/api/project')['layers']
    assert layers[-1]['source']['params']['library'] == old
    assert layers[-1]['source']['params']['values']['seed'] != made['source']['params']['values'].get('seed')
    # … until "Update to current library"
    ui.click('#gs-update-library')
    ready(ui)
    assert not ui.locator('#gs-pinned').is_visible()
    assert 'library' not in recipe(ui)
    assert voice.locator('option').count() == len(FL.options('hand'))
    ui.click('#gesture-studies-keep')
    for _ in range(100):
        layers = _get(f'{server}/api/project')['layers']
        if len(layers) == 3:
            break
        ui.wait_for_timeout(200)
    assert len(layers) == 3 and layers[-1]['source']['params']['library'] == current
    assert not ui.errors


# ---------------------------------------------------------------------------
# Bench v3 (2026-10-19): gallery, dice, Shuffle, locks, history, dimmed controls
# ---------------------------------------------------------------------------

def test_gallery_dice_and_history(ui, server):
    open_bench(ui)
    # it opens full-screen, the drawing first
    assert 'expanded' in ui.locator('#process-popup').get_attribute('class')
    assert ui.locator('#gs-study-name').text_content() == 'Hand Drift'
    # a control that does nothing right now is dimmed and says why
    nib = control(ui, 'nib_angle')
    assert 'gs-inactive' in nib.get_attribute('class')
    assert 'acts when Regimes is field' in nib.locator('.gs-why').text_content()
    assert 'gs-inactive' not in control(ui, 'hand_1').get_attribute('class')
    # Measure is there, every device off ("has to be optional")
    assert ui.locator('#gs-measure').is_visible()
    assert ui.locator('#gs-measure .gs-device-toggle input').count() == 13
    assert ui.locator('#gs-measure .gs-device-toggle input:checked').count() == 0
    assert ui.locator('#gs-history .gs-history-item').count() == 1

    # the gallery: every study as a card, grouped by family; a card opens its study
    ui.click('#gs-gallery-open')
    assert ui.locator('#gs-gallery').is_visible() and not ui.locator('#process-canvas').is_visible()
    families = ui.locator('#gs-gallery .gs-family h3').all_text_contents()
    assert families[:6] == ['Hands and drift', 'Measurement', 'Several voices', 'Swell', 'After Oehlen', 'Rivers']
    assert ui.locator('#gs-gallery .gs-card').count() >= 28
    card = ui.locator('#gs-gallery .gs-card[data-study-id="bold_swell"]')
    assert 'very nice' in card.locator('.gs-card-words').text_content()      # Ian's own words
    card.locator('img').wait_for(timeout=60000)                               # its thumbnail arrives
    shot(ui, 'gallery')
    card.click()
    assert not ui.locator('#gs-gallery').is_visible()
    ready(ui)
    assert recipe(ui)['study']['id'] == 'bold_swell'
    assert ui.locator('#gs-history .gs-history-item').count() == 2
    # Dot shape acts only with dots on
    assert 'gs-inactive' in control(ui, 'renderer.dot_shape').get_attribute('class')
    control(ui, 'renderer.dots').locator('button', has_text='count').click()
    ready(ui)
    assert 'gs-inactive' not in control(ui, 'renderer.dot_shape').get_attribute('class')

    # the seed's die draws a random seed; each preview joins the strip
    seed = recipe(ui)['values'].get('seed', 7601)
    ui.click('#gs-seed-die')
    ready(ui)
    assert recipe(ui)['values']['seed'] != seed
    assert ui.locator('#gs-history .gs-history-item').count() == 4

    # a lock keeps a control through Shuffle; Shuffle and the lock are undoable
    hand = recipe(ui)['values'].get('parts.0.voice.hand', 'shikasta')
    control(ui, 'parts.0.voice.hand').locator('.gs-lock').click()
    assert control(ui, 'parts.0.voice.hand').locator('.gs-lock').get_attribute('aria-pressed') == 'true'
    before = recipe(ui)
    ui.click('#gs-shuffle')
    ready(ui)
    after = recipe(ui)
    assert after != before and after['values'].get('parts.0.voice.hand', 'shikasta') == hand
    ui.click('#gesture-studies-undo')
    ready(ui)
    assert recipe(ui) == before
    ui.click('#gesture-studies-undo')
    assert control(ui, 'parts.0.voice.hand').locator('.gs-lock').get_attribute('aria-pressed') == 'false'

    # a hand's die picks another library hand
    control(ui, 'parts.0.voice.hand').locator('.gs-die').click()
    ready(ui)
    assert recipe(ui)['values']['parts.0.voice.hand'] != hand

    # the strip goes back: the first Bold swell preview, in one step
    items = ui.locator('#gs-history .gs-history-item')
    n = items.count()
    assert 4 <= n <= 12
    ui.locator('#gs-history .gs-history-item[aria-label*="Bold swell"]').last.click()
    ready(ui)
    assert recipe(ui)['study']['id'] == 'bold_swell' and recipe(ui)['values'] == {}
    assert ui.locator('#gs-history [aria-current="true"]').count() == 1
    shot(ui, 'history')
    ui.click('#gesture-studies-undo')
    ready(ui)
    assert recipe(ui)['values'].get('parts.0.voice.hand', hand) != hand
    assert not ui.errors


def device(page, label):
    return page.get_by_label(f'Measure: {label}', exact=True)


def test_measure_devices_preview_and_keep_as_a_group(ui, server):
    """Bench v3 move G: a device is a toggle with a placement; it previews as
    its own run (its own colour and width) and Keep makes a group of the
    drawing and a Measure layer on its own pen. One that has nothing to read
    in the study says so."""
    open_bench(ui)
    ui.select_option('#gs-study', 'river_zoom')
    ready(ui)
    families = ui.locator('#gs-measure .gs-device-family h5').all_text_contents()
    assert families == ["From the drawing's process", 'General']
    assert ui.locator('#gesture-studies-keep').text_content() == 'Keep as layer'
    plain = ink(ui)
    width = float(ui.locator('#process-canvas').get_attribute('viewBox').split()[2])
    assert not ui.locator('#process-canvas .gs-measure-ink').count()

    # the rose sits beside the drawing: the sheet grows, the drawing stays
    device(ui, 'Heading rose').check()
    ready(ui)
    assert recipe(ui)['devices'] == [{'id': 'heading_rose', 'place': 'beside', 'side': 'right', 'size': 60.0}]
    assert float(ui.locator('#process-canvas').get_attribute('viewBox').split()[2]) == width + 60
    assert ui.locator('#process-canvas .gs-measure-ink polyline').count() > 0
    assert plain in ink(ui)                                          # the drawing itself is unchanged
    row = ui.locator('#gs-measure .gs-device[data-device="heading_rose"]')
    assert row.locator('.gs-place button[aria-pressed="true"]').text_content() == 'beside'
    assert ui.locator('#gesture-studies-keep').text_content() == 'Keep as group'

    # placement: in the bottom margin instead (the sheet is its own size again)
    row.locator('.gs-place button', has_text='margin').click()
    ready(ui)
    assert recipe(ui)['devices'][0]['place'] == 'margin'
    assert float(ui.locator('#process-canvas').get_attribute('viewBox').split()[2]) == width

    # a process device with nothing to read in this study says so
    device(ui, 'Arcs of the score').check()
    ready(ui)
    note = ui.locator('#gs-measure .gs-device[data-device="meas_arcs"] .gs-device-note')
    assert 'no score' in note.text_content()
    shot(ui, 'measure-nothing-to-read')
    # undo takes the device off again, in one step
    ui.click('#gesture-studies-undo')
    ready(ui)
    assert [d['id'] for d in recipe(ui)['devices']] == ['heading_rose']
    assert not device(ui, 'Arcs of the score').is_checked()

    # the river's own km along the line, beside the bottom
    device(ui, 'Stations (river km / dance seconds)').check()
    ready(ui)
    assert [d['id'] for d in recipe(ui)['devices']] == ['meas_stations', 'heading_rose']
    assert not ui.locator('#gs-measure .gs-device[data-device="meas_stations"] .gs-device-note').count()
    shot(ui, 'measure-river-km')

    # Keep: a group of the drawing and a Measure layer, the Measure on its own pen
    assert not _get(f'{server}/api/project')['layers']
    ui.click('#gesture-studies-keep')
    ui.wait_for_function("() => document.querySelector('#gesture-studies-kept').textContent.includes('Kept')")
    assert 'with Measure' in ui.locator('#gesture-studies-kept').text_content()
    proj = _get(f'{server}/api/project')
    assert len(proj['groups']) == 1 and proj['groups'][0]['name'] == 'Amazon, zooming'
    layers = proj['layers']
    assert [layer['name'] for layer in layers] == ['Amazon, zooming', 'Measure']
    assert {layer['group_id'] for layer in layers} == {proj['groups'][0]['id']}
    assert layers[1]['pen_id'] and layers[1]['pen_id'] != layers[0]['pen_id']
    assert [layer['source']['params']['show'] for layer in layers] == ['drawing', 'measure']
    shot(ui, 'measure-kept')
    assert not ui.errors


def test_river_zoom_line_source_swaps_recipe_and_controls(ui, server):
    """Study modes (2026-10-19): river_zoom's Line source picks river (the study as
    it was kept) or relay of hands (round 16 hdist); each shows its own controls."""
    open_bench(ui)
    ui.select_option('#gs-study', 'river_zoom')
    ready(ui)
    switch = ui.locator('#process-gesture-studies [data-mode-key="line_source"]')
    assert switch.locator('button').all_text_contents() == ['river', 'relay of hands']
    assert switch.locator('button[aria-pressed=true]').text_content() == 'river'
    assert control(ui, 'parts.0.voice.zoom').is_visible() and not control(ui, 'parts.0.voice.hands').count()
    assert 'line_source' not in recipe(ui)['values']
    river = ink(ui)

    switch.locator('button', has_text='relay of hands').click()
    ready(ui)
    assert recipe(ui)['values'] == {'line_source': 'relay'}
    keys = ui.eval_on_selector_all('#process-gesture-studies [data-control-key]',
                                   'els => els.map(e => e.dataset.controlKey)')
    assert set(keys) == {'parts.0.voice.hands', 'parts.0.voice.R_mm', 'parts.0.voice.peak_fine_mm', 'seed'}
    route = control(ui, 'parts.0.voice.hands').locator('select')
    assert [route.nth(i).input_value() for i in range(4)] == ['river_bend', 'shikasta', 'trail_borer', 'fly_fru']
    assert ui.locator('#gs-seed-input').input_value() == '3001'
    relay = ink(ui)
    assert relay and relay != river
    colours = ui.eval_on_selector_all('#process-canvas .gesture-studies-ink g.gs-ink',
                                      'els => [...new Set(els.map(e => e.style.getPropertyValue("--gs-ink")))]')
    assert len(colours) == 4                                  # an ink per hand
    shot(ui, 'river-zoom-relay')

    # a relay value, then back to river (its own values) and undo returns to the relay
    control(ui, 'seed').locator('.gs-next-seed').click()
    ready(ui)
    assert recipe(ui)['values'] == {'line_source': 'relay', 'seed': 3002}
    switch = ui.locator('#process-gesture-studies [data-mode-key="line_source"]')
    switch.locator('button', has_text='river').click()
    ready(ui)
    assert recipe(ui)['values'] == {} and ink(ui) == river and control(ui, 'parts.0.voice.zoom').is_visible()
    switch = ui.locator('#process-gesture-studies [data-mode-key="line_source"]')
    switch.locator('button', has_text='relay of hands').click()
    ready(ui)
    assert recipe(ui)['values'] == {'line_source': 'relay', 'seed': 3002}    # each mode remembers its values
    ui.click('#gesture-studies-undo')
    ready(ui)
    assert recipe(ui)['values'] == {}

    # Keep: one layer carrying the moded study, its values and the relay's hands pinned
    switch = ui.locator('#process-gesture-studies [data-mode-key="line_source"]')
    switch.locator('button', has_text='relay of hands').click()
    ready(ui)
    ui.click('#gesture-studies-keep')
    ui.wait_for_function("() => document.querySelector('#gesture-studies-kept').textContent.includes('Kept')")
    layers = _get(f'{server}/api/project')['layers']
    assert len(layers) == 1
    kept = layers[0]['source']['params']
    assert kept['values']['line_source'] == 'relay' and kept['study']['modes']['key'] == 'line_source'
    assert {p['id'] for p in kept['pins']} == {'river_bend', 'shikasta', 'trail_borer', 'fly_fru'}
    assert not ui.errors
