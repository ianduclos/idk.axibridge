"""Regression for the deliberately fractured 2026-09-09 ribbon trial."""
import json
from pathlib import Path

import pytest

from axibridge.compose import CanvasLayer, _layer_seed
from axibridge.effects import ribbon
from axibridge.effects.ribbon import RibbonParams, _construct, _points, _prepare
from axibridge.registry import EffectContext
from axibridge.sources.pen import PenParams, PenSource


def test_fractured_envelope_reproduces_ordered_trial():
    fixture_dir = Path(__file__).resolve().parents[1] / "docs/reviews/ribbon-edge-joins-2026-09-09"
    layer_data = json.loads((fixture_dir / "input.json").read_text())
    expected = json.loads((fixture_dir / "ordered.json").read_text())
    layer = CanvasLayer(**layer_data)
    params = RibbonParams(**layer.effects[0].params).model_copy(update={"fractured_edges": True})
    source = PenSource().generate(PenParams(**layer.source.params)).layers[0].paths[0]
    ctx = EffectContext(seed=_layer_seed(layer_data["id"]))
    data = _prepare(_points(source), params, ctx)

    actual = _construct(data, params, data["required"], data["required"])["strokes"]

    assert len(actual) == len(expected)
    for actual_path, expected_path in zip(actual, expected):
        actual_flat = [coordinate / ribbon._SCALE for point in actual_path for coordinate in point]
        expected_flat = [coordinate for point in expected_path["points"] for coordinate in point]
        assert actual_flat == pytest.approx(expected_flat, abs=1e-10)
