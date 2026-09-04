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
is drawn, and every measure is an O(1) read off that grid. Two invariants hold
that up, both asserted in ``tests/test_homeostasis.py`` and both the first
thing to check if a measure ever looks wrong, because nothing else here fails
loudly: the running ``occupied`` count never diverges from the grid it
summarises, and the grid agrees with an independent dense rasterisation.

Kept free of pens, params and modules on purpose. A7 (algedonic marks) wants
this vocabulary and nothing else in ``homeostat.py``.
"""

from __future__ import annotations

import math

import numpy as np


class OccupancyGrid:
    """Which millimetre cells of the sheet have ink on them.

    Boolean, not a visit count: every measure here is a fraction of cells, so
    counts would only invite an unnormalised number into a design where
    ``target``/``tolerance`` are meant to mean the same thing across all three
    measures.
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
        supercover, which makes this an 8-CONNECTED CHAIN and not a supercover:
        it finds ~94% of the cells a dense walk finds, missing only cells the
        segment merely clips at a corner, and it never invents one. The
        shortfall is uniform, so it shifts every measure by the same small
        factor and the tuned bands absorb it; it is asserted rather than
        assumed (``test_the_grid_agrees_with_an_independent_rasterisation``).
        Densifying is cheap if a use ever needs true supercover fidelity, but
        it would move every band.
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
