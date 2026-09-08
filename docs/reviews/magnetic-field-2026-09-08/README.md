# Magnetic field visual study — 8 September 2026

[Comparison sheet (PNG)](comparison.png) · [Vector sheet (SVG)](comparison.svg)

Nine drawings implement Ian's approved first study. This is a standalone
experiment, not a registered generator or bench. No application or hardware code
is imported. Black ink on white follows the study brief.

## Reading the sheet

| Row | Arrangement | A | B | C |
| --- | --- | --- | --- | --- |
| 1 | Two bars, opposite poles facing | Continuous | Irregular chains | Loose filings |
| 2 | Two bars, like poles facing | Continuous | Irregular chains | Loose filings |
| 3 | Angled bar and independent N/S poles | Continuous | Irregular chains | Loose filings |

Cell IDs are addressable: e.g. [B1 close view](B1.png), [C3 close view](C3.png).
Every cell has its own PNG and SVG (`A1` through `C3`). SVG labels are vector
outlines so another machine does not need the rendering fonts.

## Lead's screen reading

1. A1 and A2 establish different relationships: the narrow horizontal connection
   becomes a vertical separating passage when the second magnet is flipped.
   The crowded pole approaches and broad empty lobes make those changes legible.
2. B retains those structures and breaks the stroke rhythm. At close scale the
   uneven lengths are evident, but much of B1 still reads as a dashed diagram.
   It does not yet reproduce the reference's thick, granular chains. This is a
   useful limitation to retain in the comparison, not grounds to claim the
   material treatment is finished.
3. C3 is my most promising starting point for further exploration: the angled
   bar and two circular poles give three different local gatherings, while
   the scattered marks leave a readable passage between them. At sheet scale,
   however, the short marks become pale and some of the long routes disappear.
4. Preserve the uneven empty pockets rather than filling the frame uniformly.
   The many lines ending at the rectangular crop are a study boundary, not yet
   an accepted compositional decision.

Next experiment, subject to Ian's selection: gather neighbouring filings into
short uneven chains while keeping some long gaps. Compare against B and C,
retaining the same field. Bench implementation remains deferred until selection.

## Model and reproducibility

Run from the repository root:

```sh
.venv/bin/python docs/reviews/magnetic-field-2026-09-08/study.py
```

Requires the existing numpy and matplotlib installations. Fixed seed: `90826`.
Each bar has equal, opposite point contributions at its ends. The independent
points in row 3 also balance in strength. Outside the bodies, the direction
field is the normalized sum of `q * displacement / (distance² + 0.7²)`, a
softened planar pole approximation. Midpoint integration uses a 0.42 nominal-mm
step; nulls, bodies, the frame and a bounded step count stop traces. Occupancy
rejects duplicate routes without interrupting accepted routes midway.

The scalar-potential/effective-pole approach has a physical basis, but these
point ends, softening, seeding and illustrative free poles are deliberate study
simplifications. No permeability, finite magnet-face distribution, force,
filing interaction or physically calibrated flux density is simulated. See
[FEMM's explanation of the equivalent charge formulation](https://www.femm.info/doku/doku.php?id=faq)
and [its planar scalar magnetostatics example](https://www.femm.info/dmeeker/pdf/TMAG-13-10-0652.pdf).
This study is not a scientific field solver.

All columns reuse the exact traced paths within a row, with unchanged framing
and field settings. B varies segment and gap lengths with a shared spatial
modulation and slight lateral drift. C uses shorter marks, wider gaps, lateral
scatter and angular variation. Neither simulates individual interacting filings.
Ink paths use a single nominal 0.19-mm nib in a 240 × 170-mm coordinate frame;
the sheet and close views scale that frame for viewing. Local weight comes from
overlap, not variable SVG widths. Export sizes are presentation sizes, not a
plot-ready paper assignment. Body outlines and labels are diagram annotations.

## Verification and limits

1. Generation assertions check nonempty paths, positive lengths, finite vertices
   and coordinates within the nominal frame. [Geometry metrics](geometry-checks.json)
   record bounds, mark counts and the matching underlying-field hashes per row.
2. All ten SVG files parse as XML without nonfinite numeric values. PNGs and
   selected close views were inspected visually. Two Chromium capture attempts
   timed out (direct SVG screenshot, then SVG embedded as an image); independent
   browser rendering of the SVG remains unverified. The PNGs were rendered by
   matplotlib from the same drawing objects as the vector files.
3. The irregular columns contain roughly 8,400–9,900 separate ink paths per cell;
   their physical plotting time and small-gap behaviour remain untested. No
   application regression suite was needed for an isolated artifact script.
4. The neutral sheet and `review-variants.png` support the bounded Sol review.
   Calibration X uses constant 1.2-mm dashes and 0.6-mm gaps; Y uses B1's marks.
   Both use identical underlying geometry and pen width. Mechanisms were withheld
   for the reviewer's initial reading. See [SECOND-EYE.md](SECOND-EYE.md).

Ready for Ian to check on screen. Paper appearance, native bench interaction and
physical output have not been verified.
