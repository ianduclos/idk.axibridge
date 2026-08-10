"""Fast Marching Contours: an edge-seeded wavefront traced into warped,
image-responsive isochrones, optionally threaded into a few long serpentine
strokes along the image frame.

Where ``fast_marching_topo`` seeds one point and treats brightness as speed
directly (bright = fast = spread-out rings around a center), this source
seeds an entire image EDGE at once — the front starts as a straight line
parallel to that edge and bends as it crosses the image, slowed by dark
detail and hurried through bright detail. Successive contours are, by
construction, "parallel-ish" curves sweeping across the sheet rather than
concentric rings, which is what a plotter-artist technique reverse-engineered
from reference SVGs turned out to look like: dark areas draw dense, bright
areas draw sparse, and where geometry permits, one continuous ~1 mm-jogged
line threads level after level along the left/right (or top/bottom) frame
edge instead of lifting the pen every contour.

The Eikonal solve and marching-squares contour extraction are the same
engine as ``fast_marching_topo`` — see ``_fast_marching.py``'s docstring for
the Roland Blok / FastMarchingTopoPlot (Unlicense) credit on the heap
update. Multi-seed solving (:func:`_fast_marching.travel_time_multi`) and
per-level contour grouping (:func:`_fast_marching.iso_contour_levels`) are
new here, added specifically so this source can seed an edge instead of a
point and thread level-by-level. The 1/(1-intensity) speed mapping (dark =
slow, floored by ``max_speed_ratio``) matches the published padcrafting/
ContourTool project's documented approach — that's an algorithm reference
only, no code taken — but the edge front and the boundary-threading stage
(``_fm_threading.py``) are original to axibridge; ContourTool seeds a point
and has no threading at all.
"""

from __future__ import annotations

import math
from typing import Literal

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
from . import _fm_threading as fmt
from ._pixelgen import ImageBaseParams, luma_grid, pixel_doc

_IMAGE_PROCESSING = IMAGE_PROCESSING_GROUP
_COMPUTATION = {"group": "Computation"}


class FastMarchingContoursParams(ImageBaseParams):
    line_count: int = Field(
        default=200, ge=10, le=500, title="Contour lines",
        description="Number of evenly spaced travel-time levels",
        json_schema_extra=_COMPUTATION,
    )
    source_edge: Literal["top", "bottom", "left", "right"] = Field(
        default="top", title="Source edge",
        description="Image edge the wavefront starts from, seeded all at once",
        json_schema_extra=_COMPUTATION,
    )
    max_speed_ratio: float = Field(
        default=100.0, ge=2.0, le=200.0, title="Max speed ratio",
        description="Fastest (brightest) wave speed relative to the slowest — "
                     "how strongly dark image detail compresses contour spacing",
        json_schema_extra=_COMPUTATION,
    )
    threading: Literal["off", "boundary"] = Field(
        default="boundary", title="Threading",
        description="Join successive contours along the frame into long "
                     "serpentine strokes instead of one pen-lift per level",
        json_schema_extra=_COMPUTATION,
    )
    max_join: float = Field(
        default=30.0, ge=0.0, le=100.0, title="Max join (mm)",
        description="Longest boundary jump threading will bridge between "
                     "two contours before giving up and lifting the pen",
        json_schema_extra=_COMPUTATION,
    )
    min_length: float = Field(
        default=0.5, ge=0.0, le=50.0, title="Min length (mm)",
        description="Drop threaded/unthreaded strokes shorter than this — "
                     "clears pixel-noise fragments left by alpha clipping",
        json_schema_extra=_COMPUTATION,
    )
    smoothing: float = Field(
        default=1.3, ge=0.0, le=20.0, title="Smoothing (mm)",
        description="Gaussian pre-blur of the image, in final paper units. "
                     "Experimental default chosen to resemble reference plots",
        json_schema_extra=_COMPUTATION,
    )
    field_smoothing: float = Field(
        default=0.0, ge=0.0, le=10.0, title="Field smoothing (px)",
        description="Gaussian blur on the solved arrival-time field itself — "
                     "softens 4-neighbour grid artifacts; 0 disables it",
        json_schema_extra=_COMPUTATION,
    )
    resolution: float = Field(
        default=1.0, ge=0.25, le=2.0, title="Resolution ×",
        description="Working-canvas multiplier; finer detail costs more time",
        json_schema_extra=_COMPUTATION,
    )
    clip_transparent: bool = Field(
        default=True, title="Clip transparent areas",
        description="Split contours wherever PNG alpha is below 50%, before threading",
        json_schema_extra=_COMPUTATION,
    )

    invert: bool = Field(
        default=False, title="Invert",
        description="Treat dark image areas as fast instead of slow",
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


def _tone_lut(params: FastMarchingContoursParams) -> np.ndarray:
    tone = image_processing_kwargs(params)
    return np.asarray(
        [apply_image_processing_value(v / 255.0, **tone) for v in range(256)],
        dtype=np.float64,
    )


def _edge_seeds(edge: str, w: int, h: int) -> list[tuple[int, int]]:
    if edge == "top":
        return [(x, 0) for x in range(w)]
    if edge == "bottom":
        return [(x, h - 1) for x in range(w)]
    if edge == "left":
        return [(0, y) for y in range(h)]
    return [(w - 1, y) for y in range(h)]  # "right"


def _line_length(line: list[tuple[float, float]]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in zip(line, line[1:]):
        total += math.hypot(x1 - x0, y1 - y0)
    return total


@register_source
class FastMarchingContours(SourceModule):
    id = "fast_marching_contours"
    orientation = "param"
    label = "Fast marching contours"
    description = "Edge-seeded wavefront contours, optionally threaded into serpentine strokes."
    Params = FastMarchingContoursParams

    def generate(self, params: FastMarchingContoursParams) -> PathDocument:
        p = params
        report_progress(0.01, "Loading image")
        rows, w, h = luma_grid(p, scale=p.resolution)
        image = asset_store.resolve_frame(p.image, p.frame)
        alpha_rows = asset_store.alpha(image, rotate=p.rotate, size=(w, h))
        alpha = None if alpha_rows is None else np.asarray(alpha_rows, dtype=np.float64)

        luma = np.asarray(rows, dtype=np.float64) / 255.0
        # Composite transparency over white before blur/tone, same as topo —
        # clip_transparent controls the OUTPUT, not the sampled field.
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
        # dark (toned -> 0) = slow = dense lines; bright (toned -> 1) = fast =
        # sparse lines. slowness is floored so max_speed_ratio bounds contrast.
        slowness = np.maximum(1.0 - toned, 1.0 / p.max_speed_ratio)
        speed = 1.0 / slowness

        report_progress(0.1, "Fast marching")
        seeds = _edge_seeds(p.source_edge, w, h)
        times = fmm.travel_time_multi(
            speed,
            seeds,
            progress=lambda frac: report_progress(0.1 + 0.45 * frac, "Fast marching"),
        )

        if p.field_smoothing > 0.0:
            report_progress(0.56, "Smoothing field")
            finite = np.isfinite(times)
            if finite.all():
                times = gaussian_filter(times, sigma=p.field_smoothing, mode="nearest")
            elif finite.any():
                fill = float(times[finite].max())
                filled = np.where(finite, times, fill)
                blurred = gaussian_filter(filled, sigma=p.field_smoothing, mode="nearest")
                times = np.where(finite, blurred, times)

        report_progress(0.58, "Tracing contours")
        levels = fmm.iso_contour_levels(
            times,
            p.line_count,
            progress=lambda frac: report_progress(0.58 + 0.2 * frac, "Tracing contours"),
        )

        if p.clip_transparent and alpha is not None:
            report_progress(0.79, "Clipping transparency")
            levels = [fmm.clip_to_alpha(group, alpha) for group in levels]

        if p.threading == "boundary":
            report_progress(0.82, "Threading")
            px_per_mm = w / p.width
            prefer_axis = "x" if p.source_edge in ("top", "bottom") else "y"
            lines = fmt.thread_boundary(
                levels,
                w,
                h,
                max_join=p.max_join * px_per_mm,
                tol=1.5,
                prefer_axis=prefer_axis,
                progress=lambda frac: report_progress(0.82 + 0.15 * frac, "Threading"),
            )
        else:
            report_progress(0.9, "Assembling contours")
            lines = [line for group in levels for line in group]

        if p.min_length > 0.0:
            min_len_px = p.min_length * (w / p.width)
            lines = [line for line in lines if _line_length(line) >= min_len_px]

        report_progress(0.99, "Building paths")
        return pixel_doc(
            p,
            w,
            h,
            lines,
            "fast marching contours",
            f"fast_marching_contours {p.image}",
        )
