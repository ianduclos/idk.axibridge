"""Server-side session: one open Project, its source geometry, and the
resolve pipeline that preview / estimate / plot all share.

One session per server process — this is a single-operator instrument. State
lives server-side so a browser reconnecting over Tailscale (or a second
device) sees the same canvas.

The critical invariant lives here: :meth:`resolved`, :meth:`resolved_document`
and :meth:`plot_document` all flow through ONE call to
:func:`compose.resolve_project`. What the preview shows is what the estimator
times is what the pen draws.
"""

from __future__ import annotations

import threading
from collections import OrderedDict, deque
from typing import Any

from . import compose, tween
from .compose import (
    Affine,
    CanvasLayer,
    CaptureGroup,
    CaptureSnapshot,
    EffectStep,
    LayerSource,
    PaperGuide,
    PlotOptions,
    Project,
    StagedPass,
    StagedSheet,
)
from .machine import manager
from .model import Layer, Path, PathDocument
from .registry import get_source
from .stores import Pen, pen_library, settings_store
from .svg_io import doc_from_svg, doc_from_vpype, doc_to_vpype


def _mul_affine(left: Affine, right: Affine) -> Affine:
    return Affine(
        a=left.a * right.a + left.c * right.b,
        b=left.b * right.a + left.d * right.b,
        c=left.a * right.c + left.c * right.d,
        d=left.b * right.c + left.d * right.d,
        e=left.a * right.e + left.c * right.f + left.e,
        f=left.b * right.e + left.d * right.f + left.f,
    )


def _invert_affine(m: Affine) -> Affine:
    det = m.a * m.d - m.b * m.c
    if abs(det) < 1e-12:
        raise ValueError("cannot transform animation group through a singular matrix")
    return Affine(
        a=m.d / det,
        b=-m.b / det,
        c=-m.c / det,
        d=m.a / det,
        e=(m.c * m.f - m.d * m.e) / det,
        f=(m.b * m.e - m.a * m.f) / det,
    )


#: Lineart v2 one-click stack presets (AARON-pass §D, docs/IDEAS-aaron-pass.md):
#: bottom-to-top layer order per flavor. Each entry's ``params`` overrides the
#: generator's own defaults; ``image``/``rotate``/``width`` come from the call
#: and are never listed here. Starting points, tuned by eye afterwards — one
#: dict literal, so a tuning pass is one obvious edit.
LINEART_STACK_PRESETS: dict[str, list[dict[str, Any]]] = {
    "faithful": [
        # lights start at 0.2 with wider spacing: below that the streamlines
        # fragment into pen-lift confetti on near-white gradients
        {"name": "lineart · lights", "generator": "lineart_hatch",
         "params": {"band_from": 0.2, "band_to": 0.45, "spacing": 12, "wobble": 0.6,
                    "direction": "flow"}},
        {"name": "lineart · mids", "generator": "lineart_hatch",
         "params": {"band_from": 0.45, "band_to": 0.75, "spacing": 7, "direction": "flow"}},
        {"name": "lineart · darks", "generator": "lineart_hatch",
         "params": {"band_from": 0.75, "band_to": 1.0, "spacing": 5, "cross_hatch": True,
                    "direction": "flow"}},
        {"name": "lineart · edges", "generator": "lineart_edges",
         "params": {"edge_mode": "xdog", "edge_threshold": 0.4,
                    "carefulness_tight": 0.15, "carefulness_loose": 0.8}},
    ],
    "artistic": [
        # wobble stays ≤1.1 on the mids: above that the hand noise erases the
        # flow direction and the band reads as scribble, not form
        {"name": "lineart · mids", "generator": "lineart_hatch",
         "params": {"band_from": 0.35, "band_to": 0.7, "spacing": 9, "dash": 0.25,
                    "wobble": 1.1}},
        {"name": "lineart · darks", "generator": "lineart_hatch",
         "params": {"band_from": 0.7, "band_to": 1.0, "spacing": 7, "cross_hatch": True,
                    "dash": 0.15}},
        {"name": "lineart · edges", "generator": "lineart_edges",
         "params": {"edge_mode": "xdog", "sharpness": 35, "edge_threshold": 0.6,
                    "wobble": 1.5, "carefulness_loose": 3.0}},
    ],
}


class Session:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.project = Project()
        self.project_dir: str | None = None
        #: layer id -> source paths in the layer's LOCAL frame (pre-transform)
        self.source_geometry: dict[str, list[Path]] = {}
        #: uploaded-SVG raw text by project-relative filename (written on save)
        self.svg_files: dict[str, str] = {}
        #: project-relative staging/<id>.svg -> frozen staged document.
        self.staging_documents: dict[str, PathDocument] = {}
        self._shaped_cache: dict[str, tuple[str, list[Path]]] = {}
        #: undo snapshots, newest last. Paths/lists are never mutated in place
        #: (module purity contract), so sharing references is safe — only the
        #: project model needs a deep copy.
        self._history: deque[
            tuple[Project, dict[str, list[Path]], dict[str, str], dict[str, PathDocument]]
        ] = deque(maxlen=8)
        #: last checkpoint's coalesce key: consecutive checkpoints carrying the
        #: same key collapse into ONE undo entry (live slider runs on a latched
        #: layer), so undo returns to the state before the run started.
        self._coalesce_key: tuple | None = None
        #: tween layer id -> (content key, materialised paths)
        self._tween_cache: dict[str, tuple[str, list[Path]]] = {}
        #: frame-follow generator layer id -> (content key, clip-advanced paths).
        #: An EPHEMERAL scrub overlay: computed only when resolving with a
        #: master_t, never written into ``source_geometry`` (the user's stored
        #: geometry stays byte-identical under a scrub). Keyed on content, so a
        #: cache hit hands back the SAME list object and the shaped cache re-hits.
        self._clip_cache: dict[str, tuple[str, list[Path]]] = {}
        #: grid-sheet frame caches, valid between project mutations only
        #: (cleared on every checkpoint/undo/history event). Keyed by
        #: (t, pens-signature, assets-signature) — pens and assets can change
        #: without a checkpoint, so they ride in the key rather than the
        #: clearing. ``_frame_lru`` holds resolved per-layer geometry for the
        #: last few frames (a page's worth); ``_frame_bbox`` holds only the
        #: combined bbox per frame, cheap enough to keep for a whole animation,
        #: so the shared-scale scan stops re-resolving every frame per page.
        self._frame_lru: "OrderedDict[tuple, dict[str, list[Path]]]" = OrderedDict()
        self._frame_bbox: dict[tuple, tuple[float, float, float, float] | None] = {}

    # -- undo -----------------------------------------------------------------

    def _checkpoint(self, coalesce: tuple | None = None) -> None:
        if coalesce is not None and coalesce == self._coalesce_key and self._history:
            # same coalesce run as the previous checkpoint: keep the run's
            # opening snapshot as THE undo point, but caches still go stale
            self._frame_lru.clear()
            self._frame_bbox.clear()
            return
        self._coalesce_key = coalesce
        # The deep copy deliberately EXCLUDES staging: capture groups, their
        # snapshots and staged documents are frozen by construction (staging
        # mutations replace objects wholesale — see rename_capture_group), so
        # history entries share them by reference, exactly like geometry
        # lists. Without this exclusion every checkpoint deep-copied every
        # capture snapshot's full geometry AND every staged document — the
        # "snapshots are cheap by construction" invariant had broken silently
        # when staging moved inside the Project model (found 2026-07-19).
        staging = self.project.staging
        self.project.staging = []
        try:
            proj = self.project.model_copy(deep=True)
        finally:
            self.project.staging = staging
        proj.staging = list(staging)
        self._history.append(
            (proj, dict(self.source_geometry), dict(self.svg_files),
             dict(self.staging_documents))
        )
        # a checkpoint precedes a mutation — cached frames are about to go stale
        self._frame_lru.clear()
        self._frame_bbox.clear()

    def clear_history(self) -> None:
        """Project switch: snapshots of another project must not restore here."""
        with self._lock:
            self._history.clear()
            self._coalesce_key = None
            self._frame_lru.clear()
            self._frame_bbox.clear()

    def undo(self) -> bool:
        with self._lock:
            self._coalesce_key = None  # a new edit after undo must push
            if not self._history:
                return False
            self.project, self.source_geometry, self.svg_files, self.staging_documents = self._history.pop()
            self._shaped_cache.clear()
            self._tween_cache.clear()
            self._clip_cache.clear()
            self._frame_lru.clear()
            self._frame_bbox.clear()
            return True

    def history_for_save(
        self,
    ) -> list[tuple[Project, dict[str, list[Path]], dict[str, str], dict[str, PathDocument]]]:
        """Newest-last history snapshots, trimmed by project_io to its persisted cap."""
        with self._lock:
            return list(self._history)

    def restore_history(
        self,
        history: list[tuple[Project, dict[str, list[Path]], dict[str, str], dict[str, PathDocument]]],
    ) -> None:
        with self._lock:
            self._history.clear()
            for item in history[-self._history.maxlen:]:
                self._history.append(item)

    # -- pens ---------------------------------------------------------------

    def pens(self) -> dict[str, Pen]:
        """Library pens, with the project's snapshots as fallback for pens
        that travelled with the file but aren't in this machine's drawer."""
        merged = dict(self.project.pens_used)
        for pen in pen_library.all():
            merged[pen.id] = pen
        return merged

    def _snapshot_pen(self, pen_id: str | None) -> None:
        if pen_id:
            pen = pen_library.get(pen_id)
            if pen:
                self.project.pens_used[pen.id] = pen

    # -- layer CRUD -----------------------------------------------------------

    @staticmethod
    def _effective_gen_params(
        layer: CanvasLayer, master_t: float | None = None
    ) -> dict[str, Any]:
        """The generator params to actually GENERATE with: the layer's stored
        source params, but with the layer's frame shift folded into the
        generator's ``frame`` axis (clamped 0..1) when the generator exposes
        one. The stored params are NEVER mutated — this returns a copy — so
        the user's raw ``frame`` and the undo/purity contract stay intact.

        The frame shift is ``frame_offset``, PLUS ``master_t`` when the layer
        opted into ``frame_follow`` and a ``master_t`` is supplied (the single
        place that folds a clip-follow scrub — the effective frame for the
        preview, estimate and plotter alike is computed here)."""
        params = dict(layer.source.params or {})
        if layer.source.type not in ("generator", "baked") or not layer.source.generator:
            return params
        shift = layer.frame_offset
        if master_t is not None and layer.frame_follow:
            shift += master_t
        if not shift:
            return params
        if "frame" not in get_source(layer.source.generator).Params.model_fields:
            return params
        params["frame"] = min(1.0, max(0.0, params.get("frame", 0.0) + shift))
        return params

    @staticmethod
    def _sequence_driven(generator_id: str, params: dict[str, Any]) -> bool:
        """True when this generator+params pair is clip-backed: the generator
        has a ``frame`` axis and its ``image`` param names a frame sequence —
        exactly the eligibility test ``_clip_overrides`` applies at scrub
        time. Used to default ``frame_follow`` ON at creation: a layer built
        from a video should play under the timeline without hunting for the
        opt-in checkbox (untick it for a deliberately frozen frame)."""
        from .assets import asset_store

        if "frame" not in get_source(generator_id).Params.model_fields:
            return False
        image = params.get("image")
        return isinstance(image, str) and asset_store.is_sequence(image)

    def _centering_transform(
        self, generator_id: str, params: dict[str, Any], doc: PathDocument
    ) -> Affine:
        """Image-based generators (params expose an ``image`` asset field)
        return a PathDocument anchored at (0,0) with known ``width``/
        ``height`` (mm) — the image's own placement, not a deliberate
        composition choice — so centre it on the bed instead of leaving it
        pinned at the machine origin. Procedural/geometric generators
        (rectangle, polygon, lissajous, grid, …) place themselves via their
        own size/margin params and are left at identity: their ``width``/
        ``height`` is just as often set, but re-centering would fight their
        own layout math and the tests/tools built on it. Clip-backed layers
        (``_sequence_driven``) are ALSO left at identity: their whole point
        is spatial-ladder positioning (duplicate + explicit transform per
        rung, see the timeline docs) where the base frame's placement is a
        deliberate anchor other rungs are measured from, not a stray origin
        pin to correct."""
        if doc.width is None or doc.height is None:
            return Affine()
        if "image" not in get_source(generator_id).Params.model_fields:
            return Affine()
        if self._sequence_driven(generator_id, params):
            return Affine()
        return Affine(e=(compose.BED_WIDTH - doc.width) / 2, f=(compose.BED_HEIGHT - doc.height) / 2)

    def add_generated_layer(self, generator_id: str, params: dict[str, Any]) -> CanvasLayer:
        src = get_source(generator_id)
        doc = src.generate(src.Params(**params))
        paths = [p for layer in doc.layers for p in layer.paths]
        layer = CanvasLayer(
            name=src.label,
            source=LayerSource(type="generator", generator=generator_id, params=params),
            transform=self._centering_transform(generator_id, params, doc),
            frame_follow=self._sequence_driven(generator_id, params),
        )
        with self._lock:
            self._checkpoint()
            self.project.layers.append(layer)
            self.source_geometry[layer.id] = paths
        return layer

    def regenerate_layer(self, layer_id: str, params: dict[str, Any] | None = None,
                         coalesce: bool = False) -> CanvasLayer:
        """``coalesce=True`` (the bench's latched live-edit) folds consecutive
        regenerates of the same layer into one undo entry — undo returns to
        the moment the slider run started, not one notch back."""
        with self._lock:
            layer = self.project.layer(layer_id)
            if layer.source.type not in ("generator", "baked") or not layer.source.generator:
                raise RuntimeError("layer was not generated; nothing to regenerate")
            self._checkpoint(("regen", layer_id) if coalesce else None)
            if params is not None:
                layer.source.params = params
            src = get_source(layer.source.generator)
            doc = src.generate(src.Params(**self._effective_gen_params(layer)))
            self.source_geometry[layer.id] = [p for lyr in doc.layers for p in lyr.paths]
            layer.source.type = "generator"  # a baked layer returns to live output
            layer.source.file = None  # snapshot is stale; rewritten on save
            self._shaped_cache.pop(layer_id, None)
            return layer

    def preview_layer_effects(self, layer_id: str, effects: list[dict[str, Any]]) -> list[Path]:
        """Shape a layer with a CANDIDATE effect stack — strictly read-only:
        no checkpoint, no cache writes, nothing stored. Feeds the live
        preview overlay; the commit still happens through update_layer."""
        with self._lock:
            layer = self.project.layer(layer_id)
            src = self.source_geometry.get(layer_id)
            candidate = layer.model_copy(deep=True)
        if src is None:
            raise RuntimeError("layer has no source geometry to preview (tween layers preview live already)")
        candidate.effects = [EffectStep(**e) for e in effects]
        # outside the lock: shape_layer is pure and src is never mutated in place
        return compose.shape_layer(candidate, src)

    def add_svg_layers(
        self, svg_text: str, filename: str, quantization_mm: float,
        rename: str | None = None,
    ) -> list[CanvasLayer]:
        """An uploaded SVG contributes its layers as compositor layers.
        ``rename`` overrides the SVG-derived layer names (scrap import: the
        library name beats whatever ids the SVG round-trip produced)."""
        doc = doc_from_svg(svg_text, quantization_mm, source=filename)
        if not doc.layers:
            raise RuntimeError("no plottable geometry found in the SVG")
        relname = f"sources/{filename}"
        created: list[CanvasLayer] = []
        with self._lock:
            self._checkpoint()
            self.svg_files[relname] = svg_text
            for i, svg_layer in enumerate(doc.layers):
                if rename:
                    name = rename if len(doc.layers) == 1 else f"{rename} {i + 1}"
                else:
                    name = svg_layer.name
                layer = CanvasLayer(
                    name=name,
                    source=LayerSource(
                        type="svg", file=relname, svg_layer=svg_layer.id,
                        quantization_mm=quantization_mm,
                    ),
                )
                self.project.layers.append(layer)
                self.source_geometry[layer.id] = list(svg_layer.paths)
                created.append(layer)
        return created

    def update_layer(self, layer_id: str, patch: dict[str, Any]) -> CanvasLayer:
        allowed = {"name", "visible", "draw", "transform", "effects", "pen_id",
                   "occluder", "receives_occlusion", "occlusion_margin_mm",
                   "region", "region_boundary", "frame_offset", "frame_follow"}
        with self._lock:
            layer = self.project.layer(layer_id)
            self._checkpoint()
            effective_patch = dict(patch)
            if "transform" in effective_patch and layer.source.type == "tween":
                keyframes = self._animation_keyframes_for(layer)
                if keyframes:
                    requested = Affine(**effective_patch["transform"])
                    delta = _mul_affine(requested, _invert_affine(layer.transform))
                    for keyframe in keyframes:
                        keyframe.transform = _mul_affine(delta, keyframe.transform)
                        self._shaped_cache.pop(keyframe.id, None)
                    self._tween_cache.pop(layer.id, None)
                    # The visible tween parent is the UI handle for the group;
                    # the actual placement lives on the A/B keyframes.
                    effective_patch["transform"] = layer.transform.model_dump()
            data = layer.model_dump()
            for k, v in effective_patch.items():
                if k not in allowed:
                    raise KeyError(f"field not patchable: {k}")
                data[k] = v
            updated = CanvasLayer(**data)
            idx = self.project.layers.index(layer)
            self.project.layers[idx] = updated
            self._snapshot_pen(updated.pen_id)
            # A frame_offset change on a frame-driven generator re-samples the
            # clip: regenerate its source geometry with the offset folded into
            # ``frame`` (stored params keep the user's raw value). Same lock,
            # same single checkpoint; a generation failure propagates (identical
            # failure semantics to regenerate_layer, which has already
            # checkpointed). Non-generator sources just store the field.
            # (live generators only: a baked layer's geometry holds consolidated
            # transform/effects — regenerating here would silently discard them;
            # an explicit "regenerate" un-bakes on purpose and picks up the offset)
            if ("frame_offset" in patch and updated.frame_offset != layer.frame_offset
                    and updated.source.type == "generator"
                    and updated.source.generator
                    and "frame" in get_source(updated.source.generator).Params.model_fields):
                src = get_source(updated.source.generator)
                doc = src.generate(src.Params(**self._effective_gen_params(updated)))
                self.source_geometry[updated.id] = [p for lyr in doc.layers for p in lyr.paths]
                self._shaped_cache.pop(updated.id, None)
            return updated

    def delete_layer(self, layer_id: str) -> list[str]:
        return self.delete_layers([layer_id])

    def _tweens(self) -> list[CanvasLayer]:
        return [l for l in self.project.layers if l.source.type == "tween"]

    def _tween_dependency_order(self) -> list[CanvasLayer]:
        """Tween layers ordered so a tween is materialised AFTER any tween it
        references. Nested tweens (a sweep between two tweens) need their inner
        tweens resolved first: the inner geometry must be in the ephemeral
        ``geo`` overlay, and its list identity is folded into the outer tween's
        cache key, so a stale ordering would let a grandchild edit go unseen.
        A reference cycle is broken by the visited/on-stack guard."""
        tweens = self._tweens()
        by_id = {l.id: l for l in tweens}
        ordered: list[CanvasLayer] = []
        seen: set[str] = set()

        def visit(layer: CanvasLayer, stack: set[str]) -> None:
            if layer.id in seen or layer.id in stack:
                return
            stack.add(layer.id)
            for rid in self._tween_refs(layer):
                dep = by_id.get(rid)
                if dep is not None:
                    visit(dep, stack)
            stack.discard(layer.id)
            seen.add(layer.id)
            ordered.append(layer)

        for layer in tweens:
            visit(layer, set())
        return ordered

    @staticmethod
    def _tween_refs(layer: CanvasLayer) -> tuple[Any, Any]:
        p = layer.source.params or {}
        return p.get("a"), p.get("b")

    def _animation_keyframes_for(self, tween_layer: CanvasLayer) -> list[CanvasLayer]:
        """Hidden A/B layers created by Animate, not visible manual tween refs."""
        if tween_layer.source.type != "tween":
            return []
        refs: list[CanvasLayer] = []
        for ref_id in self._tween_refs(tween_layer):
            try:
                refs.append(self.project.layer(ref_id))
            except KeyError:
                return []
        if len(refs) != 2:
            return []
        if all((not l.visible) and (" ▸ A" in l.name or " ▸ B" in l.name) for l in refs):
            return refs
        return []

    def delete_layers(self, layer_ids: list[str], cascade: bool = True) -> list[str]:
        """Bulk delete = ONE history entry, so one undo restores the lot.

        ``cascade`` (the default) expands the doomed set to a fixpoint so a
        delete never leaves a dangling tween: (a) any tween referencing a
        doomed layer joins it; (b) any HIDDEN layer referenced only by doomed
        tweens joins it (the animate-created keyframes travel with their
        tween, but a manual tween's VISIBLE sources are never swept). Returns
        the ordered (project z-order) list of deleted layer ids.

        Un-animate: deleting a tween DIRECTLY (its id in ``layer_ids``, not
        merely cascade-collected) does not sweep its A keyframe — it RESTORES
        it (un-hides it and strips the ``" ▸ A"`` suffix), turning the
        animation back into the plain layer it came from. The A keyframe is
        restored only when hidden and unreferenced by any surviving tween; the
        B keyframe still sweeps. Directly deleting a keyframe keeps the full
        group cascade.

        ``cascade=False`` refuses the delete (human-readable RuntimeError) if a
        surviving tween still references a doomed layer — the strict mode."""
        with self._lock:
            layers = [self.project.layer(i) for i in layer_ids]  # all-or-nothing
            direct = {l.id for l in layers}  # caller's targets, pre-cascade
            doomed = set(direct)

            if cascade:
                while True:
                    changed = False
                    # (a) tweens that reference anything doomed
                    for tw in self._tweens():
                        if tw.id in doomed:
                            continue
                        a, b = self._tween_refs(tw)
                        if a in doomed or b in doomed:
                            doomed.add(tw.id)
                            changed = True
                    # (b) hidden layers referenced by a doomed tween and by no
                    # surviving tween (collects animate keyframes; never takes a
                    # manual tween's visible sources)
                    for layer in self.project.layers:
                        if layer.id in doomed or layer.visible:
                            continue
                        by_doomed = by_surviving = False
                        for tw in self._tweens():
                            a, b = self._tween_refs(tw)
                            if layer.id in (a, b):
                                if tw.id in doomed:
                                    by_doomed = True
                                else:
                                    by_surviving = True
                        if by_doomed and not by_surviving:
                            doomed.add(layer.id)
                            changed = True
                    if not changed:
                        break

                # Un-animate: a DIRECTLY deleted tween restores its A keyframe
                # instead of sweeping it. Decide here (part of the final doomed
                # set) so the restored, re-shown A is never re-collected; the
                # visible/name mutation happens after the checkpoint below.
                restore: set[str] = set()
                for tw in self._tweens():
                    if tw.id not in direct:  # only DIRECT tween deletions
                        continue
                    a_ref, _ = self._tween_refs(tw)
                    if a_ref in direct:
                        continue  # the user deleted A itself too — honour that
                    try:
                        a_layer = self.project.layer(a_ref)
                    except KeyError:
                        continue
                    if a_layer.visible:
                        continue
                    referenced_by_surviving = any(
                        a_ref in self._tween_refs(t2)
                        for t2 in self._tweens()
                        if t2.id not in doomed
                    )
                    if not referenced_by_surviving:
                        restore.add(a_ref)
                doomed -= restore
            else:
                restore = set()
                for tw in self._tweens():
                    if tw.id in doomed:
                        continue
                    a, b = self._tween_refs(tw)
                    if a in doomed or b in doomed:
                        raise RuntimeError(
                            f"layer is referenced by interpolation layer {tw.name!r} — "
                            "delete that first (or together)"
                        )

            self._checkpoint()
            # un-hide + un-suffix the restored A keyframes (already excluded
            # from ``doomed``, so they survive the deletion below)
            for rid in restore:
                a_layer = self.project.layer(rid)
                a_layer.visible = True
                if a_layer.name.endswith(" ▸ A"):
                    a_layer.name = a_layer.name[: -len(" ▸ A")]
            # delete in project z-order for a deterministic, reported result
            deleted = [l for l in list(self.project.layers) if l.id in doomed]
            for layer in deleted:
                self.project.layers.remove(layer)
                self.source_geometry.pop(layer.id, None)
                self._shaped_cache.pop(layer.id, None)
                self._tween_cache.pop(layer.id, None)
                self._clip_cache.pop(layer.id, None)
            return [l.id for l in deleted]

    def reorder_layers(self, ordered_ids: list[str]) -> None:
        with self._lock:
            if sorted(ordered_ids) != sorted(l.id for l in self.project.layers):
                raise ValueError("order must contain exactly the current layer ids")
            self._checkpoint()
            by_id = {l.id: l for l in self.project.layers}
            self.project.layers = [by_id[i] for i in ordered_ids]

    def create_tween_layer(self, a_id: str, b_id: str) -> CanvasLayer:
        """Interpolation layer between two compatible layers (see tween.py).
        Validated NOW with a human-readable reason; the references are live."""
        with self._lock:
            la = self.project.layer(a_id)
            lb = self.project.layer(b_id)
            reason = tween.check_compatible(
                la, lb, self.source_geometry.get(a_id, []),
                self.source_geometry.get(b_id, []), self.project,
            )
            if reason:
                raise RuntimeError(reason)
            self._checkpoint()
            layer = CanvasLayer(
                name=f"{la.name} ⇄ {lb.name}",
                source=LayerSource(
                    type="tween",
                    params=tween.TweenParams(a=a_id, b=b_id).model_dump(),
                ),
                pen_id=la.pen_id,
            )
            # Project order is bottom->top, while the layer list displays the
            # reverse. Insert just below the selected top layer so the new
            # interpolation appears directly under it in the UI.
            idx = max(self.project.layers.index(la), self.project.layers.index(lb))
            self.project.layers.insert(idx, layer)
            self.source_geometry[layer.id] = []  # materialised on next resolve
            return layer

    def set_tween_params(self, layer_id: str, values: dict[str, Any]) -> CanvasLayer:
        with self._lock:
            layer = self.project.layer(layer_id)
            if layer.source.type != "tween":
                raise RuntimeError("not an interpolation layer")
            current = dict(layer.source.params or {})
            merged = tween.TweenParams(**{**current, **values})  # validates bounds
            self._checkpoint()
            layer.source.params = merged.model_dump()
            return layer

    def explode_tween(self, layer_id: str) -> list[CanvasLayer]:
        """Split a tween into one baked layer per sweep step (each gets its
        own pen / occlusion / further editing). The live tween stays, hidden,
        so the morph can be re-tuned and re-exploded. One undo step."""
        with self._lock:
            layer = self.project.layer(layer_id)
            if layer.source.type != "tween":
                raise RuntimeError("not an interpolation layer")
            p = tween.TweenParams(**(layer.source.params or {}))
            self._checkpoint()
            ts = [p.t] if p.sweep <= 1 else [
                i / (p.sweep + 1) for i in range(1, p.sweep + 1)
            ]
            created: list[CanvasLayer] = []
            idx = self.project.layers.index(layer)
            for i, t in enumerate(ts):
                step = layer.model_copy(deep=True)
                step.source.params = {**(layer.source.params or {}), "t": t, "sweep": 1}
                paths = tween.materialize(step, self.project, self.source_geometry)
                shaped = compose.shape_layer(layer, paths)  # tween's own tf/fx baked in
                data = layer.model_dump()
                del data["id"]
                data.update(
                    name=f"{layer.name} t={t:.2f}", visible=True,
                    transform=Affine().model_dump(), effects=[],
                    source={"type": "baked"},
                )
                nl = CanvasLayer(**data)
                self.project.layers.insert(idx + 1 + i, nl)
                self.source_geometry[nl.id] = shaped
                created.append(nl)
            layer.visible = False
            return created

    def _sheet_rect(self) -> tuple[float, float, float, float]:
        """The paper-guide rectangle grid sheets are laid on (bed if no guide)."""
        guide = self.project.guide
        if guide is None:
            return 0.0, 0.0, compose.BED_WIDTH, compose.BED_HEIGHT
        return guide.x, guide.y, guide.width, guide.height

    def _frame_sig(self) -> tuple[int, int]:
        """Cache-key component for state that can change WITHOUT a checkpoint:
        pen line diameters (occlusion masks) and the asset store (frame-follow
        clips re-sample it during resolve)."""
        from .assets import asset_store

        pens_sig = hash(tuple(sorted(
            (pid, p.line_diameter_mm) for pid, p in self.pens().items())))
        assets_sig = hash(tuple(sorted(
            (name, len(data)) for name, data in asset_store.all().items())))
        return pens_sig, assets_sig

    def _grid_place(
        self, ts: list[float], cols: int, rows: int, margin_mm: float,
        master_scale_ts: list[float] | None = None,
        framing: str = "center",
    ) -> list[dict[str, list[Path]]]:
        """Lay each master-timeline sample ``ts[i]`` into cell i of a cols×rows
        grid on the paper guide, keeping PER-LAYER geometry (not flattened) so
        callers can group by pen. One SHARED scale across every frame — derived
        from the union bounding box over ``master_scale_ts`` (defaults to
        ``ts``); the sheet callers pass the FULL animation's ts so frame k is
        the same size on every page. Cells are row-major. Geometry is the
        VISIBLE, resolved (post-occlusion) paths, so a cell is exactly what the
        canvas/plotter show at that t.

        ``framing``:
        * ``"center"`` — each frame centred in its cell by its OWN bbox. Right
          for parameter sweeps; but pure translation animations largely cancel
          (each cell re-centres the moving subject).
        * ``"fixed"`` — every frame shares ONE window (the union bbox), like a
          locked-off camera: motion stays motion across the flipbook.

        Resolves go through the per-frame caches (``_frame_lru`` geometry,
        ``_frame_bbox`` bounds), cleared on any project mutation — so stepping
        pages/passes of an unchanged project stops re-resolving the whole
        animation. Read-only: no checkpoint, no user source_geometry writes.
        Call under ``self._lock``."""
        sig = self._frame_sig()

        def frame_key(t: float) -> tuple:
            return (round(t, 9), *sig)

        def visible_geo(t: float) -> dict[str, list[Path]]:
            key = frame_key(t)
            hit = self._frame_lru.get(key)
            if hit is not None:
                self._frame_lru.move_to_end(key)
                return hit
            # resolved() re-materialises tweens as a side effect (the single
            # resolve path); z-order preserved so flattening callers match.
            resolved = self.resolved(master_t=t)
            frame = {layer.id: resolved[layer.id]
                     for layer in self.project.layers
                     if layer.visible and resolved.get(layer.id)}
            self._frame_lru[key] = frame
            while len(self._frame_lru) > 144:  # a 12×12 page's worth
                self._frame_lru.popitem(last=False)
            xs = [x for paths in frame.values() for p in paths for x, _ in p.points]
            ys = [y for paths in frame.values() for p in paths for _, y in p.points]
            self._frame_bbox[key] = (
                (min(xs), min(ys), max(xs), max(ys)) if xs else None)
            return frame

        def frame_bbox(t: float) -> tuple[float, float, float, float] | None:
            key = frame_key(t)
            if key not in self._frame_bbox:
                visible_geo(t)
            return self._frame_bbox[key]

        # shared scale from bboxes only — cached across pages/passes
        boxes = [b for t in (master_scale_ts or ts) if (b := frame_bbox(t)) is not None]
        if not boxes:
            raise RuntimeError("nothing to place (no visible geometry across the frame range)")
        uminx = min(b[0] for b in boxes)
        uminy = min(b[1] for b in boxes)
        umaxx = max(b[2] for b in boxes)
        umaxy = max(b[3] for b in boxes)
        bw = max(umaxx - uminx, 1e-6)
        bh = max(umaxy - uminy, 1e-6)

        sheet_x, sheet_y, sheet_w, sheet_h = self._sheet_rect()
        cell_w = sheet_w / cols - 2 * margin_mm
        cell_h = sheet_h / rows - 2 * margin_mm
        if cell_w <= 0 or cell_h <= 0:
            raise RuntimeError("margin too large for this grid on the current paper guide")

        scale = min(cell_w / bw, cell_h / bh)  # shared: no per-frame size jitter

        placed_frames: list[dict[str, list[Path]]] = []
        for i, t in enumerate(ts):
            frame = visible_geo(t)
            row, col = divmod(i, cols)  # row-major, left-to-right, top-to-bottom
            cx = sheet_x + (col + 0.5) * (sheet_w / cols)
            cy = sheet_y + (row + 0.5) * (sheet_h / rows)
            if framing == "fixed":
                fcx, fcy = (uminx + umaxx) / 2, (uminy + umaxy) / 2
            else:
                box = frame_bbox(t)
                fcx = (box[0] + box[2]) / 2 if box else 0.0
                fcy = (box[1] + box[3]) / 2 if box else 0.0
            aff = Affine(a=scale, b=0.0, c=0.0, d=scale,
                         e=cx - scale * fcx, f=cy - scale * fcy)
            placed_frames.append(
                {lid: compose.transform_paths(paths, aff) for lid, paths in frame.items()}
            )
        return placed_frames

    def _sheet_marks(self, cols: int, rows: int, arm_mm: float = 2.0) -> list[Path]:
        """Registration crosshairs at every grid intersection of the sheet —
        (cols+1)×(rows+1) small ＋ marks separating the frames. Clamped to the
        bed (the machine frame has no negatives)."""
        x0, y0, w, h = self._sheet_rect()
        out: list[Path] = []
        for i in range(cols + 1):
            for j in range(rows + 1):
                cx, cy = x0 + i * w / cols, y0 + j * h / rows
                out.append(Path(points=[
                    (max(cx - arm_mm, 0.0), cy),
                    (min(cx + arm_mm, compose.BED_WIDTH), cy)], filled=False))
                out.append(Path(points=[
                    (cx, max(cy - arm_mm, 0.0)),
                    (cx, min(cy + arm_mm, compose.BED_HEIGHT))], filled=False))
        return out

    def sheet_document(
        self, cols: int, rows: int, frames: int,
        t_from: float, t_to: float, margin_mm: float, page: int,
        pen_id: str | None = None,
        framing: str = "center", marks: bool = False,
    ) -> PathDocument:
        """One physical sheet of the flip-book, assembled at plot time — NO
        project mutation, no checkpoint (it is pure assembly; the tray capture
        path is how a sheet becomes editable layers, via ``insert``).

        ``frames`` timeline samples over [t_from, t_to] are laid into a
        cols×rows grid, chunked ``cols*rows`` cells per page; ``page`` (0-based)
        selects the chunk, the last of which may be partial. The scale is shared
        across ALL frames (every page) so frame k is the same size wherever it
        lands — flipbook-consistent.

        The document is grouped BY PEN: one doc layer per pen worn by a
        contributing layer, plus a ``""`` "no pen" group, each carrying every
        cell's geometry for layers wearing that pen, in project z-order. The
        physical pen-nib offset (:meth:`_pen_offsets`) is applied AFTER
        placement so registration compensation is not scaled by the cell
        factor. ``pen_id`` restricts the document to one pen group — a single
        plot pass (``""`` selects the no-pen group); ``None`` returns every
        group (export / plan). Call the result through :meth:`_optimize` when
        plotting (crop applies to sheets too — that is correct)."""
        if not (1 <= cols <= 12 and 1 <= rows <= 12):
            raise ValueError("cols and rows must each be 1..12")
        if not (2 <= frames <= 240):
            raise ValueError("frames must be 2..240")
        if not (0.0 <= margin_mm <= 30.0):
            raise ValueError("margin_mm must be 0..30")
        if not (0.0 <= t_from <= 1.0 and 0.0 <= t_to <= 1.0):
            raise ValueError("t_from/t_to must be 0..1")

        with self._lock:
            groups, n_pages = self._sheet_groups(
                cols, rows, frames, t_from, t_to, margin_mm, page, pen_id,
                framing=framing, marks=marks)
            pens = self.pens()
            out_layers = [
                Layer(
                    id=j + 1,
                    name=(pens[pid].name if pid and pid in pens else "no pen"),
                    color=(pens[pid].color if pid and pid in pens else compose.INK),
                    paths=paths,
                )
                for j, (pid, paths) in enumerate(groups)
            ]
            return PathDocument(
                layers=out_layers, width=compose.BED_WIDTH, height=compose.BED_HEIGHT,
                source=f"{self.project.name} [sheet {page + 1}/{n_pages}]",
            )

    def _sheet_groups(
        self, cols: int, rows: int, frames: int,
        t_from: float, t_to: float, margin_mm: float, page: int,
        pen_id: str | None,
        framing: str = "center", marks: bool = False,
    ) -> tuple[list[tuple[str, list[Path]]], int]:
        """The by-pen assembly behind :meth:`sheet_document` and
        :meth:`sheet_passes`: places the page's frames, groups their geometry by
        pen (``""`` = no pen), applies the physical nib offset AFTER placement,
        and orders the groups by project z-order of each pen's first layer.
        ``marks`` prepends the crosshair grid to the FIRST pass (they plot once
        per page, whatever pen that pass wears). Returns
        ``([(pen_id, paths), …], n_pages)`` with empty groups dropped.
        ``pen_id`` (not None) filters to that single group — after ordering and
        marks, so the filtered pass is identical to its slice of the full set.
        Call under the lock."""
        per_page = cols * rows
        n_pages = (frames + per_page - 1) // per_page
        if not (0 <= page < n_pages):
            raise IndexError(f"page {page} out of range (0..{n_pages - 1})")

        all_ts = [t_from] if frames <= 1 else [
            t_from + (t_to - t_from) * i / (frames - 1) for i in range(frames)
        ]
        chunk = all_ts[page * per_page: (page + 1) * per_page]
        placed = self._grid_place(chunk, cols, rows, margin_mm,
                                  master_scale_ts=all_ts, framing=framing)

        pen_offsets = self._pen_offsets()
        layer_pen = {l.id: (l.pen_id or "") for l in self.project.layers}
        # pens in project z-order of first appearance (stable pass order across
        # pages) — "" (no pen) ranks wherever its first layer sits.
        rank: dict[str, int] = {}
        for i, l in enumerate(self.project.layers):
            rank.setdefault(l.pen_id or "", i)

        groups: dict[str, list[Path]] = {}
        for frame in placed:
            for lid, paths in frame.items():
                pid = layer_pen.get(lid, "")
                ox, oy = pen_offsets.get(lid, (0.0, 0.0))
                if ox or oy:  # physical registration, applied post-placement
                    paths = [Path(points=[(x - ox, y - oy) for x, y in p.points],
                                  filled=p.filled) for p in paths]
                groups.setdefault(pid, []).extend(paths)

        ordered = [
            (pid, groups[pid])
            for pid in sorted(groups, key=lambda p: rank.get(p, 1 << 30))
            if groups[pid]
        ]
        if marks and ordered:
            first_pid, first_paths = ordered[0]
            ordered[0] = (first_pid, self._sheet_marks(cols, rows) + first_paths)
        if pen_id is not None:
            ordered = [(pid, paths) for pid, paths in ordered if pid == pen_id]
        return ordered, n_pages

    def sheet_passes(
        self, cols: int, rows: int, frames: int,
        t_from: float = 0.0, t_to: float = 1.0, margin_mm: float = 5.0, page: int = 0,
    ) -> list[str]:
        """Ordered pen-ids (``""`` = no pen) that plot as passes on ``page`` —
        one entry per plot pass, in pass order. For the stepper's page summary."""
        with self._lock:
            groups, _ = self._sheet_groups(
                cols, rows, frames, t_from, t_to, margin_mm, page, None)
            return [pid for pid, _ in groups]

    def sheet_pages(self, frames: int, cols: int, rows: int) -> int:
        """Number of physical sheets ``frames`` cells fill at cols×rows."""
        per_page = max(cols * rows, 1)
        return (frames + per_page - 1) // per_page

    # -- staging tray ---------------------------------------------------------

    def _capture_snapshot(self) -> CaptureSnapshot:
        return CaptureSnapshot(
            name=self.project.name,
            layers=[l.model_copy(deep=True) for l in self.project.layers],
            guide=self.project.guide.model_copy(deep=True),
            view=self.project.view,
            pens_used={k: v.model_copy(deep=True) for k, v in self.project.pens_used.items()},
            backend_params={k: dict(v) for k, v in self.project.backend_params.items()},
            plot_options=self.project.plot_options.model_copy(deep=True),
            # geometry is shared by reference, not deep-copied: lists are only
            # ever replaced wholesale and Path objects are never mutated (the
            # module-purity contract, enforced by test_effect_contract), so
            # the snapshot freezes for free — same argument as undo history.
            # Layers stay deep-copied: regenerate/update DO rebind fields on
            # the live layer objects (source.params etc.).
            source_geometry=dict(self.source_geometry),
            svg_files=dict(self.svg_files),
        )

    @staticmethod
    def _doc_has_geometry(doc: PathDocument) -> bool:
        return any(layer.paths for layer in doc.layers)

    @staticmethod
    def _pass_stats(doc: PathDocument, pen_ids: list[str] | None = None) -> list[StagedPass]:
        out: list[StagedPass] = []
        for i, layer in enumerate(doc.layers):
            paths = layer.paths
            pid = pen_ids[i] if pen_ids and i < len(pen_ids) else ""
            out.append(StagedPass(
                pen_id=pid,
                name=layer.name or "no pen",
                color=layer.color,
                paths=len(paths),
                points=sum(len(p.points) for p in paths),
                pen_down_distance=sum(p.length() for p in paths),
            ))
        return out

    def _grouped_document(self, target: str = "all", master_t: float | None = None) -> PathDocument:
        """Resolved, pen-compensated output grouped by physical pen pass.

        Unlike ``plot_document`` this intentionally does not optimise/sort:
        staged sheets store frozen geometry, and plotting/planning applies the
        current plot-pass optimiser at use time just like grid sheets do."""
        resolved = self.resolved(master_t)
        pens = self.pens()
        offsets = self._pen_offsets()
        rank: dict[str, int] = {}
        groups: dict[str, list[Path]] = {}
        names: dict[str, str] = {}
        colors: dict[str, str] = {}
        for i, layer in enumerate(self.project.layers):
            if target != "all" and layer.id != target:
                continue
            if not layer.visible:
                continue
            paths = resolved.get(layer.id, [])
            if not paths:
                continue
            pid = layer.pen_id or ""
            rank.setdefault(pid, i)
            pen = pens.get(pid)
            names[pid] = pen.name if pen else "no pen"
            colors[pid] = pen.color if pen else compose.INK
            ox, oy = offsets.get(layer.id, (0.0, 0.0))
            if ox or oy:
                paths = [Path(points=[(x - ox, y - oy) for x, y in p.points],
                              filled=p.filled) for p in paths]
            groups.setdefault(pid, []).extend(paths)
        layers = [
            Layer(id=j + 1, name=names[pid], color=colors[pid], paths=groups[pid])
            for j, pid in enumerate(sorted(groups, key=lambda p: rank.get(p, 1 << 30)))
        ]
        return PathDocument(
            layers=layers, width=compose.BED_WIDTH, height=compose.BED_HEIGHT,
            source=f"{self.project.name} [{target}]",
        )

    def _grouped_pass_ids(self, target: str = "all", master_t: float | None = None) -> list[str]:
        resolved = self.resolved(master_t)
        rank: dict[str, int] = {}
        for i, layer in enumerate(self.project.layers):
            if target != "all" and layer.id != target:
                continue
            if layer.visible and resolved.get(layer.id):
                rank.setdefault(layer.pen_id or "", i)
        return sorted(rank, key=lambda p: rank.get(p, 1 << 30))

    def _documents_for_format(self, fmt: dict[str, Any]) -> list[PathDocument]:
        kind = fmt.get("kind")
        if kind == "sheet":
            frames = int(fmt["frames"])
            cols = int(fmt["cols"])
            rows = int(fmt["rows"])
            pages = self.sheet_pages(frames, cols, rows)
            return [
                self.sheet_document(
                    cols, rows, frames,
                    float(fmt.get("t_from", 0.0)),
                    float(fmt.get("t_to", 1.0)),
                    float(fmt.get("margin_mm", 5.0)),
                    page,
                    pen_id=None,
                    framing=str(fmt.get("framing", "center")),
                    marks=bool(fmt.get("marks", False)),
                )
                for page in range(pages)
            ]
        if kind == "frame":
            return [self._grouped_document(
                str(fmt.get("target", "all")),
                float(fmt.get("master_t", 0.0)),
            )]
        if kind == "plot":
            return [self._grouped_document(str(fmt.get("target", "all")), None)]
        raise ValueError(f"unknown capture format kind: {kind!r}")

    def _pass_ids_for_format(self, fmt: dict[str, Any]) -> list[list[str]]:
        kind = fmt.get("kind")
        if kind == "sheet":
            frames = int(fmt["frames"])
            cols = int(fmt["cols"])
            rows = int(fmt["rows"])
            pages = self.sheet_pages(frames, cols, rows)
            return [
                self.sheet_passes(
                    cols, rows, frames,
                    float(fmt.get("t_from", 0.0)),
                    float(fmt.get("t_to", 1.0)),
                    float(fmt.get("margin_mm", 5.0)),
                    page,
                )
                for page in range(pages)
            ]
        if kind == "frame":
            return [self._grouped_pass_ids(
                str(fmt.get("target", "all")),
                float(fmt.get("master_t", 0.0)),
            )]
        if kind == "plot":
            return [self._grouped_pass_ids(str(fmt.get("target", "all")), None)]
        return [[]]

    def _store_capture_group(
        self,
        *,
        name: str,
        kind: str,
        fmt: dict[str, Any],
        docs: list[PathDocument],
        snapshot: CaptureSnapshot | None,
        pass_ids: list[list[str]] | None = None,
        source_capture_ids: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> CaptureGroup:
        group = CaptureGroup(
            name=name,
            kind=kind,
            format=fmt,
            snapshot=snapshot,
            source_capture_ids=source_capture_ids or [],
            warnings=warnings or [],
        )
        for i, doc in enumerate(docs):
            ids_for_sheet = pass_ids[i] if pass_ids and i < len(pass_ids) else None
            sheet = StagedSheet(
                name=f"sheet {i + 1}",
                passes=self._pass_stats(doc, ids_for_sheet),
            )
            relname = f"staging/{group.id}-{sheet.id}.svg"
            sheet.file = relname
            for pinfo, layer in zip(sheet.passes, doc.layers):
                pinfo.name = layer.name or pinfo.name
            group.sheets.append(sheet)
            # ownership handover, no defensive copy: staged documents are
            # frozen at store time (reads go through staged_document's copy)
            self.staging_documents[relname] = doc
        self.project.staging.append(group)
        return group

    def capture_to_staging(
        self,
        *,
        kind: str,
        name: str | None = None,
        target: str = "all",
        master_t: float | None = None,
        cols: int = 1,
        rows: int = 1,
        frames: int = 2,
        t_from: float = 0.0,
        t_to: float = 1.0,
        margin_mm: float = 5.0,
        framing: str = "center",
        marks: bool = False,
    ) -> CaptureGroup:
        with self._lock:
            if kind == "sheet":
                if not (1 <= cols <= 12 and 1 <= rows <= 12):
                    raise ValueError("cols and rows must each be 1..12")
                if not (2 <= frames <= 240):
                    raise ValueError("frames must be 2..240")
                if not (0.0 <= margin_mm <= 30.0):
                    raise ValueError("margin_mm must be 0..30")
                if not (0.0 <= t_from <= 1.0 and 0.0 <= t_to <= 1.0):
                    raise ValueError("t_from/t_to must be 0..1")
                if framing not in ("center", "fixed"):
                    raise ValueError("framing must be center or fixed")
                fmt = {
                    "kind": "sheet", "target": "all",
                    "cols": cols, "rows": rows, "frames": frames,
                    "pages": self.sheet_pages(frames, cols, rows),
                    "t_from": t_from, "t_to": t_to, "margin_mm": margin_mm,
                    "framing": framing, "marks": marks,
                }
            elif kind == "frame":
                mt = 0.0 if master_t is None else master_t
                if not (0.0 <= mt <= 1.0):
                    raise ValueError("master_t must be 0..1")
                fmt = {"kind": "frame", "target": target, "master_t": mt}
            elif kind == "plot":
                fmt = {"kind": "plot", "target": target}
            else:
                raise ValueError("kind must be plot, frame, or sheet")

            docs = self._documents_for_format(fmt)
            pass_ids = self._pass_ids_for_format(fmt)
            if not any(self._doc_has_geometry(doc) for doc in docs):
                raise RuntimeError("nothing to capture (no staged geometry)")
            snapshot = self._capture_snapshot()
            self._checkpoint()
            return self._store_capture_group(
                name=name or f"{kind} capture",
                kind=kind,
                fmt=fmt,
                docs=docs,
                snapshot=snapshot,
                pass_ids=pass_ids,
            )

    def _find_capture(self, group_id: str) -> CaptureGroup:
        for group in self.project.staging:
            if group.id == group_id:
                return group
        raise KeyError(f"unknown capture group: {group_id!r}")

    @staticmethod
    def _find_sheet(group: CaptureGroup, sheet_id: str | None = None) -> StagedSheet:
        if sheet_id is None:
            if not group.sheets:
                raise KeyError("capture has no sheets")
            return group.sheets[0]
        for sheet in group.sheets:
            if sheet.id == sheet_id:
                return sheet
        raise KeyError(f"unknown staged sheet: {sheet_id!r}")

    def staged_document(
        self, group_id: str, sheet_id: str | None = None, pen_id: str | None = None
    ) -> PathDocument:
        with self._lock:
            group = self._find_capture(group_id)
            sheet = self._find_sheet(group, sheet_id)
            if not sheet.file or sheet.file not in self.staging_documents:
                raise KeyError("staged sheet geometry is missing")
            doc = self.staging_documents[sheet.file].model_copy(deep=True)
            if pen_id is None:
                return doc
            layers: list[Layer] = []
            for layer, pinfo in zip(doc.layers, sheet.passes):
                if pinfo.pen_id == pen_id:
                    layers.append(layer)
            return PathDocument(
                layers=layers, width=doc.width, height=doc.height,
                source=f"{doc.source} [{pen_id or 'no pen'}]",
            )

    def rename_capture_group(self, group_id: str, name: str) -> CaptureGroup:
        with self._lock:
            group = self._find_capture(group_id)
            self._checkpoint()
            # replace, never mutate: undo history shares group objects by
            # reference, so an in-place rename would rewrite the past
            renamed = group.model_copy(update={"name": name.strip() or group.name})
            self.project.staging = [renamed if g.id == group_id else g
                                    for g in self.project.staging]
            return renamed

    def delete_capture_group(self, group_id: str) -> list[str]:
        with self._lock:
            group = self._find_capture(group_id)
            self._checkpoint()
            self.project.staging = [g for g in self.project.staging if g.id != group_id]
            removed = []
            for sheet in group.sheets:
                if sheet.file:
                    removed.append(sheet.file)
                    self.staging_documents.pop(sheet.file, None)
            return removed

    def reorder_capture_groups(self, ids: list[str]) -> list[CaptureGroup]:
        with self._lock:
            current = {g.id: g for g in self.project.staging}
            if set(ids) != set(current):
                raise ValueError("ids must match existing capture groups exactly")
            self._checkpoint()
            self.project.staging = [current[i] for i in ids]
            return self.project.staging

    def duplicate_capture_group(self, group_id: str) -> CaptureGroup:
        with self._lock:
            group = self._find_capture(group_id)
            # frozen objects are shared, not copied: the duplicate's sheets get
            # their own ids/files but may point at the same document objects,
            # and both groups may reference one snapshot — neither is ever
            # mutated (the staging replace-wholesale discipline)
            docs = [
                self.staging_documents[sheet.file]
                for sheet in group.sheets
                if sheet.file and sheet.file in self.staging_documents
            ]
            pass_ids = [
                [p.pen_id for p in sheet.passes]
                for sheet in group.sheets
                if sheet.file and sheet.file in self.staging_documents
            ]
            self._checkpoint()
            return self._store_capture_group(
                name=f"{group.name} copy",
                kind=group.kind,
                fmt=dict(group.format),
                docs=docs,
                snapshot=group.snapshot,
                pass_ids=pass_ids,
                source_capture_ids=list(group.source_capture_ids),
                warnings=list(group.warnings),
            )

    def insert_staged_sheet(self, group_id: str, sheet_id: str | None = None) -> list[CanvasLayer]:
        """Destructive/editable escape hatch for staged output — the single
        path from a rendered sheet back to editable project layers.

        Appends one baked layer per staged pen pass and hides the prior visible
        layers ("replace the canvas view"). One undo step."""
        with self._lock:
            group = self._find_capture(group_id)
            sheet = self._find_sheet(group, sheet_id)
            doc = self.staged_document(group_id, sheet.id)
            self._checkpoint()
            pre_existing = list(self.project.layers)
            created: list[CanvasLayer] = []
            for i, layer_doc in enumerate(doc.layers):
                pinfo = sheet.passes[i] if i < len(sheet.passes) else StagedPass()
                layer = CanvasLayer(
                    name=f"{group.name} · {sheet.name} · {layer_doc.name or pinfo.name}",
                    source=LayerSource(type="baked"),
                    transform=Affine(),
                    pen_id=pinfo.pen_id or None,
                )
                self.project.layers.append(layer)
                self.source_geometry[layer.id] = [p.model_copy(deep=True) for p in layer_doc.paths]
                self._snapshot_pen(layer.pen_id)
                created.append(layer)
            for layer in pre_existing:
                layer.visible = False
            return created

    @staticmethod
    def _lerp_num(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    def _interpolate_layer(
        self,
        la: CanvasLayer | None,
        lb: CanvasLayer | None,
        ga: list[Path],
        gb: list[Path],
        t: float,
        warnings: list[str],
    ) -> tuple[CanvasLayer, list[Path]] | None:
        if la is None or lb is None:
            # one-sided layer: absent before the midpoint if it only exists in
            # B, absent from the midpoint on if it only exists in A — the same
            # step-at-0.5 rule as every other non-lerpable. (Returning None
            # means "no layer in this in-between"; the old code crashed on the
            # B-only-and-t<0.5 case instead of stepping.)
            warnings.append(f"{(la or lb).name} only exists on one side; stepped at midpoint")
            chosen = lb if t >= 0.5 else la
            if chosen is None:
                return None
            geo = gb if chosen is lb else ga
            return chosen.model_copy(deep=True), [p.model_copy(deep=True) for p in geo]
        if la.source.type != lb.source.type:
            chosen = lb if t >= 0.5 else la
            geo = gb if t >= 0.5 else ga
            warnings.append(f"{la.name}: source type changed; stepped at midpoint")
            return chosen.model_copy(deep=True), [p.model_copy(deep=True) for p in geo]

        data = la.model_dump()
        data["transform"] = tween.lerp_affine(la.transform, lb.transform, t).model_dump()
        data["frame_offset"] = self._lerp_num(la.frame_offset, lb.frame_offset, t)
        data["occlusion_margin_mm"] = self._lerp_num(la.occlusion_margin_mm, lb.occlusion_margin_mm, t)
        for key in ("visible", "pen_id", "occluder", "receives_occlusion", "frame_follow", "name"):
            data[key] = getattr(la, key) if t < 0.5 else getattr(lb, key)

        effects, stacks_matched = tween.blend_effect_stacks(la.effects, lb.effects, t)
        data["effects"] = [e.model_dump() for e in effects]
        if not stacks_matched and (la.effects or lb.effects):
            warnings.append(f"{la.name}: effect stack changed; stepped at midpoint")

        out_layer = CanvasLayer(**data)
        gen_params = tween.blend_generator_params(la, lb, t)
        if gen_params is not None:
            out_layer.source.params = gen_params
            out_layer.source.file = None
            try:
                src = get_source(la.source.generator)
                doc = src.generate(src.Params(**self._effective_gen_params(out_layer)))
                return out_layer, [p for lyr in doc.layers for p in lyr.paths]
            except Exception as e:
                warnings.append(f"{la.name}: generator interpolation failed ({e}); stepped at midpoint")
        if la.source.type == "tween" and lb.source.type == "tween":
            # TweenParams floats (t, windows) lerp per the unblendables rule —
            # refs/bools/curve step at 0.5 like everywhere else. Without this
            # the blended layer kept capture A's params wholesale, and since
            # re-materialisation (in the batch's temp state) overwrites the
            # geometry lerped below, a tween-t change between captures froze
            # every step at A's morph — the last step didn't reproduce B.
            try:
                pa = tween.TweenParams(**(la.source.params or {})).model_dump()
                pb = tween.TweenParams(**(lb.source.params or {})).model_dump()
                out_layer.source.params = tween.lerp_params(pa, pb, t, {})
            except Exception:
                pass  # invalid stored refs/params: keep A's source, as before
        if tween.structures_match(ga, gb):
            return out_layer, tween.lerp_paths(ga, gb, t)
        chosen_geo = gb if t >= 0.5 else ga
        warnings.append(f"{la.name}: geometry structure changed; stepped at midpoint")
        return out_layer, [p.model_copy(deep=True) for p in chosen_geo]

    def _interpolate_snapshots(
        self, a: CaptureSnapshot, b: CaptureSnapshot, t: float
    ) -> tuple[Project, dict[str, list[Path]], dict[str, str], list[str]]:
        warnings: list[str] = []
        by_b = {l.id: l for l in b.layers}
        seen: set[str] = set()
        out_layers: list[CanvasLayer] = []
        out_geo: dict[str, list[Path]] = {}
        for la in a.layers:
            lb = by_b.get(la.id)
            seen.add(la.id)
            blended = self._interpolate_layer(
                la, lb, a.source_geometry.get(la.id, []),
                b.source_geometry.get(la.id, []) if lb else [], t, warnings)
            if blended is None:
                continue  # A-only layer, t >= 0.5: stepped out
            layer, geo = blended
            out_layers.append(layer)
            out_geo[layer.id] = geo
        for lb in b.layers:
            if lb.id in seen:
                continue
            blended = self._interpolate_layer(
                None, lb, [], b.source_geometry.get(lb.id, []), t, warnings)
            if blended is None:
                continue  # B-only layer, t < 0.5: not stepped in yet
            layer, geo = blended
            out_layers.append(layer)
            out_geo[layer.id] = geo
        project = Project(
            name=a.name if t < 0.5 else b.name,
            layers=out_layers,
            guide=PaperGuide(
                x=self._lerp_num(a.guide.x, b.guide.x, t),
                y=self._lerp_num(a.guide.y, b.guide.y, t),
                width=self._lerp_num(a.guide.width, b.guide.width, t),
                height=self._lerp_num(a.guide.height, b.guide.height, t),
            ),
            view=a.view if t < 0.5 else b.view,
            pens_used={**a.pens_used, **b.pens_used},
            backend_params=a.backend_params if t < 0.5 else b.backend_params,
            plot_options=a.plot_options if t < 0.5 else b.plot_options,
        )
        return project, out_geo, dict(a.svg_files if t < 0.5 else b.svg_files), warnings

    def _documents_with_temp_state(
        self, project: Project, geo: dict[str, list[Path]], svg_files: dict[str, str],
        fmt: dict[str, Any],
    ) -> tuple[list[PathDocument], list[list[str]]]:
        old_project, old_geo, old_svg = self.project, self.source_geometry, self.svg_files
        old_shaped, old_tween, old_clip = self._shaped_cache, self._tween_cache, self._clip_cache
        old_frames, old_bbox = self._frame_lru, self._frame_bbox
        try:
            self.project = project
            self.source_geometry = geo
            self.svg_files = svg_files
            self._shaped_cache = {}
            self._tween_cache = {}
            self._clip_cache = {}
            self._frame_lru = OrderedDict()
            self._frame_bbox = {}
            return self._documents_for_format(fmt), self._pass_ids_for_format(fmt)
        finally:
            self.project = old_project
            self.source_geometry = old_geo
            self.svg_files = old_svg
            self._shaped_cache = old_shaped
            self._tween_cache = old_tween
            self._clip_cache = old_clip
            self._frame_lru = old_frames
            self._frame_bbox = old_bbox

    @staticmethod
    def _captures_compatible(a: CaptureGroup, b: CaptureGroup) -> None:
        """Raise ValueError unless A and B can interpolate: same kind, and for
        sheet captures the same essential shape (cols/rows/frames/t range).
        Presentation-only format fields — margin_mm, framing, marks — may
        differ; the batch inherits A's values with the rest of ``a.format``."""
        if a.kind != b.kind:
            raise ValueError(f"capture kinds do not match ({a.kind} vs {b.kind})")
        if a.kind == "sheet":
            for key in ("cols", "rows", "frames", "t_from", "t_to"):
                if a.format.get(key) != b.format.get(key):
                    raise ValueError(
                        f"sheet layouts do not match: {key} differs "
                        f"({a.format.get(key)} vs {b.format.get(key)})")

    def _interpolate_batch_docs(
        self, a: CaptureGroup, b: CaptureGroup, steps: int, fmt: dict[str, Any],
        name: str,
    ) -> tuple[list[PathDocument], list[list[str]], list[str]]:
        """The step loop behind :meth:`interpolate_captures` (and batch
        re-layout): render ``steps`` snapshot blends A→B through ``fmt``.
        Call under the lock; both captures must carry snapshots."""
        if a.snapshot is None or b.snapshot is None:
            raise ValueError("both captures need source snapshots")
        docs: list[PathDocument] = []
        pass_ids: list[list[str]] = []
        warnings: list[str] = []
        for i in range(steps):
            t = i / (steps - 1)
            project, geo, svg_files, ww = self._interpolate_snapshots(a.snapshot, b.snapshot, t)
            warnings.extend(ww)
            step_docs, step_pass_ids = self._documents_with_temp_state(project, geo, svg_files, fmt)
            for j, doc in enumerate(step_docs):
                doc.source = f"{name} step {i + 1}/{steps} sheet {j + 1}"
                docs.append(doc)
                pass_ids.append(step_pass_ids[j] if j < len(step_pass_ids) else [])
        return docs, pass_ids, warnings

    def interpolate_captures(
        self, a_id: str, b_id: str, steps: int, name: str | None = None
    ) -> CaptureGroup:
        if not (2 <= steps <= 60):
            raise ValueError("steps must be 2..60")
        with self._lock:
            a = self._find_capture(a_id)
            b = self._find_capture(b_id)
            self._captures_compatible(a, b)
            label = name or f"{a.name} ⇄ {b.name} · {steps} steps"
            docs, pass_ids, warnings = self._interpolate_batch_docs(
                a, b, steps, a.format, name or "interpolated batch")
            self._checkpoint()
            fmt = {**a.format, "kind": "batch", "source_kind": a.format.get("kind"), "variants": steps}
            return self._store_capture_group(
                name=label,
                kind="batch",
                fmt=fmt,
                docs=docs,
                snapshot=None,
                pass_ids=pass_ids,
                source_capture_ids=[a.id, b.id],
                warnings=sorted(set(warnings)),
            )

    def _snapshot_state(
        self, snap: CaptureSnapshot
    ) -> tuple[Project, dict[str, list[Path]], dict[str, str]]:
        """Mirror :meth:`_capture_snapshot` back into a transient
        project/geometry/svg triple for :meth:`_documents_with_temp_state` —
        the single-snapshot analogue of :meth:`_interpolate_snapshots`."""
        project = Project(
            name=snap.name,
            layers=[l.model_copy(deep=True) for l in snap.layers],
            guide=snap.guide.model_copy(deep=True),
            view=snap.view,
            pens_used={k: v.model_copy(deep=True) for k, v in snap.pens_used.items()},
            backend_params={k: dict(v) for k, v in snap.backend_params.items()},
            plot_options=snap.plot_options.model_copy(deep=True),
        )
        geo = {
            lid: [p.model_copy(deep=True) for p in paths]
            for lid, paths in snap.source_geometry.items()
        }
        return project, geo, dict(snap.svg_files)

    def relayout_capture(
        self, group_id: str, cols: int, rows: int,
        margin_mm: float | None = None, framing: str | None = None,
        marks: bool | None = None,
    ) -> CaptureGroup:
        """Re-render a captured animation at a new grid — a NEW group; the
        original is untouched. Snapshot-bearing sheet captures re-render from
        their stored state; batches re-run the interpolation from their source
        captures (which must still exist with snapshots). Grids only: frame and
        plot captures have no cols/rows to change."""
        if not (1 <= cols <= 12 and 1 <= rows <= 12):
            raise ValueError("cols and rows must each be 1..12")
        if margin_mm is not None and not (0.0 <= margin_mm <= 30.0):
            raise ValueError("margin_mm must be 0..30")
        if framing is not None and framing not in ("center", "fixed"):
            raise ValueError("framing must be center or fixed")
        with self._lock:
            group = self._find_capture(group_id)
            source_kind = group.format.get("source_kind") if group.kind == "batch" else group.kind
            if source_kind != "sheet":
                raise ValueError(
                    f"re-layout applies to grid-sheet captures only, not {group.kind!r}")
            # new sheet-format: keep the timeline shape, swap the grid
            fmt = {k: v for k, v in group.format.items()
                   if k not in ("kind", "source_kind", "variants")}
            fmt["kind"] = "sheet"
            fmt["cols"], fmt["rows"] = cols, rows
            if margin_mm is not None:
                fmt["margin_mm"] = margin_mm
            if framing is not None:
                fmt["framing"] = framing
            if marks is not None:
                fmt["marks"] = marks
            fmt["pages"] = self.sheet_pages(int(fmt["frames"]), cols, rows)

            if group.kind == "batch":
                sources = [
                    next((g for g in self.project.staging if g.id == sid), None)
                    for sid in group.source_capture_ids
                ]
                if len(sources) != 2 or any(s is None or s.snapshot is None for s in sources):
                    raise RuntimeError("source captures no longer available")
                a, b = sources
                steps = int(group.format.get("variants", 2))
                name = f"{group.name} · re-laid {cols}×{rows}"
                docs, pass_ids, warnings = self._interpolate_batch_docs(a, b, steps, fmt, name)
                self._checkpoint()
                return self._store_capture_group(
                    name=name,
                    kind="batch",
                    fmt={**fmt, "kind": "batch", "source_kind": "sheet", "variants": steps},
                    docs=docs,
                    snapshot=None,
                    pass_ids=pass_ids,
                    source_capture_ids=list(group.source_capture_ids),
                    warnings=sorted(set(warnings)),
                )

            if group.snapshot is None:
                raise RuntimeError("capture has no source snapshot to re-render from")
            project, geo, svg_files = self._snapshot_state(group.snapshot)
            docs, pass_ids = self._documents_with_temp_state(project, geo, svg_files, fmt)
            if not any(self._doc_has_geometry(doc) for doc in docs):
                raise RuntimeError("nothing to re-layout (no geometry at the new grid)")
            self._checkpoint()
            return self._store_capture_group(
                name=f"{group.name} · re-laid {cols}×{rows}",
                kind="sheet",
                fmt=fmt,
                docs=docs,
                snapshot=group.snapshot,  # shared: snapshots are frozen
                pass_ids=pass_ids,
            )

    def duplicate_layer(self, layer_id: str) -> CanvasLayer:
        """Copy a layer (new id) directly above the original — same source,
        transform, effects, pen. Geometry list is shared by reference; it is
        only ever replaced wholesale (regen/consolidate), never mutated."""
        with self._lock:
            layer = self.project.layer(layer_id)
            self._checkpoint()
            data = layer.model_dump()
            del data["id"]  # CanvasLayer mints a fresh one
            data["name"] = f"{layer.name} copy"
            copy = CanvasLayer(**data)
            copy.source.file = None  # snapshot belongs to the original; rewritten on save
            idx = self.project.layers.index(layer)
            self.project.layers.insert(idx + 1, copy)
            self.source_geometry[copy.id] = self.source_geometry.get(layer_id, [])
            return copy

    def add_lineart_stack(
        self, image: str, flavor: str, rotate: int = 0, width: float = 150.0
    ) -> list[CanvasLayer]:
        """One-click "Lineart stack": run ``LINEART_STACK_PRESETS[flavor]``
        top to bottom, creating one ordinary generator layer per preset
        entry — "faithful" (4 tonal-band hatch layers + edges) or "artistic"
        (3 layers, looser/dashed). Inlines ``add_generated_layer``'s logic
        per layer so the whole stack is ONE undo step; every layer carries
        real ``source=LayerSource(type="generator", ...)`` provenance, so
        regenerate/tween/effects all work on it exactly like a hand-built
        layer."""
        if flavor not in LINEART_STACK_PRESETS:
            raise ValueError(f"unknown lineart stack flavor: {flavor!r}")
        # generate everything BEFORE mutating (add_generated_layer's semantics —
        # it too generates outside the lock): a failure mid-stack must not
        # leave a partial stack in the project
        generated: list[tuple[dict[str, Any], dict[str, Any], list[Path], Affine]] = []
        for spec in LINEART_STACK_PRESETS[flavor]:
            params = {"image": image, "rotate": rotate, "width": width, **spec["params"]}
            src = get_source(spec["generator"])
            doc = src.generate(src.Params(**params))
            generated.append((
                spec, params, [p for lyr in doc.layers for p in lyr.paths],
                self._centering_transform(spec["generator"], params, doc),
            ))
        with self._lock:
            self._checkpoint()
            created: list[CanvasLayer] = []
            for spec, params, paths, band_transform in generated:
                layer = CanvasLayer(
                    name=spec["name"],
                    source=LayerSource(type="generator", generator=spec["generator"], params=params),
                    transform=band_transform,
                    frame_follow=self._sequence_driven(spec["generator"], params),
                )
                self.project.layers.append(layer)
                self.source_geometry[layer.id] = paths
                created.append(layer)
            return created

    def animate_layer(self, layer_id: str) -> CanvasLayer:
        """One-click "Animate this layer": turn a layer into a keyframed
        animation without the manual duplicate + create-tween dance.

        Splits the layer into keyframes A (the original, renamed/hidden) and
        B (a fresh duplicate, hidden), then inserts a tween above them set to
        follow the master timeline. The displayed stack reads tween → A → B;
        A and B start identical, so the tween looks exactly like the original
        the moment this returns — edit either keyframe and scrub to animate.

        Inlines ``duplicate_layer`` and ``create_tween_layer``'s logic rather
        than calling them (each checkpoints itself) so the whole operation is
        ONE undo step."""
        with self._lock:
            layer = self.project.layer(layer_id)
            if layer.source.type == "tween":
                raise RuntimeError("layer is already an interpolation layer — "
                                    "animate one of its keyframes instead")
            self._checkpoint()
            original_name = layer.name

            # -- B: duplicate_layer's logic, inlined (no nested checkpoint) --
            data = layer.model_dump()
            del data["id"]  # CanvasLayer mints a fresh one
            data["name"] = f"{original_name} ▸ B"
            data["visible"] = False
            b = CanvasLayer(**data)
            b.source.file = None  # snapshot belongs to the original; rewritten on save
            idx = self.project.layers.index(layer)
            self.project.layers.insert(idx, b)
            self.source_geometry[b.id] = self.source_geometry.get(layer_id, [])

            # Auto-frame: a generator driven by a frame sequence animates its
            # ``frame`` axis by default — B jumps to the last frame while A holds
            # the current one, so scrubbing plays the clip. Non-sequence layers
            # are untouched (A == B, as before).
            self._auto_frame_keyframe_b(layer, b)

            # -- A: rename + hide the original in place ----------------------
            layer.name = f"{original_name} ▸ A"
            layer.visible = False

            # -- tween: create_tween_layer's logic, inlined ------------------
            tween_layer = CanvasLayer(
                name=original_name,
                source=LayerSource(
                    type="tween",
                    params=tween.TweenParams(a=layer.id, b=b.id, follow_master=True).model_dump(),
                ),
                pen_id=layer.pen_id,
                visible=True,
            )
            idx_a = self.project.layers.index(layer)
            self.project.layers.insert(idx_a + 1, tween_layer)
            self.source_geometry[tween_layer.id] = []  # materialised on next resolve
            return tween_layer

    @staticmethod
    def _auto_frame_keyframe_b(source_layer: CanvasLayer, b: CanvasLayer) -> None:
        """If ``source_layer`` is a generator with a ``frame`` param bound to a
        frame-sequence asset, set B's ``frame`` to the last frame (1.0). A keeps
        its current value so t=0 reproduces exactly what the user saw."""
        from .assets import asset_store

        src = source_layer.source
        if src.type != "generator" or not src.generator:
            return
        params = src.params or {}
        if "frame" not in get_source(src.generator).Params.model_fields:
            return
        image = params.get("image")
        if isinstance(image, str) and asset_store.is_sequence(image):
            b.source.params = {**params, "frame": 1.0}

    def consolidate_effects(self, layer_id: str) -> CanvasLayer:
        """Bake transform + effect stack into the source geometry.

        The resolved output is unchanged (occlusion runs downstream as
        before): the shaped paper-space paths become the new source, the
        transform resets to identity and the stack empties. Generator
        provenance survives, so "regenerate" undoes the bake explicitly.
        """
        with self._lock:
            layer = self.project.layer(layer_id)
            self._checkpoint()
            self._materialize_tweens()  # a stale tween must bake its CURRENT look
            shaped = compose.shape_layer(layer, self.source_geometry.get(layer_id, []))
            self.source_geometry[layer_id] = shaped
            layer.transform = Affine()
            layer.effects = []
            layer.source.type = "baked"
            layer.source.file = None  # snapshot is stale; rewritten on save
            self._shaped_cache.pop(layer_id, None)
            return layer

    # -- resolve pipeline (the single source of truth) -------------------------

    def resolved(self, master_t: float | None = None) -> dict[str, list[Path]]:
        """Resolve the project through the single geometry path. ``master_t``
        (0..1, or None to disable) is the ephemeral master-timeline value.

        It drives two things, live and WITHOUT mutating stored state (no
        checkpoint, ``source_geometry`` for user layers byte-identical):

        * **Clip-follow** — every visible ``frame_follow`` generator backed by
          a frame sequence has its clip advanced (frame += master_t). Its
          advanced geometry is an EPHEMERAL overlay layered over
          ``source_geometry`` in a throwaway ``geo`` dict; the stored list stays
          untouched.
        * **Tween morph** — a tween whose ``follow_master`` is set moves its
          ``t`` (single) through its window; a swept tween's stamp positions are
          time-invariant, but the master value still advances each stamp's clip
          content via its endpoints' ``frame_follow``.

        ``master_t=None`` is byte-identical to no scrub at all."""
        with self._lock:
            overrides = self._clip_overrides(master_t)
            # ephemeral overlay: the follow generators' advanced geometry rides
            # over the stored source geometry for THIS resolve only. Tweens read
            # their endpoints from it and write their own results back into it
            # (below), so resolve_project sees a single consistent geometry map.
            geo = {**self.source_geometry, **overrides}
            self._materialize_tweens(master_t, geo)
            return compose.resolve_project(
                self.project, geo, self.pens(), self._shaped_cache
            )

    def _clip_overrides(self, master_t: float | None) -> dict[str, list[Path]]:
        """Ephemeral clip-follow overlay: ``{layer_id: advanced paths}`` for
        every VISIBLE ``frame_follow`` generator whose ``image`` param is a
        frame sequence, with its clip advanced by ``master_t``. Empty when
        ``master_t is None`` (byte-identical to no scrub).

        The advanced geometry NEVER touches ``source_geometry`` — it lives only
        in the returned dict, so a scrub leaves the user's stored geometry (and
        the undo history) intact. Cached on content (params + offset + master_t)
        so a cache hit returns the SAME list object, letting compose's
        ``id(src)``-keyed shaped cache re-hit. A generation failure inside an
        override is swallowed — the layer falls back to its base geometry so a
        stored project always resolves."""
        if master_t is None:
            return {}
        import json

        from .assets import asset_store

        overrides: dict[str, list[Path]] = {}
        for layer in self.project.layers:
            if not layer.visible or not layer.frame_follow:
                continue
            src = layer.source
            if src.type != "generator" or not src.generator:
                continue
            gen = get_source(src.generator)
            if "frame" not in gen.Params.model_fields:
                continue
            image = (src.params or {}).get("image")
            if not (isinstance(image, str) and asset_store.is_sequence(image)):
                continue
            key = json.dumps(
                {"p": src.params, "off": layer.frame_offset, "mt": master_t},
                sort_keys=True)
            hit = self._clip_cache.get(layer.id)
            if hit is not None and hit[0] == key:
                overrides[layer.id] = hit[1]  # same object -> shaped cache re-hits
                continue
            try:
                doc = gen.generate(gen.Params(**self._effective_gen_params(layer, master_t)))
                paths = [p for lyr in doc.layers for p in lyr.paths]
            except Exception:
                continue  # fall back to stored base geometry for this layer
            self._clip_cache[layer.id] = (key, paths)
            overrides[layer.id] = paths
        return overrides

    def _materialize_tweens(
        self, master_t: float | None = None,
        geo: dict[str, list[Path]] | None = None,
    ) -> None:
        """Refresh every tween layer's source geometry from its referenced
        layers (they are live references). Cached on a content key of both
        definitions + the tween params (+ the master-timeline values), so an
        untouched tween costs one hash. Called under the lock, only from
        resolved() — the single resolve path stays single.

        ``geo`` (when given) is the ephemeral overlay dict resolved() reads
        from: endpoints are read out of it (so a tween over follow generators
        lerps their advanced geometry), and each tween's materialised result is
        written back into it AS WELL as into ``source_geometry`` (tween geometry
        is derived state — writing it under a scrub is fine; the user's source
        layers are the ones that must stay byte-identical).

        ``master_t`` (when not None) drives tweens two ways, both ephemeral (the
        stored ``layer.source.params`` are never mutated): a ``follow_master``
        tween's local ``t`` is mapped through its window and time curve into
        ``override_t``; and the RAW clamped master value goes to ``materialize``
        unconditionally so any endpoint's ``frame_follow`` advances the clip.
        Both are folded into the cache key so scrubbing invalidates correctly."""
        import json

        read_geo = geo if geo is not None else self.source_geometry
        clamped_master = None if master_t is None else min(1.0, max(0.0, master_t))
        # Dependency order (inner tweens first) so a nested tween reads a fresh
        # inner result — for its geometry AND its cache key. See
        # _tween_dependency_order.
        for layer in self._tween_dependency_order():
            params = layer.source.params or {}
            override_t: float | None = None
            if master_t is not None and params.get("follow_master"):
                mt = clamped_master
                # map the master timeline into this tween's local t through the
                # window: hold A before ``window_from``, animate inside, hold B
                # after ``window_to``.
                wf = params.get("window_from", 0.0)
                wt = params.get("window_to", 1.0)
                if wt > wf:
                    local = min(1.0, max(0.0, (mt - wf) / (wt - wf)))
                else:  # degenerate window: step A -> B at the collapsed point
                    local = 0.0 if mt < wf else 1.0
                override_t = tween.map_time_curve(local, params.get("time_curve", "linear"))
            refs = []
            for rid in params.get("a"), params.get("b"):
                try:
                    ref = self.project.layer(rid)
                    refs.append({
                        "src": ref.source.model_dump(),
                        "tf": ref.transform.model_dump(),
                        "fx": [s.model_dump() for s in ref.effects],
                        "geo": id(read_geo.get(ref.id)),
                        "fo": ref.frame_offset,
                        "ff": ref.frame_follow,
                    })
                except KeyError:
                    refs.append(None)
            key = json.dumps(
                {"refs": refs, "p": params, "mt": override_t, "master": clamped_master},
                sort_keys=True)
            hit = self._tween_cache.get(layer.id)
            if hit is not None and hit[0] == key:
                if geo is not None:
                    geo[layer.id] = hit[1]
                continue
            paths = tween.materialize(
                layer, self.project, read_geo, override_t, clamped_master)
            self._tween_cache[layer.id] = (key, paths)
            self.source_geometry[layer.id] = paths  # replaced wholesale, never mutated
            if geo is not None:
                geo[layer.id] = paths

    def resolved_document(self, target: str = "all",
                          master_t: float | None = None) -> PathDocument:
        """Un-compensated resolved geometry — what the preview renders.
        ``master_t`` scrubs the master timeline (see :meth:`resolved`)."""
        return compose.flatten_to_document(
            self.project, self.resolved(master_t), self.pens(), target)

    def _pen_offsets(self) -> dict[str, tuple[float, float]]:
        cal = settings_store.settings.holder_calibration
        if cal.is_zero:
            return {}
        pens = self.pens()
        out: dict[str, tuple[float, float]] = {}
        for layer in self.project.layers:
            pen = pens.get(layer.pen_id or "")
            if pen:
                out[layer.id] = cal.offset_for(pen.barrel_diameter_mm)
        return out

    def plot_document(self, target: str = "all",
                      master_t: float | None = None) -> PathDocument:
        """What actually gets plotted: resolved geometry, pen-offset
        compensated, then plot-pass optimised. ``master_t`` scrubs the master
        timeline (see :meth:`resolved`) — the hook for frame-by-frame render."""
        doc = compose.flatten_to_document(
            self.project, self.resolved(master_t), self.pens(), target, self._pen_offsets()
        )
        return self._optimize(doc)

    def _crop_rect(self) -> tuple[float, float, float, float] | None:
        """The active crop rectangle (mode -> rect, inset by ``crop_margin_mm``
        on all four sides), or None when crop is off or the margin collapses
        the rect to non-positive width/height. Never raises."""
        opts = self.project.plot_options
        if opts.crop == "off":
            return None
        if opts.crop == "guide":
            g = self.project.guide
            x, y, w, h = g.x, g.y, g.width, g.height
        elif opts.crop == "bed":
            x, y, w, h = 0.0, 0.0, compose.BED_WIDTH, compose.BED_HEIGHT
        else:  # "custom"
            x, y, w, h = opts.crop_x, opts.crop_y, opts.crop_w, opts.crop_h
        m = opts.crop_margin_mm
        x, y = x + m, y + m
        w, h = w - 2 * m, h - 2 * m
        if w <= 0 or h <= 0:
            return None
        return (x, y, w, h)

    def _optimize(self, doc: PathDocument) -> PathDocument:
        opts = self.project.plot_options
        crop_rect = self._crop_rect()
        cmds: list[str] = []
        if crop_rect is not None:
            x, y, w, h = crop_rect
            cmds.append(f"crop {x}mm {y}mm {w}mm {h}mm")
        if opts.merge:
            cmds.append(f"linemerge --tolerance {opts.merge_tolerance_mm}mm")
        if opts.reloop:
            cmds.append("reloop")
        if opts.sort:
            cmds.append("linesort")
        if opts.simplify:
            cmds.append(f"linesimplify --tolerance {opts.simplify_tolerance_mm}mm")
        if not cmds or not doc.layers:
            return doc
        import vpype_cli

        vdoc = vpype_cli.execute(" ".join(cmds), document=doc_to_vpype(doc))
        out = doc_from_vpype(vdoc, source=doc.source)
        out.width, out.height = doc.width, doc.height
        return out

    def cropped(self, doc: PathDocument) -> PathDocument:
        """Apply ONLY the active crop to ``doc`` via the same vpype round-trip
        ``_optimize`` uses — for exports (SVG download, animation frames) that
        must respect the crop without applying the other plot-pass options.
        No-op (returns ``doc`` unchanged) when crop is off or there's nothing
        to crop."""
        crop_rect = self._crop_rect()
        if crop_rect is None or not doc.layers:
            return doc
        import vpype_cli

        x, y, w, h = crop_rect
        vdoc = vpype_cli.execute(f"crop {x}mm {y}mm {w}mm {h}mm", document=doc_to_vpype(doc))
        out = doc_from_vpype(vdoc, source=doc.source)
        out.width, out.height = doc.width, doc.height
        return out

    # -- backend params (stored in the project, per spec) -----------------------

    def params_for(self, backend_id: str):
        backend = manager.backends[backend_id]
        machine = settings_store.settings.backend_params.get(backend_id, {})
        stored = self.project.backend_params.get(backend_id, {})
        return backend.Params(**{**machine, **stored})

    def set_params(self, backend_id: str, values: dict[str, Any]) -> dict[str, Any]:
        backend = manager.backends[backend_id]
        validated = backend.Params(**values)
        dumped = validated.model_dump()
        self.project.backend_params[backend_id] = dumped
        # Mirror into the machine-level store so the values survive a server
        # restart and seed fresh projects (project-stored params still win).
        machine = dict(settings_store.settings.backend_params)
        machine[backend_id] = dumped
        settings_store.update({"backend_params": machine})
        return dumped

    @staticmethod
    def _apply_pen_overrides(params, pen: Pen | None):
        """Fold a pen's height overrides (pen_pos_down/up, when set) into the
        backend params. Pure — returns ``params`` unchanged when there is no
        pen or nothing to override."""
        if not pen:
            return params
        overrides = {}
        if pen.pen_pos_down is not None and "pen_pos_down" in type(params).model_fields:
            overrides["pen_pos_down"] = pen.pen_pos_down
        if pen.pen_pos_up is not None and "pen_pos_up" in type(params).model_fields:
            overrides["pen_pos_up"] = pen.pen_pos_up
        return params.model_copy(update=overrides) if overrides else params

    def effective_params(self, backend_id: str, target: str = "all",
                         pen: Pen | None = None):
        """Backend params with a pen's height overrides applied. An explicit
        ``pen`` wins (the sheet plot pass hands its pass pen directly);
        otherwise, when a single layer is targeted (the manual multi-pen unit
        of work) its pen's overrides apply."""
        params = self.params_for(backend_id)
        if pen is not None:
            return self._apply_pen_overrides(params, pen)
        if target != "all":
            try:
                layer = self.project.layer(target)
            except KeyError:
                return params
            return self._apply_pen_overrides(params, self.pens().get(layer.pen_id or ""))
        return params


session = Session()
