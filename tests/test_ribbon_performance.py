"""Regression checks for Ribbon's indexed silhouette spine lookup."""

import math

import pytest

from axibridge.effects._ribbon_geometry import EPS, _spine_at


def _linear_reference(values, s, hint):
    exact = [i for i, (_, station) in enumerate(values) if abs(station - s) <= EPS]
    if exact:
        return values[min(exact, key=lambda i: abs(i - hint))][0]
    for (a, sa), (b, sb) in zip(values, values[1:]):
        if sa - EPS <= s <= sb + EPS and sb > sa + EPS:
            t = max(0.0, min(1.0, (s - sa) / (sb - sa)))
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return values[0 if s <= values[0][1] else -1][0]


@pytest.mark.parametrize(
    ("s", "hint"),
    [
        (2.0, 1.1),       # duplicate station, earlier hint
        (2.0, 2.9),       # duplicate station, later hint
        (2.0 + EPS, 2.0), # inclusive exact tolerance
        (3.0, 0.0),       # interpolation after duplicate stations
        (-EPS * 2, 0.0),  # before the spine
        (6.0, 0.0),       # after the spine
    ],
)
def test_indexed_spine_lookup_matches_linear_reference_with_duplicate_stations(s, hint):
    values = [((0.0, 0.0), 0.0), ((2.0, 1.0), 2.0), ((20.0, 2.0), 2.0), ((4.0, 4.0), 4.0)]
    stations = [station for _, station in values]

    assert _spine_at(values, stations, s, hint) == _linear_reference(values, s, hint)


def test_indexed_spine_lookup_keeps_float_boundary_semantics():
    raw_stations = (0.0, 1e-8, 1.0, 1.0, 1.0, 1.0, 1.0, 1e8, 1e8 + 1e-6)
    values = [((float(i), -float(i)), station) for i, station in enumerate(raw_stations)]
    stations = [station for _, station in values]
    probes = []
    for station in stations:
        probes.extend((station - EPS, math.nextafter(station - EPS, -math.inf), station,
                       station + EPS, math.nextafter(station + EPS, math.inf)))

    for s in probes:
        for hint in (0.0, 2.25, 10.0):
            assert _spine_at(values, stations, s, hint) == _linear_reference(values, s, hint)
