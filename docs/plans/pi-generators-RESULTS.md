# Results: four generators/effects — scheduled Pi run, 2026-07-10

Executed by Claude (Fable 5) headless on idkpi per `pi-generators.md`.
All four modules shipped completely, in the planned priority order, one
conventional commit each on `feat/pi-generators` (pushed). Suite went
242 → 276 passing, hardware untouched.

## What shipped

| Module | File | Tests |
|---|---|---|
| Continue strokes (effect) | `axibridge/effects/continue_strokes.py` | `tests/test_continue_strokes.py` (8) |
| Misremembered image (source) | `axibridge/sources/misremembered.py` | `tests/test_misremembered.py` (7) |
| Grammar w/ transgressions (source) | `axibridge/sources/grammar.py` | `tests/test_grammar.py` (11) |
| Two hands (source) | `axibridge/sources/two_hands.py` | `tests/test_two_hands.py` (8) |

Every module was verified visually with throwaway PIL sweeps under `/tmp/`
(grey intention / black output grids), iterating until the aesthetic target
read on the image — that loop is where most of the changes below came from.

## What the visual loop changed (the interesting part)

- **continue_strokes**: fixed-width turning-angle bins collapsed smooth
  layers into "continue dead straight". The quantization grid now adapts
  to the layer's own angle spread — a wiry layer continues wiry, a straight
  one straight. Seams land tangent-continuous and drift over ~10 mm, as
  briefed. At temperature 0 a hook continues into a closed loop (the most
  typical turn, applied forever) — reads as fluent-but-hollow, kept.
- **misremembered**: the first cut spent the whole budget tiling the
  darkest mass with tiny blobs and looked like edge detection everywhere
  else. Three structural fixes: (1) blobs are a capped phase (~12% of
  budget) of amoebas sized by probing the mass field in 8 directions;
  (2) trace arms are short, so long contours come out as several
  overlapping recalled pieces instead of one perfect trace; (3) the recall
  threshold relaxes as strong structure runs out, so big budgets strain
  into faint low-confidence details. Even firm strokes carry a slow
  lateral drift — memory is never exact.
- **grammar**: violations at the "haunted" setting (budget 2–3,
  violation 0.2) were imperceptible because salience preferred the
  composition center, where motifs are smallest. Salience is now
  discounted by placed motif size ("a violation nobody can see isn't a
  transgression"), and aliens for rule-swaps share the host motif's local
  space — a radial petal swaps into a *stem*, i.e. a petal that forgot to
  close, which is the single best haunt in the sweep.
- **two_hands**: worked close to spec on the first render; the agree
  column reads as one drawing in two moods, the argue column as blocking
  and crossing. The pen-split determinism check (both == hand_a ∪ hand_b,
  in order) passed and is pinned by a test.

## What I'd tune next

- **misremembered** on a real photograph: the synthetic test face is
  high-contrast, so mid-confidence marks were rare. On a soft-gradient
  portrait the confidence→mark mapping should show more range; if not,
  widen the searching-mark band (the 0.55 confidence threshold).
- **grammar** could use 1–2 more grammars (the plan said 2–4; three
  shipped). A grid/lattice grammar would give transgressions the classic
  "one cell rotated 3°" reading. Also worth trying: violations that
  propagate to a site's *subtree* in the branching grammar (currently the
  subtree stays put, which reads as a break rather than a lean).
- **two_hands** agrees fastest with the freehand effect stacked on top
  (as the plan predicted for misremembered too). A genome-preset store
  (IDEAS pass-1 UI principle 2) is the natural next step; params are
  already grouped for it.
- **continue_strokes** `both_ends` on filled-but-open paths: fine, but a
  future "seam pen" (different pen for continuations) would need the
  emissions split like two_hands' `draw` — same trick would work.

## Surprises

- No pyaxidraw/hardware friction at all — the suite is genuinely
  simulator-only, as promised.
- One pre-existing roster test (`test_app.py::test_state_shape`) pins the
  effect id list exhaustively; adding any effect module requires touching
  it (sources are pinned with `>=`, effects with `==`). Amended into the
  module-1 commit.
- Numpy was already in the venv (used it for the misremembered gradient
  field); budget 800 on the Pi runs in under a second at working
  resolution, so the report_progress plumbing barely matters there —
  kept anyway per MODULES.md.
