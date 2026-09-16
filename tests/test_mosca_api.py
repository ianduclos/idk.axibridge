"""Portable recording assets, normal layers, and the read-only HTTP boundary."""
import io
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.assets import asset_store
from axibridge import mosca
from axibridge.session import session
from axibridge.module_library import ModuleLibraryStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / 'mosca' / 'out' / 'test'
    root.mkdir(parents=True)
    np.savez(root / 'walk.npz', path=np.array([[0.,0.],[10.,0.],[10.,10.],[20.,10.]]),
             pen_down=np.array([False,True,False,True]), dt=np.array(10.))
    monkeypatch.setenv('AXIBRIDGE_MOSCA_DIR', str(root.parent.parent))
    asset_store.replace_all({})
    with TestClient(create_app()) as c:
        yield c
    asset_store.replace_all({})


def prepare(client):
    response = client.post('/api/mosca/prepare',json={'id':'test/walk'})
    assert response.status_code == 200, response.text
    return response.json()


def keep(client, meta, progress=1):
    response = client.post('/api/layers/generate',json={'module':'mosca', 'params':{
        'recording':meta['recording'],'progress':progress,'tolerance':0}})
    assert response.status_code == 200, response.text
    return response.json()


def test_browse_preview_are_read_only_and_keeps_are_independent(client):
    assert client.get('/api/mosca/recordings').json()['recordings'][0]['id'] == 'test/walk'
    meta = prepare(client)
    assert asset_store.all() == {}
    before_history = len(session._history)
    preview = client.post('/api/mosca/preview',json={'params':{
        'recording':meta['recording'],'progress':.5,'tolerance':0}})
    assert preview.status_code == 200, preview.text
    assert len(preview.json()['lines']) == 1
    assert session.project.layers == [] and len(session._history) == before_history
    first = keep(client,meta,.5)
    second = keep(client,meta,1)
    assert first['id'] != second['id']
    assert session.project.layers[0].source.params['progress'] == .5
    assert len(session._history) == before_history + 2
    assert meta['recording'] in asset_store.all()
    assert client.delete('/api/assets').json()['kept'] == [meta['recording']]
    assert session.undo()
    assert len(session.project.layers) == 1


def test_export_import_retains_recording_without_source(client,monkeypatch,tmp_path):
    meta = prepare(client)
    original = keep(client,meta,.5)
    data = client.get('/api/project/export.zip')
    assert data.status_code == 200, data.text
    with zipfile.ZipFile(io.BytesIO(data.content)) as archive:
        assert any(name.endswith('/'+meta['recording']) for name in archive.namelist())
    assert client.post('/api/project/new').status_code == 200
    with mosca._prepared_lock:
        mosca._prepared.clear(); mosca._prepared_size = 0
    monkeypatch.setenv('AXIBRIDGE_MOSCA_DIR',str(tmp_path/'absent'))
    imported = client.post('/api/project/import',files={'file':('portable.zip',data.content,'application/zip')})
    assert imported.status_code == 200, imported.text
    assert session.project.layers[0].source.params == original['source']['params']
    info = client.get('/api/mosca/info',params={'recording':meta['recording']})
    assert info.status_code == 200, info.text
    keep(client,meta,1)
    assert len(session.project.layers) == 2
    assert len(session.source_geometry[session.project.layers[-1].id]) == 2


def test_recording_is_excluded_from_presets(client,tmp_path):
    meta = prepare(client)
    library = ModuleLibraryStore(tmp_path/'library')
    preset = library.create('source','mosca','Fine',{'recording':meta['recording'],'progress':.2,'tolerance':.01})
    assert 'recording' not in preset['params']
    assert preset['params']['tolerance'] == .01


def test_invalid_source_and_missing_directory_are_actionable(client,monkeypatch,tmp_path):
    assert client.post('/api/mosca/prepare',json={'id':'../private'}).status_code == 400
    monkeypatch.setenv('AXIBRIDGE_MOSCA_DIR',str(tmp_path/'absent'))
    response = client.get('/api/mosca/recordings')
    assert response.status_code == 400
    assert 'AXIBRIDGE_MOSCA_DIR' in response.json()['detail']


def test_new_preview_cancels_old_geometry_work(client,monkeypatch):
    import threading
    from axibridge.registry import get_source
    from axibridge.render_work import checkpoint
    meta = prepare(client)
    source = get_source('mosca')
    generate = source.generate
    entered = threading.Event()
    release = threading.Event()
    result = []

    def slow(params):
        if params.progress == .321:
            entered.set()
            assert release.wait(5)
            checkpoint()
        return generate(params)

    monkeypatch.setattr(source,'generate',slow)
    thread = threading.Thread(target=lambda: result.append(client.post('/api/mosca/preview',json={
        'params':{'recording':meta['recording'],'progress':.321}})))
    thread.start()
    try:
        assert entered.wait(5)
        newer = client.post('/api/mosca/preview',json={'params':{'recording':meta['recording'],'progress':.654}})
        assert newer.status_code == 200
    finally:
        release.set(); thread.join(5)
    assert not thread.is_alive() and result[0].status_code == 409


def test_stationary_recording_cannot_be_kept_by_bench(client,monkeypatch,tmp_path):
    root = tmp_path/'stationary'/'out'/'test'
    root.mkdir(parents=True)
    np.savez(root/'walk.npz',path=np.ones((3,2)))
    monkeypatch.setenv('AXIBRIDGE_MOSCA_DIR',str(root.parent.parent))
    meta = prepare(client)
    preview = client.post('/api/mosca/preview',json={'params':{'recording':meta['recording']}})
    assert preview.status_code == 200
    assert preview.json()['drawable'] is False
