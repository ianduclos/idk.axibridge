> Supporting review evidence. The primary review in REVIEW.md owns prioritization, interpretation and final recommendations. Source-only findings are not independently reproduced unless stated.

# AxiBridge UI architecture evidence audit

Scope: read-only source and documentation audit, 2026-09-07. No server was
started and no interaction was run. “Observed” means the cited source directly
establishes the condition; “hypothesis” means the user-facing failure needs a
timed or dense real interaction to reproduce. The single resolve path and the
rule that Plot reflects the canvas must remain intact.

## 1. The geometry authority is correctly singular — preserve it

**Status: observed strength.** `Session.resolved()` locks, materializes only
ephemeral timeline overlays, and calls `compose.resolve_project()`
([session.py:2888-2917](../../../axibridge/session.py)). The resolved endpoint uses that result
([api.py:1104-1168](../../../axibridge/api.py)); plot documents call it too
([session.py:3077-3085](../../../axibridge/session.py)). This implements the stated contract
([ARCHITECTURE.md:61-65](../../../ARCHITECTURE.md)).

**Consequence.** Preview, estimate, and plotting have a defensible common
geometry authority, including an occluded “plot this layer.”

**Smallest response.** Treat this as a non-negotiable acceptance invariant for
every UI repair below; do not introduce client-side geometry or a shortcut plot
route. **Acceptance:** a selected occluded layer has the same clipped paths in
the canvas payload, estimate input, and `plot_document()` at a chosen `t`.

## 2. Canvas tools already have one exclusive owner

**Status: observed strength.** `main.js` owns `toolMode`, deactivates the old
tool before activating the new one, and forces Select when a transient document
preview appears ([main.js:699-775](../../../axibridge/static/js/main.js)). Draw, pen, brush, and shape modules therefore own gesture details without each
being a competing global mode.

**Consequence.** A sheet/tray preview cannot accidentally receive a draw/brush
gesture, and adding another canvas tool does not require changing canvas
selection semantics.

**Smallest response.** Preserve this broker; make a new tool supply the same
activate/deactivate/escape seam. **Acceptance:** start a pen gesture, switch to
Brush and then enter a tray preview; neither partial gesture is committed and
all tool buttons are disabled during the preview.

## 3. Primary resolved refreshes can paint an older intent over a newer one

**Status: observed risk.** `actions.refreshResolved()` has no request token or
abort signal and always assigns the arriving response to `S.resolved`
([main.js:247-268](../../../axibridge/static/js/main.js)). It is called from mutations and timeline controls, while the timeline's own
single-flight guard protects only its internal caller
([plot.js:1698-1737](../../../axibridge/static/js/plot.js)). By contrast, generator preview explicitly serializes and drops stale replies
([compose.js:66-116](../../../axibridge/static/js/compose.js)).

**User consequence: hypothesis.** A slow older resolve can finish after a
newer scrub, undo, or edit and repaint the canvas/selection/plan with stale
geometry until the next refresh.

**Smallest response.** Give the shared resolved refresh a monotonically
increasing presentation generation; only the current generation may update
canvas, labels, or plan. Cancellation is optional. The architectural option is
a small request coordinator shared by resolved, plan, and document-preview
views; the tradeoff is a little explicit UI lifecycle state in exchange for
one consistent stale-response rule. **Acceptance:** delay `t=.1`, immediately
request `t=.9`, release `.1` last, and assert the canvas and view label remain
at `.9`.

## 4. Transient sheet/tray preview has the same late-reply hole

**Status: observed risk.** `showDocPreview()` awaits a sheet response and then
unconditionally sets `S.docPreview` and canvas layers
([main.js:282-290](../../../axibridge/static/js/main.js)). `exitDocPreview()` only begins a live refresh; it does not invalidate the
pending preview request ([main.js:293-297](../../../axibridge/static/js/main.js)).

**User consequence: hypothesis.** Leaving a slow sheet/tray preview, then
editing or scrubbing, can allow the old preview to reappear after the user is
back on the live canvas. That makes the label, target-picker semantics, and
visible geometry disagree temporarily.

**Smallest response.** Use the same presentation generation as finding 3 and
invalidate it on every preview exit, scrub, project replacement, and new
preview request. **Acceptance:** hold a sheet response, exit to live, make a
layer change, release the sheet response; the live canvas remains visible and
Plot continues to describe the live target.

## 5. Project-level edits bypass undo and the session mutation boundary

**Status: observed defect.** Layer edits checkpoint under `Session._lock`
([session.py:806-830](../../../axibridge/session.py)); the documented rule requires mutators to checkpoint under that lock
([CLAUDE.md:107-115](../../../CLAUDE.md)). In contrast, `PUT /project` assigns `name`, `guide`, and `plot_options` directly to
`session.project`, outside that boundary ([api.py:2012-2023](../../../axibridge/api.py)). `set_view()` checkpoints only when it finds geometry-oriented layers
([session.py:634-651](../../../axibridge/session.py)).

**Direct API result (hardware-free).** In an isolated `TestClient` run with
`AXIBRIDGE_CONFIG_DIR` and `AXIBRIDGE_NO_AUTOCONNECT=1` set before AxiBridge
imports: create one polygon, move guide `x: 0 → 17`, then `POST /undo` returned
200, removed the polygon (`1 → 0` layers), and restored guide `x` to `0`; the
next Undo returned 409 “nothing to undo.” A second run added another polygon
after the guide change, then undid that later add: it left one layer and guide
`x = 17`. Therefore the guide change created no history entry: it is restored
only incidentally when an older snapshot is restored, and it remains after an
unrelated later undo. The same direct assignment applies to name and
plot-options.

**Smallest response.** Add one `Session.update_project()` that validates,
checks for a real change, checkpoints exactly once under the lock, and replaces
the project fields; route the endpoint through it. **Acceptance:** change guide
position, crop mode, and a no-geometry view in separate operations; one Undo
per operation restores the exact prior values and the resolved/plan state.

## 6. API snapshots are assembled outside the resolve lock

**Status: plausible concurrent-request boundary gap, not a same-event-loop
race.** `Session.resolved()` releases its lock when it returns
([session.py:2906-2917](../../../axibridge/session.py)); afterwards `get_resolved()` iterates the live project and reads live source geometry to build region display paths
([api.py:1126-1168](../../../axibridge/api.py)). `_project_payload()` also directly dumps the live project
([api.py:74-75](../../../axibridge/api.py)). The relevant AxiBridge endpoints are synchronous `def`s
([api.py:1104-1108](../../../axibridge/api.py), [api.py:2012-2013](../../../axibridge/api.py)). The installed FastAPI dispatches non-coroutine endpoints through
`run_in_threadpool` ([fastapi/routing.py:321-330](../../../.venv/lib/python3.13/site-packages/fastapi/routing.py)), which delegates to `anyio.to_thread.run_sync`
([starlette/concurrency.py:30-32](../../../.venv/lib/python3.13/site-packages/starlette/concurrency.py)).

**User consequence: hypothesis.** This cannot interleave within one synchronous
handler on one event-loop task, but it can overlap in separate worker threads
when the browser issues concurrent requests. In that case a payload can pair a
resolved map from one project version with layer metadata from another (most
visibly after deletion/load or a region toggle). Finding 5 widens the window by
writing fields without the session lock. This audit did not force a timed
interleaving, so it remains a plausible concurrency risk rather than a
reproduced defect.

**Smallest response.** Have Session create an immutable, versioned resolved
payload while it holds its lock, including the region display silhouettes, then
serialize that snapshot in the API. A project revision number is the broader
option; it also lets the frontend reject old responses. Tradeoff: snapshotting
cost is paid once per response, but it protects the current single resolve
instead of duplicating it. **Acceptance:** overlap a delayed resolve with a
delete/load loop and assert every returned layer id has matching metadata and
paths from one revision.

## 7. Dense resolved documents have no display budget

**Status: observed scaling limit; user impact untested.** Generator live
preview is capped at 60,000 points ([api.py:325-370](../../../axibridge/api.py)), but `/compose/resolved` emits every path and point
([api.py:1158-1168](../../../axibridge/api.py)). Each canvas refresh clears the entire SVG and creates a visible SVG path per
source path plus a hit path per layer ([canvas.js:273-380](../../../axibridge/static/js/canvas.js)).

**User consequence: hypothesis.** Dense image/region output can make ordinary
edits or scrub frames appear frozen even when server caches make the resolve
fast; transfer, string construction, DOM creation, and style/layout all remain
linear in visible paths/points.

**Smallest response.** First measure point/path counts and paint time in a
real dense project, then set a displayed “preview simplified” budget that never
changes server geometry or plot output. A future renderer can consolidate
per-layer path strings in ink mode or rasterize only the display; the tradeoff
is less inspectable individual-stroke order at high density. **Acceptance:** a
100k-point layer remains selectable and a slider/scrub has a stated responsive
target while Plot/export remains exact.

## 8. The form engine is intentionally a narrow schema dialect, not arbitrary JSON Schema

**Status: observed extension limit.** `renderForm()` only iterates top-level
`schema.properties` and chooses a concrete optional branch
([forms.js:64-96](../../../axibridge/static/js/forms.js)); it explicitly handles assets/fonts/enums/bools/numbers/textareas, then treats all remaining
shapes as a text input ([forms.js:223-341](../../../axibridge/static/js/forms.js)). The module guide promises “No frontend work, ever” after registration
([docs/MODULES.md:14-24](../../../docs/MODULES.md)) but documents only that scalar control set
([docs/MODULES.md:26-42](../../../docs/MODULES.md)).

**User consequence.** A new module with an array, nested model, discriminated
union, `$ref`, or arbitrary object parameter will present an apparently valid
text field and then fail server validation, creating an extension surprise.

**Smallest response.** Name and enforce the supported schema profile at module
registration/test time; render an explicit unsupported-field notice rather
than a text box. The alternative is a recursive JSON-Schema renderer, with a
larger UI semantics and migration commitment. **Acceptance:** a deliberately
nested test parameter is rejected at registration (or visibly marked
unsupported), while every shipped module still renders unchanged.

## 9. The process bench is a sound separation, with a deliberate specialized escape hatch

**Status: observed strength and bounded cost.** The generic popup has clear
watch/bench semantics and never patches an existing layer
([process.js:1-25](../../../axibridge/static/js/process.js)). Its bench intentionally shares the Generate form’s params object
([process.js:182-206](../../../axibridge/static/js/process.js)). Second Reading is isolated in a separate score-editor module,
selected only by both declared capabilities
([second_reading_bench.js:1-38](../../../axibridge/static/js/second_reading_bench.js)); the guide explicitly says those capabilities do not make an arbitrary
process understand interventions ([docs/MODULES.md:175-190](../../../docs/MODULES.md)).

**Consequence.** The ordinary time-axis bench stays reusable and cheap, while
the experimental instrument preserves event/branch semantics without leaking
them into persisted layer mutation or the compositor.

**Smallest response.** Preserve this split. Add another special bench only
when it has a distinct recorded-event contract; then make the capability
descriptor select a named bench adapter rather than treating capabilities as a
generic interaction language. Tradeoff: each exceptional bench owns UI code,
which is preferable to a premature universal score editor. **Acceptance:**
generic Watch remains read-only; keeping a Second Reading result creates a new
layer and leaves the originating layer unchanged.

## 10. Second Reading working drafts are intentionally volatile

**Status: observed, documented tradeoff.** Its drafts live in a module-level
map and the file states that they survive close/reopen only during the current
app run ([second_reading_bench.js:17-26](../../../axibridge/static/js/second_reading_bench.js)). `closeSecondReadingBench()` copies the active recipe back to the external
form/layer context but persists no unfinished branch set
([second_reading_bench.js:304-315](../../../axibridge/static/js/second_reading_bench.js)).

**User consequence.** An unkept alternative, local bench undo history, and
working branch structure disappear on a browser/server restart. This is not a
bug in the current stated model; it is a recovery boundary the UI should make
legible.

**Smallest response.** Show a compact “working draft lives until restart” cue
when the bench has unkept branches. Revisit persistence only after actual
bench loss is reported; saving drafts introduces project dirty-state and
recovery semantics. **Acceptance:** close/reopen preserves the in-run draft;
reload clearly starts from the saved recipe rather than implying a recovery.

## 11. Unsaved-work protection is a known missing recovery boundary, and one roadmap detail is stale

**Status: observed/documented debt.** The restart endpoint says the in-memory
project is lost ([api.py:120-139](../../../axibridge/api.py)); the UI’s Save action is explicit
([main.js:483-495](../../../axibridge/static/js/main.js)). ROADMAP calls for a recovery slot and dirty restart guard
([ROADMAP.md:633-639](../../../ROADMAP.md)). Its statement that a bare save 422s is stale: the current endpoint accepts an empty body
([api.py:2051-2071](../../../axibridge/api.py)).

**User consequence.** A restart/crash can lose any work since Save; the stale
roadmap sentence weakens future decisions about the guard.

**Smallest response.** Correct that documentation now. Keep autosave/recovery
as a deliberately scoped follow-up: a private recovery slot plus dirty marker,
never silent overwrite of a chosen project folder. **Acceptance:** after one
mutation, restart asks about unsaved work (or recovery is offered on launch);
an explicit saved project is never overwritten by recovery data.

## 12. Reusable async patterns exist but are not yet shared infrastructure

**Status: observed.** Generator preview and live regeneration both implement
pending/latest/single-flight handling ([compose.js:123-168](../../../axibridge/static/js/compose.js)); the generic process popup does likewise
([process.js:309-347](../../../axibridge/static/js/process.js)); the Second Reading bench adds an identity/serial check before painting a reply
([second_reading_bench.js:671-695](../../../axibridge/static/js/second_reading_bench.js)). The central read paths in findings 3–4 do not use that vocabulary.

**Consequence.** The codebase already contains correct local solutions, but a
new asynchronous surface must rediscover its own stale-result policy.

**Smallest response.** Extract only a tiny “latest presentation wins” helper
after addressing resolved and document preview; leave specialized request
queues local where their semantics differ. **Acceptance:** unit-test the helper
with out-of-order completion, then use it for resolved and document preview
without changing generator/score-bench behavior.

## Suggested order

1. Fix the project mutation/undo boundary (finding 5), then make API payloads
   atomic (finding 6).
2. Apply one presentation-generation rule to resolved and document preview
   (findings 3–4), using the already-proven local patterns (finding 12).
3. Add a dense-canvas measurement and a supported-schema guard before either
   becomes an extension blocker (findings 7–8).
4. Keep the bench split; decide recovery only with real bench or restart-loss
   evidence (findings 9–11).
