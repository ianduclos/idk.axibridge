from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from axibridge import registry
from axibridge.registry import (
    SourceModule,
    describe_modules,
    effective_bench,
    get_source,
    load_builtin_modules,
)


class _NoParams(BaseModel):
    pass


class _FrameParams(BaseModel):
    frame: float = Field(default=0.0, ge=0.0, le=1.0)


class _Source(SourceModule):
    id = "bench-test"
    label = "Bench test"
    orientation = "none"
    Params = _NoParams

    def generate(self, params):  # pragma: no cover - descriptor tests only
        raise NotImplementedError


def test_explicit_bench_does_not_require_a_time_axis(monkeypatch):
    class Explicit(_Source):
        id = "explicit-no-axis-bench-test"
        bench = {"adapter": "grammar", "version": 2, "modes": ["new", "resume"]}

    source = Explicit()
    monkeypatch.setitem(registry._SOURCES, source.id, source)
    item = next(
        item for item in describe_modules()["sources"] if item["id"] == source.id
    )
    assert item["time_axis"] is None
    assert item["bench"] == {
        "adapter": "grammar", "version": 2, "modes": ["new", "resume"]
    }


def test_frame_axis_keeps_the_legacy_process_bench():
    class Framed(_Source):
        Params = _FrameParams

    assert effective_bench(Framed()) == {
        "adapter": "process", "version": 1, "modes": ["new", "watch"]
    }


def test_declared_adapter_name_is_open_grammar():
    class Future(_Source):
        bench = {"adapter": "future.instrument", "version": 7, "modes": ["watch"]}

    assert effective_bench(Future())["adapter"] == "future.instrument"


@pytest.mark.parametrize("descriptor", [
    {"adapter": "", "version": 1, "modes": ["new"]},
    {"adapter": "process", "version": 0, "modes": ["new"]},
    {"adapter": "process", "version": 1, "modes": ["edit"]},
])
def test_invalid_explicit_descriptor_is_rejected(descriptor):
    class Invalid(_Source):
        bench = descriptor

    with pytest.raises(ValueError, match="bench"):
        effective_bench(Invalid())


def test_second_reading_has_an_explicit_stable_bench_identity():
    load_builtin_modules()
    source = get_source("second_reading")
    identity = {
        "adapter": "second-reading", "version": 1, "modes": ["new", "resume"]
    }
    assert source.bench == identity
    assert effective_bench(source) == identity
    catalogue_item = next(
        item for item in describe_modules()["sources"] if item["id"] == source.id
    )
    assert catalogue_item["bench"] == identity
    assert source.bench_capabilities == ("intervene", "branch")
