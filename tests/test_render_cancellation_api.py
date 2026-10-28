"""Concurrent edits can interrupt pure preview work without partial commits."""
from concurrent.futures import ThreadPoolExecutor
import threading
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from axibridge import compose, registry
from axibridge.app import create_app
from axibridge.render_work import checkpoint
from axibridge.session import session


class EmptyParams(BaseModel):
    pass


@pytest.mark.parametrize('operation', ['patch', 'regenerate', 'delete', 'bulk_delete'])
@pytest.mark.parametrize('preview', ['resolved', 'effects', 'plan', 'sheet', 'raster'])
def test_edit_interrupts_preview_and_never_publishes_partial_cache(monkeypatch, operation, preview):
    entered, stop = threading.Event(), threading.Event()

    class SlowEffect(registry.EffectModule):
        id = 'cancellation_probe'
        Params = EmptyParams

        def apply(self, paths, params, ctx):
            entered.set()
            while not stop.wait(.002):
                checkpoint()
            checkpoint()
            return paths

    monkeypatch.setitem(registry._EFFECTS, SlowEffect.id, SlowEffect())
    layer = session.add_generated_layer('polygon', {'sides': 3})
    effects = [{'effect': SlowEffect.id, 'params': {}}]
    session.update_layer(layer.id, {'effects': effects})
    original = session.source_geometry[layer.id]
    with TestClient(create_app()) as client, ThreadPoolExecutor(max_workers=2) as pool:
        if preview == 'effects':
            request = lambda: client.post(f'/api/layers/{layer.id}/effects/preview', json={'effects': effects})
        elif preview == 'sheet':
            request = lambda: client.get('/api/preview/sheet', params={'sheet': json.dumps({'cols': 1, 'rows': 1, 'frames': 2})})
        elif preview == 'raster':
            request = lambda: client.get('/api/animation/preview.png?width_px=240')
        else:
            request = lambda: client.get('/api/plan' if preview == 'plan' else '/api/compose/resolved?stats=false')
        result = pool.submit(request)
        try:
            assert entered.wait(3), 'preview never reached the slow effect'
            if operation == 'patch':
                changed = pool.submit(client.patch, f'/api/layers/{layer.id}', json={'effects': []})
            elif operation == 'regenerate':
                changed = pool.submit(client.post, f'/api/layers/{layer.id}/regenerate',
                                      json={'params': {'sides': 5}})
            elif operation == 'delete':
                changed = pool.submit(client.delete, f'/api/layers/{layer.id}')
            else:
                changed = pool.submit(client.post, '/api/layers/delete', json={'ids': [layer.id]})
            response = changed.result(timeout=3)
            assert response.status_code == 200, response.text
            cancelled = result.result(timeout=3)
            assert cancelled.status_code == 409
            assert cancelled.json()['detail']['code'] == 'render_cancelled'
            assert not session._shaped_cache.get(layer.id), 'cancelled effect was cached'
            if operation == 'regenerate':
                stop.set()  # the retained effect may now finish the fresh render
            fresh = client.get('/api/compose/resolved?stats=false')
            assert fresh.status_code == 200
            if operation == 'patch':
                assert session.source_geometry[layer.id] is original
                assert len(fresh.json()['layers']) == 1
            elif operation == 'regenerate':
                assert len(fresh.json()['layers']) == 1
                assert session.project.layer(layer.id).source.params['sides'] == 5
            else:
                assert fresh.json()['layers'] == []
                assert session.undo()
                assert session.source_geometry[layer.id] is original
        finally:
            stop.set()


def test_cancelled_occlusion_finishes_cache_lifecycle(monkeypatch):
    layer = session.add_generated_layer('polygon', {'sides': 3})
    finished = []
    original_end = session._occlusion_cache.end

    def end(ids):
        finished.append(ids)
        original_end(ids)

    def cancel_mask(*args):
        session.render_work.cancel()
        checkpoint()

    session.update_layer(layer.id, {'occluder': True})
    monkeypatch.setattr(session._occlusion_cache, 'end', end)
    monkeypatch.setattr(session._occlusion_cache, 'mask', cancel_mask)
    with TestClient(create_app()) as client:
        response = client.get('/api/compose/resolved?stats=false')
    assert response.status_code == 409
    assert finished == [{layer.id}]


def test_cancellation_is_not_applied_to_unscoped_plot_resolution():
    layer = session.add_generated_layer('polygon', {'sides': 3})
    with session.render_work.mutation():
        # A pending UI edit must not silently cancel plotting/committing work.
        assert session.resolved()[layer.id]


def test_delete_interrupts_estimation_after_geometry_is_finished(monkeypatch):
    from axibridge.model import PathDocument

    layer = session.add_generated_layer('polygon', {'sides': 3})
    entered, stop = threading.Event(), threading.Event()
    original_iter = PathDocument.iter_paths

    def many_paths(doc):
        pair = next(original_iter(doc))
        entered.set()
        while not stop.wait(.002):
            yield pair

    monkeypatch.setattr(PathDocument, 'iter_paths', many_paths)
    with TestClient(create_app()) as client, ThreadPoolExecutor(max_workers=2) as pool:
        rendering = pool.submit(client.get, '/api/compose/resolved')
        try:
            assert entered.wait(3)
            deleted = pool.submit(client.delete, f'/api/layers/{layer.id}')
            assert deleted.result(timeout=3).status_code == 200
            assert rendering.result(timeout=3).json()['detail']['code'] == 'render_cancelled'
        finally:
            stop.set()


def test_real_server_replacement_and_disconnect_cancel_fill_work(monkeypatch):
    import socket
    import time
    import uvicorn
    from axibridge.render_work import RenderCancelled

    started = [threading.Event(), threading.Event()]
    cancelled = [threading.Event(), threading.Event()]
    def cooperative(point, **kwargs):
        index = int(point[0]) - 1
        started[index].set()
        try:
            while True:
                checkpoint()
                threading.Event().wait(.005)
        except RenderCancelled:
            cancelled[index].set()
            raise
    monkeypatch.setattr(session, 'preview_fill_face', cooperative)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(), log_level='error', lifespan='off'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3
    while not server.started and time.monotonic() < deadline:
        threading.Event().wait(.005)
    assert server.started
    def send(point):
        conn = socket.create_connection(('127.0.0.1', port), timeout=3)
        body = json.dumps({'point': [point, 1]}).encode()
        conn.sendall(b'POST /api/geometry/face HTTP/1.1\r\nHost: localhost\r\nX-Axb-Client: same-tab\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
        return conn
    first = second = None
    try:
        first = send(1)
        assert started[0].wait(3)
        second = send(2)
        assert cancelled[0].wait(3)
        assert started[1].wait(3)
        assert b'409' in first.recv(4096)
        second.close(); second = None
        assert cancelled[1].wait(3)
        deadline = time.monotonic() + 3
        while session.render_work._events and time.monotonic() < deadline:
            threading.Event().wait(.005)
        assert not session.render_work._events
    finally:
        if first: first.close()
        if second: second.close()
        server.should_exit = True
        thread.join(3)
        sock.close()
        # Earlier TestClient lifespans leave the singleton pointing at their
        # closed loop; this lifespan-free server must not leak that into later tests.
        from axibridge.events import bus
        if bus._loop is not None and bus._loop.is_closed():
            bus._loop = None
        assert not thread.is_alive()
