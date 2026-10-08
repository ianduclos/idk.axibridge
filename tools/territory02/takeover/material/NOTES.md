# Three material experiments

Ian approved three separate experiments after favouring takeover curves-only and
course-led texture. The [viewer](index.html) retains both references and all
three alternatives. No convergence is selected. During review Ian objected that
the grammar remains limited, with recurring stars and the same curves. These
trials do not resolve that objection. A [separate grammar probe](../grammar/index.html)
addresses the underlying constructors. See the [lead report](../../../../docs/reviews/territory02-material-2026-10-05.md)
and [independent review](../../../../docs/reviews/territory02-material-sol.md).

- Opening compresses actual d-grow donors into unequal local bodies along
  principal courses. Trial 1 made dense repeated spindles; the revised version
  has broader flanks, whole-donor thinning and staggered release. It sometimes
  scatters angular annotations instead. Trial 1 source is preserved.
- Pressure measures texture ink near a course, displaces the course away from
  the more resistant side, then lets nearby sparse texture partly follow.
  It changes existing curves, but can produce serration or detach a curve from
  the mass it encountered. This is a geometric heuristic, not physical simulation.
- Unravelling pulls an existing grown run from its root, moves neighbouring
  fragments to its torn rim or carries them as scraps. The source run and
  fragment provenance are recorded. Dark cavity rims may attract more notice
  than the exposed strand. It is not conservation of ink after clipping.

Makers owned opening.cjs, pressure.cjs and unravel.cjs respectively; root owned
shared inputs, presentation, interpretation and integration. Baseline drawing,
course-led recipe and 0.1 mm physical stroke are unchanged in the references.
The experiments all begin with the same actual bare/course-led inputs. Different
ink totals are part of the intervention, not normalized aesthetic scores.

Development seeds: 5,13,18,24,47,82. Source and upstream hashes were frozen before
first generation of fresh 521,587,631,683; no subsequent mechanism tuning.
All 50 final seed/variant cases passed repeatability for the three developments,
input purity, finite geometry, bed bounds and limits of 100 m / 250k points.
Optional causal stages are also checked for finite, bounded geometry.
`checks.json` and `checks-heldout.json` record actual ink, hashes and events.
Per-maker checks retain their earlier bounded development runs, not acceptance.

Labels C/T/L/F/R mean bare/course-led/opening/pressure/unravelling. The reviewer
read H/J/P calibration first: H unravelling5, J its original course-led input,
P H with exposed pulls and carried scraps removed but the excavated body left.
The later human grammar complaint was revealed before the population review;
mechanisms and identities were withheld until its first reading was written.
This is not a wholly preference-blind review. The report preserves that limit.

Whole 300×218 mm sheets and matched 100×70 details use fixed bare-curve pivots.
A matched detail can miss the material intervention. Additional `*-event.png`
and `*-event-before.png` use the first recorded event, not a selected success,
with equal framing within that before/after pair. They are not common frames
across the three mechanisms. Causal-stage SVGs retain intermediate geometry.

The viewer's 100 image states, equal two-column layout, 390 px mobile stacking,
seed navigation and full-SVG references passed in-memory Playwright checks.
CSS and own generated SVG text are inlined at about:blank; external requests
are blocked. Actual in-app/file URL navigation and link opening remain unverified
following the earlier URL-policy rejection. Screen evidence is not paper or
interactive-response acceptance. Production and hardware remain untouched.

Reproduce from worktree root:

```sh
node tools/territory02/takeover/material/render.cjs
node tools/territory02/takeover/material/render.cjs --holdouts
node tools/territory02/takeover/material/calibrate.cjs
```

Run `rasterize.py` with existing Matplotlib; `check-viewer.py` with existing
Playwright/Chromium. The original checkout's `.venv/bin/python` provides both.
Tracked source, PNGs, JSON and this commit's upstream fragments reproduce the
ignored SVG files. Frozen source copies document versions; their relative
imports refer to the live directory layout, so they are not standalone engines.
