"""MCP server for axibridge — see docs/MCP.md.

Talks to an axibridge server over HTTP only; never imports the app's live
state, so it cannot become a second geometry path."""

import time as _time

#: when this MCP process loaded its code. diagnose.mcp_self_warning compares
#: it with the source files, because Claude Code keeps the MCP process alive
#: across edits to axibridge_mcp/ until someone reconnects it with /mcp.
STARTED = _time.time()
