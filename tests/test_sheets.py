"""Grid sheets — transient plot-time assembly of many timeline frames per
physical sheet (1/2/4/16 per page). The editable escape hatch (capture a sheet
to the tray, then insert as layers) is covered in test_staging.py; here we
exercise the non-mutating ``sheet_document`` / ``_grid_place`` path and its API
surface."""

import time

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.session import session
from axibridge.stores import Pen, pen_library, settings_store


def _two_pen_project():
    """Two polygon layers on distinct pens, positioned apart. Static (no tween)
    so master_t leaves every frame identical — good for placement/grouping."""
    a = session.add_generated_layer("polygon", {"sides": 5, "radius": 12})
    b = session.add_generated_layer("polygon", {"sides": 3, "radius": 8})
    session.update_layer(b.id, {"transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 40, "f": 20}})
    pa = pen_library.upsert(Pen(name="pen A", color="#ff0000"))
    pb = pen_library.upsert(Pen(name="pen B", color="#0000ff"))
    session.update_layer(a.id, {"pen_id": pa.id})
    session.update_layer(b.id, {"pen_id": pb.id})
    return a, b, pa, pb


def _growing_follow():
    """A follow-master tween whose radius grows 10→40 over the timeline, with
    both keyframes hidden — so only the morphing tween is visible and the
    combined bbox grows monotonically with master_t."""
    a = session.add_generated_layer("polygon", {"sides": 6, "radius": 10})
    b = session.add_generated_layer("polygon", {"sides": 6, "radius": 40})
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 0.5, "follow_master": True})
    session.update_layer(a.id, {"visible": False})
    session.update_layer(b.id, {"visible": False})
    return a, b, tw


# -- placement core -----------------------------------------------------------


def test_grid_place_cells_within_rect_and_per_layer():
    _two_pen_project()
    placed = session._grid_place([0.0, 0.0, 0.0, 0.0], cols=2, rows=2, margin_mm=5.0)
    assert len(placed) == 4
    g = session.project.guide
    cw, ch = g.width / 2, g.height / 2
    for i, frame in enumerate(placed):
        assert len(frame) == 2  # per-layer geometry kept (both pens present)
        row, col = divmod(i, 2)
        x0, y0 = g.x + col * cw, g.y + row * ch
        for paths in frame.values():
            for p in paths:
                for x, y in p.points:
                    assert x0 <= x <= x0 + cw
                    assert y0 <= y <= y0 + ch


def test_grid_place_shared_scale_is_global_not_per_frame():
    _growing_follow()
    all_ts = [i / 5 for i in range(6)]
    t = all_ts[1]

    def size(frame):
        xs = [x for paths in frame.values() for p in paths for x, _ in p.points]
        ys = [y for paths in frame.values() for p in paths for _, y in p.points]
        return max(xs) - min(xs), max(ys) - min(ys)

    glob = size(session._grid_place([t], 2, 2, 5.0, master_scale_ts=all_ts)[0])
    local = size(session._grid_place([t], 2, 2, 5.0, master_scale_ts=[t])[0])
    # the global reference includes the largest (t=1) frame, so the shared
    # scale is smaller: the same frame renders smaller under the global scale.
    assert glob[0] < local[0]
    assert glob[1] < local[1]


# -- sheet documents: paging, pen grouping, offsets ---------------------------


def test_sheet_pages_and_pen_grouping():
    a, b, pa, pb = _two_pen_project()
    assert session.sheet_pages(6, 2, 2) == 2

    doc0 = session.sheet_document(2, 2, 6, 0.0, 1.0, 5.0, page=0, pen_id=None)
    by_name = {l.name: l for l in doc0.layers}
    assert set(by_name) == {"pen A", "pen B"}  # one doc layer per pen used
    assert by_name["pen A"].color == "#ff0000"  # pen color survives
    assert by_name["pen B"].color == "#0000ff"

    # a single pen filters to one group (one plot pass)
    only_a = session.sheet_document(2, 2, 6, 0.0, 1.0, 5.0, page=0, pen_id=pa.id)
    assert [l.name for l in only_a.layers] == ["pen A"]

    # page out of range → IndexError (API maps to 400)
    with pytest.raises(IndexError):
        session.sheet_document(2, 2, 6, 0.0, 1.0, 5.0, page=2, pen_id=None)


def test_sheet_no_pen_group():
    session.add_generated_layer("polygon", {"sides": 5, "radius": 12})  # no pen
    doc = session.sheet_document(2, 1, 4, 0.0, 1.0, 5.0, page=0, pen_id=None)
    assert [l.name for l in doc.layers] == ["no pen"]
    # the no-pen group is addressable as a single pass via pen_id=""
    only = session.sheet_document(2, 1, 4, 0.0, 1.0, 5.0, page=0, pen_id="")
    assert [l.name for l in only.layers] == ["no pen"]


def test_sheet_pen_offset_is_raw_not_scaled():
    a, b, pa, pb = _two_pen_project()
    settings_store.update({"holder_calibration": {"dx_per_mm": 0.0, "dy_per_mm": 0.0}})
    base = session.sheet_document(2, 2, 4, 0.0, 1.0, 5.0, page=0, pen_id=pa.id)
    settings_store.update({"holder_calibration": {"dx_per_mm": 0.1, "dy_per_mm": -0.05}})
    off = session.sheet_document(2, 2, 4, 0.0, 1.0, 5.0, page=0, pen_id=pa.id)
    # pen A barrel 10mm → nib offset (1.0, -0.5); the pass is translated by its
    # negative, and that raw shift is NOT scaled by the cell factor.
    bpts = [pt for l in base.layers for p in l.paths for pt in p.points]
    opts = [pt for l in off.layers for p in l.paths for pt in p.points]
    assert len(bpts) == len(opts) and bpts
    for (bx, by), (ox, oy) in zip(bpts, opts):
        assert ox == pytest.approx(bx - 1.0)
        assert oy == pytest.approx(by + 0.5)


# -- API surface --------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def _sheet_spec(**over):
    spec = {"cols": 2, "rows": 2, "frames": 6, "t_from": 0.0, "t_to": 1.0,
            "margin_mm": 5.0, "page": 0}
    spec.update(over)
    return spec


def test_sheet_info_reports_sheets_and_passes(client):
    client.post("/api/layers/generate",
                json={"module": "polygon", "params": {"sides": 5, "radius": 12}})
    pa = client.post("/api/pens", json={"name": "pen A", "color": "#ff0000"}).json()
    layers = client.get("/api/project").json()["layers"]
    client.patch(f"/api/layers/{layers[0]['id']}", json={"pen_id": pa["id"]})

    info = client.get("/api/animation/sheet_info",
                      params={"frames": 6, "cols": 2, "rows": 2}).json()
    assert info["sheets"] == 2
    assert info["cells"] == 4  # page 0 full
    assert [p["pen_id"] for p in info["passes"]] == [pa["id"]]
    assert info["passes"][0]["name"] == "pen A"


def test_plan_with_sheet_shrinks_cells_below_native(client):
    import json

    client.post("/api/layers/generate",
                json={"module": "polygon", "params": {"sides": 6, "radius": 40}})
    native = client.get("/api/plan").json()["job"]["pen_down_distance"]
    # a 4×4 grid puts 6 frames in cells smaller than the native geometry, so the
    # whole page draws LESS than six native-size copies would.
    spec = _sheet_spec(cols=4, rows=4)
    sheet = client.get("/api/plan", params={"sheet": json.dumps(spec)})
    assert sheet.status_code == 200
    page = sheet.json()["job"]["pen_down_distance"]
    assert 0 < page < 6 * native  # every cell scaled below native size


def test_preview_sheet_returns_page_geometry(client):
    import json

    client.post("/api/layers/generate",
                json={"module": "polygon", "params": {"sides": 6, "radius": 20}})
    pa = client.post("/api/pens", json={"name": "pen A", "color": "#ff0000",
                                        "line_diameter_mm": 0.7, "opacity": 0.5}).json()
    layers = client.get("/api/project").json()["layers"]
    client.patch(f"/api/layers/{layers[0]['id']}", json={"pen_id": pa["id"]})

    r = client.get("/api/preview/sheet", params={"sheet": json.dumps(_sheet_spec())})
    assert r.status_code == 200
    body = r.json()
    assert body["layers"], "sheet preview should carry the page's geometry"
    lay = body["layers"][0]
    # display-only shape the canvas reads: visible + ink-sim fields, no stats
    assert lay["visible"] is True
    assert lay["color"] == "#ff0000"
    assert lay["line_diameter_mm"] == 0.7 and lay["opacity"] == 0.5
    assert "stats" not in lay
    assert lay["paths"] and lay["paths"][0]["points"]
    # geometry lands inside the bed (grid cells, not native placement)
    for p in lay["paths"]:
        for x, y in p["points"]:
            assert 0 <= x <= body["width"] and 0 <= y <= body["height"]


def test_preview_sheet_requires_exactly_one_source(client):
    import json

    client.post("/api/layers/generate",
                json={"module": "polygon", "params": {"sides": 6, "radius": 20}})
    # neither → 400
    assert client.get("/api/preview/sheet").status_code == 400
    # both → 400
    both = client.get("/api/preview/sheet", params={
        "sheet": json.dumps(_sheet_spec()),
        "staged": json.dumps({"group_id": "x", "sheet_id": "y"})})
    assert both.status_code == 400
    # out-of-range page → 400
    bad = client.get("/api/preview/sheet", params={"sheet": json.dumps(_sheet_spec(page=9))})
    assert bad.status_code == 400


def test_plot_start_with_sheet_completes_on_simulator(client):
    client.post("/api/layers/generate",
                json={"module": "polygon", "params": {"sides": 6, "radius": 20}})
    client.put("/api/params/simulator", json={"time_scale": 1000})
    assert client.post("/api/connect", json={}).status_code == 200
    r = client.post("/api/plot/start", json={"sheet": _sheet_spec(page=0, pen_id="")})
    assert r.status_code == 200
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get("/api/state").json()["machine"]["job_state"] == "idle":
            break
        time.sleep(0.1)
    else:
        pytest.fail("simulator sheet plot did not finish")
    # page out of range → 400
    bad = client.post("/api/plot/start", json={"sheet": _sheet_spec(page=9)})
    assert bad.status_code == 400


def test_export_zip_per_sheet(client):
    import io
    import zipfile

    client.post("/api/layers/generate",
                json={"module": "polygon", "params": {"sides": 6, "radius": 20}})
    r = client.get("/api/animation/export.zip",
                   params={"frames": 6, "cols": 2, "rows": 2, "margin_mm": 5.0})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = sorted(zf.namelist())
    assert names == ["sheet_00.svg", "sheet_01.svg"]  # 6 frames / 4 per page
    for n in names:
        assert b"<svg" in zf.read(n)
