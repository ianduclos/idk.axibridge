"""Frame-sequence assets: the store's prefix index + resolve_frame, the
POST /api/assets/sequence importer (multi-image and video), and the ``frame``
param wired through an image-consuming generator.

All synthetic and hardware-free: tiny PNGs made with PIL, and (for the video
path) a tiny clip written with imageio — skipped gracefully if ffmpeg is
missing. AXIBRIDGE_CONFIG_DIR isolation is set up in conftest.py."""

import io

import pytest

from axibridge.assets import SEQUENCE_FRAME_RE, asset_store


def _png(shade: int, size=(8, 8)) -> bytes:
    """Solid-gray PNG of the given 0..255 shade."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", size, shade).save(buf, "PNG")
    return buf.getvalue()


def _png_blob(dark_box, size=(32, 32)) -> bytes:
    """White PNG with one black rectangle ``dark_box`` = (x0,y0,x1,y1)."""
    from PIL import Image, ImageDraw

    img = Image.new("L", size, 255)
    ImageDraw.Draw(img).rectangle(dark_box, fill=0)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def clean_asset_store():
    """The store is a module singleton — start each test empty, restore after."""
    before = asset_store.all()
    asset_store.replace_all({})
    yield
    asset_store.replace_all(before)


# -- store: index + resolve_frame --------------------------------------------


def test_regex_matches_frames_not_plain():
    assert SEQUENCE_FRAME_RE.match("clip#0000.jpg").group(1) == "clip#"
    assert SEQUENCE_FRAME_RE.match("clip#0123.png").group(1) == "clip#"
    assert SEQUENCE_FRAME_RE.match("plain.png") is None
    assert SEQUENCE_FRAME_RE.match("clip#12.jpg") is None  # needs 4+ digits


def test_resolve_frame_maps_normalized_position():
    for i in range(5):
        asset_store.put(f"clip#{i:04d}.png", _png(i * 40))
    assert asset_store.resolve_frame("clip#", 0.0) == "clip#0000.png"
    assert asset_store.resolve_frame("clip#", 1.0) == "clip#0004.png"
    assert asset_store.resolve_frame("clip#", 0.5) == "clip#0002.png"  # round(0.5*4)=2
    assert asset_store.resolve_frame("clip#", 0.24) == "clip#0001.png"  # round(0.96)=1
    assert asset_store.resolve_frame("clip#", 0.76) == "clip#0003.png"  # round(3.04)=3
    # clamps out-of-range, never raises
    assert asset_store.resolve_frame("clip#", -5.0) == "clip#0000.png"
    assert asset_store.resolve_frame("clip#", 9.0) == "clip#0004.png"


def test_resolve_frame_passes_plain_and_unknown_through():
    asset_store.put("still.png", _png(128))
    assert asset_store.resolve_frame("still.png", 0.7) == "still.png"
    assert asset_store.resolve_frame("no-such", 0.5) == "no-such"  # never raises


def test_info_collapses_sequence_to_one_entry():
    for i in range(3):
        asset_store.put(f"clip#{i:04d}.png", _png(80, size=(10, 6)))
    asset_store.put("still.png", _png(128, size=(4, 4)))
    info = asset_store.info()
    by_name = {e["name"]: e for e in info}
    # exactly two entries: the sequence prefix + the plain still
    assert set(by_name) == {"clip#", "still.png"}
    assert by_name["clip#"] == {"name": "clip#", "frames": 3, "width": 10, "height": 6}
    assert by_name["still.png"] == {"name": "still.png", "frames": 1, "width": 4, "height": 4}
    # individual frames must not leak into the listing
    assert not any(e["name"].startswith("clip#0") for e in info)


def test_get_sequence_prefix_returns_first_frame_bytes():
    first = _png(10)
    asset_store.put("clip#0000.png", first)
    asset_store.put("clip#0001.png", _png(200))
    assert asset_store.get("clip#") == first  # representative image, not a 404


# -- API: importer -----------------------------------------------------------


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from axibridge.app import create_app

    with TestClient(create_app()) as c:
        yield c


def _imgfiles(shades, stem="shot"):
    return [("files", (f"{stem}{i:04d}.png", _png(s), "image/png"))
            for i, s in enumerate(shades)]


def test_multi_image_upload_creates_sequence(client):
    r = client.post("/api/assets/sequence", files=_imgfiles([0, 60, 120, 180]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "shot#"
    assert body["frames"] == 4
    seq = {e["name"]: e for e in body["assets"]}["shot#"]
    assert seq["frames"] == 4
    # the frames landed as concrete assets under the prefix, re-encoded to jpg
    keys = sorted(asset_store.all())
    assert keys == [f"shot#{i:04d}.jpg" for i in range(4)]


def test_frames_param_subsamples_evenly(client):
    r = client.post("/api/assets/sequence",
                    files=_imgfiles([0, 30, 60, 90, 120, 150]), data={"frames": "3"})
    assert r.status_code == 200, r.text
    assert r.json()["frames"] == 3
    assert len(asset_store.all()) == 3


def test_reimport_shorter_leaves_no_stale_frames(client):
    client.post("/api/assets/sequence", files=_imgfiles([0, 40, 80, 120, 160]))
    assert len(asset_store.all()) == 5
    r = client.post("/api/assets/sequence", files=_imgfiles([200, 220]))
    assert r.status_code == 200, r.text
    assert r.json()["frames"] == 2
    keys = sorted(asset_store.all())
    assert keys == ["shot#0000.jpg", "shot#0001.jpg"]  # tail frames gone


def test_sequence_downscaled_to_1024_long_edge(client):
    big = _png(90, size=(2000, 1000))
    r = client.post("/api/assets/sequence", files=[("files", ("big.png", big, "image/png"))])
    assert r.status_code == 200, r.text
    info = {e["name"]: e for e in r.json()["assets"]}["big#"]
    assert info["width"] == 1024 and info["height"] == 512


def _tiny_mp4(n=8):
    import numpy as np
    import imageio.v3 as iio

    frames = np.stack([np.full((16, 16, 3), i * 25, dtype=np.uint8) for i in range(n)])
    buf = io.BytesIO()
    iio.imwrite(buf, frames, extension=".mp4", plugin="FFMPEG", fps=8)
    return buf.getvalue()


def test_video_upload_extracts_frames(client):
    try:
        data = _tiny_mp4(8)
    except Exception as e:
        pytest.skip(f"ffmpeg/imageio unavailable: {e}")
    r = client.post("/api/assets/sequence",
                    files=[("files", ("myclip.mp4", data, "video/mp4"))],
                    data={"frames": "4"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "myclip#"
    assert r.json()["frames"] == 4
    assert sorted(asset_store.all()) == [f"myclip#{i:04d}.jpg" for i in range(4)]


# -- generators: frame selection changes geometry ----------------------------


def test_image_threshold_differs_across_frames():
    from axibridge.registry import get_source

    asset_store.put("clip#0000.png", _png_blob((2, 2, 12, 12)))     # blob top-left
    asset_store.put("clip#0001.png", _png_blob((20, 20, 30, 30)))   # blob bottom-right
    src = get_source("image_threshold")
    at0 = src.generate(src.Params(image="clip#", frame=0.0, detail=1.0))
    at1 = src.generate(src.Params(image="clip#", frame=1.0, detail=1.0))
    pts0 = [p.points for layer in at0.layers for p in layer.paths]
    pts1 = [p.points for layer in at1.layers for p in layer.paths]
    assert pts0 and pts1
    assert pts0 != pts1  # a different frame traces different geometry
