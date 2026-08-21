"""The whole run of a process, so a scrub is a slice instead of a re-run."""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

from .assets import asset_store
from .gencache import cache_budget_multiplier
from .model import Path
from .registry import field_bounds

if TYPE_CHECKING:
    from .process import ProcessModule


@dataclass
class Trajectory:
    #: per step: the marks added (accumulative) or the whole state (not)
    steps: list[list[Path]]
    telemetry: list[dict[str, float]]
    accumulative: bool

    def state(self, n: int) -> list[Path]:
        """The drawing as it stands at step ``n``."""
        if not self.steps:
            return []
        n = max(0, min(n, len(self.steps) - 1))
        if not self.accumulative:
            return list(self.steps[n])
        out: list[Path] = []
        for chunk in self.steps[: n + 1]:
            out.extend(chunk)
        return out


def _run(module: "ProcessModule", params: BaseModel) -> Trajectory:
    """The whole run, up to the time axis's upper bound.

    Bounds come from the PARAMS MODEL directly (``field_bounds`` on the
    field itself), never from a registry/session lookup keyed by
    ``module.id``: this module sits under ``session`` in the import graph
    (``session -> registry -> sources -> process -> trajectory``), so a
    lookup back up through the registry would be circular, and a process
    class under test is never registered, so a registry lookup would raise
    on the exact fixtures that exercise this function.
    """
    bounds = field_bounds(type(params).model_fields[module.time_axis])
    last = int(bounds[1]) if bounds else int(getattr(params, module.time_axis))
    steps: list[list[Path]] = []
    telemetry: list[dict[str, float]] = []
    for i, step in enumerate(module.run(params)):
        steps.append(list(step.paths))
        telemetry.append(dict(step.telemetry or {}))
        if i >= last:
            break
    return Trajectory(steps, telemetry, module.accumulative)


#: Cached trajectory points before LRU eviction. A trajectory of an
#: accumulative process is ONE drawing's worth of geometry however many steps
#: it has — the increments, not a snapshot per step — so this is generous.
#: Scaled by the same AXIBRIDGE_CACHE_BUDGET multiplier as every other cache,
#: so the Pi's 0.25 applies here too.
CACHE_BUDGET_POINTS = 4_000_000
CACHE_MAX_ENTRIES = 32

_lock = threading.Lock()
_CACHE: "OrderedDict[str, Trajectory]" = OrderedDict()


def clear_cache() -> None:
    with _lock:
        _CACHE.clear()


def _points(traj: Trajectory) -> int:
    return sum(len(p.points) for chunk in traj.steps for p in chunk)


def _evict_locked(protect_key: str) -> None:
    """Caller holds ``_lock``. Evicts the oldest entries — never
    ``protect_key``, the one just inserted — until both the point budget and
    the entry cap are satisfied, or nothing else is left to evict. Without
    the protection, an entry over budget on its own (a long accumulative
    trajectory can be) would still get popped once it is the last one
    standing, emptying the cache and forcing a recompute on the very next
    call for the same params — silently, forever, at a zero hit rate. An
    oversized single trajectory staying cached beats that. Mirrors
    ``gencache._evict_locked``'s protect-the-inserted-key contract, though
    that cache evicts randomly and this one evicts oldest-first (LRU, via
    ``OrderedDict``)."""
    budget = CACHE_BUDGET_POINTS * cache_budget_multiplier()
    while len(_CACHE) > CACHE_MAX_ENTRIES or sum(_points(t) for t in _CACHE.values()) > budget:
        victims = [k for k in _CACHE if k != protect_key]
        if not victims:
            break
        del _CACHE[victims[0]]


def _key(module: "ProcessModule", params: BaseModel) -> str:
    """Everything about the run EXCEPT where along it we are looking. Dropping
    the time axis from the key is the whole trick: every step of a scrub is
    then the same cache entry.

    Folds in ``asset_store.version()``, the same way ``gencache.generate_
    cached`` does — no ``ProcessModule`` takes an asset param today, so this
    is latent, but without it the first one that does would serve geometry
    from a replaced image forever (a project switch bumps the version but
    this cache has no other way to notice)."""
    raw = params.model_dump()
    raw.pop(module.time_axis, None)
    blob = json.dumps(
        {"id": module.id, "params": raw, "asset_version": asset_store.version()},
        sort_keys=True, default=str)
    return hashlib.blake2b(blob.encode(), digest_size=16).hexdigest()


def build(module: "ProcessModule", params: BaseModel) -> Trajectory:
    key = _key(module, params)
    with _lock:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return hit
    traj = _run(module, params)
    with _lock:
        _CACHE[key] = traj
        _CACHE.move_to_end(key)
        _evict_locked(key)
    return traj
