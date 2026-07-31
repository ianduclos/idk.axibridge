"""Invert — the layer's ink becomes a hole; the page around it becomes ink.

The negative of the layer against a page-boundary rectangle: everything the
layer WOULD have plotted (filled shapes as polygons, open strokes as a band
``stroke_width`` mm wide — the same ink accounting the occlusion mask uses)
is subtracted from the page rect, and the result is emitted as closed
``filled=True`` rings. Put a fill effect after it and the page gets inked
*except* where the layer's shapes were; stacked above other layers, the
inverted mass occludes them through the normal mask machinery.

The boundary comes from the project, not a param: ``ctx.page`` (the paper
guide, or the full bed when no guide is set) — so the negative follows the
page setup you already have. ``margin`` insets that rect on every side,
cropping the outer edge of the inverted shape away from the page boundary
(the ask: "crop the outer shape from the margins").

Nested filled paths use even-odd parity — a donut's hole stays paper, not an
ink island — matching ``compose.build_mask``'s rule. The negative of NOTHING
is the whole page rect (page minus nothing): an empty input emits the full
boundary, and an empty result (the layer covers the whole page, or the
margin collapsed the rect) emits nothing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from .. import compose
from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect

#: a ring shorter than this (mm) is a numerical crumb from the boolean
_MIN_RING_LEN = 0.05


class InvertParams(BaseModel):
    margin: float = Field(
        default=0.0, ge=0.0, le=50.0, title="Page margin (mm)",
        description="Crop the boundary rectangle inward on every side")
    stroke_width: float = Field(
        default=0.5, ge=0.05, le=5.0, title="Stroke width (mm)",
        description="Open paths join the negative mass as a band this wide — "
                    "match your pen so their ink is protected too")


def _fill_mass(polys: list[Polygon]):
    """Even-odd parity over the filled paths (build_mask's rule): a ring
    nested inside another is a hole, not an ink island. Depth = how many
    other rings contain it; even depths add, odd depths subtract."""
    if not polys:
        return None
    even: list[Polygon] = []
    odd: list[Polygon] = []
    for i, p in enumerate(polys):
        depth = sum(1 for j, o in enumerate(polys) if i != j and o.contains(p))
        (odd if depth % 2 else even).append(p)
    mass = unary_union(even) if even else None
    if odd and mass is not None:
        mass = mass.difference(unary_union(odd))
    return mass


def _ink_mass(paths: list[Path], stroke_width: float):
    """Everything the layer would ink, as one shapely region: filled paths as
    even-odd polygons (nesting = holes, like build_mask), open paths as a
    swept band."""
    fill_polys: list[Polygon] = []
    strokes: list[LineString] = []
    for p in paths:
        if len(p.points) < 2:
            continue
        if p.filled and len(p.points) >= 4:
            poly = Polygon(p.points)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                fill_polys.append(poly)
        else:
            strokes.append(LineString(p.points))
    mass = _fill_mass(fill_polys)
    if strokes:
        band = unary_union(
            [s.buffer(stroke_width / 2.0, quad_segs=8,
                      cap_style="round", join_style="round") for s in strokes])
        mass = band if mass is None else mass.union(band)
    return mass


def _rings(geom) -> list[list[tuple[float, float]]]:
    """Every ring of the inverted region — exteriors and holes alike — as
    closed point lists. Holes stay implicit in the nesting (brush.py's rule)."""
    if geom is None or geom.is_empty:
        return []
    parts = geom.geoms if hasattr(geom, "geoms") else [geom]
    out: list[list[tuple[float, float]]] = []
    for poly in parts:
        if not isinstance(poly, Polygon) or poly.is_empty:
            continue
        for ring in [poly.exterior, *poly.interiors]:
            pts = [(x, y) for x, y in ring.coords]
            if len(pts) < 4 or ring.length < _MIN_RING_LEN:
                continue
            out.append(pts)
    return out


@register_effect
class Invert(EffectModule):
    id = "invert"
    label = "Invert (page negative)"
    description = ("The layer's ink becomes a hole in a page-size rectangle — "
                   "the page gets inked everywhere EXCEPT the shapes. Boundary "
                   "follows the paper guide; margin crops the outer edge.")
    Params = InvertParams

    def apply(self, paths: list[Path], params: InvertParams, ctx: EffectContext) -> list[Path]:
        px, py, pw, ph = ctx.page or (0.0, 0.0, compose.BED_WIDTH, compose.BED_HEIGHT)
        if pw - 2 * params.margin <= 0 or ph - 2 * params.margin <= 0:
            return []  # margin collapsed the page rect (box() would normalise
                       # the inverted corners and pretend nothing happened)
        boundary = box(px + params.margin, py + params.margin,
                       px + pw - params.margin, py + ph - params.margin)
        mass = _ink_mass(paths, params.stroke_width)
        region = boundary if mass is None else boundary.difference(mass)
        return [Path(points=ring, filled=True) for ring in _rings(region)]
