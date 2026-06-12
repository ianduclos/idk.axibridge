"""Linescan (plotterfun, algorithm by j-waal): scan lines that draw only
where the image is darker than a threshold — clean, screen-print-like bands."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageSampler, PixelGenParams, pixel_doc


class LinescanParams(PixelGenParams):
    spacing: int = Field(default=5, ge=1, le=20, title="Spacing (px)",
                         description="Gap between scan lines in working pixels")
    threshold: float = Field(default=128, ge=0, le=255, title="Threshold",
                             description="Darkness above this draws")
    min_length: int = Field(default=1, ge=0, le=32, title="Min length (px)",
                            description="Drop segments shorter than this")
    alternate: bool = Field(default=False, title="Alternate direction",
                            description="Reverse every other row (less pen travel)")
    direction: Literal["horizontal", "vertical", "both"] = Field(
        default="horizontal", title="Direction")


@register_source
class Linescan(SourceModule):
    id = "linescan"
    label = "Linescan"
    description = "Scan lines drawn only where the image is dark — banded shading."
    Params = LinescanParams

    def generate(self, params: LinescanParams) -> PathDocument:
        p = params
        sam = ImageSampler(p)
        lines: list[list[tuple[float, float]]] = []

        def pass_(vertical: bool, base_frac: float) -> None:
            along = sam.h if vertical else sam.w
            across = sam.w if vertical else sam.h
            pt = (lambda a, b: (b, a)) if vertical else (lambda a, b: (a, b))
            toggle = True
            for j in range(0, across, p.spacing):
                report_progress(base_frac + 0.5 * j / across)
                row: list[list[tuple[float, float]]] = []
                start = None
                for i in range(along):
                    dark = sam(*pt(i, j)) > p.threshold
                    if dark and start is None:
                        start = i
                    elif not dark and start is not None:
                        if i - start > p.min_length:
                            seg = [pt(start, j), pt(i, j)]
                            row.append(seg if toggle else seg[::-1])
                        start = None
                if start is not None and along - start > p.min_length:
                    seg = [pt(start, j), pt(along, j)]
                    row.append(seg if toggle else seg[::-1])
                lines.extend(row if toggle else row[::-1])
                if p.alternate and row:
                    toggle = not toggle

        if p.direction in ("horizontal", "both"):
            pass_(False, 0.0)
        if p.direction in ("vertical", "both"):
            pass_(True, 0.5)
        return pixel_doc(p, sam.w, sam.h, lines, "linescan", f"linescan {p.image}")
