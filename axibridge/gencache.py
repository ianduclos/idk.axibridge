"""Content-keyed memo for ``SourceModule.generate()``.

A tween layer lerps generator params through the master timeline and
re-materialises every resolve — but a ``follow_master`` tween with IDENTICAL
params on both keyframes (only the window/curve differs) produces the exact
same ``(generator, params)`` pair every tick, and even a genuinely-morphing
tween revisits the same param set on loop playback or a scrub that overshoots
and comes back. None of that is cached anywhere else: ``Session._tween_cache``
and ``_clip_cache`` key on the SURROUNDING context (refs, offsets, master_t),
not on what actually gets handed to ``generate()``. This module is the one
layer low enough to catch it — a plain ``(source id, canonicalized params,
asset generation) -> PathDocument`` map, a singleton like ``assets.asset_store``
(same reasoning: reachable from the session, the live-preview endpoint, and
the tween module without an import cycle).

Eviction is RANDOM, not LRU: looped/scrubbed playback is a cyclic access
pattern (frame 0, 1, 2, ..., N, 0, 1, 2, ...) where LRU evicts exactly the
entry that is about to be reused next, i.e. a 0% hit rate at capacity. Random
eviction keeps a nonzero hit rate under the same access pattern.
"""

from __future__ import annotations

import os
import random
import threading
from typing import Any

from .render_work import checkpoint
from .assets import asset_store
from .model import PathDocument

#: Total cached points (summed once per entry, over all paths in the
#: document) allowed before random eviction kicks in. This machine has 32 GB
#: — the default is generous. The Pi is the constrained bench and runs with
#: ``AXIBRIDGE_CACHE_BUDGET=0.25`` (see the multiplier below) to keep the
#: memo from competing with everything else for RAM. Raise either the
#: constant or the env multiplier if a workload legitimately needs a bigger
#: cache.
GENERATE_MEMO_BUDGET_POINTS = 3_000_000

#: Hard cap on entry count regardless of point budget — a generator that
#: produces many tiny documents could otherwise accumulate unboundedly.
GENERATE_MEMO_MAX_ENTRIES = 128

_CACHE_BUDGET_MULTIPLIER = float(os.environ.get("AXIBRIDGE_CACHE_BUDGET", "1.0"))


def cache_budget_multiplier() -> float:
    """The ``AXIBRIDGE_CACHE_BUDGET`` env multiplier, read once at import
    (default ``1.0``). Exported so later cache-budgeted stages can apply the
    same per-machine scale without re-reading the env themselves."""
    return _CACHE_BUDGET_MULTIPLIER


_lock = threading.Lock()
_cache: dict[tuple[str, str, int], PathDocument] = {}
_points: dict[tuple[str, str, int], int] = {}
_total_points = 0


def _doc_points(doc: PathDocument) -> int:
    return sum(len(p.points) for layer in doc.layers for p in layer.paths)


def _evict_locked(protect_key: tuple[str, str, int]) -> None:
    """Caller holds ``_lock``. Evicts random entries (never ``protect_key``,
    the one just inserted) until both the point budget and the entry cap are
    satisfied, or nothing is left to evict."""
    global _total_points
    budget = int(GENERATE_MEMO_BUDGET_POINTS * cache_budget_multiplier())
    while _total_points > budget or len(_cache) > GENERATE_MEMO_MAX_ENTRIES:
        candidates = [k for k in _cache if k != protect_key]
        if not candidates:
            break
        victim = random.choice(candidates)
        _total_points -= _points.pop(victim)
        del _cache[victim]


def generate_cached(src: Any, params: dict[str, Any]) -> PathDocument:
    """Content-keyed memo of ``src.generate(src.Params(**params))``.

    Validation happens FIRST, unconditionally, so a bad ``params`` dict
    raises exactly as a direct call would (callers' try/except around
    validation errors keeps working unchanged). ``getattr(src, "cacheable",
    True) is False`` bypasses the cache entirely — the determinism escape
    hatch for a future nondeterministic source.

    The cache key folds in ``asset_store.version()``, so any asset upload or
    project load/new (both bump the version) implicitly orphans stale
    entries keyed on the old images — no explicit invalidation hooks needed
    anywhere that touches assets.

    The returned ``PathDocument`` is the cached object itself, not a copy:
    legal only because generate() must be pure and callers never mutate what
    it returns (the same contract effects/transforms already have)."""
    checkpoint()
    validated = src.Params(**params)
    if not getattr(src, "cacheable", True):
        return src.generate(validated)
    key = (src.id, validated.model_dump_json(), asset_store.version())
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            return hit
    doc = src.generate(validated)
    checkpoint()
    with _lock:
        # Another thread may have raced us to the same key (generate_cached
        # has its own lock independent of the session lock — the live-preview
        # endpoint calls it with no session lock held at all). Keep whichever
        # copy landed first so _total_points never double-counts one key.
        if key not in _cache:
            _cache[key] = doc
            _points[key] = _doc_points(doc)
            global _total_points
            _total_points += _points[key]
            _evict_locked(key)
        return _cache[key]


def clear() -> None:
    """Drop every cached entry. Called on project new/load for hygiene —
    the asset-version bump already orphans stale entries implicitly, this
    just reclaims the memory immediately instead of waiting on eviction."""
    global _total_points
    with _lock:
        _cache.clear()
        _points.clear()
        _total_points = 0
