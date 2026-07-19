"""Contract / expand — grow or shrink the layer's geometry by a signed offset.

Filled closed paths buffer as polygons: a positive offset fattens the mass,
a negative one erodes it (a shrink that vanishes emits nothing). Open
strokes shift sideways by the signed distance instead — a parallel curve,
not an outline. Each path offsets separately (no cross-path union, same
reasoning as fat_tube): draw order and per-path occlusion semantics survive.

Stack it twice — or several copies with growing offsets — and filled shapes
become insets / onion rings around the original; that is most of the
ROADMAP's "offset rings" idea with no dedicated module.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from shapely.geometry import LineString, Polygon
from shapely.validation import make_valid

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect


class ContractExpandParams(BaseModel):
    offset: float = Field(default=3.0, ge=-20.0, le=20.0, title="Offset (mm)",
                          description="Signed distance: filled shapes grow (+) or "
                                      "shrink (−); open strokes shift to the left "
                                      "of their travel direction (+, shapely "
                                      "convention) or the right (−)")
    smooth: int = Field(default=8, ge=2, le=16, title="Corner detail",
                        description="Arc segments per quarter circle on rounded "
                                    "corners and joins",
                        json_schema_extra={"group": "Fine tuning"})


@register_effect
class ContractExpand(EffectModule):
    id = "contract_expand"
    label = "Contract / expand"
    description = ("Grows or shrinks geometry by a signed mm offset — filled "
                   "shapes buffer in or out, open strokes become parallel "
                   "curves. Stack copies for insets and onion rings.")
    Params = ContractExpandParams

    def apply(self, paths: list[Path], params: ContractExpandParams,
              ctx: EffectContext) -> list[Path]:
        if params.offset == 0.0:
            return list(paths)
        out: list[Path] = []
        for path in paths:
            pts = path.points
            closed = path.is_closed
            if path.filled and closed:
                shape = Polygon(pts)
                if not shape.is_valid:
                    shape = make_valid(shape)
                shape = shape.buffer(params.offset, quad_segs=params.smooth,
                                     join_style="round")
                if shape.is_empty:
                    continue  # shrunk to nothing — honest disappearance
                geoms = list(shape.geoms) if shape.geom_type == "MultiPolygon" else [shape]
                for geom in geoms:
                    out.append(Path(points=[(x, y) for x, y in geom.exterior.coords],
                                    filled=True))
                    for ring in geom.interiors:
                        out.append(Path(points=[(x, y) for x, y in ring.coords],
                                        filled=True))
                continue
            if len(pts) < 2 or all(p == pts[0] for p in pts):
                out.append(Path(points=list(pts), filled=path.filled))
                continue  # a dot has no side to offset toward
            curve = LineString(pts).offset_curve(params.offset,
                                                 quad_segs=params.smooth,
                                                 join_style="round")
            if curve.is_empty:
                continue
            parts = list(curve.geoms) if curve.geom_type == "MultiLineString" else [curve]
            for part in parts:
                cpts = [(x, y) for x, y in part.coords]
                if len(cpts) < 2:
                    continue
                if closed and len(parts) == 1 and cpts[0] != cpts[-1]:
                    cpts.append(cpts[0])  # arrived closed → leaves closed
                out.append(Path(points=cpts, filled=path.filled))
        return out
