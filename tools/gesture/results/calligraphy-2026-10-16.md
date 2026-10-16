# Calligraphy and Arabic print as hands — 2026-10-16

Research round on the harvested calligraphy scans (33 files plus the
Baghdadi PDF) and the Arabic print set (Bulaq/European letterpress scans and
OFL fonts). Code: `gesture/broadnib.py` (nib width model, rendering
options), `gesture/calligraphy.py` (manifests, policy gate, sheet crops/ink
modes, outline view, neutral font shaping),
`experiments/calligraphy_study.py` (stages `extract outline fonts synth nib
render panel generate`), `tests/test_broadnib.py` (11 tests, about 2.5 s).
Per-run outputs: `.local/gesture/out/calligraphy/`.

Figures: `calligraphy-extraction.jpg` (centreline overlays, every sheet),
`calligraphy-nib.jpg` (width against direction for the best sheet per genre,
plus per-stroke φ histograms), `calligraphy-render.jpg` (thickness-gap
options), `calligraphy-generate.jpg` (shikasta line studies).

**Angle convention.** φ is the page angle of the nib *edge*,
counter-clockwise from the rightward horizontal as the sheet is seen. The
thickest strokes run at φ + 90°. Width units are each sheet's median stroke
width.

## 1. Extraction per genre

The default `extract_hybrid` settings fail on broad-nib ribbons. The local
paper level is a box mean over 1.5 % of the diagonal, a window that fits
*inside* a reed-pen downstroke, so the extractor reads the stroke as paper.
The hysteresis noise model also assumes sparse lines, while calligraphy
covers 10–35 % of a panel. On wc-12 the defaults kept only the illumination
hairlines and every letter vanished. The calligraphy settings
(`calligraphy.EXTRACT_DEFAULTS`) are:

- global **Otsu** on an ink-mode grey;
- paper window 8 %;
- spur cut 2.5 w;
- no plate or frame logic.

Ink modes:

- `black` = max(R,G,B) + chroma. Gold, red and blue go to paper and black
  ink stays dark.
- `lum` for blue or red ink (tughras, the red maghribi page).
- `white` = 1 − min(R,G,B) for light ink on a dark ground (wc-39).

Every sheet has a hand-picked crop, chosen from gridded thumbnails. A
ruling eraser removes long, thin, *isolated* straight lines. The isolation
test matters: without it the eraser also cut a slice out of a long kashida.
I checked numerically that centrelines sit on the ink ridge (EDT at the
points 8.2 against a local maximum of 9.8 px; distance to the mask skeleton
0.5 px). The overlays appear to show the lines hugging the top edge of
strokes, but that is a drawing artefact.

| # | genre (sheets) | verdict |
|---|---|---|
| 1 | nasta'liq (10) | Good on the plain exercise and album sheets (met-716305/716307, wal-W668-66b/74b). Topology breaks at T-joins in thick strokes and leaves short zig-zags. wc-19 and wc-22 are small manuscript text with illumination, so they are noisy. met-716304's gold-ground panel gives only 26 strokes. |
| 2 | shikasta (7) | wc-12/wc-13 (large letters in cloud bands): letters are clean, but the illumination outlines between the clouds come out as hairline strokes (`pen_strokes` drops them by width). wc-15/wc-17 are fine. wc-10 has gold cloud bands, which work only partly. met-716315 (pale ink on a decorated ground) fails. |
| 3 | diwani (2) | wc-05 is good after chroma; the gold dots disappear. wc-39 (white ink) works with the `white` mode. |
| 4 | naskh MSS (2) | Readable. Strokes are short and dense (median 7–9 w long). Red rubrics drop out in `black` mode. |
| 5 | karalama (2) | Extracts, but the overwritten exercise gives a dense tangle of short strokes. |
| 6 | maghribi (3) | Clean. wc-32 (red ink) needs `lum`. |
| 7 | kufic (3) | wc-35 (grid drawing) and wc-37 (cells) are clean. The met-451802 bowl fails: the rim and the bowl's own shading dominate. |
| 8 | tughra (2) | Long loops extract with `lum`, but the gold and blue fill patterns add hundreds of fragments. |
| 9 | ghubar (1) | Micro-script reads as texture only, as expected. |
| 10 | **Baghdadi PDF** | The NYU low-res PDF holds about 1140 × 820 px JPEGs (96 ppi). I took them natively with `pdfimages`, with `pdftoppm` as fallback (`calligraphy.render_pdf_page`). Plates 5, 8, 20 and 48 extract cleanly at w ≈ 3–5 px, which is coarse but usable. |
| 11 | print (28 pages) | Body text is sparse and thin, so the *default* hysteresis is the right choice here; Otsu read a faint page's shading as ink. Two pages were unusable: AL09 p0067 and p0351 are near-blank with show-through, and AL08 p0024's JP2 is corrupt on disk. |

**Outline view** (`calligraphy.outlines`): closed contours of the same ink
mask, with counters marked. One part-of-word gives one closed contour, so
this view suits Ian's contiguous-lines direction. The ribbon's geometry
lives here: the centreline loses the wedge terminals and the thick/thin
silhouette, and the outline keeps both.

## 2. Broad-nib width model (`broadnib.py`)

The model is width(θ) = W·|sin(θ − φ)| + w_min, a Minkowski sweep of a
segment plus a disc. The fit runs a φ grid with closed-form non-negative W
and w_min, then Huber IRLS. Each fit also reports a θ-permutation null R²
and the angular span.

**Synthetic validation** (`synth` stage: 21 scenes, known φ/W/w0, rendered,
then extracted, then fitted):

- **φ error: median 0.4°.** 18 of 21 scenes recover W to within about 10 %
  (W is biased slightly low and w_min high, by about 0.5 px, from
  anti-aliasing). R² is 0.98–0.997 against a null of ≤ 0.03.
- **The 3 failures are all the widest nib** (W = 24 px on curves with
  ≈ 70 px radius). There the ribbon folds over itself and the extractor
  splits it (φ error 26° at φ = 0).
- The ground-truth-centreline control recovers all 21. The breakdown is the
  extractor on self-overlapping ribbons, not the model.
- **Nib twist** of 20° and 40° along a stroke still gives φ to within
  1.5°, but W drops 20–30 % and w_min grows. Added noise (σ = 0.08) changes
  nothing.

**Fitted nib angles** (`nib_summary.json`, `nib_fits.json`). Sheet R² is
the pooled fit. "Per-stroke" fits run on strokes with enough angular span.

| # | group | sheets | page φ (sheets) | sheet R² median | per-stroke φ spread | note |
|---|---|---|---|---|---|---|
| 1 | Amiri (font) | 6 | **77°** (76–78) | **0.82** | 4° | the type *does* encode a nib |
| 2 | Amiri Typewriter | 6 | 77° | 0.74 | 8° | same nib, flatter contrast (0.45 vs 0.66) |
| 3 | Aref Ruqaa | 6 | 71° (66–76) | 0.68 | — | nib kept |
| 4 | Noto Kufi (control) | 6 | 17° (scattered) | 0.43 | — | contrast 0.14: near-monoline, as expected |
| 5 | Baghdadi plates | 4 | **75–80°** on plates 5/8 | 0.69–0.71 (pl. 5/8) | 4–5° | the cleanest scans of the round |
| 6 | naskh MSS | 2 | 71°, 92° | 0.14 | 16–35° | small script, extractor-limited |
| 7 | shikasta | 7 | 17–111° | 0.19 (0.53 on wc-12/13) | 10–25° | page φ mixes the sheets' diagonal baselines |
| 8 | nasta'liq | 10 | 14–123° | 0.25 (0.45–0.62 best) | 8–40° | qit'a lines are written diagonally |
| 9 | diwani | 2 | 70°, 87° | 0.13 | 21–35° | thin chancery hand, low contrast |
| 10 | maghribi | 3 | 57–96° | **0.42** | 5–22° | contrast 0.45: higher than the "near-monoline" prior |
| 11 | karalama | 2 | 170–173° | 0.34 | 24–38° | rotated exercise panels |
| 12 | Kufic | 3 | — | 0.08 | — | constant width; no direction dependence |
| 13 | Bulaq print AL08/AL09 | 16 | 96–122° | **0.06–0.08** | 30–40° | the nib is not resolvable at w ≈ 7 px of letterpress |

What these numbers support:

- **Within a sheet, the nib is real and consistent.** The null R² is 0.000
  everywhere, and the cleanest sheets give per-stroke φ spreads of 4–15°
  (Amiri 4°, Baghdadi pl. 8 4°, met-716307 8°, wc-13 10°).
- **Across sheets the page angle is not a genre signature.** Album
  nasta'liq and shikasta are written along diagonal baselines, and siyah
  mashq panels are rotated. A baseline proxy (the length-weighted mode of
  stroke direction, `calligraphy.dominant_direction`) brings shikasta into
  agreement: φ relative to the baseline is 20 ± 12°, R̄ 0.88 (raw page R̄
  0.60). The proxy fails wherever vertical alifs or Kufic cells dominate.
  Comparing angles between genres needs a real baseline estimator, such as
  a line-direction fit of the ink.
- **Horizontal-baseline material agrees:** Amiri 77°, Baghdadi 75–80°,
  naskh 71°, Aref Ruqaa 71°. With horizontals thick and verticals thin,
  this is the naskh-family nib held at about 10–20° from the vertical.
  Classical prescriptions are not source-checked here (†).
- Real sheets fit far worse than synthetic or font material: R² 0.2–0.6
  against 0.98 and 0.82. Pressure, twist, ink pooling and extractor widths
  at T-joins account for the rest. Maghribi is *not* monoline in these
  scans (contrast about 0.45).

**Does the type encode the nib?** Yes. Amiri gives a single clean |sin|
(R² 0.82, φ 77°, every page within 2°). It matches the Baghdadi model book
to within a few degrees. Noto Kufi is the monoline control.

## 3. Rendering width with a constant-width plotter (the thickness gap — options, not settled)

All three options were tested at plotter scale (10 px/mm, 0.35 mm pen, nib
3 mm and 1.5 mm, `render_options.json`):

| # | option | paths | pen-down length | IoU with ribbon | character |
|---|---|---|---|---|---|
| a | **nib outline** (swept-nib envelope as closed contours) | 1–2 per ribbon | 0.17–0.31 m | 0.16–0.31 (an outline, not a fill: the silhouette is exact) | contiguous; reads as a drawn ribbon; thick/thin comes from the gap between the two edges; hairlines collapse into one line |
| b | concentric inset fill | 6–23 | 0.22–1.05 m (2–3.5× a) | **0.86–0.97** | contiguous closed rings; reads as solid ink; **breaks wherever the ribbon is thinner than one pen** (gaps at hairlines) |
| c | multipass centreline offsets | 7–34 | 0.15–0.90 m | 0.64–0.86 | many pen lifts; strands start and stop where the width crosses pen multiples, so it looks stepped; worst on both counts |

**Recommendation for Ian's decision:** make (a) the default for line
studies. It is the only option that stays one contiguous line per ribbon,
costs the least ink and time, and needs no hatching. Offer (b) as an opt-in
"solid" look, after fixing its hairline gaps (fall back to the outline
where the inset vanishes). Drop (c), which is effectively `fat_tube` with
the same stepped look. This bears on the open "thickness gap" item in
`docs/IDEAS-gesture-bank.md`. Calligraphy is the case where (a) earns its
place, but the decision is left open.

## 4. Hand statistics — where the new hands sit

The panel was run on 180 drawings: the artists (hybrid extracts) plus every
group here. It used standard preprocessing (σ ≥ 7 w plus the Matisse medium
projection) and also raw. The method is logistic regression with repeated
stratified CV pairwise AUCs. **Samples are small:** 2–10 sheets per
calligraphy genre. Groups with fewer than 3 sheets (diwani, naskh,
karalama, tughra, ghubar) are excluded from the AUCs, and every
calligraphy number below has wide uncertainty.

| # | pair (standard, geometry only) | AUC |
|---|---|---|
| 1 | shikasta vs Matisse / Hokusai / Ingres | 0.87 / 0.84 / 0.90 |
| 2 | nasta'liq vs Matisse / Hokusai / Ingres | 0.96 / **0.81** / 0.97 |
| 3 | **shikasta vs nasta'liq** | **0.49** (0.69 raw) |
| 4 | maghribi vs nasta'liq / shikasta | 0.77 / 0.84 |
| 5 | Baghdadi plates vs shikasta / nasta'liq | 0.87 / 0.79 |
| 6 | Kufic vs everything | 0.96–1.0 |
| 7 | (reference) Hokusai vs Matisse | 0.85 |

What the table supports:

- The cursive calligraphy hands sit **closer to Hokusai** than to Matisse or
  Ingres: the brush is the nearest drawing medium.
- **Shikasta and nasta'liq are not separable** at panel scale. That fits
  shikasta being "broken nasta'liq", but the σ ≥ 7 w floor is coarse for
  ribbon hands: σ spans a large part of a letter.
- **Adding width helps:** shikasta against the artists rises to
  0.95–0.97. Kufic separates from everything, which is the geometric pole
  as predicted.

**Print vs font (Bulaq 1905 type vs its Amiri revival): negative result.**
Amiri renders separate from Bulaq pages at AUC 1.0, but the effect sizes
show why: line width relative to the page, stroke count, length quantiles
and near-touch rate. Those are *page layout and content*: 6 lines of
neutral drills against a full page of text. They are not print texture.
Two books set in the same 1905 type (AL08 vs AL09) also separate at 0.94.

A band-limited edge-texture measure (outline residual between 0.15 w and
0.6 w smoothing, on low-curvature runs) does not isolate print either. It
gives Amiri 0.072 w RMS against Bulaq 0.053 w; the font is "rougher"
because of polygon flattening and anti-aliasing at w ≈ 6–7 px. At this scan
resolution (about 7 px line width) print texture is below the pixel. The
test needs:

1. registered blob-level comparison against the matching Amiri glyph, as
   typography.md §4.4 proposes;
2. scans with w ≥ 15 px;
3. finer outline flattening.

## 5. Generative glimpse (policy-gated)

The `generate` stage keeps only shikasta sheets whose `content_type` is in
{exercise, poetry, document} with nothing marked "verify". That leaves
**wc-12, wc-13 (siyah mashq exercise) and wc-15 (petition document)**. It
excluded met-450714, met-716315, wc-10 and wc-17 (album pages). The
`require_generative` gate raises on anything else.

`pen_strokes` removes illumination hairlines and frame remnants (kept
44/250, 43/116 and 645/692 strokes). The frozen grammar v6 was then learned
at `min_len_w = 12` (226 training strokes). Rendering used the
best-fitting training sheet's nib (wc-15: φ 60°, R² 0.56, contrast 0.63)
with option (a). The memorisation check gives a nearest-training distance
median of 0.118.

Honest look (`calligraphy-generate.jpg`):

1. **Single-line mode looks like a coastline, not a hand.** Shikasta's
   extracted strokes are short (median 7–12 w) and corner-rich because
   parts-of-words break at every lift and join. The chain therefore stitches
   many corners. The sweep, the hand's best feature, is diluted.
2. **Contiguous mode is better.** Sheet 2 has long sweeping arcs with hooks
   that read as "after a reed pen". Sheet 3 scatters short hooks and ticks
   across the page.
3. **Thick/thin is mild.** The fitted contrast of the best-fitting sheet is
   only 0.63. The sheets with stronger contrast (wc-12/13) fit less well
   once hairlines are removed.
4. **Legibility.** No words appear. Some *isolated* hooks resemble single
   letter shapes (a ر/د-like hook, a ل-like curve), most of all in the
   scatter sheet. Under the policy these are exactly what the E3 reader
   check must catch before any public showing, and no automated check
   exists. Generation draws only from the line statistics, as the policy
   requires, but short hooks are letter-scale by construction.
5. **Framing.** These are "line studies after the shikasta hand", not
   calligraphy.

## 6. Policy compliance

- `calligraphy.generative_allowed` treats only {exercise, poetry, document}
  as generative, and anything with "verif" in `content_type` or `note` is
  restricted. Under this rule the Baghdadi book is measure-only, because
  its manifest note flags unverified religious phrases (plate 45, a
  Qur'anic thuluth composition, was only viewed while picking plates). wc-37, met-451802,
  every album and manuscript page, all print items and all fonts are also
  measure-only.
- Tests cover the filter, the real manifests and the raising gate.
- Measure-only material appears only in statistics, the extraction report
  and nib fits. It never reaches `learn`.
- Fonts were shaped (uharfbuzz 0.56.3, installed into the research venv
  only) from `NEUTRAL_STRINGS`: single-letter repetition drills and spaced
  isolated letters. The strings are checked by `neutral_string_ok`, which
  blacklists الله/لله, the U+FDF2/FDFA/FDFB/FDFD ligatures and any lam–heh
  sequence, and requires every word to be one repeated letter.
- No legible text was produced. Overlay JPEGs of the scans stay in
  `.local/`. The result figures show extraction overlays of the source
  sheets, which is research documentation and not output.

## 7. Recommendations

1. **Extraction:** keep `calligraphy.EXTRACT_DEFAULTS` (Otsu + wide paper
   window) for ribbon hands and the default hysteresis for print. Next, add
   a width-aware junction model: thick T-joins zig-zag today.
2. **Nib:** the model works (synthetic error 0.4°; the font clearly encodes
   a nib). Before comparing genres, build a real baseline-direction
   estimator, and fit φ per text line, not per sheet.
3. **Thickness gap:** propose (a) nib outline as the plotter rendering of
   width, with (b) as an opt-in. Ian decides.
4. **Grammar for ribbon hands:** learn from *outline contours* or from
   parts-of-words joined across lifts. Otherwise the short strokes of
   cursive scripts make the chain corner-bound. Fit at σ in nib widths.
5. **Print texture:** do the registered Amiri-vs-Bulaq blob experiment on
   higher-resolution scans. The panel as it stands only hears layout.
6. Run the E3 reader check before showing any generated sheet; a
   letter-scale-hook detector could pre-filter.
