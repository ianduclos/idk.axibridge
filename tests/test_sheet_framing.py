"""Grid-sheet v2: fixed framing (motion survives), crosshair marks, frame caches."""

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.session import session
from axibridge.stores import Pen, pen_library


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _translating_follow():
    """A follow-master tween that TRANSLATES +60 mm in x over the timeline —
    shape and size constant, so any placement difference is pure motion."""
    a = session.add_generated_layer("polygon", {"sides": 4, "radius": 10})
    b = session.add_generated_layer("polygon", {"sides": 4, "radius": 10})
    session.update_layer(b.id, {"transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 60, "f": 0}})
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 0.0, "follow_master": True})
    session.update_layer(a.id, {"visible": False})
    session.update_layer(b.id, {"visible": False})
    return tw


def _cell_offsets(placed, cols):
    """Per frame: its bbox centre minus its cell centre (x only)."""
    g = session.project.guide
    cw = g.width / cols
    out = []
    for i, frame in enumerate(placed):
        xs = [x for paths in frame.values() for p in paths for x, _ in p.points]
        cell_cx = g.x + (i % cols + 0.5) * cw
        out.append((min(xs) + max(xs)) / 2 - cell_cx)
    return out


def test_center_framing_cancels_translation_fixed_preserves_it():
    _translating_follow()
    # 1×2 (unrotated — 2×1/4×2 flip the scene 90°, which would swap the axes
    # this test measures): two stacked cells, motion measured along x
    centered = session._grid_place([0.0, 1.0], cols=1, rows=2, margin_mm=5.0, framing="center")
    off_c = _cell_offsets(centered, 1)
    assert all(abs(o) < 1e-6 for o in off_c), "center: every frame re-centred (motion cancelled)"

    fixed = session._grid_place([0.0, 1.0], cols=1, rows=2, margin_mm=5.0, framing="fixed")
    off_f = _cell_offsets(fixed, 1)
    assert off_f[0] < -1.0 and off_f[1] > 1.0, "fixed: t=0 sits left of centre, t=1 right"
    assert off_f[1] - off_f[0] > 2.0  # the scaled 60mm translation survives


def _two_pen_layers():
    a = session.add_generated_layer("polygon", {"sides": 5, "radius": 12})
    b = session.add_generated_layer("polygon", {"sides": 3, "radius": 8})
    session.update_layer(b.id, {"transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 40, "f": 20}})
    pa = pen_library.upsert(Pen(name="pen A", color="#ff0000"))
    pb = pen_library.upsert(Pen(name="pen B", color="#0000ff"))
    session.update_layer(a.id, {"pen_id": pa.id})
    session.update_layer(b.id, {"pen_id": pb.id})
    return pa, pb


def test_marks_prepend_to_first_pass_only():
    pa, pb = _two_pen_layers()
    plain = session.sheet_document(2, 2, 4, 0.0, 1.0, 5.0, 0)
    marked = session.sheet_document(2, 2, 4, 0.0, 1.0, 5.0, 0, marks=True)
    n_marks = 2 * (2 + 1) * (2 + 1)  # two strokes per ＋, (cols+1)×(rows+1) crosses
    assert len(marked.layers[0].paths) == len(plain.layers[0].paths) + n_marks
    assert [len(l.paths) for l in marked.layers[1:]] == [len(l.paths) for l in plain.layers[1:]]

    # crosshair geometry: 2-point strokes, never filled, on the guide's grid lines
    g = session.project.guide
    xs_expected = {g.x, g.x + g.width / 2, g.x + g.width}
    crosses = marked.layers[0].paths[:n_marks]
    assert all(len(p.points) == 2 and not p.filled for p in crosses)
    for p in crosses:
        (x0, y0), (x1, y1) = p.points
        assert 0 <= min(x0, x1) and max(x0, x1) <= 300 and 0 <= min(y0, y1) <= 218

    # pen-filtered single passes match their slice of the full set
    order = session.sheet_passes(2, 2, 4, 0.0, 1.0, 5.0, 0)
    first = session.sheet_document(2, 2, 4, 0.0, 1.0, 5.0, 0, pen_id=order[0], marks=True)
    second = session.sheet_document(2, 2, 4, 0.0, 1.0, 5.0, 0, pen_id=order[1], marks=True)
    assert len(first.layers[0].paths) == len(marked.layers[0].paths)
    assert len(second.layers[0].paths) == len(marked.layers[1].paths)


def test_frame_cache_collapses_repeat_resolves(monkeypatch):
    _two_pen_layers()
    calls = {"n": 0}
    orig = session.resolved

    def counting(master_t=None):
        calls["n"] += 1
        return orig(master_t=master_t)

    monkeypatch.setattr(session, "resolved", counting)

    session.sheet_document(2, 2, 8, 0.0, 1.0, 5.0, 0)
    cold = calls["n"]
    assert cold == 8, "cold assembly resolves each frame exactly once"

    session.sheet_document(2, 2, 8, 0.0, 1.0, 5.0, 1)          # next page
    session.sheet_document(2, 2, 8, 0.0, 1.0, 5.0, 0)          # back again
    session.sheet_passes(2, 2, 8, 0.0, 1.0, 5.0, 1)            # stepper info
    assert calls["n"] == cold, "warm pages/passes resolve nothing"

    # any mutation invalidates (checkpoint clears the caches)
    layer = session.project.layers[0]
    session.update_layer(layer.id, {"transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 5, "f": 5}})
    session.sheet_document(2, 2, 8, 0.0, 1.0, 5.0, 0)
    assert calls["n"] == cold + 8, "post-mutation assembly re-resolves"


def test_sheet_spec_api_round_trip(client):
    client.post("/api/layers/generate", json={"module": "polygon", "params": {"sides": 6, "radius": 15}})
    tw = client.post("/api/layers/generate", json={"module": "polygon", "params": {"sides": 6, "radius": 30}}).json()
    client.post("/api/layers/tween", json={
        "a": client.get("/api/project").json()["layers"][0]["id"], "b": tw["id"]})

    sheet = ('{"cols":2,"rows":2,"frames":4,"framing":"fixed","marks":true}')
    r = client.get(f"/api/plan?sheet={sheet}")
    assert r.status_code == 200

    r = client.post("/api/staging/capture", json={
        "kind": "sheet", "cols": 2, "rows": 2, "frames": 4,
        "framing": "fixed", "marks": True})
    assert r.status_code == 200
    fmt = r.json()["group"]["format"]
    assert fmt["framing"] == "fixed" and fmt["marks"] is True

    r = client.get("/api/animation/export.zip?frames=4&cols=2&rows=2&framing=fixed&marks=true")
    assert r.status_code == 200

    # bad framing rejected at the boundary
    assert client.get("/api/animation/export.zip?frames=4&cols=2&rows=2&framing=diag").status_code == 422
