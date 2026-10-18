"""Geometry checks for the three finished-ink measuring devices."""
from __future__ import annotations

import json

import numpy as np
import pytest

from gesture import kit
from gesture.kit._devices import DCtx, _DEVICES, apply_devices, device_list


IDS = ("arc_ticks", "survey_marks", "misfit_grid")


def sheet_with(*lines):
    return kit.Sheet((100.0, 80.0), [], [kit.Ink(p) for p in lines],
                     {"recipe": {"seed": 4243}})


def call(did, sheet, *, region=(10.0, 10.0, 80.0, 60.0), **params):
    # A fixed region lets a single straight input test a two-dimensional field.
    d = _DEVICES[did]
    values = {p.name: p.default for p in d.params}
    values.update(params)
    ctx = DCtx(sheet.frame, region, region, "over", 4243, did)
    return d.fn(ctx, sheet, **values)


def fingerprint(inks):
    return [(k.points.tobytes(), k.closed, k.filled, k.pen,
             json.dumps(k.meta, sort_keys=True)) for k in inks]


def test_devices_register_as_general():
    registered = {d["id"]: d for d in device_list()}
    assert set(IDS) <= registered.keys()
    assert all(registered[did]["family"] == "general" for did in IDS)


@pytest.mark.parametrize("did", IDS)
def test_devices_return_finite_thin_unfilled_ink_and_repeat(did):
    sheet = sheet_with([[10, 20], [40, 20], [40, 60]])
    before = fingerprint(sheet.inks)
    a, b = call(did, sheet), call(did, sheet)
    assert a
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(sheet.inks) == before
    for k in a:
        assert isinstance(k, kit.Ink)
        assert len(k.points) >= 2 and np.isfinite(k.points).all()
        assert 0.15 <= k.pen <= 0.3 and not k.filled


def test_arc_ticks_count_real_arc_length_and_label_cumulative_mm():
    # 30 horizontal + 40 vertical = 70 mm, regardless of vertex spacing.
    sheet = sheet_with([[10, 20], [11, 20], [40, 20], [40, 60]])
    out = call("arc_ticks", sheet, every=10, major_every=3, offset=1)
    ticks = [k for k in out if k.meta["role"] == "tick"]
    assert len(ticks) == 7
    assert [k.meta["arc_mm"] for k in ticks] == [10, 20, 30, 40, 50, 60, 70]
    np.testing.assert_allclose(ticks[0].points[0], [20, 21])
    assert ticks[0].points[1, 0] == pytest.approx(20)  # perpendicular
    assert np.linalg.norm(ticks[2].points[1] - ticks[2].points[0]) > np.linalg.norm(
        ticks[0].points[1] - ticks[0].points[0])
    labels = sorted({k.meta["text"] for k in out if k.meta["role"] == "arc_label"})
    assert labels == ["30", "60"]


def test_arc_selection_threshold_and_device_ink_exclusion():
    sheet = sheet_with([[10, 20], [40, 20], [40, 60]], [[10, 40], [35, 40]])
    sheet.inks.append(kit.Ink([[0, 0], [1000, 0]], meta={"layer": "device"}))
    for which, minimum, expected in [("longest", 1, 7), ("all_over", 20, 9),
                                      ("all_over", 30, 7)]:
        ticks = [k for k in call("arc_ticks", sheet, which=which, min_length=minimum, every=10)
                 if k.meta["role"] == "tick"]
        assert len(ticks) == expected


def test_closed_ink_counts_implicit_closing_segment_once():
    sheet = sheet_with([[10, 10], [20, 10], [20, 20], [10, 20]])
    sheet.inks[0] = kit.Ink(sheet.inks[0].points, closed=True)
    ticks = [k for k in call("arc_ticks", sheet, every=5) if k.meta["role"] == "tick"]
    assert len(ticks) == 8


def test_arc_tick_at_corner_stays_beside_both_incident_segments():
    sheet = sheet_with([[10, 20], [40, 20], [40, 60]])
    ticks = [k for k in call("arc_ticks", sheet, every=10, offset=1)
             if k.meta["role"] == "tick"]
    corner = next(k for k in ticks if k.meta["arc_mm"] == 30)
    probes = corner.points[0] + np.linspace(0, 1, 21)[:, None] * (corner.points[1] - corner.points[0])
    horizontal = np.column_stack([np.clip(probes[:, 0], 10, 40), np.full(21, 20)])
    vertical = np.column_stack([np.full(21, 40), np.clip(probes[:, 1], 20, 60)])
    assert np.linalg.norm(probes - horizontal, axis=1).min() > 0.2
    assert np.linalg.norm(probes - vertical, axis=1).min() > 0.2


def test_survey_centroid_integrates_segment_lengths_not_vertex_counts():
    # Centroid = (30*(25,20) + 40*(40,40))/70 = (235/7,220/7).
    sheet = sheet_with([[10, 20], [11, 20], [40, 20], [40, 60]])
    out = call("survey_marks", sheet, region=(10, 20, 30, 40), principal_axis=False)
    circle = next(k for k in out if k.meta["role"] == "centroid_ring")
    centre = (circle.points.min(axis=0) + circle.points.max(axis=0)) / 2
    np.testing.assert_allclose(centre, [235 / 7, 220 / 7], atol=1e-10)
    assert circle.closed
    corners = [k for k in out if k.meta["role"] == "corner_cross"]
    centres = {tuple(np.mean(k.points, axis=0)) for k in corners}
    assert centres == {(10, 20), (40, 20), (10, 60), (40, 60)}
    labels = {k.meta["text"] for k in out if k.meta["role"] == "coordinate_label"}
    assert "X33.6 Y31.4" in labels


def test_principal_axis_is_separate_short_dashes_on_true_horizontal_axis():
    sheet = sheet_with([[10, 40], [90, 40]])
    out = call("survey_marks", sheet, principal_axis=True, dash=3, gap=2)
    dashes = [k for k in out if k.meta["role"] == "principal_axis"]
    assert len(dashes) > 3
    for k in dashes:
        assert len(k.points) == 2
        np.testing.assert_allclose(k.points[:, 1], 40)
        assert np.linalg.norm(k.points[1] - k.points[0]) <= 3 + 1e-10


def test_grid_zero_strength_has_one_contiguous_polyline_per_grid_line():
    sheet = sheet_with([[45, 25], [55, 55]])
    out = call("misfit_grid", sheet, pitch=10, strength=0, clear=0)
    assert len(out) == 16  # 9 vertical and 7 horizontal, including region edges.
    for k in out:
        assert k.meta["role"] == "grid_line"
        assert len(k.points) > 2
        assert np.linalg.norm(np.diff(k.points, axis=0), axis=1).max() <= 1.01
        axis = k.meta["axis"]
        np.testing.assert_allclose(k.points[:, 0 if axis == "x" else 1], k.meta["coordinate"])


def test_grid_gradient_moves_toward_ink_and_signed_strength_reverses_it():
    sheet = sheet_with([[50, 20], [50, 60]])
    for strength, direction in [(4, 1), (-4, -1)]:
        out = call("misfit_grid", sheet, pitch=10, blur=8, strength=strength, clear=0)
        left = next(k for k in out if k.meta["axis"] == "x" and k.meta["coordinate"] == 40)
        right = next(k for k in out if k.meta["axis"] == "x" and k.meta["coordinate"] == 60)
        assert direction * (left.points[len(left.points) // 2, 0] - 40) > 0.1
        assert direction * (right.points[len(right.points) // 2, 0] - 60) < -0.1


def test_grid_clearance_breaks_crossings_and_drops_short_stubs():
    sheet = sheet_with([[10, 40], [90, 40]])
    out = call("misfit_grid", sheet, pitch=10, strength=0, clear=2, min_stub=3)
    assert out
    vertical_middle = [k for k in out if k.meta["axis"] == "x" and k.meta["coordinate"] == 50]
    assert len(vertical_middle) == 2
    for k in out:
        assert np.linalg.norm(np.diff(k.points, axis=0), axis=1).sum() >= 3 - 1e-8
        for a, b in zip(k.points[:-1], k.points[1:]):
            probes = a + np.linspace(0, 1, 21)[:, None] * (b - a)
            nearest = np.column_stack([np.clip(probes[:, 0], 10, 90), np.full(21, 40)])
            assert np.linalg.norm(probes - nearest, axis=1).min() >= 2 - 1e-8


@pytest.mark.parametrize("pitch", [0, 5.99, 61, float("nan"), float("inf")])
def test_grid_pitch_bounds_rejected_at_public_device_boundary(pitch):
    with pytest.raises(kit.KitError):
        apply_devices(sheet_with([[10, 20], [40, 60]]), [{"id": "misfit_grid", "pitch": pitch}])


@pytest.mark.parametrize("did", IDS)
def test_empty_or_zero_length_ink_has_no_invented_measurement(did):
    assert call(did, sheet_with()) == []
    assert call(did, sheet_with([[30, 30], [30, 30]])) == []


def test_layer_application_keeps_ink_and_tags_new_layers():
    sheet = sheet_with([[10, 20], [40, 20], [40, 60]])
    out = apply_devices(sheet, [{"id": "misfit_grid", "place": "under", "clear": 0},
                                {"id": "arc_ticks", "place": "over"},
                                {"id": "survey_marks", "place": "over"}])
    source_at = next(i for i, ink in enumerate(out.inks) if ink is sheet.inks[0])
    assert source_at > 0
    assert all(k.meta["device"] == "misfit_grid" for k in out.inks[:source_at])
    assert all(k.meta["layer"] == "device" for k in out.inks[source_at + 1:])
    assert len(sheet.inks) == 1
