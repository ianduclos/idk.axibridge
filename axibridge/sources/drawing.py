"""Drawing (pointer) — pointer strokes captured on the canvas become a
generator layer's source geometry (docs/plans/draw-mode.md).

Why a layer, not a tool: the moment a drawing is an ordinary layer it
inherits occlusion, pens, estimates, undo, regions, A/B capture, tweening
and the timeline for free — nothing here adds a second geometry path to
the plotter (see CLAUDE.md's single-resolve invariant).

Strokes are geometry-as-params, mirroring api.py's ``WorkbenchBody``/
``_drawing_paths`` point-budget-and-bed-clamp pattern: each point is
``[x_mm, y_mm, t_s]`` (machine-frame mm, seconds since that stroke's
pen-down). Timestamps are captured so a "velocity tube" render mode can
derive drawing speed from them (docs/plans/response-brushes.md Part 2) —
each stroke's own outline width is driven by its own speed: slow points
(corners lingered over, dwells) swell toward ``width_max``, fast points
(flicks) taper toward ``width_min``. This lives here rather than as an
effect because effects only see ``list[Path]`` (x, y) — the timing exists
only in this source's ``strokes`` params and must never leak into the
pure-geometry effect pipeline.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source

# Bed bounds mirror axibridge.compose.BED_WIDTH/BED_HEIGHT (not imported to
# avoid a sources -> compose dependency; compose never imports sources).
BED_WIDTH = 300.0
BED_HEIGHT = 218.0

# geometry-as-params: bounded like api._drawing_paths' _MAX_DRAWING_POINTS —
# a regenerate must never die on a stray captured point, but density is capped
_MAX_POINTS = 50_000

StrokePoint = tuple[float, float, float]


class DrawingParams(BaseModel):
    strokes: list[list[StrokePoint]] = Field(
        default_factory=list,
        title="Strokes",
        description="Captured pointer strokes: [x_mm, y_mm, t_s] per point",
        json_schema_extra={"hidden": True},
    )
    resample_mm: float = Field(
        default=0.8, ge=0.2, le=5.0, title="Resample (mm)",
        description="Resample each stroke at a fixed arc-length step so "
                    "pointer-event density doesn't matter",
    )
    smooth: int = Field(
        default=1, ge=0, le=4, title="Smooth passes",
        description="3-point smoothing passes over the resampled stroke",
    )
    render: Literal["centerline", "velocity_tube"] = Field(
        default="centerline", title="Render",
        description="centerline: the resampled/smoothed stroke as-is. "
                    "velocity_tube: a swollen outline whose width is driven "
                    "by drawing speed (dwells swell, flicks taper)",
    )
    width_min: float = Field(
        default=1.0, ge=0.3, le=10.0, title="Width min (mm)",
        description="Outline width at the stroke's fastest points",
        json_schema_extra={"group": "Velocity tube"},
    )
    width_max: float = Field(
        default=6.0, ge=1.0, le=25.0, title="Width max (mm)",
        description="Outline width at the stroke's slowest points",
        json_schema_extra={"group": "Velocity tube"},
    )
    speed_smooth_mm: float = Field(
        default=8.0, ge=1.0, le=30.0, title="Speed smoothing (mm)",
        description="Arc-length window for smoothing the speed signal before "
                    "it drives width — too small and the width flutters point-to-point",
        json_schema_extra={"group": "Velocity tube"},
    )
    keep_centerline: bool = Field(
        default=False, title="Keep centerline",
        description="Also emit the plain centerline path alongside the outline "
                    "(off: the tube alone is the stroke)",
        json_schema_extra={"group": "Velocity tube"},
    )


def _prepare_strokes(strokes: list[list[tuple[float, float, float]]]
                      ) -> list[list[tuple[float, float, float]]]:
    """Cap total density (raise) and clamp every point into the bed (never
    raise for a stray off-bed point — a regenerate must always succeed)."""
    total = sum(len(stroke) for stroke in strokes)
    if total > _MAX_POINTS:
        raise ValueError(f"drawing too dense: {total} points (max {_MAX_POINTS})")
    out = []
    for stroke in strokes:
        if not stroke:
            continue
        out.append([
            (min(BED_WIDTH, max(0.0, float(x))),
             min(BED_HEIGHT, max(0.0, float(y))),
             max(0.0, float(t)))
            for x, y, t in stroke
        ])
    return out


def _resample(pts: list[tuple[float, float, float]], step: float
              ) -> list[tuple[float, float, float]]:
    """Even resampling along arc length (mm); t is interpolated alongside
    x/y. Ports draw.js's stroke ``resample`` with a third channel.
    Endpoints are always preserved exactly."""
    if len(pts) < 2:
        return list(pts)
    out = [pts[0]]
    acc = 0.0
    for i in range(len(pts) - 1):
        x0, y0, t0 = pts[i]
        x1, y1, t1 = pts[i + 1]
        seg = math.hypot(x1 - x0, y1 - y0)
        while seg > 0 and acc + seg >= step:
            frac = (step - acc) / seg
            nx = x0 + (x1 - x0) * frac
            ny = y0 + (y1 - y0) * frac
            nt = t0 + (t1 - t0) * frac
            out.append((nx, ny, nt))
            x0, y0, t0 = nx, ny, nt
            seg = math.hypot(x1 - x0, y1 - y0)
            acc = 0.0
        acc += seg
    out.append(pts[-1])
    return out


def _smooth(pts: list[tuple[float, float, float]], passes: int
            ) -> list[tuple[float, float, float]]:
    """3-point kernel smoothing over x/y only (the sources/misremembered.py
    ``_smooth`` style): endpoints untouched, vertex count unchanged, t
    carried through from the centre point of each window."""
    for _ in range(max(passes, 0)):
        if len(pts) < 3:
            break
        pts = ([pts[0]]
               + [((a[0] + 2 * b[0] + c[0]) / 4, (a[1] + 2 * b[1] + c[1]) / 4, b[2])
                  for a, b, c in zip(pts, pts[1:], pts[2:])]
               + [pts[-1]])
    return pts


def _tangents(xy: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Unit tangent per point (central difference; forward/backward at ends)."""
    n = len(xy)
    out = []
    for i in range(n):
        a = xy[i - 1] if i > 0 else xy[i]
        b = xy[i + 1] if i < n - 1 else xy[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        out.append((dx / d, dy / d) if d > 1e-12 else (1.0, 0.0))
    return out


def _smooth_along_arclength(values: list[float], cum: list[float], window_mm: float) -> list[float]:
    """Box filter over a value sampled at increasing arc-length positions —
    a two-pointer sliding window since `cum` is sorted, O(n) total, so the
    width signal reflects nearby speed rather than one point's instant
    (noisy) reading."""
    n = len(values)
    if window_mm <= 0 or n < 2:
        return list(values)
    half = window_mm / 2.0
    out = []
    j_lo = j_hi = 0
    for i in range(n):
        while cum[i] - cum[j_lo] > half:
            j_lo += 1
        while j_hi < n - 1 and cum[j_hi + 1] - cum[i] <= half:
            j_hi += 1
        window = values[j_lo:j_hi + 1]
        out.append(sum(window) / len(window))
    return out


def _velocity_widths(xy: list[tuple[float, float]], ts: list[float], cum: list[float],
                      width_min: float, width_max: float, speed_smooth_mm: float) -> list[float]:
    """Per-point outline width from drawing speed, normalized to THIS
    stroke's own min/max speed (so a uniformly-drawn stroke sits mid-width
    and dwells swell relative to its own pace, not some global scale)."""
    n = len(xy)
    mid = (width_min + width_max) / 2.0
    if n < 3 or (max(ts) - min(ts)) < 1e-6:
        return [mid] * n  # degenerate: too few points, or all-equal timestamps

    seg_speed: list[float | None] = []
    for i in range(n - 1):
        dt = ts[i + 1] - ts[i]
        d = cum[i + 1] - cum[i]
        seg_speed.append(d / dt if dt > 1e-6 else None)
    if all(v is None for v in seg_speed):
        return [mid] * n
    last_valid = next(v for v in seg_speed if v is not None)
    filled = []
    for v in seg_speed:
        last_valid = v if v is not None else last_valid
        filled.append(last_valid)
    point_speed = ([filled[0]]
                   + [(filled[i - 1] + filled[i]) / 2.0 for i in range(1, n - 1)]
                   + [filled[-1]])

    smoothed = _smooth_along_arclength(point_speed, cum, speed_smooth_mm)
    lo, hi = min(smoothed), max(smoothed)
    if hi - lo < 1e-9:
        return [mid] * n
    # slow -> width_max, fast -> width_min
    return [width_max - (width_max - width_min) * (v - lo) / (hi - lo) for v in smoothed]


def _velocity_outline(pts: list[tuple[float, float, float]], width_min: float,
                       width_max: float, speed_smooth_mm: float) -> Path | None:
    """The swollen outline: left offsets forward, a round end cap, right
    offsets back, a round start cap, closed — one path per stroke. Built by
    hand (no shapely) so a self-intersecting outline is left as-is; the
    plotter draws it fine and shapely's cleanup would erase the very
    pooling/tapering shape this mode exists to draw."""
    if len(pts) < 2:
        return None
    xy = [(x, y) for x, y, _t in pts]
    ts = [t for _x, _y, t in pts]
    cum = [0.0]
    for a, b in zip(xy, xy[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    if cum[-1] < 1e-9:
        return None  # zero-length stroke: no tangent to build an outline from

    widths = _velocity_widths(xy, ts, cum, width_min, width_max, speed_smooth_mm)
    tangents = _tangents(xy)
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for (x, y), (tx, ty), w in zip(xy, tangents, widths):
        nx, ny = -ty, tx  # unit normal, 90deg CCW of tangent
        hw = w / 2.0
        left.append((x + nx * hw, y + ny * hw))
        right.append((x - nx * hw, y - ny * hw))

    n_cap = 10

    def cap(center: tuple[float, float], tangent: tuple[float, float],
            normal: tuple[float, float], hw: float, sign: float) -> list[tuple[float, float]]:
        # semicircle from +normal to -normal, bulging `sign*tangent` —
        # sign=+1 (end cap) bulges forward past the tip, sign=-1 (start cap)
        # bulges backward before the first point. Endpoints (k=0, k=n_cap)
        # are omitted — they coincide with the adjoining left/right offsets.
        cx, cy = center
        tx, ty = tangent
        nx, ny = normal
        out = []
        for k in range(1, n_cap):
            theta = math.pi * k / n_cap
            out.append((cx + hw * (math.cos(theta) * nx + math.sin(theta) * sign * tx),
                        cy + hw * (math.cos(theta) * ny + math.sin(theta) * sign * ty)))
        return out

    end_cap = cap(xy[-1], tangents[-1], (-tangents[-1][1], tangents[-1][0]), widths[-1] / 2.0, 1.0)
    start_cap = cap(xy[0], tangents[0], (tangents[0][1], -tangents[0][0]), widths[0] / 2.0, -1.0)
    outline = left + end_cap + list(reversed(right)) + start_cap
    outline.append(outline[0])  # exact closure — occlusion masks depend on first==last
    return Path(points=outline, filled=False)


@register_source
class DrawingSource(SourceModule):
    id = "drawing"
    label = "Drawing (pointer)"
    description = "Freehand pointer strokes captured on the canvas."
    Params = DrawingParams

    def generate(self, params: DrawingParams) -> PathDocument:
        strokes = _prepare_strokes(params.strokes)
        if not strokes:
            # an empty layer is a deliberate state ("＋ empty layer" button):
            # a blank target the draw tool appends strokes into
            return PathDocument(layers=[], width=BED_WIDTH, height=BED_HEIGHT,
                                source="drawing (empty)")
        paths: list[Path] = []
        for stroke in strokes:
            pts = _resample(stroke, params.resample_mm)
            pts = _smooth(pts, params.smooth)
            if params.render == "velocity_tube":
                if params.keep_centerline:
                    paths.append(Path(points=[(x, y) for x, y, _t in pts], filled=False))
                outline = _velocity_outline(pts, params.width_min, params.width_max, params.speed_smooth_mm)
                if outline is not None:
                    paths.append(outline)
            else:
                paths.append(Path(points=[(x, y) for x, y, _t in pts], filled=False))
        return PathDocument(
            layers=[Layer(id=1, name="drawing", paths=paths)],
            width=BED_WIDTH, height=BED_HEIGHT,
            source=f"drawing {len(paths)} stroke(s)",
        )
