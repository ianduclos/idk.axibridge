# Restore the textural baseline

Ian rejected the preceding shared-band/pocket fills: they were worse than the
earlier textural baseline and poorly integrated with the lines. Those trials
remain archived under `../fill/`; they are not the target for this study.
The [comparison](index.html) restores the actual full Territory recipe and
uses its existing texture generator on the new curves. Two probes remain
separate. [Lead report](../../../../docs/reviews/territory02-texture-2026-10-05.md)
and [blind second eye](../../../../docs/reviews/territory02-texture-sol.md).

## Actual baseline and controlled differences

The old full recipe is `tools/territory02/full.json`, with nominal ink 60 m,
density 1, planes 0.15 and mutate 1. Earlier fill trials used 8/18 m allowances;
that was a second difference from this baseline, alongside their panel-like
construction. Here original full Territory is checked byte-for-byte at the
stroke-record level against the unmodified baseline engine for every seed.

`regrow.cjs` concatenates the tracked baseline fragments in memory and captures
the density context at the original debug boundary. It exports the existing
`densityPass` for this isolated adapter. No original fragment, density code,
finish function or recipe is changed. `frozen-source/original-engine.cjs`
preserves the exact original concatenation, beside the full recipe and adapter.
The adapter's context capture does not alter ordinary baseline output.

Both new trials retain byte-identical takeover base strokes. Geometry,
tangents, signed bend direction, junction tests, occupancy and nearest-course
labels are rebuilt from actual rewritten courses. The existing density pass
then grows physical strokes. Its echo inheritance, staggered ends, changing
gaps, mutation, smoothing, retracing, wobble and dry skips are retained. Its
secondary continuations, ribbons, chords and small plane events also remain;
this is the full previous texture regime, not solely its `d-grow` layer.

**Baseline texture on new curves** retains original Territory activity, chaos
and history guidance while replacing present geometry and occupancy. Those
guides can favour a location no longer governed by the current drawing.

**Course-led texture** additionally replaces those guides. History refers to
actual first-pass curves matched through source lineage. The work field uses
the nearest geometric change from first to second rewrite, blurred and
normalized with the original work-map machinery. This is geometric change,
not the original simulation's migration velocity. A 0.12 activity floor and
0.88 work contribution keep quieter areas available; chaos is centered on the
actual pressure pivot with a 35 mm reach. The original texture algorithm and
its finish are still unchanged. Full density can seed from its own added
continuations/ribbons, so even this variant can grow material away from the
principal takeover course.

Nominal allowance is the same 60 m full recipe for all three textured variants.
They need not spend the same ink. Original density budgeting and short-gap
ordering are preserved; actual ink is recorded. Hard mechanical limits are
100 m, 250k points and the 300 × 218 mm bed. Physical stroke width stays 0.1 mm.
No raster brush or filled polygon replaces the physical line families.

## Evidence and limits

Development: 5, 13, 18, 24, 47, 82. The curve, adapter, renderer, full recipe and
original texture source were frozen before first generation/inspection of
fresh 331, 389, 419, 463. No curve/texture tuning followed those images.
All 40 seed/variant cases passed baseline parity, repeated regrowth, unchanged
input/base strokes, finite geometry, bounds and physical-limit checks.
`check.cjs` separately exercises two actual seeds with frozen rewrite inputs.

Neutral labels: A original full baseline, N bare takeover curves, V baseline
texture on new curves, B course-led texture. Removal calibration H is V-13;
D removes its `d-grow` layer; R removes all texture. Whole sheets and matched
100 × 70 mm details are shown before revealing identity or mechanisms to Sol.
Whole sheets are primary. Details center on the V variant's most occupied
20 mm grown-ink tile, so they can omit another important encounter. In seed
389 that frame contains no bare course: this is an actual separation exposed
by the comparison, not an image-loading failure.

PNG previews rasterize generated vector paths directly with Matplotlib Agg.
Fine marks and retracing can merge on screen; no paper appearance is verified.
The viewer's 80 images, controls and desktop/mobile layout passed in-memory
Playwright checks with own CSS/SVG text at about:blank, no URL navigation or
external requests. Actual in-app file navigation/link opening remain unverified
after the earlier automatic file-URL security rejection. No app, hardware or
Pi action, interactive response acceptance, production integration or convergence.

## Reproduction

Build the original local engine with `sh build.sh` from
`tools/territory02/experiments/baseline` if absent. From the worktree root:

```sh
node tools/territory02/takeover/texture/check.cjs
node tools/territory02/takeover/texture/render.cjs
node tools/territory02/takeover/texture/render.cjs --holdouts
node tools/territory02/takeover/texture/calibrate.cjs
```

Run `texture/rasterize.py` with existing Matplotlib, and
`texture/check-viewer.py` with existing Playwright/Chromium. The original
repo's `.venv/bin/python` provides both here. Source snapshots, PNGs and JSON
are retained; generated SVGs are reproducible and ignored. Use this commit's
baseline fragments and full recipe when reproducing the frozen population.
