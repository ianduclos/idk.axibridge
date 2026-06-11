"""Worked example of a Source module: Lissajous / harmonograph curves.

This file is the template for writing your own generator — a params model,
a class with ``generate()``, and the ``@register_source`` decorator. Nothing
else is required; the UI controls come from the params model's JSON Schema.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source


class LissajousParams(BaseModel):
    freq_x: float = Field(default=3, ge=1, le=32, title="X frequency")
    freq_y: float = Field(default=4, ge=1, le=32, title="Y frequency")
    phase_deg: float = Field(default=90, ge=0, le=360, title="Phase (degrees)")
    damping: float = Field(
        default=0.0, ge=0.0, le=2.0, title="Damping",
        description="Exponential decay — turns a Lissajous figure into a harmonograph trace",
    )
    turns: float = Field(default=1, ge=0.1, le=60, title="Turns", description="How many 2π cycles to trace")
    size: float = Field(default=120, ge=10, le=400, title="Size (mm)")
    margin: float = Field(default=20, ge=0, le=100, title="Margin (mm)")
    points_per_turn: int = Field(default=720, ge=32, le=4096, title="Resolution (points/turn)")


@register_source
class Lissajous(SourceModule):
    id = "lissajous"
    label = "Lissajous / harmonograph"
    description = "Damped Lissajous curve — a one-path stress test for speed and cornering params."
    Params = LissajousParams

    def generate(self, params: LissajousParams) -> PathDocument:
        p = params
        n = max(int(p.points_per_turn * p.turns), 2)
        r = p.size / 2.0
        cx = cy = p.margin + r
        phase = math.radians(p.phase_deg)
        pts = []
        for i in range(n + 1):
            t = (i / n) * p.turns * 2 * math.pi
            decay = math.exp(-p.damping * t / (2 * math.pi))
            x = cx + r * decay * math.sin(p.freq_x * t + phase)
            y = cy + r * decay * math.sin(p.freq_y * t)
            pts.append((x, y))
        side = p.size + 2 * p.margin
        return PathDocument(
            layers=[Layer(id=1, name="lissajous", color="#0066cc", paths=[Path(points=pts)])],
            width=side,
            height=side,
            source=f"lissajous {p.freq_x}:{p.freq_y}",
        )
