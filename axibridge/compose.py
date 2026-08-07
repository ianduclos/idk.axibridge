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
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, Field, model_validator
import shapely
from shapely.geometry import LineString, Point as ShPoint, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .model import Layer, Path, PathDocument, is_closed
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
    draw: bool = True
    source: LayerSource
    transform: Affine = Field(default_factory=Affine)
    effects: list[EffectStep] = Field(default_factory=list)
    pen_id: str | None = None
    occluder: bool = False
    receives_occlusion: bool = True
    occlude_groups: list[Literal["A", "B", "C", "D"]] = Field(
        default_factory=list,
        description="When this layer occludes: which groups it masks. EMPTY = "
                    "mask every receiver below (the classic global occluder); "
                    "otherwise only receivers listing any of these groups")
    receives_groups: list[Literal["A", "B", "C", "D"]] = Field(
        default_factory=list,
        description="Group channels this receiver listens to, ON TOP of the "
                    "global mask (additive semantics). EMPTY = receives only "
                    "ungrouped occlusion")

    @model_validator(mode="before")
    @classmethod
    def _migrate_occlusion_group(cls, data):
        """Load-time migration for projects saved when occlusion had a single
        shared ``occlusion_group`` letter: it meant both directions, so it
        becomes both lists."""
        if isinstance(data, dict):
            legacy = data.pop("occlusion_group", None)
            if legacy:
                data.setdefault("occlude_groups", [legacy])
                data.setdefault("receives_groups", [legacy])
        return data
    region: bool = Field(
        default=False,
        description="Affects below: this layer's placed silhouette becomes a "
                    "mask and its effect stack shapes the layers underneath, "
                    "clipped to the region — the layer itself is never drawn. "
                    "(Adjustment-layer model; see docs/IDEAS-oehlen-pass.md §2)")
    region_boundary: Literal["cut", "continuous"] = Field(
        default="cut",
        description="Region seam handling: 'cut' lifts the pen at every "
                    "boundary crossing; 'continuous' stitches each path below "
                    "back into ONE path — outside sections verbatim, inside "
                    "sections replaced by their effected geometry, the seam a "
                    "drawn connection wherever the effect moved the ends")
    occlusion_margin_mm: float = Field(default=0.0, ge=-20, le=20,
                                       description="Signed: + opens a gap, − bleeds under")
    frame_offset: float = Field(
        default=0.0, ge=-1.0, le=1.0,
        description="Added to the generator's 'frame' when sampling an image "
                    "sequence (result clamped 0..1); layers can time-shift the "
                    "same clip, and interpolation layers lerp it")
    frame_follow: bool = Field(
        default=False,
        description="Clip advances with the master timeline: effective frame = "
                    "frame + frame_offset + master t (clamped 0..1); positions "
                    "never move")


class PaperGuide(BaseModel):
    """Movable registration rectangle (where to tape the paper), machine frame.
    Default: A4 registered at the machine origin — physically landscape,
    because A4's long edge only fits the machine's X axis."""

    x: float = 0.0
    y: float = 0.0
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
    crop: Literal["off", "guide", "bed", "custom"] = Field(
        default="off", title="Crop to",
        description="Clip plotted output (and exports/estimates) to: the paper "
                    "guide, the whole bed, or a custom rectangle")
    crop_margin_mm: float = Field(
        default=0.0, ge=0.0, le=100.0, title="Crop margin (mm)",
        description="Inward inset from the crop rectangle's edges")
    crop_x: float = Field(default=1.5, ge=0, le=300, title="Custom crop x (mm)")
    crop_y: float = Field(default=4.0, ge=0, le=218, title="Custom crop y (mm)")
    crop_w: float = Field(default=297.0, ge=1, le=300, title="Custom crop width (mm)")
    crop_h: float = Field(default=210.0, ge=1, le=218, title="Custom crop height (mm)")


class CaptureSnapshot(BaseModel):
    """Project/source state at capture time, excluding staging itself.

    Frozen staged sheets are the output tray. This snapshot is the optional
    recipe/source layer used later when two compatible captures generate an
    interpolated batch.
    """

    name: str = "untitled"
    layers: list[CanvasLayer] = Field(default_factory=list)
    guide: PaperGuide = Field(default_factory=PaperGuide)
    view: Literal["portrait", "landscape"] = "portrait"
    pens_used: dict[str, Pen] = Field(default_factory=dict)
    backend_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    plot_options: PlotOptions = Field(default_factory=PlotOptions)
    source_geometry: dict[str, list[Path]] = Field(default_factory=dict)
    svg_files: dict[str, str] = Field(default_factory=dict)


class StagedPass(BaseModel):
    pen_id: str = ""
    name: str = "no pen"
    color: str = INK
    paths: int = 0
    points: int = 0
    pen_down_distance: float = 0.0


class StagedSheet(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "sheet"
    file: str | None = None  # project-relative: staging/<id>.svg
    passes: list[StagedPass] = Field(default_factory=list)


class CaptureGroup(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "capture"
    kind: Literal["plot", "frame", "sheet", "batch"] = "sheet"
    format: dict[str, Any] = Field(default_factory=dict)
    sheets: list[StagedSheet] = Field(default_factory=list)
    snapshot: CaptureSnapshot | None = None
    source_capture_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Project(BaseModel):
    version: int = 2
    name: str = "untitled"
    layers: list[CanvasLayer] = Field(default_factory=list)
    guide: PaperGuide = Field(default_factory=PaperGuide)
    view: Literal["portrait", "landscape"] = "portrait"  # display-only
    pens_used: dict[str, Pen] = Field(default_factory=dict)
    backend_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    plot_options: PlotOptions = Field(default_factory=PlotOptions)
    staging: list[CaptureGroup] = Field(default_factory=list)

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


def guide_page(project: Project) -> tuple[float, float, float, float]:
    """The page rect page-relative effects see (paper guide, else full bed)."""
    g = project.guide
    if g is None:
        return (0.0, 0.0, BED_WIDTH, BED_HEIGHT)
    return (g.x, g.y, g.width, g.height)


def _layer_ctx(layer: CanvasLayer,
               page: tuple[float, float, float, float] | None = None) -> EffectContext:
    return EffectContext(
        layer_id=layer.id,
        translation=layer.transform.translation,
        seed=_layer_seed(layer.id),
        page=page,
    )


def _apply_effect_stack(paths: list[Path], steps: list[EffectStep], ctx: EffectContext) -> list[Path]:
    for step in steps:
        if not step.enabled:
            continue
        eff = get_effect(step.effect)
        ok, reason = eff.available()
        if not ok:
            raise RuntimeError(f"effect {step.effect!r} unavailable: {reason}")
        paths = eff.apply(paths, eff.Params(**step.params), ctx)
    return paths


def shape_layer(layer: CanvasLayer, source_paths: list[Path],
                page: tuple[float, float, float, float] | None = None) -> list[Path]:
    """transform → effect stack. Pure; caller caches."""
    placed = transform_paths(source_paths, layer.transform)
    return _apply_effect_stack(placed, layer.effects, _layer_ctx(layer, page))


def build_mask(
    shaped: list[Path], line_diameter_mm: float, margin_mm: float
) -> BaseGeometry | None:
    """An occluder layer's mask: filled closed paths as polygons, everything
    else as a swept band at the pen's line width, buffered by the signed
    margin. Nested filled paths use even-odd parity, so an inner threshold
    contour becomes a hole instead of occluding as a solid island."""
    fill_polys: list[BaseGeometry] = []
    stroke_geoms: list[BaseGeometry] = []
    half = max(line_diameter_mm, 0.01) / 2.0
    for p in shaped:
        pts = p.points
        if p.filled and p.is_closed:
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                fill_polys.append(poly)
        elif len(pts) >= 2:
            stroke_geoms.append(LineString(pts).buffer(half))
        elif pts:
            stroke_geoms.append(ShPoint(pts[0]).buffer(half))
    geoms: list[BaseGeometry] = []
    if fill_polys:
        fill_mask: BaseGeometry | None = None
        sorted_polys = sorted(fill_polys, key=lambda g: g.area, reverse=True)
        for i, poly in enumerate(sorted_polys):
            pt = poly.representative_point()
            depth = sum(1 for parent in sorted_polys[:i] if parent.covers(pt))
            if depth % 2 == 0:
                fill_mask = poly if fill_mask is None else fill_mask.union(poly)
            elif fill_mask is not None:
                fill_mask = fill_mask.difference(poly)
        if fill_mask is not None and not fill_mask.is_empty:
            geoms.append(fill_mask)
    geoms.extend(stroke_geoms)
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
    (an open fragment of a filled outline is just a line).

    Two cheap rejects run before the expensive part. ``difference`` is by far
    the most costly call in a resolve — with an occluder over a dense layer it
    was ~87% of total resolve time — and most paths in a typical project never
    touch the mask at all. A bounds check skips those for free, and a prepared
    ``intersects`` catches the ones inside the mask's bounding box but not its
    geometry. Both are pure filters: a path that cannot intersect the mask
    survives whole, which is exactly what ``difference`` would have returned.
    """
    if mask.is_empty:
        return list(shaped)
    # prepare() builds an index on the mask once; every later predicate call
    # against it is then much cheaper (Shapely 2 uses it implicitly).
    shapely.prepare(mask)
    mnx, mny, mxx, mxy = mask.bounds
    out: list[Path] = []
    for p in shaped:
        xs = [q[0] for q in p.points]
        ys = [q[1] for q in p.points]
        if max(xs) < mnx or min(xs) > mxx or max(ys) < mny or min(ys) > mxy:
            out.append(p)          # bounds can't overlap -> untouched
            continue
        if len(p.points) == 1:
            if not mask.covers(ShPoint(p.points[0])):
                out.append(p)
            continue
        line = LineString(p.points)
        if not mask.intersects(line):
            out.append(p)          # inside the bbox, but misses the geometry
            continue
        diff = line.difference(mask)
        if diff.is_empty:
            continue
        pieces = getattr(diff, "geoms", [diff])
        for g in pieces:
            if g.geom_type != "LineString" or len(g.coords) < 2:
                continue
            pts = _dedupe([(float(x), float(y)) for x, y in g.coords])
            if len(pts) < 2:
                continue
            survived_closed = is_closed(pts)
            out.append(Path(points=pts, filled=p.filled and survived_closed))
    return out


def clip_paths_inside(shaped: list[Path], mask: BaseGeometry) -> list[Path]:
    """Intersection twin of ``clip_paths``: keep only the pieces INSIDE the
    mask. Same ``filled`` rule — a fragment keeps the flag only if it
    survived intact and closed."""
    out: list[Path] = []
    for p in shaped:
        if len(p.points) == 1:
            if mask.covers(ShPoint(p.points[0])):
                out.append(p)
            continue
        hit = LineString(p.points).intersection(mask)
        if hit.is_empty:
            continue
        pieces = getattr(hit, "geoms", [hit])
        for g in pieces:
            if g.geom_type != "LineString" or len(g.coords) < 2:
                continue
            pts = _dedupe([(float(x), float(y)) for x, y in g.coords])
            if len(pts) < 2:
                continue
            survived_closed = is_closed(pts)
            out.append(Path(points=pts, filled=p.filled and survived_closed))
    return out


def region_stitch_paths(
    shaped: list[Path], mask: BaseGeometry,
    steps: list["EffectStep"], ctx: EffectContext,
) -> list[Path]:
    """The 'continuous' region boundary: one input path → one output path.

    Each path is walked in its original order; sections outside the mask pass
    through verbatim, sections inside are replaced by their effected geometry,
    and everything is concatenated with no pen lift — the seam is a drawn
    connection, wherever the effect moved the piece's ends.

    Contract limitation, stated honestly: stitching needs the inside pieces to
    stay identifiable, so the effect stack runs once PER PIECE (unlike cut
    mode's one run over the whole inside set — seeded effects will differ).
    An effect that returns several paths for one piece (bitmap blocks,
    fat_tube rings) has them concatenated in output order into the stitch:
    connected is the promise, not pretty. ``filled`` follows the existing
    survived-closed rule on the stitched result.
    """
    def effected_points(pts: list[tuple[float, float]], filled: bool) -> list[tuple[float, float]]:
        piece = Path(points=pts, filled=filled and is_closed(pts))
        return [pt for f in _apply_effect_stack([piece], steps, ctx) for pt in f.points]

    out: list[Path] = []
    for p in shaped:
        if len(p.points) == 1:
            if not mask.covers(ShPoint(p.points[0])):
                out.append(p)
                continue
            pts = effected_points(p.points, p.filled)
            if pts:
                out.append(Path(points=_dedupe(pts), filled=False))
            continue
        line = LineString(p.points)
        inside_geom = line.intersection(mask)
        if inside_geom.is_empty:
            out.append(p)
            continue
        # collect every piece (both sides) with its position along the path,
        # so the stitch preserves the original travel order
        pieces: list[tuple[float, bool, list[tuple[float, float]]]] = []
        for geom, is_inside in ((line.difference(mask), False), (inside_geom, True)):
            for g in getattr(geom, "geoms", [geom]):
                if g.geom_type != "LineString" or len(g.coords) < 2:
                    continue
                pts = _dedupe([(float(x), float(y)) for x, y in g.coords])
                if len(pts) < 2:
                    continue
                pos = line.project(g.interpolate(0.5, normalized=True))
                pieces.append((pos, is_inside, pts))
        pieces.sort(key=lambda t: t[0])
        stitched: list[tuple[float, float]] = []
        for _, is_inside, pts in pieces:
            stitched.extend(effected_points(pts, p.filled) if is_inside else pts)
        if not stitched:
            continue
        stitched = _dedupe(stitched)
        survived_closed = is_closed(stitched)
        out.append(Path(points=stitched, filled=p.filled and survived_closed))
    return out


def line_diameter_for(layer: CanvasLayer, pens: dict[str, Pen]) -> float:
    pen = pens.get(layer.pen_id or "")
    return pen.line_diameter_mm if pen else DEFAULT_LINE_DIAMETER_MM


# ---------------------------------------------------------------------------
# Occlusion memo
# ---------------------------------------------------------------------------
#
# Occlusion is by far the most expensive stage of a resolve: with an occluder
# over a dense layer, ~87% of the time is inside shapely's ``difference``.
# It also ran unconditionally on every resolve, so idle re-renders (a preview
# refresh, an estimate, a tab switch) paid full price for geometry that had
# not changed.
#
# THE SAFETY ARGUMENT — a stale occlusion cache would make the tool draw
# something that is not true, so the key has to be provably complete:
#
# * The clip result for a layer is a pure function of exactly four things:
#   its shaped geometry, its ``receives_occlusion`` flag, which channels it
#   listens to, and the masks accumulated from the occluders ABOVE it.
#   ``layer.draw`` is deliberately NOT part of it — it selects between the
#   clip result and ``[]`` outside the memo.
# * A mask is a pure function of the occluder's shaped geometry, its pen line
#   diameter and its occlusion margin; which channel it lands in is its
#   ``occlude_groups``. All of those ride in the signature.
# * Geometry is identified by **object identity**, the same discipline the
#   shaped cache uses: modules are pure and geometry lists are replaced
#   wholesale, never mutated, so a changed list is always a NEW list.
# * ``id()`` reuse — the one way identity keys go wrong — cannot happen here
#   because every entry stores a strong reference to each list its key names.
#   A cached id therefore belongs to a live object, and no other live object
#   can share it, so an id match IS an object match.
# * Layer order rides in the signature implicitly: the accumulated tuple
#   records which occluders were seen above this layer, in order.
#
# Regions are the documented gap: step 1.5 replaces the shaped list of every
# layer under a visible region with a fresh list each resolve, so those layers
# (and anything they occlude) legitimately miss every time. That is slow, not
# wrong.


class _Channel(NamedTuple):
    """One accumulating mask channel (the global one, or a group letter).

    ``sig`` is the hashable identity of everything folded in so far; ``refs``
    holds the geometry lists that ``sig`` names, keeping them alive so their
    ids cannot be recycled; ``mask`` is the union itself."""

    sig: tuple
    refs: tuple
    mask: BaseGeometry


class _ClipEntry(NamedTuple):
    key: tuple
    subject: list[Path]     # keeps the clipped layer's shaped list alive
    refs: tuple             # keeps every occluder list named in ``key`` alive
    result: list[Path]


class OcclusionCache:
    """Session-owned memo for the occlusion stage. Content-keyed, so it needs
    no explicit invalidation — see the safety argument above. ``resolve_project``
    prunes whatever it did not touch, which bounds the memory."""

    def __init__(self) -> None:
        self._masks: dict[tuple, tuple[list[Path], BaseGeometry | None]] = {}
        self._unions: dict[tuple, tuple[tuple, BaseGeometry]] = {}
        self._clips: dict[str, _ClipEntry] = {}
        self._touched_masks: set[tuple] = set()
        self._touched_unions: set[tuple] = set()

    def clear(self) -> None:
        self._masks.clear()
        self._unions.clear()
        self._clips.clear()

    # -- one resolve ------------------------------------------------------
    def begin(self) -> None:
        self._touched_masks.clear()
        self._touched_unions.clear()

    def end(self, live_layer_ids: set[str]) -> None:
        self._masks = {k: v for k, v in self._masks.items() if k in self._touched_masks}
        self._unions = {k: v for k, v in self._unions.items() if k in self._touched_unions}
        self._clips = {k: v for k, v in self._clips.items() if k in live_layer_ids}

    def mask(self, layer: CanvasLayer, shaped: list[Path],
             diameter: float, margin: float) -> BaseGeometry | None:
        key = (layer.id, id(shaped), diameter, margin)
        self._touched_masks.add(key)
        hit = self._masks.get(key)
        if hit is not None and hit[0] is shaped:
            return hit[1]
        built = build_mask(shaped, diameter, margin)
        self._masks[key] = (shaped, built)
        return built

    def union(self, sig: tuple, refs: tuple, geoms: list[BaseGeometry]) -> BaseGeometry:
        self._touched_unions.add(sig)
        hit = self._unions.get(sig)
        if hit is not None:
            return hit[1]
        merged = unary_union(geoms)
        self._unions[sig] = (refs, merged)
        return merged

    def clipped(self, layer_id: str, key: tuple, subject: list[Path],
                refs: tuple, mask: BaseGeometry) -> list[Path]:
        hit = self._clips.get(layer_id)
        if hit is not None and hit.key == key and hit.subject is subject:
            return hit.result
        result = clip_paths(subject, mask)
        self._clips[layer_id] = _ClipEntry(key, subject, refs, result)
        return result


def resolve_project(
    project: Project,
    source_geometry: dict[str, list[Path]],
    pens: dict[str, Pen],
    shaped_cache: dict[str, tuple[str, list[Path]]] | None = None,
    occlusion_cache: "OcclusionCache | None" = None,
) -> dict[str, list[Path]]:
    """Resolve every visible layer. Returns ``{layer_id: resolved paths}``.

    This is THE single source of truth: preview, per-layer estimates, and
    plotting all read their geometry from here — there is no second path.

    ``shaped_cache`` (optional, owned by the session) memoises the
    transform+effects stage per layer, keyed by a content hash, so dragging
    one layer doesn't re-run every other layer's effect stack.
    ``occlusion_cache`` (optional, likewise session-owned) memoises the far
    more expensive occlusion stage — see the safety argument above
    :class:`OcclusionCache`. Both are pure accelerators: passing neither
    produces byte-identical output, just slower.
    """
    # 1. shape every visible layer (cached). Region layers are skipped: their
    # effect stack is a payload for the layers below, never for themselves.
    page = guide_page(project)
    shaped: dict[str, list[Path]] = {}
    for layer in project.layers:
        if not layer.visible or layer.region:
            continue
        src = source_geometry.get(layer.id, [])
        if shaped_cache is not None:
            key = _shape_key(layer, src, page)
            hit = shaped_cache.get(layer.id)
            if hit is not None and hit[0] == key:
                shaped[layer.id] = hit[1]
                continue
            shaped[layer.id] = shape_layer(layer, src, page)
            shaped_cache[layer.id] = (key, shaped[layer.id])
        else:
            shaped[layer.id] = shape_layer(layer, src, page)

    # 1.5 region layers ("affects below"), bottom -> top so an upper region
    # sees the output of a lower one (adjustment-layer stacking). The region's
    # placed silhouette clips every layer beneath it; the inside pieces run
    # the region's effect stack. This happens post-effect / pre-occlusion, so
    # region output (pixellated blocks, tubes…) still occludes normally.
    # Reassignment only — cached shaped lists are never mutated in place.
    for r_idx, region in enumerate(project.layers):
        if not (region.visible and region.region):
            continue
        placed = transform_paths(source_geometry.get(region.id, []), region.transform)
        mask = build_mask(placed, line_diameter_for(region, pens), 0.0)
        if mask is None:
            continue
        ctx = _layer_ctx(region, page)
        for below in project.layers[:r_idx]:
            if below.id not in shaped:
                continue  # hidden, or itself a region
            if region.region_boundary == "continuous":
                shaped[below.id] = region_stitch_paths(
                    shaped[below.id], mask, region.effects, ctx)
                continue
            inside = clip_paths_inside(shaped[below.id], mask)
            if not inside:
                continue
            outside = clip_paths(shaped[below.id], mask)
            shaped[below.id] = outside + _apply_effect_stack(inside, region.effects, ctx)

    # 2. occlusion, top -> bottom, accumulating mask unions PER CHANNEL:
    # the global union (occluders with an EMPTY occlude_groups — these mask
    # every receiver) plus one union per group. An occluder with groups adds
    # its mask to each of them; a receiver is clipped by global ∪ every group
    # it listens to — additive semantics, all-empty behaves exactly as before.
    resolved: dict[str, list[Path]] = {}
    if occlusion_cache is not None:
        occlusion_cache.begin()
    #: accumulating channels: the global one plus one per group letter. Each
    #: carries the mask AND the identity of everything folded into it, which
    #: is what lets a receiver below decide whether its clip is still valid.
    global_ch: _Channel | None = None
    group_ch: dict[str, _Channel] = {}
    for layer in reversed(project.layers):
        if not layer.visible:
            continue
        if layer.region:
            resolved[layer.id] = []  # a region is never drawn and never occludes
            continue
        s = shaped[layer.id]
        channels = [global_ch, *(group_ch[g] for g in layer.receives_groups if g in group_ch)]
        channels = [c for c in channels if c is not None]
        if layer.receives_occlusion and channels:
            parts = [c.mask for c in channels]
            sig = tuple(c.sig for c in channels)
            refs = tuple(r for c in channels for r in c.refs)
            if occlusion_cache is not None:
                applicable = occlusion_cache.union(("|",) + sig, refs, parts)
                clipped = occlusion_cache.clipped(
                    layer.id, (id(s), sig), s, refs, applicable)
            else:
                clipped = clip_paths(s, unary_union(parts))
        else:
            clipped = s
        resolved[layer.id] = clipped if layer.draw else []
        if layer.occluder:
            diameter = line_diameter_for(layer, pens)
            margin = layer.occlusion_margin_mm
            if occlusion_cache is not None:
                m = occlusion_cache.mask(layer, s, diameter, margin)
            else:
                m = build_mask(s, diameter, margin)
            if m is not None:
                item = (layer.id, id(s), diameter, margin)
                targets = layer.occlude_groups or [None]
                for g in targets:
                    prev = global_ch if g is None else group_ch.get(g)
                    if prev is None:
                        merged = _Channel((item,), (s,), m)
                    else:
                        grown_sig = prev.sig + (item,)
                        grown_refs = prev.refs + (s,)
                        grown_mask = (
                            occlusion_cache.union(grown_sig, grown_refs, [prev.mask, m])
                            if occlusion_cache is not None
                            else unary_union([prev.mask, m]))
                        merged = _Channel(grown_sig, grown_refs, grown_mask)
                    if g is None:
                        global_ch = merged
                    else:
                        group_ch[g] = merged
    if occlusion_cache is not None:
        occlusion_cache.end({lay.id for lay in project.layers})
    return resolved


def _shape_key(layer: CanvasLayer, src: list[Path],
               page: tuple[float, float, float, float] | None = None) -> str:
    h = hashlib.sha256()
    h.update(str(id(src)).encode())  # source list identity: replaced wholesale on regen
    h.update(json.dumps({
        "t": layer.transform.model_dump(),
        "e": [s.model_dump() for s in layer.effects],
        # page-relative effects (invert) must re-run when the guide moves
        "p": page,
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

    ``target`` is ``"all"``, a layer id, or ``"pen:<pen_id>"`` — every layer
    carrying that pen, which is how a multi-pen sheet is actually plotted:
    load a pen, plot everything it draws, swap, repeat. Addressing it by pen
    rather than by layer is the difference between one pass and remembering
    which four of fifteen layers were blue. A layer target plots that layer's
    *resolved* geometry, clipped by whatever occludes it; a pen target does
    the same for each of its layers, in document order.

    Deliberately NOT paired with a "done" ledger: a ledger records intent,
    paper records truth, and a stale one is exactly what authorises replotting
    over wet ink. What was SENT is already in the job log.

    ``pen_offsets``
    maps layer id → that layer's pen nib offset; the pass is translated by
    the *negative* of it — the plot-time toolpath compensation that registers
    multi-pen passes on the same sheet. Per layer, because an "all" pass may
    mix pens.
    """
    want_pen = target[4:] if target.startswith("pen:") else None
    out_layers: list[Layer] = []
    for i, layer in enumerate(project.layers):
        if want_pen is not None:
            if (layer.pen_id or "") != want_pen:
                continue
        elif target != "all" and layer.id != target:
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
