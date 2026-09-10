"""Usage measures committed tool actions, independently of project history."""
import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.module_library import ModuleLibraryStore
from axibridge.registry import describe_modules, effects, _EFFECT_LIBRARY_CATEGORIES


@pytest.fixture
def usage(tmp_path, monkeypatch):
    store = ModuleLibraryStore(tmp_path / 'library')
    monkeypatch.setattr('axibridge.module_library.module_library_store', store)
    monkeypatch.setattr('axibridge.module_library_api.module_library_store', store)
    with TestClient(create_app()) as client:
        yield client, store


def counts(store):
    return {(p['kind'], p['module']): p['use_count'] for p in store.list()['preferences']}


def test_usage_records_material_actions_not_browsing_or_history(usage):
    client, store = usage
    assert client.get('/api/module-library').status_code == 200
    assert client.post('/api/module-library/resolve', json={
        'kind': 'source', 'module': 'polygon', 'current_params': {}}).status_code == 200
    assert client.post('/api/generators/preview', json={
        'module': 'polygon', 'params': {}}).status_code == 200
    assert counts(store) == {}
    assert client.post('/api/layers/generate', json={
        'module': 'missing-tool', 'params': {}}).status_code == 404
    assert counts(store) == {}
    layer = client.post('/api/layers/generate', json={'module': 'polygon', 'params': {}}).json()
    assert counts(store) == {('source', 'polygon'): 1}
    for radius in [20, 25, 30]:
        response = client.post(f"/api/layers/{layer['id']}/regenerate", json={
            'params': {'radius': radius}, 'coalesce': True})
        assert response.status_code == 200
    assert counts(store) == {('source', 'polygon'): 2}  # one live-edit undo run
    for action in ['undo', 'redo']:
        assert client.post(f'/api/{action}').status_code == 200
    assert counts(store) == {('source', 'polygon'): 2}
    assert client.post(f"/api/layers/{layer['id']}/regenerate", json={
        'params': {'radius': 35}, 'coalesce': False}).status_code == 200
    assert counts(store) == {('source', 'polygon'): 3}


def test_effect_usage_ignores_reorder_removal_toggle_and_noop(usage):
    client, store = usage
    layer = client.post('/api/layers/generate', json={'module': 'polygon', 'params': {}}).json()
    url = f"/api/layers/{layer['id']}"
    steps = [{'effect': 'multipass', 'params': {'count': 2}},
             {'effect': 'perspective', 'params': {}}]
    assert client.patch(url, json={'effects': steps}).status_code == 200
    before = counts(store)
    assert before[('effect', 'multipass')] == before[('effect', 'perspective')] == 1
    assert client.patch(url, json={'effects': steps}).status_code == 200
    steps.reverse()
    assert client.patch(url, json={'effects': steps}).status_code == 200
    steps[0]['enabled'] = False
    assert client.patch(url, json={'effects': steps}).status_code == 200
    assert counts(store) == before
    steps[1]['params'] = {'count': 3}
    assert client.patch(url, json={'effects': steps}).status_code == 200
    assert counts(store)[('effect', 'multipass')] == 2
    after = counts(store)
    assert client.patch(url, json={'effects': []}).status_code == 200
    assert client.patch(url, json={'visible': False}).status_code == 200
    assert client.patch('/api/layers/missing', json={'effects': steps}).status_code == 404
    assert counts(store) == after


def test_categories_are_explicit_and_bench_membership_overlaps():
    catalogue = describe_modules()
    sources = {m['id']: m['library_categories'] for m in catalogue['sources']}
    fx = {m['id']: m['library_categories'] for m in catalogue['effects']}
    assert sources['polygon'] == ['procedural']
    assert sources['linedraw'] == ['image']
    assert sources['magnetic_field'] == ['procedural', 'bench']
    assert set(effects()) == set(_EFFECT_LIBRARY_CATEGORIES)
    assert fx['ribbon'] == ['line']  # output can be filled, input is strokes
    assert fx['hatch_fill'] == ['shape']
    assert fx['perspective'] == ['agnostic']


def test_failed_usage_write_cannot_fail_committed_geometry(usage, monkeypatch):
    client, store = usage
    def fail(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr(store, '_write', fail)
    response = client.post('/api/layers/generate', json={'module': 'polygon', 'params': {}})
    assert response.status_code == 200
    assert client.get('/api/project').json()['layers'][0]['id'] == response.json()['id']
    assert client.post('/api/undo').status_code == 200
    assert client.get('/api/project').json()['layers'] == []


def test_rating_validation_clear_and_restart_preserve_usage(usage):
    client, store = usage
    url = '/api/module-library/preferences/source/polygon'
    assert client.put(url, json={'rating': 4}).status_code == 200
    for value in [0, 6, 2.5]:
        assert client.put(url, json={'rating': value}).status_code in {400, 422}
    client.post('/api/layers/generate', json={'module': 'polygon', 'params': {}})
    updated = client.put(url, json={'rating': None, 'tags': ['Keep']})
    assert updated.status_code == 200
    pref = ModuleLibraryStore(store.root).list()['preferences'][0]
    assert pref['rating'] is None and pref['use_count'] == 1
    assert pref['last_used_at'] and pref['tags'] == ['Keep']
