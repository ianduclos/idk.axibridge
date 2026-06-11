"""No-hardware simulator backend.

Executes a :class:`PlannedJob` (from the estimator) against a wall clock, so
the whole app — preview, params, plot control, progress, pause/resume — works
with nothing plugged in. It is also the worked example of writing a backend:
everything except the absence of a serial port looks exactly like a real one.

Capability asymmetry on display: the simulator supports cornering (it drives
the estimator, which models junctions) but not raw EBB (there is no EBB), the
inverse of saxi which has a planner but no trapdoor.
"""

from __future__ import annotations

import math
import time
from typing import Any

from pydantic import BaseModel, Field

from ..estimate import MotionParams, plan_job
from ..model import PathDocument
from .base import BackendCapabilities, EmitFn, ExecutionBackend, JobControl


class SimulatorParams(MotionParams):
    """All estimator params, plus simulator-only time scaling."""

    time_scale: float = Field(
        default=10.0, ge=0.1, le=1000.0, title="Time scale ×",
        description="Simulated seconds per wall-clock second (10 = 10× faster than real time)",
    )


class SimulatorBackend(ExecutionBackend):
    id = "simulator"
    label = "Simulator (no hardware)"
    description = "Virtual machine: walks the planned job on a clock and streams position."
    Params = SimulatorParams

    TICK_S = 0.04  # emit cadence in wall-clock seconds

    def __init__(self) -> None:
        self._connected = False
        self._pos: tuple[float, float] = (0.0, 0.0)
        self._origin: tuple[float, float] = (0.0, 0.0)
        self._pen_down = False

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            requires_serial_port=False,
            jog=True,
            pen_control=True,
            set_origin=True,
            raw_ebb=False,
            pause_resume=True,
            live_position=True,
            progress_granularity="path",
            notes="Timing comes from the estimator; treat it as ±15% of the real machine.",
        )

    # -- lifecycle ---------------------------------------------------------

    def connect(self, port: str | None) -> dict[str, Any]:
        self._connected = True
        self._pos = (0.0, 0.0)
        return {"port": "virtual", "firmware": "axibridge simulator"}

    def disconnect(self) -> None:
        self._connected = False

    def deactivate(self) -> None:
        self.disconnect()

    @property
    def connected(self) -> bool:
        return self._connected

    # -- interactive --------------------------------------------------------

    def pen(self, down: bool, params: BaseModel) -> None:
        self._pen_down = down

    def jog(self, dx: float, dy: float, params: BaseModel) -> tuple[float, float]:
        self._pos = (self._pos[0] + dx, self._pos[1] + dy)
        return self.position()

    def goto(self, x: float, y: float, params: BaseModel) -> tuple[float, float]:
        self._pos = (self._origin[0] + x, self._origin[1] + y)
        return self.position()

    def set_origin(self, x: float = 0.0, y: float = 0.0) -> None:
        self._origin = (self._pos[0] - x, self._pos[1] - y)

    def position(self) -> tuple[float, float]:
        return (self._pos[0] - self._origin[0], self._pos[1] - self._origin[1])

    # -- plotting ------------------------------------------------------------

    def plot(self, doc: PathDocument, params: SimulatorParams, control: JobControl, emit: EmitFn) -> None:
        from ..estimate import EstimatorConstants
        from ..stores import settings_store

        consts = EstimatorConstants(**settings_store.settings.model_dump())
        job = plan_job(doc, MotionParams(**params.model_dump(exclude={"time_scale"})), consts=consts)
        scale = params.time_scale
        paths_total = sum(1 for m in job.moves if m.pen_down)
        paths_done = 0
        sim_elapsed = 0.0

        emit({"kind": "started", "paths_total": paths_total,
              "estimated_duration": job.total_duration})

        for move in job.moves:
            if control.stopped:
                break
            control.wait_if_paused()
            self._pen_down = move.pen_down
            # Walk the move point-to-point at the estimated pace.
            seg_lens = [math.dist(a, b) for a, b in zip(move.points, move.points[1:])]
            total = sum(seg_lens) or 1.0
            for (a, b), seg in zip(zip(move.points, move.points[1:]), seg_lens):
                if control.stopped:
                    break
                control.wait_if_paused()
                seg_t = move.duration * (seg / total)
                steps = max(int(seg_t / scale / self.TICK_S), 1)
                for i in range(1, steps + 1):
                    if control.stopped:
                        break
                    control.wait_if_paused()
                    t = i / steps
                    self._pos = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                    sim_elapsed += seg_t / steps
                    time.sleep(seg_t / scale / steps)
                    emit({
                        "kind": "position",
                        "position": list(self.position()),
                        "pen_down": move.pen_down,
                        "progress": min(sim_elapsed / job.total_duration, 1.0) if job.total_duration else 1.0,
                        "elapsed": sim_elapsed,
                        "remaining": max(job.total_duration - sim_elapsed, 0.0),
                    })
            if move.pen_down and not control.stopped:
                paths_done += 1
                emit({"kind": "progress", "paths_done": paths_done, "paths_total": paths_total,
                      "progress": min(sim_elapsed / job.total_duration, 1.0) if job.total_duration else 1.0})

        self._pen_down = False
        emit({"kind": "stopped" if control.stopped else "finished",
              "paths_done": paths_done, "paths_total": paths_total})
