# Gesture timing → line texture (round 8, 2026-10-16)

Files: `gesture/gesture_timing.py`, `experiments/gesture_timing.py`
(`measure | static | strips | sheet | limb`), `tests/test_gesture_timing.py`
(8 tests, about 1 s). Raw outputs are in `.local/gesture/out/gesture_timing/`
(`measure.json`, `measure_table.md`, `static.json`, `static_table.md`, `sheet.json`,
`strips.json`, `limb_zoom.jpg`).

**Images to look at:**

- `gesture_timing-sheet.jpg`: the same lines with regimes placed by preset spatial
  fields, compared with six dancers' timings.
- `gesture_timing-limb.jpg`: one shikasta line danced by subject 49, and the dance
  drawing itself.
- `gesture_timing-strips.jpg`: the diagnostic. Each dancer's speed record sits
  above one wavy line drawn at that tempo.

## What was built

- **Parsers.** A numpy-only BVH parser and an ASF/AMC parser with forward
  kinematics. CMU units are converted to cm. Bone lengths stay constant to
  1e-12 on real takes. Heads sit at 140 cm and toes at about 2 cm.
- **Dynamics of an end-effector trail.** Speed, acceleration, jerk and 3-D
  curvature are computed with explicit time smoothing (σ = 30 ms). Stillness is
  speed below max(8 % of p95, 2 cm/s) held for at least 120 ms.
- **The two-thirds power law.** It is fitted three ways: pooled, per movement
  unit (between speed minima), and on the "wall" plane that holds most of the
  horizontal motion. A null re-fits after shifting κ by half the take.
- **Static stand-ins for time.** Width is normalised per stroke and compared
  with |κ|. The broad-nib fold zone, terminals and junctions are excluded, as in
  `broadnib.width_samples`, so the fold artefact cannot fake a signal.
  Calligraphy is measured raw and again with a per-sheet nib fit divided out.
  The Arabic sets are measure-only.
- **The mapping: ink per unit TIME.**
  - The pen travels the line at the dancer's speed, rescaled so the whole line
    takes the dance window.
  - Every frame deposits the same ink, spread over σ = 0.6 nib.
  - ink/median = q. q ≤ 1 gives a dry line, then a nib ribbon. q ≥ 6 gives a
    mass whose diameter is ∝ √q, because area ∝ dwell.
  - The nib angle comes from the dancer's palm axis projected on the wall
    plane (BVH: index→pinky knuckles; CMU: thumb→fingers).
  - Tremor is the hand's own lateral high-pass residual.
  - Jerk peaks, weighted toward the jolt out of a stillness, become interior
    line events (`signs.apply_events`: comb / drip / knot / nib) at the
    burst's arc length.

## Numbers

**1. Dance obeys the two-thirds law, per movement unit.** The 3-D slope of
log v on log κ per unit, for the right hand:

| set | slope |
|---|---|
| CMU 05 | −0.39 |
| Stocos | −0.38 |
| E2-MB | −0.36 |
| CMU 55 mantis etc. | −0.29 |
| CMU 49 | −0.13 (slow fold-ins; few units) |

- R² is 0.6–0.7 per unit.
- The plane projection gives −0.26 to −0.32.
- The shifted-κ null gives −0.04 to +0.06.
- Pooled slopes are steeper (−0.44 to −0.51), because the gain factor changes
  between units.
- Guard against the known low-speed κ-noise artefact: on the faster half of
  samples only, the slopes are −0.27 to −0.37.
- Feet are steeper (−0.45 to −0.59) and still 40–70 % of the time.
- So **a slope near 1/3 is real in dance hands**. This is the timing the
  lognormal study (`lognormal-2026-10-16.md`) had to assume for static traces.

**2. Drawn lines carry no measurable dwell signal.** At the movement scale
(κ at σ = 4 widths):

- Matisse: Spearman ρ(width residual, κ) = +0.03, slope of log w on log κ =
  +0.004.
- Hokusai: ρ = +0.07, slope = +0.015.
- Ingres: ρ = +0.04, slope = +0.008.
- A dwell-inked line with v ∝ κ^(−1/3) would give a slope of about +1/3.
- Bends are only 1–4 % wider than straights.
- Shikasta, nasta'liq, naskh, diwani and maghribi give ρ −0.10 to +0.07,
  with or without the nib divided out.

At the fine scale ρ is +0.04 to +0.16, but **typeset print (AL04/08/09) shows
the same +0.14 to +0.16**. Print has no time, so the fine-scale signal is an
extraction artefact.

Stroke ends are slightly *thinner* (0.93–1.0×), with no terminal pooling. The
nib R² computed here (0.03–0.31) is lower than in the calligraphy study, because
widths were normalised per stroke rather than per sheet. That does not change ρ.

Conclusion: time is not recoverable from these widths. Any "thick where slow"
has to be imposed. The dance is the only real source of time in the corpus.

**3. Regime shares produced by timing (sheet, grammar/matisse lines).** Columns
are line / nib / mass:

| source | line | nib | mass |
|---|---|---|---|
| Fluidity | 85 % | 15 % | 0 % |
| Particles | 81 % | 18 % | 1 % |
| Mantis | 79 % | 21 % | 1 % |
| Staccato | 74 % | 23 % | 3 % |
| Levitation | 73 % | 19 % | 8 % |
| CMU 49 fold-in | 69 % | 17 % | 14 % |
| Preset 'noise' | 33 % | 31 % | 36 % |

## What it looks like

- **The presets give zones; timing gives events strung along the line.** A
  preset field makes territories where a whole stretch becomes mass. A dance
  makes beads, swellings and ticks *in order along the line*, spaced by the
  body's rhythm.
- **Each quality reads differently:**
  - Staccato: many small beads, evenly spaced.
  - Levitation: a few large pools after long suspensions.
  - Fluidity and Particles: almost all dry line, with jolt-ticks.
  - CMU 49's slow fold-in: long vessels, where the hand curls slowly at the
    end of the take.
- **Population, not one image.** These are different texture regimes from one
  mapping.

## Limb: "one shikasta line danced by subject 49", and the dance drawing itself

**What held:**

- Stillness → masses, timed by a body, on a calligraphic line. The masses come
  as *sequences*, not territories: 49's slow curl swells the line into one long
  vessel, and Staccato strings it with beads.
- **The dance drawing itself** is the surprise, in the bottom row of the limb
  sheet. The right-hand trail is projected on the wall and inked by its own
  timing and wrist. Romero's *Staccato* comes out as a knotted nest of loops,
  beaded wherever she held still. The beads are where the line *stops*, so they
  sit on the line's own turning points. It looks less like a drawing of a
  dancer than a sign system with its own punctuation.
- CMU 49_10 gives almost nothing: one long arc and a pool. That is a dud, kept
  as evidence.

**What failed:**

- **The wrist-held nib is invisible.** Columns 2 and 3 of row 1 differ only in
  who holds the nib, and look the same. The crops in `limb_zoom.jpg` confirm it.
- The width CV in nib zones is 0.43 for fixed and 0.44 for wrist.
- 49's palm axis spreads only 25° over the window; Staccato's spreads 62°. At a
  15 px nib, the |sin| law barely registers a 25° wander.
- The "braided" ribbon texture in both columns is probably the dancer's lateral
  jitter twisting thin ribbons. That is not confirmed.

## Next limb

1. **Make the wrist matter.** Use a wide nib (3–4× now) and Staccato or
   Particles, whose wrists rotate 60°+. Also try the *rate* of wrist roll: a
   twisting wrist flips a ribbon thick→thin, which a fixed nib cannot do.
2. **Duets.** Two dancers' timings on two lines that cross. The beads of one
   could respond to the stillness of the other (E2 duet data is not on disk).
3. **Pause grammar.** Pause duration and inter-pause interval distributions per
   movement quality, as a learned rhythm model that generates *new* timings,
   instead of replaying a take.

## Proposed changes to existing modules

None are required. Optional changes:

1. `regime_field.compose` could accept `timing=` (a `gesture_timing.Timing`) as
   an alternative to `field=`, routing through `danced_strokes`. Today
   I reach compose's centrelines via `field=constant(0)`, which works but
   renders twice.
2. `width_samples_k` imports the private `broadnib._resample`. Making it public,
   or adding a `kappa=True` option to `broadnib.width_samples`, would remove
   that coupling.

Unsure:

- CMU 05's hand median speed is 130 cm/s. I took 120 fps from the manifest and
  did not verify it independently.
- The E2 BVH root offsets suggest the rest pose has the spine along +z, but FK
  heights come out sane, with y up.
