"""Asset publication and recovery dirty-state regressions."""

from __future__ import annotations

import asyncio
import io
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from axibridge import depth_pro
from axibridge.app import create_app
from axibridge.assets import asset_store
from axibridge.session import session
from starlette.datastructures import UploadFile


def _png(shade: int = 128) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("L", (4, 4), shade).save(out, "PNG")
    return out.getvalue()


@pytest.fixture(autouse=True)
def clean_assets():
    before = asset_store.all()
    asset_store.replace_all({})
    session.begin_project()
    yield
    asset_store.replace_all(before)


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def _start_request(call):
    result = {}

    def run():
        try:
            result["response"] = call()
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, result


def _response(thread, result):
    thread.join(timeout=5)
    assert not thread.is_alive(), "request did not finish"
    assert "error" not in result, repr(result.get("error"))
    return result["response"]


def test_failed_image_replacement_preserves_prior_asset_and_clean_state(client):
    original = _png(40)
    asset_store.put("same.png", original)
    session.begin_project()

    response = client.post("/api/assets", files={"file": ("same.png", b"bad image", "image/png")})

    assert response.status_code == 400
    assert asset_store.get("same.png") == original
    assert session.recovery_status()["dirty"] is False


def test_failed_font_replacement_preserves_prior_asset_and_clean_state(client):
    font = Path(__file__).resolve().parents[1] / "axibridge/fonts/variable/Recursive-Variable.ttf"
    original = font.read_bytes()
    asset_store.put("same.ttf", original)
    session.begin_project()

    response = client.post("/api/assets/font", files={"file": ("same.ttf", b"bad font", "font/ttf")})

    assert response.status_code == 400
    assert asset_store.get("same.ttf") == original
    assert session.recovery_status()["dirty"] is False


def test_identical_asset_replace_all_does_not_mark_recovery_dirty():
    asset_store.put("image.png", _png())
    session.begin_project()
    version = asset_store.version()

    asset_store.replace_all(asset_store.all())

    assert asset_store.version() > version
    status = session.recovery_status()
    assert status["dirty"] is False
    assert status["revision"] == 0


def test_depth_inference_cannot_publish_into_new_project(client, monkeypatch):
    asset_store.put("photo.png", _png(20))
    old_session_id = session.recovery_status()["session_id"]
    entered = threading.Event()
    release = threading.Event()

    def delayed_depth(*args, **kwargs):
        entered.set()
        assert release.wait(5), "test did not release inference"
        return _png(220)

    monkeypatch.setattr(depth_pro, "depth_png_from_image", delayed_depth)
    thread, result = _start_request(
        lambda: client.post("/api/assets/depth-pro", json={"image": "photo.png"})
    )
    try:
        assert entered.wait(5), "inference did not start"
        switched = client.post("/api/project/new", json={"recovery_action": "discard"})
        assert switched.status_code == 200, switched.text
        assert session.recovery_status()["session_id"] != old_session_id
    finally:
        release.set()

    response = _response(thread, result)
    assert response.status_code == 409, response.text
    assert asset_store.all() == {}


def test_async_image_read_cannot_publish_into_new_project(client, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    original_read = UploadFile.read
    old_session_id = session.recovery_status()["session_id"]

    async def delayed_read(self, *args, **kwargs):
        if self.filename == "late.png":
            entered.set()
            assert await asyncio.to_thread(release.wait, 5), "test did not release upload"
        return await original_read(self, *args, **kwargs)

    monkeypatch.setattr(UploadFile, "read", delayed_read)
    thread, result = _start_request(
        lambda: client.post("/api/assets", files={"file": ("late.png", _png(), "image/png")})
    )
    try:
        assert entered.wait(5), "upload read did not start"
        switched = client.post("/api/project/new", json={"recovery_action": "discard"})
        assert switched.status_code == 200, switched.text
        assert session.recovery_status()["session_id"] != old_session_id
    finally:
        release.set()

    response = _response(thread, result)
    assert response.status_code == 409, response.text
    assert asset_store.all() == {}


def test_sequence_replacement_publishes_complete_frame_set(client, monkeypatch):
    for i in range(3):
        asset_store.put(f"shot#{i:04d}.jpg", _png(30 + i))
    session.begin_project()
    entered = threading.Event()
    release = threading.Event()
    original_replace_all = asset_store.replace_all

    def paused_replace_all(assets):
        original_replace_all(assets)
        entered.set()
        assert release.wait(5), "test did not release sequence publication"

    monkeypatch.setattr(asset_store, "replace_all", paused_replace_all)
    files = [("files", (f"shot{i:04d}.png", _png(120 + i), "image/png")) for i in range(2)]
    thread, result = _start_request(lambda: client.post("/api/assets/sequence", files=files))
    try:
        assert entered.wait(5), "sequence publication did not start"
        visible = {name for name in asset_store.all() if name.startswith("shot#")}
        assert visible in (
            {"shot#0000.jpg", "shot#0001.jpg", "shot#0002.jpg"},
            {"shot#0000.jpg", "shot#0001.jpg"},
        )
    finally:
        release.set()

    response = _response(thread, result)
    assert response.status_code == 200, response.text
    assert set(asset_store.all()) == {"shot#0000.jpg", "shot#0001.jpg"}
