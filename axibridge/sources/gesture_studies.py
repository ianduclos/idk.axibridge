"""Gesture Studies: saved pieces from the gesture research, each with its own controls.

Ian (2026-10-17): "These feel like pieces and I'm afraid to overcook or have
an instrument that encompasses too much … save these, each with its own
relevant parameters, still able to have dynamism, and develop on top, but
without overcrowding the generator dropdown." One generator, one bench
(adapter `gesture-studies`), a study dropdown inside. Spec:
docs/superpowers/specs/2026-10-17-gesture-studies.md.

A layer's params carry everything it needs, so it never changes when a study
is edited, renamed, deleted or the library is refrozen:

- `study`   — the full study snapshot (id, label, version, parent, engine,
              recipe, controls);
- `values`  — the control values (key → value; missing = the recipe's own);
- `library` — the frozen-library snapshot the layer resolves against (filled
              in at Keep by `complete_params`; empty = the current snapshot,
              which is what a live preview uses);
- `pins`    — kind / id / version / content hash of every library entry the
              study's controls name, also filled at Keep.

Output: the study's frame in mm (`placement_frame`, fitted onto the bed when
kept); ink paths simplified at 0.01 mm; closed rings closed exactly, outline
rings of nib ribbons and masses `filled=True` (they occlude), everything else
`filled=False`. Deterministic: the frozen kit seeds every draw from the
recipe (CRC-32 string tags, never `hash()`), the Hand Drift engine from
seed + line.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path as FsPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from ..model import Layer, PathDocument
from ..registry import SourceModule, register_source
from ._gesture_studies import frozen_library as FL
from ._gesture_studies import studies as ST

_INK = "#100f0f"
_HIDDEN = {"hidden": True}


@lru_cache(maxsize=1)
def frozen_from() -> str:
    p = FsPath(__file__).resolve().parent / "_gesture_studies" / "kit" / "FROZEN.json"
    return json.loads(p.read_text())["frozen_from"]


def _default_study() -> ST.Study:
    return ST.builtin_studies()[0]


class Pin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["hand", "tempo", "dance_trail"]
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    version: int = Field(ge=1, le=100_000)
    hash: str = Field(pattern=r"^[0-9a-f]{12}$")


class GestureStudiesParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    study: ST.Study = Field(default_factory=_default_study, title="Study", json_schema_extra=_HIDDEN)
    values: dict[str, Any] = Field(default_factory=dict, max_length=32, title="Control values",
                                   json_schema_extra=_HIDDEN)
    library: str | None = Field(default=None, pattern=r"^[0-9a-f]{12}$", title="Library snapshot",
                                json_schema_extra=_HIDDEN)
    pins: list[Pin] = Field(default_factory=list, max_length=64, title="Pinned library entries",
                            json_schema_extra=_HIDDEN)

    _recipe: dict | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _resolve(self):
        try:
            lib = self.frozen_library()
            ST.check_study(self.study, lib)
            self._recipe = ST.resolve(self.study, self.values, lib)
        except (ST.StudyError, FL._kl.LibraryError, FL._kl.PolicyError) as e:
            raise ValueError(str(e)) from None
        return self

    def frozen_library(self) -> FL.FrozenLibrary:
        return FL.FrozenLibrary(self.library, {(p.kind, p.id): p.hash for p in self.pins})

    @property
    def recipe(self) -> dict:
        return self._recipe


@register_source
class GestureStudiesSource(SourceModule):
    id = "gesture_studies"
    label = "Gesture Studies"
    description = ("Saved pieces from the gesture research — Hand Drift, danced chains, polyphonic "
                   "surfaces, annotated pages, a shape atlas, conversations — each with its own few controls")
    orientation = "geometry"
    library_bench = True
    bench = {"adapter": "gesture-studies", "version": 1, "modes": ["new", "resume"]}
    Params = GestureStudiesParams

    def placement_frame(self, params: dict) -> tuple[float, float] | None:
        from ._gesture_studies.engine import frame_of  # noqa: PLC0415
        p = GestureStudiesParams(**params)
        return frame_of(p.study.engine, p.recipe)

    def complete_params(self, params: dict) -> dict:
        """Pin the library at Keep: the snapshot the layer resolves against and
        the version + content hash of every entry its controls name, so a
        later refreeze can never change the kept layer."""
        p = GestureStudiesParams(**params)
        lib = p.frozen_library()
        named = ST.named_entries(p.study, p.values, lib)
        have = {(x.kind, x.id) for x in p.pins}
        pins = [x.model_dump() for x in p.pins] + [lib.pin(k, i) for k, i in named if (k, i) not in have]
        return {**params, "library": lib.snapshot_id, "pins": pins}

    def generate(self, params: GestureStudiesParams) -> PathDocument:
        from ._gesture_studies import engine  # noqa: PLC0415
        lib = params.frozen_library()
        recipe = params.recipe
        st = params.study
        paths = engine.render(st.engine, recipe, lib)
        W, H = engine.frame_of(st.engine, recipe)
        return PathDocument(
            layers=[Layer(id=1, name=st.label, color=_INK, paths=paths)] if paths else [],
            width=W, height=H,
            source=f"gesture_studies {st.id} v{st.version} (kit {frozen_from()}, library {lib.snapshot_id})",
        )
