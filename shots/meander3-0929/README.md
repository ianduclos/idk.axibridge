# Meander 3 (29 September 2026)

Round 3 of meander, after Ian's notes on Version 6. They are verbatim in `docs/plans/territory-meander-round-3.md`. In short:
- lines more deliberate for the most part, with a bit of chaos kept;
- chaos paired with one or two stylised elements;
- curves that integrate crossings "in another liminal plane";
- more complex compositions;
- simpler parameters, with randomize and locks;
- cores hidden.

The design is in `docs/research/meander3/`: the Opus brainstorm, the Fable synthesis brief, and Fable's advice after review 1. The reviews are "Meander 3, round 1/2" in `docs/reviews/meander-sonnet.md`. Everything was judged on screen only; nothing was plotted.

## Page (Version 7)

The page is meander only. It has seven dials plus the seed: complexity, drift, band, chaos, accents, bridges, history. Randomize changes every unlocked dial within a curated range, and each dial has a lock. Copy settings gives a one-line recipe, and pasting it back restores it. A twelve-seed contact sheet replaces the experiments. Cores are hidden by default. The seed picks the cores through the same population sheet (E1) as before, so at the default dials seeds 22 and 10 draw exactly as in Version 6 until the round-3 features act.

## What changed in the engine

| # | Change | What it does |
|---|---|---|
| 1 | Chaos field χ | One centre (two above chaos 0.6), placed on the knot or the rivers' crossing. Outside it: calm hand, lightly pre-smoothed centrelines, steadier band edges, and bands capped per channel at a single line, 3 strands or 5. Wobble outside χ is about half of Version 6. |
| 2 | One knot | The knot is 25–55 mm long, at least 25 mm from either end (slid inward if needed), with at most 4 revived strands. It is on 18 of 24 sheets. |
| 3 | Accents | 3–4 leaning stated arcs outside a sharp bend near the chaos, at most 2 per sheet. Gaps are uneven, from {0.6, 0.9, 1.5} mm. |
| 4 | Bridges | A fillet in the corner of a crossing, or a continuation from a line end that bends and lands along another line (35 mm or less). Occasionally one echo lands elsewhere. There is 1 at the default dial, more toward bridges 1, and never near the chaos. They are drawn over the bands and under the history. |
| 5 | Second river | Gated by complexity (about 5 of 24 sheets at 0.5, most at 0.9). It crosses the first river once, in the middle 60 % of the sheet, and 2 sprouts start at the crossing. |
| 6 | Other | Stricter bean test. Fewer search passes. Fewer, varied hooks. A banded minor has to meet the trunk. |

## Where it landed

- **Round 1** (`round1/`): "the busier version loses every time". Frays, arcs and bridges each became stamps. The Fable fixes F1–F8 subtracted instances.
- **Round 2** (`round2/`, same cells): better overall, but too tidy. Chaos survived in 4 of 18 cells, and the band crescents became the new stamp.
- **Post-review** (`post-r2-check.png`, not reviewed): knots slide inward instead of being dropped, and each channel's band is a single line, 3 or 5 strands. Checked by the lead only.
- **Reviewers' favourites:** R02 (seed 5), R03 (seed 22, accents 0 and bridges 0), R13 (seed 7), R10 (seed 13, chaos 0.8), R17 (seed 31). Versus Version 6 on seed 22: R03 ties it, and R15 (defaults) is close.
- **Still open:**
  - closed ovals and beans on some seeds (40, 13, 10's pear, which Ian liked);
  - bridges are the least certain register, and reviewers identify them only loosely;
  - the long sweep (Ian's longest blue curve) is deferred.

## Checks

- Recipes without the round-3 dials are byte-identical to Version 6 on seeds 1–24.
- `smoke_meander.js --r3 1…24` is deterministic on all 24 sheets.
- 24 sheets take about 4.9 s at the default dials; there was an exact early-out speed-up first.
- Two sheets flag K: short, compact knots that the anti-hairball metric reads as low-aspect.
