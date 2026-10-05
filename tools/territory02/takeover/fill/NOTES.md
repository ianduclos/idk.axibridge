# Course-bound fill probes

Ian found more character in the takeover curves but less overall coherence,
and pointed out that fills had not changed. He chose binding the courses as
the next test. These two probes retain identical takeover base strokes and
derive new physical fill from pairs of their actual rewritten courses.
They remain alternatives for inspection, without integration or a selected
new default. [Lead report](../../../../docs/reviews/territory02-fill-2026-10-05.md)
and [blind Sol review](../../../../docs/reviews/territory02-fill-sol.md).

## Construction

`bind-fill.cjs` looks for nearby, roughly aligned interior course spans and
selects at most three spatially separated pairs. Corresponding arclength
spans form two boundaries. Shared bands interpolate curved strokes between
them, with an unequal progression across the interval. Shared pockets hatch
the same polygon with straight parallel strokes oriented along its course
chord. Self-intersecting pockets use an even-odd scan rule. Neither uses the
original Territory tone field or a raster brush.

A 0.55 mm exclusion around principal courses leaves narrow white channels;
restatement strands are not all masked. Paths are sampled and clipped to a
1 mm bed inset, with pieces under 2 mm dropped. All marks use 0.1 mm physical
stroke width. Crowded bands can look solid or exhibit screen moiré; that is
not a tested paper effect.

The three region shares are unequal (55/30/15, normalized for fewer regions).
Light and dense are nominal total ink allowances of 8 m and 18 m, including
the unchanged base curves. Spacing is bounded between 0.2 and 1.2 mm. A small
region can already reach minimum spacing at light: more allowance need not
change its geometry or tone. New fills obey their strict physical caps;
unused allowance is not redistributed to force a darker drawing.

The ordinary filled Territory reference uses those same nominal allowances,
but its existing stroke-ordering pass joins short gaps after budgeting.
Its actual ink can slightly exceed the nominal cap (seed 24 light is
8,054 mm). It is preserved as the ordinary reference, checked against the
100 m physical ceiling and recorded honestly in JSON. Only curves-alone,
bands and pockets isolate fill changes: their base stroke hash is identical.
Original Territory has different course geometry, so matching seeds do not
make it a fill-only control.

The selector does not require all chosen pairs to form a connected course
network. Local masses can therefore strengthen unrelated incidents. Straight
span end caps can also produce arbitrary wedges. These are consequential
limits exposed by this test, not resolved claims of coherence.

## Evidence and verification

Development seeds: 5, 13, 18, 24, 47, 82. Source was frozen before first
rendering and inspection of fresh seeds 113, 179, 233, 293. No subsequent
curve or fill tuning followed. `frozen-source/manifest.json` records source
hashes; the parent curve source is the same frozen bulb/corner fit.

`check.cjs` checks repeatability, frozen inputs, disabled/empty output,
physical strokes and budgets. Renderer checks passed for all 80
seed/allowance/variant cases: finite geometry, 300 × 218 mm bounds, point
limits, repeatability and unchanged new-variant base curves. These are
mechanical constraints, not aesthetic scores.

Neutral review labels are J ordinary filled Territory, C takeover curves
alone, F shared bands, S shared pockets. A reviewer first inspected whole
development and held-out populations, matching close views and D/H/R removal
calibration before receiving those identities and mechanism descriptions.
Calibration H is full seed-13 light bands; D removes its first region's
stroke bucket; R removes all fill. Remaining material in D is almost entirely
outside this detail frame, with only a tiny left-edge sliver, so D/R can appear
identical there. Their source SVGs differ.

Each variant uses the same 100 × 70 mm detail window, centered on the first
selected region. This can omit important passages. Whole sheets remain the
primary evidence. `rasterize.py` draws the generated polylines directly with
Matplotlib Agg; PNG previews preserve physical width at their chosen scale,
but screen rasterization can change apparent weight.

The viewer's 160 images, controls and desktop/mobile layouts passed an
in-memory Playwright check using own CSS/SVG text, with no URL navigation or
external requests. `viewer-check.json` records that scope. Automatic browser
security rejected opening a local file URL; actual in-app navigation and
link opening remain unverified. No app, hardware, Pi or paper action.

## Reproduction

If absent, build the generated engine by running `sh build.sh` with
`tools/territory02/experiments/baseline` as working directory. Then, from the
worktree root:

```sh
node tools/territory02/takeover/fill/check.cjs
node tools/territory02/takeover/fill/render.cjs
node tools/territory02/takeover/fill/render.cjs --holdouts
node tools/territory02/takeover/fill/calibrate.cjs
```

Use a Python runtime with Matplotlib for `fill/rasterize.py`, then its
`--calibration-only` option; use existing Playwright/Chromium for
`fill/check-viewer.py`. On this machine the original repo's `.venv/bin/python`
provides both. PNGs, JSON and source snapshots are retained. Large generated
SVGs are reproducible and omitted from Git; rebuild before using the viewer
in another checkout.
