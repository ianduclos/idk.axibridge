# Grammar break

Ian's intervention was specific: the vocabulary keeps returning to the same
curves and goofy stars. The three material studies do not answer that by
merely changing surface treatment. This is a separate structural probe, with
[matched references and controls](index.html), not their convergence.

Two inherited defaults were identified directly in source:

1. `experiments/baseline/t_density.js` constructs the non-legacy surprise as a
   radial thorn, with 5–11 narrow spokes. Slash adds restated chords and an
   occasional crossing X. These are explicit recurring ornaments.
2. `takeover/rewrite.cjs` fits selected bends with the same 3.5 perpendicular
   inflation and very short incoming handle. Restatements repeat nearby curves.
   Selecting other bends does not itself enlarge the vocabulary.

`rebuild.cjs` creates new courses rather than fitting or decorating those old
paths. Their source locations and initial directions are memories from Territory;
subsequent geometry integrates direction along unequal travel intervals. Turning
amount, concentration and location vary independently, occasional tangent changes
produce corners, and nearby existing courses locally redirect a passage. Each
course can stop without returning to its old endpoint. No central spoke hub,
old inflation fitter, or offset restatement is called to construct these paths.
It does **not** implement a general graph surgery system: cutting, topological
joining and branch abandonment proposed in commentary remain future options.

This is a broader range of turn scales, not a claim to an open-ended grammar.
The process can still settle into cursive loops and smooth hooks. Screen trials
show actual different trajectories and enclosures, but coherent relations remain
uneven. Bare 18 has disconnected passages; 82 concentrates loops into a knot.
Removing one stock device is not enough to establish a richer instrument.

Texture keeps the real baseline density/grow/finish implementation. For the
stripped-recipe control and new paths, continue/slash/surprise are zero, planes
zero, cover 0.32, nominal ink 24 m. This removes the thorn, chords, ribbons and
continuations at generation, rather than deleting them after they influenced
texture. Grain, dry skips, retracing and grown mutations survive. There are
multiple recipe changes, so the control is **not** a pure ablation of stars.
The earlier full-texture reference retains its previous nominal 60 m recipe.
The two stripped-recipe versions use the same parameters but different curves
and geometric history. Actual ink, not nominal budget, is in the JSON records.

Trial 1 had loose continuous curls. Trial 2 concentrated turns too often into
tiny coils. Both source versions and population PNGs are retained. The current
third version lengthens the compact turning intervals to allow larger bodies
and returns. Six development seeds precede the final source freeze. Fresh
739/797/853/911 were generated only afterward; no tuning follows those images.
Frozen copies document versions; reproduction uses this commit's actual paths
and upstream baseline fragments, rather than running snapshot files in place.

All output uses physical 0.1 mm strokes on 300×218 mm. Five versions across ten
seeds produce 50 checked cases. The generator is repeated and input-hashed;
finite geometry, bed bounds, 100 m/250k-point ceilings and absence of the named
ornamental layers are checked. These are mechanical limits, not art scores.
Matched 100×70 detail frames come from the most occupied 30 mm tile of the new
bare paths. A detail can omit another important passage; inspect whole sheets.

Neutral labels: A earlier bare, B earlier course-led, D earlier curves with
stripped recipe, Q new bare paths, V new paths with the stripped recipe.
The second-eye addendum is contextual, not fully blind: the reviewer had
already heard the concern and the broad nature of the structural response.

Reproduce from the worktree root:

```sh
node tools/territory02/takeover/grammar/render.cjs
node tools/territory02/takeover/grammar/render.cjs --holdouts
```

Run `preview.py` with existing Matplotlib and `check-viewer.py` with existing
Playwright/Chromium (provided by the original checkout's `.venv/bin/python`).
In-memory browser checks inline own CSS/SVG text at about:blank; no navigation
or external requests. File/IAB navigation, link opening, paper and interactive
response acceptance remain unverified. No production/hardware changes.
