# Parallel research round — 2026-10-16 (afternoon)

Five agents in parallel, each on its own module, plus a blinded judge.
Detail lives in each result file; this page is the cross-reading.

| # | thread | file | headline |
|---|---|---|---|
| 1 | grammar v4 | `grammar-v4.md` | Corner excess is half steering, half cross-stroke splicing. **Test-1 floor found:** real drawings re-drawn through their own tokens already score AUC 0.64–0.73, so ~0.7 is the target, not 0.5. v4 0.90 / 0.80 / 0.90 (M/H/I). |
| 2 | restyle | `restyle-2026-10-16.md` | Structure kept, slider monotone (useful 0.4–0.8); `gauss` decomposition + `trace` re-synthesis win. Hand attribution of restyled output at chance: restyle inherits the grammar's texture, so the hands look alike. |
| 3 | kinematic (lognormal) | `lognormal-2026-10-16.md` | Faithful representation (fits indistinguishable from originals); interpretable signatures (direction jump between pulses 0.29 M vs 0.61 H). Fixes extrema sharpness, not corners; test 1 not better than v3. Single-line mode is its strongest output. |
| 4 | topology | `topology-2026-10-16.md` | Per-artist composition signatures (artists separate at 0.70–0.75 on topology alone); v3's composition errors named (smooth end-joins where real joins are sharp, ~1.2 rad). `oehlen_tree` generator reads as trees / cell networks. |
| 5 | blind judge | `visual-judge-2026-10-16.md` | After an artefact hunt the judge still spots v3 at 0.83; top cue = coherent contours forming a figure; then tremor, junction behaviour, isolated fragments. |

## What the threads agree on

1. **Two gaps, everywhere.** (a) *Along-line texture*: every generator
   (v3, v4, lognormal, restyle) has ~1.8–2× the real corner rate. (b)
   *Composition*: no figure, fragments unrelated to neighbours — the judge's
   #1 cue and topology's AUC 0.90–0.95. Neither is solved by changing the
   stroke representation alone (lognormal didn't fix (a)).
2. **Single continuous lines are the best output** of both grammar and
   lognormal models — consistent with Ian's direction (contiguous lines,
   Oehlen).
3. **Structure-first works.** Topology trees redrawn by restyle keep their
   structure and junctions; this is the clearest image of "structure
   translated into a hand". What doesn't work yet is making the *hands*
   distinguishable after translation.
4. **Measure against floors.** Test 1's floor is ~0.7 (v4); the judge needs
   its calib_neg; restyle needs a pairwise test on matched structure rather
   than absolute attribution.

## Candidate next round

1. **Joins and corners** from topology's finding: real joins are sharp
   (~1.2 rad) and generated ones smooth; feed join/kiss/double-contour
   statistics into the grammar; corner-aware steering.
2. **Perceived lines** (topology next step 2): merge real strokes across
   aimed near-meetings and sharp joins, so the hand is learned from lines
   as drawn, not as extracted fragments — likely fixes `len_q10` and part of
   the corner excess at the source.
3. **Tremor layer** (judge cue 2, below the grammar's 2 w): a residual
   model at 0.5–2 w, possibly from the lognormal fits.
4. **Composite pipeline sheets**: topology structure → restyle (v4 grammar
   or lognormal) → single-line chaining; judge it pairwise and by eye.
5. **Pairwise hand test** for restyle: same structure, two hands — can the
   panel / judge say which is Matisse?
