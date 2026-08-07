"""Waves (plotterfun): parallel lines at any angle that push apart over
bright areas — a flowing, topographic shading. Unlike the original, lines
are split where they leave the canvas instead of bridging the gap."""

from __future__ import annotations

import math

from pydantic import Field

from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageSampler, PixelGenParams, pixel_doc


class WavesParams(PixelGenParams):
    angle: float = Field(default=0, ge=0, le=360, title="Angle (°)",
                         json_schema_extra={"viewAngle": 360})
    step_size: float = Field(default=5, ge=1, le=20, title="Step size (px)",
                             description="Base gap between neighbouring lines")


@register_source
class Waves(SourceModule):
    id = "waves"
    orientation = "param"
    label = "Waves"
    description = "Angled parallel lines repelled by bright areas."
    Params = WavesParams

    def generate(self, params: WavesParams) -> PathDocument:
        p = params
        sam = ImageSampler(p)
        w, h = sam.w, sam.h
        a = p.step_size
        cos = math.cos(math.radians(p.angle))
        sin = math.sin(math.radians(p.angle))
        L = int(math.sqrt(w * w + h * h))

        def inside(x: float, y: float) -> bool:
            return 0 <= x < w and 0 <= y < h

        def pix(x: float, y: float) -> float:
            return (255 - sam(x, y)) * a / 255 if inside(x, y) else 0.0

        # initial straight centre line, then march displaced copies both ways
        first = []
        x, y = (w - L * cos) / 2, (h - L * sin) / 2
        for _ in range(L):
            x += cos
            y += sin
            first.append((x, y))

        half = int(L / 2 / a)

        def march(start: list[tuple[float, float]], sign: float, base_frac: float):
            out, last = [], start
            for j in range(half):
                report_progress(base_frac + 0.5 * j / max(half, 1))
                line = []
                for lx, ly in last:
                    nx = lx + sign * sin * a
                    ny = ly - sign * cos * a
                    z = pix(nx, ny)
                    line.append((nx + sign * sin * z, ny - sign * cos * z))
                out.append(line)
                last = line
            return out

        left = [first] + march(first, +1, 0.0)
        right = march(first, -1, 0.5)
        ordered = right[::-1] + left

        # clip to the canvas, splitting at gaps (no bridging strokes)
        lines: list[list[tuple[float, float]]] = []
        for line in ordered:
            run: list[tuple[float, float]] = []
            for pt in line:
                if inside(*pt):
                    run.append(pt)
                elif len(run) > 1:
                    lines.append(run)
                    run = []
                else:
                    run = []
            if len(run) > 1:
                lines.append(run)
        return pixel_doc(p, w, h, lines, "waves", f"waves {p.image}")
