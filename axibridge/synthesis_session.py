"""Synthesis: keep a score as a group of layers (the chorus pattern, S4).

Design §10 (Ian's decision 1): Keep makes one app layer per score layer, each
on its pen, all resolving the same score and showing one layer, plus a
Measure layer when devices are on. One undo step. A kept group reopens in the
bench; keeping it again (`replace`) swaps the group's members in place, in
the same undo step, keeping the group and where Ian moved it.

Every member is an ordinary `synthesis` layer: the same params (library
snapshot + pins completed ONCE, so every member resolves the very same
played sheet) plus `show` = "layer" and `layer` = its score layer id, or
`show` = "measure". Resolve stays the one path: each member resolves on its
own and keeps only its own inks (`engine.play` memoises the sheet).

Pens: each score layer's Flexoki ink goes to a pen of exactly that colour in
the pen library, a different pen per member; missing pens are added
(`gesture_studies_session.voice_pens`, one implementation).
"""
from __future__ import annotations

from typing import Any

from .compose import CanvasLayer, LayerGroup, LayerSource
from .gesture_studies_session import measure_pen, voice_pens
from .stores import pen_library

SOURCE = "synthesis"


class SynthesisSessionMixin:
    def keep_synthesis(self, params: dict[str, Any], replace: str | None = None) -> tuple[LayerGroup, list[CanvasLayer]]:
        """Keep a score as a group: one layer per score layer that drew, on its pen, plus a Measure
        layer when devices drew. `replace`: the id of a kept synthesis group to swap in place."""
        with self.render_work.mutation():          # obsolete preview readers stop first
            return self._keep_synthesis(params, replace)

    def _keep_synthesis(self, params: dict[str, Any], replace: str | None):
        from . import gencache  # noqa: PLC0415
        from .groups import validate_hierarchy  # noqa: PLC0415
        from .registry import get_source  # noqa: PLC0415
        from .sources._synthesis import engine as EN  # noqa: PLC0415
        from .sources.synthesis import MEASURE_NAME  # noqa: PLC0415

        src = get_source(SOURCE)
        base = {k: v for k, v in params.items() if k not in ("show", "layer")}
        base = self._completed(src, base)                     # pin once: every member, the same sheet
        p = src.Params(**base)
        sheet, _ = EN.play(p.score, p._lib)
        _, groups = EN.layer_paths(sheet, p.score)
        if not groups:
            raise ValueError("the score drew nothing to keep")
        flex = EN.flexoki()
        made = []
        for g in groups:
            mp = {**base, "show": "measure"} if g["id"] == EN.MEASURE else {**base, "show": "layer", "layer": g["id"]}
            doc = gencache.generate_cached(src, mp)
            paths = [q for layer in doc.layers for q in layer.paths]
            if paths:
                made.append((g, mp, doc, paths))
        label = p.score.get("label") or "Synthesis"
        drawn = [m for m in made if m[0]["id"] != EN.MEASURE]
        measure = next((m for m in made if m[0]["id"] == EN.MEASURE), None)
        pens = voice_pens([{"color": flex.get(g["pen"], EN.INK), "ink": g["pen"]} for g, *_ in drawn])
        mpen = measure_pen(measure[2].layers[0].color, set(pens)) if measure else None
        pen_of = {id(m): pen for m, pen in zip(drawn, pens)}
        if measure:
            pen_of[id(measure)] = mpen
        all_paths = [q for *_, paths in made for q in paths]
        with self._lock:
            candidate = self._hierarchy_candidate()
            old: list[CanvasLayer] = []
            group = None
            if replace is not None:
                group = next((g for g in candidate.groups if g.id == replace), None)
                if group is None:
                    raise KeyError(f"group {replace} not found")
                old = [layer for layer in candidate.layers if layer.group_id == group.id]
                if not old or any(layer.source.type != "generator" or layer.source.generator != SOURCE
                                  for layer in old):
                    raise ValueError("only a kept synthesis group (its members, no other layers) can be replaced")
                gone_ids = {layer.id for layer in old}
                if any(layer.animation_owner_id in gone_ids
                       or (layer.source.type == "tween" and set(self._tween_refs(layer)) & gone_ids)
                       for layer in candidate.layers if layer.id not in gone_ids):
                    raise ValueError("an interpolation or animation uses a member of this group: keep as a new group")
                group.name = label
            transform = (old[0].transform.model_copy() if old
                         else self._placement_transform(SOURCE, made[0][1], made[0][2], all_paths))
            if group is None:
                group = LayerGroup(name=label)
                candidate.groups.append(group)
            members = [CanvasLayer(name=MEASURE_NAME if g["id"] == EN.MEASURE else (g["label"] or g["id"]),
                                   group_id=group.id, pen_id=pen_of[id(m)],
                                   source=LayerSource(type="generator", generator=SOURCE, params=mp),
                                   transform=transform.model_copy())
                       for m in made for g, mp, _doc, _paths in [m]]
            if old:
                at = candidate.layers.index(old[0])
                gone = {layer.id for layer in old}
                rest = [layer for layer in candidate.layers if layer.id not in gone]
                at = sum(1 for layer in candidate.layers[:at] if layer.id not in gone)
                candidate.layers = rest[:at] + members + rest[at:]
            else:
                candidate.layers.extend(members)
            validate_hierarchy(candidate)
            for pen_id in [*pens, mpen]:
                pen = pen_library.get(pen_id) if pen_id else None
                if pen:
                    candidate.pens_used[pen.id] = pen
            self._checkpoint()
            self.project = candidate
            for layer in old:
                for cache in (self.source_geometry, self._shaped_cache, self._tween_cache, self._clip_cache):
                    cache.pop(layer.id, None)
            for layer, (*_, paths) in zip(members, made):
                self.source_geometry[layer.id] = paths
        return group, members
