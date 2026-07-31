"""Interrupted-plot fragments: a contiguous pen-down slice of the whole
resolved project, baked into one layer (session.interrupt_fragment +
POST /api/layers/interrupt)."""

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.session import _subpath_by_distance, session


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _line_layer(x0=10.0, y0=100.0, x1=210.0, y1=100.0):
    """One straight 200mm stroke as a drawing layer."""
    return session.add_generated_layer(
        "drawing", {"strokes": [[[x0, y0, 0.0], [x1, y1, 1.0]]], "resample_mm": 5.0})


def _fragment_length(layer):
    return sum(p.length() for p in session.source_geometry[layer.id])


# -- slicing math ---------------------------------------------------------------


def test_subpath_full_interval_is_identity():
    pts = [(0.0, 0.0), (100.0, 0.0)]
    assert _subpath_by_distance(pts, 0.0, 100.0) == pts


def test_subpath_cuts_mid_segment():
    pts = [(0.0, 0.0), (100.0, 0.0)]
    assert _subpath_by_distance(pts, 25.0, 75.0) == [(25.0, 0.0), (75.0, 0.0)]


def test_subpath_spanning_vertices():
    pts = [(0.0, 0.0), (50.0, 0.0), (50.0, 50.0)]  # an L, 100mm total
    out = _subpath_by_distance(pts, 25.0, 75.0)
    assert out == [(25.0, 0.0), (50.0, 0.0), (50.0, 25.0)]


def test_subpath_miss_returns_empty():
    pts = [(0.0, 0.0), (100.0, 0.0)]
    assert _subpath_by_distance(pts, 150.0, 200.0) == []
    assert _subpath_by_distance(pts, 50.0, 50.0) == []


# -- session behaviour ----------------------------------------------------------


def test_empty_project_raises():
    with pytest.raises(RuntimeError, match="nothing to interrupt"):
        session.interrupt_fragment(seed=1)


def test_full_range_keeps_everything():
    _line_layer()
    layer, a, b = session.interrupt_fragment(seed=1, start=0.0, stop=1.0)
    assert (a, b) == (0.0, 1.0)
    assert _fragment_length(layer) == pytest.approx(200.0, abs=1.0)


def test_mid_slice_cuts_the_stroke():
    _line_layer()
    layer, a, b = session.interrupt_fragment(seed=1, start=0.25, stop=0.75)
    frag = session.source_geometry[layer.id]
    assert len(frag) == 1  # one continuous piece of the one stroke
    assert _fragment_length(layer) == pytest.approx(100.0, abs=1.0)  # half of 200mm
    xs = [x for x, _ in frag[0].points]
    assert min(xs) == pytest.approx(60.0, abs=1.0)   # 10 + 0.25*200
    assert max(xs) == pytest.approx(160.0, abs=1.0)  # 10 + 0.75*200


def test_fragment_is_never_filled():
    session.add_generated_layer("polygon", {"sides": 5, "radius": 20})
    layer, _, _ = session.interrupt_fragment(seed=3, start=0.0, stop=1.0)
    assert session.source_geometry[layer.id]
    assert all(not p.filled for p in session.source_geometry[layer.id])


def test_seed_rolls_deterministically():
    _line_layer()
    first, a1, b1 = session.interrupt_fragment(seed=42)
    len1 = _fragment_length(first)
    session.undo()  # drop the fragment so the reroll sees the same project
    second, a2, b2 = session.interrupt_fragment(seed=42)
    assert (a1, b1) == (a2, b2)
    assert _fragment_length(second) == pytest.approx(len1)
    # a rolled slice is strictly inside the plot (random start, early stop)
    assert 0.0 < b1 - a1 < 1.0


def test_start_stop_swapped_is_tolerated():
    _line_layer()
    _layer, a, b = session.interrupt_fragment(seed=1, start=0.8, stop=0.2)
    assert (a, b) == (0.2, 0.8)


def test_one_undo_step_removes_the_fragment():
    _line_layer()
    before = len(session.project.layers)
    layer, _, _ = session.interrupt_fragment(seed=1)
    assert len(session.project.layers) == before + 1
    session.undo()
    assert len(session.project.layers) == before
    assert layer.id not in session.source_geometry


def test_optimized_order_path_runs():
    _line_layer()
    session.project.plot_options.sort = True
    layer, _, _ = session.interrupt_fragment(seed=1, optimized=True)
    assert session.source_geometry[layer.id]


# -- API ------------------------------------------------------------------------


def test_api_empty_project_400(client):
    r = client.post("/api/layers/interrupt", json={"seed": 1})
    assert r.status_code == 400


def test_api_creates_layer_and_reports_fractions(client):
    _line_layer()
    r = client.post("/api/layers/interrupt", json={"seed": 7})
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["start"] < body["stop"] <= 1.0
    assert body["layer"]["source"]["type"] == "baked"
    assert body["layer"]["id"] in session.source_geometry


def test_api_manual_range(client):
    _line_layer()
    r = client.post("/api/layers/interrupt",
                    json={"seed": 7, "start": 0.1, "stop": 0.4, "optimized": False})
    assert r.status_code == 200
    body = r.json()
    assert (body["start"], body["stop"]) == (0.1, 0.4)
    frag = session.source_geometry[body["layer"]["id"]]
    assert sum(p.length() for p in frag) == pytest.approx(60.0, abs=1.0)  # 0.3 * 200mm
