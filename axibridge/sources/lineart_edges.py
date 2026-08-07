"""Lineart v2, edges: XDoG or Sobel edge extraction traced into hand-wobbled
contour strokes — the "stroke tracing" stage of the AARON-pass §D pipeline
(``docs/IDEAS-aaron-pass.md``), split from tonal hatching (``lineart_hatch``)
so each band gets its own texture/pen. Thin wrapper: all the numerics live in
``_lineart.py`` (xdog/sobel_edges/trace/hand); this module is params + the
plumbing to get an image asset into and out of that engine.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import Field

from ..image_processing import (
    IMAGE_PROCESSING_GROUP,
    apply_image_processing_value,
    image_processing_kwargs,
)
from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from . import _lineart as L
from ._pixelgen import ImageBaseParams, luma_grid, pixel_doc
from ._pixelgen import working_dims as _pixelgen_working_dims

Pt = tuple[float, float]

_IMAGE_PROCESSING = IMAGE_PROCESSING_GROUP
_EDGE = {"group": "Edge extraction"}
_TRACE = {"group": "Tracing"}
_HAND = {"group": "Hand"}


class LineartEdgesParams(ImageBaseParams):
    invert: bool = Field(default=False, title="Invert",
                         description="Draw the light areas instead",
                         json_schema_extra=_IMAGE_PROCESSING)
    brightness: float = Field(default=0.0, ge=-100.0, le=100.0, title="Brightness",
                              json_schema_extra=_IMAGE_PROCESSING)
    contrast: float = Field(default=0.0, ge=-100.0, le=100.0, title="Contrast",
                            json_schema_extra=_IMAGE_PROCESSING)
    gamma: float = Field(default=1.0, ge=0.1, le=5.0, title="Gamma",
                         json_schema_extra=_IMAGE_PROCESSING)
    black_point: float = Field(default=0.0, ge=0.0, le=1.0, title="Black point",
                               json_schema_extra=_IMAGE_PROCESSING)
    white_point: float = Field(default=1.0, ge=0.0, le=1.0, title="White point",
                               json_schema_extra=_IMAGE_PROCESSING)

    edge_mode: Literal["xdog", "sobel"] = Field(default="xdog", title="Edge mode")

    sigma: float = Field(default=2.0, ge=0.5, le=8.0, title="Sigma (px)",
                         description="XDoG blur radius — bigger picks up coarser structure",
                         json_schema_extra=_EDGE)
    sharpness: float = Field(default=20.0, ge=1.0, le=60.0, title="Sharpness",
                             description="XDoG soft-threshold steepness (xdog mode only)",
                             json_schema_extra=_EDGE)
    edge_threshold: float = Field(default=0.5, ge=0.0, le=1.0, title="Strictness",
                                  description="Higher = fewer, cleaner lines",
                                  json_schema_extra=_EDGE)
    mass: float = Field(default=0.0, ge=0.0, le=1.0, title="Ink mass",
                        description="Adds solid ink where the image is dark (1 = below "
                                    "mid-grey) — with 'Fill ink' the layer holds as a "
                                    "full drawing",
                        json_schema_extra=_EDGE)
    resolution: float = Field(default=1.0, ge=1.0, le=2.0, title="Resolution ×",
                              description="Working-canvas multiplier — finer detail, slower",
                              json_schema_extra=_EDGE)

    ink_fill: bool = Field(default=False, title="Fill ink",
                           description="Fill solid ink regions with tight flow-following "
                                       "strokes instead of outlining them",
                           json_schema_extra=_EDGE)
    fill_spacing: float = Field(default=2.5, ge=1.0, le=10.0, title="Fill spacing (px)",
                                json_schema_extra=_EDGE)

    join_angle_deg: float = Field(default=50.0, ge=0.0, le=90.0, title="Join angle (deg)",
                                  description="Max tangent disagreement to chain two strokes",
                                  json_schema_extra=_TRACE)
    min_length: float = Field(default=6.0, ge=0.0, le=60.0, title="Min length (px)",
                              description="Shorter strokes are culled as scan noise",
                              json_schema_extra=_TRACE)
    smoothing: float = Field(default=0.5, ge=0.0, le=1.0, title="Smoothing",
                             json_schema_extra=_TRACE)
    detail: int = Field(default=2, ge=1, le=16, title="Detail",
                        description="Point-subsample stride after smoothing — higher is coarser",
                        json_schema_extra=_TRACE)

    carefulness_tight: float = Field(default=0.3, ge=0.0, le=4.0, title="Carefulness (tight, px)",
                                     description="Wobble amplitude right on an edge",
                                     json_schema_extra=_HAND)
    carefulness_loose: float = Field(default=1.5, ge=0.0, le=8.0, title="Carefulness (loose, px)",
                                     description="Wobble amplitude away from edges",
                                     json_schema_extra=_HAND)
    wobble: float = Field(default=1.0, ge=0.0, le=2.0, title="Wobble",
                          description="Overall hand-wobble scale; 0 disables it",
                          json_schema_extra=_HAND)
    seed: int = Field(default=0, ge=0, le=9999, title="Seed", json_schema_extra=_HAND)


def _tone_lut(p: LineartEdgesParams) -> np.ndarray:
    """Byte luma -> toned byte luma, vectorized: build the 256-entry curve
    once (same shared tone pipeline as linedraw/pixelgen) and index with the
    byte image rather than looping per pixel."""
    tone = image_processing_kwargs(p)
    return np.array(
        [apply_image_processing_value(v / 255.0, **tone) * 255.0 for v in range(256)]
    )


def _subsample_keep_ends(line: L.Line, stride: int) -> L.Line:
    """Point-subsample stride ``detail`` applied after smoothing/tracing —
    v1's ``contour[::sc]``, but explicit about keeping the exact endpoint
    (plain slicing only does that when the stride divides the length)."""
    if stride <= 1 or len(line) <= 2:
        return line
    out = line[::stride]
    if out[-1] != line[-1]:
        out = out + [line[-1]]
    return out


@register_source
class LineartEdges(SourceModule):
    id = "lineart_edges"
    orientation = "param"
    label = "Lineart edges (v2)"
    description = "XDoG/Sobel edge extraction, traced into hand-wobbled contour strokes."
    Params = LineartEdgesParams

    def generate(self, params: LineartEdgesParams) -> PathDocument:
        p = params
        # px-space params keep their working-canvas meaning at any resolution:
        # everything calibrated in px is multiplied by the same factor the
        # canvas grew by (luma_grid caps the actual size, so derive k from it)
        rows, w, h = luma_grid(p, scale=p.resolution)
        base_w, _ = _pixelgen_working_dims(p)
        k = w / base_w
        report_progress(0.05, "Tone")
        luma = np.asarray(rows, dtype=float)  # row-major (h, w), matches _lineart's convention
        lut = _tone_lut(p)
        byte = np.clip(np.round(luma), 0, 255).astype(np.uint8)
        toned = lut[byte]
        if p.invert:
            toned = 255.0 - toned

        report_progress(0.15, "Edge extraction")
        if p.edge_mode == "xdog":
            edge_map = L.xdog(toned, sigma=p.sigma * k,
                              sharpness=p.sharpness, threshold=p.edge_threshold)
        else:
            edge_map = L.sobel_edges(toned, threshold=p.edge_threshold)
        if p.mass > 0.0:
            # union in solid ink for dark regions (DoG alone can't see flat
            # darkness): mass=1 inks everything below mid-grey
            edge_map = edge_map | L.dark_mass(toned, cut=153.0 * p.mass,
                                              soften_px=1.5 * k)

        # thick ink collapses badly through the run-midpoint tracer (branches
        # and fine features merge into blobby centrelines) — skeletonize
        # first so every stroke and junction survives as its own line
        report_progress(0.3, "Thinning")
        skeleton = L.thin_mask(edge_map)

        report_progress(0.45, "Tracing")
        lines = L.trace(skeleton, join_angle_deg=p.join_angle_deg,
                        min_len_px=p.min_length * k, smooth=p.smoothing)
        lines = [_subsample_keep_ends(line, p.detail) for line in lines]
        lines = [line for line in lines if len(line) >= 2]

        if p.ink_fill:
            # render the ink MASS as tight flow-following strokes over the
            # pre-thinning map — this is what lets a maxed edges layer hold
            # as a complete drawing instead of an outline sketch
            report_progress(0.6, "Filling ink")
            field = L.flow_field(toned, smooth_px=6.0 * k)
            fill = L.streamlines(edge_map.astype(float) * 255.0, field, (0.5, 1.0),
                                 p.fill_spacing * k, 200.0 * k, p.seed)
            lines += fill

        report_progress(0.8, "Hand wobble")
        lines = L.hand(lines, edge_map, p.carefulness_tight * k,
                       p.carefulness_loose * k, p.wobble, p.seed)

        report_progress(0.95, "Building paths")
        return pixel_doc(p, w, h, lines, "lineart_edges", f"lineart_edges {p.image}")
