"""Plot-time estimation: PathDocument + motion params -> PlannedJob.

This is **not** a motion planner. The real planning happens inside pyaxidraw/
plotink (or saxi); this module only predicts how long that execution will
take, so the preview can show an estimated plot time and the simulator has a
realistic clock to walk. It uses the textbook model the real planners are
built on — trapezoidal velocity profiles with junction (cornering) speed
limits — but its output never reaches the machine.

Calibration values default to nominal AxiDraw V3 figures (EMSL quotes a max
XY speed of ~11 in/s). Treat estimates as ±15% until calibrated. Since v2 the
constants live in machine settings (Settings tab) and are passed in as
:class:`EstimatorConstants`; the module-level defaults remain for tests and
standalone use.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from .model import PathDocument, PlannedJob, PlannedMove, Point

#: Nominal max carriage speed (11 in/s) — what speed_pendown=100 means.
MAX_SPEED_MM_S = 279.4
#: Nominal max acceleration — what accel=100 means. Calibration constant.
MAX_ACCEL_MM_S2 = 4000.0
#: Base servo travel time for a full pen up/down swing at rate=100.
PEN_SWING_S = 0.15


class EstimatorConstants(BaseModel):
    """Machine calibration for the estimator. ``Settings`` shares these field
    names, so ``EstimatorConstants(**settings.model_dump())`` just works."""

    model_config = {"extra": "ignore"}

    max_speed_mm_s: float = MAX_SPEED_MM_S
    max_accel_mm_s2: float = MAX_ACCEL_MM_S2
    pen_swing_s: float = PEN_SWING_S


_DEFAULT_CONSTS = EstimatorConstants()


class MotionParams(BaseModel):
    """The motion parameter vocabulary the estimator understands.

    Backends each declare their *own* params model; this one is the superset
    the estimator consumes. Backend models reuse these field names so a plain
    dict can flow from UI -> backend -> estimator. (pyaxidraw-style 1–100
    percentage semantics throughout.)
    """

    speed_pendown: float = Field(default=25, ge=1, le=110, title="Pen-down speed %")
    speed_penup: float = Field(default=75, ge=1, le=110, title="Pen-up speed %")
    accel: float = Field(default=75, ge=1, le=100, title="Acceleration %")
    cornering: float = Field(
        default=10, ge=0.01, le=100, title="Cornering %",
        description="Junction speed tolerance — higher takes corners faster",
    )
    pen_pos_down: float = Field(default=40, ge=0, le=100, title="Pen height: down %")
    pen_pos_up: float = Field(default=60, ge=0, le=100, title="Pen height: up %")
    pen_rate_lower: float = Field(default=50, ge=1, le=100, title="Pen lower rate %")
    pen_rate_raise: float = Field(default=75, ge=1, le=100, title="Pen raise rate %")
    pen_delay_down: float = Field(default=0, ge=-500, le=2000, title="Extra delay after lowering (ms)")
    pen_delay_up: float = Field(default=0, ge=-500, le=2000, title="Extra delay after raising (ms)")
    const_speed: bool = Field(default=False, title="Constant pen-down speed (no accel ramps)")


def _polyline_time(
    pts: list[Point], v_max: float, a: float, cornering: float, const_speed: bool
) -> float:
    """Trapezoidal time over a polyline with junction speed limits."""
    segs = [math.dist(a_, b_) for a_, b_ in zip(pts, pts[1:])]
    segs = [s for s in segs if s > 1e-9]
    if not segs:
        return 0.0
    if const_speed:
        return sum(segs) / v_max

    n = len(segs)
    # Junction speed limit at each interior vertex from turn angle.
    v_junc = [0.0] * (n + 1)  # entry speed bound per segment boundary
    for i in range(1, n):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        ux, uy = x1 - x0, y1 - y0
        wx, wy = x2 - x1, y2 - y1
        nu = math.hypot(ux, uy) or 1.0
        nw = math.hypot(wx, wy) or 1.0
        cos_t = max(-1.0, min(1.0, (ux * wx + uy * wy) / (nu * nw)))
        # Straight-through (cos 1) -> full speed; reversal (cos -1) -> stop.
        factor = (cos_t + 1.0) / 2.0
        v_junc[i] = v_max * (factor ** (1.0 / max(cornering / 25.0, 0.05)))
    # Forward pass: limited by acceleration from previous boundary.
    v = [0.0] * (n + 1)
    for i in range(1, n + 1):
        v[i] = min(v_max if i < n else 0.0, v_junc[i] if i < n else 0.0)
        v[i] = min(v[i], math.sqrt(v[i - 1] ** 2 + 2 * a * segs[i - 1]))
    # Backward pass: must be able to decelerate to each boundary speed.
    for i in range(n - 1, -1, -1):
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * a * segs[i]))
    # Time per segment with trapezoid/triangle between v[i] and v[i+1].
    t = 0.0
    for i, s in enumerate(segs):
        v0, v1 = v[i], v[i + 1]
        v_peak = math.sqrt(max((2 * a * s + v0**2 + v1**2) / 2.0, 0.0))
        v_peak = min(v_peak, v_max)
        t_acc = (v_peak - v0) / a
        t_dec = (v_peak - v1) / a
        d_acc = (v0 + v_peak) / 2.0 * t_acc
        d_dec = (v1 + v_peak) / 2.0 * t_dec
        d_cruise = max(s - d_acc - d_dec, 0.0)
        t += t_acc + t_dec + (d_cruise / v_peak if v_peak > 0 else 0.0)
    return t


def pen_lift_time(p: MotionParams, consts: EstimatorConstants = _DEFAULT_CONSTS) -> float:
    swing = abs(p.pen_pos_up - p.pen_pos_down) / 100.0
    return consts.pen_swing_s * swing * (100.0 / p.pen_rate_raise) + max(p.pen_delay_up, 0) / 1000.0


def pen_lower_time(p: MotionParams, consts: EstimatorConstants = _DEFAULT_CONSTS) -> float:
    swing = abs(p.pen_pos_up - p.pen_pos_down) / 100.0
    return consts.pen_swing_s * swing * (100.0 / p.pen_rate_lower) + max(p.pen_delay_down, 0) / 1000.0


def plan_job(
    doc: PathDocument,
    params: MotionParams,
    start: Point = (0.0, 0.0),
    return_home: bool = True,
    consts: EstimatorConstants = _DEFAULT_CONSTS,
) -> PlannedJob:
    """Expand a document into an explicit, timed move list.

    Travel moves are generated between consecutive paths in draw order —
    exactly the order an execution backend will visit them (backends iterate
    the same ``iter_paths()``), so the preview shows what will actually
    happen, not an idealised version.
    """
    v_down = min(params.speed_pendown, 110) / 100.0 * consts.max_speed_mm_s
    v_up = min(params.speed_penup, 110) / 100.0 * consts.max_speed_mm_s
    a = params.accel / 100.0 * consts.max_accel_mm_s2
    t_lift = pen_lift_time(params, consts)
    t_lower = pen_lower_time(params, consts)

    job = PlannedJob()
    pos: Point = start
    for layer, path in doc.iter_paths():
        pts = path.points
        # Travel to path start (pen already up).
        if math.dist(pos, pts[0]) > 1e-9:
            d = math.dist(pos, pts[0])
            t = _polyline_time([pos, pts[0]], v_up, a, params.cornering, False)
            job.moves.append(
                PlannedMove(pen_down=False, points=[pos, pts[0]], distance=d, duration=t)
            )
            job.travel_distance += d
            job.travel_duration += t
        # Draw the path.
        d = path.length()
        t_draw = _polyline_time(pts, v_down, a, params.cornering, params.const_speed)
        job.moves.append(
            PlannedMove(
                pen_down=True,
                points=list(pts),
                layer_id=layer.id,
                distance=d,
                duration=t_lower + t_draw + t_lift,
            )
        )
        job.pen_down_distance += d
        job.pen_down_duration += t_draw
        job.pen_lift_duration += t_lower + t_lift
        job.pen_lifts += 1
        pos = pts[-1]

    if return_home and math.dist(pos, start) > 1e-9:
        d = math.dist(pos, start)
        t = _polyline_time([pos, start], v_up, a, params.cornering, False)
        job.moves.append(PlannedMove(pen_down=False, points=[pos, start], distance=d, duration=t))
        job.travel_distance += d
        job.travel_duration += t

    job.total_duration = job.pen_down_duration + job.travel_duration + job.pen_lift_duration
    return job
