"""A gallery asset is exact reusable geometry, independent of live projects."""
import json

import pytest

from axibridge.compose import Affine, CanvasLayer, EffectStep, LayerSource
from axibridge.model import Path
from axibridge.session import session


@pytest.fixture
def gallery(tmp_path, monkeypatch):
    from axibridge import gallery as module
    store = module.GalleryStore(tmp_path / "gallery")
    monkeypatch.setattr(module, "gallery_store", store)
    return store


@pytest.fixture
def client(gallery):
    from fastapi.testclient import TestClient
    from axibridge.app import create_app
    with TestClient(create_app()) as client:
        yield client


def save(client, source, **metadata):
    response = client.post('/api/gallery/prepare', json=source)
    assert response.status_code == 200, response.text
    prepared = response.json()
    response = client.post('/api/gallery', json={
        'capture_id': prepared['capture_id'], 'name': 'Collected shape',
        'tags': ['Organic', 'ink'], **metadata})
    assert response.status_code == 200, response.text
    return response.json(), prepared


def test_store_exact_restart_filter_metadata_and_bad_record(gallery):
    from axibridge.gallery import GalleryStore
    paths = [Path(points=[(-1.123456789123, 2), (4, 8), (-1.123456789123, 2)], filled=True)]
    draft = gallery.prepare(paths, 'Test', {'kind': 'generator', 'module': 'polygon', 'label': 'Polygon'})
    assert draft['geometry_type'] == 'line', 'three-point backtracking paths are not closed shapes'
    saved = gallery.save(draft['capture_id'], name='One', tags=[' Ink ', 'ink'], note='branches')
    assert saved['geometry_type'] == 'line'
    assert 'geometry_type' not in json.loads(gallery._file(saved['id']).read_text())
    reopened = GalleryStore(gallery.root)
    assert reopened.paths(saved['id']) == paths
    assert reopened.list(q='BRANCH', tag='ink', generator='polygon')['items'][0]['name'] == 'One'
    assert 'paths' not in reopened.list()['items'][0]
    assert saved['tags'] == ['Ink']
    reopened.update(saved['id'], name='Two', tags=['fine'], note='')
    assert reopened.get(saved['id'])['name'] == 'Two'
    assert reopened.get(saved['id'])['geometry_type'] == 'line'
    (gallery.root / ('f' * 32 + '.json')).write_text('{bad')
    assert len(reopened.list()['items']) == 1
    assert reopened.list()['warnings']
    reopened.delete(saved['id'])
    with pytest.raises(KeyError):
        reopened.get(saved['id'])


def test_geometry_type_classification_and_filtering_are_derived(gallery):
    def make(name, paths, tags, module):
        draft = gallery.prepare(paths, name, {
            'kind': 'generator', 'module': module, 'label': module.title()})
        saved = gallery.save(draft['capture_id'], name=name, tags=tags, note='find me')
        return draft, saved

    closed = [(0, 0), (2, 0), (2, 2), (0, 0)]
    shape_draft, shape = make('Shape', [Path(points=closed, filled=True)], ['shared'], 'polygon')
    _, line = make('Line', [
        Path(points=closed, filled=False),
        Path(points=[(0, 0), (2, 2)], filled=True),
    ], ['shared'], 'polygon')
    _, mixed = make('Mixed', [
        Path(points=closed, filled=True),
        Path(points=[(0, 0), (3, 1)]),
    ], ['other'], 'lines')

    assert shape_draft['geometry_type'] == 'shape'
    assert shape['geometry_type'] == 'shape'
    assert line['geometry_type'] == 'line'
    assert mixed['geometry_type'] == 'mixed'
    assert gallery.get(mixed['id'])['geometry_type'] == 'mixed'

    gallery.update(mixed['id'], name='Mixed updated', tags=['other'], note='find me')
    assert gallery.get(mixed['id'])['geometry_type'] == 'mixed'
    from axibridge.gallery import GalleryStore
    reopened = GalleryStore(gallery.root)
    assert reopened.get(shape['id'])['geometry_type'] == 'shape'
    assert [item['id'] for item in reopened.list(geometry_type='line')['items']] == [line['id']]
    assert [item['id'] for item in reopened.list(q='find', tag='shared', generator='polygon',
                                                  geometry_type='shape')['items']] == [shape['id']]
    assert reopened.list(tag='shared', geometry_type='mixed')['items'] == []


def test_layer_capture_freezes_effects_ignores_occlusion_and_does_not_mutate(client, gallery):
    layer = session.add_generated_layer('polygon', {'sides': 4, 'radius': 12})
    layer.transform = Affine(e=20, f=30)
    layer.effects = [EffectStep(effect='smoothen', params={'resolution': 2})]
    from axibridge import compose
    expected = compose.shape_layer(layer, session.source_geometry[layer.id],
        compose.guide_page(session.project), compose.line_diameter_for(layer, session.pens()))
    cover = session.add_generated_layer('polygon', {'sides': 4, 'radius': 100})
    cover.transform = Affine()
    session.source_geometry[cover.id] = [Path(points=[(-100, -100), (100, -100),
        (100, 100), (-100, 100), (-100, -100)], filled=True)]
    cover.occluder = True
    assert not session.resolved()[layer.id], 'fixture must actually hide the captured layer'
    before = session.project.model_dump_json()
    geometry = dict(session.source_geometry)
    session.clear_history()
    saved, draft = save(client, {'kind': 'layer', 'layer_id': layer.id})
    assert gallery.paths(saved['id']) == expected
    assert session.project.model_dump_json() == before
    assert session.source_geometry == geometry
    assert not session.can_undo()
    # Retrying an uncertain save with the same capture cannot duplicate it.
    again = client.post('/api/gallery', json={'capture_id': draft['capture_id'], 'name': 'retry'})
    assert again.json()['id'] == saved['id']
    assert len(gallery.list()['items']) == 1


def test_generator_full_precision_and_frozen_dialog(client, gallery):
    from axibridge import gencache
    from axibridge.registry import get_source
    source = {'kind': 'generator', 'module': 'polygon', 'params': {'sides': 7, 'radius': 12.3456789}}
    exact = gencache.generate_cached(get_source('polygon'), source['params'])
    before = session.project.model_dump_json()
    saved, draft = save(client, source)
    assert gallery.paths(saved['id']) == [p for layer in exact.layers for p in layer.paths]
    assert session.project.model_dump_json() == before
    assert '<svg' in draft['thumbnail']


def test_insert_centered_independent_undo_and_project_portability(client, gallery, tmp_path):
    from axibridge import project_io
    saved, _ = save(client, {'kind': 'generator', 'module': 'polygon', 'params': {'sides': 4, 'radius': 12}})
    session.clear_history()
    first = client.post(f"/api/gallery/{saved['id']}/insert").json()
    layer = session.project.layer(first['id'])
    assert layer.source.type == 'baked' and layer.source.generator is None
    assert not layer.effects
    assert len(session._history) == 1
    resolved = session.resolved()[layer.id]
    xs = [x for p in resolved for x, _ in p.points]
    ys = [y for p in resolved for _, y in p.points]
    guide = session.project.guide
    assert (min(xs) + max(xs)) / 2 == pytest.approx(guide.x + guide.width / 2)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(guide.y + guide.height / 2)
    assert max(xs) - min(xs) == pytest.approx(saved['width_mm'])
    assert session.undo() and not session.project.layers
    assert session.redo()
    second = client.post(f"/api/gallery/{saved['id']}/insert").json()
    assert second['id'] != first['id']
    gallery.delete(saved['id'])
    folder = tmp_path / 'portable'
    project_io.save_project(session.project, session.source_geometry, {}, folder)
    loaded = project_io.load_project(folder)
    reloaded_paths = loaded[1][first['id']]
    original_paths = session.source_geometry[first['id']]
    assert len(reloaded_paths) == len(original_paths)
    for actual, expected in zip(reloaded_paths, original_paths):
        assert actual.filled == expected.filled
        assert len(actual.points) == len(expected.points)
        for point, original in zip(actual.points, expected.points):
            assert point == pytest.approx(original, rel=0, abs=1e-12)
    assert session.resolved()[first['id']] == resolved


def test_capture_animation_frame_without_materializing_into_source(client, gallery):
    layer = session.add_generated_layer('polygon', {'sides': 4, 'radius': 10})
    animation = session.animate_layer(layer.id)
    keys = session._animation_keyframes_for(animation)
    session.regenerate_layer(keys[-1].id, {'sides': 4, 'radius': 35})
    expected = session.resolved(master_t=.7)[animation.id]
    session.resolved(master_t=.1)
    before = session.project.model_dump_json()
    sources = dict(session.source_geometry)
    history = len(session._history)
    saved, _ = save(client, {'kind': 'layer', 'layer_id': animation.id, 'master_t': .7})
    assert gallery.paths(saved['id']) == expected
    assert session.project.model_dump_json() == before
    assert session.source_geometry == sources
    assert len(session._history) == history


def test_empty_region_and_invalid_inputs(client):
    layer = CanvasLayer(name='empty', source=LayerSource(type='baked'))
    session.project.layers.append(layer)
    session.source_geometry[layer.id] = []
    assert client.post('/api/gallery/prepare', json={'kind': 'layer', 'layer_id': layer.id}).status_code == 400
    layer.region = True
    assert client.post('/api/gallery/prepare', json={'kind': 'layer', 'layer_id': layer.id}).status_code == 400
    assert client.post('/api/gallery/prepare', json={'kind': 'layer', 'layer_id': 'missing'}).status_code == 404
    assert client.post('/api/gallery', json={'capture_id': 'missing', 'name': 'x'}).status_code == 404
    assert client.get('/api/gallery/not-an-id').status_code == 404


def test_large_geometry_keeps_small_closed_silhouettes_in_preview(gallery):
    paths = [Path(points=[(float(i), float(i % 7)) for i in range(60001)]),
             Path(points=[(0, 0), (2, 0), (1, 1), (0, 0)], filled=True)]
    draft = gallery.prepare(paths, 'Dense', {'kind': 'layer', 'label': 'Layer'})
    from xml.etree import ElementTree
    svg = ElementTree.fromstring(draft['thumbnail'])
    silhouette = list(svg[0])[-1].attrib['points'].split()
    assert len(silhouette) >= 4
    saved = gallery.save(draft['capture_id'], name='Dense')
    assert gallery.paths(saved['id']) == paths


def test_thumbnail_uses_shared_padded_bounds():
    from axibridge.gallery import thumbnail, thumbnail_bounds
    paths = [Path(points=[(2, 3), (6, 5)])]
    rectangle = thumbnail_bounds(paths)
    assert rectangle == pytest.approx((1.76, 2.76, 4.48, 2.48))
    from xml.etree import ElementTree
    svg = ElementTree.fromstring(thumbnail(paths))
    assert tuple(map(float, svg.attrib['viewBox'].split())) == pytest.approx(rectangle)


def test_capture_is_frozen_and_failed_atomic_edit_preserves_saved_record(gallery, monkeypatch):
    from axibridge import gallery as module
    paths = [Path(points=[(0., 0.), (3.123456789, 4.)])]
    draft = gallery.prepare(paths, 'Line', {'kind': 'layer', 'label': 'Layer'})
    paths[0].points[1] = (99, 99)
    saved = gallery.save(draft['capture_id'], name='Original')
    assert gallery.paths(saved['id'])[0].points[-1] == (3.123456789, 4.)
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(OSError, match='disk full'):
        gallery.update(saved['id'], name='Failed change')
    assert gallery.get(saved['id'])['name'] == 'Original'
    assert not list(gallery.root.glob('*.tmp'))


def test_nonfinite_and_future_version_are_rejected(gallery):
    with pytest.raises(ValueError, match='non-finite'):
        gallery.prepare([Path(points=[(0, 0), (float('inf'), 2)])],
                        'Bad', {'kind': 'layer', 'label': 'Layer'})
    gallery.root.mkdir(exist_ok=True)
    (gallery.root / ('f' * 32 + '.json')).write_text(json.dumps({'version': 2}))
    assert not gallery.list()['items']
    assert gallery.list()['warnings']


def test_project_snapshot_preserves_submicron_asset_coordinates(client, gallery, tmp_path):
    from axibridge import project_io
    paths = [Path(points=[(0.123456789123, -0.987654321987), (1.234567891234, 2.345678912345)])]
    prepared = gallery.prepare(paths, 'Precise', {'kind': 'layer', 'label': 'Layer'})
    saved = gallery.save(prepared['capture_id'], name='Precise')
    layer = client.post(f"/api/gallery/{saved['id']}/insert").json()
    folder = tmp_path / 'precise'
    project_io.save_project(session.project, session.source_geometry, {}, folder)
    gallery.delete(saved['id'])
    loaded = project_io.load_project(folder)
    for actual, expected in zip(loaded[1][layer['id']][0].points, paths[0].points):
        assert actual == pytest.approx(expected, rel=0, abs=1e-14)


def test_popular_tags_count_assets_case_insensitively_across_filters(gallery):
    def make(name, tags):
        draft = gallery.prepare([Path(points=[(0, 0), (1, 1)])], name,
                                {'kind': 'layer', 'label': 'Layer'})
        return gallery.save(draft['capture_id'], name=name, tags=tags)
    first = make('One', ['Ink', 'ink', 'organic'])
    second = make('Two', ['ink', 'angular'])
    make('Three', ['organic'])
    stats = gallery.list(q='Three')['tag_counts']
    assert [(t['tag'].casefold(), t['count']) for t in stats] == [('ink', 2), ('organic', 2), ('angular', 1)]
    gallery.update(second['id'], name='Two', tags=['angular'])
    assert gallery.list()['tag_counts'][0] == {'tag': 'organic', 'count': 2}
    gallery.delete(first['id'])
    assert all(t['tag'].casefold() != 'ink' for t in gallery.list()['tag_counts'])
