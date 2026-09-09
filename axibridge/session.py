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

import math
import random
import re
import threading
from collections import OrderedDict, deque
from typing import Any, NamedTuple

from . import compose, gencache, tween
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
from .registry import effective_time_axis, field_bounds, fold_time_axis, get_source
from .stores import Pen, pen_library, settings_store
from .svg_io import doc_from_svg, doc_from_vpype, doc_to_vpype

#: Undo depth, capped two ways because undo entries are not all the same size.
#: Measured 2026-08-07 on a 16-layer project with 59k source points:
#:
#: * a checkpoint costs 0.4 ms and ~29 KB of deep-copied Project, so the
#:   ordinary edits — drag, param tweak, visibility, pen, reorder — retain
#:   only that: 50 of them is ~1.3 MB, and the old depth of 8 was throwing
#:   away free undo steps.
#: * edits that REPLACE geometry (bake, regenerate, draw, brush, shape ops)
#:   are a different animal: each entry pins its own copy of that layer's
#:   paths at roughly 130 bytes per point, so 50 bakes of a 1200-path import
#:   is ~110 MB.
#:
#: Hence a count cap for the cheap case and a geometry budget for the
#: expensive one — depth stays generous without a heavy project quietly
#: eating a gigabyte. The persisted history is capped separately, at 4
#: entries, in ``project_io``.
UNDO_DEPTH = 50  # Ian's call, 2026-08-07, off the measurement above
#: ~65 MB of retained path points at ~130 bytes each.
UNDO_GEOMETRY_BUDGET_POINTS = 500_000

#: Points retained by the tween + clip-follow caches TOGETHER (same ~130 B per
#: point calibration as the undo budget). Both caches hold one entry per
#: (layer, master value) visited, so an animated project fills them by
#: scrubbing; the budget is what stops a long scrub from retaining every frame
#: of every layer for the life of the session. Eviction is RANDOM, for the same
#: reason ``gencache`` gives: playback is cyclic, and LRU at capacity evicts
#: precisely the frame about to be reused.
TWEEN_CACHE_BUDGET_POINTS = 3_000_000


class _TweenEntry(NamedTuple):
    """One materialised tween, for one content key.

    ``refs`` is the load-bearing field: the cache key embeds ``id()`` of each
    endpoint's geometry list, and a key whose object has been collected can be
    matched by an unrelated list that recycled the id — a silently wrong hit.
    Holding the lists keeps every id in the key belonging to a live object, the
    same discipline ``compose._ClipEntry`` and ``_ShapedEntry`` follow."""

    paths: list[Path]
    refs: tuple
    points: int


class _ClipFollowEntry(NamedTuple):
    """One clip-advanced generator result. The key is pure content (params +
    frame offset + master value), so there is no id() to keep alive."""

    paths: list[Path]
    points: int


def _evict_tween_caches(
    caches: tuple[dict[str, "OrderedDict[str, Any]"], ...],
    protect: tuple[int, str, str],
) -> None:
    """Random-evict across the tween and clip caches (one shared budget) until
    the point total fits. ``protect`` is ``(cache index, layer id, key)`` — the
    entry just inserted, which must survive its own insert."""
    budget = int(TWEEN_CACHE_BUDGET_POINTS * gencache.cache_budget_multiplier())
    total = sum(e.points for cache in caches for m in cache.values() for e in m.values())
    while total > budget:
        candidates = [(i, layer_id, key)
                      for i, cache in enumerate(caches)
                      for layer_id, m in cache.items()
                      for key in m
                      if (i, layer_id, key) != protect]
        if not candidates:
            return
        i, layer_id, key = random.choice(candidates)
        total -= caches[i][layer_id].pop(key).points
        if not caches[i][layer_id]:
            del caches[i][layer_id]


def _nudge_onto(coords: list[float], extent: float) -> float:
    """How far to slide a span so it sits inside ``0..extent``. Zero when it
    already does; centres it when it is simply too big to fit."""
    lo, hi = min(coords), max(coords)
    if hi - lo > extent:
        return (extent - (lo + hi)) / 2
    if lo < 0:
        return -lo
    if hi > extent:
        return extent - hi
    return 0.0


def _subpath_by_distance(
    points: list[tuple[float, float]], d0: float, d1: float
) -> list[tuple[float, float]]:
    """The sub-polyline of ``points`` between arc distances ``d0``..``d1``
    (mm along the stroke) — where the pen was down between two moments of an
    interrupted plot. ``[]`` when the interval misses the stroke entirely."""
    if d1 <= d0:
        return []
    out: list[tuple[float, float]] = []
    cum = 0.0
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        seg = math.hypot(x1 - x0, y1 - y0)
        nxt = cum + seg
        if seg > 0 and nxt > d0 and cum < d1:
            fa = (max(d0, cum) - cum) / seg
            fb = (min(d1, nxt) - cum) / seg
            pa = (x0 + (x1 - x0) * fa, y0 + (y1 - y0) * fa)
            pb = (x0 + (x1 - x0) * fb, y0 + (y1 - y0) * fb)
            if not out:
                out.append(pa)
            out.append(pb)
        cum = nxt
        if cum >= d1:
            break
    return out


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


#: valid ``crop`` modes for grid-sheet placement (2026-08-11, Ian's ruling —
#: docs/plans/timeline-v2.md §2c "Baking crop"). NO per-frame mode: the old
#: "center" behaviour (each frame recentred on its own bbox) cancelled
#: translation and is removed entirely, not merely deprecated.
_CROP_MODES = ("timeline", "full")


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
        #: layer id -> {shape key: entry}, recency-ordered. Multi-entry so a
        #: scrub that returns to a frame re-hits (see compose._ShapedEntry).
        self._shaped_cache: dict[str, "OrderedDict[str, compose._ShapedEntry]"] = {}
        #: occlusion-stage memo (the expensive one). Content-keyed on geometry
        #: identity + the occluder properties, so it needs no invalidation —
        #: see ``compose.OcclusionCache`` for why the key is complete.
        self._occlusion_cache = compose.OcclusionCache()
        #: undo snapshots, newest last. Paths/lists are never mutated in place
        #: (module purity contract), so sharing references is safe — only the
        #: project model needs a deep copy.
        self._history: deque[
            tuple[Project, dict[str, list[Path]], dict[str, str], dict[str, PathDocument]]
        ] = deque(maxlen=UNDO_DEPTH)
        #: redo branch: states undone away, newest last. Filled only by
        #: ``undo()`` and emptied by the next real edit — a mutation after an
        #: undo abandons the branch it was going to redo into, which is what
        #: every editor does and the only behaviour that can't surprise.
        self._redo: deque[
            tuple[Project, dict[str, list[Path]], dict[str, str], dict[str, PathDocument]]
        ] = deque(maxlen=UNDO_DEPTH)
        #: id(geometry list) -> (list ref, point count) for the history budget.
        #: The stored reference keeps the id valid — same identity discipline
        #: as the occlusion memo — and the map is pruned to what history still
        #: holds every time the budget is measured.
        self._geom_points: dict[int, tuple[list[Path], int]] = {}
        #: last checkpoint's coalesce key: consecutive checkpoints carrying the
        #: same key collapse into ONE undo entry (live slider runs on a latched
        #: layer), so undo returns to the state before the run started.
        self._coalesce_key: tuple | None = None
        #: tween layer id -> {content key: entry}, recency-ordered. One entry
        #: per master value visited, so scrubbing back to a frame re-hits.
        self._tween_cache: dict[str, "OrderedDict[str, _TweenEntry]"] = {}
        #: frame-follow generator layer id -> {content key: entry}.
        #: An EPHEMERAL scrub overlay: computed only when resolving with a
        #: master_t, never written into ``source_geometry`` (the user's stored
        #: geometry stays byte-identical under a scrub). Keyed on content, so a
        #: cache hit hands back the SAME list object and the shaped cache re-hits.
        self._clip_cache: dict[str, "OrderedDict[str, _ClipFollowEntry]"] = {}
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
        self._redo.clear()  # a fresh edit abandons the branch redo led into
        if coalesce is not None and coalesce == self._coalesce_key and self._history:
            # same coalesce run as the previous checkpoint: keep the run's
            # opening snapshot as THE undo point, but caches still go stale
            self._frame_lru.clear()
            self._frame_bbox.clear()
            return
        self._coalesce_key = coalesce
        self._history.append(self._snapshot())
        self._trim_history()
        # a checkpoint precedes a mutation — cached frames are about to go stale
        self._frame_lru.clear()
        self._frame_bbox.clear()

    def _snapshot(self) -> tuple[Project, dict[str, list[Path]], dict[str, str],
                                 dict[str, PathDocument]]:
        """One history entry for the CURRENT state — what undo and redo both
        step between.

        The deep copy deliberately EXCLUDES staging: capture groups, their
        snapshots and staged documents are frozen by construction (staging
        mutations replace objects wholesale — see rename_capture_group), so
        history entries share them by reference, exactly like geometry lists.
        Without this exclusion every checkpoint deep-copied every capture
        snapshot's full geometry AND every staged document — the "snapshots
        are cheap by construction" invariant had broken silently when staging
        moved inside the Project model (found 2026-07-19)."""
        staging = self.project.staging
        self.project.staging = []
        try:
            proj = self.project.model_copy(deep=True)
        finally:
            self.project.staging = staging
        proj.staging = list(staging)
        return (proj, dict(self.source_geometry), dict(self.svg_files),
                dict(self.staging_documents))

    def _restore(self, entry: tuple[Project, dict[str, list[Path]], dict[str, str],
                                    dict[str, PathDocument]]) -> None:
        """Adopt a history entry as the live state and drop every derived
        cache. Shared by undo and redo so they cannot diverge."""
        self.project, self.source_geometry, self.svg_files, self.staging_documents = entry
        self._shaped_cache.clear()
        self._occlusion_cache.clear()
        self._tween_cache.clear()
        self._clip_cache.clear()
        self._frame_lru.clear()
        self._frame_bbox.clear()

    def _history_points(self) -> int:
        """Total points of geometry pinned by history, counting each list once
        however many entries share it. Also prunes the memo to what is still
        referenced, so the map can never outlive the history."""
        seen: dict[int, tuple[list[Path], int]] = {}
        total = 0
        for _proj, geo, _svg, _staging in (*self._history, *self._redo):
            for paths in geo.values():
                key = id(paths)
                if key in seen:
                    continue
                hit = self._geom_points.get(key)
                if hit is None or hit[0] is not paths:
                    hit = (paths, sum(len(p.points) for p in paths))
                seen[key] = hit
                total += hit[1]
        self._geom_points = seen
        return total

    def _trim_history(self) -> None:
        """Drop entries while the geometry they pin is over budget, always from
        the end furthest from now: the oldest undo step first, then the
        furthest-future redo step. One undo step is never traded away."""
        while self._history_points() > UNDO_GEOMETRY_BUDGET_POINTS:
            if len(self._history) > 1:
                self._history.popleft()
            elif self._redo:
                self._redo.popleft()
            else:
                return

    def clear_history(self) -> None:
        """Project switch: snapshots of another project must not restore here."""
        with self._lock:
            self._history.clear()
            self._redo.clear()
            self._geom_points.clear()
            self._coalesce_key = None
            self._frame_lru.clear()
            self._frame_bbox.clear()

    def undo(self) -> bool:
        """Step back one entry, remembering where we were so redo can return.

        History is a pair of stacks rather than a cursor: ``_history`` holds
        the states behind us, ``_redo`` the states we stepped out of. Undo
        moves the current state from one to the other, redo moves it back, and
        any real edit clears ``_redo`` (see ``_checkpoint``)."""
        with self._lock:
            self._coalesce_key = None  # a new edit after undo must push
            if not self._history:
                return False
            self._redo.append(self._snapshot())
            self._restore(self._history.pop())
            return True

    def redo(self) -> bool:
        """Step forward again into the branch ``undo`` stepped out of. Empty
        as soon as anything is edited — there is no branch left to return to."""
        with self._lock:
            self._coalesce_key = None
            if not self._redo:
                return False
            self._history.append(self._snapshot())
            self._restore(self._redo.pop())
            return True

    def can_undo(self) -> bool:
        with self._lock:
            return bool(self._history)

    def can_redo(self) -> bool:
        with self._lock:
            return bool(self._redo)

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
            self._redo.clear()
            self._geom_points.clear()
            for item in history[-self._history.maxlen:]:
                self._history.append(item)
            self._trim_history()

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
    def time_axis(generator_id: str) -> str | None:
        """Which param of this generator is time, or None.

        The ``frame`` fallback is what makes this a generalisation rather than
        a migration: every image generator predates the declaration and keeps
        working untouched. Declaring is how a NEW axis opts in."""
        try:
            src = get_source(generator_id)
        except KeyError:
            return None
        return effective_time_axis(src)

    @staticmethod
    def axis_bounds(generator_id: str, axis: str) -> tuple[float, float] | None:
        """The axis's own ``ge``/``le``, or None when it is not bounded on both
        sides — in which case there is nothing to map ``master_t`` onto and the
        layer simply does not follow the timeline."""
        return field_bounds(get_source(generator_id).Params.model_fields[axis])

    @staticmethod
    def _effective_gen_params(
        layer: CanvasLayer, master_t: float | None = None
    ) -> dict[str, Any]:
        """The generator params to actually GENERATE with: the layer's stored
        source params, but with the layer's time shift folded into whichever
        param the generator declares as its TIME AXIS. The stored params are
        NEVER mutated — this returns a copy — so the user's raw value and the
        undo/purity contract stay intact.

        The shift is ``frame_offset``, PLUS ``master_t`` when the layer opted
        into ``frame_follow`` and a ``master_t`` is supplied (the single place
        that folds a scrub — the effective params for the preview, estimate and
        plotter alike are computed here).

        The shift is in NORMALISED units (0..1 across the axis's own bounds),
        which is what lets one mechanism serve a 0..1 video ``frame`` and a
        0..2000 step count. The layer fields are still named ``frame_*``
        because they are persisted in every saved project; renaming them would
        buy clarity worth less than a migration."""
        params = dict(layer.source.params or {})
        if layer.source.type not in ("generator", "baked") or not layer.source.generator:
            return params
        shift = layer.frame_offset
        if master_t is not None and layer.frame_follow:
            shift += master_t
        if not shift:
            return params
        return fold_time_axis(get_source(layer.source.generator), params, shift)

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

    @staticmethod
    def _orientation_turn() -> Affine:
        """The quarter-turn a ``"geometry"``-oriented layer needs in
        portrait: the canvas draws portrait through ``translate(H 0)
        rotate(90)``, i.e. machine (x, y) appears at (H - y, x), so
        machine-frame geometry with a dominant axis — a text baseline, a
        scan direction, a width x height field — arrives a quarter-turn
        round. This is the display map's inverse, (x, y) -> (y, H - x): a
        270-degree (clockwise) turn plus H — the same machine-frame value
        ``viewmap.js`` hands a ``viewRotate`` param whose displayed default
        is 0. Shared by ``_placement_transform`` (bakes it in once, at
        creation) and ``set_view`` (applies or undoes it on an EXISTING
        layer when the view toggles afterwards) — one formula, so the two
        can't quietly drift apart the way this bug started as."""
        return Affine(a=0.0, b=-1.0, c=1.0, d=0.0, e=0.0, f=compose.BED_HEIGHT)

    @staticmethod
    def _fit_frame_placement(frame: tuple[float, float], view: str) -> Affine:
        """One affine for an element's entire declared physical frame."""
        width, height = frame
        bw, bh = compose.BED_WIDTH, compose.BED_HEIGHT
        if view == "portrait":
            scale = min(1., bw / height, bh / width)
            return Affine(a=0., b=-scale, c=scale, d=0.,
                          e=(bw-scale*height)/2, f=(bh+scale*width)/2)
        scale = min(1., bw / width, bh / height)
        return Affine(a=scale, d=scale, e=(bw-scale*width)/2, f=(bh-scale*height)/2)

    def _placement_transform(
        self, generator_id: str, params: dict[str, Any], doc: PathDocument,
        paths: list[Path],
    ) -> Affine:
        """A new layer's opening transform: centring, plus portrait's
        quarter-turn for sources that declare ``orientation = "geometry"``.

        THE ONE PLACE orientation is corrected for a freshly created layer
        (ROADMAP "URGENT", option B) — ``set_view`` is the other, for a layer
        that already existed when the view changed. The layer's own affine
        undoes the display map exactly, so the layer lands **where it would
        have landed in landscape, on screen**: see ``_orientation_turn``.

        Sources declaring ``"param"`` already get this from their tagged
        rotation param and must not be turned twice; ``"none"`` has no
        dominant axis to get wrong. Nothing downstream reads ``view``: the
        correction is baked into the stored transform, so resolve stays
        byte-identical across a view toggle (test_view_coherence)."""
        frame = get_source(generator_id).placement_frame(params)
        if frame is not None:
            return self._fit_frame_placement(frame, self.project.view)
        base = self._centering_transform(generator_id, params, doc)
        if self.project.view != "portrait":
            return base
        if getattr(get_source(generator_id), "orientation", None) != "geometry":
            return base
        pts = [pt for path in paths for pt in path.points]
        if not pts:
            return base
        turned = _mul_affine(self._orientation_turn(), base)
        # The portrait sheet is narrower than the landscape one (218 vs 300),
        # so geometry laid out for the full width can now hang off the bed.
        # Slide it back rather than hand the user something to rescue.
        corners = [turned.apply(x, y)
                   for x in (min(x for x, _ in pts), max(x for x, _ in pts))
                   for y in (min(y for _, y in pts), max(y for _, y in pts))]
        return turned.model_copy(update={
            "e": turned.e + _nudge_onto([c[0] for c in corners], compose.BED_WIDTH),
            "f": turned.f + _nudge_onto([c[1] for c in corners], compose.BED_HEIGHT),
        })

    def set_view(self, view: str) -> None:
        """Change the project's display view (portrait/landscape) and
        retroactively re-orient every live ``"geometry"``-oriented layer to
        match — closes the gap ``_placement_transform`` left open: that
        method only corrects a layer at the moment it's CREATED, so a layer
        created in one view and left alone while the other view is selected
        used to just sit there un-rotated, rendering sideways. Composes
        ``_orientation_turn`` (or its inverse, going the other way) onto
        whatever transform each layer already has, so any manual Placement-
        panel edit made since creation is preserved, not clobbered — and
        toggling back and forth is exact (affine composition, no drift).

        Only ``"generator"``-type layers qualify — a ``"baked"`` layer's
        transform already got reset to identity when its geometry was
        consolidated (``consolidate_effects``); its ORIENTATION is frozen
        into that baked geometry the same way its params are, and turning
        the (now-identity) transform on top would just rotate it wrong.
        Un-bake (regenerate) to pick up a view change.

        ``view`` is validated here (not just by the API layer): an invalid
        or no-op value is silently ignored, matching ``ProjectPatch``'s
        existing tolerance."""
        if view not in ("portrait", "landscape") or view == self.project.view:
            return
        old = self.project.view
        targets = []
        for layer in self.project.layers:
            if layer.source.type != "generator" or not layer.source.generator:
                continue
            try:
                src = get_source(layer.source.generator)
            except KeyError:
                continue  # stale/renamed module id — nothing to correct
            if src.orientation == "geometry":
                targets.append(layer)
        with self._lock:
            if targets:
                self._checkpoint()
            self.project.view = view
            if not targets:
                return
            step = self._orientation_turn()
            if old == "portrait":  # portrait -> landscape undoes the turn
                step = _invert_affine(step)
            for layer in targets:
                frame = get_source(layer.source.generator).placement_frame(layer.source.params)
                if frame is not None:
                    # Relative frame placements are invertible: toggling back
                    # restores the exact scale instead of shrinking every time.
                    before = self._fit_frame_placement(frame, old)
                    after = self._fit_frame_placement(frame, view)
                    delta = _mul_affine(after, _invert_affine(before))
                else:
                    delta = step
                layer.transform = _mul_affine(delta, layer.transform)

    def add_generated_layer(self, generator_id: str, params: dict[str, Any]) -> CanvasLayer:
        src = get_source(generator_id)
        # The Compose form normally rolls a seed before POSTing, so this only
        # bites callers that never went through one — the API, a script, a
        # test — which used to get seed 0 every time.
        params = self._rolled_seed(src, params)
        doc = gencache.generate_cached(src, params)
        paths = [p for layer in doc.layers for p in layer.paths]
        layer = CanvasLayer(
            name=src.label,
            source=LayerSource(type="generator", generator=generator_id, params=params),
            transform=self._placement_transform(generator_id, params, doc, paths),
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
            doc = gencache.generate_cached(src, self._effective_gen_params(layer))
            self.source_geometry[layer.id] = [p for lyr in doc.layers for p in lyr.paths]
            layer.source.type = "generator"  # a baked layer returns to live output
            layer.source.file = None  # snapshot is stale; rewritten on save
            self._shaped_cache.pop(layer_id, None)
            return layer

    def append_shape_op(self, layer_id: str, op: dict[str, Any]) -> CanvasLayer:
        """Commit one add/subtract op to a shape-mass layer, CONVERTING the
        layer first when it is still a plain pen or brush layer: the existing
        content becomes the leading ops (pen subpaths → ``add`` pen ops,
        brush strokes → add/subtract brush ops) and the new gesture is
        appended. This is the single seam behind every cross-tool action
        (erase into a pen shape, pen-cut into a brushed blob, pen subtract
        anywhere) — see sources/shape.py's docstring.

        One checkpoint: convert+commit is a single undo step, so ⌘Z returns
        the layer to its pre-conversion pen/brush state with the gesture
        uncommitted. The op is validated BEFORE anything mutates."""
        with self._lock:
            layer = self.project.layer(layer_id)
            gen = layer.source.generator if layer.source.type == "generator" else None
            params = layer.source.params or {}
            if gen == "shape":
                new_params = {**params, "ops": [*params.get("ops", []), op]}
            elif gen == "pen":
                ops = [{"kind": "pen", "mode": "add",
                        "anchors": sp.get("anchors", []),
                        "closed": sp.get("closed", False)}
                       for sp in params.get("subpaths", [])]
                new_params = {"ops": [*ops, op]}
            elif gen == "brush":
                ops = [{"kind": "brush",
                        "mode": "subtract" if s.get("mode") == "erase" else "add",
                        "points": s.get("points", []),
                        "radius": s.get("radius", 5.0)}
                       for s in params.get("strokes", [])]
                new_params = {"ops": [*ops, op]}
            else:
                raise RuntimeError(
                    "only pen, brush and shape layers take shape ops "
                    f"(this layer is {gen or layer.source.type})")
            src = get_source("shape")
            src.Params(**new_params)  # raises before any mutation
            self._checkpoint()
            layer.source.type = "generator"
            layer.source.generator = "shape"
            layer.source.file = None
            layer.source.params = new_params
            if gen != "shape":
                layer.name = src.label
            # re-validates internally (gencache validates first, always) —
            # cheap and keeps generate_cached's contract uniform; the raw
            # dict (not the pre-validated model) is what the cache key needs.
            doc = gencache.generate_cached(src, new_params)
            self.source_geometry[layer.id] = [p for lyr in doc.layers for p in lyr.paths]
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
            diameter = compose.line_diameter_for(layer, self.pens())
        if src is None:
            raise RuntimeError("layer has no source geometry to preview (tween layers preview live already)")
        candidate.effects = [EffectStep(**e) for e in effects]
        # outside the lock: shape_layer is pure and src is never mutated in place
        return compose.shape_layer(
            candidate, src, compose.guide_page(self.project), diameter)

    def add_svg_layers(
        self, svg_text: str, filename: str, quantization_mm: float,
        rename: str | None = None,
    ) -> list[CanvasLayer]:
        """An uploaded SVG contributes its layers as compositor layers.
        ``rename`` overrides the SVG-derived layer names (the caller's name
        beats whatever ids the SVG round-trip produced)."""
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
                   "occlude_groups", "receives_groups",
                   "region", "region_boundary", "frame_offset", "frame_follow", "effect_seed"}
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
            # A frame_offset change on a time-axis generator re-samples it:
            # regenerate its source geometry with the offset folded into
            # whichever param is its TIME AXIS (stored params keep the user's
            # raw value). Same lock, same single checkpoint; a generation
            # failure propagates (identical failure semantics to
            # regenerate_layer, which has already checkpointed). Non-generator
            # sources just store the field.
            # (live generators only: a baked layer's geometry holds consolidated
            # transform/effects — regenerating here would silently discard them;
            # an explicit "regenerate" un-bakes on purpose and picks up the offset)
            if ("frame_offset" in patch and updated.frame_offset != layer.frame_offset
                    and updated.source.type == "generator"
                    and updated.source.generator
                    and effective_time_axis(get_source(updated.source.generator)) is not None):
                src = get_source(updated.source.generator)
                doc = gencache.generate_cached(src, self._effective_gen_params(updated))
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
    def _tween_refs(layer: CanvasLayer) -> list[Any]:
        """Every layer id a tween references, in order — ``[a, b]`` for a
        pair, the whole ``keys`` list for a chain (S2), so this is the ONE
        place that knows how many refs a tween has. Every caller must treat
        the result as a variable-length sequence (membership / iteration),
        never unpack a
        fixed 2-tuple — a chain with mid keyframes would silently dangle
        wherever that assumption survived (see F3 in
        docs/plans/timeline-v2.md)."""
        p = layer.source.params or {}
        keys = p.get("keys")
        if keys:
            return list(keys)
        return [p.get("a"), p.get("b")]

    #: an Animate-created keyframe's name always carries a " ▸ <LETTER>"
    #: SUFFIX (A, B, and — from S2 on — C, D, … for chain mid-keys), always
    #: appended at the very end (``f"{original_name} ▸ B"``, never embedded
    #: mid-string). Anchoring on ``$`` — rather than the old substring test —
    #: is what makes this a genuine suffix pattern per F3/S1, and it is what
    #: lets ``_animation_keyframes_for`` recognise a chain's hidden keyframes
    #: once they exist; zero behaviour change today, since every name this
    #: app ever produces already puts the suffix last.
    _KEYFRAME_SUFFIX_RE = re.compile(r" ▸ [A-Z]$")

    def _animation_keyframes_for(self, tween_layer: CanvasLayer) -> list[CanvasLayer]:
        """Hidden Animate-created keyframe layers, not visible manual tween refs.

        Length-agnostic since S2: a CHAIN's mid-keys are Animate-created
        keyframes too, so dragging the tween moves the whole group (all N
        keyframes) exactly as it moves A and B on a pair — the visible tween
        stays the one handle for the animation."""
        if tween_layer.source.type != "tween":
            return []
        refs: list[CanvasLayer] = []
        for ref_id in self._tween_refs(tween_layer):
            try:
                refs.append(self.project.layer(ref_id))
            except KeyError:
                return []
        if len(refs) < 2:
            return []
        if all((not l.visible) and self._KEYFRAME_SUFFIX_RE.search(l.name) for l in refs):
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
                        if any(r in doomed for r in self._tween_refs(tw)):
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
                            if layer.id in self._tween_refs(tw):
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
                    tw_refs = self._tween_refs(tw)
                    a_ref = tw_refs[0] if tw_refs else None  # first key only ("A")
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
                    if any(r in doomed for r in self._tween_refs(tw)):
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
            if "keys" in values:
                # a chain rides the ordinary params merge, so this is the ONE
                # place a keys list can arrive from outside: every id must name
                # a real layer, and none may be the tween itself (a self-
                # reference is a cycle the resolve path would have to unwind
                # every tick). Bounds/uniqueness/endpoint sync are TweenParams'.
                self._validate_chain_keys(layer, merged.keys)
            self._checkpoint()
            layer.source.params = merged.model_dump()
            return layer

    def _validate_chain_keys(self, tween_layer: CanvasLayer, keys: list[str]) -> None:
        for kid in keys:
            if kid == tween_layer.id:
                raise RuntimeError("an interpolation layer cannot be its own keyframe")
            self.project.layer(kid)  # KeyError -> 404 at the API edge

    def _chain_keys(self, layer: CanvasLayer) -> list[str]:
        """This tween's keyframe ids as a chain would see them: the stored
        ``keys`` when set, else the implicit ``[a, b]`` pair — so the chain
        verbs below work on a plain A/B animation without a "convert to chain"
        step (Q6: chains grow out of the existing Animate flow)."""
        if layer.source.type != "tween":
            raise RuntimeError("not an interpolation layer")
        return [r for r in self._tween_refs(layer) if isinstance(r, str)]

    def _set_chain_keys(self, layer: CanvasLayer, keys: list[str]) -> None:
        """Store a chain's key list (caller holds the lock and has already
        checkpointed). A chain that falls back to two keys is stored as a plain
        pair (``keys = []``): the classic form is fully reversible, and every
        pre-chain reader — including an older build loading the saved project —
        sees exactly the A/B tween it understands."""
        params = dict(layer.source.params or {})
        params["keys"] = list(keys) if len(keys) > 2 else []
        params["a"], params["b"] = keys[0], keys[-1]
        layer.source.params = tween.TweenParams(**params).model_dump()
        self._tween_cache.pop(layer.id, None)

    def add_chain_keyframe(self, layer_id: str) -> CanvasLayer:
        """Append a keyframe to a tween, turning A/B into a chain (A▸B▸C…).

        Per Ian's Q6 ruling the new key DUPLICATES THE LAST one, so the
        appended segment starts static: the animation looks identical the
        moment this returns and endpoint fidelity is preserved (duplicating
        the FIRST key would make the tail snap back). The duplicate is hidden
        and named with the next letter suffix, exactly like Animate's A/B, so
        the cascade-delete rules collect it with its tween.

        One checkpoint, no coalescing — adding a checkpoint is a discrete act,
        not a latched drag."""
        with self._lock:
            layer = self.project.layer(layer_id)
            keys = self._chain_keys(layer)
            if len(keys) >= tween.MAX_CHAIN_KEYS:
                raise RuntimeError(
                    f"a keyframe chain holds at most {tween.MAX_CHAIN_KEYS} keyframes")
            last = self.project.layer(keys[-1])
            self._checkpoint()

            data = last.model_dump()
            data["effect_seed"] = compose.layer_effect_seed(last)
            del data["id"]  # CanvasLayer mints a fresh one
            base = self._KEYFRAME_SUFFIX_RE.sub("", last.name)
            data["name"] = f"{base} ▸ {chr(ord('A') + len(keys))}"
            data["visible"] = False
            new_key = CanvasLayer(**data)
            new_key.source.file = None  # snapshot belongs to the original
            # below every existing keyframe, so the layer dock reads
            # tween / A / B / C top-down (the list displays bottom->top reversed)
            idx = min(self.project.layers.index(self.project.layer(k)) for k in keys)
            self.project.layers.insert(idx, new_key)
            # geometry lists are shared by reference and replaced wholesale,
            # never mutated in place (module purity) — the same thing
            # animate_layer does for keyframe B
            self.source_geometry[new_key.id] = self.source_geometry.get(last.id, [])
            self._set_chain_keys(layer, [*keys, new_key.id])
            return new_key

    def remove_chain_keyframe(self, layer_id: str, key_layer_id: str) -> CanvasLayer:
        """Drop one keyframe from a chain, returning the tween.

        The chain re-spaces itself (spacing is derived from the key count, not
        stored), and a chain that falls back to two keys becomes a plain A/B
        tween again. The removed layer is deleted along with it when it is a
        hidden keyframe no surviving tween still references — the same rule
        the delete cascade uses; a VISIBLE layer (a manual tween's own source)
        is only unlinked, never destroyed. One checkpoint."""
        with self._lock:
            layer = self.project.layer(layer_id)
            keys = self._chain_keys(layer)
            if key_layer_id not in keys:
                raise KeyError(f"not a keyframe of this interpolation layer: {key_layer_id}")
            if len(keys) <= 2:
                raise RuntimeError(
                    "an interpolation layer needs two keyframes — delete the "
                    "layer itself to un-animate")
            remaining = [k for k in keys if k != key_layer_id]
            self._checkpoint()
            self._set_chain_keys(layer, remaining)
            try:
                orphan = self.project.layer(key_layer_id)
            except KeyError:
                return layer
            still_referenced = any(
                key_layer_id in self._tween_refs(tw) for tw in self._tweens())
            if not orphan.visible and not still_referenced:
                self.project.layers.remove(orphan)
                self.source_geometry.pop(orphan.id, None)
                self._shaped_cache.pop(orphan.id, None)
                self._tween_cache.pop(orphan.id, None)
                self._clip_cache.pop(orphan.id, None)
            return layer

    def reorder_chain_keyframes(self, layer_id: str, ordered_ids: list[str]) -> CanvasLayer:
        """Re-order a chain's keyframes (the same set, a new order). The
        segments and their isometric spacing follow from the list, so this is
        the only "move a keyframe in time" verb there is. One checkpoint."""
        with self._lock:
            layer = self.project.layer(layer_id)
            keys = self._chain_keys(layer)
            if sorted(ordered_ids) != sorted(keys):
                raise ValueError(
                    "order must contain exactly this interpolation layer's keyframes")
            self._checkpoint()
            self._set_chain_keys(layer, list(ordered_ids))
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
                diameter = compose.line_diameter_for(layer, self.pens())
                paths = tween.materialize(
                    step, self.project, self.source_geometry,
                    line_diameter_mm=diameter)
                shaped = compose.shape_layer(
                    layer, paths, compose.guide_page(self.project), diameter)  # tween's own tf/fx baked in
                data = layer.model_dump()
                del data["id"]
                data.update(
                    name=f"{layer.name} t={t:.2f}", visible=True,
                    transform=Affine().model_dump(), effects=[], effect_seed=None,
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
        crop: str = "timeline",
    ) -> list[dict[str, list[Path]]]:
        """Lay each master-timeline sample ``ts[i]`` into cell i of a cols×rows
        grid on the paper guide, keeping PER-LAYER geometry (not flattened) so
        callers can group by pen. Cells are row-major. Geometry is the
        VISIBLE, resolved (post-occlusion) paths, so a cell is exactly what the
        canvas/plotter show at that t.

        ``crop`` (2026-08-11 ruling, docs/plans/timeline-v2.md §2c "Baking
        crop" — NO per-frame mode; the old "center each frame on its own
        bbox" behaviour cancelled relative motion and was removed entirely):
        * ``"timeline"`` (default) — ONE bbox unioned across every frame in
          ``master_scale_ts`` (defaults to ``ts``), applied identically —
          same scale, same centre — to every frame: a locked-off camera, so
          relative movement between frames survives.
        * ``"full"`` — no crop: every frame keeps the full page/guide bounds,
          scaled and centred on the PAGE rather than on content, so negative
          space is preserved and a frame's position within the page reads the
          same in its cell.

        Orientation (rotate frames 90° inside their cells when that fits
        better) is decided ONCE per call, from cell aspect vs. the fit box's
        aspect — not per frame — by comparing the scale each orientation
        would achieve and keeping the larger. Replaces the old hardcoded
        ``_ROTATED_GRIDS`` lookup (2×1, 4×2 only) with the general case.

        Resolves go through the per-frame caches (``_frame_lru`` geometry,
        ``_frame_bbox`` bounds), cleared on any project mutation — so stepping
        pages/passes of an unchanged project stops re-resolving the whole
        animation. The ``"timeline"`` union bbox reuses the same
        ``_frame_bbox`` cache (via ``frame_bbox`` below), so it costs nothing
        extra on a warm page. Read-only: no checkpoint, no user
        source_geometry writes. Call under ``self._lock``."""
        if crop not in _CROP_MODES:
            raise ValueError(f"crop must be one of {_CROP_MODES}")
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

        # shared bboxes only — cached across pages/passes. Kept for BOTH crop
        # modes (not just "timeline"): it is also the emptiness guard below,
        # and it costs nothing extra since visible_geo() populates the same
        # _frame_bbox cache every caller already warms.
        boxes = [b for t in (master_scale_ts or ts) if (b := frame_bbox(t)) is not None]
        if not boxes:
            raise RuntimeError("nothing to place (no visible geometry across the frame range)")

        sheet_x, sheet_y, sheet_w, sheet_h = self._sheet_rect()
        # cols/rows are what the user SEES on the sheet, in whichever view is
        # current — the same "I shouldn't have to think about this" contract
        # as a single layer's orientation (test_orientation.py), applied to
        # which CELL a frame index lands in instead of a layer's transform.
        # The bed's own axes are transposed relative to the screen under the
        # portrait display map (canvas.js's translate(H 0) rotate(90):
        # machine (x, y) -> screen (H - y, x)) — a machine COLUMN determines
        # screen VERTICAL position, a machine ROW determines screen
        # HORIZONTAL position, mirrored. So the physical grid this actually
        # subdivides into is (mcols, mrows) = (rows, cols) in portrait; see
        # the per-frame loop below for the matching index remap.
        portrait = self.project.view == "portrait"
        mcols, mrows = (rows, cols) if portrait else (cols, rows)
        cell_w = sheet_w / mcols - 2 * margin_mm
        cell_h = sheet_h / mrows - 2 * margin_mm
        if cell_w <= 0 or cell_h <= 0:
            raise RuntimeError("margin too large for this grid on the current paper guide")

        if crop == "full":
            # no crop: fit/centre on the PAGE, not on content — every frame
            # keeps the whole guide rect, so negative space and each frame's
            # true position on the page survive into its cell.
            fit_w, fit_h = sheet_w, sheet_h
            fcx, fcy = sheet_x + sheet_w / 2, sheet_y + sheet_h / 2
        else:
            uminx = min(b[0] for b in boxes)
            uminy = min(b[1] for b in boxes)
            umaxx = max(b[2] for b in boxes)
            umaxy = max(b[3] for b in boxes)
            fit_w = max(umaxx - uminx, 1e-6)
            fit_h = max(umaxy - uminy, 1e-6)
            fcx, fcy = (uminx + umaxx) / 2, (uminy + umaxy) / 2

        # Orientation, decided ONCE for the whole bake (not per frame): try
        # both ways up and keep whichever gives the bigger scale. Generalises
        # the old (cols, rows)-keyed lookup table (2×1, 4×2 only) to any
        # grid shape, including hand-entered ones.
        scale_upright = min(cell_w / fit_w, cell_h / fit_h)
        scale_rotated = min(cell_w / fit_h, cell_h / fit_w)
        rotate = scale_rotated > scale_upright
        scale = scale_rotated if rotate else scale_upright  # shared: no per-frame size jitter

        placed_frames: list[dict[str, list[Path]]] = []
        for i, t in enumerate(ts):
            frame = visible_geo(t)
            if portrait:
                # read (screen_row, screen_col) in SCREEN terms first —
                # row-major, left-to-right, top-to-bottom as the user sees
                # it — then map to the machine cell that displays there.
                screen_row, screen_col = divmod(i, cols)
                mcol, mrow = screen_row, (cols - 1) - screen_col
            else:
                mrow, mcol = divmod(i, cols)  # row-major, left-to-right, top-to-bottom
            cx = sheet_x + (mcol + 0.5) * (sheet_w / mcols)
            cy = sheet_y + (mrow + 0.5) * (sheet_h / mrows)
            if rotate:
                aff = Affine(a=0.0, b=scale, c=-scale, d=0.0,
                             e=cx + scale * fcy, f=cy - scale * fcx)
            else:
                aff = Affine(a=scale, b=0.0, c=0.0, d=scale,
                             e=cx - scale * fcx, f=cy - scale * fcy)
            placed_frames.append(
                {lid: compose.transform_paths(paths, aff) for lid, paths in frame.items()}
            )
        return placed_frames

    def _sheet_marks(self, cols: int, rows: int, arm_mm: float = 2.0) -> list[Path]:
        """Registration crosshairs at every grid intersection of the sheet —
        (cols+1)×(rows+1) small ＋ marks separating the frames. Clamped to the
        bed (the machine frame has no negatives). ``cols``/``rows`` are
        screen-frame, like ``_grid_place`` — swapped to the physical
        (mcols, mrows) the bed actually divides into under portrait, so the
        crosshairs land on the SAME cell boundaries ``_grid_place`` used
        (a full mesh, so no reading-order remap needed, just the swap)."""
        x0, y0, w, h = self._sheet_rect()
        mcols, mrows = (rows, cols) if self.project.view == "portrait" else (cols, rows)
        out: list[Path] = []
        for i in range(mcols + 1):
            for j in range(mrows + 1):
                cx, cy = x0 + i * w / mcols, y0 + j * h / mrows
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
        crop: str = "timeline", marks: bool = False,
    ) -> PathDocument:
        """One physical sheet of the flip-book, assembled at plot time — NO
        project mutation, no checkpoint (it is pure assembly; the tray capture
        path is how a sheet becomes editable layers, via ``insert``).

        ``frames`` timeline samples over [t_from, t_to] are laid into a
        cols×rows grid, chunked ``cols*rows`` cells per page; ``page`` (0-based)
        selects the chunk, the last of which may be partial. The scale is shared
        across ALL frames (every page) so frame k is the same size wherever it
        lands — flipbook-consistent. See :meth:`_grid_place` for ``crop``.

        The document is grouped BY PEN: one doc layer per pen worn by a
        contributing layer, plus a ``""`` "no pen" group, each carrying every
        cell's geometry for layers wearing that pen, in project z-order. The
        physical pen-nib offset (:meth:`_pen_offsets`) is applied AFTER
        placement so registration compensation is not scaled by the cell
        factor. ``pen_id`` restricts the document to one pen group — a single
        plot pass (``""`` selects the no-pen group); ``None`` returns every
        group (export / plan). Call the result through :meth:`_optimize` when
        plotting (the PLOT-PASS crop rectangle — a different, unrelated
        "crop" — applies to sheets too; that is correct)."""
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
                crop=crop, marks=marks)
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
        crop: str = "timeline", marks: bool = False,
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
                                  master_scale_ts=all_ts, crop=crop)

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

    @staticmethod
    def _crop_from_format(fmt: dict[str, Any]) -> str:
        """Read a stored sheet-format dict's crop mode, with a legacy path:
        captures/formats saved before 2026-08-11 carry ``"framing"``
        (``"fixed"``/``"center"``), not ``"crop"``. Old bytes are frozen and
        never rewritten (they stay exactly as baked — see §2c "Trays"), but a
        RE-bake (rebake/relayout, both explicitly re-render against live or
        current state) must still produce something, so both legacy values
        map to ``"timeline"`` — the closer of the two ("fixed" IS today's
        "timeline"; "center" is the banned per-frame mode, and "timeline" is
        the safe default now that it no longer exists)."""
        crop = fmt.get("crop")
        if crop in _CROP_MODES:
            return crop
        return "timeline"

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
                    crop=self._crop_from_format(fmt),
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
        # S7 client mirror (P8/interpolateBlocker): the snapshot itself never
        # rides the wire ("heavy source state never rides the wire" — every
        # group payload excludes it), so the ONE bit the frontend needs to
        # reproduce _captures_compatible's chain refusal has to travel some
        # other way. Stamped here, the single place every stored group
        # (capture, batch, relayout, rebake) passes through, so it can never
        # drift from what _captures_compatible actually sees.
        if snapshot is not None:
            chain_layer = next(
                (l.name for l in snapshot.layers
                 if l.source.type == "tween" and tween.chain_key_ids(l.source.params or {})),
                None,
            )
            fmt = {**fmt, "has_chain": chain_layer is not None, "chain_layer": chain_layer}
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
        crop: str = "timeline",
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
                if crop not in _CROP_MODES:
                    raise ValueError(f"crop must be one of {_CROP_MODES}")
                fmt = {
                    "kind": "sheet", "target": "all",
                    "cols": cols, "rows": rows, "frames": frames,
                    "pages": self.sheet_pages(frames, cols, rows),
                    "t_from": t_from, "t_to": t_to, "margin_mm": margin_mm,
                    "crop": crop, "marks": marks,
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

    #: capture kinds `_documents_for_format` can rebuild straight from the
    #: LIVE project (`self.project`/`self.resolved()`) — see that method.
    #: "batch" is deliberately excluded: it is rendered from two OTHER
    #: captures' frozen snapshots (`_interpolate_batch_docs`), not from live
    #: state, so "re-bake against current project state" does not apply to it.
    _REBAKEABLE_KINDS = ("sheet", "frame", "plot")

    @classmethod
    def rebake_blocked(cls, group: CaptureGroup) -> str | None:
        """Why `group` can't be re-baked from live project state, or None if
        it can. Pure — also drives the tray UI's disabled/tooltip state
        client-side (mirrored in plot.js, same pattern as interpolateBlocker)."""
        if group.kind not in cls._REBAKEABLE_KINDS:
            return (f'"{group.kind}" captures are derived from OTHER captures, '
                     "not the live project — re-bake those instead")
        return None

    def rebake_capture_group(self, group_id: str) -> CaptureGroup:
        """9a: re-run the capture that produced `group` (same kind, same
        layout/format params — `group.format` already carries everything
        `_documents_for_format` needs) against CURRENT project state,
        replacing its sheets in place: same group id, name kept. One
        checkpoint, so one undo restores the group's prior bake untouched
        (groups replace-wholesale here too, never mutate in place — the old
        object stays intact in history)."""
        with self._lock:
            group = self._find_capture(group_id)
            reason = self.rebake_blocked(group)
            if reason:
                raise ValueError(reason)
            docs = self._documents_for_format(group.format)
            pass_ids = self._pass_ids_for_format(group.format)
            if not any(self._doc_has_geometry(doc) for doc in docs):
                raise RuntimeError("nothing to re-bake (no resolved geometry at this capture's settings)")
            snapshot = self._capture_snapshot()
            self._checkpoint()
            old_files = [s.file for s in group.sheets if s.file]
            new_sheets: list[StagedSheet] = []
            for i, doc in enumerate(docs):
                ids_for_sheet = pass_ids[i] if i < len(pass_ids) else None
                sheet = StagedSheet(name=f"sheet {i + 1}", passes=self._pass_stats(doc, ids_for_sheet))
                relname = f"staging/{group.id}-{sheet.id}.svg"
                sheet.file = relname
                for pinfo, layer in zip(sheet.passes, doc.layers):
                    pinfo.name = layer.name or pinfo.name
                new_sheets.append(sheet)
                # ownership handover, no defensive copy — same discipline as
                # _store_capture_group: frozen at store time.
                self.staging_documents[relname] = doc
            for f in old_files:
                self.staging_documents.pop(f, None)
            rebaked = group.model_copy(update={
                "sheets": new_sheets, "snapshot": snapshot, "warnings": [],
            })
            self.project.staging = [rebaked if g.id == group_id else g
                                    for g in self.project.staging]
            return rebaked

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
        for key in ("visible", "pen_id", "occluder", "receives_occlusion", "frame_follow", "name", "effect_seed"):
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
                doc = gencache.generate_cached(src, self._effective_gen_params(out_layer))
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
        old_occlusion = self._occlusion_cache
        try:
            self.project = project
            self.source_geometry = geo
            self.svg_files = svg_files
            self._shaped_cache = {}
            self._tween_cache = {}
            self._clip_cache = {}
            self._occlusion_cache = compose.OcclusionCache()
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
            self._occlusion_cache = old_occlusion
            self._frame_lru = old_frames
            self._frame_bbox = old_bbox

    @staticmethod
    def _captures_compatible(a: CaptureGroup, b: CaptureGroup) -> None:
        """Raise ValueError unless A and B can interpolate: same kind, and for
        sheet captures the same essential shape (cols/rows/frames/t range).
        Presentation-only format fields — margin_mm, crop, marks — may
        differ; the batch inherits A's values with the rest of ``a.format``.

        S7 (docs/plans/timeline-v2.md Q5, narrow ruling): refuse when either
        capture's snapshot carries a keyframe CHAIN — a tween whose ``keys``
        holds more than two entries; ``tween.chain_key_ids`` is THE
        definition (F9's four growths this fence avoids: the tray blend
        lerps ``TweenParams`` field-wise, which has no meaning for a list of
        3+ refs). Video/frame captures are deliberately untouched: a
        ``kind="frame"`` capture already froze one clip frame before it ever
        reaches here, so two of those still blend (Ian: "refuse chains
        only")."""
        if a.kind != b.kind:
            raise ValueError(f"capture kinds do not match ({a.kind} vs {b.kind})")
        if a.kind == "sheet":
            for key in ("cols", "rows", "frames", "t_from", "t_to"):
                if a.format.get(key) != b.format.get(key):
                    raise ValueError(
                        f"sheet layouts do not match: {key} differs "
                        f"({a.format.get(key)} vs {b.format.get(key)})")
        for snap in (a.snapshot, b.snapshot):
            if snap is None:
                continue
            for layer in snap.layers:
                if layer.source.type != "tween":
                    continue
                if tween.chain_key_ids(layer.source.params or {}):
                    raise ValueError(
                        f"cannot interpolate: {layer.name!r} is a keyframe chain "
                        "(tray-to-tray transitions are reserved for simple A/B "
                        "animations — video keeps blending)")

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

    def _interpolate_sheet_group_docs(
        self, a: CaptureGroup, b: CaptureGroup, steps: int, fmt: dict[str, Any],
        name: str,
    ) -> tuple[list[PathDocument], list[list[str]], list[str]]:
        """Q5 amendment (docs/plans/timeline-v2.md §2b — Ian's "2D frame
        matrix"): interpolating two SHEET captures produces one group shaped
        A → blends → B, not a plain step ladder. The frame axis (t_from..t_to
        across each sheet) stays A's/B's own; the blend steps are the second
        axis. The group's first pages are A's OWN state re-rendered at
        ``fmt`` (not a t=0 approximation — exact by construction, since
        that's what "A's state at fmt" means), the last are B's, and the
        interior is the same per-step blend :meth:`_interpolate_batch_docs`
        computes, trimmed to the open interval so the endpoints aren't
        rendered twice. Total sheet count is unchanged from the old plain
        ladder (``steps`` × pages-per-capture) — only how the two end steps
        are produced changed."""
        if a.snapshot is None or b.snapshot is None:
            raise ValueError("both captures need source snapshots")
        a_project, a_geo, a_svg = self._snapshot_state(a.snapshot)
        b_project, b_geo, b_svg = self._snapshot_state(b.snapshot)
        a_docs, a_pass_ids = self._documents_with_temp_state(a_project, a_geo, a_svg, fmt)
        b_docs, b_pass_ids = self._documents_with_temp_state(b_project, b_geo, b_svg, fmt)
        for i, doc in enumerate(a_docs):
            doc.source = f"{a.name} sheet {i + 1}/{len(a_docs)}"
        for i, doc in enumerate(b_docs):
            doc.source = f"{b.name} sheet {i + 1}/{len(b_docs)}"
        warnings: list[str] = []
        mid_docs: list[PathDocument] = []
        mid_pass_ids: list[list[str]] = []
        for i in range(1, steps - 1):
            t = i / (steps - 1)
            project, geo, svg_files, ww = self._interpolate_snapshots(a.snapshot, b.snapshot, t)
            warnings.extend(ww)
            step_docs, step_pass_ids = self._documents_with_temp_state(project, geo, svg_files, fmt)
            for j, doc in enumerate(step_docs):
                doc.source = f"{name} step {i + 1}/{steps} sheet {j + 1}"
                mid_docs.append(doc)
                mid_pass_ids.append(step_pass_ids[j] if j < len(step_pass_ids) else [])
        return (a_docs + mid_docs + b_docs, a_pass_ids + mid_pass_ids + b_pass_ids,
                sorted(set(warnings)))

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
            batch_name = name or "interpolated batch"
            if a.kind == "sheet":
                docs, pass_ids, warnings = self._interpolate_sheet_group_docs(
                    a, b, steps, a.format, batch_name)
            else:
                docs, pass_ids, warnings = self._interpolate_batch_docs(
                    a, b, steps, a.format, batch_name)
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
        margin_mm: float | None = None, crop: str | None = None,
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
        if crop is not None and crop not in _CROP_MODES:
            raise ValueError(f"crop must be one of {_CROP_MODES}")
        with self._lock:
            group = self._find_capture(group_id)
            source_kind = group.format.get("source_kind") if group.kind == "batch" else group.kind
            if source_kind != "sheet":
                raise ValueError(
                    f"re-layout applies to grid-sheet captures only, not {group.kind!r}")
            # new sheet-format: keep the timeline shape, swap the grid. Drop
            # any stale legacy "framing" key so it can't shadow an explicit
            # new "crop" (_crop_from_format prefers "crop" either way, but
            # this keeps a re-laid group's format clean going forward).
            fmt = {k: v for k, v in group.format.items()
                   if k not in ("kind", "source_kind", "variants", "framing")}
            fmt["kind"] = "sheet"
            fmt["cols"], fmt["rows"] = cols, rows
            if margin_mm is not None:
                fmt["margin_mm"] = margin_mm
            fmt["crop"] = crop if crop is not None else self._crop_from_format(group.format)
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
                # source_kind is always "sheet" here (validated above), so this
                # is always the grouped A→blends→B shape (Q5 amendment) —
                # re-rendered at the NEW grid, not literal copies of the old
                # sheets, which is the entire point of a re-layout.
                docs, pass_ids, warnings = self._interpolate_sheet_group_docs(a, b, steps, fmt, name)
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
            data["effect_seed"] = None  # ordinary copies get independent fields
            del data["id"]  # CanvasLayer mints a fresh one
            data["name"] = f"{layer.name} copy"
            copy = CanvasLayer(**data)
            copy.source.file = None  # snapshot belongs to the original; rewritten on save
            idx = self.project.layers.index(layer)
            self.project.layers.insert(idx + 1, copy)
            self.source_geometry[copy.id] = self.source_geometry.get(layer_id, [])
            return copy

    def split_hatch_layer(self, layer_id: str, step: int | None = None) -> CanvasLayer:
        """Move a ``hatch_fill`` step's FILL onto a layer of its own, so the
        fill can plot with a different pen from the outline it fills.

        A pen is a property of a layer (``CanvasLayer.pen_id``) — plot passes,
        pen registration offsets and SVG export all group by it — while hatch
        lines are just paths inside one layer. So "hatch on a different pen"
        is a two-layer arrangement, and this builds it in one undo step:

        * a new layer directly above, same source/transform/effects, with the
          hatch step's ``outline`` turned off (fill only) and no pen assigned,
          so it is its own plot pass immediately and the operator picks the pen;
        * the original keeps everything else but loses the hatch step, so it
          draws the outline alone — and keeps occluding as a solid, since
          occlusion masks come from filled outlines (see hatch_fill's module
          docstring; the fill-only copy deliberately no longer occludes).

        Above, not below, because a filled occluder must not end up on top of
        its own fill. Pass order follows layer order, so an operator who wants
        the fill laid down before the outline reorders the two.

        Effects *after* the hatch step are copied to both layers, where they
        then see different input (outline only / fill only) — which is the
        point, but worth knowing if the tail of the stack is doing something
        that assumed both.
        """
        with self._lock:
            layer = self.project.layer(layer_id)
            if step is None:
                step = next((i for i, s in enumerate(layer.effects)
                             if s.effect == "hatch_fill"), None)
                if step is None:
                    raise ValueError("layer has no hatch_fill step to split")
            if not (0 <= step < len(layer.effects)):
                raise ValueError(f"no effect step {step} on this layer")
            if layer.effects[step].effect != "hatch_fill":
                raise ValueError(f"step {step} is {layer.effects[step].effect!r}, not hatch_fill")
            self._checkpoint()

            fill_data = layer.model_dump()
            fill_data["effect_seed"] = None
            del fill_data["id"]  # CanvasLayer mints a fresh one
            fill_data["name"] = f"{layer.name} · hatch"
            fill_data["pen_id"] = None
            fill_data["effects"][step]["params"] = {
                **fill_data["effects"][step]["params"], "outline": False,
            }
            fill = CanvasLayer(**fill_data)
            fill.source.file = None  # the snapshot belongs to the original

            outline_data = layer.model_dump()  # keeps the id
            outline_data["effects"].pop(step)
            outline = CanvasLayer(**outline_data)

            idx = self.project.layers.index(layer)
            self.project.layers[idx] = outline
            self.project.layers.insert(idx + 1, fill)
            # shared by reference: source geometry is only ever replaced
            # wholesale, never mutated in place
            self.source_geometry[fill.id] = self.source_geometry.get(layer_id, [])
            return fill

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
            # a fresh hand per band, and a different stack every press — the
            # presets name no seed, so every stack used to come out identical
            params = self._rolled_seed(src, params)
            doc = gencache.generate_cached(src, params)
            paths = [p for lyr in doc.layers for p in lyr.paths]
            generated.append((
                spec, params, paths,
                self._placement_transform(spec["generator"], params, doc, paths),
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

    def add_separation_stack(
        self,
        generator_id: str,
        params: dict[str, Any],
        plates: list[dict[str, Any]],
        misregistration_mm: float = 0.0,
        seed: int = 0,
    ) -> list[CanvasLayer]:
        """Separate one image into plates — one ordinary generator layer each,
        in a single undo step.

        A **plate** is ``{"name", "generator"?, "params", "pen_id"?}``. It
        carries a params *override* rather than a channel, which is what lets
        colour separation (``{"channel": "c"}``) and tonal separation
        (``{"tone_from": 0, "tone_to": 0.33}``) share this whole path — the
        same shape ``LINEART_STACK_PRESETS`` entries already use.

        A plate may also name its **own generator**: cyan as halftone dots,
        magenta as squiggles, black as traced edges. Params carry across a
        generator switch by keeping only the fields the target actually
        declares, so the merge can never build an invalid params dict; the
        rest fall to that generator's defaults. Omitting ``generator`` means
        "same as the base", which is the ordinary case.

        Nothing links the resulting layers — they are N normal layers that
        happen to share a placement, each with its own effect stack, pen,
        transform and timeline behaviour. That is the whole point: a plate is
        not a special kind of layer, so everything already works on it.
        """
        if not plates:
            raise ValueError("pick at least one plate to separate into")
        base_src = get_source(generator_id)
        if "channel" not in base_src.Params.model_fields:
            raise ValueError(
                f"{base_src.label!r} has no channel to separate — pick an "
                "image-based generator")

        # One seed for the whole separation, not one per plate: the plates are
        # one artwork in several inks, so they should share a hand. Per-plate
        # variation is then something you dial in deliberately rather than
        # something you get by accident.
        params = self._rolled_seed(base_src, params)

        # Generate everything BEFORE mutating (add_lineart_stack's discipline):
        # a failure mid-stack must not leave a partial separation behind.
        generated: list[tuple[dict[str, Any], str, dict[str, Any], list[Path], Affine]] = []
        for i, plate in enumerate(plates):
            gen_id = plate.get("generator") or generator_id
            src = get_source(gen_id)
            merged = {**params, **plate.get("params", {})}
            if gen_id != generator_id:
                merged = {k: v for k, v in merged.items() if k in src.Params.model_fields}
            doc = gencache.generate_cached(src, merged)
            paths = [p for lyr in doc.layers for p in lyr.paths]
            transform = self._placement_transform(gen_id, merged, doc, paths)
            if misregistration_mm > 0:
                transform = self._misregister(transform, misregistration_mm, seed, i)
            generated.append((plate, gen_id, merged, paths, transform))

        with self._lock:
            self._checkpoint()
            created: list[CanvasLayer] = []
            for plate, gen_id, merged, paths, transform in generated:
                label = get_source(gen_id).label
                layer = CanvasLayer(
                    name=f"{label} · {plate['name']}",
                    source=LayerSource(type="generator", generator=gen_id, params=merged),
                    transform=transform,
                    pen_id=plate.get("pen_id") or None,
                    frame_follow=self._sequence_driven(gen_id, merged),
                )
                self.project.layers.append(layer)
                self.source_geometry[layer.id] = paths
                self._snapshot_pen(layer.pen_id)
                created.append(layer)
            return created

    @staticmethod
    def _rolled_seed(module: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Fill in a random ``seed`` if the module has one and the caller
        didn't pick a value.

        The Compose form rolls a seed client-side before it POSTs, but nothing
        that creates layers server-side went through a form — the lineart and
        separation stacks, and any scripted call — so those all landed on seed
        0 and every invocation produced the identical drawing. Rolled once at
        creation and stored in the layer's params, so the layer is still
        reproducible forever after; this randomises where you START.

        Only an INTEGER field named exactly ``seed``. ``fast_marching_topo``
        has ``seed_x``/``seed_y`` — those are where the wavefront begins, and
        randomising them would move the picture instead of varying it.
        """
        field = module.Params.model_fields.get("seed")
        if field is None or "seed" in params or field.annotation is not int:
            return params
        top = 99999
        for meta in field.metadata:  # pydantic keeps le/ge as annotated-types
            top = getattr(meta, "le", None) or top
        return {**params, "seed": random.randint(0, int(top))}

    @staticmethod
    def _misregister(transform: Affine, amount_mm: float, seed: int, index: int) -> Affine:
        """Nudge a plate off perfect registration by up to ``amount_mm``.

        Offset printing's charm is that the plates never land quite on top of
        one another. This is only a translation composed into the layer's own
        affine — so it is undoable, hand-editable afterwards, and zero is exact
        identity. Seeded per (seed, index) so the same press gives the same
        drift every time."""
        rng = random.Random(f"misregistration:{seed}:{index}")
        angle = rng.uniform(0, 2 * math.pi)
        radius = amount_mm * math.sqrt(rng.random())  # uniform over the disc
        return transform.model_copy(update={
            "e": transform.e + radius * math.cos(angle),
            "f": transform.f + radius * math.sin(angle),
        })

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
            # Sharing the existing field preserves the original drawing and
            # keeps an untouched A/B animation static, for every effect.
            data["effect_seed"] = compose.layer_effect_seed(layer)
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

    def rehearse_layer(self, layer_id: str, moments: int = 4) -> list[CanvasLayer]:
        """Stamp several moments of one process onto the sheet — pencil
        rehearsals under a committed stroke, which is what makes a drawing
        show its own history.

        A moment is nothing but the layer's own generator re-run with a
        different value on its TIME AXIS: no tween, no baking, no new
        machinery. ``moments`` values are spread evenly across the axis's own
        declared bounds (:meth:`axis_bounds`), not the layer's current value —
        the rehearsal covers the whole process, not just the neighbourhood of
        where this particular layer happens to sit today. Each moment is an
        ORDINARY generator layer, inserted just below the original (still on
        top, still the "ink"), and stays exactly as live and re-editable as
        any other layer — nothing here is frozen or baked.

        This is nearly free FOR A ``ProcessModule`` SOURCE. The trajectory
        cache (Task 3) keys on every param EXCEPT the time axis by design —
        that is the whole trick behind scrubbing — so every moment below hits
        the SAME cached trajectory and only slices a different prefix of it:
        N moments cost one process run, not N. A generator reached only
        through the plain ``frame`` fallback (an image generator with no
        declared ``time_axis``) has no trajectory cache to share — each
        moment is its own ``generate()`` call, memoised by `gencache` like
        any other, so N moments cost N (cheap) calls rather than one shared
        run.

        Follows ``add_separation_stack``'s shape, not ``animate_layer``'s:
        every moment's geometry is generated BEFORE anything is mutated, then
        one ``_checkpoint()`` takes the whole project at once and every layer
        is appended directly — no other checkpointing method is called along
        the way, so this is one undo step, not several."""
        layer = self.project.layer(layer_id)
        if layer.source.type not in ("generator", "baked") or not layer.source.generator:
            raise RuntimeError(f"{layer.name} was not generated; nothing to rehearse")
        if moments < 2:
            raise ValueError("rehearse needs at least 2 moments")
        generator_id = layer.source.generator
        axis = self.time_axis(generator_id)
        bounds = self.axis_bounds(generator_id, axis) if axis else None
        if not axis or not bounds:
            raise RuntimeError(f"{layer.name} has no time axis to rehearse along")

        src = get_source(generator_id)
        base = dict(layer.source.params or {})
        is_int_axis = src.Params.model_fields[axis].annotation is int
        lo, hi = bounds
        span = hi - lo

        # Generate every moment BEFORE mutating anything — a failure partway
        # through must not leave a partial rehearsal behind.
        generated: list[tuple[dict[str, Any], list[Path]]] = []
        for i in range(moments):
            frac = i / (moments - 1) if moments > 1 else 0.0
            value: float = lo + frac * span
            if is_int_axis:
                value = int(round(value))
            params = {**base, axis: value}
            doc = gencache.generate_cached(src, params)
            paths = [p for lyr in doc.layers for p in lyr.paths]
            generated.append((params, paths))

        with self._lock:
            self._checkpoint()
            idx = self.project.layers.index(layer)
            created: list[CanvasLayer] = []
            for offset, (params, paths) in enumerate(generated):
                moment = CanvasLayer(
                    name=f"{layer.name} · moment {offset + 1}/{moments}",
                    source=LayerSource(type="generator", generator=generator_id, params=params),
                    transform=layer.transform.model_copy(),
                    # Effects carry — a rehearsal should look like the thing
                    # being rehearsed (a process read through ``freehand``
                    # must rehearse in the same hand). ``pen``, ``occluder``
                    # and ``region`` stay at their CanvasLayer defaults on
                    # purpose: the pen is precisely what you want to differ
                    # (pencil under ink), and occluder/region are layer
                    # ROLES rather than appearance — inheriting them would
                    # make every moment clip the layers below it.
                    effects=[e.model_copy(deep=True) for e in layer.effects],
                )
                self.project.layers.insert(idx + offset, moment)
                self.source_geometry[moment.id] = paths
                created.append(moment)
            return created

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
            shaped = compose.shape_layer(
                layer, self.source_geometry.get(layer_id, []),
                compose.guide_page(self.project),
                compose.line_diameter_for(layer, self.pens()))
            self.source_geometry[layer_id] = shaped
            layer.transform = Affine()
            layer.effects = []
            layer.source.type = "baked"
            layer.source.file = None  # snapshot is stale; rewritten on save
            self._shaped_cache.pop(layer_id, None)
            return layer

    def merge_layers(self, layer_ids: list[str]) -> CanvasLayer:
        """Consolidate several layers and join them into one.

        The layers-area button. Each selected layer is baked exactly as
        ``consolidate_effects`` bakes one — transform and effect stack shaped
        into paper-space geometry — and the results are concatenated in STACK
        ORDER (bottom first, so the drawing order is preserved) into the
        top-most selected layer, which survives with its own name, pen and
        position. The others are deleted. One checkpoint, so one undo puts them
        all back.

        Two refusals rather than guesses. A selection mixing occluders (or
        regions) with ordinary layers has no honest answer: an occluder masks
        what is below it and a region reshapes it, and plain baked geometry can
        express neither, so merging one into the other would quietly change
        what the sheet does. And tween layers are not merged at all — a tween
        is a live relationship between two keyframes, not geometry that happens
        to be somewhere.

        One consequence worth knowing, inherent to merging rather than to this
        implementation: if the selection is NOT contiguous, a layer left
        between two merged ones no longer sits between them, so its occlusion
        of the lower member is lost. The pixels move because the stack changed,
        which is what merging means.
        """
        with self._lock:
            if len(set(layer_ids)) < 2:
                raise ValueError("merge needs at least two layers")
            order = [l.id for l in self.project.layers]
            chosen = [self.project.layer(i) for i in layer_ids]
            if any(l.source.type == "tween" for l in chosen):
                raise ValueError("cannot merge a tween layer: it is a relationship "
                                 "between keyframes, not geometry")
            if len({l.occluder for l in chosen}) > 1:
                raise ValueError("cannot merge an occluder with a normal layer — "
                                 "baked geometry cannot mask what is below it")
            if len({l.region for l in chosen}) > 1:
                raise ValueError("cannot merge a region with a normal layer — "
                                 "baked geometry cannot reshape what is below it")

            self._checkpoint()
            self._materialize_tweens()  # a stale tween must bake its CURRENT look
            chosen.sort(key=lambda l: order.index(l.id))
            page = compose.guide_page(self.project)
            merged: list[Path] = []
            for layer in chosen:
                merged.extend(compose.shape_layer(
                    layer, self.source_geometry.get(layer.id, []), page,
                    compose.line_diameter_for(layer, self.pens())))

            survivor = chosen[-1]
            self.source_geometry[survivor.id] = merged
            survivor.transform = Affine()
            survivor.effects = []
            survivor.source.type = "baked"
            survivor.source.file = None  # snapshot is stale; rewritten on save
            self._shaped_cache.pop(survivor.id, None)
            for layer in chosen[:-1]:
                self._shaped_cache.pop(layer.id, None)
                self.source_geometry.pop(layer.id, None)
                self.project.layers = [l for l in self.project.layers
                                       if l.id != layer.id]
            self._occlusion_cache.clear()
            return survivor

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
                self.project, geo, self.pens(), self._shaped_cache,
                self._occlusion_cache,
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
            layer_map = self._clip_cache.get(layer.id)
            hit = layer_map.get(key) if layer_map is not None else None
            if hit is not None:
                layer_map.move_to_end(key)
                overrides[layer.id] = hit.paths  # same object -> shaped cache re-hits
                continue
            try:
                doc = gencache.generate_cached(gen, self._effective_gen_params(layer, master_t))
                paths = [p for lyr in doc.layers for p in lyr.paths]
            except Exception:
                continue  # fall back to stored base geometry for this layer
            if layer_map is None:
                layer_map = self._clip_cache[layer.id] = OrderedDict()
            layer_map[key] = _ClipFollowEntry(paths, sum(len(p.points) for p in paths))
            layer_map.move_to_end(key)
            _evict_tween_caches((self._tween_cache, self._clip_cache), (1, layer.id, key))
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
                # window+curve mapping: the ONE helper in tween.py, also used
                # by effective_generator's nested-tween sampling — see
                # tween.resolve_local_t's docstring for why this must not
                # drift into a second copy of the formula.
                override_t = tween.resolve_local_t(params, clamped_master)
            refs = []
            #: the endpoint geometry lists whose id() the key embeds — the
            #: entry holds them so no collected list's id can be recycled into
            #: a false hit (see _TweenEntry)
            ref_objects: list[list[Path]] = []
            for rid in self._tween_refs(layer):
                try:
                    ref = self.project.layer(rid)
                    ref_geo = read_geo.get(ref.id)
                    if ref_geo is not None:
                        ref_objects.append(ref_geo)
                    refs.append({
                        "src": ref.source.model_dump(),
                        "tf": ref.transform.model_dump(),
                        "fx": [s.model_dump() for s in ref.effects],
                        **({"effect_seed": compose.layer_effect_seed(ref)}
                           if any(s.enabled for s in ref.effects) else {}),
                        "geo": id(ref_geo),
                        "fo": ref.frame_offset,
                        "ff": ref.frame_follow,
                    })
                except KeyError:
                    refs.append(None)
            key_data = {
                "refs": refs, "p": params, "mt": override_t,
                "master": clamped_master,
            }
            # Endpoint effects run while materialising the tween and see the
            # pen assigned to the tween output. Keep the historic key bytes
            # unchanged when no enabled effect can observe that width.
            if any(ref and any(s.get("enabled", True) for s in ref["fx"])
                   for ref in refs):
                key_data["pen_width"] = compose.line_diameter_for(layer, self.pens())
            key = json.dumps(key_data, sort_keys=True)
            layer_map = self._tween_cache.get(layer.id)
            hit = layer_map.get(key) if layer_map is not None else None
            if hit is not None:
                layer_map.move_to_end(key)
                # the SAME list object every time this key comes round, which
                # is what lets compose's id(src)-keyed shaped cache re-hit
                self.source_geometry[layer.id] = hit.paths
                if geo is not None:
                    geo[layer.id] = hit.paths
                continue
            paths = tween.materialize(
                layer, self.project, read_geo, override_t, clamped_master,
                compose.line_diameter_for(layer, self.pens()))
            if layer_map is None:
                layer_map = self._tween_cache[layer.id] = OrderedDict()
            layer_map[key] = _TweenEntry(paths, tuple(ref_objects),
                                         sum(len(p.points) for p in paths))
            layer_map.move_to_end(key)
            _evict_tween_caches((self._tween_cache, self._clip_cache), (0, layer.id, key))
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

    # -- interrupted-plot fragments --------------------------------------------

    def interrupt_fragment(
        self,
        seed: int = 0,
        start: float | None = None,
        stop: float | None = None,
        optimized: bool = True,
    ) -> tuple[CanvasLayer, float, float]:
        """Recreate a plot that was interrupted: the WHOLE resolved project in
        draw order, keeping only a contiguous pen-down slice — a random start
        spot, an early stop, strokes cut mid-line exactly where the pen would
        have lifted. The fragment becomes ONE baked layer on top.

        Order basis: ``optimized=True`` runs the flatten through
        :meth:`_optimize` first, so an active plot-pass optimisation
        (linesort/merge/reloop/crop) gives the order the machine would really
        have drawn — nib compensation is NOT applied (it only shifts where the
        carriage goes; the ink lands at resolved positions).

        ``start``/``stop`` are fractions of total pen-down distance; either
        left None is rolled from ``seed`` (deterministic per seed — rerolling
        the same seed recreates the same fragment). Returns the new layer and
        the (rolled or given) fractions so the UI can show what the seed
        picked. One undo step.

        Known approximation: the slice is taken from post-occlusion geometry,
        so regions hidden under layers that "hadn't been drawn yet" stay
        hidden — this recreates the PLANNED plot stopped early."""
        with self._lock:
            doc = self.resolved_document("all")  # flatten skips hidden layers
            if optimized:
                doc = self._optimize(doc)
            flat = [p for _layer, p in doc.iter_paths()]
            total = sum(p.length() for p in flat)
            if total <= 0:
                raise RuntimeError("nothing to interrupt (no pen-down geometry)")

            rng = random.Random(seed)
            a = start if start is not None else rng.uniform(0.0, 1.0)
            b = stop if stop is not None else rng.uniform(0.0, 1.0)
            a, b = min(a, b), max(a, b)
            a = min(max(a, 0.0), 1.0)
            b = min(max(b, 0.0), 1.0)
            if b - a < 0.01:  # never a sliver — keep the fragment readable
                b = min(1.0, a + 0.01)
                if b - a < 0.01:
                    a = b - 0.01
            d0, d1 = a * total, b * total

            fragment: list[Path] = []
            cum = 0.0
            for p in flat:
                plen = p.length()
                lo, hi = cum, cum + plen
                cum = hi
                if hi <= d0 or lo >= d1:
                    continue
                if len(p.points) < 2:
                    fragment.append(Path(points=list(p.points), filled=False))
                    continue
                pts = _subpath_by_distance(p.points, d0 - lo, d1 - lo)
                if len(pts) >= 2:
                    # filled=False always: a cut fill outline is just a line,
                    # exactly like the ink of a real interrupted stroke
                    fragment.append(Path(points=pts, filled=False))
            if not fragment:
                raise RuntimeError("the rolled slice contains no strokes")

            self._checkpoint()
            layer = CanvasLayer(
                name=f"interrupted {a * 100:.0f}–{b * 100:.0f}%",
                source=LayerSource(type="baked"),
                transform=Affine(),
            )
            self.project.layers.append(layer)
            self.source_geometry[layer.id] = fragment
            return layer, a, b

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
        if backend_id == "native" and "model" in values:
            manager.sync_limits_for_model(validated.model)
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
