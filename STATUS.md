---
project: idk.axibridge
state: active
updated: 2026-09-07
machine: mac+pi
summary: Holistic UI review is ready for Ian, with reproduced trust issues, design sketches and a phased proposal; application behaviour is unchanged.
next:
  - "Read docs/reviews/ui-review-2026-09-07/index.html; choose the first implementation scope from M1-M6"
  - "Review F01-F05 first: sheet fit, preservation, undo, local errors and modal focus"
  - "Second Reading still needs Ian's alternating-use and paper judgement; see its existing handoff"
handoff_for: ian
---

# idk.axibridge — status

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
