# FROZEN from research commit f59eac4: tools/gesture/gesture/kit/core.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Gesture kit core: Marks, Inks, Sheets, the module registry, recipes, seeds.

Spec: docs/superpowers/specs/2026-10-17-gesture-kit.md. How to add a
technique: kit/README.md (the contract; read it before writing a module).

Pipeline of one recipe (all in sheet millimetres, y down):

    arranger(ctx, parts)            places PARTS in the frame and returns Marks
      part.voice(box)               voice(ctx, **params) -> list[Mark], fitted into box
      part.modulate(marks)          modulator(ctx, marks, **params) -> list[Mark], chained
    renderer(ctx, marks)            per part (a part may override it) -> list[Ink]

Nothing here knows a particular technique: modules register with
`@voice/@modulator/@renderer/@arranger` from any file in this package, and
`discover()` imports every such file (new technique = new file).

Determinism: part i's seed is `recipe seed + i` (the Hand Drift bench's
"line i uses seed + i", so bench recipes reproduce); every other random
stream comes from `ctx.rng(*tags)`, a numpy Generator seeded from
(part seed, stage, module id, tags) with strings folded by CRC-32 — never
`hash()` (salted per process) and never set/dict order of anything unsorted.
"""
from __future__ import annotations

import copy
import importlib
import json
import math
import pkgutil
import sys
import time
import traceback
import warnings
import zlib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

KIT_VERSION = 1
KINDS = ("voice", "modulator", "renderer", "arranger")
REQUIRED_CHANNELS = ("r", "phi", "W", "M")
# Defaults = the Hand Drift bench's nib defaults (wire, 35°, 3.5 mm nib, 9 mm mass).
DEFAULT_CHANNELS = {"r": 0.0, "phi": math.radians(35.0), "W": 3.5, "M": 9.0}
DEFAULT_FRAME = (267.0, 180.0)
SEED_MAX = 2**31 - 1
PAPER = (0xFF, 0xFC, 0xF0)        # Flexoki paper
INK = (0x10, 0x0F, 0x0F)          # Flexoki black


class KitError(Exception):
    """Base class of kit errors."""


class RecipeError(KitError, ValueError):
    """A recipe (or a module's params) does not validate."""


class RegistrationError(KitError):
    """Two different modules claim the same (kind, id)."""


class ChannelError(KitError):
    """A stage broke the channel contract (bad shape, dropped a channel)."""


# ---------------------------------------------------------------------------
# channel interpolation kinds (how a channel follows when points are resampled)
# ---------------------------------------------------------------------------

_CHANNEL_KIND: dict[str, str] = {"phi": "axial", "voice": "nearest"}


def channel_kind(name: str, how: str | None = None) -> str:
    """Get (or declare, with `how`) how channel `name` is interpolated when a
    stage resamples points: "linear" (default), "axial" (an angle of period
    π, like a nib angle) or "nearest" (categorical, like `voice`)."""
    if how is not None:
        if how not in ("linear", "axial", "nearest"):
            raise ValueError("channel kind must be linear | axial | nearest")
        _CHANNEL_KIND[name] = how
    return _CHANNEL_KIND.get(name, "linear")


def _readonly(a: np.ndarray) -> np.ndarray:
    a.setflags(write=False)
    return a


def arclength(points: np.ndarray) -> np.ndarray:
    p = np.asarray(points, dtype=np.float64)
    if len(p) < 2:
        return np.zeros(len(p))
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def interp_channel(name: str, s_new: np.ndarray, s_old: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Channel `name` (values v at arc lengths s_old) at arc lengths s_new."""
    how = channel_kind(name)
    if len(v) == 1:
        return np.full(len(s_new), float(v[0]))
    if how == "axial":
        u = np.unwrap(2.0 * v) / 2.0
        return np.mod(np.interp(s_new, s_old, u), np.pi)
    if how == "nearest":
        j = np.clip(np.searchsorted(s_old, s_new, side="right") - 1, 0, len(v) - 1)
        nxt = np.clip(j + 1, 0, len(v) - 1)
        pick = np.where(np.abs(s_old[nxt] - s_new) < np.abs(s_new - s_old[j]), nxt, j)
        return v[pick].astype(np.float64)
    return np.interp(s_new, s_old, v)


# ---------------------------------------------------------------------------
# Mark, Ink, Sheet
# ---------------------------------------------------------------------------

@dataclass(frozen=True, eq=False)
class Mark:
    """One line in sheet millimetres with per-point channels.

    points (N, 2) float64; channels {name: (N,) float64} — always at least
    r (regime 0 wire … 1 nib … 2 mass), phi (nib angle, rad, period π),
    W (nib width, mm), M (mass width, mm); missing required channels are
    filled with DEFAULT_CHANNELS. Optional: voice (index into
    meta["voices"]), emphasis, tremor, … — unknown channels are carried by
    every stage. meta: voice id, hand log, fit, provenance ids, …

    Immutable: arrays are read-only copies; use `evolve` / `remap` /
    `resampled` / `transformed` to make new Marks."""

    points: np.ndarray
    channels: Mapping[str, np.ndarray] = field(default_factory=dict)
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        p = np.array(self.points, dtype=np.float64)
        if p.ndim != 2 or p.shape[1] != 2:
            raise ChannelError(f"Mark points must be (N, 2), got {p.shape}")
        if not np.all(np.isfinite(p)):
            raise ChannelError("Mark points must be finite")
        n = len(p)
        ch: dict[str, np.ndarray] = {}
        for k in sorted(self.channels):
            v = np.array(self.channels[k], dtype=np.float64)
            v = np.full(n, float(v)) if v.ndim == 0 else v
            if v.shape != (n,):
                raise ChannelError(f"channel {k!r} has shape {v.shape}, expected ({n},)")
            ch[k] = _readonly(v)
        for k in REQUIRED_CHANNELS:
            if k not in ch:
                ch[k] = _readonly(np.full(n, DEFAULT_CHANNELS[k]))
        object.__setattr__(self, "points", _readonly(p))
        object.__setattr__(self, "channels", dict(sorted(ch.items())))
        object.__setattr__(self, "meta", copy.deepcopy(dict(self.meta)))

    def __len__(self) -> int:
        return len(self.points)

    def __getitem__(self, name: str) -> np.ndarray:
        return self.channels[name]

    def channel(self, name: str, default: float | None = None) -> np.ndarray | None:
        if name in self.channels:
            return self.channels[name]
        return None if default is None else np.full(len(self), float(default))

    def arclength(self) -> np.ndarray:
        return arclength(self.points)

    def length(self) -> float:
        s = self.arclength()
        return float(s[-1]) if len(s) else 0.0

    def evolve(self, *, points=None, channels: Mapping | None = None, meta: Mapping | None = None,
               drop: Iterable[str] = ()) -> "Mark":
        """A new Mark: `channels` and `meta` are MERGED over this mark's (a
        value of None in meta deletes the key); `drop` removes channels
        (required ones come back as defaults). Changing the point count
        requires every kept channel to be given anew — use `remap` instead."""
        pts = self.points if points is None else points
        ch = {k: v for k, v in self.channels.items() if k not in set(drop)}
        ch.update(channels or {})
        n = len(np.asarray(pts))
        stale = [k for k, v in ch.items() if len(np.atleast_1d(v)) != n and np.ndim(v) != 0]
        if stale:
            raise ChannelError(f"evolve changed the point count; give channels {stale} anew or use remap()")
        md = dict(self.meta)
        for k, v in (meta or {}).items():
            if v is None:
                md.pop(k, None)
            else:
                md[k] = v
        return Mark(pts, ch, md)

    def remap(self, s_new, points=None, channels: Mapping | None = None, meta: Mapping | None = None) -> "Mark":
        """A new Mark sampled at arc lengths `s_new` of THIS mark: every
        channel is interpolated by its channel_kind (so unknown channels pass
        through); `points` default to this line at s_new (give your own to
        displace them); `channels` then override."""
        s_old = self.arclength()
        s_new = np.asarray(s_new, dtype=np.float64)
        if points is None:
            points = np.column_stack([np.interp(s_new, s_old, self.points[:, 0]),
                                      np.interp(s_new, s_old, self.points[:, 1])])
        ch = {k: interp_channel(k, s_new, s_old, v) for k, v in self.channels.items()}
        ch.update(channels or {})
        md = dict(self.meta)
        md.update(meta or {})
        return Mark(points, ch, md)

    def resampled(self, step: float) -> "Mark":
        """Uniform arc-length resampling at ≈ `step` mm (ends kept)."""
        s = self.arclength()
        L = float(s[-1]) if len(s) else 0.0
        if L <= 0 or len(self) < 2:
            return self
        n = max(int(round(L / max(step, 1e-9))), 2)
        return self.remap(np.linspace(0.0, L, n + 1))

    def transformed(self, scale: float, offset) -> "Mark":
        """points·scale + offset (channels untouched; a recorded meta["fit"]
        is composed so arrangers can refit again later)."""
        off = np.asarray(offset, dtype=np.float64)
        md = dict(self.meta)
        if "fit" in md:
            f = md["fit"]
            md["fit"] = {"scale": float(f["scale"]) * scale,
                         "offset": [float(v) for v in np.asarray(f["offset"]) * scale + off]}
        return Mark(self.points * scale + off, self.channels, md)

    def to_json(self) -> dict:
        return {"points": self.points.tolist(), "channels": {k: v.tolist() for k, v in self.channels.items()},
                "meta": _jsonable(self.meta)}

    @staticmethod
    def from_json(d: dict) -> "Mark":
        return Mark(np.asarray(d["points"], float).reshape(-1, 2), d.get("channels", {}), d.get("meta", {}))


@dataclass(frozen=True, eq=False)
class Ink:
    """One plotter polyline in sheet mm. `closed`: first point == last;
    `filled`: an outline ring that should occlude (a mass or ribbon rim)."""

    points: np.ndarray
    closed: bool = False
    filled: bool = False
    pen: float = 0.4
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        p = np.array(self.points, dtype=np.float64)
        if p.ndim != 2 or p.shape[1] != 2:
            raise ChannelError(f"Ink points must be (N, 2), got {p.shape}")
        object.__setattr__(self, "points", _readonly(p))
        object.__setattr__(self, "meta", dict(self.meta))


@dataclass
class Sheet:
    """The result of `run(recipe)`: marks (after modulators), inks (after
    renderers) and meta (normalized recipe, library ids used, parts, timing)."""

    frame: tuple[float, float]
    marks: list[Mark]
    inks: list[Ink]
    meta: dict

    @property
    def recipe(self) -> dict:
        return self.meta["recipe"]

    def save_recipe(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.recipe, indent=1) + "\n")
        return path

    def to_svg(self, path, *, stroke: str = "#100F0F") -> Path:
        """A plain mm SVG of the inks (one <path> per ink)."""
        W, H = self.frame
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
               f'<g fill="none" stroke="{stroke}" stroke-linecap="round" stroke-linejoin="round">']
        for ink in self.inks:
            if len(ink.points) < 2:
                continue
            d = "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in ink.points)
            out.append(f'<path d="{d}" stroke-width="{ink.pen:g}"/>')
        out.append("</g></svg>")
        path = Path(path)
        path.write_text("\n".join(out) + "\n")
        return path


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.generic):
        return o.item()
    return o


# ---------------------------------------------------------------------------
# params
# ---------------------------------------------------------------------------

PARAM_TYPES = ("int", "float", "bool", "str", "choice", "ref", "refs", "floats")


@dataclass(frozen=True)
class Param:
    """One module parameter. type: int | float | bool | str | choice
    (one of `choices`) | ref (a library id of `kind`) | refs (a list of
    them, min_len..max_len) | floats (a list of floats). min/max bound
    numbers (and list items for floats). optional=True allows None."""

    name: str
    type: str
    default: Any
    doc: str = ""
    min: float | None = None
    max: float | None = None
    choices: tuple | None = None
    kind: str | None = None
    min_len: int | None = None
    max_len: int | None = None
    optional: bool = False

    def __post_init__(self):
        if self.type not in PARAM_TYPES:
            raise RegistrationError(f"param {self.name!r}: unknown type {self.type!r} ({PARAM_TYPES})")
        if self.type in ("ref", "refs") and not self.kind:
            raise RegistrationError(f"param {self.name!r}: ref params need kind=")
        if self.type == "choice" and not self.choices:
            raise RegistrationError(f"param {self.name!r}: choice params need choices=")
        if self.type in ("int", "float") and (self.min is None or self.max is None):
            raise RegistrationError(f"param {self.name!r}: numeric params must be bounded (min=, max=)")
        if self.default is not None or not self.optional:
            self.validate(self.default, where="default")

    def validate(self, v, *, where: str = "") -> Any:
        where = where or self.name
        if v is None:
            if self.optional:
                return None
            raise RecipeError(f"{where}: {self.name} may not be None")
        t = self.type
        if t == "bool":
            if not isinstance(v, (bool, np.bool_)):
                raise RecipeError(f"{where}: {self.name} must be true/false, got {v!r}")
            return bool(v)
        if t in ("int", "float"):
            if isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, float, np.integer, np.floating)):
                raise RecipeError(f"{where}: {self.name} must be a number, got {v!r}")
            if t == "int":
                if float(v) != int(v):
                    raise RecipeError(f"{where}: {self.name} must be an integer, got {v!r}")
                v = int(v)
            else:
                v = float(v)
                if not math.isfinite(v):
                    raise RecipeError(f"{where}: {self.name} must be finite")
            if v < self.min or v > self.max:
                raise RecipeError(f"{where}: {self.name}={v} outside [{self.min}, {self.max}]")
            return v
        if t in ("str", "ref"):
            if not isinstance(v, str):
                raise RecipeError(f"{where}: {self.name} must be a string, got {v!r}")
            return v
        if t == "choice":
            if v not in self.choices:
                raise RecipeError(f"{where}: {self.name}={v!r} not one of {list(self.choices)}")
            return v
        if t in ("refs", "floats"):
            if isinstance(v, (str, bytes)) or not isinstance(v, (list, tuple)):
                raise RecipeError(f"{where}: {self.name} must be a list, got {v!r}")
            if self.min_len is not None and len(v) < self.min_len:
                raise RecipeError(f"{where}: {self.name} needs ≥ {self.min_len} items")
            if self.max_len is not None and len(v) > self.max_len:
                raise RecipeError(f"{where}: {self.name} takes ≤ {self.max_len} items")
            if t == "refs":
                if not all(isinstance(x, str) for x in v):
                    raise RecipeError(f"{where}: {self.name} items must be strings")
                return [str(x) for x in v]
            out = []
            for x in v:
                if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x)):
                    raise RecipeError(f"{where}: {self.name} items must be finite numbers")
                if (self.min is not None and x < self.min) or (self.max is not None and x > self.max):
                    raise RecipeError(f"{where}: {self.name} item {x} outside [{self.min}, {self.max}]")
                out.append(float(x))
            return out
        raise RecipeError(f"{where}: unhandled type {t}")

    def to_json(self) -> dict:
        d = {"name": self.name, "type": self.type, "default": self.default, "doc": self.doc}
        for k in ("min", "max", "kind", "min_len", "max_len"):
            if getattr(self, k) is not None:
                d[k] = getattr(self, k)
        if self.choices:
            d["choices"] = list(self.choices)
        if self.optional:
            d["optional"] = True
        return d


def P(name: str, type: str, default, doc: str = "", **kw) -> Param:
    """Shorthand for Param(name, type, default, doc, **kw)."""
    return Param(name, type, default, doc, **kw)


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Module:
    kind: str
    id: str
    fn: Callable
    params: tuple[Param, ...]
    doc: str
    reach: Callable[[dict], float] | None
    source: str

    def param(self, name: str) -> Param:
        for p in self.params:
            if p.name == name:
                return p
        raise KeyError(name)

    def defaults(self) -> dict:
        return {p.name: copy.deepcopy(p.default) for p in self.params}

    def validate(self, spec: Mapping, *, where: str = "") -> dict:
        """{"id": ..., **params} → normalized {"id", every param} (defaults filled)."""
        where = where or f"{self.kind} {self.id!r}"
        names = [p.name for p in self.params]
        extra = sorted(k for k in spec if k != "id" and k not in names)
        if extra:
            raise RecipeError(f"{where}: unknown param(s) {extra}; known: {names}")
        out = {"id": self.id}
        for p in self.params:
            out[p.name] = p.validate(copy.deepcopy(spec[p.name]) if p.name in spec else copy.deepcopy(p.default),
                                     where=where)
        return out

    def reach_mm(self, params: dict) -> float:
        return float(self.reach(params)) if self.reach is not None else 0.0

    def spec(self) -> dict:
        return {"kind": self.kind, "id": self.id, "doc": self.doc, "source": self.source,
                "params": [p.to_json() for p in self.params]}


_REGISTRY: dict[str, dict[str, Module]] = {k: {} for k in KINDS}
DISCOVERY_ERRORS: dict[str, str] = {}


def _register(kind: str, id: str, params: Sequence[Param] = (), doc: str = "",
              reach: Callable[[dict], float] | None = None):
    if not isinstance(id, str) or not id or not id.replace("_", "").replace("-", "").isalnum():
        raise RegistrationError(f"{kind} id must be a non-empty [a-z0-9_-] string, got {id!r}")
    names = [p.name for p in params]
    if len(set(names)) != len(names):
        raise RegistrationError(f"{kind} {id!r}: duplicate param names")
    if "id" in names:
        raise RegistrationError(f"{kind} {id!r}: 'id' is reserved")

    def deco(fn: Callable) -> Callable:
        src = f"{fn.__module__}.{fn.__qualname__}"
        old = _REGISTRY[kind].get(id)
        if old is not None and old.source != src:
            raise RegistrationError(f"{kind} {id!r} is already registered by {old.source}; pick another id")
        _REGISTRY[kind][id] = Module(kind, id, fn, tuple(params), doc or (fn.__doc__ or "").strip().split("\n")[0],
                                     reach, src)
        return fn
    return deco


def voice(id: str, params: Sequence[Param] = (), doc: str = "", reach=None):
    """Register `fn(ctx, **params) -> list[Mark]` (centrelines fitted into ctx.box)."""
    return _register("voice", id, params, doc, reach)


def modulator(id: str, params: Sequence[Param] = (), doc: str = "", reach=None):
    """Register `fn(ctx, marks, **params) -> list[Mark]` (writes channels)."""
    return _register("modulator", id, params, doc, reach)


def renderer(id: str, params: Sequence[Param] = (), doc: str = "", reach=None):
    """Register `fn(ctx, marks, **params) -> list[Ink]`."""
    return _register("renderer", id, params, doc, reach)


def arranger(id: str, params: Sequence[Param] = (), doc: str = "", reach=None):
    """Register `fn(ctx, parts, **params) -> list[Mark]` placed in the frame."""
    return _register("arranger", id, params, doc, reach)


def get(kind: str, id: str) -> Module:
    discover()
    if kind not in _REGISTRY:
        raise RecipeError(f"unknown module kind {kind!r} ({KINDS})")
    try:
        return _REGISTRY[kind][id]
    except KeyError:
        raise RecipeError(f"unknown {kind} {id!r}; registered: {sorted(_REGISTRY[kind])}") from None


def registry(kind: str | None = None) -> dict:
    """{kind: {id: Module}} (or {id: Module} for one kind), sorted by id."""
    discover()
    if kind is not None:
        return dict(sorted(_REGISTRY[kind].items()))
    return {k: dict(sorted(v.items())) for k, v in _REGISTRY.items()}


_DISCOVERED = False
_SKIP = {"core", "library"}


def discover(force: bool = False) -> dict[str, str]:
    """Import every module file in this package (sorted by name; files
    starting with '_' and core/library skipped), so their decorators
    register. A file that fails to import is reported in DISCOVERY_ERRORS
    (and warned) instead of breaking every other technique. Returns
    DISCOVERY_ERRORS."""
    global _DISCOVERED
    if _DISCOVERED and not force:
        return DISCOVERY_ERRORS
    _DISCOVERED = True
    pkg_name = __name__.rsplit(".", 1)[0]
    pkg = sys.modules[pkg_name]
    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        name = info.name
        if name.startswith("_") or name in _SKIP or info.ispkg:
            continue
        full = f"{pkg_name}.{name}"
        try:
            if full in sys.modules and force:
                importlib.reload(sys.modules[full])
            else:
                importlib.import_module(full)
            DISCOVERY_ERRORS.pop(name, None)
        except Exception:  # noqa: BLE001 — one broken technique must not break the kit
            DISCOVERY_ERRORS[name] = traceback.format_exc()
            warnings.warn(f"gesture.kit: technique file {name}.py failed to import:\n{DISCOVERY_ERRORS[name]}",
                          stacklevel=2)
    return DISCOVERY_ERRORS


def list_modules(kind: str | None = None, *, file=None, quiet: bool = False) -> str:
    """Print (and return) every registered module with its params."""
    reg = registry()
    lines = []
    for k in KINDS if kind is None else (kind,):
        lines.append(f"== {k}s")
        for mid, m in reg[k].items():
            lines.append(f"  {mid:<12} {m.doc}   [{m.source.rsplit('.', 2)[-2]}.py]")
            for p in m.params:
                rng = ""
                if p.type in ("int", "float"):
                    rng = f" [{p.min:g}..{p.max:g}]"
                elif p.type == "choice":
                    rng = " {" + "|".join(map(str, p.choices)) + "}"
                elif p.type in ("ref", "refs"):
                    rng = f" <{p.kind}>"
                lines.append(f"      {p.name:<12} {p.type}{rng} = {json.dumps(p.default)}   {p.doc}")
    if DISCOVERY_ERRORS:
        lines.append("== discovery errors: " + ", ".join(sorted(DISCOVERY_ERRORS)))
    text = "\n".join(lines)
    if not quiet:
        print(text, file=file or sys.stdout)
    return text


def describe() -> dict:
    """JSON spec of every module (what a future bench renders controls from)."""
    return {k: [m.spec() for m in v.values()] for k, v in registry().items()}


# ---------------------------------------------------------------------------
# seeds
# ---------------------------------------------------------------------------

def tag(x) -> int:
    """A stable non-negative int for a seed tag: ints as is, strings by
    CRC-32 of their UTF-8 (never hash(), which is salted per process)."""
    if isinstance(x, (bool, np.bool_)):
        return int(x)
    if isinstance(x, (int, np.integer)):
        if x < 0:
            raise ValueError("seed tags must be ≥ 0")
        return int(x)
    if isinstance(x, str):
        return zlib.crc32(x.encode("utf-8"))
    raise TypeError(f"seed tags are ints or strings, got {type(x).__name__}")


def part_seed(sheet_seed: int, index: int) -> int:
    """Part i's seed: sheet seed + i (the Hand Drift bench's line seeds)."""
    return int(sheet_seed) + int(index)


# ---------------------------------------------------------------------------
# ctx + parts + run
# ---------------------------------------------------------------------------

class _Run:
    """Per-run shared state: library access + the record of ids used."""

    def __init__(self, library):
        self.library = library
        self.used: dict[tuple[str, str], dict] = {}
        self.notes: dict = {}

    def entry(self, kind: str, id: str) -> dict:
        e = self.library.entry(kind, id)
        self.used.setdefault((kind, id), {"kind": kind, "id": id, "version": e.get("version"),
                                          "policy": e.get("policy")})
        return e

    def use(self, kind: str, id: str, purpose: str = "generate"):
        obj = self.library.load(kind, id, purpose=purpose)
        self.entry(kind, id)
        return obj


@dataclass(frozen=True)
class Ctx:
    """What a stage knows. frame: sheet (W, H) mm; box: (x0, y0, w, h) the
    area this stage works in (a voice fits its marks into it); seed: the
    part's seed (sheet_seed for the arranger); stage/module: where we are."""

    frame: tuple[float, float]
    box: tuple[float, float, float, float]
    seed: int
    sheet_seed: int
    part: int
    stage: str
    module: str
    run: _Run = field(repr=False, compare=False)

    def rng(self, *tags) -> np.random.Generator:
        """A Generator seeded from (part seed, stage, module id, *tags)."""
        return np.random.default_rng([tag(self.seed), tag(self.stage), tag(self.module), *map(tag, tags)])

    def use(self, kind: str, id: str, purpose: str = "generate"):
        """Load a library entry's data through the policy gate (and record its id)."""
        return self.run.use(kind, id, purpose)

    def entry(self, kind: str, id: str) -> dict:
        """A library entry's metadata (entry.json), recorded as used."""
        return self.run.entry(kind, id)

    def note(self, key: str, value) -> None:
        """Record JSON-able structure for sheet.meta["notes"][key] (e.g. an
        arranger's composition score). Absent from meta when nothing is noted."""
        self.run.notes[str(key)] = copy.deepcopy(value)

    def with_box(self, box) -> "Ctx":
        return replace(self, box=tuple(float(v) for v in box))


class Part:
    """One voice → modulators chain (+ its renderer), handed to arrangers.
    `voice(box)` grows and fits the marks into box; `modulate(marks)` runs
    the modulators on placed marks; `run(box)` does both."""

    def __init__(self, index: int, spec: dict, renderer: dict, frame, sheet_seed: int, run: _Run, box):
        self.index = index
        self.spec = spec
        self.renderer = renderer
        self.label = spec.get("label") or ""
        self.seed = part_seed(sheet_seed, index)
        self._frame = tuple(frame)
        self._sheet_seed = sheet_seed
        self._run = run
        self.box = tuple(box)

    def ctx(self, stage: str, module: str, box=None) -> Ctx:
        return Ctx(self._frame, tuple(box if box is not None else self.box), self.seed, self._sheet_seed,
                   self.index, stage, module, self._run)

    def voice(self, box=None) -> list[Mark]:
        spec = self.spec["voice"]
        m = get("voice", spec["id"])
        params = {k: v for k, v in spec.items() if k != "id"}
        marks = m.fn(self.ctx("voice", m.id, box), **copy.deepcopy(params))
        marks = _check_marks(marks, f"voice {m.id!r}")
        return [mk.evolve(meta={"part": self.index, "voice_id": m.id}) for mk in marks]

    def modulate(self, marks: list[Mark], box=None) -> list[Mark]:
        for i, spec in enumerate(self.spec["modulators"]):
            m = get("modulator", spec["id"])
            params = {k: v for k, v in spec.items() if k != "id"}
            need = set.intersection(*(set(mk.channels) for mk in marks)) if marks else set()
            out = m.fn(self.ctx(f"modulator.{i}", m.id, box), list(marks), **copy.deepcopy(params))
            out = _check_marks(out, f"modulator {m.id!r}")
            for mk in out:
                lost = sorted(need - set(mk.channels))
                if lost:
                    raise ChannelError(f"modulator {m.id!r} dropped channel(s) {lost}; unknown channels must "
                                       "pass through (use Mark.evolve / Mark.remap)")
            marks = out
        return marks

    def run(self, box=None) -> list[Mark]:
        return self.modulate(self.voice(box), box)

    def reach(self) -> float:
        """How far ink may spread from a centreline (mm): max over its modules."""
        r = get("renderer", self.renderer["id"]).reach_mm(self.renderer)
        r = max(r, get("voice", self.spec["voice"]["id"]).reach_mm(self.spec["voice"]))
        for spec in self.spec["modulators"]:
            r = max(r, get("modulator", spec["id"]).reach_mm(spec))
        return r


def _check_marks(marks, where: str) -> list[Mark]:
    if not isinstance(marks, (list, tuple)):
        raise ChannelError(f"{where} must return a list of Marks, got {type(marks).__name__}")
    for mk in marks:
        if not isinstance(mk, Mark):
            raise ChannelError(f"{where} returned a {type(mk).__name__}, not a Mark")
    return list(marks)


_TOP = ("label", "notes", "frame", "seed", "margin", "arranger", "parts", "renderer", "voice", "modulators", "kit")
_PART = ("label", "voice", "modulators", "renderer")


def _module_spec(kind: str, spec, where: str, library=None) -> dict:
    if isinstance(spec, str):
        spec = {"id": spec}
    if not isinstance(spec, Mapping) or "id" not in spec:
        raise RecipeError(f"{where}: a {kind} is {{\"id\": ..., params}}, got {spec!r}")
    m = get(kind, spec["id"])
    out = m.validate(spec, where=f"{where} ({kind} {spec['id']!r})")
    if library is not None:
        for p in m.params:
            v = out[p.name]
            refs = [v] if p.type == "ref" and v is not None else (v or []) if p.type == "refs" else []
            for ref in refs:
                if not library.has(p.kind, ref):
                    raise RecipeError(f"{where} ({kind} {m.id!r}): {p.name}={ref!r} is not a library "
                                      f"{p.kind}; have {library.ids(p.kind)}")
    return out


def validate(recipe: Mapping, *, library=None) -> dict:
    """Normalize a recipe: shorthand expanded, every module id checked, every
    param validated and defaults filled. Returns a new JSON-native dict
    (saving it reproduces the run). Library refs are checked against
    `library` (default: the committed library). Raises RecipeError."""
    discover()
    if library is None:
        from . import library as _lib  # noqa: PLC0415
        library = _lib.default()
    if not isinstance(recipe, Mapping):
        raise RecipeError("a recipe is a dict")
    extra = sorted(k for k in recipe if k not in _TOP)
    if extra:
        raise RecipeError(f"recipe: unknown key(s) {extra}; known: {list(_TOP)}")
    r = copy.deepcopy(dict(recipe))
    if "parts" in r and ("voice" in r or "modulators" in r):
        raise RecipeError("recipe: give either parts or a top-level voice/modulators, not both")
    if "parts" not in r:
        if "voice" not in r:
            raise RecipeError("recipe: needs parts (or a top-level voice)")
        r["parts"] = [{"voice": r.pop("voice"), "modulators": r.pop("modulators", [])}]
    frame = r.get("frame", list(DEFAULT_FRAME))
    if (not isinstance(frame, (list, tuple)) or len(frame) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in frame)
            or not all(10.0 <= float(v) <= 2000.0 for v in frame)):
        raise RecipeError(f"recipe: frame must be [W, H] mm in [10, 2000], got {frame!r}")
    seed = r.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= SEED_MAX:
        raise RecipeError(f"recipe: seed must be an int in [0, {SEED_MAX}], got {seed!r}")
    margin = r.get("margin")
    if margin is not None and (isinstance(margin, bool) or not isinstance(margin, (int, float))
                               or not 0.0 <= float(margin) <= 0.25 * min(frame)):
        raise RecipeError(f"recipe: margin must be null or mm in [0, {0.25 * min(frame):g}]")
    parts = r["parts"]
    if not isinstance(parts, list) or not parts:
        raise RecipeError("recipe: parts must be a non-empty list")
    out_parts = []
    for i, p in enumerate(parts):
        where = f"part {i}"
        if not isinstance(p, Mapping):
            raise RecipeError(f"{where}: must be a dict")
        bad = sorted(k for k in p if k not in _PART)
        if bad:
            raise RecipeError(f"{where}: unknown key(s) {bad}; known: {list(_PART)}")
        if "voice" not in p:
            raise RecipeError(f"{where}: needs a voice")
        mods = p.get("modulators", [])
        if not isinstance(mods, list):
            raise RecipeError(f"{where}: modulators must be a list")
        q = {"voice": _module_spec("voice", p["voice"], where, library),
             "modulators": [_module_spec("modulator", m, f"{where} modulator {j}", library) for j, m in enumerate(mods)]}
        if p.get("renderer") is not None:
            q["renderer"] = _module_spec("renderer", p["renderer"], where, library)
        if p.get("label"):
            q["label"] = str(p["label"])
        out_parts.append(q)
    out = {"kit": KIT_VERSION, "frame": [float(frame[0]), float(frame[1])], "seed": int(seed),
           "margin": None if margin is None else float(margin),
           "arranger": _module_spec("arranger", r.get("arranger", {"id": "single"}), "recipe", library),
           "parts": out_parts,
           "renderer": _module_spec("renderer", r.get("renderer", {"id": "wire"}), "recipe", library)}
    for k in ("label", "notes"):
        if r.get(k):
            out[k] = str(r[k])
    return out


def run(recipe: Mapping, *, library=None) -> Sheet:
    """Run a recipe → Sheet. Deterministic in the recipe alone."""
    from . import library as _lib  # noqa: PLC0415
    t0 = time.perf_counter()
    lib = library if library is not None else _lib.default()
    rec = validate(recipe, library=lib)
    state = _Run(lib)
    W, H = rec["frame"]
    seed = rec["seed"]
    parts = [Part(i, p, p.get("renderer", rec["renderer"]), (W, H), seed, state, (0.0, 0.0, W, H))
             for i, p in enumerate(rec["parts"])]
    inset = rec["margin"] if rec["margin"] is not None else max(p.reach() for p in parts)
    inset = min(inset, 0.25 * min(W, H))
    box = (inset, inset, W - 2 * inset, H - 2 * inset)
    for p in parts:
        p.box = box
    arr = get("arranger", rec["arranger"]["id"])
    actx = Ctx((W, H), box, seed, seed, -1, "arranger", arr.id, state)
    marks = arr.fn(actx, parts, **{k: v for k, v in copy.deepcopy(rec["arranger"]).items() if k != "id"})
    marks = _check_marks(marks, f"arranger {arr.id!r}")
    t1 = time.perf_counter()
    inks: list[Ink] = []
    for p in parts:
        mine = [m for m in marks if m.meta.get("part") == p.index]
        rnd = get("renderer", p.renderer["id"])
        out = rnd.fn(p.ctx("renderer", rnd.id, box), mine, **{k: v for k, v in copy.deepcopy(p.renderer).items()
                                                               if k != "id"})
        for ink in out:
            if not isinstance(ink, Ink):
                raise ChannelError(f"renderer {rnd.id!r} returned a {type(ink).__name__}, not an Ink")
        inks += [Ink(k.points, k.closed, k.filled, k.pen, {**k.meta, "part": p.index}) for k in out]
    t2 = time.perf_counter()
    used = [state.used[k] for k in sorted(state.used)]
    meta = {"recipe": rec, "library": used, "inset": inset, "kit": KIT_VERSION,
            "parts": [{"index": p.index, "seed": p.seed, "voice": p.spec["voice"]["id"],
                       "modulators": [m["id"] for m in p.spec["modulators"]], "renderer": p.renderer["id"],
                       "label": p.label} for p in parts],
            "seconds": {"marks": round(t1 - t0, 3), "inks": round(t2 - t1, 3)}}
    if state.notes:
        meta["notes"] = state.notes
    return Sheet((W, H), marks, inks, meta)


# ---------------------------------------------------------------------------
# geometry helpers for voices and arrangers
# ---------------------------------------------------------------------------

def fit(points: Sequence[np.ndarray], box) -> tuple[float, np.ndarray]:
    """(scale, offset) fitting the bbox of all `points` (native units) into
    box (x0, y0, w, h), centred, uniform scale — the Hand Drift bench's fit.
    mm = native·scale + offset."""
    P_ = np.vstack([np.asarray(p, float) for p in points if len(p)])
    lo, hi = P_.min(axis=0), P_.max(axis=0)
    x0, y0, w, h = box
    bw, bh = hi - lo
    s = min(w / max(bw, 1e-9), h / max(bh, 1e-9))
    centre = np.array([x0 + 0.5 * w, y0 + 0.5 * h])
    return float(s), centre - (lo + hi) / 2 * s


def fitted(native: Sequence[np.ndarray], box, channels: Sequence[Mapping] | None = None,
           metas: Sequence[Mapping] | None = None) -> list[Mark]:
    """Marks from native polylines fitted together into box; each records
    meta["fit"] = {scale, offset} so arrangers can refit (`refit`)."""
    s, off = fit(native, box)
    out = []
    for i, p in enumerate(native):
        md = dict(metas[i]) if metas else {}
        md["fit"] = {"scale": s, "offset": [float(off[0]), float(off[1])]}
        out.append(Mark(np.asarray(p, float) * s + off, channels[i] if channels else {}, md))
    return out


def native_bbox(marks: Sequence[Mark]) -> tuple[np.ndarray, np.ndarray, float] | None:
    """(lo, hi) of the marks in their voice's native units + current scale,
    from meta["fit"]; None if any mark lacks a fit."""
    if not marks or any("fit" not in m.meta for m in marks):
        return None
    pts = []
    s0 = float(marks[0].meta["fit"]["scale"])
    for m in marks:
        f = m.meta["fit"]
        pts.append((m.points - np.asarray(f["offset"])) / float(f["scale"]))
    P_ = np.vstack(pts)
    return P_.min(axis=0), P_.max(axis=0), s0


def refit(marks: Sequence[Mark], box, scale: float | None = None) -> list[Mark]:
    """Move marks (together) into box, centred: at native `scale` if given
    (needs meta["fit"]), else as large as fits. Channels untouched."""
    if not marks:
        return []
    P_ = np.vstack([m.points for m in marks])
    lo, hi = P_.min(axis=0), P_.max(axis=0)
    x0, y0, w, h = box
    bw, bh = hi - lo
    if scale is not None:
        nb = native_bbox(marks)
        if nb is None:
            raise KitError("refit at a native scale needs meta['fit'] on every mark")
        k = scale / nb[2]
    else:
        k = min(w / max(bw, 1e-9), h / max(bh, 1e-9))
    centre = np.array([x0 + 0.5 * w, y0 + 0.5 * h])
    off = centre - (lo + hi) / 2 * k
    return [m.transformed(k, off) for m in marks]


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------

def _font(size: int):
    from PIL import ImageFont  # noqa: PLC0415
    for f in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/SFNS.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def summary(recipe: Mapping) -> str:
    """One line naming a recipe's modules (for labels)."""
    rec = recipe
    bits = []
    for p in rec["parts"]:
        v = p["voice"]
        who = v.get("hands") or v.get("hand") or ""
        who = "→".join(who) if isinstance(who, list) else who
        mods = "+".join(m["id"] if m["id"] != "timing" else f"timing:{m.get('tempo')}" for m in p["modulators"])
        r = p.get("renderer")
        bits.append(f"{v['id']}({who})" + (f" ~{mods}" if mods else "") + (f" /{r['id']}" if r else ""))
    rd = rec["renderer"]
    rs = rd["id"] + (f":{rd['style']}" if "style" in rd else "")
    return f"{rec['arranger']['id']}[ " + " | ".join(bits) + f" ] {rs}  seed {rec['seed']}"


def render_image(sheet: Sheet, *, px_per_mm: float = 6.0, label: str | None = "auto", ss: int = 2):
    """PIL image of the sheet: inks at their pen width on warm paper, with a
    label strip (label="auto" → recipe summary; None → no strip)."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    W, H = sheet.frame
    k = px_per_mm * ss
    im = Image.new("L", (int(round(W * k)), int(round(H * k))), 0)
    dr = ImageDraw.Draw(im)
    for ink in sheet.inks:
        q = ink.points * k
        d = max(ink.pen * k, 1.0)
        if len(q) >= 2:
            dr.line([tuple(v) for v in q], fill=255, width=max(int(round(d)), 1), joint="curve")
        r = d / 2
        for v in (q if d > 4 else q[[0, -1]]):
            dr.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=255)
    im = im.resize((im.width // ss, im.height // ss), Image.Resampling.BOX)
    a = np.asarray(im, dtype=np.float64)[..., None] / 255.0
    rgb = (np.array(PAPER) * (1 - a) + np.array(INK) * a).astype(np.uint8)
    out = Image.fromarray(rgb, "RGB")
    if label is None:
        return out
    text = summary(sheet.recipe) if label == "auto" else label
    fs = max(12, int(out.width / 80))
    strip = Image.new("RGB", (out.width, int(fs * 2.0)), PAPER)
    ImageDraw.Draw(strip).text((int(fs * 0.6), int(fs * 0.45)), text, fill=INK, font=_font(fs))
    full = Image.new("RGB", (out.width, out.height + strip.height), PAPER)
    full.paste(out, (0, 0))
    full.paste(strip, (0, out.height))
    return full


def preview(sheet: Sheet, path, *, px_per_mm: float = 6.0, label: str | None = "auto",
            recipe_beside: bool = True, quality: int = 88) -> Path:
    """Write the standard ink-on-paper image (jpg/png by suffix) and, by
    default, the normalized recipe beside it (<stem>.recipe.json)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im = render_image(sheet, px_per_mm=px_per_mm, label=label)
    if path.suffix.lower() in (".jpg", ".jpeg"):
        im.save(path, quality=quality, optimize=True)
    else:
        im.save(path)
    if recipe_beside:
        sheet.save_recipe(path.with_suffix(".recipe.json"))
    return path


def contact(images: Sequence, cols: int, *, title: str | None = None, gap: int = 16):
    """Tile PIL images (equal widths assumed) on paper, optional title."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    rows = -(-len(images) // cols)
    cw = max(im.width for im in images)
    ch = max(im.height for im in images)
    th = 0
    fs = max(14, int(cw / 55))
    if title:
        th = int(fs * 2.2)
    sheet = Image.new("RGB", (cols * cw + (cols + 1) * gap, th + rows * ch + (rows + 1) * gap), PAPER)
    dr = ImageDraw.Draw(sheet)
    if title:
        dr.text((gap, int(fs * 0.6)), title, fill=INK, font=_font(fs))
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        x, y = gap + c * (cw + gap), th + gap + r * (ch + gap)
        sheet.paste(im, (x, y))
        dr.rectangle([x - 1, y - 1, x + im.width, y + im.height], outline=(0xE6, 0xE4, 0xD9))
    return sheet
