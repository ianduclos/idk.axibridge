# Meander 2 (29 September 2026)

Round 2 of meander, after Ian said of round 1: "bah this is super nice. how can we keep going? keep pushing the thing". He picked four directions: tangle, composition, polish, and a paper test. He then dropped the paper test ("forget the paper test"). The plan is `docs/plans/territory-meander-round-2.md`.

Artifact: https://claude.ai/artifact/Bawx12VN4uRgWR2wU2Lso3 (private), the next version after Version 5. Render is Meander; the new controls are Tangle, Work map, Graft and Found window. Everything was judged on screen only; nothing was plotted.

## Process

The research reports and the synthesis brief are in `docs/research/meander2/`:
1. Two Opus brainstorms, on tangle and on composition.
2. One Sonnet research report on tangle procedures.
3. A Fable synthesis brief.
4. The build (`tools/territory-prototype/t_meander.js`), in four checkpoints.
5. Two blind Sonnet reviews, "Meander 2, round 1/2" in `docs/reviews/meander-sonnet.md`. Their sheets are in `round1/` and `round2/`, with recipes in `withheld/`.

## What changed

- **Tangle (the new register).** At a band's most active swell, or at a refused neck, the band's own strands lose rank, spacing and continuity along 40–120 mm, then regather. It is the line losing order, not an object added to it. There are at most 2 zones per sheet, and about 1 sheet in 5 has none. A per-zone metric (aspect, tangent deviation, tight curls) guards against v5's hairball, and it never fired.
- **Work map.** Render weight follows where the river actually migrated (accumulated migration speed), blended 50/50 with the random activity field.
- **Rails.** A gentle arc (radius over 80 mm) gets at most a third of its swell, and an absolute speed floor stops channels that barely moved from getting a manufactured swell. Dropout is heavier on gentle arcs.
- **Curls.** Channel tails no longer coil into spirals. Migration tapers over the last 25 mm, and tails are cut back to a 60–150° hook.
- **Searching register.** 2–3 patches of unequal size per sheet, instead of one.
- **Graft.** From the territory, only channels touching the trunk are kept, about half of the minors; the rest sprout from the trunk's bends. Graft 1 reproduces round 1 exactly (regression checked).
- **Found window.** This option simulates on a 1.6× field and chooses the frame by a score. It is **off by default**: the reviewer read the crops as excerpts or details, and turning it off gave whole drawings with shaped voids.

## Where it landed (round-2 reviewer)

- The tangle is visible and graded. One line frays into 6–10 strands over 30–40 mm and regathers (T02, T04, T05, T10, T03). It is never a hairball. Tangle 1 beat 0.6 in all three pairs, so the default is now 1.
- Compared with the round-1 version Ian liked, it is better on tangle and slightly worse on painterly/dynamic, because the middle of most cells is a plain single contour. It is clearly better than meander-2 round 1.
- Defaults generalise to about 5 of 9 cells, including the fresh seeds 40 and 5.
- **Still failing:**
  - the smooth line between events is one handwriting;
  - nested even arcs in T08 and T09;
  - a few closed beans;
  - forms turning fleshy and figurative (bag, head in profile, mushroom).
- **Reviewer's next move:** let one tangle per drawing run 60–100 mm along a gentle stretch and thin out into the void, so it becomes a field.
- **Shortlist,** with page settings. All are the Meander render, reversed order, Auto camps, and "from the territory".

| Cell | Seed | Notes |
|---|---|---|
| T02 | 21 | defaults (tangle 1) |
| T04 | 13 | defaults (tangle 1) |
| T05 | 5 | defaults, a fresh seed |
| T10 | 34 | defaults |
| T03 | 40 | defaults, a fresh seed |
| T08 | 3 | defaults (shows nested arcs, as a counter-example) |

## Checks

- `smoke_meander.js`: deterministic. About 200–300 ms per sheet once warm. **24 sheets take 5.2 s in node, just over the 5 s budget** (it was 4.4 s before this round).
- Playwright on the built page: no console errors, and the Meander group shows and hides with the render mode.
