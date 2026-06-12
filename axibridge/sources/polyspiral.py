"""Polygon spiral (plotterfun): one continuous polygonal spiral from the
centre outward, oscillating with local darkness — a single-path portrait."""

from __future__ import annotations

import math

from pydantic import Field

from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageSampler, PixelGenParams, pixel_doc

#: hard stop: at the smallest spacing the spiral is ~300k points; never spin forever
_MAX_POINTS = 400_000


class PolyspiralParams(PixelGenParams):
    sides: int = Field(default=4, ge=3, le=8, title="Polygon sides")
    frequency: float = Field(default=150, ge=5, le=256, title="Frequency",
                             description="Lower wiggles faster in dark areas")
    amplitude: float = Field(default=1, ge=0.1, le=5, title="Amplitude")
    spacing: float = Field(default=1, ge=0.5, le=5, title="Spacing (px)",
                           description="Step length — also scales the spiral pitch")


@register_source
class Polyspiral(SourceModule):
    id = "polyspiral"
    label = "Polygon spiral"
    description = "One continuous polygonal spiral, oscillating with darkness."
    Params = PolyspiralParams

    def generate(self, params: PolyspiralParams) -> PathDocument:
        p = params
        sam = ImageSampler(p)
        w, h = sam.w, sam.h
        cx, cy = w / 2, h / 2
        points: list[tuple[float, float]] = [(cx, cy)]

        x, y = cx, cy
        theta = 0.0
        a = 0.0
        travelled = 0
        seg_len = 1
        incr_theta = math.tau / p.sides
        incr_len = int(10 / p.sides + 0.5)  # JS Math.round, not banker's
        max_r = math.hypot(w, h) / 2

        while 0 < x < w and 0 < y < h and len(points) < _MAX_POINTS:
            z = sam(x, y)
            r = p.amplitude * z * 0.02 * p.spacing
            a += z / p.frequency
            disp = math.sin(a) * r
            points.append((x - disp * math.sin(theta), y + disp * math.cos(theta)))
            travelled += 1
            if travelled >= seg_len:
                travelled = 0
                theta += incr_theta
                seg_len += incr_len
                report_progress(min(math.hypot(x - cx, y - cy) / max_r, 1.0))
            x += p.spacing * math.cos(theta)
            y += p.spacing * math.sin(theta)

        return pixel_doc(p, w, h, [points], "polyspiral", f"polyspiral {p.image}")
