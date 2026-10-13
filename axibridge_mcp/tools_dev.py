"""For developing axibridge itself: logs, staleness, the sandbox."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from . import diagnose as diag
from .targets import TargetName, Targets

LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}


def register(tool, targets: Targets) -> None:
    @tool
    def logs(target: TargetName = "live",
             level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO",
             contains: str | None = None,
             limit: Annotated[int, Field(ge=1, le=500)] = 50) -> str:
        """The server's log ring (last ~500 records), oldest first, filtered by
        minimum level and an optional case-insensitive substring."""
        entries = targets.client(target).get("/api/logs")["entries"]
        floor = LEVELS[level]
        q = (contains or "").lower()
        keep = [e for e in entries
                if LEVELS.get(e.get("level", "INFO"), 20) >= floor
                and (not q or q in f"{e.get('logger', '')} {e.get('msg', '')}".lower())]
        if not keep:
            return "no matching log entries"
        return "\n".join(
            f"{time.strftime('%H:%M:%S', time.localtime(e['ts']))} {e['level']:<7} "
            f"{e.get('logger', '')}: {e.get('msg', '')}" for e in keep[-limit:])

    @tool
    def diagnose(target: TargetName = "live") -> str:
        """Who is serving this target and is it the current code? Reports pid,
        command, cwd, start time, parent, newest source edits vs the server's
        start, frontend build age, and lists problems."""
        url = targets.live_url if target == "live" else targets.client("sandbox").base_url
        return diag.report(url)

    @tool
    def sandbox(action: Literal["status", "start", "stop", "reset"],
                seed_project: str | None = None) -> str:
        """The private server: start (optionally seeded with a COPY of a saved
        project from Ian's projects folder), stop, reset (stop + start), status.
        Any tool with target="sandbox" also starts it on demand."""
        sb = targets.sandbox
        if action == "status":
            return f"running at {sb.url} (dir {sb.dir})" if sb.running else "not running"
        if action == "stop":
            sb.stop()
            return "sandbox stopped"
        if action == "reset":
            sb.stop()
        root = None
        if seed_project:
            try:
                root = Path(targets.client("live").get("/api/settings")["projects_root"]).expanduser()
            except (ToolError, KeyError):
                root = None  # live app down: fall back to ~/AxidrawProjects
        url = sb.start(seed=seed_project, seed_root=root)
        return f"sandbox running at {url}" + (f" with a copy of {seed_project}" if seed_project else "")
