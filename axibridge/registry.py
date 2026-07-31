"""Module registry: the extension mechanism for geometry modules.

Geometry module kinds (execution backends are the remaining extension point
and live in :mod:`axibridge.backends` because their lifecycle — port
ownership, threading — is nothing like a pure function over geometry):

* **Source** — ``params -> PathDocument``. Produces geometry from nothing.
  A generated document enters the compositor as a layer.
* **Effect** — ``(list[Path], params, ctx) -> list[Path]``. One step of a
  layer's non-destructive effect stack. Effects receive geometry already
  *placed* on the paper (the layer transform is applied first), so a
  physical parameter like "0.5 mm jitter" means 0.5 mm on the final sheet
  regardless of layer scale. ``ctx`` carries the layer id and translation
  for seed-stability and layer-anchored noise sampling.
* **Transform** — ``(PathDocument, params) -> PathDocument``. v1's
  document-level operation, retained for the plot-pass optimisation step
  (linesort/linemerge/simplify over resolved geometry); no longer a
  user-arranged pipeline.

Each module declares a Pydantic ``Params`` model. Its JSON Schema is shipped
to the frontend, which auto-generates the controls — adding a module requires
zero frontend work.

Registration is decorator-based::

    @register_source
    class Lissajous(SourceModule):
        id = "lissajous"
        ...

Modules placed in ``axibridge/sources/`` or ``axibridge/transforms/`` are
auto-imported at startup (see ``load_builtin_modules``), so dropping a new
file in is enough.
"""

from __future__ import annotations

import importlib
import pkgutil
from abc import ABC, abstractmethod
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

from pydantic import BaseModel

from .model import Path, PathDocument


class ModuleParams(BaseModel):
    """Base class for module parameter models (plain pydantic is fine too)."""


# -- generation progress -------------------------------------------------------
#
# Slow generators call ``report_progress`` from inside ``generate``; it is a
# no-op unless the caller (the API layer, which owns the event bus) installed
# a sink with ``progress_scope``. A contextvar so concurrent generations from
# two clients can't cross-talk; it survives FastAPI's threadpool because
# anyio copies the context into the worker thread.

_progress: ContextVar[Callable[[float, str], None] | None] = ContextVar(
    "generation_progress", default=None
)


def report_progress(frac: float, msg: str = "") -> None:
    """Cheap to call in inner loops: a sink decides throttling, not the module."""
    cb = _progress.get()
    if cb is not None:
        cb(frac, msg)


@contextmanager
def progress_scope(sink: Callable[[float, str], None]) -> Iterator[None]:
    token = _progress.set(sink)
    try:
        yield
    finally:
        _progress.reset(token)


class SourceModule(ABC):
    """Produces geometry from parameters alone."""

    id: str
    label: str
    description: str = ""
    Params: type[BaseModel] = ModuleParams

    @abstractmethod
    def generate(self, params: BaseModel) -> PathDocument:
        """Build and return a new document. Must not mutate shared state."""


class EffectContext(BaseModel):
    """What an effect may know about the layer it is shaping.

    ``translation`` is the layer transform's (e, f) component: noise-field
    effects sample their field at ``point - translation`` so dragging a layer
    around the canvas does not reshuffle its wobble. ``seed`` is stable per
    layer, so two overlapping layers with the same effect get distinct fields.
    ``page`` is the paper-guide rect (x, y, w, h — the bed when no guide is
    set), for effects whose geometry is page-relative (invert). ``None`` only
    in hand-built contexts; the resolve path always fills it.
    """

    layer_id: str = ""
    translation: tuple[float, float] = (0.0, 0.0)
    seed: int = 0
    page: tuple[float, float, float, float] | None = None


class EffectModule(ABC):
    """One step of a layer's non-destructive effect stack.

    Must be pure: return new ``Path`` objects, never mutate the input — the
    compositor caches and re-runs stacks freely. Preserve each path's
    ``filled`` flag (and closure: keep first==last for closed paths) so
    occlusion masks survive the stack.
    """

    id: str
    label: str
    description: str = ""
    Params: type[BaseModel] = ModuleParams

    @abstractmethod
    def apply(self, paths: list[Path], params: BaseModel, ctx: EffectContext) -> list[Path]: ...

    def available(self) -> tuple[bool, str]:
        return True, ""


class TransformModule(ABC):
    """Maps a document to a new document. Must be pure: never mutate the input
    (the UI's before/after view depends on the input surviving intact)."""

    id: str
    label: str
    description: str = ""
    #: "reshape" | "optimize" | "layout" — UI grouping only, no semantics.
    category: str = "reshape"
    Params: type[BaseModel] = ModuleParams

    @abstractmethod
    def apply(self, doc: PathDocument, params: BaseModel) -> PathDocument: ...

    def available(self) -> tuple[bool, str]:
        """Override to declare unavailability (e.g. missing optional dep).
        Returns (ok, reason-if-not)."""
        return True, ""


_SOURCES: dict[str, SourceModule] = {}
_TRANSFORMS: dict[str, TransformModule] = {}
_EFFECTS: dict[str, EffectModule] = {}


def register_source(cls: type[SourceModule]) -> type[SourceModule]:
    inst = cls()
    if inst.id in _SOURCES:
        raise ValueError(f"duplicate source module id: {inst.id}")
    _SOURCES[inst.id] = inst
    return cls


def register_effect(cls: type[EffectModule]) -> type[EffectModule]:
    inst = cls()
    if inst.id in _EFFECTS:
        raise ValueError(f"duplicate effect module id: {inst.id}")
    _EFFECTS[inst.id] = inst
    return cls


def register_transform(cls: type[TransformModule]) -> type[TransformModule]:
    inst = cls()
    if inst.id in _TRANSFORMS:
        raise ValueError(f"duplicate transform module id: {inst.id}")
    _TRANSFORMS[inst.id] = inst
    return cls


def sources() -> dict[str, SourceModule]:
    return dict(_SOURCES)


def transforms() -> dict[str, TransformModule]:
    return dict(_TRANSFORMS)


def effects() -> dict[str, EffectModule]:
    return dict(_EFFECTS)


def get_source(module_id: str) -> SourceModule:
    try:
        return _SOURCES[module_id]
    except KeyError:
        raise KeyError(f"unknown source module: {module_id!r}") from None


def get_transform(module_id: str) -> TransformModule:
    try:
        return _TRANSFORMS[module_id]
    except KeyError:
        raise KeyError(f"unknown transform module: {module_id!r}") from None


def get_effect(module_id: str) -> EffectModule:
    try:
        return _EFFECTS[module_id]
    except KeyError:
        raise KeyError(f"unknown effect module: {module_id!r}") from None


def describe_modules() -> dict[str, list[dict[str, Any]]]:
    """Module catalogue for the frontend: ids, labels, categories and the
    JSON Schema of each module's params (drives auto-generated controls)."""

    def describe(inst, kind: str) -> dict[str, Any]:
        ok, reason = (True, "") if kind == "source" else inst.available()
        d: dict[str, Any] = {
            "id": inst.id,
            "label": inst.label,
            "description": inst.description,
            "schema": inst.Params.model_json_schema(),
            "defaults": inst.Params().model_dump(),
            "available": ok,
            "unavailable_reason": reason,
        }
        if kind == "transform":
            d["category"] = inst.category
        return d

    return {
        "sources": [describe(m, "source") for m in _SOURCES.values()],
        "effects": [describe(m, "effect") for m in _EFFECTS.values()],
        "transforms": [describe(m, "transform") for m in _TRANSFORMS.values()],
    }


def load_builtin_modules() -> None:
    """Import every module in the sources / effects / transforms packages so
    their @register_* decorators run."""
    for pkg_name in ("axibridge.sources", "axibridge.effects", "axibridge.transforms"):
        pkg = importlib.import_module(pkg_name)
        for info in pkgutil.iter_modules(pkg.__path__):
            importlib.import_module(f"{pkg_name}.{info.name}")
