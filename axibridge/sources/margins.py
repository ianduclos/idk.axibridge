"""Margins (plotterfun): a grid of short arcs whose bend and swing follow
image darkness — dark areas get wide, rotated arcs."""

from __future__ import annotations

import math

from pydantic import Field

from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageSampler, PixelGenParams, pixel_doc


class MarginsParams(PixelGenParams):
    squiggles: int = Field(default=2000, ge=500, le=10000, title="Squiggles",
                           description="Arc count — sets the sampling grid density")
    max_length: float = Field(default=10, ge=0.1, le=20, title="Max length (px)",
                              description="Arc radius in working pixels")
    min_arc: float = Field(default=10, ge=0, le=180, title="Min arc (°)")
    max_arc: float = Field(default=120, ge=0, le=180, title="Max arc (°)")
    rotation_factor: float = Field(default=0.5, ge=-1, le=1, title="Rotation factor",
                                   description="How much darkness spins each arc")


@register_source
class Margins(SourceModule):
    id = "margins"
    orientation = "param"
    label = "Margins (arc field)"
    description = "Grid of short arcs, bent and spun by image darkness."
    Params = MarginsParams

    def generate(self, params: MarginsParams) -> PathDocument:
        p = params
        sam = ImageSampler(p)
        w, h = sam.w, sam.h
        grid = max(int(math.sqrt(w * h / p.squiggles)), 1)
        min_arc = math.radians(p.min_arc)
        max_arc = math.radians(p.max_arc)
        lines: list[list[tuple[float, float]]] = []

        for y in range(grid, h - grid, grid):
            report_progress(y / h)
            for x in range(grid, w - grid, grid):
                strength = sam(x, y) / 255.0
                arc = min_arc + (max_arc - min_arc) * strength
                base = p.rotation_factor * strength * math.tau
                lines.append([
                    (x + math.cos(theta) * p.max_length, y + math.sin(theta) * p.max_length)
                    for j in range(5)
                    for theta in (base - arc / 2 + arc * j / 4,)
                ])
        return pixel_doc(p, w, h, lines, "margins", f"margins {p.image}")
