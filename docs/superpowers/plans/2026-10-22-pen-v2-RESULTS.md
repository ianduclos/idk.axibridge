# Pen v2 — results, rulings and deferred items

Built 2026-10-22 on branch `pen-v2` (ddc2a0d..80ce7bc) from [the plan](2026-10-22-pen-v2.md), task by task with a review after each and a final whole-branch review. Full suite at head: 2390 passed, 2 skipped, 0 failed. Nothing here has been checked by hand in the app yet.

## Rulings the lead made (Ian can overturn any)

- Ruling 1: pen_ops tests load the SOURCE file into a blank chromium page (data: URL import or page.route), not via the app server — the pure module must be testable independent of static_dist — cost if wrong: test harness differs from other UI tests, trivial rework.
- Ruling 2: T7 adds the #pen-mode segment with bezier + curvature only; T8 adds the sketch button, T9 the knife button — no buttons for unbuilt modes — cost if wrong: none.
- Ruling 3: T3 (new files only) runs in parallel with T2 (curvefit/api) — disjoint files, path-only commits — cost if wrong: an index.lock retry or a mixed commit to untangle
- Ruling 4: fit_bezier must never return more than pen._MAX_ANCHORS — coarsen tolerance until it fits — the product call is "always give an editable path", since a regenerate 422 after a sketch is a dead end — cost if wrong: very long dense sketches lose detail silently at the top of the slider
- Ruling 5: applyArmDrag gains optional opts {isEnd} so open-end anchors never grow an outward arm — cost if wrong: signature differs from plan's 4 params (backward compatible)
- Task 2: review -> Needs fixes (Important: Ruling 4 cap missing; corners tolerance-independent so need corner pruning). Fix round 1 sent (HEAD before fix c026f86; T2 commit 6ab1ced)
- Ruling 6: upgraded T2 Minor "closed <3-point loop labelled smooth with non-opposed handles" to Important — spec Settled 1 makes join labels drive editing, a wrong label reshapes on first drag — cost if wrong: a few lines
- Ruling 7: T5 bend grabs with t<0.05 or >0.95 route to the nearer anchor (addresses T3 deferred minor) — cost if wrong: slightly smaller bendable zone near points
- Ruling 8: T5 edits write the classified join explicitly on touched anchors so edits stick (T3 deferred minor) — cost if wrong: saved params gain join fields (geometry unchanged)
- Ruling 9: joining a subpath's own two ends closes it — cost if wrong: none expected
- Ruling 10: regenerate's `coalesce` accepts bool | short token string; a token folds only checkpoints with the same (regen, layer, token) key; pen sends a fresh token per drag — global constraint "one ⌘Z per gesture" requires it — cost if wrong: small API widening (MCP unaffected, bool still works)
- Ruling 11: ⌘Z / ⇧⌘Z work while the pen tool is active: with a pending path ⌘Z removes its last point, otherwise normal undo/redo — spec "as direct as Illustrator/Figma"; pre-existing gap but the new gestures make it glaring — cost if wrong: small keyboard-handler change in main.js
- Task 5: review -> Needs fixes (Important: refresh overwrites queued edits — fast J-J-J / flick-release snap-back; Rulings 10, 11 not implemented). Fix round 1 sent (HEAD 40575bf)
- Ruling 12: T5 fix round also takes minors 4 (selection clears on layer change — controller ruling compliance), 5, 6, 9 (extract queue + edit gestures out of 1024-line pen.js before T6–T10), 10 (tests) — cost if wrong: a larger fix round
- Ruling 13: switching pen mode mid-draw freezes already-placed pending points as drawn (bezier points → corners with their arms); only new points follow the new mode — nothing on screen changes on a mode switch — cost if wrong: small behaviour change Ian may want different
- Ruling 14: entering sketch mode with a pending bezier/curvature path commits it (same as a tool switch does) — cost if wrong: Ian may prefer it kept pending
- Task 9: implemented d541b44 (carried T8 fixes) + cf6d083; knife mode also commits pending path (Ruling 14 extended); slider re-dispatches foreign keys as synthetic keydown; review dispatched (opus)
- Ruling 15: Ruling 14 extended to knife mode (entering knife commits a pending path) — accepted — cost if wrong: same as 14
- Ruling 16: the dead-zone fix lands as a second commit (no amend: history edits need Ian's ask) — reverting A2 means reverting both commits — cost if wrong: one extra revert
- Ruling 17: Task 11 (docs-only diff) is reviewed inside the final whole-branch review rather than a separate task review — its doc claims (tween None-vs-str step, 2000 cap) were verified by T1/T2 reviews — cost if wrong: a doc inaccuracy caught later
- Ruling 18: overturn Ruling 13's label — frozen pending points keep classifyJoin(a), protected by `fixed` only (reviewer: forcing "corner" changes glyphs and kinks on later drag) — cost if wrong: none
- Ruling 19: drop the wall-clock assert in test_curvefit; keep the machine-independent fit-pass bound — cost if wrong: a perf regression only caught by feel
- Ruling 20: Escape mid-drag keeping the drag (final-review minor 9) is NOT fixed in this wave — reported to Ian — cost if wrong: one more small change later

## Deferred minor findings (not fixed; triaged as can-wait by the final review)

- Task 1: minor (deferred): round-trip test RED masked by typo (GREEN assertions real); tween test exercises _blend_geometry directly, not via session
- Task 3: minor (deferred): bendSegment gain near ends (t clamp 1e-3 lets 1mm drag throw 34mm arm) — T5 gesture should route near-end grabs to the anchor or clamp t to ~[0.05,0.95]
- Task 3: minor (deferred): joinEnds self-join detection by object identity; kind taken from first subpath
- Task 3: minor (deferred): stale joins at open ends after delete; applyArmDrag never persists inferred class
- Task 3: minor (deferred): tests lack same-segment multi-crossing knife case
- Task 2: minor (deferred→included in fix): runtime guard 10s too loose; _anchor nulls non-finite handle silently
- Task 3: minor (deferred): smooth anchor whose opposite arm is [0,0] doesn't grow it (degenerate input only)
- Task 2: minor (deferred): 3s timing test has ~1.8x headroom on Mac; Pi runs backend suite slower — final review to decide (env-scaled limit?)
- Task 4: minor (deferred): canvas resize without window resize not observed (ResizeObserver); redundant pen-pending-change per wheel tick; pending vs committed fill rule differs (Ian's eye); shapes.js preview now constant 2px
- Task 2: minor (deferred): wall-clock 3s guard flaky under machine load (load avg 20-69 seen from unrelated builds) — final review: keep fit-count test, relax/drop wall-clock assert
- Task 2: minor (deferred): over-cap worst case is 4 tolerances incl. inf fallback; test asserts <=3 (passes on tested walks; implementer ran 46/46 twice)
- Task 5: minor (deferred): synthesized dblclick compares screen position not point identity; mergedContinue trusts cont.si across undo
- Task 5: minor (deferred): rapid-J test filters every "status of 409" console line; narrow to /api/plan and /api/compose/resolved
- Task 5: minor (deferred, pre-existing): external-sync timer refreshProject between queued posts skips reapplyQueued
- Task 6: minor (deferred): Space-slide clamped at bed edge changes the arm vector; new place gesture starts space=false while Space held
- Task 7: minor (deferred): curvature hover rubber-band lacks in-arm (cosmetic); pending double-click compares click pos not placed (snapped) point; #pen-mode display:contents drops group semantics in old WebKit
- Task 7: minor (deferred): in curvature mode, frozen bezier pending points don't show arm knobs
- Task 8: minor (deferred): lastFit set after Escape/mode switch during commit fit (harmless); Repeat toggle ignored in sketch mode (doc)
- Task 9: minor (deferred): knife preview recomputes crossings per move (bbox prefilter if dense layers lag)
- Task 10: minor (deferred): ⌥ during placement never writes join (differs from ⌥ re-edit)

## Not fixed, worth Ian's eye

- Escape during a drag keeps the drag (a pro tool would cancel it).
- In sketch mode a press exactly on a point drags that point; a sketch can't start on an existing end.
- A2 (grab arms directly) is two commits, 8508e08 and 4caa8b3: `git revert 4caa8b3 8508e08` removes it cleanly.
