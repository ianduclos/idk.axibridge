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
from axibridge.model import Path
from axibridge.registry import EffectContext, effects, load_builtin_modules

load_builtin_modules()

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
    """ARPACK starts from a random vector unless told otherwise, and the basis
    of a degenerate group is settled lazily — both have to come out the same
    on a cold cache or the effect contract's determinism clause is a lie."""
    def solved():
        E.clear_cache()
        basis = E.basis(SQUARE, 0.8, 6)
        E.mode_field(basis, 2, 0.25)   # forces the degenerate group to settle
        return basis.vectors.copy()

    assert np.array_equal(solved(), solved())


# -- the effect ----------------------------------------------------------------

def _square_path(size: float = 40.0) -> Path:
    return Path(points=[(0.0, 0.0), (size, 0.0), (size, size), (0.0, size), (0.0, 0.0)],
                filled=True)


def run(paths, **params) -> list[Path]:
    eff = effects()["eigen_fill"]
    return eff.apply(paths, eff.Params(**params), EffectContext(layer_id="t", seed=7))


def fills(out: list[Path]) -> list[Path]:
    return [p for p in out if not p.filled]


def test_open_and_unfilled_paths_pass_through_untouched():
    wiggle = Path(points=[(5.0, 5.0), (20.0, 9.0), (35.0, 5.0)], filled=False)
    out = run([wiggle], mode=4)
    assert out == [wiggle]


def test_fill_lines_are_open_and_inside_the_shape():
    out = run([_square_path()], mode=9, inset=1.0)
    lines = fills(out)
    assert lines
    for path in lines:
        assert not path.filled
        for x, y in path.points:
            assert 0.9 <= x <= 39.1 and 0.9 <= y <= 39.1


def test_outline_is_kept_or_dropped_on_request():
    assert any(p.filled for p in run([_square_path()], mode=6))
    assert not any(p.filled for p in run([_square_path()], mode=6, outline=False))


def test_first_mode_draws_no_fill_lines():
    """The fundamental has no interior nodal line at all. An empty fill is the
    correct answer, not a failure — worth pinning so nobody 'fixes' it."""
    assert fills(run([_square_path()], mode=1)) == []


def test_higher_modes_draw_more_line():
    def ink(mode: int) -> float:
        return sum(math.dist(a, b) for p in fills(run([_square_path()], mode=mode))
                   for a, b in zip(p.points, p.points[1:]))

    assert ink(20) > ink(9) > ink(3) > 0


def test_a_hole_is_a_real_boundary():
    ring = [_square_path(),
            Path(points=[(15.0, 15.0), (25.0, 15.0), (25.0, 25.0), (15.0, 25.0), (15.0, 15.0)],
                 filled=True)]
    for path in fills(run(ring, mode=12, inset=0.5)):
        for x, y in path.points:
            assert not (15.6 < x < 24.4 and 15.6 < y < 24.4)


def test_min_length_drops_fragments():
    # a high mode is where the short pieces are: a nodal line clipped near a
    # corner leaves a sliver that costs a whole pen lift to draw
    long_only = fills(run([_square_path()], mode=60, min_length=15.0))
    everything = fills(run([_square_path()], mode=60, min_length=0.0))
    assert len(long_only) < len(everything)
    assert all(sum(math.dist(a, b) for a, b in zip(p.points, p.points[1:])) >= 15.0
               for p in long_only)


def test_mix_changes_the_figure_within_one_frequency():
    a = fills(run([_square_path()], mode=2, mix=-1.0))
    b = fills(run([_square_path()], mode=2, mix=1.0))
    assert [p.points for p in a] != [p.points for p in b]


def test_missing_asset_falls_back_to_a_uniform_membrane():
    """A stored project whose assets have gone walkabout must still resolve."""
    plain = fills(run([_square_path()], mode=8))
    gone = fills(run([_square_path()], mode=8, image="nope.png", density=1.0))
    assert [p.points for p in gone] == [p.points for p in plain]


def test_density_bunches_the_lines_where_the_image_is_dark():
    from PIL import Image

    import io

    from axibridge.assets import asset_store

    img = Image.new("L", (64, 64), 255)
    img.paste(0, (0, 0, 32, 64))          # left half black = heavy = slow
    buf = io.BytesIO()
    img.save(buf, "PNG")
    before = asset_store.all()
    asset_store.put("half.png", buf.getvalue())
    try:
        out = fills(run([_square_path()], mode=10, image="half.png", density=1.0))
        left = right = 0.0
        for path in out:
            for a, b in zip(path.points, path.points[1:]):
                length = math.dist(a, b)
                if (a[0] + b[0]) / 2 < 20.0:
                    left += length
                else:
                    right += length
        assert left > 1.5 * right
    finally:
        asset_store.replace_all(before)
