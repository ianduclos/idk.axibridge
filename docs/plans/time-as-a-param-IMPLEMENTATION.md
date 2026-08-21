# Time as a Param — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give generators an optional time axis, so a process can be scrubbed, watched in a popup, bound to the master timeline, and stamped as several moments on one sheet — without a second geometry path into the plotter.

**Architecture:** Time is an ordinary bounded param; `generate()` stays a pure function of params. A `ProcessModule` base yields per-step *increments*, and a trajectory cache runs the whole process once so scrubbing is a prefix slice rather than a re-run. The master timeline already folds `master_t` into a generator's `frame` field — that one method is generalised to fold into whatever axis a module declares.

**Tech Stack:** Python 3.13 + Pydantic v2 (`.venv/bin/python`), FastAPI, pytest, vanilla ES modules + Vite for the frontend, Playwright for UI acceptance.

**Spec:** `docs/plans/time-as-a-param.md` — read it first; this plan argues from it.

## Global Constraints

- **The interpreter is `.venv/bin/python`.** Never substitute another; it holds `pyaxidraw`, which is not on PyPI.
- **`generate()` must stay pure**: same params → same geometry, no mutation of inputs. `tests/test_orientation.py` and the generate-memo tests enforce it registry-wide the moment a module registers.
- **Every numeric param is bounded** (`ge`/`le`). A time axis *must* be bounded — the fold reads those bounds, and an unbounded axis is treated as no axis at all.
- **Every source must declare `orientation`** (`"none" | "param" | "geometry"`) or `tests/test_orientation.py` fails.
- **Frontend source lives in `axibridge/static/**`**; the server serves the built `static_dist/` when it exists. Run `npm run build` after any JS/HTML change or a stale bundle shadows it.
- **Undo discipline:** any `Session` method that mutates the project calls `self._checkpoint()` once, under `self._lock`, before mutating.
- **Coordinates are millimetres**, machine frame, x ≤ 300, y ≤ 218.
- Commit style: conventional (`feat:`, `fix:`, `docs:`), ending with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Full suite must stay green: `.venv/bin/python -m pytest -q` (1080 passing, 1 environmental skip as of 2026-08-21).

---

### Task 1: Declare a time axis, and generalise the master_t fold

**Files:**
- Modify: `axibridge/registry.py` (`SourceModule`, after the `cacheable` attribute ~line 116)
- Modify: `axibridge/session.py:452-476` (`_effective_gen_params`)
- Modify: `axibridge/sources/grammar.py:218` (the `Grammar` class body)
- Test: `tests/test_time_axis.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `SourceModule.time_axis: str | None`; `Session.time_axis(generator_id) -> str | None`; `Session.axis_bounds(generator_id, axis) -> tuple[float, float] | None`. Later tasks call `Session.time_axis` to decide whether a layer is watchable.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_time_axis.py
"""A generator's time axis: which param the master timeline scrubs.

`frame` was always this mechanism; it was just hardcoded and named after
video. These tests pin the generalisation AND the fact that the old path is
unchanged, because every image generator depends on it."""

import pytest

from axibridge.compose import CanvasLayer, LayerSource
from axibridge.session import session


def layer(generator: str, params: dict, **kw) -> CanvasLayer:
    return CanvasLayer(
        source=LayerSource(type="generator", generator=generator, params=params), **kw)


def test_an_undeclared_generator_has_no_time_axis():
    assert Session.time_axis("polygon") is None


def test_a_generator_with_a_frame_field_keeps_the_old_axis_without_declaring_it():
    """No migration: every image generator predates the declaration and must
    keep working whether or not anyone remembers to add one."""
    assert Session.time_axis("image_threshold") == "frame"


def test_grammar_declares_its_iteration_count_as_time():
    assert Session.time_axis("grammar") == "iterations"


def test_master_t_maps_onto_the_axis_own_bounds():
    """master_t is 0..1; the axis is whatever it is. Halfway through the
    timeline is halfway through the process."""
    lyr = layer("grammar", {"iterations": 1}, frame_follow=True)
    got = Session._effective_gen_params(lyr, master_t=0.5)
    # iterations is ge=1 le=8, and 1 + 0.5*(8-1) = 4.5 -> 4 (int field)
    assert got["iterations"] == 4


def test_an_integer_axis_is_rounded_not_handed_a_float():
    """Pydantic v2 REJECTS 4.5 for an int field rather than truncating it, so
    an unrounded fold would 422 on a scrub."""
    lyr = layer("grammar", {"iterations": 1}, frame_follow=True)
    for t in (0.0, 0.13, 0.5, 0.99, 1.0):
        got = Session._effective_gen_params(lyr, master_t=t)
        assert isinstance(got["iterations"], int)
        assert 1 <= got["iterations"] <= 8


def test_the_fold_never_leaves_the_axis_bounds():
    lyr = layer("grammar", {"iterations": 8}, frame_follow=True)
    assert Session._effective_gen_params(lyr, master_t=1.0)["iterations"] == 8


def test_a_frame_axis_is_byte_identical_to_the_old_behaviour():
    """frame is ge=0 le=1, so normalising against its own bounds is the
    identity — the old hardcoded path is the special case, not a parallel one."""
    lyr = layer("image_threshold", {"image": "x.png", "frame": 0.25},
                frame_follow=True)
    assert Session._effective_gen_params(lyr, master_t=0.5)["frame"] == 0.75


def test_the_stored_params_are_never_mutated():
    params = {"iterations": 2}
    lyr = layer("grammar", params, frame_follow=True)
    Session._effective_gen_params(lyr, master_t=1.0)
    assert params == {"iterations": 2}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest -q tests/test_time_axis.py`
Expected: FAIL — `AttributeError: type object 'Session' has no attribute 'time_axis'`.

- [ ] **Step 3: Declare the attribute on `SourceModule`, and add the bounds helper**

In `axibridge/registry.py`, add this module-level function (near the top, after
the imports) — it takes a *field*, not a generator id, so that `trajectory.py`
can read bounds without importing the session or the registry lookup, which
would be a circular import and would also break unregistered test fixtures:

```python
def field_bounds(field: Any) -> tuple[float, float] | None:
    """A numeric field's ``ge``/``le``, or None unless BOTH are set.

    Pydantic v2 keeps these in ``field.metadata`` as ``annotated_types``
    markers rather than as attributes on the field itself."""
    lo = hi = None
    for meta in field.metadata:
        lo = getattr(meta, "ge", lo) if getattr(meta, "ge", None) is not None else lo
        hi = getattr(meta, "le", hi) if getattr(meta, "le", None) is not None else hi
    return (float(lo), float(hi)) if lo is not None and hi is not None else None
```

Then, directly below the `cacheable` attribute:

```python
    #: The param that is this generator's TIME axis, if it has one — the field
    #: the master timeline scrubs and the process popup plays. ``None`` means
    #: an instantaneous generator, which is most of them.
    #:
    #: The axis MUST be a bounded numeric field: the fold normalises against
    #: its own ``ge``/``le``, so an unbounded one is ignored rather than
    #: guessed at. Modules that already have a ``frame`` field need not
    #: declare anything — see ``Session.time_axis``.
    time_axis: str | None = None
```

- [ ] **Step 4: Generalise the fold**

Replace `axibridge/session.py`'s `_effective_gen_params` (and add two helpers above it):

```python
    @staticmethod
    def time_axis(generator_id: str) -> str | None:
        """Which param of this generator is time, or None.

        The ``frame`` fallback is what makes this a generalisation rather than
        a migration: every image generator predates the declaration and keeps
        working untouched. Declaring is how a NEW axis opts in."""
        try:
            src = get_source(generator_id)
        except KeyError:
            return None
        fields = src.Params.model_fields
        axis = getattr(src, "time_axis", None)
        if axis and axis in fields:
            return axis
        return "frame" if "frame" in fields else None

    @staticmethod
    def axis_bounds(generator_id: str, axis: str) -> tuple[float, float] | None:
        """The axis's own ``ge``/``le``, or None when it is not bounded on both
        sides — in which case there is nothing to map ``master_t`` onto and the
        layer simply does not follow the timeline."""
        return field_bounds(get_source(generator_id).Params.model_fields[axis])

    @staticmethod
    def _effective_gen_params(
        layer: CanvasLayer, master_t: float | None = None
    ) -> dict[str, Any]:
        """The generator params to actually GENERATE with: the layer's stored
        source params, but with the layer's time shift folded into whichever
        param the generator declares as its TIME AXIS. The stored params are
        NEVER mutated — this returns a copy — so the user's raw value and the
        undo/purity contract stay intact.

        The shift is ``frame_offset``, PLUS ``master_t`` when the layer opted
        into ``frame_follow`` and a ``master_t`` is supplied (the single place
        that folds a scrub — the effective params for the preview, estimate and
        plotter alike are computed here).

        The shift is in NORMALISED units (0..1 across the axis's own bounds),
        which is what lets one mechanism serve a 0..1 video ``frame`` and a
        0..2000 step count. The layer fields are still named ``frame_*``
        because they are persisted in every saved project; renaming them would
        buy clarity worth less than a migration."""
        params = dict(layer.source.params or {})
        if layer.source.type not in ("generator", "baked") or not layer.source.generator:
            return params
        shift = layer.frame_offset
        if master_t is not None and layer.frame_follow:
            shift += master_t
        if not shift:
            return params
        gen = layer.source.generator
        axis = Session.time_axis(gen)
        if axis is None:
            return params
        bounds = Session.axis_bounds(gen, axis)
        if bounds is None:
            return params
        lo, hi = bounds
        span = hi - lo
        field = get_source(gen).Params.model_fields[axis]
        current = params.get(axis, field.default)
        norm = (float(current) - lo) / span if span else 0.0
        value = lo + min(1.0, max(0.0, norm + shift)) * span
        # An int axis must be handed an int: Pydantic v2 rejects 4.5 for an int
        # field rather than truncating, so an unrounded fold 422s on a scrub.
        if field.annotation is int:
            value = int(round(value))
        params[axis] = min(hi, max(lo, value))
        return params
```

- [ ] **Step 5: Declare grammar's axis**

In `axibridge/sources/grammar.py`, in the `Grammar` class body under `orientation`:

```python
    #: Rewrite generations ARE this grammar's time — scrubbing the master
    #: timeline grows it. Note it regenerates rather than accumulating: the
    #: composition is scaled from the hull of all emissions, so iteration 4 is
    #: not a superset of iteration 3. Correct for an axis; it is why grammar is
    #: not a ProcessModule.
    time_axis = "iterations"
```

- [ ] **Step 6: Run the new test and the whole suite**

Run: `.venv/bin/python -m pytest -q tests/test_time_axis.py && .venv/bin/python -m pytest -q`
Expected: the new file PASSES, and the full suite still reports 1080 passed / 1 skipped. The unchanged suite *is* the evidence that the frame path is untouched — if any image/sequence/tween test moves, stop and find out why before continuing.

- [ ] **Step 7: Commit**

```bash
git add axibridge/registry.py axibridge/session.py axibridge/sources/grammar.py tests/test_time_axis.py
git commit -m "feat(time): a generator can declare which param is its time axis

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `ProcessModule` — a generator that unfolds

**Files:**
- Create: `axibridge/process.py`
- Test: `tests/test_process.py` (create)

**Interfaces:**
- Consumes: `SourceModule.time_axis` (Task 1).
- Produces: `axibridge.process.Step(paths: list[Path], telemetry: dict[str, float] | None)`; `axibridge.process.ProcessModule` with `run(params) -> Iterator[Step]`, class attrs `time_axis: str` and `accumulative: bool`, an overridable `document(params, paths) -> PathDocument`, and a final `generate(params)`. Task 3 replaces the body of its trajectory lookup; Task 4 subclasses it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_process.py
"""ProcessModule: a generator whose output is the state of a process at step N.

The contract is one sentence — `generate()` is still a pure function of params
— and every test here is a consequence of it."""

import pytest
from pydantic import BaseModel, Field

from axibridge.model import Path
from axibridge.process import ProcessModule, Step


class CountParams(BaseModel):
    steps: int = Field(default=3, ge=0, le=10)
    dx: float = Field(default=1.0, ge=0.0, le=10.0)


class Counter(ProcessModule):
    """Adds one horizontal segment per step, one unit further along."""
    id = "test_counter"
    orientation = "none"
    label = "Counter"
    Params = CountParams

    def run(self, params):
        i = 0
        while True:
            y = i * params.dx
            yield Step(paths=[Path(points=[(0.0, y), (10.0, y)], filled=False)],
                       telemetry={"i": float(i)})
            i += 1


def paths_at(step: int, **kw) -> list[Path]:
    doc = Counter().generate(CountParams(steps=step, **kw))
    return [p for layer in doc.layers for p in layer.paths]


def test_state_at_step_n_is_the_first_n_plus_one_increments():
    assert len(paths_at(0)) == 1
    assert len(paths_at(3)) == 4


def test_a_prefix_equals_a_truncated_full_run():
    """The trajectory's whole correctness claim, asserted before there is a
    cache to get it wrong."""
    full = [tuple(p.points) for p in paths_at(9)]
    for n in range(10):
        assert [tuple(p.points) for p in paths_at(n)] == full[:n + 1]


def test_generate_is_pure_and_repeatable():
    assert [tuple(p.points) for p in paths_at(5)] == [tuple(p.points) for p in paths_at(5)]


def test_an_unbounded_run_is_stopped_by_the_param():
    """`run` here is `while True`. The PARAM decides how long it runs — the
    same reason every numeric field in this repo is bounded, applied to time."""
    assert len(paths_at(10)) == 11


def test_telemetry_is_collected_per_step():
    traj = Counter().trajectory(CountParams(steps=4))
    assert [t["i"] for t in traj.telemetry] == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_a_process_declares_its_time_axis_by_default():
    assert Counter.time_axis == "steps"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest -q tests/test_process.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'axibridge.process'`.

- [ ] **Step 3: Write `axibridge/process.py`**

```python
"""A generator whose output is the state of a process at step N.

Most generators here are instantaneous: params in, drawing out. A growth, a
search, a system holding itself in equilibrium is a process that UNFOLDS, and
the interesting output is often the trajectory rather than the converged
result. This is the base class for those.

THE RULE EVERYTHING RESTS ON: ``generate()`` stays a pure function from params
to geometry, and time is an ordinary bounded param. Everything downstream —
``gencache``'s content-keyed memo, ``tween``'s param lerp, undo, the estimate,
the plotter, the single-resolve invariant — holds only because a generator is a
pure function of its params. A process carrying live mutable state would need a
second geometry path into the plotter, which CLAUDE.md forbids. So the process
is REPLAYED, never HELD.

An author writes ``run()``, which yields one ``Step`` per tick; ``generate()``
is provided. ``run()`` may be an unbounded ``while True`` loop — the base stops
consuming at the time axis's upper bound, so the PARAM decides how long the
process runs. A ``run()`` that ends early simply ends: steps past the last
yield repeat the final state rather than raising, so a process that converges
before its budget still scrubs to the end.

``Step.paths`` is **the marks ADDED at this step** for an accumulative process
(the default), which is what makes the state at step N a prefix slice rather
than a re-run. A process that REVISES earlier marks instead of adding to them
(a curve-shortening flow, a diffusion descent) sets ``accumulative = False``
and yields the complete state each time; see ``trajectory.py`` for what that
costs.

``Step.telemetry`` is not decoration. A homeostat's whole premise is an
essential variable leaving its viable range, and "you cannot tune a homeostat
you cannot watch" means watching that NUMBER, not only the marks it leaves.
The popup plots whatever keys turn up; a process that reports nothing gets no
plot and costs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from pydantic import BaseModel

from .model import Layer, Path, PathDocument
from .registry import SourceModule


@dataclass
class Step:
    """One tick of a process."""

    #: The marks ADDED at this step (accumulative, the default), or the
    #: complete state at this step when ``accumulative`` is False.
    paths: list[Path] = field(default_factory=list)
    #: Anything worth plotting against time — an essential variable, a
    #: population count, an error. Flat and unregistered on purpose: the popup
    #: plots whatever keys turn up.
    telemetry: dict[str, float] | None = None


class ProcessModule(SourceModule):
    """A ``SourceModule`` that unfolds. Registers and behaves like any other."""

    #: Processes are stepped, so the axis is an int step count by convention.
    #: Override if the param has another name; it must exist and be bounded.
    time_axis: str = "steps"

    #: True: each Step ADDS marks, and state N is the concatenation of steps
    #: 0..N. False: each Step is the whole state, which costs far more to
    #: cache — see trajectory.py.
    accumulative: bool = True

    def run(self, params: BaseModel) -> Iterator[Step]:  # pragma: no cover - abstract
        raise NotImplementedError

    def trajectory(self, params: BaseModel) -> "Trajectory":
        """The whole run, up to the axis's upper bound. Task 3 makes this
        cached; the semantics do not change."""
        from .trajectory import build

        return build(self, params)

    def document(self, params: BaseModel, paths: list[Path]) -> PathDocument:
        """Wrap a state in a document. Override to set width/height/name."""
        xs = [x for p in paths for x, _ in p.points] or [0.0]
        ys = [y for p in paths for _, y in p.points] or [0.0]
        return PathDocument(
            layers=[Layer(id=1, name=self.id, color="#26241f", paths=list(paths))],
            width=max(xs) - min(xs),
            height=max(ys) - min(ys),
            source=f"{self.id} @ {getattr(params, self.time_axis)}",
        )

    def generate(self, params: BaseModel) -> PathDocument:
        step = int(getattr(params, self.time_axis))
        return self.document(params, self.trajectory(params).state(step))
```

- [ ] **Step 4: Write the minimal `trajectory.build` this task needs**

`axibridge/trajectory.py`, uncached for now — Task 3 adds the cache, and doing
it in this order means the cache is provably a speed change and not a
behaviour change:

```python
"""The whole run of a process, so a scrub is a slice instead of a re-run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

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


def build(module: "ProcessModule", params: BaseModel) -> Trajectory:
    from .session import Session

    bounds = Session.axis_bounds(module.id, module.time_axis)
    last = int(bounds[1]) if bounds else int(getattr(params, module.time_axis))
    steps: list[list[Path]] = []
    telemetry: list[dict[str, float]] = []
    for i, step in enumerate(module.run(params)):
        steps.append(list(step.paths))
        telemetry.append(dict(step.telemetry or {}))
        if i >= last:
            break
    return Trajectory(steps, telemetry, module.accumulative)
```

- [ ] **Step 5: Run the test**

Run: `.venv/bin/python -m pytest -q tests/test_process.py`
Expected: PASS, 7 tests.

- [ ] **Step 6: Document the new module kind**

Append to `docs/MODULES.md`, after the "Geometry-as-params sources" bullet:

```markdown
- **Process sources** (`axibridge/process.py`): a generator that UNFOLDS.
  Subclass `ProcessModule`, declare a bounded step param as `time_axis`, and
  write `run()` yielding one `Step` per tick — the marks ADDED at that step,
  plus optional `telemetry` for the popup to plot. `generate()` is provided
  and stays pure: it asks the trajectory cache for the state at step N. `run()`
  may be `while True`; the param bounds it. A process that revises earlier
  marks rather than adding sets `accumulative = False` and yields whole states,
  which costs much more to cache. Copy `sources/venation.py`.
```

- [ ] **Step 7: Commit**

```bash
git add axibridge/process.py axibridge/trajectory.py tests/test_process.py docs/MODULES.md
git commit -m "feat(process): ProcessModule — a generator whose output is step N

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The trajectory cache — run once, scrub free

**Files:**
- Modify: `axibridge/trajectory.py` (add the cache around `build`)
- Test: `tests/test_trajectory_cache.py` (create)

**Interfaces:**
- Consumes: `Trajectory`, `build` (Task 2).
- Produces: `trajectory.build` becomes cached (same signature, same results); `trajectory.clear_cache()` and `trajectory.CACHE_BUDGET_POINTS` for tests and for the Pi's budget multiplier.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trajectory_cache.py
"""Running the process once and slicing it is the difference between
'scrubbing is free' and 'scrubbing re-runs the process'. These tests pin that
the cache is a SPEED change only."""

from pydantic import BaseModel, Field

from axibridge import trajectory
from axibridge.model import Path
from axibridge.process import ProcessModule, Step


class P(BaseModel):
    steps: int = Field(default=2, ge=0, le=6)
    seed: int = Field(default=0, ge=0, le=99)


class Counted(ProcessModule):
    id = "test_counted"
    orientation = "none"
    label = "Counted"
    Params = P
    runs = 0

    def run(self, params):
        Counted.runs += 1
        for i in range(7):
            yield Step(paths=[Path(points=[(0.0, float(i)), (1.0, float(i))])])


def test_scrubbing_the_axis_runs_the_process_once():
    trajectory.clear_cache()
    Counted.runs = 0
    mod = Counted()
    for n in range(7):
        mod.generate(P(steps=n))
    assert Counted.runs == 1, "the step param must not be part of the cache key"


def test_a_different_param_is_a_different_trajectory():
    trajectory.clear_cache()
    Counted.runs = 0
    mod = Counted()
    mod.generate(P(steps=3, seed=1))
    mod.generate(P(steps=3, seed=2))
    assert Counted.runs == 2


def test_the_cache_changes_no_output():
    mod = Counted()
    trajectory.clear_cache()
    cold = [tuple(p.points) for layer in mod.generate(P(steps=5)).layers
            for p in layer.paths]
    warm = [tuple(p.points) for layer in mod.generate(P(steps=5)).layers
            for p in layer.paths]
    trajectory.clear_cache()
    again = [tuple(p.points) for layer in mod.generate(P(steps=5)).layers
             for p in layer.paths]
    assert cold == warm == again


def test_the_cache_is_bounded():
    trajectory.clear_cache()
    mod = Counted()
    for seed in range(60):
        mod.generate(P(steps=6, seed=seed))
    assert len(trajectory._CACHE) <= trajectory.CACHE_MAX_ENTRIES
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest -q tests/test_trajectory_cache.py`
Expected: FAIL — `AttributeError: module 'axibridge.trajectory' has no attribute 'clear_cache'`.

- [ ] **Step 3: Add the cache**

In `axibridge/trajectory.py`, rename the existing `build` to `_run` **keeping
its body exactly** (including the `field_bounds` call — do not reintroduce a
session import), then add the constants and the caching `build` below:

```python
import hashlib
import json
import threading
from collections import OrderedDict

from .gencache import cache_budget_multiplier

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


def _key(module: "ProcessModule", params: BaseModel) -> str:
    """Everything about the run EXCEPT where along it we are looking. Dropping
    the time axis from the key is the whole trick: every step of a scrub is
    then the same cache entry."""
    raw = params.model_dump()
    raw.pop(module.time_axis, None)
    blob = json.dumps({"id": module.id, "params": raw}, sort_keys=True, default=str)
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
        budget = CACHE_BUDGET_POINTS * cache_budget_multiplier()
        while _CACHE and (len(_CACHE) > CACHE_MAX_ENTRIES
                          or sum(_points(t) for t in _CACHE.values()) > budget):
            _CACHE.popitem(last=False)
    return traj
```

- [ ] **Step 4: Run both process test files**

Run: `.venv/bin/python -m pytest -q tests/test_trajectory_cache.py tests/test_process.py`
Expected: PASS. Task 2's tests passing unchanged is the evidence that the cache changed no behaviour.

- [ ] **Step 5: Commit**

```bash
git add axibridge/trajectory.py tests/test_trajectory_cache.py
git commit -m "perf(process): cache the whole trajectory, keyed without the time axis

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `venation` — the first real process

**Files:**
- Create: `axibridge/sources/venation.py`
- Test: `tests/test_venation.py` (create)

**Interfaces:**
- Consumes: `ProcessModule`, `Step` (Task 2); the cache (Task 3).
- Produces: a registered source with id `venation`, `time_axis = "steps"`, telemetry keys `"attractors"` and `"tips"`. Task 5's popup test uses it.

Space colonisation (Runions et al.): scatter attractors, grow a tree of nodes toward them, kill each attractor when a node gets close. Branching, continuous, structure-following — and accumulative by construction, which is what makes it the honest proof of the substrate.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_venation.py
"""Venation growth — the first ProcessModule, and the proof the substrate
carries a real generator rather than a fixture."""

import math

from axibridge.registry import get_source, load_builtin_modules

load_builtin_modules()


def run(**kw):
    src = get_source("venation")
    doc = src.generate(src.Params(**kw))
    return [p for layer in doc.layers for p in layer.paths]


def test_it_grows_monotonically():
    """Accumulative by construction: a later step contains every mark of an
    earlier one, in order. This is what makes the trajectory a prefix slice."""
    early = [tuple(p.points) for p in run(steps=20, seed=3)]
    late = [tuple(p.points) for p in run(steps=60, seed=3)]
    assert len(late) > len(early)
    assert late[:len(early)] == early


def test_growth_stays_on_the_bed():
    for p in run(steps=80, seed=1):
        for x, y in p.points:
            assert 0.0 <= x <= 300.0 and 0.0 <= y <= 218.0


def test_every_segment_is_a_real_line():
    for p in run(steps=50, seed=7):
        assert len(p.points) >= 2
        assert math.dist(p.points[0], p.points[-1]) > 0


def test_a_seed_pins_the_whole_run():
    assert ([tuple(p.points) for p in run(steps=40, seed=11)]
            == [tuple(p.points) for p in run(steps=40, seed=11)])
    assert ([tuple(p.points) for p in run(steps=40, seed=11)]
            != [tuple(p.points) for p in run(steps=40, seed=12)])


def test_telemetry_reports_the_hunt():
    src = get_source("venation")
    traj = src.trajectory(src.Params(steps=60, seed=2))
    counts = [t["attractors"] for t in traj.telemetry]
    assert counts[0] >= counts[-1], "attractors are consumed as growth reaches them"
    assert all("tips" in t for t in traj.telemetry)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest -q tests/test_venation.py`
Expected: FAIL — `KeyError: unknown source module: 'venation'`.

- [ ] **Step 3: Write the generator**

```python
"""Venation growth (space colonisation) — branching lines that grow toward
scattered attractors, one step at a time.

Runions et al.'s leaf-venation algorithm, and the first ``ProcessModule`` in
the repo: scatter attractor points, grow a tree from a seed node, and let each
attractor pull the nearest node toward it until something gets close enough to
consume it. Branches appear where attractors disagree — the structure is a
consequence of the point cloud rather than a rule about branching.

It earns its place here twice over: the marks are continuous coherent lines
that follow a structure (not scatter), and each step only ADDS segments, which
is exactly the accumulative case the trajectory cache is built around.
"""

from __future__ import annotations

import math
import random
from typing import Iterator

from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..process import ProcessModule, Step
from ..registry import register_source

BED_WIDTH = 300.0
BED_HEIGHT = 218.0


class VenationParams(BaseModel):
    steps: int = Field(default=120, ge=0, le=600, title="Steps",
                       description="How far the growth has run. This is the time "
                                   "axis — bind it to the master timeline and the "
                                   "growth becomes an animation")
    attractors: int = Field(default=400, ge=10, le=3000, title="Attractors",
                            description="Points the growth reaches toward; more "
                                        "gives denser, finer venation")
    width: float = Field(default=160.0, ge=20.0, le=280.0, title="Width (mm)")
    height: float = Field(default=140.0, ge=20.0, le=200.0, title="Height (mm)")
    step_len: float = Field(default=2.0, ge=0.3, le=10.0, title="Step length (mm)",
                            description="How far a tip advances per step")
    attraction: float = Field(default=30.0, ge=2.0, le=120.0, title="Attraction (mm)",
                              description="How far an attractor can pull a tip")
    kill: float = Field(default=4.0, ge=0.5, le=40.0, title="Kill radius (mm)",
                        description="An attractor is consumed when growth comes "
                                    "this close — small values let branches crowd")
    seed: int = Field(default=0, ge=0, le=99999, title="Seed")


@register_source
class Venation(ProcessModule):
    id = "venation"
    orientation = "geometry"  # a width x height field
    label = "Venation (growth)"
    description = "Branching growth toward scattered attractors, one step at a time."
    Params = VenationParams
    time_axis = "steps"
    accumulative = True

    def run(self, params: VenationParams) -> Iterator[Step]:
        p = params
        rng = random.Random(p.seed)
        w = min(p.width, BED_WIDTH - 4.0)
        h = min(p.height, BED_HEIGHT - 4.0)
        ox, oy = 2.0, 2.0
        attractors = [(ox + rng.uniform(0, w), oy + rng.uniform(0, h))
                      for _ in range(p.attractors)]
        nodes = [(ox + w / 2, oy + h)]      # a single root at the bottom middle
        parents = [-1]

        while True:
            # each attractor votes for its nearest node within reach
            votes: dict[int, list[tuple[float, float]]] = {}
            for a in attractors:
                best, best_d = -1, p.attraction
                for i, n in enumerate(nodes):
                    d = math.dist(a, n)
                    if d < best_d:
                        best, best_d = i, d
                if best >= 0:
                    votes.setdefault(best, []).append(a)

            added: list[Path] = []
            for i, pulls in votes.items():
                nx = sum(a[0] - nodes[i][0] for a in pulls)
                ny = sum(a[1] - nodes[i][1] for a in pulls)
                mag = math.hypot(nx, ny)
                if mag < 1e-9:
                    continue
                tip = (nodes[i][0] + nx / mag * p.step_len,
                       nodes[i][1] + ny / mag * p.step_len)
                tip = (min(BED_WIDTH, max(0.0, tip[0])),
                       min(BED_HEIGHT, max(0.0, tip[1])))
                added.append(Path(points=[nodes[i], tip], filled=False))
                nodes.append(tip)
                parents.append(i)

            # consume the attractors growth has reached
            attractors = [a for a in attractors
                          if all(math.dist(a, n) > p.kill for n in nodes[-len(added):])
                          ] if added else attractors

            yield Step(paths=added,
                       telemetry={"attractors": float(len(attractors)),
                                  "tips": float(len(votes))})
            if not added:
                return   # nothing left in reach: the process has converged

    def document(self, params: VenationParams, paths: list[Path]) -> PathDocument:
        return PathDocument(
            layers=[Layer(id=1, name="venation", color="#26241f", paths=list(paths))],
            width=params.width,
            height=params.height,
            source=f"venation {params.seed} @ {params.steps}",
        )
```

- [ ] **Step 4: Run the test**

Run: `.venv/bin/python -m pytest -q tests/test_venation.py`
Expected: PASS, 5 tests. If `test_it_grows_monotonically` fails, the bug is in
`run` mutating shared state between steps — the trajectory is built once and
sliced, so any per-step mutation of an already-yielded list breaks the prefix
property.

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: green. A new source is automatically pulled into
`tests/test_orientation.py` and `tests/test_app.py`'s module roster — **add
`"venation"` to the sorted source list in `tests/test_app.py` if that test
asserts one**, then re-run.

- [ ] **Step 6: Commit**

```bash
git add axibridge/sources/venation.py tests/test_venation.py tests/test_app.py
git commit -m "feat(sources): venation — branching growth as the first process

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The process popup

**Files:**
- Modify: `axibridge/static/index.html` (popup markup beside the render popup at ~line 318; a Watch button in the layer detail area)
- Create: `axibridge/static/js/process.js`
- Modify: `axibridge/static/js/main.js` (import + init, beside `initShapeMode()` ~line 691)
- Modify: `axibridge/api.py` (`/api/state` module descriptors gain `time_axis`)
- Test: `tests/test_acceptance_ui.py` (append)

**Interfaces:**
- Consumes: `Session.time_axis` (Task 1), the `venation` source (Task 4), the existing `POST /api/generators/preview` (`api.py:329`).
- Produces: `initProcessPopup()` / `openProcessPopup(layerId)` exported from `process.js`; each module descriptor in `/api/state` gains a `time_axis` key (string or null).

The popup adds **no new endpoint**. It drives `/api/generators/preview`, which
already runs a generator with no layer, no undo checkpoint and no session lock
— exactly a scrub's requirements.

- [ ] **Step 1: Ship the axis to the frontend**

In `axibridge/api.py`, `describe_modules()` lives in `registry.py` — add the
key there instead, inside `describe()`:

```python
        if kind == "source":
            d["time_axis"] = getattr(inst, "time_axis", None)
```

- [ ] **Step 2: Write the failing acceptance test**

```python
# append to tests/test_acceptance_ui.py

def test_the_watch_button_appears_only_for_a_process_layer(ui):
    """A time axis is what makes a layer watchable. A polygon has none, and
    offering to play it would describe something that cannot happen."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 25})
    reload_app(ui)
    wait_for_ink(ui)
    select_layer(ui, 0)
    assert not ui.is_visible("#process-watch")

    add_layer(ui, "venation", {"steps": 40, "attractors": 120, "seed": 2})
    reload_app(ui)
    wait_for_ink(ui)
    select_layer(ui, 0)
    ui.wait_for_selector("#process-watch:not([hidden])", timeout=10_000)
    assert ui.is_visible("#process-watch")
    assert not ui.errors


def test_scrubbing_the_popup_changes_the_ink_and_not_the_project(ui):
    """The popup is a viewer of a param. Same discipline as the timeline bar:
    it must never PATCH the project."""
    add_layer(ui, "venation", {"steps": 80, "attractors": 150, "seed": 5})
    reload_app(ui)
    wait_for_ink(ui)
    select_layer(ui, 0)
    before = json.dumps(_get(f"{ui.base}/api/project"))

    ui.click("#process-watch")
    ui.wait_for_selector("#process-popup:not([hidden])", timeout=10_000)
    ui.wait_for_function(
        "() => document.querySelectorAll('#process-canvas path').length > 0",
        timeout=20_000)
    early = ui.eval_on_selector_all(
        "#process-canvas path", "els => els.length")

    ui.eval_on_selector("#process-scrub",
                        "(el) => { el.value = el.max; "
                        "el.dispatchEvent(new Event('input', {bubbles: true})); }")
    ui.wait_for_function(
        "(n) => document.querySelectorAll('#process-canvas path').length > n",
        arg=early, timeout=20_000)

    assert json.dumps(_get(f"{ui.base}/api/project")) == before, \
        "the popup scrubbed the project instead of previewing it"
    assert not ui.errors
```

- [ ] **Step 3: Run it and watch it fail**

Run: `.venv/bin/python -m pytest -q tests/test_acceptance_ui.py -k "watch_button or scrubbing_the_popup"`
Expected: FAIL — `#process-watch` never appears.

- [ ] **Step 4: Add the popup markup**

In `axibridge/static/index.html`, immediately after the render popup block
(search for `<!-- Render popup`), add:

```html
<!-- Process popup: watch a layer whose generator has a TIME AXIS play and
     scrub. Static top-level markup like the render popup, opened from the
     Watch button in the layer detail panel. Preview only — it drives
     /api/generators/preview and never PATCHes the project, the same
     discipline the timeline bar keeps. -->
<div id="process-popup" class="popup" hidden>
  <div class="popup-head">
    <span id="process-title">Process</span>
    <button id="process-close" title="Close">✕</button>
  </div>
  <svg id="process-canvas" viewBox="0 0 300 218" preserveAspectRatio="xMidYMid meet"></svg>
  <svg id="process-telemetry" viewBox="0 0 300 60" preserveAspectRatio="none"></svg>
  <div class="popup-controls">
    <button id="process-play" class="primary">Play</button>
    <button id="process-prev">← Step</button>
    <button id="process-next">Step →</button>
    <input id="process-scrub" type="range" min="0" max="100" step="1" value="0">
    <span id="process-readout">0</span>
  </div>
</div>
```

And in the layer detail area, beside the existing Animate button:

```html
<button id="process-watch" hidden title="Watch this process play and scrub its time axis">Watch</button>
```

- [ ] **Step 5: Write `axibridge/static/js/process.js`**

```javascript
// The process popup: watch a layer whose generator declares a TIME AXIS.
//
// It adds no API. /api/generators/preview already runs a generator with no
// layer, no undo checkpoint and no session lock — which is exactly what a
// scrub needs — and with the trajectory cached server-side each step is a
// prefix slice rather than a re-run.
//
// It never PATCHes the project. Same rule the timeline bar keeps: this is a
// viewer of a param, and committing a step means typing it in the form.

import { api } from "./api.js";
import { S, actions } from "./main.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";

let layerId = null;
let axis = null;
let bounds = [0, 100];
let playing = null;
let wired = false;

function moduleFor(layer) {
  const gen = layer?.source?.type === "generator" ? layer.source.generator : null;
  return (S.state.modules.sources || []).find((m) => m.id === gen) || null;
}

export function watchableAxis(layer) {
  const mod = moduleFor(layer);
  return mod?.time_axis || null;
}

export function initProcessPopup() {
  if (wired) return;
  if (!$("process-popup")) return; // stale cached index.html: degrade silently
  wired = true;
  $("process-close").onclick = close;
  $("process-play").onclick = () => (playing ? stop() : play());
  $("process-prev").onclick = () => nudge(-1);
  $("process-next").onclick = () => nudge(+1);
  $("process-scrub").addEventListener("input", () => render());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("process-popup").hidden) close();
  });
}

export async function openProcessPopup(id) {
  const layer = S.state.project.layers.find((l) => l.id === id);
  axis = watchableAxis(layer);
  if (!axis) return;
  layerId = id;
  const mod = moduleFor(layer);
  const schema = mod.schema.properties[axis] || {};
  bounds = [schema.minimum ?? 0, schema.maximum ?? 100];
  const scrub = $("process-scrub");
  scrub.min = bounds[0];
  scrub.max = bounds[1];
  scrub.step = schema.type === "integer" ? 1 : (bounds[1] - bounds[0]) / 200;
  scrub.value = layer.source.params?.[axis] ?? bounds[0];
  $("process-title").textContent = `${layer.name} — ${axis}`;
  $("process-popup").hidden = false;
  await render();
}

function close() {
  stop();
  $("process-popup").hidden = true;
  layerId = null;
}

function nudge(dir) {
  const scrub = $("process-scrub");
  scrub.value = Number(scrub.value) + dir * Number(scrub.step || 1);
  render();
}

function play() {
  $("process-play").textContent = "Pause";
  const tick = async () => {
    const scrub = $("process-scrub");
    if (Number(scrub.value) >= Number(scrub.max)) { stop(); return; }
    nudge(+1);
    await render();
    if (playing) playing = setTimeout(tick, 40);
  };
  playing = setTimeout(tick, 0);
}

function stop() {
  if (playing) clearTimeout(playing);
  playing = null;
  const btn = $("process-play");
  if (btn) btn.textContent = "Play";
}

let pending = false;
async function render() {
  const layer = S.state.project.layers.find((l) => l.id === layerId);
  if (!layer || pending) return;
  const value = Number($("process-scrub").value);
  $("process-readout").textContent = String(value);
  pending = true;
  try {
    const params = { ...layer.source.params, [axis]: value };
    const out = await api.post("/api/generators/preview",
                               { module: layer.source.generator, params });
    draw(out.lines || []);
  } catch (e) {
    actions.oops(e);
  } finally {
    pending = false;
  }
}

function draw(lines) {
  const svg = $("process-canvas");
  svg.replaceChildren();
  for (const line of lines) {
    if (line.length < 2) continue;
    const el = document.createElementNS(NS, "polyline");
    el.setAttribute("points", line.map(([x, y]) => `${x},${y}`).join(" "));
    el.setAttribute("class", "draw-line");
    svg.appendChild(el);
  }
}
```

- [ ] **Step 6: Wire it into `main.js`**

Add the import beside the other tool imports, and the init beside
`initShapeMode()`:

```javascript
import { initProcessPopup, openProcessPopup, watchableAxis } from "./process.js";
```

```javascript
  initProcessPopup();
```

And where the layer detail panel is rendered (`compose.js`, beside the Animate
button wiring), show the button for a watchable layer:

```javascript
  const watch = document.getElementById("process-watch");
  if (watch) {
    watch.hidden = !watchableAxis(layer);
    watch.onclick = () => openProcessPopup(layer.id);
  }
```

- [ ] **Step 7: Build and run the acceptance tests**

Run: `npm run build && .venv/bin/python -m pytest -q tests/test_acceptance_ui.py -k "watch_button or scrubbing_the_popup"`
Expected: PASS. **If a JS change appears to do nothing, the bundle is stale — re-run `npm run build`.**

- [ ] **Step 8: Commit**

```bash
git add axibridge/static axibridge/registry.py tests/test_acceptance_ui.py
git commit -m "feat(process): a popup that plays and scrubs a layer's time axis

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Rehearse — several moments of one process on one sheet

**Files:**
- Modify: `axibridge/session.py` (add `rehearse_layer`, near `animate_layer` at line 2593)
- Modify: `axibridge/api.py` (a `POST /layers/{layer_id}/rehearse` route beside `/animate` at line 1010)
- Modify: `axibridge/static/js/compose.js` (a Rehearse button beside Animate)
- Test: `tests/test_rehearse.py` (create)

**Interfaces:**
- Consumes: `Session.time_axis`, `Session.axis_bounds` (Task 1); the `venation` source (Task 4); the existing `Session.animate_layer` (`session.py:2593`), `Session.regenerate_layer` (`session.py:641`), `Session.set_tween_params` (`session.py:1035`) and `Session.explode_tween` (`session.py:1168`) — **verified to exist under those exact names**; the first draft of this plan invented `update_tween`, `split_tween` and `layer_geometry`, none of which are real.
- Produces: `Session.rehearse_layer(layer_id: str, moments: int = 4) -> list[CanvasLayer]`, and `POST /api/layers/{layer_id}/rehearse?moments=N`.

This is the roadmap's second argument for A1 and it needs no new machinery:
`animate_layer` already splits a layer into A/B keyframes under a tween, and
`explode_tween` already bakes one layer per sweep step (and keeps the live
tween, hidden, so the rehearsal can be re-tuned and re-exploded). Rehearse sets
A to the start of the axis, B to the end, sweeps N, and explodes — **one session method so
it is one undo step**, not three client calls.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rehearse.py
"""Pentimento: several moments of one process, on one sheet, in one undo step.

Pass 1's §2 has been open since July waiting for a time axis to point the
existing sweep machinery at."""

import pytest

from axibridge.session import session


# The session is a module-level SINGLETON, and every session test in this repo
# uses it directly (see tests/test_tween.py). `AXIBRIDGE_CONFIG_DIR` in
# tests/conftest.py isolates the machine-level stores.


def venation_layer(session):
    return session.add_generated_layer(
        "venation", {"steps": 200, "attractors": 200, "seed": 4})


def test_rehearsing_produces_one_layer_per_moment():
    layer = venation_layer(session)
    out = session.rehearse_layer(layer.id, moments=4)
    assert len(out) == 4


def test_each_moment_contains_the_one_before_it():
    """Accumulative growth, so the rehearsal is a nesting — which is exactly
    what makes pencil-under-ink read as rehearsal rather than as four
    unrelated drawings."""
    layer = venation_layer(session)
    out = session.rehearse_layer(layer.id, moments=4)
    resolved = session.resolved()
    counts = [sum(len(p.points) for lay in resolved.layers if lay.id == l.id
                  for p in lay.paths) for l in out]
    assert counts == sorted(counts)


def test_rehearsing_is_one_undo_step():
    layer = venation_layer(session)
    before = len(session.project.layers)
    session.rehearse_layer(layer.id, moments=5)
    assert len(session.project.layers) > before
    session.undo()
    assert len(session.project.layers) == before


def test_a_layer_with_no_time_axis_cannot_be_rehearsed():
    layer = session.add_generated_layer("polygon", {"sides": 5})
    with pytest.raises(Exception, match="time axis"):
        session.rehearse_layer(layer.id, moments=3)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python -m pytest -q tests/test_rehearse.py`
Expected: FAIL — `AttributeError: 'Session' object has no attribute 'rehearse_layer'`.

**Note for the implementer:** this test uses `session.add_generated_layer`
(`session.py:621`), `session.resolved()` and `session.undo()` (`session.py:382`),
all verified. Every other session name in this task was checked against
`session.py` for the same reason — the first draft of this plan invented three
methods that do not exist, and a plan that names a method into being is worse
than one that says "look it up".

- [ ] **Step 3: Implement `rehearse_layer`**

```python
    def rehearse_layer(self, layer_id: str, moments: int = 4) -> list[CanvasLayer]:
        """Stamp several moments of one process onto the sheet.

        The roadmap's second argument for a time axis, and it needs no new
        machinery: ``animate_layer`` already splits a layer into A/B keyframes
        under a tween, and ``explode_tween`` already bakes one layer per sweep
        step. Rehearse points those at the time axis — A at the start of the
        process, B at the end, ``moments`` stamps between them.

        One checkpoint for the whole thing, so it is one undo step rather than
        three. Assign a pale pen to the early moments and the real one to the
        last and you have rehearsal in pencil under a committed stroke, which
        is what pass 1's §2 asked for.
        """
        with self._lock:
            layer = self.project.layer(layer_id)
            gen = layer.source.generator if layer.source.type == "generator" else None
            axis = self.time_axis(gen) if gen else None
            bounds = self.axis_bounds(gen, axis) if axis else None
            if not axis or not bounds:
                raise RuntimeError(
                    f"{layer.name} has no time axis to rehearse along")
            self._checkpoint()
        tween = self.animate_layer(layer_id)
        a_id = tween.source.params["a"]
        b_id = tween.source.params["b"]
        lo, hi = bounds
        base = dict(layer.source.params or {})
        self.regenerate_layer(a_id, {**base, axis: lo})
        self.regenerate_layer(b_id, {**base, axis: hi})
        self.set_tween_params(tween.id, {"sweep": moments})
        return self.explode_tween(tween.id)
```

**Implementer's note:** `animate_layer`, `regenerate_layer`, `set_tween_params`
and `explode_tween` each take their own `_checkpoint()` today. Passing a coalesce key
(CLAUDE.md's Undo discipline: `self._checkpoint(coalesce=("rehearse", layer_id))`)
is how consecutive checkpoints fold into one undo entry. Verify against
`session.py`'s existing `coalesce` usage and use the same spelling.

- [ ] **Step 4: Add the route**

```python
@router.post("/layers/{layer_id}/rehearse")
def rehearse_layer(layer_id: str, moments: int = Query(default=4, ge=2, le=12)) -> dict[str, Any]:
    """Stamp `moments` moments of a process layer's time axis onto the sheet."""
    try:
        layers = session.rehearse_layer(layer_id, moments)
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)
    return {"layers": [l.model_dump() for l in layers]}
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest -q tests/test_rehearse.py && .venv/bin/python -m pytest -q`
Expected: both green.

- [ ] **Step 6: Add the button**

In `compose.js`, beside the Animate button:

```javascript
  const rehearse = document.getElementById("layer-rehearse");
  if (rehearse) {
    rehearse.hidden = !watchableAxis(layer);
    rehearse.onclick = async () => {
      await api.post(`/api/layers/${layer.id}/rehearse?moments=4`, {});
      await actions.refreshProject();
      await actions.refreshResolved();
    };
  }
```

with the markup beside `#layer-animate`:

```html
<button id="layer-rehearse" hidden title="Stamp several moments of this process onto the sheet — assign a pale pen to the early ones for rehearsal under ink">Rehearse</button>
```

- [ ] **Step 7: Build, run everything, commit**

```bash
npm run build && .venv/bin/python -m pytest -q
git add axibridge/session.py axibridge/api.py axibridge/static tests/test_rehearse.py
git commit -m "feat(process): Rehearse — several moments of one process on one sheet

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Close the round in the docs

**Files:**
- Modify: `ROADMAP.md` (remove A1 from Round 3 — shipped items leave the file)
- Modify: `docs/IDEAS-pass4.md` (mark §A1 shipped, in place, with what the design learned)
- Create: `docs/plans/time-as-a-param-RESULTS.md`
- Modify: `STATUS.md`, `HANDOFF.md`, and `~/_SecondBrain/02_Areas/__claude/CHANGES.md` via the `wrapup` skill

- [ ] **Step 1: Write the RESULTS doc**

Follow `docs/plans/pen-brush-tools-RESULTS.md`'s shape: what shipped, what the
design got wrong, what is still open. Record at minimum: whether the
`frame`-fallback kept every image generator byte-identical, what a full
venation run actually costs at 600 steps, and whether the popup's per-step
round trip is fast enough to play at 25 fps or needs prefetching.

- [ ] **Step 2: Flag the A1.5 decision**

Add to `HANDOFF.md` an entry asking Ian the question this round exists to
answer: **now that there is something to watch, does poking it want to be
direct manipulation or a recorded score?** That is the input A1.5 needs and it
cannot be answered from a desk.

- [ ] **Step 3: Run the wrapup skill and commit**

---

## Self-review notes

**Spec coverage.** Every section of `docs/plans/time-as-a-param.md` maps to a
task: the declared axis and the bounds fold → Task 1; `ProcessModule`, `Step`
and telemetry → Task 2; run-once-index-every-step → Task 3; the popup and its
no-new-API rule → Task 5; pentimento → Task 6; the docs and known gaps → Task 7.

**One deviation from the spec, deliberately.** The spec named `grammar` as the
retrofit proof and listed no new generator. Reading `grammar.generate` showed
it scales the composition from the hull of ALL emissions, so iteration 4 is not
a superset of iteration 3 — it is a fine *time axis* (Task 1) but a bad
*trajectory* client. Task 4 adds `venation` so the substrate ships with a real
user rather than a fixture. Agreed with Ian, 2026-08-21.

**Not in this plan, by the spec's own decision:** interaction (A1.5), A2's
homeostat, A4, A7. Task 7 sets up the question A1.5 needs answered.
