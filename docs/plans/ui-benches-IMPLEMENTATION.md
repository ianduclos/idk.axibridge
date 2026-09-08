# Compose and expandable benches implementation plan

Approved 8 September 2026: “ok i like it. go”, after selecting popup by default.

**Goal:** implement the reviewed Compose hierarchy and expandable popup benches,
with specialised interaction and a small open registration/lifecycle seam.
**Spec:** ../design/ui-benches-2026-09-07/PROPOSAL.md. D1–D4 now accepted for this
bounded pass. Durable recovery and speculative application integrations remain out.
**Stack:** existing vanilla ES modules, FastAPI/Pydantic, existing Vite build and
source fallback. No new dependency, hardware action, push or app restart.

## Responsibilities and invariants

Primary owns frontend contracts, layout, integration and acceptance. Sol owns
registry descriptors and module guide; Terra owns a separate UI regression file.
Preserve ordinary bench shared params, read-only Watch, Second Reading local draft
undo, exact recipe Keep, generator purity, single resolve path, coordinate frames,
and the existing project mutation callbacks. Popup expansion changes no recipe.

## Tasks

1. [x] Registry: SourceModule optional `bench` descriptor with adapter, version,
   modes. Validate shape; explicit non-axis bench allowed; compatibility fallback
   intervention+branch then effective axis. Tests in test_bench_descriptor.py.
2. [x] Shared frontend: bench_registry.js resolves descriptors into registered local
   adapters; bench_host.js owns popup focus/inertness, expand/restore, compact
   controls, origin, return affordance and local error/retry. It must not know
   branch/event schema. Future adapters register without changing host dispatch.
3. [x] Process adapter: preserve params object and write callback. Render identity
   guards and exact-preview creation gate; local retry; observed Homeostat numeric
   telemetry. Existing axis fallback and read-only Watch remain.
4. [x] Second Reading adapter: move unchanged control nodes into stage/action/sidebar
   regions; local error surface; optional reference comparison from exact recipes.
   Same-page draft retention, pending settings, human capture and history retained.
5. [x] Compose: selected detail before new material, retain latch scope visibly,
   metadata-based Benches picker group, narrow default sidebar, persistent compact
   layer list with expansion. Keep existing operation IDs and handlers.
6. [x] Verify: new UI regressions first red then green; existing UI suite; full
   hardware-free suite, build/typecheck; isolated source-only browser smoke and
   screenshots at 1440/1100/900/700 plus expanded controls and failures.
7. [x] Review integrated diff, update architecture/module notes and status/handoff,
   commit verified checkpoint. Native feel/physical output remain owner acceptance.

## Test contracts

UI test fixtures use temporary config and simulator, never the user's running app.
Assert popup Expand/Restore leaves `process-recipe` unchanged; focus stays inside
except explicit hardware Stop; Escape cancels capture before closing. Fail preview:
local error visible, exact Keep/Create disabled, retry same recipe without new turn.
Delay old previews: newer intent alone may paint/enable promotion. Watch scrubs must
leave API project bytes unchanged. Compact sheets fit both dimensions; controls
scroll without clipping, primary actions remain reachable. Test ordinary declared
axis, effective frame fallback and explicit non-axis registration separately.

The backend descriptor is `{adapter: string, version: positive int, modes: string[]}`,
with new/watch/resume modes. Initial adapters process, homeostat and second-reading, version 1.
Unknown adapters show a named unavailable reason rather than assuming an event
contract. Application writes remain caller callbacks; no hidden service mutations.


## Implemented boundary

The shared host is a small lifecycle wrapper around existing adapters/callbacks,
not the full future factory/services sketch. Homeostat owns its grouped form schema;
telemetry plots only preview samples actually observed, with no invented full trace.
Unkept Second Reading drafts remain memory-only, explicitly labelled, and clear on
project replacement. Durable recovery, unified loss prompts and server revision /
mutation reconciliation remain deferred. Evidence: ../../shots/ui-benches-0908/README.md.

Final verification: 1,285 tests passed (107 browser), build/typecheck passed,
isolated source-only smoke and comparison checks passed. No browser page errors.
