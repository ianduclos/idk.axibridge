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

from .compose import Affine, CanvasLayer, Project, _layer_seed, transform_paths
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
    time_curve: Literal["linear", "cosine_pingpong"] = Field(
        default="linear", title="Timeline curve",
        description="linear: A→B. cosine_pingpong: A→B→A over the same timeline; "
                    "clip/frame-follow playback stays linear.")
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
    """Map a window-normalized timeline value into morph t."""
    t = min(1.0, max(0.0, local_t))
    if curve == "cosine_pingpong":
        return 0.5 - 0.5 * math.cos(2 * math.pi * t)
    return t


def _structures_match(ga: list[Path], gb: list[Path]) -> bool:
    return len(ga) == len(gb) and all(
        len(pa.points) == len(pb.points) for pa, pb in zip(ga, gb)
    )


def check_compatible(
    la: CanvasLayer, lb: CanvasLayer,
    geo_a: list[Path], geo_b: list[Path],
) -> str | None:
    """None if A/B can tween; otherwise the human-readable reason."""
    if la.id == lb.id:
        return "pick two different layers"
    if la.source.type == "tween" or lb.source.type == "tween":
        return "tween-of-tween is not supported"
    same_gen = (
        la.source.type == "generator" and lb.source.type == "generator"
        and la.source.generator and la.source.generator == lb.source.generator
    )
    if not same_gen and not _structures_match(geo_a, geo_b):
        return ("layers are not interpolatable: need the same generator on both, "
                "or identical path structure (use 'duplicate layer')")
    return None


def _source_paths_at(la: CanvasLayer, lb: CanvasLayer,
                     geo_a: list[Path], geo_b: list[Path], t: float,
                     master_t: float | None = None) -> list[Path]:
    same_gen = (
        la.source.type == "generator" and lb.source.type == "generator"
        and la.source.generator and la.source.generator == lb.source.generator
    )
    if same_gen:
        src = get_source(la.source.generator)
        defaults = src.Params().model_dump()
        params = lerp_params(la.source.params or {}, lb.source.params or {}, t, defaults)
        # frame_offset is a layer-level lerped quantity (like the transform):
        # fold the interpolated offset into the generator's ``frame`` axis so an
        # A/B pair with identical params but different offsets plays the clip.
        # Clip-follow: each endpoint's FULL effective offset also carries the raw
        # (clamped) master value when that endpoint opted into ``frame_follow`` —
        # so scrubbing the master timeline advances the clip content the ladder
        # samples, without moving any stamp. The per-endpoint offsets lerp like
        # the layer-level ones.
        off_a = la.frame_offset + (master_t if (la.frame_follow and master_t is not None) else 0.0)
        off_b = lb.frame_offset + (master_t if (lb.frame_follow and master_t is not None) else 0.0)
        off = off_a + (off_b - off_a) * t
        if (off or off_a or off_b) and "frame" in src.Params.model_fields:
            params["frame"] = min(1.0, max(0.0, params.get("frame", 0.0) + off))
        doc = src.generate(src.Params(**params))
        return [p for lyr in doc.layers for p in lyr.paths]
    # structural mode: pointwise lerp (validated to match)
    out = []
    for pa, pb in zip(geo_a, geo_b):
        pts = [(ax + (bx - ax) * t, ay + (by - ay) * t)
               for (ax, ay), (bx, by) in zip(pa.points, pb.points)]
        out.append(Path(points=pts, filled=pa.filled if t < 0.5 else pb.filled))
    return out


def _effects_at(la: CanvasLayer, lb: CanvasLayer, t: float):
    """Lerped enabled-effect stack as (effect_id, params dict) pairs.
    Mismatched stacks step whole at 0.5 (endpoint fidelity over smoothness)."""
    ea = [s for s in la.effects if s.enabled]
    eb = [s for s in lb.effects if s.enabled]
    if [s.effect for s in ea] != [s.effect for s in eb]:
        return [(s.effect, dict(s.params)) for s in (ea if t < 0.5 else eb)]
    out = []
    for sa, sb in zip(ea, eb):
        defaults = get_effect(sa.effect).Params().model_dump()
        out.append((sa.effect, lerp_params(sa.params, sb.params, t, defaults)))
    return out


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
        if check_compatible(la, lb, geo_a, geo_b) is not None:
            return []
        if p.sweep <= 1:
            ts = [override_t if override_t is not None else p.t]
        else:
            # exclusive in-betweens: evenly spaced strictly between the endpoints
            ts = [i / (p.sweep + 1) for i in range(1, p.sweep + 1)]
        out: list[Path] = []
        for t in ts:
            paths = _source_paths_at(la, lb, geo_a, geo_b, t, master_t)
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
