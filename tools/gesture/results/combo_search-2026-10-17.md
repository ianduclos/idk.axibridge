# combo_search — searching the kit's combination space — 2026-10-17

Round 10, the risky exploration. Code: `tools/gesture/experiments/combo_search.py`
(run: `.local/gesture/.venv/bin/python tools/gesture/experiments/combo_search.py all`,
~5.5 min with 2 workers); tests: `tools/gesture/tests/test_combo_search.py`.
Every candidate is `kit.run` + `kit.preview`: `<id>.jpg` and `<id>.recipe.json`
are in `.local/gesture/out/combo_search/`. Give an id (e.g. `g2-19`) to rebuild it.
No kit-core file was edited.

## What I built

1. **Sampler** (`sample_recipe`): recipe families around kit demo 4. Each one has a
   HEAVY voice and a WIRE voice, and sometimes a third.
   - HEAVY: a drift with 2–3 hands, a single hand, or a dance trail. Its weight
     comes from a noise/radial/bands field, a timing tempo, event-pulse prosody,
     or own_tempo. It is inked with nib a/b+/c/e/c+e, and rarely with restate or coil.
     About 15 % add an occasional handover.
   - WIRE: a dry hand from a machine-ish pool, a `machine` voice, or a dance trail
     (pen 0.2–0.35).
   - THIRD (60 %): either the heavy line's own measurement (`annotate`: kappa,
     route, phase, atlas or ledger, laid out as shadow, right or below, sometimes
     drawn by matisse or hokusai) or a dance wire.
   - Arranger: single, or poly_scatter 15 % of the time.
   - Heavy and wire never share a hand. All params are bounded and every recipe
     passes `kit.validate`.
2. **Selector** (`features`/`terms`/`score`). These are proxies, not taste:
   - `sep`: can a nearest-centroid classifier tell which voice a 12 mm patch
     came from? It uses six texture features per patch (density, stroke
     half-width, ink per skeleton px, free ends, junctions, orientation
     coherence), computed on each voice's own mask, two folds, balanced
     accuracy, and takes the minimum over voice pairs.
   - `contrast`: log ratio of ink per line length between the heaviest and the lightest voice.
   - `crossing`: share of inked cells where two or more voices meet.
   - `presence`: how much line the quietest voice has, relative to the loudest.
   - `wholeness`: share of each voice's line that lies in islands ≥ 27 mm.
   - `capsule`: solid, nearly convex, elongated closed mass rings (aspect ≥ 2.2,
     solidity ≥ 0.75, inside more than half inked). These are the sausages.
   - `hatch`: 12 mm windows with ≥ 4 separate parallel strokes, after a 0.5 mm
     dilation so that nib lanes merge.
   - `confetti`: share of the line in islands under 3 mm.
   - `cover`: ink share outside 2.5–14 %.
   - The weights were fixed a priori (`WEIGHTS`).
3. **Sheets**: population, top 12, bottom 12, gen-2 population, and gen 1 vs gen 2.
   Each thumbnail shows its id, score and rank (or lineage) and a one-line recipe.
4. **Breeding**: the top 8 of gen 1 produced 24 children. Even ids are crossovers
   (A's heavy voice, B's wire, maybe a third). Odd ids are 1–2 mutations: swap a
   hand, swap the weight source, swap the renderer, change the route, swap the
   wire, add/drop the third, or reseed.

## Does the proxy agree with Ian? (calibration on 32 round-9 recipes)

Each round-9 recipe was re-run and labelled from Ian's notes: +1 kept (15),
−1 passed over (12), 0 neutral (5). The full table is in
`.local/gesture/out/combo_search/calibration.md` (`calibration-v1.md` is the first pass).

- **AUC kept vs rejected: 0.87.** This flatters the selector. Most of the
  rejected recipes are single-voice prosody variants, which the capsule term
  catches and the polyphony terms never reward.
- **Among multi-voice recipes only: 0.61** (9 kept vs 2 rejected). The two
  siblings sheets (M1 and M2, both "meh") score as high as the converse sheets
  Ian liked. The selector cannot see "systematic structure as the main event".
- **Kit demo 4 ranks 1st of 32** in the calibration set. In the gen-1 run it
  ranks 12th of 41, so the sampler finds 11 candidates the proxy likes more.
- Per-term AUC: sep 0.76, contrast 0.72, cover 0.74, presence 0.74, capsule
  0.70, crossing 0.66. Three terms are uninformative or inverted: wholeness
  0.34, confetti 0.43, hatch 0.47. Hatch never fires on the labelled set, so it
  is untested.
- **Honest note: three terms were redefined after the first calibration pass**
  (v1 AUC 0.89, multi-voice 0.72).
  - Capsule: v1 flagged demo 4's winding nib ribbons and d7 as sausages; the
    solidity and fill tests were added.
  - Wholeness: v1 used "largest island share", which punished the converse
    sheets Ian kept.
  - Confetti: v1 counted islands, which punished chart labels.
  - The weights were not changed. With n = 32 these numbers are optimistic.

## Numbers

| | n | failures | score median | top-8 mean | distinct heavy lines | weight source (field/timing/prosody) |
|---|---|---|---|---|---|---|
| gen 1 | 40 + demo-4 anchor | 0 | +1.72 | +2.04 | 40 | 14 / 13 / 13 |
| gen 2 | 24 | 0 | +1.95 | +2.14 | **12** | **19** / 1 / 4 |

- Gen-1 runtime: median 1.8 s per candidate, max 42 s. The slow ones combine
  `annotate` (atlas or ledger) with nasta'liq chain.
- In gen 1, score correlates with crossing (r 0.66), contrast (0.58) and
  capsule (−0.44).
- Gen-1 candidates with a measurement layer score a median of +1.68, against
  +1.77 for those without. The proxy mildly punishes the accompaniment Ian loves.
- poly_scatter candidates have a median of +1.30, so the selector dislikes them.

## Images

- `results/combo_search-gen1-population-2026-10-17.jpg`: all 41, in id order.
- `results/combo_search-gen1-top-2026-10-17.jpg` and `-gen1-bottom-…jpg`: the selector's picks.
- `results/combo_search-gen2-population-2026-10-17.jpg`: 24 children with their lineage.
- `results/combo_search-gen1-vs-gen2-2026-10-17.jpg`: the top 6 of each generation.

Worth Ian's eyes:

1. **g2-19** (gen 2, a mutation of g1-25 that added a third voice): a
   dance_staccato > matisse drift whose noise field gives black worm-masses. A
   prairie-dog wire runs through it. Below sits a **phase portrait of the same
   line**, drawn as a nest of ellipses on crossed axes. It has three grammars:
   gesture, foreign wire, and self-measurement. Caveat: the worms are elongated,
   so they may read as "sausagy", and the proxy does not flag them because they
   wind (low solidity).
2. **g1-32**: a thrusting-dance trail with pulse prosody, giving round beads
   (not capsules). A Koch-rule wire re-speaks the roadrunner hand. A
   four-row κ seismograph runs below. It is drawing, machine, and measurement on
   one sheet. Gen 2 (g2-03, g2-08, g2-14) bred variants of it.
3. **g2-04** (the top score, +2.30, a crossover of g1-20 and g1-32): a marden >
   mantis drift (nib c+e, field) crossed by the same Koch roadrunner wire. It is
   the closest relative of demo 4: one wide calligraphic gesture and one dry,
   jagged, fractal voice that never merge.

Also see g1-27 (rank 1: nasta'liq ribbons × polygon_walk) and g1-10 (nasta'liq
chain × aaron, which looks most like demo 4). The bottom sheet holds g1-17
(dance + atlas) and g1-22 (prosody beads + charts). These are measurement
accompaniments that the proxy ranks low, and I suspect Ian would rank them higher.

## Surprises

- **Crossover keeps the heavy line and swaps its partner.** The heavy voice
  keeps its seed, so a crossover produces *the same drawing with a different
  second voice*: g2-00, g2-04 and g2-12 are one marden > mantis gesture with
  aaron, Koch, and aaron again. That is a usable instrument in itself, a
  "re-accompany" control.
- The measurement layer combines well with a foreign wire. The strongest three-way
  sheets (g1-32, g2-19) came from adding a third voice, a combination no
  round-9 thread tried.
- The machine voice (Koch, compass, codebook) works as the dry wire much better
  than as a main event. That matches Ian's "systematic only as accessory".

## Failures

- **The risk partly failed: the population collapsed.** Gen 2 has 12 distinct
  heavy lines out of 24, and 19 of 24 use the noise field. The proxy prefers
  heavy versus thin, so breeding drove out timing, prosody and own_tempo, and
  with them the round beads Ian liked. Two gen-2 recipes are near-duplicates
  (g2-00 / g2-12; g2-21 is g1-10 again after an add-then-drop of the third). The
  score rose (median +1.72 → +1.95), but that is the selector agreeing with
  itself, not evidence of taste.
- The proxy cannot see systematic-as-main-event (siblings) or sausages that
  wind (g2-19). It mildly punishes measurement accompaniment and scatter, which
  Ian rated well or with interest.
- Hatching never occurred in sampled or labelled sheets, so that term is untested.

## Next

1. Rank Ian's picks from the population sheet, then refit the weights on
   round-9 and round-10 labels together (about 100 labels).
2. Breed with novelty pressure: penalise distance to the nearest sibling in
   feature space, and require one candidate from each weight-source family.
3. A "re-accompany" mode: fix the heavy part and seed, then sweep the wire and
   the third voice.
4. Add a proxy for systematic structure (straight-run share, regular spacing)
   and a proxy for winding sausages (constant-width solid runs along the marks'
   `r` channel).

## Proposed kit-core changes (not made)

1. `kit.mutate(recipe, rng, ops=…)` / `kit.crossover(a, b)` in core. They would
   respect param bounds from the registry, so that breeding does not
   hard-code pools.
2. A per-part seed override (`part.seed`). Crossover could then keep or
   re-roll a voice's line explicitly, and "same drawing, new partner" would be a
   first-class operation.
3. `kit.render_masks(sheet)`, one mask per part, so that selectors and
   statistics do not re-implement the rasteriser.
4. A `kit.preview(..., thumb=…)` option to write a small unlabelled
   thumbnail beside the image.

## Tests

- `tests/test_combo_search.py`: 7 passed in 2.5 s. They cover sampler validity
  and determinism, distinct grammars, breeding purity, the capsule proxy (solid
  vs open vs bead), the hatching proxy, separability, score bounds, and a small
  end-to-end feature run.
- The whole research suite (`tools/gesture/tests`): **553 passed** in 87 s, no
  failures.

## Index (rank within generation; recipe beside each `<id>.jpg`)

| id | rank | score | recipe |
|---|---|---|---|
| g1-27 | 1 | +2.13 | nastaliq{f:noise} nib:c+e  x  polygon_walk[ch] wire |
| g1-14 | 2 | +2.09 | meander69[ch]{f:noise} nib:c  x  aaron wire |
| g1-25 | 3 | +2.06 | dance_staccato>matisse{f:noise} nib:a  x  mime_prairiedog[ch] wire |
| g1-35 | 4 | +2.04 | dance_staccato[ch]{f:bands} nib:c  x  meander69 wire |
| g1-10 | 5 | +2.04 | nastaliq[ch]{f:noise} nib:e  x  aaron wire |
| g1-20 | 6 | +2.02 | marden>mime_mantis{f:noise} nib:c+e  x  dance:staccato/rhand wire |
| g1-32 | 7 | +2.01 | dance:thrusting/hands{prosody,+kappa/below} nib:c  x  koch(mime_roadrunner) wire |
| g1-28 | 8 | +1.96 | dance:penguin/all{prosody,+route/shadow} nib:c  x  dance:particles/all wire |
| g1-05 | 9 | +1.95 | mime_mantis>dance_fluidity~[ch]{t:fluidity} nib:c+e  x  mime_monkey_hands[ch] wire |
| g1-08 | 10 | +1.95 | dance:particles/all{f:noise,+atlas/shadow} nib:c+e  x  compass(marden) wire |
| g1-37 | 11 | +1.91 | shikasta{f:bands} restate  x  dance:dragon/hands wire |
| g1-ref4 | 12 | +1.90 | hokusai>nastaliq~{f:noise} nib:c  x  bubble[ch] wire |
| g1-36 | 13 | +1.87 | shikasta>dance_fluidity~[ch]{handover,t:cmu_49_10} nib:c+e  x  koch(nastaliq) wire |
| g1-18 | 14 | +1.85 | hokusai>dance_levitation>nastaliq{handover,prosody} nib:e  x  dance:outofbalance/all wire |
| g1-34 | 15 | +1.85 | mime_mantis>dance_levitation~[ch]{f:noise} nib:c+e  x  codebook(marden) wire  x  dance:hummingbird/hands wire |
| g1-07 | 16 | +1.81 | shikasta{prosody,+kappa/below} nib:c+e  x  aaron[ch] wire |
| g1-19 | 17 | +1.81 | nastaliq{t:staccato} nib:c  x  lichtenberg[ch] wire |
| g1-15 | 18 | +1.79 | nastaliq>meander69~{f:noise,+atlas/below} nib:c  x  dance:dragon/hands wire |
| g1-39 | 19 | +1.78 | dance:hummingbird/lhand{f:noise,+phase/shadow} nib:e  x  stair(dance_thrusting) wire |
| g1-31 | 20 | +1.74 | meander69[ch]{handover,t:levitation} nib:c+e  x  dance_thrusting[ch] wire  x  dance:dragon/hands wire |
| g1-16 | 21 | +1.73 | nastaliq[ch]{handover,t:levitation} nib:e  x  mime_penguin wire  x  dance:staccato/hands wire |
| g1-12 | 22 | +1.71 | marden>mime_dragon~{f:noise} nib:e  x  mime_prairiedog[ch] wire  x  dance:outofbalance/hands wire |
| g1-13 | 23 | +1.71 | dance_staccato>mime_dragon~[ch]{handover,prosody} nib:e  x  dance_particles[ch] wire |
| g1-01 | 24 | +1.68 | matisse>dance_levitation{prosody,+ledger/below} nib:e  x  aaron[ch] wire |
| g1-24 | 25 | +1.68 | dance:dragon/lhand{t:levitation,+kappa/shadow} nib:e  x  compass(lichtenberg) wire |
| g1-02 | 26 | +1.65 | hokusai>ingres~[ch]{handover,t:staccato} nib:a  x  compass(dance_levitation) wire |
| g1-38 | 27 | +1.65 | dance_fluidity>hokusai~{f:noise} nib:e  x  dance_thrusting[ch] wire  x  dance:particles/hands wire |
| g1-23 | 28 | +1.64 | shikasta>nastaliq~{t:particles} nib:e  x  dance:levitation/head wire  x  dance:mantis/hands wire |
| g1-00 | 29 | +1.56 | [poly_scatter] dance_fluidity>mime_roadrunner~{t:staccato,+atlas/right} nib:c  x  meander69 wire |
| g1-30 | 30 | +1.56 | mime_roadrunner>dance_levitation~{prosody} nib:b+  x  bubble[ch] wire  x  dance:dragon/hands wire |
| g1-04 | 31 | +1.49 | nastaliq>dance_staccato>meander69~[ch]{handover,prosody} nib:c  x  dance:penguin/rhand wire  x  dance:levitation/hands wire |
| g1-33 | 32 | +1.49 | [poly_scatter] mime_dragon>dance_staccato~{f:noise,+ledger/shadow} nib:a  x  compass(ingres) wire |
| g1-06 | 33 | +1.44 | dance:particles/all{prosody,+atlas/shadow} nib:b+  x  meander69 wire |
| g1-11 | 34 | +1.42 | ingres>meander69>mime_dragon~[ch]{t:staccato,+phase/right} nib:a  x  dance:penguin/head wire |
| g1-26 | 35 | +1.36 | [poly_scatter] shikasta>ingres~[ch]{t:staccato} restate  x  ruler(dance_levitation) wire |
| g1-29 | 36 | +1.33 | mime_roadrunner{t:staccato,+kappa/shadow} nib:a  x  dance:hummingbird/hands wire |
| g1-09 | 37 | +1.24 | [poly_scatter] mime_roadrunner[ch]{prosody} nib:e  x  marden[ch] wire |
| g1-21 | 38 | +1.21 | [poly_scatter] hokusai{prosody} restate  x  stair(mime_mantis) wire |
| g1-22 | 39 | +1.15 | [poly_scatter] dance_staccato>nastaliq>dance_fluidity[ch]{prosody,+route/right} nib:c  x  mime_roadrunner wire |
| g1-03 | 40 | +1.11 | mime_roadrunner>dance_levitation>matisse~{prosody} nib:a  x  compass(polygon_walk) wire |
| g1-17 | 41 | +1.00 | dance:penguin/hands{t:cmu_55_mantis,+atlas/right} nib:b+  x  ruler(dance_levitation) wire |
| g2-04 | 1 | +2.30 | marden>mime_mantis{f:noise} nib:c+e  x  koch(mime_roadrunner) wire — g1-20 x g1-32 |
| g2-10 | 2 | +2.18 | meander69[ch]{f:noise} nib:c  x  dance:particles/all wire — g1-14 x g1-28 |
| g2-16 | 3 | +2.18 | meander69[ch]{f:noise} nib:c  x  dance:particles/all wire — g1-14 x g1-28 |
| g2-06 | 4 | +2.15 | nastaliq{f:noise} nib:c+e  x  mime_prairiedog[ch] wire — g1-27 x g1-25 |
| g2-22 | 5 | +2.15 | nastaliq{f:noise} nib:c+e  x  koch(mime_roadrunner) wire — g1-27 x g1-32 |
| g2-13 | 6 | +2.08 | nastaliq{f:noise} nib:c+e  x  dance:mantis/hands wire — g1-27 ~ wire |
| g2-02 | 7 | +2.05 | nastaliq[ch]{f:noise} nib:e  x  aaron wire — g1-10 x g1-14 |
| g2-05 | 8 | +2.04 | nastaliq{f:noise,+kappa/below} nib:c+e  x  codebook(meander69) wire — g1-27 ~ third+wire |
| g2-21 | 9 | +2.04 | nastaliq[ch]{f:noise} nib:e  x  aaron wire — g1-10 ~ third+third |
| g2-00 | 10 | +2.02 | marden>mime_mantis{f:noise} nib:c+e  x  aaron wire — g1-20 x g1-10 |
| g2-03 | 11 | +1.99 | dance:thrusting/hands{t:particles,+kappa/below} nib:c  x  koch(mime_roadrunner) wire — g1-32 ~ weight |
| g2-14 | 12 | +1.96 | dance:thrusting/hands{prosody,+kappa/below} nib:c  x  meander69 wire — g1-32 x g1-35 |
| g2-17 | 13 | +1.94 | dance_staccato>matisse{f:bands} nib:a  x  mime_prairiedog[ch] wire — g1-25 ~ weight |
| g2-12 | 14 | +1.93 | marden>mime_mantis{f:noise} nib:c+e  x  aaron wire — g1-20 x g1-14 |
| g2-07 | 15 | +1.92 | marden>matisse{f:noise} nib:c+e  x  dance:staccato/rhand wire — g1-20 ~ hand |
| g2-01 | 16 | +1.90 | dance:outofbalance/all{prosody,+route/shadow} nib:c  x  koch(ingres) wire — g1-28 ~ hand+wire |
| g2-18 | 17 | +1.89 | dance:penguin/all{prosody,+route/shadow} nib:c  x  polygon_walk[ch] wire — g1-28 x g1-27 |
| g2-20 | 18 | +1.85 | dance_staccato>matisse{f:noise} nib:a  x  aaron wire — g1-25 x g1-14 |
| g2-11 | 19 | +1.73 | dance:thrusting/hands{f:noise,+kappa/below} nib:c  x  ruler(dance_particles) wire — g1-32 ~ weight+wire |
| g2-19 | 20 | +1.68 | dance_staccato>matisse{f:noise,+phase/below} nib:a  x  mime_prairiedog[ch] wire — g1-25 ~ seed+third |
| g2-09 | 21 | +1.66 | nastaliq[ch]{f:noise} nib:c+e  x  koch(mime_roadrunner) wire — g1-27 ~ wire+route |
| g2-08 | 22 | +1.66 | dance:thrusting/hands{prosody,+kappa/below} nib:c  x  aaron wire — g1-32 x g1-14 |
| g2-23 | 23 | +1.52 | mime_roadrunner[ch]{f:noise} nib:a  x  aaron wire — g1-14 ~ renderer+hand |
| g2-15 | 24 | +1.45 | nastaliq[ch]{f:noise} nib:c  x  polygon_walk[ch] wire — g1-27 ~ renderer+route |
