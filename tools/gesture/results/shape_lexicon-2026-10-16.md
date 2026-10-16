# Shapes → signs and masses: a learned shape vocabulary — 2026-10-16 (round 8)

Until now, signs and masses came from hand-made operators (`signs.py` line
events, `regime.py` masses). This thread measures closed shapes from the
corpora, builds a shape space, samples new shapes from it, and grows them
out of lines at the same event sites. The question it answers: do signs
grown from the learned vocabulary "seem to communicate something"?

Code:
- `gesture/shape_lexicon.py`: extraction, EFD shape space, `Lexicon` (PCA,
  k-means, kNN, sampler, policy gate), `grow_events`, `grow_sequence`,
  `compose_learned` (wraps `regime_field.compose`, no edits), and the
  language statistics.
- `experiments/shape_lexicon.py`, stages `extract atlas odd vocab sheets
  compose language`.
- `tests/test_shape_lexicon.py`: 7 tests, about 3 s.

Raw outputs: `.local/gesture/out/shape_lexicon/`: `shapes.json`,
`sheets.json`, `odd_stats.json`, `sheets_log.json`, `language.json`.

## 1. What was extracted

There are 139 sheets. One print jp2 is broken (`AL08_p0024`), and the Kelly
leaf gave 0 shapes because its counters are larger than the 4 %-of-sheet cap.

Each sheet gets a background-normalised Otsu mask (as in `regime_study`),
then three kinds of shape:

| # | kind | what it is | rule |
|---|---|---|---|
| 1 | body | an ink mass | component of the ink opened by 0.9 w, deeper than 1.2 w; its **exits** are the thin-ink pieces touching it, kept as points in the shape's own frame |
| 2 | mark | a whole thin component: a tick, a hook, a short stroke, a nuqta-less letter fragment | max depth < 1.2 w, bbox ≤ 30 w |
| 3 | counter | paper enclosed by ink | background component off the border, (2.5 w)² … 4 % of the sheet |

Each kind is capped at 150 per sheet. Frames are cropped 6 % off the artists'
photographs. Cohen's painted sheets use a "colour" ink mode (dark OR
saturated). Print is read at 3600 px.

**20,124 shapes** in total, 13,349 of them in the generative pool:

| # | source | bodies | marks | counters |
|---|---|---|---|---|
| 1 | calligraphy (all 31 sheets measured; 13 generative) | 1996 | 3392 | 817 |
| 2 | Hokusai | 1424 | 3241 | 679 |
| 3 | print (Bulaq books, Euclid 1594, cassettes; measure-only) | 695 | 1841 | 202 |
| 4 | Matisse | 223 | 1083 | 29 |
| 5 | Marden | 278 | 291 | 744 |
| 6 | Cohen | 326 | 482 | 447 |
| 7 | Henry | 157 | 405 | 236 |
| 8 | early computer (Noll, Nake, Molnar) | 137 | 227 | 593 |
| 9 | Ian's reference (atlas only) | 39 | 36 | 104 |

**Shape space.**
- Elliptic Fourier descriptors with 20 harmonics, made counter-clockwise and
  normalised for position, scale, rotation and start point.
- The 180° ambiguity is fixed by a sign rule on harmonic 2.
- Features are harmonics 1–10 (37 numbers), standardised, then PCA 12, then
  k-means with k = 16.
- Test: the descriptors are identical under similarity transforms and
  start-point shifts (to 1e-6).

## 2. Images

1. **`shape_lexicon-vocab.jpg`, the sampler population.** Start here.
   - One row per class: dot, terminal, through, node, mark, loop.
   - Then one row of bodies and one of counters per source.
   - Every glyph is new: a base shape mixed with a kNN neighbour
     (λ ∈ [0.25, 0.75]) plus harmonic noise.
   - The sources read differently even as silhouettes:
     - Hokusai bodies are arched, jointed forms ("legs");
     - calligraphy bodies are bowls and hooks;
     - early-computer counters are triangles and squares, with two
       sickle-arch counters from Noll;
     - Marden and Henry bodies are low, lumpy bars.
2. **`shape_lexicon-detail.jpg`, hand-made | learned at the same events**
   (100 × 100 mm, pen 0.5 mm).
   - The learned shapes are irregular: a three-lobed slug mass, a beaded
     bar, a twisted hook.
   - The hand-made ops are rounder, more symmetric, and larger.
3. **`shape_lexicon-sheets.jpg`**: three structures × five columns (hand-made |
   learned all | Marden | calligraphy | early computer + Cohen).
   - Same lines, same sites, same sizes, same sides; only the operator
     differs.
4. **`shape_lexicon-language.jpg`**, the limb (§4).
   - The **morph** rows are the most interesting thing in this thread.
5. Also:
   - `shape_lexicon-atlas.jpg`: t-SNE, coloured by corpus;
   - `-clusters.jpg`: 16 clusters with members and corpus mix;
   - `-odd.jpg`: between clusters, atypical yet coherent, migrants;
   - `-compose.jpg`: `regime_field.compose`, same seeds, stamps vs learned;
   - `-language-pairs.jpg`.

## 3. Looked at honestly

1. **Does the learned vocabulary communicate more?**
   - At sheet scale, only a little.
     - Both columns read as "the line doing something". The learned shapes
       are lighter (35/37 filled, but smaller footprints) and more
       elongated (marks dominate the corpora).
     - At sheet scale the columns for the different sources are hard to
       tell apart.
   - At detail scale, yes: they look found rather than designed. This is
     the "useful awkwardness" the hand-made operators lack: no two are
     symmetric, and none is an obvious primitive.
   - The strongest learned sign families:
     - Hokusai's jointed arches;
     - calligraphy hooks and bowls (abstracted by the mix; the
       copy-distance gate held);
     - Noll's sickle arch as a counter.
   - Not judged blind. Pairs could be built from `stage_sheets`
     (hand-made vs learned at identical events).
2. **Corpus structure in the atlas.**
   - Elongation dominates the first axis: one big continent of bars and
     strokes, with round masses and polygons on the other side.
   - Early-computer polygon counters form the only tight corpus island.
   - **Migrants**: 412 shapes sit among another corpus's neighbours (≥ 3×
     base rate, ≥ 6 of 15 neighbours).
     - Most migrate *into* the early-computer region (Hokusai → early
       computer 95, calligraphy → early computer 76): the polygon/sickle
       island attracts hand-made shapes that happen to be geometric.
   - **Ian's reference**: its shapes' neighbours are enriched for early
     computer ×2.08, its own shapes ×1.93, Cohen ×1.07; Matisse only ×0.68,
     Hokusai ×0.86. His shape vocabulary sits nearer the computer drawings
     than the brush hands. This surprised me.
3. **Compose.**
   - `compose_learned` swaps only the sign hook. The structure, hands and
     regimes are the same by construction (sign RNG is separate; not diffed). Polylines 308 → 224 (seed 5).
   - The learned shapes fold into the regime masses better than stamps do.
   - At the compose scale a few learned bodies are too large: seed 8, bottom
     centre.

## 4. Limb: shapes as a language

- **Question:** are some shapes neighbours of each other more than chance
  would give (a syntax)?
- **Method:**
  - Pairs: shapes within 2.5 line widths, by bounding box.
  - The mutual information of their cluster labels is compared against
    200 shuffles of the labels *within each sheet*.

| # | corpus | pairs | MI (bits) | shuffle null | z |
|---|---|---|---|---|---|
| 1 | Hokusai | 7918 | 0.024 | 0.013 | **6.5** |
| 2 | print | 2381 | 0.118 | 0.062 | **5.5** |
| 3 | Matisse | 676 | 0.242 | 0.172 | 2.8 |
| 4 | Henry | 1372 | 0.089 | 0.067 | 2.7 |
| 5 | calligraphy | 6408 | 0.029 | 0.022 | 2.4 |
| 6 | reference | 494 | 0.193 | 0.159 | 1.6 |
| 7 | Marden | 3176 | 0.031 | 0.030 | 0.3 |
| 8 | Cohen | 1400 | 0.211 | 0.231 | −0.8 |
| 9 | early computer | 2184 | 0.509 | 0.691 | **−5.1** |

**Reading:**
- There is a weak but real syntax in Hokusai and in print: shapes prefer
  certain neighbours.
- Marden's shapes are syntax-free: any loop sits next to any other.
- The early-computer sheets are *anti*-structured. Within a sheet, shapes
  sit next to *different* clusters more than chance would give: alternation,
  not repetition.
- The excess is small, 0.01–0.07 bits, so the limb holds only as a
  measurement.

**Caveats:**
- Bounding-box adjacency is crude.
- Part of the excess is "bodies next to bodies, counters next to counters".
  The kind-level MI is 0.15–0.56 bits, and I did not separate the two.

**Generation, the second half of the limb:** Markov walks over each
corpus's cluster transitions, using generative calligraphy sheets only.
- **"sequence"** rows: each cluster becomes a newly sampled shape hung off
  one line. They read like a script in an unknown alphabet, the Hokusai and
  calligraphy rows most of all.
- **"morph"** rows: EFD interpolation from one shape to the next while the
  fill depth ramps between mass (full rings), nib (1–4 inward rings, a
  thick rim) and line (the outline loop only). This is "regimes becoming
  one another" carried by shape rather than by width.
  - The Hokusai and calligraphy morph rows show a mass thinning into a rim,
    opening into a sickle, and closing again. **I'd show Ian these first.**

## 5. Failed / weak

1. **Exits are over-counted.**
   - Median exits per body: Marden 9, Henry 13, Hokusai 5, calligraphy 3.
   - Thin wet fringes and texture count as exits, so 80–95 % of bodies are
     "node".
   - The site-conditioned sampling (terminal / through / node) therefore
     mostly falls back.
   - Fix: count only exits that persist ≥ 2 w away from the body.
2. **Size semantics.** Learned shapes take the event size as their
   equivalent diameter. Elongated marks then become long, thin and light,
   while the hand-made ops add ramps. Matching ink area, not diameter, would
   make the comparison fairer.
3. **Counters (line loops) are rare in the events** (2–5 per sheet): only
   half of the light ops use them, and light ops are rare.
4. **Matisse has few counters** (29): his lines rarely close.
5. **The bbox-adjacency language** needs real line-connectivity (skeleton
   graph) before it is evidence of syntax.

## 6. Policy

- Calligraphy and print are measured everywhere (atlas, odd, MI).
- Generation draws only from the generative pool:
  - `generative_pool` runs `calligraphy.require_generative` on every
    calligraphy sheet in the pool;
  - print raises `PolicyError` (books and cassettes are not in
    `GENERATIVE_TYPES`).
- Sampled shapes whose base or mix is calligraphic must sit farther than
  q25 of the calligraphy nearest-neighbour distance from every calligraphy
  shape.
- Outputs are single shapes, never sequences of letters. The language
  transitions for calligraphy use the generative sheets only.
- Tests cover the gate.

## 7. Next limb

The morph chain as an operator: one line event that runs a three-to-five-shape
EFD morph *along* the line (mass → rim → loop → mass), with the shapes drawn
from one corpus's transition chain. Then blind-judge it against the
hand-made `nib` and `body` ops, which were the weakest and the strongest of
round 7.

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
$P -m experiments.shape_lexicon extract        # ~4 min, 2 workers
$P -m experiments.shape_lexicon atlas odd vocab sheets compose language   # ~2.5 min
cd ../.. && .local/gesture/.venv/bin/python -m pytest -q tools/gesture/tests/test_shape_lexicon.py
```
