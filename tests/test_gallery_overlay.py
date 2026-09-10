"""Gallery placement is shared by transient previews and independent insertion."""
import pytest

from test_gallery import gallery, client
from axibridge.model import Path
from axibridge.session import session


def test_preview_matches_insertion_and_is_read_only(client, gallery):
    paths = [Path(points=[(-11.125, 5), (32, 5), (32, 22), (-11.125, 5)], filled=True)]
    draft = gallery.prepare(paths, 'Offset shape', {'kind': 'layer', 'label': 'Layer'})
    item = gallery.save(draft['capture_id'], name='Offset shape')
    before = session.project.model_dump()
    undo = list(session._history)
    response = client.get(f"/api/gallery/{item['id']}/preview")
    assert response.status_code == 200
    preview = response.json()
    assert session.project.model_dump() == before
    assert list(session._history) == undo
    assert preview['x'] + preview['width'] / 2 == pytest.approx(session.project.guide.x + session.project.guide.width / 2)
    assert preview['y'] + preview['height'] / 2 == pytest.approx(session.project.guide.y + session.project.guide.height / 2)
    inserted = client.post(f"/api/gallery/{item['id']}/insert").json()
    assert inserted['transform'] == preview['transform']
    assert session.source_geometry[inserted['id']] == paths
    assert client.get('/api/gallery?geometry_type=shape').json()['items'][0]['id'] == item['id']
    assert client.get('/api/gallery?geometry_type=line').json()['items'] == []
    assert client.get('/api/gallery?geometry_type=invalid').status_code == 422
    assert client.get('/api/gallery/missing/preview').status_code == 404


def test_tiny_preview_contains_full_stroke(client, gallery):
    import xml.etree.ElementTree as ET
    draft = gallery.prepare([Path(points=[(0, 0), (0, .1)])], 'Tiny line',
                            {'kind': 'layer', 'label': 'Layer'})
    item = gallery.save(draft['capture_id'], name='Tiny line')
    preview = client.get(f"/api/gallery/{item['id']}/preview").json()
    svg = ET.fromstring(preview['svg'])
    x, y, width, height = map(float, svg.attrib['viewBox'].split())
    stroke = float(svg[0].attrib['stroke-width'])
    assert x <= -stroke / 2 and x + width >= stroke / 2
    assert y <= -stroke / 2 and y + height >= .1 + stroke / 2
    assert preview['width'] == width and preview['height'] == height
