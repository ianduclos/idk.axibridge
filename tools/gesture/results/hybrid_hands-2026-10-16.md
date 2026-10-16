# Hybrid and non-human hands — round 8 (2026-10-16)

Code: `gesture/hybrid.py` (new), `experiments/hybrid_hands.py` (stages
`extract learn panel hybrids sheets drift figures`), `tests/test_hybrid.py`
(13 tests, about 2 s). Raw outputs: `.local/gesture/out/hybrid_hands/`
(grammars, 360 generated sheets, `hybrid_positions.{md,json}`,
`panel_real_report.json`, drift JSONs).

## Look at these first

1. `hybrid_hands-drift.jpg`: **the limb.** Four single lines whose hand
   drifts Matisse → shikasta → Lichtenberg. Each line appears twice, in ink
   and coloured by hand weight (blue Matisse, red shikasta, green
   Lichtenberg).
2. `hybrid_hands-population.jpg`: one row per pair. The columns are parent A,
   pooled, mixture, crossover, interpolation and parent B.
3. `hybrid_hands-marden-panel.jpg`: Marden among the real hands.

Also: `hybrid_hands-drift-trace.jpg` (token statistics along the drift),
`hybrid_hands-drift-interp.jpg` (the same drift with interpolated tokens),
`hybrid_hands-drift-chainctx.jpg` (the failure described in §4) and
`hybrid_hands-restyle.jpg` (one Matisse structure redrawn in every hand).

## 1. What a hybrid is here

`HybridGrammar` is a `grammar.Grammar` built over the parents' concatenated
data, so `generate_drawing`, `restyle` and `generate_tokens` run on it
unchanged. Sheet-level data are mixed by weight: drawings (which set ink and
line plans) are replicated to the weight, relations and topology lists are
pooled by weight, and numbers are averaged. Only `draw` differs between the
methods:

- **pooled**: one k-NN pool over both parents; the context chooses.
- **mixture**: each token comes from parent i with probability w_i, drawn from
  that parent's own pool.
- **crossover**: arc-length blocks of 0.06 R, each drawn by one parent only.
- **interp**: each token is moved toward its nearest same-kind token in the
  other parent (log length, κ·R, corner angle). The result is a token that
  neither parent has.

No calibration was done for the new grammars (Marden, shikasta, nasta'liq,
Lichtenberg, bubble chamber), so their cross and end gains are 1.

## 2. Data

- **Marden**: 8 MoMA sheets: the 4 Howell/handmade-paper drawings, St Barts,
  the Aphrodite study and two Cold Mountain–style etchings. They were cropped
  and run through `extract_hybrid` with its defaults, which gives clean
  centrelines. The grammar is learned at `min_len_w` 12; his lines are 4–12
  px wide on 1024 px scans, so 40 w kept only 53 strokes.
- **Lichtenberg-02**: inverted, and extracted with the calligraphy Otsu
  settings because the default hysteresis returned 0 strokes on this dense
  figure. That gives 791 strokes, of which 135 are long. The fine twigs are
  lost. The figure is tiled 2 × 2 into 4 "sheets" so that line plans vary.
- **Bubble chamber**: bc-06 was usable (spirals, tracks, plus fiducial lines
  and a printed legend). bc-04 came out as 16 blobs. The bubble grammar was
  learned from bc-06 but not used further.
- **Policy:**
  - shikasta was trained on wc-12, wc-13 and wc-15; nasta'liq on cma-1983.1115.a,
    met-716304/5/7 and wal-W668-66b/74b. All of these are exercise or document
    sheets and passed through `require_generative`.
  - **Bulaq print is content_type "book", which makes it measure-only.** I did
    not learn from it. The Hokusai × Bulaq pair became **Hokusai × nasta'liq
    exercise sheets**, and Bulaq pages appear only in the panel placement.
  - No output contains legible script; the drift lines are single continuous
    lines.

## 3. Marden in panel space (standard preprocessing, real drawings)

CV AUC of Marden (8 sheets) against each group, and centroid distance in
units of the groups' mean RMS radius:

| # | vs | AUC | distance |
|---|---|---|---|
| 1 | **nasta'liq exercises (10)** | **0.62** | **0.78** |
| 2 | Hokusai | 0.87 | 0.99 |
| 3 | shikasta | 0.91 | 1.03 |
| 4 | Matisse | 0.92 | 1.14 |
| 5 | Bulaq AL09 / AL08 | 0.85 / 0.90 | 1.18 / 1.45 |
| 6 | Ingres | 0.95 | 1.40 |

By nearest centroid, 5 of the 8 Marden sheets fall nearest nasta'liq, 2 nearest
Bulaq AL09 and 1 nearest Hokusai. **Marden sits with the Persian calligraphy
exercises, then with Hokusai, and far from Ingres.**

Caveat: the handmade-paper sheets and the nasta'liq exercises share a
*sparse sheet* (few long strokes). In the PCA view they sit together at the
far left, and part of this nearness may be layout rather than line. The two
etchings (69038, 69053) sit elsewhere, among the brush and print points.

## 4. Where hybrids land (12 sheets per cell, generated-parent axis)

Columns:

- **t**: position on the axis from parent A (0) to parent B (1), median.
- **off**: distance from that axis ÷ the parents' own median off-axis
  distance.
- **P(B)**: a classifier trained on the two generated parents.
- **AUC vs A / vs B**: whether a classifier can tell the hybrid from each
  parent (0.5 means it cannot).

Full table: `.local/gesture/out/hybrid_hands/hybrid_positions.md`.

| # | pair | method | t | off | P(B) | AUC vs A | AUC vs B |
|---|---|---|---|---|---|---|---|
| 1 | Matisse × shikasta | pooled | .14 | .87 | .28 | .67 | .92 |
| 2 | | mixture | .09 | 1.12 | .13 | .88 | .99 |
| 3 | | crossover | .20 | 1.11 | .27 | .83 | .91 |
| 4 | | interp | .22 | 1.21 | .17 | .90 | 1.00 |
| 5 | Hokusai × nasta'liq | mixture | .07 | 1.07 | .38 | .64 | .74 |
| 6 | | interp | .14 | 1.16 | .36 | .71 | .89 |
| 7 | Ingres × Matisse | pooled | −.08 | 1.24 | .54 | **.85** | **.86** |
| 8 | | mixture | .02 | 1.22 | **.50** | .59 | .66 |
| 9 | Marden × shikasta | pooled | .16 | .93 | .35 | **.38** | .71 |
| 10 | | mixture | .59 | .90 | .52 | .53 | .67 |
| 11 | | interp | .45 | 1.01 | .53 | .52 | .62 |
| 12 | Matisse × Lichtenberg | pooled | .93 | 1.29 | .92 | .99 | .79 |
| 13 | | mixture | .95 | 1.34 | .79 | .91 | .64 |
| 14 | | interp | .87 | 1.31 | .82 | .93 | .67 |

What the table supports:

1. **No method reliably lands midway.**
   - Hybrids collapse toward one parent: Matisse wins over shikasta,
     Hokusai over nasta'liq, and **Lichtenberg wins over Matisse**.
   - The collapse is not complete. Most hybrids remain separable from the
     parent they collapse toward (AUC .64–.99): they are near that parent
     but slightly off it.
2. **Pooled k-NN collapses hardest.** In a pooled Matisse × shikasta sheet only
   **4 % of tokens come from shikasta**. Matisse's pool is about 10× larger,
   and its context always finds a Matisse record. The context decides who
   speaks, and the bigger, more self-similar hand wins.
3. **Close hands mix cleanly.**
   - Ingres × Matisse mixture sits at P(B) = .50 and is hard to tell from
     either parent (.59 / .66).
   - Marden × shikasta mixture and interpolation land midway (t ≈ .5,
     P(B) ≈ .52).
   - Pooled Ingres × Matisse is the one **"third thing"**: separable from
     both parents (.85 / .86) and the most off-axis among the Ingres × Matisse
     methods.
4. **Off-axis ratios are about 0.9–1.4.** Hybrids do not leave the parents'
   spread by much. There is no strong evidence of a region that neither hand
   occupies. Matisse × Lichtenberg comes closest (1.3–1.4).
5. **A mechanism found on the way.** A hand's k-NN depends on its "remaining
   length" context. If a short-stroke hand (shikasta strokes have a median of
   0.039 R, Lichtenberg 0.088 R) is asked for a line planned by a long-stroke
   hand (Matisse, 0.106 R), it extrapolates. That plausibly contributes to the
   collapse: the hybrid's lines are planned by whichever parent's drawing the
   sheet drew.

The restyle sheet (`hybrid_hands-restyle.jpg`, centre detail at ×2.2) shows
little difference between hands. Hybrids add small nicks and bumps, and the
Lichtenberg restyle is almost smooth. At `detail_frac` 0.015 the restyle
residual carries little hand, so the sheet is not much evidence either way.

## 5. The limb: a hand that drifts along one line

`hybrid.drift_line`:

- one line of 6 R grown in chunks, each chunk the best of 8 proposals (stay
  on the sheet, avoid crowding);
- route weights move along arc length: Matisse is pure at the start,
  shikasta in the middle, Lichtenberg at the end, with linear cross-fades;
- **chunks are training-length strokes of the hand that dominates at that
  point**, and κ is made continuous at each joint.

Shares of tokens by hand per tenth of the line (drift 1):

| tenth | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Matisse | .93 | .76 | .48 | .17 | 0 | 0 | 0 | 0 | 0 | 0 |
| shikasta | .07 | .24 | .52 | .83 | 1 | 1 | .75 | .64 | .25 | 0 |
| Lichtenberg | 0 | 0 | 0 | 0 | 0 | 0 | .25 | .36 | .75 | 1 |

**Did it hold? Visually, mostly yes.** On the sheet:

- The Matisse stretch is contour-like with small loops.
- The shikasta stretch turns into tight curls, hooks and spirals. The median
  |κ|·R peaks at 45 against the training 12.
- The Lichtenberg stretch opens into long sweeping arcs with occasional
  corners. Segments lengthen from .022 to .05 R (training .079).

The cross-fades are the interesting part: corner rates there are 15–18 per R,
about 2× Matisse and 4× shikasta. **The transition makes its own awkwardness**
that neither parent has. That fits the brief's interest in transitions, but
it is an artefact of splicing two pools, not something either hand showed us.

**What surprised me:**

- **Lichtenberg as a hand is gentle.** As a *line* it is long, smooth arcs
  with few corners (1.1 per R, against Matisse 7.7). Its "spark" character is
  topological: branching and density, which a single line cannot carry. The
  spark is in the sheet, not in the line. A drift into Lichtenberg needs the
  relations layer (branch starts), not tokens.
- **The failed first version is worth a look**
  (`hybrid_hands-drift-chainctx.jpg`). Conditioning each chunk's k-NN on the
  previous chunk's last two tokens, which `grammar`'s single mode does, sends
  short-stroke hands into a **corner and straight-line attractor**: median
  |κ| 0, corners 3–15× the hand's own rate. The lines are jagged polygons:
  awkward and sometimes striking, but not the hand.
  - This probably also explains the calligraphy round's finding that
    "single-line mode looks like a coastline" for shikasta.
  - Proof for this round: in fresh chunks shikasta keeps |κ|·R 3.4–4.9 and
    9–11 corners per R; with chained context it falls to |κ| 0 and 27–37
    corners per R.

## 6. Proposed changes to existing modules (not made)

1. `grammar._single_line` / `generate_tokens(context=…)`: offer a mode that
   uses the previous tokens for κ continuity only, not as k-NN context. This
   matters for short-stroke hands (calligraphy, earth). See §5.
2. `grammar.generate_drawing`: let a mixed grammar plan lines per hand (plan
   length from the hand that will draw the line). Today a hybrid's plan comes
   from whichever parent's drawing the sheet drew (§4.5).
3. `calligraphy`/earth extraction: dense figures need the Otsu settings. A
   coverage-based auto-switch in `extract_hybrid` would have saved a rerun.

## 7. Next limbs

- Drift in **regime space as well as hand space**: let the Lichtenberg end
  of a drift line spawn branch starts through the relations layer, so the
  spark arrives as topology.
- A **population of drifts** over all 2-hand routes (Marden → nasta'liq is the
  pair the panel says is closest; Hokusai → Lichtenberg the furthest), judged
  on the sheet.
- The "gap" limb, generating from where no corpus sits, was not attempted. The
  off-axis ratios say hybrids do not reach the gap by themselves.

## Commands

```bash
cd tools/gesture; P=../../.local/gesture/.venv/bin/python
$P -m experiments.hybrid_hands extract      # ~1 min (Lichtenberg ~30 s)
$P -m experiments.hybrid_hands learn
$P -m experiments.hybrid_hands panel        # ~1 min
$P -m experiments.hybrid_hands hybrids --n 12   # 360 sheets, ~6 min at 2 workers
$P -m experiments.hybrid_hands sheets
$P -m experiments.hybrid_hands drift --drift-mode mixture --trace 12
$P -m experiments.hybrid_hands drift --drift-mode interp --trace 12
$P -m experiments.hybrid_hands drift --context chain --tag _chainctx   # the failure
$P -m experiments.hybrid_hands figures
```
