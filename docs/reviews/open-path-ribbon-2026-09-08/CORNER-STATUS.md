# Corner and overlap follow-up — ready for Ian to check

Ian asked to remove the mirrored-corner glitch, prioritised even interpolation
and avoiding crossings, and allowed a smooth outer turn. He rejected the
steady-width treatment because it introduced forced shoulders. That treatment
is removed: the original width profiles and random rhythm are unchanged.

## Current corner geometry

`corner-envelope.js` constructs a local swept strip for each interpolation level,
regularizes its boundary using polygon union, and extracts the offset side. The
outer turn uses circular sectors; the inside boundary retains the natural join.
It does not freeze the width, smooth the source, or independently shift crests.
Only neighborhoods of detected sharp corners use this path. The non-corner
fixtures match baseline 39af8e7 exactly with masking off.

The numerical union helper is pinned and vendored from
[polygon-clipping 0.15.7](https://github.com/mfogel/polygon-clipping), with its MIT
license under `vendor/`. The visualization embeds it and needs no network at
runtime. Browser and Node loaders use the same helper. This remains a standalone
study, not an installed Python AxiBridge effect.

All 108 tested corner configurations pass proper self/inter-strand crossing
checks, including the curved corner and both V orientations, three side modes,
three widths, two wavelengths and two seeds. These finite fixtures are evidence,
not a guarantee for all shapes. At excessive widths the envelope may flatten or
produce closer gaps; it does not promise perfectly uniform spacing. If a complex
local union cannot provide an unambiguous endpoint route, that local join is
retained rather than an invented route being substituted.

## Optional overlap mask

Ian chose later passages above earlier ones, plus reversal of the whole order.
`Mask loops` clips actual drawing segments underneath the full upper envelope.
`Reverse order` swaps priority while preserving the generated silhouette.
Transparent overlap remains the default. This is not a preview-only cover.

The helper checks and integration test pass. A known crossing verifies that the
actual visible centreline direction changes when the order reverses, while the
unmasked spine and edge geometry stay identical. This does not model pen thickness
or compensate plotter registration. Masked paths are intentionally split.

## Verification and evidence

Passing: `geometry-check.cjs`, `corner-check.cjs`, `masking-check.cjs`,
`overlap-check.cjs`, and `check-study.py`. Browser checks cover all six fixture
families, mask/inversion controls, strand count, seed changes, finite SVG and
360/736-pixel layouts in light and dark appearances.

`corner-evidence.py` produces `corner-comparison.png`, `loop-comparison.png` and
L2/L3 close views, comparing immutable baseline 39af8e7 with the current engine.
The inline fragment has been rebuilt from the current code. Lead visual review
finds the normal-width joined corner clean and the wide case less even; Sol's
follow-up is recorded in `CORNER-SECOND-EYE.md`.

No application source, running server or hardware changed. Application suite
not rerun; paper output and final aesthetic acceptance remain Ian's.
