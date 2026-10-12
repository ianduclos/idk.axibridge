# axibridge MCP server — design

Date: 2026-10-12 · Status: approved in conversation, awaiting spec review

## Intent

An MCP server that lets an agent (Claude first, any MCP client after) work
*with* axibridge. Ian's stated requirements: it must be **flexible**, serving
both co-creation (working on an image together: hands, eyes, bridge, body)
and **development** of axibridge itself. All four development uses are in
scope: verifying code changes against a running app, tuning generators and
effects, dogfooding the UI as a user, and diagnosing the live app.

Success looks like:

- Ian has the app open; the agent adds or edits a layer; Ian's canvas shows
  it without a reload, and Ian's ⌘Z undoes it.
- The agent can look at the resolved canvas and at the UI as images.
- The agent can tune a generator in a contact-sheet loop without touching the
  project.
- The agent can tell, from one call, that port 2942 is serving stale code.
- Nothing moves the plotter without Ian approving that specific call.

Non-goals: no new UI in the app, no node editor, no change to the resolve
pipeline, no test-runner tool (the agent already has a shell), no Pi
deployment (the Pi stays backend-only).

## Decisions (made with Ian, 2026-10-12)

1. **Targets:** both, chosen explicitly per call. `live` attaches to the
   running app; `sandbox` is a server the MCP owns.
2. **Physical motion:** motion tools exist, are never allow-listed (Claude
   Code prompts every call), and only accept the `live` target.
3. **Tool surface:** a curated core plus one escape hatch (`call_api`) that
   refuses motion endpoints.
4. **Live sync:** part of this project. The app announces project changes so
   an open window follows external edits.
5. **Placement:** a separate stdio process, in this repo, launched from the
   project `.mcp.json` with the pinned venv.

## Architecture

### 1. `axibridge_mcp/` (new top-level package, sibling of `axibridge/`)

Talks to targets over HTTP only. It never imports `axibridge.session` or any
other module holding live state, so it cannot become a second geometry path.
Pure helpers (e.g. `model.Path` for typing) may be imported.

| Module | Responsibility |
|---|---|
| `targets.py` | Target registry. `live` = `http://127.0.0.1:2942` (overridable by `AXIBRIDGE_MCP_LIVE_URL`, used by tests); attach-only, never started or killed. `sandbox` = `python -m axibridge --host 127.0.0.1 --port <free>` spawned with a temp `AXIBRIDGE_CONFIG_DIR` and temp project dir, killed on MCP exit (atexit + signal). Optional seed: copy of a named project. |
| `client.py` | HTTP wrapper. Converts failures to readable tool errors (status + server `detail`). |
| `render.py` | Rasterises `/api/compose/resolved` geometry to PNG with Pillow: pen colours from the pen library, bed and guide outline, optional travel moves, fixed long-edge size. No browser dependency. Also builds contact sheets (grid of renders + captions). |
| `ui.py` | Headless Chromium (Playwright) against a target's UI: open a tab, optionally run a short list of clicks/keystrokes, screenshot. Disabled with a clear message when Playwright or its browser is missing. Follows CLAUDE.md's Playwright rules (`domcontentloaded`, function-scoped `sync_playwright`). |
| `tools_look.py`, `tools_modules.py`, `tools_compose.py`, `tools_machine.py`, `tools_dev.py`, `tools_api.py` | The tool families below. |
| `server.py` | MCP wiring (Python `mcp` SDK, stdio transport). Entry point: `python -m axibridge_mcp`. |

### 2. Live sync (app change)

- `Session` gains an integer `revision`, incremented in `_checkpoint()`
  (including the coalesce branch, since the state still changes), in
  `undo()`, `redo()`, `restore_history()`, and wherever `self.project` is
  replaced (load/new/recovery restore).
- `_checkpoint()` runs *before* a mutation, so the event is not emitted
  there. An HTTP middleware reads the revision before and after each
  non-GET request and, if it moved, emits
  `{"type": "project", "rev": n, "origin": <client id or null>}` on the
  existing event bus. This guarantees subscribers fetch post-mutation state.
- The frontend generates a per-tab client id and sends it as
  `X-Axb-Client` on every request (`static/js/api.js`). `main.js` handles
  `project` events: ignore its own origin; otherwise refetch `/api/project`
  and re-render. If a drag or latched live edit is in progress, defer the
  refetch until release.
- Two windows on one server stop drifting apart as a side effect.

### 3. Wiring

- `pyproject.toml`: new optional extra `mcp = ["mcp>=X.Y"]`, with X.Y set to the current stable release
  version checked at install time, not from memory. Installed in the Mac
  venv only.
- Project `.mcp.json`: an `axibridge` stdio server running
  `.venv/bin/python -m axibridge_mcp`.

## Tools

Every tool takes `target: "live" | "sandbox"` (default `live`) unless noted.

**Look**
1. `state`: compact summary of the project (name, revision), layers (id,
   name, kind, pen, visible, path count) and machine (backend, connected,
   job state). Far smaller than `/api/state` (~320 KB).
2. `see`: PNG of the resolved canvas. Options: `layer_ids`, `t`, `travel`,
   `size`.
3. `see_ui`: PNG screenshot of the UI, optional `tab` and `steps`
   (click/type/key/wait). Dogfooding only.

**Modules and tuning**
4. `modules`: generators, effects and transforms with one-line descriptions;
   optional `kind` and `query` filters.
5. `module_schema`: one module's full parameter JSON Schema.
6. `try_generator`: one or more param sets → contact-sheet PNG via
   `/api/generators/preview`. Never mutates the project.
7. `try_effects`: one or more effect chains on an existing layer →
   contact sheet via `/api/layers/{id}/effects/preview`. Never mutates.

**Compose**
8. `add_layer`: generator, params, optional name and pen.
9. `edit_layer`: params, transform, pen, visibility, effects.
10. `delete_layers`, `reorder_layers`.
11. `undo`, `redo` (with count).
12. `project`: open, new, list, recovery status. `save_project` is a
    separate tool because it overwrites disk.

**Machine** (motion tools: live target only, never allow-listed)
13. `estimate`: time and travel for the plot target (`/api/plan`), plus the
    project revision it was computed at.
14. `plot`: takes the plot target (`all` or a layer id) of `/api/plot/start`'s
    default route, plus the `revision` returned by `estimate`; refuses if the
    project has changed since, so what gets plotted is what was previewed.
    `master_t`, sheet and staged-tray routes are out of scope for v1 (use the
    app's ▶), because `/api/plan` cannot estimate a scrubbed `t`.
    `pen` (up/down), `jog`, `go_home`: prompted motion.
15. `stop` (with `return_home`) and `pause`: not motion-gated, since stopping
    is the safe direction.

**Dev**
16. `logs`: `/api/logs` with level and text filters, newest last.
17. `diagnose`: listener PID on the target port, its command path and start
    time, parent (app shell or orphan), newest backend/frontend source
    mtimes, `static_dist` mtime; flags "source changed after the server
    started" (catches uncommitted edits, not just commits), "frontend build
    older than its source" and "path is not this repo".
18. `sandbox`: start, stop, reset, optional seed project.

**Escape hatch**
19. `call_api`: any method/path/body against a target. Refuses
    `/api/machine/{pen,jog,goto,origin,raw,block}`, `/api/plot/{start,resume}`,
    `/api/calibration/*` (teststroke and holder marks move the pen), and
    `/api/server/restart` on `live`.

## Error handling

- Live app not reachable: "the live app isn't running — open
  AxiBridge.app"; the MCP never starts the live server.
- Sandbox crash: error includes the last 20 lines of its log.
- API errors: status + server `detail` as text, never a traceback.
- Stale live server: the first tool call per MCP session runs `diagnose`
  and prefixes a warning to that call's result when the server is older than
  the working tree's source or runs from another path.
- Stale MCP process: every tool warns once per change when `axibridge_mcp/`
  source is newer than the running MCP (reconnect with `/mcp`).

## Freshness (added 2026-10-12)

The app is still in active development, so drift is caught by tests in the
normal suite: every endpoint the MCP calls must exist in the app's OpenAPI;
every non-GET route whose path looks like motion must be refused by
`call_api` or explicitly reviewed; `docs/MCP.md` must name every tool.
Modules and schemas are read live, so new generators/effects need no MCP
change.

## Testing

All hardware-free and part of the normal suite; MCP tests skip when `mcp`
isn't importable (the Pi).

- **Live sync (backend):** revision moves for each mutation kind (edit,
  coalesced edit, undo, redo, load, new, recovery restore); exactly one
  event per changing request; origin echoed; GETs and no-op requests emit
  nothing.
- **Live sync (UI acceptance):** a layer added from outside the page appears
  in it; a page mid-drag is not refetched until release. Asserts what the
  user sees, per the acceptance-test rule.
- **MCP tools:** an in-process MCP client drives the tools against a temp
  simulator server, motion tools included (via `AXIBRIDGE_MCP_LIVE_URL`).
  Never touches port 2942.
- **Escape hatch:** blocklist unit test.
- **Render:** PNG size and non-blank checks; contact-sheet layout.
- **Plot guard:** `plot` with a stale revision is refused.

## Docs

`docs/MCP.md` (setup, targets, tool reference, safety rules), a row in
CLAUDE.md's "Where things live", and a `CHANGES.md` entry: the new `project`
SSE event and `X-Axb-Client` header are boundary changes other consumers may
see.

## Related but separate

- **Pi Stop ⌂ lies:** on the `pi_ssh` backend, Stop kills axicli and raises
  the pen, but return-home is a `goto(0,0)` from dead-reckoned position
  (still 0,0), so nothing moves while the UI reports "carriage returned
  home". Fix candidate: `axicli -m manual -M walk_home` (present in axicli
  3.9.6 on idkpi), and it needs a hardware check. Separate bounded task, not part of
  this spec.
