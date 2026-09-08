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
