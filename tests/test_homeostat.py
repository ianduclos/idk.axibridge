"""The homeostat — a wandering pen whose handwriting is rerolled blindly when
an essential variable leaves its viable range."""

import numpy as np

from axibridge.registry import get_source, load_builtin_modules
from axibridge.sources._homeostasis import MEASURES
from axibridge.sources.homeostat import (
    BED_HEIGHT, BED_WIDTH, Genome, advance, sample_genome,
)

load_builtin_modules()


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
    sweeps, so it is the one worth a behavioural assertion rather than a range
    check.

    Measured as RELATIVE roughness — the spread of successive turn differences
    against the spread of the turns themselves. Absolute roughness is the wrong
    metric and will mislead anyone who tries it: the turn is an AR(1) process,
    so persistence multiplies its variance by 1/(1-p^2) at the same time as it
    correlates successive values. A persistent hand therefore makes BIGGER
    turns that are individually smoother, and std(diff(turns)) alone goes the
    wrong way. Ratios separate the two effects; measured 1.43 / 1.04 / 0.54 for
    p = 0 / 0.5 / 0.9, stable across seeds."""
    def relative_roughness(persistence, seed=11):
        rng = np.random.default_rng(seed)
        g = Genome(turn_bias=0.0, wander=25.0, persistence=persistence,
                   step_scale=1.0, dwell=1)
        x, y, heading, turn = 60.0, 45.0, 0.0, 0.0
        turns = []
        for i in range(600):
            x, y, heading, turn = advance(x, y, heading, turn, g, 2.0, i,
                                          120.0, 90.0, rng)
            turns.append(turn)
        t = np.array(turns)
        return float(np.std(np.diff(t)) / np.std(t))

    for seed in (11, 3, 42):
        assert (relative_roughness(0.9, seed)
                < relative_roughness(0.5, seed)
                < relative_roughness(0.0, seed))


def test_the_bed_constants_match_the_machine():
    assert (BED_WIDTH, BED_HEIGHT) == (300.0, 218.0)


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
    # 302, not 301: `Trajectory.state(n)` is steps 0..n INCLUSIVE, so 300 steps
    # is 301 segments, and 301 stitched segments share endpoints into 302
    # points. Same prefix contract venation is tested against.
    assert len(paths[0].points) == 302


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
    for name in MEASURES:
        paths = draw(steps=120, seed=6, measure=name)
        assert paths and all(len(p.points) >= 2 for p in paths)


def test_the_defaults_are_mostly_viable_but_do_get_into_trouble():
    """The tuning, as a contract. A homeostat whose defaults sit permanently
    outside their range is not hunting, it is thrashing — and one that never
    leaves range has nothing at stake, which is the whole point of the module.
    The first defaults were the former: target 0.25 against a variable that
    lives around 0.14 gave 37% in range and 71 rerolls. Measured 74-76% in
    range and ~21 rerolls across seeds at 0.12 +- 0.08."""
    import numpy as np

    for seed in (1, 2, 7):
        tel = telemetry(steps=1200, seed=seed)
        strain = np.array([t["strain"] for t in tel])
        in_range = float(np.mean(np.abs(strain) <= 1.0))
        assert 0.55 < in_range < 0.95, (seed, in_range)
        assert tel[-1]["rerolls"] >= 5


def _out_of_range_profile(**kw):
    """(total steps out of range, longest consecutive run, rerolls)."""
    import numpy as np

    tel = telemetry(**kw)
    out = np.abs(np.array([t["strain"] for t in tel])) > 1.0
    longest = cur = 0
    for b in out:
        cur = cur + 1 if b else 0
        longest = max(longest, cur)
    return int(out.sum()), longest, tel[-1]["rerolls"]


def test_patience_counts_consecutive_steps_not_total_ones():
    """The discriminating test for sample-and-hold, and the one the plan
    dropped between the design doc and the implementation.

    A cumulative counter — one that forgets to reset when the variable comes
    back into range — is indistinguishable from a consecutive one in any
    fixture whose range is never reachable, which is what the other two
    controller tests use. So: pick a regime that goes out of range OFTEN but
    never for long, and assert nothing rerolls even though the running total
    passes `patience` many times over. Both implementations are identical up
    to the first reroll, so a cumulative counter provably fires here and this
    test provably fails against it."""
    for seed, tol, patience in ((7, 0.20, 40), (1, 0.15, 45)):
        total, longest, rerolls = _out_of_range_profile(
            steps=1200, seed=seed, tolerance=tol, patience=patience)
        assert rerolls == 0.0, (seed, rerolls)
        assert longest < patience, (seed, longest)
        assert total > patience, (seed, total)   # a cumulative rule would fire


def test_lifting_on_reroll_breaks_the_stroke_into_one_per_hand():
    """`lift_on_reroll` is the aesthetic escape hatch — the seam as two marks
    instead of one change of character — so it needs to actually break the
    stitch, not merely be readable in the form."""
    joined = draw(steps=1200, seed=1, lift_on_reroll=False)
    lifted = draw(steps=1200, seed=1, lift_on_reroll=True)
    assert len(joined) == 1
    assert len(lifted) > 1
    tel = telemetry(steps=1200, seed=1, lift_on_reroll=True)
    assert len(lifted) == int(tel[-1]["rerolls"]) + 1


def test_the_measure_enum_matches_the_measurement_vocabulary():
    """Two lists of measure names that can drift apart is one list too many."""
    from typing import get_args

    from axibridge.sources.homeostat import HomeostatParams

    declared = get_args(HomeostatParams.model_fields["measure"].annotation)
    assert set(declared) == set(MEASURES)


def test_an_unknown_measure_is_refused_at_the_param_boundary():
    """A bad measure should be a 422 from validation, not a 400 from deep
    inside generate()."""
    import pydantic

    src = get_source("homeostat")
    try:
        src.Params(measure="vibes")
    except pydantic.ValidationError:
        return
    raise AssertionError("an unknown measure should not validate")


# --- coupled pens: N units, one shared sheet ---------------------------------


def test_three_pens_draw_three_strokes():
    """Units emit one segment each per step, so the accumulated list
    interleaves them; `document()` de-interleaves by index before stitching or
    the drawing comes back as thousands of two-point fragments."""
    paths = draw(steps=600, seed=3, pens=3)
    assert len(paths) == 3
    # 602 for the same reason the single-pen case gives 302: state(n) is steps
    # 0..n inclusive, and each unit lays exactly one segment per step.
    assert all(len(p.points) == 602 for p in paths)


def test_one_unit_is_exactly_its_slice_of_the_ensemble():
    """`unit` is what makes multi-pen possible without a session change:
    duplicate the layer, set unit 0/1/2, give each a pen. All three must be
    views of ONE simulation, not three separate ones."""
    everything = draw(steps=400, seed=3, pens=3)
    assert len(everything) == 3
    for i in range(3):
        only = draw(steps=400, seed=3, pens=3, unit=i)
        assert len(only) == 1
        assert only[0].points == everything[i].points


def test_the_pens_are_actually_coupled():
    """The test without which 'coupled' is decoration. Unit 0 has the same
    seed, the same starting point and the same first genome whether it draws
    alone or in company — so if its trail is unchanged by two other pens
    inking the sheet it measures, they are three independent drawings sharing
    a frame and nothing more."""
    alone = draw(steps=600, seed=3, pens=1)
    in_company = draw(steps=600, seed=3, pens=3, unit=0)
    assert alone[0].points[:2] == in_company[0].points[:2]   # same start
    assert alone[0].points != in_company[0].points           # different life


def test_an_ensemble_still_accumulates_monotonically():
    early = [pt for p in draw(steps=200, seed=3, pens=3) for pt in p.points]
    late = [pt for p in draw(steps=201, seed=3, pens=3) for pt in p.points]
    assert len(late) == len(early) + 3


def test_a_single_pen_is_unchanged_by_the_ensemble_machinery():
    """`pens=1` must draw exactly what it drew before units existed: unit 0
    starts at the centre and consumes no extra randomness. The other 21 tests
    in this file all run at pens=1 and assert exact counts and strain
    profiles, so they are the real regression guard; this states the intent."""
    paths = draw(steps=300, seed=2)
    assert len(paths) == 1
    assert paths[0].points[0] == (2.0 + 200.0 / 2.0, 2.0 + 160.0 / 2.0)


def test_every_unit_reports_its_own_strain():
    tel = telemetry(steps=200, seed=3, pens=3)
    assert {"variable", "strain", "rerolls", "strain_0", "strain_1", "strain_2"} <= set(tel[-1])
    assert "strain_0" not in telemetry(steps=200, seed=3, pens=1)[-1]


def test_a_full_ensemble_trajectory_is_fast():
    import time

    from axibridge import trajectory as trajectory_module

    trajectory_module.clear_cache()
    src = get_source("homeostat")
    t0 = time.perf_counter()
    src.trajectory(src.Params(steps=10, seed=1, pens=6))
    assert time.perf_counter() - t0 < 20.0
