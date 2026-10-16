# Idea pass 5 — the gesture bank (October 2026)

Brainstorm + research plan, 2026-10-16. Not commitments — ROADMAP.md carries
conviction ordering. Passes 1–4 are `IDEAS-generators.md` (Cohen / uncanny),
`IDEAS-oehlen-pass.md` (regime collision), `IDEAS-aaron-pass.md` (AARON's
mechanisms) and `IDEAS-pass4.md` (stakes, fields, blending).

Ian's prompt: a bank of gesture styles. Analyse the lines of a painter, a plant,
typography — distil the *hand* — draw with it, then juxtapose hands. First
target chosen: **Matisse's line drawings**, and the lens is **geometric** even
where the source isn't.

## The framing

Every line has two layers: the **path** (where it goes — composition) and the
**hand** (how it gets there). The hand is what this pass is about, and it is
geometrically well-posed:

> **A hand is a probability distribution over curvature-vs-arc-length κ(s),
> plus rules for how strokes relate to each other.**

κ(s) is intrinsic — invariant to position and rotation, and to scale once
normalised — and, unlike timing, it survives a scan. It is direction-invariant
up to sign, so the analysis does not need stroke order or direction, which a
scan cannot give back.

Matisse is a good first case precisely because his line is near-uniform in
width with few crossings: stroke recovery from a raster is mostly tractable.

## What the research said (2026-10-16, five parallel passes)

1. **The κ(s)-as-style idea is untried.** Every piece exists separately —
   piecewise-linear κ(s) fitting (McCrae & Singh 2008, which is option A
   almost verbatim), Markov chains over drawing primitives (Lake et al. 2015,
   BPL), stroke-level attribution (Elgammal et al. 2018) — but nobody has used
   a clothoid/κ(s) decomposition as a style signature or a generative grammar.
2. **The warning: geometry alone discriminated weakly.** Elgammal et al.
   (Picasso vs Matisse, 297 drawings, ~80k strokes) found stroke *thickness*
   the strongest single feature (63.7%); contour curvature alone 60.2%; all
   features combined 75% per stroke, >80% per drawing. Thickness is the one
   thing a pen plotter can't vary. So the panel must lean on segment, corner,
   ending and inter-stroke statistics, not mean curvature.
3. **The Pollock lesson.** Taylor's fractal "signature" was passed by a
   child's star doodle and by Gaussian random motion. Every style statistic
   must be validated against **null drawings**, not just against other
   artists.
4. **Data scale kills deep models.** sketch-rnn wants thousands of drawings;
   VQ-SGen/StrokeFusion train on QuickDraw. A freely obtainable Matisse corpus
   is ~150–300 clean line works. Tokens + sequence model (C) are fine as an
   *analysis* codebook (~10k+ strokes), not as a generator.
5. **AI writing the generator (D1) is the most feasible "smart" route** and is
   uncharted for a named artist's line style. Closest precedents close a
   render→critique→revise loop (SketchAgent, IntroSVG, RLRF). Main risk:
   Goodhart — code that hits the statistics and misses the line.
6. **VLM-as-judge (D2) is a calibrated sanity check, not a reward.** VLMs are
   decent at pairwise comparison, poor at absolute scoring and at artist
   attribution, and swing heavily on authorship labels. With Matisse they will
   likely key on *subject* (odalisques, faces) rather than line.
7. **Stroke recovery from a scan is solvable for a spike, unsolved in
   general.** Skeleton → graph → pair branches by tangent continuity. X-vs-T
   junctions and pencil grain are the hard cases; stroke direction is at best
   a per-stroke probability; global order is unrecoverable. Never compute κ
   from a vectorizer's SVG — they smooth and simplify, biasing curvature.
8. **Corpus is legal for private research but US status is contested.**
   Matisse is public domain in the EU/France since 2025-01-01; the estate
   (via ARS) still claims most US rights. Usable now: **SMK Copenhagen**
   (open API, IIIF, PD-marked lithographs/etchings/drawings up to ~8,900 px)
   and **BnF Gallica** (~660 items, free non-commercial reuse with credit).
   Comparison hands that are fully PD: Ingres, Hokusai, Schiele, Rodin,
   Modigliani. Picasso and Giacometti are not.

## The representations (from the brainstorm)

- **A. Clothoid alphabet.** Fit each stroke's κ(s) as piecewise-linear
  (McCrae DP / Baran shortest-path): line, arc, clothoid pieces. Hand =
  distribution of segment params + transition probabilities. Inspectable,
  generative immediately.
- **B. κ-strokelets.** A dictionary over κ(s) windows; sparseness of
  reconstruction as a fidelity score. Our adaptation of Hughes et al. (who
  coded *pixel patches*, not curves, and used coefficient kurtosis).
- **C. Tokens + small model.** Vector-quantise κ(s) fragments into a
  vocabulary. Analysis codebook first; generation deferred.
- **D1. AI writes the generator** in A's primitives, scored on the panel.
- **D2. AI as critic**, only after calibration.
- **Above the stroke: economy and relation.** Strokes per figure, one line
  standing for two edges, open vs closed contours, where curvature extrema
  fall relative to the subject's (Attneave). Lake's BPL relations ("start of",
  "end of", "along") are the precedent.

## The staged plan

Each stage ends in a **gate**: a test that decides whether the next stage is
worth building. Stages 0–2 are pure research code; nothing touches the
compositor until stage 3.

### 0. Corpus, nulls and ground truth

- Pull 50–100 clean single-contour works from SMK (API) and Gallica:
  Mallarmé etchings, Ronsard lithographs, *Thèmes et Variations* plates if
  available. Exclude tonal odalisque lithographs. Record source + license per
  image. Scans live **outside git** (gitignored, or machine-level like the
  gallery); only manifests are committed.
- Comparison set: Ingres graphite portraits, Hokusai sketches (both PD,
  plentiful).
- **Null drawings**, generated, same stroke-length distribution: Gaussian
  random walks, shuffled-segment Matisse (real segments, wrong order), and
  axibridge's own `freehand` / `continue_strokes` output.
- **Ground truth with known strokes** (the key test asset): (a) synthetic —
  render known polylines and clothoid splines as ink at 600 dpi with width
  jitter and paper noise; (b) **physical** — plot known geometry on the
  AxiDraw with a fineliner, scan it, recover it. axibridge can produce its own
  calibration corpus; few style projects can.

### 1. Extraction: raster → strokes

- Pipeline: threshold (Sauvola) → `skeletonize` + `medial_axis` (width w(s)
  for free) → `sknw` graph → prune spurs < 2w → cluster junction nodes within
  w → pair branches by tangent continuity → re-centre through junctions →
  uniform arc-length resample → Gaussian-smoothed κ(s) at σ stated in mm
  (1–2 line widths), swept as a curvature scale space.
- Benchmark against Deep Sketch Vectorization (SIGGRAPH 2024, MIT,
  pretrained) for **topology only**.
- **Tests:**
  1. Synthetic round-trip: κ(s) recovered vs known, error below a set
     threshold at the chosen σ; segment-boundary recall on clothoid splines.
  2. Junction fixtures: X crossings must chain through, T junctions must not.
  3. Plotter round-trip: recovered strokes vs the plotted SVG (Fréchet
     distance, κ error).
  4. Resolution stability: same drawing at 3 scan resolutions → panel
     features stable within tolerance.
- **Gate:** κ recovery and X/T accuracy good enough on the ground truth that
  measured differences between artists exceed extraction error.

### 2. The measurement panel (the fingerprint)

Features, weighted toward what perception and Elgammal say matters:

- curvature extrema: height, sharpness, spacing; inflection rate; corner rate
- clothoid segment count, length and sharpness distributions (A's fit)
- stroke length, closure ratio, strokes per drawing, ink length per area
- endings: taper, hook, blob (from w(s)); junction behaviour: gaps,
  overshoots, retraces
- width profile w(s) — measured even though the plotter can't draw it

**Tests:**

1. Cross-validated classification per drawing: Matisse vs Ingres vs Hokusai.
2. **Matisse vs every null** must separate cleanly, or the feature is noise.
3. Per-feature ablation, to learn which features carry the hand.
4. Shuffled-segment null tests whether *order* matters (if it doesn't, the
   Markov layer in A is unnecessary).

**Gate:** clean separation from nulls and per-drawing discrimination near
Elgammal's ~80% without thickness. If geometry alone fails, rethink features
before generating anything.

### 3. Grammar (A) → first axibridge modules

- Markov chain over clothoid segment types + params, with BPL-style
  inter-stroke relations. Profile = small JSON.
- Two modules: a **restyle effect** (path in, same path redrawn in the hand —
  Kalnins' "base path + learned residual" recipe) and a **hand source**
  (generates new strokes). `continue_strokes` is the in-repo precedent: it
  already pools turning-angle n-grams from its own layer.
- **Tests:**
  1. Generated strokes scored by the stage-2 classifier — it should fail to
     separate them from real Matisse at better than a set margin.
  2. **Memorisation check:** nearest-neighbour distance from generated to
     training strokes stays above a floor (it must speak the language, not
     quote it).
  3. Usual module invariants: purity, closure, bounded params.
  4. Ian looks at plots. Statistics are necessary, not sufficient.

### 4. Codebook (B/C) as analysis

- κ-window dictionary / VQ codebook. Use sparseness (Hughes) as an extra
  panel feature, and the codebook as the shared alphabet for translation in
  stage 6.
- **Test:** does adding codebook features to the panel raise discrimination?
  If not, it stays a curiosity.

### 5. AI as scientist (D1, D2)

- **D1:** an LLM writes an axibridge generator in stage 3's primitives;
  ~20 iterations scored on panel distance; Ian reviews each generation.
  **Anti-Goodhart test:** fit on a subset of panel features, evaluate on held-
  out features — a program that only learned the fitness will fail the held-
  out ones.
- **D2 calibration before any use:** hidden names, randomised and swapped
  order, forced choice on cropped line patches — real vs procedural baseline,
  real vs Ingres. Cropping removes subject. Use only if it beats chance and
  stays position-consistent.

### 6. The bank and juxtaposition

- Bank = many profiles. Operations:
  1. **Code-switching** — hand A → hand B along arc length.
  2. **Translation** — map each segment/token of A to its nearest in B.
  3. **Structure from A, hand from B** (path vs hand split, literally).
  4. **Blending** — OT/Wasserstein between profile distributions
     (`IDEAS-pass4.md` C1/C2).
- `two_hands` already juxtaposes two parametric genomes; learned profiles
  could slot in as its genomes.
- Non-artist hands come cheap once the pipeline exists: plant contours,
  type skeletons, Ian's own hand via the draw tool (which also records
  timing — the one source with real speed).

## Ledger — overnight run 2026-10-16

Code in `tools/gesture/` (research only, own venv; see its README). Results
in `tools/gesture/results/` — read `review-2026-10-16.md` first.

- **Stage 0 — done.** Corpus: 31 Matisse (SMK), 27 Hokusai + 34 Ingres
  (Met), all PD; manifests in `docs/research/gesture-corpus/`. Synthetic
  ground truth (`synth.py`), four nulls + an identity control (`nulls.py`).
  Non-artist hands researched (`hands-to-collect.md`), nothing downloaded.
  Gallica blocked by a Cloudflare human check; physical plotter round-trip
  not done (needs Ian at the machine).
- **Stage 1 — gate met.** Six-way extraction bake-off; default is
  `extract_hybrid` (hysteresis-ink skeleton topology + sub-pixel
  core-of-profile refinement). GT κ error 0.72 → 0.09 (0.034 at the panel's
  own σ). Faint pencil (KKS18238) and dense small motifs remain weak.
- **Stage 2 — null half met; artist half met for printmaking medium.**
  Against a pipeline-matched control the four nulls separate at AUC
  0.92–0.999. Matisse's own etchings vs lithographs first separated at
  0.78–0.80 (medium, not hand). Remedy (`results/medium-invariance-2026-10-16.md`):
  σ ≥ 7 line widths + nullspace projection of the etching/litho directions
  takes that control to chance held-out (0.44 linear, 0.61 forest probe)
  while artists still separate (0.83 / 0.79, chance 0.33; Matisse vs Hokusai
  0.90–0.93, vs Ingres 0.88–0.89). This is now the **standard
  preprocessing** (`gesture/medium.py`, pairs in
  `docs/research/gesture-corpus/medium-pairs.csv`); v4 with it: control
  0.41 (linear) / 0.60 (forest), artists 0.81 / 0.79, nulls vs identity
  0.82–0.99 (`results/discriminate-real-v4-standard.md`). Brush/graphite
  invariance is still unshown — needs a within-hand comparison across those
  media.
- **Stage 3 — preview only.** `grammar.py` learns, generates, code-switches,
  translates, restyles. At σ = 0.01·ref ~90% of strokes fit as one segment,
  so order is barely modelled; drawings have no composition. Not a result.
- **Representation note:** clothoid fitter (`clothoid.py`) — DP seeding,
  continuous κ spline, line/arc/clothoid labels. Scan-stroke blow-ups
  (corner angles ~1e6 rad from unregularised pieces) fixed at the end of the
  run: 5,758 → 0 over 48k fits. The grammar's guard filters can be relaxed.

## Open decisions (flagged, not settled)

- **Where a profile lives.** Repo survey: corpus fits the gallery, a learned
  profile fits a project asset (JSON decoder; `gencache` invalidation for
  free), curated hands fit module-library presets — but presets drop asset
  params. Decide at stage 3, not before.
- **Where research code lives** and whether `scikit-image` / `sknw` enter
  `pyproject.toml` — probably an optional extra (like `[fast]`) so the Pi
  never needs them.
- **The thickness gap.** The strongest measured cue can't be plotted
  directly. Options: drop it, map it to pen choice per stroke, or render width
  as offset/multi-pass lines (`fat_tube`). Leave open until stage 2 says how
  much it matters.

## Deliberately not in this pass

- Training sketch-rnn / diffusion models on a few hundred drawings.
- Recovering global stroke order from scans.
- Painterly (brush) hands — Oehlen stays a juxtaposition partner, not a
  corpus.

## References

- Elgammal, Kang, Den Leeuw, *Picasso, Matisse, or a Fake?* AAAI 2018 — https://arxiv.org/abs/1711.03536
- McCrae & Singh, *Sketching piecewise clothoid curves*, SBIM 2008 — https://www.dgp.toronto.edu/~karan/papers/sbim2008mccrae.pdf
- Baran, Lehtinen, Popović, *Sketching Clothoid Splines Using Shortest Paths*, CGF 2010 — https://homes.cs.washington.edu/~jovan/papers/baran-2010-scs.pdf
- Lake, Salakhutdinov, Tenenbaum, BPL, Science 2015 (supplement) — https://cims.nyu.edu/~brenden/papers/LakeEtAl2015Science_supp.pdf
- Hughes, Graham, Rockmore, PNAS 2010 — https://pmc.ncbi.nlm.nih.gov/articles/PMC2824352
- Jones-Smith & Mathur, Nature 2006 (Pollock fractals revisited) — https://www.nature.com/articles/nature05398
- Kalnins et al., *WYSIWYG NPR*, SIGGRAPH 2002 — https://gfx.cs.princeton.edu/pubs/Kalnins_2002_WND/wnpr-final.pdf
- Mokhtarian & Mackworth, curvature scale space — https://www.cs.ubc.ca/tr/1989/tr-89-14
- Bessmeltsev & Solomon, PolyVector Fields, TOG 2019 — https://arxiv.org/abs/1801.01922
- Yan et al., Deep Sketch Vectorization, SIGGRAPH 2024 — https://github.com/Nauhcnay/Deep-Sketch-Vectorization
- Ha & Eck, sketch-rnn — https://arxiv.org/abs/1704.03477 (data floor: https://github.com/magenta/magenta/blob/main/magenta/models/sketch_rnn/README.md)
- SketchAgent, CVPR 2025 — https://arxiv.org/abs/2411.17673
- MLLM-as-a-Judge, ICML 2024 — https://arxiv.org/abs/2402.04788
- Ellis et al., graphics programs from hand-drawn images — https://arxiv.org/abs/1707.09627
- SMK open API — https://api.smk.dk/api/v1/art/search/ · BnF Matisse — https://www.bnf.fr/fr/loeuvre-de-matisse-la-portee-de-tous
- ARS on Matisse US rights — https://arsny.com/blog/kahlo-matisse-public-domain/
