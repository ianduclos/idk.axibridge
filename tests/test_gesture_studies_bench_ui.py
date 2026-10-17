"""Gesture Studies bench user workflows, on the isolated real-server UI harness."""
import json
import os
from pathlib import Path

from test_acceptance_ui import _get, frontend_mode, select_layer, server, ui  # noqa: F401


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
    return page.locator(f'#gs-controls [data-control-key="{key}"]')


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
    ui.click('#gs-save-group summary')
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
    ui.click('#gs-recipe-group summary')
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
