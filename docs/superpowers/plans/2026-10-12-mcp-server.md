# axibridge MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An MCP server that lets an agent see, compose, tune, diagnose and (with Ian's per-call approval) plot through axibridge, plus a live-sync change so Ian's open window follows edits made from outside it.

**Architecture:** A separate stdio process, `axibridge_mcp/` (sibling of `axibridge/`), talks to an axibridge server over HTTP only. Tools pick a target per call: `live` (Ian's app on 2942, attach-only) or `sandbox` (a server the MCP spawns with temp config and projects). The app gains a monotonic `Session.edit_rev`, an HTTP middleware that announces `{type:"project", rev, origin}` on the existing SSE bus after any request that changed it, and a frontend handler that refetches on changes it didn't cause, deferred while a pointer is held or its own mutation is in flight.

**Tech Stack:** Python 3.13 (pinned `.venv`), FastAPI, `mcp` 2.3 SDK (`mcp.server.mcpserver.MCPServer`, NOT v1 `FastMCP`), httpx, Pillow 12, Playwright (sync API, Mac only), vanilla ES modules + Vite build.

**Spec:** `docs/superpowers/specs/2026-10-12-mcp-server-design.md`. Read it before starting any task.

## Global Constraints

- Interpreter: always `.venv/bin/python`. `.venv/bin/pip` has a stale shebang (points at the pre-move `01_Projects` path) — use `.venv/bin/python -m pip`.
- MCP SDK is **2.x**: `from mcp.server.mcpserver import MCPServer, Image`; errors via `from mcp.server.mcpserver.exceptions import ToolError`; in-process test client `from mcp.client.client import Client` used as `async with Client(server) as c: await c.call_tool(name, args)`. `mcp.server.fastmcp` raises `ModuleNotFoundError` in 2.x.
- Every tool is registered with `structured_output=False` through the `tool` decorator from `server.make_tool_decorator` (Task 3) — never `srv.tool()` directly — so the one-time stale-server warning can be prefixed to any return type.
- Every tool takes `target: Literal["live", "sandbox"] = "live"` unless the task says otherwise.
- `axibridge_mcp` never imports `axibridge.session`, `axibridge.api`, `axibridge.machine` or anything holding live state. HTTP only.
- Bound every numeric tool parameter with `Annotated[..., Field(ge=..., le=...)]` (repo rule: unbounded values reach an open-loop machine).
- Motion tools (`plot`, `pen`, `jog`, `go_home`) call `targets.live_only(target)` first. They are never added to any allow-list.
- The escape hatch refuses `/api/machine/{pen,jog,goto,origin,raw,block}`, `/api/plot/{start,resume}`, `/api/calibration/*` on every target, and `/api/server/restart` on `live`.
- Tests never touch port 2942, `~/.axibridge`, or `~/AxidrawProjects`. Test servers get a temp `AXIBRIDGE_CONFIG_DIR` **and** a temp `projects_root` (the default projects root is Ian's real folder even with a temp config dir).
- MCP test modules start with `pytest.importorskip("mcp")` (via the harness) so the Pi, which never installs the extra, skips them.
- UI acceptance tests assert what the user sees, never how it is built (repo rule). Use `wait_until="domcontentloaded"` and counting `wait_for_function`.
- Frontend source is `axibridge/static/**`; after JS edits run `npm run build` (or the stale `static_dist/` shadows them) and `npm run typecheck`.
- Undo discipline is unchanged: no new mutation path. The MCP only calls existing endpoints.
- Palette for rendered PNGs is Flexoki, hexes copied from `~/_SecondBrain/02_Areas/_Coding/twistermapper/web/flexoki.css`: paper `#FFFCF0`, black `#100F0F`, 100 `#E6E4D9`, 300 `#B7B5AC`, 600 `#6F6E69`, red-400 `#D14D41`.
- **Freshness (the app is still moving):** every `/api/...` path the MCP calls appears in `axibridge_mcp/*.py` as a string literal or an f-string whose only `{…}` parts are path parameters (`f"/api/layers/{layer_id}"`), never computed from variables (`f"/api/{direction}"`), so the drift test in Task 11 can see it. Generators, effects and their params are never hard-coded in tools; they're read live from `/api/state`.
- Commits: conventional style, one per task at minimum, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.

## Review Focus

1. **Plain-http LAN access:** the app is also opened over `http://<host>:2942` from other machines, a non-secure context where `crypto.randomUUID` does not exist; the per-tab client id must still be generated and live sync must still work. Pinned in Task 2 (`test_client_id_does_not_need_a_secure_context`).
2. **Escape-hatch bypass by path spelling:** `%6Aog`, `/api/machine/jog/`, `//api/machine/jog`, `/api/x/../machine/jog` and mixed method casing must all be refused like `/api/machine/jog`. Pinned in Task 8.
3. **Dirty live project on new/open:** an agent switching projects must never silently discard Ian's unsaved work; with no `recovery_action` the server's 409 "unsaved work" text must come back verbatim. Pinned in Task 5 (`test_open_refuses_to_discard_unsaved_work`).
4. **Edits between estimate and plot:** if Ian (or anyone) edits the project after the agent showed an estimate, `plot` must refuse, so the machine never draws something nobody previewed. Pinned in Task 6 (`test_plot_refuses_after_an_edit`).
5. **Sandbox leak when the MCP process exits:** Claude Code ending the stdio session must take the sandbox server down with it. Pinned in Task 10 (`test_stdio_exit_stops_the_sandbox`).

---

### Task 1: Live sync — backend revision and `project` event

**Files:**
- Modify: `axibridge/session.py` (Session `__init__` near line 253; `_checkpoint` ~313; `undo` ~405; `redo` ~421)
- Modify: `axibridge/recovery_state.py` (`begin_project` ~144)
- Modify: `axibridge/api.py` (`_project_payload` ~108)
- Modify: `axibridge/app.py` (`create_app` ~110)
- Test: `tests/test_live_sync.py` (create)

**Interfaces:**
- Produces: `session.edit_rev: int` (monotonic for the process lifetime, never reset); `session._bump_edit_rev() -> None`; `GET /api/project` (and every `_project_payload()` response) gains `"edit_rev": int`; SSE event `{"type": "project", "rev": int, "origin": str | None, "ts": float}`; request header `X-Axb-Client` (echoed as `origin`).
- Note: `/api/project` already has a `"revision"` key — that is the **recovery** revision (resets per project, fingerprint-observed). Do not reuse or rename it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_live_sync.py`:

```python
"""Live sync: every project change bumps Session.edit_rev and is announced
once on the event bus as {type: "project", rev, origin} — after the request
finished, so a subscriber that refetches sees the post-mutation state."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.events import bus

REPO = Path(__file__).resolve().parent.parent
POLY = {"module": "polygon", "params": {"sides": 5, "radius": 20}}


@pytest.fixture()
def api(monkeypatch):
    seen: list[dict] = []
    with TestClient(create_app()) as c:
        monkeypatch.setattr(bus, "emit", lambda ev: seen.append(ev))
        yield c, seen


def project_events(seen):
    return [e for e in seen if e.get("type") == "project"]


def emits(seen, fn) -> list[dict]:
    """Run fn and return the project events it caused."""
    before = len(project_events(seen))
    fn()
    return project_events(seen)[before:]


def test_edit_rev_is_in_the_project_payload_and_moves_on_edit(api):
    c, _ = api
    r0 = c.get("/api/project").json()["edit_rev"]
    c.post("/api/layers/generate", json=POLY)
    assert c.get("/api/project").json()["edit_rev"] > r0


def test_one_event_per_changing_request_carrying_origin_and_rev(api):
    c, seen = api
    ev = emits(seen, lambda: c.post("/api/layers/generate", json=POLY,
                                    headers={"X-Axb-Client": "tab-1"}))
    assert len(ev) == 1
    assert ev[0]["origin"] == "tab-1"
    assert ev[0]["rev"] == c.get("/api/project").json()["edit_rev"]


def test_origin_is_null_without_the_header(api):
    c, seen = api
    ev = emits(seen, lambda: c.post("/api/layers/generate", json=POLY))
    assert len(ev) == 1 and ev[0]["origin"] is None


def test_reads_and_refused_requests_announce_nothing(api):
    c, seen = api
    assert emits(seen, lambda: c.get("/api/project")) == []
    assert emits(seen, lambda: c.get("/api/compose/resolved")) == []
    # nothing to undo → 409, no state change
    assert emits(seen, lambda: c.post("/api/undo")) == []
    # unknown layer → 404 before any checkpoint
    assert emits(seen, lambda: c.patch("/api/layers/nope", json={"name": "x"})) == []


def test_every_kind_of_change_is_announced(api):
    c, seen = api
    lid = c.post("/api/layers/generate", json=POLY).json()["id"]
    assert len(emits(seen, lambda: c.patch(f"/api/layers/{lid}", json={"name": "renamed"}))) == 1
    assert len(emits(seen, lambda: c.post(f"/api/layers/{lid}/regenerate",
                                          json={"params": {"sides": 6}, "coalesce": True}))) == 1
    # a coalesced run still changes state, so it is still announced
    assert len(emits(seen, lambda: c.post(f"/api/layers/{lid}/regenerate",
                                          json={"params": {"sides": 7}, "coalesce": True}))) == 1
    assert len(emits(seen, lambda: c.post("/api/undo"))) == 1
    assert len(emits(seen, lambda: c.post("/api/redo"))) == 1
    assert len(emits(seen, lambda: c.post("/api/project/save", json={"name": "sync-test"}))) == 1
    assert len(emits(seen, lambda: c.post("/api/project/new",
                                          json={"recovery_action": "discard"}))) == 1
    assert len(emits(seen, lambda: c.post("/api/project/load",
                                          json={"name": "sync-test",
                                                "recovery_action": "discard"}))) == 1


def test_edit_rev_never_goes_backwards_across_projects(api):
    c, _ = api
    c.post("/api/layers/generate", json=POLY)
    before = c.get("/api/project").json()["edit_rev"]
    c.post("/api/project/new", json={"recovery_action": "discard"})
    assert c.get("/api/project").json()["edit_rev"] > before


def test_client_id_does_not_need_a_secure_context():
    # Review Focus 1: the app is opened over plain http from the LAN, where
    # crypto.randomUUID is undefined. The tab id must not depend on it.
    src = (REPO / "axibridge" / "static" / "js" / "api.js").read_text()
    assert "X-Axb-Client" in src
    assert "randomUUID" not in src
```

(`test_client_id_does_not_need_a_secure_context` fails until Task 2; that is expected — leave it failing at the end of this task and note it in the commit body.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_live_sync.py -q`
Expected: FAIL — `KeyError: 'edit_rev'` and empty event lists.

- [ ] **Step 3: Add the counter to `Session`**

In `axibridge/session.py`, in `Session.__init__`, directly after `self.project = Project()` (line ~253):

```python
        #: Monotonic count of project changes for the whole process lifetime
        #: (never reset — not even by New/Load). The live-sync middleware
        #: (app.announce_project_edits) compares it before/after each request.
        #: Distinct from the recovery revision, which resets per project.
        self.edit_rev = 0
```

Add a method next to `_checkpoint` (in the `# -- undo` section):

```python
    def _bump_edit_rev(self) -> None:
        self.edit_rev += 1
```

At the very top of `_checkpoint`'s body (before `self._redo.clear()`, so the coalesce branch counts too):

```python
        self._bump_edit_rev()
```

In `undo()`, after `self._restore(self._history.pop())` and before `return True`:

```python
            self._bump_edit_rev()
```

In `redo()`, after `self._restore(self._redo.pop())` and before `return True`:

```python
            self._bump_edit_rev()
```

- [ ] **Step 4: Bump on project replacement**

In `axibridge/recovery_state.py`, inside `begin_project`'s `with self._lock:` block, as its first line:

```python
            self._bump_edit_rev()  # New/Load/recovery restore replace the whole project
```

(`begin_project` runs from `init_recovery_state()` inside `Session.__init__`, after `edit_rev` exists, and from `api._replace_project` on every new/load/restore.)

- [ ] **Step 5: Expose it in the payload**

In `axibridge/api.py`, `_project_payload`:

```python
def _project_payload() -> dict[str, Any]:
    with session._lock:
        return {**session.project.model_dump(exclude={"staging": {"__all__": {"snapshot"}}}),
                **session.recovery_status(), "edit_rev": session.edit_rev}
```

- [ ] **Step 6: Add the middleware**

In `axibridge/app.py`, add `from .events import bus` to the imports, and inside `create_app()` directly after the existing `observe_persistent_edits` middleware:

```python
    @app.middleware("http")
    async def announce_project_edits(request, call_next):
        """Live sync: one {type: "project"} event per request that changed the
        project, emitted AFTER the handler returned so subscribers refetch the
        new state (Session._checkpoint runs before the mutation, so it cannot
        announce). Concurrent requests may each see the other's bump; that only
        costs a duplicate refetch, and every change still gets an event that
        carries its own request's origin."""
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await call_next(request)
        from .session import session
        before = session.edit_rev
        response = await call_next(request)
        if session.edit_rev != before:
            bus.emit({"type": "project", "rev": session.edit_rev,
                      "origin": request.headers.get("x-axb-client")})
        return response
```

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_live_sync.py -q`
Expected: all PASS except `test_client_id_does_not_need_a_secure_context` (Task 2).

If `test_every_kind_of_change_is_announced` fails on `save`: `save_project` checkpoints only when the name changes; the fixture's project is unnamed, so naming it must announce. If `load` announces 0, check that `_replace_project` still calls `session.begin_project()`.

- [ ] **Step 8: Run the neighbouring suites**

Run: `.venv/bin/python -m pytest tests/test_app.py tests/test_events_shutdown.py tests/test_app_shell.py -q`
Expected: PASS (no regressions from the payload key or middleware).

- [ ] **Step 9: Commit**

```bash
git add axibridge/session.py axibridge/recovery_state.py axibridge/api.py axibridge/app.py tests/test_live_sync.py
git commit -m "feat(sync): announce project changes as a project event with edit_rev

The secure-context client-id test lands with the frontend in the next commit.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Live sync — the UI follows external edits

**Files:**
- Modify: `axibridge/static/js/api.js` (whole `req` function and `upload`)
- Modify: `axibridge/static/js/main.js` (import line 13; `onEvent` ~1273; new live-sync block after `onEvent`)
- Check: `axibridge/static/js/plot.js:2048` (raw `fetch` — GET only, leave it)
- Test: `tests/test_live_sync_ui.py` (create)

**Interfaces:**
- Consumes: Task 1's SSE event and `X-Axb-Client` header.
- Produces (api.js exports): `CLIENT_ID: string`, `mutationsPending(): number`, `onMutationsIdle(fn): void`.

- [ ] **Step 1: Write the failing acceptance tests**

Create `tests/test_live_sync_ui.py`:

```python
"""Live sync, as the user sees it: a change made outside the window (the MCP,
another window, a script) shows up without a reload — but never yanks the
canvas out from under a gesture in progress."""

from test_acceptance_ui import _post, add_layer, frontend_mode, rows, server, ui  # noqa: F401

POLY = {"sides": 5, "radius": 20}
ROWS_ARE = "n => document.querySelectorAll('#layer-list .layer-row').length === n"


def test_a_layer_added_elsewhere_appears_without_reload(ui):
    assert rows(ui) == 0
    add_layer(ui, "polygon", POLY)
    ui.wait_for_function(ROWS_ARE, arg=1, timeout=10_000)
    assert not ui.errors


def test_an_undo_made_elsewhere_shows_up(ui):
    add_layer(ui, "polygon", POLY)
    ui.wait_for_function(ROWS_ARE, arg=1, timeout=10_000)
    _post(f"{ui.base}/api/undo")
    ui.wait_for_function(ROWS_ARE, arg=0, timeout=10_000)
    assert not ui.errors


def test_the_refresh_waits_while_the_pointer_is_held(ui):
    box = ui.locator("#layer-list").bounding_box()
    ui.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] - 4)
    ui.mouse.down()
    add_layer(ui, "polygon", POLY)
    ui.wait_for_timeout(1200)
    assert rows(ui) == 0, "refetched mid-gesture"
    ui.mouse.up()
    ui.wait_for_function(ROWS_ARE, arg=1, timeout=10_000)
    assert not ui.errors
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_live_sync_ui.py -q`
Expected: the first two FAIL on timeout (no row appears without a reload). The third may pass vacuously; that's fine.

- [ ] **Step 3: Tag requests and count in-flight mutations in `api.js`**

Replace the top of `axibridge/static/js/api.js` (the `req` function) with:

```js
// Thin API client + SSE subscription. All server errors are normalised to
// thrown Error(detail) so panels can toast them uniformly.

// Per-tab identity for live sync: the server echoes it as a project event's
// `origin`, so a tab can skip changes it made itself. Deliberately NOT
// crypto.randomUUID — that only exists in secure contexts, and the app is
// also opened over plain http from other machines on the LAN.
export const CLIENT_ID = `tab-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

// Mutating requests this tab has in flight. Live sync waits for them to
// settle before refetching, so an external refresh never interleaves with
// this tab's own edit sequence.
let mutationsInFlight = 0;
const idleListeners = new Set();
export const mutationsPending = () => mutationsInFlight;
export function onMutationsIdle(fn) { idleListeners.add(fn); }
function settle(mutating) {
  if (mutating && --mutationsInFlight === 0) idleListeners.forEach((fn) => fn());
}

async function req(method, url, body, requestOpts = {}) {
  const opts = { method, headers: { "X-Axb-Client": CLIENT_ID }, signal: requestOpts.signal };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const mutating = method !== "GET";
  if (mutating) mutationsInFlight++;
  try {
    const res = await fetch(url, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch {}
      const payload = typeof detail === "object" && detail ? detail : null;
      const error = new Error(payload?.message || detail);
      error.code = payload?.code;
      error.status = res.status;
      throw error;
    }
    const ct = res.headers.get("content-type") || "";
    return ct.includes("json") ? res.json() : res.text();
  } finally {
    settle(mutating);
  }
}
```

And replace `upload` in the `api` object with:

```js
  upload: async (url, formData) => {
    mutationsInFlight++;
    try {
      const res = await fetch(url, { method: "POST", body: formData,
                                     headers: { "X-Axb-Client": CLIENT_ID } });
      if (!res.ok) {
        let detail = res.statusText;
        try { detail = (await res.json()).detail || detail; } catch {}
        throw new Error(detail);
      }
      return res.json();
    } finally {
      settle(true);
    }
  },
```

- [ ] **Step 4: Handle `project` events in `main.js`**

Change line 13 to:

```js
import { api, subscribe, CLIENT_ID, mutationsPending, onMutationsIdle } from "./api.js";
```

In `onEvent`, add a branch before the closing brace:

```js
  } else if (ev.type === "project") {
    onProjectEvent(ev);
  }
```

Directly after the `onEvent` function, add:

```js
// ---- live sync: follow edits made outside this tab --------------------------
// The server announces every project change as {type: "project", rev, origin}
// (app.announce_project_edits). This tab's own edits already refresh through
// their action; anything else (the MCP, another window, an undo from
// elsewhere) refetches here — but never mid-gesture: not while a pointer is
// held (slider drag, pen anchor, marquee) and not while this tab still has a
// mutation in flight. Release/settle re-runs the flush.
let externalChangePending = false;
let pointerHeld = false;
let externalTimer = null;

function onProjectEvent(ev) {
  if (ev.origin === CLIENT_ID || !S.state) return;
  externalChangePending = true;
  flushExternalChange();
}

function flushExternalChange() {
  if (!externalChangePending || pointerHeld || mutationsPending() > 0) return;
  clearTimeout(externalTimer);
  externalTimer = setTimeout(async () => {
    if (pointerHeld || mutationsPending() > 0) return;
    externalChangePending = false;
    try {
      // the same sequence historyStep() uses after an undo
      await actions.refreshProject();
      actions.setSelection(S.selection.filter((id) => S.state.project.layers.some((l) => l.id === id)));
      await actions.refreshResolved();
      renderLayerDetail();
    } catch (err) {
      oops(err);
    }
  }, 120);
}

addEventListener("pointerdown", () => { pointerHeld = true; }, true);
for (const type of ["pointerup", "pointercancel"]) {
  addEventListener(type, () => { pointerHeld = false; flushExternalChange(); }, true);
}
onMutationsIdle(flushExternalChange);
```

- [ ] **Step 5: Confirm the raw fetch in plot.js is read-only**

Run: `sed -n 2040,2055p axibridge/static/js/plot.js`
Expected: a GET (no `method:` option). If it is a mutation, add `headers: { "X-Axb-Client": CLIENT_ID }` and import `CLIENT_ID` from `./api.js`.

- [ ] **Step 6: Build, typecheck, run the tests**

Run: `npm run build && npm run typecheck && .venv/bin/python -m pytest tests/test_live_sync.py tests/test_live_sync_ui.py -q`
Expected: build and typecheck clean; all tests PASS, including `test_client_id_does_not_need_a_secure_context`.

- [ ] **Step 7: Run the full acceptance module (live sync must not break existing flows)**

Run: `.venv/bin/python -m pytest tests/test_acceptance_ui.py -q`
Expected: PASS. If a test that seeds via the API and then reloads now flakes, it's because the row appeared before the reload; the reload is still correct, so look for a console error instead (e.g. a refresh racing `reload_app`'s aborted fetches, which `reload_app` already filters).

- [ ] **Step 8: Commit**

```bash
git add axibridge/static/js/api.js axibridge/static/js/main.js tests/test_live_sync_ui.py
git commit -m "feat(sync): the UI refetches on project changes it didn't make

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: MCP foundation — package, client, targets, sandbox, `state`

**Files:**
- Modify: `pyproject.toml` (`[project.optional-dependencies]`)
- Create: `axibridge_mcp/__init__.py`, `axibridge_mcp/__main__.py`, `axibridge_mcp/client.py`, `axibridge_mcp/targets.py`, `axibridge_mcp/server.py`, `axibridge_mcp/tools_look.py`
- Create: `tests/_mcp_harness.py`, `tests/test_mcp_foundation.py`

**Interfaces:**
- Produces:
  - `client.ApiClient(base_url: str, label: str, unreachable_hint: Callable[[], str], timeout: float = 300.0)` with `.request(method, path, body=None, params=None) -> httpx.Response`, `.json(method, path, body=None, params=None) -> Any`, `.get(path, **params)`, `.post(path, body=None)` (sends `{}` when body is None), `.put(path, body)`, `.patch(path, body)`, `.delete(path)`, `.alive() -> bool`, `.close()`, `.base_url: str`, `.label: str`. Every failure raises `ToolError` with a readable sentence.
  - `targets.TargetName = Literal["live", "sandbox"]`; `targets.REPO: Path`; `targets.Sandbox` with `.start(timeout: float = 45.0) -> str` (url; Task 7 adds `seed`/`seed_root`), `.stop()`, `.running: bool`, `.url: str | None`, `.dir: Path | None`, `.log_tail(n=20) -> str`; `targets.Targets(live_url: str | None = None, stale_check: Callable[[str], str | None] | None = None)` with `.client(target) -> ApiClient`, `.live_only(target) -> ApiClient`, `.take_warning() -> str | None`, `.sandbox: Sandbox`, `.live_url: str`, `.close()`.
  - `server.build_server(targets: Targets | None = None) -> MCPServer`; `server.make_tool_decorator(srv, targets)` returning `tool(fn) -> fn`; `server.main()`.
  - Each `tools_*.py` exposes `register(tool, targets) -> None`.
  - Harness: fixtures `axb` (module-scoped base URL), `targets`, `srv`; helpers `call(srv, name, args=None)`, `text(result) -> str`, `images(result) -> list[bytes]`, `http(base) -> httpx.Client`.

- [ ] **Step 1: Install the SDK**

Edit `pyproject.toml`, adding under `[project.optional-dependencies]` (after `text = [...]`):

```toml
# The agent-facing MCP server (axibridge_mcp/, docs/MCP.md). Mac bench only:
# the Pi never installs it, and its tests skip without it.
mcp = ["mcp>=2.3,<3", "httpx>=0.27"]
```

Then create the package directory with a placeholder `__init__.py` (Step 4 fills it) and reinstall editable so the static editable finder maps the new top-level package:

```bash
mkdir -p axibridge_mcp && touch axibridge_mcp/__init__.py
.venv/bin/python -m pip install -e '.[mcp]'
cd /tmp && /Users/ianduclos/_SecondBrain/02_Areas/_Coding/idk.axibridge/.venv/bin/python -c "import axibridge_mcp, mcp.server.mcpserver; print('ok')"; cd -
```

Expected: `ok`. The install must not upgrade existing packages; if pip proposes upgrading fastapi/starlette/pydantic, stop and report instead of accepting.

- [ ] **Step 2: Write the harness**

Create `tests/_mcp_harness.py`:

```python
"""Shared harness for the MCP tests: a real axibridge on a temp port (never
2942, never Ian's config or projects folder) and an in-process MCP client.

Skips the importing module when the `mcp` extra isn't installed (the Pi)."""

from __future__ import annotations

import base64
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="mcp extra not installed (backend-only machine)")

import anyio  # noqa: E402
import httpx  # noqa: E402
from mcp.client.client import Client  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server() -> tuple[subprocess.Popen, str]:
    root = Path(tempfile.mkdtemp(prefix="axibridge-mcp-test-"))
    port = free_port()
    env = {**os.environ, "AXIBRIDGE_CONFIG_DIR": str(root / "config"),
           "AXIBRIDGE_NO_AUTOCONNECT": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "axibridge.app:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("test server exited during startup")
        try:
            httpx.get(base + "/api/project", timeout=1.0)
            break
        except httpx.HTTPError:
            time.sleep(0.15)
    else:
        proc.kill()
        raise RuntimeError("test server never answered")
    # the default projects_root is Ian's real ~/AxidrawProjects even with a
    # temp config dir — point it somewhere disposable before anything saves
    httpx.put(base + "/api/settings", json={"projects_root": str(root / "projects")},
              timeout=10).raise_for_status()
    return proc, base


def stop_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def http(base: str) -> httpx.Client:
    return httpx.Client(base_url=base, timeout=60)


@pytest.fixture(scope="module")
def axb():
    proc, base = start_server()
    yield base
    stop_server(proc)


@pytest.fixture()
def targets(axb):
    from axibridge_mcp.targets import Targets

    with http(axb) as h:
        h.post("/api/project/new", json={"recovery_action": "discard"}).raise_for_status()
    t = Targets(live_url=axb)
    yield t
    t.close()


@pytest.fixture()
def srv(targets):
    from axibridge_mcp.server import build_server

    return build_server(targets)


def call(srv, name: str, args: dict | None = None):
    async def go():
        async with Client(srv) as c:
            return await c.call_tool(name, args or {})
    return anyio.run(go)


def text(result) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


def images(result) -> list[bytes]:
    return [base64.b64decode(c.data) for c in result.content if c.type == "image"]
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_mcp_foundation.py`:

```python
import json
import time

import httpx

from _mcp_harness import axb, call, free_port, http, srv, targets, text  # noqa: F401

POLY = {"module": "polygon", "params": {"sides": 5, "radius": 20}}


def test_state_summarises_project_layers_and_machine(srv, axb):
    with http(axb) as h:
        lid = h.post("/api/layers/generate", json=POLY).json()["id"]
    r = call(srv, "state")
    assert not r.is_error, text(r)
    data = json.loads(text(r))
    assert data["target"] == "live"
    assert isinstance(data["project"]["edit_rev"], int)
    [layer] = data["layers"]
    assert layer["id"] == lid
    assert layer["source"] == "generator:polygon"
    assert layer["paths"] == 1
    assert data["machine"]["job_state"] == "idle"


def test_state_says_plainly_when_the_live_app_is_down():
    from axibridge_mcp.server import build_server
    from axibridge_mcp.targets import Targets

    t = Targets(live_url=f"http://127.0.0.1:{free_port()}")
    try:
        r = call(build_server(t), "state")
    finally:
        t.close()
    assert r.is_error
    assert "isn't running" in text(r) and "AxiBridge.app" in text(r)


def test_unknown_targets_are_rejected(srv):
    r = call(srv, "state", {"target": "elsewhere"})
    assert r.is_error


def test_the_sandbox_starts_on_demand_and_is_isolated(srv, targets, axb):
    with http(axb) as h:
        h.post("/api/layers/generate", json=POLY)
    r = call(srv, "state", {"target": "sandbox"})
    assert not r.is_error, text(r)
    assert json.loads(text(r))["layers"] == []
    url = targets.sandbox.url
    assert url and url != axb
    targets.close()
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            httpx.get(url + "/api/project", timeout=0.5)
            time.sleep(0.2)
        except httpx.HTTPError:
            break
    else:
        raise AssertionError("sandbox still answering after close()")


def test_api_errors_come_back_as_readable_text(targets):
    from mcp.server.mcpserver.exceptions import ToolError
    import pytest

    with pytest.raises(ToolError, match=r"live: PATCH /api/layers/nope → 404"):
        targets.client("live").patch("/api/layers/nope", {"name": "x"})
```

- [ ] **Step 4: Write the package**

`axibridge_mcp/__init__.py`:

```python
"""MCP server for axibridge — see docs/MCP.md.

Talks to an axibridge server over HTTP only; never imports the app's live
state, so it cannot become a second geometry path."""
```

`axibridge_mcp/__main__.py`:

```python
from .server import main

main()
```

`axibridge_mcp/client.py`:

```python
"""HTTP client for one axibridge server. Every failure becomes a ToolError
carrying a sentence a person can act on — never a traceback."""

from __future__ import annotations

from typing import Any, Callable

import httpx
from mcp.server.mcpserver.exceptions import ToolError

#: echoed by the server as the project event's `origin` (live sync)
CLIENT_ID = "mcp"


class ApiClient:
    def __init__(self, base_url: str, label: str, unreachable_hint: Callable[[], str],
                 timeout: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.label = label
        self._hint = unreachable_hint
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout,
                                  headers={"X-Axb-Client": CLIENT_ID})

    def request(self, method: str, path: str, body: Any = None,
                params: dict[str, Any] | None = None) -> httpx.Response:
        try:
            r = self._http.request(method, path, json=body, params=params)
        except httpx.ConnectError:
            raise ToolError(self._hint()) from None
        except httpx.TimeoutException:
            raise ToolError(f"{self.label}: {method} {path} timed out") from None
        if r.status_code >= 400:
            raise ToolError(f"{self.label}: {method} {path} → {r.status_code}: {_detail(r)}")
        return r

    def json(self, method: str, path: str, body: Any = None,
             params: dict[str, Any] | None = None) -> Any:
        r = self.request(method, path, body, params)
        return r.json() if r.content else None

    def get(self, path: str, **params: Any) -> Any:
        return self.json("GET", path, params={k: v for k, v in params.items() if v is not None} or None)

    def post(self, path: str, body: Any = None) -> Any:
        return self.json("POST", path, {} if body is None else body)

    def put(self, path: str, body: Any) -> Any:
        return self.json("PUT", path, body)

    def patch(self, path: str, body: Any) -> Any:
        return self.json("PATCH", path, body)

    def delete(self, path: str) -> Any:
        return self.json("DELETE", path)

    def alive(self) -> bool:
        try:
            self._http.get("/api/project", timeout=2.0)
            return True
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        self._http.close()


def _detail(r: httpx.Response) -> str:
    try:
        d = r.json().get("detail", r.text)
    except (ValueError, AttributeError):
        return r.text[:500]
    if isinstance(d, dict):
        return str(d.get("message") or d)[:500]
    if isinstance(d, list):
        return "; ".join(str(x.get("msg", x)) if isinstance(x, dict) else str(x) for x in d)[:500]
    return str(d)[:500]
```

`axibridge_mcp/targets.py`:

```python
"""Where tools point. `live` is Ian's running app — attach-only, never
started or killed here. `sandbox` is a server this process owns: temp port,
temp config, temp projects folder, killed on close()."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Literal

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from .client import ApiClient

REPO = Path(__file__).resolve().parent.parent
PYTHON = REPO / ".venv" / "bin" / "python"
DEFAULT_LIVE_URL = "http://127.0.0.1:2942"
TargetName = Literal["live", "sandbox"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Sandbox:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.dir: Path | None = None
        self.url: str | None = None
        self._log = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, timeout: float = 45.0) -> str:
        if self.running:
            return self.url  # type: ignore[return-value]
        self.stop()  # clear a dead one
        self.dir = Path(tempfile.mkdtemp(prefix="axibridge-mcp-sandbox-"))
        port = _free_port()
        env = {**os.environ, "AXIBRIDGE_CONFIG_DIR": str(self.dir / "config"),
               "AXIBRIDGE_NO_AUTOCONNECT": "1"}
        python = str(PYTHON if PYTHON.exists() else sys.executable)
        self._log = open(self.dir / "server.log", "wb")
        self.proc = subprocess.Popen(
            [python, "-m", "axibridge", "--host", "127.0.0.1", "--port", str(port)],
            cwd=REPO, env=env, stdin=subprocess.DEVNULL, stdout=self._log,
            stderr=subprocess.STDOUT)
        self.url = f"http://127.0.0.1:{port}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                tail = self.log_tail()
                self.stop()
                raise ToolError(f"sandbox server exited during startup:\n{tail}")
            try:
                httpx.get(self.url + "/api/project", timeout=1.0)
                break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            self.stop()
            raise ToolError(f"sandbox server did not answer within {timeout:.0f} s")
        httpx.put(self.url + "/api/settings",
                  json={"projects_root": str(self.dir / "projects")},
                  timeout=10).raise_for_status()
        return self.url

    def log_tail(self, n: int = 20) -> str:
        if not self.dir or not (self.dir / "server.log").exists():
            return "(no sandbox log)"
        lines = (self.dir / "server.log").read_text(errors="replace").splitlines()
        return "\n".join(lines[-n:]) or "(sandbox log empty)"

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if self._log is not None:
            self._log.close()
            self._log = None
        if self.dir is not None:
            shutil.rmtree(self.dir, ignore_errors=True)
            self.dir = None
        self.url = None


class Targets:
    def __init__(self, live_url: str | None = None,
                 stale_check: Callable[[str], str | None] | None = None) -> None:
        self.live_url = (live_url or os.environ.get("AXIBRIDGE_MCP_LIVE_URL")
                         or DEFAULT_LIVE_URL).rstrip("/")
        self.sandbox = Sandbox()
        self._stale_check = stale_check
        self._live = ApiClient(
            self.live_url, "live",
            lambda: f"the live app isn't running at {self.live_url} — open AxiBridge.app")
        self._sandbox_client: ApiClient | None = None
        self._live_checked = False
        self._warning: str | None = None

    def client(self, target: TargetName) -> ApiClient:
        if target == "live":
            if not self._live_checked:
                self._live_checked = True
                if self._stale_check is not None:
                    self._warning = self._stale_check(self.live_url)
            return self._live
        if target == "sandbox":
            url = self.sandbox.start()
            if self._sandbox_client is None or self._sandbox_client.base_url != url:
                if self._sandbox_client is not None:
                    self._sandbox_client.close()
                self._sandbox_client = ApiClient(
                    url, "sandbox",
                    lambda: "the sandbox server died:\n" + self.sandbox.log_tail())
            return self._sandbox_client
        raise ToolError(f"unknown target {target!r} — use 'live' or 'sandbox'")

    def live_only(self, target: TargetName) -> ApiClient:
        if target != "live":
            raise ToolError("motion tools only drive the live app — the sandbox has no machine")
        return self.client("live")

    def take_warning(self) -> str | None:
        warning, self._warning = self._warning, None
        return warning

    def close(self) -> None:
        self.sandbox.stop()
        self._live.close()
        if self._sandbox_client is not None:
            self._sandbox_client.close()
            self._sandbox_client = None
```

`axibridge_mcp/server.py`:

```python
"""axibridge MCP server: see, compose, tune, diagnose — and, with Ian's
per-call approval, plot. Entry point: `python -m axibridge_mcp` (stdio)."""

from __future__ import annotations

import atexit
import functools
import signal
import sys

from mcp.server.mcpserver import MCPServer

from . import tools_look
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

MODULES = (tools_look,)


def make_tool_decorator(srv: MCPServer, targets: Targets):
    """Register fn as an unstructured tool whose result gets the one-time
    stale-server warning prefixed (see Targets.client)."""
    def tool(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            out = fn(*args, **kwargs)
            warning = targets.take_warning()
            if not warning:
                return out
            return [warning, *out] if isinstance(out, list) else [warning, out]

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
    targets = Targets()
    atexit.register(targets.close)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(0))  # sys.exit runs atexit → sandbox stops
    build_server(targets).run("stdio")
```

`axibridge_mcp/tools_look.py`:

```python
"""Looking: compact state now; canvas and UI images in later tasks."""

from __future__ import annotations

import json

from .targets import TargetName, Targets


def _source_label(source: dict) -> str:
    kind = source.get("type", "?")
    name = source.get("generator") or source.get("file") or ""
    return f"{kind}:{name}" if name else kind


def register(tool, targets: Targets) -> None:
    @tool
    def state(target: TargetName = "live") -> str:
        """Compact snapshot of a target: project (name, dir, edit_rev, dirty,
        view), layers bottom→top (id, name, source, pen, visible, effects,
        paths, points) and machine (backend, connected, job state, position).
        Call this first — /api/state itself is ~300 KB."""
        c = targets.client(target)
        project = c.get("/api/project")
        resolved = c.get("/api/compose/resolved")
        st = c.get("/api/state")
        stats = {l["id"]: l.get("stats") or {} for l in resolved["layers"]}
        layers = [{
            "id": l["id"],
            "name": l["name"],
            "source": _source_label(l["source"]),
            "pen": l.get("pen_id"),
            "visible": l.get("visible", True),
            "effects": [e.get("effect") for e in l.get("effects", [])],
            "paths": stats.get(l["id"], {}).get("paths"),
            "points": stats.get(l["id"], {}).get("points"),
        } for l in project["layers"]]
        m = st["machine"]
        return json.dumps({
            "target": target,
            "project": {"name": project.get("name"), "dir": st.get("project_dir"),
                        "edit_rev": project.get("edit_rev"), "dirty": project.get("dirty"),
                        "view": project.get("view")},
            "layers": layers,
            "machine": {"backend": m.get("backend"), "connected": m.get("connected"),
                        "job_state": m.get("job_state"), "position": m.get("position")},
        }, indent=1)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_mcp_foundation.py -q`
Expected: PASS. If `test_the_sandbox_starts_on_demand_and_is_isolated` times out, read `targets.sandbox.log_tail()`; the sandbox runs `python -m axibridge --host 127.0.0.1 --port N`, which must not try to auto-connect hardware (`AXIBRIDGE_NO_AUTOCONNECT=1` is set).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml axibridge_mcp tests/_mcp_harness.py tests/test_mcp_foundation.py
git commit -m "feat(mcp): server skeleton with live/sandbox targets and state tool

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Eyes and tuning — `render.py`, `see`, `try_generator`, `try_effects`, `modules`, `module_schema`

**Files:**
- Create: `axibridge_mcp/render.py`, `axibridge_mcp/tools_modules.py`
- Modify: `axibridge_mcp/tools_look.py` (add `see`), `axibridge_mcp/server.py` (`MODULES`)
- Test: `tests/test_mcp_render.py`, `tests/test_mcp_look.py`

**Interfaces:**
- Consumes: `Targets.client`, harness from Task 3.
- Produces: `render.render_layers(layers: list[dict], *, bed: tuple[float, float], guide: dict | None, travel: list[list[list[float]]] | None, view: str, size: int) -> bytes` (PNG); `render.fit_lines(lines: list[list[list[float]]], size: int) -> PIL.Image.Image`; `render.contact_sheet(tiles: list[tuple[PIL.Image.Image, str]], cols: int | None = None) -> bytes` (PNG); `render.png(data: bytes) -> mcp Image`.
- API facts used: `GET /api/compose/resolved?t=&stats=` → `{"layers": [{"id","name","visible","color","line_diameter_mm","paths": [{"points": [[x,y],…], "filled": bool}], "stats": {...}}], "bed": {"width","height"}}`; `GET /api/plan` → `{"job": {"moves": [{"pen_down": bool, "points": [[x,y],…]}]}}`; `POST /api/generators/preview {"module","params"}` → `{"lines": [[[x,y],…]], "points": int, "decimated": bool, "width", "height"}`; `POST /api/layers/{id}/effects/preview {"effects": [{"effect","params"}]}` → `{"lines", "points", "decimated"}`; `/api/state` → `"modules": {"sources"|"effects"|"transforms": [{"id","label","description","schema","defaults"}]}`.
- Portrait mapping (from `static/js/canvas.js:280`, `translate(H 0) rotate(90)`): machine `(x, y)` → screen `(H − y, x)`; output is H wide, W tall; machine origin lands top-right.

- [ ] **Step 1: Write the failing render unit tests**

Create `tests/test_mcp_render.py`:

```python
import io

import pytest

pytest.importorskip("mcp")
from PIL import Image  # noqa: E402

from axibridge_mcp import render  # noqa: E402

PAPER = (0xFF, 0xFC, 0xF0)
LINE = [{"id": "a", "visible": True, "color": "#100F0F", "line_diameter_mm": 0.5,
         "paths": [{"points": [[10.0, 10.0], [290.0, 208.0]], "filled": False}]}]


def decode(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGB")


def test_landscape_render_is_bed_shaped_and_draws_the_path():
    img = decode(render.render_layers(LINE, bed=(300.0, 218.0), guide=None, travel=None,
                                      view="landscape", size=600))
    assert img.size == (600, round(218 * 600 / 300))
    mid = img.getpixel((300, round(109 * 2)))  # (150, 109) mm lies on the diagonal
    assert mid != PAPER


def test_portrait_render_swaps_axes_and_puts_origin_top_right():
    dot = [{"id": "o", "visible": True, "color": "#100F0F", "line_diameter_mm": 2.0,
            "paths": [{"points": [[1.0, 1.0], [6.0, 1.0]], "filled": False}]}]
    img = decode(render.render_layers(dot, bed=(300.0, 218.0), guide=None, travel=None,
                                      view="portrait", size=600))
    w, h = img.size
    assert (w, h) == (round(218 * 600 / 300), 600)
    assert img.getpixel((w - 3, 6)) != PAPER      # near top-right
    assert img.getpixel((3, 6)) == PAPER          # top-left stays empty


def test_hidden_layers_are_not_drawn():
    hidden = [{**LINE[0], "visible": False}]
    img = decode(render.render_layers(hidden, bed=(300.0, 218.0), guide=None, travel=None,
                                      view="landscape", size=600))
    assert img.getpixel((300, 218)) == PAPER


def test_contact_sheet_lays_tiles_in_a_grid_with_captions():
    tiles = [(render.fit_lines([[[0, 0], [10, 10]]], 100), f"{i}") for i in range(3)]
    img = decode(render.contact_sheet(tiles))
    assert img.size[0] == 2 * 100          # ceil(sqrt(3)) = 2 columns
    assert img.size[1] > 2 * 100           # two rows plus caption strips


def test_fit_lines_survives_empty_and_degenerate_input():
    assert render.fit_lines([], 50).size == (50, 50)
    assert render.fit_lines([[[5, 5]]], 50).size == (50, 50)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_mcp_render.py -q`
Expected: FAIL — `ImportError: cannot import name 'render'`.

- [ ] **Step 3: Write `render.py`**

```python
"""Rasterise axibridge geometry to PNG — the agent's eyes on what the canvas
shows. Pillow only: no browser, no cairo. Flexoki palette (hexes from
flexoki.css: paper, black, 100, 300, 600, red-400)."""

from __future__ import annotations

import io
import math

from mcp.server.mcpserver import Image as McpImage
from PIL import Image, ImageDraw, ImageFont

PAPER = "#FFFCF0"
INK = "#100F0F"
BED_LINE = "#E6E4D9"
GUIDE_LINE = "#B7B5AC"
CAPTION = "#6F6E69"
TRAVEL = "#D14D41"
CAPTION_H = 22


def png(data: bytes) -> McpImage:
    return McpImage(data=data, format="png")


def _encode(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def render_layers(layers: list[dict], *, bed: tuple[float, float], guide: dict | None,
                  travel: list[list[list[float]]] | None, view: str, size: int) -> bytes:
    W, H = bed
    portrait = view == "portrait"
    out_w, out_h = (H, W) if portrait else (W, H)
    scale = size / max(out_w, out_h)
    img = Image.new("RGB", (round(out_w * scale), round(out_h * scale)), PAPER)
    d = ImageDraw.Draw(img)

    def px(x: float, y: float) -> tuple[float, float]:
        if portrait:  # canvas.js: translate(H 0) rotate(90) — origin top-right
            x, y = H - y, x
        return (x * scale, y * scale)

    def rect(x: float, y: float, w: float, h: float, color: str) -> None:
        corners = [px(x, y), px(x + w, y), px(x + w, y + h), px(x, y + h), px(x, y)]
        d.line(corners, fill=color, width=1)

    rect(0, 0, W, H, BED_LINE)
    if guide:
        rect(guide["x"], guide["y"], guide["width"], guide["height"], GUIDE_LINE)
    for layer in layers:
        if not layer.get("visible", True):
            continue
        color = layer.get("color") or INK
        width = max(1, round((layer.get("line_diameter_mm") or 0.4) * scale))
        for path in layer.get("paths", []):
            pts = [px(*p) for p in path["points"]]
            if len(pts) >= 2:
                d.line(pts, fill=color, width=width, joint="curve")
            elif pts:
                d.point(pts, fill=color)
    for seg in travel or []:
        if len(seg) >= 2:
            d.line([px(*p) for p in seg], fill=TRAVEL, width=1)
    return _encode(img)


def fit_lines(lines: list[list[list[float]]], size: int) -> Image.Image:
    """A free-floating preview (generator/effect `lines`) fitted to a square
    tile with a small margin. Absolute scale is dropped; captions carry it."""
    img = Image.new("RGB", (size, size), PAPER)
    pts = [p for line in lines for p in line]
    if not pts:
        return img
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0 = min(xs), min(ys)
    span = max(max(xs) - x0, max(ys) - y0) or 1.0
    pad = size * 0.06
    k = (size - 2 * pad) / span
    d = ImageDraw.Draw(img)
    for line in lines:
        q = [(pad + (x - x0) * k, pad + (y - y0) * k) for x, y in line]
        if len(q) >= 2:
            d.line(q, fill=INK, width=1)
        elif q:
            d.point(q, fill=INK)
    return img


def contact_sheet(tiles: list[tuple[Image.Image, str]], cols: int | None = None) -> bytes:
    if not tiles:
        return _encode(Image.new("RGB", (1, 1), PAPER))
    cols = cols or math.ceil(math.sqrt(len(tiles)))
    rows = math.ceil(len(tiles) / cols)
    tw, th = tiles[0][0].size
    sheet = Image.new("RGB", (cols * tw, rows * (th + CAPTION_H)), PAPER)
    d = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=13)
    for i, (tile, caption) in enumerate(tiles):
        x, y = (i % cols) * tw, (i // cols) * (th + CAPTION_H)
        sheet.paste(tile, (x, y))
        d.rectangle([x, y, x + tw - 1, y + th - 1], outline=BED_LINE)
        d.text((x + 6, y + th + 4), caption, fill=CAPTION, font=font)
    return _encode(sheet)
```

- [ ] **Step 4: Run the render tests**

Run: `.venv/bin/python -m pytest tests/test_mcp_render.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing tool tests**

Create `tests/test_mcp_look.py`:

```python
import io
import json

from PIL import Image

from _mcp_harness import axb, call, http, images, srv, targets, text  # noqa: F401

POLY = {"module": "polygon", "params": {"sides": 5, "radius": 20}}


def test_see_returns_a_png_of_the_canvas_with_a_caption(srv, axb):
    with http(axb) as h:
        h.post("/api/layers/generate", json=POLY)
    r = call(srv, "see", {"size": 600})
    assert not r.is_error, text(r)
    [png] = images(r)
    img = Image.open(io.BytesIO(png))
    assert max(img.size) == 600
    assert "1 layer" in text(r)


def test_see_follows_the_project_view(srv, axb):
    with http(axb) as h:
        h.put("/api/project", json={"view": "portrait"})
    [png] = images(call(srv, "see", {"size": 600}))
    w, h_ = Image.open(io.BytesIO(png)).size
    assert h_ > w
    [png] = images(call(srv, "see", {"size": 600, "orient": "machine"}))
    w, h_ = Image.open(io.BytesIO(png)).size
    assert w > h_


def test_see_rejects_out_of_range_sizes(srv):
    assert call(srv, "see", {"size": 50}).is_error


def test_try_generator_returns_one_contact_sheet_and_leaves_the_project_alone(srv, axb):
    r = call(srv, "try_generator", {"module": "polygon",
                                    "param_sets": [{"sides": 3}, {"sides": 8}], "tile": 200})
    assert not r.is_error, text(r)
    [png] = images(r)
    assert Image.open(io.BytesIO(png)).size[0] == 400
    with http(axb) as h:
        assert h.get("/api/project").json()["layers"] == []


def test_try_generator_reports_a_bad_set_without_losing_the_good_ones(srv):
    r = call(srv, "try_generator", {"module": "polygon",
                                    "param_sets": [{"sides": 3}, {"sides": "many"}], "tile": 200})
    assert not r.is_error
    assert "2: error" in text(r)
    assert len(images(r)) == 1


def test_try_effects_previews_chains_on_an_existing_layer(srv, axb):
    with http(axb) as h:
        lid = h.post("/api/layers/generate", json=POLY).json()["id"]
    r = call(srv, "try_effects", {"layer_id": lid, "tile": 200, "chains": [
        [], [{"effect": "freehand", "params": {}}]]})
    assert not r.is_error, text(r)
    assert len(images(r)) == 1
    with http(axb) as h:
        assert h.get(f"/api/project").json()["layers"][0]["effects"] == []


def test_modules_lists_and_filters(srv):
    out = text(call(srv, "modules", {"kind": "sources", "query": "polygon"}))
    assert "polygon" in out
    assert "freehand" not in out


def test_module_schema_returns_schema_and_defaults(srv):
    data = json.loads(text(call(srv, "module_schema", {"module_id": "polygon"})))
    assert data["kind"] == "sources"
    assert "sides" in data["schema"]["properties"]
    assert "sides" in data["defaults"]


def test_module_schema_names_unknown_modules(srv):
    r = call(srv, "module_schema", {"module_id": "nope"})
    assert r.is_error and "nope" in text(r)
```

- [ ] **Step 6: Add `see` to `tools_look.py`**

Add imports at the top of `tools_look.py`:

```python
from typing import Annotated, Literal

from pydantic import Field

from .render import png, render_layers
```

Inside `register`, after `state`:

```python
    @tool
    def see(target: TargetName = "live",
            layer_ids: list[str] | None = None,
            t: Annotated[float | None, Field(ge=0.0, le=1.0)] = None,
            travel: bool = False,
            size: Annotated[int, Field(ge=200, le=2400)] = 1200,
            orient: Literal["view", "machine"] = "view") -> list:
        """PNG of the resolved canvas — exactly what plotting consumes.
        `layer_ids` limits it to some layers; `t` scrubs the master timeline
        (tweens that follow it); `travel` overlays pen-up moves in red (from
        the stored-t plan); `orient="view"` matches Ian's screen (portrait is
        rotated, origin top-right), "machine" is the raw machine frame."""
        c = targets.client(target)
        resolved = c.get("/api/compose/resolved", t=t, stats="false")
        project = c.get("/api/project")
        layers = [l for l in resolved["layers"] if layer_ids is None or l["id"] in layer_ids]
        moves = None
        if travel:
            moves = [m["points"] for m in c.get("/api/plan")["job"]["moves"] if not m["pen_down"]]
        view = project.get("view", "landscape") if orient == "view" else "landscape"
        bed = (resolved["bed"]["width"], resolved["bed"]["height"])
        data = render_layers(layers, bed=bed, guide=project.get("guide"), travel=moves,
                             view=view, size=size)
        paths = sum(len(l["paths"]) for l in layers if l.get("visible", True))
        n = len(layers)
        caption = f"{n} layer{'s' if n != 1 else ''}, {paths} paths, {view}"
        return [caption, png(data)]
```

- [ ] **Step 7: Write `tools_modules.py`**

```python
"""Module discovery and the tuning loop. Previews never touch the project."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from mcp.server.mcpserver.exceptions import ToolError
from PIL import Image as PILImage
from pydantic import Field

from .render import contact_sheet, fit_lines, png
from .targets import TargetName, Targets

KINDS = ("sources", "effects", "transforms")


def _modules(targets: Targets, target: TargetName) -> dict:
    return targets.client(target).get("/api/state")["modules"]


def _first_sentence(text: str | None) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text.split(". ")[0][:140]


def _error_tile(size: int) -> PILImage.Image:
    return PILImage.new("RGB", (size, size), "#FFE1D5")  # flexoki red-50


def register(tool, targets: Targets) -> None:
    @tool
    def modules(kind: Literal["sources", "effects", "transforms", "all"] = "all",
                query: str | None = None, target: TargetName = "live") -> str:
        """List generators ("sources"), effects and transforms as
        `id — label: summary`. `query` filters on id/label/description."""
        mods = _modules(targets, target)
        q = (query or "").lower()
        out = []
        for k in KINDS if kind == "all" else (kind,):
            rows = [m for m in mods.get(k, []) if not q or q in
                    f"{m['id']} {m.get('label', '')} {m.get('description', '')}".lower()]
            if rows:
                out.append(f"## {k}")
                out += [f"{m['id']} — {m.get('label', '')}: {_first_sentence(m.get('description'))}"
                        for m in rows]
        return "\n".join(out) or "no modules match"

    @tool
    def module_schema(module_id: str, target: TargetName = "live") -> str:
        """Full JSON Schema and defaults for one module's params."""
        mods = _modules(targets, target)
        for k in KINDS:
            for m in mods.get(k, []):
                if m["id"] == module_id:
                    return json.dumps({"id": m["id"], "kind": k, "label": m.get("label"),
                                       "description": m.get("description"),
                                       "schema": m.get("schema"),
                                       "defaults": m.get("defaults")}, indent=1)
        raise ToolError(f"no module {module_id!r} — call `modules` to list them")

    @tool
    def try_generator(module: str, param_sets: list[dict],
                      target: TargetName = "live",
                      tile: Annotated[int, Field(ge=100, le=800)] = 400) -> list:
        """Run a generator once per param set (each merged over its defaults by
        the server) and return ONE contact sheet, tiles numbered in order.
        Never touches the project. 1–16 sets."""
        if not 1 <= len(param_sets) <= 16:
            raise ToolError("give 1–16 param sets")
        c = targets.client(target)
        tiles, notes = [], []
        for i, params in enumerate(param_sets, 1):
            try:
                r = c.post("/api/generators/preview", {"module": module, "params": params})
            except ToolError as e:
                tiles.append((_error_tile(tile), f"{i}: error"))
                notes.append(f"{i}: {e}")
                continue
            extra = " (decimated)" if r.get("decimated") else ""
            tiles.append((fit_lines(r["lines"], tile), f"{i}: {r['points']} pts{extra}"))
        head = f"{module} — " + "; ".join(f"{i}={json.dumps(p)}" for i, p in enumerate(param_sets, 1))
        return ["\n".join([head, *notes]), png(contact_sheet(tiles))]

    @tool
    def try_effects(layer_id: str, chains: list[list[dict]],
                    target: TargetName = "live",
                    tile: Annotated[int, Field(ge=100, le=800)] = 400) -> list:
        """Preview whole effect stacks on an existing layer, one tile per chain.
        A chain is a list like [{"effect": "freehand", "params": {...}}]; an
        empty chain shows the bare layer. Never touches the project. 1–16."""
        if not 1 <= len(chains) <= 16:
            raise ToolError("give 1–16 chains")
        c = targets.client(target)
        tiles, notes = [], []
        for i, chain in enumerate(chains, 1):
            try:
                r = c.post(f"/api/layers/{layer_id}/effects/preview", {"effects": chain})
            except ToolError as e:
                tiles.append((_error_tile(tile), f"{i}: error"))
                notes.append(f"{i}: {e}")
                continue
            label = " + ".join(s.get("effect", "?") for s in chain) or "bare"
            tiles.append((fit_lines(r["lines"], tile), f"{i}: {label}, {r['points']} pts"))
        return ["\n".join([f"layer {layer_id}", *notes]), png(contact_sheet(tiles))]
```

In `server.py`: `from . import tools_look, tools_modules` and `MODULES = (tools_look, tools_modules)`.

- [ ] **Step 8: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_mcp_render.py tests/test_mcp_look.py -q`
Expected: PASS. If `test_try_effects_...` 422s, read `EffectsPreviewBody`/the effect-step model in `axibridge/compose.py` for the exact step keys and fix the docstring and test together.

- [ ] **Step 9: Commit**

```bash
git add axibridge_mcp tests/test_mcp_render.py tests/test_mcp_look.py
git commit -m "feat(mcp): see the canvas, browse modules, tune via contact sheets

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Compose tools — layers, history, projects

**Files:**
- Create: `axibridge_mcp/tools_compose.py`
- Modify: `axibridge_mcp/server.py` (`MODULES`)
- Test: `tests/test_mcp_compose.py`

**Interfaces:**
- API facts: `POST /api/layers/generate {"module","params"}` → layer dict with `id`; `PATCH /api/layers/{id}` takes any layer-field dict (`name`, `visible`, `pen_id`, `transform`, `effects`, …); `POST /api/layers/{id}/regenerate {"params", "coalesce": false}`; `POST /api/layers/delete {"ids", "cascade"}` → `{"deleted": [...]}`; `POST /api/layers/order {"ids"}` (full list, bottom→top = `project.layers` order); `POST /api/undo` / `/api/redo` → project payload, **409 "nothing to undo/redo"** when empty; `POST /api/project/new {"recovery_action"}`; `POST /api/project/load {"name","recovery_action"}`; `GET /api/projects` → names; `GET /api/recovery`; `POST /api/project/save {"name"?}` (always send a JSON body). Dirty project + no `recovery_action` → **409 "unsaved work: choose Save, Continue with recovery, Discard or Cancel"**.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_compose.py`:

```python
import json

from _mcp_harness import axb, call, http, srv, targets, text  # noqa: F401


def layers(axb):
    with http(axb) as h:
        return h.get("/api/project").json()["layers"]


def test_add_layer_with_name_and_params(srv, axb):
    r = call(srv, "add_layer", {"module": "polygon", "params": {"sides": 4}, "name": "square"})
    assert not r.is_error, text(r)
    [layer] = layers(axb)
    assert layer["name"] == "square"
    assert layer["source"]["params"]["sides"] == 4
    assert layer["id"] in text(r)


def test_edit_layer_patches_fields_and_regenerates_params(srv, axb):
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 5}})
    lid = layers(axb)[0]["id"]
    r = call(srv, "edit_layer", {"layer_id": lid, "patch": {"name": "renamed", "visible": False},
                                 "params": {"sides": 9}})
    assert not r.is_error, text(r)
    [layer] = layers(axb)
    assert layer["name"] == "renamed" and layer["visible"] is False
    assert layer["source"]["params"]["sides"] == 9


def test_edit_layer_needs_something_to_change(srv, axb):
    call(srv, "add_layer", {"module": "polygon", "params": {}})
    assert call(srv, "edit_layer", {"layer_id": layers(axb)[0]["id"]}).is_error


def test_undo_and_redo_report_how_far_they_got(srv, axb):
    call(srv, "add_layer", {"module": "polygon", "params": {}})
    out = text(call(srv, "undo", {"steps": 5}))
    assert "undid 1" in out and "nothing more" in out
    assert layers(axb) == []
    assert "redid 1" in text(call(srv, "redo"))
    assert len(layers(axb)) == 1


def test_delete_and_reorder(srv, axb):
    for n in (3, 4, 5):
        call(srv, "add_layer", {"module": "polygon", "params": {"sides": n}})
    ids = [l["id"] for l in layers(axb)]
    assert not call(srv, "reorder_layers", {"ids": list(reversed(ids))}).is_error
    assert [l["id"] for l in layers(axb)] == list(reversed(ids))
    assert not call(srv, "delete_layers", {"ids": ids[:2]}).is_error
    assert [l["id"] for l in layers(axb)] == [ids[2]]


def test_save_list_new_open_roundtrip(srv, axb):
    call(srv, "add_layer", {"module": "polygon", "params": {}})
    assert not call(srv, "save_project", {"name": "mcp-roundtrip"}).is_error
    assert "mcp-roundtrip" in text(call(srv, "project", {"action": "list"}))
    assert not call(srv, "project", {"action": "new"}).is_error
    assert layers(axb) == []
    assert not call(srv, "project", {"action": "open", "name": "mcp-roundtrip"}).is_error
    assert len(layers(axb)) == 1


def test_open_refuses_to_discard_unsaved_work(srv, axb):
    # Review Focus 3: never a silent discard of Ian's work
    call(srv, "add_layer", {"module": "polygon", "params": {}})
    call(srv, "save_project", {"name": "keep-me"})
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 7}})  # now dirty
    r = call(srv, "project", {"action": "new"})
    assert r.is_error and "unsaved work" in text(r)
    assert len(layers(axb)) == 2


def test_project_status_reports_name_dirty_and_recovery(srv):
    data = json.loads(text(call(srv, "project", {"action": "status"})))
    assert {"name", "dir", "dirty", "recovery"} <= set(data)


def test_open_needs_a_name(srv):
    assert call(srv, "project", {"action": "open"}).is_error
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_mcp_compose.py -q`
Expected: FAIL — unknown tools.

- [ ] **Step 3: Write `tools_compose.py`**

```python
"""Composing through the normal API — every edit is one of Ian's undo steps."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .targets import TargetName, Targets

RecoveryAction = Literal["save", "recover", "discard"]


def _layer_line(layer: dict) -> str:
    src = layer.get("source", {})
    return f"{layer['id']} “{layer.get('name')}” ({src.get('type')}:{src.get('generator') or ''})"


def register(tool, targets: Targets) -> None:
    @tool
    def add_layer(module: str, params: dict[str, Any] | None = None,
                  name: str | None = None, pen_id: str | None = None,
                  target: TargetName = "live") -> str:
        """Add a generator layer (params merged over the module's defaults).
        Setting name/pen is a second edit, so ⌘Z takes two steps then."""
        c = targets.client(target)
        layer = c.post("/api/layers/generate", {"module": module, "params": params or {}})
        patch = {k: v for k, v in {"name": name, "pen_id": pen_id}.items() if v is not None}
        if patch:
            layer = c.patch(f"/api/layers/{layer['id']}", patch)
        return f"added {_layer_line(layer)}"

    @tool
    def edit_layer(layer_id: str, patch: dict[str, Any] | None = None,
                   params: dict[str, Any] | None = None,
                   target: TargetName = "live") -> str:
        """Change a layer. `patch` sets layer fields (name, visible, pen_id,
        transform {a,b,c,d,e,f}, effects [{effect, params}], occluder, …);
        `params` re-runs a generator layer with new params."""
        if not patch and not params:
            raise ToolError("nothing to change — pass `patch`, `params` or both")
        c = targets.client(target)
        layer = None
        if params:
            layer = c.post(f"/api/layers/{layer_id}/regenerate", {"params": params, "coalesce": False})
        if patch:
            layer = c.patch(f"/api/layers/{layer_id}", patch)
        return f"edited {_layer_line(layer)}"

    @tool
    def delete_layers(ids: list[str], cascade: bool = True,
                      target: TargetName = "live") -> str:
        """Delete layers in one undo step. cascade=True also removes tweens
        that reference them."""
        r = targets.client(target).post("/api/layers/delete", {"ids": ids, "cascade": cascade})
        return f"deleted {', '.join(r.get('deleted', ids))}"

    @tool
    def reorder_layers(ids: list[str], target: TargetName = "live") -> str:
        """Set the full layer order, bottom→top (the resolve order). Must list
        every current layer id exactly once."""
        r = targets.client(target).post("/api/layers/order", {"ids": ids})
        return "order (bottom→top): " + ", ".join(r["ids"])

    def _history(direction: str, steps: int, target: TargetName) -> str:
        c = targets.client(target)
        # literal paths, not f"/api/{direction}": the freshness test (Task 11)
        # finds endpoints by their string literals
        path = "/api/undo" if direction == "undo" else "/api/redo"
        done = 0
        for _ in range(steps):
            try:
                c.post(path)
            except ToolError as e:
                if f"nothing to {direction}" in str(e):
                    return f"{'undid' if direction == 'undo' else 'redid'} {done}; nothing more to {direction}"
                raise
            done += 1
        return f"{'undid' if direction == 'undo' else 'redid'} {done}"

    @tool
    def undo(steps: Annotated[int, Field(ge=1, le=50)] = 1, target: TargetName = "live") -> str:
        """Step back through the shared undo history (Ian's ⌘Z history too)."""
        return _history("undo", steps, target)

    @tool
    def redo(steps: Annotated[int, Field(ge=1, le=50)] = 1, target: TargetName = "live") -> str:
        """Step forward again after undo."""
        return _history("redo", steps, target)

    @tool
    def project(action: Literal["status", "list", "new", "open"],
                name: str | None = None,
                recovery_action: RecoveryAction | None = None,
                target: TargetName = "live") -> str:
        """Project status, list saved projects, start a new one, or open one.
        If the open project has unsaved work, new/open fail with "unsaved work"
        — then pass recovery_action: "save" (save first), "recover" (keep a
        recovery copy) or "discard". On live, never "discard" unless Ian said so."""
        c = targets.client(target)
        if action == "status":
            p = c.get("/api/project")
            st = c.get("/api/state")
            return json.dumps({"name": p.get("name"), "dir": st.get("project_dir"),
                               "dirty": p.get("dirty"), "edit_rev": p.get("edit_rev"),
                               "recovery": c.get("/api/recovery")}, indent=1)
        if action == "list":
            return "\n".join(c.get("/api/projects")) or "no saved projects"
        if action == "new":
            c.post("/api/project/new", {"recovery_action": recovery_action})
            return "new empty project"
        if not name:
            raise ToolError("open needs `name` — `project(action='list')` shows them")
        p = c.post("/api/project/load", {"name": name, "recovery_action": recovery_action})
        return f"opened {name} ({len(p.get('layers', []))} layers)"

    @tool
    def save_project(name: str | None = None, target: TargetName = "live") -> str:
        """Save the open project to its folder (overwrites it on disk).
        `name` saves under a new name."""
        targets.client(target).post("/api/project/save", {"name": name})
        return f"saved {name or 'project'}"
```

In `server.py`: add `tools_compose` to the imports and `MODULES`.

Note: `load`'s response shape — if `POST /api/project/load` doesn't return the project payload, replace the layer count with a follow-up `c.get("/api/project")`. Check with `sed -n 2216,2240p axibridge/api.py`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_mcp_compose.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add axibridge_mcp tests/test_mcp_compose.py
git commit -m "feat(mcp): compose tools — layers, undo/redo, projects

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Machine tools — estimate, guarded plot, motion, stop

**Files:**
- Create: `axibridge_mcp/tools_machine.py`
- Modify: `axibridge_mcp/server.py` (`MODULES`)
- Test: `tests/test_mcp_machine.py`

**Interfaces:**
- API facts: `GET /api/plan?target=all|<layer id>` → `{"job": {"total_duration", "pen_down_distance", "travel_distance", "pen_lifts", "moves"}, "warnings": [...], "estimator_note"}`; `POST /api/plot/start {"target"}` → machine status, 409 with reason when not connected/busy; `POST /api/plot/stop {"return_home"}`; `POST /api/plot/pause`; `POST /api/machine/pen {"down"}`; `POST /api/machine/jog {"dx","dy"}` → `{"position"}`; `POST /api/machine/goto {"x","y"}` → `{"position"}`; `POST /api/connect {}` (tests only). Simulator is the default backend on a fresh config.
- `plot` deliberately does not take `master_t`, sheets or staged trays in v1 (spec): it plots what `estimate` timed, which is the stored-t default route.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_machine.py`:

```python
import json
import re
import time

from _mcp_harness import axb, call, http, srv, targets, text  # noqa: F401


def connect(axb):
    with http(axb) as h:
        h.post("/api/connect", json={}).raise_for_status()


def wait_idle(axb, timeout=60):
    deadline = time.time() + timeout
    with http(axb) as h:
        while time.time() < deadline:
            if h.get("/api/state").json()["machine"]["job_state"] == "idle":
                return
            time.sleep(0.2)
    raise AssertionError("job never finished")


def rev_of(estimate_text: str) -> int:
    return int(re.search(r"revision (\d+)", estimate_text).group(1))


def test_estimate_states_time_and_the_revision_to_plot(srv, axb):
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 5, "radius": 20}})
    out = text(call(srv, "estimate"))
    assert "pen-down" in out and "revision" in out
    with http(axb) as h:
        assert rev_of(out) == h.get("/api/project").json()["edit_rev"]


def test_plot_runs_what_was_estimated(srv, axb):
    connect(axb)
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 5, "radius": 10}})
    rev = rev_of(text(call(srv, "estimate")))
    r = call(srv, "plot", {"revision": rev})
    assert not r.is_error, text(r)
    wait_idle(axb)


def test_plot_refuses_after_an_edit(srv, axb):
    # Review Focus 4: an edit between estimate and plot means nobody saw this
    connect(axb)
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 5, "radius": 10}})
    rev = rev_of(text(call(srv, "estimate")))
    with http(axb) as h:  # Ian nudges something in the UI
        lid = h.get("/api/project").json()["layers"][0]["id"]
        h.patch(f"/api/layers/{lid}", json={"name": "changed"})
    r = call(srv, "plot", {"revision": rev})
    assert r.is_error and "changed since" in text(r)
    with http(axb) as h:
        assert h.get("/api/state").json()["machine"]["job_state"] == "idle"


def test_motion_tools_refuse_the_sandbox_without_starting_it(srv, targets):
    for name, args in [("plot", {"revision": 1}), ("pen", {"down": False}),
                       ("jog", {"dx": 1}), ("go_home", {})]:
        r = call(srv, name, {**args, "target": "sandbox"})
        assert r.is_error and "only drive the live app" in text(r), name
    assert not targets.sandbox.running


def test_jog_is_bounded(srv):
    assert call(srv, "jog", {"dx": 500}).is_error


def test_jog_then_go_home(srv, axb):
    connect(axb)
    assert "position" in text(call(srv, "jog", {"dx": 5, "dy": 3}))
    out = text(call(srv, "go_home"))
    assert "0.0, 0.0" in out or "[0.0, 0.0]" in out


def test_stop_halts_a_running_plot(srv, axb):
    connect(axb)
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 40, "radius": 90}})
    rev = rev_of(text(call(srv, "estimate")))
    assert not call(srv, "plot", {"revision": rev}).is_error
    r = call(srv, "stop")
    assert not r.is_error, text(r)
    wait_idle(axb, timeout=20)


def test_stop_when_idle_is_harmless(srv):
    assert not call(srv, "stop").is_error
```

(If the simulator finishes the 40-gon before `stop` lands, raise `radius`/`sides` until `stop` catches it running; the assertion that matters is "idle afterwards, no error".)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_mcp_machine.py -q`
Expected: FAIL — unknown tools.

- [ ] **Step 3: Write `tools_machine.py`**

```python
"""The machine. plot/pen/jog/go_home move a real pen: live target only, and
never allow-listed, so Ian approves every call. stop/pause are always fine —
stopping is the safe direction."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .targets import TargetName, Targets


def _fmt_s(seconds: float) -> str:
    m, s = divmod(round(seconds), 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


def register(tool, targets: Targets) -> None:
    @tool
    def estimate(plot_target: str = "all", target: TargetName = "live") -> str:
        """Time and travel for a plot of `plot_target` ("all" or a layer id),
        plus the project revision it was computed at. Show Ian this and a
        `see` image, then pass the revision to `plot`."""
        c = targets.client(target)
        plan = c.get("/api/plan", target=plot_target)
        p = c.get("/api/project")
        st = c.get("/api/state")["machine"]
        job = plan["job"]
        lines = [
            f"plot {plot_target}: {_fmt_s(job['total_duration'])} total, "
            f"{job['pen_down_distance'] / 1000:.2f} m pen-down, "
            f"{job['travel_distance'] / 1000:.2f} m travel, {job['pen_lifts']} lifts",
            f"backend {st.get('backend')} ({'connected' if st.get('connected') else 'NOT connected'}), "
            f"job {st.get('job_state')}",
            f"revision {p['edit_rev']} — call plot(revision={p['edit_rev']}) to plot exactly this",
        ]
        lines += [f"warning: {w}" for w in plan.get("warnings", [])]
        if plan.get("estimator_note"):
            lines.append(plan["estimator_note"])
        return "\n".join(lines)

    @tool
    def plot(revision: int, plot_target: str = "all", target: TargetName = "live") -> str:
        """MOVES THE MACHINE. Plot `plot_target` on the live app. `revision`
        must be the one `estimate` returned; if the project changed since,
        this refuses — re-estimate and show Ian again."""
        c = targets.live_only(target)
        current = c.get("/api/project")["edit_rev"]
        if current != revision:
            raise ToolError(f"project changed since the estimate (revision {revision} → {current}); "
                            "run estimate again and show Ian before plotting")
        st = c.post("/api/plot/start", {"target": plot_target})
        return (f"plotting {plot_target} on {st.get('backend')} — job {st.get('job_state')}. "
                "stop() halts and returns home.")

    @tool
    def pen(down: bool, target: TargetName = "live") -> str:
        """MOVES THE MACHINE. Raise (down=false) or lower the pen."""
        c = targets.live_only(target)
        c.post("/api/machine/pen", {"down": down})
        return f"pen {'down' if down else 'up'}"

    @tool
    def jog(dx: Annotated[float, Field(ge=-300.0, le=300.0)] = 0.0,
            dy: Annotated[float, Field(ge=-218.0, le=218.0)] = 0.0,
            target: TargetName = "live") -> str:
        """MOVES THE MACHINE. Relative move in mm (pen as it is)."""
        c = targets.live_only(target)
        r = c.post("/api/machine/jog", {"dx": dx, "dy": dy})
        return f"position {r['position']}"

    @tool
    def go_home(target: TargetName = "live") -> str:
        """MOVES THE MACHINE. Travel to (0, 0), the home corner."""
        c = targets.live_only(target)
        r = c.post("/api/machine/goto", {"x": 0.0, "y": 0.0})
        return f"position {r['position']}"

    @tool
    def stop(return_home: bool = True, target: TargetName = "live") -> str:
        """Stop the running job (safe to call any time). return_home walks the
        carriage home afterwards (see docs/MCP.md for the pi_ssh caveat)."""
        st = targets.client(target).post("/api/plot/stop", {"return_home": return_home})
        return f"stop sent — job {st.get('job_state')}"

    @tool
    def pause(target: TargetName = "live") -> str:
        """Pause the running job (backends that support it)."""
        st = targets.client(target).post("/api/plot/pause")
        return f"job {st.get('job_state')}"
```

In `server.py`: add `tools_machine` to imports and `MODULES`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_mcp_machine.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add axibridge_mcp tests/test_mcp_machine.py
git commit -m "feat(mcp): machine tools with a revision-guarded plot

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Dev tools — `logs`, `diagnose`, `sandbox`, stale-server warning

**Files:**
- Create: `axibridge_mcp/diagnose.py`, `axibridge_mcp/tools_dev.py`
- Modify: `axibridge_mcp/targets.py` (`Sandbox.start(seed=...)`), `axibridge_mcp/server.py` (`MODULES`; `main()` passes `stale_check`)
- Test: `tests/test_mcp_dev.py`

**Interfaces:**
- Produces: `diagnose.Facts` (dataclass: `pid: int | None, command: str | None, cwd: str | None, started: float | None, parent: str | None, newest_backend: tuple[str, float] | None, newest_frontend: tuple[str, float] | None, dist_built: float | None, error: str | None`); `diagnose.gather(url: str) -> Facts`; `diagnose.assess(f: Facts, repo: Path) -> list[str]`; `diagnose.stale_warning(url: str) -> str | None`; `diagnose.report(url: str) -> str`.
- Staleness is judged from **file mtimes**, not git: backend is stale if any `axibridge/**/*.py` changed after the server process started (this catches uncommitted dev edits, the main dev-loop case); the frontend build is stale if `axibridge/static_dist/index.html` is older than the newest file under `axibridge/static/` (excluding nothing; `static_dist` is a sibling, not inside).
- API: `GET /api/logs?after=` → `{"entries": [{"id","ts","level","logger","msg"}]}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_dev.py`:

```python
import time
from pathlib import Path

import httpx

from _mcp_harness import axb, call, http, srv, targets, text  # noqa: F401

REPO = Path(__file__).resolve().parent.parent


def facts(**kw):
    from axibridge_mcp.diagnose import Facts
    base = dict(pid=123, command=f"{REPO}/.venv/bin/python -m axibridge", cwd=str(REPO),
                started=time.time(), parent="launch/axibridge_app.py",
                newest_backend=("axibridge/session.py", time.time() - 3600),
                newest_frontend=("axibridge/static/js/main.js", time.time() - 3600),
                dist_built=time.time() - 60, error=None)
    return Facts(**{**base, **kw})


def test_assess_is_quiet_for_a_fresh_owned_server():
    from axibridge_mcp.diagnose import assess
    assert assess(facts(), REPO) == []


def test_assess_flags_backend_edits_after_start():
    from axibridge_mcp.diagnose import assess
    out = assess(facts(newest_backend=("axibridge/api.py", time.time() + 5)), REPO)
    assert any("axibridge/api.py" in p and "restart" in p for p in out)


def test_assess_flags_a_server_from_another_checkout():
    from axibridge_mcp.diagnose import assess
    out = assess(facts(cwd="/Users/x/old/idk.axibridge",
                       command="/Users/x/old/idk.axibridge/.venv/bin/python -m axibridge"), REPO)
    assert any("not this repo" in p for p in out)


def test_assess_flags_a_stale_frontend_build():
    from axibridge_mcp.diagnose import assess
    out = assess(facts(dist_built=time.time() - 7200), REPO)
    assert any("npm run build" in p for p in out)


def test_assess_notes_an_orphan():
    from axibridge_mcp.diagnose import assess
    out = assess(facts(parent="launchd"), REPO)
    assert any("orphan" in p for p in out)


def test_assess_reports_nothing_listening():
    from axibridge_mcp.diagnose import assess
    out = assess(facts(pid=None, error="nothing listening on port 1"), REPO)
    assert out == ["nothing listening on port 1"]


def test_diagnose_tool_on_the_test_server(srv, axb):
    out = text(call(srv, "diagnose"))
    assert "pid" in out and str(REPO) in out


def test_logs_filters_by_text(srv, axb):
    with http(axb) as h:
        h.post("/api/layers/generate", json={"module": "nope", "params": {}})
    r = call(srv, "logs", {"level": "DEBUG", "limit": 500})
    assert not r.is_error, text(r)
    out = text(call(srv, "logs", {"contains": "zzz-not-there"}))
    assert out == "no matching log entries"


def test_sandbox_status_start_seed_stop(srv, targets, axb):
    with http(axb) as h:
        h.post("/api/layers/generate", json={"module": "polygon", "params": {}})
        h.post("/api/project/save", json={"name": "seed-me"}).raise_for_status()
    assert "not running" in text(call(srv, "sandbox", {"action": "status"}))
    r = call(srv, "sandbox", {"action": "start", "seed_project": "seed-me"})
    assert not r.is_error, text(r)
    url = targets.sandbox.url
    assert len(httpx.get(url + "/api/project").json()["layers"]) == 1
    assert "running" in text(call(srv, "sandbox", {"action": "status"}))
    call(srv, "sandbox", {"action": "stop"})
    assert not targets.sandbox.running


def test_first_live_call_carries_the_stale_warning_once(axb):
    from axibridge_mcp.server import build_server
    from axibridge_mcp.targets import Targets
    t = Targets(live_url=axb, stale_check=lambda url: "WARNING: stale test server")
    try:
        srv = build_server(t)
        first = text(call(srv, "state"))
        second = text(call(srv, "state"))
    finally:
        t.close()
    assert first.startswith("WARNING: stale test server")
    assert "WARNING" not in second
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_mcp_dev.py -q`
Expected: FAIL — `ModuleNotFoundError: axibridge_mcp.diagnose`.

- [ ] **Step 3: Write `diagnose.py`**

```python
"""Is the server on a port the code in this repo? Answers the "I restarted it
and nothing changed" class (CLAUDE.md): stale processes, servers running
from another checkout, frontend builds older than their source, orphans.
macOS/Linux via lsof + ps; degrades to an `error` fact without them."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
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


def _run(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, timeout=10).stdout.strip()


def _newest(root: Path, pattern: str) -> tuple[str, float] | None:
    best: tuple[str, float] | None = None
    for p in root.glob(pattern):
        if p.is_file() and "__pycache__" not in p.parts:
            m = p.stat().st_mtime
            if best is None or m > best[1]:
                best = (str(p.relative_to(REPO)), m)
    return best


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
    pids = _run("lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t").split()
    if not pids:
        return Facts(**blank, error=f"nothing listening on port {port}")
    pid = int(pids[0])
    command = _run("ps", "-p", str(pid), "-o", "command=")
    lstart = _run("ps", "-p", str(pid), "-o", "lstart=")
    try:
        started = time.mktime(time.strptime(lstart, "%a %b %d %H:%M:%S %Y"))
    except ValueError:
        started = None
    cwd_lines = _run("lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn").splitlines()
    cwd = next((l[1:] for l in cwd_lines if l.startswith("n")), None)
    ppid = _run("ps", "-p", str(pid), "-o", "ppid=")
    parent = _run("ps", "-p", ppid, "-o", "command=") if ppid else None
    return Facts(pid=pid, command=command, cwd=cwd, started=started, parent=parent,
                 newest_backend=newest_backend, newest_frontend=newest_frontend,
                 dist_built=dist_built, error=None)


def _when(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def assess(f: Facts, repo: Path) -> list[str]:
    if f.error:
        return [f.error]
    problems = []
    where = f.cwd or f.command or ""
    if str(repo) not in where:
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
    f = gather(url)
    if f.error:
        return None
    serious = [p for p in assess(f, REPO) if "orphan" not in p]
    return ("WARNING — live server may be stale: " + "; ".join(serious)) if serious else None


def report(url: str) -> str:
    f = gather(url)
    lines = [f"url {url}"]
    if f.pid is not None:
        lines += [f"pid {f.pid}", f"command {f.command}", f"cwd {f.cwd}",
                  f"started {_when(f.started) if f.started else '?'}", f"parent {f.parent}"]
    if f.newest_backend:
        lines.append(f"newest backend source {f.newest_backend[0]} at {_when(f.newest_backend[1])}")
    lines.append(f"frontend build {_when(f.dist_built) if f.dist_built else 'absent (serving source)'}")
    problems = assess(f, REPO)
    lines.append("problems: none" if not problems else "problems:\n- " + "\n- ".join(problems))
    return "\n".join(lines)
```

Note on the orphan rule: `ps -o command=` of PID 1 prints `/sbin/launchd` on macOS. The check compares the stripped parent command against that set; the unit test passes `"launchd"`.

- [ ] **Step 4: Add seeding to `Sandbox.start`**

Change the signature to `def start(self, timeout: float = 45.0, seed: str | None = None, seed_root: Path | None = None) -> str:` and, at the end of the method just before `return self.url`, add:

```python
        if seed:
            self.seed(seed, seed_root)
        return self.url
```

(also make the early `if self.running:` branch seed when asked: `if self.running: if seed: self.seed(seed, seed_root); return self.url`), and add:

```python
    def seed(self, name: str, root: Path | None) -> None:
        """Copy a saved project folder into the sandbox and open it there."""
        src = (root or Path("~/AxidrawProjects").expanduser()) / name
        if not src.is_dir():
            raise ToolError(f"no saved project folder {src}")
        dest = self.dir / "projects" / name  # type: ignore[operator]
        shutil.copytree(src, dest, dirs_exist_ok=True)
        r = httpx.post(self.url + "/api/project/load",
                       json={"name": name, "recovery_action": "discard"}, timeout=120)
        if r.status_code >= 400:
            raise ToolError(f"sandbox could not open {name}: {r.text[:300]}")
```

- [ ] **Step 5: Write `tools_dev.py`**

```python
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
            except ToolError:
                root = None  # live app down: fall back to ~/AxidrawProjects
        url = sb.start(seed=seed_project, seed_root=root)
        return f"sandbox running at {url}" + (f" with a copy of {seed_project}" if seed_project else "")
```

In `server.py`: add `tools_dev` to imports and `MODULES`; change `main()`'s first line to:

```python
    from .diagnose import stale_warning
    targets = Targets(stale_check=stale_warning)
```

Note: in tests the harness `targets` fixture's live server has its own `projects_root` (set by the harness), and the `sandbox` tool reads it from the live `/api/settings` — so seeding copies from the test server's folder, never Ian's.

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_mcp_dev.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add axibridge_mcp tests/test_mcp_dev.py
git commit -m "feat(mcp): dev tools — logs, diagnose, sandbox, stale-server warning

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Escape hatch — `call_api` with the motion blocklist

**Files:**
- Create: `axibridge_mcp/tools_api.py`
- Modify: `axibridge_mcp/server.py` (`MODULES`)
- Test: `tests/test_mcp_api.py`

**Interfaces:**
- Produces: `tools_api.normalize(path: str) -> str` (decoded, single-slashed, dot-segments resolved, no trailing slash, no query); `tools_api.check_allowed(method: str, path: str, target: str) -> None` (raises `ToolError`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_api.py`:

```python
import pytest

from _mcp_harness import axb, call, images, srv, targets, text  # noqa: F401

BLOCKED = ["/api/machine/jog", "/api/machine/pen", "/api/machine/goto", "/api/machine/origin",
           "/api/machine/raw", "/api/machine/block", "/api/plot/start", "/api/plot/resume",
           "/api/calibration/teststroke", "/api/calibration/holder/mark"]
# Review Focus 2: spellings that reach the same route
SNEAKY = ["/api/machine/%6Aog", "/api/machine/jog/", "//api/machine/jog",
          "/api/layers/../machine/jog", "/api/machine/jog?x=1", "/api/machine/%2E%2E/machine/jog"]


@pytest.mark.parametrize("path", BLOCKED + SNEAKY)
def test_motion_paths_are_refused_on_every_target(path):
    from mcp.server.mcpserver.exceptions import ToolError
    from axibridge_mcp.tools_api import check_allowed
    for target in ("live", "sandbox"):
        with pytest.raises(ToolError, match="refused"):
            check_allowed("POST", path, target)


def test_restart_is_refused_on_live_only():
    from mcp.server.mcpserver.exceptions import ToolError
    from axibridge_mcp.tools_api import check_allowed
    with pytest.raises(ToolError):
        check_allowed("POST", "/api/server/restart", "live")
    check_allowed("POST", "/api/server/restart", "sandbox")


def test_paths_must_be_api_paths():
    from mcp.server.mcpserver.exceptions import ToolError
    from axibridge_mcp.tools_api import check_allowed
    with pytest.raises(ToolError):
        check_allowed("GET", "/index.html", "live")


def test_call_api_get_returns_json_text(srv):
    r = call(srv, "call_api", {"method": "GET", "path": "/api/pens"})
    assert not r.is_error, text(r)
    assert text(r).startswith("200")


def test_call_api_lowercase_method_is_still_checked(srv):
    r = call(srv, "call_api", {"method": "post", "path": "/api/machine/jog", "body": {"dx": 1}})
    assert r.is_error and "refused" in text(r)


def test_call_api_truncates_big_responses(srv):
    r = call(srv, "call_api", {"method": "GET", "path": "/api/state", "max_chars": 500})
    assert "truncated" in text(r)


def test_call_api_passes_png_through_as_an_image(srv, axb):
    import httpx
    httpx.post(axb + "/api/layers/generate", json={"module": "polygon", "params": {}})
    r = call(srv, "call_api", {"method": "GET", "path": "/api/animation/preview.png"})
    if r.is_error:
        pytest.skip(f"preview.png needs an animation here: {text(r)[:120]}")
    assert images(r)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_mcp_api.py -q`
Expected: FAIL — `ModuleNotFoundError: axibridge_mcp.tools_api`.

- [ ] **Step 3: Write `tools_api.py`**

```python
"""call_api: the long tail of the HTTP API, minus anything that moves the
machine. Paths are normalised BEFORE the check and the normalised path is
what gets sent, so no spelling reaches a blocked route."""

from __future__ import annotations

import json
import posixpath
import re
from typing import Annotated, Any, Literal
from urllib.parse import unquote, urlsplit

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
    raw = urlsplit(path).path
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
```

In `server.py`: add `tools_api` to imports and `MODULES`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_mcp_api.py -q`
Expected: PASS (the PNG test may skip).

- [ ] **Step 5: Commit**

```bash
git add axibridge_mcp tests/test_mcp_api.py
git commit -m "feat(mcp): call_api escape hatch with a normalised motion blocklist

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: UI eyes — `see_ui`

**Files:**
- Create: `axibridge_mcp/ui.py`
- Modify: `axibridge_mcp/tools_look.py` (add `see_ui`)
- Test: `tests/test_mcp_ui.py`

**Interfaces:**
- Produces: `ui.UiStep` (pydantic model: `action: Literal["click","fill","press","wait"]`, `selector: str | None`, `text: str | None`, `ms: int` 0–5000); `ui.screenshot(base_url: str, tab: str | None, steps: list[UiStep], width: int, height: int) -> bytes`.
- UI facts: tabs are `<button data-tab="compose|assets|plot|pens|settings">`; the app has booted when `#gen-select` has options.
- Threading: MCPServer runs sync tools in a worker thread (anyio.to_thread), which has no asyncio loop, so `sync_playwright()` is safe there. Keep it function-scoped (CLAUDE.md).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_ui.py`:

```python
import io

import pytest

from _mcp_harness import axb, call, images, srv, targets, text  # noqa: F401

pytest.importorskip("playwright.sync_api")


def test_see_ui_screenshots_a_tab(srv):
    r = call(srv, "see_ui", {"tab": "plot", "width": 1200, "height": 800})
    if r.is_error and "chromium" in text(r):
        pytest.skip(text(r))
    assert not r.is_error, text(r)
    from PIL import Image
    assert Image.open(io.BytesIO(images(r)[0])).size == (1200, 800)


def test_see_ui_reports_a_missing_selector_readably(srv):
    r = call(srv, "see_ui", {"steps": [{"action": "click", "selector": "#does-not-exist"}]})
    if "chromium" in text(r):
        pytest.skip(text(r))
    assert r.is_error and "#does-not-exist" in text(r)


def test_see_ui_rejects_unknown_tabs(srv):
    assert call(srv, "see_ui", {"tab": "kitchen"}).is_error
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_mcp_ui.py -q`
Expected: FAIL — unknown tool.

- [ ] **Step 3: Write `ui.py`**

```python
"""The agent's eyes on the interface: headless Chromium against a target's
UI, for dogfooding. Mac bench only (needs `playwright install chromium`).
Clicks are real: on `live` they edit Ian's project — prefer the sandbox."""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field


class UiStep(BaseModel):
    action: Literal["click", "fill", "press", "wait"]
    selector: str | None = None
    text: str | None = None
    ms: int = Field(default=500, ge=0, le=5000)


def screenshot(base_url: str, tab: str | None, steps: list[UiStep],
               width: int, height: int) -> bytes:
    try:
        from playwright.sync_api import Error as PwError, sync_playwright
    except ImportError:
        raise ToolError("playwright isn't installed in the venv") from None
    with sync_playwright() as p:  # function-scoped on purpose (CLAUDE.md)
        try:
            browser = p.chromium.launch(headless=True)
        except PwError as e:
            raise ToolError("no chromium — run `.venv/bin/python -m playwright install chromium` "
                            f"({str(e)[:120]})") from None
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(base_url, wait_until="domcontentloaded")  # SSE: never networkidle
            page.wait_for_function(
                "() => document.querySelectorAll('#gen-select option').length > 0",
                timeout=20_000)
            if tab:
                page.click(f'button[data-tab="{tab}"]', timeout=5_000)
            for i, step in enumerate(steps, 1):
                try:
                    if step.action == "click":
                        page.click(step.selector or "", timeout=5_000)
                    elif step.action == "fill":
                        page.fill(step.selector or "", step.text or "", timeout=5_000)
                    elif step.action == "press":
                        page.keyboard.press(step.text or "")
                    page.wait_for_timeout(step.ms if step.action == "wait" else 150)
                except PwError as e:
                    raise ToolError(f"step {i} ({step.action} {step.selector or step.text}) "
                                    f"failed: {str(e).splitlines()[0][:200]}") from None
            return page.screenshot()
        finally:
            browser.close()
```

- [ ] **Step 4: Add `see_ui` to `tools_look.py`**

Add `from .ui import UiStep, screenshot` to the imports, and inside `register`:

```python
    @tool
    def see_ui(target: TargetName = "live",
               tab: Literal["compose", "assets", "plot", "pens", "settings"] | None = None,
               steps: list[UiStep] | None = None,
               width: Annotated[int, Field(ge=800, le=2560)] = 1440,
               height: Annotated[int, Field(ge=600, le=1600)] = 900) -> list:
        """Screenshot the app's UI in a headless browser, optionally after
        switching tab and running steps (click/fill/press/wait). This is a
        separate browser, not Ian's window — but clicks are real edits on the
        target, so dogfood on the sandbox."""
        c = targets.client(target)
        data = screenshot(c.base_url, tab, steps or [], width, height)
        return [f"{target} UI{f' — {tab} tab' if tab else ''}", png(data)]
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_mcp_ui.py -q`
Expected: PASS (or SKIP without chromium).

- [ ] **Step 6: Commit**

```bash
git add axibridge_mcp tests/test_mcp_ui.py
git commit -m "feat(mcp): see_ui screenshots the interface for dogfooding

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Wiring, docs, full verification

**Files:**
- Create: `.mcp.json`, `docs/MCP.md`, `tests/test_mcp_wiring.py`
- Modify: `CLAUDE.md` ("Where things live" table), `~/_SecondBrain/02_Areas/__claude/CHANGES.md` (new entry at the top of the entries)

**Interfaces:**
- Consumes: everything above. The complete tool roster is: `state, see, see_ui, modules, module_schema, try_generator, try_effects, add_layer, edit_layer, delete_layers, reorder_layers, undo, redo, project, save_project, estimate, plot, pen, jog, go_home, stop, pause, logs, diagnose, sandbox, call_api` (26).

- [ ] **Step 1: Write the failing wiring tests**

Create `tests/test_mcp_wiring.py`:

```python
"""The real entry point over stdio — what Claude Code actually launches."""

import os
import sys
import time

import anyio
import httpx

from _mcp_harness import REPO, axb, text  # noqa: F401
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters

ROSTER = {"state", "see", "see_ui", "modules", "module_schema", "try_generator", "try_effects",
          "add_layer", "edit_layer", "delete_layers", "reorder_layers", "undo", "redo",
          "project", "save_project", "estimate", "plot", "pen", "jog", "go_home", "stop",
          "pause", "logs", "diagnose", "sandbox", "call_api"}


def params(axb):
    return StdioServerParameters(command=sys.executable, args=["-m", "axibridge_mcp"],
                                 env={**os.environ, "AXIBRIDGE_MCP_LIVE_URL": axb}, cwd=str(REPO))


def test_stdio_server_lists_the_full_roster(axb):
    async def go():
        async with Client(params(axb)) as c:
            return {t.name for t in (await c.list_tools()).tools}
    assert anyio.run(go) == ROSTER


def test_stdio_exit_stops_the_sandbox(axb):
    # Review Focus 5: Claude Code closing the session must not leak a server
    async def go():
        async with Client(params(axb)) as c:
            out = await c.call_tool("sandbox", {"action": "start"})
            return text(out)
    out = anyio.run(go)
    url = out.split("running at ")[1].split()[0]
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            httpx.get(url + "/api/project", timeout=0.5)
            time.sleep(0.3)
        except httpx.HTTPError:
            return
    raise AssertionError(f"sandbox at {url} survived the MCP process")
```

If `StdioServerParameters` lives elsewhere in 2.3, find it with `grep -rn "class StdioServerParameters" .venv/lib/python3.13/site-packages/mcp/` and fix the import.

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_mcp_wiring.py -q`
Expected: PASS if Tasks 3–9 registered everything. If the roster differs, the set difference names the missing/extra tool. If the sandbox survives: the stdio client closes stdin then sends SIGTERM; `main()`'s SIGTERM handler raises `SystemExit`, which runs `atexit` → `targets.close()`. If the SDK kills with SIGKILL instead, add a watchdog in `Sandbox.start` — pass `AXIBRIDGE_PARENT_WATCH=<mcp pid>` is NOT available in axibridge, so instead start the sandbox in its own process group (`start_new_session=True`) and in `server.main()` wrap `run("stdio")` in `try/finally: targets.close()`, which runs when stdin closes and `run` returns.

- [ ] **Step 3: Register the server for Claude Code**

Create `.mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "axibridge": {
      "command": "/Users/ianduclos/_SecondBrain/02_Areas/_Coding/idk.axibridge/.venv/bin/python",
      "args": ["-m", "axibridge_mcp"]
    }
  }
}
```

(Absolute Mac path on purpose: the Pi clone never installs the extra, and a relative command would depend on Claude Code's launch cwd.)

- [ ] **Step 4: Write `docs/MCP.md`**

```markdown
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
  a saved project. Use it for dev checks, experiments and `see_ui` clicking.

## Safety

- `plot`, `pen`, `jog`, `go_home` move the machine. They refuse the sandbox,
  and they must never be added to an allow-list: Claude Code asks Ian every
  time. `plot` needs the `revision` from `estimate` and refuses if the
  project changed since — show Ian `see` + `estimate` first.
- `stop` and `pause` are always safe.
- `call_api` refuses machine motion, calibration and (on live) server
  restart, after normalising the path (percent-encoding, dot segments,
  slashes).
- `project(new|open)` on a dirty project fails with "unsaved work" unless
  given `recovery_action`; on live prefer "recover", never "discard" unless
  Ian said so.
- Known caveat: on the `pi_ssh` backend, `stop(return_home=True)` does not
  actually move the carriage home (dead-reckoned position never changes);
  tracked separately.

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
```

- [ ] **Step 5: Add the CLAUDE.md row**

In `CLAUDE.md`'s "Where things live" table, after the "Bottom timeline bar" row:

```markdown
| MCP server for agents (live/sandbox targets, see/compose/tune/diagnose; motion tools always prompted) + live sync (`edit_rev`, `project` SSE event) | `axibridge_mcp/`, `docs/MCP.md` |
```

- [ ] **Step 6: Announce the boundary change**

Add to `~/_SecondBrain/02_Areas/__claude/CHANGES.md`, as the newest entry (match the existing entry format exactly — read the top two entries first):

```markdown
### 2026-10-12 — idk.axibridge — MCP server + live-sync project events (claude)
- affects: anything subscribing to axibridge's `/api/events` or reading `/api/project`; agents on the Mac bench.
- detail: New `axibridge_mcp/` stdio MCP server (Mac-only `[mcp]` extra, registered in the repo's `.mcp.json`) with `live`/`sandbox` targets; motion tools are live-only and never allow-listed. App side: `/api/project` gains `edit_rev` (monotonic, distinct from the recovery `revision`), and every mutating request that changes the project emits `{"type": "project", "rev", "origin"}` on `/api/events`, `origin` echoing the `X-Axb-Client` request header. Consumers that ignore unknown event types are unaffected. Docs: `docs/MCP.md`.
```

- [ ] **Step 7: Commit**

```bash
git add .mcp.json docs/MCP.md CLAUDE.md tests/test_mcp_wiring.py
git commit -m "feat(mcp): register the server, document it, verify the stdio entry point

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(CHANGES.md lives outside this repo and is not committed here.)

---

### Task 11: Freshness guards — keep the MCP current while the app changes

The app is still in active development (Ian, 2026-10-12). This task makes drift between the app and the MCP **fail loudly in the normal suite**, names what to fix, and tells the agent when its own MCP process is out of date. Nothing here needs a running server.

**Files:**
- Create: `tests/test_mcp_freshness.py`
- Modify: `axibridge_mcp/__init__.py` (record start time), `axibridge_mcp/diagnose.py` (`mcp_self_warning`), `axibridge_mcp/server.py` (`make_tool_decorator`), `CLAUDE.md` (conventions bullet), `docs/MCP.md` ("Keeping it fresh" section)

**Interfaces:**
- Produces: `axibridge_mcp.STARTED: float` (import time of the package); `diagnose.mcp_self_warning() -> tuple[str, float] | None`, giving (message, newest source mtime) when any `axibridge_mcp/*.py` is newer than `STARTED`.
- Consumes: `axibridge.app.create_app().openapi()` (in-process, no server), `tools_api.check_allowed`, `server.build_server`, `targets.Targets`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_freshness.py`:

```python
"""Keeps the MCP honest while the app changes under it. In-process, no
server: an app change that strands a tool fails HERE, naming the tool file
and the endpoint, in the same suite run as the change itself."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="mcp extra not installed (backend-only machine)")

import anyio  # noqa: E402
from mcp.client.client import Client  # noqa: E402

from axibridge.app import create_app  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MCP_DIR = REPO / "axibridge_mcp"
# '/api/...' in a plain or f-string literal; stops at a quote, query or space
LITERAL = re.compile(r"""["'](/api/[^"'?\s]*)""")
PARAM = re.compile(r"\{[^}]+\}")
# control endpoints that are safe by design (stopping is the safe direction)
SAFE_CONTROL = {"/api/plot/stop", "/api/plot/pause"}
# path segments that smell like machine motion. A non-GET route containing one
# must be refused by call_api or listed in REVIEWED_NOT_MOTION with a reason.
MOTION_WORDS = {"machine", "plot", "jog", "goto", "home", "pen", "motor", "motors",
                "raw", "calibration", "teststroke", "servo"}
REVIEWED_NOT_MOTION: dict[str, str] = {
    # "/api/example/plot-preview": "renders an image, never touches the machine",
}


def app_routes() -> set[tuple[str, str]]:
    spec = create_app().openapi()
    return {(method.upper(), PARAM.sub("{}", path))
            for path, ops in spec["paths"].items() for method in ops}


def used_paths() -> dict[str, set[str]]:
    used: dict[str, set[str]] = {}
    for f in sorted(MCP_DIR.glob("*.py")):
        for m in LITERAL.finditer(f.read_text()):
            path = PARAM.sub("{}", m.group(1)).rstrip("/")
            if path == "/api":  # tools_api's prefix check, not an endpoint
                continue
            used.setdefault(path, set()).add(f.name)
    return used


def test_the_mcp_finds_its_endpoints():
    # guards the guard: if the literal scan breaks, the drift test passes vacuously
    used = used_paths()
    assert "/api/project" in used and "/api/layers/{}/regenerate" in used


def test_every_endpoint_the_mcp_calls_still_exists():
    routes = {path for _, path in app_routes()}
    missing = {p: sorted(files) for p, files in used_paths().items() if p not in routes}
    assert not missing, (
        "the MCP calls endpoints the app no longer has — fix the tool in the same change:\n"
        + "\n".join(f"  {p}  (used in {', '.join(files)})" for p, files in sorted(missing.items())))


def test_every_motion_shaped_endpoint_is_refused_by_call_api():
    from mcp.server.mcpserver.exceptions import ToolError
    from axibridge_mcp.tools_api import check_allowed

    unguarded = []
    for method, path in sorted(app_routes()):
        segments = set(path.strip("/").split("/"))
        if method == "GET" or not segments & MOTION_WORDS:
            continue
        if path in SAFE_CONTROL or path in REVIEWED_NOT_MOTION:
            continue
        if path == "/api/pens" or path.startswith("/api/pens/"):
            continue  # the pen LIBRARY (names, colours), not the pen servo
        try:
            check_allowed(method, path.replace("{}", "x"), "sandbox")
        except ToolError:
            continue
        unguarded.append(f"{method} {path}")
    assert not unguarded, (
        "new motion-shaped endpoints reachable through call_api — block them in "
        "tools_api._MOTION, or add them to REVIEWED_NOT_MOTION with a reason:\n  "
        + "\n  ".join(unguarded))


def tool_names() -> set[str]:
    from axibridge_mcp.server import build_server
    from axibridge_mcp.targets import Targets

    t = Targets(live_url="http://127.0.0.1:9")  # never contacted: listing is local

    async def go():
        async with Client(build_server(t)) as c:
            return {tool.name for tool in (await c.list_tools()).tools}
    try:
        return anyio.run(go)
    finally:
        t.close()


def test_the_docs_name_every_tool():
    doc = (REPO / "docs" / "MCP.md").read_text()
    missing = sorted(n for n in tool_names() if f"`{n}`" not in doc)
    assert not missing, f"docs/MCP.md doesn't mention: {missing}"


def test_every_tool_has_a_docstring_the_agent_can_read():
    async def go():
        from axibridge_mcp.server import build_server
        from axibridge_mcp.targets import Targets
        t = Targets(live_url="http://127.0.0.1:9")
        try:
            async with Client(build_server(t)) as c:
                return [(x.name, x.description or "") for x in (await c.list_tools()).tools]
        finally:
            t.close()
    thin = [name for name, desc in anyio.run(go) if len(desc.strip()) < 20]
    assert not thin, f"tools without a real description: {thin}"


def test_the_mcp_notices_its_own_source_changed(tmp_path, monkeypatch):
    import axibridge_mcp
    from axibridge_mcp import diagnose

    assert diagnose.mcp_self_warning() is None or axibridge_mcp.STARTED < time.time()
    monkeypatch.setattr(axibridge_mcp, "STARTED", time.time() - 10_000)
    hit = diagnose.mcp_self_warning()
    assert hit is not None and "/mcp" in hit[0]
```

- [ ] **Step 2: Run to verify which fail**

Run: `.venv/bin/python -m pytest tests/test_mcp_freshness.py -q`
Expected: `test_the_mcp_notices_its_own_source_changed` FAILS (`STARTED` / `mcp_self_warning` missing). The drift, motion and docs tests should already PASS. If the drift test fails now, a tool from Tasks 3–9 uses a computed path or a wrong one; fix the tool. If the motion test fails, a real endpoint is unguarded; block it in `_MOTION` before going on.

- [ ] **Step 3: Record the MCP's own start time**

Append to `axibridge_mcp/__init__.py`:

```python

import time as _time

#: when this MCP process loaded its code. diagnose.mcp_self_warning compares
#: it with the source files, because Claude Code keeps the MCP process alive
#: across edits to axibridge_mcp/ until someone reconnects it with /mcp.
STARTED = _time.time()
```

- [ ] **Step 4: Add `mcp_self_warning` to `diagnose.py`**

```python
def mcp_self_warning() -> tuple[str, float] | None:
    """(message, newest mtime) when this MCP process predates its own source."""
    import axibridge_mcp

    newest = _newest(REPO / "axibridge_mcp", "*.py")
    if newest is None or newest[1] <= axibridge_mcp.STARTED:
        return None
    return (f"WARNING — this MCP server is older than its source ({newest[0]} changed at "
            f"{_when(newest[1])}); reconnect it with /mcp to load the change", newest[1])
```

- [ ] **Step 5: Surface it from every tool, once per change**

Replace `make_tool_decorator` in `server.py` with:

```python
def make_tool_decorator(srv: MCPServer, targets: Targets):
    """Register fn as an unstructured tool. Its result gets prefixed with the
    one-time stale-live-server warning (Targets.client) and, once per source
    change, a warning that this MCP process itself is out of date."""
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
```

- [ ] **Step 6: Write down the rule**

In `CLAUDE.md` under "Conventions & invariants", add:

```markdown
- **The MCP follows the API, in the same change** (`axibridge_mcp/`,
  `docs/MCP.md`). Renaming or removing an endpoint the MCP calls fails
  `tests/test_mcp_freshness.py` with the tool file named: fix the tool in the
  same commit. A new non-GET endpoint whose path smells like motion
  (`machine`, `plot`, `jog`, `home`, `calibration`, …) fails the same file until
  it is blocked in `tools_api._MOTION` or listed as reviewed. New generators
  and effects need no MCP change, since tools read modules and schemas live. Add a
  dedicated tool only when `call_api` use of an endpoint becomes routine,
  and name it in `docs/MCP.md` (a test checks the roster). After editing
  `axibridge_mcp/`, reconnect with `/mcp`; tools warn until you do.
```

In `docs/MCP.md`, add before "## Live sync (app side)":

```markdown
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
```

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_mcp_freshness.py tests/test_mcp_foundation.py tests/test_mcp_dev.py -q`
Expected: PASS. (`test_first_live_call_carries_the_stale_warning_once` must still see the warning first: the self-warning appends after it.)

- [ ] **Step 8: Commit**

```bash
git add axibridge_mcp tests/test_mcp_freshness.py CLAUDE.md docs/MCP.md
git commit -m "test(mcp): freshness guards for API drift, motion endpoints and docs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Full verification and hand-back

- [ ] **Step 1: Full verification**

Run, in order:

```bash
npm run build
npm run typecheck
.venv/bin/python -m pytest -q
```

Expected: build and typecheck clean; the full suite passes with only the known skips (one native-launch skip, plus any chromium skips). Record the pass/skip counts for the wrapup. Nothing to commit unless a fix was needed (then commit it as `fix(mcp): …`).

- [ ] **Step 2: Hand back to Ian (do not do these yourself)**

Report, and ask before acting on each:

1. **Activation:** the live app runs the pre-live-sync backend and frontend. Activating means restarting through `AxiBridge.app` after preserving its open project (CLAUDE.md "Desktop delivery" rules) — ask first.
2. **Allow-list proposal:** offer to add the non-motion tools to `.claude/settings.local.json` as `mcp__axibridge__<name>` allow rules (`state, see, see_ui, modules, module_schema, try_generator, try_effects, logs, diagnose, estimate, stop, pause`), and show the exact diff. Editing tools (`add_layer`, …) and every motion tool stay prompted unless Ian says otherwise. Settings are shared config: preview, then wait for a go.
3. **Loading it:** Claude Code must be restarted (or `/mcp`) in this repo to pick up `.mcp.json`.
4. **Not verified by tests:** how live sync feels in the native window during real drags, and plotting through the MCP on real hardware. Both are Ian's to check.
```
