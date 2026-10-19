"""The study format: a frozen recipe + the few controls that matter for it.

    {"id": "two_voices", "label": "Two voices, one surface", "version": 1,
     "parent": null, "created": "2026-10-17", "source": "kit demo 4 (round 9)",
     "engine": "kit", "notes": "...", "recipe": {... kit recipe ...},
     "controls": [{"path": "parts.0.voice.hands", "label": "Heavy voice route",
                   "type": "hands", "min_len": 2, "max_len": 4}, ...]}

A control points into the recipe (`path`, or `paths` when one control sets
several places, e.g. both charts of the atlas) and declares a type:

- `int` / `float` — `min`, `max` (required; inside the module param's own
  bounds), optional `step`;
- `bool`; `choice` — `choices` (a subset of the param's; default: all). A
  choice may also set a free `str` kit param: its `choices` are then required
  and are the only values it takes;
- `toggles` — a set of words joined into one `str` kit param (`choices`
  required, `join` "," by default; `min_len` / `max_len` bound how many are
  on), e.g. what a prosody modulator listens to: "switch,corner,kappa";
- `hand` / `tempo` / `trail` — one library id of that kind; `hands` — a list
  (`min_len`, `max_len`; `join: " "` stores it as a space-separated string,
  the conversation's pool). Their options are NOT listed in the study: every
  generative entry of the kind in the frozen library is offered, so hands
  learned later appear in every study after a refreeze. `allow_none` +
  `none_value` (+ `none_label`) add a "none" choice where the param allows it.

`when` (study bench v3, 2026-10-19) says when a control acts at all, so the
bench can dim it and say why ("acts when Regimes is on"):
`{"key": <another control's key>, "is": v}` / `"not": v` / `"in": [v, ...]`,
or `{"all": [...]}` / `{"any": [...]}` of those, with an optional `"say"`
(the reason, in words). The values are checked against the named control.
It is advice for the bench only: the recipe resolves the same either way.

A voices study (`keep: "voices"`) keeps as a group, one layer per voice on its
own pen: by part (the chorus: dev_chorus inks), or, when the study lists
`inks`, by the Flexoki pen each kit ink names (the Oehlen found ground: blue
found layer, green tint, black gesture). An ink the drawing does not use this
time is an empty voice and is not kept.

`modes` (2026-10-19, river_zoom's line source: river | relay of hands) give a
study alternate recipes picked by ONE choice: `{"key", "label", "choices":
[{"id", "label"}, {"id", "label", "recipe", "controls"}, ...]}`. The first
choice is the study's own recipe and controls; each other one carries its own
(a control cannot swap a voice). The chosen id is a value under `key`
(missing = the first). `active(study, values)` is the study as the chosen mode
draws it — no modes — and everything that resolves goes through it, so a study
in its first mode resolves exactly as one that never had modes. A study
without modes dumps without the key. A fork ("Save as new study") saves the
chosen mode alone.

The default of a control is the value at its path in the recipe; everything
not under a control is fixed. `resolve(study, values, library)` writes the
values into a copy of the recipe and validates the result with the engine
(the frozen kit's own validator, or Hand Drift's params). Unknown value keys,
out-of-bounds numbers and ids outside the library are refused.
"""
from __future__ import annotations

import copy
import json
import re
import typing
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from . import frozen_library as FL

STUDIES_DIR = Path(__file__).resolve().parent / "studies"
ID_RE = r"^[a-z0-9][a-z0-9_-]{0,63}$"
KEY_RE = r"^[A-Za-z0-9_.-]{1,120}$"
PATH_RE = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+){0,7}$"
RECIPE_MAX_BYTES = 64_000
FRAME_MM = (20.0, 400.0)
SEED_MAX = 2_147_483_647
LIBRARY_TYPES = ("hand", "hands", "tempo", "trail")
JOINS = (" ", ",", "+", "|")
WHEN_DEPTH = 4
Scalar = str | int | float | bool | None


class StudyError(ValueError):
    """A study, a control or a control value does not validate."""


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    key: str | None = Field(default=None, pattern=KEY_RE)
    path: str | None = Field(default=None, pattern=PATH_RE, max_length=200)
    paths: list[typing.Annotated[str, Field(pattern=PATH_RE, max_length=200)]] | None = Field(
        default=None, min_length=1, max_length=8)
    label: str = Field(min_length=1, max_length=80)
    type: Literal["int", "float", "bool", "choice", "toggles", "hand", "hands", "tempo", "trail"]
    min: float | None = Field(default=None, ge=-1e10, le=1e10)
    max: float | None = Field(default=None, ge=-1e10, le=1e10)
    step: float | None = Field(default=None, gt=0, le=1e9)
    choices: list[Scalar] | None = Field(default=None, min_length=1, max_length=32)
    min_len: int | None = Field(default=None, ge=0, le=64)
    max_len: int | None = Field(default=None, ge=1, le=64)
    allow_none: bool = False
    none_value: str | None = Field(default=None, max_length=40)
    none_label: str = Field(default="none", max_length=60)
    join: Literal[" ", ",", "+", "|"] | None = None
    group: str = Field(default="", max_length=40)
    help: str = Field(default="", max_length=400)
    #: when the control acts (bench v3): see the module docstring
    when: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _shape(self):
        if (self.path is None) == (self.paths is None):
            raise ValueError(f"control {self.label!r}: give exactly one of path / paths")
        if self.key is None:
            self.key = self.path or self.paths[0]
        if self.type in ("int", "float"):
            if self.min is None or self.max is None or not self.min < self.max:
                raise ValueError(f"control {self.label!r}: numeric controls need min < max")
            if self.type == "int" and (self.min != int(self.min) or self.max != int(self.max)):
                raise ValueError(f"control {self.label!r}: int bounds must be integers")
        elif self.min is not None or self.max is not None:
            raise ValueError(f"control {self.label!r}: min/max only on numeric controls")
        if self.choices is not None and self.type not in ("choice", "toggles"):
            raise ValueError(f"control {self.label!r}: choices only on choice / toggles controls")
        if self.type == "toggles":
            if not self.choices or not all(isinstance(x, str) and x for x in self.choices):
                raise ValueError(f"control {self.label!r}: a toggles control lists its words as choices")
            if len(set(self.choices)) != len(self.choices):
                raise ValueError(f"control {self.label!r}: choices must be distinct")
            self.join = self.join or ","
            if any(self.join in x or x != x.strip() for x in self.choices):
                raise ValueError(f"control {self.label!r}: a choice may not contain the join {self.join!r}")
            if self.max_len is not None and self.max_len > len(self.choices):
                raise ValueError(f"control {self.label!r}: max_len exceeds the number of choices")
        elif self.type == "hands":
            if self.join not in (None, " "):
                raise ValueError(f"control {self.label!r}: a joined hands control joins with a space")
        elif self.min_len is not None or self.max_len is not None or self.join:
            raise ValueError(f"control {self.label!r}: min_len/max_len/join only on hands / toggles controls")
        if self.when is not None:
            _when_shape(self.when, self.label)
        if self.allow_none and self.type not in ("hand", "tempo", "trail"):
            raise ValueError(f"control {self.label!r}: allow_none only on hand/tempo/trail controls")
        return self

    @property
    def targets(self) -> list[str]:
        return [self.path] if self.path is not None else list(self.paths)

    @property
    def kind(self) -> str | None:
        return FL.KIND_OF.get(self.type)


def _when_shape(w, label: str, depth: int = 0) -> None:
    """The form of a `when` condition (its keys and values are checked
    against the study's controls in `check_study`)."""
    where = f"control {label!r}: when"
    if depth > WHEN_DEPTH:
        raise ValueError(f"{where} nests deeper than {WHEN_DEPTH}")
    if not isinstance(w, dict):
        raise ValueError(f"{where} must be an object")
    say = w.get("say")
    if say is not None and (not isinstance(say, str) or not 0 < len(say) <= 120):
        raise ValueError(f"{where}: say is a short sentence")
    ops = [k for k in ("is", "not", "in", "all", "any") if k in w]
    extra = set(w) - {"key", "is", "not", "in", "all", "any", "say"}
    if extra or len(ops) != 1:
        raise ValueError(f"{where} takes key + one of is / not / in, or all / any (got {sorted(w)})")
    op = ops[0]
    if op in ("all", "any"):
        if "key" in w or not isinstance(w[op], list) or not 1 <= len(w[op]) <= 8:
            raise ValueError(f"{where}: {op} is a list of 1-8 conditions, without a key")
        for x in w[op]:
            _when_shape(x, label, depth + 1)
        return
    if not isinstance(w.get("key"), str) or not re.fullmatch(KEY_RE, w["key"]):
        raise ValueError(f"{where}: key names another control")
    vals = w[op] if op == "in" else [w[op]]
    if op == "in" and (not isinstance(w[op], list) or not 1 <= len(w[op]) <= 32):
        raise ValueError(f"{where}: in is a list of 1-32 values")
    for v in vals:
        if not isinstance(v, (str, int, float, bool, list)) or (isinstance(v, list) and len(v) > 64):
            raise ValueError(f"{where}: {v!r} is not a control value")


def when_keys(w) -> set[str]:
    """Every control key a condition reads."""
    if w is None:
        return set()
    if "all" in w or "any" in w:
        return set().union(*(when_keys(x) for x in w.get("all") or w.get("any")))
    return {w["key"]}


def when_holds(w, value_of) -> bool:
    """Does condition `w` hold, reading control values through `value_of(key)`?"""
    if w is None:
        return True
    if "all" in w:
        return all(when_holds(x, value_of) for x in w["all"])
    if "any" in w:
        return any(when_holds(x, value_of) for x in w["any"])
    v = value_of(w["key"])
    if "is" in w:
        return v == w["is"]
    if "not" in w:
        return v != w["not"]
    return v in w["in"]


class Parent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=ID_RE)
    version: int = Field(ge=1, le=100_000)


class Mode(BaseModel):
    """One choice of a study's mode switch. The first choice is the study's own
    recipe and controls and carries neither; every other one carries both."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID_RE)
    label: str = Field(min_length=1, max_length=60)
    recipe: dict[str, Any] | None = None
    controls: list[Control] | None = Field(default=None, min_length=1, max_length=32)


class Modes(BaseModel):
    """A study's mode switch (river_zoom's line source, 2026-10-19): one choice
    control (`key`, `label`) that picks which recipe draws and which controls
    show. The value is a choice id, stored under `key` in the layer's values
    like any control's; missing = the first choice (the study as it was)."""
    model_config = ConfigDict(extra="forbid")

    key: str = Field(default="mode", pattern=KEY_RE)
    label: str = Field(min_length=1, max_length=80)
    help: str = Field(default="", max_length=400)
    choices: list[Mode] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def _shape(self):
        ids = [m.id for m in self.choices]
        if len(set(ids)) != len(ids):
            raise ValueError("mode ids must be unique")
        first, *others = self.choices
        if first.recipe is not None or first.controls is not None:
            raise ValueError(f"mode {first.id!r} is the study's own recipe and controls: it carries neither")
        for m in others:
            if m.recipe is None or m.controls is None:
                raise ValueError(f"mode {m.id!r} needs its own recipe and controls")
            keys = [c.key for c in m.controls]
            if len(set(keys)) != len(keys):
                raise ValueError(f"mode {m.id!r}: control keys must be unique")
        return self


class Study(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID_RE)
    label: str = Field(min_length=1, max_length=120)
    version: int = Field(default=1, ge=1, le=100_000)
    parent: Parent | None = None
    created: str = Field(default="", max_length=40)
    source: str = Field(default="", max_length=400)
    engine: Literal["kit", "hand_drift", "sampler"] = "kit"
    keep: Literal["layer", "voices"] = "layer"
    #: a voices study whose pens are its INKS, not its parts (round-12 keeps, 2026-10-18): the kit
    #: names each ink's Flexoki pen (`Ink.meta` "ink", else "colour"), e.g. the Oehlen found ground's
    #: blue found layer, black late line and green tint. One voice per name, in this order; a name the
    #: drawing does not use this time is simply an empty voice (not kept).
    inks: list[typing.Annotated[str, Field(pattern=r"^[a-z]+(-[0-9]{3})?$")]] | None = Field(
        default=None, min_length=1, max_length=16)
    notes: str = Field(default="", max_length=4000)
    #: the gallery's grouping (bench v3): "Hands and drift", "Measurement", ...
    family: str = Field(default="", max_length=60)
    recipe: dict[str, Any]
    controls: list[Control] = Field(min_length=1, max_length=32)
    #: alternate recipes picked by one choice (see `Modes`); a study without is dumped without the key
    modes: Modes | None = None

    @model_serializer(mode="wrap")
    def _dump(self, handler):
        # a study without modes dumps exactly as it did before modes existed
        out = handler(self)
        if isinstance(out, dict) and out.get("modes") is None:
            out.pop("modes", None)
        return out

    @model_validator(mode="after")
    def _keys(self):
        keys = [c.key for c in self.controls]
        if len(set(keys)) != len(keys):
            raise ValueError("control keys must be unique")
        if len(json.dumps(self.recipe)) > RECIPE_MAX_BYTES:
            raise ValueError(f"recipe larger than {RECIPE_MAX_BYTES} bytes")
        if self.modes is not None:
            every = keys + [c.key for m in self.modes.choices for c in (m.controls or [])]
            if self.modes.key in every:
                raise ValueError(f"the mode switch's key {self.modes.key!r} is also a control's key")
            if len(json.dumps([m.recipe for m in self.modes.choices])) > RECIPE_MAX_BYTES:
                raise ValueError(f"mode recipes larger than {RECIPE_MAX_BYTES} bytes")
        if self.keep == "voices" and self.engine != "kit":
            raise ValueError("only a kit study can keep its voices as a group of layers")
        if self.inks is not None:
            if self.keep != "voices":
                raise ValueError("inks name the voices of a voices study (keep: voices)")
            if len(set(self.inks)) != len(self.inks):
                raise ValueError("inks must be distinct")
            bad = [x for x in self.inks if x not in flexoki()]
            if bad:
                raise ValueError(f"inks {bad} are not Flexoki pens ({sorted(flexoki())})")
        return self


# ---------------------------------------------------------------------------
# json paths
# ---------------------------------------------------------------------------

def _steps(path: str) -> list:
    return [int(s) if s.isdigit() else s for s in path.split(".")]


def get_at(obj, path: str):
    cur = obj
    for s in _steps(path):
        try:
            cur = cur[s]
        except (KeyError, IndexError, TypeError):
            raise StudyError(f"path {path!r} does not exist in the recipe") from None
    return cur


def set_at(obj, path: str, value) -> None:
    steps = _steps(path)
    cur = get_at(obj, ".".join(map(str, steps[:-1]))) if len(steps) > 1 else obj
    try:
        cur[steps[-1]]
    except (KeyError, IndexError, TypeError):
        raise StudyError(f"path {path!r} does not exist in the recipe") from None
    cur[steps[-1]] = value


# ---------------------------------------------------------------------------
# engines: what a path points at (for bounds checks) and recipe validation
# ---------------------------------------------------------------------------

class Spec(typing.NamedTuple):
    """What a control may set at a path: the param's type and bounds."""
    type: str                   # int | float | bool | choice | ref | refs | str
    min: float | None = None
    max: float | None = None
    choices: tuple | None = None
    kind: str | None = None
    min_len: int | None = None
    max_len: int | None = None
    optional: bool = False
    none_value: Any = None


def _kit():
    from . import kit  # noqa: PLC0415 — the frozen kit loads on first use
    from . import engine  # noqa: PLC0415,F401 — installs the cancellation hooks
    return kit


def kit_spec(recipe: dict, path: str) -> Spec:
    kit = _kit()
    s = _steps(path)

    def from_param(kind: str, mid: str, name) -> Spec:
        try:
            p = kit.get(kind, mid).param(name)
        except (KeyError, kit.RecipeError):
            raise StudyError(f"path {path!r}: {kind} {mid!r} has no param {name!r}") from None
        return Spec(p.type, p.min, p.max, tuple(p.choices) if p.choices else None, p.kind, p.min_len,
                    p.max_len, p.optional, None)

    if s == ["seed"]:
        return Spec("int", 0, SEED_MAX)
    try:
        if len(s) == 2 and s[0] in ("arranger", "renderer"):
            return from_param(s[0], recipe[s[0]]["id"], s[1])
        if len(s) >= 4 and s[0] == "parts" and isinstance(s[1], int):
            part = recipe["parts"][s[1]]
            if s[2] == "voice" and len(s) == 4:
                return from_param("voice", part["voice"]["id"], s[3])
            if s[2] == "modulators" and len(s) == 5 and isinstance(s[3], int):
                return from_param("modulator", part["modulators"][s[3]]["id"], s[4])
            if s[2] == "renderer" and len(s) == 4 and part.get("renderer"):
                return from_param("renderer", part["renderer"]["id"], s[3])
    except (KeyError, IndexError, TypeError):
        pass
    raise StudyError(f"control path {path!r} does not point at a module param of this recipe")


def _hd():
    from .. import hand_drift  # noqa: PLC0415
    from .._hand_drift import hands as H  # noqa: PLC0415
    return hand_drift, H


_HD_HANDS = ("hand_1", "hand_2", "hand_3", "hand_4")


def hand_drift_spec(path: str) -> Spec:
    hand_drift, _ = _hd()
    fields = hand_drift.HandDriftParams.model_fields
    if path not in fields:
        raise StudyError(f"control path {path!r} is not a Hand Drift param")
    if path in _HD_HANDS:
        return Spec("ref", kind="hand", optional=path in ("hand_3", "hand_4"), none_value="none")
    if path == "timing":
        return Spec("ref", kind="tempo")
    f = fields[path]
    ann = f.annotation
    if typing.get_origin(ann) is Literal:
        return Spec("choice", choices=typing.get_args(ann))
    if ann is bool:
        return Spec("bool")
    lo = hi = None
    for m in f.metadata:
        lo = getattr(m, "ge", lo)
        hi = getattr(m, "le", hi)
    return Spec("int" if ann is int else "float", lo, hi)


def sampler_spec(path: str) -> Spec:
    if path == "seed":
        return Spec("int", 0, SEED_MAX)
    if path == "clean":                     # round 12: tidy the combination (kit/sampler.tidy)
        return Spec("bool")
    raise StudyError(f"control path {path!r}: a sampler study's controls are its seed and clean")


def spec_at(study: Study, recipe: dict, path: str) -> Spec:
    if study.engine == "kit":
        return kit_spec(recipe, path)
    if study.engine == "sampler":
        return sampler_spec(path)
    return hand_drift_spec(path)


def library_ids(lib: FL.FrozenLibrary, kind: str) -> set[str]:
    """Ids a control may use: generative, not withdrawn, in this library's snapshot."""
    out = set()
    withdrawn = set(FL.index().get("withdrawn", []))
    for eid in lib.ids(kind):
        if f"{kind}/{eid}" in withdrawn:
            continue
        e = lib.entry(kind, eid)
        if e.get("policy") == "generative":
            out.add(eid)
    return out


def hand_drift_ids(kind: str, lib: FL.FrozenLibrary) -> set[str]:
    """Hand Drift study: every library entry plus the engine's own frozen set."""
    _, H = _hd()
    own = set(H.HAND_IDS) if kind == "hand" else set(H.TIMING_IDS) if kind == "tempo" else set()
    return own | library_ids(lib, kind)


def _kit_recipe(recipe: dict, lib: FL.FrozenLibrary) -> dict:
    kit = _kit()
    try:
        out = kit.validate(recipe, library=lib)
    except (kit.RecipeError, KeyError, TypeError) as e:
        raise StudyError(f"recipe: {e}") from None
    # the kit allows sheets up to 2 m; the app keeps a study near bed size
    # (ink is laid in mm, so a huge frame is a huge, slow drawing)
    if not all(FRAME_MM[0] <= v <= FRAME_MM[1] for v in out["frame"]):
        raise StudyError(f"recipe: frame sides must be {FRAME_MM[0]:g}–{FRAME_MM[1]:g} mm, got {out['frame']}")
    return out


def _sampler_recipe(recipe: dict) -> dict:
    """A sampler study's recipe: {"frame": [W, H], "seed": n} and, optionally,
    "clean": bool (round 12: the combination tidied, `kit/sampler.tidy`). A
    recipe without "clean" normalizes without it, so what older kept layers
    were sampled from (`sample_key`) never changes."""
    extra = sorted(set(recipe) - {"frame", "seed", "clean"})
    if extra:
        raise StudyError(f"recipe: a sampler recipe is frame + seed (+ clean), not {extra}")
    if "clean" in recipe and not isinstance(recipe["clean"], bool):
        raise StudyError("recipe: clean must be true or false")
    frame, seed = recipe.get("frame", [267.0, 180.0]), recipe.get("seed", 0)
    if (not isinstance(frame, list) or len(frame) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in frame)
            or not all(FRAME_MM[0] <= float(v) <= FRAME_MM[1] for v in frame)):
        raise StudyError(f"recipe: frame must be [W, H] with sides {FRAME_MM[0]:g}–{FRAME_MM[1]:g} mm")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= SEED_MAX:
        raise StudyError(f"recipe: seed must be an int in [0, {SEED_MAX}]")
    out = {"frame": [float(frame[0]), float(frame[1])], "seed": int(seed)}
    if "clean" in recipe:
        out["clean"] = recipe["clean"]
    return out


def validate_recipe(study: Study, recipe: dict, lib: FL.FrozenLibrary) -> dict:
    """Engine validation → the normalized recipe (defaults filled)."""
    if study.engine == "kit":
        return _kit_recipe(recipe, lib)
    if study.engine == "sampler":
        return _sampler_recipe(recipe)
    hand_drift, _ = _hd()
    r = dict(recipe)
    loose = {**r, **{h: "matisse" for h in _HD_HANDS if h in r}, "timing": "staccato"}
    try:
        base = hand_drift.HandDriftParams(**loose).model_dump()
    except Exception as e:  # noqa: BLE001 — pydantic's message is the useful part
        raise StudyError(f"recipe: {e}") from None
    hands, tempi = hand_drift_ids("hand", lib), hand_drift_ids("tempo", lib)
    for h in _HD_HANDS:
        v = r.get(h, base[h])
        if not isinstance(v, str) or (v not in hands and not (v == "none" and h in ("hand_3", "hand_4"))):
            raise StudyError(f"recipe: {h}={v!r} is not a library hand")
        base[h] = v
    t = r.get("timing", "staccato")
    if not isinstance(t, str) or t not in tempi:
        raise StudyError(f"recipe: timing={t!r} is not a library tempo")
    base["timing"] = t
    return base


# ---------------------------------------------------------------------------
# controls
# ---------------------------------------------------------------------------

def _check_control(study: Study, recipe: dict, c: Control) -> None:
    """Does control c fit the params it points at? (type, bounds, kind)"""
    first = None
    for i, path in enumerate(c.targets):
        sp = spec_at(study, recipe, path)
        v = get_at(recipe, path)
        if i == 0:
            first = v
        elif v != first:
            raise StudyError(f"control {c.label!r}: its paths hold different values ({first!r} vs {v!r})")
        where = f"control {c.label!r} ({path})"
        if c.type in ("int", "float"):
            if sp.type != c.type:
                raise StudyError(f"{where}: the param is {sp.type}, not {c.type}")
            if (sp.min is not None and c.min < sp.min) or (sp.max is not None and c.max > sp.max):
                raise StudyError(f"{where}: bounds [{c.min}, {c.max}] exceed the param's [{sp.min}, {sp.max}]")
        elif c.type == "bool":
            if sp.type != "bool":
                raise StudyError(f"{where}: the param is {sp.type}, not bool")
        elif c.type == "choice" and sp.type == "str":
            # a free text param offered as a few words (bench v3): the study names them
            if not c.choices or not all(isinstance(x, str) for x in c.choices):
                raise StudyError(f"{where}: a choice over a text param lists its choices (as text)")
        elif c.type == "choice":
            if sp.type != "choice":
                raise StudyError(f"{where}: the param is {sp.type}, not a choice")
            if c.choices is not None and not set(c.choices) <= set(sp.choices):
                raise StudyError(f"{where}: choices {c.choices} are not all among {list(sp.choices)}")
        elif c.type == "toggles":
            if sp.type != "str":
                raise StudyError(f"{where}: toggles join their words into a text param, not a {sp.type}")
        elif c.type == "hands" and c.join:
            if sp.type != "str":
                raise StudyError(f"{where}: a joined hands control needs a string param")
        elif c.type == "hands":
            if sp.type != "refs" or sp.kind != "hand":
                raise StudyError(f"{where}: the param is not a list of hands")
            lo, hi = c.min_len or 1, c.max_len or (sp.max_len or 8)
            if (sp.min_len is not None and lo < sp.min_len) or (sp.max_len is not None and hi > sp.max_len):
                raise StudyError(f"{where}: length bounds exceed the param's")
        else:                                   # hand / tempo / trail
            if sp.type != "ref" or sp.kind != c.kind:
                raise StudyError(f"{where}: the param is not one {c.kind} id")
            if c.allow_none and (not sp.optional or c.none_value != sp.none_value):
                raise StudyError(f"{where}: the param does not take {c.none_value!r} as none")


# ---------------------------------------------------------------------------
# what a resolved study runs: the kit recipe (a sampler's sampled one), voices
# ---------------------------------------------------------------------------

def sample_key(recipe: dict) -> str:
    """What a sampled recipe was sampled FROM (frame + seed [+ clean]),
    canonical. `clean: false` samples exactly what a recipe without it does,
    so it is left out: a layer kept before the option existed still matches."""
    r = {k: v for k, v in recipe.items() if not (k == "clean" and v is False)}
    return json.dumps(r, sort_keys=True, separators=(",", ":"))


def run_recipe(study: Study, recipe: dict, lib: FL.FrozenLibrary, sampled: dict | None = None) -> dict:
    """The kit recipe a resolved study runs. Kit: the recipe itself. Sampler:
    the combination its seed samples from `lib`'s pools — or, when `sampled`
    ({"of": sample_key, "recipe": ...}, what a kept layer stores) was sampled
    from this very recipe, that stored combination, so a refreeze that adds
    hands (or changes the sampler) never changes a kept layer."""
    if study.engine != "sampler":
        return recipe
    if sampled and sampled.get("of") == sample_key(recipe) and isinstance(sampled.get("recipe"), dict):
        return _kit_recipe(sampled["recipe"], lib)
    from .kit import sampler  # noqa: PLC0415
    _kit()
    try:
        out = sampler.sample(recipe["seed"], library=lib, frame=tuple(recipe["frame"]),
                             clean=bool(recipe.get("clean", False)))
    except (_kit().RecipeError, KeyError, StopIteration, ValueError) as e:
        raise StudyError(f"sampler: {e}") from None
    return _kit_recipe(out, lib)


def summary_of(study: Study, kit_recipe: dict) -> str:
    """One line naming what is combined (the sampler's own summary)."""
    from .kit import sampler  # noqa: PLC0415
    if study.engine not in ("kit", "sampler"):
        return ""
    try:
        return sampler.summarize(kit_recipe)
    except (KeyError, TypeError):           # an arranger or voice the summary does not know
        return ""


def flexoki() -> dict[str, str]:
    """Flexoki pen name -> hex: the 600 accents + black (dev_chorus) and the
    400 accents (the Oehlen found ground's tint)."""
    from .kit import arrangers_oehlen_found  # noqa: PLC0415
    return dict(arrangers_oehlen_found.FLEXOKI)


def voices_of(study: Study, kit_recipe: dict) -> list[dict]:
    """`when` (study bench v3, 2026-10-19) says when a control acts at all, so the
bench can dim it and say why ("acts when Regimes is on"):
`{"key": <another control's key>, "is": v}` / `"not": v` / `"in": [v, ...]`,
or `{"all": [...]}` / `{"any": [...]}` of those, with an optional `"say"`
(the reason, in words). The values are checked against the named control.
It is advice for the bench only: the recipe resolves the same either way.

A voices study (`keep: "voices"`): one entry per sung voice — index,
    ink name and colour (the dev_chorus arranger's Flexoki inks, or the
    study's own `inks`), label."""
    if study.keep != "voices":
        return []
    if study.inks:
        fx = flexoki()
        return [{"index": i, "ink": n, "color": fx[n], "label": n} for i, n in enumerate(study.inks)]
    from .kit import dev_chorus  # noqa: PLC0415
    arr = kit_recipe["arranger"]
    n = len(kit_recipe["parts"])
    if arr.get("voices") is not None:
        n = min(n, int(arr["voices"]))
    inks = dev_chorus.parse_inks(arr["inks"]) if arr.get("id") == "dev_chorus" else ["black"]
    out = []
    for i in range(n):
        ink = inks[i % len(inks)]
        part = kit_recipe["parts"][i]
        out.append({"index": i, "ink": ink, "color": dev_chorus.FLEXOKI[ink],
                    "label": part.get("label") or part["voice"]["id"]})
    return out


def options_for(study: Study, c: Control, lib: FL.FrozenLibrary) -> set[str]:
    if study.engine == "hand_drift":
        return hand_drift_ids(c.kind, lib)
    return library_ids(lib, c.kind)


def coerce(study: Study, recipe: dict, c: Control, v, lib: FL.FrozenLibrary):
    """A control value checked against the control (and the library) → the
    value written into the recipe."""
    where = f"{c.label} ({c.key})"
    if c.type in ("int", "float"):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise StudyError(f"{where}: needs a number, got {v!r}")
        if c.type == "int":
            if float(v) != int(v):
                raise StudyError(f"{where}: needs an integer, got {v!r}")
            v = int(v)
        else:
            v = float(v)
            if v != v or v in (float("inf"), float("-inf")):
                raise StudyError(f"{where}: needs a finite number")
        if not c.min <= v <= c.max:
            raise StudyError(f"{where}: {v} outside [{c.min:g}, {c.max:g}]")
        return v
    if c.type == "bool":
        if not isinstance(v, bool):
            raise StudyError(f"{where}: needs true/false, got {v!r}")
        return v
    if c.type == "toggles":
        if isinstance(v, str):
            items = [x.strip() for x in v.split(c.join)] if v.strip() else []
        elif isinstance(v, list) and all(isinstance(x, str) for x in v):
            items = list(v)
        else:
            raise StudyError(f"{where}: needs a list of words, got {v!r}")
        bad = [x for x in items if x not in c.choices]
        if bad:
            raise StudyError(f"{where}: {bad} are not among {c.choices}")
        if len(set(items)) != len(items):
            raise StudyError(f"{where}: a word is on twice")
        lo = c.min_len if c.min_len is not None else 0
        hi = c.max_len if c.max_len is not None else len(c.choices)
        if not lo <= len(items) <= hi:
            raise StudyError(f"{where}: takes {lo}-{hi} of {c.choices}, got {len(items)}")
        return c.join.join(items)
    if c.type == "choice":
        allowed = c.choices if c.choices is not None else list(spec_at(study, recipe, c.targets[0]).choices)
        if v not in allowed:
            raise StudyError(f"{where}: {v!r} is not one of {allowed}")
        return v
    ids = options_for(study, c, lib)
    if c.type == "hands":
        items = v.split() if (c.join and isinstance(v, str)) else v
        if isinstance(items, str) or not isinstance(items, list) or not all(isinstance(x, str) for x in items):
            raise StudyError(f"{where}: needs a list of hand ids")
        lo = c.min_len if c.min_len is not None else 1
        hi = c.max_len if c.max_len is not None else 8
        if not lo <= len(items) <= hi:
            raise StudyError(f"{where}: takes {lo}–{hi} hands, got {len(items)}")
        bad = [x for x in items if x not in ids]
        if bad:
            raise StudyError(f"{where}: {bad} not in the frozen library")
        return " ".join(items) if c.join else list(items)
    if c.allow_none and v == c.none_value:
        return v
    if not isinstance(v, str) or v not in ids:
        raise StudyError(f"{where}: {v!r} is not a frozen library {c.kind}")
    return v


# ---------------------------------------------------------------------------
# modes: one choice picks the recipe and controls (river_zoom's line source)
# ---------------------------------------------------------------------------

def mode_of(study: Study, values: dict[str, Any]) -> str | None:
    """The mode these values choose (None: the study has no modes)."""
    if study.modes is None:
        return None
    ids = [m.id for m in study.modes.choices]
    v = values.get(study.modes.key, ids[0])
    if v not in ids:
        raise StudyError(f"{study.modes.label} ({study.modes.key}): {v!r} is not one of {ids}")
    return v


def active(study: Study, values: dict[str, Any]) -> tuple[Study, dict[str, Any]]:
    """The study as the chosen mode draws it — its recipe and controls, no
    modes — and the values without the mode switch. A study without modes, or
    in its first mode, is itself (minus `modes`), so it resolves exactly as a
    study that never had modes."""
    m = mode_of(study, values)
    if m is None:
        return study, values
    vals = {k: v for k, v in values.items() if k != study.modes.key}
    mode = next(x for x in study.modes.choices if x.id == m)
    if mode.recipe is None:
        return study.model_copy(update={"modes": None}), vals
    return study.model_copy(update={"modes": None, "recipe": mode.recipe, "controls": mode.controls}), vals


def check_study(study: Study, lib: FL.FrozenLibrary | None = None) -> Study:
    """Semantic validation (recipe through its engine, every control against
    the params it points at, every default value against its control); a study
    with modes: every mode's recipe and controls the same way."""
    lib = lib or FL.FrozenLibrary()
    if study.modes is None:
        return _check_one(study, lib)
    base = _check_one(study.model_copy(update={"modes": None}), lib)
    choices = [study.modes.choices[0]]
    for m in study.modes.choices[1:]:
        one = _check_one(study.model_copy(update={"modes": None, "recipe": m.recipe, "controls": m.controls}), lib)
        choices.append(m.model_copy(update={"recipe": one.recipe, "controls": one.controls}))
    return base.model_copy(update={"modes": study.modes.model_copy(update={"choices": choices})})


def _check_one(study: Study, lib: FL.FrozenLibrary) -> Study:
    recipe = validate_recipe(study, study.recipe, lib)
    controls = []
    for c in study.controls:
        _check_control(study, recipe, c)
        if c.type == "choice" and c.choices is None:      # spell the param's choices out for the bench
            c = c.model_copy(update={"choices": list(spec_at(study, recipe, c.targets[0]).choices)})
        coerce(study, recipe, c, get_at(recipe, c.targets[0]), lib)
        controls.append(c)
    by_key = {c.key: c for c in controls}
    for c in controls:
        _check_when(study, recipe, c, c.when, by_key, lib)
    return study.model_copy(update={"recipe": recipe, "controls": controls})


def _check_when(study: Study, recipe: dict, c: Control, w, by_key: dict, lib: FL.FrozenLibrary) -> None:
    if w is None:
        return
    if "all" in w or "any" in w:
        for x in w.get("all") or w.get("any"):
            _check_when(study, recipe, c, x, by_key, lib)
        return
    other = by_key.get(w["key"])
    if other is None or other.key == c.key:
        raise StudyError(f"control {c.label!r}: when names {w['key']!r}, which is not another control of this study")
    for v in (w["in"] if "in" in w else [w.get("is", w.get("not"))]):
        try:
            coerce(study, recipe, other, copy.deepcopy(v), lib)
        except StudyError as e:
            raise StudyError(f"control {c.label!r}: when {w['key']}: {e}") from None


def acts(study: Study, values: dict[str, Any], c: Control) -> bool:
    """Does control c act with these values (its `when` holds)? Values not
    given are the recipe's own. A control of a mode not chosen never acts."""
    study, values = active(study, values)
    by_key = {x.key: x for x in study.controls}
    if c.key not in by_key:
        return False
    return when_holds(c.when, lambda k: values[k] if k in values else get_at(study.recipe, by_key[k].targets[0]))


def defaults(study: Study) -> dict[str, Any]:
    """The values of the study as it opens: its own recipe's (the first mode's)."""
    return {c.key: copy.deepcopy(get_at(study.recipe, c.targets[0])) for c in study.controls}


def resolve(study: Study, values: dict[str, Any], lib: FL.FrozenLibrary) -> dict:
    """The recipe with the control values written in (validated); a study with
    modes: the chosen mode's recipe with its controls' values."""
    study, values = active(study, values)
    keys = {c.key for c in study.controls}
    extra = sorted(k for k in values if k not in keys)
    if extra:
        raise StudyError(f"unknown control value(s) {extra}; this study's controls: {sorted(keys)}")
    recipe = validate_recipe(study, study.recipe, lib)
    for c in study.controls:
        v = values[c.key] if c.key in values else get_at(recipe, c.targets[0])
        v = coerce(study, recipe, c, copy.deepcopy(v), lib)
        for path in c.targets:
            set_at(recipe, path, copy.deepcopy(v))
    return validate_recipe(study, recipe, lib)


def named_entries(study: Study, values: dict[str, Any], lib: FL.FrozenLibrary) -> list[tuple[str, str]]:
    """(kind, id) of every library entry the study's library controls name
    (the entries a kept layer pins explicitly; with modes: the chosen mode's)."""
    study, values = active(study, values)
    out = []
    for c in study.controls:
        if c.type not in LIBRARY_TYPES:
            continue
        v = values.get(c.key, get_at(study.recipe, c.targets[0]))
        items = (v.split() if isinstance(v, str) and c.join else v) if c.type == "hands" else [v]
        for x in items or []:
            if isinstance(x, str) and not (c.allow_none and x == c.none_value) and x in lib.ids(c.kind):
                out.append((c.kind, x))
    return sorted(set(out))


# ---------------------------------------------------------------------------
# built-ins
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _builtin_raw() -> tuple[dict, ...]:
    order = json.loads((STUDIES_DIR / "index.json").read_text())["order"]
    return tuple(json.loads((STUDIES_DIR / sid / "study.json").read_text()) for sid in order)


def builtin_studies() -> list[Study]:
    return [Study(**copy.deepcopy(d)) for d in _builtin_raw()]


def builtin_ids() -> list[str]:
    return [d["id"] for d in _builtin_raw()]


def builtin(sid: str) -> Study:
    for d in _builtin_raw():
        if d["id"] == sid:
            return Study(**copy.deepcopy(d))
    raise KeyError(f"no built-in study {sid!r}")


def slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return (s or "study")[:40]
