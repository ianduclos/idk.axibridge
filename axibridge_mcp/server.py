"""axibridge MCP server: see, compose, tune, diagnose — and, with Ian's
per-call approval, plot. Entry point: `python -m axibridge_mcp` (stdio)."""

from __future__ import annotations

import atexit
import functools
import signal
import sys

from mcp.server.mcpserver import MCPServer

from . import tools_api, tools_compose, tools_dev, tools_look, tools_machine, tools_modules, tools_synthesis
from .targets import Targets

INSTRUCTIONS = """\
axibridge is Ian's pen-plotter compositor (AxiDraw V3). Coordinates are
millimetres in the machine frame (x right <= 300, y down <= 218).
Targets: 'live' is Ian's open app — he sees every edit, and his cmd-Z undoes
yours. 'sandbox' is a private server for experiments and dev checks.
Start with `state`, look with `see`, tune with `try_generator`/`try_effects`.
Motion tools (plot, pen, jog, go_home) are live-only and Ian approves each
call: show him `see` + `estimate` first. `stop` is always safe.
"""

MODULES = (tools_look, tools_modules, tools_compose, tools_synthesis, tools_machine, tools_dev, tools_api)


def make_tool_decorator(srv: MCPServer, targets: Targets):
    """Register fn as an unstructured tool. Its result gets the one-time
    stale-live-server warning (see Targets.client) prefixed first and, once per
    source change, a warning that this MCP process itself is out of date.
    Tools must be sync functions: an async tool would return an un-awaited
    coroutine through the wrapper."""
    from .diagnose import mcp_self_warning

    warned_for = {"mtime": 0.0}

    def tool(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            out = fn(*args, **kwargs)
            warnings = [w for w in (targets.take_warning(),) if w]
            self_stale = mcp_self_warning()
            if self_stale and self_stale[1] > warned_for["mtime"]:
                warned_for["mtime"] = self_stale[1]
                warnings.append(self_stale[0])
            if not warnings:
                return out
            return [*warnings, *out] if isinstance(out, list) else [*warnings, out]

        srv.tool(structured_output=False)(wrapper)
        return fn
    return tool


def build_server(targets: Targets | None = None) -> MCPServer:
    targets = targets or Targets()
    srv = MCPServer("axibridge", instructions=INSTRUCTIONS)
    tool = make_tool_decorator(srv, targets)
    for module in MODULES:
        module.register(tool, targets)
    return srv


def main() -> None:
    from .diagnose import stale_warning
    targets = Targets(stale_check=stale_warning)
    atexit.register(targets.close)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(0))  # sys.exit runs atexit → sandbox stops
    build_server(targets).run("stdio")
