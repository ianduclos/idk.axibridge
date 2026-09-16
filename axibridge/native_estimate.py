"""Offline timing through the installed pyaxidraw motion planner.

This module deliberately creates its own preview-only AxiDraw object.  It
never borrows the native backend's live object and never opens a serial port.
The returned duration is firmware motion plus pen-servo time; synchronous USB
command/acknowledgement overhead is necessarily absent.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .model import PathDocument, PlannedJob, PlannedMove, Point
from .render_work import checkpoint


_OPTION_NAMES = (
    "speed_pendown", "speed_penup", "accel", "pen_pos_down", "pen_pos_up",
    "pen_rate_lower", "pen_rate_raise", "pen_delay_down", "pen_delay_up",
    "resolution", "penlift", "model",
)


def _values(params: Any) -> dict[str, Any]:
    if isinstance(params, Mapping):
        return dict(params)
    if hasattr(params, "model_dump"):
        return params.model_dump()
    return {name: getattr(params, name) for name in (*_OPTION_NAMES, "const_speed")}


def estimate_native_job(
    doc: PathDocument,
    params: Any,
    start: Point = (0.0, 0.0),
    return_home: bool = True,
    origin: Point = (0.0, 0.0),
) -> PlannedJob:
    """Return pyaxidraw's preview timing without discovering hardware.

    ``origin`` is the backend's user-origin offset in the physical machine
    frame. Geometry is clipped with the same official routine as interactive
    ``draw_path``; returned move points remain in the user's coordinate frame.
    """
    # Optional/private dependencies stay local so importing axibridge does not
    # make pyaxidraw mandatory for simulator-only installations.
    from axidrawinternal import dripfeed, motion  # type: ignore[import-not-found]
    from pyaxidraw import axidraw  # type: ignore[import-not-found]

    values = _values(params)
    ad = axidraw.AxiDraw()
    ad.interactive()
    ad.options.preview = True
    ad.options.rendering = 0
    for name in _OPTION_NAMES:
        if name in values:
            setattr(ad.options, name, int(round(values[name])))
    if "const_speed" in values:
        ad.options.const_speed = bool(values["const_speed"])

    # These routines only derive bounds, speeds, resolution and servo timing
    # in preview mode.  Their I/O branches are guarded by ``not preview``.
    ad.update_options()
    ad.pen.servo_init(ad)
    ad.enable_motors()
    _assert_offline(ad)

    sx = (origin[0] + start[0]) / 25.4
    sy = (origin[1] + start[1]) / 25.4
    ad.pen.phys.xpos = sx
    ad.pen.phys.ypos = sy
    ad.pen.phys.z_up = True
    ad.pen.turtle.xpos = sx
    ad.pen.turtle.ypos = sy
    ad.pen.turtle.z_up = True

    job = PlannedJob()
    pos = start
    for layer, path in doc.iter_paths():
        checkpoint()
        if len(path.points) == 1:
            dot = _clip_dot(ad, path.points[0], origin)
            subpaths = [[dot]] if dot is not None else []
        else:
            subpaths = _clip_subpaths(ad, path.points, origin)
        for points in subpaths:
            checkpoint()
            pos = _append_path(ad, job, layer.id, points, pos, origin, motion, dripfeed)

    if return_home and math.dist(pos, start) > 1e-9:
        before_t, before_u, _ = _stats(ad)
        ad.go_to_position(sx, sy)
        _assert_offline(ad)
        after_t, after_u, _ = _stats(ad)
        duration = (after_t - before_t) / 1000.0
        distance = (after_u - before_u) * 25.4
        job.moves.append(PlannedMove(
            pen_down=False, points=[pos, start], distance=distance, duration=duration,
        ))
        job.travel_distance += distance
        job.travel_duration += duration

    job.total_duration = (
        job.pen_down_duration + job.travel_duration + job.pen_lift_duration
    )
    return job


def _append_path(
    ad: Any,
    job: PlannedJob,
    layer_id: int,
    points: list[Point],
    pos: Point,
    origin: Point,
    motion: Any,
    dripfeed: Any,
) -> Point:
    """Append one already-clipped subpath, returning its final user position."""
    if math.dist(pos, points[0]) > 1e-9:
        before_t, before_u, _ = _stats(ad)
        ad.go_to_position(
            (origin[0] + points[0][0]) / 25.4,
            (origin[1] + points[0][1]) / 25.4,
        )
        _assert_offline(ad)
        after_t, after_u, _ = _stats(ad)
        duration = (after_t - before_t) / 1000.0
        distance = (after_u - before_u) * 25.4
        job.moves.append(PlannedMove(
            pen_down=False, points=[pos, points[0]],
            distance=distance, duration=duration,
        ))
        job.travel_distance += distance
        job.travel_duration += duration

    before_t, _, before_d = _stats(ad)
    if len(points) == 1:
        ad.pen.pen_lower(ad)
        ad.pen.pen_raise(ad)
        plotted = True
    else:
        vertices = [
            [(origin[0] + x) / 25.4, (origin[1] + y) / 25.4]
            for x, y in points
        ]
        planned = motion.trajectory(ad, vertices)
        # The native driver deliberately executes lower/raise even when motor
        # quantization leaves this trajectory with no SM commands.
        plotted = planned is not None
        if plotted:
            dripfeed.feed(ad, planned[0])
    _assert_offline(ad)
    if not plotted:
        return points[-1]

    after_t, _, after_d = _stats(ad)
    duration = (after_t - before_t) / 1000.0
    distance = (after_d - before_d) * 25.4
    pen_time = (
        ad.pen.heights.times.lower_time + ad.pen.heights.times.raise_time
    ) / 1000.0
    job.moves.append(PlannedMove(
        pen_down=True, points=points, layer_id=layer_id,
        distance=distance, duration=duration,
    ))
    job.pen_down_distance += distance
    job.pen_down_duration += duration - pen_time
    job.pen_lift_duration += pen_time
    job.pen_lifts += 1
    return points[-1]


def _stats(ad: Any) -> tuple[int, float, float]:
    stats = ad.plot_status.stats
    return stats.pt_estimate, stats.up_travel_inch, stats.down_travel_inch


def _assert_offline(ad: Any) -> None:
    if ad.plot_status.port is not None:
        raise RuntimeError("native estimator unexpectedly acquired a serial port")


def _clip_subpaths(ad: Any, points: list[Point], origin: Point) -> list[list[Point]]:
    """Run the exact pure clipping stage used by pyaxidraw ``draw_path``."""
    from axidrawinternal import boundsclip, path_objects  # type: ignore[import-not-found]

    physical = [
        [(origin[0] + x) / 25.4, (origin[1] + y) / 25.4]
        for x, y in points
    ]
    item = path_objects.PathItem()
    item.item_id = "axibridge_native_estimate"
    item.stroke = "Black"
    item.subpaths = [physical]
    layer = path_objects.LayerItem()
    layer.paths.append(item)
    digest = path_objects.DocDigest()
    digest.layers.append(layer)
    digest.flat = True
    boundsclip.clip_at_bounds(
        digest, ad.bounds, ad.bounds, ad.params.bounds_tolerance, doc_clip=False,
    )
    ox, oy = origin
    return [
        [((x * 25.4) - ox, (y * 25.4) - oy) for x, y in path.subpaths[0]]
        for path in digest.layers[0].paths
        if path.subpaths and path.subpaths[0]
    ]


def _clip_dot(ad: Any, point: Point, origin: Point) -> Point | None:
    """Clip the backend's special moveto/lower/raise dot operation."""
    from plotink import plot_utils  # type: ignore[import-not-found]

    target = [(origin[0] + point[0]) / 25.4, (origin[1] + point[1]) / 25.4]
    current = [ad.pen.phys.xpos, ad.pen.phys.ypos]
    accepted, segment = plot_utils.clip_segment([current, target], ad.bounds)
    if not accepted:
        return None
    x, y = segment[1]
    return ((x * 25.4) - origin[0], (y * 25.4) - origin[1])
