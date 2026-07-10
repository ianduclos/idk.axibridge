# Plan: round 2 — scheduled unattended run on idkpi

You are Claude (Fable 5) running headless on `idkpi`, in the clone at
`~/idk.axibridge`. Written by the Mac session on 2026-07-10; the user asked
for these four items verbatim. Round 1 (`pi-generators.md` → RESULTS) went
well — same standards apply.

## Read first

1. `CLAUDE.md`, `docs/MODULES.md` — the contracts. Non-negotiable.
2. `ARCHITECTURE.md` "Resolve order" — you will touch the region seam
   (task 3); understand `occlusion(regions(effects(transform(source))))`
   before editing compose.py.
3. `docs/plans/pi-generators-RESULTS.md` — how round 1 worked and verified.
4. `axibridge/static/js/workbench.js` + `docs/IDEAS-oehlen-pass.md` §0 —
   the workbench you'll extend in task 4.

## Protocol

- `git fetch origin && git checkout -B feat/pi-round2 origin/main` FIRST.
- `.venv/bin/python -m pytest -q` green before every commit; one
  conventional commit per task; push the branch; **never touch main**.
- Visual verification is the job, not a formality: PIL sweeps under `/tmp`
  for geometry (grey intention / black output), and for UI work Playwright
  IS INSTALLED in the venv with chromium — drive the real popup
  (`wait_until="domcontentloaded"`; SSE keeps connections open so
  networkidle never fires). Look at every screenshot with Read.
- Priority for partial completion (fewer complete > all partial):
  task 1 → 2 → 4 → 3. (3 last not least: it edits compose.py, the most
  invariant-dense file — do it with the most remaining focus, and skip it
  rather than half-land it.)
- Finish: shipped-markers in ROADMAP ("Pi round 2" bullet under Sheets v2 +
  the near-term effects list), `docs/plans/pi-round2-RESULTS.md`, push.

## Task 1 — redesign `effects/bitmap.py`: quantize LINES, not blocks

User (verbatim intent): "make it simply quantize any existing lines to hard
cornered grids." The current effect replaces geometry with merged filled
staircase regions; the user wants the lines to KEEP THEIR IDENTITY but move
only on the grid.

- New default `style="lines"`: snap every path's points to the grid
  (anchored at `ctx.translation`, as now), and connect consecutive snapped
  points with **axis-aligned staircase segments only** (Manhattan routing —
  a diagonal becomes hard 90° steps; pick the corner order deterministically,
  e.g. by segment direction, so re-resolves are stable). Collapse repeated
  points. One input path → one output path (identity preserved), `filled`
  carried through, closed stays exactly closed (snap start == snap end).
- Keep the old behavior behind `style="blocks"` (code exists — move, don't
  rewrite). The `solid` param only applies to blocks; note it in the
  description so the UI reads sanely.
- Existing tests in `tests/test_regime_effects.py` pin blocks behavior —
  point them at `style="blocks"` and add lines-mode tests: grid alignment
  of every vertex, axis-alignment of every segment, path-count identity,
  closure preservation. `tests/test_regions.py::test_region_splits…` uses
  bitmap inside a region — update expectations thoughtfully (lines mode
  emits strokes, not filled blocks).
- Aesthetic target: a freehand square through bitmap-lines should read as
  the same drawing forced onto graph paper — wobble becomes hard steps.

## Task 2 — `effects/contract_expand.py` (signed offset)

Grow or shrink the layer's geometry by a signed millimetre offset.

- Filled closed paths: shapely `Polygon.buffer(offset)` — emit exterior +
  interior rings `filled=True`; a shrink that vanishes emits nothing; a
  grow that merges neighbours merging is fine (per-path buffers, like
  fat_tube, to preserve draw order/occlusion semantics).
- Open strokes: `LineString.offset_curve(offset)` (signed side = left of
  travel direction; say so in the param description); `offset=0` passes
  through untouched.
- Params: `offset` (mm, −20..20, default 3), `smooth` (quad_segs 2..16,
  Fine tuning group). Pure, deterministic, bounded.
- Stacking it twice gives insets/onion rings — mention in the docstring
  (the ROADMAP "offset rings" item is then mostly covered; note that in
  your ROADMAP update).

## Task 3 — region boundary continuity (`cut` | `continuous`)

Regions currently SPLIT paths at the boundary (pen lifts at every seam).
User: "an option for regional effects to smoothly continue the lines
instead of cutting them."

- New field `CanvasLayer.region_boundary: Literal["cut","continuous"] =
  "cut"` (+ session `update_layer` allowed-set + a small checkbox next to
  the region toggle in compose.js, shown only when region is on).
- `continuous` semantics: each original path below the region emits **one
  path again** — outside sections verbatim, inside sections replaced by
  their effected geometry, stitched in original order with no pen lift
  (append the effected piece's points between the outside sections; the
  seam is a drawn connection, wherever the effect moved the ends).
- Contract limitation, stated honestly in code + docs: stitching requires
  the region's effect stack to return the inside pieces in order (the
  in-order piece list you clipped). Apply the stack **per piece** in
  continuous mode (pieces stay identifiable) rather than on the whole
  inside set; if an effect returns multiple paths for one piece (bitmap
  blocks, fat_tube), concatenate them in output order into the stitch —
  connected is the promise, not pretty. `filled` handling: a filled closed
  path that gets stitched stays closed if its start/end survive; follow the
  existing survived-closed rule.
- Where: `compose.resolve_project`'s region pass (1.5). Keep the
  reassignment-only cache discipline. Tests: path-count identity in
  continuous mode, seam connectivity (consecutive points exist across the
  boundary — no separate fragments), cut mode byte-identical to today's
  behavior, and `tests/test_regions.py` still green for cut.

## Task 4 — workbench mouse drawing + drawing modes

User: "mouse drawing along with mouse drawing modes (smooth lines along
with more patterned ones)". The workbench popup grows a ✏ draw mode.

- **Input**: a pointer-drawn overlay on the workbench stage SVG (mm coords
  via the viewBox — the sheet is already mm). Pointerdown starts a stroke,
  move appends (throttle to ~1mm spacing), up ends it. Buttons: ✏ toggle,
  ↩ undo last stroke, ✕ clear. Strokes live in the wb state.
- **Modes** (a select, applied to strokes as they land AND re-applied on
  mode change): `raw`, `smooth` (Chaikin corner-cutting ×2–3), plus at
  least two patterned ones — e.g. `steps` (Manhattan-quantize the stroke —
  reuse task 1's snapping server-side or duplicate the tiny math client-
  side), `zigzag` (triangle wave along the stroke), `stitch` (dashes).
  Patterned modes are what make drawn input collide with the machine
  vocabulary — make them read distinctly in a screenshot.
- **Server side**: extend `WorkbenchBody` with optional
  `paths: list[list[tuple[float,float]]]` as an alternative base to
  `module+params` — `_workbench_result` uses them verbatim (mm, already
  placed) and the entire existing pipeline follows for free: effect-stack
  preview, `POST /api/scraps` (store `module="drawing"`, params empty —
  scrap save must freeze the geometry it was given rather than
  regenerating), scrap import, everything. Validate bounds (0..bed) and
  cap total points (~50k) — bounded params rule applies to geometry too.
- **Import live** for drawings: import as a baked layer (the scrap-import
  path already does SVG→layers; a fresh drawing can save-then-import, or
  add a direct import that round-trips through the same code — prefer
  reuse over a new path).
- Playwright-verify the full loop: open bench → draw (synthesize
  pointer events) → mode change visibly re-shapes the stroke → effect
  stack applies on top → save scrap → import → layer exists. Screenshot
  each stage and LOOK at them.

## Boundaries

Tasks 1–4, their tests, docs updates, RESULTS note. No new endpoints
beyond what task 4 specifies, no model.py changes, no backend/serial code,
never open the AxiDraw port. Every numeric param bounded; effects pure;
`filled`/closure preserved; the zero-build ES-module frontend stays
zero-build.
