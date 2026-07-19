# Plan: pen tool + brush tool (Sonnet 5)

You are Claude (Sonnet 5) running as a coding agent on Ian's Mac, in a git
worktree of axibridge. Written 2026-07-19 (Sonnet 5, no Fable in the loop —
judgment calls below are frozen, not left for you to improvise).
PREREQUISITE: `feat/draw-mode` and `feat/response-brushes` must already be
merged — `sources/drawing.py`, `static/js/draw.js`, and the `#draw-toggle`
button must exist. If they don't, stop and write
`docs/plans/pen-brush-tools-BLOCKED.md` instead of building around it.

## Why one brief for two tools

ROADMAP 0b/0c call these siblings on purpose: "every tool = geometry-as-params
source + canvas-mode JS module (the draw-mode pattern)." `sources/drawing.py`
is the first instance of that pattern; MODULES.md now names and documents it
("Geometry-as-params sources" — read it, it's short). Pen and brush are the
second and third instances, and the toolbar becomes a proper mode segment
(↖ select · ✎ draw · ⚓ pen · ● brush) instead of draw mode's lone toggle
button. Build the segment once (Part 0), then each tool (Parts 1–2) is a new
source module + a new canvas-mode JS module that plugs into it — same shape,
different capture/flatten mechanics. Ship pen fully before starting brush;
priority order pen → brush if you run short on time (pen unblocks region-input
workflows sooner — a closed pen path is an instant occluder/region mask).

## Read first (in order, all in-repo)

1. `CLAUDE.md` — module purity, bounded params, the undo/coalesce discipline
   (you'll use it constantly here — every drag mid-edit should be one ⌘Z).
2. `docs/MODULES.md` §"Geometry-as-params sources" — the pattern you're
   instancing twice.
3. `axibridge/sources/drawing.py` — read the WHOLE file, not just the params.
   `_prepare_strokes` (bound + bed-clamp on every hidden-param input, never
   trust the client), `_resample`/`_smooth` (arc-length helpers you'll reuse
   patterns from, if not the exact functions), `_velocity_outline` (proof
   that per-point-varying geometry from captured data is a normal thing to
   build by hand, no shapely needed for the pen path).
4. `axibridge/static/js/draw.js` — the canvas-mode JS shape: capture-phase
   listeners on `#canvas-wrap` (so `canvas.js`'s own drag/marquee, registered
   bubble-phase on `#canvas`, never sees your events), `CanvasEditor.toBed`
   for pointer→mm, `activeDrawLayerId` (one active layer per mode session,
   created lazily on the first commit, each subsequent commit appends to it).
   Pen and brush copy this shape exactly — `activePenLayerId` /
   `activeBrushLayerId`, same lazy-create-on-first-commit rule.
5. `axibridge/api.py` around `RegenerateBody`/`coalesce` and
   `session.regenerate_layer` — how a live drag becomes one undo entry.
6. `axibridge/compose.py::build_mask` (lines ~293–334) — the even-odd
   depth-parity nesting pass. **Load-bearing correction for this brief**: as
   of 2026-07-10 this ALREADY reassembles nested holes correctly for
   occlusion, not just `hatch_fill` (`tests/test_compose.py::
   test_filled_occlusion_mask_respects_nested_holes`). If you read an older
   note anywhere claiming occlusion "over-covers a donut's hole," it's stale
   — ROADMAP.md and CLAUDE.md were corrected today. A closed pen path or a
   donut-shaped brush stroke gets correct hole occlusion for free; don't
   build a workaround for a bug that isn't there.
7. `axibridge/effects/hatch_fill.py` — how nested `filled=True` loops become
   visible ink with holes (same nesting idea, independent code path).

## Protocol

- `.venv/bin/python -m pytest -q` green before EVERY commit.
- Branch `feat/pen-brush-tools` from main. One conventional commit per part
  (toolbar segment, pen source, pen JS, brush source, brush JS). NEVER main.
  Do not push.
- **Eye-check is the core loop.** Throwaway server on a temp port (NEVER
  2942), Playwright, `wait_until="domcontentloaded"` (SSE keeps the
  connection open — `networkidle` never fires). For each tool: enter its
  mode, draw a real shape (not a straight line — a shape with at least one
  curve/corner for pen, at least one overlapping self-crossing stroke for
  brush), screenshot, and LOOK. That screenshot is the acceptance test.

## Part 0 — toolbar mode segment

Replace the standalone `#draw-toggle` button with a 4-way exclusive mode
segment: **select** (default, canvas.js's existing behavior — nothing new to
build here, it's just "no tool active"), **draw**, **pen**, **brush**.
Exactly one is active at a time; switching modes must cleanly tear down the
previous mode's capture-phase listeners before the next mode wires its own
(draw.js's `on` boolean becomes "am I the active mode," driven by a shared
broker rather than its own independent toggle). Put the broker wherever it
reads cleanest — a few lines in `main.js` (`setToolMode(mode)` that each of
draw.js/pen.js/brush.js calls to activate, and that calls each module's own
`deactivate()` when it's no longer the active mode) is the minimal-diff
option; a new `static/js/toolmode.js` is fine too if the broker grows. Rules:

- Escape always returns to select mode (in addition to each tool's own
  Esc-cancels-current-edit behavior — two different Esc meanings stacked:
  first Esc cancels an in-progress anchor/stroke, second Esc exits the tool).
  Don't conflate them into one keystroke that sometimes loses work.
- The mode segment buttons live where `#draw-toggle` lives now; keep the
  existing `#draw-toggle`'s title-tooltip style for the new buttons.
- Verify by eye: switch select→draw→pen→brush→select in one Playwright
  script, confirm only one mode's cursor/overlay is ever active.

## Part 1 — Pen tool (`sources/pen.py` + `static/js/pen.js`)

### Data model

```python
class PenAnchor(BaseModel):
    x: float
    y: float
    in_handle: tuple[float, float] | None = None   # delta from (x,y), or None = no incoming curve
    out_handle: tuple[float, float] | None = None  # delta from (x,y), or None = no outgoing curve

class PenSubpath(BaseModel):
    anchors: list[PenAnchor] = Field(default_factory=list)
    closed: bool = False

class PenParams(BaseModel):
    subpaths: list[PenSubpath] = Field(default_factory=list, json_schema_extra={"hidden": True})
    flatten_tol: float = Field(default=0.2, ge=0.05, le=2.0, title="Flatten tolerance (mm)")
```

A **corner anchor** (plain click) has both handles `None`. A **smooth
anchor** (click-drag) has `out_handle = drag_vector`, `in_handle =
-drag_vector` — symmetric by construction. **Option-drag** sets them
independently (breaks symmetry: a cusp with curves on both sides but
different tangents). This is a UI-time distinction only — the data model
already supports any combination, nothing further to encode.

### Flattening

For each consecutive anchor pair `(a, b)` in a subpath (plus, when
`closed`, one more pair wrapping `last → first`), the segment is the cubic
Bézier `p0=a.pos, p1=a.pos+(a.out_handle or (0,0)), p2=b.pos+(b.in_handle or
(0,0)), p3=b.pos` — this degenerates to a straight line automatically when
both handles are `None`/zero, so don't special-case corners. Flatten by
recursive de Casteljau subdivision against `flatten_tol` (standard flatness
test: max deviation of the two inner control points from the `p0–p3` chord;
subdivide via de Casteljau when over tolerance). Cap recursion depth (e.g.
16) so a degenerate curve (coincident points, zero-length) can't hang —
bail to a straight `p0→p3` segment past the cap rather than raising.
Concatenate segment flattenings anchor-to-anchor, deduping the shared
endpoint between consecutive segments (mirror `drawing.py`'s `_dedupe`-style
near-coincidence guard in `compose.py` if you want a precedent, or just skip
appending `p0` for every segment after the first).

### generate()

- Empty `subpaths` → `raise ValueError("draw a path first")` (mirrors
  `drawing.py`'s message style).
- Each `PenSubpath` → one `Path`. `closed=True` → append the wrap segment,
  force exact closure (`points[0] == points[-1]`, snap don't just rely on
  float equality — same reasoning as `freehand.py`'s closed-path snap) and
  `filled=True`. `closed=False` → `filled=False`, no wrap segment.
- Bound total anchor count server-side (a stray huge paste of anchors must
  never hang flattening) — pick a number in the drawing.py spirit (a few
  thousand anchors is already an absurd pen path; a few hundred is normal).
  Raise the same way `drawing.py` does for over-dense strokes.
- Deterministic: same `(subpaths, flatten_tol)` → byte-identical output,
  trivially true since there's no randomness — still write the test, it's
  what catches an accidental float-order-dependent bug in the flattener.

### `static/js/pen.js`

- Click on empty canvas (not near an existing anchor): add a **corner**
  anchor at the click point, pending. Click-drag: add a **smooth** anchor,
  handle length/direction from the drag vector (clamp handle length to
  something sane, e.g. cap at a few tens of mm, so a wild drag can't produce
  a curve that loops back on itself absurdly — this is a UI-side clamp, not
  a `PenParams` bound, since handles are per-anchor deltas not a single
  bounded field). Option-drag: same as smooth-anchor drag but breaks the
  mirror — drag sets `out_handle`; a SECOND drag-while-still-held (or a
  distinct chord — your call, document whichever you pick in the RESULTS)
  adjusts `in_handle` independently.
- Live preview: a rubber-band cubic from the last committed anchor to the
  current pointer position, redrawn on every `pointermove` (client-side SVG
  only, never touches the layer/regenerate — same "instant feedback, commit
  later" split canvas.js already uses for drags).
- **Commit triggers**: clicking back on the FIRST anchor of the current
  subpath closes it (`closed=True`) and commits; `Enter` commits the current
  subpath open (`closed=False`). Either way: append the finished
  `PenSubpath` to the active pen layer's `subpaths` (create the layer lazily
  on the FIRST commit of the mode session, exactly like `activeDrawLayerId`
  in draw.js), clear the pending anchor list, and immediately start a new
  empty pending subpath — pen mode stays active so the next click begins a
  second shape in the SAME layer without leaving the tool. This is a
  deliberate difference from "one shape, one layer": it mirrors how draw
  mode accumulates multiple strokes into one drawing layer per session.
- `Backspace` removes the last PENDING anchor (not yet committed) — no-op if
  none pending. `Esc` (first press) clears the pending subpath without
  committing it; leaves already-committed subpaths on the layer untouched.
- Regenerate calls: while dragging an anchor's handle, use
  `coalesce=true` with a key stable for that one drag (e.g.
  `("pen-anchor", layer_id, subpath_idx, anchor_idx)`); the commit itself
  (finishing a subpath) is its own, non-coalesced checkpoint — one ⌘Z per
  finished shape, one ⌘Z per in-progress handle drag, not one per mousemove.
- **Post-commit overlay**: while pen mode is active and a pen layer is
  selected, draw small circles at each anchor and lines to its handles
  (classic Bézier handle overlay) so re-editing an existing anchor is
  possible — dragging an anchor or handle moves it and regenerates
  (coalesced). This is expected by the ROADMAP spec ("pen mode + selected
  pen layer shows an anchors/handles overlay"); if it's too much for one
  session, ship anchor-drag-to-move at minimum and note handle-re-editing as
  a follow-up in RESULTS rather than skipping the overlay's existence
  entirely — a pen layer with NO way to see its own anchors reads as broken.

### Tests (`tests/test_pen_source.py`)

- Two collinear-handle anchors flatten to (approximately) a straight line;
  a symmetric smooth anchor between two corners produces a smooth curve
  (sample the middle of the flattened output, confirm it deviates from the
  straight chord by roughly the handle length, not by ~0 and not by some
  wild multiple).
- `closed=True` output has `points[0] == points[-1]` exactly and
  `filled=True`; `closed=False` has `filled=False` and no wrap segment.
- Both-handles-`None` anchor pair produces exactly the two endpoints (no
  spurious intermediate points from a "curve" that's actually straight).
- Determinism: same params called twice → identical point lists.
- `flatten_tol` bounds respected; a tiny `flatten_tol` produces measurably
  more points than a large one on the same curved subpath.
- Empty `subpaths` raises; absurd anchor count raises (both via the
  documented ValueError message).
- Degenerate: two coincident anchors (zero-length segment) doesn't hang or
  raise — recursion cap kicks in, segment flattens to nothing/a point.

### Aesthetic target

Draw a rounded rectangle-ish blob with 4 smooth anchors and close it: the
result should look like a genuinely smooth closed curve at the default
`flatten_tol`, no visible faceting, and it should occlude/hatch-fill like
any other closed shape. Draw an open zigzag with corner anchors, hit Enter:
straight segments, no unwanted curvature. If curves look faceted at the
default tolerance, `flatten_tol`'s default is too coarse — tune it down
before shipping, don't just leave it and call it done.

## Part 2 — Brush tool (`sources/brush.py` + `static/js/brush.js`)

### Data model

```python
class BrushStroke(BaseModel):
    points: list[tuple[float, float]]
    mode: Literal["paint", "erase"] = "paint"
    radius: float = Field(default=5.0, ge=0.3, le=50.0)

class BrushParams(BaseModel):
    strokes: list[BrushStroke] = Field(default_factory=list, json_schema_extra={"hidden": True})
```

Radius is captured **per stroke**, not a single top-level dial — the client
keeps a "current radius" in memory (`[`/`]` resize the live cursor circle,
same interaction as a raster paint tool) and bakes it onto each stroke as
drawn, exactly like `drawing.py` bakes `t_s` per point. This means resizing
mid-session never retroactively changes strokes already committed, which is
the behavior a user actually expects from a brush.

### generate() — sequential fold, not union-all/diff-all

This is the one correctness trap in this whole brief: **erasing must be a
per-stroke fold in chronological order**, not "union everything painted,
then subtract everything erased." Those two give different answers whenever
a later paint stroke re-covers an earlier erased spot — union-then-diff
would erase the re-paint too (the diff doesn't know it came first), which is
wrong; the fold gives the correct "paint, undo that bit, paint over it
again = it's back" result users expect from history.

```
acc = None  # shapely geometry, accumulates as we fold
for stroke in strokes:
    buf = (Point(stroke.points[0]).buffer(stroke.radius) if len(stroke.points) == 1
           else LineString(stroke.points).buffer(stroke.radius, cap_style=1, join_style=1))
    if stroke.mode == "paint":
        acc = buf if acc is None else acc.union(buf)
    else:  # erase
        acc = None if acc is None else acc.difference(buf)
```

Single-point strokes (a click, no drag) are a dot — buffer a `Point`, not a
degenerate zero-length `LineString` (shapely will accept the latter but it's
the wrong mental model and worth avoiding). Convert the final `acc`
(`Polygon`, `MultiPolygon`, or `None`/empty) into `Path` objects: **every
ring, exterior AND interior, becomes its own closed `filled=True` Path** —
nesting alone (per `build_mask`'s depth-parity pass, see Read First #6)
marks interior rings as holes; there is no separate "this is a hole" flag to
set. `acc is None` or empty → return zero paths, not an error (an
all-erased brush layer is a legitimate, if useless, state — must not crash
`regenerate`). Empty `strokes` list on a FRESH layer, though, should still
raise `ValueError("paint a stroke first")` — same reasoning as pen/drawing:
a layer that exists with truly nothing captured is a client bug, not a
valid empty state.

Bound total captured points across all strokes server-side (same pattern as
`drawing.py`'s `_MAX_POINTS`) so a long erratic session can't hang the
buffer/union chain — shapely ops on hundreds of strokes are cheap, but put
a real cap in and test it raises cleanly past it.

### `static/js/brush.js`

- A circle cursor at the pointer, radius = current live radius, in bed mm
  (same `toBed` conversion as draw.js). `[`/`]` grow/shrink it (clamp into
  the `BrushStroke.radius` bounds).
- A mode toggle (paint/erase) — a button is sufficient and most reliable to
  build correctly; if you have time, holding Option while dragging as a
  quick-erase (mirroring pen's Option-drag vocabulary) is a nice-to-have,
  not required for acceptance.
- Pointer down→move→up captures one stroke's point list (resample at a
  fixed arc-length step during capture, drawing.py-style, so pointer-event
  density doesn't matter); on pointer-up, append `{points, mode, radius}`
  to the active brush layer's `strokes` (lazy-create on first stroke, same
  as pen/draw), regenerate. Use `coalesce=true` for the live drag preview if
  you choose to regenerate mid-stroke for feedback; the final commit on
  pointer-up is its own checkpoint either way — don't let a whole stroke
  collapse into the SAME coalesce key as the previous stroke, only within
  one stroke's own drag.
- If regenerating on every `pointermove` is too slow to feel live (shapely
  buffer+union on every intermediate point), fall back to a **client-side
  SVG preview** of the raw stroke (a translucent circle-radius polyline)
  during the drag, and only call `regenerate` once on pointer-up — same
  "instant feedback, commit later" split as canvas.js drags and pen's
  rubber-band. Prefer this if the live-shapely approach feels laggy at the
  bench; don't ship something that stutters.

### Tests (`tests/test_brush_source.py`)

- One paint stroke → one closed `filled=True` Path whose enclosed area is
  close to the buffered-line area (sanity check, generous tolerance).
- Paint a stroke, then paint a second overlapping one → single unioned
  region (no seam/duplicate boundary at the overlap — check resulting path
  count / rough area, not exact geometry).
- **The donut case**: paint a stroke that covers a wide area, then erase a
  stroke strictly inside it → exactly two closed `filled=True` Paths (outer
  boundary + inner hole boundary), and reconstructing them as shapely
  polygons-with-holes gives a smaller area than the paint alone (the hole is
  really subtracted, not just visually).
- **The fold-order case**: paint A, erase (overlapping A), paint C
  (overlapping the erased region again) → C's area is present in the final
  result. Construct this with a union-then-diff implementation in the test
  as the WRONG answer to differentiate from (i.e. assert your result
  differs from naive union-all/diff-all on this specific case) — this is
  the test that would have caught the trap above if you'd built it wrong.
- Erase with nothing painted yet → empty result, no raise.
- Determinism: same strokes twice → identical output.
- Bounded `radius` (Pydantic `ge`/`le` on `BrushStroke` — confirm a 422 on
  violation via the normal params validation path, not a custom check).
- Absurd total point count raises cleanly.

### Aesthetic target

Paint a rough blob shape with 3–4 overlapping strokes at a medium radius,
erase a bite out of one edge, paint a small stroke back over part of the
erased bite. Screenshot: one coherent filled shape with a real concave bite
where you erased-and-didn't-repaint, and solid coverage where you painted
back over. If the whole thing looks like a pile of separate circles instead
of one merged shape, the union isn't happening; if the erased bite doesn't
show, the difference isn't happening; if the repainted part is still
missing, you built union-all/diff-all instead of the fold.

## Boundaries

- Do not touch: `model.py`, `compose.py`, `session.py`, `estimate.py`,
  backends, `sources/drawing.py`, `static/js/draw.js`, `effects/hatch_fill.py`,
  any existing module's params or ids.
- Every numeric param bounded (Pydantic `Field(ge=..., le=...)`, including
  nested models like `BrushStroke.radius` — don't hand-roll a clamp where a
  Field bound does the same job with automatic 422s); every source pure and
  deterministic; `filled`/closure correct on every emitted path.
- Neither tool imports `compose.py` — `build_mask`'s even-odd logic is
  precedent to understand, not a function to call from a source; brush
  builds its own shapely polygons directly from its own strokes.
- When done: `docs/plans/pen-brush-tools-RESULTS.md` with both acceptance
  screenshots' paths, the anchor-handle-editing/Option-drag chord you
  settled on for pen, the live-preview-vs-shapely-per-move decision you made
  for brush, and any bound values you tuned away from what's specified here.
