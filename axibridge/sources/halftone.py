"""Halftone (plotterfun): classic dot screen — circles (or diamonds) on a
grid, sized by local darkness over a blurred copy of the image."""

from __future__ import annotations

from pydantic import Field

from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageSampler, PixelGenParams, circle, pixel_doc, working_dims


class HalftoneParams(PixelGenParams):
    divisions: int = Field(default=25, ge=10, le=100, title="Divisions",
                           description="Cells across the page — the screen pitch")
    factor: float = Field(default=100, ge=10, le=400, title="Factor (%)",
                          description="Dot size relative to the cell")
    cutoff: float = Field(default=0, ge=0, le=254, title="Cutoff",
                          description="Skip dots lighter than this")
    interlaced: bool = Field(default=False, title="Interlaced",
                             description="Offset every other row by half a cell")
    diamond: bool = Field(default=False, title="Diamonds instead of circles")


@register_source
class Halftone(SourceModule):
    id = "halftone"
    orientation = "param"
    label = "Halftone"
    description = "Dot screen: circles or diamonds sized by local darkness."
    Params = HalftoneParams

    def generate(self, params: HalftoneParams) -> PathDocument:
        p = params
        w, h = working_dims(p)
        major = (w + h) / p.divisions / 2
        # plotterfun stack-blurs at half the cell size before sampling
        sam = ImageSampler(p, blur_px=major / 2)
        hm = major / 2
        lines: list[list[tuple[float, float]]] = []
        tog = False

        y = hm
        while y < h:
            report_progress(y / h)
            tog = not tog
            x = hm + (major / 2 if p.interlaced and tog else 0)
            while x < w:
                z = sam(x, y)
                if z >= p.cutoff:
                    r = z * hm / 255 * p.factor / 100
                    if p.diamond:
                        lines.append([(x - r, y), (x, y - r), (x + r, y),
                                      (x, y + r), (x - r, y)])
                    else:
                        # plotterfun draws the circle a half-cell up-left; kept
                        lines.append(circle(x - hm / 2, y - hm / 2, r))
                x += major
            y += major
        return pixel_doc(p, w, h, lines, "halftone", f"halftone {p.image}")
