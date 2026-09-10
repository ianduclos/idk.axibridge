"""The module browser is a non-mutating selector with personal recall aids."""
import json

from test_acceptance_ui import (_get, _post, add_layer, frontend_mode,
                                reload_app, select_layer, server, ui)
from test_compose_presets_ui import clean_module_library


def test_stars_tags_and_preset_search_keep_current_tool_visible(ui):
    _post(f'{ui.base}/api/module-library/presets', {
        'kind': 'source', 'module': 'lissajous', 'name': 'Rising knots',
        'params': {'freq_x': 4}})
    ui.select_option('#gen-select', 'polygon')
    before = _get(f'{ui.base}/api/project')
    ui.click('#gen-browse')
    ui.get_by_label('Search tools').fill('Rising knots')
    ui.wait_for_function("() => document.querySelectorAll('.module-library-card').length === 1")
    assert ui.locator('.module-library-card').get_attribute('data-module') == 'lissajous'
    detail = ui.locator('.module-library-detail')
    detail.locator('.module-library-star').click()
    ui.wait_for_function("() => document.querySelector('.module-library-star')?.getAttribute('aria-pressed') === 'true'")
    detail.locator('.module-library-tags').fill('knotted, studies')
    save = detail.get_by_role('button', name='Save tags', exact=True)
    assert not save.is_disabled()
    save.click()
    ui.wait_for_function("() => !document.querySelector('.module-library-save-tags')?.disabled")
    ui.get_by_label('Search tools').fill('knotted')
    ui.wait_for_function("() => document.querySelectorAll('.module-library-card').length === 1")
    assert ui.locator('.module-library-card').get_attribute('data-module') == 'lissajous'
    ui.wait_for_function("() => { const image = document.querySelector('.module-library-detail-identifier'); return image?.complete && image.naturalWidth > 0; }")
    ui.screenshot(path='/tmp/module-library-generators.png', full_page=True)
    ui.set_viewport_size({'width': 1024, 'height': 768})
    assert ui.locator('.module-library-dialog').evaluate('(node) => node.scrollWidth <= node.clientWidth')
    ui.screenshot(path='/tmp/module-library-generators-1024.png')
    ui.set_viewport_size({'width': 1440, 'height': 900})
    ui.keyboard.press('Escape')
    ui.wait_for_function("() => document.querySelector('#gen-select').options.length === 2")
    assert set(ui.locator('#gen-select option').evaluate_all('(els) => els.map(el => el.value)')) == {'polygon', 'lissajous'}
    assert ui.locator('#gen-select').input_value() == 'polygon'
    assert _get(f'{ui.base}/api/project') == before
    ui.click('#gen-browse')
    assert ui.get_by_label('Search tools').input_value() == 'knotted'
    ui.locator('.module-library-star').click()
    ui.keyboard.press('Escape')
    ui.wait_for_function("() => document.querySelector('#gen-select').options.length > 2")
    assert not ui.errors


def test_categories_sort_rating_and_tag_chips_are_independent(ui):
    data = _get(f'{ui.base}/api/module-library')
    data['preferences'] = [
        {'kind': 'source', 'module': 'polygon', 'starred': False,
         'tags': ['geometric'], 'rating': 2, 'use_count': 8,
         'last_used_at': '2026-09-09T10:00:00Z'},
        {'kind': 'source', 'module': 'lissajous', 'starred': False,
         'tags': ['curves'], 'rating': 5, 'use_count': 2,
         'last_used_at': '2026-09-10T10:00:00Z'},
    ]
    ui.route('**/api/module-library', lambda route: route.fulfill(
        status=200, content_type='application/json', body=json.dumps(data)))
    updates = []

    def save_preference(route):
        body = route.request.post_data_json
        updates.append(body)
        old = next(item for item in data['preferences']
                   if item['module'] == route.request.url.rsplit('/', 1)[-1])
        old.update(body)
        route.fulfill(status=200, content_type='application/json', body=json.dumps(old))

    ui.route('**/api/module-library/preferences/source/*', save_preference)
    ui.click('#gen-browse')
    procedural = ui.get_by_role('button', name='Procedural', exact=True)
    bench = ui.get_by_role('button', name='Bench', exact=True)
    assert procedural.is_visible() and bench.is_visible()
    bench.click()
    assert ui.locator('.module-library-card[data-module="magnetic_field"]').is_visible()
    procedural.click()
    assert ui.locator('.module-library-card[data-module="magnetic_field"]').is_visible()
    ui.get_by_label('Sort modules').select_option('rating')
    assert ui.locator('.module-library-card').first.get_attribute('data-module') == 'lissajous'
    ui.get_by_label('Sort modules').select_option('most-used')
    assert ui.locator('.module-library-card').first.get_attribute('data-module') == 'polygon'
    ui.get_by_label('Sort modules').select_option('least-used')
    assert ui.locator('.module-library-card').first.get_attribute('data-module') != 'polygon'
    ui.get_by_label('Sort modules').select_option('recently-used')
    assert ui.locator('.module-library-card').first.get_attribute('data-module') == 'lissajous'
    ui.get_by_label('Sort modules').select_option('rating')
    ui.locator('.module-library-card').first.click()

    detail = ui.locator('.module-library-detail')
    detail.get_by_role('button', name='Rate 3 stars').click()
    ui.wait_for_function("() => document.querySelector('.module-library-rating')?.dataset.rating === '3'")
    assert updates[-1] == {'rating': 3}
    detail.get_by_role('button', name='Clear rating').click()
    ui.wait_for_function("() => document.querySelector('.module-library-rating')?.dataset.rating === ''")
    assert updates[-1] == {'rating': None}

    tag_input = detail.get_by_role('textbox', name='Add tag', exact=True)
    tag_input.fill('fresh')
    tag_input.press('Enter')
    detail.get_by_role('button', name='Remove tag curves').click()
    detail.get_by_role('button', name='Save tags', exact=True).click()
    ui.wait_for_function("() => !document.querySelector('.module-library-save-tags')?.disabled")
    assert updates[-1] == {'tags': ['fresh']}
    ui.keyboard.press('Escape')
    add_layer(ui, 'polygon', {'sides': 5})
    reload_app(ui)
    select_layer(ui)
    ui.click('#fx-browse')
    effect_categories = ui.locator('.module-library-categories')
    effect_categories.get_by_role('button', name='Line', exact=True).click()
    assert ui.locator('.module-library-card[data-module="hatch_fill"]').count() == 0
    effect_categories.get_by_role('button', name='Shape', exact=True).click()
    assert ui.locator('.module-library-card[data-module="hatch_fill"]').is_visible()


def test_failed_tag_save_preserves_unsaved_chips(ui):
    ui.click('#gen-browse')
    ui.locator('.module-library-card[data-module="lissajous"]').click()
    ui.route('**/api/module-library/preferences/source/lissajous', lambda route: route.fulfill(
        status=503, content_type='application/json', body='{"detail":"Store unavailable"}'))
    detail = ui.locator('.module-library-detail')
    field = detail.get_by_label('Add tag')
    field.fill('still-here')
    field.press('Enter')
    detail.get_by_role('button', name='Save tags', exact=True).click()
    detail.locator('[role="alert"]').wait_for(state='visible')
    assert detail.get_by_text('still-here', exact=True).is_visible()


def test_changed_preset_choice_and_closed_browser_discard_late_use(ui):
    for sides, name in [(4, 'Four'), (8, 'Eight')]:
        _post(f'{ui.base}/api/module-library/presets', {
            'kind': 'source', 'module': 'polygon', 'name': name, 'params': {'sides': sides}})
    before = _get(f'{ui.base}/api/project')
    ui.click('#gen-browse')
    ui.locator('.module-library-card[data-module="polygon"]').click()
    detail = ui.locator('.module-library-detail')
    select = detail.get_by_label('Preset', exact=True)
    select.select_option(label='Four')
    pending = []
    ui.route('**/api/module-library/resolve', lambda route: pending.append(route))
    detail.get_by_role('button', name='Use', exact=True).click()
    ui.wait_for_timeout(100)
    assert pending
    select.select_option(label='Eight')
    pending.pop(0).fulfill(status=200, content_type='application/json', body=json.dumps({'params': {'sides': 4, 'radius': 30}}))
    ui.wait_for_timeout(100)
    assert ui.locator('.module-library-browser').is_visible()
    assert select.locator('option:checked').inner_text() == 'Eight'
    detail.get_by_role('button', name='Use', exact=True).click()
    ui.wait_for_timeout(100)
    assert pending
    ui.keyboard.press('Escape')
    pending.pop(0).fulfill(status=200, content_type='application/json', body=json.dumps({'params': {'sides': 8, 'radius': 30}}))
    ui.wait_for_timeout(100)
    assert ui.locator('.module-library-browser').count() == 0
    assert _get(f'{ui.base}/api/project') == before
    assert not ui.locator('main').evaluate('(el) => el.inert')
    assert not ui.errors


def test_missing_module_preset_is_visible_and_removable(ui):
    orphan_id = 'f' * 32
    data = _get(f'{ui.base}/api/module-library')
    data['presets'].append({'id': orphan_id, 'kind': 'source',
        'module': 'removed_source', 'name': 'Old favourite', 'params': {}})
    def missing_library(route):
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data))
    ui.route('**/api/module-library', missing_library)
    deleted = []
    def remove(route):
        deleted.append(route.request.method)
        route.fulfill(status=200, content_type='application/json', body='{"ok":true}')
    ui.route(f'**/api/module-library/presets/{orphan_id}', remove)
    ui.click('#gen-browse')
    ui.get_by_label('Search tools').fill('Old favourite')
    card = ui.locator('.module-library-card[data-module="removed_source"]')
    card.wait_for()
    assert 'Unavailable' in card.inner_text()
    card.click()
    detail = ui.locator('.module-library-detail')
    assert detail.get_by_role('button', name='Use', exact=True).is_disabled()
    detail.get_by_label('Preset', exact=True).select_option(orphan_id)
    detail.get_by_role('button', name='Delete', exact=True).click()
    ui.locator('.module-library-name-dialog').get_by_role('button', name='Delete', exact=True).click()
    card.wait_for(state='detached')
    assert deleted == ['DELETE']
    assert not ui.errors
