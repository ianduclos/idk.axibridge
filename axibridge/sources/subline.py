"""Subline (plotterfun): each scan line is a bundle of sublines that fan
apart over dark areas — out along the top, back along the bottom."""

from __future__ import annotations

from pydantic import Field

from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageSampler, PixelGenParams, pixel_doc


class SublineParams(PixelGenParams):
    line_count: int = Field(default=50, ge=10, le=200, title="Line count")
    sublines: int = Field(default=3, ge=1, le=10, title="Sublines",
                          description="Strands per line")
    amplitude: float = Field(default=1, ge=0.1, le=5, title="Amplitude")
    sampling: float = Field(default=1, ge=0.5, le=5, title="Sampling (px)",
                            description="Step along the line — smaller is smoother")


@register_source
class Subline(SourceModule):
    id = "subline"
    orientation = "param"
    label = "Subline"
    description = "Scan lines made of strands that fan apart over dark areas."
    Params = SublineParams

    def generate(self, params: SublineParams) -> PathDocument:
        p = params
        sam = ImageSampler(p)
        w, h = sam.w, sam.h
        amp = p.amplitude / p.sublines / p.line_count
        incr_y = max(h // p.line_count, 1)
        lines: list[list[tuple[float, float]]] = []

        for y in range(0, h, incr_y):
            report_progress(y / h)
            for j in range(p.sublines):
                line: list[tuple[float, float]] = []
                x = 0.0
                while x <= w:
                    line.append((x, y + amp * j * sam(x, y)))
                    x += p.sampling
                x = float(w)
                while x >= 0:
                    line.append((x, y - amp * j * sam(x, y)))
                    x -= p.sampling
                lines.append(line)
        return pixel_doc(p, w, h, lines, "subline", f"subline {p.image}")
