"""Eigenfunction fill — the membrane solver and the effect that draws it.

The solver is checked against things that are TRUE OF THE PHYSICS rather than
against a golden file, because a golden file for this would only ever say
"still does whatever it did":

* a rectangle's membrane spectrum is known in closed form;
* Courant's nodal domain theorem bounds how many pieces the n-th mode may cut
  the drum into, and a subtly wrong discretisation breaks it;
* a square's degenerate pairs must come out EQUAL, which is exactly what
  caught the boundary-row bug in ``rasterise``.
"""

import math

import numpy as np
import pytest
from scipy import ndimage
from shapely.geometry import Point, Polygon

from axibridge.effects import _eigenmode as E

SQUARE = Polygon([(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)])


def analytic(a: float, b: float, n: int) -> list[float]:
    """The first n eigenvalues of a clamped a x b membrane."""
    return sorted(math.pi ** 2 * (m * m / a ** 2 + k * k / b ** 2)
                  for m in range(1, 9) for k in range(1, 9))[:n]


def nodal_domains(basis: E.Basis, mode: int, mix: float = 0.0) -> int:
    """Connected components of constant sign — the sand-free patches. Specks
    of a few cells are discretisation dust on a staircased boundary, not
    domains."""
    field = E.mode_field(basis, mode, mix)
    total = 0
    for sign in (1.0, -1.0):
        labels, count = ndimage.label((field * sign > 0) & basis.mask)
        if count:
            sizes = ndimage.sum(np.ones_like(labels), labels, range(1, count + 1))
            total += int((sizes > 3).sum())
    return total


def test_rectangle_spectrum_matches_analytic():
    basis = E.basis(Polygon([(0, 0), (60, 0), (60, 35), (0, 35)]), 0.7, 8)
    for got, want in zip(basis.values[:8], analytic(60.0, 35.0, 8)):
        assert abs(got - want) / want < 0.01


def test_square_degenerate_pairs_are_equal_and_grouped():
    basis = E.basis(SQUARE, 0.8, 8)
    # (1,2) and (2,1) share a frequency; so do (1,3)/(3,1) and (2,3)/(3,2)
    assert basis.groups[1] == (1, 3)
    assert basis.groups[3] == (4, 6)
    for lo, hi in basis.groups:
        for i in range(lo + 1, hi):
            assert abs(basis.values[i] - basis.values[lo]) / basis.values[lo] < 1e-6


def test_courant_bound_holds():
    basis = E.basis(SQUARE, 0.6, 12)
    for mode in range(1, 13):
        assert nodal_domains(basis, mode) <= mode


def test_first_mode_is_a_single_domain():
    """The fundamental never crosses zero inside: no interior nodal line, so
    the fill draws nothing but the outline. That is correct, not a bug."""
    assert nodal_domains(E.basis(SQUARE, 0.6, 4), 1) == 1


def test_mix_reaches_the_two_figures_of_one_frequency():
    basis = E.basis(SQUARE, 0.6, 8)
    plus = E.mode_field(basis, 2, 1.0)
    minus = E.mode_field(basis, 2, -1.0)
    # u1+u2 and u1-u2 are genuinely different pictures at the same frequency
    assert not np.allclose(plus, minus)
    assert nodal_domains(basis, 2, 1.0) == 2


def test_mix_partner_is_the_degenerate_neighbour():
    basis = E.basis(SQUARE, 0.8, 8)
    assert E.mix_group(basis, 2) == (1, 2)      # inside the degenerate pair
    assert E.mix_group(basis, 1) == (0, 1)      # alone: chords with the next


def test_holes_are_outside_the_membrane():
    ring = Polygon([(0, 0), (40, 0), (40, 40), (0, 40)],
                   [[(15, 15), (25, 15), (25, 25), (15, 25)]])
    basis = E.basis(ring, 0.5, 4)
    xs, ys = E.node_coords(basis.mask, basis.pitch, basis.origin)
    inside_hole = (xs > 15.5) & (xs < 24.5) & (ys > 15.5) & (ys < 24.5)
    assert not inside_hole.any()


def test_density_localises_the_low_modes():
    heavy = lambda xs, ys: np.where(xs < 20.0, 8.0, 1.0)  # noqa: E731
    basis = E.basis(SQUARE, 0.8, 6, density=heavy)
    xs, _ = E.node_coords(basis.mask, basis.pitch, basis.origin)
    u = E.mode_field(basis, 1, 0.0)[basis.mask]
    assert (u[xs < 20.0] ** 2).sum() > 2.0 * (u[xs >= 20.0] ** 2).sum()
    # heavier means slower means a lower fundamental
    assert basis.values[0] < E.basis(SQUARE, 0.8, 6).values[0]


def test_pitch_coarsens_instead_of_exploding():
    bed = Polygon([(0, 0), (280, 0), (280, 200), (0, 200)])
    mask, pitch, _ = E.rasterise(bed, 0.2)
    assert mask.sum() <= E.MAX_NODES
    assert pitch > 0.2


def test_solve_is_deterministic_across_a_cold_cache():
    first = E.basis(SQUARE, 0.8, 6).vectors.copy()
    E.clear_cache()
    second = E.basis(SQUARE, 0.8, 6).vectors
    assert np.array_equal(first, second)
