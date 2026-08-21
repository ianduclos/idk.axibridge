"""Venation growth — the first ProcessModule, and the proof the substrate
carries a real generator rather than a fixture."""

import math
import time

from axibridge.registry import get_source, load_builtin_modules

load_builtin_modules()


def run(**kw):
    src = get_source("venation")
    doc = src.generate(src.Params(**kw))
    return [p for layer in doc.layers for p in layer.paths]


def test_it_grows_monotonically():
    """Accumulative by construction: a later step contains every mark of an
    earlier one, in order. This is what makes the trajectory a prefix slice."""
    early = [tuple(p.points) for p in run(steps=20, seed=3)]
    late = [tuple(p.points) for p in run(steps=60, seed=3)]
    assert len(late) > len(early)
    assert late[:len(early)] == early


def test_growth_stays_on_the_bed():
    for p in run(steps=80, seed=1):
        for x, y in p.points:
            assert 0.0 <= x <= 300.0 and 0.0 <= y <= 218.0


def test_every_segment_is_a_real_line():
    for p in run(steps=50, seed=7):
        assert len(p.points) >= 2
        assert math.dist(p.points[0], p.points[-1]) > 0


def test_a_seed_pins_the_whole_run():
    assert ([tuple(p.points) for p in run(steps=40, seed=11)]
            == [tuple(p.points) for p in run(steps=40, seed=11)])
    assert ([tuple(p.points) for p in run(steps=40, seed=11)]
            != [tuple(p.points) for p in run(steps=40, seed=12)])


def test_telemetry_reports_the_hunt():
    src = get_source("venation")
    traj = src.trajectory(src.Params(steps=60, seed=2))
    counts = [t["attractors"] for t in traj.telemetry]
    assert counts[0] >= counts[-1], "attractors are consumed as growth reaches them"
    assert all("tips" in t for t in traj.telemetry)


def test_coordinates_are_plain_python_floats():
    """Everything downstream (Pydantic, JSON, the SVG writer) expects plain
    floats, not numpy scalars — a real risk once the hot loop is numpy."""
    for p in run(steps=30, seed=5):
        for x, y in p.points:
            assert type(x) is float and type(y) is float


def test_a_full_trajectory_is_fast():
    """The performance guard. The plan's un-vectorised nearest-node search
    (a Python double loop over every attractor x every node, every step) costs
    ~918M distance computations at this module's declared bounds — about 3
    minutes for one trajectory. Because `trajectory()` always runs a process
    to its time axis's declared upper bound regardless of the `steps` value
    passed in (that's what lets a single cached run serve every scrub
    position), that cost would land on the very first `generate()` call. This
    asserts the vectorised version stays well clear of that: a generous 20s
    budget — loose enough not to flake on a loaded machine or the Raspberry
    Pi, tight enough to catch a regression back to the double loop."""
    from axibridge import trajectory as trajectory_module

    trajectory_module.clear_cache()
    src = get_source("venation")
    start = time.perf_counter()
    src.trajectory(src.Params())  # runs to the "steps" axis's declared le=600
    elapsed = time.perf_counter() - start
    assert elapsed < 20.0, f"venation trajectory took {elapsed:.1f}s, budget is 20s"
