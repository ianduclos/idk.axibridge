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
