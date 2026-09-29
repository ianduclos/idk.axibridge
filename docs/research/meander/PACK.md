# Meander round — shared agent pack (29 September 2026)

Read-only context for every agent in this round. The plan is
`docs/plans/territory-meander-round.md`; the section below is copied verbatim
from it and is binding.

## Ian's aesthetic direction (verbatim, 29 September; carry it into every agent pack)

- "i dont wanna do an imitation" (of AARON). Earlier: potent abstraction, where near-associations need not be nameable. Figuration slight at most.
- On v3: "meh i was thinking of way more organic results. use thinner lines too and make them shmoother and have more character. we have to think outside the box a bit and push the smartness of it"
- On v4: "bit too concrete. i was thinking open shapes based on the compositions we had before … i want it more unpredictable and more dense"
- On the references: "a bit more rigid than what i want but maybe it can do something". From them: a net on one lobe, and apertures.
- "bit of either [one mass or all-over], weird compositions, negative space, different registers mixing into each other"
- "stranger yet coherent forms. more weight at parts and less at others. nuanced tangle that becomes textural at places, organic line based at others. painterly. dynamic. make you ask whats really going on"
- One pen. Weight comes from density, restatement, tangle and overdraw only.
- On v5: "seed 3, seed 13 are going somewhere. seed 21 also has something. perhaps we're holding onto the territory thing too closely. also, i was expecting to see the illusion of line width and narrowness through the lines, to create the illusion of volume etc. also kinda more unified stuff idk."
- What worked, and is worth keeping in spirit:
  - reversed arrival order (it changed the base masses)
  - long open lines *between* things rather than around them
  - restated searching bundles next to thin single lines and open ground
- Rejected along the way:
  - blobs and closed pebble or bean bodies
  - one handwriting everywhere
  - tight ruled parallels and tree rings
  - engraving, weather-chart and topographic looks
  - brain coral, fingerprint and bullseye wound lines
  - short straight hatch dashes
  - scribble-filter restatement of every edge (economy off)

His sketch of the vibe: `~/Desktop/Screenshot 2026-09-29 at 3.12.10 AM.png`. It shows:
- contours restated 2–6 times that drift and don't agree
- lines shared between lobes
- a sling band between bulbs
- inward hooks at line ends
- density piled at the junctions

The references are `~/Desktop/Screenshot 2026-09-29 at 3.15.04 AM.png` and `…3.15.39 AM.png`.

Background: the memory `generator-aesthetic-direction`, `.agents/skills/drawing-review/references/aesthetic-brief.md`, and the evidence README files in `shots/territory-v5-0929/README.md` and `shots/territory-v4-organic-0929/README.md`.


## Images (inspect them with the Read tool; do not rely on descriptions)

- River: `~/Downloads/meandering-amazon-river-nasa-700x467.jpg` (Rio Mamoré: oxbows, point bars, scroll bars).
- Ian's sketch of the vibe: `~/Desktop/Screenshot 2026-09-29 at 3.12.10 AM.png`.
- References (a bit too rigid, but: a net on one lobe, apertures): `~/Desktop/Screenshot 2026-09-29 at 3.15.04 AM.png`, `~/Desktop/Screenshot 2026-09-29 at 3.15.39 AM.png`.
- v5 seeds 3, 13, 21, which Ian said are "going somewhere": `shots/meander-0929/v5-seeds.png`.
- v5 blind-review sheets for context: `shots/territory-v5-0929/sheet-*.png`, README alongside.

## Background

- Memory: `~/.claude/projects/-Users-ianduclos--SecondBrain-02-Areas--Coding-idk-axibridge/memory/generator-aesthetic-direction.md`
- `.agents/skills/drawing-review/references/aesthetic-brief.md`
- `shots/territory-v5-0929/README.md`, `shots/territory-v4-organic-0929/README.md`
- Prototype sources (plain browser JS, also runs in node): `tools/territory-prototype/` — README lists the parts. Useful utilities: `t_head.js` (RNG/noise, `Sheet` occupancy with lineage, `distField`, `walkLine`, `isolines`), `t_hand.js` (Catmull-Rom hand, sway, overshoot, lift).
- The v5 round's reports, for what was tried: `docs/research/territory-v5/`.

## Medium constraints

One pen, one line width, AxiDraw on a 300 × 218 mm sheet. Weight comes only
from density, restatement, tangle and overdraw. Everything is open polylines.
Browser JS, deterministic by seed; a thumbnail must render in ~0.2 s.

## Named risks for this round

A generic river render, or a Robert Hodgin *Meander*-style map. Scroll bars
turning into tree rings (evenly spaced concentric arcs). Abstraction must be
designed in from the start, not patched afterwards.
