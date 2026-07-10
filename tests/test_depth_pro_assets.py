import io
import sys

import pytest

from axibridge.assets import asset_store


def _png(shade: int, size=(8, 8)) -> bytes:
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
    from fastapi.testclient import TestClient

    from axibridge.app import create_app

    with TestClient(create_app()) as c:
        yield c


def test_depth_pro_status_reports_mocked_ready(client, monkeypatch):
    from axibridge import depth_pro

    monkeypatch.setattr(
        depth_pro,
        "status",
        lambda: {"available": True, "ready": False, "detail": "Depth Pro installed"},
    )

    r = client.get("/api/assets/depth-pro/status")

    assert r.status_code == 200
    assert r.json()["available"] is True


def test_depth_pro_status_reports_missing_configured_cli(monkeypatch):
    from axibridge import depth_pro

    monkeypatch.setenv("AXIBRIDGE_DEPTH_PRO_RUN", "/no/such/depth-pro-run")

    status = depth_pro.status()

    assert status["available"] is False
    assert "not found" in status["detail"]


def test_depth_pro_can_use_external_cli(tmp_path, monkeypatch):
    from axibridge import depth_pro

    script = tmp_path / "fake_depth_pro.py"
    script.write_text(
        "import argparse\n"
        "from pathlib import Path\n"
        "import numpy as np\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('-i')\n"
        "p.add_argument('-o')\n"
        "p.add_argument('--skip-display', action='store_true')\n"
        "args = p.parse_args()\n"
        "Path(args.o).mkdir(parents=True, exist_ok=True)\n"
        "np.savez_compressed(Path(args.o) / 'input.npz', depth=np.array([[1, 2], [3, 4]], dtype=float))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AXIBRIDGE_DEPTH_PRO_RUN", f"{sys.executable} {script}")

    png = depth_pro.depth_png_from_image(_png(80), "photo.png")
    name = asset_store.put("cli_depth.png", png)
    rows, w, h = asset_store.grayscale(name)

    assert (w, h) == (2, 2)
    assert rows[0][0] > rows[-1][-1]  # near/low metric depth maps to white.


def test_depth_pro_asset_generation_stores_new_png(client, monkeypatch):
    from axibridge import depth_pro

    source = asset_store.put("photo.png", _png(80, size=(5, 4)))

    def fake_depth(data: bytes, source_name: str, near_white: bool = True) -> bytes:
        assert data == asset_store.get(source)
        assert source_name == source
        assert near_white is True
        return _png(220, size=(3, 2))

    monkeypatch.setattr(depth_pro, "depth_png_from_image", fake_depth)

    r = client.post("/api/assets/depth-pro", json={"image": source, "near_white": True})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "photo_depth.png"
    rows, w, h = asset_store.grayscale(body["name"])
    assert (w, h) == (3, 2)
    assert rows[0][0] > 0.8


def test_depth_pro_generation_can_sample_sequence_frame(client, monkeypatch):
    from axibridge import depth_pro

    first = asset_store.put("clip#0000.png", _png(20))
    last = asset_store.put("clip#0001.png", _png(240))
    seen = {}

    def fake_depth(data: bytes, source_name: str, near_white: bool = True) -> bytes:
        seen["data"] = data
        seen["source_name"] = source_name
        return _png(120)

    monkeypatch.setattr(depth_pro, "depth_png_from_image", fake_depth)

    r = client.post("/api/assets/depth-pro", json={"image": "clip#", "frame": 1.0})

    assert r.status_code == 200, r.text
    assert first != last
    assert seen == {"data": asset_store.get(last), "source_name": last}
    assert r.json()["name"] == "clip_f1000_depth.png"


def test_depth_pro_unavailable_is_reported_without_storing(client, monkeypatch):
    from axibridge import depth_pro

    source = asset_store.put("photo.png", _png(80))

    def missing(*args, **kwargs):
        raise depth_pro.DepthProUnavailable("Depth Pro checkpoint not found")

    monkeypatch.setattr(depth_pro, "depth_png_from_image", missing)

    r = client.post("/api/assets/depth-pro", json={"image": source})

    assert r.status_code == 503
    assert "checkpoint" in r.json()["detail"]
    assert sorted(asset_store.all()) == [source]
