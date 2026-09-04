"""The homeostat — a wandering pen whose handwriting is rerolled blindly when
an essential variable leaves its viable range."""

import numpy as np

from axibridge.sources.homeostat import (
    BED_HEIGHT, BED_WIDTH, Genome, advance, sample_genome,
)


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
