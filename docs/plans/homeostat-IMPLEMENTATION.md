# The homeostat — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `ProcessModule` that draws with a single wandering pen and rerolls
that pen's handwriting blindly whenever an essential variable leaves its viable
range.

**Architecture:** Two new files. `sources/_homeostasis.py` is the measurement
vocabulary — one incremental occupancy grid and three measures read off it in
O(1) per step. `sources/homeostat.py` is the module — genome, pen, and the
Ashby loop (advance → measure → judge → reroll → report). No session, compose,
cache or API change; a source registers by dropping a file in `sources/`.

**Tech Stack:** Python 3.11, Pydantic v2 params, numpy (already required),
pytest. Run everything with `.venv/bin/python` — the pinned interpreter.

**Spec:** `docs/plans/homeostat.md` — read it first; this plan argues from it.

## Global Constraints

- **Every numeric param bounded** (`ge`/`le`). CLAUDE.md: unbounded values
  reach an open-loop machine. `tests/test_effect_contract.py::test_every_numeric_param_is_bounded`
  sweeps the source registry and will fail otherwise.
- **`generate()` stays pure** — params in, geometry out, no held state. The
  process is replayed, never held.
- **`orientation` must be set** on the module class or
  `tests/test_orientation.py` fails. This one is `"geometry"` (a width×height
  field), matching venation.
- **Coordinates are millimetres**, machine frame, x ≤ 300, y ≤ 218
  (`BED_WIDTH` / `BED_HEIGHT`, as venation declares them).
- **Effects/geometry are never mutated in place** — paths are replaced
  wholesale.
- Run tests with `.venv/bin/python -m pytest -q`.

## Two corrections to the spec, made while planning

Both are recorded here and should be patched back into `docs/plans/homeostat.md`
in Task 6.

1. **The spec is silent on stroke continuity, and the naive reading breaks the
   central ruling.** `Step.paths` is "marks ADDED this step", so one segment per
   step yields ~1200 two-point paths — which the plotter draws as 1200 separate
   strokes with a pen lift between each. The ruling "the line does not lift at
   a reroll" would be false on paper. Fix: `document()` stitches consecutive
   paths whose endpoints coincide into single polylines. It is pure, O(N), runs
   once per `generate()` on the state being viewed, and leaves the accumulative
   prefix contract untouched (the trajectory still stores per-step increments).
2. **No point cap is needed.** Venation needs `_MAX_NODES` because one step can
   add unboundedly many nodes. Here one step adds exactly one segment, so the
   time axis's upper bound *is* the point bound. Adding a cap would be dead
   code.

## File structure

| File | Responsibility |
|---|---|
| `axibridge/sources/_homeostasis.py` | `OccupancyGrid` + `Measures`. Knows nothing about pens, params or modules. This is the file A7 (algedonic marks) will import. |
| `axibridge/sources/homeostat.py` | `Genome`, `sample_genome`, `advance`, `HomeostatParams`, `Homeostat(ProcessModule)`. The module's own drawing rule. |
| `tests/test_homeostasis.py` | Grid and measure unit tests — no module, no registry. |
| `tests/test_homeostat.py` | Module behaviour through the registry, venation's test file as the model. |

---

### Task 1: The occupancy grid

**Files:**
- Create: `axibridge/sources/_homeostasis.py`
- Test: `tests/test_homeostasis.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `OccupancyGrid(width: float, height: float, cell: float = 1.0)`
  with `.nx: int`, `.ny: int`, `.total: int`, `.occupied: int`,
  `.cells: np.ndarray` (uint8, shape `(ny, nx)`, values 0 or 1),
  `.mark(x0, y0, x1, y1) -> tuple[int, int]` returning
  `(cells_touched, cells_already_occupied)`, and
  `.window_occupancy(x: float, y: float, radius: float) -> float` in 0…1.

- [ ] **Step 1: Write the failing tests**

```python
"""The homeostat's measurement vocabulary — the occupancy grid and the three
measures read off it. Tested without the module, because A7 is expected to
import this file and nothing else."""

import numpy as np

from axibridge.sources._homeostasis import OccupancyGrid


def test_a_fresh_grid_is_empty():
    g = OccupancyGrid(100.0, 50.0, cell=1.0)
    assert (g.nx, g.ny) == (100, 50)
    assert g.total == 5000
    assert g.occupied == 0
    assert g.window_occupancy(50.0, 25.0, 5.0) == 0.0


def test_marking_a_segment_occupies_the_cells_it_crosses():
    g = OccupancyGrid(100.0, 50.0, cell=1.0)
    touched, revisits = g.mark(10.0, 10.0, 20.0, 10.0)
    assert touched >= 10          # ~11 cells along a 10mm horizontal run
    assert revisits == 0
    assert g.occupied == touched


def test_remarking_the_same_segment_is_all_revisits():
    g = OccupancyGrid(100.0, 50.0, cell=1.0)
    touched, _ = g.mark(10.0, 10.0, 20.0, 10.0)
    touched_again, revisits = g.mark(10.0, 10.0, 20.0, 10.0)
    assert (touched_again, revisits) == (touched, touched)
    assert g.occupied == touched   # the count did NOT double


def test_the_incremental_count_equals_a_from_scratch_rasterisation():
    """THE invariant. Every measure is a cheap running read off this grid
    instead of a walk over accumulated paths, and that is only legitimate if
    the running state matches what a from-scratch pass would produce. If this
    ever fails, all three measures are quietly wrong."""
    rng = np.random.default_rng(4)
    g = OccupancyGrid(120.0, 80.0, cell=1.0)
    segs = []
    x, y = 60.0, 40.0
    for _ in range(300):
        nx_, ny_ = x + rng.uniform(-4, 4), y + rng.uniform(-4, 4)
        nx_, ny_ = min(max(nx_, 0.0), 120.0), min(max(ny_, 0.0), 80.0)
        segs.append((x, y, nx_, ny_))
        g.mark(x, y, nx_, ny_)
        x, y = nx_, ny_

    fresh = OccupancyGrid(120.0, 80.0, cell=1.0)
    for s in segs:
        fresh.mark(*s)
    assert np.array_equal(g.cells, fresh.cells)
    assert g.occupied == int(np.count_nonzero(g.cells))


def test_a_point_outside_the_sheet_is_clamped_not_crashed():
    g = OccupancyGrid(50.0, 50.0, cell=1.0)
    g.mark(-10.0, -10.0, 60.0, 60.0)
    assert g.occupied > 0


def test_window_occupancy_is_a_fraction():
    g = OccupancyGrid(100.0, 100.0, cell=1.0)
    for i in range(40):
        g.mark(30.0 + i * 0.5, 50.0, 30.5 + i * 0.5, 50.0)
    v = g.window_occupancy(40.0, 50.0, 5.0)
    assert 0.0 < v < 1.0
    assert g.window_occupancy(90.0, 90.0, 5.0) == 0.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_homeostasis.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'axibridge.sources._homeostasis'`

- [ ] **Step 3: Write the implementation**

```python
"""The homeostat's measurement vocabulary: what "the drawing so far" is worth
measuring about, and how to read it without walking the drawing.

THE COST THAT SHAPES THIS FILE. A homeostat measures the drawing so far at
every step. Doing that by walking the accumulated paths is quadratic in the
step count — and because ``trajectory()`` always runs a process to its time
axis's declared UPPER bound (that is what lets one cached run serve every
scrub position), the whole quadratic cost lands on the first ``generate()``,
not when someone drags the scrub to the end. ``sources/venation.py`` was bitten
by the same shape of mistake; its docstring is the account.

So the drawing is rasterised once, incrementally, into an occupancy grid as it
is drawn, and every measure is an O(1) read off that grid. The invariant this
rests on — that the incrementally built grid equals a from-scratch
rasterisation of the same segments — is asserted in
``tests/test_homeostasis.py``.
"""

from __future__ import annotations

import math

import numpy as np


class OccupancyGrid:
    """Which millimetre cells of the sheet have ink on them.

    Boolean, not a visit count: every measure here is a fraction of cells, so
    counts would only invite an unnormalised number into a design where
    ``target``/``tolerance`` mean the same thing across all three measures.
    """

    def __init__(self, width: float, height: float, cell: float = 1.0) -> None:
        self.cell = cell
        self.width = width
        self.height = height
        self.nx = max(1, int(math.ceil(width / cell)))
        self.ny = max(1, int(math.ceil(height / cell)))
        self.cells = np.zeros((self.ny, self.nx), dtype=np.uint8)
        self.total = self.nx * self.ny
        self.occupied = 0

    def _cells_on(self, x0: float, y0: float, x1: float, y1: float):
        """Row/column indices the segment passes through, deduplicated.

        Sampled at half-cell intervals rather than run through a Bresenham
        supercover: a pen step is a couple of mm over 1 mm cells, so the
        sampling is dense enough to leave no gaps, and it stays vectorised.
        """
        length = math.dist((x0, y0), (x1, y1))
        n = max(2, int(math.ceil(length / (self.cell * 0.5))) + 1)
        ts = np.linspace(0.0, 1.0, n)
        xs = np.clip(((x0 + (x1 - x0) * ts) / self.cell).astype(np.int64), 0, self.nx - 1)
        ys = np.clip(((y0 + (y1 - y0) * ts) / self.cell).astype(np.int64), 0, self.ny - 1)
        flat = np.unique(ys * self.nx + xs)
        return flat // self.nx, flat % self.nx

    def mark(self, x0: float, y0: float, x1: float, y1: float) -> tuple[int, int]:
        """Lay one segment. Returns ``(cells_touched, cells_already_occupied)``
        — the second number is what ``tangle`` is built from."""
        ry, rx = self._cells_on(x0, y0, x1, y1)
        before = self.cells[ry, rx]
        revisits = int(np.count_nonzero(before))
        self.cells[ry, rx] = 1
        self.occupied += int(before.size) - revisits
        return int(before.size), revisits

    def window_occupancy(self, x: float, y: float, radius: float) -> float:
        """Fraction of occupied cells in a square window around a point."""
        r = max(1, int(round(radius / self.cell)))
        cx = min(max(int(x / self.cell), 0), self.nx - 1)
        cy = min(max(int(y / self.cell), 0), self.ny - 1)
        sub = self.cells[max(0, cy - r):cy + r + 1, max(0, cx - r):cx + r + 1]
        return float(sub.mean()) if sub.size else 0.0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_homeostasis.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add axibridge/sources/_homeostasis.py tests/test_homeostasis.py
git commit -m "feat(homeostat): an incremental occupancy grid to measure the drawing so far"
```

---

### Task 2: The three measures

**Files:**
- Modify: `axibridge/sources/_homeostasis.py` (append)
- Test: `tests/test_homeostasis.py` (append)

**Interfaces:**
- Consumes: `OccupancyGrid` from Task 1.
- Produces: `MEASURES: tuple[str, ...] = ("crowding", "coverage", "tangle")`
  and `class Measures(width, height, cell=1.0, window=6.0, tangle_window=40)`
  with `.grid: OccupancyGrid`, `.add(x0, y0, x1, y1) -> None`, and
  `.read(measure: str, x: float, y: float) -> float` returning 0…1.

- [ ] **Step 1: Write the failing tests**

```python
from axibridge.sources._homeostasis import MEASURES, Measures


def test_every_measure_is_normalised():
    """target/tolerance mean the same thing across measures only because all
    three land in 0..1. This is the property that lets the measure be a knob."""
    m = Measures(120.0, 80.0)
    x, y = 10.0, 40.0
    for i in range(200):
        m.add(x, y, x + 0.5, y)
        x += 0.5
        if x > 110.0:
            x, y = 10.0, y + 1.0
    for name in MEASURES:
        v = m.read(name, x, y)
        assert 0.0 <= v <= 1.0, (name, v)


def test_crowding_is_local():
    """The point of the default measure: it reports where the pen IS, not what
    the sheet looks like overall."""
    m = Measures(200.0, 200.0)
    for i in range(120):
        m.add(20.0 + i * 0.5, 20.0, 20.5 + i * 0.5, 20.0)
    busy = m.read("crowding", 40.0, 20.0)
    empty = m.read("crowding", 180.0, 180.0)
    assert busy > empty
    assert empty == 0.0


def test_coverage_is_global_and_rises_monotonically():
    m = Measures(100.0, 100.0)
    seen = 0.0
    x = 5.0
    for _ in range(150):
        m.add(x, 50.0, x + 0.5, 50.0)
        x += 0.5
        now = m.read("coverage", x, 50.0)
        assert now >= seen
        seen = now
    assert seen > 0.0


def test_tangle_separates_fresh_ground_from_retraced_ground():
    m = Measures(100.0, 100.0)
    for i in range(60):
        m.add(10.0 + i, 50.0, 11.0 + i, 50.0)
    fresh = m.read("tangle", 70.0, 50.0)
    for i in range(60):
        m.add(10.0 + i, 50.0, 11.0 + i, 50.0)
    retraced = m.read("tangle", 70.0, 50.0)
    assert retraced > fresh
    assert retraced <= 1.0


def test_an_unknown_measure_is_refused():
    m = Measures(50.0, 50.0)
    try:
        m.read("vibes", 10.0, 10.0)
    except ValueError:
        return
    raise AssertionError("an unknown measure should raise")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_homeostasis.py -q`
Expected: FAIL — `ImportError: cannot import name 'MEASURES'`

- [ ] **Step 3: Write the implementation**

```python
#: The essential variables a homeostat can be built around. The idea doc calls
#: the choice "the biggest lever by far", which is why it is a knob — and why
#: it is three, not eight.
MEASURES: tuple[str, ...] = ("crowding", "coverage", "tangle")


class Measures:
    """One grid, three readings, all in 0..1 and all O(1) per step.

    ``tangle`` is explicitly a PROXY for crossing density: it is the rate at
    which the pen enters cells that already have ink, over a trailing window of
    segments. Counting real segment intersections is the quadratic trap this
    whole file exists to avoid, and calling the proxy a crossing count would be
    a lie a later reader would build on.
    """

    def __init__(self, width: float, height: float, cell: float = 1.0,
                 window: float = 6.0, tangle_window: int = 40) -> None:
        self.grid = OccupancyGrid(width, height, cell)
        self.window = window
        self._tangle_window = tangle_window
        self._recent: list[float] = []

    def add(self, x0: float, y0: float, x1: float, y1: float) -> None:
        touched, revisits = self.grid.mark(x0, y0, x1, y1)
        self._recent.append(revisits / touched if touched else 0.0)
        if len(self._recent) > self._tangle_window:
            del self._recent[0]

    def read(self, measure: str, x: float, y: float) -> float:
        if measure == "crowding":
            return self.grid.window_occupancy(x, y, self.window)
        if measure == "coverage":
            return self.grid.occupied / self.grid.total if self.grid.total else 0.0
        if measure == "tangle":
            return sum(self._recent) / len(self._recent) if self._recent else 0.0
        raise ValueError(f"unknown measure: {measure!r}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_homeostasis.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add axibridge/sources/_homeostasis.py tests/test_homeostasis.py
git commit -m "feat(homeostat): crowding, coverage and tangle off one grid"
```

---

### Task 3: The genome and the pen

**Files:**
- Create: `axibridge/sources/homeostat.py`
- Test: `tests/test_homeostat.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2 (this task is independent of them).
- Produces: `BED_WIDTH = 300.0`, `BED_HEIGHT = 218.0`;
  `@dataclass(frozen=True) class Genome` with fields
  `turn_bias: float`, `wander: float`, `persistence: float`,
  `step_scale: float`, `dwell: int`;
  `sample_genome(rng: np.random.Generator, variety: float, centre: Genome | None = None) -> Genome`;
  `advance(x, y, heading, prev_turn, g: Genome, step_len: float, i: int, w: float, h: float, rng) -> tuple[float, float, float, float]`
  returning `(nx, ny, heading, turn)`.

- [ ] **Step 1: Write the failing tests**

```python
"""The homeostat — a wandering pen whose handwriting is rerolled blindly when
an essential variable leaves its viable range."""

import numpy as np

from axibridge.sources.homeostat import (
    BED_HEIGHT, BED_WIDTH, Genome, advance, sample_genome,
)


def test_a_genome_is_reproducible_from_its_seed():
    a = sample_genome(np.random.default_rng(7), 1.0)
    b = sample_genome(np.random.default_rng(7), 1.0)
    assert a == b
    c = sample_genome(np.random.default_rng(8), 1.0)
    assert a != c


def test_zero_variety_always_rerolls_to_the_same_hand():
    """`variety` is the one knob over the genome, and 0 must mean "reroll to
    nearly the same hand" — otherwise a crisis with variety=0 is still a
    lurch and the knob does not say what it claims."""
    a = sample_genome(np.random.default_rng(1), 0.0)
    b = sample_genome(np.random.default_rng(999), 0.0)
    assert a == b


def test_memory_centres_a_reroll_on_a_genome_that_held():
    held = Genome(turn_bias=9.0, wander=1.0, persistence=0.9,
                  step_scale=1.9, dwell=1)
    near = sample_genome(np.random.default_rng(3), 0.1, centre=held)
    far = sample_genome(np.random.default_rng(3), 0.1)
    assert abs(near.turn_bias - held.turn_bias) < abs(far.turn_bias - held.turn_bias)


def test_the_pen_cannot_leave_the_sheet():
    rng = np.random.default_rng(5)
    g = Genome(turn_bias=0.0, wander=40.0, persistence=0.0,
               step_scale=2.0, dwell=1)
    x, y, heading, turn = 10.0, 10.0, 0.0, 0.0
    for i in range(4000):
        x, y, heading, turn = advance(x, y, heading, turn, g, 3.0, i,
                                      120.0, 90.0, rng)
        assert 0.0 <= x <= 120.0 and 0.0 <= y <= 90.0


def test_persistence_makes_a_smoother_line():
    """Persistence is the gene that decides whether the hand scribbles or
    sweeps, so it is the one worth a behavioural assertion rather than a
    range check."""
    def total_turning(persistence):
        rng = np.random.default_rng(11)
        g = Genome(turn_bias=0.0, wander=25.0, persistence=persistence,
                   step_scale=1.0, dwell=1)
        x, y, heading, turn = 60.0, 45.0, 0.0, 0.0
        turns = []
        for i in range(600):
            x, y, heading, turn = advance(x, y, heading, turn, g, 2.0, i,
                                          120.0, 90.0, rng)
            turns.append(abs(turn))
        return float(np.std(np.diff(turns)))

    assert total_turning(0.9) < total_turning(0.0)


def test_the_bed_constants_match_the_machine():
    assert (BED_WIDTH, BED_HEIGHT) == (300.0, 218.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_homeostat.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'axibridge.sources.homeostat'`

- [ ] **Step 3: Write the implementation**

```python
"""The homeostat — a wandering pen that rerolls its own handwriting when the
drawing gets into trouble.

Ashby's homeostat held an essential variable inside a viable range and, pushed
outside it, RANDOMLY REWIRED ITSELF until it found a configuration that worked.
Blindly: it rerolls, it does not reason. That blindness is the point. The
reconfiguration is not a search for a better drawing, so the seam it leaves
lands exactly where the system was in trouble — which is Oehlen's regime
collision with a reason the sheet can show.

Design notes, including the two alternatives rejected (a bank of named regimes;
a coupled population of agents, which is what Ashby's machine actually was):
``docs/plans/homeostat.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Iterator

import numpy as np
from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..process import ProcessModule, Step
from ..registry import register_source
from ._homeostasis import MEASURES, Measures

BED_WIDTH = 300.0
BED_HEIGHT = 218.0


@dataclass(frozen=True)
class Genome:
    """One hand. A flat vector of bounded numbers on purpose: a coupled
    population is N of these plus a coupling matrix, and a regime bank is this
    with a discrete gene — both alternatives stay one refactor away."""

    turn_bias: float     # degrees per step, signed — a drift that spirals
    wander: float        # degrees, the random component
    persistence: float   # 0..1, how much of the previous turn carries over
    step_scale: float    # multiplier on the base step length
    dwell: int           # steps between fresh random turns


#: (low, high) for each gene. `variety` samples a band of this width around the
#: middle, so variety=0 is the centre hand and variety=1 is the whole range.
GENE_RANGES: dict[str, tuple[float, float]] = {
    "turn_bias": (-12.0, 12.0),
    "wander": (0.0, 45.0),
    "persistence": (0.0, 0.95),
    "step_scale": (0.4, 2.0),
    "dwell": (1.0, 8.0),
}


def sample_genome(rng: np.random.Generator, variety: float,
                  centre: Genome | None = None) -> Genome:
    """A fresh hand. ``centre`` is the memory path: with it, the band is drawn
    around a genome that previously held instead of around the range middle."""
    genes: dict[str, float] = {}
    for name, (lo, hi) in GENE_RANGES.items():
        mid = getattr(centre, name) if centre is not None else (lo + hi) / 2.0
        half = (hi - lo) / 2.0 * variety
        genes[name] = float(np.clip(rng.uniform(mid - half, mid + half), lo, hi))
    genes["dwell"] = int(round(genes["dwell"]))
    return Genome(**genes)  # type: ignore[arg-type]


def advance(x: float, y: float, heading: float, prev_turn: float,
            g: Genome, step_len: float, i: int, w: float, h: float,
            rng: np.random.Generator) -> tuple[float, float, float, float]:
    """One pen step. Returns ``(x, y, heading, turn)``.

    Edges REFLECT rather than clamp: a clamped pen slides along the wall and
    piles up ink there, which the crowding measure would read as a crisis
    caused by the boundary rather than by the drawing.
    """
    wander = float(rng.normal(0.0, g.wander)) if i % max(1, g.dwell) == 0 else 0.0
    turn = g.persistence * prev_turn + g.turn_bias + wander
    heading = heading + math.radians(turn)

    step = step_len * g.step_scale
    nx = x + math.cos(heading) * step
    ny = y + math.sin(heading) * step
    if nx < 0.0 or nx > w:
        heading = math.pi - heading
        nx = min(max(nx, 0.0), w)
    if ny < 0.0 or ny > h:
        heading = -heading
        ny = min(max(ny, 0.0), h)
    return nx, ny, heading, turn
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_homeostat.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add axibridge/sources/homeostat.py tests/test_homeostat.py
git commit -m "feat(homeostat): the genome and the pen that writes with it"
```

---

### Task 4: The module — params, the Ashby loop, and the stitch

**Files:**
- Modify: `axibridge/sources/homeostat.py` (append)
- Test: `tests/test_homeostat.py` (append)

**Interfaces:**
- Consumes: `Genome`, `sample_genome`, `advance` (Task 3); `MEASURES`,
  `Measures` (Task 2).
- Produces: `HomeostatParams(BaseModel)` and
  `Homeostat(ProcessModule)` registered as source id `"homeostat"`, with
  `time_axis = "steps"`, `accumulative = True`, and telemetry keys
  `"variable"`, `"strain"`, `"rerolls"`.

- [ ] **Step 1: Write the failing tests**

```python
from axibridge.registry import get_source, load_builtin_modules

load_builtin_modules()


def draw(**kw):
    src = get_source("homeostat")
    doc = src.generate(src.Params(**kw))
    return [p for layer in doc.layers for p in layer.paths]


def telemetry(**kw):
    src = get_source("homeostat")
    return src.trajectory(src.Params(**kw)).telemetry


def test_it_is_registered_and_oriented():
    src = get_source("homeostat")
    assert src.time_axis == "steps"
    assert src.accumulative is True
    assert src.orientation == "geometry"


def test_it_accumulates_monotonically():
    """The prefix contract: a later step contains every mark of an earlier one.
    Compared as flattened points because `document()` stitches contiguous
    segments, so path COUNTS need not grow even though the drawing does."""
    early = [pt for p in draw(steps=40, seed=3) for pt in p.points]
    late = [pt for p in draw(steps=90, seed=3) for pt in p.points]
    assert len(late) > len(early)
    assert late[:len(early)] == early


def test_the_line_is_stitched_not_shattered():
    """One segment per step would be one two-point PATH per step — 300 pen
    lifts on paper, which would make the no-lift ruling false where it counts.
    `document()` stitches contiguous segments into runs."""
    paths = draw(steps=300, seed=2, lift_on_reroll=False)
    assert len(paths) == 1
    assert len(paths[0].points) == 301


def test_a_seed_pins_the_whole_run():
    from axibridge import trajectory as trajectory_module

    trajectory_module.clear_cache()
    first = [tuple(p.points) for p in draw(steps=80, seed=11)]
    trajectory_module.clear_cache()
    second = [tuple(p.points) for p in draw(steps=80, seed=11)]
    assert first == second

    trajectory_module.clear_cache()
    third = [tuple(p.points) for p in draw(steps=80, seed=12)]
    assert first != third


def test_a_wide_range_never_puts_the_system_in_trouble():
    """tolerance=1.0 makes every value viable, so a reroll would mean the
    controller fires on something other than the variable leaving range."""
    tel = telemetry(steps=400, seed=5, tolerance=1.0, target=0.5)
    assert tel[-1]["rerolls"] == 0.0


def test_a_narrow_range_forces_rerolls():
    tel = telemetry(steps=400, seed=5, measure="coverage",
                    target=1.0, tolerance=0.01, patience=1)
    assert tel[-1]["rerolls"] > 0.0


def test_patience_delays_the_reroll():
    """Sample-and-hold, not a hair trigger: the same impossible range with a
    long patience must reroll strictly less often than with a short one."""
    impatient = telemetry(steps=400, seed=5, measure="coverage",
                          target=1.0, tolerance=0.01, patience=1)
    patient = telemetry(steps=400, seed=5, measure="coverage",
                        target=1.0, tolerance=0.01, patience=50)
    assert patient[-1]["rerolls"] < impatient[-1]["rerolls"]


def test_strain_is_zero_when_the_variable_sits_on_target():
    tel = telemetry(steps=120, seed=4, measure="coverage",
                    target=0.0, tolerance=0.5)
    assert abs(tel[5]["strain"]) < 1.0


def test_the_drawing_stays_on_the_bed():
    for p in draw(steps=500, seed=9, width=280.0, height=200.0):
        for x, y in p.points:
            assert 0.0 <= x <= BED_WIDTH and 0.0 <= y <= BED_HEIGHT


def test_a_full_trajectory_is_fast():
    """The performance guard, venation's precedent. `trajectory()` always runs
    to the axis's DECLARED upper bound regardless of the `steps` passed in, so
    a measure that walked the accumulated paths each step would put its whole
    quadratic cost on this call. Generous enough not to flake on a loaded
    machine or the Pi, tight enough to catch a regression to a path walk."""
    import time

    from axibridge import trajectory as trajectory_module

    trajectory_module.clear_cache()
    src = get_source("homeostat")
    t0 = time.perf_counter()
    src.trajectory(src.Params(steps=10, seed=1))
    assert time.perf_counter() - t0 < 10.0


def test_every_measure_runs_end_to_end():
    from axibridge.sources._homeostasis import MEASURES

    for name in MEASURES:
        paths = draw(steps=120, seed=6, measure=name)
        assert paths and all(len(p.points) >= 2 for p in paths)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_homeostat.py -q`
Expected: FAIL — `KeyError: 'homeostat'` from `get_source`

- [ ] **Step 3: Write the implementation**

```python
class HomeostatParams(BaseModel):
    steps: int = Field(default=300, ge=0, le=1200, title="Steps",
                       description="How far the pen has walked. This is the time "
                                   "axis — bind it to the master timeline and the "
                                   "hunt becomes an animation")
    width: float = Field(default=200.0, ge=20.0, le=290.0, title="Width (mm)")
    height: float = Field(default=160.0, ge=20.0, le=210.0, title="Height (mm)")
    step_len: float = Field(default=2.0, ge=0.3, le=8.0, title="Step length (mm)",
                            description="Base pen advance per step; the hand scales it")
    measure: str = Field(default="crowding", title="Essential variable",
                         json_schema_extra={"enum": list(MEASURES)},
                         description="What the system is trying not to lose. "
                                     "Crowding is local (am I in a corner?), "
                                     "coverage is global, tangle is how much "
                                     "ground it is retracing")
    target: float = Field(default=0.25, ge=0.0, le=1.0, title="Target",
                          description="Where the variable wants to sit")
    tolerance: float = Field(default=0.12, ge=0.01, le=1.0, title="Tolerance",
                             description="Half-width of the viable range. Narrow "
                                         "gives constant crisis and visible "
                                         "thrash; wide gives long stable passages "
                                         "punctuated by lurches")
    patience: int = Field(default=8, ge=1, le=60, title="Patience (steps)",
                          description="Consecutive steps out of range before the "
                                      "hand is rerolled")
    variety: float = Field(default=0.8, ge=0.0, le=1.0, title="Variety",
                           description="How wide a reroll samples. 0 rerolls to "
                                       "nearly the same hand")
    memory: float = Field(default=0.0, ge=0.0, le=1.0, title="Memory",
                          description="Bias a reroll toward hands that held "
                                      "before. Ashby had none, and adding it "
                                      "makes the system converge — which is "
                                      "another word for finished")
    lift_on_reroll: bool = Field(default=False, title="Lift on reroll",
                                 description="Off: the hand changes mid-stroke "
                                             "and the seam is a change of "
                                             "character. On: the pen lifts and "
                                             "the seam is two marks")
    seed: int = Field(default=0, ge=0, le=99999, title="Seed")


def _stitch(paths: list[Path]) -> list[Path]:
    """Join consecutive paths that share an endpoint into single polylines.

    The trajectory stores per-step increments — that is what makes state at
    step N a prefix slice — so an unstitched state is one two-point path per
    step, which the plotter would draw as one pen lift per step. Stitching
    here, at document time, keeps the increments intact and gives the plotter
    the continuous line the module's whole premise rests on.
    """
    out: list[Path] = []
    for p in paths:
        if out and out[-1].points[-1] == p.points[0]:
            out[-1] = Path(points=out[-1].points + list(p.points[1:]), filled=False)
        else:
            out.append(Path(points=list(p.points), filled=False))
    return out


@register_source
class Homeostat(ProcessModule):
    id = "homeostat"
    orientation = "geometry"  # a width x height field
    label = "Homeostat (hunting)"
    description = ("A pen that rerolls its own handwriting, blindly, whenever "
                   "the drawing leaves its viable range.")
    Params = HomeostatParams
    time_axis = "steps"
    accumulative = True

    def run(self, params: HomeostatParams) -> Iterator[Step]:
        p = params
        rng = np.random.default_rng(p.seed)
        w = min(p.width, BED_WIDTH - 4.0)
        h = min(p.height, BED_HEIGHT - 4.0)
        ox, oy = 2.0, 2.0

        field = Measures(w, h)
        hand = sample_genome(rng, p.variety)
        held: list[Genome] = []

        x, y = w / 2.0, h / 2.0
        heading, turn = 0.0, 0.0
        out_of_range = 0
        in_range_run = 0
        rerolls = 0.0
        i = 0

        while True:
            nx, ny, heading, turn = advance(x, y, heading, turn, hand,
                                            p.step_len, i, w, h, rng)
            field.add(x, y, nx, ny)
            seg = Path(points=[(ox + x, oy + y), (ox + nx, oy + ny)], filled=False)
            x, y = nx, ny
            i += 1

            v = field.read(p.measure, x, y)
            strain = (v - p.target) / p.tolerance

            if abs(strain) > 1.0:
                out_of_range += 1
                if in_range_run > p.patience:
                    # This hand kept the system viable for a while; remember it
                    # only if memory is on.
                    held.append(hand)
                in_range_run = 0
            else:
                out_of_range = 0
                in_range_run += 1

            if out_of_range >= p.patience:
                centre = None
                if p.memory > 0.0 and held and rng.random() < p.memory:
                    centre = held[int(rng.integers(len(held)))]
                hand = sample_genome(rng, p.variety, centre=centre)
                out_of_range = 0
                rerolls += 1.0
                if p.lift_on_reroll:
                    # Break the stitch: a segment starting somewhere else is a
                    # new stroke, and _stitch only joins shared endpoints.
                    x, y = float(rng.uniform(0.0, w)), float(rng.uniform(0.0, h))

            yield Step(paths=[seg],
                       telemetry={"variable": v, "strain": strain,
                                  "rerolls": rerolls})

    def document(self, params: HomeostatParams, paths: list[Path]) -> PathDocument:
        return PathDocument(
            layers=[Layer(id=1, name="homeostat", color="#26241f",
                          paths=_stitch(paths))],
            width=params.width,
            height=params.height,
            source=f"homeostat {params.seed} @ {params.steps}",
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_homeostat.py tests/test_homeostasis.py -q`
Expected: all passed

- [ ] **Step 5: Run the whole suite — this task registers a new source, and
      three contract tests sweep the registry**

Run: `.venv/bin/python -m pytest -q`
Expected: no failures. If `test_every_numeric_param_is_bounded`,
`test_orientation.py` or a roster contract fails, fix the module — those tests
are the contract, not an obstacle.

- [ ] **Step 6: Commit**

```bash
git add axibridge/sources/homeostat.py tests/test_homeostat.py
git commit -m "feat(sources): homeostat — a hand rerolled blindly when the drawing leaves its range"
```

---

### Task 5: Eyes on it — the bench, and a plotted sheet

**Files:**
- Modify: none expected. This task is verification, and any change it forces
  is a bug fix in `homeostat.py`.

**Interfaces:**
- Consumes: the registered module from Task 4.
- Produces: an opinion, and the tuning defaults that come out of it.

This is the task the whole round exists for, and it cannot be done by an agent.
CLAUDE.md: a verification report on anything user-visible is provisional until
Ian has run it himself.

- [ ] **Step 1: Start the server**

```bash
.venv/bin/python -m axibridge
```

If a change appears to do nothing, check for a stale server first —
`lsof -nP -iTCP:2942 -sTCP:LISTEN`, then `ps -p <pid> -o command` — and check
whether a stale `static_dist/` is shadowing the source frontend.

- [ ] **Step 2: Open the bench**

Generate panel → **Homeostat (hunting)** → **▷ Bench**. Play it. The telemetry
plot is the point: `strain` crossing ±1 is the system in trouble, and `rerolls`
stepping up is it rewiring.

- [ ] **Step 3: The tuning questions, in order**

- Does a reroll **read** on the sheet? If the hand changes and the line looks
  the same, `variety` is too low or the gene ranges are too narrow.
- Drag **tolerance** from 0.02 to 0.5. Narrow should thrash visibly, wide
  should give long stable passages. If it doesn't, the measure is not moving
  and `measure`/`target` are mismatched.
- Switch **measure** through all three. Crowding should look like a pen that
  keeps escaping itself; coverage like eras; tangle like it avoids its own
  tracks.
- Turn **memory** to 1.0 and watch it converge and die. That is the intended
  behaviour, not a bug.

- [ ] **Step 4: Plot one**

▶ Plot, on the real AxiDraw. This is the first sheet from pass 4 — neither
venation nor the cymatic fill has touched paper either.

- [ ] **Step 5: Commit any defaults that changed**

```bash
git add axibridge/sources/homeostat.py
git commit -m "fix(homeostat): defaults from the bench"
```

---

### Task 6: The docs trail

**Files:**
- Modify: `docs/plans/homeostat.md` (the two corrections above)
- Modify: `docs/IDEAS-pass4.md` (§A2 → SHIPPED)
- Modify: `ROADMAP.md` (Round 3, item 6)
- Modify: `~/_SecondBrain/02_Areas/__claude/CHANGES.md` (cross-project feed)
- Create: `docs/plans/homeostat-RESULTS.md` if the build taught anything the
  design got wrong, as A1's did.

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code reads.

- [ ] **Step 1: Patch the spec with the two corrections**

Add the stitch decision to `docs/plans/homeostat.md`'s measurement section, and
strike the point-cap paragraph — one segment per step means the axis bound is
the point bound.

- [ ] **Step 2: Mark A2 shipped in the ideas doc**

Follow the format §A1 and §B2 already use: `### A2. Homeostat generator —
SHIPPED <date>`, the files, and what the sketch got wrong.

- [ ] **Step 3: Strike Round 3 item 6 in ROADMAP.md**

Leave A4 (the seam) in place — it is the other Round 3 item and is untouched.

- [ ] **Step 4: Write the CHANGES.md entry**

A new source id is a boundary others read. Affects: anyone enumerating source
ids (`homeostat` is new); idkpi (no new dependency — numpy and scipy are
already required). No API change.

- [ ] **Step 5: Commit**

```bash
git add docs/ ROADMAP.md
git commit -m "docs(homeostat): close the round — ledger, roadmap, spec corrections"
```

- [ ] **Step 6: Wrap up**

Run the `wrapup` skill: `STATUS.md` frontmatter and `HANDOFF.md`. STATUS is
currently stale (it says A1 is unmerged; A1 merged 2026-08-29) — fix that in
the same pass.

## Self-review

**Spec coverage.** The drawer (Task 3), the no-lift ruling (Tasks 3–4, tested
by `test_the_line_is_stitched_not_shattered`), the loop and telemetry (Task 4),
the three measures and the O(1) grid (Tasks 1–2), memory off by default
(Task 4, param default 0.0), all eleven params (Task 4), every test in the
spec's list (Tasks 1–4), the docs trail (Task 6). The spec's point cap is
struck with reasons, and the stitch it omitted is added.

**Type consistency.** `Measures.read(measure, x, y)` is called with exactly
that signature in Task 4. `advance(...) -> (x, y, heading, turn)` is unpacked
four-wide at both call sites. `sample_genome(rng, variety, centre=None)` —
`centre` is keyword in both uses. `MEASURES` is imported from
`_homeostasis` in both the module and its tests.

**Known soft spot.** `test_persistence_makes_a_smoother_line` and
`test_tangle_separates_fresh_ground_from_retraced_ground` are behavioural
rather than analytic, so a legitimate retune could move them. They assert a
direction, not a value, which is the weakest assertion that still catches the
bug they exist for.
