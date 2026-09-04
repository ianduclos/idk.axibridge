"""The homeostat's measurement vocabulary — the occupancy grid and the three
measures read off it. Tested without the module, because A7 (algedonic marks)
is expected to import this file and nothing else."""

import numpy as np

from axibridge.sources._homeostasis import MEASURES, Measures, OccupancyGrid


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


def _dense_reference(segs, w, h, cell=1.0):
    """An INDEPENDENT rasterisation: walk each segment at 1/50th of a cell and
    mark wherever a sample lands. Deliberately shares no code with
    `OccupancyGrid._cells_on` — a reference that called it would only compare
    the algorithm to itself."""
    nx, ny = int(np.ceil(w / cell)), int(np.ceil(h / cell))
    grid = np.zeros((ny, nx), dtype=np.uint8)
    for x0, y0, x1, y1 in segs:
        n = max(2, int(np.hypot(x1 - x0, y1 - y0) / (cell * 0.02)) + 1)
        for t in np.linspace(0.0, 1.0, n):
            xi = min(max(int((x0 + (x1 - x0) * t) / cell), 0), nx - 1)
            yi = min(max(int((y0 + (y1 - y0) * t) / cell), 0), ny - 1)
            grid[yi, xi] = 1
    return grid


def _wander(n=300, seed=4):
    rng = np.random.default_rng(seed)
    segs, x, y = [], 60.0, 40.0
    for _ in range(n):
        nx_ = min(max(x + rng.uniform(-4, 4), 0.0), 120.0)
        ny_ = min(max(y + rng.uniform(-4, 4), 0.0), 80.0)
        segs.append((x, y, nx_, ny_))
        x, y = nx_, ny_
    return segs


def test_the_running_count_never_diverges_from_the_grid():
    """THE invariant. Every measure is a cheap running read instead of a walk
    over accumulated paths, and that is only legitimate if the running state
    matches the grid it claims to summarise."""
    g = OccupancyGrid(120.0, 80.0, cell=1.0)
    for seg in _wander():
        g.mark(*seg)
        assert g.occupied == int(np.count_nonzero(g.cells))


def test_marking_order_does_not_change_the_grid():
    """Occupancy is a set union, so the same segments in any order must give
    the same grid. Catches state that leaks between marks."""
    segs = _wander()
    a = OccupancyGrid(120.0, 80.0)
    for seg in segs:
        a.mark(*seg)
    b = OccupancyGrid(120.0, 80.0)
    for seg in reversed(segs):
        b.mark(*seg)
    assert np.array_equal(a.cells, b.cells)
    assert a.occupied == b.occupied


def test_the_grid_agrees_with_an_independent_rasterisation():
    """What the previous version of this test claimed to do and did not: check
    the rasterisation against something that is not itself.

    `_cells_on` samples at half a cell, which gives an 8-connected chain rather
    than a supercover — it finds ~94% of the cells a dense walk does, missing
    only corner clips, and it never invents one. That shortfall is uniform and
    absorbed by the tuned bands, but it is a real property and it is asserted
    here rather than left to a docstring. The 0.85 floor is set to catch
    genuine under-sampling: sampling at 4x the cell size instead of half
    scores 0.45."""
    segs = _wander()
    g = OccupancyGrid(120.0, 80.0)
    for seg in segs:
        g.mark(*seg)
    ref = _dense_reference(segs, 120.0, 80.0)

    assert int(np.count_nonzero(g.cells & ref)) == g.occupied   # a strict subset
    assert g.occupied / int(np.count_nonzero(ref)) > 0.85


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
