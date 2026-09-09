"""Late replies and nested modals must not duplicate or lose drawings."""
from test_acceptance_ui import (
    _get, add_layer, frontend_mode, reload_app, select_layer, server, ui,
)
from test_gallery_ui import empty_gallery, _open_gallery, _seed_asset
from test_bench_ui import _choose_bench


def test_insert_refresh_failure_retries_only_refresh(ui):
    _seed_asset(ui)
    reload_app(ui)
    _open_gallery(ui)
    inserted = []
    refresh_failures = []

    def insert(route):
        inserted.append(route.request.url)
        route.continue_()

    def project(route):
        if inserted and not refresh_failures:
            refresh_failures.append(True)
            route.fulfill(status=503, content_type='application/json', body='{"detail":"refresh unavailable"}')
        else:
            route.continue_()

    ui.route('**/api/gallery/*/insert', insert)
    ui.route('**/api/project', project)
    ui.get_by_role('button', name='Add as layer', exact=True).click()
    ui.get_by_role('button', name='Refresh Compose', exact=True).wait_for()
    assert len(inserted) == 1
    assert len(_get(f'{ui.base}/api/project')['layers']) == 2
    ui.get_by_role('button', name='Refresh Compose', exact=True).click()
    ui.locator('.gallery-browser').wait_for(state='detached')
    assert len(inserted) == 1
    ui.errors[:] = [e for e in ui.errors if '503' not in e]
    assert not ui.errors


def test_closed_prepare_cannot_reopen_a_save_dialog(ui):
    add_layer(ui, 'polygon', {'sides': 5, 'radius': 12})
    reload_app(ui)
    select_layer(ui)
    pending = []
    ui.route('**/api/gallery/prepare', lambda route: pending.append(route))
    ui.click('#btn-layer-gallery')
    ui.locator('.gallery-save').wait_for()
    ui.keyboard.press('Escape')
    ui.locator('.gallery-save').wait_for(state='detached')
    assert pending
    with ui.expect_response('**/api/gallery/prepare'):
        pending[0].fulfill(response=pending[0].fetch())
    ui.wait_for_function("() => !document.querySelector('#btn-layer-gallery').disabled")
    assert ui.locator('.gallery-save').count() == 0
    assert not ui.errors


def test_escape_from_save_returns_to_bench_without_closing_it(ui):
    _choose_bench(ui, 'homeostat')
    ui.wait_for_function("() => document.querySelector('#process-generic-save-gallery')?.disabled === false")
    ui.click('#process-generic-save-gallery')
    ui.wait_for_function("() => document.querySelector('.gallery-save button[type=submit]')?.disabled === false")
    ui.keyboard.press('Escape')
    ui.locator('.gallery-save').wait_for(state='detached')
    assert ui.locator('#process-popup').is_visible()
    assert not _get(f'{ui.base}/api/project')['layers']
    assert not ui.errors
