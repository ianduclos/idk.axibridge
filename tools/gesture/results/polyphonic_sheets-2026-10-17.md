# Polyphonic sheets: units, pages, annotation, conversation (round 9, 2026-10-17)

Thread `polyphonic_sheets`. This round adds kit modules
`gesture/kit/poly_sheets.py` and `gesture/kit/poly_converse.py`, the
experiment `experiments/polyphonic_sheets.py` (`annot | scatter | page |
converse | mixed | all`) and the tests `tests/test_polyphonic_sheets.py`
(10 tests, about 3 s). The images and their recipe JSON are in
`.local/gesture/out/polyphonic_sheets/`, and the numbers are in
`measure.json` there.

The question came from the round-8 review: a sheet should be a set of
distinct grammars, each kept whole and set side by side, with some elements
commenting on others. Sheet composition supplied the diagnosis: our sheets
were one welded net (1–2 islands, 6 free ends per side-length, margin
ratio 0.14), and structure, not post-processing, decides what kind of
composition you get.

## What was built (all arrangers take any voice by id)

1. **`poly_scatter`** scatters separate units over the sheet.
   - Part *i* becomes `counts[i]` units at its own size class, `sizes[i]`.
     Each voice has one scale, because a hand writes at one size.
   - Units are either **cut** from one long line (words of one utterance)
     or **restated** (separate growths with seeds derived from the part
     seed).
   - `bleed` pushes units over an edge, where they are clipped exactly. The
     cuts carry channels, so the ends at the sheet edge are free ends.
   - `pull: edges` gives a dominant unit with marginal units at the rim.
   - `rotate` can be none, quarter (each unit turned) or voice (one turn
     per voice).
2. **`poly_page`** lays out a page of writing.
   - Body voices are cut into words and laid in rows: 1–4 columns, ltr or
     rtl, ragged or justified, with a common x-height per voice.
   - With several body voices, `interlinear` alternates them row by row.
   - Gloss voices are set small in a margin column beside the rows they
     gloss.
   - `bleed` lets rows run past the block into the sheet edge.
3. **Annotation** works in all three arrangers through `annotate`,
   `annotator`, `n_annot` and `annot_amp`.
   - The annotator part draws no unit of its own. Its voice is regrown for
     each annotation and **band-warped** along a route that another unit
     defines: the line's principal axis runs along the route, and its minor
     axis becomes the band's lateral motion (95th percentile = `annot_amp`).
   - Routes: `underline`, `bracket` (a span of 2–4 rows on a page, with
     hooks), `encircle`, `tether` (from a unit's free end to a unit of a
     different voice), `point` (from beyond the sheet edge to a unit,
     stopping short), `echo` (the unit's own path, smoothed, offset and
     partial: a paraphrase), and `mixed`.
   - The annotator keeps its own modulators and renderer, so a
     staccato-danced nib, a dance trail or a dry Lichtenberg wire can all
     annotate.
4. **`poly_converse`** (the limb) is described below.

## Numbers (sheetcomp, clean render at 4 px/mm)

Distances are RMS robust z over the 15 composition statistics, using the
corpus scale. The first three rows are references from
`sheet_composition`.

| sheet | islands 1 % | islands 3 % | free ends / len | margin | cover | d ref | d mashq | d Marden |
|---|---|---|---|---|---|---|---|---|
| *r7 (old)* | 2 | 1 | 6.3 | 0.14 | 0.131 | — | — | — |
| *Ian ref 2024* | 12 | 5 | 15.2 | 0.67 | 0.233 | 0 | — | — |
| *mashq median* | 92 | 14 | 43.9 | 0.73 | 0.139 | — | 0 | — |
| scatter A dominant | 16 | 12 | 17.2 | 0.73 | 0.022 | 1.51 | 1.22 | 0.93 |
| scatter B cut, many | 25 | 22 | 10.5 | 1.19 | 0.029 | 1.54 | 1.23 | 1.23 |
| **scatter C sizes** | 20 | 13 | 35.2 | 0.87 | 0.031 | **1.03** | **0.73** | **0.66** |
| **page P1 interlinear** | 168 | 19 | 31.6 | 0.87 | 0.056 | 1.23 | **0.69** | 0.88 |
| page P2 columns rtl | 233 | 11 | 34.5 | 0.60 | 0.045 | 1.04 | 0.74 | 0.78 |
| page P3 sparse | 40 | 35 | 17.0 | 0.83 | 0.016 | 1.72 | 1.28 | 1.20 |
| M1 page, sibling voices | 134 | 30 | 65.4 | 1.09 | 0.054 | 1.44 | 0.92 | 1.03 |
| converse contrast | 10 | 7 | 9.8 | 1.17 | 0.020 | 2.28 | 2.05 | 1.71 |
| converse echo | 12 | 10 | 9.0 | 1.22 | 0.019 | 2.18 | 1.91 | 1.69 |

- **The net is broken.** Every arranger moves the two statistics nothing
  else moved:
  - islands go from 2 to 8–233;
  - margin contact goes from 0.14 to 0.6–2.1, at or above the reference's
    0.67;
  - free ends go from 6 to 9–74.
- Scatter C and the pages are the nearest of all our sheets to mashq and
  Marden, at distance 0.66–0.74 (the round-8 tuned best was 0.43–0.73).
- **What still separates us from the reference is cover.** We are at
  2–6 %; the reference is at 23 % and the corpora at 6–17 %. Islands are
  no longer what is off. The pages over-fragment: 168–233 islands at 1 %,
  because a "word" cut from a whole-drawing line is a tiny arc.

## Images worth Ian's eyes

1. **`results/polyphonic_sheets-page.jpg`, P1, and
   `results/polyphonic_sheets-siblings.jpg`, M1.** These are interlinear
   pages. Shikasta in nib lanes alternates row by row with a thin Marden
   wire (P1), or with the sibling `machine` voice's angular re-speaking
   (M1). Two incompatible scripts share a page and do not merge. It reads
   as writing at the threshold of legibility, with no content. In M1 a
   dance trail circles words and underlines the last row.
2. **`results/polyphonic_sheets-page.jpg`, P2.** The annotation is a
   heavy staccato-danced nib: brackets and underlines cross a two-column
   rtl page like an editor's marks. They are louder than the text they
   comment on. Weight here is a decision about stress, which is principle 3
   at sheet scale.
3. **`results/polyphonic_sheets-scatter.jpg`, C.** Three voices at
   different sizes: large dry bubble shapes, mid Ingres→Marden units
   danced by Particles, and tiny Shikasta nib units. A Hokusai wire
   encircles one unit and tethers or points across the others. This sheet
   is nearest to the reference and the corpora.

Also see `results/polyphonic_sheets-annotation-modes.jpg`: the six
annotation modes on one scatter. `encircle` and `echo` read immediately.
`underline` with a Lichtenberg band comes out nearly straight. `point`
gives long crossing lines.

## The limb: conversation as a composition rule (`poly_converse`)

Units take turns. Each reply is derived from what the previous unit drew:

- **Hand.** We measure three scale-free statistics on the caller's line:
  turning per radius of gyration, straight share, and compactness. These
  are compared with a probe line from every hand in the pool. `contrast`
  replies in the most unlike hand, `echo` in the most alike, and
  `alternate` switches between the two. A `drift` voice gets the route
  [caller's hand → reply hand], so the reply begins in the caller's voice
  and drifts away.
- **Length.** A busy call gets a short reply.
- **Weight.** A heavy call gets a dry reply.
- **Placement.** The reply starts where the call ended, a gap away along
  the call's last heading. It takes the best of 8 orientations, or starts a
  "new topic" in the emptiest place.

**Did it hold? Partly.**

1. **The rule works mechanically.** The turn log is in
   `marks[0].meta["converse_log"]`. Contrast without memory ping-pongs
   between two extremes (matisse ↔ polygon_walk). This is a real finding
   about "most unlike" as a rule. It led to `memory`: avoid the last N
   turns' hands, and the exchange travels through the pool.
2. **It does not read by eye.** Two things hide it:
   - **The weight chain.** The speaker's own modulators (staccato →
     masses) dominate every second unit. The units that look alike are the
     ones that share a chain, whatever hand they speak in.
   - **Placement.** "Start where the call ended" either welds the
     exchange back into a net (gap 4 mm: 6–8 islands, the old failure) or,
     with a strict overlap rule (gap 10 mm), sends most replies to "new
     topic", so the turn-taking disappears into a scatter.

   The converse sheets measure worst of all of these: distance 2.2–2.3 to
   the reference.
3. **The rule is right, but its outputs are wrong.** What a reply changes
   has to be visible at the scale of a unit. Next time the rule should
   steer a *visible* property, such as size, weight, orientation or
   density, before it steers the hand. The placement should be a
   *response position* (beside, below, facing) rather than a continuation.

## Surprises

- The **siblings' voices dropped straight in**: `machine`, `diagram` and
  `dance`, by id with default params. A `diagram` cut into units makes
  tiny chart-like units, a near-object, at the rim (M2).
- The **library grew mid-run**: `polygon_walk`, `meander69`, `aaron` and
  dance hands appeared. With an empty pool, `poly_converse` draws on every
  generative hand present, so its output depends on the library's contents.
  Recipes should pin `pool`, and the experiment does.
- A **bracket band-warped from a Lichtenberg line** reads as a real
  bracket. The grammar survives as small hesitations along the stroke.

## Failures

- **P3 is a dud.** It has six rows and few long words, and nothing reads
  as rows.
- **Cut mode on whole-drawing hands** makes arcs. The units lose the
  grammar's identity, so restate mode is usually better for scatter.
- **Gloss columns look thin.** Small gloss words cut from a long line
  nearly vanish at 0.45 of the body's x-height.
- `underline` in `mixed` mode can also be nearly straight.

## Proposed kit-core changes (not made)

1. **`Part.variant(k)`** (or `Part.restated(k)`): a copy with a seed
   derived from (part seed, k), keeping its index and renderer. Unit
   arrangers need several growths per part. `poly_sheets._variant` does
   this today with `copy.copy` and a seed assignment.
2. **`Part.with_spec(spec)`**: the same copy with a re-validated voice
   and modulators. `poly_converse` hand-validates the edited voice spec.
3. **A per-run sheet log in `Sheet.meta`**, e.g. `ctx.note(key, value)`
   from arrangers. Today the converse log rides on the first mark's meta.
4. **A `strs` param type**, a list of strings, for per-part roles.
   `poly_page.roles` is a space-separated `str` today.

## Tests

- **Mine:** 10 passed in 3.2 s.
- **Whole research suite:** 486 passed and 1 failed. The failure is
  `test_kit.py::test_committed_library_shape_and_budget`, which asserts
  the seed set of library ids. It fails because sibling threads added
  library entries (`aaron`, `meander69`, `dance_*`, …). This thread added
  no library entries.

## Next limb

1. **Density.** Raise cover toward the reference, with heavier units and
   pages with fewer, longer words, without re-welding the net.
2. **Conversation that changes visible properties.** Make a reply's size,
   weight and position answer the call, using response positions.
3. **Annotation by a voice that is itself a process.** Use `diagram` as the
   annotator: the system's measurement of a unit drawn beside it, as its
   gloss.
