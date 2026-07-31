"""Execution backend protocol + capability advertising.

Design notes
------------
* **Capabilities are data, not documentation.** ``capabilities()`` returns
  feature flags, and the backend's ``Params`` model *is* the set of motion
  parameters it honours. The UI renders forms from that schema, so a backend
  that doesn't support cornering simply doesn't have a cornering field — no
  dead knobs by construction.
* **Backends are blocking and synchronous.** ``plot()`` runs in a worker
  thread owned by the MachineManager and communicates through ``JobControl``
  (pause/stop events) and ``emit`` (progress events). This keeps backends
  trivially simple to write — no asyncio in the hardware layer — and is also
  the seam for a future streaming/look-ahead backend: such a backend would
  implement the same ``plot()`` signature but feed the EBB incrementally,
  checking ``control`` between chunks instead of between paths.
* **Port ownership** is enforced by the manager, not by convention: only the
  *active* backend is ever activated, and switching always runs
  ``deactivate()`` (which must release the serial port / kill subprocesses)
  before the next backend's ``activate()``.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Any, Callable

from pydantic import BaseModel, Field

from ..model import PathDocument

#: Progress callback: backends emit small dicts; the manager wraps them into
#: SSE events. Keys used by the frontend: kind, message, paths_done,
#: paths_total, progress (0..1), position [x, y], pen_down, elapsed, remaining.
EmitFn = Callable[[dict[str, Any]], None]


class BackendCapabilities(BaseModel):
    """What a backend can do — drives which UI panels are live."""

    requires_serial_port: bool = Field(description="Needs a physical EBB serial port selected")
    jog: bool = False
    pen_control: bool = False
    set_origin: bool = False
    raw_ebb: bool = False
    pause_resume: bool = False
    live_position: bool = Field(default=False, description="Emits positions during plot (animates the preview marker)")
    progress_granularity: str = Field(default="none", description="'path' | 'coarse' | 'none'")
    notes: str = ""


class JobControl:
    """Pause/stop signalling between the manager and a plotting thread."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._resume.set()  # not paused

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    def stop(self) -> None:
        self._stop.set()
        self._resume.set()  # unblock a paused job so it can exit

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    @property
    def paused(self) -> bool:
        return not self._resume.is_set() and not self._stop.is_set()

    def wait_if_paused(self) -> None:
        """Block while paused; returns immediately if running or stopped."""
        self._resume.wait()


class ExecutionBackend(ABC):
    """Base class for execution backends.

    Lifecycle: ``activate() -> [connect(port) -> ... -> disconnect()] ->
    deactivate()``. Only one backend is active at a time (manager-enforced).
    All methods are called from worker threads / the API thread pool — never
    from the event loop — so blocking on serial I/O is fine.
    """

    id: str
    label: str
    description: str = ""
    #: Motion/behaviour parameters this backend honours. The JSON Schema of
    #: this model is the backend's *parameter capability advertisement*.
    Params: type[BaseModel] = BaseModel

    # -- availability / capability --------------------------------------

    def available(self) -> tuple[bool, str]:
        """(ok, reason-if-not) — e.g. pyaxidraw not installed."""
        return True, ""

    @abstractmethod
    def capabilities(self) -> BackendCapabilities: ...

    # -- lifecycle --------------------------------------------------------

    def activate(self) -> None:
        """Become the active backend. Must NOT grab the serial port yet
        (that's connect's job) so enumeration works while inactive."""

    def deactivate(self) -> None:
        """Release everything: serial port, subprocesses, threads."""

    @abstractmethod
    def connect(self, port: str | None) -> dict[str, Any]:
        """Open the device (or virtual device). Returns info for the UI,
        e.g. {"firmware": ..., "port": ...}. Raises on failure."""

    @abstractmethod
    def disconnect(self) -> None: ...

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    # -- interactive (idle-state) operations ------------------------------
    # Only called when no job is running and the capability flag is set.

    def pen(self, down: bool, params: BaseModel) -> None:
        raise NotImplementedError(f"{self.id}: pen control not supported")

    def jog(self, dx: float, dy: float, params: BaseModel) -> tuple[float, float]:
        """Relative pen-up move. Returns the new dead-reckoned position."""
        raise NotImplementedError(f"{self.id}: jog not supported")

    def goto(self, x: float, y: float, params: BaseModel) -> tuple[float, float]:
        """Absolute pen-up move in the user frame."""
        raise NotImplementedError(f"{self.id}: goto not supported")

    def set_origin(self, x: float = 0.0, y: float = 0.0) -> None:
        """Declare the current carriage position to be design point (x, y).

        (0, 0) is the classic re-zero; passing the paper-guide corner instead
        lets the user jog to the taped sheet's corner and bind the design
        frame to it without moving the carriage."""
        raise NotImplementedError(f"{self.id}: set_origin not supported")

    def position(self) -> tuple[float, float]:
        """Dead-reckoned position in the user frame. Open-loop machine:
        this is the commanded position, which IS the physical position as
        long as nothing skipped steps."""
        return (0.0, 0.0)

    def origin_offset(self) -> tuple[float, float]:
        """Where the user origin sits in the connect frame. Non-zero after a
        mid-bed set-origin; the envelope guard must shift the guarded window
        by this much or a design-frame-legal plot exceeds the physical bed."""
        return (0.0, 0.0)

    def raw(self, command: str, expect_reply: bool = True) -> str:
        """Raw EBB pass-through. The trapdoor."""
        raise NotImplementedError(f"{self.id}: raw EBB access not supported")

    def block(self) -> None:
        """Wait until the machine's motion queue is empty."""
        raise NotImplementedError(f"{self.id}: wait-for-idle not supported")

    # -- plotting ----------------------------------------------------------

    @abstractmethod
    def plot(
        self,
        doc: PathDocument,
        params: BaseModel,
        control: JobControl,
        emit: EmitFn,
    ) -> None:
        """Plot the document. Blocking; runs in a manager-owned thread.

        Must check ``control.wait_if_paused()`` / ``control.stopped`` at its
        natural granularity (between paths for path-based backends), emit
        progress dicts via ``emit``, and leave the pen UP on any exit path.
        """
