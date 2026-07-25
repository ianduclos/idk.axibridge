---
project: idk.axibridge
updated: 2026-07-25
entries: 4
---

### hatch_fill connect_strokes v2: boundary-hugging connector — opened 2026-07-25, owner: opus
- done: root-caused the "loose ends" Ian saw on a concave/holed shape
  (screenshot this session) — `_join_where_possible`'s straight-line-only
  connector test fails constantly near cusps/holes, exactly where joining
  matters most. Loose plan written: `docs/plans/hatch-connect-strokes-v2.md`.
- next: implement the boundary-hugging connector (walk the shape's own
  boundary ring between two endpoints when the straight connector fails,
  instead of forcing a lift) — the fix Ian specifically asked for. The plan
  doc also notes two smaller, independent wins (min-length fragment filter,
  greedy nearest-reachable join) that are worth doing alongside it but
  aren't the main ask.
- blockers: none — this is intentionally a loose/unfrozen plan (unlike the
  other `docs/plans/*.md` briefs), leaving the exact mechanics to whoever
  picks it up.
- context: `axibridge/effects/hatch_fill.py` (`_hatch`, `_join_where_possible`,
  lines ~56-105); `docs/plans/hatch-connect-strokes-v2.md` has the full
  writeup, constraints (hole still forces a lift, crosshatch passes never
  join, effects stay pure), and a verification sketch.

### Post-merge follow-through: idkpi pull + push + bench check — opened 2026-07-25, owner: ian
- done: all four pending branches (feat/nested-tween-morph, feat/pen-tool,
  feat/geometry-morph-tween, feat/hatch-connect-strokes) merged to main in
  dependency order, suite 511 green throughout. geometry-morph-tween was
  rebased onto pen-tool's advanced tip as flagged; the rebase's tween.py
  conflict exposed a real regression (nested-tween-morph's
  `_source_paths_at` had switched to `effective_generator`/`lerp_params`
  directly, bypassing `blend_generator_params`'s captured-geometry deep-lerp
  — pen/drawing shape morph would have silently stopped working). Fixed by
  applying the same deep-lerp inside `_source_paths_at` on the
  post-reduction param dicts; caught by
  `test_pen_tween_morphs_shape_continuously_not_stepped` failing before the
  fix. CHANGES.md feed entry filed (2026-07-25 idk.axibridge entry).
- next: pull the idkpi clone (semantics changed: tween-of-tween lifted for
  same-generator, pen/drawing shapes morph instead of step); push main to
  origin (confirm with Ian first — currently far ahead, not yet pushed);
  bench-verify pen tool + animated pen morph on paper; once confirmed
  nothing else needs them, delete the four now-merged local feature
  branches.
- blockers: none — routine follow-through, no design decision pending.
- context: `git log --oneline main -8` shows the four merge commits atop
  `8164dc8`; `axibridge/tween.py` `_source_paths_at`/`blend_generator_params`
  docstrings explain the two call sites and why both apply the geometry
  deep-lerp now.

### Bench eye-check of the 07-16→19 wave — opened 2026-07-19, owner: ian
- done: generator v2 (misremembered scribble masses + tone dial, glyphgram
  coherent-field + continuity), bench latch with coalesced undo, draw tool
  + response brushes all merged (main, suite 430); screen-level eye-checks
  passed via rendered PNGs and Playwright acceptance.
- next: plot on paper — (1) misremembered v2 on a real photo (tone ≈ 0.35,
  compare mass_style scribble vs blob), (2) glyphgram continuity 0.6 vs 1.0
  at pen width, (3) a response-brush stroke (watch dash density: ~174 lifts
  per stroke; a sparser dash variant is the queued tune), (4) velocity tube
  now ships WITHOUT centerline by default — confirm that reads right.
- blockers: none.
- context: docs/plans/draw-mode-RESULTS.md,
  docs/plans/response-brushes-RESULTS.md, ROADMAP 0a–0c.

### Bench eye-check of the URGENT round — opened 2026-07-13, owner: ian
- done: all 11 URGENT items merged to main (`16fc350`), suite 382,
  12/12 automated live checks passed.
- next: Ian verifies at the bench the four behavior changes machines can't
  judge: (1) image output now centers on the bed — does it feel right with
  stacks/regenerate? (2) image_threshold band select on a real photo,
  (3) portrait "Width (mm)" now means on-paper visual width, (4) the
  viewAxis fader fix — one fader's drag direction deliberately flipped in
  portrait (correct per the rotation math; revert candidate if it feels
  wrong: see the feat(view) commit).
- blockers: none.
- context: ROADMAP.md URGENT section (struck through, with notes);
  `tests/test_view_coherence.py` locks resolve view-independence.
