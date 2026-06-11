"""Perspective: tilt the layer like a sheet in 3-D and project it back to
the paper — the "looking at a plane from an angle" look.

Geometry math: points are lifted onto a plane through the pivot, rotated
about the paper's x then y axis, then centrally projected from a camera
``distance`` mm above the pivot. Straight lines stay straight under central
projection, so no resampling is needed and point counts are preserved
(closure and ``filled`` survive trivially).

The singularity (plane edge swinging through the camera plane) is kept out
of reach: tilt is bounded to ±75° and the projection denominator is clamped,
so extreme settings flatten instead of exploding to infinity.

Pivot: the centroid of the layer's bounding box by default, optionally
offset — so a tilt reads as "the sheet leans away" rather than the geometry
flying off the bed.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect


class PerspectiveParams(BaseModel):
    tilt_x: float = Field(default=35.0, ge=-75.0, le=75.0, title="Tilt x (degrees)",
                          description="Rotate about the horizontal axis — positive leans the top away")
    tilt_y: float = Field(default=0.0, ge=-75.0, le=75.0, title="Tilt y (degrees)",
                          description="Rotate about the vertical axis")
    distance: float = Field(default=300.0, ge=50.0, le=2000.0, title="Camera distance (mm)",
                            description="Closer = stronger perspective; far = near-isometric")
    pivot_dx: float = Field(default=0.0, ge=-200.0, le=200.0, title="Pivot offset x (mm)",
                            description="Shift the tilt axis off the bbox centre",
                            json_schema_extra={"viewAxis": True})
    pivot_dy: float = Field(default=0.0, ge=-200.0, le=200.0, title="Pivot offset y (mm)",
                            json_schema_extra={"viewAxis": True})


@register_effect
class Perspective(EffectModule):
    id = "perspective"
    label = "Perspective"
    description = "Tilt the layer like a 3-D plane and project it back onto the paper."
    Params = PerspectiveParams

    def apply(self, paths: list[Path], params: PerspectiveParams, ctx: EffectContext) -> list[Path]:
        pts_all = [pt for p in paths for pt in p.points]
        if not pts_all or (params.tilt_x == 0 and params.tilt_y == 0):
            return list(paths)
        xs = [x for x, _ in pts_all]
        ys = [y for _, y in pts_all]
        cx = (min(xs) + max(xs)) / 2 + params.pivot_dx
        cy = (min(ys) + max(ys)) / 2 + params.pivot_dy
        ax, ay = math.radians(params.tilt_x), math.radians(params.tilt_y)
        cosx, sinx = math.cos(ax), math.sin(ax)
        cosy, siny = math.cos(ay), math.sin(ay)
        d = params.distance

        def project(x: float, y: float) -> tuple[float, float]:
            dx, dy = x - cx, y - cy
            # rotate about the x axis (paper-horizontal), then the y axis
            ry, rz = dy * cosx, dy * sinx
            rx = dx * cosy + rz * siny
            rz = -dx * siny + rz * cosy
            # central projection; clamp the denominator so the edge nearest
            # the camera flattens instead of diverging
            s = d / max(d - rz, d * 0.08)
            return (cx + rx * s, cy + ry * s)

        out = []
        for p in paths:
            moved = [project(x, y) for x, y in p.points]
            out.append(Path(points=moved, filled=p.filled))
        return out
