"""Gesture Studies: keep a voices study (the chorus) as a group of layers.

Ian (2026-10-17, Studies v2): "Keep creates a layer GROUP named after the
study; inside, one layer per voice, each assigned its own pen/colour. Moving
or hiding the group moves all voices; each pen plots as its own pass."

Every member is an ordinary `gesture_studies` layer: the same pinned params
(library snapshot + pins, completed ONCE so every voice resolves the very same
recipe) plus `voice` = which part it draws. Resolve stays the one path: each
layer resolves on its own and keeps only its voice's ink. One undo checkpoint
for the whole keep (groups: docs/LAYER-GROUPS.md).

Pens: each voice ink (a Flexoki 600 accent) goes to a pen of exactly that
colour in the pen library, a different pen per voice; when the library has
none, a pen named after the ink is added to it (so the next chorus reuses it).

Measuring devices (study bench v3, move G): a study kept with devices on is a
group too — the drawing's layer (or one per voice) plus ONE "Measure" layer
holding the device inks, on its own pen, so the readings can be hidden,
deleted or plotted on their own. Every member carries the same pinned params
and devices (`show` says which part it draws), so they resolve the same sheet
and stay in register. One undo step, like the chorus.
"""
from __future__ import annotations

from typing import Any

from .compose import CanvasLayer, LayerGroup, LayerSource
from .stores import Pen, pen_library

SOURCE = "gesture_studies"


def _hex(c: str) -> str:
    return c.strip().lower()


def measure_pen(color: str, used: set[str]) -> str:
    """The Measure layer's pen: a library pen of exactly its colour that no
    drawing layer of this keep uses; added when there is none."""
    want = _hex(color)
    pen = next((p for p in sorted(pen_library.all(), key=lambda p: (p.name, p.id))
                if _hex(p.color) == want and p.id not in used), None)
    if pen is None:
        from .sources._gesture_studies.studies import flexoki  # noqa: PLC0415
        name = next((n for n, c in sorted(flexoki().items()) if _hex(c) == want), color)
        taken = any(_hex(p.color) == want for p in pen_library.all())
        pen = pen_library.upsert(Pen(name=f"Flexoki {name}{' (measure)' if taken else ''}", color=color))
    return pen.id


def voice_pens(voices: list[dict]) -> list[str]:
    """One distinct library pen per voice, by exact colour; missing ones are
    created ("Flexoki red", …). Returns pen ids in voice order."""
    used: set[str] = set()
    out = []
    for v in voices:
        want = _hex(v["color"])
        pen = next((p for p in sorted(pen_library.all(), key=lambda p: (p.name, p.id))
                    if _hex(p.color) == want and p.id not in used), None)
        if pen is None:
            pen = pen_library.upsert(Pen(name=f"Flexoki {v['ink']}", color=v["color"]))
        used.add(pen.id)
        out.append(pen.id)
    return out


class GestureStudiesSessionMixin:
    def keep_gesture_study_voices(self, params: dict[str, Any]) -> tuple[LayerGroup, list[CanvasLayer]]:
        """Keep a voices study as a group with one layer per voice (one undo
        step). `params` are the bench's params (any `voice` is ignored: the
        whole chorus is kept)."""
        with self.render_work.mutation():          # obsolete preview readers stop first
            return self._keep_voices(params)

    def keep_gesture_study_measured(self, params: dict[str, Any]) -> tuple[LayerGroup, list[CanvasLayer]]:
        """Keep a study with measuring devices as a group: the drawing (one
        layer, or one per voice on its own pen) and a Measure layer of the
        device inks on its own pen — one undo step."""
        with self.render_work.mutation():
            return self._keep_measured(params)

    def _keep_measured(self, params: dict[str, Any]) -> tuple[LayerGroup, list[CanvasLayer]]:
        from . import gencache  # noqa: PLC0415
        from .groups import validate_hierarchy  # noqa: PLC0415
        from .registry import get_source  # noqa: PLC0415
        from .sources._gesture_studies import studies as ST  # noqa: PLC0415
        from .sources.gesture_studies import MEASURE_NAME  # noqa: PLC0415

        src = get_source(SOURCE)
        base = {k: v for k, v in params.items() if k not in ("voice", "show")}
        base = self._completed(src, base)                     # pin once: every member, the same sheet
        p = src.Params(**base)
        if not p.devices:
            raise ValueError("no measuring devices are on: keep the study as usual")
        label = p.study.label
        voices = ST.voices_of(p.study, p.run_recipe)
        wanted = ([(f"{label} · {v['ink']}", {**base, "voice": v["index"], "show": "drawing"}, v) for v in voices]
                  if voices else [(label, {**base, "show": "drawing"}, None)])
        drawn = []
        for name, mp, v in wanted:
            doc = gencache.generate_cached(src, mp)
            paths = [q for layer in doc.layers for q in layer.paths]
            if paths:                       # an ink this drawing does not use is no layer
                drawn.append((name, mp, v, doc, paths))
        mparams = {**base, "show": "measure"}
        mdoc = gencache.generate_cached(src, mparams)
        mpaths = [q for layer in mdoc.layers for q in layer.paths]
        if not mpaths:
            raise ValueError(f"the measuring devices found nothing to read in {label}; turn on another one")
        if not drawn:
            raise ValueError(f"{label} drew nothing to keep")
        all_paths = [q for *_, paths in drawn for q in paths] + mpaths
        transform = self._placement_transform(SOURCE, mparams, mdoc, all_paths)
        pens = voice_pens([v for _, _, v, _, _ in drawn]) if voices else [None] * len(drawn)
        mpen = measure_pen(mdoc.layers[0].color, {x for x in pens if x})
        under = all(d["place"] == "under" for d in p.devices)
        with self._lock:
            candidate = self._hierarchy_candidate()
            group = LayerGroup(name=label)
            candidate.groups.append(group)
            members = [(CanvasLayer(name=name, group_id=group.id, pen_id=pen_id,
                                    source=LayerSource(type="generator", generator=SOURCE, params=mp),
                                    transform=transform.model_copy()), paths)
                       for (name, mp, _v, _doc, paths), pen_id in zip(drawn, pens)]
            measure = (CanvasLayer(name=MEASURE_NAME, group_id=group.id, pen_id=mpen,
                                   source=LayerSource(type="generator", generator=SOURCE, params=mparams),
                                   transform=transform.model_copy()), mpaths)
            # pen order: a Measure laid under the drawing plots (and stacks) first
            members = [measure, *members] if under else [*members, measure]
            candidate.layers.extend(layer for layer, _ in members)
            validate_hierarchy(candidate)
            for pen_id in [*pens, mpen]:
                pen = pen_library.get(pen_id) if pen_id else None
                if pen:
                    candidate.pens_used[pen.id] = pen
            self._checkpoint()
            self.project = candidate
            for layer, paths in members:
                self.source_geometry[layer.id] = paths
        return group, [layer for layer, _ in members]

    def _keep_voices(self, params: dict[str, Any]) -> tuple[LayerGroup, list[CanvasLayer]]:
        from . import gencache  # noqa: PLC0415
        from .groups import validate_hierarchy  # noqa: PLC0415
        from .registry import get_source  # noqa: PLC0415
        from .sources._gesture_studies import studies as ST  # noqa: PLC0415

        src = get_source(SOURCE)
        base = {k: v for k, v in params.items() if k != "voice"}
        base = self._completed(src, base)                     # pin once: every voice, the same recipe
        p = src.Params(**base)
        voices = ST.voices_of(p.study, p.run_recipe)
        if not voices:
            raise ValueError(f"{p.study.label} is not a voices study; keep it as one layer")
        made = []
        for v in voices:
            vp = {**base, "voice": v["index"]}
            doc = gencache.generate_cached(src, vp)
            paths = [q for layer in doc.layers for q in layer.paths]
            if paths:                       # an ink this drawing does not use is no layer (e.g. no tint cover)
                made.append((v, vp, doc, paths))
        if not made:
            raise ValueError(f"{p.study.label} drew nothing to keep")
        voices = [v for v, *_ in made]
        all_paths = [q for *_, paths in made for q in paths]
        transform = self._placement_transform(SOURCE, made[0][1], made[0][2], all_paths)
        pens = voice_pens(voices)
        with self._lock:
            candidate = self._hierarchy_candidate()
            group = LayerGroup(name=p.study.label)
            candidate.groups.append(group)
            layers = []
            for (v, vp, _doc, _paths), pen_id in zip(made, pens):
                layers.append(CanvasLayer(
                    name=f"{p.study.label} · {v['ink']}", group_id=group.id, pen_id=pen_id,
                    source=LayerSource(type="generator", generator=SOURCE, params=vp),
                    transform=transform.model_copy()))
            candidate.layers.extend(layers)
            validate_hierarchy(candidate)
            for pen_id in pens:
                pen = pen_library.get(pen_id)
                if pen:
                    candidate.pens_used[pen.id] = pen
            self._checkpoint()
            self.project = candidate
            for layer, (*_, paths) in zip(layers, made):
                self.source_geometry[layer.id] = paths
        return group, layers
