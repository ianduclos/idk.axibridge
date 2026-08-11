"""Grid-sheet v2: crop modes (timeline preserves motion, full keeps the
whole page), crosshair marks, frame caches.

Renamed from test_sheet_framing.py (2026-08-11): the old "framing" enum
("fixed"/"center") is replaced by "crop" ("timeline"/"full") per Ian's
ruling in docs/plans/timeline-v2.md §2c "Baking crop" — the old "center"
mode (each frame recentred on its own bbox, cancelling relative motion) is
removed entirely, not merely renamed. See test_legacy_framing_format_still_
loads for the backward-compat read path old saved captures still need."""

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


def _bbox(frame):
    xs = [x for paths in frame.values() for p in paths for x, _ in p.points]
    ys = [y for paths in frame.values() for p in paths for _, y in p.points]
    return min(xs), min(ys), max(xs), max(ys)


def test_timeline_crop_preserves_motion_with_shared_bounds():
    _translating_follow()
    # 1×2 (unrotated — 2×1/4×2 flip the scene 90°, which would swap the axes
    # this test measures): two stacked cells, motion measured along x.
    placed = session._grid_place([0.0, 1.0], cols=1, rows=2, margin_mm=5.0, crop="timeline")
    offsets = _cell_offsets(placed, 1)
    assert offsets[0] < -1.0 and offsets[1] > 1.0, "t=0 sits left of centre, t=1 right"
    assert offsets[1] - offsets[0] > 2.0  # the scaled 60mm translation survives

    def width(frame):
        xs = [x for paths in frame.values() for p in paths for x, _ in p.points]
        return max(xs) - min(xs)

    # the SAME crop window is applied to both frames: the shape's own
    # footprint doesn't grow/shrink between frames, only its position moves —
    # a per-frame crop (the removed "center" mode) would instead re-normalise
    # each frame to its own bbox and erase the offset measured above.
    assert width(placed[0]) == pytest.approx(width(placed[1]), abs=1e-6)


def test_full_crop_keeps_page_bounds_and_negative_space():
    session.add_generated_layer("polygon", {"sides": 4, "radius": 5})
    resolved = session.resolved(master_t=0.0)
    xs = [x for paths in resolved.values() for p in paths for x, _ in p.points]
    ys = [y for paths in resolved.values() for p in paths for _, y in p.points]
    own_box = (min(xs), min(ys), max(xs), max(ys))

    # 1×1 grid, no margin: cell == the guide rect exactly, so "full" (fit the
    # PAGE, not the content, into the cell) is a scale-1 identity placement —
    # the content keeps its natural size AND position (negative space around
    # a small shape is preserved, not zoomed away).
    full = session._grid_place([0.0], cols=1, rows=1, margin_mm=0.0, crop="full")
    assert _bbox(full[0]) == pytest.approx(own_box, abs=1e-6)

    # "timeline" (the default), same grid: fits the CONTENT to the cell — the
    # small shape is zoomed up to fill the guide, a much bigger footprint.
    timeline = session._grid_place([0.0], cols=1, rows=1, margin_mm=0.0, crop="timeline")
    own_w = own_box[2] - own_box[0]
    full_w = _bbox(full[0])[2] - _bbox(full[0])[0]
    timeline_w = _bbox(timeline[0])[2] - _bbox(timeline[0])[0]
    assert full_w == pytest.approx(own_w, abs=1e-6)
    assert timeline_w > full_w * 2


def test_bad_crop_value_rejected():
    session.add_generated_layer("polygon", {"sides": 4, "radius": 5})
    with pytest.raises(ValueError, match="crop must be one of"):
        session._grid_place([0.0], cols=1, rows=1, margin_mm=0.0, crop="center")


def test_legacy_framing_format_still_loads():
    """Captures/formats saved before 2026-08-11 store "framing" ("fixed" or
    "center"), not "crop". Old baked bytes stay frozen and untouched (§2c
    "Trays") — this covers only the RE-derive path (rebake/relayout), which
    must still work rather than crash on an old format dict."""
    session.add_generated_layer("polygon", {"sides": 5, "radius": 12})
    legacy_fixed = {"kind": "sheet", "cols": 2, "rows": 2, "frames": 8,
                     "t_from": 0.0, "t_to": 1.0, "margin_mm": 5.0,
                     "framing": "fixed", "marks": False}
    docs = session._documents_for_format(legacy_fixed)
    assert len(docs) == 2  # ceil(8 / 4) == 2 pages
    assert any(l.paths for d in docs for l in d.layers)

    # "center" (the banned per-frame mode) must also degrade gracefully
    # rather than raise — it maps to "timeline", the closest safe default.
    legacy_center = {**legacy_fixed, "framing": "center"}
    docs2 = session._documents_for_format(legacy_center)
    assert len(docs2) == 2

    assert session._crop_from_format(legacy_fixed) == "timeline"
    assert session._crop_from_format(legacy_center) == "timeline"
    assert session._crop_from_format({"crop": "full"}) == "full"
    assert session._crop_from_format({}) == "timeline"


def test_bake_more_frames_than_cells_makes_one_group_with_ceil_sheets():
    """docs/plans/timeline-v2.md §2c "Sheet grid": frames > rows×cols must
    produce ⌈frames/cells⌉ sheets, all as ONE capture group in the tray —
    Ian's "set rows×cols, hit Bake, get a tray group of N sheets" flow."""
    session.add_generated_layer("polygon", {"sides": 5, "radius": 12})
    group = session.capture_to_staging(kind="sheet", name="bake", cols=2, rows=2, frames=10)
    assert group.kind == "sheet"
    assert len(group.sheets) == 3  # ceil(10 / 4) == 3, all in ONE group
    assert group.format["pages"] == 3


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

    sheet = ('{"cols":2,"rows":2,"frames":4,"crop":"timeline","marks":true}')
    r = client.get(f"/api/plan?sheet={sheet}")
    assert r.status_code == 200

    r = client.post("/api/staging/capture", json={
        "kind": "sheet", "cols": 2, "rows": 2, "frames": 4,
        "crop": "timeline", "marks": True})
    assert r.status_code == 200
    fmt = r.json()["group"]["format"]
    assert fmt["crop"] == "timeline" and fmt["marks"] is True

    r = client.get("/api/animation/export.zip?frames=4&cols=2&rows=2&crop=timeline&marks=true")
    assert r.status_code == 200

    # bad crop rejected at the boundary
    assert client.get("/api/animation/export.zip?frames=4&cols=2&rows=2&crop=diag").status_code == 422
