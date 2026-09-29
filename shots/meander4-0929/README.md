# Meander 4: Density (29 September 2026)

Ian's notes on Version 7 are verbatim in `docs/plans/territory-meander-round-4.md`. He asked to make it "busier, more painterly", with the "shapes continued, fields covered, surprises arising", and he wants to be able to get close to the two references (`ref-*`). Ink should stay under 100 m and be controllable. The design is in `docs/research/meander4/`: the Opus brainstorm and the Fable brief. The reviews are "Meander 4 (Density), round 1/2" in `docs/reviews/meander-sonnet.md`. Everything was judged on screen only; nothing was plotted.

## The seed-22 rescue (before Density)

Ian said "i stopped seeing these sexy shapes". The causes were found by toggling features (`../meander3-0929/seed22-rescue.png`):
- accents wrapped the drip's cusp;
- the band cap thinned junction bands;
- the calm hand cut overshoot curls;
- pre-smoothing ironed the cusp out.

Within 12 mm of another channel, all of these are now off. Seed 22's drip, ring crescents and restated neck are back.

## Page (Version 8)

A Density group sits under the seven dials:

| # | Dial | What it does |
|---|---|---|
| 1 | Density | 0 is the calm drawing, byte-identical |
| 2 | Continue | band ends run on; ribbons from old river courses cross the sheet |
| 3 | Cover | the ground is laid in planes, and voids are carved out of it |
| 4 | Slash | chords, shard wedges, and rarely an X |
| 5 | Surprise | a thorn star or a black cross-scrubbed void |
| 6 | Ink limit | 5–100 m, default 40 |

The stats line shows ink and strokes, since stroke count means pen lifts and so plot time.

## Engine (`t_density.js`)

Density runs after the base drawing and never changes it. The base is reserved with a jittered white halo. A quiet zone around each knot grows with Density.

Layers are stacked through a z-mask, from top to bottom: chords, base, surprise, ribbons, fans, ground.

The ground is 1–3-pass drags (median 50 mm) that overlap for tone. They are laid in Voronoi planes 25–50 mm across, each with its own direction and weight. Drags start and end on the plane's edges, so the edges are hard. Candidates are fixed per cell, so raising the dial only adds strokes.

## Where it landed

- **Round 1:** the ground read as combed hair and stitched dashes. The voids were leftovers. The knots were buried at Density 1. The best cells were at Density 0.7.
- **Round 2 (same cells):** better. It read as dry-brush swathes from a distance and hair up close. Edges were ragged, and fans and dotted arcs looked stamped. The top was D10 (seed 13 at 0.7), then D09 (seed 10 at 0.7), D05, D01 and D04.
- **After round 2** (lead only; `post-r2-check.png`, `post-r2-close.png`):
  - every drag starts and ends on its plane's edge, giving hard plane edges;
  - fans appear only at Cover above 0.75;
  - no ring surprise;
  - shorter slashes.
- **Still open:**
  - the top end (Density 1) tends to bury the drawing, and 0.6–0.8 is the sweet spot;
  - reserved ribbons can read as pipes.

## Checks

- Density 0 is byte-identical to the rescued base on seeds 1–24.
- Deterministic.
- 0.35–0.6 s per sheet at Density 1 in node. On the page, a sheet plus 12 thumbnails at 0.7 takes about 11 s.
- At 40 m: about 400–800 strokes. At 100 m: about 900.
- No page errors (headless).
