"""POST /api/assets/font: drag-in font upload, and the asset-store additions
that back it (font_label/font_names, and info() surviving non-image bytes
now sharing the store with images). Same isolation pattern as
test_assets_clear.py: asset_store is a module singleton, save/restore it
around each test."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.assets import asset_store

RECURSIVE = "axibridge/fonts/variable/Recursive-Variable.ttf"


@pytest.fixture(autouse=True)
def clean_asset_store():
    before = asset_store.all()
    asset_store.replace_all({})
    yield
    asset_store.replace_all(before)


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def test_upload_font_succeeds_and_appears_in_catalogue(client):
    with open(RECURSIVE, "rb") as f:
        r = client.post("/api/assets/font", files={"file": ("Dropped.ttf", f, "font/ttf")})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Dropped.ttf"
    assert any(f["id"] == "Dropped.ttf" and f["source"] == "uploaded" for f in body["fonts"])


def test_upload_rejects_non_font_bytes_and_rolls_back(client):
    r = client.post("/api/assets/font", files={"file": ("junk.ttf", b"not a font", "font/ttf")})
    assert r.status_code == 400
    assert "junk.ttf" not in asset_store.all()


def test_uploaded_font_does_not_break_image_asset_listing(client):
    with open(RECURSIVE, "rb") as f:
        client.post("/api/assets/font", files={"file": ("Dropped.ttf", f, "font/ttf")})
    # info() (the image dropdown's data source) must not crash on a font
    # asset sharing the store, and must not list it as an image either
    names = [a["name"] for a in client.get("/api/assets").json()["assets"]]
    assert "Dropped.ttf" not in names


def test_uploaded_font_usable_by_text_fill_and_survives_state_hydration(client):
    with open(RECURSIVE, "rb") as f:
        client.post("/api/assets/font", files={"file": ("Dropped.ttf", f, "font/ttf")})
    st = client.get("/api/state").json()
    assert any(f["id"] == "Dropped.ttf" for f in st["fonts"])

    r = client.post("/api/layers/generate",
                    json={"module": "text_fill", "params": {"text": "Hi", "font": "Dropped.ttf"}})
    assert r.status_code == 200


def test_clear_assets_garbage_collects_unreferenced_uploaded_font(client):
    with open(RECURSIVE, "rb") as f:
        client.post("/api/assets/font", files={"file": ("Dropped.ttf", f, "font/ttf")})
    r = client.delete("/api/assets")
    assert r.status_code == 200
    assert "Dropped.ttf" in r.json()["removed"]
    assert "Dropped.ttf" not in asset_store.all()


def test_clear_assets_keeps_a_font_referenced_by_a_layer(client):
    with open(RECURSIVE, "rb") as f:
        client.post("/api/assets/font", files={"file": ("Dropped.ttf", f, "font/ttf")})
    client.post("/api/layers/generate",
               json={"module": "text_fill", "params": {"text": "Hi", "font": "Dropped.ttf"}})
    r = client.delete("/api/assets")
    assert "Dropped.ttf" not in r.json()["removed"]
    assert "Dropped.ttf" in asset_store.all()
