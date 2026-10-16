# Path ordering and the polished Strahler sheet (2026-10-16)

Round-6 follow-up (`round6-2026-10-16.md`, "candidate next round" 4): order
the plotter paths, then polish `regimes-strahler-tree` as a paper candidate.
Nothing was plotted.

Code:
- `gesture/pathorder.py`: `order_paths`, `nest_order`, `travel`, `segments`,
  and `estimate`, a port of the app's estimator.
- `gesture/regime_field.py`: `Composition.groups` / `.kinds` (mark id and
  kind of every polyline), `fill_components`, `nest_tags`, `clip_to_sheet`,
  and `compose(clip=...)`.
- `experiments/regime_compose.py`: subcommands `order` and `polish`.
- `tests/test_pathorder.py` (4 tests, about 2 s) and one new test in
  `tests/test_regime_field.py`.

Outputs:
- SVGs, JSON stats and 10 px/mm previews in `.local/gesture/out/plot_candidates_r7/`.
- `order_rows.json` (every row of table 1).

## 1. Method

**Atoms.**
- A free path can be drawn either way. A closed ring can start at any vertex:
  its seam is rotated to suit its neighbours.
- A mass's fill is a **chain** with a fixed internal order. Each element may
  still be reversed or re-seamed, but the chain as a whole is never reversed.

**Search.**
1. Greedy nearest neighbour from home, using a KD-tree over every legal entry
   point.
2. 2-opt, applied only to segments that are reversible.
3. Or-opt, which moves runs of 1–3 atoms, reversed where that is legal.
4. A monotone re-seam sweep. Each atom's orientation, ring seam or chain
   entry is picked against both of its neighbours.

Steps 2–4 repeat until there is no gain. That takes 0.7 s on A4 and 1.4 s on
A3. If the result has more pen-up travel than the input order, the input
order is returned instead (this is tested). Layers (pens) are ordered
separately, and each starts and ends at home.

**Joining.**
- Consecutive paths are joined when their pen-up gap is at most 1 pen width
  (0.35 mm). The connector is inked.
- Inside one mass, the tolerance is 2 pen widths. This links the graded-fill
  open arcs, which close the comb of clipped arcs, into one inked run. On A4
  this cuts the open arcs from 82 to 38 that are still drawn on their own.

**The constraints, and why they are set this way.**
1. **Lines before masses.** Phase 0 holds lines, nib outlines, signs, drips
   and echo outlines. Phase 1 holds all concentric fill.
   - A line drawn after a mass drags wet ink out of it wherever it crosses or
     ends in it, and leaves a smear trail beyond the edge.
   - A mass drawn over dry hairlines just covers them.
   - Masses carry most of the ink and dry slowest. Drawing them last means no
     pen ever passes over them.
2. **Fill outside-in.**
   - The outline is drawn first, on dry paper, so the edge is crisp. Often it
     is spliced onto the line that enters it.
   - Each inset then goes against the previous wet one, so any drag is pushed
     inward, never across the edge.
   - The pen finishes at the centre, where any excess ink pools invisibly
     inside solid black.
3. **Chains are per connected mass, not per stroke.**
   - One stroke can swell into several masses, and `regime.render` sweeps its
     fill depth by depth across all of them. Kept verbatim, that order gave
     17 400 px of pen-up travel against 6 700 px free (sheet units).
   - `fill_components` splits the fill by mass.
   - `nest_order` then walks each mass depth-first through its nesting tree:
     every inset follows the inset that encloses it, and a long mass is filled
     end by end instead of alternating between its two ends.

**Timing.**
- `pathorder.estimate` ports `axibridge/estimate.py` `plan_job`, using the
  native backend's saved parameters (pen-down 25 %, pen-up 75 %, accel 100,
  pen 20/60, cornering 10).
- The research venv has no pydantic. `regime_compose` imports the real module
  read-only by appending the app venv's site-packages. The port and the app
  agree to 0.1 s on every row (for example 330.5 s against 330.5 s).
- vpype is imported the same way to run the app's own plot pass:
  `session._optimize` defaults, `linemerge --tolerance 0.05mm linesort`.
- estimate.py has no error bound. Real plots also pay USB overhead.
- The 23.6 / 39.7 min figures in round 6 used a nominal 25 mm/s and 0.5 s per
  lift. The app model is about 3× faster.

## 2. Before and after: the round-6 and v2 candidates (`pathorder-travel-r6.jpg`)

These are the exported SVGs, in mm. The marks were recovered from geometry
with `nest_tags`: a path inside a closed ring counts as that ring's fill.

| # | candidate | variant | lifts | pen-up | est. (app model) |
|---|---|---|---|---|---|
| 1 | strahler-tree | as exported | 337 | 13.86 m | 6.8 min |
| 2 | | app plot pass (merge + linesort) | 326 | 2.61 m | 5.8 min |
| 3 | | pathorder free (no constraints) | 337 | 1.60 m | 5.8 min |
| 4 | | pathorder marks (lines → masses, nested fill) | 337 | 3.46 m | 6.0 min |
| 5 | | **pathorder marks + join** | **260** | **3.43 m** | **5.7 min** |
| 6 | single-noise | as exported | 489 | 31.83 m | 10.0 min |
| 7 | | app plot pass | 479 | 2.57 m | 7.6 min |
| 8 | | pathorder free | 489 | 1.57 m | 7.5 min |
| 9 | | pathorder marks | 489 | 2.43 m | 7.6 min |
| 10 | | **pathorder marks + join** | **349** | **2.36 m** | **7.1 min** |
| 11 | v2 single lines (6 files) | any | 1 path, 0 lifts | 0.24–0.52 m (home legs only) | 0.4–1.1 min |

Reading the table:
1. Unordered export was the real waste: 14–32 m of pen-up travel.
2. **The app already fixes most of it at plot time.** Its default plot pass
   runs linesort.
3. Free ordering beats linesort on travel (1.6 against 2.6 m), because it uses
   ring re-seaming and 2-opt.
4. The constraints cost about 1.9 m (about 9 s) of that gain.
5. Joining wins back lifts: 23 % fewer on strahler-tree, 29 % on
   single-noise, at 0.2 s each.
6. Net, the constrained, joined order is a little faster than the app's plot
   pass. Its value is the **draw order** (lines dry before masses, no pen
   through wet fill), not time.
7. The single-line v2 candidates have nothing to order.

The maps show where the constrained travel goes. Each long mass forks into
two partial-fill ends, and the walk crosses between them, so short red runs
follow the trunk. A precedence-aware TSP could remove these. They cost
seconds.

## 3. The polished Strahler sheet (`out/plot_candidates_r7/`)

The sheet was regenerated with the current `regime.py` and `signs.py`, which
include the other agents' mass edges and line events. The final run was at
21:33. Same spec as P1: seed 3, tree, Strahler field, hands by regime,
signs 8, echo 2, drip 5, tremor 0.8, script 5.

Polish steps:
1. **Fill spacing set by the pen.** `pen_px` = 0.35 mm on each paper, so A3
   gets its own denser fill rather than A4 scaled up. A4 scaled up would leave
   0.49 mm spacing, which reads as stripes.
2. **No clamping at the sheet edge.**
   - `compose` used to `np.clip` polylines onto the sheet. A ribbon running off
     the right edge became a ruled bar along the border; you could see it in
     the first polish.
   - It now cuts at the edge (`clip_to_sheet`). Polish uses `clip=False` and
     fits the ink bounding box, so edge marks stay whole.
   - The fill then lands at **0.318 mm**, slightly under the pen, which inks
     solid.
3. Ordered and joined as in §1.
4. Written with one `<g>` layer, in plot order, at stroke 0.35 mm.

| # | file | paper | paths (lifts) | pen-down | pen-up before → after | est. before → after | hatching (pre-join) | open fill arcs left |
|---|---|---|---|---|---|---|---|---|
| 1 | `regimes-strahler-tree-A4.svg` | A4 portrait 210 × 297 | 373 → **251** | 17.1 m | 13.04 → **2.60 m** | 6.8 → **5.5 min** | 0 families, 0 solid | 82 → 38 |
| 2 | `regimes-strahler-tree-A3.svg` | A3 portrait 297 × 420 | 518 → **324** | 33.3 m | 21.74 → **4.39 m** | 12.0 → **9.9 min** | 0 families, 1 solid (pen-spaced fill) | 124 → 48 |

On these sheets the app's plot pass gives 367 / 515 lifts, 2.41 / 3.18 m of
pen-up travel and 5.9 / 10.5 min. Regime shares are line .54, nib .34 and
shape .12, the same as P1.

**A3 does not fit the AxiDraw V3.** Its travel is 300 × 218 mm, so the A3
variant needs an A3-class machine. A4 portrait must go on the bed in
landscape. The app's portrait view handles that and does not change the
lengths. Times assume home is at the SVG's (0, 0).

## 4. Physical preview (`pathorder-preview-sheets.jpg`, `pathorder-preview-detail.jpg`)

Each polyline is drawn as the Minkowski sum with a 0.35 mm disc: a thick
segment per edge plus a disc at every vertex. It is rendered at 20 px/mm and
box-filtered to 10 px/mm, with Flexoki ink on Flexoki paper and no ink
spread. The full-resolution JPEGs are in `out/plot_candidates_r7/*-preview-10ppm.jpg`.

What it looks like, honestly:
1. **The overall image.** The trunk is a solid black river that splits at mid
   height, with a club-like mass at the top. A side branch runs through a
   short nib ribbon into small masses, and a dark lozenge sits mid-left. A
   tangle of wire covers the rest. The best of round 6 survives intact.
2. **The masses ink solid.** At 1:1 (detail, "densest") the concentric
   structure shows only as faint sub-pen striations where curvature opens the
   rings. There are a few hairline white flecks on the trunk's spine, where
   the last inset leaves gaps. That belongs to `regime.render`, not to
   ordering. On real paper, ink spread should close most of it, but that is a
   guess until it is plotted.
3. **Nib zones still read as hollow double lines** ("pipe", open problem 1):
   the middle crops are outlined ribbons, not broad-nib strokes.
4. **New since round 6, from the other agents' line events.**
   - The right branch now ends in a large notched lozenge, about 20 mm, with a
     short thick neck. It reads as a spade or arrow glyph: strong, a little
     stamped.
   - There are small drop and comma events and a few square "diacritic" pairs.
5. **The two sizes now agree in content.** In earlier runs during the session,
   the A3 sheet had sign and terminal events of its own. A3 reads lighter and
   more airy, because the lines stay one pen wide while the sheet grows.

## 5. Recommendation for the first regimes plot

1. Plot **`plot_candidates_r7/regimes-strahler-tree-A4.svg`**: A4, 0.35 mm
   pen, about 5.5 min on the app model.
2. **In the app, turn off "Sort paths"** (and "Merge", which is redundant
   here) in the plot options for this file. The app's default plot pass runs
   vpype linesort and would throw away the lines-before-masses order. Travel
   would be about the same, but with 116 more lifts and pen-down passes
   through wet fill.
3. Use a pen that tolerates dense fill. The trunk alone is several metres of
   pen-spaced insets. Watch the first mass for paper cockling and for pooling
   at the centre, which the outside-in order puts at the end.
4. Ian's approval is needed for any motion.

## 6. Tests

`tests/test_pathorder.py`, 4 tests in about 2 s:
1. Geometry is preserved: the same undirected segment set and the same
   pen-down length, with or without chains or nesting. Pen-up travel never
   exceeds the input order's, including on an input that is already ordered.
2. Joins stay inside the tolerance:
   - every new (inked) segment is at most max(join, chain tol);
   - a 0.61 mm gap stays open at 0.6 mm and closes at 0.62 mm;
   - joining never adds pen-up travel.
3. Mass order:
   - chains are kept verbatim;
   - in nest mode, every inset comes after its parent;
   - every fill path comes after every line;
   - layers never mix.
4. Determinism, plus an analytic trapezoid check on the estimator port.

`tests/test_regime_field.py` adds a test that cuts at the edge instead of
clamping, splits `fill_components` per mass, and checks `nest_tags`
grouping.

**Full gesture suite: 342 passed, 4 failed.** All four failures are in
`tests/test_signs.py::test_events_*`, the signs agent's in-flight line
events. They fail with `ValueError` in `signs._choice` through `plan_events`
and do not touch these files.

## Open

1. Precedence-aware chain splitting: subtrees of the nesting forest as atoms
   with parent-before-child constraints. This would remove the trunk
   back-and-forth, about 1 m of travel.
2. The spine flecks and the nib "pipe" belong to `regime.render`.
3. An app-side option to keep the file's order. "Sort paths" off already does
   this; the question is only whether to surface it as a per-file hint.

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
$P -m experiments.regime_compose order     # round-6 + v2 before/after → results/pathorder-travel-r6.jpg
$P -m experiments.regime_compose polish    # A4 + A3 → out/plot_candidates_r7/, previews → results/pathorder-*.jpg
$P -m pytest -q tests/test_pathorder.py tests/test_regime_field.py
```
