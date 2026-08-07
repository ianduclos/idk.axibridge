---
project: idk.axibridge
state: active
updated: 2026-08-07
machine: mac+pi
summary: The layer list is now a persistent collapsible dock at the foot of the sidebar (Ian's Photoshop ask), and Slice 4 of the UI redesign is complete (a-g) — the toolbar is one fixed row of tools, the View and Machine menus hold what left it, machine state and plot transport live in the always-visible status line, the Plot tab is down from ten panels to five, plotting can be addressed by pen, and the layer list drags to reorder and renames in place; the app shell's macOS menu is now derived from the page's own markup instead of hand-written beside it; 727 tests green.
next:
  - "Ian eye-checks — CHECKME.md at the repo root is the list, grouped by how likely each thing is to be wrong; the shell-only paths need a full relaunch and are verified only against fakes"
  - "Re-ask whether jog earns its place, now that it is a menu item (Ian's ruling: use it that way first, then decide)"
  - "ROADMAP: interrupted plot as a live generator — the design is settled (snapshot-input) and the cost measured (~64 B/point), so it is ready to build rather than ready to decide"
  - "Still open from July: bench eye-checks of offset_fill + brush, the 07-16 to 19 wave, and the URGENT round (see HANDOFF)"
handoff_for: ian
---

# idk.axibridge — status

**Session 2026-08-07 (part 3, Opus 5): Slice 4 finished — 4c through 4g.**

The redesign's own slice, done. 727 tests green, 26 acceptance tests.

- **The canvas toolbar is one fixed row of tools.** It wrapped to three at
  1500px and every row it wrapped to pushed the sheet down while you resized.
  The overlays and render mode went to the View menu, the A/B ⇄ cluster to
  Plot › Staging, Animate + speed to a playback strip under the sheet that is
  absent when there is nothing to play. Measured 1600 → 900px: toolbar 39.8px
  and canvas top 95.8px, both constant. Below 900 the HEADER wraps — a
  separate control, recorded rather than hidden.
- **Machine state lives in the status line** (4d), visible from any tab:
  position, pen, progress, time left, and Pause/Resume/Stop moved there
  bodily. Fixes the bug the plan named — `remaining …` used to be written
  OVER the est/ink/lifts readout and never restored.
- **The Plot tab is five panels, not ten.** Motion parameters, jog & pen, raw
  EBB, soft limits and holder calibration went to Settings (which already
  owned calibration's reset button, so that control is reunited); only the
  pure actions became a **Machine menu**. Ian delegated the per-panel calls;
  the reasoning is in `plot.js`'s `MACHINE_PANELS` comment.
- **Plot by pen** (4e): `target` takes `pen:<id>`, one filter in
  `compose.flatten_to_document` so every consumer sees it through the single
  resolve path. No done-ledger, on purpose — a stale one authorises
  replotting over wet ink.
- **The layer list** (4f): drag to reorder with a drop line, ⌥-drag to
  duplicate, rename in place, and the per-row ↑ ↓ retired — moving a layer
  across fifteen was fourteen reorders and fourteen resolves. Occlusion
  channels are two segmented groups instead of eight tickboxes (4g).
- **The menu greys what it cannot do.** The probe reports `{on, enabled}` per
  item; an NSMenu autoenables its items by default and would have overruled
  every `setEnabled_` on open, so `setAutoenablesItems_(False)` is what makes
  it stick.

Two of my own mistakes worth carrying forward. Double-click-to-rename never
fired and I blamed `draggable`, changed the code on that theory, and the probe
came back `draggable: false` with the event still missing — the real cause is
that selecting a row rebuilds it between the two clicks, so `e.detail` is used
instead. And two acceptance assertions depended on which tests ran first (the
server fixture is session-scoped): both now establish their own precondition.

**Ian has not eye-checked this round.** The Machine menu's greying in
particular is verified only against real AppKit objects and a faked bridge.

---

**Session 2026-08-07 later (Opus 5): the two menu bars became one definition.**

Slice 4 of `docs/plans/ui-redesign.md`. 15 commits, suite 689 → 712. Four of
those commits are reverts, and the reverts are the story.

- **4a shipped, 4b was built and reverted.** The engraved-voice consolidation
  (`50dab95`) stands: one selector list states the uppercase/tracked treatment
  once through `--engraved-*` custom properties, where eight rules used to
  restate it. Zero visual change, measured over 2904 elements across all four
  tabs. **4b (IBM Plex Sans) was built, shown, and reverted the same day** —
  Ian: *"got used to the mono"*. Mono-only is now a decision, not an omission;
  the plan's 4b section is annotated BUILT-THEN-REVERTED with the three
  findings that outlive it, chief among them that
  `input, select, textarea { font-family: inherit }` is load-bearing only
  while `body` is mono.
- **No emoji in this UI** (`e3adad3`) — the layer-visibility `👁` is now inline
  Lucide `eye`/`eye-off` via the existing `.tool-icon` class, and the layer
  row's controls got a shallow well so they stop reading as decoration. Ian
  has said this before; it is now in auto-memory.
- **The menu unification, which took most of the session and four failures.**
  The app shell hides the in-page menu bar and showed a SECOND hand-written
  list, where Undo sat under "History" and orientation under "Canvas" — so the
  previous session's Edit-menu work had never been visible to Ian at all, and
  moving controls into the in-page menu made them *unreachable* in his app.
  `axibridge/menu_spec.py` now parses `#menubar` out of `index.html` into
  (label, selector, kind, shortcut); `build_menu` walks it; `merge_native_menus`
  folds our Edit/View items into pywebview's own menus of those names. **The
  markup is the contract now** — add a menu item to the page and it appears in
  both bars, with a checkmark.
- **Four bugs, all in the one path no test here can reach**, each fixed by
  removing its class rather than its instance:
  `item.title()` on a bar menu (pywebview titles the SUBMENU) → prefer the
  submenu; `NSMenuItem.alloc().init()` leaves the title as the literal string
  **"NSMenuItem"**, not empty, so an emptiness fallback never fired; the state
  sync pulled via `evaluate_js` from inside the `js_api` handler the page was
  awaiting (a bridge deadlock) → the page pushes instead; and a main-queue
  block that **returns a value** makes PyObjC raise an uncaught ObjC exception
  that terminates the app → `on_main()` is now the only way this file schedules
  main-thread work, and it always returns None.
- **The shell leaves evidence now.** Every AppKit poke swallows its exception
  so a cosmetic failure cannot stop the app opening, and Finder gives the
  bundle no stderr — so "best-effort" meant "invisible", and each bug cost a
  round trip through Ian relaunching. `~/Library/Logs/axibridge-shell.log`
  records the merge, the resulting bar, every state sync and every swallowed
  exception. It found the crash in one step after three days' worth of guessing
  in one afternoon.
- **4c's first step landed** (`6d0f047`): the View menu took the travel /
  draw-order / paper-guide checkboxes and Schematic·Ink. Toolbar three rows →
  two. It shook out a parser bug worth remembering — `<input>` is a VOID
  element, so `handle_endtag` never fires and a naive tag stack never unwinds;
  the whole View menu silently vanished from the spec until void tags were
  balanced on the way in.

Ian confirmed the menu bar, the checkmarks and the moved controls in the real
app. **Testing lesson banked:** two of the four fixes passed a unit test whose
fake encoded what I believed about NSMenu rather than what it does. There is
now a real-AppKit test (`test_merge_against_real_appkit_menus`) and a
subprocess test for the crash class, because a recurrence kills the
interpreter rather than failing an assertion.

---

**Session 2026-08-07 (Opus 5): the redesign plan's first three slices, plus redo.**

Worked `docs/plans/ui-redesign.md` from Slice 1 to Slice 3, checkpointing
after each. Seven commits, suite 639 → 689.

- **Occlusion is memoised** (`compose.OcclusionCache`). It used to run in full
  on every resolve; a repeat resolve on a 5-layer scene with a stroke occluder
  over a dense hatch fill went 430 ms → ~0. The cache is **content-keyed and
  never invalidated**: geometry is identified by object identity (legal only
  because modules are pure and lists are replaced wholesale), plus pen
  diameter, margin, groups, the receives flag, and layer order via the
  accumulated channel signature. `id()` reuse can't bite because every entry
  holds a strong reference to each list its key names. `tests/test_occlusion_cache.py`
  never inspects the cache — it asserts the cached resolve is byte-identical
  to an uncached one after every mutation that can move a mask. Known gap,
  documented: a visible region layer rewrites the shaped geometry below it
  each resolve, so those layers miss every time. Slow, never wrong.
- **Undo 8 → 50, with a geometry budget, and redo.** Measured first: an
  ordinary edit retains ~29 KB (the deep-copied Project), while an edit that
  REPLACES geometry pins its own copy at ~130 bytes/point — 50 bakes of a
  1200-path import is ~110 MB. Hence two caps, not one number. Redo makes
  history a pair of stacks; any real edit clears the redo branch, and a
  coalesced slider run is one entry in both directions.
- **Orientation is a declared layer property** (ROADMAP option B).
  `SourceModule.orientation` is mandatory — `"none" | "param" | "geometry"` —
  and for `"geometry"` sources in portrait the layer's affine carries the
  display map's inverse, so a layer lands where it would have in landscape,
  on screen. All 27 sources classified. The recurrence-stopper is
  `tests/test_orientation.py`: it fails on a source that declares nothing.
- **Acceptance harness** (`tests/test_acceptance_ui.py`): ten Playwright tests
  driving the real UI against a real server on a temp port, asserting what the
  user sees. They skip cleanly with no browser, which is how the Pi stays
  backend-only.
- **Vite + TypeScript**, with the source unmoved. `app.frontend_dir()` is the
  whole switch: built output when it exists, source when it doesn't — the
  fallback is what keeps a machine with no npm working. TypeScript is a lint
  pass (`allowJs`, `noEmit`), nothing renamed. ROADMAP's "Far / undecided — UI
  revamp" is marked RESOLVED with what was adopted and what it cost.
- **Edit menu** (Ian's ask, mid-session): Undo/Redo with ⌘Z / ⇧⌘Z; the
  portrait/landscape control **moved** into the View menu rather than being
  proxied there, so it cannot drift from `main.js`.


**Session 2026-07-27 (Opus 5): two new modules, and the workflow changed.**

Ian asked that work be **incorporated automatically** from here on — commit
straight to `main`, only branch when he says so. (Pushing still requires
asking; that rule is unchanged.) The trigger: nine feature branches had piled
up committed-but-unmerged, so finished work read to him as missing entirely.
`feat/ui-round-0726` was the last one and is now merged.

- **`effects/offset_fill.py`** — the second fill primitive beside `hatch_fill`:
  repeats the outline *inward* as concentric rings (contour-map look) instead
  of laying scanlines across it. The whole effect is erosion by a disk, and
  **topology needs no special-casing** — components split, components vanish,
  holes grow and merge, and shapely returning a `MultiPolygon` or an empty
  geometry *is* the event. The levels form a monotone forest because erosion
  can never invent a hole nor merge components. Load-bearing details, each
  pinned by a test: rings are eroded from the ORIGINAL at `k*spacing` (never
  iteratively, or corners re-round each pass); the even-odd hole assembly runs
  BEFORE eroding, which is why this is layer-wide and can't be a mode on
  `contract_expand`; inner rings are `filled=False` or occlusion reads the
  stack as stripes. `medial_tail` draws a centreline down limbs too narrow for
  another ring, suppressed when it would double an existing one.
- **`round_center`** (Ian's follow-up, same day) — relaxes each ring's corners
  in proportion to its depth, so the family morphs from the shape toward
  circles on the way in. A morphological opening, which is what buys the three
  properties that matter: it leaves straight runs untouched (ring spacing
  survives), it stays contained in the shape (rings can't escape or enter a
  hole), and it rounds only CONVEX corners — so concave structure survives and
  a star's centre becomes a flower, not a disc. That is the honest result, not
  a shortfall. The radius backs off by halves rather than ever costing a ring:
  verified that without the guard a 40mm square drops from 10 rings to 5.
- **`sources/brush.py` + `static/js/brush.js`** — ROADMAP 0c, the sibling of
  the shipped pen tool, now a 4th toolbar segment button. Circle brush, `[`/`]`
  resize, `E` toggles erase. The correctness story is the **sequential fold**:
  erases apply per stroke in chronological order, never
  union-all-then-subtract-all, or a repaint over an erased spot is swallowed.
  `test_repaint_over_an_erase_survives` builds the batched answer explicitly
  and asserts the real one differs — confirmed it is the only test of the 17
  that fails under a batched implementation. Output is every ring as a closed
  `filled=True` path, holes by nesting. Playwright-verified end-to-end against
  the real UI (4 strokes, no console errors, the erase bite and repaint bulge
  both visible in the resolved output).
- **`docs/plans/liquify-effect.md`** — a *loose* plan (hatch-connect-v2 style,
  not a frozen brief) for a soft-brush warp effect Ian raised hypothetically.
  Three findings worth keeping: it would be the first captured-input *Effect*
  (draw/pen/brush are all Sources); "depth as parameter" reads as a global
  `amount` 0..1 that must be exactly identity at 0, which makes timeline
  animation free; and **interpolating two liquifications is easier than the
  captured-geometry morph already shipped**, because a warp is a field rather
  than a structure. The trap there is that the tempting fix (A/B inside the
  effect) re-forks interpolation — extend the core instead. Filed as ROADMAP 0d.

Also merged this session: **`feat/ui-round-0726`** (Lucide tool icons, pen
Commit button, hatch-to-its-own-pen split), which had been sitting unmerged
since 07-26.

**Not done:** nothing has touched paper. Both new modules are screen-verified
only (rendered PNGs + Playwright), and ring-spacing-vs-pen-width is exactly
the kind of thing only real ink settles.

**Late in the session** (Ian's ask, all pushed):

- **`main` is on origin** — first push ever, and **idkpi pulled** to the same
  commit with 560 green there. Standing rule changed: push without asking on
  this project.
- **`fix(server)`: the app's slow quit was a one-line uvicorn default.**
  `timeout_graceful_shutdown` defaults to *wait forever* for open connections,
  and `/api/events` is an SSE stream that never finishes by design — so every
  quit hung until `launch/axibridge_app.py`'s 5s grace expired and SIGKILLed
  it. Measured with a stream held open: before, SIGTERM hung past 10s; after,
  clean exit in 2.17s. The plot-running close guard is untouched.
- **"Unknown source: brush" is a stale server, not a bug.**
  `load_builtin_modules()` runs once at startup, so a process started before a
  new module file exists never imports it — the browser picks up new JS
  instantly (no build step) and the mismatch looks like a broken tool. Restart
  the app after any new source/effect lands. Worth knowing generally.
- **"Graduate to a real app?"** — the shell question and the frontend-build
  question are separate and must stay that way (ROADMAP keeps the latter
  deliberately open). A Tauri/Electron shell would still point at
  `localhost:2942`, so the dev loop would be unchanged; a bundler is what
  would actually add tedium. Most of the "cheap" feeling was the shutdown bug
  above. Recommendation on record: use it a week, then fix the specific
  irritations rather than buying an architecture.

---

**Prior session 2026-07-25 (Sonnet 5): merged the four pending branches to main**
(nested-tween-morph, pen-tool, geometry-morph-tween, hatch-connect-strokes),
in dependency order with tests run after each step (suite 511 green).
`feat/geometry-morph-tween` needed a rebase onto the advanced `feat/pen-tool`
tip as flagged, which surfaced a real conflict/regression: nested-tween-morph
had rewired the live tween resolve path (`_source_paths_at`) to reduce
endpoints via `effective_generator` + `lerp_params` directly, bypassing
`blend_generator_params` — where the captured-geometry deep-lerp (pen/drawing
shape morph) lived. Fixed by applying the same deep-lerp inside
`_source_paths_at` on the post-reduction param dicts; one failing test
(`test_pen_tween_morphs_shape_continuously_not_stepped`) caught it before it
reached main.

---

**Session 2026-07-20 → 21 (Sonnet 5 / Opus 4.8): pen tool built, tween shapes now morph, hatch strokes join.**

The ⚓ pen tool (`sources/pen.py` + `static/js/pen.js`) with Photoshop grammar
and a 3-way toolbar mode segment driven by a shared `setToolMode` broker;
captured-geometry tween morph (`tween._blend_geometry` — pen/drawing shapes
morph A→B structurally instead of stepping at 0.5) plus a `cosine` ease;
`hatch_fill.connect_strokes` to cut pen lifts. Full record:
`docs/plans/pen-brush-tools-RESULTS.md`.

## Prior arc — 2026-07-19 (Fable + Sonnet 5): interpolation core unified, canon audit

One interpolation blend core in `tween.py` (`structures_match` / `lerp_paths` /
`blend_generator_params` / `blend_effect_stacks`), cheap-checkpoint invariant
restored, capture snapshots externalized to `staging/snapshot-<group>.json`,
registry-wide contract tests (`test_effect_contract.py`). **This is the
unification that ROADMAP 0d's liquify note warns against re-forking.**

## Prior arc — 2026-07-16 → 19 (generator v2, bench latch, draw/response tools)

`misremembered`/`glyphgram` v2 (scribble masses + tone, coherent-field +
continuity); generate-bench latch with coalesced undo; draw tool
(`sources/drawing.py` + `static/js/draw.js`) and response brushes
(`parasite_line`, `eyelets`, `velocity_tube`). Aesthetic rule (auto-memory):
structure-following marks, coherent fields, chaining — never uniform scatter.
Agent-ops: no worktrees (PEP 660 editable install imports main checkout);
agents work in the main checkout.

## Older history

URGENT round 11/11 (2026-07-13, orientation coherence via viewmap tags),
lineart v2, animation previews, Pi rounds, sheets v2, A/B capture — see
ROADMAP shipped sections and git history. Architecture invariants:
`ARCHITECTURE.md`, `docs/MODULES.md` (single resolve path; scrubbing never
mutates stored state). Two AxiDraw modes contend for the serial port —
Mac-driven pi_ssh (default) vs the disabled Pi-served service.
