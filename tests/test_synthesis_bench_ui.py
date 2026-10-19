"""Synthesis bench workflows against the isolated, built, real-server UI."""
import os
from pathlib import Path

from test_acceptance_ui import _get, frontend_mode, server, ui  # noqa: F401


TIMEOUT = 120_000


def shot(page, name):
    directory = os.environ.get('AXIBRIDGE_SYNTHESIS_SHOTS')
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(directory) / f'{name}.png'))


def preview_response(response):
    return (response.url.endswith('/api/generators/preview') and response.status == 200
            and response.request.post_data_json.get('module') == 'synthesis')


def drawn(page, action):
    """Observe the preview users just requested, rather than reading JS state."""
    with page.expect_response(preview_response, timeout=TIMEOUT) as pending:
        action()
    response = pending.value
    result = response.json()
    page.wait_for_function("() => document.querySelector('#sy-canvas polyline') !== null",
                           timeout=TIMEOUT)
    page.wait_for_function("() => document.querySelector('#sy-keep')?.disabled === false",
                           timeout=TIMEOUT)
    return response.request.post_data_json['params']['score'], result


def open_bench(page):
    page.wait_for_function("() => !!document.querySelector('#gen-select option[value=synthesis]')",
                           timeout=20_000)
    page.select_option('#gen-select', 'synthesis')
    page.click('#btn-bench')
    page.locator('#process-synthesis').wait_for()
    page.wait_for_function("() => document.querySelector('#sy-keep')?.disabled === false", timeout=TIMEOUT)


def start(page, gallery='writer:listen'):
    bench = page.locator('#process-synthesis')
    if not page.locator('#sy-gallery').is_visible():
        bench.get_by_role('button', name='Gallery', exact=True).click()
    return drawn(page, lambda: page.locator(f'#sy-gallery [data-gallery="{gallery}"] .sy-card-open').click())


def layer_ink(preview, layer_id):
    offset = 0
    for layer in preview['synthesis']['layers']:
        count = layer['paths']
        if layer['id'] == layer_id:
            return preview['lines'][offset:offset + count]
        offset += count
    return []


def stack(page, layer_id):
    return page.locator(f'#sy-stack [data-layer="{layer_id}"]')


def node(page, layer_id):
    return page.locator(f'#sy-arcs [data-layer="{layer_id}"]')


def selected(locator):
    return locator.get_attribute('aria-selected') == 'true' or 'selected' in (locator.get_attribute('class') or '')


def hand_layer(score):
    return next(layer for layer in score['layers'] if layer.get('part', {}).get('voice', {}).get('id') == 'hand')


def test_gallery_written_score_and_shared_layer_selection(ui):
    ui.set_viewport_size({'width': 1440, 'height': 900})
    open_bench(ui)
    score, preview = start(ui)
    assert score['decisions']['writers'][-1]['writer'] == 'listen'
    assert len(score['layers']) > 1 and score['relations']
    assert ui.locator('#sy-stack [data-layer]').count() == len(score['layers'])
    assert ui.locator('#sy-arcs [data-layer]').count() == len(score['layers']) + 1
    assert preview['styles'] and preview['synthesis']['relations']
    first, second = [layer['id'] for layer in score['layers'][:2]]
    stack(ui, first).get_by_role('button', name=f'{first} ·', exact=False).click()
    assert selected(stack(ui, first)) and selected(node(ui, first))
    node(ui, second).locator('circle').click()
    assert selected(stack(ui, second)) and selected(node(ui, second))
    assert not selected(stack(ui, first))
    shot(ui, 'listen-selected')
    assert not ui.errors


def test_hand_swap_history_and_ripple_none(ui):
    open_bench(ui)
    score, before = start(ui)
    layer = hand_layer(score)
    layer_id = layer['id']
    hand = ui.get_by_label(f'Hand {layer_id}', exact=True)
    original = hand.input_value()
    choices = hand.locator('option').evaluate_all('os => os.map(o => o.value)')
    other = next(value for value in choices if value != original)
    original_drawing = ui.locator('#sy-canvas polyline').evaluate_all(
        'els => els.map(el => el.getAttribute("points")).join("|")')
    history_index = ui.locator('#sy-history button').count() - 1
    changed, after = drawn(ui, lambda: hand.select_option(other))
    assert layer_ink(after, layer_id) != layer_ink(before, layer_id)
    assert changed != score
    ui.locator('#sy-history button').nth(history_index).click()
    # A history entry restores its own drawing and hand, and remains branchable.
    ui.wait_for_function('(a) => document.querySelector(`[aria-label="Hand ${a.id}"]`)?.value === a.hand',
                         arg={'id': layer_id, 'hand': original}, timeout=TIMEOUT)
    ui.wait_for_function('(ink) => Array.from(document.querySelectorAll("#sy-canvas polyline"))'
                         '.map(el => el.getAttribute("points")).join("|") === ink',
                         arg=original_drawing, timeout=TIMEOUT)
    ui.locator('#sy-ripple-buttons button[data-value=none]').click()
    ui.wait_for_function("() => document.querySelector('#sy-keep')?.disabled === false", timeout=TIMEOUT)
    held_score, held_preview = drawn(ui, lambda: ui.get_by_label(f'Hand {layer_id}', exact=True).select_option(other))
    others = {item['id'] for item in score['layers']} - {layer_id}
    assert set(held_score['decisions']['bench']['held']) == others
    assert all('held' in stack(ui, item).inner_text().lower() for item in others)
    for item in others:
        assert layer_ink(held_preview, item) == layer_ink(before, item)
    shot(ui, 'ripple-none')
    assert not ui.errors


def test_layer_lock_survives_recompose(ui):
    open_bench(ui)
    score, preview = start(ui)
    layer_id = next(item['id'] for item in preview['synthesis']['layers'] if item['paths'])
    locked, frozen = drawn(ui, lambda: ui.get_by_role('button', name=f'Lock {layer_id}', exact=True).click())
    assert next(item for item in locked['layers'] if item['id'] == layer_id)['lock']
    recomposed, after = drawn(ui, lambda: ui.locator('#process-synthesis').get_by_role(
        'button', name='Recompose', exact=True).click())
    assert next(item for item in recomposed['layers'] if item['id'] == layer_id)['lock']
    assert ui.get_by_role('button', name=f'Unlock {layer_id}', exact=True).is_visible()
    assert layer_ink(after, layer_id) == layer_ink(frozen, layer_id)
    assert layer_ink(after, layer_id) == layer_ink(preview, layer_id)
    shot(ui, 'locked-recomposed')
    assert not ui.errors


def test_arc_drag_adds_relation_chip(ui):
    open_bench(ui)
    score, _ = start(ui)
    src, dst = [layer['id'] for layer in score['layers'][:2]]
    first, last = node(ui, src).locator('circle').bounding_box(), node(ui, dst).locator('circle').bounding_box()
    ui.mouse.move(first['x'] + first['width'] / 2, first['y'] + first['height'] / 2)
    ui.mouse.down()
    ui.mouse.move(last['x'] + last['width'] / 2, last['y'] + last['height'] / 2, steps=12)
    ui.mouse.up()
    picker = ui.get_by_label('Relation kind', exact=True)
    picker.wait_for()
    kinds = picker.locator('option').evaluate_all('os => os.map(o => o.value).filter(Boolean)')
    picker.select_option(kinds[0])
    added, _ = drawn(ui, lambda: ui.get_by_role('button', name='Add relation', exact=True).click())
    assert len(added['relations']) == len(score['relations']) + 1
    relation = added['relations'][-1]
    assert relation['src'] == src and relation['dst'] == dst
    assert relation['kind'] in stack(ui, dst).inner_text()
    shot(ui, 'relation-added')
    assert not ui.errors


def test_sealed_study_keep_group_and_measure(ui, server):
    ui.set_viewport_size({'width': 1024, 'height': 768})
    open_bench(ui)
    catalogue = _get(f'{server}/api/synthesis', timeout=30)
    study = next(card for card in catalogue['gallery'] if card['kind'] == 'sealed')
    score, preview = start(ui, study['id'])
    assert len(score['layers']) == 1 and score['layers'][0]['role'] == 'sealed'
    assert 'sealed' in stack(ui, score['layers'][0]['id']).inner_text().lower()
    assert not score['relations']
    assert preview['lines']
    shot(ui, 'sealed-1024')
    score, _ = start(ui)
    bench = ui.locator('#process-synthesis')
    ui.locator('#sy-measure > summary').click()
    toggle = ui.get_by_label('Measure: Heading rose', exact=True)
    assert not toggle.is_checked()
    measured, result = drawn(ui, toggle.check)
    assert measured['devices'] and any(item['inks'] for item in result['synthesis']['devices'])
    assert not _get(f'{server}/api/project')['layers']
    with ui.expect_response(lambda response: response.url.endswith('/api/synthesis/keep')
                            and response.status == 200, timeout=TIMEOUT):
        bench.get_by_role('button', name='Keep', exact=True).click()
    project = _get(f'{server}/api/project')
    assert len(project['groups']) == 1
    members = [layer for layer in project['layers'] if layer['group_id'] == project['groups'][0]['id']]
    drawn_layers = [item for item in result['synthesis']['layers'] if item['role'] != 'measure']
    assert len(members) == len(drawn_layers) + 1
    assert sum(layer['name'] == 'Measure' for layer in members) == 1
    assert all(layer['source']['generator'] == 'synthesis' for layer in members)
    assert all(layer['pen_id'] for layer in members)
    shot(ui, 'measure-kept')
    assert not ui.errors


def test_saved_gallery_and_resume_replace_or_keep_as_new(ui, server):
    open_bench(ui)
    score, _ = start(ui)
    original_ink = ui.locator('#sy-canvas polyline').evaluate_all(
        'els => els.map(el => el.getAttribute("points")).join("|")')
    ui.fill('#sy-save-name', 'Listening bench checkpoint')
    with ui.expect_response(lambda response: response.url.endswith('/api/synthesis/saved')
                            and response.request.method == 'POST' and response.status == 200,
                            timeout=TIMEOUT) as pending:
        ui.click('#sy-save')
    saved = pending.value.json()
    ui.wait_for_function("() => document.querySelector('#sy-notice').textContent.includes('Saved')",
                         timeout=TIMEOUT)
    assert saved['thumb'].startswith('data:image/png;base64,')

    # Open a different sheet, then restore the saved score through its card.
    drawn(ui, lambda: ui.get_by_role('button', name='Recompose', exact=True).click())
    ui.get_by_role('button', name='Gallery', exact=True).click()
    card = ui.locator(f'#sy-gallery [data-gallery="saved:{saved["id"]}"]')
    assert 'Listening bench checkpoint' in card.inner_text()
    with ui.expect_response(lambda response: response.url.endswith('/api/synthesis/start')
                            and response.status == 200, timeout=TIMEOUT) as pending:
        card.locator('.sy-card-open').click()
    assert pending.value.json()['score'] == score
    ui.wait_for_function("() => document.querySelector('#sy-keep')?.disabled === false",
                         timeout=TIMEOUT)
    ui.wait_for_function('(ink) => Array.from(document.querySelectorAll("#sy-canvas polyline"))'
                         '.map(el => el.getAttribute("points")).join("|") === ink',
                         arg=original_ink, timeout=TIMEOUT)

    with ui.expect_response(lambda response: response.url.endswith('/api/synthesis/keep')
                            and response.status == 200, timeout=TIMEOUT) as pending:
        ui.click('#sy-keep')
    kept = pending.value.json()
    group_id = kept['group']['id']
    ui.wait_for_function("() => document.querySelector('#sy-notice').textContent.includes('Kept')",
                         timeout=TIMEOUT)
    ui.click('#process-close')
    ui.get_by_role('button', name=f'Enter {kept["group"]["name"]}', exact=True).click()
    member_id = kept['layers'][0]['id']
    row = ui.locator(f'#layer-list .layer-row[data-layer-id="{member_id}"]')
    row.locator('.lname').click()
    ui.wait_for_selector('#layer-detail-panel:not([hidden])', timeout=20_000)
    ui.click('#process-resume')
    ui.wait_for_function("() => document.querySelector('#sy-keep')?.disabled === false",
                         timeout=TIMEOUT)
    assert ui.locator('#sy-keep').inner_text() == 'Replace group'
    assert ui.locator('#sy-keep-new').is_visible()
    assert any(layer['id'] == member_id for layer in _get(f'{server}/api/project')['layers'])
    shot(ui, 'resumed-replace')

    with ui.expect_response(lambda response: response.url.endswith('/api/synthesis/keep')
                            and response.status == 200, timeout=TIMEOUT) as pending:
        ui.click('#sy-keep')
    replaced = pending.value.json()
    assert pending.value.request.post_data_json['replace'] == group_id
    assert replaced['group']['id'] == group_id
    ui.wait_for_function("() => document.querySelector('#sy-notice').textContent.includes('Replaced')",
                         timeout=TIMEOUT)
    project = _get(f'{server}/api/project')
    assert len(project['groups']) == 1
    assert {layer['id'] for layer in project['layers']} == {layer['id'] for layer in replaced['layers']}

    with ui.expect_response(lambda response: response.url.endswith('/api/synthesis/keep')
                            and response.status == 200, timeout=TIMEOUT) as pending:
        ui.click('#sy-keep-new')
    added = pending.value.json()
    assert 'replace' not in pending.value.request.post_data_json
    assert added['group']['id'] != group_id
    ui.wait_for_function("() => document.querySelector('#sy-notice').textContent.includes('Kept')",
                         timeout=TIMEOUT)
    project = _get(f'{server}/api/project')
    assert {group['id'] for group in project['groups']} == {group_id, added['group']['id']}
    assert len(project['layers']) == len(replaced['layers']) + len(added['layers'])
    assert not ui.errors
