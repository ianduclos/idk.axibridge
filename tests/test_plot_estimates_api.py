"""Estimates and execution share optimized geometry and effective pen settings."""
import json

import pytest
from fastapi.testclient import TestClient

from axibridge import api
from axibridge.app import create_app
from axibridge.backends.axidraw_native import NativeParams
from axibridge.compose import PlotOptions
from axibridge.model import Layer, Path, PathDocument, PlannedJob
from axibridge.session import session


@pytest.mark.parametrize('route', ['normal', 'sheet', 'staged'])
def test_plan_and_plot_use_same_optimized_document_and_params(monkeypatch, route):
    doc = PathDocument(layers=[Layer(id=1, paths=[Path(points=[(10, 10), (10.5, 10.005), (11, 10)])])])
    session.project.plot_options = PlotOptions(sort=False, merge=False, simplify=False)
    monkeypatch.setattr(session, 'plot_document', lambda *args, **kw: session._optimize(doc))
    monkeypatch.setattr(api, '_sheet_document', lambda spec: doc)
    monkeypatch.setattr(api, '_staged_document', lambda spec: doc)
    effective = NativeParams(pen_pos_down=42)
    calls = []
    monkeypatch.setattr(session, 'effective_params', lambda *args, **kw: calls.append((args, kw)) or effective)
    estimates, plots = [], []
    monkeypatch.setattr(api, '_estimate_plot', lambda doc, params: estimates.append((doc, params)) or PlannedJob())
    monkeypatch.setattr(api.manager, 'start_plot', lambda doc, params: plots.append((doc, params)))
    spec = {'sheet': {'cols': 1, 'rows': 1, 'frames': 2}, 'staged': {'group_id': 'test'}}
    query = {} if route == 'normal' else {route: json.dumps(spec[route])}
    body = {} if route == 'normal' else {route: spec[route]}
    with TestClient(create_app()) as client:
        assert client.get('/api/plan', params=query).status_code == 200
        assert client.post('/api/plot/start', json=body).status_code == 200
    assert estimates == plots
    assert calls[0] == calls[1]
    assert estimates[0][0].layers[0].paths[0].points == [(10, 10), (11, 10)]


def test_native_plan_uses_driver_and_reports_failures(monkeypatch):
    from axibridge import native_estimate
    monkeypatch.setattr(api.manager, 'active_id', 'native')
    layer = session.add_generated_layer('polygon', {'sides': 3, 'radius': 5})
    seen = []
    def estimate(doc, params, **kwargs):
        seen.append((doc, params))
        return PlannedJob(total_duration=123)
    monkeypatch.setattr(native_estimate, 'estimate_native_job', estimate)
    with TestClient(create_app()) as client:
        response = client.get('/api/plan', params={'target': layer.id})
        assert response.status_code == 200
        assert response.json()['job']['total_duration'] == 123
        assert 'USB/host overhead' in response.json()['estimator_note']
        assert isinstance(seen[0][1], NativeParams)
        def fail(*args, **kw):
            raise RuntimeError('driver unavailable')
        monkeypatch.setattr(native_estimate, 'estimate_native_job', fail)
        response = client.get('/api/plan')
        assert response.status_code == 400
        assert 'driver unavailable' in response.json()['detail']
        resolved = client.get('/api/compose/resolved')
        assert resolved.status_code == 200
        assert resolved.json()['layers'][0]['paths']
        assert resolved.json()['layers'][0]['stats']['est_s'] is None
        assert 'driver unavailable' in resolved.json()['layers'][0]['stats']['estimate_error']
