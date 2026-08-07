# Plan: UI redesign pass — correctness, then toolchain, then instrument

You are Claude running as a coding agent on Ian's Mac, in the axibridge repo.
This plan was written 2026-08-07 by an Opus 5 session, after a full UI review
by three critics and a design interrogation with Ian. **The decisions in
"Settled" are settled — implement them, don't redesign them.** If one turns
out to be impossible as specified, stop, write what you found to
`docs/plans/ui-redesign-BLOCKED.md`, commit that, and end the run.

Ian works alone, for hours, on a machine that wastes paper when the UI lies.
Everything below is ordered by that.

## Read first (in this order, all in-repo)

1. `CLAUDE.md` — operating rules. Single resolve path, module purity, bounded
   params, undo discipline, pyaxidraw ints. Non-negotiable.
2. `ROADMAP.md` — the new top section "URGENT (Ian, 2026-08-07)" is Slice 1's
   orientation work. "Far / undecided — UI revamp" records the tooling history
   this plan is now resolving.
3. `axibridge/static/style.css` — read the header comment. It states the
   visual system ("bench & bed") and why each rule exists.
4. `axibridge/session.py` — `_history` (line ~150), `undo()` (~221),
   `_checkpoint`, `resolved()` (~1922).
5. `axibridge/compose.py` — `clip_paths()` and `resolve_project()`. The
   resolve order is `occlusion(regions(effects(transform(source))))`.
6. `axibridge/static/js/menu.js` — read the header comment. It states the
   proxy rule the menu work must obey.
7. `launch/axibridge_app.py` — the macOS shell: title-bar merge, native menu,
   `ShellApi`, drag region. Every AppKit call is dispatched to the main queue
   for a reason (see below).

## Two review artifacts (context, not instructions)

- Review, with 12 ranked proposals, three critics' disagreements and rulings:
  https://claude.ai/code/artifact/eb6f2105-7669-4bab-867b-2012122f84f6
- The visual direction and why it is what it is:
  https://claude.ai/code/artifact/b595fdb0-9204-45c0-83ce-571dbcfb6427

## Protocol

- **Solo run with checkpoints.** Work the slices in order. At the end of each
  slice: full suite green, commit, then **stop and report to Ian** with what
  changed and what to look at. Do not start the next slice unprompted.
- **Every slice ends somewhere Ian can plot from.** He uses this between
  sessions. Never leave the app unusable across a checkpoint.
- Conventional commits. Commit at verified checkpoints, never broken state,
  never push without asking.
- `.venv/bin/python -m pytest -q` must be green before any commit.
- Anything user-visible is **provisional until Ian looks at it**. Say "ready
  for you to check", never "works", off a passing test or a screenshot.

## Settled (do not re-litigate)

| Decision | Value | Why |
|---|---|---|
| Order | correctness → tests → port → redesign | Prettying an app that loses work and stalls is polishing the wrong layer |
| Branch | merge `design/bench-and-bed` to main **first** | 11 commits ahead; don't stack a redesign on an unmerged branch |
| Orientation fix | **option B** (layer property) | Option A leaves the failure mode intact; this has recurred three times |
| Toolchain | **Vite + TypeScript** | Ian's call. Buys npm access + cross-file types. NOT speed — see Facts |
| TS strictness | loose, ratchet per file | Keeps the port mechanical instead of a 6,400-line annotation project |
| Test runner | **pytest + Playwright only** | One suite, one command, no second ecosystem |
| Typeface | **IBM Plex Sans** + Roboto Mono | Technical/industrial, pairs with mono, closer to the CAD/Ableton anchors than Inter |
| Toolbar | thinner; menu bar grows | Toolbar wraps to 3 rows at 1100px and moves the canvas edge ~140px |
| Tools | stay **horizontal**, first position | Wrapping is caused by the other clusters, which this pass removes; a vertical rail would spend canvas width on a solved problem |
| Menu rule | actions + simple on/off **only** | Anything with a readout or live value stays a panel. This is the guardrail that stops consolidation hiding machine truth |
| Targeting | pen targets **and** layer targets | Pen addresses the swap loop; layers stay for complex runs |
| Groups | deferred | Touches model, save/load, occlusion, tweens — too big inside a redesign |
| ⌘K launcher | deferred (now unblocked by npm) | Shouldn't share a slice with a restructure |
| Pi | backend-only | Frontend tests/builds are Mac-only; skip browser tests when Chromium is absent |
| Execution | solo + checkpoints | Work is sequential; parallel agents would start cold on interdependent code |

## Facts already established (don't re-derive)

- **Undo is 8 deep.** `session.py:156`, `deque(maxlen=8)`. `undo()` **pops**
  (`session.py:226`) so there is nothing to redo to — redo needs history to
  become a cursor, not an appended function. **[Done 2026-08-07, out of
  order, at Ian's request: depth is now 50 + a geometry budget, and redo
  ships as a second stack — see ARCHITECTURE "Undo, duplication,
  consolidation".]** Each entry is a full project +
  source-geometry + staging snapshot, which is presumably why it's 8.
- **Occlusion recomputes on every resolve.** `_shaped_cache` covers
  transform+effects; occlusion runs after it. Measured on 5 layers with an
  occluder over a `hatch_fill` layer: cold 2243 ms, warm 2146 ms — the cache
  saves 53 ms. 87% of the time is `shapely.set_operations.difference` (355
  calls), which is already compiled C. **A faster language would not help.**
  `clip_paths()` already rejects non-intersecting paths (bounds + prepared
  `intersects`); that is correct and free but does not touch this case,
  because when an occluder covers a hatch fill almost everything overlaps.
- **Orientation coverage: 7 of 27 sources.** Tagged: `_pixelgen`, `dots`,
  `image_threshold`, `lineart_hatch`, `linescan`, `longwave`, `waves`.
  `text` and `glyphgram` have **no rotation param at all**, so there is
  nothing for `applyViewDefaults` (`static/js/viewmap.js`) to remap.
- **Registry: 45 modules** — 27 sources, 14 effects, 4 transforms. (Counting
  files gives the wrong answer; the 4 transforms share one file.)
- **`.engraved` is dead code.** Defined in `style.css`, referenced **0** times
  in markup or JS. The uppercase treatment is re-specified inline in seven
  separate rules, so "sentence-case the headings" is a seven-place edit until
  that is consolidated. Do that first.
- **Vite builds this frontend unmodified.** Measured: `npm install` 4.9 s
  (18 MB `node_modules`), production build **243 ms** (16 modules), dev cold
  start **84 ms**, output 148 KB JS / 22 KB CSS. It bundled and hashed JS+CSS,
  rewrote the vendored font URLs, kept all 7 inline SVG icons, and correctly
  left `/api/doc/all/svg` alone as a runtime route. Node 23.11 is installed.
- **Playwright gotcha.** The venv's playwright wants chromium revision 1223;
  only 1234 is installed. Either run `playwright install`, or pass
  `executable_path=` — see any probe script pattern. Fix this properly in
  Slice 2 rather than carrying the workaround. **[Done 2026-08-07:
  `.venv/bin/python -m playwright install chromium` fetched 1223; no
  `executable_path` anywhere. Two more gotchas found while building the
  harness — `<option>` is never "visible" to Playwright, and a
  session-scoped `sync_playwright()` breaks every later `asyncio.run()` in
  the suite. Both are written up in CLAUDE.md.]**
- **pywebview gotchas** (all already bitten, all in `launch/axibridge_app.py`):
  window events fire **off the main thread**, so AppKit calls must be
  dispatched to `NSOperationQueue.mainQueue()` or they silently no-op;
  pywebview paints the title bar `windowBackgroundColor` on purpose, so
  transparency alone loses; custom menus are appended **after** its own
  app/View/Edit menus. Failures in this area do nothing rather than raise —
  which is why the outcome is published to the DOM as `data-titlebar`.

## Slice 0 — merge

Merge `design/bench-and-bed` into main (it is ~11 commits ahead; the shell
work in it is confirmed working on Ian's machine). Suite green. Delete the
branch. **Checkpoint.**

## Slice 1 — correctness

Nothing here is cosmetic. Do it first.

**1a. Occlusion cost.** Cache the occlusion stage. The cache key must cover
everything the mask depends on: shaped geometry identity of every
contributing layer, `occluder` / `receives_occlusion` / `occlude_groups` /
`receives_groups` / `occlusion_margin_mm`, and pen line diameters (masks come
from filled outlines at pen width). **A stale occlusion cache makes the tool
draw something that is not true — the one failure this app cannot have.** If
you cannot convince yourself the key is complete, ship the measurement and the
bounds work only, and say so. Target: repeat resolves with no relevant change
cost ~0; verify with a timing test, not a claim.

**1b. Undo depth.** First *measure* one history entry against a realistically
large project (many layers, hatch fills, staging) — `sys.getsizeof` is not
enough, walk it. Then raise `maxlen` to what fits a sane budget (~50 was the
review's guess; the measurement decides). If snapshots prove too heavy, do
deltas instead. Redo is **out of scope for this slice** — it needs history
restructured into a cursor and that is its own change.

**1c. Orientation, option B.** Sources declare orientation (e.g. an
`oriented` class attribute); portrait contributes a documented rotation once
at layer creation, in one place. Then the part that actually ends the
recurrence: **a test that fails when a new source module declares nothing.**
Acceptance, in Ian's words: *"stuff appears in the position I'm facing when I
insert it — I shouldn't have to think about this."* Verify `text` and
`glyphgram` specifically. `tests/test_view_coherence.py` must still pass:
resolve stays bit-identical across views, view rotation stays display-only.

**Stop-here state:** the app plots as before, but no longer stalls on
occlusion, remembers far more undo steps, and puts generated geometry the
right way up. **Checkpoint.**

## Slice 2 — acceptance harness

pytest + Playwright, driving the real UI against a real server on a temp port.
Fix the chromium revision mismatch properly. Skip cleanly when no browser is
present (the Pi runs this suite and stays backend-only).

Cover the flows a redesign will disturb, not module internals:
- load → tabs render → layer list populates
- create a generated layer; select it; edit a param; preview updates
- pen assignment shows on the layer row
- plot target selection; the Plot button enables only when connected and idle
- panel collapse persists across reload (already implemented — pin it)
- portrait/landscape toggle changes display only
- no console errors on any tab

These tests are the contract the port must not break. Keep them behavioural —
assert what the user sees, not how it is built, or they will fight the
redesign instead of protecting it. **Checkpoint.**

## Slice 3 — mechanical port to Vite + TypeScript

**Zero behaviour change.** The entire claim of this slice is "nothing moved
except the build". Slice 2's tests must pass identically before and after.

- Vite config with an `/api` dev proxy; `outDir` the server can serve.
- FastAPI serves the built output in production and the source in dev — one
  switch, documented, no third mode. Keep `_RevalidatedStatic`'s no-cache
  behaviour (`app.py`) or the version-mix bug it guards returns.
- `allowJs`, loose types; rename `.js` → `.ts` only as files get touched later.
- **Run the acceptance tests against the BUILT output, not the dev server** —
  otherwise the works-in-dev-broken-in-build class goes uncaught.
- Update `CLAUDE.md` (the "Run / test" and "Frontend stays build-free"
  sections are now wrong) and `ARCHITECTURE.md` "Stack". Record in ROADMAP
  that the Far/undecided tooling question is resolved and how.
- `launch/axibridge_app.py` must still work — it points at the server, so it
  should be unaffected, but verify the app shell opens and the menus work.

**Stop-here state:** identical app, new toolchain. **Checkpoint.**

## Slice 4 — the redesign

Only now. Sub-steps are independently shippable; commit each.

**4a. Consolidate `.engraved` first** (see Facts) so the typography change is
a one-place edit.

**4b. Typography.** Vendor IBM Plex Sans (Latin subset, woff2, alongside the
existing Roboto Mono — offline, no CDN, matching `@font-face` pattern). Mono
keeps readouts, values, inputs and panel titles; sans takes prose, control
labels, buttons, menus. Collapse the scale to ~10/12/13/15/20. Demote body ink
from `#ece7da` to `#d8d2c4` and reserve `#ece7da` for the focused element.
Sentence-case `h3`; the engraved+rule device survives at panel level only.

**4c. Menu bar and toolbar.** Grow the in-page menu bar to File / Edit / View /
Layer / Machine / Plot / Help, **on the proxy rule `menu.js` already states**:
every item clicks a control that already exists, so the menu cannot drift.
Mirror the same structure into the native macOS menu in `launch/axibridge_app.py`
from one shared definition — do not maintain two lists.

**The menu rule (decided, Ian):** a menu item may be an action, a checkmark or
a radio choice. Anything carrying a readout, a live value or explanatory state
stays a panel. Apply it literally; it is what keeps this consolidation from
hiding machine truth.

*Leaves the Plot tab* → a Machine menu: raw EBB, soft limits, holder
calibration, **and jog/pen**. Jog looks like it violates the rule because it
has a position readout — it doesn't, because 4d promotes that readout to the
persistent machine strip. The jog *actions* become menu items; the *value*
becomes always-visible, which is strictly better than today.

*Stays visible in the Plot tab:* **Backend** (its cards carry the capability
tags — "no raw · jog · no pause" — that you need BEFORE committing to a job,
and a menu cannot show them), plus passes/targets, plot-pass optimisation,
interrupted plot, animation/sheets, staging.

*Leaves the canvas toolbar* (all four, decided): the travel / draw-order /
paper-guide checkboxes and the Portrait-Landscape + Schematic-Ink toggles → the
View menu as checkmarks and radios; the A/B/steps/⇄ cluster → Plot › Staging
entirely; Animate plot + speed → a playback strip at the canvas foot that
appears only when a timeline or staged series exists.

*The toolbar then holds:* tools (Select/Draw/Pen/Brush, horizontal, first
position), zoom-fit, and the existing contextual brush/pen bars. One row,
`flex-wrap: nowrap`, overflow behind a "»" — the canvas top edge must stop
moving when the window resizes.

Biggest density win and biggest edit — do it in visible steps, not one sweep,
and show Ian a before/after at the FIRST step.

**4d. Machine state into `#canvas-status`** — it already exists, is already
persistent across tabs, and currently holds one line of "nothing selected".
Progress, remaining, X/Y, pen up/down, Pause, Stop. Costs no vertical space.
Note `main.js:828` currently overwrites the est/ink/lifts readout with
`remaining …` during a job; those are job facts and should stay put.

**4e. Pen-addressed plot targets**, alongside the existing all/one-layer
targets. Do **not** build a "done ✓" ledger: a ledger records intent, paper
records truth, and a stale one is exactly what authorises replotting over wet
ink. An append-only log of what was *sent* is fine; derived done-state is not.

**4f. Layer list**: drag-to-reorder with a drop line, inline rename (it is a
native `prompt()` today, `compose.js:785`), `⌥`-drag to duplicate. Retire the
per-row up/down buttons — moving a layer across 15 costs 14 clicks and 14
resolves today.

**4g. Boolean/occlusion density**: replace the two rows of single-letter
A/B/C/D checkboxes (`compose.js:1068–1078`) with two 4-segment `.seg` groups,
and collapse the occlusion block behind a one-line summary.

**Checkpoint after each of 4a–4g.**

## Explicitly out of scope

⌘K launcher (unblocked by npm now, but its own decision) · layer groups ·
~~redo~~ (shipped 2026-08-07 at Ian's request, with the Edit menu) ·
split inspector (worsens density before density is fixed) · frameless
window · any change to the resolve order or the single-resolve invariant.

## Open decisions — these are Ian's, not yours

1. **Undo depth number** — depends on the measurement in 1b. Report it, propose
   a number, let him choose. Do not silently trade an annoyance for a stall.
2. **Occlusion cache key completeness** — if in doubt, say so rather than ship
   a cache that can lie.
3. **Does jog earn its place at all?** Ian: *"never used jog matter of fact,
   not sure bout the utility."* The plan moves it to a menu rather than
   deleting it — but if, once it's a menu item, it still goes untouched, raise
   deleting it rather than carrying it forever. Do not delete it unilaterally:
   pen up/down and go-to-origin inside that group may be the parts that
   actually earn their keep.

## Verification protocol (mandatory)

- `.venv/bin/python -m pytest -q` green before every commit.
- For anything visual: drive the real app in a real browser, screenshot, and
  *look at the screenshot*. Fresh page per shot — the headless shell ghosts
  repaints across tab switches and it has already produced artifacts that look
  like real bugs.
- For the app shell specifically: headless verification cannot see the title
  bar or the traffic lights. Check `document.documentElement.dataset.titlebar`
  for whether the merge applied, and hand the visual check to Ian.
- Measure, don't assert. Three separate failures in this codebase looked
  correct, raised nothing, and did nothing.
