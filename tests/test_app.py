"""API integration tests: the full v2 loop on the simulator, no hardware."""

import time

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:  # context manager runs lifespan
        yield c


def test_state_shape(client):
    st = client.get("/api/state").json()
    assert {b["id"] for b in st["backends"]} == {"native", "simulator", "saxi", "pi_ssh"}
    # sorted: registration order follows first-import order, which can differ
    # between machines (Mac/Pi share this suite) — the roster is the contract
    assert sorted(m["id"] for m in st["modules"]["effects"]) == [
        "bitmap", "coherent_jitter", "continue_strokes", "contract_expand",
        "depth_displace", "eyelets", "fat_tube", "freehand", "hatch_fill",
        "multipass", "parasite_line", "perspective",
    ]
    assert {m["id"] for m in st["modules"]["sources"]} >= {"grid", "flowfield", "lissajous", "polygon"}
    assert st["bed"] == {"width": 300.0, "height": 218.0}
    assert "plot_options" in st["schemas"]
    # capability asymmetry advertised
    native = next(b for b in st["backends"] if b["id"] == "native")
    saxi = next(b for b in st["backends"] if b["id"] == "saxi")
    assert native["capabilities"]["raw_ebb"] and not saxi["capabilities"]["raw_ebb"]
    assert "cornering" not in native["params_schema"]["properties"]


def test_layer_lifecycle_and_resolved(client):
    r = client.post("/api/layers/generate",
                    json={"module": "lissajous", "params": {"size": 100, "points_per_turn": 256}})
    liss_id = r.json()["id"]
    r = client.post("/api/layers/generate",
                    json={"module": "polygon", "params": {"sides": 6, "radius": 25, "filled": True}})
    hex_id = r.json()["id"]
    client.patch(f"/api/layers/{hex_id}", json={
        "occluder": True,
        "transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 30, "f": 30},
    })

    res = client.get("/api/compose/resolved").json()
    by_id = {l["id"]: l for l in res["layers"]}
    assert by_id[liss_id]["stats"]["paths"] > 1, "resolved endpoint must show the occlusion"
    assert by_id[liss_id]["stats"]["est_s"] > 0

    # plan per target uses resolved geometry
    plan_all = client.get("/api/plan?target=all").json()
    plan_one = client.get(f"/api/plan?target={hex_id}").json()
    assert 0 < plan_one["job"]["total_duration"] < plan_all["job"]["total_duration"]

    # reorder kills the mask (occluder below)
    client.post("/api/layers/order", json={"ids": [hex_id, liss_id]})
    res2 = client.get("/api/compose/resolved").json()
    assert {l["id"]: l for l in res2["layers"]}[liss_id]["stats"]["paths"] == 1

    client.delete(f"/api/layers/{hex_id}")
    assert len(client.get("/api/project").json()["layers"]) == 1


def test_master_timeline_scrub_endpoint(client):
    a = client.post("/api/layers/generate",
                    json={"module": "polygon", "params": {"sides": 6, "radius": 15}}).json()
    b = client.post("/api/layers/generate",
                    json={"module": "polygon", "params": {"sides": 6, "radius": 30}}).json()
    client.patch(f"/api/layers/{b['id']}",
                 json={"transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 60, "f": 25}})
    tw = client.post("/api/layers/tween", json={"a": a["id"], "b": b["id"]}).json()

    # follow_master round-trips through the TweenParams model on PUT
    client.put(f"/api/layers/{tw['id']}/tween", json={"follow_master": True})
    proj = client.get("/api/project").json()
    twl = next(l for l in proj["layers"] if l["id"] == tw["id"])
    assert twl["source"]["params"]["follow_master"] is True

    def tween_paths(resp):
        assert resp.status_code == 200
        return next(l for l in resp.json()["layers"] if l["id"] == tw["id"])["paths"]

    p0 = tween_paths(client.get("/api/compose/resolved?t=0.0"))
    p1 = tween_paths(client.get("/api/compose/resolved?t=1.0"))
    assert p0 and p1 and p0 != p1  # scrubbing moves the geometry

    # out-of-range t is rejected by the bounded query param
    assert client.get("/api/compose/resolved?t=1.5").status_code == 422
    assert client.get("/api/compose/resolved?t=-0.1").status_code == 422


def test_animate_layer_endpoint(client):
    layer = client.post("/api/layers/generate",
                         json={"module": "polygon", "params": {"sides": 6, "radius": 15}}).json()

    tw = client.post(f"/api/layers/{layer['id']}/animate").json()
    assert tw["source"]["type"] == "tween"
    assert tw["source"]["params"]["follow_master"] is True
    assert tw["name"] == layer["name"]

    proj = client.get("/api/project").json()
    assert len(proj["layers"]) == 3
    a = next(l for l in proj["layers"] if l["id"] == layer["id"])
    assert not a["visible"] and a["name"].endswith("▸ A")

    # refuses animating a tween (409, RuntimeError)
    r = client.post(f"/api/layers/{tw['id']}/animate")
    assert r.status_code == 409

    # 404 on an unknown layer id
    assert client.post("/api/layers/nope/animate").status_code == 404


def test_export_animation_frames_zip(client):
    import zipfile
    from io import BytesIO

    layer = client.post("/api/layers/generate",
                        json={"module": "polygon", "params": {"sides": 6, "radius": 15}}).json()
    tw = client.post(f"/api/layers/{layer['id']}/animate").json()
    b_id = tw["source"]["params"]["b"]
    client.patch(f"/api/layers/{b_id}", json={
        "transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 60, "f": 40}})

    r = client.get("/api/animation/export.zip?frames=4&t_from=0&t_to=1")
    assert r.status_code == 200
    assert r.headers["content-disposition"].endswith('_frames.zip"')
    z = zipfile.ZipFile(BytesIO(r.content))
    names = z.namelist()
    assert names == [f"frame_{i:04d}.svg" for i in range(4)]
    svgs = [z.read(n).decode() for n in names]
    assert all("<svg" in s for s in svgs)  # each entry parses as an SVG document
    assert svgs[0] != svgs[-1]  # t=0 vs t=1 differ (the follow_master tween moved)

    # bounds: frames outside 2..240 is a 422 (FastAPI query validation)
    assert client.get("/api/animation/export.zip?frames=1").status_code == 422
    assert client.get("/api/animation/export.zip?frames=241").status_code == 422


def test_export_animation_frames_empty_project_400(client):
    assert client.get("/api/animation/export.zip?frames=3").status_code == 400


def test_animation_preview_png(client):
    from io import BytesIO

    from PIL import Image

    client.post("/api/layers/generate",
                json={"module": "polygon", "params": {"sides": 6, "radius": 15}})

    r = client.get("/api/animation/preview.png?t=0.25&width_px=300")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    img = Image.open(BytesIO(r.content))
    assert img.size == (218, 300)

    assert client.put("/api/project", json={"view": "landscape"}).status_code == 200
    r = client.get("/api/animation/preview.png?t=0.25&width_px=300")
    assert r.status_code == 200
    img = Image.open(BytesIO(r.content))
    assert img.size == (300, 218)

    assert client.get("/api/animation/preview.png?t=1.5").status_code == 422
    assert client.get("/api/animation/preview.png?width_px=100").status_code == 422


def test_plot_start_with_master_t_scrubs_geometry(client):
    layer = client.post("/api/layers/generate",
                        json={"module": "polygon", "params": {"sides": 6, "radius": 15}}).json()
    tw = client.post(f"/api/layers/{layer['id']}/animate").json()
    b_id = tw["source"]["params"]["b"]
    client.patch(f"/api/layers/{b_id}", json={
        "transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 60, "f": 40}})

    from axibridge.session import session
    doc0 = session.plot_document("all", master_t=0.0)
    doc1 = session.plot_document("all", master_t=1.0)
    pts0 = [[p.points for p in l.paths] for l in doc0.layers]
    pts1 = [[p.points for p in l.paths] for l in doc1.layers]
    assert pts0 != pts1  # scrubbing the master timeline moves the plotted geometry

    client.put("/api/params/simulator", json={"time_scale": 1000})
    assert client.post("/api/connect", json={}).status_code == 200
    r = client.post("/api/plot/start", json={"target": "all", "master_t": 0.25})
    assert r.status_code == 200
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get("/api/state").json()["machine"]["job_state"] == "idle":
            break
        time.sleep(0.1)
    else:
        pytest.fail("simulator plot did not finish")

    # out-of-range master_t rejected (422, bounded field)
    assert client.post("/api/plot/start", json={"target": "all", "master_t": 1.5}).status_code == 422


def test_plot_single_layer_on_simulator(client):
    r = client.post("/api/layers/generate",
                    json={"module": "polygon", "params": {"sides": 4, "radius": 20}})
    layer_id = r.json()["id"]
    client.put("/api/params/simulator", json={"time_scale": 1000})
    assert client.post("/api/connect", json={}).status_code == 200
    assert client.post("/api/plot/start", json={"target": layer_id}).status_code == 200
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get("/api/state").json()["machine"]["job_state"] == "idle":
            break
        time.sleep(0.1)
    else:
        pytest.fail("simulator plot did not finish")


def test_plot_empty_target_refused(client):
    client.post("/api/connect", json={})
    r = client.post("/api/plot/start", json={"target": "all"})
    assert r.status_code == 409
    assert "nothing to plot" in r.json()["detail"]


def test_jog_limits_and_guide_origin(client):
    client.post("/api/connect", json={})
    r = client.post("/api/machine/jog", json={"dx": 50, "dy": 20})
    assert r.json()["position"] == [50, 20]
    assert client.post("/api/machine/jog", json={"dx": 5000, "dy": 0}).status_code == 409
    # origin = guide corner: current position becomes the guide's (x, y)
    guide = client.get("/api/project").json()["guide"]
    client.post("/api/machine/origin", json={"x": guide["x"], "y": guide["y"]})
    st = client.get("/api/state").json()["machine"]
    assert st["position"] == [pytest.approx(guide["x"]), pytest.approx(guide["y"])]


def test_pens_and_settings_endpoints(client):
    pen = client.post("/api/pens", json={"name": "brush", "barrel_diameter_mm": 14}).json()
    assert pen["id"] in {p["id"] for p in client.get("/api/pens").json()}
    cal = client.post("/api/calibration/holder/compute",
                      json={"diameter_1": 8, "diameter_2": 14, "dx_mm": 0.9, "dy_mm": -0.3}).json()
    assert cal["dx_per_mm"] == pytest.approx(0.15)
    assert cal["dy_per_mm"] == pytest.approx(-0.05)
    # too-close diameters refused
    r = client.post("/api/calibration/holder/compute",
                    json={"diameter_1": 10, "diameter_2": 10.2, "dx_mm": 1, "dy_mm": 0})
    assert r.status_code == 422
    client.delete(f"/api/pens/{pen['id']}")


def test_project_save_load_api(client):
    client.post("/api/layers/generate", json={"module": "polygon", "params": {}})
    client.put("/api/project", json={"name": "api roundtrip"})
    r = client.post("/api/project/save", json={})
    assert r.status_code == 200
    assert "api roundtrip" in client.get("/api/projects").json()
    client.post("/api/project/new")
    assert client.get("/api/project").json()["layers"] == []
    r = client.post("/api/project/load", json={"name": "api roundtrip"})
    assert len(r.json()["layers"]) == 1


def test_raw_refused_on_simulator(client):
    client.post("/api/connect", json={})
    assert client.post("/api/machine/raw", json={"command": "QM"}).status_code == 409


def test_stop_with_return_home(client):
    """Stop ⌂: a stopped job walks the carriage back to (0,0); the flag is
    one-shot and never fires on a normal finish."""
    import time as _t

    r = client.post("/api/layers/generate",
                    json={"module": "polygon", "params": {"sides": 64, "radius": 60}})
    layer_id = r.json()["id"]
    client.put("/api/params/simulator", json={"time_scale": 1})  # slow: stoppable
    assert client.post("/api/connect", json={}).status_code == 200
    assert client.post("/api/plot/start", json={"target": layer_id}).status_code == 200
    deadline = _t.time() + 10
    while _t.time() < deadline:  # wait until the pen is measurably away from home
        st = client.get("/api/state").json()["machine"]
        if st["job_state"] != "idle" and st["position"] != [0, 0]:
            break
        _t.sleep(0.05)
    assert client.post("/api/plot/stop", json={"return_home": True}).status_code == 200
    deadline = _t.time() + 10
    while _t.time() < deadline:
        st = client.get("/api/state").json()["machine"]
        if st["job_state"] == "idle" and st["position"] == [0, 0]:
            break
        _t.sleep(0.05)
    else:
        pytest.fail(f"carriage did not return home: {st}")

    # normal finish must NOT walk home (one-shot flag consumed above)
    client.put("/api/params/simulator", json={"time_scale": 1000})
    client.post("/api/machine/goto", json={"x": 30, "y": 30})
    assert client.post("/api/plot/start", json={"target": layer_id}).status_code == 200
    deadline = _t.time() + 15
    while _t.time() < deadline:
        if client.get("/api/state").json()["machine"]["job_state"] == "idle":
            break
        _t.sleep(0.05)
    st = client.get("/api/state").json()["machine"]
    assert st["position"] != [0, 0], "normal finish should stay where the plot ended"
