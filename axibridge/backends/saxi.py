"""saxi execution backend — deliberately thin: SVG in, plot, progress, stop.

Integration note (verified against the saxi source, June 2026): the saxi
*server's* ``POST /plot`` accepts a pre-computed motion **Plan** in saxi's
internal JSON format — planning happens in its browser UI, so the stock
server cannot accept an SVG. Mimicking that format would mean reimplementing
saxi's planner, which is exactly what we don't do. The supported SVG-in entry
point is the CLI: ``saxi plot file.svg --paper-size WxHmm``, which plans and
plots in one shot and prints progress to stdout. So this backend shells out
to the saxi CLI as a subprocess.

Consequences, all by design and advertised via capabilities:

* saxi opens the serial port itself — the manager guarantees the native
  backend has released it first (and vice versa).
* No jog / pen toggle / raw EBB / pause — the CLI has no channel for them.
  Stop = terminate the subprocess (saxi lifts the pen on SIGINT).
* Progress is coarse (planning phases + plotting), not per-path.
* Motion parameters are saxi's planner vocabulary (velocity in mm/s,
  acceleration in mm/s², cornering factor) — intentionally different fields
  from the native backend; the UI just renders this model's schema.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path as FsPath
from typing import Any

from pydantic import BaseModel, Field

from ..model import PathDocument
from ..svg_io import doc_to_svg
from .base import BackendCapabilities, EmitFn, ExecutionBackend, JobControl


class SaxiParams(BaseModel):
    paper_width: float = Field(default=210, ge=10, le=1000, title="Paper width (mm)")
    paper_height: float = Field(default=148, ge=10, le=1000, title="Paper height (mm)")
    landscape: bool = Field(default=False, title="Landscape")
    margin: float = Field(default=10, ge=0, le=100, title="Margin (mm)")
    pen_up_height: float = Field(default=50, ge=0, le=100, title="Pen-up height %")
    pen_down_height: float = Field(default=60, ge=0, le=100, title="Pen-down height %")
    pen_down_velocity: float = Field(default=200, ge=1, le=500, title="Pen-down max velocity (mm/s)")
    pen_up_velocity: float = Field(default=400, ge=1, le=600, title="Pen-up max velocity (mm/s)")
    pen_down_acceleration: float = Field(default=2000, ge=10, le=10000, title="Pen-down acceleration (mm/s²)")
    pen_down_cornering: float = Field(default=0.127, ge=0.001, le=2.0, title="Cornering factor (mm)")
    sort_paths: bool = Field(default=True, title="Let saxi sort paths",
                             description="Disable if draw order is part of the piece")
    fit_page: bool = Field(default=False, title="Let saxi fit the drawing to the page",
                           description="Usually off — place layers on the canvas so the preview matches")
    saxi_command: str = Field(default="saxi", title="saxi executable",
                              description="Command or absolute path to the saxi CLI")
    device: str = Field(default="", title="Device override",
                        description="Serial device path; empty = saxi auto-detects")


class SaxiBackend(ExecutionBackend):
    id = "saxi"
    label = "saxi (CLI)"
    description = "Hand the SVG to saxi's planner for clean, well-planned plots. Thin by design."
    Params = SaxiParams

    def __init__(self) -> None:
        self._connected = False
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._saxi_cmd = "saxi"

    def available(self) -> tuple[bool, str]:
        # Name the environment in the diagnostic (same lesson as pyaxidraw):
        # "works in my shell" usually means a different PATH than the server's.
        if shutil.which(self._saxi_cmd) is None:
            return False, (
                f"saxi CLI ({self._saxi_cmd!r}) not found on this server "
                f"process's PATH ({os.environ.get('PATH', '')[:120]}…). "
                "Install with: npm install -g saxi — or set an absolute path "
                "in the backend's saxi_command parameter."
            )
        return True, ""

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            requires_serial_port=False,  # saxi auto-detects; override via params
            jog=False,
            pen_control=False,
            set_origin=False,
            raw_ebb=False,
            pause_resume=False,
            live_position=False,
            progress_granularity="coarse",
            notes=(
                "saxi plans and owns the port while plotting. No trapdoor, no jog, "
                "no pause — switch to the native backend for interactive control."
            ),
        )

    # -- lifecycle -----------------------------------------------------------

    def connect(self, port: str | None) -> dict[str, Any]:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        # No persistent connection: saxi opens the port per plot.
        self._connected = True
        return {"port": port or "saxi auto-detect", "firmware": "n/a (saxi-managed)"}

    def disconnect(self) -> None:
        self._connected = False
        self._terminate()

    def deactivate(self) -> None:
        self.disconnect()

    @property
    def connected(self) -> bool:
        return self._connected

    def _terminate(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                self._proc.terminate()  # saxi lifts the pen on termination
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None

    # -- plotting --------------------------------------------------------------

    def _build_cmd(self, svg_path: str, p: SaxiParams) -> list[str]:
        size = f"{p.paper_width}x{p.paper_height}mm"
        cmd = [
            p.saxi_command or "saxi", "plot", svg_path,
            "--paper-size", size,
            "--margin", str(p.margin),  # bare number: saxi's yargs parses "10mm" as NaN
            "--pen-up-height", str(p.pen_up_height),
            "--pen-down-height", str(p.pen_down_height),
            "--pen-down-max-velocity", str(p.pen_down_velocity),
            "--pen-up-max-velocity", str(p.pen_up_velocity),
            "--pen-down-acceleration", str(p.pen_down_acceleration),
            "--pen-down-cornering-factor", str(p.pen_down_cornering),
        ]
        cmd.append("--landscape" if p.landscape else "--portrait")
        if not p.sort_paths:
            cmd.append("--no-sort-paths")
        if not p.fit_page:
            cmd.append("--no-fit-page")
        if p.device:
            cmd += ["--device", p.device]
        return cmd

    def plot(self, doc: PathDocument, params: SaxiParams, control: JobControl, emit: EmitFn) -> None:
        self._saxi_cmd = params.saxi_command or "saxi"
        svg = doc_to_svg(doc)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".svg", prefix="axibridge_", delete=False
        ) as f:
            f.write(svg)
            svg_path = f.name
        try:
            cmd = self._build_cmd(svg_path, params)
            emit({"kind": "started", "message": " ".join(cmd)})
            with self._lock:
                self._proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )
            proc = self._proc
            stopper = threading.Thread(
                target=self._watch_control, args=(control,), daemon=True
            )
            stopper.start()
            for line in proc.stdout:  # streams saxi's phase messages as progress
                line = line.strip()
                if line:
                    emit({"kind": "message", "message": line})
            rc = proc.wait()
            if control.stopped:
                emit({"kind": "stopped"})
            elif rc == 0:
                emit({"kind": "finished"})
            else:
                emit({"kind": "error", "message": f"saxi exited with code {rc}"})
        finally:
            with self._lock:
                self._proc = None
            FsPath(svg_path).unlink(missing_ok=True)

    def _watch_control(self, control: JobControl) -> None:
        """Bridge JobControl.stop() to subprocess termination."""
        while True:
            with self._lock:
                proc = self._proc
            if proc is None or proc.poll() is not None:
                return
            if control.stopped:
                self._terminate()
                return
            control._stop.wait(timeout=0.2)
