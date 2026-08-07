"""Squiggle left-right (plotterfun): the classic squigglecam — boustrophedon
scan lines that oscillate faster and wider over dark areas."""

from __future__ import annotations

import math

from pydantic import Field

from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageSampler, PixelGenParams, pixel_doc


class SquiggleLRParams(PixelGenParams):
    frequency: float = Field(default=150, ge=5, le=256, title="Frequency",
                             description="Lower oscillates faster in dark areas")
    line_count: int = Field(default=50, ge=10, le=200, title="Line count")
    amplitude: float = Field(default=1, ge=0.1, le=5, title="Amplitude")
    sampling: float = Field(default=1, ge=0.5, le=2.9, title="Sampling (px)",
                            description="Step along the line — smaller is smoother")
    join_ends: bool = Field(default=False, title="Join ends",
                            description="One continuous path, never lifting the pen")


@register_source
class SquiggleLR(SourceModule):
    id = "squiggle_lr"
    orientation = "param"
    label = "Squiggle (left-right)"
    description = "Squigglecam: scan lines oscillating with darkness, alternating direction."
    Params = SquiggleLRParams

    def generate(self, params: SquiggleLRParams) -> PathDocument:
        p = params
        sam = ImageSampler(p)
        w, h = sam.w, sam.h
        spacing = max(h // p.line_count, 1)
        lines: list[list[tuple[float, float]]] = []
        joined: list[tuple[float, float]] = []
        toggle = False

        for y in range(0, h, spacing):
            report_progress(y / h)
            a = 0.0
            toggle = not toggle
            line: list[tuple[float, float]] = [(0.0 if toggle else float(w), float(y))]
            x = p.sampling if toggle else w - p.sampling
            while (toggle and x <= w) or (not toggle and x >= 0):
                z = sam(x, y)
                r = p.amplitude * z / p.line_count
                a += z / p.frequency
                line.append((x, y + math.sin(a) * r))
                x += p.sampling if toggle else -p.sampling
            if p.join_ends:
                joined.extend(line)
            else:
                lines.append(line)

        if p.join_ends:
            lines = [joined]
        return pixel_doc(p, w, h, lines, "squiggle", f"squiggle_lr {p.image}")
