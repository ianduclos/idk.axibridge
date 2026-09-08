"""Production integration contracts for the Ribbon effect."""

from __future__ import annotations

from axibridge.compose import build_mask
from axibridge.effects.ribbon import Ribbon, RibbonParams
from axibridge.model import Path
from axibridge.registry import EffectContext


def line(length: float, y: float = 0.0) -> Path:
    return Path(points=[(0.0, y), (length, y)])


def apply(paths, **params):
    return Ribbon().apply(paths, RibbonParams(**params), EffectContext(seed=3))


def test_ribbon_is_pure_and_closed_paths_bypass_unchanged():
    open_path = line(90)
    closed = Path(points=[(10, 10), (20, 10), (20, 20), (10, 10)], filled=True)
    before = [path.model_copy(deep=True) for path in (open_path, closed)]

    out = apply([open_path, closed], width=8, steps=3)

    assert [open_path, closed] == before
    assert out[0] is closed
    assert out[0].points == closed.points and out[0].filled
    assert len(out) == 1 + 2 * 3 + 1


def test_ribbon_shared_remove_outer_cutoff_respects_length_trimmed_pairs():
    paths = [line(150), line(75, 30)]
    common = dict(width=8, steps=10, width_by_length=True)

    cutoff_three = apply(paths, remove_outer=3, **common)
    cutoff_six = apply(paths, remove_outer=6, **common)
    untrimmed = apply(paths, **common)

    # Long/short retain 7/5 pairs at cutoff 3, then 4/4 at cutoff 6.
    assert len(cutoff_three) == (2 * 7 + 1) + (2 * 5 + 1)
    assert len(cutoff_six) == (2 * 4 + 1) + (2 * 4 + 1)
    assert cutoff_three[:15] == untrimmed[3:18]
    assert cutoff_three[15:] == untrimmed[21:]
    assert cutoff_six[9:] == untrimmed[22:-1]


def test_ribbon_edges_interpolation_has_no_dedicated_center_strand():
    out = apply([line(100)], width=8, steps=4, interpolation="edges", relation="mirrored")

    assert len(out) == 8
    assert not any(all(y == 0 for _, y in path.points) for path in out)


def test_ribbon_solid_output_builds_a_filled_occlusion_mask():
    out = apply([line(100)], width=10, steps=4, output="solid")

    assert out and all(path.filled and path.is_closed for path in out)
    mask = build_mask(out, line_diameter_mm=.5, margin_mm=0)
    assert mask is not None and mask.area > 1


def test_ribbon_cross_path_masking_changes_with_priority_order():
    paths = [Path(points=[(0, 0), (100, 100)]), Path(points=[(0, 100), (100, 0)])]
    common = dict(width=12, steps=3, mask_overlaps=True)

    later_on_top = apply(paths, **common)
    earlier_on_top = apply(paths, reverse_order=True, **common)

    assert later_on_top and earlier_on_top
    assert [path.points for path in later_on_top] != [path.points for path in earlier_on_top]


def test_ribbon_auto_density_uses_effect_context_pen_width():
    source = [line(120)]
    params = RibbonParams(width=12, steps=1, auto_density=True)
    narrow = Ribbon().apply(source, params, EffectContext(seed=3, line_diameter_mm=.2))
    broad = Ribbon().apply(source, params, EffectContext(seed=3, line_diameter_mm=2.0))

    assert len(narrow) > len(broad) >= 3


def test_short_independent_wavelength_retains_its_crests():
    out = apply([line(10)], wavelength=200, wavelength_right=.5,
                independent_wavelengths=True, relation="mirrored", steps=1,
                height_variation=0, spacing_variation=0, taper=0)
    widths = [-y for _, y in out[-1].points]
    peaks = sum(b > a and b >= c for a,b,c in zip(widths,widths[1:],widths[2:]))
    assert peaks == 20
