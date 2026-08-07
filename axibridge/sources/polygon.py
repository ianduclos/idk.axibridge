"""Regular polygon / star generator — produces *filled* closed shapes, which
makes it the natural test subject for fill-aware occlusion masks."""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source


class PolygonParams(BaseModel):
    sides: int = Field(default=6, ge=3, le=64, title="Sides / points")
    radius: float = Field(default=40, ge=1, le=200, title="Radius (mm)")
    star_ratio: float = Field(
        default=1.0, ge=0.1, le=1.0, title="Star ratio",
        description="Inner/outer radius — 1.0 is a polygon, smaller makes a star",
    )
    rotation_deg: float = Field(default=0, ge=0, le=360, title="Rotation (°)")
    rings: int = Field(default=1, ge=1, le=40, title="Concentric rings")
    ring_gap: float = Field(default=3, ge=0.2, le=30, title="Ring gap (mm)")
    filled: bool = Field(default=True, title="Filled (solid occlusion mask)",
                         description="Off = outline only; masks as a stroke band when occluding")


@register_source
class PolygonSource(SourceModule):
    id = "polygon"
    orientation = "none"  # radial about its centre
    label = "Polygon / star"
    description = "Closed (optionally filled) shape — the occluder workhorse."
    Params = PolygonParams

    def generate(self, params: PolygonParams) -> PathDocument:
        p = params
        cx = cy = p.radius + 2
        paths: list[Path] = []
        n = p.sides * (2 if p.star_ratio < 1.0 else 1)
        for ring in range(p.rings):
            r_outer = p.radius - ring * p.ring_gap
            if r_outer <= 0.1:
                break
            pts = []
            for i in range(n + 1):
                t = math.radians(p.rotation_deg) + 2 * math.pi * i / n - math.pi / 2
                r = r_outer if (p.star_ratio >= 1.0 or i % 2 == 0) else r_outer * p.star_ratio
                pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
            pts[-1] = pts[0]
            # only the outermost ring is the occlusion silhouette
            paths.append(Path(points=pts, filled=p.filled and ring == 0))
        side = 2 * (p.radius + 2)
        return PathDocument(
            layers=[Layer(id=1, name="polygon", color="#26241f", paths=paths)],
            width=side, height=side, source=f"polygon {p.sides}",
        )
