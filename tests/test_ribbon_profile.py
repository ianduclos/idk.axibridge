from __future__ import annotations

import math

import pytest

from axibridge.effects._ribbon_profile import make_profiles


SAMPLE_FRACTIONS = (0.0, 0.07, 0.23, 0.5, 0.81, 1.0)


def _samples(profile, total):
    return [profile(total * fraction) for fraction in SAMPLE_FRACTIONS]


def test_phrased_profile_matches_javascript_reference():
    params = {
        "rhythm": "phrased", "wavelength": 90, "spacing_variation": 0.7,
        "height_variation": 0.7, "phrasing": 0.65, "relation": "related",
    }
    left, right = make_profiles(620, params, 17)

    assert [k["s"] for k in left.knots[:4]] == pytest.approx(
        [0, 16.422301132879674, 45.650729335202676, 88.68104322742236]
    )
    assert [k["v"] for k in left.knots[:4]] == pytest.approx(
        [0, 0.2571399425525988, 0.029334895306945066, 0.8676189569859526]
    )
    assert _samples(left, 620) == pytest.approx(
        [0, 0.03902380707634468, 0.13639736093876614,
         0.5464403809105979, 0.22256994411834521, 0], abs=2e-15
    )
    assert [k["s"] for k in right.knots[:4]] == pytest.approx(
        [0, 16.572655782575225, 45.15449187642593, 84.7530523773328]
    )
    assert _samples(right, 620)[1:-1] == pytest.approx(
        [0.04281867300957067, 0.07643281971726046,
         0.5524501445476598, 0.19546522113107342], abs=5e-15
    )


def test_legacy_profile_matches_javascript_reference():
    left, _ = make_profiles(
        240, {"rhythm": "legacy", "wavelength": 90, "variation": 0.7,
              "relation": "related"}, 31
    )
    assert [k["s"] for k in left.knots] == pytest.approx([
        0, 47.71303382789483, 85.60847875534091, 128.1771161778015,
        178.09854952903697, 220.27022651745938, 240,
    ])
    assert _samples(left, 240) == pytest.approx([
        0, 0.26352093682514716, 0.8522308195431835,
        0.7212577904604758, 0.4519961568433565, 0,
    ], abs=2e-15)


def test_independent_wavelength_right_matches_javascript_reference():
    params = {
        "rhythm": "phrased", "wavelength": 55, "wavelength_right": 83,
        "independent_wavelengths": True, "spacing_variation": 1,
        "height_variation": 0.2, "phrasing": 0.9, "relation": "independent",
    }
    _, right = make_profiles(175, params, 0xFFFFFFFF)
    assert [k["s"] for k in right.knots] == pytest.approx(
        [0, 10.545382023869859, 21.261485028327627, 122.5565319970314, 175]
    )
    assert _samples(right, 175) == pytest.approx([
        0, 0.7229617928256823, 0.2471115713171506,
        0.630443629628297, 0.5547629294374266, 0,
    ], abs=2e-15)


@pytest.mark.parametrize("relation", ["mirrored", "related", "independent"])
def test_profiles_are_finite_bounded_positive_and_keep_zero_endpoints(relation):
    params = {
        "rhythm": "phrased", "wavelength": 70, "variation": 1,
        "relation": relation, "smoothing_variation": 1,
    }
    for profile in make_profiles(350, params, -23):
        values = [profile(station * 0.25) for station in range(1401)]
        assert values[0] == 0
        assert values[-1] == 0
        assert all(math.isfinite(value) and 0 <= value <= 1 for value in values)
        assert any(value > 0 for value in values[1:-1])
        assert profile.knots[0] == {"s": 0.0, "v": 0.0}
        assert profile.knots[-1] == {"s": 350.0, "v": 0.0}


def test_zero_softening_bypasses_averaging():
    profile, _ = make_profiles(
        410, {"rhythm": "phrased", "crest_softening": 0, "relation": "mirrored"}, 8
    )
    assert profile.smoothing_radius == 0
    assert [profile(knot["s"]) for knot in profile.knots] == pytest.approx(
        [knot["v"] for knot in profile.knots]
    )


def test_uneven_softening_is_deterministic_smooth_and_does_not_move_knots():
    base = {
        "rhythm": "phrased", "wavelength": 90, "spacing_variation": 0.9,
        "height_variation": 0.8, "phrasing": 0.7, "relation": "mirrored",
    }
    regular, _ = make_profiles(620, base, 43)
    varied_a, _ = make_profiles(620, {**base, "smoothing_variation": 1}, 43)
    varied_b, _ = make_profiles(620, {**base, "smoothing_variation": 1}, 43)

    assert varied_a.knots == regular.knots == varied_b.knots
    assert varied_a.smoothing_scales == varied_b.smoothing_scales
    assert len(varied_a.smoothing_scales) == len(varied_a.knots) - 1
    assert all(0.85 <= scale <= 1.15 for scale in varied_a.smoothing_scales)
    assert _samples(varied_a, 620) == _samples(varied_b, 620)
    assert _samples(varied_a, 620) != _samples(regular, 620)
    for knot in varied_a.knots[1:-1]:
        step = 1e-3
        left_slope = (varied_a(knot["s"]) - varied_a(knot["s"] - step)) / step
        right_slope = (varied_a(knot["s"] + step) - varied_a(knot["s"])) / step
        assert left_slope == pytest.approx(right_slope, abs=2e-5)


def test_every_crest_has_distinct_seeded_approach_and_departure_softening():
    params = {
        "rhythm": "phrased", "wavelength": 65, "relation": "mirrored",
        "smoothing_variation": 1,
    }
    profile, _ = make_profiles(620, params, 91)
    repeat, _ = make_profiles(620, params, 91)

    # Phrased knots alternate endpoint, crest, trough, crest, ...; interval
    # targets therefore address the two flanks of each odd-indexed crest.
    flank_pairs = [
        (profile.smoothing_scales[index - 1], profile.smoothing_scales[index])
        for index in range(1, len(profile.knots) - 1, 2)
    ]
    assert flank_pairs
    assert all(approach != departure for approach, departure in flank_pairs)
    assert profile.smoothing_scales == repeat.smoothing_scales


def test_near_zero_smoothing_variation_converges_to_accepted_baseline():
    params = {"rhythm": "phrased", "wavelength": 90, "relation": "related"}
    baseline, _ = make_profiles(620, params, 17)
    near_zero, _ = make_profiles(620, {**params, "smoothing_variation": 1e-9}, 17)
    stations = [620 * index / 200 for index in range(201)]
    assert max(abs(baseline(s) - near_zero(s)) for s in stations) < 1e-9


def test_height_and_spacing_random_streams_are_independent():
    base = {"rhythm": "phrased", "wavelength": 90, "phrasing": 0.7}
    low_height, _ = make_profiles(620, {**base, "height_variation": 0.1}, 31)
    high_height, _ = make_profiles(620, {**base, "height_variation": 0.9}, 31)
    assert [k["s"] for k in low_height.knots] == [k["s"] for k in high_height.knots]
    assert [k["v"] for k in low_height.knots] != [k["v"] for k in high_height.knots]

    low_spacing, _ = make_profiles(620, {**base, "spacing_variation": 0.1}, 31)
    high_spacing, _ = make_profiles(620, {**base, "spacing_variation": 0.9}, 31)
    assert [k["v"] for k in low_spacing.knots] == [k["v"] for k in high_spacing.knots]
    assert [k["s"] for k in low_spacing.knots] != [k["s"] for k in high_spacing.knots]
