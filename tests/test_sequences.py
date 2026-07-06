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


# -- API: import selection controls (start / every) --------------------------


def _mean_shade(name) -> int:
    rows, w, h = asset_store.grayscale(name)
    return round(sum(v for row in rows for v in row) / (w * h) * 255)


def test_import_start_drops_leading_frames(client):
    r = client.post("/api/assets/sequence",
                    files=_imgfiles([i * 20 for i in range(12)]), data={"start": "4"})
    assert r.status_code == 200, r.text
    assert r.json()["frames"] == 8
    assert len(asset_store.all()) == 8


def test_import_start_and_every_select_source_frames(client):
    # distinct shades so the stored frames identify their source indices
    r = client.post("/api/assets/sequence",
                    files=_imgfiles([i * 20 for i in range(12)]),
                    data={"start": "2", "every": "3"})
    assert r.status_code == 200, r.text
    assert r.json()["frames"] == 4
    means = [_mean_shade(k) for k in sorted(asset_store.all())]
    # source indices 2, 5, 8, 11 -> shades 40, 100, 160, 220
    assert means == pytest.approx([40, 100, 160, 220], abs=3)


def test_import_every_capped_by_frames(client):
    r = client.post("/api/assets/sequence",
                    files=_imgfiles([i * 20 for i in range(12)]),
                    data={"every": "2", "frames": "3"})
    assert r.status_code == 200, r.text
    assert r.json()["frames"] == 3  # [0,2,4,6,8,10][:3]


def test_import_start_leaves_too_few_is_400(client):
    r = client.post("/api/assets/sequence",
                    files=_imgfiles([i * 20 for i in range(12)]), data={"start": "11"})
    assert r.status_code == 400
    assert "fewer than 2" in r.json()["detail"]


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


def test_video_upload_with_start_and_frames(client):
    try:
        data = _tiny_mp4(8)
    except Exception as e:
        pytest.skip(f"ffmpeg/imageio unavailable: {e}")
    r = client.post("/api/assets/sequence",
                    files=[("files", ("clip.mp4", data, "video/mp4"))],
                    data={"start": "2", "frames": "3"})  # even spread of 3 after dropping 2
    assert r.status_code == 200, r.text
    assert r.json()["frames"] == 3
    assert sorted(asset_store.all()) == [f"clip#{i:04d}.jpg" for i in range(3)]


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


# -- animate: auto-frame a sequence-driven layer -----------------------------


def test_animate_sequence_layer_sets_frame_b_to_one():
    from axibridge.session import session

    for i in range(3):
        asset_store.put(f"clip#{i:04d}.png", _png_blob((2 + i, 2 + i, 12 + i, 12 + i)))
    layer = session.add_generated_layer(
        "image_threshold", {"image": "clip#", "frame": 0.0, "detail": 1.0})
    tw = session.animate_layer(layer.id)
    a = session.project.layer(layer.id)
    b = session.project.layer(tw.source.params["b"])
    assert b.source.params["frame"] == 1.0     # B jumps to the last frame
    assert a.source.params["frame"] == 0.0     # A holds what the user saw


def test_animate_non_sequence_layer_adds_no_frame_key():
    from axibridge.session import session

    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    tw = session.animate_layer(layer.id)
    b = session.project.layer(tw.source.params["b"])
    assert "frame" not in (b.source.params or {})


# -- frame offset (per-layer time-shift of a clip) ---------------------------


def _seq3():
    """A 3-frame clip whose frames trace visibly different geometry."""
    asset_store.put("clip#0000.png", _png_blob((2, 2, 12, 12)))    # blob top-left
    asset_store.put("clip#0001.png", _png_blob((10, 10, 20, 20)))  # blob middle
    asset_store.put("clip#0002.png", _png_blob((20, 20, 30, 30)))  # blob bottom-right


def _pts(paths):
    return [p.points for p in paths]


def test_effective_gen_params_shifts_and_clamps():
    from axibridge.session import Session

    _seq3()
    from axibridge.session import session

    layer = session.add_generated_layer(
        "image_threshold", {"image": "clip#", "frame": 0.8, "detail": 1.0})
    stored = layer.source.params
    layer.frame_offset = 0.5
    eff = Session._effective_gen_params(layer)
    assert eff["frame"] == 1.0            # 0.8 + 0.5 -> clamped to 1.0
    assert eff is not stored              # a copy, never the stored dict
    assert stored["frame"] == 0.8         # stored params untouched

    layer.frame_offset = -0.5
    assert Session._effective_gen_params(layer)["frame"] == pytest.approx(0.3)

    # negative past the floor clamps to 0
    layer.source.params = {"image": "clip#", "frame": 0.2, "detail": 1.0}
    layer.frame_offset = -0.5
    assert Session._effective_gen_params(layer)["frame"] == 0.0


def test_effective_gen_params_leaves_non_frame_generators_alone():
    from axibridge.session import Session, session

    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    layer.frame_offset = 0.5
    eff = Session._effective_gen_params(layer)
    assert "frame" not in eff
    assert eff == {"sides": 6, "radius": 15}


def test_patch_frame_offset_resamples_clip_and_is_one_undo():
    from axibridge.session import session

    _seq3()
    layer = session.add_generated_layer(
        "image_threshold", {"image": "clip#", "frame": 0.0, "detail": 1.0})
    at0 = _pts(session.resolved()[layer.id])

    session._history.clear()
    hist_before = len(session._history)
    session.update_layer(layer.id, {"frame_offset": 1.0})  # jump to the last frame

    assert len(session._history) == hist_before + 1        # exactly one undo step
    shifted = _pts(session.resolved()[layer.id])
    assert shifted != at0                                  # a different frame traced
    # stored params keep the user's RAW frame — the offset applies at gen time
    assert session.project.layer(layer.id).source.params["frame"] == 0.0
    assert session.project.layer(layer.id).frame_offset == 1.0

    assert session.undo()                                  # restores geometry AND field
    assert _pts(session.resolved()[layer.id]) == at0
    assert session.project.layer(layer.id).frame_offset == 0.0


def test_patch_frame_offset_on_non_frame_generator_only_stores_field():
    from axibridge.session import session

    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    before = _pts(session.resolved()[layer.id])
    session.update_layer(layer.id, {"frame_offset": 0.5})
    assert session.project.layer(layer.id).frame_offset == 0.5
    assert _pts(session.resolved()[layer.id]) == before   # geometry unchanged


def test_tween_lerps_frame_offset_to_play_a_clip():
    from axibridge.session import session

    _seq3()
    # identical generator params on both sides — ONLY the offsets differ
    a = session.add_generated_layer(
        "image_threshold", {"image": "clip#", "frame": 0.0, "detail": 1.0})
    b = session.add_generated_layer(
        "image_threshold", {"image": "clip#", "frame": 0.0, "detail": 1.0})
    session.update_layer(b.id, {"frame_offset": 1.0})
    tw = session.create_tween_layer(a.id, b.id)

    session.set_tween_params(tw.id, {"t": 0.0})
    at_t0 = _pts(session.resolved()[tw.id])
    session.set_tween_params(tw.id, {"t": 1.0})
    at_t1 = _pts(session.resolved()[tw.id])
    assert at_t0 != at_t1                     # the clip plays purely via offsets

    # endpoint fidelity: t=0 == layer A's own output (offset 0, frame 0)
    session.set_tween_params(tw.id, {"t": 0.0})
    r = session.resolved()
    assert _pts(r[tw.id]) == _pts(r[a.id])


def test_canvaslayer_without_frame_offset_defaults_zero():
    from axibridge.compose import CanvasLayer

    layer = CanvasLayer(**{
        "name": "old", "source": {"type": "generator", "generator": "polygon",
                                   "params": {"sides": 5}}})
    assert layer.frame_offset == 0.0


def test_asset_endpoint_serves_the_requested_frame(client):
    """The canvas ghost overlay must track the frame the generator samples —
    a prefix without ?frame= serves frame 0 (legacy), ?frame= picks like
    resolve_frame, and plain assets ignore the query."""
    client.post("/api/assets/sequence", files=_imgfiles([0, 120, 240]))
    first = asset_store.get("shot#0000.jpg")
    last = asset_store.get("shot#0002.jpg")
    assert first != last

    assert client.get("/api/assets/shot%23").content == first          # legacy default
    assert client.get("/api/assets/shot%23?frame=0").content == first
    assert client.get("/api/assets/shot%23?frame=1").content == last
    assert client.get("/api/assets/shot%23?frame=0.5").content == asset_store.get("shot#0001.jpg")
    assert client.get("/api/assets/shot%23?frame=2").status_code == 422  # bounded

    plain = client.post(
        "/api/assets", files={"file": ("still.png", _png(90), "image/png")})
    assert plain.status_code == 200
    name = plain.json()["name"]
    assert (client.get(f"/api/assets/{name}?frame=1").content
            == client.get(f"/api/assets/{name}").content)


def test_frame_offset_patch_never_discards_a_bake():
    """PATCHing frame_offset on a BAKED layer must not regenerate — the baked
    geometry holds consolidated transform/effects that raw generator output
    would silently discard. The offset is stored and applies on an explicit
    regenerate (which un-bakes on purpose)."""
    from axibridge.session import session

    for i in range(3):
        asset_store.put(f"bk#{i:04d}.png", _png_blob((2 + i, 2 + i, 12 + i, 12 + i)))
    layer = session.add_generated_layer(
        "image_threshold", {"image": "bk#", "frame": 0.0, "detail": 1.0})
    session.update_layer(layer.id, {"transform": {
        "a": 1, "b": 0, "c": 0, "d": 1, "e": 40, "f": 0}})
    session.consolidate_effects(layer.id)
    baked_geo = session.source_geometry[layer.id]
    session.update_layer(layer.id, {"frame_offset": 1.0})
    assert session.source_geometry[layer.id] is baked_geo  # untouched
    assert session.project.layer(layer.id).frame_offset == 1.0  # stored


# -- ladder scrub: the timeline moves a SWEPT (sweep > 1) tween ---------------


def _identical_thirds(paths) -> bool:
    """True iff ``paths`` splits into three byte-identical stamp blocks (i.e.
    every stamp sampled the same frame/params — a fully saturated ladder)."""
    k, r = divmod(len(paths), 3)
    if r or k == 0:
        return False
    a, b, c = _pts(paths[:k]), _pts(paths[k:2 * k]), _pts(paths[2 * k:])
    return a == b == c


def _ladder():
    """A 3-frame clip driven as a stamped, timeline-following morph: layer A at
    frame 0, an offset-equivalent B (frame_offset 1.0 = last frame), and a
    follow-master tween that stamps sweep=3 across the first half of the morph."""
    from axibridge.session import session

    _seq3()
    a = session.add_generated_layer(
        "image_threshold", {"image": "clip#", "frame": 0.0, "detail": 1.0})
    b = session.duplicate_layer(a.id)
    session.update_layer(b.id, {"frame_offset": 1.0})  # B plays the last frame
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {
        "sweep": 3, "sweep_from": 0.0, "sweep_to": 0.5, "follow_master": True})
    return a, b, tw


def test_ladder_scrub_advances_swept_stamps():
    from axibridge.session import session

    a, b, tw = _ladder()
    g0 = session.resolved(master_t=0.0)[tw.id]
    g5 = session.resolved(master_t=0.5)[tw.id]
    g1 = session.resolved(master_t=1.0)[tw.id]

    # at master_t=0 the stamps sit at their static positions and sample distinct
    # frames — the ladder is NOT three identical blocks
    assert not _identical_thirds(g0)
    # scrubbing pushes every stamp forward along the morph: the geometry moves
    assert _pts(g0) != _pts(g5)
    assert _pts(g5) != _pts(g1)
    # at master_t=1 every stamp saturates at the B end -> three identical blocks
    assert _identical_thirds(g1)


def test_ladder_scrub_regression_sweep_one_matches_own_t():
    """A sweep==1 follow tween scrubbed to master_t=x must equal the same tween
    resolving at its own t=x (no follow) — the pre-refactor single-tween path."""
    from axibridge.session import session

    _seq3()
    a = session.add_generated_layer(
        "image_threshold", {"image": "clip#", "frame": 0.0, "detail": 1.0})
    b = session.duplicate_layer(a.id)
    session.update_layer(b.id, {"frame_offset": 1.0})
    tw = session.create_tween_layer(a.id, b.id)

    for x in (0.0, 0.3, 0.7, 1.0):
        session.set_tween_params(tw.id, {"t": x, "follow_master": True, "sweep": 1})
        followed = _pts(session.resolved(master_t=x)[tw.id])
        session.set_tween_params(tw.id, {"t": x, "follow_master": False, "sweep": 1})
        own = _pts(session.resolved()[tw.id])
        assert followed == own


# -- import progress over SSE ------------------------------------------------


def _capture_sink(monkeypatch):
    calls: list[tuple[float, str]] = []

    def fake_factory():
        def sink(frac: float, msg: str = "") -> None:
            calls.append((frac, msg))
        return sink

    monkeypatch.setattr("axibridge.api._gen_progress_sink", fake_factory)
    return calls


def test_import_progress_multi_image_monotonic(client, monkeypatch):
    calls = _capture_sink(monkeypatch)
    r = client.post("/api/assets/sequence", files=_imgfiles([0, 40, 80, 120, 160, 200]))
    assert r.status_code == 200, r.text
    fracs = [f for f, _ in calls]
    assert fracs == sorted(fracs)          # monotonically nondecreasing
    assert fracs[-1] == 1.0                # finishes at 1.0
    assert len(calls) >= 6                 # at least one per imported frame


def test_import_progress_video_reports_phases(client, monkeypatch):
    try:
        data = _tiny_mp4(8)
    except Exception as e:
        pytest.skip(f"ffmpeg/imageio unavailable: {e}")
    calls = _capture_sink(monkeypatch)
    r = client.post("/api/assets/sequence",
                    files=[("files", ("clip.mp4", data, "video/mp4"))],
                    data={"frames": "4"})
    assert r.status_code == 200, r.text
    msgs = [m for _, m in calls]
    assert any("decoding" in m for m in msgs)   # decode phase reported
    assert any("encoding" in m for m in msgs)   # encode phase reported
    fracs = [f for f, _ in calls]
    assert fracs == sorted(fracs)
    assert fracs[-1] == 1.0
