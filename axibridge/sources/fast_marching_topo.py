"""Fast Marching Topo: image brightness controls the spacing of seeded
topographic contour lines.

A wavefront expands from one point through a speed field derived from the
uploaded image.  Bright pixels are fast, spreading successive iso-time lines
apart; dark pixels are slow, compressing the lines and concentrating detail.

This is an axibridge-native adaptation of Roland Blok's FastMarchingTopoPlot
(https://github.com/rolandblok/FastMarchingTopoPlot), released under the
Unlicense.  The source keeps the algorithm but adopts the shared 800-pixel
working canvas, millimetre smoothing, image-processing controls, asset/frame
handling, progress events, and ordinary layer placement.
"""

from __future__ import annotations

import numpy as np
from pydantic import Field
from scipy.ndimage import gaussian_filter

from ..assets import asset_store
from ..image_processing import (
    IMAGE_PROCESSING_GROUP,
    apply_image_processing_value,
    image_processing_kwargs,
)
from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from . import _fast_marching as fmm
from ._pixelgen import ImageBaseParams, luma_grid, pixel_doc

_IMAGE_PROCESSING = IMAGE_PROCESSING_GROUP
_COMPUTATION = {"group": "Computation"}


class FastMarchingTopoParams(ImageBaseParams):
    line_count: int = Field(
        default=200, ge=10, le=500, title="Contour lines",
        description="Number of evenly spaced travel-time levels",
        json_schema_extra=_COMPUTATION,
    )
    speed_offset: float = Field(
        default=0.1, ge=0.01, le=1.0, title="Speed offset",
        description="Minimum wave speed; higher values make image tone less influential",
        json_schema_extra=_COMPUTATION,
    )
    seed_x: float = Field(
        default=0.5, ge=0.0, le=1.0, title="Center X",
        description="Horizontal wave origin, normalized across the image",
        json_schema_extra=_COMPUTATION,
    )
    seed_y: float = Field(
        default=0.5, ge=0.0, le=1.0, title="Center Y",
        description="Vertical wave origin, normalized across the image",
        json_schema_extra=_COMPUTATION,
    )
    smoothing: float = Field(
        default=0.0, ge=0.0, le=20.0, title="Smoothing (mm)",
        description="Gaussian pre-blur in final paper units",
        json_schema_extra=_COMPUTATION,
    )
    resolution: float = Field(
        default=1.0, ge=0.25, le=2.0, title="Resolution ×",
        description="Working-canvas multiplier; finer detail costs more time",
        json_schema_extra=_COMPUTATION,
    )
    clip_transparent: bool = Field(
        default=True, title="Clip transparent areas",
        description="Split contours wherever PNG alpha is below 50%",
        json_schema_extra=_COMPUTATION,
    )

    invert: bool = Field(
        default=False, title="Invert",
        description="Compress contours in light areas instead",
        json_schema_extra=_IMAGE_PROCESSING,
    )
    brightness: float = Field(
        default=0.0, ge=-100.0, le=100.0, title="Brightness",
        json_schema_extra=_IMAGE_PROCESSING,
    )
    contrast: float = Field(
        default=0.0, ge=-100.0, le=100.0, title="Contrast",
        json_schema_extra=_IMAGE_PROCESSING,
    )
    gamma: float = Field(
        default=1.0, ge=0.1, le=5.0, title="Gamma",
        json_schema_extra=_IMAGE_PROCESSING,
    )
    black_point: float = Field(
        default=0.0, ge=0.0, le=1.0, title="Black point",
        json_schema_extra=_IMAGE_PROCESSING,
    )
    white_point: float = Field(
        default=1.0, ge=0.0, le=1.0, title="White point",
        json_schema_extra=_IMAGE_PROCESSING,
    )


def _tone_lut(params: FastMarchingTopoParams) -> np.ndarray:
    tone = image_processing_kwargs(params)
    return np.asarray(
        [apply_image_processing_value(v / 255.0, **tone) for v in range(256)],
        dtype=np.float64,
    )


@register_source
class FastMarchingTopo(SourceModule):
    id = "fast_marching_topo"
    orientation = "param"
    label = "Fast marching topo"
    description = "Seeded topographic contours compressed by dark image detail."
    Params = FastMarchingTopoParams

    def generate(self, params: FastMarchingTopoParams) -> PathDocument:
        p = params
        report_progress(0.01, "Loading image")
        rows, w, h = luma_grid(p, scale=p.resolution)
        image = asset_store.resolve_frame(p.image, p.frame)
        alpha_rows = asset_store.alpha(image, rotate=p.rotate, size=(w, h))
        alpha = None if alpha_rows is None else np.asarray(alpha_rows, dtype=np.float64)

        luma = np.asarray(rows, dtype=np.float64) / 255.0
        # Browser canvas extraction (and the upstream source) composites PNG
        # transparency over white before blur/tone.  Keep that behavior even
        # when clipping is disabled; the toggle controls output, not sampling.
        if alpha is not None:
            luma = luma * alpha + (1.0 - alpha)

        blur_px = p.smoothing * w / p.width
        if blur_px > 0.0:
            report_progress(0.04, "Smoothing")
            luma = gaussian_filter(luma, sigma=blur_px, mode="nearest")

        report_progress(0.08, "Tone and speed")
        byte = np.clip(np.round(luma * 255.0), 0, 255).astype(np.uint8)
        toned = _tone_lut(p)[byte]
        if p.invert:
            toned = 1.0 - toned
        speed = toned + p.speed_offset

        sx = round(p.seed_x * (w - 1))
        sy = round(p.seed_y * (h - 1))
        report_progress(0.1, "Fast marching")
        times = fmm.travel_time(
            speed,
            sx,
            sy,
            progress=lambda frac: report_progress(0.1 + 0.68 * frac, "Fast marching"),
        )

        report_progress(0.8, "Tracing contours")
        lines = fmm.iso_contours(
            times,
            p.line_count,
            progress=lambda frac: report_progress(0.8 + 0.17 * frac, "Tracing contours"),
        )
        if p.clip_transparent and alpha is not None:
            report_progress(0.98, "Clipping transparency")
            lines = fmm.clip_to_alpha(lines, alpha)

        report_progress(0.99, "Building paths")
        return pixel_doc(
            p,
            w,
            h,
            lines,
            "fast marching topo",
            f"fast_marching_topo {p.image}",
        )
