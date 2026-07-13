"""Hatch fill: turn ``filled`` shapes into plottable line fill.

The preview can paint a fill; a pen cannot — hatching is how a plotter says
"solid". Every closed+filled path in the layer grows a set of parallel lines
clipped to its interior (optionally crosshatched, optionally inset so wet ink
doesn't bleed past the outline). Open / unfilled paths pass through untouched.

The original outlines are kept by default and keep their ``filled`` flag —
occlusion masks are built from filled outlines downstream of the effect
stack, so removing them (``outline`` off) also stops the layer occluding as
a solid. That is sometimes exactly what you want; now you know.

Hatch geometry via shapely (already the occlusion engine): rotate the shape
so hatches are horizontal scanlines, clip, rotate back. Scanlines alternate
direction so the pen serpentines instead of always homing to one side.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field
from shapely import affinity
from shapely.geometry import LineString, Polygon

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect


class HatchFillParams(BaseModel):
    spacing: float = Field(default=2.0, ge=0.2, le=20.0, title="Spacing (mm)")
    angle_deg: float = Field(default=45.0, ge=0.0, le=180.0, title="Angle (degrees)",
                             json_schema_extra={"viewAngle": 180})
    cross: bool = Field(default=False, title="Crosshatch",
                        description="Second pass at 90° to the first")
    inset: float = Field(default=0.3, ge=0.0, le=10.0, title="Inset (mm)",
                         description="Pull hatching in from the outline")
    outline: bool = Field(default=True, title="Keep outline",
                          description="Off also stops the shape occluding as a solid")


def _hatch(poly: Polygon, spacing: float, angle_deg: float) -> list[list[tuple[float, float]]]:
    """Parallel lines at `angle_deg`, clipped to `poly`, serpentine-ordered."""
    cx, cy = poly.centroid.x, poly.centroid.y
    flat = affinity.rotate(poly, -angle_deg, origin=(cx, cy))
    minx, miny, maxx, maxy = flat.bounds
    segments: list[LineString] = []
    y = miny + spacing / 2
    flip = False
    while y < maxy:
        scan = LineString([(minx - 1, y), (maxx + 1, y)])
        clipped = flat.intersection(scan)
        # MultiLineString or GeometryCollection (tangencies add Points)
        parts = getattr(clipped, "geoms", [clipped])
        row = [g for g in parts if isinstance(g, LineString) and g.length > 1e-9]
        row.sort(key=lambda g: g.bounds[0], reverse=flip)
        segments.extend(LineString(g.coords[::-1]) if flip else g for g in row)
        flip = not flip
        y += spacing
    out = []
    for seg in segments:
        back = affinity.rotate(seg, angle_deg, origin=(cx, cy))
        out.append([(x, y) for x, y in back.coords])
    return out


@register_effect
class HatchFill(EffectModule):
    id = "hatch_fill"
    label = "Hatch fill"
    description = "Fill closed filled shapes with clipped parallel/cross hatching."
    Params = HatchFillParams

    def apply(self, paths: list[Path], params: HatchFillParams, ctx: EffectContext) -> list[Path]:
        out: list[Path] = []
        shapes: list[Polygon] = []
        for path in paths:
            pts = path.points
            closed = len(pts) > 3 and pts[0] == pts[-1]
            if not (path.filled and closed):
                out.append(path)
                continue
            if params.outline:
                out.append(path)
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                shapes.append(poly)
        if not shapes:
            return out
        # even-odd assembly: a closed loop nested inside another is a HOLE
        # (image-threshold traces holes as their own loops) — XOR is the
        # standard even-odd fill rule and degenerates to union for disjoint
        # shapes, so plain multi-shape layers behave as before
        region = shapes[0]
        for poly in shapes[1:]:
            region = region.symmetric_difference(poly)
        if params.inset > 0:
            region = region.buffer(-params.inset)
        polys = region.geoms if hasattr(region, "geoms") else [region]
        angles = [params.angle_deg]
        if params.cross:
            angles.append(math.fmod(params.angle_deg + 90.0, 180.0))
        for sub in polys:
            if not isinstance(sub, Polygon) or sub.is_empty:
                continue
            for a in angles:
                for line in _hatch(sub, params.spacing, a):
                    if len(line) >= 2:
                        out.append(Path(points=line, filled=False))
        return out
