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
- `bool`; `choice` — `choices` (a subset of the param's; default: all);
- `hand` / `tempo` / `trail` — one library id of that kind; `hands` — a list
  (`min_len`, `max_len`; `join: " "` stores it as a space-separated string,
  the conversation's pool). Their options are NOT listed in the study: every
  generative entry of the kind in the frozen library is offered, so hands
  learned later appear in every study after a refreeze. `allow_none` +
  `none_value` (+ `none_label`) add a "none" choice where the param allows it.

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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import frozen_library as FL

STUDIES_DIR = Path(__file__).resolve().parent / "studies"
ID_RE = r"^[a-z0-9][a-z0-9_-]{0,63}$"
KEY_RE = r"^[A-Za-z0-9_.-]{1,120}$"
PATH_RE = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+){0,7}$"
RECIPE_MAX_BYTES = 64_000
FRAME_MM = (20.0, 400.0)
SEED_MAX = 2_147_483_647
LIBRARY_TYPES = ("hand", "hands", "tempo", "trail")
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
    type: Literal["int", "float", "bool", "choice", "hand", "hands", "tempo", "trail"]
    min: float | None = Field(default=None, ge=-1e10, le=1e10)
    max: float | None = Field(default=None, ge=-1e10, le=1e10)
    step: float | None = Field(default=None, gt=0, le=1e9)
    choices: list[Scalar] | None = Field(default=None, min_length=1, max_length=32)
    min_len: int | None = Field(default=None, ge=0, le=64)
    max_len: int | None = Field(default=None, ge=1, le=64)
    allow_none: bool = False
    none_value: str | None = Field(default=None, max_length=40)
    none_label: str = Field(default="none", max_length=60)
    join: Literal[" "] | None = None
    group: str = Field(default="", max_length=40)
    help: str = Field(default="", max_length=400)

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
        if self.choices is not None and self.type != "choice":
            raise ValueError(f"control {self.label!r}: choices only on choice controls")
        if self.type != "hands" and (self.min_len is not None or self.max_len is not None or self.join):
            raise ValueError(f"control {self.label!r}: min_len/max_len/join only on hands controls")
        if self.allow_none and self.type not in ("hand", "tempo", "trail"):
            raise ValueError(f"control {self.label!r}: allow_none only on hand/tempo/trail controls")
        return self

    @property
    def targets(self) -> list[str]:
        return [self.path] if self.path is not None else list(self.paths)

    @property
    def kind(self) -> str | None:
        return FL.KIND_OF.get(self.type)


class Parent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=ID_RE)
    version: int = Field(ge=1, le=100_000)


class Study(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID_RE)
    label: str = Field(min_length=1, max_length=120)
    version: int = Field(default=1, ge=1, le=100_000)
    parent: Parent | None = None
    created: str = Field(default="", max_length=40)
    source: str = Field(default="", max_length=400)
    engine: Literal["kit", "hand_drift"] = "kit"
    notes: str = Field(default="", max_length=4000)
    recipe: dict[str, Any]
    controls: list[Control] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def _keys(self):
        keys = [c.key for c in self.controls]
        if len(set(keys)) != len(keys):
            raise ValueError("control keys must be unique")
        if len(json.dumps(self.recipe)) > RECIPE_MAX_BYTES:
            raise ValueError(f"recipe larger than {RECIPE_MAX_BYTES} bytes")
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


def spec_at(study: Study, recipe: dict, path: str) -> Spec:
    return kit_spec(recipe, path) if study.engine == "kit" else hand_drift_spec(path)


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


def validate_recipe(study: Study, recipe: dict, lib: FL.FrozenLibrary) -> dict:
    """Engine validation → the normalized recipe (defaults filled)."""
    if study.engine == "kit":
        kit = _kit()
        try:
            out = kit.validate(recipe, library=lib)
        except (kit.RecipeError, KeyError) as e:
            raise StudyError(f"recipe: {e}") from None
        # the kit allows sheets up to 2 m; the app keeps a study near bed size
        # (ink is laid in mm, so a huge frame is a huge, slow drawing)
        if not all(FRAME_MM[0] <= v <= FRAME_MM[1] for v in out["frame"]):
            raise StudyError(f"recipe: frame sides must be {FRAME_MM[0]:g}–{FRAME_MM[1]:g} mm, got {out['frame']}")
        return out
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
        elif c.type == "choice":
            if sp.type != "choice":
                raise StudyError(f"{where}: the param is {sp.type}, not a choice")
            if c.choices is not None and not set(c.choices) <= set(sp.choices):
                raise StudyError(f"{where}: choices {c.choices} are not all among {list(sp.choices)}")
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


def check_study(study: Study, lib: FL.FrozenLibrary | None = None) -> Study:
    """Semantic validation (recipe through its engine, every control against
    the params it points at, every default value against its control)."""
    lib = lib or FL.FrozenLibrary()
    recipe = validate_recipe(study, study.recipe, lib)
    controls = []
    for c in study.controls:
        _check_control(study, recipe, c)
        if c.type == "choice" and c.choices is None:      # spell the param's choices out for the bench
            c = c.model_copy(update={"choices": list(spec_at(study, recipe, c.targets[0]).choices)})
        coerce(study, recipe, c, get_at(recipe, c.targets[0]), lib)
        controls.append(c)
    return study.model_copy(update={"recipe": recipe, "controls": controls})


def defaults(study: Study) -> dict[str, Any]:
    return {c.key: copy.deepcopy(get_at(study.recipe, c.targets[0])) for c in study.controls}


def resolve(study: Study, values: dict[str, Any], lib: FL.FrozenLibrary) -> dict:
    """The recipe with the control values written in (validated)."""
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
    (the entries a kept layer pins explicitly)."""
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
