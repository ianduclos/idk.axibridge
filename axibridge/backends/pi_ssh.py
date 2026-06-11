"""Remote execution backend: the AxiDraw hangs off a Pi; jobs travel by ssh.

Deliberately thin, like the saxi backend: the Mac-side axibridge owns
composition and the single resolve; the Pi is a dumb axicli runtime. A plot
is: resolved PathDocument → SVG (mm units — axicli honours them) → scp to
the Pi → ``axicli <file>`` with motion flags. Pen toggle and jog ride the
same pipe as short ``axicli -m manual -M …`` invocations, dead-reckoned
locally (each axicli run treats the carriage's CURRENT position as home, so
relative walks compose; plot assumes the carriage starts at the home corner,
exactly like the native backend).

Sharp edges, advertised in capabilities.notes:

* Stop terminates the ssh session (remote gets HUP). axicli may not lift
  the pen on HUP, so a best-effort ``raise_pen`` is sent right after.
* No pause, no live position, no raw EBB — there is no channel for them.
* axicli's numeric options are argparse ``type=int`` (same family as
  pyaxidraw): flags are formatted as ints. See the native backend's
  serial-desync story for why this is not negotiable.

Requires: a working ``ssh <host>`` (key auth — BatchMode never prompts) and
the AxiDraw API installed on the Pi; ``axicli_path`` defaults to the
absolute venv path because non-interactive ssh has a minimal PATH.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
from typing import Any

from pydantic import BaseModel, Field

from ..model import PathDocument
from ..svg_io import doc_to_svg
from .base import BackendCapabilities, EmitFn, ExecutionBackend, JobControl

_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]


class PiSshParams(BaseModel):
    host: str = Field(default="idkpi", title="SSH host",
                      description="ssh alias or user@host (Tailscale name works)")
    axicli_path: str = Field(
        default="/home/ianduclos/axibridge/.venv/bin/axicli", title="axicli path",
        description="Absolute path on the Pi — non-interactive ssh has a minimal PATH")
    remote_tmp: str = Field(default="/tmp/axibridge-job.svg", title="Remote job file",
                            json_schema_extra={"hidden": True})
    speed_pendown: float = Field(default=25, ge=1, le=110, title="Pen-down speed %")
    speed_penup: float = Field(default=75, ge=1, le=110, title="Pen-up speed %")
    accel: float = Field(default=75, ge=1, le=100, title="Acceleration %")
    pen_pos_down: float = Field(default=40, ge=0, le=100, title="Pen height: down %")
    pen_pos_up: float = Field(default=60, ge=0, le=100, title="Pen height: up %")
    pen_rate_lower: float = Field(default=50, ge=1, le=100, title="Pen lower rate %")
    pen_rate_raise: float = Field(default=75, ge=1, le=100, title="Pen raise rate %")
    const_speed: bool = Field(default=False, title="Constant pen-down speed")


class PiSshBackend(ExecutionBackend):
    id = "pi_ssh"
    label = "AxiDraw via Pi (ssh)"
    description = "Send the job over Tailscale to a Pi running axicli. Thin by design."
    Params = PiSshParams

    def __init__(self) -> None:
        self._connected = False
        self._host = ""
        self._axicli = ""
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._pos = (0.0, 0.0)  # dead-reckoned from jogs, this session

    def available(self) -> tuple[bool, str]:
        if shutil.which("ssh") is None:
            return False, "no ssh client on this machine"
        return True, ""

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            requires_serial_port=False,
            jog=True,
            pen_control=True,
            set_origin=False,
            raw_ebb=False,
            pause_resume=False,
            live_position=False,
            progress_granularity="job",
            notes=(
                "Carriage must start at the home corner (each axicli run "
                "homes to its start position). Stop kills the ssh session "
                "and then best-effort raises the pen. Jog/pen are one ssh "
                "round-trip each (~1-2 s)."
            ),
        )

    # -- ssh plumbing --------------------------------------------------------

    def _flags(self, p: PiSshParams) -> list[str]:
        # axicli numerics are argparse type=int — format as ints, always
        return [
            "--speed_pendown", str(int(round(p.speed_pendown))),
            "--speed_penup", str(int(round(p.speed_penup))),
            "--accel", str(int(round(p.accel))),
            "--pen_pos_down", str(int(round(p.pen_pos_down))),
            "--pen_pos_up", str(int(round(p.pen_pos_up))),
            "--pen_rate_lower", str(int(round(p.pen_rate_lower))),
            "--pen_rate_raise", str(int(round(p.pen_rate_raise))),
            "--model", "1",
        ] + (["--const_speed"] if p.const_speed else [])

    def _ssh(self, args: list[str], timeout: float = 30) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["ssh", *_SSH_OPTS, self._host, *args],
            capture_output=True, text=True, timeout=timeout,
        )

    def _axicli_run(self, p: PiSshParams, args: list[str], timeout: float = 60) -> str:
        r = self._ssh([self._axicli or p.axicli_path, *args, *self._flags(p)], timeout)
        if r.returncode != 0:
            raise RuntimeError(f"axicli on {self._host}: {(r.stderr or r.stdout).strip()[:300]}")
        return r.stdout

    # -- lifecycle ------------------------------------------------------------

    def connect(self, port: str | None) -> dict[str, Any]:
        # manager.connect carries no params; read the stored ones (host,
        # axicli path) from the session. Lazy import: session ← machine ←
        # this module at load time, so a top-level import would cycle.
        from ..session import session  # noqa: PLC0415

        p = session.params_for(self.id)
        self._host = p.host
        self._axicli = p.axicli_path
        r = self._ssh([self._axicli, "--version"], timeout=15)
        if r.returncode != 0:
            raise RuntimeError(
                f"ssh {self._host}: {(r.stderr or r.stdout).strip()[:300] or 'unreachable'}"
            )
        version = (r.stdout or "").strip().splitlines()[0] if r.stdout else "axicli"
        port_ok = self._ssh(["test", "-c", "/dev/ttyACM0", "&&", "echo", "ok"]).stdout.strip()
        self._connected = True
        self._pos = (0.0, 0.0)
        return {"host": self._host, "axicli": version,
                "serial": "present" if port_ok == "ok" else "NOT FOUND (/dev/ttyACM0)"}

    def disconnect(self) -> None:
        self.deactivate()

    def deactivate(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None
            self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def _require(self) -> None:
        if not self._connected:
            raise RuntimeError("pi_ssh backend: not connected")

    # -- interactive ----------------------------------------------------------

    def pen(self, down: bool, params: PiSshParams) -> None:
        self._require()
        self._axicli_run(params, ["-m", "manual", "-M", "lower_pen" if down else "raise_pen"])

    def jog(self, dx: float, dy: float, params: PiSshParams) -> tuple[float, float]:
        self._require()
        # axicli walks are relative, distances in inches
        if dx:
            self._axicli_run(params, ["-m", "manual", "-M", "walk_x",
                                      "--walk_dist", f"{dx / 25.4:.4f}"])
        if dy:
            self._axicli_run(params, ["-m", "manual", "-M", "walk_y",
                                      "--walk_dist", f"{dy / 25.4:.4f}"])
        self._pos = (self._pos[0] + dx, self._pos[1] + dy)
        return self._pos

    def position(self) -> tuple[float, float]:
        return self._pos

    # -- plotting --------------------------------------------------------------

    def plot(self, doc: PathDocument, params: PiSshParams, control: JobControl, emit: EmitFn) -> None:
        self._require()
        self._host = params.host
        self._axicli = params.axicli_path
        svg = doc_to_svg(doc)
        with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
            f.write(svg)
            local = f.name
        emit({"kind": "started", "paths_total": sum(len(l.paths) for l in doc.layers)})
        scp = subprocess.run(["scp", "-q", *_SSH_OPTS, local, f"{self._host}:{params.remote_tmp}"],
                             capture_output=True, text=True)
        if scp.returncode != 0:
            raise RuntimeError(f"scp to {self._host}: {scp.stderr.strip()[:300]}")
        # -tt: force a tty so killing the local ssh HUPs the remote axicli
        cmd = ["ssh", "-tt", *_SSH_OPTS, self._host,
               self._axicli, params.remote_tmp, "--report_time", *self._flags(params)]
        with self._lock:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            proc = self._proc

        stopper = threading.Thread(target=self._watch_control, args=(control, proc), daemon=True)
        stopper.start()
        for line in proc.stdout:  # axicli is quiet; surface whatever it says
            text = line.strip()
            if text:
                emit({"kind": "message", "message": f"axicli: {text[:200]}"})
        code = proc.wait()
        with self._lock:
            self._proc = None
        if control.stopped:
            # HUP'd axicli may leave the pen down — best-effort lift
            try:
                self._axicli_run(params, ["-m", "manual", "-M", "raise_pen"])
            except Exception:
                pass
            emit({"kind": "stopped"})
        elif code != 0:
            raise RuntimeError(f"axicli exited with code {code}")
        else:
            emit({"kind": "finished"})

    def _watch_control(self, control: JobControl, proc: subprocess.Popen) -> None:
        """Bridge JobControl.stop() to ssh termination (remote gets HUP)."""
        import time

        while proc.poll() is None:
            if control.stopped:
                proc.terminate()
                return
            time.sleep(0.3)
