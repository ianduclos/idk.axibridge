# Phrased crests — 8 September 2026

Ian asked to develop the uneven/smart crest randomness after accepting the corner
and loop follow-ups. This remains a standalone study, not an installed effect.

## Current experiment

The visual starts with Phrased, a straight source, wavelength 120, spacing and
height variation 75%, and phrase strength 70%. Original randomness remains in
the selector. The engine's omitted `rhythm` option still selects the original
implementation, preserving old numerical baselines; opt into `rhythm:'phrased'`.

Phrased builds a whole number of lobes along arc length, distributes their spans
to fill the source, and connects crest/trough knots with horizontal-tangent cubic
segments. This avoids truncating the final lobe but makes wavelength an approximate
mean: the lobe count changes discretely when wavelength crosses a threshold.
A short path has a single lobe rather than a meaningful multi-crest phrase.

Groups of 3–5 crests share a three-span timing motif, a group pace and a height
scale. Each group has one accent and smaller answering crests. Phrase strength
blends this with independent per-lobe heights and spans. Spacing variation also
moves a crest within its lobe, giving unequal ascent/descent lengths. Height
variation controls crests and troughs. Separate seeded streams keep height edits
from moving knot stations and spacing edits from changing knot values. With both
variations zero, every seed and side relation produces the regular profile.

Related sides perturb corresponding stations within their neighbouring intervals,
so their timing does not accumulate drift. Mirrored shares a profile; independent
uses another seed. Width interpolation, corner joins, taper and masking are the
existing implementations. No curvature narrowing was reintroduced.

## Reading and limits

`crest-population.png` contains 15 neutral cases; `crest-review-map.json` records
parameters. The Sol review is in `CREST-SECOND-EYE.md`. The lead sees useful delays
and unequal authority in R01/R04 but agrees that ungrouped R03/R08 also offer useful
rhythm. Keep the full phrase-strength range; grouping is not a quality guarantee.
R09 and other cases can still read as beads, and some phrases become too similar.
These are provisional screen readings, pending Ian's judgement and paper trials.

`crest-check.cjs` passes profile range/order, deterministic seeds, independent
controls, zero-variation behaviour, side relationships, endpoints and 24 new-mode
fixture configurations (all six fixtures, two scales, masked/unmasked).
Existing geometry, corner and overlap checks pass against the original mode.
`check-study.py` passes the new controls, mode visibility, 12 new-mode shape/width
states, mask/reversal, seed changes and 360/736 light/dark layouts. The initial
browser check caught utility styling overriding HTML hidden; scoped hidden
handling corrected that before the passing rerun. No application suite or hardware
run: no application source changed. These checks do not promise crossing-free
geometry at arbitrary curvature or widths.

Reproduce the new population with `.venv/bin/python
 docs/reviews/open-path-ribbon-2026-09-08/crest-evidence.py` (one shell line).

## Stronger maximum variation

Ian requested more dramatic maxima for both controls. Above 50%, spacing now
progressively expands span ratios with a bounded power curve; height progressively
increases contrast between small and large swells, with a positive floor. The lower
half retains the preceding behaviour (compared numerically at 25% and 50%). For
seed 7 at maximum, five lobe spans changed from roughly 90–150 to 37–215 study
units, and peak heights from .42–.65 to .24–.90. Width remains an outer bound.
`crest-maximum.png` records seed 8 at both maxima. The earlier population and
second-eye report describe the preceding range, not this follow-up. All 24 crest
configurations and browser checks passed again; the lead inspected the maximum
render. Ready for Ian to check.

## Softer steepness changes

Ian requested blending the abrupt shoulders visible in the attached screenshot.
Phrased profiles now use an exact moving average of the cubic profile, with radius
5.5% of wavelength (capped at 4% of total length). Integrating the cubics makes
curvature continuous at the former knot seams. Odd endpoint reflection preserves
zero endpoint widths. It rounds down narrow peaks slightly and lifts nearby
troughs; knot positions/heights remain generation targets, not exact samples of
the filtered outline. Related sides use the same radius. Original mode and corner
geometry are unchanged. This smoothing also applies to the lower variation range.

`crest-smoothing-check.cjs` passed reduced maximum slopes, continuous curvature
at knot seams, endpoints and width bounds across four maximum-variation seeds.
The 24 crest configurations and browser suite passed again. The lead inspected
the regenerated `crest-maximum.png`; visual acceptance remains with Ian.

## Seed blend and independent side wavelengths

The study now accepts Seed A, Seed B and a 0–100% blend. It interpolates the two
positive width functions pointwise along arc length, before strand construction,
corner joins and overlap clipping. This is a profile crossfade: crests may merge
or fade, rather than moving one-to-one between assigned landmarks. End settings
select their seed exactly. Shared endpoints and width bounds remain intact.
Mask visibility and corner-union topology can still change as geometry moves;
continuous profiles are not a promise of unchanged output fragment counts.

Independent wavelengths reveals a right-side wavelength, retaining the existing
wavelength as the left setting. Related sides run their shared seeded pattern at
their respective wavelengths before the usual bounded perturbation. The first
comparison uses the same seeded pattern at each wavelength; its label changes to
“Same pattern, unequal wavelengths” because it is no longer literally mirrored.
Independent sides also retain their distinct random streams. Equal wavelengths
preserve the earlier result. Engine options: `seedB`, `seedBlend` (0–1),
`independentWavelengths`, `wavelengthRight`; omitted options preserve prior output.

`seed-blend-check.cjs` passes exact endpoints, same-seed invariance, pointwise
straight blending and continuity, right-side isolation, equal-wavelength backwards
compatibility, and six unequal-wavelength fixtures with masking in both orders.
The existing geometry/crest/smoothing checks and browser interactions/layouts
also pass. The lead inspected the 736/360 layouts with both new features active.
No paper or installed-app testing; ready for Ian to check.
