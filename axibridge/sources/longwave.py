"""Longwave (plotterfun): sinusoidal scan lines that appear where darkness
crosses a per-line threshold, with hysteresis to suppress flicker. Depth > 1
cycles several thresholds for a layered, woodgrain-like density."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import Field

from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageSampler, PixelGenParams, pixel_doc


class LongwaveParams(PixelGenParams):
    wave_speed: float = Field(default=20, ge=1, le=100, title="Wave speed")
    wave_amplitude: float = Field(default=10, ge=0, le=50, title="Wave amplitude")
    step_size: float = Field(default=5, ge=1, le=20, title="Step size (px)",
                             description="Half the gap between wave lines")
    simplify: float = Field(default=10, ge=1, le=50, title="Simplify",
                            description="Hysteresis — higher ignores small flickers")
    depth: int = Field(default=1, ge=1, le=8, title="Depth",
                       description="Threshold bands cycled across lines")
    direction: Literal["vertical", "horizontal", "both"] = Field(
        default="vertical", title="Direction",
        json_schema_extra={"viewOrient": True})


@register_source
class Longwave(SourceModule):
    id = "longwave"
    label = "Longwave"
    description = "Sinusoidal scan lines gated by darkness with hysteresis."
    Params = LongwaveParams

    def generate(self, params: LongwaveParams) -> PathDocument:
        p = params
        sam = ImageSampler(p)
        w, h = sam.w, sam.h
        spacing = 2 * p.step_size
        freq = p.wave_speed ** 0.8 / w
        amp = p.wave_amplitude / 50 / freq
        t = [128 + i * 128 / p.depth for i in range(p.depth)]
        thresholds = t + t[:-1][::-1]
        lines: list[list[tuple[float, float]]] = []
        ln = 0

        def pass_(vertical_lines: bool, base_frac: float) -> None:
            nonlocal ln
            # vertical lines sweep start-x across the width and march down y
            across, along = (w, h) if vertical_lines else (h, w)
            s = -amp
            while s <= across + amp:
                report_progress(base_frac + 0.5 * (s + amp) / (across + 2 * amp))
                threshold = thresholds[ln % len(thresholds)]
                ln += 1
                hysteresis = 0.0
                line: list[tuple[float, float]] = []
                for i in range(along):
                    n = s + math.sin(i * freq) * amp
                    x, y = (n, i) if vertical_lines else (i, n)
                    hysteresis += 1 if sam(x, y) > threshold else -1
                    hysteresis = max(-p.simplify, min(p.simplify, hysteresis))
                    if 0 < n < across and hysteresis > 0:
                        line.append((x, y))
                    elif line:
                        lines.append(line)
                        line = []
                if line:
                    lines.append(line)
                s += spacing

        if p.direction in ("vertical", "both"):
            pass_(True, 0.0)
        if p.direction in ("horizontal", "both"):
            pass_(False, 0.5)
        return pixel_doc(p, w, h, lines, "longwave", f"longwave {p.image}")
