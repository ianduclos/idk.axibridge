"""Shared scaffolding for the plotterfun-family image generators.

These sources are ports of mitxela's plotterfun generators
(https://github.com/mitxela/plotterfun, MIT licence): each samples an
uploaded image asset for per-pixel "darkness" and traces a line pattern
over it. They work in a fixed pixel space — the asset is resampled so the
working width is ``WORK_W`` px (plotterfun's canvas width), so every
px-calibrated parameter (spacing, amplitude, …) means the same thing for
any source resolution — and the result is scaled to ``width`` mm on output
(height follows the image aspect ratio, exactly like image_threshold).

``ImageSampler`` replicates plotterfun's ``pixelProcessor`` tone pipeline:
brightness, contrast (the 259-curve), optional invert, min/max clamps,
flattened to a *darkness* value in 0..255 (255 = draw hardest); sampling
outside the image returns 0. The shared image-processing fields carry
``json_schema_extra={"group": "Image processing"}`` — forms.js renders
grouped fields in a collapsed <details>, keeping ten near-identical forms
uncrammed.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

from ..assets import asset_store
from ..image_processing import (
    IMAGE_PROCESSING_GROUP,
    apply_image_processing_value,
    image_processing_kwargs,
)
from ..model import Layer, Path, PathDocument

#: plotterfun's canvas width: its slider ranges are calibrated against this.
WORK_W = 800
#: very tall images cap here instead (working width shrinks to keep aspect).
MAX_H = 1600

_IMAGE_PROCESSING = IMAGE_PROCESSING_GROUP


class ImageBaseParams(BaseModel):
    """Image selection + placement, shared by every pixel-space generator."""

    image: str = Field(default="", title="Image (asset)",
                       description="Uploaded image asset that drives the pattern",
                       json_schema_extra={"format": "asset"})
    rotate: Literal[0, 90, 180, 270] = Field(
        default=0, title="Rotate image (°)",
        description="Image rotation as seen in the current view",
        json_schema_extra={"viewRotate": True})
    width: float = Field(default=150.0, ge=10, le=400, title="Width (mm)",
                         description="Height follows the image aspect ratio",
                         json_schema_extra={"viewSize": True})
    frame: float = Field(default=0.0, ge=0.0, le=1.0, title="Frame",
                         description="Position in an image sequence (0=first, 1=last); "
                                     "ignored for still images")
    show_map: bool = Field(default=False, title="Show image on canvas",
                           description="Preview-only ghost of the source image")


class PixelGenParams(ImageBaseParams):
    """Adds shared image-processing controls (rendered as a collapsed group)."""

    invert: bool = Field(default=False, title="Invert",
                         description="Draw the light areas instead",
                         json_schema_extra=_IMAGE_PROCESSING)
    brightness: float = Field(default=0, ge=-100, le=100, title="Brightness",
                              json_schema_extra=_IMAGE_PROCESSING)
    contrast: float = Field(default=0, ge=-100, le=100, title="Contrast",
                            json_schema_extra=_IMAGE_PROCESSING)
    gamma: float = Field(default=1.0, ge=0.1, le=5.0, title="Gamma",
                         json_schema_extra=_IMAGE_PROCESSING)
    black_point: float = Field(default=0.0, ge=0.0, le=1.0, title="Black point",
                               json_schema_extra=_IMAGE_PROCESSING)
    white_point: float = Field(default=1.0, ge=0.0, le=1.0, title="White point",
                               json_schema_extra=_IMAGE_PROCESSING)
    min_brightness: float = Field(default=0, ge=0, le=255, title="Min brightness",
                                  json_schema_extra=_IMAGE_PROCESSING)
    max_brightness: float = Field(default=255, ge=0, le=255, title="Max brightness",
                                  json_schema_extra=_IMAGE_PROCESSING)


def working_dims(p: ImageBaseParams) -> tuple[int, int]:
    """Pixel dimensions of the working canvas for this image: WORK_W wide,
    aspect preserved, height capped at MAX_H. Raises like the generators do
    so error messages stay consistent."""
    if not p.image:
        raise ValueError("upload an image asset and pick it in 'Image'")
    image = asset_store.resolve_frame(p.image, p.frame)  # sequence -> concrete frame
    probe = asset_store.grayscale(image, rotate=p.rotate)
    if probe is None:
        raise ValueError(f"no asset named {image!r}")
    _, iw, ih = probe
    w = WORK_W
    h = max(round(w * ih / iw), 2)
    if h > MAX_H:
        h = MAX_H
        w = max(round(h * iw / ih), 2)
    return w, h


def luma_grid(p: ImageBaseParams, blur_px: float = 0.0,
              scale: float = 1.0) -> tuple[list[list[float]], int, int]:
    """Working-resolution luma rows in 0..255 (255 = white), no tone applied.

    ``scale`` multiplies the working canvas (capped at 2× the usual bounds)
    for generators that want finer structure than WORK_W allows — px-space
    params must be scaled by the caller to keep their meaning."""
    w, h = working_dims(p)
    if scale != 1.0:
        s = max(1.0, min(float(scale), 2.0))
        w = min(int(round(w * s)), 2 * WORK_W)
        h = min(int(round(h * s)), 2 * MAX_H)
    image = asset_store.resolve_frame(p.image, p.frame)  # sequence -> concrete frame
    rows, w, h = asset_store.grayscale(image, blur_px, p.rotate, size=(w, h))
    return [[v * 255.0 for v in row] for row in rows], w, h


def _tone_lut(p: PixelGenParams) -> list[float]:
    """Byte luma -> darkness 0..255; plotterfun tone plus gamma/levels."""
    tone = image_processing_kwargs(p)
    out = []
    for v in range(256):
        b = apply_image_processing_value(v / 255.0, **tone) * 255.0
        if p.invert:
            b = min(255 - p.min_brightness, 255 - b)
        else:
            b = max(p.min_brightness, b)
        out.append(max(p.max_brightness - b, 0.0))
    return out


class ImageSampler:
    """Callable (x, y) -> darkness 0..255 over the working canvas; 0 outside."""

    def __init__(self, p: PixelGenParams, blur_px: float = 0.0):
        w, h = working_dims(p)
        image = asset_store.resolve_frame(p.image, p.frame)  # sequence -> concrete frame
        rows, w, h = asset_store.grayscale(image, blur_px, p.rotate, size=(w, h))
        self.w, self.h = w, h
        lut = _tone_lut(p)
        self.grid = [[lut[int(v * 255 + 0.5)] for v in row] for row in rows]

    def __call__(self, x: float, y: float) -> float:
        xi, yi = math.floor(x), math.floor(y)
        if 0 <= xi < self.w and 0 <= yi < self.h:
            return self.grid[yi][xi]
        return 0.0


def pixel_doc(
    p: ImageBaseParams,
    work_w: int,
    work_h: int,
    lines: list[list[tuple[float, float]]],
    name: str,
    source: str,
    filled: bool = False,
) -> PathDocument:
    """Scale working-pixel polylines to mm and wrap them as a document."""
    s = p.width / work_w
    paths = [
        Path(points=[(x * s, y * s) for x, y in line], filled=filled)
        for line in lines
        if len(line) >= 2
    ]
    return PathDocument(
        layers=[Layer(id=1, name=name, color="#26241f", paths=paths)],
        width=p.width,
        height=work_h * s,
        source=source,
    )


def circle(cx: float, cy: float, r: float, min_seg: int = 10) -> list[tuple[float, float]]:
    """Closed polyline circle (first == last), segment count following radius."""
    r = max(r, 0.001)
    n = max(min_seg, min(int(r * 3), 64))
    pts = [
        (cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]
    pts.append(pts[0])
    return pts
