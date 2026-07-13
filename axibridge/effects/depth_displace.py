"""Depth-map displacement: push geometry by the brightness of an imported
image. Run dense parallel lines (the grid generator) through a portrait depth
map and you get the classic "Unknown Pleasures" relief / woodgrain-shaded
look — the depth map is invisible, only its terrain shows.

The image is an uploaded project asset, referenced by name (one map can
drive any number of layers). It sits ON THE PAPER, independent of the layer:
``x`` / ``y`` / ``width`` place and scale it in mm, so the map can be moved
under the geometry without re-anchoring anything; ``show_map`` ghosts it on
the canvas (preview only — never plotted).

Direction: ``fixed angle`` slides every point the same way, which is
invisible on lines PARALLEL to that direction (they slide along themselves).
``path normal`` displaces perpendicular to each line locally, so every
orientation shows relief.

Smoothness: brightness is sampled bilinearly from a Gaussian-blurred copy
(``smoothing``), which removes both 8-bit banding and pixel steps — raise it
until surfaces feel continuous.
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
from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect
from .coherent_jitter import _resample


_IMAGE_PROCESSING = IMAGE_PROCESSING_GROUP


class DepthDisplaceParams(BaseModel):
    image: str = Field(default="", title="Depth map (asset)",
                       description="Uploaded image asset; white pushes furthest",
                       json_schema_extra={"format": "asset"})
    show_map: bool = Field(default=False, title="Show map on canvas",
                           description="Preview-only ghost of the image at its placement")
    frame: float = Field(default=0.0, ge=0.0, le=1.0, title="Frame",
                         description="Position in an image sequence (0=first, 1=last); "
                                     "ignored for still images")
    rotate: Literal[0, 90, 180, 270] = Field(
        default=0, title="Rotate map (°)",
        description="Image rotation as seen in the current view",
        json_schema_extra={"viewRotate": True})
    anchor: Literal["layer", "paper"] = Field(
        default="layer", title="Anchor",
        description="layer: the map rides along when you drag the layer — "
                    "paper: the map is pinned to the bed (share one global map "
                    "across layers by giving each the same image + paper anchor)")
    x: float = Field(default=0.0, ge=-400, le=400, title="Map x (mm)",
                     description="The image's left edge — in layer frame when "
                                 "anchored to the layer, paper frame otherwise",
                     json_schema_extra={"viewAxis": True})
    y: float = Field(default=0.0, ge=-400, le=400, title="Map y (mm)",
                     json_schema_extra={"viewAxis": True})
    width: float = Field(default=150.0, ge=5, le=600, title="Map width (mm)",
                         description="Height follows the image aspect ratio",
                         json_schema_extra={"viewSize": True})
    amplitude: float = Field(default=6.0, ge=0.0, le=60.0, title="Displacement depth (mm)",
                             description="Displacement at pure white")
    bias: float = Field(default=0.0, ge=0.0, le=1.0, title="Bias",
                        description="Brightness that maps to zero — 0: black stays put, "
                                    "0.5: signed around mid-gray (darker pulls back)")
    background: float = Field(default=0.0, ge=0.0, le=1.0, title="Background depth",
                              description="Brightness assumed outside the image (and under "
                                          "transparent pixels) — 0 with zero bias keeps the "
                                          "background still")
    crop: Literal["off", "outside map", "transparent", "outside + transparent"] = Field(
        default="off", title="Crop",
        description="Drop geometry beyond the image edge and/or where PNG alpha < 0.5 "
                    "(cut paths split; closed shapes that get cut stop occluding as solids)")
    direction: Literal["fixed angle", "path normal"] = Field(
        default="fixed angle", title="Direction",
        description="Fixed angle is invisible on lines parallel to it; "
                    "path normal shows relief on every orientation")
    angle_deg: float = Field(default=90.0, ge=0.0, le=360.0, title="Angle (degrees)",
                             description="Fixed-angle mode only; 90 = down the page",
                             json_schema_extra={"viewAngle": 360})
    smoothing: float = Field(default=1.0, ge=0.0, le=20.0, title="Smoothing (mm)",
                             description="Gaussian blur of the map, in paper mm — kills "
                                         "pixel steps and 8-bit banding")
    invert: bool = Field(default=False, title="Invert (black pushes)",
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
    step: float = Field(default=1.0, ge=0.1, le=20.0, title="Resample step (mm)",
                        description="Paths are resampled at this interval before displacement")


@register_effect
class DepthDisplace(EffectModule):
    id = "depth_displace"
    label = "Depth map displace"
    description = "Displace geometry by an imported image's brightness — joy-division relief."
    Params = DepthDisplaceParams

    def apply(self, paths: list[Path], params: DepthDisplaceParams, ctx: EffectContext) -> list[Path]:
        decoded = None
        image = asset_store.resolve_frame(params.image, params.frame)  # sequence -> concrete frame
        if params.image:
            blur_px = 0.0
            probe = asset_store.grayscale(image, rotate=params.rotate)
            if probe is not None and params.smoothing > 0:
                blur_px = params.smoothing * probe[1] / params.width
            decoded = asset_store.grayscale(image, blur_px, rotate=params.rotate)
        if decoded is None or (params.amplitude == 0 and params.crop == "off"):
            return list(paths)  # no map yet: pass through, don't error the resolve
        rows, iw, ih = decoded
        alpha = asset_store.alpha(image, rotate=params.rotate)
        map_h = params.width * ih / iw
        sx = iw / params.width
        sy = ih / map_h
        # layer anchor: the map's placement follows the layer's translation
        # (drag the layer, the relief comes along); paper anchor pins it
        tx, ty = ctx.translation if params.anchor == "layer" else (0.0, 0.0)
        map_x, map_y = params.x + tx, params.y + ty
        dirx = math.cos(math.radians(params.angle_deg))
        diry = math.sin(math.radians(params.angle_deg))
        along_normal = params.direction == "path normal"
        crop_outside = params.crop in ("outside map", "outside + transparent")
        crop_alpha = alpha is not None and params.crop in ("transparent", "outside + transparent")
        bg_depth = (params.background - params.bias) * params.amplitude
        tone = image_processing_kwargs(params)

        def lattice(px: float, py: float):
            """Paper point -> (x0,y0,x1,y1,tx,ty) bilinear weights, or None off-map."""
            fx = (px - map_x) * sx - 0.5
            fy = (py - map_y) * sy - 0.5
            if fx < -0.5 or fy < -0.5 or fx > iw - 0.5 or fy > ih - 0.5:
                return None
            x0, y0 = math.floor(fx), math.floor(fy)
            return (max(x0, 0), max(y0, 0), min(x0 + 1, iw - 1), min(y0 + 1, ih - 1),
                    fx - x0, fy - y0)

        def bilinear(grid, lat) -> float:
            x0, y0, x1, y1, tx, ty = lat
            top = grid[y0][x0] * (1 - tx) + grid[y0][x1] * tx
            bot = grid[y1][x0] * (1 - tx) + grid[y1][x1] * tx
            return top * (1 - ty) + bot * ty

        def probe_point(px: float, py: float) -> tuple[float, bool]:
            """(displacement mm, keep?) at a paper point."""
            lat = lattice(px, py)
            if lat is None:
                return bg_depth, not crop_outside
            if alpha is not None and bilinear(alpha, lat) < 0.5:
                return bg_depth, not crop_alpha
            v = apply_image_processing_value(bilinear(rows, lat), **tone)
            if params.invert:  # inside the map only — background has its own knob
                v = 1.0 - v
            return (v - params.bias) * params.amplitude, True

        out: list[Path] = []
        for path in paths:
            closed = len(path.points) > 2 and path.points[0] == path.points[-1]
            pts = _resample(path.points, params.step)
            n = len(pts)
            moved: list[tuple[float, float] | None] = []
            cropped_any = False
            for i, (px, py) in enumerate(pts):
                d, keep = probe_point(px, py)
                if not keep:
                    moved.append(None)
                    cropped_any = True
                    continue
                if along_normal:
                    # local tangent from neighbours; closed paths wrap past
                    # the duplicated seam point (pts[0] == pts[n-1])
                    if closed:
                        ax, ay = pts[i - 1] if i > 0 else pts[n - 2]
                        bx, by = pts[i + 1] if i < n - 1 else pts[1]
                    else:
                        ax, ay = pts[max(i - 1, 0)]
                        bx, by = pts[min(i + 1, n - 1)]
                    tx, ty = bx - ax, by - ay
                    norm = math.hypot(tx, ty) or 1.0
                    moved.append((px - d * ty / norm, py + d * tx / norm))
                else:
                    moved.append((px + d * dirx, py + d * diry))
            if not cropped_any:
                if closed and len(moved) > 1:
                    moved[-1] = moved[0]  # displacement is positional, but be exact
                out.append(Path(points=moved, filled=path.filled))
                continue
            # crop split the path: emit kept runs; closure (and with it the
            # filled/occluder property) is gone for the pieces by definition
            run: list[tuple[float, float]] = []
            for p in [*moved, None]:
                if p is not None:
                    run.append(p)
                elif len(run) >= 2:
                    out.append(Path(points=run, filled=False))
                    run = []
                else:
                    run = []
        return out
