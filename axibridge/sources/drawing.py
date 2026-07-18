"""Drawing (pointer) — pointer strokes captured on the canvas become a
generator layer's source geometry (docs/plans/draw-mode.md).

Why a layer, not a tool: the moment a drawing is an ordinary layer it
inherits occlusion, pens, estimates, undo, regions, A/B capture, tweening
and the timeline for free — nothing here adds a second geometry path to
the plotter (see CLAUDE.md's single-resolve invariant).

Strokes are geometry-as-params, mirroring api.py's ``WorkbenchBody``/
``_drawing_paths`` point-budget-and-bed-clamp pattern: each point is
``[x_mm, y_mm, t_s]`` (machine-frame mm, seconds since that stroke's
pen-down). Timestamps are captured now even though nothing reads them yet
— a later "velocity tube" render mode derives speed from them and they
cannot be recovered after capture, so ``render`` is a one-value enum
already: a follow-up plan adds ``"velocity_tube"``.
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
    render: Literal["centerline"] = Field(
        default="centerline", title="Render",
        description="How strokes become paths — a follow-up plan adds "
                    "velocity_tube, driven by the captured per-point timing",
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
    x/y. Ports workbench.js's ``resample`` (see static/js/workbench.js) with
    a third channel. Endpoints are always preserved exactly."""
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


@register_source
class DrawingSource(SourceModule):
    id = "drawing"
    label = "Drawing (pointer)"
    description = "Freehand pointer strokes captured on the canvas."
    Params = DrawingParams

    def generate(self, params: DrawingParams) -> PathDocument:
        strokes = _prepare_strokes(params.strokes)
        if not strokes:
            raise ValueError("draw a stroke first")
        paths: list[Path] = []
        for stroke in strokes:
            pts = _resample(stroke, params.resample_mm)
            pts = _smooth(pts, params.smooth)
            paths.append(Path(points=[(x, y) for x, y, _t in pts], filled=False))
        return PathDocument(
            layers=[Layer(id=1, name="drawing", paths=paths)],
            width=BED_WIDTH, height=BED_HEIGHT,
            source=f"drawing {len(paths)} stroke(s)",
        )
