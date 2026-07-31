"""Fat tube — the layer's paths become constant-width pipes with round caps.

The second Oehlen regime effect (docs/IDEAS-oehlen-pass.md §1): each stroke
is offset into a `width`-mm tube outline, emitted ``filled=True`` — so a
tube layer genuinely *occludes* layers beneath it through the existing mask
machinery, and two tube layers over each other read as pipes crossing
over/under (image 5's interlock) with no new machinery. Self-crossing
strokes merge into one ink mass with holes where loops enclose paper.

By default each input path buffers separately (no cross-path union): draw
order and per-path occlusion semantics survive. ``solid`` instead unions
every tube into ONE merged mass — no seam rings where strokes cross, a
single silhouette (plus enclosed-paper holes). Dots become discs. Stack
`hatch_fill` after it to put ink inside the pipes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from shapely.geometry import LineString, Point as ShPoint
from shapely.ops import unary_union

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect


class FatTubeParams(BaseModel):
    width: float = Field(default=5.0, ge=0.5, le=40.0, title="Width (mm)",
                         description="Tube diameter on the sheet")
    solid: bool = Field(default=False, title="Solid (merge overlaps)",
                        description="Union all tubes into one solid shape — no "
                                    "seam outlines where strokes cross each other")
    smooth: int = Field(default=8, ge=2, le=16, title="Cap detail",
                        description="Arc segments per quarter circle on caps and joins",
                        json_schema_extra={"group": "Fine tuning"})


@register_effect
class FatTube(EffectModule):
    id = "fat_tube"
    label = "Fat tube"
    description = ("Offsets every stroke into a constant-width round-capped pipe "
                   "(filled) — tube layers occlude and interlock via the mask system.")
    Params = FatTubeParams

    def apply(self, paths: list[Path], params: FatTubeParams, ctx: EffectContext) -> list[Path]:
        r = params.width / 2.0
        shapes = []
        for path in paths:
            pts = path.points
            if not pts:
                continue
            if len(pts) == 1 or all(p == pts[0] for p in pts):
                shape = ShPoint(pts[0]).buffer(r, quad_segs=params.smooth)
            else:
                shape = LineString(pts).buffer(
                    r, quad_segs=params.smooth, cap_style="round", join_style="round")
            if not shape.is_empty:
                shapes.append(shape)
        if params.solid and shapes:
            shapes = [unary_union(shapes)]

        out: list[Path] = []
        for shape in shapes:
            geoms = list(shape.geoms) if shape.geom_type == "MultiPolygon" else [shape]
            for geom in geoms:
                if geom.geom_type != "Polygon" or geom.is_empty:
                    continue  # union can spill stray lines/points at zero width
                out.append(Path(points=[(x, y) for x, y in geom.exterior.coords], filled=True))
                for ring in geom.interiors:
                    out.append(Path(points=[(x, y) for x, y in ring.coords], filled=True))
        return out
