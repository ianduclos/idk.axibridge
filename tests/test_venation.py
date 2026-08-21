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
    """Both halves need `clear_cache()` between calls: `run(steps=40,
    seed=11)` used against a warm trajectory cache hits the SAME cached
    Trajectory object both times, so the equality half would compare an
    object with itself and pass even against a non-deterministic
    implementation."""
    from axibridge import trajectory as trajectory_module

    trajectory_module.clear_cache()
    first = [tuple(p.points) for p in run(steps=40, seed=11)]
    trajectory_module.clear_cache()
    second = [tuple(p.points) for p in run(steps=40, seed=11)]
    assert first == second

    trajectory_module.clear_cache()
    third = [tuple(p.points) for p in run(steps=40, seed=12)]
    assert first != third


def test_telemetry_reports_the_hunt():
    src = get_source("venation")
    traj = src.trajectory(src.Params(steps=60, seed=2))
    counts = [t["attractors"] for t in traj.telemetry]
    assert counts[0] >= counts[-1], "attractors are consumed as growth reaches them"
    assert all("tips" in t for t in traj.telemetry)


# No test_coordinates_are_plain_python_floats: `Point = tuple[float, float]`,
# and every Path here is built via `Path(points=[...])`, so Pydantic v2
# coerces any numpy scalar (np.float64/np.float32) to plain `float` at
# construction — before a test could ever observe one. That coercion is the
# real guarantee, and it holds regardless of what `run()`'s internals do, so
# a `type(x) is float` assertion on the returned points cannot fail whatever
# the implementation is. Confirmed vacuous in review; not worth a fake guard.


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


def test_a_pathological_run_stays_bounded():
    """The Critical review finding on this module: covering only default
    params in the perf test above is exactly why the original vectorisation
    got through review with an unbounded worst case. At a small `kill`,
    attractors are rarely consumed, growth never converges, and node count
    runs away across the full 601-step trajectory — measured pre-fix:
    `kill` at its declared minimum (0.5) with otherwise-default params did
    not finish in 60s and peaked around 7 GB RSS, and
    `attractors=3000, attraction=120, kill=0.5, step_len=0.3` took 64s and
    6.2 GB. Both are one slider drag from the default and inside every
    declared param bound, and both land on the very first `generate()` (a
    trajectory always runs to the time axis's declared upper bound). This
    pins both halves of the fix: a tight time budget, AND that total node
    count actually stays capped rather than merely running fast while still
    unbounded."""
    from axibridge import trajectory as trajectory_module
    from axibridge.sources.venation import _MAX_NODES

    trajectory_module.clear_cache()
    src = get_source("venation")
    start = time.perf_counter()
    traj = src.trajectory(src.Params(
        attractors=3000, attraction=120.0, kill=0.5, step_len=0.3))
    elapsed = time.perf_counter() - start
    total_nodes = sum(len(step) for step in traj.steps)
    assert elapsed < 20.0, f"pathological venation trajectory took {elapsed:.1f}s, budget is 20s"
    assert total_nodes <= _MAX_NODES, (
        f"node growth ran away: {total_nodes} nodes exceeds the {_MAX_NODES} cap")
