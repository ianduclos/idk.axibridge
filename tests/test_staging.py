"""Capture-based staging tray and batch interpolation."""

import json
import time
import zipfile
from io import BytesIO
from pathlib import Path as FsPath

import pytest
from fastapi.testclient import TestClient

from axibridge import project_io
from axibridge.app import create_app
from axibridge.model import PathDocument
from axibridge.session import session


def _doc_signature(doc: PathDocument):
    return [
        [
            [(round(x, 4), round(y, 4)) for x, y in path.points]
            for path in layer.paths
        ]
        for layer in doc.layers
    ]


def _paths_signature(paths):
    return [
        [(round(x, 4), round(y, 4)) for x, y in path.points]
        for path in paths
    ]


def _doc_width(doc: PathDocument) -> float:
    bounds = doc.bounds()
    assert bounds is not None
    return bounds[2] - bounds[0]


def test_capture_round_trips_and_stays_frozen_after_edits(tmp_path):
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 12})
    group = session.capture_to_staging(kind="plot", name="frozen plot")
    sheet = group.sheets[0]
    before = _doc_signature(session.staged_document(group.id, sheet.id))

    session.regenerate_layer(layer.id, {"sides": 6, "radius": 35})
    assert _doc_signature(session.staged_document(group.id, sheet.id)) == before
    assert _doc_signature(session.plot_document("all")) != before

    target = FsPath(tmp_path) / "staged"
    project_io.save_project(
        session.project,
        session.source_geometry,
        session.svg_files,
        target,
        staging_documents=session.staging_documents,
        history=session.history_for_save(),
    )
    project, _, _, _, staging_documents, _ = project_io.load_project(target)

    assert project.staging[0].name == "frozen plot"
    assert project.staging[0].snapshot is not None
    loaded_sheet = project.staging[0].sheets[0]
    assert loaded_sheet.file in staging_documents
    assert _doc_signature(staging_documents[loaded_sheet.file]) == before


def test_compatible_captures_generate_interpolated_batch_from_snapshots():
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 10})
    small = session.capture_to_staging(kind="plot", name="small")
    session.regenerate_layer(layer.id, {"sides": 6, "radius": 30})
    large = session.capture_to_staging(kind="plot", name="large")

    batch = session.interpolate_captures(small.id, large.id, steps=3, name="radius batch")

    assert batch.kind == "batch"
    assert batch.format["source_kind"] == "plot"
    assert batch.source_capture_ids == [small.id, large.id]
    assert len(batch.sheets) == 3

    w0 = _doc_width(session.staged_document(batch.id, batch.sheets[0].id))
    w1 = _doc_width(session.staged_document(batch.id, batch.sheets[1].id))
    w2 = _doc_width(session.staged_document(batch.id, batch.sheets[2].id))
    assert w0 < w1 < w2


def test_incompatible_capture_formats_are_rejected():
    session.add_generated_layer("polygon", {"sides": 5, "radius": 15})
    plot = session.capture_to_staging(kind="plot", name="plot")
    frame = session.capture_to_staging(kind="frame", name="frame", master_t=0.0)

    with pytest.raises(ValueError, match=r"kinds do not match \(plot vs frame\)"):
        session.interpolate_captures(plot.id, frame.id, steps=3)


def test_interpolate_allows_presentation_only_format_differences():
    """margin_mm / framing / marks are presentation, not shape — a pair that
    differs only there interpolates, and the batch inherits A's values."""
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 10})
    a = session.capture_to_staging(kind="sheet", name="A", cols=2, rows=2, frames=6,
                                   margin_mm=5.0, framing="fixed")
    session.regenerate_layer(layer.id, {"sides": 6, "radius": 30})
    b = session.capture_to_staging(kind="sheet", name="B", cols=2, rows=2, frames=6,
                                   margin_mm=12.0, framing="center", marks=True)

    batch = session.interpolate_captures(a.id, b.id, steps=3)

    assert batch.name == "A ⇄ B · 3 steps"  # default name carries the step count
    assert batch.format["margin_mm"] == 5.0
    assert batch.format["framing"] == "fixed"
    assert len(batch.sheets) == 6  # 3 steps × 2 pages (6 frames at 2×2)


def test_interpolate_refuses_differing_sheet_shape():
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 10})
    a = session.capture_to_staging(kind="sheet", name="A", cols=2, rows=2, frames=6)
    session.regenerate_layer(layer.id, {"sides": 6, "radius": 30})
    c = session.capture_to_staging(kind="sheet", name="C", cols=2, rows=2, frames=8)

    with pytest.raises(ValueError, match=r"frames differs \(6 vs 8\)"):
        session.interpolate_captures(a.id, c.id, steps=3)


def test_relayout_sheet_capture_new_grid_original_untouched():
    session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    g = session.capture_to_staging(kind="sheet", name="grid", cols=2, rows=2, frames=6)
    assert len(g.sheets) == 2  # 6 frames at 2×2 → 2 pages
    orig_sig = _doc_signature(session.staged_document(g.id, g.sheets[0].id))

    new = session.relayout_capture(g.id, 1, 1, margin_mm=2.0)

    assert new.id != g.id
    assert new.name == "grid · re-laid 1×1"
    assert new.kind == "sheet" and new.snapshot is not None
    assert new.format["cols"] == 1 and new.format["rows"] == 1
    assert new.format["pages"] == 6 and len(new.sheets) == 6  # one frame per page
    assert new.format["margin_mm"] == 2.0
    for sheet in new.sheets:
        assert session.staged_document(new.id, sheet.id).stats().paths > 0
    # original group intact — same sheets, same frozen geometry
    assert len(session._find_capture(g.id).sheets) == 2
    assert _doc_signature(session.staged_document(g.id, g.sheets[0].id)) == orig_sig


def test_relayout_batch_reruns_from_sources():
    # two layers, the second translated between A and B — relative arrangement
    # survives the sheet cells' shared-scale fitting, so the A→B stepping stays
    # visible in the re-laid geometry (a lone shape would be normalised away).
    session.add_generated_layer("polygon", {"sides": 6, "radius": 10})
    mover = session.add_generated_layer("polygon", {"sides": 3, "radius": 8})
    a = session.capture_to_staging(kind="sheet", name="A", cols=2, rows=2, frames=6)
    session.update_layer(mover.id, {"transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 60, "f": 0}})
    b = session.capture_to_staging(kind="sheet", name="B", cols=2, rows=2, frames=6)
    batch = session.interpolate_captures(a.id, b.id, steps=3)
    assert len(batch.sheets) == 6

    re = session.relayout_capture(batch.id, 1, 1)

    assert re.kind == "batch" and re.snapshot is None
    assert re.format["variants"] == 3 and re.format["cols"] == 1
    assert re.source_capture_ids == [a.id, b.id]
    assert len(re.sheets) == 18  # 3 steps × 6 pages
    for sheet in re.sheets:
        assert session.staged_document(re.id, sheet.id).stats().paths > 0
    # still steps A→B: step 1's first page differs from step 3's
    assert (_doc_signature(session.staged_document(re.id, re.sheets[0].id))
            != _doc_signature(session.staged_document(re.id, re.sheets[12].id)))


def test_relayout_batch_with_deleted_source_refused():
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 10})
    a = session.capture_to_staging(kind="sheet", name="A", cols=2, rows=2, frames=6)
    session.regenerate_layer(layer.id, {"sides": 6, "radius": 30})
    b = session.capture_to_staging(kind="sheet", name="B", cols=2, rows=2, frames=6)
    batch = session.interpolate_captures(a.id, b.id, steps=3)
    session.delete_capture_group(a.id)

    with pytest.raises(RuntimeError, match="source captures no longer available"):
        session.relayout_capture(batch.id, 1, 1)


def test_relayout_refuses_non_grid_kinds():
    session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    plot = session.capture_to_staging(kind="plot", name="plot")

    with pytest.raises(ValueError, match="grid-sheet captures only"):
        session.relayout_capture(plot.id, 2, 2)


def test_insert_staged_sheet_as_layers_and_undo():
    layer = session.add_generated_layer("polygon", {"sides": 5, "radius": 15})
    group = session.capture_to_staging(kind="plot", name="editable escape hatch")
    sheet = group.sheets[0]
    frozen = _doc_signature(session.staged_document(group.id, sheet.id))
    session.clear_history()

    created = session.insert_staged_sheet(group.id, sheet.id)

    assert created
    assert not session.project.layer(layer.id).visible
    assert all(l.source.type == "baked" for l in created)
    assert _paths_signature(session.source_geometry[created[0].id]) == frozen[0]

    assert session.undo()
    assert session.project.layer(layer.id).visible
    assert all(l.id != created[0].id for l in session.project.layers)
    assert _doc_signature(session.staged_document(group.id, sheet.id)) == frozen


def test_staging_edits_and_persisted_undo_survive_save_load(tmp_path):
    session.add_generated_layer("polygon", {"sides": 6, "radius": 12})
    group = session.capture_to_staging(kind="plot", name="original")
    for i in range(5):
        session.rename_capture_group(group.id, f"rename {i}")

    target = FsPath(tmp_path) / "undo-stage"
    project_io.save_project(
        session.project,
        session.source_geometry,
        session.svg_files,
        target,
        staging_documents=session.staging_documents,
        history=session.history_for_save(),
    )
    assert len(list((target / "history").glob("undo_*.json"))) == 4

    project, geometry, svg_files, _, staging_documents, history = project_io.load_project(target)
    session.project = project
    session.source_geometry = geometry
    session.svg_files = svg_files
    session.staging_documents = staging_documents
    session.restore_history(history)

    assert session.project.staging[0].name == "rename 4"
    assert session.undo()
    assert session.project.staging[0].name == "rename 3"
    assert session.staged_document(group.id, session.project.staging[0].sheets[0].id).stats().paths > 0

    undos = 1
    while session.undo():
        undos += 1
    assert undos == 4


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def test_preview_staged_returns_sheet_geometry(client):
    client.post("/api/layers/generate",
                json={"module": "polygon", "params": {"sides": 6, "radius": 15}})
    group = client.post("/api/staging/capture",
                        json={"kind": "plot", "name": "api plot"}).json()["group"]
    sheet = group["sheets"][0]

    r = client.get("/api/preview/sheet", params={
        "staged": json.dumps({"group_id": group["id"], "sheet_id": sheet["id"]})})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["layers"] and body["layers"][0]["paths"]
    lay = body["layers"][0]
    assert lay["visible"] is True and "stats" not in lay
    # same geometry the staged document (and plotter) would use
    doc_sig = _doc_signature(session.staged_document(group["id"], sheet["id"]))
    preview_sig = [
        [[(round(x, 4), round(y, 4)) for x, y in p["points"]] for p in layer["paths"]]
        for layer in body["layers"]
    ]
    assert preview_sig == doc_sig

    # unknown group → 400
    bad = client.get("/api/preview/sheet", params={
        "staged": json.dumps({"group_id": "nope", "sheet_id": "nope"})})
    assert bad.status_code == 400


def test_relayout_api_endpoint(client):
    client.post("/api/layers/generate",
                json={"module": "polygon", "params": {"sides": 6, "radius": 15}})
    cap = client.post("/api/staging/capture",
                      json={"kind": "sheet", "name": "grid",
                            "cols": 2, "rows": 2, "frames": 6}).json()["group"]

    r = client.post(f"/api/staging/groups/{cap['id']}/relayout",
                    json={"cols": 1, "rows": 1})
    assert r.status_code == 200, r.text
    g = r.json()["group"]
    assert g["format"]["pages"] == 6 and len(g["sheets"]) == 6
    assert "snapshot" not in g  # heavy source state never rides the wire

    assert client.post("/api/staging/groups/nope/relayout",
                       json={"cols": 1, "rows": 1}).status_code == 404
    assert client.post(f"/api/staging/groups/{cap['id']}/relayout",
                       json={"cols": 0, "rows": 1}).status_code == 422  # pydantic bounds


def test_staging_api_plan_export_and_plot(client):
    client.post("/api/layers/generate",
                json={"module": "polygon", "params": {"sides": 6, "radius": 15}})
    capture = client.post("/api/staging/capture", json={"kind": "plot", "name": "api plot"})
    assert capture.status_code == 200, capture.text
    group = capture.json()["group"]
    sheet = group["sheets"][0]
    assert "snapshot" not in group

    staged = {"group_id": group["id"], "sheet_id": sheet["id"]}
    plan = client.get("/api/plan", params={"staged": json.dumps(staged)})
    assert plan.status_code == 200, plan.text
    assert plan.json()["job"]["pen_down_distance"] > 0

    export = client.get("/api/staging/export.zip", params={"group_id": group["id"]})
    assert export.status_code == 200, export.text
    zf = zipfile.ZipFile(BytesIO(export.content))
    assert zf.namelist() == ["api plot_sheet_00.svg"]
    assert b"<svg" in zf.read(zf.namelist()[0])

    client.put("/api/params/simulator", json={"time_scale": 1000})
    assert client.post("/api/connect", json={}).status_code == 200
    r = client.post("/api/plot/start", json={"staged": {**staged, "pen_id": ""}})
    assert r.status_code == 200, r.text
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get("/api/state").json()["machine"]["job_state"] == "idle":
            break
        time.sleep(0.1)
    else:
        pytest.fail("simulator staged plot did not finish")
