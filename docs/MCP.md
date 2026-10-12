# axibridge MCP server

An MCP server (`axibridge_mcp/`, stdio) that lets an agent work with
axibridge: see the canvas and the UI, compose layers, tune generators and
effects with contact sheets, read logs, diagnose stale servers, and — with
Ian's approval on every call — move the plotter. Design:
`docs/superpowers/specs/2026-10-12-mcp-server-design.md`.

## Setup (Mac bench)

    .venv/bin/python -m pip install -e '.[mcp]'
    .venv/bin/python -m playwright install chromium   # only for see_ui

`.mcp.json` registers it as `axibridge`; restart Claude Code (or `/mcp`) to
load it. The Pi never installs the extra; the MCP tests skip there.

## Targets

Every tool takes `target`:

- `live` (default) — Ian's running app on `127.0.0.1:2942` (override with
  `AXIBRIDGE_MCP_LIVE_URL`). Attach-only: the MCP never starts or kills it.
  Edits appear in Ian's window (live sync) and his ⌘Z undoes them.
- `sandbox` — a private server the MCP spawns on a free port with temp
  config and a temp projects folder, started on first use and killed when
  the MCP exits. `sandbox(action="start", seed_project=...)` opens a COPY of
  a saved project; the seed name must be a plain folder name (no `/`, no
  `..`). Use it for dev checks, experiments and `see_ui` clicking.

## Safety

- `plot`, `pen`, `jog`, `go_home` move the machine. They refuse the sandbox,
  and they must never be added to an allow-list: Claude Code asks Ian every
  time. `plot` needs the `revision` from `estimate` and refuses if the
  project changed since — show Ian `see` + `estimate` first.
- `plot`: `estimate` reads the revision before and after timing and refuses
  if it moved during the estimate. Its suggested call names `plot_target`.
- `jog` is a pen-up move.
- `go_home` goes to the design origin (0, 0): the physical home corner only
  when there is no custom origin. The `pi_ssh` backend has no goto.
- `stop` and `pause` are always safe.
- `call_api` refuses machine motion, calibration, non-GET `/api/limits` on
  live ("changes the machine's soft limits") and (on live) server restart,
  after normalising the path (percent-encoding, dot segments, slashes).
  Paths are percent-decoded before sending, so endpoints that need encoded
  characters are not reachable through `call_api`.
- The HTTP client refuses any path containing `..`, `?`, `#`, `\`, `%` or
  whitespace. Ids are never trusted.
- `project(new|open)` on a dirty project fails with "unsaved work" unless
  given `recovery_action`; on live prefer "recover", never "discard" unless
  Ian said so.
- Known caveat: on the `pi_ssh` backend, `stop(return_home=True)` does not
  actually move the carriage home (dead-reckoned position never changes);
  tracked separately.

### Known residuals

1. A millisecond window between `plot`'s revision check and
   `/api/plot/start`. Closing it needs a server-side expected revision.
2. `edit_rev` doesn't cover pen-library, calibration or backend-param
   changes.
3. `/api/connect` and `/api/backend/select` stay reachable via `call_api`.
   They only raise the pen.
4. `stop`/`pause` on the sandbox start it needlessly.
5. The `pi_ssh` "returned home" caveat above.

## Tools

| Family | Tools |
|---|---|
| Look | `state`, `see`, `see_ui` |
| Modules & tuning | `modules`, `module_schema`, `try_generator`, `try_effects` |
| Compose | `add_layer`, `edit_layer`, `delete_layers`, `reorder_layers`, `undo`, `redo`, `project`, `save_project` |
| Machine | `estimate`, `plot`*, `pen`*, `jog`*, `go_home`*, `stop`, `pause` |
| Dev | `logs`, `diagnose`, `sandbox` |
| Escape hatch | `call_api` |

\* moves the machine; always prompted.

## Keeping it fresh

The app is still moving, so drift is caught by tests, not by memory:

- `tests/test_mcp_freshness.py` (normal suite, no server) fails when a tool
  calls an endpoint the app no longer has, when a new motion-shaped endpoint
  is reachable through `call_api`, when a tool is missing from this page, or
  when a tool has no description.
- Modules, params and schemas are read live, so new generators and effects
  work through `modules` / `try_generator` / `add_layer` with no MCP change.
- Every tool warns once when the MCP process is older than its own source
  (reconnect with `/mcp`), and the first live call warns when port 2942 is
  serving older code than the working tree.
- Tool behaviour against a real server is covered by the `tests/test_mcp_*`
  modules, so a request/response shape change fails there.

## Live sync (app side)

`Session.edit_rev` counts project changes for the process lifetime. After any
mutating request that moved it, the server emits
`{"type": "project", "rev", "origin"}` on `/api/events`; `origin` is the
request's `X-Axb-Client` header (each browser tab sends its own id; the MCP
sends `mcp`). Tabs refetch on changes they didn't make, deferred while a
pointer is held or their own mutation is in flight.

## Stale-server warning

The first live call of an MCP session runs `diagnose`; if port 2942 is
serving code older than the working tree, from another checkout, or with a
frontend build older than its source, that call's result starts with a
WARNING line.
