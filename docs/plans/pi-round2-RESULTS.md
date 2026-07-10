# Results: round 2 — scheduled Pi run, 2026-07-10/11

Executed by Claude (Fable 5) headless on idkpi per `pi-round2.md`. All four
tasks shipped completely, in the planned priority order (1 → 2 → 4 → 3),
one conventional commit each on `feat/pi-round2` (pushed). Suite went
287 → 302 passing, hardware untouched.

## What shipped

| Task | Where | Tests |
|---|---|---|
| 1. Bitmap lines mode (new default) | `axibridge/effects/bitmap.py` | `test_regime_effects.py` (2 new + blocks re-pinned) |
| 2. Contract / expand | `axibridge/effects/contract_expand.py` | `tests/test_contract_expand.py` (8) |
| 4. Workbench mouse drawing | `workbench.js`, `api.py` (`WorkbenchBody.paths`) | `test_workbench.py` (3 new) + Playwright loop |
| 3. Region boundary continuity | `compose.py` (`region_stitch_paths`), `session.py`, `compose.js` | `test_regions.py` (4 new) |

Geometry tasks were verified with PIL sweeps under `/tmp/` (grey intention /
black output); task 4 with a real Playwright drive of the popup, screenshots
inspected at every stage.

## Decisions worth knowing (the judgment calls)

- **Bitmap lines: spurs are kept.** A wobble that crosses a cell boundary
  and returns produces a one-cell out-and-back tick. The sweep shows them
  clearly; they ARE "wobble becomes hard steps", so they stay. Staircase
  corner order comes from the underlying segment's dominant axis —
  deterministic, so re-resolves are byte-stable. The region-split test now
  identifies the inside piece by containment, not `filled` (lines mode
  emits strokes).
- **contract_expand sign on rings**: `offset_curve`'s "left of travel" means
  the side flips with winding direction — the ring test pins "a parallel
  ring 3 mm to the (winding-dependent) side" rather than a fixed side. The
  param description states the shapely convention honestly.
- **Region continuity ordering**: pieces from `intersection`/`difference`
  are re-ordered by `line.project()` of each piece's midpoint — arclength
  position along the original path — then stitched. Cut mode's code path is
  untouched (a test pins explicit-cut ≡ default). The honest limitation
  (per-piece stack application; multi-path effect output concatenated) is
  stated in the docstring and ARCHITECTURE.md. The continuity sweep with
  fat_tube shows exactly the promised "connected, not pretty": the pen
  drives into the tube outline and back out, one path.
- **Drawing import is save-then-import.** A drawing has no generator to
  re-run, so "Import live" freezes it to a scrap and rides the existing
  scrap-import path (baked SVG layer). Zero new endpoints; the side effect
  (the scrap stays in the library) is stated in the status line. The
  "Recipe" card button on a drawing scrap loads only the effect stack.
- **Modes are shaped client-side, functionally.** Raw strokes are the state;
  `steps` duplicates the Manhattan math (tiny) rather than calling the
  server per stroke. Shaped output is clamped to the bed before POST so
  zigzag amplitude at the sheet edge can't 400.

## What I'd tune next

- **Bitmap lines mode inside regions + continuous** is the natural combo
  (the whole reason 1 and 3 were in one round) — works, verified in the
  continuity sweep's first column. Worth a real plot to see the seams in ink.
- **Drawing mode params** (step cell size, zigzag amplitude, stitch dash/gap)
  are constants in `workbench.js`. If the modes stick, they want a small
  params row; kept minimal per plan scope.
- **A one-shot "offset rings" effect** (k rings at one spacing) if stacking
  contract_expand copies gets tedious — the ROADMAP item is annotated.
- **Region continuous + seeded effects**: per-piece application means a
  freehand region samples per piece, not per whole-inside. Fine in the
  sweep; if two adjacent pieces of one path ever need coherent noise, the
  ctx would need a per-path sub-seed.

## Surprises

- The horizontal test line at y=50 was *exactly on* the region's 4 mm grid
  (anchor y=30), making bitmap-lines a perfect no-op — the first continuity
  test failed by testing nothing. Moved the line off-grid (y=51). Grid-
  aligned inputs being invariant is correct behavior, but it can silently
  neuter a test.
- Playwright's status-text waits raced the debounced preview (stale "N pts"
  matched immediately); the decisive evidence came from effect-applied
  point counts (880 → 2473 after fat_tube) and the post-import canvas
  screenshot showing tube outlines. Wait on *changed* text, not on a
  pattern, next time.
- `test_app.py::test_state_shape` pins the effect roster with `==` as
  documented in round 1 — amended in the contract_expand commit, no friction.
