from __future__ import annotations

import pytest

pytest.importorskip("pyaxidraw")

from axibridge.backends.axidraw_native import NativeParams
from axibridge.model import Layer, Path, PathDocument
from axibridge.native_estimate import estimate_native_job


def _doc(points):
    return PathDocument(layers=[Layer(id=7, paths=[Path(points=points)])])


def test_native_estimate_never_calls_serial(monkeypatch):
    from plotink import ebb_motion, ebb_serial

    def forbidden(*_args, **_kwargs):
        raise AssertionError("serial I/O attempted by offline estimator")

    monkeypatch.setattr(ebb_serial, "command", forbidden)
    monkeypatch.setattr(ebb_motion, "query_enable_motors", forbidden)
    monkeypatch.setattr(ebb_motion, "sendEnableMotors", forbidden)

    job = estimate_native_job(_doc([(10, 10), (20, 10)]), NativeParams())
    assert job.total_duration > 0
    assert job.moves[-1].points[-1] == (0.0, 0.0)


def test_dense_native_path_pays_one_ms_motion_quantum():
    # Alternating diagonals exceed the high-resolution one-step threshold but
    # are short enough that each accepted native segment becomes a 1 ms SM.
    points = [(10 + i * 0.01, 10 + (i % 2) * 0.01) for i in range(201)]
    job = estimate_native_job(
        _doc(points), NativeParams(pen_pos_down=50, pen_pos_up=50),
        start=points[0], return_home=False,
    )
    assert job.pen_down_duration >= 0.190


def test_resolution_const_speed_and_pen_options_affect_timing():
    doc = _doc([(10, 10), (110, 10), (110, 110)])
    default = estimate_native_job(doc, NativeParams(), start=(10, 10), return_home=False)
    low_res = estimate_native_job(
        doc, NativeParams(resolution=2), start=(10, 10), return_home=False,
    )
    constant = estimate_native_job(
        doc, NativeParams(const_speed=True), start=(10, 10), return_home=False,
    )
    slow_pen = estimate_native_job(
        doc, NativeParams(pen_rate_lower=10, pen_rate_raise=10),
        start=(10, 10), return_home=False,
    )
    assert low_res.pen_down_duration != default.pen_down_duration
    assert constant.pen_down_duration != default.pen_down_duration
    assert slow_pen.pen_lift_duration > default.pen_lift_duration


def test_clips_to_model_bounds_and_returns_clipped_points():
    params = NativeParams(model=4).model_dump()
    job = estimate_native_job(
        _doc([(-10, 10), (80, 10), (170, 10)]), params,
        start=(0, 10), return_home=False,
    )
    draw = [move for move in job.moves if move.pen_down]
    assert len(draw) == 1
    assert draw[0].points[0] == pytest.approx((0, 10), abs=1e-7)
    assert draw[0].points[-1] == pytest.approx((160.02, 10), abs=1e-7)
    assert job.pen_lifts == 1


def test_origin_is_applied_for_physical_clipping_but_moves_stay_user_frame():
    job = estimate_native_job(
        _doc([(-30, 10), (10, 10)]), NativeParams(),
        start=(-20, 10), return_home=False, origin=(20, 0),
    )
    draw = [move for move in job.moves if move.pen_down]
    assert draw[0].points[0] == pytest.approx((-20, 10), abs=1e-7)
    assert draw[0].points[-1] == pytest.approx((10, 10), abs=1e-7)


def test_fully_clipped_path_vanishes_but_substep_path_cycles_pen():
    outside = estimate_native_job(
        _doc([(-20, -20), (-10, -10)]), NativeParams(), return_home=False,
    )
    tiny = estimate_native_job(
        _doc([(10, 10), (10.001, 10)]), NativeParams(),
        start=(10, 10), return_home=False,
    )
    assert outside.moves == []
    assert outside.pen_lifts == 0
    assert tiny.pen_down_distance == 0
    assert tiny.pen_down_duration == 0
    assert tiny.pen_lifts == 1
    assert tiny.pen_lift_duration > 0


def test_dot_uses_backend_special_case_and_clips_moveto():
    job = estimate_native_job(
        _doc([(350, 10)]), NativeParams(), start=(10, 10), return_home=False,
    )
    draw = [move for move in job.moves if move.pen_down]
    assert job.pen_lifts == 1
    assert len(draw) == 1
    assert draw[0].points[0] == pytest.approx((299.974, 10), abs=1e-7)
