"""The layer compositor — v2's spine.

A :class:`Project` is an ordered list of :class:`CanvasLayer` (list order =
z-order, last = top), each carrying provenance, an affine transform, a
non-destructive effect stack, a pen reference, and occlusion properties.
The compositor resolves the stack down to per-layer **resolved geometry** —
the geometry that actually gets drawn — and flattens it into the v1
:class:`PathDocument`, which the entire execution column consumes unchanged.

Resolve order per layer (user-confirmed decision):

    placed   = transform(source)        # canvas placement, plain affine
    shaped   = effect_stack(placed)     # effects in PAPER space: mm mean mm
    resolved = shaped − union of occluder masks ABOVE this layer

Occlusion notes:

* Masks are built from *shaped* (pre-clip) geometry — like physical opaque
  sheets, an occluder that is itself partially hidden still masks fully.
* Masks are computed once, in the shared design frame, **pen-invariant**: the
  per-pen nib offset is a plot-time toolpath compensation that brings every
  pen's ink *to* the design position, so one mask is correct for all pens.
  It is never folded into mask geometry.
* The mask of a filled path is its polygon; a stroke-only path masks as a
  swept band at its pen's line width. The layer's signed ``occlusion_margin``
  buffers the mask: positive opens a negative-space gap, negative lets lower
  layers bleed into the occluder deliberately.

Geometry engine is Shapely (already a vpype dependency): occult has no
signed margins, no per-layer occluder/receives flags and no stroke-band
masks, so the compositor talks to shapely directly.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field
from shapely.geometry import LineString, Point as ShPoint, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .model import Layer, Path, PathDocument
from .registry import EffectContext, get_effect
from .stores import Pen

#: AxiDraw V3/A4 usable travel — the canvas IS this rectangle, in mm.
BED_WIDTH = 300.0
BED_HEIGHT = 218.0

#: Mask band width for stroke-only occluder paths when no pen is assigned.
DEFAULT_LINE_DIAMETER_MM = 0.5

INK = "#26241f"  # default ink colour when a layer has no pen


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Affine(BaseModel):
    """SVG ``matrix(a b c d e f)``: x' = a·x + c·y + e, y' = b·x + d·y + f.

    The same six numbers drive the on-screen ``<g transform>`` and the
    server-side bake — the canvas editor and the compositor cannot disagree.
    """

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    @property
    def translation(self) -> tuple[float, float]:
        return (self.e, self.f)


class EffectStep(BaseModel):
    effect: str
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class LayerSource(BaseModel):
    """Provenance: where a layer's source geometry comes from.

    ``generator`` layers keep id+params (re-editable; "regenerate" re-runs)
    *and* snapshot their output to an SVG in the project's ``sources/`` so the
    exact geometry survives generator-code drift. ``svg`` layers reference an
    uploaded file (verbatim copy in ``sources/``) and one layer within it.
    ``baked`` layers had their transform+effects consolidated into the source
    geometry; generator provenance (if any) is kept so "regenerate" can return
    them to live generator output. ``tween`` layers interpolate two sibling
    layers (see tween.py); their ``params`` hold a TweenParams dict and their
    geometry is re-materialised from the referenced layers at every resolve.
    """

    type: Literal["generator", "svg", "baked", "tween"]
    generator: str | None = None
    params: dict[str, Any] | None = None
    file: str | None = None          # project-relative: sources/<name>.svg
    svg_layer: int | None = None     # layer id within the uploaded SVG
    quantization_mm: float = 0.1


class CanvasLayer(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "layer"
    visible: bool = True
    source: LayerSource
    transform: Affine = Field(default_factory=Affine)
    effects: list[EffectStep] = Field(default_factory=list)
    pen_id: str | None = None
    occluder: bool = False
    receives_occlusion: bool = True
    occlusion_margin_mm: float = Field(default=0.0, ge=-20, le=20,
                                       description="Signed: + opens a gap, − bleeds under")
    frame_offset: float = Field(
        default=0.0, ge=-1.0, le=1.0,
        description="Added to the generator's 'frame' when sampling an image "
                    "sequence (result clamped 0..1); layers can time-shift the "
                    "same clip, and interpolation layers lerp it")


class PaperGuide(BaseModel):
    """Movable registration rectangle (where to tape the paper), machine frame.
    Default: A4 centred on the bed — physically landscape, because A4's long
    edge only fits the machine's X axis."""

    x: float = 1.5
    y: float = 4.0
    width: float = 297.0
    height: float = 210.0


class PlotOptions(BaseModel):
    """Plot-pass optimisation, applied to the resolved geometry of each pass
    (this replaces v1's user-arranged global pipeline)."""

    sort: bool = Field(default=True, title="Sort paths (minimise pen-up travel)")
    merge: bool = Field(default=True, title="Merge near-coincident endpoints")
    # 0.05 mm (vpype's own default) is sub-visible: joins flattening seams
    # without chaining genuinely separate strokes into pen-down bridges the
    # preview never showed.
    merge_tolerance_mm: float = Field(default=0.05, ge=0.0, le=10.0, title="Merge tolerance (mm)")
    simplify: bool = Field(default=False, title="Simplify (drop redundant points)")
    simplify_tolerance_mm: float = Field(default=0.05, ge=0.001, le=2.0, title="Simplify tolerance (mm)")
    reloop: bool = Field(default=False, title="Reloop closed paths (randomise seams)")


class Project(BaseModel):
    version: int = 2
    name: str = "untitled"
    layers: list[CanvasLayer] = Field(default_factory=list)
    guide: PaperGuide = Field(default_factory=PaperGuide)
    view: Literal["portrait", "landscape"] = "portrait"  # display-only
    pens_used: dict[str, Pen] = Field(default_factory=dict)
    backend_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    plot_options: PlotOptions = Field(default_factory=PlotOptions)

    def layer(self, layer_id: str) -> CanvasLayer:
        for lyr in self.layers:
            if lyr.id == layer_id:
                return lyr
        raise KeyError(f"unknown layer: {layer_id!r}")


# ---------------------------------------------------------------------------
# Compositor
# ---------------------------------------------------------------------------


def _layer_seed(layer_id: str) -> int:
    return int.from_bytes(hashlib.sha256(layer_id.encode()).digest()[:4], "big")


def transform_paths(paths: list[Path], t: Affine) -> list[Path]:
    return [Path(points=[t.apply(x, y) for x, y in p.points], filled=p.filled) for p in paths]


def shape_layer(layer: CanvasLayer, source_paths: list[Path]) -> list[Path]:
    """transform → effect stack. Pure; caller caches."""
    placed = transform_paths(source_paths, layer.transform)
    ctx = EffectContext(
        layer_id=layer.id,
        translation=layer.transform.translation,
        seed=_layer_seed(layer.id),
    )
    for step in layer.effects:
        if not step.enabled:
            continue
        eff = get_effect(step.effect)
        ok, reason = eff.available()
        if not ok:
            raise RuntimeError(f"effect {step.effect!r} unavailable: {reason}")
        placed = eff.apply(placed, eff.Params(**step.params), ctx)
    return placed


def build_mask(
    shaped: list[Path], line_diameter_mm: float, margin_mm: float
) -> BaseGeometry | None:
    """An occluder layer's mask: filled closed paths as polygons, everything
    else as a swept band at the pen's line width, buffered by the signed
    margin."""
    geoms: list[BaseGeometry] = []
    half = max(line_diameter_mm, 0.01) / 2.0
    for p in shaped:
        pts = p.points
        if len(pts) >= 4 and p.filled and pts[0] == pts[-1]:
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                geoms.append(poly)
        elif len(pts) >= 2:
            geoms.append(LineString(pts).buffer(half))
        elif pts:
            geoms.append(ShPoint(pts[0]).buffer(half))
    if not geoms:
        return None
    mask = unary_union(geoms)
    if margin_mm:
        mask = mask.buffer(margin_mm)
    return None if mask.is_empty else mask


def _dedupe(pts: list[tuple[float, float]], eps: float = 1e-7) -> list[tuple[float, float]]:
    """Drop degenerate (sub-eps) segments — shapely's difference can emit
    near-coincident trailing vertices that break exact reproducibility."""
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    return out


def clip_paths(shaped: list[Path], mask: BaseGeometry) -> list[Path]:
    """Subtract a mask from pen-down geometry. Clipped fragments keep the
    source path's ``filled`` flag only if they survived intact and closed
    (an open fragment of a filled outline is just a line)."""
    out: list[Path] = []
    for p in shaped:
        if len(p.points) == 1:
            if not mask.covers(ShPoint(p.points[0])):
                out.append(p)
            continue
        diff = LineString(p.points).difference(mask)
        if diff.is_empty:
            continue
        pieces = getattr(diff, "geoms", [diff])
        for g in pieces:
            if g.geom_type != "LineString" or len(g.coords) < 2:
                continue
            pts = _dedupe([(float(x), float(y)) for x, y in g.coords])
            if len(pts) < 2:
                continue
            survived_closed = len(pts) > 2 and pts[0] == pts[-1]
            out.append(Path(points=pts, filled=p.filled and survived_closed))
    return out


def line_diameter_for(layer: CanvasLayer, pens: dict[str, Pen]) -> float:
    pen = pens.get(layer.pen_id or "")
    return pen.line_diameter_mm if pen else DEFAULT_LINE_DIAMETER_MM


def resolve_project(
    project: Project,
    source_geometry: dict[str, list[Path]],
    pens: dict[str, Pen],
    shaped_cache: dict[str, tuple[str, list[Path]]] | None = None,
) -> dict[str, list[Path]]:
    """Resolve every visible layer. Returns ``{layer_id: resolved paths}``.

    This is THE single source of truth: preview, per-layer estimates, and
    plotting all read their geometry from here — there is no second path.

    ``shaped_cache`` (optional, owned by the session) memoises the
    transform+effects stage per layer, keyed by a content hash, so dragging
    one layer doesn't re-run every other layer's effect stack.
    """
    # 1. shape every visible layer (cached)
    shaped: dict[str, list[Path]] = {}
    for layer in project.layers:
        if not layer.visible:
            continue
        src = source_geometry.get(layer.id, [])
        if shaped_cache is not None:
            key = _shape_key(layer, src)
            hit = shaped_cache.get(layer.id)
            if hit is not None and hit[0] == key:
                shaped[layer.id] = hit[1]
                continue
            shaped[layer.id] = shape_layer(layer, src)
            shaped_cache[layer.id] = (key, shaped[layer.id])
        else:
            shaped[layer.id] = shape_layer(layer, src)

    # 2. occlusion, top -> bottom, accumulating the mask union
    resolved: dict[str, list[Path]] = {}
    cum_mask: BaseGeometry | None = None
    for layer in reversed(project.layers):
        if not layer.visible:
            continue
        s = shaped[layer.id]
        if layer.receives_occlusion and cum_mask is not None:
            resolved[layer.id] = clip_paths(s, cum_mask)
        else:
            resolved[layer.id] = s
        if layer.occluder:
            m = build_mask(s, line_diameter_for(layer, pens), layer.occlusion_margin_mm)
            if m is not None:
                cum_mask = m if cum_mask is None else unary_union([cum_mask, m])
    return resolved


def _shape_key(layer: CanvasLayer, src: list[Path]) -> str:
    h = hashlib.sha256()
    h.update(str(id(src)).encode())  # source list identity: replaced wholesale on regen
    h.update(json.dumps({
        "t": layer.transform.model_dump(),
        "e": [s.model_dump() for s in layer.effects],
    }, sort_keys=True).encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Flatten to the execution contract
# ---------------------------------------------------------------------------


def flatten_to_document(
    project: Project,
    resolved: dict[str, list[Path]],
    pens: dict[str, Pen],
    target: str = "all",
    pen_offsets: dict[str, tuple[float, float]] | None = None,
) -> PathDocument:
    """Resolved geometry → :class:`PathDocument` for the execution column.

    ``target`` is ``"all"`` or a layer id ("plot this layer" = plot its
    *resolved* geometry, clipped by whatever occludes it). ``pen_offsets``
    maps layer id → that layer's pen nib offset; the pass is translated by
    the *negative* of it — the plot-time toolpath compensation that registers
    multi-pen passes on the same sheet. Per layer, because an "all" pass may
    mix pens.
    """
    out_layers: list[Layer] = []
    for i, layer in enumerate(project.layers):
        if target != "all" and layer.id != target:
            continue
        if not layer.visible or layer.id not in resolved:
            continue
        paths = resolved[layer.id]
        ox, oy = (pen_offsets or {}).get(layer.id, (0.0, 0.0))
        if ox or oy:
            paths = [Path(points=[(x - ox, y - oy) for x, y in p.points], filled=p.filled)
                     for p in paths]
        pen = pens.get(layer.pen_id or "")
        out_layers.append(Layer(
            id=i + 1,
            name=layer.name,
            color=(pen.color if pen else INK),
            paths=paths,
        ))
    return PathDocument(
        layers=out_layers, width=BED_WIDTH, height=BED_HEIGHT,
        source=f"{project.name} [{target}]",
    )
