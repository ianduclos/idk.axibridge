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
"""
from __future__ import annotations

from typing import Any

from .compose import CanvasLayer, LayerGroup, LayerSource
from .stores import Pen, pen_library

SOURCE = "gesture_studies"


def _hex(c: str) -> str:
    return c.strip().lower()


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
            made.append((v, vp, doc, [q for layer in doc.layers for q in layer.paths]))
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
