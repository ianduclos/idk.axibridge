"""MachineManager: the single owner of "which backend, which port, what job".

Responsibilities, and why they live here rather than in backends:

* **Port arbitration.** Only one process may own the EBB serial port.
  ``select_backend`` always runs old.deactivate() (release port / kill saxi
  subprocess) before new.activate(). Backends never coordinate with each
  other.
* **Job threading.** ``plot()`` on a backend is blocking by design; the
  manager runs it in a worker thread, owns the JobControl, and serialises
  interactive ops against it (jog while plotting is refused, not queued).
* **Soft limits.** The machine is open-loop with no limit switches — driving
  past the envelope grinds the carriage into the frame. Guards are checked
  here so every backend gets them uniformly, and they are *toggleable*
  because pushing the envelope is a legitimate experiment. The raw EBB
  trapdoor intentionally bypasses them.
"""

from __future__ import annotations

import threading
from typing import Any

from pydantic import BaseModel, Field

from .backends.axidraw_native import NativeAxidrawBackend
from .backends.base import ExecutionBackend, JobControl
from .backends.pi_ssh import PiSshBackend
from .backends.saxi import SaxiBackend
from .backends.simulator import SimulatorBackend
from .events import bus
from .model import PathDocument
from .stores import settings_store


class SoftLimits(BaseModel):
    """Travel envelope guard. Measured from the *user origin*: if you re-set
    origin mid-bed, the guarded window shifts with it — re-origin at the home
    corner (or disable the guard knowingly)."""

    enabled: bool = True
    width: float = Field(default=300, ge=10, le=1200, title="Envelope width (mm)",
                         description="AxiDraw V3: 300 — SE/A3: 430 — push at your own risk")
    height: float = Field(default=218, ge=10, le=1200, title="Envelope height (mm)",
                          description="AxiDraw V3: 218 — SE/A3: 297")

    def check_point(self, x: float, y: float) -> bool:
        return (not self.enabled) or (0 <= x <= self.width and 0 <= y <= self.height)


def find_ebb_port() -> str | None:
    """The EBB enumerates as USB CDC with product string 'EiBotBoard'
    (VID 0x04D8, PID 0xFD92)."""
    from serial.tools import list_ports

    for p in list_ports.comports():
        text = f"{p.description or ''} {p.product or ''}"
        if "EiBotBoard" in text or (p.vid == 0x04D8 and p.pid == 0xFD92):
            return p.device
    return None


class MachineManager:
    def __init__(self) -> None:
        self.backends: dict[str, ExecutionBackend] = {}
        for b in (NativeAxidrawBackend(), SimulatorBackend(), SaxiBackend(), PiSshBackend()):
            self.backends[b.id] = b
        self.active_id = "simulator"  # safe default: usable with no hardware
        try:  # soft limits persist machine-level (~/.axibridge/settings.json)
            self.limits = SoftLimits(**settings_store.settings.soft_limits)
        except Exception:
            self.limits = SoftLimits()
        self._lock = threading.RLock()
        self._job_thread: threading.Thread | None = None
        self._control: JobControl | None = None
        self._job_state = "idle"  # idle | plotting | paused
        self._return_home = False  # stop(return_home=True) pending
        self._last_connect_info: dict[str, Any] = {}

    # -- introspection ---------------------------------------------------

    @property
    def active(self) -> ExecutionBackend:
        return self.backends[self.active_id]

    @property
    def job_state(self) -> str:
        return self._job_state

    def status(self) -> dict[str, Any]:
        b = self.active
        return {
            "backend": self.active_id,
            "connected": b.connected,
            "connect_info": self._last_connect_info,
            "job_state": self._job_state,
            "position": list(b.position()) if b.connected else None,
            "limits": self.limits.model_dump(),
        }

    def describe_backends(self) -> list[dict[str, Any]]:
        out = []
        for b in self.backends.values():
            ok, reason = b.available()
            out.append({
                "id": b.id,
                "label": b.label,
                "description": b.description,
                "available": ok,
                "unavailable_reason": reason,
                "capabilities": b.capabilities().model_dump(),
                "params_schema": b.Params.model_json_schema(),
                "params_defaults": b.Params().model_dump(),
                "active": b.id == self.active_id,
                "connected": b.connected,
            })
        return out

    # -- backend switching / connection -----------------------------------

    def select_backend(self, backend_id: str) -> None:
        with self._lock:
            if backend_id not in self.backends:
                raise KeyError(f"unknown backend: {backend_id!r}")
            if self._job_state != "idle":
                raise RuntimeError("cannot switch backends while a job is running")
            if backend_id == self.active_id:
                return
            self.active.deactivate()  # releases serial port / subprocess
            self.active_id = backend_id
            self._last_connect_info = {}
            self.active.activate()
            bus.emit({"type": "backend", "backend": backend_id})
            self._emit_status()

    def connect(self, port: str | None) -> dict[str, Any]:
        with self._lock:
            info = self.active.connect(port)
            self._last_connect_info = info
            self._emit_status()
            return info

    def disconnect(self) -> None:
        with self._lock:
            if self._job_state != "idle":
                raise RuntimeError("stop the current job before disconnecting")
            self.active.disconnect()
            self._last_connect_info = {}
            self._emit_status()

    # -- interactive ops ------------------------------------------------------

    def _require_idle(self) -> ExecutionBackend:
        if self._job_state != "idle":
            raise RuntimeError("machine is busy plotting")
        b = self.active
        if not b.connected:
            raise RuntimeError("not connected")
        return b

    def pen(self, down: bool, params: BaseModel) -> None:
        with self._lock:
            self._require_idle().pen(down, params)

    def jog(self, dx: float, dy: float, params: BaseModel) -> tuple[float, float]:
        with self._lock:
            b = self._require_idle()
            x, y = b.position()
            tx, ty = x + dx, y + dy
            if not self.limits.check_point(tx, ty):
                raise RuntimeError(
                    f"jog target ({tx:.1f}, {ty:.1f}) outside soft limits "
                    f"{self.limits.width}x{self.limits.height} mm (toggle limits to override)"
                )
            pos = b.jog(dx, dy, params)
            self._emit_status()
            return pos

    def goto(self, x: float, y: float, params: BaseModel) -> tuple[float, float]:
        with self._lock:
            b = self._require_idle()
            if not self.limits.check_point(x, y):
                raise RuntimeError(f"target ({x:.1f}, {y:.1f}) outside soft limits")
            pos = b.goto(x, y, params)
            self._emit_status()
            return pos

    def set_origin(self, x: float = 0.0, y: float = 0.0) -> None:
        with self._lock:
            self._require_idle().set_origin(x, y)
            self._emit_status()

    def raw(self, command: str, expect_reply: bool) -> str:
        with self._lock:
            b = self._require_idle()
            if not b.capabilities().raw_ebb:
                raise RuntimeError(f"backend {b.id!r} has no raw EBB access")
            return b.raw(command, expect_reply)

    # -- plotting ----------------------------------------------------------------

    def check_envelope(self, doc: PathDocument) -> list[str]:
        """Pre-flight warnings (also surfaced in the UI before start).

        The guarded window shifts with the machine origin: after a mid-bed
        set-origin, design coordinates land at origin+xy physically, so the
        usable design-frame window shrinks accordingly. Ignoring this is how
        an 'all inside the guide' plot grinds past the bed edge."""
        warnings = []
        b = doc.bounds()
        if b and self.limits.enabled:
            ox, oy = self.active.origin_offset() if self.active.connected else (0.0, 0.0)
            xmin, ymin, xmax, ymax = b
            if (xmin + ox < 0 or ymin + oy < 0
                    or xmax + ox > self.limits.width or ymax + oy > self.limits.height):
                offset_note = (
                    f" (machine origin is offset by ({ox:.1f}, {oy:.1f}) mm — "
                    "set-origin at the home corner to clear)"
                    if abs(ox) > 0.05 or abs(oy) > 0.05 else ""
                )
                warnings.append(
                    f"geometry bounds ({xmin:.1f},{ymin:.1f})–({xmax:.1f},{ymax:.1f}) "
                    f"exceed the soft envelope {self.limits.width}×{self.limits.height} mm"
                    + offset_note
                )
        return warnings

    def start_plot(self, doc: PathDocument, params: BaseModel) -> None:
        with self._lock:
            b = self._require_idle()
            problems = self.check_envelope(doc)
            if problems:
                raise RuntimeError("; ".join(problems) + " — disable soft limits to plot anyway")
            self._control = JobControl()
            self._job_state = "plotting"
            control = self._control

            def emit(e: dict) -> None:
                bus.emit({"type": "job", **e})

            def run() -> None:
                try:
                    b.plot(doc, params, control, emit)
                except Exception as exc:  # surface backend crashes to the UI
                    bus.emit({"type": "job", "kind": "error", "message": str(exc)})
                finally:
                    with self._lock:
                        # walk home only for a user STOP that asked for it —
                        # never after a normal finish or a crash
                        go_home = self._return_home and control.stopped
                        self._return_home = False
                        self._job_state = "idle"
                        self._control = None
                    if go_home:
                        try:  # backend is idle again; goto re-checks limits
                            self.goto(0.0, 0.0, params)
                            emit({"kind": "message", "message": "stopped — carriage returned home"})
                        except Exception as exc:
                            emit({"kind": "message",
                                  "message": f"stopped, but return-home failed: {exc}"})
                    self._emit_status()

            self._job_thread = threading.Thread(target=run, name="axibridge-plot", daemon=True)
            self._job_thread.start()
            self._emit_status()

    def pause(self) -> None:
        with self._lock:
            if self._control is None:
                raise RuntimeError("no job running")
            if not self.active.capabilities().pause_resume:
                raise RuntimeError(f"backend {self.active_id!r} cannot pause")
            self._control.pause()
            self._job_state = "paused"
            self._emit_status()

    def resume(self) -> None:
        with self._lock:
            if self._control is None:
                raise RuntimeError("no job running")
            self._control.resume()
            self._job_state = "plotting"
            self._emit_status()

    def stop(self, return_home: bool = False) -> None:
        with self._lock:
            if self._control is None:
                return
            self._return_home = return_home
            self._control.stop()
        # state flips to idle when the worker exits (which then walks home
        # if return_home was requested — see start_plot's finally)

    def auto_connect(self) -> bool:
        """If an AxiDraw is plugged in and nothing is connected, select the
        native backend and connect to it. Called in a background thread at
        startup (serial connect blocks for a couple of seconds) and after
        the native backend is selected manually. Returns True on connect."""
        with self._lock:
            if self.active.connected or self._job_state != "idle":
                return False
            port = find_ebb_port()
            if port is None:
                return False
            native = self.backends.get("native")
            if native is None or not native.available()[0]:
                return False
            try:
                if self.active_id != "native":
                    self.select_backend("native")
                info = self.connect(port)
            except Exception as exc:
                bus.emit({"type": "job", "kind": "message",
                          "message": f"auto-connect failed: {exc}"})
                return False
            bus.emit({"type": "job", "kind": "message",
                      "message": f"auto-connected to AxiDraw on {info.get('port', port)}"})
            return True

    def shutdown(self) -> None:
        self.stop()
        if self._job_thread is not None and self._job_thread.is_alive():
            self._job_thread.join(timeout=10)
        self.active.deactivate()

    def _emit_status(self) -> None:
        bus.emit({"type": "status", **self.status()})


manager = MachineManager()
