"""Plot-time crop: _crop_rect resolution, the vpype clip in plot_document /
exports, and estimate shrinkage. The Compose preview (session.resolved) is
never cropped — that's the contract."""

import io
import zipfile

import pytest

from axibridge.compose import BED_HEIGHT, BED_WIDTH, PlotOptions
from axibridge.session import session


def _all_points(doc):
    return [(x, y) for layer in doc.layers for p in layer.paths for x, y in p.points]


def _straddler():
    """A polygon centred on the guide's LEFT edge — half in, half out. The
    polygon generator's local geometry is centred at (radius+2, radius+2)."""
    g = session.project.guide
    layer = session.add_generated_layer("polygon", {"sides": 24, "radius": 30})
    session.update_layer(layer.id, {"transform": {
        "a": 1, "b": 0, "c": 0, "d": 1,
        "e": g.x - 32, "f": g.y + g.height / 2 - 32}})
    return layer


def _set_crop(**kw):
    opts = session.project.plot_options.model_dump()
    opts.update(kw)
    session.project.plot_options = PlotOptions(**opts)


# -- _crop_rect ---------------------------------------------------------------


def test_crop_rect_off_is_none():
    assert session._crop_rect() is None


def test_crop_rect_modes_and_margin():
    g = session.project.guide
    _set_crop(crop="guide")
    assert session._crop_rect() == (g.x, g.y, g.width, g.height)
    _set_crop(crop="bed")
    assert session._crop_rect() == (0.0, 0.0, BED_WIDTH, BED_HEIGHT)
    _set_crop(crop="custom", crop_x=10, crop_y=20, crop_w=100, crop_h=50)
    assert session._crop_rect() == (10, 20, 100, 50)
    _set_crop(crop="custom", crop_x=10, crop_y=20, crop_w=100, crop_h=50, crop_margin_mm=5)
    assert session._crop_rect() == (15, 25, 90, 40)


def test_crop_rect_collapsing_margin_disables():
    _set_crop(crop="custom", crop_x=0, crop_y=0, crop_w=40, crop_h=40, crop_margin_mm=20)
    assert session._crop_rect() is None  # 40 - 2*20 == 0: collapsed, never raise


# -- plot document / estimates --------------------------------------------------


def test_plot_document_clips_to_guide():
    _straddler()
    uncropped = session.plot_document()
    _set_crop(crop="guide")
    cropped = session.plot_document()
    g = session.project.guide
    pts = _all_points(cropped)
    assert pts, "some geometry must survive the crop"
    eps = 1e-6
    assert all(g.x - eps <= x <= g.x + g.width + eps for x, _ in pts)
    assert all(g.y - eps <= y <= g.y + g.height + eps for _, y in pts)
    # and the crop genuinely removed the outside half
    def pen_down(doc):
        return sum(p.length() for layer in doc.layers for p in layer.paths)
    assert pen_down(cropped) < pen_down(uncropped)


def test_crop_off_output_unchanged():
    _straddler()
    before = _all_points(session.plot_document())
    _set_crop(crop="off", crop_margin_mm=50)  # margin without a mode: inert
    assert _all_points(session.plot_document()) == before


def test_preview_resolve_is_never_cropped():
    layer = _straddler()
    _set_crop(crop="guide", crop_margin_mm=10)
    g = session.project.guide
    pts = [(x, y) for p in session.resolved()[layer.id] for x, y in p.points]
    assert any(x < g.x for x, _ in pts)  # the outside half is still previewed


# -- API surfaces ----------------------------------------------------------------


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from axibridge.app import create_app

    with TestClient(create_app()) as c:
        yield c


def _client_straddler(client):
    g = client.get("/api/project").json()["guide"]
    r = client.post("/api/layers/generate",
                    json={"module": "polygon", "params": {"sides": 24, "radius": 30}})
    lid = r.json()["id"]
    client.patch(f"/api/layers/{lid}", json={"transform": {
        "a": 1, "b": 0, "c": 0, "d": 1,
        "e": g["x"] - 32, "f": g["y"] + g["height"] / 2 - 32}})
    return g


def _put_crop(client, **kw):
    opts = client.get("/api/project").json()["plot_options"]
    opts.update(kw)
    assert client.put("/api/project", json={"plot_options": opts}).status_code == 200


def test_plan_estimate_shrinks_with_crop(client):
    _client_straddler(client)
    full = client.get("/api/plan").json()["job"]["pen_down_distance"]
    _put_crop(client, crop="guide")
    cropped = client.get("/api/plan").json()["job"]["pen_down_distance"]
    assert 0 < cropped < full


def test_svg_download_is_cropped(client):
    from axibridge import svg_io

    g = _client_straddler(client)
    _put_crop(client, crop="guide")
    r = client.get("/api/doc/all/svg")
    assert r.status_code == 200
    doc = svg_io.doc_from_svg(r.text, 0.1)
    pts = _all_points(doc)
    assert pts
    assert all(x >= g["x"] - 1e-3 for x, _ in pts)


def test_animation_export_frames_are_cropped(client):
    g = _client_straddler(client)
    # animated pair so the export has something to sample
    layers = client.get("/api/project").json()["layers"]
    client.post(f"/api/layers/{layers[0]['id']}/animate")
    _put_crop(client, crop="guide")
    r = client.get("/api/animation/export.zip?frames=3")
    assert r.status_code == 200
    from axibridge import svg_io

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    for name in zf.namelist():
        doc = svg_io.doc_from_svg(zf.read(name).decode(), 0.1)
        assert all(x >= g["x"] - 1e-3 for x, _ in _all_points(doc))


def test_old_project_plot_options_load_without_crop_fields():
    opts = PlotOptions(**{"sort": True, "merge": False})  # pre-crop dict
    assert opts.crop == "off" and opts.crop_margin_mm == 0.0
