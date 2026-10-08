"""Mosca 2 keeps browser-generated geometry and history without changing it."""

import math

import pytest
from pydantic import ValidationError

from axibridge.registry import describe_modules, get_source, load_builtin_modules
from axibridge.sources.mosca2 import Mosca2Params


def _part(**overrides):
    return {"id": "p1", "label": "Territory", "kind": "territory",
            "strokes": [[(1.25, 2.5), (3.75, 4.5)]], **overrides}


def test_replays_visible_parts_with_exact_strokes_gaps_points_and_order():
    parts = [
        _part(strokes=[[(1.25, 2.5)], [], [(3.75, 4.5), (5.125, 6.25)]], label="A"),
        {"id": "hidden", "label": "Hidden", "kind": "response", "visible": False,
         "strokes": [[(100, 100), (110, 110)]]},
        {"id": "flow", "label": "Flow", "kind": "flowing",
         "strokes": [[(20, 21), (22, 23)], [(24, 25)]]},
    ]
    source = get_source("mosca2")
    doc = source.generate(Mosca2Params(parts=parts))
    assert [(layer.id, layer.name) for layer in doc.layers] == [(1, "A"), (2, "Flow")]
    assert [[path.points for path in layer.paths] for layer in doc.layers] == [
        [[(1.25, 2.5)], [(3.75, 4.5), (5.125, 6.25)]],
        [[(20.0, 21.0), (22.0, 23.0)], [(24.0, 25.0)]],
    ]
    assert all(not path.filled for layer in doc.layers for path in layer.paths)
    assert (doc.width, doc.height, doc.source) == (300.0, 218.0, "mosca2")
    assert source.placement_frame({}) is None  # already in physical bed coordinates
    assert source.generate(Mosca2Params()).layers == []


@pytest.mark.parametrize("point", [(-0.1, 1), (301, 1), (1, 219),
                                    (math.nan, 1), (1, math.inf)])
def test_rejects_invalid_coordinates_in_parts_and_history(point):
    with pytest.raises(ValidationError):
        Mosca2Params(parts=[_part(strokes=[[point]])])
    history = {"id": "h", "label": "Run", "before": [[point]],
               "added": [], "settings": {}}
    with pytest.raises(ValidationError):
        Mosca2Params(history=[history])


def test_rejects_aggregate_point_and_stroke_budgets():
    stroke = [(1.0, 2.0)] * 250_000
    with pytest.raises(ValidationError, match="point budget"):
        Mosca2Params(parts=[_part(strokes=[stroke])], history=[
            {"id": "h", "label": "Run", "before": [stroke],
             "added": [[(1.0, 2.0)]], "settings": {}}])
    with pytest.raises(ValidationError, match="stroke budget"):
        Mosca2Params(parts=[_part(strokes=[[]] * 50_001)])


def test_rejects_oversized_metadata_and_collection_counts():
    with pytest.raises(ValidationError):
        Mosca2Params(parts=[_part(id=str(i)) for i in range(33)])
    record = {"id": "h", "label": "Run", "settings": {}}
    with pytest.raises(ValidationError):
        Mosca2Params(history=[record] * 13)
    with pytest.raises(ValidationError):
        Mosca2Params(parts=[_part(provenance="x" * 1001)])
    with pytest.raises(ValidationError):
        Mosca2Params(history=[{**record, "events": [
            {"t_ms": 0, "kind": "contact"}] * 2001}])
    with pytest.raises(ValidationError):
        Mosca2Params(engine="future-engine")


def test_roundtrip_keeps_history_settings_and_provenance():
    payload = {"parts": [_part(provenance="captured")],
               "history": [{"id": "h1", "label": "Pass", "before": [[(1, 2)]],
                            "added": [[(3, 4)]], "settings": {"seed": 777},
                            "summary": "changed", "provenance": "reason",
                            "events": [{"t_ms": 123.5, "kind": "contact",
                                        "detail": "near line"}]}],
               "settings": {"seed": 456, "duration_s": 3.25},
               "engine": "mosca2-v1"}
    params = Mosca2Params(**payload)
    assert Mosca2Params.model_validate_json(params.model_dump_json()) == params
    assert params.history[0].settings.seed == 777
    assert params.history[0].events[0].t_ms == 123.5


@pytest.mark.parametrize("settings", [{"seed": 0}, {"duration_s": 0},
                                       {"contact_hz": -1}, {"start_x": 299},
                                       {"heading_deg": 181}])
def test_rejects_out_of_range_settings(settings):
    with pytest.raises(ValidationError):
        Mosca2Params(settings=settings)


def test_registry_metadata_and_hidden_fields():
    load_builtin_modules()
    entry = next(item for item in describe_modules()["sources"]
                 if item["id"] == "mosca2")
    assert entry["label"] == "Mosca 2"
    assert entry["bench"] == {"adapter": "mosca2", "version": 1,
                              "modes": ["new", "resume"]}
    assert "bench" in entry["library_categories"]
    assert all(entry["schema"]["properties"][name]["hidden"]
               for name in ("parts", "history", "settings", "engine"))
