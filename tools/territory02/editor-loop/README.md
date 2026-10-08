# Territory02 — first run of the revised loop

Open [the eight drawings](index.html), then [all revisions](history.html).
The [HTML reading](../../../docs/reviews/territory02-editor-round1-2026-10-05.html)
records judgement and limits. This checkpoint ends round one; Ian's response
shapes any next round. No convergence or general generator is selected.

Three bounded gpt-6.1-sol makers received identical frozen geometry and actual
whole/close images. Material, connections and composition were opening briefs;
each made two stages on S1 and two on S2, inspected them, and chose stage2 for
both. The connection assignment became cropped/repositioned strands plus new
courses implying continuation; literal endpoint exchange was not implemented.
No additional maker stage followed the independent gpt-5.6-sol review.

S1 is pressure seed5; S2 is the less resolved unravelling seed24. Their archived
SVG coordinates were frozen at 0.001 mm precision. `inputs/manifest.json`
records source paths, SVG hashes, geometry hashes and selection reasons. JSON
states are the editable, authoritative record, not a seed recipe. Ancestor IDs
record artistic revision history; some edit scripts rebuild a stage from the
input rather than applying every operation directly to its parent geometry.

`choices.json` preserves the makers' selections. `manifest.json` maps N1–N8
in a fixed shuffle (20261005). N1 is untouched S1; N7 is the older open1277
weak control. Those labels identify experimental controls, not objective quality.
All drawings use 300×218 mm, 0.1 mm, equal framing, and opaque physical paths.
Accumulated ink varies substantially. Main SVGs have physical dimensions;
close views are separately cropped. Finite bounds and replay are not aesthetic
acceptance, physical plotting or generalization evidence.

From the repository root, use the pinned Python with Matplotlib, NumPy,
Shapely and Playwright (in this worktree the existing original checkout's
`.venv/bin/python` supplied them). No packages were installed.

```sh
python tools/territory02/editor-loop/verify.py
python tools/territory02/editor-loop/assemble.py
python tools/territory02/editor-loop/calibrate.py
python tools/territory02/editor-loop/check-pages.py
```

`verify.py` replays both stages and compares all twelve saved JSON files byte
for byte, checking inputs unchanged, lineage, finite bounds and physical framing.
`assemble.py` creates the neutral sheet and fourteen-state history from saved
JSON. `render.py INPUT.json OUTPUT_STEM [x y width height]` rebuilds individual
PNG/SVGs; saved maker PNGs include additional close views.

`prepare.py` is only the initial import from older locally rendered SVGs; it
is not needed to replay the saved study. Calibration is an actual whole-stroke
omission on S1, with removed indices in `calibration-manifest.json`. It is not a
new maker proposal. The reviewer first saw anonymous whole/close images, then
histories and identities; the record keeps initial and later readings separate.

Page verification embeds our own images at about:blank with external requests
blocked. It verifies layout, image decoding, identity disclosure and file-link
targets, not local-browser navigation or user acceptance. Original studies and
production are unchanged. SVG copies are ignored because saved JSON reproduces
them; PNG evidence and JSON are retained.
