"""'Clear unused assets' (Ian's urgent item 5): DELETE /api/assets drops
assets no layer currently references, so a long session's asset store
doesn't grow unboundedly. Referenced assets (source params, effect-step
params, whole sequence clips) survive unless ?force=true is passed.

Same isolation pattern as test_depth_pro_assets.py / test_plotterfun.py:
asset_store is a module singleton, save/restore it around each test; the
session/project is already reset per test by conftest's fresh_session."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.assets import asset_store
from axibridge.compose import CanvasLayer, EffectStep, LayerSource
from axibridge.session import session


def _png(shade: int = 128, size: tuple[int, int] = (4, 4)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", size, shade).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def clean_asset_store():
    before = asset_store.all()
    asset_store.replace_all({})
    yield
    asset_store.replace_all(before)


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def test_unreferenced_asset_is_removed(client):
    asset_store.put("unused.png", _png(10))
    session.project.layers.append(CanvasLayer(
        source=LayerSource(type="svg", file="x")))

    r = client.delete("/api/assets")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["removed"] == ["unused.png"]
    assert body["kept"] == []
    assert asset_store.all() == {}


def test_asset_referenced_by_generator_layer_is_kept(client):
    asset_store.put("used.png", _png(20))
    asset_store.put("unused.png", _png(30))
    session.project.layers.append(CanvasLayer(
        source=LayerSource(type="generator", generator="image_threshold",
                            params={"image": "used.png"})))

    r = client.delete("/api/assets")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kept"] == ["used.png"]
    assert body["removed"] == ["unused.png"]
    assert set(asset_store.all()) == {"used.png"}


def test_asset_referenced_by_effect_step_is_kept(client):
    asset_store.put("depth.png", _png(40))
    asset_store.put("unused.png", _png(50))
    session.project.layers.append(CanvasLayer(
        source=LayerSource(type="svg", file="x"),
        effects=[EffectStep(effect="depth_displace", params={"image": "depth.png"})]))

    r = client.delete("/api/assets")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kept"] == ["depth.png"]
    assert body["removed"] == ["unused.png"]
    assert set(asset_store.all()) == {"depth.png"}


def test_force_removes_referenced_assets_too(client):
    asset_store.put("used.png", _png(60))
    session.project.layers.append(CanvasLayer(
        source=LayerSource(type="generator", generator="image_threshold",
                            params={"image": "used.png"})))

    r = client.delete("/api/assets?force=true")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["removed"] == ["used.png"]
    assert body["kept"] == []
    assert asset_store.all() == {}


def test_sequence_frames_kept_whole_when_clip_is_referenced(client):
    asset_store.put("clip#0000.jpg", _png(70))
    asset_store.put("clip#0001.jpg", _png(80))
    asset_store.put("solo.png", _png(90))
    session.project.layers.append(CanvasLayer(
        source=LayerSource(type="generator", generator="image_threshold",
                            params={"image": "clip#"})))

    r = client.delete("/api/assets")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kept"] == ["clip#0000.jpg", "clip#0001.jpg"]
    assert body["removed"] == ["solo.png"]
    assert set(asset_store.all()) == {"clip#0000.jpg", "clip#0001.jpg"}
