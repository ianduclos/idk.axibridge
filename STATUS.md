---
project: idk.axibridge
state: active
updated: 2026-09-09
machine: mac+pi
summary: Magnetic field bench is implemented; native and paper acceptance remain with Ian. The Mac backend serves Ribbon.
next:
  - "Try the open Magnetic field bench, including hidden magnets without silhouettes"
  - "Check Ribbon on real drawings"
  - "Check the open Mac app for native appearance and the new scaffold icon"
  - "Continue Second Reading alternating-use and paper review"
handoff_for: ian
---

# idk.axibridge — status

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
