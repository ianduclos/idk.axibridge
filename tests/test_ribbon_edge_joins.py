"""Edge lanes stay distinct when independent envelopes exchange sides at joins."""
import json
from pathlib import Path

import pytest
from shapely.geometry import LineString

from axibridge.compose import CanvasLayer, shape_layer
from axibridge.effects._ribbon_geometry import balance_edge_widths, join_ranges
from axibridge.sources.pen import PenParams, PenSource


def test_edge_corner_fixture_has_no_crossings_or_shared_interior_routes():
    fixture = Path(__file__).resolve().parents[1] / 'docs/reviews/ribbon-edge-joins-2026-09-09/input.json'
    layer = CanvasLayer(**json.loads(fixture.read_text()))
    source = PenSource().generate(PenParams(**layer.source.params))
    paths = shape_layer(layer, source.layers[0].paths)
    lines = [LineString(p.points) for p in paths]
    assert len(lines) == 20
    assert all(line.is_simple for line in lines)
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            assert not a.crosses(b)
            # Shared endpoints are intentional; overlapping centre routes are not.
            assert a.intersection(b).length < 1e-6


def test_edge_balance_preserves_total_width_and_stabilizes_corner_ratio():
    stations = list(range(301))
    left = [2 + s / 50 for s in stations]
    right = [5 - s / 100 for s in stations]
    original = left[:], right[:]
    corners = [{'s': 150., 'turn': 1.5}]
    a, b = balance_edge_widths(left, right, stations, corners, 10)
    assert (left, right) == original
    assert [x+y for x,y in zip(a,b)] == pytest.approx([x+y for x,y in zip(left,right)])
    start, end = join_ranges(stations, corners, 10)[0]
    ratios = [a[i]/(a[i]+b[i]) for i in range(start, end+1)]
    assert max(ratios)-min(ratios) < 1e-12
    assert a[:start-10] == left[:start-10]
    assert a[end+11:] == left[end+11:]
    assert min(a+b) >= 0
    assert balance_edge_widths(left, right, stations, [], 10) == original
