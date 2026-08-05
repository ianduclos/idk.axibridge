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

import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any

from pydantic import BaseModel, Field

from ..model import PathDocument
from ..svg_io import doc_to_svg
from .base import BackendCapabilities, EmitFn, ExecutionBackend, JobControl

_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]


class PiSshParams(BaseModel):
    host: str = Field(default="raspberrypi", title="SSH host",
                      description="ssh alias or user@host (a Tailscale name works)")
    axicli_path: str = Field(
        default="/home/pi/axibridge/.venv/bin/axicli", title="axicli path",
        description="Absolute path on the Pi — non-interactive ssh has a minimal PATH")
    remote_tmp: str = Field(default="/tmp/axibridge-job.svg", title="Remote job file",
                            json_schema_extra={"hidden": True})
    notify_env: str = Field(
        default="/etc/axibridge/notify.env", title="Notify env file",
        description="Optional file on the Pi holding NTFY_URL=\"...\"; a finished-plot "
                    "ping is sent there. Skipped silently if absent or unreadable.")
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
        self._job: tuple[str, str] | None = None  # (remote pid, exit-marker path)
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
                "homes to its start position). Jobs run DETACHED on the Pi: "
                "they survive the Mac sleeping or dropping off the network, "
                "and completion pings the Pi's ntfy topic. Stop kills the "
                "detached job over ssh and best-effort raises the pen. "
                "Jog/pen are one ssh round-trip each (~1-2 s)."
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
        # No local process to release: jobs run detached on the Pi (the
        # manager refuses backend switches mid-job; Stop kills via ssh).
        with self._lock:
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
        """Detached execution: the job is launched on the Pi under setsid and
        survives the Mac sleeping, roaming or dropping ssh entirely — this
        thread only POLLS for the exit marker. Completion optionally pings an
        ntfy topic (NTFY_URL, read from the `notify_env` file on the Pi if it
        is readable), so "start a plot and walk away" actually works. Stop
        kills the detached process group over a fresh ssh and raises the pen."""
        self._require()
        self._host = params.host
        self._axicli = params.axicli_path
        svg = doc_to_svg(doc)
        with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
            f.write(svg)
            local = f.name
        scp = subprocess.run(["scp", "-q", *_SSH_OPTS, local, f"{self._host}:{params.remote_tmp}"],
                             capture_output=True, text=True)
        if scp.returncode != 0:
            raise RuntimeError(f"scp to {self._host}: {scp.stderr.strip()[:300]}")

        log, exit_f = f"{params.remote_tmp}.log", f"{params.remote_tmp}.exit"
        axicli_cmd = " ".join(
            shlex.quote(a) for a in
            [self._axicli, params.remote_tmp, "--report_time", *self._flags(params)]
        )
        inner = (
            f"{axicli_cmd} > {shlex.quote(log)} 2>&1; ec=$?; "
            f"echo $ec > {shlex.quote(exit_f)}; "
            # Optional finished-plot ping. Reads NTFY_URL from notify_env if that
            # file is readable — directly, else via sudo -n, which succeeds only
            # where it's already been granted. Any failure is swallowed; the plot
            # result never depends on it.
            f'url=$( (cat {shlex.quote(params.notify_env)} 2>/dev/null '
            f'|| sudo -n cat {shlex.quote(params.notify_env)} 2>/dev/null) '
            "| sed -n 's/^NTFY_URL=\"\\(.*\\)\"/\\1/p'); "
            '[ -n "$url" ] && curl -s -m 10 -d "axibridge: plot finished (exit $ec)" "$url" '
            ">/dev/null 2>&1; true"
        )
        launch = (
            f"rm -f {shlex.quote(exit_f)}; "
            f"setsid nohup sh -c {shlex.quote(inner)} >/dev/null 2>&1 < /dev/null & echo $!"
        )
        r = self._ssh([launch], timeout=20)
        if r.returncode != 0 or not r.stdout.strip().isdigit():
            raise RuntimeError(f"could not launch remote job: {(r.stderr or r.stdout).strip()[:300]}")
        pid = r.stdout.strip()
        with self._lock:
            self._job = (pid, exit_f)
        emit({"kind": "started", "paths_total": sum(len(l.paths) for l in doc.layers)})
        emit({"kind": "message",
              "message": f"detached on {self._host} (pid {pid}) — survives Mac sleep; "
                         "ntfy pings on completion"})

        misses = 0
        try:
            while True:
                if control.stopped:
                    self._kill_remote(pid)
                    try:  # the killed job may leave the pen down
                        self._axicli_run(params, ["-m", "manual", "-M", "raise_pen"])
                    except Exception:
                        pass
                    emit({"kind": "stopped"})
                    return
                time.sleep(3.0)
                try:
                    poll = self._ssh([f"cat {shlex.quote(exit_f)} 2>/dev/null || echo RUNNING"],
                                     timeout=15)
                except subprocess.TimeoutExpired:
                    poll = None
                if poll is None or poll.returncode != 0:
                    misses += 1  # network blip / Mac just woke: the job doesn't care, keep polling
                    if misses in (5, 100):
                        emit({"kind": "message",
                              "message": f"lost contact with {self._host} — job continues there; retrying"})
                    continue
                misses = 0
                out = poll.stdout.strip()
                if out == "RUNNING" or not out:
                    continue
                code = int(out) if out.lstrip("-").isdigit() else 1
                tail = self._ssh([f"tail -n 5 {shlex.quote(log)} 2>/dev/null"], timeout=15)
                for line in (tail.stdout or "").strip().splitlines():
                    if line.strip():
                        emit({"kind": "message", "message": f"axicli: {line.strip()[:200]}"})
                if code != 0:
                    raise RuntimeError(f"axicli exited with code {code} (see {log} on {self._host})")
                emit({"kind": "finished"})
                return
        finally:
            with self._lock:
                self._job = None

    def _kill_remote(self, pid: str) -> None:
        """Kill the detached job's whole process group (setsid leader)."""
        try:
            self._ssh([f"kill -TERM -- -{pid} 2>/dev/null; sleep 1; "
                       f"kill -KILL -- -{pid} 2>/dev/null; true"], timeout=15)
        except Exception:
            pass
