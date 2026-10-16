# Grammar v2: long lines, σ in line widths, order-2 chain, relations layer (2026-10-16)

`gesture/grammar.py` v2, `experiments/grammar_eval.py` (scale / prepare / test1 / memo),
`experiments/generate_demo.py`. Extractor: `extract_hybrid`. Raw tables:
`.local/gesture/out/grammar_v2/{scale,trainset,test1,memo}.md`. Sheets:
`grammar-v2-matisse.jpg`, `grammar-v2-hokusai.jpg`, `grammar-v2-juxtaposition.jpg`.

**Verdict:** the drawings now read as contiguous, winding, branching lines, and the
order-2 chain speaks rather than quotes. **Stage-3 test 1 still fails:** real vs
generated AUC is 0.92 to 1.00. The separating features are the to-do list below.

## 1. Scale study: σ = 2 line widths

150 random long strokes per artist (≥ 40 w, no hatching). Each stroke was fitted at
every σ. err = `rms_position_error`, measured against the smoothed stroke.

| # | σ | segs/stroke median, M / H / I | single-segment share | segs, strokes ≥ 100 w | median segment length (w) | corners/stroke | err/w (median) | err/σ |
|---|---|---|---|---|---|---|---|---|
| S1 | 1.5 w | 4 / 3 / 3 | .06 / .07 / .15 | 7 / 7 / 7 | 20 | 1.1–1.7 | .42–.48 | .28–.32 |
| **S2** | **2 w** | **3 / 3 / 2** | **.11 / .13 / .22** | **6 / 5 / 6** | **24–26** | **0.9–1.2** | **.51–.68** | **.26–.34** |
| S3 | 3 w | 2 / 2 / 2 | .25 / .31 / .43 | 4 / 4 / 3.5 | 36–41 | 0.7–0.9 | .68–.91 | .23–.30 |
| S4 | 5 w | 2 / 1 / 1 | .47 / .63 / .76 | 3 | 49–51 | 0.3–0.5 | .81–1.32 | .16–.26 |
| S5 | 0.005·R (2.2–4.4 w) | 2 / 3 / 2 | .46 / .23 / .49 | 3–5.5 | 25–49 | 0.6–1.4 | .67–.95 | .19–.32 |
| S6 | 0.01·R (v1, 4.4–8.8 w) | 1 / 1 / 1 | .74 / .51 / .88 | 1–3 | 43–65 | 0.1–0.8 | .80–1.33 | .11–.28 |

Why 2 w:

1. It is the coarsest scale at which a typical long stroke carries ≥ 3 segments
   (Matisse and Hokusai), and strokes ≥ 100 w carry 5–6. At v1's scale, 74–88 % of
   strokes were a single segment.
2. A segment is about 25 w long, two orders of magnitude above the extractor's
   residual wander (0.03–0.2 w). The fit error is ≈ 0.3 σ at every scale, so the
   penalty is not adding knots for noise.
3. Going to 1.5 w adds about one segment, but also 15–35 % more corners and twice the
   fit time. The extra corners are the sign of resolving junction kinks and wander.
   For Ingres, 2 w gives a median of 2 segments (6 on strokes ≥ 100 w). 1.5 w would
   lift that to 3, which is the honest trade-off.
4. This is a finer scale than the panel's 7 w floor, as v4 predicted for order.

## 2. Training set: long, non-hatching strokes only

A stroke is kept if it is at least max(40 w, the drawing's median stroke length)
long and is not hatching.
Hatching detector (`hatch_mask`): a stroke is near-straight (chord/length ≥ 0.8),
≤ 150 w long, and has ≥ 3 near-straight neighbours within 20°, within a length ratio
of 2.5, and with centroids within about its own length.
I checked the mask visually on Matisse KKS10283, Hokusai 57260 and Ingres 409004. It
catches the background and shading hatching. On Hokusai it also flags a few short
contour details.

| # | artist | drawings | strokes | hatching | kept | ink kept | hatching ink | kept per drawing | long ink per drawing (R) | length (w) median / q90 | segs median | attached-end share | branch ∠ median | X/ink |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | matisse | 31 | 7961 | 1691 | 1308 | 50 % | 20 % | 31 | 5.7 | 80 / 227 | 3 | .26 | 61° | .24 |
| T2 | hokusai | 27 | 8176 | 2377 | 726 | 30 % | 31 % | 22 | 4.9 | 62 / 136 | 3 | .44 | 50° | .26 |
| T3 | ingres | 34 | 16994 | 3370 | 1272 | 24 % | 32 % | 35 | 4.0 | 59 / 153 | 2 | .20 | 49° | .20 |

**Finding:** only a quarter of Ingres' ink is long, contiguous line. A third is
hatching. The Ingres grammar therefore learns his contour hand only.

## 3. Grammar v2: how it works

- **Tokens.** As in v1: line, arc and clothoid segments plus corners. κ stays
  continuous inside corner-free runs. Each training stroke is also added reversed.
- **Order.** The next token's kind and parameters are drawn together. They come from
  the 12 nearest training transitions that share the previous token's kind. The
  context has four parts:
  1. the previous token's parameters;
  2. the token before that, with a penalty when its kind differs;
  3. the log of the remaining length;
  4. the position s/L along the stroke.
- **Stroke lengths** come from the long-stroke distribution.
- **Relations** learned per drawing:
  - attached ends (endpoint within 2 w of another stroke);
  - where the attachment sits on the host (u) and the branch angle;
  - X crossings per unit of ink;
  - share of strokes that cross themselves;
  - ink per drawing and w/R.
- **`generate_drawing(mode="contiguous")`** is the default. It uses tree relations:
  1. 1–3 strokes start free, at the emptiest of 8 candidate points.
  2. Every later stroke either continues from a free end or branches from a host's
     interior, at a learned u and angle.
  3. Of a few candidate attachment points, the least crowded wins.
  4. Each stroke is then walked against the ink already on the sheet. At the sheet
     edge it stops. When it meets another line it crosses only while the drawing
     stays under the learned crossing rate × ink; otherwise it ends on that line
     (a T-junction). It does not cross itself unless chosen to (learned share).
  5. Strokes shorter than the shortest training stroke are discarded.
  6. Strokes are added until the ink budget (sampled from the real drawings) is spent.
- **`relations="learned"`** sets the branch probability to the learned attached share
  instead. That is the fidelity variant, used in test 1.
- **`mode="single"`** draws one line, chunk by chunk, using the previous two tokens as
  context and keeping κ continuous across chunks. A chunk that would run into the
  line or off the sheet is retried. After 4 failed tries, the line turns toward open
  space with a **corner token**. That steering corner is an artificial device, not
  the hand.
- **Hand switching.** `hands=(gA, gB)` alternates hands along a single line.

## 4. Stage-3 test 1 (fair comparison): fails

Real drawings were reduced to the same long-stroke subset the grammar learned from.
Each artist got as many generated drawings as real ones, at the same canvas sizes.
Features: panel with `sigma_min_w = 7`, the medium projection, geometry columns only.
Grouped 5-fold CV, 5 repeats.

| # | artist | relations | n | AUC (geometry), logreg / forest | AUC (geometry, no `rel_`), logreg / forest |
|---|---|---|---|---|---|
| A1 | matisse | learned | 31/31 | 0.971 / 0.976 | 0.916 / 0.947 |
| A2 | matisse | tree | 31/31 | 0.996 / 1.000 | 0.885 / 0.901 |
| A3 | hokusai | learned | 27/27 | 0.960 / 0.922 | 0.911 / 0.922 |
| A4 | hokusai | tree | 27/27 | 0.998 / 0.994 | 0.944 / 0.940 |
| A5 | ingres | learned | 34/34 | 0.995 / 0.989 | 0.947 / 0.964 |
| A6 | ingres | tree | 34/34 | 1.000 / 1.000 | 0.995 / 0.982 |

Top separating features (Cohen's d, generated − real). This is the to-do list:

1. **Stroke length is too short** in every case: `len_q10` −1.3 to −1.7 d,
   `len_q50` −0.9 to −1.4 d. The walk truncates strokes at T-junctions and at the
   sheet edge, and it accepts results down to half the target length. Fix: re-draw
   the target length after a truncation, or condition the remaining-length context
   on the space actually available.
2. **Tree relations are visible by design:** `rel_touch_rate` 0.15 → 0.71–0.73 and
   `rel_gap_log_q50` −5 to −7 d. The real extracted subsets are fragments with
   gaps, and the tree is Ian's composition. That makes the `rel_` columns an unfair
   target for tree mode. The no-`rel_` column is the relevant one, and it is still
   0.89–0.99.
3. **Crossings:** Hokusai's `rel_cross_per_len` comes out 2–4× too high. The rate
   controller counts crossings per drawing, but the panel's crossing measure differs
   (T-ends near endpoints, closed loops).
4. **Curvature texture:** for Ingres, extrema are 50 % higher (`ext_turn_q50`,
   `ext_h_q50`) and inflection and extrema rates are lower. For Matisse,
   `cl_corner_rate` is +0.9 d and clothoid slopes run steep. Corners and κ spikes
   cluster too much, probably because joints that the order-2 k-NN resamples
   splice together sharp tokens.

## 5. Memorisation, done properly: speaks, does not quote

Method:

- 4/5 of the drawings for training, whole drawings held out.
- Multi-segment strokes only.
- Distance = turning-signature nearest-neighbour distance to the training strokes.
- Four comparison sets:
  - generated strokes (lengths matched to the held-out ones);
  - held-out real strokes;
  - a **control grammar trained on segment-shuffled strokes**;
  - **jittered copies of training strokes**, which shows the quoting floor
    produced by generation's own jitter.

| # | artist | strokes | generated (median) | held-out real | shuffled control | jittered training (quote floor) | generated below held-out q10 |
|---|---|---|---|---|---|---|---|
| M1 | matisse | ≥ 2 seg | 0.256 | 0.271 | 0.324 | 0.081 | 9 % |
| M2 | matisse | ≥ 4 seg | 0.306 | 0.322 | 0.390 | 0.082 | 12 % |
| M3 | hokusai | ≥ 2 seg | 0.324 | 0.324 | 0.335 | 0.122 | **23 %** |
| M4 | hokusai | ≥ 4 seg | 0.423 | 0.423 | 0.448 | 0.166 | **19 %** |
| M5 | ingres | ≥ 2 seg | 0.260 | 0.258 | 0.275 | 0.081 | 9 % |
| M6 | ingres | ≥ 4 seg | 0.364 | 0.347 | 0.428 | 0.122 | 2 % |

Reading:

1. Generated strokes sit where held-out real strokes sit, 3–4× above the quote
   floor. The chain speaks the hand rather than quoting it.
2. The shuffled control is consistently farther from the training strokes (by 0.06–0.08
   on ≥ 4 segments). Order now carries information the bag of segments doesn't.
3. Hokusai's lower tail is too close (19–23 % below the held-out q10, where 10 % is
   expected). With only 726 training strokes, k = 12 sometimes walks along a single
   source stroke. KNN should scale with pool size.

## 6. The sheets, honestly

1. **Contiguous / tree mode** is no longer confetti. The lines wind, fork and touch,
   form closed cells, and fill much of the sheet at the learned ink.
   - The Matisse hand reads as long, slow arcs and clothoids, with occasional abrupt
     corners: organic, coherent, a little uncanny.
   - Hokusai reads distinctly: tighter curls, small spirals, more kinks and zig-zags.
   - Ingres is sparser and more angular. Its contour-only grammar shows.
   - Duds exist: sheets with a sampled ink budget of 1–2 R are sparse, and some trees
     stay in one corner. That is within Ian's population tolerance.
   - The look is closer to an Oehlen line-network than to the real figure drawings.
     There is no figure, and no Oehlen-style dense overlap either.
2. **Single mode** gives one long continuous line that loops and doubles back.
   The steering corners show as sharp V-turns and zig-zags, which is useful
   awkwardness but not the hand.
   - Some lines stall before reaching the ink budget (3.7–6.3 of 8.4 R on Matisse).
3. **Juxtaposition.**
   - The code-switching line visibly changes character at each switch: red Matisse
     stretches are long and calm, blue Hokusai stretches are curlier and kinkier.
   - Restyling the Matisse tree in Hokusai's hand keeps the structure and roughens the
     fine turning.
   - Token translation keeps each stroke's start and heading, but the strokes drift
     away from the tree and become disconnected. Translation does not preserve
     relations.

Ready for Ian to look at. None of this is plotted, and these statistics are not a
verdict on the drawings.

## 7. Next steps

1. **Length deficit (item 4.1):** resample or extend truncated strokes, so that
   accepted lengths follow the training distribution after the walk.
2. **Test 1 for tree mode without `rel_`, plus a "chain" measure:** merge
   tangent-continuous end-to-end strokes before computing the panel. Extraction never
   splits a smooth continuation, so the real subsets should be compared after the
   same merge.
3. **Order-2 splices:** smooth κ at joints only up to the training joint statistics,
   and scale KNN with pool size (this is also the Hokusai quoting tail).
4. **Single-mode steering:** replace corner steering with κ-biased chunk selection
   (draw several chunks and choose by how much free space lies ahead) so the hand
   steers itself.
5. **Ingres:** try σ = 1.5 w for that hand, or accept a contour-only Ingres.
6. **Translate with relations:** re-anchor each translated stroke at its host point.

## Commands

```bash
cd tools/gesture
../../.local/gesture/.venv/bin/python -m experiments.grammar_eval scale     # ~5 s
../../.local/gesture/.venv/bin/python -m experiments.grammar_eval prepare   # ~10 s, caches fits
../../.local/gesture/.venv/bin/python -m experiments.grammar_eval test1     # ~1 min
../../.local/gesture/.venv/bin/python -m experiments.grammar_eval memo --n 600
../../.local/gesture/.venv/bin/python -m experiments.generate_demo          # ~20 s
```
