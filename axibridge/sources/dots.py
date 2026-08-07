"""Dots (plotterfun, algorithm by Tim Koop): stochastic stippling with short
strokes — darker pixels are more likely to receive a dash, whose direction is
fixed or per-dot random. Seeded, so regeneration is reproducible."""

from __future__ import annotations

import random

from pydantic import Field

from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageSampler, PixelGenParams, pixel_doc


class DotsParams(PixelGenParams):
    resolution: int = Field(default=2, ge=1, le=20, title="Resolution (px)",
                            description="Grid pitch — also the stroke length")
    line_direction: float = Field(default=0, ge=0, le=180, title="Line direction (°)",
                                  json_schema_extra={"viewAngle": 180})
    random_direction: bool = Field(default=False, title="Random direction")
    seed: int = Field(default=50, ge=0, le=9999, title="Seed")


@register_source
class Dots(SourceModule):
    id = "dots"
    orientation = "param"
    label = "Dots (stipple strokes)"
    description = "Probabilistic short strokes — darker areas stipple denser."
    Params = DotsParams

    def generate(self, params: DotsParams) -> PathDocument:
        p = params
        sam = ImageSampler(p)
        sp = p.resolution
        dot_rand = random.Random(p.seed)
        dir_rand = random.Random(p.seed + 1)

        if p.line_direction < 90:
            x_off, y_off = p.line_direction / 90.0 * sp, sp
        else:
            x_off, y_off = sp, sp - (p.line_direction - 90) / 90.0 * sp

        lines: list[list[tuple[float, float]]] = []
        for y in range(0, sam.h - sp, sp):
            report_progress(y / sam.h)
            for x in range(0, sam.w - sp + 1, sp):
                prob = (sam(x, y) / 255.0) ** 3 * 0.5 * sp
                if prob > dot_rand.random():
                    if p.random_direction:
                        d = dir_rand.random()
                        if dir_rand.random() > 0.5:
                            lines.append([(x + d * sp, y), (x + sp - d * sp, y + sp)])
                        else:
                            lines.append([(x, y + d * sp), (x + sp, y + sp - d * sp)])
                    else:
                        lines.append([(x + x_off, y + y_off), (x + sp - x_off, y + sp - y_off)])
        return pixel_doc(p, sam.w, sam.h, lines, "dots", f"dots {p.image}")
