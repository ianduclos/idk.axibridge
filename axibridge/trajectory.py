"""The whole run of a process, so a scrub is a slice instead of a re-run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

from .model import Path
from .registry import field_bounds

if TYPE_CHECKING:
    from .process import ProcessModule


@dataclass
class Trajectory:
    #: per step: the marks added (accumulative) or the whole state (not)
    steps: list[list[Path]]
    telemetry: list[dict[str, float]]
    accumulative: bool

    def state(self, n: int) -> list[Path]:
        """The drawing as it stands at step ``n``."""
        if not self.steps:
            return []
        n = max(0, min(n, len(self.steps) - 1))
        if not self.accumulative:
            return list(self.steps[n])
        out: list[Path] = []
        for chunk in self.steps[: n + 1]:
            out.extend(chunk)
        return out


def build(module: "ProcessModule", params: BaseModel) -> Trajectory:
    """The whole run, up to the time axis's upper bound.

    Bounds come from the PARAMS MODEL directly (``field_bounds`` on the
    field itself), never from a registry/session lookup keyed by
    ``module.id``: this module sits under ``session`` in the import graph
    (``session -> registry -> sources -> process -> trajectory``), so a
    lookup back up through the registry would be circular, and a process
    class under test is never registered, so a registry lookup would raise
    on the exact fixtures that exercise this function.
    """
    bounds = field_bounds(type(params).model_fields[module.time_axis])
    last = int(bounds[1]) if bounds else int(getattr(params, module.time_axis))
    steps: list[list[Path]] = []
    telemetry: list[dict[str, float]] = []
    for i, step in enumerate(module.run(params)):
        steps.append(list(step.paths))
        telemetry.append(dict(step.telemetry or {}))
        if i >= last:
            break
    return Trajectory(steps, telemetry, module.accumulative)
