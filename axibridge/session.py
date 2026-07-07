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
from collections import deque
from typing import Any

from . import compose, tween
from .compose import Affine, CanvasLayer, EffectStep, LayerSource, PlotOptions, Project
from .machine import manager
from .model import Layer, Path, PathDocument
from .registry import get_source
from .stores import Pen, pen_library, settings_store
from .svg_io import doc_from_svg, doc_from_vpype, doc_to_vpype


class Session:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.project = Project()
        self.project_dir: str | None = None
        #: layer id -> source paths in the layer's LOCAL frame (pre-transform)
        self.source_geometry: dict[str, list[Path]] = {}
        #: uploaded-SVG raw text by project-relative filename (written on save)
        self.svg_files: dict[str, str] = {}
        self._shaped_cache: dict[str, tuple[str, list[Path]]] = {}
        #: undo snapshots, newest last. Paths/lists are never mutated in place
        #: (module purity contract), so sharing references is safe — only the
        #: project model needs a deep copy.
        self._history: deque[tuple[Project, dict[str, list[Path]], dict[str, str]]] = deque(maxlen=8)
        #: tween layer id -> (content key, materialised paths)
        self._tween_cache: dict[str, tuple[str, list[Path]]] = {}
        #: frame-follow generator layer id -> (content key, clip-advanced paths).
        #: An EPHEMERAL scrub overlay: computed only when resolving with a
        #: master_t, never written into ``source_geometry`` (the user's stored
        #: geometry stays byte-identical under a scrub). Keyed on content, so a
        #: cache hit hands back the SAME list object and the shaped cache re-hits.
        self._clip_cache: dict[str, tuple[str, list[Path]]] = {}

    # -- undo -----------------------------------------------------------------

    def _checkpoint(self) -> None:
        self._history.append(
            (self.project.model_copy(deep=True), dict(self.source_geometry), dict(self.svg_files))
        )

    def clear_history(self) -> None:
        """Project switch: snapshots of another project must not restore here."""
        with self._lock:
            self._history.clear()

    def undo(self) -> bool:
        with self._lock:
            if not self._history:
                return False
            self.project, self.source_geometry, self.svg_files = self._history.pop()
            self._shaped_cache.clear()
            return True

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

    def add_generated_layer(self, generator_id: str, params: dict[str, Any]) -> CanvasLayer:
        src = get_source(generator_id)
        doc = src.generate(src.Params(**params))
        paths = [p for layer in doc.layers for p in layer.paths]
        layer = CanvasLayer(
            name=src.label,
            source=LayerSource(type="generator", generator=generator_id, params=params),
        )
        with self._lock:
            self._checkpoint()
            self.project.layers.append(layer)
            self.source_geometry[layer.id] = paths
        return layer

    def regenerate_layer(self, layer_id: str, params: dict[str, Any] | None = None) -> CanvasLayer:
        with self._lock:
            layer = self.project.layer(layer_id)
            if layer.source.type not in ("generator", "baked") or not layer.source.generator:
                raise RuntimeError("layer was not generated; nothing to regenerate")
            self._checkpoint()
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
        self, svg_text: str, filename: str, quantization_mm: float
    ) -> list[CanvasLayer]:
        """An uploaded SVG contributes its layers as compositor layers."""
        doc = doc_from_svg(svg_text, quantization_mm, source=filename)
        if not doc.layers:
            raise RuntimeError("no plottable geometry found in the SVG")
        relname = f"sources/{filename}"
        created: list[CanvasLayer] = []
        with self._lock:
            self._checkpoint()
            self.svg_files[relname] = svg_text
            for svg_layer in doc.layers:
                layer = CanvasLayer(
                    name=svg_layer.name,
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
        allowed = {"name", "visible", "transform", "effects", "pen_id",
                   "occluder", "receives_occlusion", "occlusion_margin_mm",
                   "frame_offset", "frame_follow"}
        with self._lock:
            layer = self.project.layer(layer_id)
            self._checkpoint()
            data = layer.model_dump()
            for k, v in patch.items():
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

    @staticmethod
    def _tween_refs(layer: CanvasLayer) -> tuple[Any, Any]:
        p = layer.source.params or {}
        return p.get("a"), p.get("b")

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
                la, lb, self.source_geometry.get(a_id, []), self.source_geometry.get(b_id, [])
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
            idx = max(self.project.layers.index(la), self.project.layers.index(lb))
            self.project.layers.insert(idx + 1, layer)
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

    def _grid_place(
        self, ts: list[float], cols: int, rows: int, margin_mm: float,
        master_scale_ts: list[float] | None = None,
    ) -> list[dict[str, list[Path]]]:
        """Lay each master-timeline sample ``ts[i]`` into cell i of a cols×rows
        grid on the paper guide, keeping PER-LAYER geometry (not flattened) so
        callers can group by pen. Placement math is the contact-sheet's: one
        SHARED scale across every frame — derived from the union bounding box
        over ``master_scale_ts`` (defaults to ``ts``); the sheet callers pass
        the FULL animation's ts so frame k is the same size on every page — and
        each frame centred in its own cell by its combined (all-visible-layers)
        bbox. Cells are row-major (left-to-right, top-to-bottom). Geometry is
        the VISIBLE, resolved (post-occlusion) paths, so a cell is exactly what
        the canvas/plotter show at that t.

        Returns one ``{layer_id: placed_paths}`` dict per ``ts`` sample, in
        project z-order, holding only visible layers with non-empty geometry.
        Read-only: no checkpoint, no user source_geometry writes — everything
        flows through :meth:`resolved` (which does refresh derived tween
        geometry, as every resolve does). Call under ``self._lock``."""
        def visible_geo(t: float) -> dict[str, list[Path]]:
            # resolved() re-materialises tweens as a side effect (the single
            # resolve path); z-order preserved so flattening callers match.
            resolved = self.resolved(master_t=t)
            return {layer.id: resolved[layer.id]
                    for layer in self.project.layers
                    if layer.visible and resolved.get(layer.id)}

        place_frames = [visible_geo(t) for t in ts]
        scale_frames = (place_frames if master_scale_ts is None
                        else [visible_geo(t) for t in master_scale_ts])

        all_xs = [x for f in scale_frames for paths in f.values() for p in paths for x, _ in p.points]
        all_ys = [y for f in scale_frames for paths in f.values() for p in paths for _, y in p.points]
        if not all_xs:
            raise RuntimeError("nothing to place (no visible geometry across the frame range)")
        bw = max(max(all_xs) - min(all_xs), 1e-6)
        bh = max(max(all_ys) - min(all_ys), 1e-6)

        guide = self.project.guide
        sheet_x = guide.x if guide else 0.0
        sheet_y = guide.y if guide else 0.0
        sheet_w = guide.width if guide else compose.BED_WIDTH
        sheet_h = guide.height if guide else compose.BED_HEIGHT
        cell_w = sheet_w / cols - 2 * margin_mm
        cell_h = sheet_h / rows - 2 * margin_mm
        if cell_w <= 0 or cell_h <= 0:
            raise RuntimeError("margin too large for this grid on the current paper guide")

        scale = min(cell_w / bw, cell_h / bh)  # shared: no per-frame size jitter

        placed_frames: list[dict[str, list[Path]]] = []
        for i, frame in enumerate(place_frames):
            row, col = divmod(i, cols)  # row-major, left-to-right, top-to-bottom
            cx = sheet_x + (col + 0.5) * (sheet_w / cols)
            cy = sheet_y + (row + 0.5) * (sheet_h / rows)
            xs = [x for paths in frame.values() for p in paths for x, _ in p.points]
            ys = [y for paths in frame.values() for p in paths for _, y in p.points]
            fcx = (min(xs) + max(xs)) / 2 if xs else 0.0
            fcy = (min(ys) + max(ys)) / 2 if ys else 0.0
            aff = Affine(a=scale, b=0.0, c=0.0, d=scale,
                         e=cx - scale * fcx, f=cy - scale * fcy)
            placed_frames.append(
                {lid: compose.transform_paths(paths, aff) for lid, paths in frame.items()}
            )
        return placed_frames

    def bake_contact_sheet(
        self, cols: int, rows: int, frames: int, margin_mm: float,
        t_from: float = 0.0, t_to: float = 1.0,
    ) -> list[CanvasLayer]:
        """Bake ``frames`` samples of the master timeline into a cols×rows
        contact sheet: one baked layer per frame. A single shared scale
        (derived from the union bounding box across ALL frames) keeps every
        frame the same size — no per-frame jitter — while each frame is
        individually centred in its own grid cell (its own bbox centre, same
        scale). Previously-visible layers are hidden, like ``explode_tween``
        hides its source tween — the new baked layers become the sheet's
        visible content. Geometry is the VISIBLE, resolved (post-occlusion)
        paths, so what gets baked is exactly what the canvas/plotter show.
        One undo step.

        The DESTRUCTIVE/editable variant: it mutates the project. Its transient
        cousin is :meth:`sheet_document` (plot-time assembly, no mutation); both
        share :meth:`_grid_place`."""
        if not (1 <= cols <= 12 and 1 <= rows <= 12):
            raise ValueError("cols and rows must each be 1..12")
        if not (2 <= frames <= cols * rows):
            raise ValueError(f"frames must be 2..{cols * rows} for a {cols}x{rows} grid")
        if not (0.0 <= margin_mm <= 30.0):
            raise ValueError("margin_mm must be 0..30")
        if not (0.0 <= t_from <= 1.0 and 0.0 <= t_to <= 1.0):
            raise ValueError("t_from/t_to must be 0..1")

        with self._lock:
            self._checkpoint()
            pre_existing = list(self.project.layers)

            ts = [t_from] if frames <= 1 else [
                t_from + (t_to - t_from) * i / (frames - 1) for i in range(frames)
            ]
            placed = self._grid_place(ts, cols, rows, margin_mm)

            created: list[CanvasLayer] = []
            for i, (t, frame) in enumerate(zip(ts, placed)):
                flat = [p for paths in frame.values() for p in paths]  # z-order
                layer = CanvasLayer(
                    name=f"frame {i:02d} · t={t:.2f}",
                    source=LayerSource(type="baked"),
                    transform=Affine(),
                )
                self.project.layers.append(layer)  # appended = top of z-order
                self.source_geometry[layer.id] = flat
                created.append(layer)

            for layer in pre_existing:
                layer.visible = False

            return created

    def sheet_document(
        self, cols: int, rows: int, frames: int,
        t_from: float, t_to: float, margin_mm: float, page: int,
        pen_id: str | None = None,
    ) -> PathDocument:
        """One physical sheet of the flip-book, assembled at plot time — NO
        project mutation, no checkpoint (contrast :meth:`bake_contact_sheet`).

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
                cols, rows, frames, t_from, t_to, margin_mm, page, pen_id)
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
    ) -> tuple[list[tuple[str, list[Path]]], int]:
        """The by-pen assembly behind :meth:`sheet_document` and
        :meth:`sheet_passes`: places the page's frames, groups their geometry by
        pen (``""`` = no pen), applies the physical nib offset AFTER placement,
        and orders the groups by project z-order of each pen's first layer.
        Returns ``([(pen_id, paths), …], n_pages)`` with empty groups dropped.
        ``pen_id`` (not None) filters to that single group. Call under the lock."""
        per_page = cols * rows
        n_pages = (frames + per_page - 1) // per_page
        if not (0 <= page < n_pages):
            raise IndexError(f"page {page} out of range (0..{n_pages - 1})")

        all_ts = [t_from] if frames <= 1 else [
            t_from + (t_to - t_from) * i / (frames - 1) for i in range(frames)
        ]
        chunk = all_ts[page * per_page: (page + 1) * per_page]
        placed = self._grid_place(chunk, cols, rows, margin_mm, master_scale_ts=all_ts)

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
                if pen_id is not None and pid != pen_id:
                    continue
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

    def animate_layer(self, layer_id: str) -> CanvasLayer:
        """One-click "Animate this layer": turn a layer into a keyframed
        animation without the manual duplicate + create-tween dance.

        Splits the layer into keyframes A (the original, renamed/hidden) and
        B (a fresh duplicate, hidden), then inserts a tween above them set to
        follow the master timeline. A and B start identical, so the tween
        looks exactly like the original the moment this returns — edit
        either keyframe and scrub to animate.

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
            self.project.layers.insert(idx + 1, b)
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
            idx_b = self.project.layers.index(b)
            self.project.layers.insert(idx_b + 1, tween_layer)
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
        tween's local ``t`` is mapped through its window into ``override_t``;
        and the RAW clamped master value goes to ``materialize`` unconditionally
        so any endpoint's ``frame_follow`` advances the clip. Both are folded
        into the cache key so scrubbing invalidates correctly."""
        import json

        read_geo = geo if geo is not None else self.source_geometry
        clamped_master = None if master_t is None else min(1.0, max(0.0, master_t))
        for layer in self.project.layers:
            if layer.source.type != "tween":
                continue
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
                override_t = local
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
