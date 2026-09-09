"""Open-path ribbons: seeded envelopes, interpolation and filled mask outlines.

Public geometry is millimetres. Internal 4-unit/mm coordinates retain the accepted
study's sampling and corner tolerances. Helpers are shared with the planned D3
crossing-envelope effect. No browser/Node runtime participates in resolve.
"""
from __future__ import annotations

import math
from typing import Literal
from pydantic import BaseModel, Field
from shapely.geometry import GeometryCollection
from shapely.ops import unary_union

from ..model import Path
from ..render_work import checkpoint
from ..registry import EffectContext, EffectModule, register_effect
from ._ribbon_profile import make_profiles
from ._ribbon_geometry import sample_polyline, frames, curve_frames, sharp_corners, envelope, silhouette, clip_paths, self_mask, balance_edge_widths

_SCALE = 4.0
_MAX_STEPS = 512
_MAX_POINTS = 1_000_000


def _group(name):
    return {"group": name, "groupOpen": name == "Shape"}


class RibbonParams(BaseModel):
    width: float = Field(6, ge=0, le=40, title="Amplitude (mm)", description="Maximum distance of each outer edge from the source", json_schema_extra=_group("Shape"))
    wavelength: float = Field(30, ge=.5, le=200, title="Left wavelength (mm)", json_schema_extra=_group("Shape"))
    independent_wavelengths: bool = Field(False, title="Independent wavelengths", json_schema_extra=_group("Shape"))
    wavelength_right: float = Field(45, ge=.5, le=200, title="Right wavelength (mm)", description="Used when independent wavelengths is on", json_schema_extra=_group("Shape"))
    relation: Literal["mirrored", "related", "independent"] = Field("related", title="Side relationship", description="Mirrored shares a pattern; unequal wavelengths still stretch each side separately", json_schema_extra=_group("Shape"))
    taper: float = Field(.12, ge=0, le=.49, title="Endpoint taper", json_schema_extra=_group("Shape"))
    seed: int = Field(7, ge=0, le=4294967295, title="Seed A", json_schema_extra=_group("Rhythm"))
    seed_b: int = Field(19, ge=0, le=4294967295, title="Seed B", json_schema_extra=_group("Rhythm"))
    seed_blend: float = Field(0, ge=0, le=1, title="Blend A to B", description="Normalized peak amplitude across the blend", json_schema_extra=_group("Rhythm"))
    rhythm: Literal["phrased", "legacy"] = Field("phrased", title="Crest rhythm", json_schema_extra=_group("Rhythm"))
    spacing_variation: float = Field(.75, ge=0, le=1, title="Spacing variation", json_schema_extra=_group("Rhythm"))
    height_variation: float = Field(.75, ge=0, le=1, title="Height variation", json_schema_extra=_group("Rhythm"))
    phrasing: float = Field(.7, ge=0, le=1, title="Phrase strength", json_schema_extra=_group("Rhythm"))
    variation: float = Field(.75, ge=0, le=1, title="Original rhythm variation", description="Only used by the legacy rhythm", json_schema_extra=_group("Rhythm"))
    crest_softening: float = Field(.055, ge=0, le=.2, title="Crest softening", description="Smoothing radius as a fraction of wavelength; zero keeps sharper crests", json_schema_extra=_group("Rhythm"))
    smoothing_variation: float = Field(0, ge=0, le=1, title="Uneven crest softening", description="Independent seeded smoothing for the rising and falling flank of each crest, blended smoothly through the peak", json_schema_extra=_group("Rhythm"))
    interpolation: Literal["spine", "edges"] = Field("spine", title="Interpolate", description="Spine keeps the source; edges spans both envelopes with no dedicated centre strand and balances their width near sharp corners", json_schema_extra=_group("Strands"))
    fractured_edges: bool = Field(False, description="Experimental polygon fractures in edge interpolation", json_schema_extra={"hidden": True})
    steps: int = Field(10, ge=1, le=512, title="Strands per side", json_schema_extra=_group("Strands"))
    auto_density: bool = Field(False, title="Density from assigned pen", description="Uses the layer pen's line width with 10% overlap; count stays fixed throughout seed blending", json_schema_extra=_group("Strands"))
    width_by_length: bool = Field(False, title="Trim width by path length", description="Shorter paths lose outer pairs without moving surviving strands", json_schema_extra=_group("Strands"))
    remove_outer: int = Field(0, ge=0, le=511, title="Remove outer pairs", description="Shared cutoff: already length-trimmed paths change only when this cutoff reaches them; at least one pair remains", json_schema_extra=_group("Strands"))
    output: Literal["strands", "outline", "solid"] = Field("strands", title="Output", description="Solid emits filled mask outlines; pen strokes remain paths, not painted pixels", json_schema_extra=_group("Output"))
    merge_overlaps: bool = Field(True, title="Merge outline overlaps", json_schema_extra=_group("Output"))
    solid_occluder: bool = Field(False, title="Solid occluder", description="Emit filled boundary rings so the layer can mask lower layers", json_schema_extra=_group("Output"))
    mask_overlaps: bool = Field(False, title="Mask overlaps", description="Later paths and passages cover earlier ones", json_schema_extra=_group("Output"))
    reverse_order: bool = Field(False, title="Reverse overlap order", json_schema_extra=_group("Output"))


def _smooth(t):
    return t*t*(3-2*t)


def _taper(s, total, amount):
    edge = max(1e-9, total*amount)
    return min(1., _smooth(max(0., min(1., s/edge))), _smooth(max(0., min(1., (total-s)/edge))))


def _points(path):
    out = []
    for i, (x, y) in enumerate(path.points):
        if not i & 255:
            checkpoint()
        p = (x*_SCALE, y*_SCALE)
        if not out or p != out[-1]:
            out.append(p)
    return out


def _prepare(points, params, ctx):
    checkpoint()
    options = params.model_dump()
    for key in ("width", "wavelength", "wavelength_right"):
        options[key] *= _SCALE
    wave = min(options["wavelength"], options["wavelength_right"]) if params.independent_wavelengths else options["wavelength"]
    spine, ss, total = sample_polyline(points, min(2., wave/12))
    frame = frames(spine) if params.fractured_edges else curve_frames(points, spine, ss)
    corners = sharp_corners(spine, ss)
    seed_a = (params.seed ^ ctx.seed) & 0xffffffff
    seed_b = (params.seed_b ^ ctx.seed) & 0xffffffff
    a = make_profiles(total, options, seed_a)
    b = a if seed_a == seed_b else make_profiles(total, options, seed_b)
    t = params.seed_blend
    taper = [options["width"]*_taper(s, total, params.taper) for s in ss]
    samples_a = []
    samples_b = []
    for profile in a:
        checkpoint()
        samples_a.append([profile(s)*gain for s, gain in zip(ss, taper)])
    for profile in b:
        checkpoint()
        samples_b.append([profile(s)*gain for s, gain in zip(ss, taper)])
    widths = []
    for aa, bb in zip(samples_a, samples_b):
        checkpoint()
        if t == 0 or seed_a == seed_b:
            values = aa[:]
        elif t == 1:
            values = bb[:]
        else:
            values = [x+(y-x)*t for x,y in zip(aa,bb)]
            target = max(aa)+(max(bb)-max(aa))*t
            peak = max(values)
            if peak > 1e-12:
                values = [v*target/peak for v in values]
        values[0] = values[-1] = 0.
        widths.append(values)
    required = params.steps
    if params.auto_density and params.output == "strands":
        pen_width = ctx.line_diameter_mm*_SCALE
        left = max(max(samples_a[0]), max(samples_b[0]))
        right = max(max(samples_a[1]), max(samples_b[1]))
        max_frame = max(math.hypot(*n) for n in frame)
        span = (left+right if params.interpolation == "edges" else max(left,right))*max_frame
        intervals = math.ceil(span/(pen_width*.9))
        required = max(1, math.ceil((intervals+1)/2) if params.interpolation == "edges" else intervals)
        if required > _MAX_STEPS:
            raise ValueError("Ribbon pen density exceeds 512 strands per side; reduce amplitude or use a wider pen")
    return dict(spine=spine, ss=ss, total=total, frame=frame, corners=corners,
                widths=widths, width=options["width"], required=required)


def _construct(data, params, steps, retained):
    checkpoint()
    spine, ss, frame = data["spine"], data["ss"], data["frame"]
    left, right = data["widths"]
    if params.interpolation == "edges" and not params.fractured_edges:
        left,right = balance_edge_widths(left,right,ss,data["corners"],data["width"])
    def side(widths):
        checkpoint()
        nodes = [{"p": (p[0]+n[0]*w,p[1]+n[1]*w), "s":s}
                 for p,n,w,s in zip(spine,frame,widths,ss)]
        nodes[0]["p"],nodes[-1]["p"] = spine[0],spine[-1]
        join = envelope
        if params.interpolation == "edges" and params.fractured_edges:
            from ._ribbon_fracture import fractured_envelope
            join = fractured_envelope
        return join(nodes,spine,ss,data["corners"],data["width"]) if data["corners"] else nodes
    spine_nodes = [{"p":p,"s":s} for p,s in zip(spine,ss)]
    if params.interpolation == "edges":
        count = 2*steps
        lanes = []
        for i in range(steps-retained, count-(steps-retained)):
            checkpoint()
            lanes.append(side([a+(-b-a)*i/(count-1) for a,b in zip(left,right)]))
        anchor = side([(a-b)/2 for a,b in zip(left,right)])
    else:
        lanes = []
        for i in range(retained, 0, -1):
            checkpoint()
            lanes.append(side([w*i/steps for w in left]))
        lanes += [spine_nodes]
        for i in range(1, retained + 1):
            checkpoint()
            lanes.append(side([-w*i/steps for w in right]))
        anchor = spine_nodes
    left_nodes,right_nodes = lanes[0],lanes[-1]
    shape = None
    if params.output != "strands" or params.solid_occluder or params.mask_overlaps:
        shape = silhouette(left_nodes,right_nodes,anchor)
    if params.output == "strands" and params.mask_overlaps:
        strokes = self_mask(lanes,left_nodes,right_nodes,ss,data["corners"],data["width"],params.reverse_order)
    else:
        strokes = [[n["p"] for n in lane] for lane in lanes]
    raw = [n["p"] for n in left_nodes]+[n["p"] for n in reversed(right_nodes)]
    if raw[-1] != raw[0]:
        raw.append(raw[0])
    return dict(strokes=strokes,shape=shape,raw=raw)


def _rings(shape):
    if shape is None or shape.is_empty:
        return []
    polygons = [shape] if shape.geom_type == "Polygon" else [g for g in getattr(shape,"geoms",[]) if g.geom_type == "Polygon"]
    return [list(r.coords) for p in polygons for r in [p.exterior,*p.interiors]]


def _path(points, filled=False):
    return Path(points=[(x/_SCALE,y/_SCALE) for x,y in points],filled=filled)


@register_effect
class Ribbon(EffectModule):
    id = "ribbon"
    label = "Ribbon"
    description = "Seeded swelling ribbons along open paths, with strand, outline and solid-mask outputs."
    Params = RibbonParams

    def apply(self, paths: list[Path], params: RibbonParams, ctx: EffectContext) -> list[Path]:
        bypass, prepared = [], []
        for path in paths:
            checkpoint()
            points = _points(path)
            if path.is_closed or len(points)<2:
                bypass.append(path)
            else:
                prepared.append(_prepare(points,params,ctx))
        if not prepared:
            return list(paths)
        steps = max(d["required"] for d in prepared)
        longest = max(d["total"] for d in prepared)
        counts = [max(1,min(math.ceil(steps*d["total"]/longest-1e-10) if params.width_by_length else steps,
                          steps-params.remove_outer)) for d in prepared]
        estimate = sum(len(d["spine"])*(2*k+(params.interpolation=="spine")) for d,k in zip(prepared,counts))
        if estimate > _MAX_POINTS:
            raise ValueError("Ribbon exceeds one million points; reduce strand density or simplify the source paths")
        built = []
        for data, count in zip(prepared, counts):
            checkpoint()
            built.append(_construct(data, params, steps, count))
        if params.mask_overlaps and params.output == "strands" and len(built)>1:
            for i,item in enumerate(built):
                checkpoint()
                blockers = [r["shape"] for j,r in enumerate(built) if (j<i if params.reverse_order else j>i)]
                if blockers:
                    checkpoint()
                    mask = unary_union(blockers)
                    checkpoint()
                    item["strokes"] = clip_paths(item["strokes"], mask)
        need_fill = params.solid_occluder or params.output == "solid"
        if need_fill or params.output != "strands" and params.merge_overlaps:
            checkpoint()
            merged = unary_union([r["shape"] for r in built if r["shape"] is not None])
            checkpoint()
        else:
            merged = GeometryCollection()
        if params.output == "strands":
            out = [_path(p) for r in built for p in r["strokes"] if len(p)>1]
            if need_fill:
                out += [_path(r,True) for r in _rings(merged)]
        elif params.merge_overlaps or need_fill:
            out = [_path(r,need_fill) for r in _rings(merged)]
        else:
            out = [_path(r["raw"]) for r in built]
        return bypass+out
