"""Lineart v2, hatch: flow-aligned tonal streamline hatching for one darkness
band — the "flow-aligned tonal work" stage of the AARON-pass §D pipeline
(``docs/IDEAS-aaron-pass.md``). One layer of this generator draws one tonal
band; ``session.add_lineart_stack`` stacks several (lights/mids/darks) with
an edges layer on top, each its own texture/pen. Numerics live in
``_lineart.py`` (flow_field/streamlines/hand); this module is params + the
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

_IMAGE_PROCESSING = IMAGE_PROCESSING_GROUP
_BAND = {"group": "Tonal band"}
_FLOW = {"group": "Flow"}
_MARKS = {"group": "Marks"}
_HAND = {"group": "Hand"}

#: fixed, not user-exposed: a cheap XDoG probe so the hand wobble tightens
#: near contours even in the hatch generator (no sigma/threshold knobs here —
#: those live on lineart_edges; this is just enough signal to keep hatching
#: from blurring across an edge it's approaching). See generate()'s docstring
#: note for why this is worth the extra pass.
_EDGE_PROBE_SIGMA = 1.5


class LineartHatchParams(ImageBaseParams):
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

    band_from: float = Field(default=0.4, ge=0.0, le=1.0, title="Band from",
                             description="Darkness window start (0=white, 1=black)",
                             json_schema_extra=_BAND)
    band_to: float = Field(default=1.0, ge=0.0, le=1.0, title="Band to",
                           json_schema_extra=_BAND)

    direction: Literal["flow", "fixed"] = Field(default="flow", title="Direction",
                                                json_schema_extra=_FLOW)
    angle_deg: float = Field(default=45.0, ge=0.0, le=180.0, title="Angle (deg)",
                             description="Used when direction=fixed",
                             json_schema_extra=_FLOW)
    field_smooth: float = Field(default=8.0, ge=1.0, le=32.0, title="Field smoothing (px)",
                                description="Used when direction=flow",
                                json_schema_extra=_FLOW)

    spacing: float = Field(default=7.0, ge=2.0, le=40.0, title="Spacing (px)",
                           json_schema_extra=_MARKS)
    max_length: float = Field(default=120.0, ge=10.0, le=400.0, title="Max length (px)",
                              json_schema_extra=_MARKS)
    cross_hatch: bool = Field(default=False, title="Cross-hatch", json_schema_extra=_MARKS)
    dash: float = Field(default=0.0, ge=0.0, le=1.0, title="Dash", json_schema_extra=_MARKS)

    carefulness_tight: float = Field(default=0.5, ge=0.0, le=4.0, title="Carefulness (tight, px)",
                                     json_schema_extra=_HAND)
    carefulness_loose: float = Field(default=2.0, ge=0.0, le=8.0, title="Carefulness (loose, px)",
                                     json_schema_extra=_HAND)
    wobble: float = Field(default=1.0, ge=0.0, le=2.0, title="Wobble", json_schema_extra=_HAND)
    seed: int = Field(default=0, ge=0, le=9999, title="Seed", json_schema_extra=_HAND)


def _tone_lut(p: LineartHatchParams) -> np.ndarray:
    tone = image_processing_kwargs(p)
    return np.array(
        [apply_image_processing_value(v / 255.0, **tone) * 255.0 for v in range(256)]
    )


@register_source
class LineartHatch(SourceModule):
    id = "lineart_hatch"
    label = "Lineart hatch (v2)"
    description = "Flow-aligned tonal streamline hatching for one darkness band."
    Params = LineartHatchParams

    def generate(self, params: LineartHatchParams) -> PathDocument:
        p = params
        rows, w, h = luma_grid(p)
        report_progress(0.05, "Tone")
        luma = np.asarray(rows, dtype=float)  # row-major (h, w), matches _lineart's convention
        lut = _tone_lut(p)
        byte = np.clip(np.round(luma), 0, 255).astype(np.uint8)
        toned = lut[byte]
        if p.invert:
            toned = 255.0 - toned
        darkness = 255.0 - toned

        if p.direction == "flow":
            report_progress(0.15, "Flow field")
            field = L.flow_field(toned, smooth_px=p.field_smooth)
        else:
            field = np.zeros_like(toned)

        band = (min(p.band_from, p.band_to), max(p.band_from, p.band_to))
        report_progress(0.3, "Streamlines")
        lines = L.streamlines(darkness, field, band, p.spacing, p.max_length, p.seed,
                              direction=p.direction, angle_deg=p.angle_deg,
                              cross_hatch=p.cross_hatch, dash=p.dash)

        # A cheap fixed-param edge probe so hand wobble tightens as hatching
        # nears a contour, rather than every stroke wobbling at one flat
        # "loose" amplitude regardless of what it's approaching — one extra
        # xdog() call (two Gaussians) is negligible next to the streamline
        # integration above.
        report_progress(0.85, "Edge probe")
        edge_map = L.xdog(toned, sigma=_EDGE_PROBE_SIGMA)

        report_progress(0.9, "Hand wobble")
        lines = L.hand(lines, edge_map, p.carefulness_tight, p.carefulness_loose,
                       p.wobble, p.seed)

        report_progress(0.95, "Building paths")
        return pixel_doc(p, w, h, lines, "lineart_hatch", f"lineart_hatch {p.image}")
