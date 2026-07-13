"""Image threshold: trace an imported image's dark regions as closed FILLED
outlines. The shapes are first-class compositor citizens — set the layer as
an occluder to mask what's below, or add a "Hatch fill" effect to shade them
(thresholding and hatching are deliberately separate stages).

The image is an uploaded project asset, drawn at ``width`` mm (height keeps
the aspect ratio) in the layer's local frame — place it by dragging the
layer; ``show_map`` ghosts the source image on the canvas (preview only).

Tracing is marching squares with linear interpolation over a Gaussian-blurred
copy of the image, sampled on a ``detail``-mm lattice padded with one ring of
"outside" so every contour closes (regions touching the image edge close
along it). PNG transparency below 0.5 alpha counts as outside. Note: a hole
inside a dark region traces as its own closed shape — occlusion masks union
filled paths, so holes read as solid to layers below.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..assets import asset_store
from ..image_processing import (
    IMAGE_PROCESSING_GROUP,
    apply_image_processing_value,
    image_processing_kwargs,
)
from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source


_IMAGE_PROCESSING = IMAGE_PROCESSING_GROUP


class ImageThresholdParams(BaseModel):
    image: str = Field(default="", title="Image (asset)",
                       description="Uploaded image asset to threshold",
                       json_schema_extra={"format": "asset"})
    show_map: bool = Field(default=False, title="Show image on canvas",
                           description="Preview-only ghost of the source image")
    rotate: Literal[0, 90, 180, 270] = Field(
        default=0, title="Rotate image (°)",
        description="Image rotation as seen in the current view",
        json_schema_extra={"viewRotate": True})
    width: float = Field(default=150.0, ge=10, le=400, title="Width (mm)",
                         description="Height follows the image aspect ratio",
                         json_schema_extra={"viewSize": True})
    threshold_min: float = Field(default=0.0, ge=0.0, le=1.0, title="Threshold min",
                                 description="Band lower bound — brightness between min and "
                                             "max is inside a shape; 0 (the default) means "
                                             "no lower bound")
    threshold_max: float = Field(default=0.5, ge=0.0, le=1.0, title="Threshold max",
                                 description="Band upper bound — brightness between min and "
                                             "max is inside a shape")
    smoothing: float = Field(default=1.0, ge=0.0, le=20.0, title="Smoothing (mm)",
                             description="Gaussian blur before tracing — rounds pixel "
                                         "staircases into curves")
    frame: float = Field(default=0.0, ge=0.0, le=1.0, title="Frame",
                         description="Position in an image sequence (0=first, 1=last); "
                                     "ignored for still images")
    invert: bool = Field(default=False, title="Invert (trace the light areas)",
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
    detail: float = Field(default=0.5, ge=0.15, le=5.0, title="Detail (mm)",
                          description="Contour-tracing lattice pitch — smaller follows "
                                      "edges tighter and costs more points")
    min_area: float = Field(default=2.0, ge=0.0, le=500.0, title="Min area (mm²)",
                            description="Drop specks smaller than this")

    @model_validator(mode="before")
    @classmethod
    def _legacy_threshold(cls, data: Any) -> Any:
        """Saved projects (pre-band) store a single ``threshold: t`` whose
        inside was {v < t} — exactly the band [0, t). Map it to
        threshold_min=0.0 (no lower bound, the field default) and
        threshold_max=t, which reproduces the old output byte-for-byte:
        the min-trace at 0.0 yields no loops ({v < 0} is empty), leaving
        the single trace at t, same as before."""
        if isinstance(data, dict) and "threshold" in data:
            data = dict(data)
            legacy = data.pop("threshold")
            data.setdefault("threshold_max", legacy)
        return data

    @model_validator(mode="after")
    def _order_band(self) -> "ImageThresholdParams":
        if self.threshold_min > self.threshold_max:
            self.threshold_min, self.threshold_max = self.threshold_max, self.threshold_min
        return self


def _trace_contours(field: list[list[float]], t: float, cell: float) -> list[list[tuple[float, float]]]:
    """Marching squares with interpolation. ``field`` is padded already; the
    returned loops are in mm, closed (first == last)."""
    ny, nx = len(field), len(field[0])
    pts: dict[tuple, tuple[float, float]] = {}     # edge key -> crossing point
    seg: dict[tuple, list[tuple]] = {}             # edge key -> connected edge keys

    def cross(a, b, fa, fb):
        """Interpolated crossing on the lattice edge a->b (lattice coords)."""
        frac = 0.5 if fb == fa else (t - fa) / (fb - fa)
        return ((a[0] + (b[0] - a[0]) * frac) * cell, (a[1] + (b[1] - a[1]) * frac) * cell)

    def link(e1, e2):
        seg.setdefault(e1, []).append(e2)
        seg.setdefault(e2, []).append(e1)

    for j in range(ny - 1):
        row0, row1 = field[j], field[j + 1]
        for i in range(nx - 1):
            tl, tr, br, bl = row0[i], row0[i + 1], row1[i + 1], row1[i]
            case = (tl < t) | ((tr < t) << 1) | ((br < t) << 2) | ((bl < t) << 3)
            if case in (0, 15):
                continue
            top, right = ("h", i, j), ("v", i + 1, j)
            bottom, left = ("h", i, j + 1), ("v", i, j)
            if top not in pts and case in (1, 2, 5, 6, 9, 10, 13, 14):
                pts[top] = cross((i, j), (i + 1, j), tl, tr)
            if right not in pts and case in (2, 3, 4, 5, 10, 11, 12, 13):
                pts[right] = cross((i + 1, j), (i + 1, j + 1), tr, br)
            if bottom not in pts and case in (4, 5, 6, 7, 8, 9, 10, 11):
                pts[bottom] = cross((i, j + 1), (i + 1, j + 1), bl, br)
            if left not in pts and case in (1, 3, 5, 7, 8, 10, 12, 14):
                pts[left] = cross((i, j), (i, j + 1), tl, bl)
            if case in (5, 10):  # saddle: split by the cell-centre value
                centre_dark = (tl + tr + br + bl) / 4 < t
                if (case == 5) == centre_dark:
                    link(top, right); link(bottom, left)
                else:
                    link(top, left); link(bottom, right)
            else:
                edges = {
                    1: (left, top), 2: (top, right), 3: (left, right),
                    4: (right, bottom), 6: (top, bottom), 7: (left, bottom),
                    8: (bottom, left), 9: (bottom, top), 11: (bottom, right),
                    12: (right, left), 13: (right, top), 14: (top, left),
                }[case]
                link(*edges)

    loops: list[list[tuple[float, float]]] = []
    used: set[tuple] = set()
    for start in seg:
        if start in used:
            continue
        loop_keys = [start]
        used.add(start)
        prev, cur = None, start
        while True:
            nxt = next((k for k in seg[cur] if k != prev and k not in used), None)
            if nxt is None:
                break
            loop_keys.append(nxt)
            used.add(nxt)
            prev, cur = cur, nxt
        if len(loop_keys) >= 3 and loop_keys[0] in seg[loop_keys[-1]]:
            loop = [pts[k] for k in loop_keys]
            loop.append(loop[0])
            loops.append(loop)
    return loops


def _shoelace(loop: list[tuple[float, float]]) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(loop, loop[1:]))) / 2


@register_source
class ImageThreshold(SourceModule):
    id = "image_threshold"
    label = "Image threshold"
    description = "Trace an image's dark regions as filled outlines — occlude or hatch-fill them."
    Params = ImageThresholdParams

    def generate(self, params: ImageThresholdParams) -> PathDocument:
        p = params
        if not p.image:
            raise ValueError("upload an image asset (Compose tab) and pick it in 'Image'")
        image = asset_store.resolve_frame(p.image, p.frame)  # sequence -> concrete frame
        probe = asset_store.grayscale(image, rotate=p.rotate)
        if probe is None:
            raise ValueError(f"no asset named {image!r}")
        blur_px = p.smoothing * probe[1] / p.width if p.smoothing > 0 else 0.0
        rows, iw, ih = asset_store.grayscale(image, blur_px, rotate=p.rotate)
        alpha = asset_store.alpha(image, rotate=p.rotate)
        w_mm, h_mm = p.width, p.width * ih / iw
        sx, sy = iw / w_mm, ih / h_mm
        # Field values (post tone-mapping) always land in [0, 1], so 2.0 is
        # safely outside the band at both ends regardless of min/max —
        # padding never reads as "inside" for either trace below.
        outside = 2.0
        tone = image_processing_kwargs(p)

        def bilinear(grid, px, py) -> float:
            fx = min(max(px * sx - 0.5, 0.0), iw - 1.0)
            fy = min(max(py * sy - 0.5, 0.0), ih - 1.0)
            x0, y0 = int(fx), int(fy)
            x1, y1 = min(x0 + 1, iw - 1), min(y0 + 1, ih - 1)
            tx, ty = fx - x0, fy - y0
            top = grid[y0][x0] * (1 - tx) + grid[y0][x1] * tx
            bot = grid[y1][x0] * (1 - tx) + grid[y1][x1] * tx
            return top * (1 - ty) + bot * ty

        # sample onto the tracing lattice, padded with one ring of "outside"
        nx = max(int(math.ceil(w_mm / p.detail)) + 1, 2)
        ny = max(int(math.ceil(h_mm / p.detail)) + 1, 2)
        field = [[outside] * (nx + 2) for _ in range(ny + 2)]
        for j in range(ny):
            py = min(j * p.detail, h_mm)
            frow = field[j + 1]
            for i in range(nx):
                px = min(i * p.detail, w_mm)
                if alpha is not None and bilinear(alpha, px, py) < 0.5:
                    continue  # transparent: stays "outside"
                v = apply_image_processing_value(bilinear(rows, px, py), **tone)
                frow[i + 1] = 1.0 - v if p.invert else v

        # True band select: inside = {threshold_min <= v <= threshold_max},
        # always. Contours of the band = contours at the min level XOR-ed
        # against contours at the max level (concatenated loops; the
        # compositor's even-odd parity — see compose.build_mask / hatch_fill —
        # turns the nested pair into the band ring, exactly like a threshold
        # hole already works). Both edges keep the same rule at their extreme:
        # * min == 0.0 traces {v < 0} = empty (values are clamped >= 0), so no
        #   lower-edge loops — the legacy one-sided cutoff, byte-identical.
        # * max >= 1.0 traces just ABOVE the value range so pure white
        #   (v == 1.0) counts as inside; against the 2.0 padding that yields
        #   the image-boundary rectangle — the honest "everything from min
        #   up" selection, continuous with max = 0.999.
        t_max = p.threshold_max if p.threshold_max < 1.0 else 1.0 + 1e-6
        loops = _trace_contours(field, p.threshold_min, p.detail)
        loops += _trace_contours(field, t_max, p.detail)
        paths = [
            Path(points=[(x - p.detail, y - p.detail) for x, y in loop], filled=True)
            for loop in loops
            if _shoelace(loop) >= p.min_area
        ]
        return PathDocument(
            layers=[Layer(id=1, name="image threshold", color="#26241f", paths=paths)],
            width=w_mm,
            height=h_mm,
            source=f"image_threshold {p.image}",
        )
