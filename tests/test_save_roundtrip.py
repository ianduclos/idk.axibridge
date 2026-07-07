"""Save/load round-trip covering the July-2026 animation state: frame
sequences in assets/, clip-follow + frame-offset layer fields, an animate
group (hidden keyframes + follow tween), and the resolve after reload."""

import io

import pytest

from axibridge.assets import asset_store


def _png_blob(box, size=(32, 32)) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("L", size, 255)
    ImageDraw.Draw(img).rectangle(box, fill=0)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from axibridge.app import create_app

    with TestClient(create_app()) as c:
        yield c


def test_animation_project_round_trips(client):
    # sequence + ladder endpoints + animate group + crop settings
    files = [("files", (f"seq_{i:04d}.png", _png_blob((2, 2, 6 + i * 8, 6 + i * 8)), "image/png"))
             for i in range(4)]
    prefix = client.post("/api/assets/sequence", files=files).json()["name"]

    lay = client.post("/api/layers/generate", json={
        "module": "image_threshold",
        "params": {"image": prefix, "frame": 0.0, "width": 20, "detail": 1.0},
    }).json()
    client.patch(f"/api/layers/{lay['id']}",
                 json={"frame_offset": 1 / 3, "frame_follow": True})
    tw = client.post(f"/api/layers/{lay['id']}/animate").json()
    client.put(f"/api/layers/{tw['id']}/tween",
               json={"sweep": 2, "window_from": 0.1, "window_to": 0.9})
    opts = client.get("/api/project").json()["plot_options"]
    opts.update({"crop": "guide", "crop_margin_mm": 3})
    client.put("/api/project", json={"plot_options": opts})

    before = client.get("/api/compose/resolved").json()["layers"]
    before_scrub = client.get("/api/compose/resolved?t=0.5").json()["layers"]

    r = client.post("/api/project/save", json={"name": "anim roundtrip"})
    assert r.status_code == 200, r.text

    # wipe and reload
    client.post("/api/project/new")
    assert client.get("/api/project").json()["layers"] == []
    r = client.post("/api/project/load", json={"name": "anim roundtrip"})
    assert r.status_code == 200, r.text

    proj = client.get("/api/project").json()
    by_id = {l["id"]: l for l in proj["layers"]}
    assert len(proj["layers"]) == 3
    restored = by_id[lay["id"]]
    assert restored["frame_offset"] == pytest.approx(1 / 3)
    assert restored["frame_follow"] is True
    tw_l = by_id[tw["id"]]
    assert tw_l["source"]["params"]["sweep"] == 2
    assert tw_l["source"]["params"]["follow_master"] is True
    assert proj["plot_options"]["crop"] == "guide"

    # sequence survived as a grouped asset
    seq = [a for a in client.get("/api/assets").json()["assets"] if a["name"] == prefix]
    assert seq and seq[0]["frames"] == 4

    # geometry: identical resolve, and the timeline still works after reload
    after = client.get("/api/compose/resolved").json()["layers"]
    assert [l["paths"] for l in after] == [l["paths"] for l in before]
    after_scrub = client.get("/api/compose/resolved?t=0.5").json()["layers"]
    assert [l["paths"] for l in after_scrub] == [l["paths"] for l in before_scrub]

    # save AGAIN over the same folder (the common "keep working" path)
    r = client.post("/api/project/save", json={})
    assert r.status_code == 200, r.text


def test_save_prunes_zombie_assets(client):
    """A re-imported, shorter sequence must not resurrect its old tail frames
    through save+load — load reads every file in assets/, so save must prune
    what the store no longer holds."""
    files = [("files", (f"z_{i:04d}.png", _png_blob((1, 1, 6, 6)), "image/png"))
             for i in range(4)]
    client.post("/api/assets/sequence", files=files)
    client.post("/api/project/save", json={"name": "zombie"})

    files = [("files", (f"z_{i:04d}.png", _png_blob((1, 1, 6, 6)), "image/png"))
             for i in range(2)]
    assert client.post("/api/assets/sequence", files=files).json()["frames"] == 2
    client.post("/api/project/save", json={})

    client.post("/api/project/new")
    client.post("/api/project/load", json={"name": "zombie"})
    seq = [a for a in client.get("/api/assets").json()["assets"] if a["name"] == "z#"]
    assert seq and seq[0]["frames"] == 2  # the deleted tail frames stayed dead


def test_save_prunes_stale_layer_snapshots(client):
    """Deleted layers' gen-*.svg snapshots are removed on the next save;
    uploaded SVG sources are never touched."""
    from pathlib import Path as FsPath

    a = client.post("/api/layers/generate",
                    json={"module": "polygon", "params": {"sides": 6, "radius": 15}}).json()
    b = client.post("/api/layers/generate",
                    json={"module": "polygon", "params": {"sides": 4, "radius": 10}}).json()
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="20mm" '
           'viewBox="0 0 20 20"><path d="M 1 1 L 19 19" stroke="#000"/></svg>')
    client.post("/api/layers/upload", files={"file": ("art.svg", svg, "image/svg+xml")})
    saved = client.post("/api/project/save", json={"name": "prune"}).json()["saved"]
    sources = FsPath(saved) / "sources"
    assert (sources / f"gen-{b['id']}.svg").exists()

    client.delete(f"/api/layers/{b['id']}")
    client.post("/api/project/save", json={})
    assert (sources / f"gen-{a['id']}.svg").exists()      # live layer kept
    assert not (sources / f"gen-{b['id']}.svg").exists()  # deleted layer pruned
    assert (sources / "art.svg").exists()                 # uploads untouched
