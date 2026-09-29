---
project: idk.axibridge
state: active
updated: 2026-09-29
machine: mac+pi
summary: Main now includes Linedraw v3 and plot estimates (local, unpushed); a Territory bench prototype (web artifact, v1-v5) is on feat/territory-bench with a meander round planned next.
next:
  - "Start the meander round in a fresh session: docs/plans/territory-meander-round.md"
  - "Try Linedraw v3 components, tonal shading, Smoothen and the revised bench"
  - "After the active plot finishes, activate and check mandatory simplification and native timing"
  - "Decide whether to push main (fast-forwarded to codex/linedraw-v3) and merge feat/territory-bench"
  - "Continue remaining native and paper acceptance entries in HANDOFF.md"
handoff_for: Codex
---

# idk.axibridge — status

**Territory bench prototype, 29 September:** An AARON-adjacent drawing bench is
being prototyped as private web artifacts, with no `axibridge/` changes. *Cores and Skins*
(v1) led to *Territory*: rival camps with log-sum-exp fields, borders and fading
edges, voids, and history-aware redraw (v2); a lit-landscape volume pass (v3); soft
bodies with wrap, wound and growth renderers and a smooth two-handed line (v4, "too
concrete"); and searching lines, where borders restate their own history with an
economy of weight (v5). Seeds 3, 13 and 21 were "going somewhere". Ian wants the illusion of
line width from lines, a more unified sheet and less territory scaffold, so the
meander round comes next ([plan](docs/plans/territory-meander-round.md)). Sources are in
`tools/territory-prototype/`. Evidence is in `shots/territory-v2-0929` through
`shots/territory-v5-0929`. Blind Sonnet reviews are in `docs/reviews/territory-v2-0929-sonnet.md`, and
the research and briefs are in `docs/research/territory-v5/`. Roles on this track: Fable designs,
Sonnet critiques. Everything was judged on screen; nothing has been plotted. Earlier the same day, local
`main` was fast-forwarded to `codex/linedraw-v3`, which contains the plot-estimate
commits. The full suite passed (1,688) before the merge, and nothing has been pushed.

**Components and bench, 28 September:** Contours/form/cores can be independently
included in the recipe or kept as aligned frozen layers in one undo step. Tonal
coverage, normal-tangent flow, bounded regional hair steering and Smoothen are
opt-in; original defaults retain the same drawing geometry. The bench now groups
Image/Guides/Drawing controls, hides irrelevant options, shows white paper, and
keeps automatic redraw optional/off during guide creation. 44 focused backend and
12 UI checks plus two private cached-photo comparisons cover this extension; no
full-suite rerun or hardware activity. Independent review found tonal gains in
one case and preference for original shading in the other, so new treatments
remain optional. User and paper acceptance remain pending.

**Reference choices, 28 September:** Light form support and Regional face + form
are now separate choices, with saved editable ownership/detail regions, category
switches, automatic debounced redraw and shared drawing status. Verified with
55 focused tests, typecheck/build and private real-model runs; no full-suite
rerun requested. Light rendering closely matches the frozen evidence; regional
hatching and faces are preserved with small legacy base-contour differences.
All source-specific evidence remains outside Git. Component separation and optional tonal treatments are now implemented above;
linked multi-layer regeneration remains a design idea in ROADMAP.md.

**Linedraw v3 integration, 28 September:** Four styles, automatic editable face
regions, local model workers, cancellation, real shadow-fill pen strokes and a
source/drawing bench are implemented. Keep creates a normal layer; Open drawing
bench → Apply updates its recipe with undo. Saved geometry opens without models.
Models are configured locally, outside Git. Private study material remains out
of the repository. [Usage and limits](docs/LINEDRAW.md).

The normal app launcher is running from the isolated `codex/linedraw-v3` worktree
with its own backend and hardware auto-connect disabled. Native backend flow
verified Analyze → Keep → reopen → Redraw → Apply → undo; original empty project
restored. Bundled public portrait: first analysis/drawing 13.52 s, warm redraw
1.06 s on MPS. Final suite: **1,649 passed**, one existing Starlette warning.
Typecheck/build passed. Screen results are ready for Ian's check; no paper test.
The original checkout and main are unchanged; no push or merge.

**Linedraw research checkpoint, 28 September:** Reusable array/geometry kernels
for shadow shapes, form hatching, regional allocation and optional facial
guidance are preserved under `tools/linedraw_research/`, with synthetic tests.
The registered application generators remain unchanged. Reference photographs,
annotations, model evidence, rendered geometry and comparison artifacts stay
outside Git; an ignored local handoff locates the complete private studies.
Verification: **1,596 hardware-free tests passed**, with one existing Starlette
deprecation warning. No application restart, push or hardware action.
[Findings and continuation](docs/research/linedraw-v3.md) distinguish manual
attention from automatic evidence and retain negative results.

**Plot optimization and timing, 16 September:** All normal, sheet and tray
passes now simplify each trajectory at a minimum 0.01 mm tolerance, including
older projects. Optional simplification can increase that tolerance. Native
estimates use the installed driver's isolated preview planner with the same
optimized geometry and effective pen settings. Motion time includes motor-step
and millisecond quantization plus pen timing; USB/host overhead is excluded.
The current physical plot was left untouched; backend activation is pending.
Verification covers **1,576 passing tests and one native-launch skip** across
runs: the full run passed 1,475 but its first browser server missed the 30 s
startup deadline under load; all 101 affected browser tests plus 16 focused
checks passed on rerun with a 120 s startup allowance. Typecheck, build and
isolated native-estimate browser smoke passed. One existing Starlette warning.
Committed on `codex/plot-optimization-estimates`; not merged or pushed.

**Mosca recording bench, 16 September:** Read-only experiment browser, playback,
fractional prefix cutoffs, recorded pen lifts and fixed-frame placement are
implemented. Keep stays open and creates independent layers; recording assets
travel through project save/load/ZIP and support Resume without mosca-draw.
The largest 2.4M-sample history was previewed and kept at 55% in an isolated
browser. Full suite: **1,561 passed**, one existing Starlette warning;
typecheck and build passed. The normal native app was opened with hardware
auto-connect disabled; its owned backend advertises Mosca, lists 108 recordings
and previews the masked retracing run at 50%. The project remains empty.
Native interaction and paper output remain Ian's acceptance.
Wrapup verification after the finer 0.07-unit preview stroke: **1,560 passed,
1 native-launch skip** (the app was running), one existing Starlette warning.
Typecheck, build and isolated large-history browser smoke passed. Integrated
on `main`; no Pi deployment.
See [behavior and file contract](docs/MOSCA-BENCH.md).


**Browser refinements, 10 September:** Identifier SVGs now persist on disk
across backend restarts and invalidate when renderer dependencies change. The
selected tool gets a larger copy of that same SVG. Visible category chips,
optional personal 1–5 ratings, usage/recency sorting and Enter-to-box tags with
frequent suggestions make both browsers easier to search. Working benches share
the same catalogue classification with Compose. Usage counts successful tool
actions, excludes previews and effect reorder/removal, and leaves undo intact.
Activated after diagnosing an orphaned backend: the app was closed, but an old
server remained attached to PID 1. Saved recovery copy
`before-browser-activation-20260910-040525-31f4a4`, retired the idle orphan and
opened the normal app launcher with auto-connect disabled. The new backend is
owned by the app shell; the drawing was restored. Live generator/effect category
filters passed a browser smoke without changing project state. CLAUDE.md now
requires live backend verification and explicit process-ownership checks.
Verification: 1538 hardware-free tests passed, 1 skipped, one existing Starlette
deprecation warning. Typecheck/build passed. Both browsers were inspected with
loaded identifiers at 1024×768; the generator browser was also checked at
1440×900. Added cancellation coverage ensures usage accounting still interrupts
slow previews before waiting for the project lock. Ready for Ian's native check.

**Module browsers and presets, 10 September:** Generators and effects have
separate selection browsers, small fixed identifiers, stars, personal tags
and named starting-settings presets. Browser Use prepares existing controls;
Apply preset changes an existing generator/effect in one undo step. Editable
benches load drafts and reset interaction histories; Watch stays read-only.
Source inputs and captured arrangements are excluded; compatible current image
inputs are retained and saved seeds are restored. No preset thumbnails.

Identifiers render actual modules against fixed examples in isolated workers
(two active, eight queued); all 52 registered source/effect identifiers were
verified. Expected failures fall back to a tool name. Twenty-seven focused
module/browser/bench checks passed, including stale replies, metadata failures,
missing modules, stars and one-step undo. The full hardware-free suite passed: 1517 passed, 1 skipped, with one existing
Starlette deprecation warning. Typecheck and build passed.

The running backend has been updated after preserving/restoring the empty
project in `before-module-library-20260910-030127-18912f`. Simulator remains
disconnected/idle; no browser reload or hardware operation. Native appearance
and interaction remain for Ian. Contract: `docs/MODULE-LIBRARY.md`.


**Gallery geometry and canvas comparison, 10 September:** Automatic Line-based,
Shape-based and Mixed metadata now derives from filled/closed path flags, also
for existing records. A geometry filter helps recall. Preview on canvas folds
the gallery into a compact panel with a blue original-size centered overlay,
opacity and hide/show controls. It shares insertion placement and never enters
project geometry or undo history. Close/back/late-request cleanup is covered;
small-asset preview padding contains the full stroke.

The running backend includes these endpoints. The empty project was preserved
and restored from `before-gallery-overlay-20260910-011636-831727`; simulator
remains disconnected/idle. No browser reload or hardware action. Verification
completed: full suite **1,489 passed, one intentional skip**, one existing
Starlette warning. The final stroke-padding correction was then verified by
**18 focused gallery tests**; typecheck and frontend build passed. Isolated
browser appearance inspected. Ian still owns native acceptance.

**Gallery follow-up, 10 September:** The reported preview/405 error came
from a detached September-8 backend serving new frontend files without gallery
routes. Replaced it with current code and verified live prepare HTTP 200 after
the helper exited. The empty untitled project was recovered from
`before-gallery-reload-20260910-005643-00dcc8`; simulator/disconnected state
was retained without hardware auto-connect. No browser page was reloaded.

Save and detail tag inputs now create removable boxes on Enter, support comma
input and unfinished drafts, and offer up to eight Most used tags by asset
count. Duplicate capitalization is ignored. The 405 dialog now explains the
backend mismatch. **1,483 tests passed, one intentional native lifecycle skip**,
one existing warning; typecheck and frontend build passed. Isolated browser
appearance checked; reload the page for Ian's interaction check.

**Asset gallery, 10 September:** Local frozen line assets can be saved from
layers and all working benches, browsed with thumbnails/search/tag/generator
filters, edited and inserted as independent baked copies centered at original
size. Layer capture preserves its own effects and animation frame before
external clipping; preparing a save never mutates the source or undo history.
Atomic JSON records preserve full paths; project SVG snapshots now serialize
17 significant digits to avoid six-decimal rounding on save/load.

Full hardware-free suite: **1,477 passed, one intentional native lifecycle
skip**, one existing Starlette warning. Typecheck and the suite's frontend
build passed. Browser coverage includes all bench adapters, save failures,
stale captures, nested Escape, deletion, independent insertion and refresh-only
retry after a committed insert. Corrected preview containment inspected in an
isolated browser; native appearance/feel remain Ian's acceptance. The running
app/backend were not restarted; no push, Pi deployment or hardware action.
[Workflow and storage contract](docs/ASSET-GALLERY.md).



**Animation families and drawing tools, 9 September:** Explicit persisted
ownership replaces name/visibility inference for live animation families.
Child deletion preserves siblings, one remaining restores an ordinary drawing,
and master Delete removes the family. Un-animate explicitly retains A. Ordering,
duplication, consolidation, capture interpolation and save/load preserve ownership;
master-only occlusion controls apply to materialized output. Pen and Shape return
to Select after successful drawing unless Repeat is enabled; Enter commits,
Escape cancels/exits, and failed writes retain drafts without duplicating successful
writes after preview failures.

Full hardware-free suite: **1,455 passed, one intentional native lifecycle skip**,
one existing Starlette warning. Typecheck and build passed. An earlier suite run
had a browser startup timeout; the full rerun passed. Final focused backend/browser checks: **28 passed**,
covering late integration details. The running app was not restarted; native input
and appearance remain Ian's acceptance. Nested layer groups are design-only in
ROADMAP.md. No push, Pi deployment or hardware action. The pre-existing untracked
Pi skill remains outside this work.

**Session wrap-up, 9 September:** Full suite **1,428 passed**, one intentional
native-app lifecycle skip, one existing Starlette warning. Typecheck and the
suite's rebuilt browser acceptance checks passed. Animation continuity, preview
cancellation, Ribbon curve sampling and fine Pen defaults are committed. Native
appearance and paper review remain with Ian; D3 and the expanded effect editor
remain in ROADMAP.md. The pre-existing untracked Pi skill is outside this work.

**Curve defaults, 9 September:** New Pen paths default to 0.05 mm, the
smoothest supported tolerance, including Pen silhouettes inside Shape. Pen,
Grammar, Text/Text Fill and SVG import now say “Curve tolerance” and explain
that lower values produce smoother geometry. The
module-authoring contract records fine curve defaults and explicit quality
trade-offs. Existing explicit recipe tolerances remain unchanged. Relevant
Pen/Shape/Grammar/Text/Ribbon and browser tests passed, with typecheck/build;
the live backend advertises both Pen defaults as 0.05 mm. Refresh the window.

**Ribbon curve sampling, 9 September:** Gentle curve directions are blended
before offsetting, reducing kinks inherited from flattened source segments.
Source geometry, crest profiles and sample counts stay unchanged; sharp-corner
and hidden fractured treatments are preserved. Full suite: 1,428 passed, one
lifecycle skip. Backend reloaded with the current empty project preserved;
native acceptance remains with Ian.
[Comparison and limits](docs/reviews/ribbon-curve-sampling-2026-09-09/README.md).

**Render cancellation, 9 September:** Superseded read-only drawing work is
cancelled cooperatively before edits/deletion wait on the project lock. Browser
requests are guarded against stale responses, layer edits coalesce, and the
elapsed timer follows the newest edit. Full suite: 1,423 passed, one lifecycle
skip; typecheck/build and final focused browser checks passed. The bar stays indeterminate; a native
geometry operation must return before cancellation takes effect. Backend reloaded
and the current three-layer animation restored; its full live render exceeded
the 30-second verification timeout. Refresh the window for new JS.
[Behavior and verification](docs/reviews/render-cancellation-2026-09-09/README.md).

**Animation identity correction, 9 September:** Animate and appended keyframes
share the original effect field; equal generator seeds including zero stay
fixed. Schema-typed interpolation covers effects and generators. Full suite
1,399 passed; final copy/capture safeguards passed 105 focused tests. Backend
is loaded; the current Homeostat drawing is retained. Prior Ribbon is saved as
`ribbon-midpoint-repaired-20260909-015259`.
[Contract and verification](docs/reviews/animation-random-identity-2026-09-09.md).

**Ribbon animation correction, 9 September:** Effect endpoint values are now
typed through their parameter models before blending. Whole-number JSON values
for Seed blend no longer round the intermediate frames. 116 related tests pass;
three distinct live intermediate frames verified after backend reload, with
the A/B drawing preserved. [Evidence](docs/reviews/ribbon-animation-2026-09-09.md).

**Magnetic corners extension, 9 September:** Ian approved position, rotation
and strength interpolation between four stored arrangements, implemented on
main with two X/Y sliders. Scatter strength ranges, per-magnet scatter locks,
canonical sizes, full recipe persistence and optional whole-route pole thinning
are included. [Behavior, review and evidence](docs/reviews/magnetic-corners-2026-09-09/README.md).
Full suite: **1,387 passed, one intentional lifecycle skip**, one existing
Starlette warning. Typecheck and isolated unbundled UI smoke passed. The final
Scatter-count display correction has a separate rebuilt browser regression run.
Main app/backend were not restarted at that checkpoint. The backend was
subsequently reloaded for the Ribbon animation correction; native and paper
acceptance remain with Ian.

**Ribbon session closed, 9 September:** Ian accepted the effect and requested
commit/push. Corner and edge interpolation repairs, the hidden fractured
experiment, loading activity and exact-preserving optimization are complete.
Latest verification: 1,371 tests passed, one lifecycle skip; typecheck and
built browser smoke passed. Paper output has not been tested. D3 and the
expanded editor remain deferred in ROADMAP.md.

**Magnetic field bench, 9 September:** Continuous curves are the default in the
new arrangement bench. Bars and independent poles are editable; seeded scatter,
whole-route escape removal, visibility, optional empty silhouettes, local undo
and Keep/Resume are implemented. Ian's later filings reference informed the
no-silhouette option. [Evidence and verification](docs/reviews/magnetic-bench-2026-09-09/README.md).
Full suite: **1,360 passed, one intentional lifecycle skip**; typecheck and
isolated source-only smoke passed. Native app restart and paper acceptance
remain with Ian; no hardware action.

**Native launch follow-up, 9 September:** At Ian's request, saved a separate
`before-magnetic-bench-20260909-002530` recovery project, restarted the backend
and reopened the native app. The saved Ribbon layer manifest matches the
restored project. Magnetic field is open with continuous curves, magnet bodies
hidden and empty silhouettes off. User judgement and paper output remain pending.

**Magnetic field study, 8 September:** Nine standalone drawings compare three
magnet arrangements with continuous curves, irregular chains and loose filings.
[SVG, image and review](docs/reviews/magnetic-field-2026-09-08/README.md).
The same field is preserved across each row; finite/bounded geometry is checked.
This is a visual study only: no generator or bench is registered, and paper
appearance remains untested. Ian's treatment selection precedes bench design.

**Ribbon update feedback and speed, 9 September:** A persistent animated
activity bar and elapsed time now cover effect edits, live previews and drawing
refreshes, including overlapping requests and failures. The silhouette lookup
reuses and indexes its spine: the actual corner fixture improved from 4.147 s
to 2.953 s (28.8%) with exact coordinate equality.
[Benchmark and UI evidence](docs/reviews/ribbon-performance-2026-09-09/README.md).
Full suite: 1,371 passed, one lifecycle skip; typecheck passed. Backend reloaded
with drawing restored and exact live geometry verified. Refresh the window for
the new status strip; native acceptance remains with Ian.

**Ribbon edge joins, 9 September:** Edge interpolation now stabilizes the
left/right width allocation through acute corner joins while preserving total
width modulation. The captured drawing retains 20 distinct, non-crossing
strands. Local asymmetry changes around severe corners; spine mode is unchanged.
The polygon-cutout trial is preserved as hidden `fractured_edges` (default off).
[Evidence and limits](docs/reviews/ribbon-edge-joins-2026-09-09/README.md).
Full suite: 1,363 passed, one lifecycle skip. Backend reloaded with the current
drawing restored; live output matches the reviewed candidate. Visual acceptance
remains with Ian.

**Ribbon hard corners, 8 September:** The live pen-path regression now retains
21 strands with zero self-intersecting strands or crossing strand pairs (previously
20 and 53). Overlapping corner supports are swept together; miter-capped radii
are recovered correctly. The six accepted study fixtures remain unchanged.
Full suite: 1,326 passed, one intentional lifecycle skip. See
[comparison and evidence](docs/reviews/ribbon-hard-corners-2026-09-08/README.md).

**Ribbon effect shipping pass, 8 September:** The accepted study is now a
registered Python effect with paper-space parameters, optional crest softening,
seeded per-flank softening, a shared outer-pair cutoff, and grouped controls.
Automatic density uses the actual assigned pen through normal, region, tween,
preview and consolidation contexts. See
[production status](docs/reviews/open-path-ribbon-2026-09-08/PRODUCTION-STATUS.md).
D3 and a popup effect editor are deferred in ROADMAP.md. The Mac backend was restarted with Ian’s authorization and its live effect
list includes Ribbon. The Settings restart action now uses a visible confirmation
dialog; its previous timed second click was hidden when the menu closed. User visual
and paper acceptance remain outstanding. Final suite: 1,322 passed, one native
app lifecycle skip; typecheck and built UI acceptance passed. No push or hardware
action.

**Final wrap-up verification, 8 September:** 1,289 passed, one intentional skip
(the app lifecycle test leaves the running Mac app alone), one existing Starlette
deprecation warning. Typecheck and isolated source smoke passed, including four
tabs, Second Reading and the chosen favicon. Earlier 1,290-pass results below
precede opening the native app. All session work is committed locally; no push.

**Favicon:** Ian selected the geometric scaffold in sheet white on black.
Installed as the web favicon and touch icon; frontend rebuilt. The separate
Mac application icon was also regenerated from the selected mark. The app was
opened at Ian’s request, and its running server was verified to serve the chosen
favicon. Preview reports were approved; native icon appearance is not yet confirmed.

**Cosmetic follow-up:** Ian approved all five finishing touches: paper edge/depth,
optical alignment, faint surface lift, readout spacing and quieter inactive borders.
[Sheen comparison](docs/reviews/ui-sheen-2026-09-08/index.html); 28 stable drawing
fixtures match the precision pass. Mac-only acceptance remains Ian’s.

**Session 2026-09-08: whole-app visual precision pass.**

Implemented Ian's approved precision-instrument direction across Compose, all
three benches, Plot, Pens, Settings, menus and shared controls. Shared type/spacing,
paired values, quieter structure, action priority and focus states retain Flexoki
and offline mono. Compact boolean labels and zoomed popup reachability are fixed;
the calibration ruler retains its physical length in a local scroll container.

[Matched before/after evidence](docs/reviews/ui-precision-2026-09-08/report.html)
and [implementation record](docs/plans/ui-precision-IMPLEMENTATION.md).
Full suite **1,290 passed**, including 112 browser regressions, after the final
dialog fit correction.
Typecheck/build and source-only evidence checks passed. Zoom evidence explicitly
uses CSS approximation and reduced viewport/DPR emulation. UI acceptance is
Mac-only: the Pi does not run the UI. Native Mac feel and physical output remain
for Ian. No push, hardware use or running-app restart.

**Session 2026-09-08: approved Compose and benches implementation.**

Ian approved the mockups and architecture direction (“ok i like it. go”).
Follow-up: visible working benches are only Venation, Homeostat and Second Reading;
other generators retain normal forms and time-axis layer Watch. This correction
passed 17 relevant browser tests and typecheck (full suite not repeated).
Implemented popup default with expansion, compact control shelves, explicit
selected-source scope, persistent expandable layers, versioned bench descriptors,
local error/focus lifecycle, Second Reading comparison, and Homeostat grouped
controls with observed telemetry. Same-page drafts and explicit Keep/Create remain.

[Implementation evidence and limits](shots/ui-benches-0908/README.md).
Full hardware-free suite: **1,285 passed**, including 107 browser tests;
build/typecheck and isolated source-only smoke passed.
Native feel and physical output remain for Ian to check. No push, hardware action
or running-app restart. Recovery and richer application services remain deferred.

**Session 2026-09-07: design interview complete; fresh-session handoff saved.**

[Next-session brief](docs/plans/ui-benches-next-session.md) records the agreed
layout direction and Ian's request for an open bench architecture. Compose and
benches are to be designed together, preserving specialised bench interactions
and allowing richer exchanges with the application in future. Next deliverables
are mockups and an architecture proposal, not implementation. Broader
reorganisation is welcome, with radical changes reviewed with Ian first.

This wrap-up changes documentation only. Existing verification is recorded below
and was not rerun; native-app judgement remains pending. No push.

**Session 2026-09-07: approved cosmetics pass, ready for Ian to check.**

Flexoki surfaces and contrast, clearer mono labels, consistent controls and SVG
action icons, stronger focus, and visible pending slider states. Second Reading
now fits the complete working frame inside its stage, including when help grows;
small windows scroll once the stage reaches its minimum. No generator policy,
workflow architecture, hardware or saved-project changes.

[Implementation and captures](docs/reviews/ui-review-2026-09-07/cosmetics/README.md).
The full hardware-free suite passed **1,267 tests**; build/typecheck and isolated
built/source browser checks passed. All **96 UI tests** passed again after the
final label/hover polish.
Native macOS and Pi appearance/input feel remain for Ian to judge. No push or
running-app restart.

**Session 2026-09-07: holistic UI review, documentation only.**

The [illustrated report](docs/reviews/ui-review-2026-09-07/index.html) and
[editable source](docs/reviews/ui-review-2026-09-07/REVIEW.md) contain about
11,000 words, 18 UI findings, five architectural proposals, three structural
sketches, source/visual evidence and a phased roadmap. The review preserves
bench-and-bed and the mono voice while proposing explicit editing scope,
recovery and visual comparison of alternatives. Implementation is not approved
by this review alone.

Live inspection used an isolated built copy, temporary config/projects and
simulator only. Reproduced: Second Reading stage clipping at smaller windows,
volatile unkept alternatives, modal focus escape and preview errors behind the
modal. A separate hardware-free API check confirmed guide edits bypass undo.
Concurrency and rendering proposals retain their source-only/measurement limits.
The full isolated baseline finished **1,263 passed**, with one dependency
warning. The report reader was checked at desktop and narrow sizes, with local
links and navigation verified. No hardware, running user app or user project
was touched. No application source changed.


**Session 2026-09-06: Second Reading recovery and agreed experiment.**

First was recovered from prior tool history. After Ian’s follow-up, Responsive is the default; ordinary readings no longer make thick reinforcement stacks. All 30
original study cells match saved geometry precision and decisions. Shape and
Relation experiments are selectable, with separate Attention/Departure/Scale
meanings, occasional guided wandering, and clip / containment / whole-element-fit
boundaries. Reading changes are recorded next-turn events. The existing bench,
branches, capture smoothing and Keep/Resume remain.

A bounded Sol image-first review included neutral populations and altered
variants, followed by isolated sequences and a provenance correction. The lead
then changed only the sampling-dependent echo deformation. Iteration sheets,
weak cases and actual lead-driven alternating captures are preserved under
`shots/second-reading-recovery{,-final}-0906/`. The final placement fix fits the
whole source frame through portrait/landscape creation and view changes, preserving
physical bed bounds. No hardware or Ian's running app was used.

Read `docs/reviews/second-reading-0906-lead.md` for judgement and limitations.
The latest cleanup adds visible Pen smoothing (including during capture), Randomize for the next seed, persistent pending new-drawing settings, active/pending boundary labels and a dashed nominal sheet in overshoot mode. Turn inside now actually returns inward instead of squeezing against the edge. Historical geometry remains reproducible with the internal historical_stacks recipe flag. Final verification: **1,262 passed, 1 skipped**; frontend build/typecheck and a separate exact-recipe Resume/placed-canvas check passed.

**Session 2026-09-04 (Opus 5): pass 4's A2 — the homeostat — designed, built,
reviewed, extended twice, and pushed.**

Nine commits, suite **1121 → 1182**, all on `main` at `67824b1`.

**What shipped.** `sources/homeostat.py` + `sources/_homeostasis.py`: Ashby's
homeostat as a generator. A pen wanders; an essential variable is measured
against a viable range; when it sits outside for `patience` consecutive steps
the pen's handwriting is **rerolled blindly** — no gradient, no search, no
memory of what failed. Oehlen's regime collision with a motive: the seam lands
where the system was in trouble.

Then two rounds on top of it:

- **Coupled pens** (1–6 units, one shared occupancy grid, no concept of each
  other — they meet only in the ink). This also closes **A4, the seam**:
  independent fronts with identical local rules and no awareness of each other.
  Each unit gets its own RNG stream, without which "coupled" cannot be told
  apart from "the random numbers moved".
- **Self-surprise and ultrastability.** A fourth variable that is not a
  property of the ink at all: the pen's own prediction error about its own next
  turn, from two exponentially-weighted timescales, normalised by the hand's own
  spread — so a passage that has become *predictable* is itself a crisis. And
  `escalation`, Ashby's second loop: a reroll that **failed** widens the space
  the next hand is drawn from, a long viable passage narrows it. The drawing
  gets an arc instead of a texture.

Also this session: **⤓ Consolidate & merge** in the layers dock (bake several
selected layers and join them into one, one undo step), and
`docs/BRIEF-new-generator.md` — a self-contained brief for handing the next
generator to another model, whose section 6 is an honest critique of what this
module cannot do.

**What it looks like.** `shots/homeostat-bench-0904/` (Ian's own four runs, and
what they showed that the renders did not), `shots/homeostat-coupled-pens.png`,
`shots/homeostat-surprise-arc.png`.

**What is unverified.** Everything on paper. No sheet from pass 4 exists —
homeostat, venation and the eigenfunction fill are all unplotted. The bench
half is done (Ian drove it on 2026-09-04); the pen half is not.

**Where the ceiling is,** in one line, from the brief's critique: every variable
this module can measure is a first-order statistic of ink, so it has no
vocabulary of *relations between marks* — and relations are what make a drawing
read as drawn rather than deposited.

Ledgers: `docs/plans/homeostat.md`, `-IMPLEMENTATION.md`, `-RESULTS.md`.
