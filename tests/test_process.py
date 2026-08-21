"""ProcessModule: a generator whose output is the state of a process at step N.

The contract is one sentence — `generate()` is still a pure function of params
— and every test here is a consequence of it."""

import pytest
from pydantic import BaseModel, Field

from axibridge.model import Path
from axibridge.process import ProcessModule, Step


class CountParams(BaseModel):
    steps: int = Field(default=3, ge=0, le=10)
    dx: float = Field(default=1.0, ge=0.0, le=10.0)


class Counter(ProcessModule):
    """Adds one horizontal segment per step, one unit further along."""
    id = "test_counter"
    orientation = "none"
    label = "Counter"
    Params = CountParams

    def run(self, params):
        i = 0
        while True:
            y = i * params.dx
            yield Step(paths=[Path(points=[(0.0, y), (10.0, y)], filled=False)],
                       telemetry={"i": float(i)})
            i += 1


def paths_at(step: int, **kw) -> list[Path]:
    doc = Counter().generate(CountParams(steps=step, **kw))
    return [p for layer in doc.layers for p in layer.paths]


def test_state_at_step_n_is_the_first_n_plus_one_increments():
    assert len(paths_at(0)) == 1
    assert len(paths_at(3)) == 4


def test_a_prefix_equals_a_truncated_full_run():
    """The trajectory's whole correctness claim, asserted before there is a
    cache to get it wrong."""
    full = [tuple(p.points) for p in paths_at(9)]
    for n in range(10):
        assert [tuple(p.points) for p in paths_at(n)] == full[:n + 1]


def test_generate_is_pure_and_repeatable():
    assert [tuple(p.points) for p in paths_at(5)] == [tuple(p.points) for p in paths_at(5)]


def test_an_unbounded_run_is_stopped_by_the_param():
    """`run` here is `while True`. The PARAM decides how long it runs — the
    same reason every numeric field in this repo is bounded, applied to time."""
    assert len(paths_at(10)) == 11


def test_telemetry_is_collected_per_step():
    """The trajectory runs to the time axis's own declared bound (steps'
    ge=0/le=10), not to whatever value `steps` happens to hold in `params` —
    that decoupling is what lets a scrub slice one cached trajectory instead
    of re-running it per step (see trajectory.py's module docstring)."""
    traj = Counter().trajectory(CountParams(steps=4))
    assert [t["i"] for t in traj.telemetry] == [float(i) for i in range(11)]


def test_a_process_declares_its_time_axis_by_default():
    assert Counter.time_axis == "steps"
