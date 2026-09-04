"""The homeostat's measurement vocabulary — the occupancy grid and the three
measures read off it. Tested without the module, because A7 (algedonic marks)
is expected to import this file and nothing else."""

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
