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
              study's controls name, also filled at Keep. A resumed layer keeps
              both through every edit (Studies v2, Ian: "stay pinned; explicit
              update"); only the bench's "Update to current library" clears them;
- `sampled` — a Sampler study's combination at Keep ({"of": what it was
              sampled from, "recipe": the kit recipe}), so neither a refreeze
              nor a sampler change ever changes the layer;
- `voice`   — a voices study (the chorus): which voice this layer draws
              (null = all of them, the bench preview). Keep makes one layer per
              voice in a group; each resolves the same pinned recipe and keeps
              only its own voice's ink.

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
    sampled: dict[str, Any] | None = Field(default=None, title="Sampled combination", json_schema_extra=_HIDDEN)
    voice: int | None = Field(default=None, ge=0, le=15, title="Voice", json_schema_extra=_HIDDEN)

    _recipe: dict | None = PrivateAttr(default=None)
    _run: dict | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _resolve(self):
        try:
            lib = self.frozen_library()
            ST.check_study(self.study, lib)
            self._recipe = ST.resolve(self.study, self.values, lib)
            self._run = ST.run_recipe(self.study, self._recipe, lib, self.sampled)
            if self.voice is not None:
                n = len(ST.voices_of(self.study, self._run))
                if not n:
                    raise ST.StudyError("only a voices study (the chorus) draws one voice per layer")
                if self.voice >= n:
                    raise ST.StudyError(f"voice {self.voice} is not sung: this chorus has {n} voices")
        except (ST.StudyError, FL._kl.LibraryError, FL._kl.PolicyError) as e:
            raise ValueError(str(e)) from None
        return self

    def frozen_library(self) -> FL.FrozenLibrary:
        return FL.FrozenLibrary(self.library, {(p.kind, p.id): p.hash for p in self.pins})

    @property
    def recipe(self) -> dict:
        """The study's recipe with the control values written in."""
        return self._recipe

    @property
    def run_recipe(self) -> dict:
        """The kit recipe that is drawn (a sampler's sampled combination)."""
        return self._run


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
        return frame_of(_engine(p), p.run_recipe)

    def complete_params(self, params: dict) -> dict:
        """Pin the library at Keep: the snapshot the layer resolves against and
        the version + content hash of every entry its controls name, so a
        later refreeze can never change the kept layer. A layer that already
        carries a snapshot keeps it (and the hashes it pinned); pins of entries
        no control names any more are dropped. A Sampler layer also stores the
        combination it drew."""
        p = GestureStudiesParams(**params)
        lib = p.frozen_library()
        named = ST.named_entries(p.study, p.values, lib)
        have = {(x.kind, x.id): x.model_dump() for x in p.pins}
        pins = [have.get((k, i)) or lib.pin(k, i) for k, i in named]
        out = {**params, "library": lib.snapshot_id, "pins": pins}
        if p.study.engine == "sampler":
            out["sampled"] = {"of": ST.sample_key(p.recipe), "recipe": p.run_recipe}
        return out

    def generate(self, params: GestureStudiesParams) -> PathDocument:
        from ._gesture_studies import engine  # noqa: PLC0415
        lib = params.frozen_library()
        recipe = params.run_recipe
        st = params.study
        eng = _engine(params)
        W, H = engine.frame_of(eng, recipe)
        tag = f"gesture_studies {st.id} v{st.version} (kit {frozen_from()}, library {lib.snapshot_id})"
        voices = ST.voices_of(st, recipe)
        if not voices:
            paths = engine.render(eng, recipe, lib)
            return PathDocument(layers=[Layer(id=1, name=st.label, color=_INK, paths=paths)] if paths else [],
                                width=W, height=H, source=tag)
        by_voice = engine.render_voices(recipe, lib, st.inks)
        want = [v for v in voices if params.voice is None or v["index"] == params.voice]
        layers = [Layer(id=v["index"] + 1, name=f"{st.label} · {v['ink']}", color=v["color"],
                        paths=by_voice.get(v["index"], [])) for v in want]
        return PathDocument(layers=[x for x in layers if x.paths], width=W, height=H,
                            source=tag + ("" if params.voice is None else f" voice {params.voice}"))


def _engine(p: GestureStudiesParams) -> str:
    """The engine that draws the run recipe (a sampler draws through the kit)."""
    return "kit" if p.study.engine == "sampler" else p.study.engine
