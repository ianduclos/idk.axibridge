"""The acceptance error collector distinguishes superseded renders from faults."""
import json
from types import SimpleNamespace

import pytest

from test_acceptance_ui import (
    _capture_conflict, frontend_mode, server, ui,  # noqa: F401
)


def test_error_capture_preserves_conflicts_and_javascript_errors(ui):
    cases = {
        'cancelled': json.dumps({'detail': {'code': 'render_cancelled'}}),
        'conflict': json.dumps({'detail': {'code': 'real_conflict'}}),
        'malformed': 'not JSON',
        'wrong-shape': json.dumps({'detail': 'render_cancelled'}),
    }
    def fulfill(route):
        route.fulfill(status=409, content_type='application/json',
                      body=cases[route.request.url.rsplit('/', 1)[-1]])

    for name in cases:
        ui.route(f'**/error-capture/{name}', fulfill)
    messages = []
    ui.on('console', lambda message: messages.append(message))
    with ui.expect_event('pageerror'):
        ui.evaluate("""async names => {
        await Promise.all(names.map(name => fetch('/error-capture/' + name)
            .then(response => response.text())));
        console.error('Failed to load resource: the server responded with a status of 409 (Conflict)');
        setTimeout(() => { throw new Error('error-capture-javascript-probe'); }, 0);
    }""", list(cases))
    ui.expose_function('errorCaptureSettled', lambda: not any(
        'response classification pending' in error for error in ui.errors))
    ui.wait_for_function('async () => await window.errorCaptureSettled()')
    resources = [message for message in messages if message.text.startswith('Failed to load resource')
                 and not message.args]
    assert {message.location['url'].rsplit('/', 1)[-1] for message in resources} == set(cases)
    assert len(ui.errors) == 5, ui.errors
    assert not any('/error-capture/cancelled' in error for error in ui.errors)
    for name in ('conflict', 'malformed', 'wrong-shape'):
        assert any(f'/error-capture/{name}' in error for error in ui.errors), ui.errors
    assert any(error == 'Failed to load resource: the server responded with a status of 409 (Conflict)'
               for error in ui.errors), ui.errors
    assert any('error-capture-javascript-probe' in error for error in ui.errors), ui.errors


@pytest.mark.parametrize('payload', [
    None, [], {}, {'detail': None}, {'detail': []},
    {'detail': 'render_cancelled'}, {'detail': {}},
    {'detail': {'code': 'other'}}, {'detail': {'code': 'RENDER_CANCELLED'}},
])
def test_error_capture_reports_every_other_conflict_shape(payload):
    errors = []
    response = SimpleNamespace(status=409, url='https://example.test/conflict',
                               json=lambda: payload)
    _capture_conflict(response, errors)
    assert len(errors) == 1 and response.url in errors[0]


@pytest.mark.parametrize('exception', [ValueError('invalid JSON'), RuntimeError('read failed')])
def test_error_capture_reports_body_read_errors(exception):
    def read():
        raise exception

    errors = []
    response = SimpleNamespace(status=409, url='https://example.test/conflict', json=read)
    _capture_conflict(response, errors)
    assert len(errors) == 1
    assert type(exception).__name__ in errors[0]
    assert str(exception) in errors[0]


def test_error_capture_keeps_pending_response_visible_until_classified():
    errors = []

    def read():
        assert len(errors) == 1
        assert 'response classification pending' in errors[0]
        return {'detail': {'code': 'render_cancelled'}}

    response = SimpleNamespace(status=409, url='https://example.test/cancelled', json=read)
    _capture_conflict(response, errors)
    assert errors == []
