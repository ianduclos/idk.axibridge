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

from . import compose
from .compose import Affine, CanvasLayer, EffectStep, LayerSource, PlotOptions, Project
from .machine import manager
from .model import Path, PathDocument
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
            doc = src.generate(src.Params(**(layer.source.params or {})))
            self.source_geometry[layer.id] = [p for lyr in doc.layers for p in lyr.paths]
            layer.source.type = "generator"  # a baked layer returns to live output
            layer.source.file = None  # snapshot is stale; rewritten on save
            self._shaped_cache.pop(layer_id, None)
            return layer

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
                   "occluder", "receives_occlusion", "occlusion_margin_mm"}
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
            return updated

    def delete_layer(self, layer_id: str) -> None:
        self.delete_layers([layer_id])

    def delete_layers(self, layer_ids: list[str]) -> None:
        """Bulk delete = ONE history entry, so one undo restores the lot."""
        with self._lock:
            layers = [self.project.layer(i) for i in layer_ids]  # all-or-nothing
            self._checkpoint()
            for layer in layers:
                self.project.layers.remove(layer)
                self.source_geometry.pop(layer.id, None)
                self._shaped_cache.pop(layer.id, None)

    def reorder_layers(self, ordered_ids: list[str]) -> None:
        with self._lock:
            if sorted(ordered_ids) != sorted(l.id for l in self.project.layers):
                raise ValueError("order must contain exactly the current layer ids")
            self._checkpoint()
            by_id = {l.id: l for l in self.project.layers}
            self.project.layers = [by_id[i] for i in ordered_ids]

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
            shaped = compose.shape_layer(layer, self.source_geometry.get(layer_id, []))
            self.source_geometry[layer_id] = shaped
            layer.transform = Affine()
            layer.effects = []
            layer.source.type = "baked"
            layer.source.file = None  # snapshot is stale; rewritten on save
            self._shaped_cache.pop(layer_id, None)
            return layer

    # -- resolve pipeline (the single source of truth) -------------------------

    def resolved(self) -> dict[str, list[Path]]:
        with self._lock:
            return compose.resolve_project(
                self.project, self.source_geometry, self.pens(), self._shaped_cache
            )

    def resolved_document(self, target: str = "all") -> PathDocument:
        """Un-compensated resolved geometry — what the preview renders."""
        return compose.flatten_to_document(self.project, self.resolved(), self.pens(), target)

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

    def plot_document(self, target: str = "all") -> PathDocument:
        """What actually gets plotted: resolved geometry, pen-offset
        compensated, then plot-pass optimised."""
        doc = compose.flatten_to_document(
            self.project, self.resolved(), self.pens(), target, self._pen_offsets()
        )
        return self._optimize(doc)

    def _optimize(self, doc: PathDocument) -> PathDocument:
        opts = self.project.plot_options
        cmds: list[str] = []
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

    def effective_params(self, backend_id: str, target: str = "all"):
        """Backend params with the pen's height overrides applied when a
        single layer (the manual multi-pen unit of work) is being plotted."""
        params = self.params_for(backend_id)
        if target != "all":
            try:
                layer = self.project.layer(target)
            except KeyError:
                return params
            pen = self.pens().get(layer.pen_id or "")
            if pen:
                overrides = {}
                if pen.pen_pos_down is not None and "pen_pos_down" in type(params).model_fields:
                    overrides["pen_pos_down"] = pen.pen_pos_down
                if pen.pen_pos_up is not None and "pen_pos_up" in type(params).model_fields:
                    overrides["pen_pos_up"] = pen.pen_pos_up
                if overrides:
                    params = params.model_copy(update=overrides)
        return params


session = Session()
