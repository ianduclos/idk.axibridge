---
project: idk.axibridge
updated: 2026-07-21
entries: 3
---

### Three unmerged session branches — pen tool, tween morph, hatch join — opened 2026-07-21, owner: ian
- done: all three built + suites green + live-verified (see STATUS.md this
  session). feat/pen-tool (⚓ pen tool, RESULTS doc, suite ~492),
  feat/geometry-morph-tween (pen/drawing shapes MORPH in tweens + `cosine`
  ease, suite 499), feat/hatch-connect-strokes (`connect_strokes` cuts pen
  lifts, suite 497). Nothing pushed; nothing on main.
- next: review + merge. ORDER MATTERS — feat/geometry-morph-tween is stacked
  on an OLDER feat/pen-tool tip (`cbb2df3`); rebase it onto the current pen
  tip (`4ecb49e`) before merging, or feat/pen-tool's last two commits
  (`7af3fb4`, `4ecb49e`) look reverted. feat/hatch-connect-strokes is
  independent (off main). At merge: add a CHANGES.md feed entry (tween
  geometry semantics change — pen/drawing shapes morph instead of stepping)
  and pull the idkpi clone.
- blockers: none — awaiting Ian's review/merge call.
- context: docs/plans/pen-brush-tools-RESULTS.md (pen tool, all fix rounds);
  MODULES.md + ROADMAP.md on feat/geometry-morph-tween (morph resolution);
  `git log --oneline --all` shows the three tips. Brush tool (0c) still
  deferred — pen-brush-tools.md Part 2.

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
