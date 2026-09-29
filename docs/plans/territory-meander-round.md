# Next round: meander (multi-agent plan)

Status: planned 2026-09-29 and not started. Start it in a fresh session.

## Why

v5 "searching lines" got partway. Ian's verdict, verbatim:

> seed 3, seed 13 are going somewhere. seed 21 also has something. perhaps we're holding onto the territory thing too closely. also, i was expecting to see the illusion of line width and narrowness through the lines, to create the illusion of volume etc. also kinda more unified stuff idk.

He then shared a meandering river, the Rio Mamoré: `~/Downloads/meandering-amazon-river-nasa-700x467.jpg`. Its oxbow lakes, point bars and scroll bars read as one process that produces:

- **Line width made of lines.** A channel is two banks that pinch and swell.
- **History as traces.** Scroll bars are the channel's earlier positions, packed where a bend migrated.
- **Open shapes and events.** Oxbows are stranded loops, cut off when two bends touch.
- **A unified sheet with uneven weight.** Active bends are dense and the floodplain stays empty.

This replaces the territory scaffold as the core. Territories become at most one possible source of starting centrelines.

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

## Roles (Ian's rulings for this track)

- **Opus:** brainstorms with sharp edges.
- **Sonnet:** research, mechanical work, and the blind aesthetic review (drawing-review procedure; Sonnet replaces Sol on this track).
- **Fable:** system-design synthesis and advice during the build.
- **Lead:** owns direction, acceptance and relaying to Ian. Decisions that are Ian's go through the questions UI.

**Risk statement (read before starting).** The main risk is a generic river render or a Robert Hodgin *Meander*-style map. The second is scroll bars becoming tree rings, meaning evenly spaced concentric arcs. Abstraction must be designed in from step 1, not patched afterwards.

## Steps

0. **Orient.** Read this plan, `tools/territory-prototype/README.md`, the v5 README and round 4 of `docs/reviews/territory-v2-0929-sonnet.md`. Rebuild the prototype and re-render seeds 3, 13 and 21 from the v5 defaults (render `v5`, order `reversed`, reach 15, 3 camps) so everyone can see them.
1. **Brainstorm: 3 Opus agents in parallel.** Each is read-only and writes a report to `docs/research/meander/brainstorm-N.md`. The shared pack: Ian's words, the river image, his sketch (`~/Desktop/Screenshot 2026-09-29 at 3.12.10 AM.png`), seeds 3, 13 and 21, and the memory and brief above. Each returns 5–7 mechanism-level ideas, with the decision each makes, its cliché, and a kill criterion. Lenses:
   1. **Meander as drawing process.** Migration, cutoffs and reversals chosen as drawing decisions. Several channels that cross, interrupt, capture and abandon one another. Starting centrelines from v5 seeds, from cores, or from nothing.
   2. **Width from lines.** Paired banks that disagree. Converging and diverging strands that give swelling and tapering. How volume reads through the width of a line alone, with one pen. How history traces modulate weight.
   3. **Unity and abstraction.** How one process covers the sheet without becoming a map: scale jumps, a floodplain as shaped emptiness, registers from one mechanism, what makes you ask what's going on.
2. **Research: 2 Sonnet agents in parallel.** Reports go to `docs/research/meander/research-*.md`.
   1. Techniques, with browser-JS feasibility and cost:
      - curvature-driven migration (Howard & Knutson 1984; Ikeda-Parker-Sawai; Kinoshita curve)
      - cutoff detection
      - scroll-bar and point-bar generation from migration history
      - resampling and stability
      - variable-width stroke from a line family
   2. Artistic procedures (not looks) for width and volume made from line bundles, and for landscape abstraction that is not a map. Each yields a transferable rule and a warning.
3. **Synthesis: Fable.** Writes `docs/research/meander/synthesis-brief.md`:
   - 2–3 mechanisms
   - a data model on the prototype's utilities (hand, occupancy with lineage, isolines, chamfer)
   - a weight and width model
   - an event budget (oxbows, captures)
   - a kill table
   - a blind test matrix including seeds 3, 13 and 21
   - a not-this-round list
4. **Build (lead).** A new render mode, `meander`, in `tools/territory-prototype/` (a new `t_meander.js`) and in the Territory artifact, same URL, new version. Territory composition is optional input. Checks: node smoke tests for determinism and speed (24 thumbnails in 5 s or less), plus Playwright with no console errors.
5. **Review loop (at most 2 rounds before Ian).** Contact sheets with neutral labels, close views and withheld recipes. Sonnet appends "Meander round N" to a new `docs/reviews/meander-sonnet.md`. Fable checks the system if something misbehaves.
6. **Evidence.** `shots/meander-<date>/` with a README, recipes and sheets. Commit on `feat/territory-bench` at verified checkpoints. Ian judges; report it as "ready for you to check", on screen only, with no plot.

## Not in scope

- Any `axibridge/` change or port.
- Plotting.
- Colour or multi-pen.
- Reviving v4 bodies.

The bench port (over the `second_reading` event model) is a later decision, once Ian accepts a direction.
