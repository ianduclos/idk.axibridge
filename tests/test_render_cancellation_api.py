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


@pytest.mark.parametrize('operation', ['patch', 'delete', 'bulk_delete'])
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
            fresh = client.get('/api/compose/resolved?stats=false')
            assert fresh.status_code == 200
            if operation == 'patch':
                assert session.source_geometry[layer.id] is original
                assert len(fresh.json()['layers']) == 1
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
