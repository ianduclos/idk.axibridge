# territory02 — independent curve studies

Screen-only exploration requested by Ian on 5 October 2026. Three Sol makers,
loose starting questions, matched populations, three critique/development rounds,
and three independent Sol evaluations. Original Territory stays intact. Ian later
explicitly deferred convergence: this study presents independent results and
possible strategies, not an integrated generator or new production bench.

Open `index.html` for a same-seed comparison of all three rounds, sparse/full density,
and original Territory. Click drawings for full-resolution SVG. SVG files and embedding HTML are generated locally and omitted from Git;
neutral PNG sheets and review reports preserve the inspected evidence.
Run render.cjs for round1, round2 and round3 after cloning to populate the viewer. The final report
is `../../docs/reviews/territory02-2026-10-05.md`.

## Reproduction

Each `experiments/{baseline,pace,silhouette,void}` directory is a self-contained
copy of the original prototype with a local-only build script. Build in place
with `sh build.sh`. Unlike the original prototype script, these never write into
`axibridge/`. Each maker retains source snapshots for all three rounds and
documents its checks and discarded trials in NOTES.md.

`node render.cjs round3` generates the neutral matched sheets and SVGs from the
frozen third-round source fragments. `node render.cjs round1` uses the retained first-round source fragments directly.
It does not overwrite engines or mix fragments from different rounds. `sparse.json` and `full.json` specify common recipes. The
renderer adds seeds 47 and 82, withheld from the initial makers.

`node render.cjs round2` likewise uses frozen second-round sources.

The original project's `.venv/bin/python capture.py evidence/round3` captures
local HTML with Playwright. This script accepts a Python runtime that already has
Playwright and its Chromium browser; it does not install anything.

After building all four current experiment engines, `node verify.cjs round3`
repeats the 48 matched geometry cases. `check-viewer.py` loads every selection in
the comparison and checks seed navigation. Historical maker check scripts describe
their original stage; retained JSON records their results. They may require a
rebuilt engine for that frozen stage rather than the current third-round build.

Neutral labels: M original, R pacing, K silhouette, P empty space. Reviewers first
saw images and calibration counterfactuals without labels' identities or maker
mechanisms. `withheld-manifest.json` preserves geometry statistics and mappings.
Those counts check physical bounds and repeatability; they are not aesthetic scores.

All current study outputs use the same 0.1mm drawn line width, requested thinner by Ian during round 1. The initial 0.3mm round-1 rendering is retained in `evidence/round1-030/`. Review close windows are
100×70mm at recorded coordinates, identical across versions; this can miss an
important passage elsewhere, so full sheets remain the primary evidence.
Third-round sparse18/47 also have larger identically framed course windows.
No physical plotting, native application restart, or interactive human/machine
response acceptance took place.

## Takeover probe

Ian subsequently asked for a radical second regime, then rejected literal curve
recipes and insufficient tightening. `takeover/index.html` compares original
Territory with two actual successive rewrites; the current fit inflates selected
bends, compresses incoming handles and allows genuine tangent breaks. This does
not integrate the three makers or change production. Its failed trials, current
frozen source, fresh four-seed population and limits are in `takeover/NOTES.md`;
the follow-up report is `../../docs/reviews/territory02-takeover-2026-10-05.md`.
