# Wet, irregular mass edges from data — 2026-10-16 (round 7)

This picks up open problems 2–4 and 6 of `regime-2026-10-16.md`: the mass
outlines are perfect sweeps, beads carry a white rim around a pooled core,
drips are too regular, pulses read as capsules on a string, and masses are
expensive. Direction: `docs/IDEAS-gesture-bank.md`, "three regimes", plus
the lead's note from "What Oehlen's trees teach the regimes work" (a
scalloped or notched mass edge as a rhythmic edge event).

Code:
- `gesture/regime.py`: the edge process, `WET_PROFILES`, the rim fix, the
  scallop and notch events, spiral fill, new drips and hairs, `rim_gap`, and
  a `nib_renderer` hook. The public interface is unchanged: every new
  argument has a default, and with the defaults the output is round 6's
  apart from the rim fix and the new drips and hairs.
- `experiments/regime_study.py`, stages `edges masses sources masstree grammarwet`.
- `tests/test_regime.py`: 35 tests (15 new), about 12 s.

Raw outputs: `.local/gesture/out/regime_masses/`
- `edges_rows.json` (one row per mass), `edges_summary.json`;
- `catalogue_costs.json`;
- `regime_r6.py`, a frozen copy of round 6's renderer for the "before"
  columns.

Sheets: `regime-masses-catalogue.jpg`, `-sources.jpg`, `-tree.jpg`,
`-grammar.jpg`. Pen 0.35 mm.

## 1. Measurement

**Sources, all measured.**
- Ian's reference image.
- 12 Brice Marden sheets.
- 26 Hokusai sheets (scaled to 2400 px).
- All 31 calligraphy sheets, cropped as in `calligraphy.SHEETS`; the
  Baghdadi PDF is skipped.
- The calligraphy *generator* profile uses only the 13 generative-allowed
  sheets: `generative_allowed`, then `require_generative` over the ids.

**Mask.**
- A 0.8 px blur, then the background is normalised with a large grey
  closing, then Otsu.
- The line width w is the median of 2·EDT on the skeleton.

**What counts as a mass.**
- A component of the mask after opening with a disc of 0.9 w (this
  removes lines).
- It must contain a pixel deeper than 1.5 w (Marden: 1.0 w, because his
  pools are only 2–3 line widths across).
- Its equivalent diameter D = √(4A/π) must be ≥ 24 px.
- It must not touch the border.

**Per mass**, all in units of D:
- **Edge spectrum.** The sub-pixel contour is resampled to 1024 points. The
  deviation δ(s) is taken from the outline smoothed at σ = 0.25 D along the
  arc. Its RMS is reported per octave band of cycles per D, with the
  smoothing's high-pass corrected for. Bands above D / (5 px) are dropped.
- **Shape.** Skew and kurtosis of δ, lobes, solidity, and **edge bays**:
  hull pockets deeper than 0.06 D that the smoothed core outline does not
  have.
- **Anisotropy.** RMS at the ends ÷ RMS at the sides, relative to the
  major axis.
- **Pooling.** The ink-darkness centroid offset; the width ratio of the
  heavy end third to the light one; whether the heavy end is the lower one.
- **Thin exits.** Thin ink leaving the mass within 0.6 D: count, width
  (in units of w), and how far out it reaches.
- **Fine edge vs line edge.** δ against a σ = 1 w smoothing, in units of w,
  measured on masses and on long thin-line contours.

**Floor:** rasterised 1.6:1 ellipses measure, in units of D, 0.054 in the
0.5–1 band (shape leakage), 0.003–0.005 in 1–2, and ≤ 0.003 in 2–4.

### 1.1 Results (median, IQR in brackets)

| # | source | masses / sheets | D / w | elong | edge RMS 1–2 | 2–4 | 4–8 cyc/D | skew of δ | edge bays | heavy-end ratio | heavy end lower | exits / mass | exit length (D) | fine edge, mass vs line (w) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | reference | 27 / 1 | 10.1 | 2.0 | 0.027 | 0.0094 | 0.0036 | −0.18 | 1.6 | 1.25 | 50 % | 4 | 0.20 | 0.145 vs 0.185 |
| 2 | Marden | 221 / 12 | 5.4 | 2.3 | 0.026 | 0.0102 | 0.0040 | **−0.38** | **1.9** | 1.24 | 57 % | **6** | **0.29** | 0.190 vs 0.203 |
| 3 | Hokusai | 810 / 26 | 8.0 | 2.8 | 0.026 | 0.0102 | 0.0043 | +0.08 | 1.6 | **1.32** | 40 % | 5 | 0.17 | 0.166 vs 0.169 |
| 4 | calligraphy, all (measure) | 693 / 25 | 8.1 | 2.1 | 0.023 | 0.0080 | 0.0033 | −0.05 | 1.1 | 1.21 | 46 % | 3 | 0.18 | 0.143 vs 0.207 |
| 5 | calligraphy, generative only | 371 / 13 | 7.5 | 2.0 | 0.022 | 0.0078 | 0.0032 | −0.08 | 1.0 | 1.19 | 52 % | 3 | 0.19 | 0.133 vs 0.207 |

The edge RMS columns are in units of D. Further quantities:
- Total RMS: 0.042–0.051 D.
- Solidity: 0.78–0.87.
- Bay depth: median 0.15–0.18 D.
- Anisotropy: about 1.0, except Marden at 0.66, whose sides are rougher
  than his ends.

On compact masses only (solidity > 0.88, elongation < 2.5):
- The 0.5–1 band is 0.077–0.087 D (0.047 for calligraphy). Against the
  0.054 floor, that is a real **low-order lumpiness** of about 0.06 D.
- The 1–2 band is 0.020–0.023 D.
- Skew is −0.44 for the reference, **−0.8 for Marden**, −0.25 for Hokusai
  and −0.19 for calligraphy.

### 1.2 What the numbers say (honest reading)

1. **The edge spectrum is nearly universal.**
   - Above 1 cycle/D the four sources agree within about 20 %: 0.022–0.027
     at 1–2, about 0.008–0.010 at 2–4 and about 0.003–0.004 at 4–8 cycles/D.
   - Amplitude falls by about 2.6× per octave (a red spectrum).
   - What separates the sources is the *shape statistics*, not the
     roughness:
     - Marden: cusped bays (negative skew), more exits, longer exits, rough
       sides;
     - Hokusai: elongated masses with heavy ends;
     - calligraphy: crisp masses, fewer bays.
2. **"Wet" is low-order, not jitter.**
   - A smooth *stadium* rendered and measured through the same raster path
     already shows about 0.019 / 0.012 / 0.008 D in the 1–2 / 2–4 / 4–8
     bands. The data barely exceed that.
   - What does exceed the smooth sweep is lumpiness at harmonics 2–3 of the
     whole outline, a sharper inward than outward profile (rounded lobes,
     cusped bays), and roughly one bay per mass.
3. **At the line's own scale, mass edges are not rougher than line edges.**
   - Fine-edge RMS of masses is 0.13–0.19 w, against 0.17–0.21 w for lines.
   - Calligraphy masses are clearly *smoother* than its line edges.
   - So a wet mass is not a "trembling" mass; tremor stays a line property.
4. **Pooling has no gravity direction.**
   - The heavy end is the lower one in 40–57 % of masses.
   - The darkness centroid offset is < 0.013 D: scans saturate, so ink
     density inside the mass is not measurable here.
   - The heavy-end ratio of 1.2–1.3 is real, but its direction (stroke end
     vs start) cannot be recovered from blobs. The model puts it at the
     stroke's end, by assumption.
5. **Dry-brush hairs cannot be separated from line exits** at scan
   resolution.
   - Thin exits are 0.45–0.7 w wide and number 3–6 per mass.
   - Most reach only 0.15–0.3 D within the 0.6 D window: short spurs and
     dry ends.
   - Drips were not measured at all; their parameters below are hand-set.

## 2. Model (`regime.py`)

**Edge process** (`wet=`), run on the unioned pen-centre outline before line
runs are clipped:
1. Each outline vertex is attributed to the centreline sample that
   *generates* it: argmax_j (H_j − |x − P_j|).
2. Its weight is `massness(r)` = smoothstep((r − 1.2)/0.6). The weight is
   min-filtered and smoothed along the ring, so it fades out before any
   line, nib or drip outline. Lines still enter a wet mass tangentially, and
   line and nib strokes are bit-identical with wet on (tested).
3. **Displacement** along the outward normal, in units of the local D_eq.
   D_eq is built from the local ink width and the massy run length, capped
   at 1.6 widths. The terms:
   - **coloured noise** with the per-band RMS of the profile. The lowest
     band is ring harmonics 2–3 (lobes of the whole mass); the rest are
     octaves per D.
   - a **negative-skew transform** x → (1 − e^(−a·x))/a: rounded lobes and
     cusped bays. a is 0.3 for calligraphy, 0.4 Hokusai, 0.6 reference and
     1.1 Marden.
   - Poisson **bays**: narrow Gaussian notches, at half the measured pocket
     depth, because measured pockets include the core shape's own
     concavities.
   - **end-third anisotropy**.
   - a **heavier pooled end** on elongated runs only.
4. **Clamps.** Inward moves are limited to 0.45 of the half-width and
   outward moves to 0.3 of the width. The polygon is repaired with
   `make_valid`.

**Variety.** Each mass draws its own parameters (`wet_params`):
- a log-normal multiplier on all bands, with sd 0.35–0.47 taken from the
  per-mass IQR;
- a per-band jitter;
- a Poisson bay count with log-normal depths;
- a randomised end ratio.

Seeds come from `seed=`, else `meta["seed"]`, else a hash of the geometry,
so output is deterministic.

**Calibration.**
- The raster closed loop is confounded: a smooth stadium already measures
  near the data. The generator is therefore checked on the polygon itself.
- A 9 mm oval measures 0.016 (calligraphy) and 0.027 D (reference) in the
  1–2 band, against 0.007 for the smooth sweep and 0.020–0.023 for compact
  data masses.
- That puts it within about 1.5× of the data; the reference profile is on
  the strong side.

**Profiles** (`WET_PROFILES`): `reference`, `marden`, `hokusai` and
`calligraphy` (generative sheets only). A dict with `base` and `gain`
overrides a profile.

**Edge events** (`edge=`, Oehlen's Baum 44 and 92):
- `{"mode": "scallop" | "notch", "count", "amp" (× local width), "extent"
  (stroke arc fraction), "side" (±1, page-left of travel), "jitter"}`.
- The event is placed on one side only, and the opposite half-plane is
  unchanged (tested).
- Scallops are round bumps with cusps between them; notches are V cuts.
- It combines with `wet` or runs alone, and works per stroke through
  `meta["edge"]`.

## 3. Artefact fixes

1. **White rim.** The graded fill looked up each inset vertex's *nearest*
   centreline sample. At a round mass's ends and shoulders that sample has
   r < 1.5, so f < 1, while the outline there is really the disc of a
   sample well inside. Using the generating sample (`_attribute`) instead
   removes the rim, and the pooled-from-centre grading in transitions is
   kept.
   - `rim_gap` (the widest white gap where the generating sample is a full
     mass) on the catalogue items:

     | item | round 6 (mm) | now (mm) |
     |---|---|---|
     | bead | 1.15 | 0.19 |
     | nib → mass | 1.17 | 0.19 |
     | drop | 1.05 | 0.24 |

   - Everything is ≤ 0.33 mm, below the 0.35 mm pen, dry and wet. This is
     tested on 4 marks × 2 settings.
   - This changes the default render (the requested fix), so every
     importer's beads and drops are now solid.
2. **Drips** are now shape-regime threads: r = 2, width carried by `mass`,
   fill = 1, so they are solid at any width, with no double ribbon.
   - A wet neck leaves at 0.15–0.4 of the mass's diameter and thins over
     12–50 % of the drip.
   - Length is log-normal (σ 0.5).
   - Each drip has a lean and a slow curvature walk.
   - 30 % get a hanging swelling and about 50 % a tip drop.
   - Wet edges are switched off on shed children (`meta["shed"]`), so drips
     stay clean threads.
3. **Hairs (dry exits)** have irregular roots, log-normal lengths and a
   random fan. Each is a wet wedge that dries into a pen line, and 35 % are
   broken into dashes (dry skips).
4. **Capsule pulses.** In `regime_study.profile_r("pulses")`, pulses now
   have irregular spacing, unequal heights and asymmetric profiles: a slow
   swell and an abrupt end, with 30 % reversed.
5. **Open clipped arcs at mass ends.** `fill_style="spiral"` chains each
   fill contour to the next one within 1.25 pen (rings rotated, arcs
   reversed). The graded U-arcs therefore become one meander instead of
   open hairpins. It is opt-in.
6. **`nib_renderer` hook.** It is called as
   `nib_renderer(strokes=, pen=, paths=, parts={"G","F","runs","rings","fill"})`
   and returns the paths, so `penrender.py` can replace the nib part.

## 4. Pen cost (catalogue, 0.35 mm pen; paths / pen-down mm)

| # | mark | round 6 | now, concentric | now, spiral |
|---|---|---|---|---|
| 1 | bead | 15 / 160 | 12 / 198 | 6 / 200 |
| 2 | nib → mass | 18 / 346 | 15 / 354 | 9 / 356 |
| 3 | line closes into a dot | 15 / 303 | 14 / 336 | 5 / 339 |
| 4 | vessel | 21 / 750 | 21 / 791 | 13 / 794 |
| 5 | big vertical mass | 18 / 969 | 23 / 1039 | 11 / 1043 |
| 6 | drips from a mass | 38 / 552 | 26 / 555 | 21 / 557 |
| 7 | tree (whole sheet) | 81 / 4562 | — | 82 / 4341 |

What the table shows:
- Filling to the edge and wet outlines cost **+2–24 % pen-down length**.
  The bead is the worst case, because its rim is now inked.
- The spiral fill cuts **pen lifts by 40–65 %** for less than 1 % extra
  length.
- The tree's lifts are dominated by its lines. Its pen length dropped
  because the new drips are shorter, solid threads.

Masses are still 15–45× the cost of a line per mm.

## 5. The sheets, looked at honestly

1. **`regime-masses-catalogue.jpg`** (before/after pairs, then the edge
   events):
   - The rim is gone everywhere: beads, drops and dots are solid. This is
     the clearest win.
   - Wet edges give masses irregular, kidney- and potato-like silhouettes
     with an occasional cusp. That reads as *organic*, not as noise.
   - Do they read as *wet*? Only partly.
     - The reference's wetness also comes from things the plotter cannot
       draw: pooled density inside the mass, dry streaks, soft bleed.
     - At 0.35 mm pen, the measured fine roughness (about 0.01 D) is
       below the pen on masses under about 10 mm.
     - What remains visible is lumpiness and bays.
   - The vertical mass reads irregular but not lush. An earlier version
     that counted the lowest band per D turned it into a caterpillar; it is
     now whole-ring lobes.
   - Drips are solid icicle necks with thin threads and occasional beads,
     much less mechanical than round 6's double ribbons.
   - Hairs are fewer, irregular and partly broken, which is better. They
     are still thin, single pen lines.
   - **The scallop run (Baum 44) reads immediately as a deliberate rhythmic
     event**: the strongest new sign on the sheet. The notch run (Baum 92)
     reads as teeth and is a little mechanical: square-ish at this amp.
2. **`regime-masses-sources.jpg`** (the same 4 shapes × 3 seeds per
   profile; row 1 is smooth):
   - The variety is real: no two masses match.
   - **The sources are hard to tell apart.** This matches the measurement:
     the spectra are near-universal. Marden's cusps and calligraphy's
     crispness are visible only side by side.
   - Some small ovals show tiny nicks that read as "cut", not wet.
3. **`regime-masses-tree.jpg`** (Strahler trunk, before/after):
   - The trunk gains irregular bulges, a pooled foot and one drip.
   - The scallop run on its side is too small to read at that scale; it
     needs amp ≥ 0.25 or a larger count.
   - The branches are unchanged, as intended: wet applies only where r ≥
     1.2.
4. **`regime-masses-grammar.jpg`** (grammar-v6 lines, wet on):
   - Pulses now come as unequal teardrops: still a chain in one cell, but
     no longer capsules.
   - "Through mass" swellings become irregular lenses.
   - Hokusai crescendos end in clubbed, lumpy drops: the best mass
     transitions here.

Nothing has been plotted or seen by Ian. The edge statistics are
measurements of scanned or generated images. The calibration is to within
about 1.5×.

## 6. Open problems

1. **Wetness the plotter can't draw.** The reference's masses read wet
   through internal density and dry streaks. Options:
   - bristle striations inside a mass, as Oehlen's brushed trunks. These are
     streamlines along the stroke, which is close to hatching, so this
     needs Ian's call against the "never hatching" rule.
   - a sparse "dry" fill that leaves pen-wide gaps along the stroke.
2. **Source identity is weak.** If sources should look different, it will
   have to come from shape statistics (elongation, end ratio, cusp skew,
   exit count), not edge roughness.
3. **Wet is opt-in.** `signs.py` and `regime_field` must pass `wet=`
   (or set `meta["wet"]`) to get it. `fill_style="spiral"` is a safe default
   candidate, but it changes everyone's path lists. These are the lead's
   decisions.
4. **Drip parameters are hand-set.** Drips were not measured; the
   reference's drips would need a dedicated vertical-thread detector.
5. **The edge-bay measure is noisy.** A smooth stadium scores about 1 bay,
   so the "about one bay per mass" figure is at the measure's own floor.

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
$P -m experiments.regime_study edges        # measurement, 3 workers, ~3 min
$P -m experiments.regime_study masses sources masstree grammarwet   # sheets, ~1.5 min
$P -m pytest -q tests/test_regime.py        # 35 tests, ~12 s
```
