"""Image hatch: threshold an imported image into gray bands and fill each
band with hatching — the plotter's halftone. One level is a hard threshold
silhouette; more levels add hatch passes at rotated angles, so darker areas
accumulate density (classic crosshatch shading: 0°, 90°, 45°, 135°…).

The image is an uploaded project asset, drawn at ``width`` mm (height keeps
the aspect ratio) in the layer's local frame — place it on the canvas by
dragging the layer. ``show_map`` ghosts the source image under the hatching
(preview only). Levels work like an image editor's levels dialog:
``black_point`` / ``white_point`` clip the brightness range before banding,
``smoothing`` Gaussian-blurs away pixel steps and JPEG noise.

Hatching samples the (blurred) bitmap directly along angled scanlines — no
contour tracing, so ragged photographic edges cost nothing.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ..assets import asset_store
from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source

#: classic crosshatch angle progression, relative to the base angle
_LEVEL_ANGLES = [0.0, 90.0, 45.0, 135.0, 22.5]


class ImageHatchParams(BaseModel):
    image: str = Field(default="", title="Image (asset)",
                       description="Uploaded image asset to threshold and hatch",
                       json_schema_extra={"format": "asset"})
    show_map: bool = Field(default=False, title="Show image on canvas",
                           description="Preview-only ghost of the source image")
    width: float = Field(default=150.0, ge=10, le=400, title="Width (mm)",
                         description="Height follows the image aspect ratio")
    levels: int = Field(default=3, ge=1, le=5, title="Levels",
                        description="Gray bands — each darker band adds a hatch pass "
                                    "at a rotated angle")
    spacing: float = Field(default=1.6, ge=0.3, le=10.0, title="Hatch spacing (mm)")
    angle_deg: float = Field(default=45.0, ge=0.0, le=180.0, title="Base angle (degrees)")
    smoothing: float = Field(default=1.0, ge=0.0, le=20.0, title="Smoothing (mm)",
                             description="Gaussian blur before thresholding")
    black_point: float = Field(default=0.0, ge=0.0, le=1.0, title="Black point",
                               description="Levels: brightness at/below this is full dark")
    white_point: float = Field(default=1.0, ge=0.0, le=1.0, title="White point",
                               description="Levels: brightness at/above this stays empty")
    invert: bool = Field(default=False, title="Invert (hatch the light areas)")
    min_run: float = Field(default=0.6, ge=0.0, le=10.0, title="Min segment (mm)",
                           description="Drop hatch dashes shorter than this — speckle filter")


@register_source
class ImageHatch(SourceModule):
    id = "image_hatch"
    label = "Image hatch"
    description = "Threshold an imported image into bands and crosshatch them — plotter halftone."
    Params = ImageHatchParams

    def generate(self, params: ImageHatchParams) -> PathDocument:
        p = params
        if not p.image:
            raise ValueError("upload an image asset (Compose tab) and pick it in 'Image'")
        probe = asset_store.grayscale(p.image)
        if probe is None:
            raise ValueError(f"no asset named {p.image!r}")
        blur_px = p.smoothing * probe[1] / p.width if p.smoothing > 0 else 0.0
        rows, iw, ih = asset_store.grayscale(p.image, blur_px)
        w_mm = p.width
        h_mm = p.width * ih / iw
        sx, sy = iw / w_mm, ih / h_mm
        lo, hi = p.black_point, max(p.white_point, p.black_point + 1e-6)

        def value(px: float, py: float) -> float:
            """Normalized brightness at a local-frame mm point (bilinear)."""
            fx = min(max(px * sx - 0.5, 0.0), iw - 1.0)
            fy = min(max(py * sy - 0.5, 0.0), ih - 1.0)
            x0, y0 = int(fx), int(fy)
            x1, y1 = min(x0 + 1, iw - 1), min(y0 + 1, ih - 1)
            tx, ty = fx - x0, fy - y0
            top = rows[y0][x0] * (1 - tx) + rows[y0][x1] * tx
            bot = rows[y1][x0] * (1 - tx) + rows[y1][x1] * tx
            v = top * (1 - ty) + bot * ty
            if p.invert:
                v = 1.0 - v
            return min(max((v - lo) / (hi - lo), 0.0), 1.0)

        paths: list[Path] = []
        step = min(max(p.spacing * 0.25, 0.15), 0.6)  # sample interval along scanlines
        diag = math.hypot(w_mm, h_mm)
        cx, cy = w_mm / 2, h_mm / 2
        for k in range(p.levels):
            threshold = (k + 1) / (p.levels + 1)
            a = math.radians(p.angle_deg + _LEVEL_ANGLES[k])
            ux, uy = math.cos(a), math.sin(a)        # along the hatch line
            vx, vy = -uy, ux                          # across, line-to-line
            n_lines = int(diag / p.spacing) + 1
            flip = False
            for li in range(-n_lines, n_lines + 1):
                ox, oy = cx + vx * li * p.spacing, cy + vy * li * p.spacing
                run_start = None
                last_in = None
                ts = range(int(-diag / 2 / step), int(diag / 2 / step) + 1)
                for t in (reversed(ts) if flip else ts):
                    qx, qy = ox + ux * t * step, oy + uy * t * step
                    inside = 0 <= qx <= w_mm and 0 <= qy <= h_mm
                    dark = inside and value(qx, qy) < threshold
                    if dark and run_start is None:
                        run_start = (qx, qy)
                    elif not dark and run_start is not None:
                        if last_in and math.dist(run_start, last_in) >= p.min_run:
                            paths.append(Path(points=[run_start, last_in]))
                        run_start = None
                    if dark:
                        last_in = (qx, qy)
                if run_start is not None and last_in and math.dist(run_start, last_in) >= p.min_run:
                    paths.append(Path(points=[run_start, last_in]))
                flip = not flip
        return PathDocument(
            layers=[Layer(id=1, name="image hatch", color="#26241f", paths=paths)],
            width=w_mm,
            height=h_mm,
            source=f"image_hatch {p.image}",
        )
