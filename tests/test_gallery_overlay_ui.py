"""Canvas comparison is transient and uses actual insertion placement."""
import json

from test_gallery_ui import (frontend_mode, server, ui, empty_gallery,
                             _get, _seed_asset, _open_gallery, reload_app)


def test_gallery_overlay_comparison_cleanup_and_insertion(ui):
    _, asset_id = _seed_asset(ui)
    reload_app(ui)
    before = _get(f'{ui.base}/api/project')
    _open_gallery(ui)
    assert 'Shape-based' in ui.locator('.gallery-card-meta').inner_text()
    ui.get_by_role('button', name='Preview on canvas', exact=True).click()
    image = ui.locator('.gallery-canvas-overlay image')
    image.wait_for()
    expected = _get(f'{ui.base}/api/gallery/{asset_id}/preview')
    for attr in ('x', 'y', 'width', 'height'):
        assert float(image.get_attribute(attr)) == expected[attr]
    assert ui.locator('.gallery-grid').is_hidden()
    assert _get(f'{ui.base}/api/project') == before
    ui.get_by_label('Overlay opacity').fill('35')
    assert image.get_attribute('opacity') == '0.35'
    ui.get_by_role('button', name='Hide overlay', exact=True).click()
    assert image.get_attribute('opacity') == '0'
    ui.get_by_role('button', name='Show overlay', exact=True).click()
    assert image.get_attribute('opacity') == '0.35'
    ui.screenshot(path='/tmp/gallery-canvas-overlay.png', full_page=True)
    ui.get_by_role('button', name='Back to gallery', exact=True).click()
    assert image.count() == 0
    assert ui.locator('.gallery-grid').is_visible()
    ui.get_by_role('button', name='Preview on canvas', exact=True).click()
    image.wait_for()
    ui.get_by_role('button', name='Add as layer', exact=True).click()
    ui.locator('.gallery-browser').wait_for(state='detached')
    assert image.count() == 0
    after = _get(f'{ui.base}/api/project')
    assert len(after['layers']) == len(before['layers']) + 1
    assert after['layers'][-1]['transform'] == expected['transform']
    assert not ui.errors


def test_gallery_geometry_filter_and_escape_overlay(ui):
    _seed_asset(ui)
    reload_app(ui)
    _open_gallery(ui)
    ui.get_by_label('Filter by geometry type').select_option('line')
    ui.wait_for_function("() => document.querySelectorAll('.gallery-card').length === 0")
    ui.get_by_label('Filter by geometry type').select_option('shape')
    ui.locator('.gallery-card').wait_for()
    ui.get_by_role('button', name='Preview on canvas', exact=True).click()
    ui.locator('.gallery-canvas-overlay image').wait_for()
    ui.keyboard.press('Escape')
    assert ui.locator('.gallery-canvas-overlay image').count() == 0
    assert ui.locator('.gallery-browser').count() == 0
    assert not ui.locator('main').evaluate('(el) => el.inert')
    assert not ui.errors


def test_gallery_late_overlay_and_failed_preview(ui):
    _, asset_id = _seed_asset(ui)
    reload_app(ui)
    _open_gallery(ui)
    ui.route('**/api/gallery/*/preview', lambda route: route.fulfill(
        status=503, content_type='application/json', body='{"detail":"Preview unavailable for now"}'))
    ui.get_by_role('button', name='Preview on canvas', exact=True).click()
    ui.get_by_role('alert').filter(has_text='Preview unavailable for now').wait_for()
    assert ui.locator('.gallery-grid').is_visible()
    assert ui.locator('.gallery-canvas-overlay image').count() == 0
    ui.unroute('**/api/gallery/*/preview')
    payload = _get(f'{ui.base}/api/gallery/{asset_id}/preview')
    pending = []
    ui.route('**/api/gallery/*/preview', lambda route: pending.append(route))
    ui.get_by_role('button', name='Preview on canvas', exact=True).click()
    ui.wait_for_timeout(100)
    assert pending
    ui.keyboard.press('Escape')
    pending[0].fulfill(status=200, content_type='application/json', body=json.dumps(payload))
    ui.wait_for_timeout(100)
    assert ui.locator('.gallery-browser').count() == 0
    assert ui.locator('.gallery-canvas-overlay image').count() == 0
    ui.errors[:] = [e for e in ui.errors if '503' not in e]
    assert not ui.errors
