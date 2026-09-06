---
project: idk.axibridge
state: active
updated: 2026-09-06
machine: mac+pi
summary: Second Reading bench is implemented; Ian prefers the first response version. Next session recovers that baseline and tests shape, awareness, controls and element boundaries with a Sol reviewer.
next:
  - "Start with docs/plans/second-reading-next-session.md — latest user correction and agreed experiment, not the older optimistic study verdicts"
  - "Recover the first response baseline honestly; no selectable restoration or new Attention/Departure/Scale controls are implemented yet"
  - "Use project skill drawing-review for a bounded Sol second eye on whole iteration sheets; calibrate it and retain primary-agent ownership"
  - "Paper and older bench/hardware eye-checks remain outstanding; do not plot automatically"
handoff_for: ian
---

# idk.axibridge — status

**Session 2026-09-05–06: Second Reading bench and aesthetic experiments.**

Interactive human/machine turns, exact replay, branches, Keep/Resume and capture
smoothing are implemented. Several generator revisions and reproducible studies
are retained. **Ian's latest judgement: the first version was more responsive;
later iterations made little progress.** Mechanical completion is not aesthetic
acceptance. Current source remains the encounter revision.

The next experiment is agreed, not implemented: recover the first baseline,
improve shapes/proportions, include occasional homeostat gestures, reconsider
awareness/controls and element-friendly boundaries. Project skill `drawing-review`
defines Sol's bounded aesthetic role, with the primary agent in charge. Start
at `docs/plans/second-reading-next-session.md`; see
`docs/reviews/drawing-review-skill-trial.md` for the initial reviewer trial.
No hardware commands were sent. Wrapup verification: **1,239 tests passed**;
frontend build/typecheck and a separate three-case capture–Keep–Resume Playwright
smoke passed on a throwaway isolated server. The project skill validated and
its Sol forward-test is recorded with a specific limitation. Commit closes this session;
original and later studies remain in `shots/second-reading*/` as evidence.

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
