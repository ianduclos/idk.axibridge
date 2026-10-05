# territory02 — independent curve studies

Ian prefers HTML reports. Deliver reports in HTML, with readable images and
links. The [report index](../../docs/reviews/territory02-reports.html) includes
the complete study history and independent critiques. Markdown files remain
editable source; `render-reports.cjs` rebuilds HTML using the `marked` package
(the Codex bundled Node runtime supplies it through `NODE_PATH`).

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

Ian then found the curves less coherent and the fills unexplored. The separate
`takeover/fill/index.html` compares shared curved bands and hatched pockets
against identical bare takeover curves and ordinary filled Territory. Fresh
113/179/233/293 follow a fill-source freeze. Whole-sheet coherence remains
mixed; no convergence selected. Construction and verification limits are in
`takeover/fill/NOTES.md`, with the report at
`../../docs/reviews/territory02-fill-2026-10-05.md`.

Ian rejected those panel fills as worse than the earlier textural baseline.
`takeover/texture/index.html` restores the original full recipe and actual
density generator, beside two regrowth probes on the new curves. Original
baseline parity is checked for every seed. Fresh331/389/419/463 follow a
source freeze; texture recovery does not establish reliable course integration.
The panel trials remain archived. See `takeover/texture/NOTES.md` and
`../../docs/reviews/territory02-texture-2026-10-05.md`.

## Material and grammar studies

`takeover/material/index.html` keeps opening, pressure and unravelling beside
bare/course-led references. Ian then criticized recurring stars and curves.
`takeover/grammar/index.html` compares an alternative path constructor and
stripped texture recipe against those references. Both retain six development
and four fresh frozen-source seeds. The new vocabulary remains loop-heavy;
no convergence or production replacement is selected. Reproduction is in each
folder’s NOTES.md; the lead report is
`../../docs/reviews/territory02-material-2026-10-05.md`.

## Rough and smooth coexistence

Ian's latest direction restores the rough three-material studies as the base,
with occasional substantial smooth passages. `takeover/coexist/index.html`
compares continuity, interference and independent coexistence, plus unchanged
rough and smooth-only references. These remain separate experiments. Twelve
base cases include two fresh seeds generated after a source freeze; sixty final
drawings and 120 in-memory viewer images passed mechanical checks. The source
notes retain provenance limitations, weak cases and reproduction commands.
See `takeover/coexist/NOTES.md` and
`../../docs/reviews/territory02-coexist-2026-10-05.md`. No convergence selected.

## Scaffold replacement after rejection

Ian rejected the coexistence trial as barely changed and still repetitive.
`takeover/rupture/index.html` replaces the main paths entirely and reuses only
cropped grown grain; open constructions and folded bodies remain separate.
Six seeds include three generated after the source freeze. The earlier
coexistence output is a reference, not an accepted baseline. See
`takeover/rupture/NOTES.md` and
`../../docs/reviews/territory02-rupture-2026-10-05.md` for limits and critique.
