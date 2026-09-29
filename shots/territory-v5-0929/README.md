# Territory v5: searching lines (29 September 2026)

Ian's brief:
- "Bit too concrete … open shapes based on the compositions we had before … more unpredictable and more dense."
- "Stranger yet coherent forms. More weight at parts and less at others. Nuanced tangle that becomes textural at places, organic line based at others. Painterly. Dynamic. Make you ask what's really going on."

Other constraints: the base is the v2 Territory lines, and there is one pen only. His own sketch of the vibe was shared in the session and is not in the repo.

Artifact: https://claude.ai/artifact/Bawx12VN4uRgWR2wU2Lso3, version 4, "Searching lines v5" (private). The render mode defaults to v5.

## Process

1. **Brainstorm:** three Opus agents (searching line, registers, forms).
2. **Research:** two Sonnet agents (techniques, artistic procedures).
3. **Synthesis:** a Fable brief.
4. **Build.**
5. **Review:** a blind Sonnet review of the test matrix.
6. **One iteration.**

All reports are in `docs/research/territory-v5/`. The review is "Round 4" in `docs/reviews/territory-v2-0929-sonnet.md`.

## Mechanism (post-pass on the drawn v2 ink; `t_v5.js`)

- **Contour graph.** Built from the final *unfaded* contours, excluding a 6 mm sheet margin. Junctions become nodes. Occupancy is lineage-aware: strokes of related edges may touch, and all other ink is a wall.
- **Sediment and reduction.** Each border's earlier positions (per-arrival snapshots) are matched along normals. Positions that held still are restated in place; ones that moved become drifting ghosts. Reduction keeps the oldest and newest passes plus a few far-apart middle ones.
- **Searching passes.** 1–3 restatements. Each is offset from the previous pass rather than from the original, and anchored at junctions so ink piles there.
- **Commits.** A firm line runs through junctions onto a neighbouring contour by good continuation.
- **Economy.** The largest camp is the silent winner: its ground and edges stay single. One protagonist component gets the full pass budget.
- **Knot and hooks.** At most one varied knot per sheet, at the most doubted junction. Hooks appear only at T-ends.
- **Events.** One per drawing at most, and about a quarter of drawings have none: cancel stroke, aperture lip, net (rim streamlines stop before the peak), or rigid chord.

## Sheets

These are round 4, blind. Ha is full v5, Hb is sediment only, Hc has economy off, Hd has the aperture forced, He has the net forced, and Hf is plain v2. See `recipes.json`.

The reviewer judged Hb closest to the sketch. The failures were hairball knots, repeated crescents, economy-off scribbling, and ripple nets. `sheet-V.png` shows the default after the round-4 fixes and has not been reviewed.

Everything was judged on screen only; nothing has been plotted.
