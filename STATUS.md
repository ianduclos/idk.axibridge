---
project: idk.axibridge
state: active
updated: 2026-07-07
machine: mac+pi
summary: Grid sheets shipped and e2e-verified — plot 1/2/4/16 timeline frames per physical sheet (transient, per-pen passes, shared scale) with a two-axis stepper; suite 190 green on branch feat/grid-sheets.
next:
  - Merge feat/grid-sheets to main (2 commits + docs; suite 190 green, live-verified on :29942)
  - Canvas zoom & pan (wheel zoom + drag pan in canvas.js, display-only)
  - Easing / >2 keyframes if linear A→B starts to feel limiting (ROADMAP)
handoff_for: null
---

# idk.axibridge — status

**Grid sheets (2026-07-07, branch `feat/grid-sheets`, 2 commits
`3d32382..fd99d65`, suite 190).** Plot many timeline frames onto one physical
sheet (1/2/4/16 per page) without the destructive contact-sheet bake.
`session.sheet_document` is transient plot-time assembly (no project mutation,
flows through `resolved()` only): one shared scale across ALL sheets
(flipbook-consistent), grouped BY PEN so each sheet plots as one pass per pen,
nib offset applied after placement. Extracted `_grid_place` as the shared
placement core (`bake_contact_sheet` refactored onto it, behavior unchanged).
API: `SheetSpec` on `plot/start`, `?sheet=<json>` on `/plan`,
`cols/rows/margin_mm` on `export.zip` (one `sheet_NN.svg`/page), and
`GET /animation/sheet_info`. UI: a "per sheet" select drives a sheets × pen-
passes stepper (`static/js/plot.js`); the plan overlay previews the current
page while the panel is open. Tests: `tests/test_sheets.py`. Closes the old
"2 A5 per page" ask and the per-pen deferral (see `ROADMAP.md`). Known
limitation: `doc_to_svg` colours sheet SVG layers from vpype's palette, not
the exact pen colour (pre-existing, shared with `/doc/svg`).

## Prior arc

July 2026 animation arc, five use-driven rounds in one long session (18
commits `5367bcc..d02f93e`, suite 177 passing): frame-sequence assets with
video import + progress SSE; master timeline scrubbing through the single
resolve path; one-click animate; timeline windows; per-layer frame offset
(frame units) and **clip-follow** ("clip follows timeline"); exclusive tween
in-betweens; cascade delete with un-animate; plot-time crop (guide/bed/
custom); pywebview app shell (`launch/AxiBridge.app`) with in-app server log.
The canonical **frame-ladder recipe** is documented in `ROADMAP.md` (v1.4
section); design rationale in the animation sections there and in auto-memory.

Save investigation (2026-07-07): the user's real project (`~/AxidrawProjects/
untitled`) loads/resolves/re-saves cleanly on current code — the hard failure
was almost certainly **version skew** (the live server process predated the
session's commits but served the repo's current JS, so new frontend calls hit
old endpoints). Two genuine defects found and fixed with regression tests:
save never pruned stale files, so `load_project` (which reads every file in
`assets/`) resurrected deleted assets — e.g. a re-imported shorter sequence's
old tail frames — and dead `gen-*.svg` snapshots piled up; and saving gave no
visible feedback outside the Plot-tab log (now "saved ✓" on the button + ⌘S).

Architecture and module contracts: `ARCHITECTURE.md`, `docs/MODULES.md` —
non-negotiable invariants (single resolve path; scrubbing never mutates
stored state). Deployment note: two AxiDraw modes contend for the serial
port — Mac-driven pi_ssh (default, live-verified) vs Pi-served
`axibridge.service` at `idkpi:2942` (disabled by default). See
`../../02_Areas/__claude/SYSTEM.md` arms table.
