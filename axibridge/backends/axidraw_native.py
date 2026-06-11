"""Native execution backend: the official EMSL stack with a raw-EBB trapdoor.

Layering exposed (top to bottom):

1. **plot(doc)** — iterates the IPR through pyaxidraw's *interactive* API
   (``moveto``/``lineto``), so plotink's planner handles acceleration and the
   servo, while *we* keep control of ordering, pause points and progress.
2. **Interactive ops** — jog, pen toggle, goto, set-origin between jobs.
3. **raw(cmd)** — verbatim EBB commands (``LM``, ``XM``, ``SM``, ``SP``,
   ``QM``, ``QS``, ...) via pyaxidraw's documented ``usb_command`` /
   ``usb_query``, replies surfaced. This bypasses the planner *and* the soft
   limits — that's the point, and the UI says so.

Position is dead reckoning: the machine is open-loop, so the commanded
position IS the physical position unless steps were skipped or a raw command
moved the carriage. After raw motion commands, host-side position is stale —
re-zero with set-origin if you've been spelunking.

pyaxidraw is not on PyPI; ``available()`` reports the install command.
"""

from __future__ import annotations

import importlib.util
import logging
import math
import sys
import threading
from typing import Any

from pydantic import BaseModel, Field

from ..model import PathDocument
from .base import BackendCapabilities, EmitFn, ExecutionBackend, JobControl

logger = logging.getLogger(__name__)


class NativeParams(BaseModel):
    """pyaxidraw option set — note: *no cornering field*. plotink's planner
    has a fixed cornering policy; advertising a knob it won't honour would be
    a dead control, so the field simply doesn't exist here. (saxi and the
    simulator do expose it.)"""

    speed_pendown: float = Field(default=25, ge=1, le=110, title="Pen-down speed %")
    speed_penup: float = Field(default=75, ge=1, le=110, title="Pen-up speed %")
    accel: float = Field(default=75, ge=1, le=100, title="Acceleration %")
    pen_pos_down: float = Field(default=40, ge=0, le=100, title="Pen height: down %")
    pen_pos_up: float = Field(default=60, ge=0, le=100, title="Pen height: up %")
    pen_rate_lower: float = Field(default=50, ge=1, le=100, title="Pen lower rate %")
    pen_rate_raise: float = Field(default=75, ge=1, le=100, title="Pen raise rate %")
    pen_delay_down: float = Field(default=0, ge=-500, le=2000, title="Extra delay after lowering (ms)")
    pen_delay_up: float = Field(default=0, ge=-500, le=2000, title="Extra delay after raising (ms)")
    const_speed: bool = Field(default=False, title="Constant pen-down speed")
    model: int = Field(
        default=1, ge=1, le=6, title="AxiDraw model",
        description="1=V3/SE/A4, 2=V3/A3 or SE/A3, 3=V3 XLX, 4=MiniKit, 5=SE/A1, 6=SE/A2",
        # hidden from the auto-form: it's a hardware identity, not a knob —
        # wrong values let pyaxidraw command past the V3's physical travel
        json_schema_extra={"hidden": True},
    )


class NativeAxidrawBackend(ExecutionBackend):
    id = "native"
    label = "Native (pyaxidraw + plotink)"
    description = "Official EMSL stack, full motion-parameter control, raw EBB trapdoor."
    Params = NativeParams

    def __init__(self) -> None:
        self._ad = None
        self._lock = threading.RLock()
        self._pos = (0.0, 0.0)      # connect-frame, dead-reckoned
        self._origin = (0.0, 0.0)   # user origin, connect-frame
        self._firmware = ""

    def available(self) -> tuple[bool, str]:
        # The diagnostic names the interpreter: the classic failure is
        # pyaxidraw installed into a different Python (conda base vs the
        # project venv), which otherwise reads as "backend mysteriously gone".
        if importlib.util.find_spec("pyaxidraw") is None:
            return False, (
                f"pyaxidraw is not importable in this interpreter "
                f"({sys.executable}). Install it THERE with: "
                f"{sys.executable} -m pip install "
                "https://cdn.evilmadscientist.com/dl/ad/public/AxiDraw_API.zip"
            )
        return True, ""

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            requires_serial_port=True,
            jog=True,
            pen_control=True,
            set_origin=True,
            raw_ebb=True,
            pause_resume=True,
            live_position=True,
            progress_granularity="path",
            notes=(
                "Pause/stop take effect at path boundaries (each path is "
                "planned and run as one unit). Raw EBB commands bypass the "
                "planner AND the soft limits; host position is stale after "
                "raw motion — re-set origin."
            ),
        )

    # -- lifecycle ---------------------------------------------------------

    def connect(self, port: str | None) -> dict[str, Any]:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        from pyaxidraw import axidraw  # noqa: PLC0415 — guarded optional dep

        with self._lock:
            ad = axidraw.AxiDraw()
            ad.interactive()
            if port:
                ad.options.port = port
            ad.options.units = 2  # millimetres — the IPR convention
            if not ad.connect():
                raise RuntimeError(
                    f"could not connect to AxiDraw on {port or 'auto-detected port'}"
                )
            self._ad = ad
            self._pos = (0.0, 0.0)
            self._origin = (0.0, 0.0)
            self._flush_stale()
            # pyaxidraw stores the firmware version on plot_status, not the
            # main object; query directly only if connect didn't capture it.
            self._firmware = getattr(ad.plot_status, "fw_version", "") or self._query_fw()
            return {"port": port or "auto", "firmware": self._firmware}

    def _flush_stale(self) -> None:
        """Drain unread bytes from the EBB's receive buffer.

        plotink does strict one-command-one-response bookkeeping over the
        serial link. A single stranded line (an error reply it didn't expect,
        a leftover from a retried connect probe) shifts every later response
        by one, which eventually surfaces as "USB connection lost" on a
        perfectly healthy link. Draining before each command sequence makes
        every sequence start synchronized.
        """
        try:
            port_obj = self._ad.plot_status.port if self._ad else None
            if port_obj is None:
                return
            old_timeout = port_obj.timeout
            port_obj.timeout = 0.05
            stale = b""
            while True:
                chunk = port_obj.read(1024)
                if not chunk:
                    break
                stale += chunk
            port_obj.timeout = old_timeout
            if stale:
                logger.warning(
                    "flushed %d stale byte(s) from EBB: %r — a previous "
                    "command desynchronized the serial link",
                    len(stale), stale[:200],
                )
        except Exception:
            pass

    def _query_fw(self) -> str:
        try:
            return (self._ad.usb_query("V\r") or "").strip()
        except Exception:
            return "unknown"

    def disconnect(self) -> None:
        with self._lock:
            if self._ad is not None:
                try:
                    self._ad.penup()
                except Exception:
                    pass
                try:
                    self._ad.disconnect()
                finally:
                    self._ad = None

    def deactivate(self) -> None:
        # Releasing the port here is what lets saxi (a separate process)
        # open it. Manager calls this on every backend switch.
        self.disconnect()

    @property
    def connected(self) -> bool:
        return self._ad is not None

    def _require(self):
        if self._ad is None:
            raise RuntimeError("native backend: not connected")
        return self._ad

    def _apply(self, p: NativeParams) -> None:
        ad = self._require()
        self._flush_stale()
        # pyaxidraw declares every one of these options argparse type=int; its
        # delay values are interpolated verbatim into EBB command strings, so
        # a float produces e.g. "SP,1,253.0,1" — firmware (2.7.0) rejects the
        # ".0" with "!7 Err: Extra parmater", and that extra reply line
        # desynchronizes plotink's response bookkeeping for the whole session.
        for name in (
            "speed_pendown", "speed_penup", "accel", "pen_pos_down", "pen_pos_up",
            "pen_rate_lower", "pen_rate_raise", "pen_delay_down", "pen_delay_up",
            "model",
        ):
            setattr(ad.options, name, int(round(getattr(p, name))))
        ad.options.const_speed = p.const_speed
        ad.update()  # required in interactive mode after changing options

    # -- interactive ---------------------------------------------------------

    def pen(self, down: bool, params: NativeParams) -> None:
        with self._lock:
            self._apply(params)
            ad = self._require()
            ad.pendown() if down else ad.penup()

    def jog(self, dx: float, dy: float, params: NativeParams) -> tuple[float, float]:
        with self._lock:
            self._apply(params)
            ad = self._require()
            x, y = self._pos[0] + dx, self._pos[1] + dy
            ad.moveto(x, y)  # pen-up absolute
            self._pos = (x, y)
            return self.position()

    def goto(self, x: float, y: float, params: NativeParams) -> tuple[float, float]:
        with self._lock:
            self._apply(params)
            ad = self._require()
            ax, ay = self._origin[0] + x, self._origin[1] + y
            ad.moveto(ax, ay)
            self._pos = (ax, ay)
            return self.position()

    def set_origin(self, x: float = 0.0, y: float = 0.0) -> None:
        with self._lock:
            self._origin = (self._pos[0] - x, self._pos[1] - y)

    def position(self) -> tuple[float, float]:
        return (self._pos[0] - self._origin[0], self._pos[1] - self._origin[1])

    def origin_offset(self) -> tuple[float, float]:
        return self._origin

    def raw(self, command: str, expect_reply: bool = True) -> str:
        """The trapdoor. Commands are sent verbatim (CR appended if missing).

        Replies are read with pyaxidraw's usb_query. Motion commands (SM, XM,
        LM, HM...) desynchronise dead reckoning — that is on you, by design.
        """
        with self._lock:
            ad = self._require()
            cmd = command if command.endswith("\r") else command + "\r"
            if expect_reply:
                reply = ad.usb_query(cmd)
                return (reply or "").strip()
            ad.usb_command(cmd)
            return ""

    # -- plotting --------------------------------------------------------------

    def plot(self, doc: PathDocument, params: NativeParams, control: JobControl, emit: EmitFn) -> None:
        """Plot via ``draw_path``, one call per polyline.

        Each ``draw_path`` runs plotink's REAL planner over the whole path —
        acceleration with lookahead and cornering across all vertices, and
        the pen-up approach + pen down/up handled by the library. Never plot
        a polyline as per-segment ``lineto`` calls: interactive mode plans
        every command as an isolated move (full stop at each vertex), which
        on flattened-curve geometry (~1 mm segments) is hundreds of
        stop-start moves and serial round-trips — unusably slow, visibly
        choppy, and enough USB traffic to wedge the EBB's serial link.

        Consequence: pause/stop take effect at *path* boundaries (a path is
        planned and executed as one unit).
        """
        with self._lock:
            ad = self._require()
            self._apply(params)
            ox, oy = self._origin
            paths = list(doc.iter_paths())
            paths_total = len(paths)
            total_len = sum(p.length() for _, p in paths) or 1.0
            done_len = 0.0

            emit({"kind": "started", "paths_total": paths_total})
            try:
                for i, (layer, path) in enumerate(paths):
                    if control.stopped:
                        break
                    control.wait_if_paused()
                    pts = path.points
                    if len(pts) == 1:  # dot: draw_path needs >= 2 vertices
                        ad.moveto(ox + pts[0][0], oy + pts[0][1])
                        ad.pendown()
                        ad.penup()
                    else:
                        ad.draw_path([[ox + x, oy + y] for x, y in pts])
                    self._pos = (ox + pts[-1][0], oy + pts[-1][1])
                    done_len += path.length()
                    emit({
                        "kind": "progress",
                        "paths_done": i + 1,
                        "paths_total": paths_total,
                        "progress": done_len / total_len,
                        "position": list(self.position()),
                        "pen_down": False,
                    })
                ad.penup()
                if not control.stopped:
                    ad.moveto(ox, oy)
                    self._pos = (ox, oy)
            except Exception:
                # Serial died mid-plot (or the board faulted): don't keep a
                # zombie handle that makes the UI claim "connected" while
                # every command fails. Drop the connection so status reflects
                # reality and auto/manual reconnect starts clean.
                self._kill_connection()
                raise
            finally:
                if self._ad is not None:
                    try:
                        ad.penup()
                    except Exception:
                        pass
            emit({"kind": "stopped" if control.stopped else "finished",
                  "paths_total": paths_total})

    def _kill_connection(self) -> None:
        ad, self._ad = self._ad, None
        if ad is not None:
            try:
                ad.disconnect()
            except Exception:
                pass
