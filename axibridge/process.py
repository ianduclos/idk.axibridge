"""A generator whose output is the state of a process at step N.

Most generators here are instantaneous: params in, drawing out. A growth, a
search, a system holding itself in equilibrium is a process that UNFOLDS, and
the interesting output is often the trajectory rather than the converged
result. This is the base class for those.

THE RULE EVERYTHING RESTS ON: ``generate()`` stays a pure function from params
to geometry, and time is an ordinary bounded param. Everything downstream —
``gencache``'s content-keyed memo, ``tween``'s param lerp, undo, the estimate,
the plotter, the single-resolve invariant — holds only because a generator is a
pure function of its params. A process carrying live mutable state would need a
second geometry path into the plotter, which CLAUDE.md forbids. So the process
is REPLAYED, never HELD.

An author writes ``run()``, which yields one ``Step`` per tick; ``generate()``
is provided. ``run()`` may be an unbounded ``while True`` loop — the base stops
consuming at the time axis's upper bound, so the PARAM decides how long the
process runs. A ``run()`` that ends early simply ends: steps past the last
yield repeat the final state rather than raising, so a process that converges
before its budget still scrubs to the end.

``Step.paths`` is **the marks ADDED at this step** for an accumulative process
(the default), which is what makes the state at step N a prefix slice rather
than a re-run. A process that REVISES earlier marks instead of adding to them
(a curve-shortening flow, a diffusion descent) sets ``accumulative = False``
and yields the complete state each time; see ``trajectory.py`` for what that
costs.

``Step.telemetry`` is not decoration. A homeostat's whole premise is an
essential variable leaving its viable range, and "you cannot tune a homeostat
you cannot watch" means watching that NUMBER, not only the marks it leaves.
The popup plots whatever keys turn up; a process that reports nothing gets no
plot and costs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from pydantic import BaseModel

from .model import Layer, Path, PathDocument
from .registry import SourceModule


@dataclass
class Step:
    """One tick of a process."""

    #: The marks ADDED at this step (accumulative, the default), or the
    #: complete state at this step when ``accumulative`` is False.
    paths: list[Path] = field(default_factory=list)
    #: Anything worth plotting against time — an essential variable, a
    #: population count, an error. Flat and unregistered on purpose: the popup
    #: plots whatever keys turn up.
    telemetry: dict[str, float] | None = None


class ProcessModule(SourceModule):
    """A ``SourceModule`` that unfolds. Registers and behaves like any other."""

    #: Processes are stepped, so the axis is an int step count by convention.
    #: Override if the param has another name; it must exist and be bounded.
    time_axis: str = "steps"

    #: True: each Step ADDS marks, and state N is the concatenation of steps
    #: 0..N. False: each Step is the whole state, which costs far more to
    #: cache — see trajectory.py.
    accumulative: bool = True

    def run(self, params: BaseModel) -> Iterator[Step]:  # pragma: no cover - abstract
        raise NotImplementedError

    def trajectory(self, params: BaseModel) -> "Trajectory":
        """The whole run, up to the axis's upper bound. Task 3 makes this
        cached; the semantics do not change."""
        from .trajectory import build

        return build(self, params)

    def document(self, params: BaseModel, paths: list[Path]) -> PathDocument:
        """Wrap a state in a document. Override to set width/height/name."""
        xs = [x for p in paths for x, _ in p.points] or [0.0]
        ys = [y for p in paths for _, y in p.points] or [0.0]
        return PathDocument(
            layers=[Layer(id=1, name=self.id, color="#26241f", paths=list(paths))],
            width=max(xs) - min(xs),
            height=max(ys) - min(ys),
            source=f"{self.id} @ {getattr(params, self.time_axis)}",
        )

    def generate(self, params: BaseModel) -> PathDocument:
        step = int(getattr(params, self.time_axis))
        return self.document(params, self.trajectory(params).state(step))
