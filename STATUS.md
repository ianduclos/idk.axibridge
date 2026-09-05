---
project: idk.axibridge
state: active
updated: 2026-09-04
machine: mac+pi
summary: Pass 4's A2 — the homeostat — is built, reviewed, pushed and seen in the bench, with self-surprise and Ashby's second loop on top; nothing from the whole pass has touched paper yet.
next:
  - "Plot something. Nothing from pass 4 has met a pen — not the homeostat, not venation, not the cymatic fill — and the homeostat draws ONE continuous stroke, which should plot unusually cleanly"
  - "At the bench: measure=surprise (band ~0.30 +- 0.20) against the default crowding on one seed; then escalation 0.4 with variety STARTING low (~0.35), watching the variety trace"
  - "Hand docs/BRIEF-new-generator.md to Astra and let it build a generator; its section 6 is the honest critique of what the homeostat cannot do"
  - "The biggest opening in that critique: every variable the homeostat can measure is a first-order statistic of INK. It has no vocabulary of relations between marks — parallelism, enclosure, alignment, rhyme — which is what makes a drawing read as drawn"
  - "Older, still open: colour separation's CHECKME.md 2026-08-17 section, and bench/hardware eye-checks back to 2026-07-13; the multi-pen swap queue has never touched a real AxiDraw"
handoff_for: ian
---

# idk.axibridge — status

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
