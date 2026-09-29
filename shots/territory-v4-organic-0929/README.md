# Territory v4: organic bodies (29 September 2026)

Ian's verdict on v3, verbatim: "meh — way more organic results. use thinner lines too and make them smoother and have more character … think outside the box a bit and push the smartness of it."

Artifact: https://claude.ai/artifact/Bawx12VN4uRgWR2wU2Lso3, version 3, "Organic bodies" (private).

## Mechanism

Fable advised on the system design. The composition engine (camps, borders, voids, arrival order) is unchanged. A body stage follows it:

- **Forms.** Either territories, inflated by a Poisson solve (∇²p = −1, SOR; `h = puff·√(4p)`, tanh-capped), or cores swept into tubes (a Gaussian-smoothed skeleton, elliptical end caps, a radius spread of about 5×).
- **Depth.** Ownership goes to the higher body: z = h − 1.5·rank. A fat rear body can crest over a thin front tube, and silhouettes are drawn once.
- **Renderers.**
  - *Wrap*: isolines of `u·x + k·h`, where u is the principal axis and k keeps the bands from folding. Tone comes from golden-hash thinning with hysteresis.
  - *Wound*: rings of a darkness-weighted distance from a lit interior seed. Closed rings are spliced into a spiral; open rings turn back like a thread.
  - *Growth*: an open strand where only the young tip grows, stopping at a fill target that varies from a single arc to fuller.
- **Auto** (after Sonnet round 3): the largest body winds, other tubes mix wrap and growth, touching bodies differ, and one very connected body stays bare.
- **The hand.** Catmull-Rom through sparse control points, curvature-gated sway in two octaves, a quadratic overshoot curl, one pen lift with overlap on long lines, and two contrasting hands per sheet. Pen width is 0.2 mm.
- **Ink budget.** 14 m, spent front to back at 45% of what remains per form.

## Sheets

These are Sonnet round 3, blind. The review is in `docs/reviews/territory-v2-0929-sonnet.md`, "Round 3 — organic". F, G and J are territories (wrap, wound, growth); X, Y and Z are tubes (the same three). Sonnet's finding: tubes always beat territories, and the renderer decides which cliché appears (wound gives fingerprints, growth gives coral, wrap gives ribbing).

`sheet-AA.png` shows tubes on Auto after the round-3 fixes. It has not been reviewed.

## Honest note

The bodies now read organically, but they sit close to Ian's stated fear: a "competent producer of ambiguous little organisms". The body pass is global, so adding a core changes earlier bodies; only the composition layer keeps the prefix property. Everything here was judged on screen; nothing has been plotted.
