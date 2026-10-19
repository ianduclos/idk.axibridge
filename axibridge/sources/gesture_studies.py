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
- `devices` — measuring devices laid on the finished drawing (study bench v3,
              move G; `_gesture_studies/devices.py`): `[{"id", "place":
              over|under|margin|beside, "side", "size", …params}]`, checked
              against the frozen device registry. `beside` grows the frame.
              Off (empty) by default: Ian, "has to be optional".
- `show`    — with devices: `all` (the bench preview), `drawing` (the
              drawing's layer of a kept group) or `measure` (its Measure
              layer: the device inks alone, on their own pen). Every member of
              the group resolves the same sheet, so they stay in register.

Output: the study's frame in mm (`placement_frame`, fitted onto the bed when
kept); ink paths simplified at 0.01 mm; closed rings closed exactly, outline
rings of nib ribbons and masses `filled=True` (they occlude), everything else
`filled=False`. Deterministic: the frozen kit seeds every draw from the
recipe (CRC-32 string tags, never `hash()`), the Hand Drift engine from
seed + line.
"""
from __future__ import annotations

import json
import threading
import time
import weakref
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path as FsPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from ..model import Layer, PathDocument
from ..registry import SourceModule, register_source
from ._gesture_studies import devices as DV
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
    devices: list[dict[str, Any]] = Field(default_factory=list, max_length=13, title="Measuring devices",
                                          json_schema_extra=_HIDDEN)
    show: Literal["all", "drawing", "measure"] = Field(default="all", title="Show", json_schema_extra=_HIDDEN)

    _recipe: dict | None = PrivateAttr(default=None)
    _run: dict | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _resolve(self):
        try:
            lib = self.frozen_library()
            ST.check_study(self.study, lib)
            self._recipe = ST.resolve(self.study, self.values, lib)
            self._run = ST.run_recipe(self.study, self._recipe, lib, self.sampled)
            self.devices = DV.check_specs(self.devices, lib)
            if self.show != "all" and not self.devices:
                raise ST.StudyError("only a study with measuring devices shows its drawing or its measure alone")
            if self.show == "measure" and self.voice is not None:
                raise ST.StudyError("the Measure layer draws the devices of every voice: it takes no voice")
            if self.voice is not None:
                n = len(ST.voices_of(self.study, self._run))
                if not n:
                    raise ST.StudyError("only a voices study (the chorus) draws one voice per layer")
                if self.voice >= n:
                    raise ST.StudyError(f"voice {self.voice} is not sung: this chorus has {n} voices")
        except (ST.StudyError, DV.DeviceError, FL._kl.LibraryError, FL._kl.PolicyError) as e:
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
        return DV.grown_frame(frame_of(_engine(p), p.run_recipe), p.devices)

    def complete_params(self, params: dict) -> dict:
        """Pin the library at Keep: the snapshot the layer resolves against and
        the version + content hash of every entry its controls name, so a
        later refreeze can never change the kept layer. A layer that already
        carries a snapshot keeps it (and the hashes it pinned); pins of entries
        no control names any more are dropped. A Sampler layer also stores the
        combination it drew."""
        p = GestureStudiesParams(**params)
        lib = p.frozen_library()
        named = sorted(set(ST.named_entries(p.study, p.values, lib))
                       | {("hand", h) for h in DV.named_hands(p.devices) if h in lib.ids("hand")})
        have = {(x.kind, x.id): x.model_dump() for x in p.pins}
        pins = [have.get((k, i)) or lib.pin(k, i) for k, i in named]
        out = {**params, "library": lib.snapshot_id, "pins": pins}
        if p.study.engine == "sampler":
            out["sampled"] = {"of": ST.sample_key(p.recipe), "recipe": p.run_recipe}
        return out

    def generate(self, params: GestureStudiesParams) -> PathDocument:
        key = params.model_dump_json()
        hit = _slow_get(key)
        if hit is not None:
            return hit
        t0 = time.perf_counter()
        doc, styles, notes = self._generate(params)
        _remember_styles(doc, styles, notes)
        if time.perf_counter() - t0 >= SLOW_SECONDS:
            _slow_put(key, doc)
        return doc

    def preview_styles(self, doc: PathDocument) -> list[dict] | None:
        """How the bench draws `doc` (one this source generated): runs of
        consecutive paths, in the document's path order, each with its ink's
        colour and pen width (bench v3: "each ink in its pen colour at its width")."""
        return (_STYLES.get(id(doc)) or {}).get("runs")

    def preview_extra(self, doc: PathDocument) -> dict | None:
        """What else the bench shows beside the preview: per measuring device,
        how many inks it drew (none = nothing to read) or why it refused, its
        seconds; and which of the document's layers is the Measure layer."""
        meta = _STYLES.get(id(doc)) or {}
        if meta.get("devices") is None:
            return None
        names = [layer.name for layer in doc.layers]
        return {"devices": meta["devices"], "measure_layer": names.index(MEASURE_NAME)
                if MEASURE_NAME in names else None}

    def _generate(self, params: GestureStudiesParams):
        from ._gesture_studies import engine  # noqa: PLC0415
        lib = params.frozen_library()
        recipe = params.run_recipe
        st = params.study
        eng = _engine(params)
        W, H = engine.frame_of(eng, recipe)
        tag = f"gesture_studies {st.id} v{st.version} (kit {frozen_from()}, library {lib.snapshot_id})"
        voices = ST.voices_of(st, recipe)
        if params.devices:
            return self._generate_measured(params, eng, recipe, lib, tag, voices)
        if not voices:
            paths, styles = engine.render_styled(eng, recipe, lib)
            return (PathDocument(layers=[Layer(id=1, name=st.label, color=_INK, paths=paths)] if paths else [],
                                 width=W, height=H, source=tag), styles, None)
        by_voice = engine.render_voices_styled(recipe, lib, st.inks)
        want = [v for v in voices if params.voice is None or v["index"] == params.voice]
        layers = [Layer(id=v["index"] + 1, name=f"{st.label} · {v['ink']}", color=v["color"],
                        paths=[p for p, _ in by_voice.get(v["index"], [])]) for v in want]
        # a voice is drawn in its voice's ink (its pen), at each ink's own width
        styles = [(v["color"], w) for v in want for _, (_, w) in by_voice.get(v["index"], [])]
        return (PathDocument(layers=[x for x in layers if x.paths], width=W, height=H,
                             source=tag + ("" if params.voice is None else f" voice {params.voice}")), styles, None)

    def _generate_measured(self, params: GestureStudiesParams, eng: str, recipe: dict, lib, tag: str,
                           voices: list[dict]):
        """A study with measuring devices: the drawing's layer(s) — one per
        voice for a voices study — and a Measure layer holding the device inks,
        in pen order (the Measure layer first when every device sits under).
        `show` keeps the drawing's or the Measure's alone (a kept group's members)."""
        from ._gesture_studies import engine  # noqa: PLC0415
        st = params.study
        (W, H), items, notes = engine.render_measured(eng, recipe, lib, params.devices,
                                                      st.inks if voices else None)
        measure = [(p, s) for t, p, s in items if t == engine.MEASURE]
        groups: list[tuple[Layer, list[tuple[str, float]]]] = []
        if params.show != "measure":
            if not voices:
                drawn = [(p, s) for t, p, s in items if t != engine.MEASURE]
                groups.append((Layer(id=1, name=st.label, color=_INK, paths=[p for p, _ in drawn]),
                               [s for _, s in drawn]))
            else:
                for v in voices:
                    if params.voice is not None and v["index"] != params.voice:
                        continue
                    drawn = [(p, s) for t, p, s in items if t == v["index"]]
                    groups.append((Layer(id=v["index"] + 1, name=f"{st.label} · {v['ink']}", color=v["color"],
                                         paths=[p for p, _ in drawn]), [(v["color"], w) for _, (_, w) in drawn]))
        if params.show != "drawing":
            mlayer = (Layer(id=99, name=MEASURE_NAME, color=measure_colour([s for _, s in measure]),
                            paths=[p for p, _ in measure]), [s for _, s in measure])
            under = all(d["place"] == "under" for d in params.devices)
            groups = [mlayer, *groups] if under else [*groups, mlayer]
        groups = [g for g in groups if g[0].paths]
        suffix = {"all": "", "drawing": " drawing", "measure": " measure"}[params.show]
        if params.voice is not None:
            suffix += f" voice {params.voice}"
        doc = PathDocument(layers=[layer for layer, _ in groups], width=W, height=H,
                           source=f"{tag} + {len(params.devices)} devices{suffix}")
        return doc, [s for _, styles in groups for s in styles], notes


# ---------------------------------------------------------------------------
# bench v3: preview styles beside each generated document, and a small memo of
# slow results (gencache's random eviction may drop a 76 s Shape atlas for a
# run of 0.3 s previews; this keeps the last few slow ones)
# ---------------------------------------------------------------------------

SLOW_SECONDS = 2.0
MEASURE_NAME = "Measure"
_STYLES: dict[int, dict] = {}
_SLOW: "OrderedDict[str, PathDocument]" = OrderedDict()
_SLOW_LOCK = threading.Lock()


def _runs(styles: list[tuple[str, float]]) -> list[dict]:
    out: list[dict] = []
    for colour, width in styles:
        w = round(float(width), 3)
        if out and out[-1]["color"] == colour and out[-1]["width"] == w:
            out[-1]["paths"] += 1
        else:
            out.append({"color": colour, "width": w, "paths": 1})
    return out


def measure_colour(styles: list[tuple[str, float]]) -> str:
    """The Measure layer's colour (its pen): the ink most of its paths are drawn in."""
    if not styles:
        return _INK
    count: dict[str, int] = {}
    for colour, _ in styles:
        count[colour] = count.get(colour, 0) + 1
    return max(count, key=lambda c: (count[c], c == _INK))


def _remember_styles(doc: PathDocument, styles: list[tuple[str, float]], notes: list[dict] | None = None) -> None:
    # keyed by the document object (gencache hands the same object back), and
    # forgotten with it, so the table never outgrows the caches holding documents
    _STYLES[id(doc)] = {"runs": _runs(styles), "devices": notes}
    weakref.finalize(doc, _STYLES.pop, id(doc), None)


def _slow_limits() -> tuple[int, int]:
    from ..gencache import cache_budget_multiplier  # noqa: PLC0415
    k = cache_budget_multiplier()
    return max(1, int(round(8 * k))), int(1_500_000 * k)


def _points(doc: PathDocument) -> int:
    return sum(len(p.points) for layer in doc.layers for p in layer.paths)


def _slow_get(key: str) -> PathDocument | None:
    with _SLOW_LOCK:
        doc = _SLOW.get(key)
        if doc is not None:
            _SLOW.move_to_end(key)
        return doc


def _slow_put(key: str, doc: PathDocument) -> None:
    entries, budget = _slow_limits()
    with _SLOW_LOCK:
        _SLOW[key] = doc
        _SLOW.move_to_end(key)
        while len(_SLOW) > 1 and (len(_SLOW) > entries or sum(map(_points, _SLOW.values())) > budget):
            _SLOW.popitem(last=False)


def clear_slow_cache() -> None:
    with _SLOW_LOCK:
        _SLOW.clear()


def _engine(p: GestureStudiesParams) -> str:
    """The engine that draws the run recipe (a sampler draws through the kit)."""
    return "kit" if p.study.engine == "sampler" else p.study.engine
