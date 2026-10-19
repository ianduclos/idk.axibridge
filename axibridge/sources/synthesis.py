"""Synthesis — a score of layers and the relations between them, one executor plays it.

Design: docs/synthesis-bench/design-2026-10-19.md (Ian's decisions §11: the
score lives inside one generator and is kept as a group; two editors, the
layer stack and the arc diagram; the composer proposes, Ian edits, locks and
recomposes). Build plan S4: docs/superpowers/plans/2026-10-19-synthesis-bench-build.md.
Bench and API contract: docs/SYNTHESIS.md.

A layer's params carry everything it needs:

- `score`   — the v2 score (layers, relations, devices, decisions), bounded
              (≤ 24 layers, ≤ 64 relations, ≤ 150 000 literal points across
              lines, base and pins, ≤ 4 MB) and validated by the frozen
              executor (`_synthesis/kit/_synth.py`); stored normalised.
- `show`    — `all` (the bench preview), `layer` (one score layer: a member
              of a kept group, with `layer` its score id) or `measure` (the
              device inks alone). Every member resolves the same played sheet,
              so a group stays in register.
- `library` / `pins` — the frozen-library snapshot and the entries the played
              score used, filled at Keep (`complete_params`), so a refreeze
              never changes a kept layer.

The resolve path doesn't change: the relations live inside the score, inside
one generator's params; app layers resolve one by one through the single path
(this deliberately does not settle the node question, ROADMAP "Far / undecided").
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

_HIDDEN = {"hidden": True}
MAX_LAYERS = 24
MAX_RELATIONS = 64
MAX_POINTS = 150_000
MAX_BYTES = 4_000_000
MAX_FRAME = 600.0
MEASURE_NAME = "Measure"
SLOW_SECONDS = 2.0

DEFAULT_SCORE = {"version": 2, "frame": [250.0, 175.0], "seed": 16001, "label": "one line",
                 "layers": [{"id": "L0", "role": "speaker", "pen": "black", "label": "matisse speaks",
                             "part": {"voice": {"id": "hand", "hand": "matisse"}}}],
                 "relations": []}


@lru_cache(maxsize=1)
def frozen() -> dict:
    p = FsPath(__file__).resolve().parent / "_synthesis" / "kit" / "FROZEN.json"
    return json.loads(p.read_text())


def frozen_from() -> str:
    return frozen()["frozen_from"]


class Pin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["hand", "tempo", "dance_trail", "river_stems", "corpus"]
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    version: int = Field(ge=1, le=100_000)
    hash: str = Field(pattern=r"^[0-9a-f]{12}$")


def literal_points(score: dict) -> int:
    n = sum(len(line) for line in (score.get("base") or {}).get("lines", []) or [])
    for L in score.get("layers") or []:
        n += sum(len(line) for line in L.get("lines") or [])
        n += sum(len(m.get("points") or []) for m in (L.get("pin") or {}).get("marks", []) or [])
    return n


def check_bounds(score: Any) -> None:
    """The bounds a score must keep before the executor sees it (it reaches an open-loop machine)."""
    if not isinstance(score, dict):
        raise ValueError("score must be an object")
    size = len(json.dumps(score, separators=(",", ":"), default=float))
    if size > MAX_BYTES:
        raise ValueError(f"score is {size / 1e6:.1f} MB; at most {MAX_BYTES / 1e6:.0f} MB "
                         "(unpin some layers: a pin stores its lines)")
    layers = score.get("layers") or []
    if not isinstance(layers, list) or len(layers) > MAX_LAYERS:
        raise ValueError(f"a score has at most {MAX_LAYERS} layers")
    rels = score.get("relations") or []
    if not isinstance(rels, list) or len(rels) > MAX_RELATIONS:
        raise ValueError(f"a score has at most {MAX_RELATIONS} relations")
    frame = score.get("frame") or DEFAULT_SCORE["frame"]
    if (not isinstance(frame, list) or len(frame) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and 10 <= v <= MAX_FRAME
                       for v in frame)):
        raise ValueError(f"frame must be [W, H] mm in [10, {MAX_FRAME:.0f}]")
    n = literal_points(score)
    if n > MAX_POINTS:
        raise ValueError(f"the score holds {n} literal points (lines, base, pins); at most {MAX_POINTS}")


class SynthesisParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    score: dict[str, Any] = Field(default_factory=lambda: json.loads(json.dumps(DEFAULT_SCORE)), title="Score",
                                  json_schema_extra=_HIDDEN)
    show: Literal["all", "layer", "measure"] = Field(default="all", title="Show", json_schema_extra=_HIDDEN)
    layer: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$", title="Score layer",
                              json_schema_extra=_HIDDEN)
    library: str | None = Field(default=None, pattern=r"^[0-9a-f]{12}$", title="Library snapshot",
                                json_schema_extra=_HIDDEN)
    pins: list[Pin] = Field(default_factory=list, max_length=128, title="Pinned library entries",
                            json_schema_extra=_HIDDEN)

    _lib: Any = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _check(self):
        from ._synthesis import devices as DV  # noqa: PLC0415
        from ._synthesis import engine as EN  # noqa: PLC0415
        from ._synthesis import frozen_library as FL  # noqa: PLC0415
        try:
            check_bounds(self.score)
            lib = self.frozen_library()
            rec = EN.validate(self.score, lib)
            rec["devices"] = DV.check_specs(rec.get("devices") or [], lib)
            check_bounds(rec)
            self.score = rec
            self._lib = lib
            if self.show == "layer":
                ids = {L["id"]: L for L in rec["layers"]}
                if self.layer not in ids:
                    raise ValueError(f"show=layer needs `layer`, a score layer id; have {sorted(ids)}")
                if ids[self.layer]["role"] == "unseen":
                    raise ValueError(f"layer {self.layer!r} is unseen: it is heard, never inked")
            elif self.layer is not None:
                raise ValueError("`layer` is for show=layer")
            if self.show == "measure" and not rec["devices"]:
                raise ValueError("only a score with measuring devices shows its Measure layer")
        except (FL.LibraryError, FL.PolicyError, DV.DeviceError, EN._synth.RecipeError,
                EN._synth.core.KitError) as e:
            raise ValueError(str(e)) from None
        return self

    def frozen_library(self):
        from ._synthesis import frozen_library as FL  # noqa: PLC0415
        return FL.FrozenLibrary(self.library, {(p.kind, p.id): p.hash for p in self.pins})


@register_source
class SynthesisSource(SourceModule):
    id = "synthesis"
    label = "Synthesis"
    description = ("A score of layers and the relations between them (listen, cross, carry, answer …): "
                   "a composer proposes it, you edit, lock and recompose it")
    orientation = "geometry"
    library_bench = True
    bench = {"adapter": "synthesis", "version": 1, "modes": ["new", "resume"]}
    Params = SynthesisParams

    def placement_frame(self, params: dict) -> tuple[float, float] | None:
        from ._synthesis import devices as DV  # noqa: PLC0415
        p = SynthesisParams(**params)
        W, H = p.score["frame"]
        return DV.grown_frame((float(W), float(H)), p.score.get("devices") or [])

    def complete_params(self, params: dict) -> dict:
        """Pin the library at Keep: the snapshot and the version + content hash of every entry the
        played score used (and the hands its devices name). A layer that already carries a snapshot
        keeps it and the hashes it pinned."""
        from ._synthesis import devices as DV  # noqa: PLC0415
        from ._synthesis import engine as EN  # noqa: PLC0415
        p = SynthesisParams(**params)
        lib = p._lib
        sheet, _ = EN.play(p.score, lib)
        named = {(e["kind"], e["id"]) for e in sheet.meta.get("library", []) if e.get("kind") and e.get("id")}
        named |= {("hand", h) for h in DV.named_hands(p.score.get("devices") or []) if h in lib.ids("hand")}
        have = {(x.kind, x.id): x.model_dump() for x in p.pins}
        kinds = set(Pin.model_fields["kind"].annotation.__args__)
        pins = [have.get((k, i)) or lib.pin(k, i) for k, i in sorted(named) if k in kinds and lib.hash_of(k, i)]
        return {**params, "score": p.score, "library": lib.snapshot_id, "pins": pins}

    def generate(self, params: SynthesisParams) -> PathDocument:
        key = params.model_dump_json()
        hit = _slow_get(key)
        if hit is not None:
            return hit
        t0 = time.perf_counter()
        doc, styles, extra = self._generate(params)
        _remember(doc, styles, extra)
        if time.perf_counter() - t0 >= SLOW_SECONDS:
            _slow_put(key, doc)
        return doc

    def preview_styles(self, doc: PathDocument) -> list[dict] | None:
        return (_STYLES.get(id(doc)) or {}).get("runs")

    def preview_extra(self, doc: PathDocument) -> dict | None:
        """Beside the preview: the played log per relation (the arc diagram dashes a relation that never
        fired), which document layer is which score layer, the device notes, the Measure layer."""
        meta = _STYLES.get(id(doc)) or {}
        return meta.get("extra")

    def _generate(self, params: SynthesisParams):
        from ._synthesis import engine as EN  # noqa: PLC0415
        lib = params._lib
        score = params.score
        sheet, notes = EN.play(score, lib)
        (W, H), groups = EN.layer_paths(sheet, score)
        if params.show == "layer":
            groups = [g for g in groups if g["id"] == params.layer]
        elif params.show == "measure":
            groups = [g for g in groups if g["id"] == EN.MEASURE]
        flex = EN.flexoki()
        layers, styles, index = [], [], []
        for k, g in enumerate(groups):
            colour = measure_colour([s for _, s in g["items"]]) if g["id"] == EN.MEASURE \
                else flex.get(g["pen"], EN.INK)
            name = MEASURE_NAME if g["id"] == EN.MEASURE else (g["label"] or g["id"])
            layers.append(Layer(id=k + 1, name=name, color=colour, paths=[p for p, _ in g["items"]]))
            styles += [s for _, s in g["items"]]
            index.append({"id": g["id"], "role": g["role"], "pen": g["pen"], "paths": len(g["items"])})
        tag = (f"synthesis {score.get('label') or ''} seed {score['seed']} (kit {frozen_from()}, library "
               f"{lib.snapshot_id})" + ("" if params.show == "all" else f" {params.show} {params.layer or ''}"))
        doc = PathDocument(layers=layers, width=W, height=H, source=tag.replace("  ", " ").strip())
        extra = {"synthesis": {**EN.played_summary(sheet, score), "layers": index, "devices": notes,
                               "frame": [W, H]}}
        if notes is not None:
            extra["devices"] = notes
            names = [x["id"] for x in index]
            extra["measure_layer"] = names.index(EN.MEASURE) if EN.MEASURE in names else None
        return doc, styles, extra


# ---------------------------------------------------------------------------
# preview styles beside each generated document, and a small memo of slow results
# ---------------------------------------------------------------------------

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
        return "#100f0f"
    count: dict[str, int] = {}
    for colour, _ in styles:
        count[colour] = count.get(colour, 0) + 1
    return max(count, key=lambda c: (count[c], c == "#100f0f"))


def _remember(doc: PathDocument, styles, extra) -> None:
    _STYLES[id(doc)] = {"runs": _runs(styles), "extra": extra}
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
