"""Module browser handoff prepares drafts; explicit preset application is undoable."""
import json
import urllib.request

import pytest

from test_acceptance_ui import (_get, _post, add_layer, frontend_mode,
                                reload_app, select_layer, server, ui)


def _request(base, path, method, body=None):
    req = urllib.request.Request(base + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


@pytest.fixture(autouse=True)
def clean_module_library(server):
    def clear():
        data = _get(f'{server}/api/module-library')
        for preset in data['presets']:
            _request(server, f"/api/module-library/presets/{preset['id']}", 'DELETE')
        for pref in data['preferences']:
            _request(server, f"/api/module-library/preferences/{pref['kind']}/{pref['module']}",
                     'PUT', {'starred': False, 'tags': []})
    clear()
    yield
    clear()


def _preset(ui, kind, module, params, name='Remembered settings'):
    return _post(f'{ui.base}/api/module-library/presets', {
        'kind': kind, 'module': module, 'name': name, 'params': params})


def _without_revision(project):
    # Recovery revisions count edits, including undo. The project content
    # should return to its prior value; the revision should move forward.
    return {key: value for key, value in project.items() if key != 'revision'}


def test_generator_browser_unlatches_and_prepares_without_mutation(ui):
    preset = _preset(ui, 'source', 'polygon', {'sides': 7, 'radius': 19})
    ui.select_option('#gen-select', 'polygon')
    ui.click('#btn-generate')
    ui.wait_for_function("() => document.querySelector('#gen-latch')?.hidden === false")
    before = _get(f'{ui.base}/api/project')
    ui.click('#gen-browse')
    ui.locator('.module-library-card[data-module="polygon"]').click()
    ui.locator(".module-library-detail select").select_option(preset["id"])
    ui.locator(".module-library-detail").get_by_role("button", name="Use", exact=True).click()
    ui.locator('.module-library-browser').wait_for(state='detached')
    assert _get(f'{ui.base}/api/project') == before
    assert ui.locator('#gen-latch').is_hidden()
    assert ui.locator('#btn-generate').inner_text() == '＋ Create layer'
    ui.click('#btn-generate')
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 2")
    after = _get(f'{ui.base}/api/project')
    assert after['layers'][0] == before['layers'][0]
    assert after['layers'][-1]['source']['params']['sides'] == 7
    assert after['layers'][-1]['source']['params']['radius'] == 19
    assert not ui.errors


def test_existing_generator_preset_requires_apply_and_one_undo(ui):
    layer_id = add_layer(ui, 'polygon', {'sides': 4, 'radius': 18})
    preset = _preset(ui, 'source', 'polygon', {'sides': 9, 'radius': 27})
    reload_app(ui); select_layer(ui)
    controls = ui.locator('#layer-detail .module-preset-controls[data-kind="source"]')
    controls.locator('select').select_option(preset['id'])
    before = _get(f'{ui.base}/api/project')
    assert before['layers'][0]['source']['params']['sides'] == 4
    with ui.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith(f'/layers/{layer_id}/regenerate')):
        controls.get_by_role('button', name='Apply preset', exact=True).click()
    assert _get(f'{ui.base}/api/project')['layers'][0]['source']['params']['sides'] == 9
    _post(f'{ui.base}/api/undo')
    restored = _get(f'{ui.base}/api/project')
    assert _without_revision(restored) == _without_revision(before)
    assert restored['revision'] > before['revision']
    assert not ui.errors


def test_effect_browser_prepares_add_and_existing_apply_is_independent(ui):
    layer_id = add_layer(ui, 'polygon', {'sides': 4, 'radius': 18})
    preset = _preset(ui, 'effect', 'freehand', {'tremor': 1.3, 'seed': 73})
    reload_app(ui); select_layer(ui)
    before = _get(f'{ui.base}/api/project')
    ui.click('#fx-browse')
    ui.locator('.module-library-card[data-module="freehand"]').click()
    ui.locator(".module-library-detail select").select_option(preset["id"])
    ui.locator(".module-library-detail").get_by_role("button", name="Use", exact=True).click()
    ui.locator('.module-library-browser').wait_for(state='detached')
    assert _get(f'{ui.base}/api/project') == before
    assert ui.locator('#fx-select').input_value() == 'freehand'
    with ui.expect_response(lambda r: r.request.method == 'PATCH' and r.url.endswith(f'/layers/{layer_id}')):
        ui.click('#fx-add')
    controls = ui.locator('.step .module-preset-controls[data-kind="effect"]')
    controls.wait_for()
    first = _get(f'{ui.base}/api/project')
    assert first['layers'][0]['effects'][0]['params']['seed'] == 73
    assert first['layers'][0]['effects'][0]['params']['tremor'] == 1.3
    second = _preset(ui, 'effect', 'freehand', {'tremor': 2.1, 'seed': 84}, 'Second settings')
    reload_app(ui); select_layer(ui)
    ui.locator('.step .name').click()
    controls = ui.locator('.step .module-preset-controls[data-kind="effect"]')
    controls.locator('select').select_option(second['id'])
    with ui.expect_response(lambda r: r.request.method == 'PATCH' and r.url.endswith(f'/layers/{layer_id}')):
        controls.get_by_role('button', name='Apply preset', exact=True).click()
    applied = _get(f'{ui.base}/api/project')
    assert applied['layers'][0]['effects'][0]['params']['seed'] == 84
    _request(ui.base, f"/api/module-library/presets/{second['id']}", 'DELETE')
    assert _get(f'{ui.base}/api/project') == applied
    _post(f'{ui.base}/api/undo')
    restored = _get(f'{ui.base}/api/project')
    assert _without_revision(restored) == _without_revision(first)
    assert restored['revision'] > first['revision']
    assert not ui.errors
