"""Is the server on a port the code in this repo? Answers the "I restarted it
and nothing changed" class (CLAUDE.md): stale processes, servers running
from another checkout, frontend builds older than their source, orphans.
macOS/Linux via lsof + ps; degrades to an `error` fact without them."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .targets import REPO


@dataclass
class Facts:
    pid: int | None
    command: str | None
    cwd: str | None
    started: float | None
    parent: str | None
    newest_backend: tuple[str, float] | None
    newest_frontend: tuple[str, float] | None
    dist_built: float | None
    error: str | None
    # every OTHER process listening on the same port, as (pid, cwd) — a stale
    # one on 127.0.0.1 silently shadows a fresh one on 0.0.0.0 (CLAUDE.md)
    others: list[tuple[int, str | None]] = field(default_factory=list)
    port: int | None = None


def _run(*args: str) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _newest(root: Path, pattern: str, rel: Path = REPO) -> tuple[str, float] | None:
    best: tuple[str, float] | None = None
    for p in root.glob(pattern):
        n = p.name
        if n.startswith(".") or n.endswith(("~", ".swp", ".tmp")):
            continue
        if p.is_file() and "__pycache__" not in p.parts:
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if best is None or m > best[1]:
                best = (str(p.relative_to(rel)), m)
    return best


def mcp_self_warning() -> tuple[str, float] | None:
    """(message, newest mtime) when this MCP process predates its own source."""
    import axibridge_mcp

    newest = _newest(REPO / "axibridge_mcp", "*.py")
    if newest is None or newest[1] <= axibridge_mcp.STARTED:
        return None
    return (f"WARNING — this MCP server is older than its source ({newest[0]} changed at "
            f"{_when(newest[1])}); reconnect it with /mcp to load the change", newest[1])


def gather(url: str) -> Facts:
    newest_backend = _newest(REPO / "axibridge", "**/*.py")
    newest_frontend = _newest(REPO / "axibridge" / "static", "**/*")
    dist = REPO / "axibridge" / "static_dist" / "index.html"
    dist_built = dist.stat().st_mtime if dist.exists() else None
    blank = dict(pid=None, command=None, cwd=None, started=None, parent=None,
                 newest_backend=newest_backend, newest_frontend=newest_frontend,
                 dist_built=dist_built)
    u = urlparse(url)
    if u.hostname not in ("127.0.0.1", "localhost", "::1"):
        return Facts(**blank, error=f"{u.hostname} is not this machine — only local servers can be inspected")
    if not shutil.which("lsof"):
        return Facts(**blank, error="lsof not available")
    port = u.port or 80
    raw = _run("lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t").split()
    if not raw:
        return Facts(**blank, error=f"nothing listening on port {port}")
    try:
        pids = list(dict.fromkeys(int(p) for p in raw))  # distinct, lsof order
    except ValueError:
        return Facts(**blank, error=f"could not read the listener on port {port}")
    pid = pids[0]
    command = _run("ps", "-p", str(pid), "-o", "command=")
    lstart = _run("ps", "-p", str(pid), "-o", "lstart=")
    try:
        started = time.mktime(time.strptime(lstart, "%a %b %d %H:%M:%S %Y"))
    except ValueError:
        started = None
    cwd = _cwd(pid)
    ppid = _run("ps", "-p", str(pid), "-o", "ppid=")
    parent = _run("ps", "-p", ppid, "-o", "command=") if ppid else None
    return Facts(pid=pid, command=command, cwd=cwd, started=started, parent=parent,
                 newest_backend=newest_backend, newest_frontend=newest_frontend,
                 dist_built=dist_built, error=None,
                 others=[(p, _cwd(p)) for p in pids[1:]], port=port)


def _cwd(pid: int) -> str | None:
    lines = _run("lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn").splitlines()
    return next((l[1:] for l in lines if l.startswith("n")), None)


def _when(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def assess(f: Facts, repo: Path) -> list[str]:
    if f.error:
        return [f.error]
    problems = []
    if f.others:
        listeners = [(f.pid, f.cwd), *f.others]
        port = f" on port {f.port}" if f.port else ""
        problems.append(f"{len(listeners)} processes listen{port}: " + ", ".join(
            f"pid {p} (cwd {c or '?'})" for p, c in listeners)
            + " — the browser may be talking to the wrong one")
    here = str(repo)
    is_here = f.cwd == here or any(
        x and (x == here or (here + os.sep) in x) for x in (f.cwd, f.command))
    if not is_here:
        where = f.cwd or f.command or ""
        problems.append(f"server runs from {where!r}, not this repo ({repo}) — "
                        "a leftover process; check it before trusting anything it serves")
    if f.started and f.newest_backend and f.newest_backend[1] > f.started:
        problems.append(f"backend source changed after the server started "
                        f"({f.newest_backend[0]} at {_when(f.newest_backend[1])}, "
                        f"server since {_when(f.started)}) — restart to run the current code")
    if f.dist_built and f.newest_frontend and f.newest_frontend[1] > f.dist_built:
        problems.append(f"frontend build is older than {f.newest_frontend[0]} — "
                        "run `npm run build` (the built bundle shadows source edits)")
    if f.parent and "axibridge_app.py" not in f.parent and f.parent.strip() in ("launchd", "/sbin/launchd", "init", "/sbin/init"):
        problems.append("orphan: no app shell owns this server, so closing the app won't stop it")
    return problems


def stale_warning(url: str) -> str | None:
    """One line for the first live call of a session, or None. Only the
    'serving the wrong code' problems — orphans and missing lsof stay quiet."""
    try:
        f = gather(url)
        if f.error:
            return None
        serious = [p for p in assess(f, REPO) if "orphan" not in p]
    except Exception:
        return None
    return ("WARNING — live server may be stale: " + "; ".join(serious)) if serious else None


def report(url: str) -> str:
    f = gather(url)
    lines = [f"url {url}"]
    if f.pid is not None:
        lines += [f"pid {f.pid}", f"command {f.command}", f"cwd {f.cwd}",
                  f"started {_when(f.started) if f.started else '?'}", f"parent {f.parent}"]
        for p, c in f.others:
            lines += [f"also listening: pid {p}", f"  command {_run('ps', '-p', str(p), '-o', 'command=')}",
                      f"  cwd {c}"]
    if f.newest_backend:
        lines.append(f"newest backend source {f.newest_backend[0]} at {_when(f.newest_backend[1])}")
    lines.append(f"frontend build {_when(f.dist_built) if f.dist_built else 'absent (serving source)'}")
    problems = assess(f, REPO)
    lines.append("problems: none" if not problems else "problems:\n- " + "\n- ".join(problems))
    return "\n".join(lines)
