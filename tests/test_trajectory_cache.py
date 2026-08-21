"""Running the process once and slicing it is the difference between
'scrubbing is free' and 'scrubbing re-runs the process'. These tests pin that
the cache is a SPEED change only."""

from pydantic import BaseModel, Field

from axibridge import trajectory
from axibridge.model import Path
from axibridge.process import ProcessModule, Step


class P(BaseModel):
    steps: int = Field(default=2, ge=0, le=6)
    seed: int = Field(default=0, ge=0, le=99)


class Counted(ProcessModule):
    id = "test_counted"
    orientation = "none"
    label = "Counted"
    Params = P
    runs = 0

    def run(self, params):
        Counted.runs += 1
        for i in range(7):
            yield Step(paths=[Path(points=[(0.0, float(i)), (1.0, float(i))])])


def test_scrubbing_the_axis_runs_the_process_once():
    trajectory.clear_cache()
    Counted.runs = 0
    mod = Counted()
    for n in range(7):
        mod.generate(P(steps=n))
    assert Counted.runs == 1, "the step param must not be part of the cache key"


def test_a_different_param_is_a_different_trajectory():
    trajectory.clear_cache()
    Counted.runs = 0
    mod = Counted()
    mod.generate(P(steps=3, seed=1))
    mod.generate(P(steps=3, seed=2))
    assert Counted.runs == 2


def test_the_cache_changes_no_output():
    mod = Counted()
    trajectory.clear_cache()
    cold = [tuple(p.points) for layer in mod.generate(P(steps=5)).layers
            for p in layer.paths]
    warm = [tuple(p.points) for layer in mod.generate(P(steps=5)).layers
            for p in layer.paths]
    trajectory.clear_cache()
    again = [tuple(p.points) for layer in mod.generate(P(steps=5)).layers
             for p in layer.paths]
    assert cold == warm == again


def test_the_cache_is_bounded():
    trajectory.clear_cache()
    mod = Counted()
    for seed in range(60):
        mod.generate(P(steps=6, seed=seed))
    assert len(trajectory._CACHE) <= trajectory.CACHE_MAX_ENTRIES
