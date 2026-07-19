# CLAUDE.md — operational context for working in this repo

axibridge: full-stack layer-compositing control surface for an AxiDraw V3
pen plotter. FastAPI + Pydantic v2 server owns the serial port; zero-build
vanilla-ES-module frontend; SSE for one-way progress. Design rationale lives
in `ARCHITECTURE.md`; module authoring in `docs/MODULES.md` — read those
before structural changes.

## Run / test

```bash
.venv/bin/python -m axibridge          # serves on 0.0.0.0:2942
.venv/bin/python -m pytest -q          # hardware-free suite (simulator)
```

- The venv at `.venv/` is the pinned interpreter — it has `pyaxidraw`
  installed (NOT on PyPI; see `launch/axibridge.command` for the install URL).
  Never "fix" an import error by switching interpreters.
- Frontend has no build step: edit `axibridge/static/**`, reload the browser.
- Tests isolate machine-level stores via `AXIBRIDGE_CONFIG_DIR`
  (set in `tests/conftest.py` before any axibridge import — keep it first).
- UI smoke-testing with Playwright: use `wait_until="domcontentloaded"`;
  the SSE stream keeps connections open so `networkidle` never fires.

## Where things live

| Concern | File |
|---|---|
| IPR (geometry⇄execution contract) | `axibridge/model.py` (`PathDocument`) |
| Layer model + compositor (resolve, occlusion masks) | `axibridge/compose.py` |
| One open project + the resolve pipeline + undo history | `axibridge/session.py` |
| Image assets (depth maps, `clip#NNNN` frame sequences) | `axibridge/assets.py` |
| Module registry (Source / Effect / Transform) | `axibridge/registry.py` |
| Layer interpolation (tween layers, param/affine lerp; the master timeline scrubs `follow_master` tweens via `session.resolved(master_t=…)`) | `axibridge/tween.py` |
| Generators / effects / plot-pass ops | `axibridge/sources/` `effects/` `transforms/` |
| Backends (native / simulator / saxi) + port arbitration | `axibridge/backends/`, `machine.py` |
| Pen library & machine settings (global JSON stores) | `axibridge/stores.py` |
| Roadmap / future direction | `ROADMAP.md` |
| Project folder save/load/zip | `axibridge/project_io.py` |
| Global scrap library (workbench "keep this" saves, `~/.axibridge/scraps/`) | `axibridge/scraps.py` |
| HTTP API | `axibridge/api.py` |
| Canvas editor / tabs | `axibridge/static/js/canvas.js`, `compose.js`, `plot.js`, … |

## Conventions & invariants (break these and the tool lies)

- **Single resolve path**: preview, estimates, and plotting all flow through
  `session.resolved*()` → `compose.resolve_project()`. Never add a second
  geometry path to the plotter.
- Resolve order is `occlusion(regions(effects(transform(source))))` —
  effects run in paper space (mm params stay mm at any layer scale); region
  layers then clip+effect everything below them, post-effect/pre-occlusion,
  bottom→top. Don't reorder. See ARCHITECTURE.md "Resolve order" for why.
- Coordinates: millimetres, machine frame (x right ≤300, y down ≤218),
  origin at carriage home. View rotation is display-only (`canvas.js`).
- Effects/transforms must be pure (never mutate input paths) and preserve
  `Path.filled` + closure (first==last) — occlusion masks depend on both.
- New module kinds register via decorator + drop-in file; params are Pydantic
  models whose JSON Schema auto-renders UI controls (`static/js/forms.js`).
  Bound every numeric field — unbounded values reach an open-loop machine.
- Backend `deactivate()` MUST release the serial port / kill subprocesses;
  `MachineManager.select_backend` is the only switching point.
- **pyaxidraw options are ints.** `NativeAxidrawBackend._apply` casts every
  numeric option with `int(round())` — a float reaches EBB command strings
  verbatim (`SP,1,253.0,1`), firmware rejects it, and the stray reply
  desynchronises plotink's serial bookkeeping ("USB lost" on a healthy
  link). Never remove the cast or set `ad.options.*` anywhere else.
- **Undo discipline**: every `Session` method that mutates the project MUST
  call `self._checkpoint()` once, under `self._lock`, before mutating —
  and rely on module purity (geometry lists are shared by reference, never
  mutated in place; they are only ever replaced wholesale). The one sanctioned
  exception is `coalesce`: pass a stable key (e.g. `("regen", layer_id)`) to
  `_checkpoint()` and consecutive checkpoints with the same key fold into one
  undo entry — this is how a latched live-edit run (drag a slider, drag a pen
  anchor) becomes a single ⌘Z instead of one per intermediate value. Never
  coalesce across different layers/fields under one key.
- Image assets live in the `assets.asset_store` singleton (name → bytes,
  cached grayscale/alpha); they travel in the project folder's `assets/`.
  Effects/generators reference them by name via a string param with
  `json_schema_extra={"format": "asset"}` (renders as dropdown + upload).
- `estimate.py` is an estimator, never a motion planner.
- In the svgelements-based reader, mm conversion uses svgelements' own
  constant (`_SE_PX_PER_MM` ≠ 96/25.4) — required for exact save/load
  reproducibility. vpype conversions keep 96/25.4.

## Hardware notes

- Real AxiDraw on `/dev/cu.usbmodem*` (macOS), firmware 2.7.0. Keep the test
  suite hardware-free; hardware checks are run manually (connect, firmware
  string, pen cycle, small jogs). Raw EBB commands bypass soft limits and
  desync dead reckoning by design.
- **Mac → Pi workflow**: the AxiDraw can hang off a Raspberry Pi (`ssh idkpi`
  over Tailscale; EBB on `/dev/ttyACM0`; AxiDraw API venv at
  `~/axibridge/.venv`, NOT a full axibridge install — its old systemd unit is
  stopped/disabled on purpose). Use the **"AxiDraw via Pi (ssh)"** backend
  (`backends/pi_ssh.py`): plot = resolved SVG → scp → `axicli`; pen/jog are
  short `axicli -m manual` calls. Carriage must start at the home corner.
  Motors need the barrel-jack PSU; without it axicli "plots" silently with
  nothing moving — useful for dry runs, confusing if unexpected.

## Current handoff (July 2026)

- Read `STATUS.md` (state) and `HANDOFF.md` (mid-flight work) first — the
  wrapup skill keeps them current; this section only holds durable
  operating notes.
- The repo lives on GitHub (`github.com/ianduclos/idk.axibridge`, private);
  `main` is the shared trunk with a full dev clone on idkpi
  (`~/idk.axibridge`). The `.claude/skills/pi` skill is the runbook for
  Pi work and scheduled unattended Claude runs; keep Mac and Pi in
  lockstep after merges.
- The generator/effect direction (uncanny, Cohen, Oehlen regime collision)
  is documented in `docs/IDEAS-generators.md` + `docs/IDEAS-oehlen-pass.md`
  with shipped/pending ledgers; the ROADMAP's "Oehlen pass" section is the
  build order. Region layers changed the resolve order — see
  ARCHITECTURE.md "Resolve order" before touching compose.py.
- `launch/AxiBridge.app` is the normal user restart path. Do not spin up
  random long-lived servers unless a test explicitly needs a temporary port.
  The app bundle should use `Contents/Resources/AxiBridge.icns`, generated
  from `axibridge/static/favicon.png`.
- **Open architecture questions are deliberately left open** — Ian wants
  breadth of future options kept, not decisions forced early; well-mapped,
  modular code is meant to carry that weight instead. The live ones (the IPR
  carrying no explicit hole *field* — occlusion and hatch_fill both already
  reassemble nesting-derived holes correctly as of 2026-07-10, that part is
  settled, only a first-class representation is open; the node-editor
  question; the unsaved-work autosave guard) are tracked in ROADMAP.md's "Far /
  undecided" and "Documentation / robustness debts" sections, each with the
  criterion for when to revisit. Don't resolve one implicitly as a side
  effect of an unrelated change — if a task forces the issue, stop and flag
  it rather than picking a side.
