"""Grammar source: contract (determinism, bounds) + transgression semantics."""

import math

import pytest

from axibridge.registry import get_source


def _gen(**params):
    src = get_source("grammar")
    return src.generate(src.Params(**params))


@pytest.mark.parametrize("grammar", ["branching", "band", "radial"])
def test_generates_all_grammars(grammar):
    doc = _gen(grammar=grammar, iterations=4)
    paths = doc.layers[0].paths
    assert paths
    assert all(len(p.points) >= 2 for p in paths)


def test_deterministic():
    a = _gen(grammar="branching", budget=4, seed=7)
    b = _gen(grammar="branching", budget=4, seed=7)
    assert [p.points for p in a.layers[0].paths] == [p.points for p in b.layers[0].paths]


def test_budget_zero_is_formal_and_seed_free():
    # with no transgressions the grammar is pure rule application: the seed
    # must not matter
    a = _gen(grammar="radial", budget=0, seed=1)
    b = _gen(grammar="radial", budget=0, seed=99)
    assert [p.points for p in a.layers[0].paths] == [p.points for p in b.layers[0].paths]


def test_budget_spends_violations():
    clean = _gen(grammar="radial", budget=0, seed=3)
    haunted = _gen(grammar="radial", budget=3, violation=0.3, seed=3)
    c = [p.points for p in clean.layers[0].paths]
    h = [p.points for p in haunted.layers[0].paths]
    assert len(c) == len(h)  # violations perturb motifs, never add or remove
    differing = sum(1 for x, y in zip(c, h) if x != y)
    assert 1 <= differing <= 3 * 2  # ≤ budget × subpaths-per-motif


def test_seed_moves_the_violations():
    a = _gen(grammar="band", budget=3, violation=0.5, seed=1)
    b = _gen(grammar="band", budget=3, violation=0.5, seed=2)
    assert [p.points for p in a.layers[0].paths] != [p.points for p in b.layers[0].paths]


def test_coordinates_nonnegative_and_sized():
    doc = _gen(grammar="branching", iterations=5, size=100)
    xs = [x for p in doc.layers[0].paths for x, _ in p.points]
    ys = [y for p in doc.layers[0].paths for _, y in p.points]
    assert min(xs) >= 0 and min(ys) >= 0
    longest = max(max(xs) - min(xs), max(ys) - min(ys))
    # control-hull sizing: the drawn curve is within the hull, never over it
    assert 70 < longest <= 100.5


def test_petals_flatten_closed():
    doc = _gen(grammar="radial", iterations=3, budget=0)
    closed = [p for p in doc.layers[0].paths if p.points[0] == p.points[-1]]
    assert closed, "radial petals should survive flattening as closed paths"


def test_flatten_tol_controls_point_count():
    fine = _gen(grammar="radial", iterations=3, budget=0, flatten_tol=0.05)
    coarse = _gen(grammar="radial", iterations=3, budget=0, flatten_tol=1.0)
    n_fine = sum(len(p.points) for p in fine.layers[0].paths)
    n_coarse = sum(len(p.points) for p in coarse.layers[0].paths)
    assert n_fine > n_coarse


def test_emission_cap_holds():
    doc = _gen(grammar="branching", iterations=8, flatten_tol=1.0)
    assert len(doc.layers[0].paths) < 2000
