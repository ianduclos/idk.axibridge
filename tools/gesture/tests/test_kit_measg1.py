"""Physical readings and plotting contracts for the three measg1 devices."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesture.kit import devices_measg1 as devices  # noqa: E402
from gesture.kit._devices import DCtx, _DEVICES, apply_devices, device_list  # noqa: E402
from gesture.kit.core import Ink, KitError, Mark, Sheet  # noqa: E402


IDS = ("scale_ruler", "density_isoline", "heading_rose")
BOX = (20.0, 20.0, 80.0, 60.0)


def _sheet(points=None, *, inks=None):
    if points is None:
        points = [np.array([[20., 20.], [100., 20.], [100., 80.], [20., 80.]]),
                  np.column_stack([np.linspace(30., 90., 121),
                                   50. + 12. * np.sin(np.linspace(0., 4. * np.pi, 121))])]
    marks = [Mark(p) for p in points]
    return Sheet((140., 110.), marks,
                 [Ink(m.points, pen=0.2) for m in marks] if inks is None else inks,
                 {"recipe": {"seed": 4242}})


def _ctx(device, *, region=BOX, place="over", box=BOX):
    return DCtx((300., 200.), region, box, place, 4242, device)


def _length(points):
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def _same(a, b):
    assert len(a) == len(b)
    for left, right in zip(a, b):
        assert isinstance(left, Ink) and isinstance(right, Ink)
        np.testing.assert_array_equal(left.points, right.points)
        assert (left.closed, left.filled, left.pen, left.meta) == (
            right.closed, right.filled, right.pen, right.meta)


def _inside(inks, region):
    x, y, w, h = region
    for ink in inks:
        assert isinstance(ink, Ink)
        assert not ink.filled
        assert 0.15 <= ink.pen <= 0.3
        assert len(ink.points) >= 2
        assert np.isfinite(ink.points).all()
        assert (ink.points >= np.array([x, y]) - 0.5).all()
        assert (ink.points <= np.array([x + w, y + h]) + 0.5).all()


@pytest.mark.parametrize("device_id", IDS)
def test_devices_register_as_general(device_id):
    listed = {entry["id"]: entry for entry in device_list()}
    assert listed[device_id]["family"] == "general"
    assert listed[device_id]["doc"]
    assert _DEVICES[device_id].fn is getattr(devices, device_id)


@pytest.mark.parametrize("device_id", IDS)
@pytest.mark.parametrize("region,place", [
    (BOX, "over"), ((150., 10., 80., 90.), "beside"),
    ((10., 90., 120., 18.), "margin"), ((10., 10., 18., 100.), "margin"),
])
def test_finite_bounded_plottable_and_deterministic(device_id, region, place):
    ctx = _ctx(device_id, region=region, place=place)
    fn = getattr(devices, device_id)
    a, b = fn(ctx, _sheet()), fn(ctx, _sheet())
    assert a
    _inside(a, region)
    _same(a, b)


@pytest.mark.parametrize("region,axis,expected", [
    ((10., 90., 120., 18.), 0, [20., 100.]),
    ((12., 10., 18., 100.), 1, [20., 80.]),
])
def test_drawing_ruler_measures_exact_bbox_extent(region, axis, expected):
    inks = devices.scale_ruler(_ctx("scale_ruler", region=region, place="margin"), _sheet())
    baseline = max((k for k in inks if len(k.points) == 2), key=lambda k: _length(k.points))
    np.testing.assert_allclose(np.sort(baseline.points[:, axis]), expected, atol=1e-10)
    assert np.ptp(baseline.points[:, 1 - axis]) == pytest.approx(0.)


def test_region_ruler_millimetre_tick_positions_and_grades():
    region = (10., 90., 120., 18.)
    inks = devices.scale_ruler(_ctx("scale_ruler", region=region, place="margin"),
                               _sheet(), anchor="region")
    baseline = max((k for k in inks if len(k.points) == 2), key=lambda k: _length(k.points))
    assert np.ptp(baseline.points[:, 0]) == pytest.approx(120.)
    x0, y0 = baseline.points[np.argmin(baseline.points[:, 0])]
    ticks = {}
    for ink in inks:
        p = ink.points
        if len(p) != 2 or abs(p[0, 0] - p[1, 0]) > 1e-9:
            continue
        if not np.any(np.isclose(p[:, 1], y0, atol=1e-9)):
            continue
        at = float(p[0, 0] - x0)
        if abs(at - round(at)) < 1e-9:
            ticks[int(round(at))] = _length(p)
    assert set(range(121)) <= set(ticks)
    assert ticks[1] < ticks[5] < ticks[10]
    assert ticks[2] == pytest.approx(ticks[1])
    assert ticks[15] == pytest.approx(ticks[5])
    assert ticks[20] == pytest.approx(ticks[10])


def test_drawing_ruler_never_shrinks_a_measurement_to_fit():
    ctx = _ctx("scale_ruler", region=(150., 10., 40., 20.), place="beside")
    with pytest.raises(KitError):
        devices.scale_ruler(ctx, _sheet(), anchor="drawing")


@pytest.mark.parametrize("minimum", [1., 8., 30.])
def test_density_contours_join_segments_and_filter_in_output_mm(minimum):
    inks = devices.density_isoline(_ctx("density_isoline"), _sheet(), min_length=minimum)
    assert inks
    assert max(len(k.points) for k in inks) > 10
    for ink in inks:
        assert _length(ink.points) >= minimum - 1e-9
        # A marching-square edge crosses one cell, rather than teleporting
        # between disconnected islands when segments are joined.
        assert np.linalg.norm(np.diff(ink.points, axis=0), axis=1).max() <= 3.1
        if ink.closed:
            np.testing.assert_allclose(ink.points[0], ink.points[-1], atol=1e-10)


def test_density_ignores_all_device_ink():
    sheet = _sheet()
    extra = Ink(np.array([[20., 50.], [100., 50.]]), pen=0.3, meta={"layer": "device"})
    polluted = _sheet(inks=sheet.inks + [extra])
    ctx = _ctx("density_isoline")
    _same(devices.density_isoline(ctx, sheet), devices.density_isoline(ctx, polluted))
    assert devices.density_isoline(ctx, _sheet(inks=[extra])) == []


def test_density_grid_reads_ink_not_marks():
    ink = Ink(np.array([[30., 35.], [90., 35.]]), pen=0.2)
    a = _sheet(points=[np.array([[30., 35.], [90., 35.]])], inks=[ink])
    b = _sheet(points=[np.array([[30., 65.], [90., 65.]])], inks=[ink])
    xa, ya, fa = devices._density_grid(a, BOX, 1.5, 3.)
    xb, yb, fb = devices._density_grid(b, BOX, 1.5, 3.)
    np.testing.assert_array_equal(xa, xb)
    np.testing.assert_array_equal(ya, yb)
    np.testing.assert_array_equal(fa, fb)
    assert np.isfinite(fa).all() and float(np.max(fa)) > 0.


def test_marching_squares_joins_a_single_closed_ring():
    xs, ys = np.linspace(-20., 20., 81), np.linspace(-20., 20., 81)
    x, y = np.meshgrid(xs, ys)
    field = np.exp(-(x * x + y * y) / 100.)
    contours = devices._marching_polylines(xs, ys, field, 0.5)
    assert len(contours) == 1
    contour = contours[0]
    assert len(contour) > 70
    np.testing.assert_allclose(contour[0], contour[-1], atol=1e-10)
    radii = np.linalg.norm(contour, axis=1)
    np.testing.assert_allclose(radii, np.sqrt(100. * np.log(2.)), atol=0.03)
    assert np.linalg.norm(np.diff(contour, axis=0), axis=1).max() <= np.sqrt(0.5)


def test_density_beside_preserves_aspect_of_over_reading():
    sheet = _sheet()
    a = devices.density_isoline(_ctx("density_isoline"), sheet, min_length=1.)
    region = (150., 10., 160., 120.)
    b = devices.density_isoline(_ctx("density_isoline", region=region, place="beside"),
                                 sheet, min_length=2.)
    # This panel doubles the geometry, so double the output-mm cutoff to
    # compare the same source contours before checking the uniform map.
    assert len(a) == len(b) and a
    pa, pb = np.concatenate([k.points for k in a]), np.concatenate([k.points for k in b])
    scale = np.ptp(pb, axis=0) / np.ptp(pa, axis=0)
    assert scale[0] == pytest.approx(scale[1], rel=1e-10)
    # Every corresponding vertex must undergo the same uniform map.
    np.testing.assert_allclose(pb - pb[0], (pa - pa[0]) * scale[0], atol=1e-9)
    _inside(b, region)


def _rose(sheet, **params):
    return devices.heading_rose(_ctx("heading_rose"), sheet, **params)


def _heading(inks):
    return next(ink for ink in inks if ink.meta.get("role") == "heading")


def test_heading_one_closed_contour_reference_circle_and_four_ticks():
    inks = _rose(_sheet())
    roles = [k.meta.get("role") for k in inks]
    assert roles.count("heading") == 1
    assert roles.count("reference") == 1
    assert roles.count("tick") == 4
    assert len(inks) == 6
    for role in ("heading", "reference"):
        ink = next(k for k in inks if k.meta.get("role") == role)
        assert ink.closed
        np.testing.assert_array_equal(ink.points[0], ink.points[-1])
    reference = next(k for k in inks if k.meta.get("role") == "reference")
    centre = np.array([60., 50.])
    radii = np.linalg.norm(reference.points - centre, axis=1)
    np.testing.assert_allclose(radii, radii[0], atol=1e-9)


def test_heading_is_axial_and_uses_length_not_segment_count():
    horizontal = np.array([[20., 40.], [100., 40.]])
    vertical = np.array([[60., 40.], [60., 60.]])
    sheet = _sheet(points=[horizontal, vertical])
    reversed_sheet = _sheet(points=[horizontal[::-1], vertical[::-1]])
    _same(_rose(sheet, smooth=0.), _rose(reversed_sheet, smooth=0.))
    sampled_horizontal = np.column_stack([np.linspace(20., 100., 101), np.full(101, 40.)])
    _same(_rose(sheet, smooth=0.),
          _rose(_sheet(points=[sampled_horizontal, vertical]), smooth=0.))
    p = _heading(_rose(sheet, smooth=0.)).points - np.array([60., 50.])
    angles, radius = np.arctan2(p[:, 1], p[:, 0]), np.linalg.norm(p, axis=1)
    near_horizontal = radius[np.abs(np.sin(angles)) < 0.15].max()
    near_vertical = radius[np.abs(np.cos(angles)) < 0.15].max()
    assert near_horizontal > near_vertical * 1.5


def test_heading_reads_marks_instead_of_renderer_ink_and_no_data_is_empty():
    sheet = _sheet()
    _same(_rose(sheet), _rose(_sheet(inks=[])))
    assert _rose(_sheet(points=[], inks=sheet.inks)) == []
    assert _rose(_sheet(points=[np.array([[60., 50.], [60., 50.]])])) == []


INVALID = [
    ("scale_ruler", "anchor", "sheet"),
    ("scale_ruler", "label_h", 0.79), ("scale_ruler", "label_h", 3.51),
    ("density_isoline", "cell", 0.99), ("density_isoline", "cell", 2.01),
    ("density_isoline", "sigma", 0.49), ("density_isoline", "sigma", 12.01),
    ("density_isoline", "levels", 1), ("density_isoline", "levels", 5),
    ("density_isoline", "min_length", 0.99), ("density_isoline", "min_length", 100.01),
    ("heading_rose", "bins", 7), ("heading_rose", "bins", 181),
    ("heading_rose", "smooth", -0.01), ("heading_rose", "smooth", 4.01),
]
INVALID += [(device_id, "pen", value) for device_id in IDS for value in (0.149, 0.301)]
INVALID += [(device_id, name, value)
            for device_id, names in (
                ("scale_ruler", ("label_h", "pen")),
                ("density_isoline", ("cell", "sigma", "levels", "min_length", "pen")),
                ("heading_rose", ("bins", "smooth", "pen")))
            for name in names for value in (float("nan"), float("inf"), float("-inf"))]


@pytest.mark.parametrize("device_id,name,value", INVALID)
def test_apply_devices_rejects_invalid_parameter_values(device_id, name, value):
    # int(nonfinite) raises before the device function, whereas float and
    # choice validation happen in the device; neither may emit invalid ink.
    with pytest.raises((KitError, ValueError, OverflowError)):
        apply_devices(_sheet(), [{"id": device_id, "place": "over", name: value}])


def test_apply_devices_tags_readings_and_preserves_source_sheet():
    source = _sheet()
    original = [k.points.copy() for k in source.inks]
    specs = [{"id": "scale_ruler", "place": "margin", "side": "bottom", "size": 18.},
             {"id": "density_isoline", "place": "over"},
             {"id": "heading_rose", "place": "beside", "size": 60.}]
    out = apply_devices(source, specs)
    assert out.frame == (200., 110.)
    assert source.frame == (140., 110.) and "devices" not in source.meta
    assert len(source.inks) == len(original)
    for ink, before in zip(source.inks, original):
        np.testing.assert_array_equal(ink.points, before)
    added = out.inks[len(source.inks):]
    assert {k.meta["device"] for k in added} == set(IDS)
    assert all(k.meta["layer"] == "device" for k in added)
    for applied in out.meta["devices"]:
        _inside([k for k in added if k.meta["device"] == applied["id"]], applied["region"])
