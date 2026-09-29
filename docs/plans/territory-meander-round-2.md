# Next round: meander 2 (plan)

Status: planned 2026-09-29, not started. Start it in a fresh session.

## Why

Round 1 of meander landed. Ian on the published page (Version 5 of https://claude.ai/artifact/Bawx12VN4uRgWR2wU2Lso3), verbatim: "bah this is super nice. how can we keep going? keep pushing the thing". He chose all four directions below, then dropped the paper test. Evidence and the mechanism are in `shots/meander-0929/README.md`; the reviews are in `docs/reviews/meander-sonnet.md` (rounds 1–2); the design is in `docs/research/meander/`.

His standing aesthetic direction is in `docs/plans/territory-meander-round.md` ("Ian's aesthetic direction"). Carry that section verbatim into every agent brief, as last round.

## Ian's picks (29 September), in the order to build

1. **Tangle register.** The reviewer: "no tangle anywhere". Ian's words: "nuanced tangle that becomes textural at places, organic line based at others". Candidate: the brief's deferred *braid/knot at necks* (synthesis brief §9; brainstorm 1 idea 2). Where two bends touch, the neck becomes a local tangle rather than a clean cutoff or refusal. Kill it on sight if it becomes v5's hairball: the same dark fanning cluster in every cell.
2. **Composition.**
   - Blend the territory and from-nothing centrelines. From-nothing beat territory in 4 of 6 seed pairs, and inheritance was invisible (0/6 pairings), but territory gives one coherent family per seed.
   - Also try crop-from-a-larger-field (brainstorm 3 idea 6) for weirder compositions and shaped negative space.
3. **Polish what fired in round 2:**
   - identical spiral curls (M12, M15, M17, M18);
   - rails on gentle arcs and straights (M09, M10, M13);
   - no protagonist in the thin cells (M01, M06, M07, M14).
   - Reviewer's suggestion: make dropout bands curvature-gated, and use 2–3 unequal searching patches per cell.
4. ~~Paper test~~ — dropped by Ian (29 September, mid-round: "forget the paper test").

## Roles and loop (unchanged)

Opus brainstorms, Sonnet researches and does the blind review (drawing-review procedure), Fable writes the synthesis and advises, and the lead owns direction and acceptance. At most 2 blind review rounds before Ian. Use neutral cell IDs with recipes withheld, and supply close views (`close.js ID:auto`). Commit on `feat/territory-bench` at checkpoints.

Lessons from round 1 worth keeping:
- Measure before tuning. `res.T._geo` and the kd-style coverage probe found the causes; eyeballing thumbnails did not.
- Review sheets need 6 cells per sheet plus 100 × 70 mm close views; round 4's downscaled strips hid line quality.
- The prototype is CommonJS inside an ESM repo: `tools/territory-prototype/package.json`. Build with `build.sh`.

## Not in scope

- Any `axibridge/` change.
- Plotting.
- Colour or multi-pen.
- The bench port (a later decision, once Ian accepts a direction).
