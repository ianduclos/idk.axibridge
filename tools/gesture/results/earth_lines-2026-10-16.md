# Earth and physics lines: structure and a data-born regime field (2026-10-16, round 8)

Code:
- `gesture/earth_lines.py`: GRWL shapefile and DBF parsed by hand (no pyshp
  or GDAL in the venv), river windows with width per vertex, scan extraction,
  hosts from contacts, and data-born fields.
- `experiments/earth_lines.py`: subcommands `extract`, `zoom`, `structures`,
  `sheets`, `panel` and `analyse`. Run it from `tools/gesture`.
- `tests/test_earth_lines.py`: 6 tests, about 3 s.

Raw outputs are in `.local/gesture/out/earth_lines/`: Drawings, `structures.json`,
`sheets*.jsonl`, `panel_feats.json` and `panel_report.json`. Nothing was
downloaded and nothing was plotted.

## Images (look at these)

| # | file | shows |
|---|---|---|
| 1 | `earth_lines-structures.jpg` | 4 structures. Columns: raw at width → the regime the **data** gives each point → preset Strahler → preset trunk. Black = wire, blue = nib, red = mass |
| 2 | `earth_lines-hands-lichtenberg-01.jpg` | **the best sheet.** The data field in Hokusai, Matisse and shikasta hands, then the Strahler and trunk presets |
| 3 | `earth_lines-hands-bc-14.jpg` | bubble chamber: curl field against the presets |
| 4 | `earth_lines-hands-ucayali-maranon.jpg`, `-purus.jpg` | Amazon networks, channel-width field |
| 5 | `earth_lines-panel.jpg` | limb: the physics lines placed on the human-hand map (LDA fitted on humans only) |

## 1. Structures

- **Amazon (GRWL).** The 30 m vertices of each segment ID are chained into
  strokes. They are smoothed at 1.5 channel widths, because the 30 m pixel
  staircase is not the river. Each vertex keeps its width.
  - 8 windows were made. Two are used on sheets:
    - Ucayali–Marañón confluence: 56 lines, width q10/50/90 = 39/85/1025 m.
    - Purus meanders: 41 lines.
  - Junctions are not snapped. GRWL breaks segments at confluences, and
    `with_hosts` joins them by endpoint contact.
- **Scans.** These go through `extract_hybrid`. Bright-on-dark scans are
  inverted; coloured glow uses max-RGB.
  - Usable: Lichtenberg-01 (acrylic tree, 80 lines after pruning), bc-14
    (spirals plus a vertical beam fan), bc-03/04/06/07/10/11, lightning-01/02/06,
    Lichtenberg-05, slime trails, insect-02 (leaf mine) and insect-03
    (bark-beetle comb).
  - Duds:
    - Lichtenberg-02, the dense planar fractal: 0 strokes at 700 px and
      only twig fragments at 1400 px. The extractor treats a page that is
      mostly ink as background.
    - Lichtenberg-03 gave only the cylinder edges.
    - Lightning-07: the cloud glow swamps the bolt.
    - Helminthoida: relief on rock, 0 strokes.
  - bc-14 includes the physicists' handwritten track numbers, so a human
    hand is mixed into the "non-human" line.

## 2. Data-born field compared with the presets

Construction:
- `data_field` gives each sheet position the value at the **nearest
  structure point**. Restyled lines that drift a little therefore keep their
  data.
- The value maps through two soft levels to wire, nib and mass, and fades
  out more than 2 % of the sheet away from the structure.
- **River and Lichtenberg:** the levels are width quantiles (rivers 0.6/0.9,
  discharge 0.5/0.85).
- **Bubble chamber:** the levels are absolute radii of curvature: under 25 %
  of the sheet width is nib, under 8 % is mass. The κ smoothing is 1 % of
  the diagonal, because the tracks are dotted bubbles.

Numbers per structure: Spearman ρ between the data r and the preset r at
the same points, and the mean number of regime switches per line in the
composition (seed 3).

| # | structure | ρ vs Strahler | ρ vs trunk | switches/line, data field (Hok / Mat / shik) | Strahler | trunk |
|---|---|---|---|---|---|---|
| 1 | Ucayali–Marañón | 0.44 | 0.00 | 0.98 / 0.93 / 0.71 | 0.32 | 0.93 |
| 2 | Purus | 0.58 | 0.17 | 1.17 / 0.71 / 0.85 | 0.51 | 0.78 |
| 3 | Lichtenberg-01 | 0.34 | 0.04 | 1.44 / 1.32 / 1.41 | 0.54 | 0.54 |
| 4 | bc-14 | 0.21 | −0.01 | 0.62 / 0.59 / 0.70 | 0.70 | 1.21 |

The data fields are their own information. They are partly correlated
with Strahler and not at all with trunk. On trees and rivers they make a
line **change regime 2–3× more often** than Strahler does. It is the same
line that changes, not a different line.

What it looks like:

1. **Lichtenberg (the hit).** The trunk is one mass. It then breaks upward
   into dark knots at the branch junctions, where the discharge channel
   physically swelled. Those knots thin through nib into wire twigs. The
   result is a figure that becomes a mass and then dissolves along its own
   physics.
   - Strahler gives one short mass segment and a uniform nib canopy.
   - Trunk gives a bar.
   - This is the clearest "regimes become one another" so far that was
     not authored.
2. **Bubble chamber (sign-like, small).** Only the spiral and a few vertices
   pool: 0.7 % mass and 7 % nib by length. The spiral turns into an eye-like
   loop holding dark pods. The straight beam tracks stay wire.
   - The presets put masses on arbitrary straight beam tracks, so the
     trunk preset makes a meaningless bar.
   - The curl field puts marks **where something happened** (a particle
     slowed or curled up). That is the closest thing here to "signs that
     communicate something".
   - The beam fan itself is a parallel-line family, which borders on
     hatching. Filter it out (P4 in the research note) before any plot.
3. **Rivers (bead chains).**
   - Width puts the tributaries in wire and the wide main stems in nib or
     mass. Width changes along a stem (bars, islands, confluences), so the
     Marañón becomes a **string of pods joined by wire**.
   - It is honest to the data. It is also the "bead chain" look that round
     6 already flagged for the `axis` field. The pods are about the same
     size, so the chain reads as rhythmic rather than as one gesture.
   - Strahler and trunk give one solid trunk mass instead. On rivers the
     presets cohere more and the data is more eventful. That is a judgement
     call for Ian.
4. **Hands.** The difference between hands is again small at sheet scale, as
   in round 6. The field dominates. Shikasta gives the fewest switches on
   rivers.

## 3. Limb: the physics lines measured as hands

Method:
- The full panel, using geometry only (no `w_` or `end_` features: a
  river's width is not ink width). Standard preprocessing: σ ≥ 7 w, then
  the medium projection fitted on the artists' media.
- z-scores use the human spread.
- Rows: 31 Matisse, 27 Hokusai, 34 Ingres, 27 calligraphy (shikasta,
  nasta'liq, maghribi, Kufic, Baghdadi), plus 8 river windows, 7 bubble
  chamber, 5 discharge and 3 animal trails.

Pairwise AUC, logistic regression with CV. Lower means closer.

| # | physics class | Matisse | Hokusai | Ingres | calligraphy |
|---|---|---|---|---|---|
| 1 | river (8) | 1.00 | 1.00 | 1.00 | 1.00 |
| 2 | bubble (7) | 0.99 | 1.00 | 1.00 | 0.94 |
| 3 | discharge (5) | 0.92 | **0.79** | 0.93 | **0.65** |
| 4 | animal trails (3) | 0.95 | 0.92 | 1.00 | **0.71** |

For reference, Hokusai vs Matisse is 0.89.

- **There is a "non-human hand", and it is the river.** It sits about 3
  human-sd (RMS) from every human centroid and is 8 sd out on curvature
  density: `cl_corner_rate`, `k_q50` (κ·ref median 33, against 2–7.5 for
  humans) and `turn_tcorr`. A 200 km window holds hundreds of meanders, and
  no draughtsman packs curvature that densely.
- **Lightning, Lichtenberg and the animal trails sit nearest the cursive
  calligraphy.** They are also closest to Hokusai, the brush.
  - LDA fitted on humans assigns 4 of 5 discharge drawings, all 3 trails
    and 4 of 7 bubble frames to "calligraphy".
  - The shared traits are smoothness at σ ≥ 7 w (few corners, low κ median),
    few long strokes and a high top-length share.
  - Caveat: the σ floor is 7 × median width, and glow and grooves make
    "ink" wide, so these lines are measured coarsely. This is the same
    caveat the calligraphy note raises for ribbon hands.
  - Discharge vs animal is 0.28 and bubble vs animal 0.42 (n = 3–7). The
    physics classes do **not** separate from each other, so the panel hears
    "physics photo extraction" more than a family of physics.
- **Zoom test (what surprised me).**
  - Setup: the Purus at window half-widths of 0.4°, 0.2° and 0.1°.
  - Result: κ·ref median goes 33 → 11 → 3.8. The river falls **into the
    human band once the window holds only a few bends**.
  - So the river is a hand only at one scale. Its non-humanness is meander
    density, not the shape of a bend.
  - It still separates on length features. A window that small has 3–5
    strokes, so the evidence is thin; Ucayali at 0.1° was empty and was
    dropped.
  - Read the other way, a Langbein–Leopold bend is drawable. What no hand
    does is repeat it 200 times.

## 4. What failed

- Dense fractals (Lichtenberg-02) and dim relief (trace fossils) do not
  extract. Both need a dedicated extractor: ridge filtering, or thresholds
  for figures that are mostly ink.
- The Sentinel-2 crops, JRC transitions, Dente centrelines, oxbows and FDSN
  particle motion were not touched for lack of time.
- Bubble-frame extraction breaks the inner spiral turns into separate
  strokes, so the innermost "mass" is partly lost.

## 5. Next limb

1. **Braided river as a model of transitions.** GRWL's `nchannels` counts
   threads per vertex. Where it rises, one line becomes several and then
   one again. Use that as a *split/merge* operator in the regime grammar,
   which would be a fourth regime event beside swell and pool.
2. **Fit DBM (η) to Lichtenberg-01.** The fitted discharge generator would
   then give a structure plus a width field that cohere by construction,
   free and parametric.
3. **Use width variance, not width level, as the river field**, to kill
   the bead chain: pool only where width *jumps* (confluences, islands).

## Proposed changes to existing modules (not made)

1. `regime_field.compose`: accept a Drawing that carries per-point `r` in
   stroke meta, and bypass the spatial lookup. The nearest-point Field works,
   but a per-point regime is the natural carrier for data-born r(s).
2. `regime_field.structure_field`: add mode `"width"`, i.e.
   `earth_lines.data_field` on `width_values`. Extracted scans already
   carry widths.
3. `extract`: add a "mostly-ink" mode (polarity check on the ink fraction)
   for dense figures.
