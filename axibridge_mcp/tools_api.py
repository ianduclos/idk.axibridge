"""call_api: the long tail of the HTTP API, minus anything that moves the
machine. Paths are normalised BEFORE the check and the normalised path is
what gets sent, so no spelling reaches a blocked route."""

from __future__ import annotations

import json
import posixpath
import re
from typing import Annotated, Any, Literal
from urllib.parse import unquote

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .render import png
from .targets import TargetName, Targets

_MOTION = [
    (re.compile(r"^/api/machine/(pen|jog|goto|origin|raw|block)$"), "moves the machine"),
    (re.compile(r"^/api/plot/(start|resume)$"), "starts motion"),
    (re.compile(r"^/api/calibration(/.*)?$"), "calibration moves the pen"),
]
_LIVE_ONLY = [(re.compile(r"^/api/server/restart$"), "restarts Ian's app")]


def normalize(path: str) -> str:
    # split by hand: urlsplit reads "//api/x" as host "api", hiding the route
    raw = path.split("#", 1)[0].split("?", 1)[0]
    for _ in range(3):  # repeated decoding defeats %25-style double encoding
        decoded = unquote(raw)
        if decoded == raw:
            break
        raw = decoded
    p = posixpath.normpath("/" + raw.lstrip("/"))
    return p.rstrip("/") or "/"


def check_allowed(method: str, path: str, target: str) -> None:
    p = normalize(path)
    if not p.startswith("/api/"):
        raise ToolError(f"refused: {p!r} is not an /api/ path")
    rules = _MOTION + (_LIVE_ONLY if target == "live" else [])
    for rx, why in rules:
        if rx.match(p):
            raise ToolError(f"refused: {method.upper()} {p} {why} — use the dedicated tool "
                            "(plot/pen/jog/go_home), which Ian approves per call")


def register(tool, targets: Targets) -> None:
    @tool
    def call_api(method: Literal["GET", "POST", "PUT", "PATCH", "DELETE",
                                 "get", "post", "put", "patch", "delete"],
                 path: str, body: dict[str, Any] | list | None = None,
                 query: dict[str, Any] | None = None,
                 target: TargetName = "live",
                 max_chars: Annotated[int, Field(ge=200, le=200_000)] = 20_000) -> list | str:
        """Any axibridge endpoint not covered by a dedicated tool (FastAPI docs
        at <target>/docs list them). Machine motion, calibration and (on live)
        server restart are refused. JSON comes back as text, PNGs as images."""
        m = method.upper()
        check_allowed(m, path, target)
        r = targets.client(target).request(m, normalize(path),
                                           body=None if m == "GET" else body, params=query)
        ctype = r.headers.get("content-type", "")
        if ctype.startswith("image/png"):
            return [f"{r.status_code} {ctype}", png(r.content)]
        if "json" in ctype:
            out = json.dumps(r.json(), indent=1)
        else:
            out = r.text
        if len(out) > max_chars:
            out = out[:max_chars] + f"\n… truncated ({len(out)} chars total)"
        return f"{r.status_code}\n{out}"
