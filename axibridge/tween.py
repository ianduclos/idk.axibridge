"""Layer interpolation: a *tween* layer renders the in-between of two
sibling layers A and B — duplicate a layer, change generator params /
effects / position, then sweep the morph.

Everything that defines a layer's look is a typed, numeric-heavy dict, so
interpolation is parameter-space lerp, regenerated through the normal
resolve path (the single-resolve invariant holds: tween geometry is
materialised into ``source_geometry`` by the session before every resolve).

The contract that makes it sturdy:

* **Endpoint fidelity** — t=0 reproduces A exactly, t=1 reproduces B
  exactly. Everything non-lerpable (bools, strings, enums, ``seed`` fields,
  mismatched effect stacks, the effect ctx seed) *steps* at t=0.5 rather
  than blending, precisely to keep the endpoints exact. Expect a visible
  jump at 0.5 when A and B differ in such a field.
* **Two compatibility modes** — same generator on both sides: lerp generator
  params and regenerate (geometry follows params continuously). Different
  or non-generator sources: pointwise lerp of the *source* paths, which
  requires identical structure (same path/point counts — what "duplicate
  layer" gives you).
* **Nested tweens (bilinear morph)** — an endpoint may itself be a tween, so
  long as both sides *reduce to the same generator* (``effective_generator``
  recurses through them). A ``sweep`` tween whose A and B are two
  ``follow_master`` tweens gives a two-axis morph: the master timeline drives
  the inner tweens (Xa→Xb, Ya→Yb) while sweep stamps copies across the pair
  (X(t)→Y(t)) — every stamp is a bilinear blend of the four corner param sets,
  computed in parameter space with no extra geometry path. Nesting is refused
  when the sides don't share a generator (nothing coherent to lerp).
* **Captured-geometry morph** — a geometry-as-params generator (pen, drawing)
  holds its shape in a hidden param (``subpaths`` / ``strokes``). Same
  generator on both sides, matching shape structure (identical anchor/point
  counts, again what "animate"/"duplicate" give): that hidden field is
  deep-lerped so the DRAWN FORM morphs A→B — anchors, Bézier handles and all
  — then regenerated through the source's flattening (true curved
  in-betweens, not linearly-lerped points). Structure mismatch falls back to
  stepping the field at 0.5, as before. See ``blend_generator_params``.
* **Transforms lerp decomposed** (translate / rotate / scale / shear, the
  rotation along the shortest arc) — naive matrix lerp collapses rotations
  through zero scale.
* **frame_offset lerps** like the transform — a layer-level quantity folded
  into the generator's ``frame`` axis, so an A/B pair sharing generator params
  but differing in offset plays the referenced clip across the morph.
* **Live references** — the tween reads A and B at resolve time, so editing
  either updates the morph. If a reference goes missing or incompatible the
  tween resolves to empty (never crashes a stored project); deleting a
  referenced layer is refused server-side unless the tween goes with it.
* **Stamp positions are time-invariant** — a ``sweep > 1`` (stamped) tween
  places its copies at fixed positions strictly BETWEEN A and B
  (``i/(sweep+1)`` for ``i`` in ``1..sweep``, never coincident with either
  endpoint), and a master scrub never moves them. What advances under the
  timeline is the *clip content*: an endpoint carrying ``frame_follow`` has the
  raw (clamped) master value folded into its frame axis (``master_t`` in
  ``_source_paths_at``), so the whole ladder samples later frames while every
  stamp stays put — positions never move with time, only clip content does.

The tween layer is otherwise a normal layer: its own transform (drag it),
its own effect stack, pen and occlusion flags all apply ON TOP of the
materialised geometry via the ordinary shape pipeline.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Literal

from pydantic import BaseModel, Field

from .compose import Affine, CanvasLayer, EffectStep, Project, _layer_seed, transform_paths
from .model import Path
from .registry import EffectContext, get_effect, get_source

log = logging.getLogger(__name__)

#: (layer_id, error repr) pairs already logged — materialize() runs on every
#: resolve (every scrub tick for a follow_master tween), so a persistently
#: broken tween must log its failure ONCE, not flood the ring buffer.
_logged_failures: set[tuple[str, str]] = set()


class TweenParams(BaseModel):
    a: str = Field(title="Layer A")
    b: str = Field(title="Layer B")
    t: float = Field(default=0.5, ge=0.0, le=1.0, title="t (A → B)")
    sweep: int = Field(default=1, ge=1, le=60, title="Sweep copies",
                       description="1 = single tween at t; more = in-betweens "
                                   "stamped strictly between A and B (exclusive)")
    follow_master: bool = Field(
        default=False, title="Follow timeline",
        description="Master timeline scrub / frame rendering drives this tween's t")
    time_curve: Literal["linear", "cosine", "cosine_pingpong"] = Field(
        default="linear", title="Timeline curve",
        description="linear: A→B at constant rate. cosine: A→B eased "
                    "(ease-in-out). cosine_pingpong: A→B→A over the same "
                    "timeline. Clip/frame-follow playback stays linear.")
    window_from: float = Field(
        default=0.0, ge=0.0, le=1.0, title="Window from",
        description="Maps the master timeline into this tween's local t: hold A "
                    "for master_t before this point, animate inside the window.")
    window_to: float = Field(
        default=1.0, ge=0.0, le=1.0, title="Window to",
        description="Maps the master timeline into this tween's local t: animate "
                    "inside the window, hold B for master_t past this point.")


# -- scalar / dict lerp -----------------------------------------------------


def _lerp_value(va: Any, vb: Any, t: float) -> Any:
    if isinstance(va, bool) or isinstance(vb, bool):  # bool is an int — check first
        return va if t < 0.5 else vb
    if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
        out = va + (vb - va) * t
        return int(round(out)) if isinstance(va, int) and isinstance(vb, int) else out
    return va if t < 0.5 else vb


def lerp_params(pa: dict[str, Any], pb: dict[str, Any], t: float,
                defaults: dict[str, Any]) -> dict[str, Any]:
    """Key-wise lerp of two param dicts over the union of keys (defaults fill
    gaps). ``seed`` keys step at 0.5: blending RNG seeds is meaningless and
    endpoint fidelity matters more than a smooth middle."""
    out: dict[str, Any] = {}
    for key in {*defaults, *pa, *pb}:
        va = pa.get(key, defaults.get(key))
        vb = pb.get(key, defaults.get(key))
        if key == "seed":
            out[key] = va if t < 0.5 else vb
        else:
            out[key] = _lerp_value(va, vb, t)
    return out


# -- affine lerp (decomposed) ------------------------------------------------


def decompose_affine(m: Affine) -> tuple[float, float, float, float, float, float]:
    """(e, f, rotation, scale_x, scale_y, shear) — standard QR-style
    decomposition; recomposition reproduces the matrix exactly."""
    rot = math.atan2(m.b, m.a)
    sx = math.hypot(m.a, m.b) or 1e-12
    sy = (m.a * m.d - m.b * m.c) / sx
    shear = (m.a * m.c + m.b * m.d) / (sx * sx)
    return (m.e, m.f, rot, sx, sy, shear)


def compose_affine(e: float, f: float, rot: float, sx: float, sy: float, shear: float) -> Affine:
    cos, sin = math.cos(rot), math.sin(rot)
    return Affine(
        a=sx * cos, b=sx * sin,
        c=sx * cos * shear - sy * sin, d=sx * sin * shear + sy * cos,
        e=e, f=f,
    )


def lerp_affine(ma: Affine, mb: Affine, t: float) -> Affine:
    da, db = decompose_affine(ma), decompose_affine(mb)
    drot = db[2] - da[2]
    if drot > math.pi:
        drot -= 2 * math.pi  # shortest arc
    elif drot < -math.pi:
        drot += 2 * math.pi
    vals = [a + (b - a) * t for a, b in zip(da, db)]
    vals[2] = da[2] + drot * t
    return compose_affine(*vals)


# -- compatibility + materialisation -----------------------------------------


def map_time_curve(local_t: float, curve: str = "linear") -> float:
    """Map a window-normalized timeline value into morph t.

    * ``linear`` — A→B at constant rate.
    * ``cosine`` — A→B eased (ease-in-out, zero velocity at both ends).
    * ``cosine_pingpong`` — A→B→A over the same timeline.
    """
    t = min(1.0, max(0.0, local_t))
    if curve == "cosine":
        return 0.5 - 0.5 * math.cos(math.pi * t)
    if curve == "cosine_pingpong":
        return 0.5 - 0.5 * math.cos(2 * math.pi * t)
    return t


def structures_match(ga: list[Path], gb: list[Path]) -> bool:
    """Pointwise lerp needs identical structure: same path count, same point
    count per path — what "duplicate layer" gives you."""
    return len(ga) == len(gb) and all(
        len(pa.points) == len(pb.points) for pa, pb in zip(ga, gb)
    )


def lerp_paths(ga: list[Path], gb: list[Path], t: float) -> list[Path]:
    """Pointwise structural lerp; requires ``structures_match(ga, gb)``.
    ``filled`` steps at 0.5 like every bool."""
    out: list[Path] = []
    for pa, pb in zip(ga, gb):
        pts = [(ax + (bx - ax) * t, ay + (by - ay) * t)
               for (ax, ay), (bx, by) in zip(pa.points, pb.points)]
        out.append(Path(points=pts, filled=pa.filled if t < 0.5 else pb.filled))
    return out


def _same_generator(la: CanvasLayer, lb: CanvasLayer) -> bool:
    return (la.source.type == "generator" and lb.source.type == "generator"
            and bool(la.source.generator)
            and la.source.generator == lb.source.generator)


# -- captured-geometry (shape) morph ----------------------------------------
#
# A geometry-as-params generator (pen, drawing) carries its captured shape in
# a hidden param — ``pen.subpaths``, ``drawing.strokes`` — a nested structure
# of points/anchors, not a scalar dial. ``lerp_params`` can't blend it (a list
# isn't a number), so it STEPS at t=0.5 and the shape jump-cuts. When A and B
# share structure (what "animate"/"duplicate" produce — identical subpath and
# anchor counts), we can instead deep-lerp that structure so the SHAPE morphs,
# then regenerate through the source's own flattening — true Bézier in-betweens
# at every t, not linearly-lerped points. Structure mismatch falls straight
# back to the stepped value: endpoint fidelity holds, a stored project can
# never fail to resolve.

#: sentinel: this structure can't morph (mismatched shape) — keep the stepped value
_NO_BLEND: Any = object()


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_handle(v: Any) -> bool:
    """A Bézier handle: a 2-number delta, or ``None`` for a plain corner."""
    return v is None or (
        isinstance(v, (list, tuple)) and len(v) == 2 and _is_number(v[0]) and _is_number(v[1]))


def _blend_geometry(a: Any, b: Any, t: float) -> Any:
    """Structural deep-lerp of a captured-geometry value. Recurses matching
    lists/dicts and lerps numeric leaves; bools/strings step at 0.5 (e.g. a
    subpath's ``closed`` flag can't be half-set); a ``None`` handle counts as a
    zero vector so a corner can grow into a curve across the morph. Returns
    ``_NO_BLEND`` (propagated up) the moment two sub-structures don't match, so
    the caller keeps the whole field's stepped value — morph is all-or-nothing
    per field, mirroring ``structures_match``'s philosophy for baked paths."""
    if _is_number(a) and _is_number(b):
        out = a + (b - a) * t
        return int(round(out)) if isinstance(a, int) and isinstance(b, int) else out
    if isinstance(a, bool) or isinstance(b, bool):
        return a if t < 0.5 else b
    if isinstance(a, str) and isinstance(b, str):
        return a if t < 0.5 else b
    if a is None and b is None:
        return None
    # a handle pair — including corner (None) ↔ curve: None acts as [0,0], so
    # the anchor's handle grows out of / retracts into the point continuously
    if _is_handle(a) and _is_handle(b) and not (a is None and b is None):
        va = a if a is not None else (0.0, 0.0)
        vb = b if b is not None else (0.0, 0.0)
        return [va[0] + (vb[0] - va[0]) * t, va[1] + (vb[1] - va[1]) * t]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        blended = [_blend_geometry(x, y, t) for x, y in zip(a, b)]
        return _NO_BLEND if any(c is _NO_BLEND for c in blended) else blended
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        blended = {k: _blend_geometry(a[k], b[k], t) for k in a}
        return _NO_BLEND if any(c is _NO_BLEND for c in blended.values()) else blended
    return _NO_BLEND


def _geometry_param_fields(src: Any) -> list[str]:
    """Param names a source marks as hidden captured geometry (``strokes``,
    ``subpaths``) — the fields whose value is a shape structure, not a dial.
    ``json_schema_extra={"hidden": True}`` is that marker and is used for
    nothing else (see sources/pen.py, sources/drawing.py)."""
    props = src.Params.model_json_schema().get("properties") or {}
    return [name for name, spec in props.items() if spec.get("hidden") is True]


def blend_generator_params(la: CanvasLayer, lb: CanvasLayer, t: float) -> dict[str, Any] | None:
    """Same-generator param blend, or None when A/B aren't the same generator.

    Scalar dials lerp; a hidden captured-geometry field (pen ``subpaths`` /
    drawing ``strokes``) additionally MORPHS structurally when A and B share
    shape, so the drawn form eases from A to B instead of jump-cutting at 0.5.
    The caller regenerates (each caller folds frames/offsets its own way).

    NOTE: this is the *direct* (non-nested) blend used by the capture/staging
    tray. The live tween resolve path goes through :func:`effective_generator`
    (which also reduces nested same-generator tweens) via ``_source_paths_at``
    — that path applies the same captured-geometry deep-lerp separately, on
    the effective (post-reduction) param dicts."""
    if not _same_generator(la, lb):
        return None
    src = get_source(la.source.generator)
    pa = la.source.params or {}
    pb = lb.source.params or {}
    out = lerp_params(pa, pb, t, src.Params().model_dump())
    for field in _geometry_param_fields(src):
        blended = _blend_geometry(pa.get(field), pb.get(field), t)
        if blended is not _NO_BLEND:
            out[field] = blended  # else keep lerp_params' stepped value (structure mismatch)
    return out


def resolve_local_t(params: dict[str, Any], master_t: float | None = None) -> float:
    """A tween's effective morph ``t``. With ``follow_master`` set and a master
    value supplied, map it through the ``[window_from, window_to]`` window and
    time curve exactly as the timeline does; otherwise the static stored ``t``.

    Mirrors the window/curve mapping in ``session._materialize_tweens`` so a
    *nested* tween samples its endpoints at the same ``t`` a top-level scrub
    would — the two paths must not drift (the 2026-07-19 unification lesson)."""
    if master_t is not None and params.get("follow_master"):
        mt = min(1.0, max(0.0, master_t))
        wf = params.get("window_from", 0.0)
        wt = params.get("window_to", 1.0)
        if wt > wf:
            local = min(1.0, max(0.0, (mt - wf) / (wt - wf)))
        else:  # degenerate window: step A -> B at the collapsed point
            local = 0.0 if mt < wf else 1.0
        return map_time_curve(local, params.get("time_curve", "linear"))
    return params.get("t", 0.5)


def effective_generator(
    layer: CanvasLayer, project: Project | None, master_t: float | None = None,
    _depth: int = 0,
) -> tuple[str, dict[str, Any], float] | None:
    """Reduce a layer to the ``(generator_id, params, frame_offset)`` it would
    generate from — or ``None`` when it can't (non-generator source, a nested
    tween whose sides don't share one generator, a missing/broken ref).

    Recurses through tween layers: a same-generator tween reduces to its two
    endpoints' params lerped at the tween's own effective ``t`` (``master_t``
    drives a ``follow_master`` tween through its window/curve via
    :func:`resolve_local_t`). This is what lets a *sweep* tween interpolate
    between two time-animated tweens — the bilinear (time x sweep) morph —
    entirely in parameter space, with no second geometry path. Bounded depth
    guards against a reference cycle."""
    if _depth > 8 or project is None and layer.source.type == "tween":
        return None
    src = layer.source
    if src.type == "generator" and src.generator:
        off = layer.frame_offset + (
            master_t if (layer.frame_follow and master_t is not None) else 0.0)
        return (src.generator, dict(src.params or {}), off)
    if src.type == "tween":
        try:
            p = TweenParams(**(src.params or {}))
            la = project.layer(p.a)  # type: ignore[union-attr]
            lb = project.layer(p.b)  # type: ignore[union-attr]
        except Exception:
            return None
        ega = effective_generator(la, project, master_t, _depth + 1)
        egb = effective_generator(lb, project, master_t, _depth + 1)
        if ega is None or egb is None or ega[0] != egb[0]:
            return None
        gen = ega[0]
        ti = resolve_local_t(src.params or {}, master_t)
        defaults = get_source(gen).Params().model_dump()
        params = lerp_params(ega[1], egb[1], ti, defaults)
        off = ega[2] + (egb[2] - ega[2]) * ti
        own = layer.frame_offset + (
            master_t if (layer.frame_follow and master_t is not None) else 0.0)
        return (gen, params, off + own)
    return None


def blend_effect_stacks(
    ea: list[EffectStep], eb: list[EffectStep], t: float,
) -> tuple[list[EffectStep], bool]:
    """THE stack-identity rule (Ian, 2026-07-19): the full step list IS the
    stack — disabled steps included — and a step's ``enabled`` is just a bool
    that steps at 0.5. Same effect-id sequence → per-step param lerp;
    different sequences → the whole stack steps (non-lerpable). Disabling a
    step must never change whether two layers are compatible.

    Returns ``(stack, matched)`` — callers use ``matched`` for warnings.
    Both interpolation instruments (canvas tween, tray capture blend) share
    this function; before unification tween.py compared enabled-filtered
    stacks and the tray compared full stacks, and the same A/B pair could
    blend on one path and jump-cut on the other."""
    if [s.effect for s in ea] != [s.effect for s in eb]:
        chosen = ea if t < 0.5 else eb
        return ([s.model_copy(deep=True) for s in chosen], False)
    out: list[EffectStep] = []
    for sa, sb in zip(ea, eb):
        defaults = get_effect(sa.effect).Params().model_dump()
        out.append(EffectStep(
            effect=sa.effect,
            enabled=sa.enabled if t < 0.5 else sb.enabled,
            params=lerp_params(sa.params, sb.params, t, defaults),
        ))
    return (out, True)


def check_compatible(
    la: CanvasLayer, lb: CanvasLayer,
    geo_a: list[Path], geo_b: list[Path],
    project: Project | None = None,
) -> str | None:
    """None if A/B can tween; otherwise the human-readable reason.

    Two routes make a pair interpolatable: the *parameter* route (both sides
    reduce to the SAME generator via :func:`effective_generator` — this now
    includes nested same-generator tweens, e.g. a sweep between two animated
    tweens), or the *structural* route (identical path structure for pointwise
    lerp). Nesting is allowed ONLY when the parameter route holds — a tween has
    no fixed geometry, so two tweens that don't reduce to one generator have
    nothing coherent to lerp."""
    if la.id == lb.id:
        return "pick two different layers"
    ega = effective_generator(la, project) if project is not None else None
    egb = effective_generator(lb, project) if project is not None else None
    if ega is not None and egb is not None and ega[0] == egb[0]:
        return None
    # structural route: real geometry on BOTH sides (two empty lists match
    # vacuously — an unmaterialised tween endpoint must not read as compatible)
    if geo_a and geo_b and structures_match(geo_a, geo_b):
        return None
    if la.source.type == "tween" or lb.source.type == "tween":
        return ("interpolation layers can only nest when both sides reduce to "
                "the same generator")
    return ("layers are not interpolatable: need the same generator on both, "
            "or identical path structure (use 'duplicate layer')")


def _source_paths_at(la: CanvasLayer, lb: CanvasLayer,
                     geo_a: list[Path], geo_b: list[Path], t: float,
                     master_t: float | None = None,
                     project: Project | None = None) -> list[Path]:
    # Parameter route: reduce BOTH endpoints to (generator, params, offset) via
    # effective_generator — which recurses through nested same-generator tweens,
    # so an endpoint may be a plain generator OR an animated tween. When both
    # reduce to one generator, blend in parameter space and regenerate.
    ega = effective_generator(la, project, master_t)
    egb = effective_generator(lb, project, master_t)
    if ega is not None and egb is not None and ega[0] == egb[0]:
        gen = ega[0]
        src = get_source(gen)
        params = lerp_params(ega[1], egb[1], t, src.Params().model_dump())
        # Captured-geometry morph (pen/drawing): a hidden shape field can't be
        # scalar-lerped by lerp_params above (it stepped at t=0.5 there), so
        # deep-lerp it structurally on the same reduced param dicts — for a
        # direct (non-nested) pair ega[1]/egb[1] ARE la/lb's own params, so
        # this reproduces blend_generator_params' morph exactly.
        for field in _geometry_param_fields(src):
            blended = _blend_geometry(ega[1].get(field), egb[1].get(field), t)
            if blended is not _NO_BLEND:
                params[field] = blended
        # frame_offset is a layer-level lerped quantity (like the transform):
        # fold the interpolated offset into the generator's ``frame`` axis so an
        # A/B pair with identical params but different offsets plays the clip.
        # Each endpoint's effective offset already carries the raw (clamped)
        # master value for any ``frame_follow`` layer in its reduction — so
        # scrubbing advances the clip content without moving any stamp.
        off = ega[2] + (egb[2] - ega[2]) * t
        if (off or ega[2] or egb[2]) and "frame" in src.Params.model_fields:
            params["frame"] = min(1.0, max(0.0, params.get("frame", 0.0) + off))
        doc = src.generate(src.Params(**params))
        return [p for lyr in doc.layers for p in lyr.paths]
    # structural mode: pointwise lerp (validated to match)
    return lerp_paths(geo_a, geo_b, t)


def _effects_at(la: CanvasLayer, lb: CanvasLayer, t: float):
    """The blended stack's ENABLED steps as (effect_id, params dict) pairs,
    via the shared full-stack rule (``blend_effect_stacks``): stacks compare
    by their full step list, ``enabled`` steps at 0.5 like any bool, and
    mismatched sequences step whole (endpoint fidelity over smoothness)."""
    stack, _matched = blend_effect_stacks(la.effects, lb.effects, t)
    return [(s.effect, dict(s.params)) for s in stack if s.enabled]


def materialize(
    layer: CanvasLayer, project: Project, source_geometry: dict[str, list[Path]],
    override_t: float | None = None, master_t: float | None = None,
) -> list[Path]:
    """The tween layer's source geometry: the virtual in-between layer(s),
    fully shaped (lerped transform + lerped effects) in paper space. The
    tween's OWN transform/effects then apply through the normal pipeline.
    Any breakage (missing refs, incompatibility, generator error) resolves
    to [] — a stored project must never fail to resolve.

    ``override_t`` (the master-timeline value, already mapped through the
    tween's window by the caller) drives the morph POSITION for a single tween:

    * ``sweep <= 1`` — a single tween at ``override_t`` if given, else ``p.t``.
    * ``sweep > 1`` — in-betweens stamped at fixed, time-invariant positions
      strictly BETWEEN A and B (``i/(sweep+1)`` for ``i`` in ``1..sweep``);
      ``override_t`` does NOT move them (positions never move with time).

    ``master_t`` is the RAW clamped master-timeline value (distinct from the
    window-mapped ``override_t``): passed straight through to
    ``_source_paths_at``, it advances the CLIP CONTENT of any endpoint that
    opted into ``frame_follow`` — the ladder samples later frames in place."""
    try:
        p = TweenParams(**(layer.source.params or {}))
        la = project.layer(p.a)
        lb = project.layer(p.b)
        geo_a = source_geometry.get(la.id, [])
        geo_b = source_geometry.get(lb.id, [])
        if check_compatible(la, lb, geo_a, geo_b, project) is not None:
            return []
        if p.sweep <= 1:
            ts = [override_t if override_t is not None else p.t]
        else:
            # exclusive in-betweens: evenly spaced strictly between the endpoints
            ts = [i / (p.sweep + 1) for i in range(1, p.sweep + 1)]
        out: list[Path] = []
        for t in ts:
            paths = _source_paths_at(la, lb, geo_a, geo_b, t, master_t, project)
            placed = transform_paths(paths, lerp_affine(la.transform, lb.transform, t))
            ctx = EffectContext(
                layer_id=layer.id,
                translation=lerp_affine(la.transform, lb.transform, t).translation,
                # step the ctx seed too: noise fields match A/B at the endpoints
                seed=_layer_seed(la.id) if t < 0.5 else _layer_seed(lb.id),
            )
            for effect_id, params in _effects_at(la, lb, t):
                eff = get_effect(effect_id)
                placed = eff.apply(placed, eff.Params(**params), ctx)
            out.extend(placed)
        return out
    except Exception as exc:
        # the no-crash contract stands (a stored project must always resolve),
        # but swallowing silently also hides real generator/effect bugs behind
        # an empty layer — log the first occurrence so the /api/logs ring
        # shows WHY a tween went blank.
        key = (layer.id, repr(exc))
        if key not in _logged_failures:
            _logged_failures.add(key)
            log.warning("tween %s resolves empty: %s", layer.id, exc, exc_info=True)
        return []
