"""Found faces are frozen ordinary pen layers in resolved paper space."""
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon
from axibridge.app import create_app
from axibridge.compose import Affine
from axibridge.fill_geometry import find_face
from axibridge.session import session

@pytest.fixture
def client(fresh_session):
    from axibridge.events import bus
    with TestClient(create_app()) as client:
        loop = bus._loop
        yield client
    # Do not leave this fixture's closed loop for lifespan-free clients.
    if bus._loop is loop and loop is not None and loop.is_closed():
        bus._loop = None

def square(x=20, y=20, size=60):
    return {'anchors': [{'x': a, 'y': b} for a,b in [(x,y),(x+size,y),(x+size,y+size),(x,y+size)]], 'closed': True}

def source(holes=False):
    return session.add_generated_layer('pen', {'subpaths': [square()] + ([square(40,40,20)] if holes else [])})

def snapshot():
    return session.project.model_dump(), session.edit_rev, len(session._history)

def test_preview_commit_holes_freeze_and_undo(client):
    original = source(True)
    before = snapshot()
    body = {'point': [30,30], 'detail': 1, 'master_t': .7}
    preview = client.post('/api/geometry/face', json=body)
    assert preview.status_code == 200, preview.text
    candidate = preview.json()
    assert snapshot() == before
    assert len(candidate['rings']) == len(candidate['subpaths']) == 2
    response = client.post('/api/layers/fill', json={**body, 'revision': candidate['revision']})
    assert response.status_code == 200, response.text
    layer = response.json()
    assert layer['source']['generator'] == 'pen'
    assert layer['transform'] == Affine().model_dump()
    assert layer['effects'] == []
    assert len(session._history) == before[2] + 1
    frozen = session.source_geometry[layer['id']]
    assert len(frozen) == 2 and all(p.filled and p.points[0] == p.points[-1] for p in frozen)
    session.regenerate_layer(original.id, {'subpaths': [square(100,100,20)]})
    assert session.source_geometry[layer['id']] == frozen
    session.undo()
    session.undo()
    assert [l.id for l in session.project.layers] == [original.id]

def test_preview_uses_resolved_transforms_and_visibility(client):
    layer = source()
    session.update_layer(layer.id, {'transform': Affine(e=100, f=10).model_dump()})
    body = {'point': [130,40], 'master_t': .6}
    response = client.post('/api/geometry/face', json=body)
    assert response.status_code == 200, response.text
    expected = find_face([p for paths in session.resolved(master_t=.6).values() for p in paths], body['point'], 0)
    rings = response.json()['rings']
    assert Polygon(rings[0], rings[1:]).equals(expected)
    session.update_layer(layer.id, {'visible': False})
    assert client.post('/api/geometry/face', json=body).status_code == 422

def test_stale_and_no_face_are_atomic(client):
    source()
    preview = client.post('/api/geometry/face', json={'point': [30,30]}).json()
    before = snapshot()
    assert client.post('/api/layers/fill', json={'point': [30,30], 'revision': preview['revision']-1}).status_code == 409
    assert client.post('/api/layers/fill', json={'point': [0,0], 'revision': before[1]}).status_code == 422
    assert snapshot() == before

@pytest.mark.parametrize('extra', [{'gap_mm': 6}, {'detail': -1}, {'master_t': 2}, {'point': [10001,0]}, {'gap_mm': 'NaN'}])
def test_invalid_is_atomic(client, extra):
    source()
    before = snapshot()
    assert client.post('/api/layers/fill', json={'point': [30,30], 'revision': before[1], **extra}).status_code == 422
    assert snapshot() == before

def test_refit_is_pure_and_rejects_invalid_rings(client):
    source(True)
    candidate = client.post('/api/geometry/face', json={'point': [30,30]}).json()
    before = snapshot()
    response = client.post('/api/geometry/face/fit', json={'rings': candidate['rings'], 'detail': 0})
    assert response.status_code == 200, response.text
    assert len(response.json()['subpaths']) == 2
    for rings in [[], [[[0,0],[10,10],[0,10],[10,0],[0,0]]], [[[10001,0],[0,1],[0,0]]]]:
        assert client.post('/api/geometry/face/fit', json={'rings': rings}).status_code == 422
    assert snapshot() == before

def test_off_paper_face_refuses_pen_clamping(client):
    layer = source()
    session.update_layer(layer.id, {'transform': Affine(e=1000).model_dump()})
    before = snapshot()
    assert client.post('/api/geometry/face', json={'point': [1030,30]}).status_code == 422
    assert client.post('/api/layers/fill', json={'point': [1030,30], 'revision': before[1]}).status_code == 422
    assert snapshot() == before

@pytest.mark.parametrize('scenario', ['group_effect', 'occlusion', 'timeline'])
def test_candidate_matches_displayed_resolver(client, scenario):
    from axibridge.compose import EffectStep
    layer = source()
    point = [35,35]
    if scenario == 'group_effect':
        group = session.create_group([{'kind': 'layer', 'id': layer.id}])
        session.transform_selection([{'kind': 'group', 'id': group.id}], Affine(e=100, f=20))
        session.update_layer(layer.id, {'effects': [EffectStep(effect='perspective', params={'tilt_x': 25}).model_dump()]})
        point = [140,60]
    elif scenario == 'occlusion':
        mask = session.add_generated_layer('pen', {'subpaths': [square(40,40,20)]})
        session.update_layer(mask.id, {'occluder': True, 'draw': False})
        point = [30,30]
    else:
        other = session.add_generated_layer('pen', {'subpaths': [square(120,20,60)]})
        tw = session.create_tween_layer(layer.id, other.id)
        session.update_layer(layer.id, {'visible': False})
        session.update_layer(other.id, {'visible': False})
        session.set_tween_params(tw.id, {'follow_master': True})
        point = [100,40]
    paths = [p for ps in session.resolved(master_t=.65).values() for p in ps]
    expected = find_face(paths, point, 0)
    assert expected is not None
    response = client.post('/api/geometry/face', json={'point': point, 'master_t': .65})
    assert response.status_code == 200, response.text
    candidate = response.json()
    assert Polygon(candidate['rings'][0], candidate['rings'][1:]).equals(expected)
    if scenario == 'timeline':
        assert find_face([p for ps in session.resolved(master_t=0).values() for p in ps], point, 0) is None
    commit = client.post('/api/layers/fill', json={'point': point, 'master_t': .65, 'revision': candidate['revision']})
    assert commit.status_code == 200, commit.text
    assert commit.json()['source']['params']['subpaths'] == candidate['subpaths']


def test_fill_save_load(client, tmp_path):
    from axibridge.project_io import save_project, load_project
    source(True)
    candidate = client.post('/api/geometry/face', json={'point': [30,30]}).json()
    layer = client.post('/api/layers/fill', json={'point': [30,30], 'revision': candidate['revision']}).json()
    folder = tmp_path / 'saved'
    save_project(session.project, session.source_geometry, session.svg_files, folder)
    project, geometry, *_ = load_project(folder)
    assert project.layer(layer['id']).source.params == layer['source']['params']
    for actual, expected in zip(geometry[layer['id']], session.source_geometry[layer['id']]):
        assert actual.filled == expected.filled
        assert len(actual.points) == len(expected.points)
        for a, b in zip(actual.points, expected.points):
            assert a == pytest.approx(b, abs=1e-10)


def test_refit_workload_limit(client):
    from axibridge.fill_geometry import MAX_RING_VERTICES
    before = snapshot()
    ring = [[20,20]] * (MAX_RING_VERTICES + 1)
    assert client.post('/api/geometry/face/fit', json={'rings': [ring]}).status_code == 422
    assert snapshot() == before


def test_fitted_face_must_contain_actual_click(client):
    import math
    from shapely.geometry import Point
    from axibridge.fill_geometry import fit_face
    from axibridge.sources.pen import PenSubpath, _flatten_subpath
    coords = [(100 + 40*math.cos(i*2*math.pi/64), 100 + 40*math.sin(i*2*math.pi/64)) for i in range(64)]
    session.add_generated_layer('pen', {'subpaths': [{'closed': True, 'anchors': [{'x': x, 'y': y} for x,y in coords]}]})
    face = Polygon(coords)
    fitted = fit_face(face, 0)
    flat = [_flatten_subpath(PenSubpath(**sp), .05) for sp in fitted]
    excluded = face.difference(Polygon(flat[0]))
    assert not excluded.is_empty
    point = excluded.representative_point()
    assert face.contains(point) and not Polygon(flat[0]).contains(Point(point))
    before = snapshot()
    payload = {'point': list(point.coords[0]), 'detail': 0}
    assert client.post('/api/geometry/face', json=payload).status_code == 422
    assert client.post('/api/layers/fill', json={**payload, 'revision': before[1]}).status_code == 422
    assert snapshot() == before


def test_fill_announces_one_project_change(client, monkeypatch):
    from axibridge.events import bus
    source()
    events = []
    monkeypatch.setattr(bus, 'emit', events.append)
    preview = client.post('/api/geometry/face', json={'point': [30,30]}).json()
    assert not events
    response = client.post('/api/layers/fill', json={'point': [30,30], 'revision': preview['revision']}, headers={'X-Axb-Client': 'fill-test'})
    assert response.status_code == 200
    assert [event for event in events if event['type'] == 'project'] == [
        {'type': 'project', 'rev': preview['revision'] + 1, 'origin': 'fill-test'}]


def test_regenerate_expected_revision_is_atomic_and_strict(client):
    layer = source()
    url = f'/api/layers/{layer.id}/regenerate'
    params = {'subpaths': [square(100, 100, 20)]}
    rev = session.edit_rev
    assert client.post(url, json={'params': params, 'expected_revision': rev}).status_code == 200
    before = snapshot()
    assert client.post(url, json={'params': {'subpaths': [square()]}, 'expected_revision': rev, 'coalesce': 'gesture'}).status_code == 409
    assert snapshot() == before
    for invalid in [-1, True, 1.5, '1']:
        assert client.post(url, json={'expected_revision': invalid}).status_code == 422
    assert snapshot() == before
    assert client.post(url, json={'params': params}).status_code == 200


def test_rejected_regenerate_does_not_change_usage_or_coalescing(client, monkeypatch):
    from axibridge import api
    calls = []
    monkeypatch.setattr(api, 'record_module_use', lambda *args: calls.append(args))
    layer = source()
    url = f'/api/layers/{layer.id}/regenerate'
    rev = session.edit_rev
    first = {'subpaths': [square(100,100,20)]}
    second = {'subpaths': [square(140,100,20)]}
    assert client.post(url, json={'params': first, 'coalesce': 'drag'}).status_code == 200
    assert len(calls) == 1
    before = snapshot()
    assert client.post(url, json={'params': second, 'coalesce': 'other', 'expected_revision': rev}).status_code == 409
    assert snapshot() == before and len(calls) == 1
    assert client.post(url, json={'params': second, 'coalesce': 'drag'}).status_code == 200
    assert len(calls) == 1
    assert session.undo()
    assert session.project.layer(layer.id).source.params['subpaths'][0]['anchors'][0]['x'] == 20


@pytest.mark.parametrize('invalid', [-1, True, 1.5, '1'])
def test_session_regenerate_rejects_invalid_expected_revision(fresh_session, invalid):
    layer = source()
    before = snapshot()
    with pytest.raises(ValueError):
        session.regenerate_layer(layer.id, expected_revision=invalid)
    assert snapshot() == before
