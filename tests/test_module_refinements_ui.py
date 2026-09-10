"""Refinement handoff checks for categories and asynchronous metadata edits."""
from test_acceptance_ui import (add_layer, frontend_mode, reload_app,
                                select_layer, server, ui)
from test_compose_presets_ui import clean_module_library


def test_effect_category_chips_describe_input_geometry(ui):
    add_layer(ui, 'polygon', {})
    reload_app(ui)
    select_layer(ui)
    ui.click('#fx-browse')
    ui.get_by_role('button', name='Line', exact=True).click()
    assert ui.locator('.module-library-card[data-module="ribbon"]').is_visible()
    assert ui.locator('.module-library-card[data-module="hatch_fill"]').count() == 0
    ui.locator('.module-library-categories').get_by_role('button', name='Shape', exact=True).click()
    assert ui.locator('.module-library-card[data-module="hatch_fill"]').is_visible()
    assert ui.locator('.module-library-card[data-module="ribbon"]').count() == 0
    ui.get_by_role('button', name='Agnostic', exact=True).click()
    assert ui.locator('.module-library-card[data-module="perspective"]').is_visible()
    assert ui.locator('.module-library-card[data-module="hatch_fill"]').count() == 0
    assert not ui.errors


def test_pending_metadata_stays_locked_after_reselect_and_preserves_tags(ui):
    ui.click('#gen-browse')
    ui.locator('.module-library-card[data-module="polygon"]').click()
    detail = ui.locator('.module-library-detail')
    detail.get_by_label('Add tag', exact=True).fill('unfinished')
    pending = []
    endpoint = '**/api/module-library/preferences/source/polygon'
    ui.route(endpoint, lambda route: pending.append(route))
    with ui.expect_request(endpoint):
        detail.locator('.module-library-star').click()
    assert detail.get_by_label('Add tag', exact=True).is_disabled()
    assert detail.get_by_role('button', name='Rate 5 stars').is_disabled()
    ui.locator('.module-library-card[data-module="lissajous"]').click()
    ui.locator('.module-library-card[data-module="polygon"]').click()
    assert detail.get_by_role('button', name='Save tags', exact=True).is_disabled()
    assert detail.get_by_role('button', name='Rate 5 stars').is_disabled()
    assert len(pending) == 1
    pending.pop().fulfill(status=503, content_type='application/json',
                          body='{"detail":"Store unavailable"}')
    detail.locator('[role="alert"]').wait_for(state='visible')
    assert detail.get_by_label('Add tag', exact=True).input_value() == 'unfinished'
    assert detail.get_by_label('Add tag', exact=True).is_enabled()
    assert all('503' in error for error in ui.errors)  # intentional failed request
