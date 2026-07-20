# Results: pen tool (brush deferred)

Implements `docs/plans/pen-brush-tools.md` Parts 0 and 1 (toolbar segment +
pen tool). **Part 2 (brush) was deliberately deferred to a separate pass** —
Ian asked to start with pen only. Branch `feat/pen-tool`, 2 commits so far
(source + tests, then toolbar/JS — this doc lands with the second).

## Scope decision (asked, not improvised)

The plan specs a 4-way toolbar segment (select/draw/pen/brush) since it was
written for both tools together. Asked Ian: ship 3-way now (select/draw/pen)
and add brush's button when that tool is actually built, or 4-way with a
disabled brush placeholder now. Answer: **3-way now** — shipped that way, no
dead UI for a tool that doesn't exist yet.

## What shipped

- **`axibridge/sources/pen.py`** — new registered source, `id="pen"`.
  `PenAnchor` (`x`, `y`, `in_handle`/`out_handle` deltas or `None`),
  `PenSubpath` (`anchors`, `closed`), `PenParams` (hidden `subpaths`,
  `flatten_tol` 0.05–2.0mm, default 0.2). `generate()` flattens each
  subpath's cubic Béziers via adaptive de Casteljau subdivision against
  `flatten_tol` (standard flatness test: max deviation of the two inner
  control points from the chord), with a depth-16 recursion cap so a
  degenerate curve bails to a straight segment instead of hanging. Segment
  flattenings concatenate anchor-to-anchor without a duplicated shared
  endpoint (the last point of a de Casteljau recursion is always the
  original, unmutated `p3`, so no explicit dedupe pass was needed — the
  concatenation is exact by construction). `closed=True` appends a wrap
  segment (last→first), snaps `points[0] == points[-1]` exactly, and forces
  `filled=True`; anchor positions are bed-clamped and total anchor count is
  capped at 2000 (mirrors `drawing.py`'s `_MAX_POINTS` pattern) — both raise
  the documented `ValueError`s.
- **`tests/test_pen_source.py`** (12 tests) — registration, empty-raise,
  straight two-corner segment, collinear handles ≈ straight line, a
  symmetric smooth anchor bows the curve by a real (bounded) amount, closed
  output's exact closure + `filled=True`, open output's no-wrap +
  `filled=False`, determinism, `flatten_tol` density ordering, absurd
  anchor-count raise, degenerate coincident anchors don't hang, bed-clamping.
  All passed on the first run.
- **Toolbar (Part 0)** — `#draw-toggle` replaced with `#tool-toggle`, a
  3-button `.seg` (select/draw/pen), reusing the existing generic
  `.seg button.on` CSS (no new toolbar styling needed). `main.js` owns a
  `setToolMode(mode)` broker: each mode's `activate()`/`deactivate()` lives
  in its own module (`draw.js`, `pen.js`); "select" is an empty pair — it's
  just canvas.js's existing behavior with no capture listener stealing
  events. `draw.js` was refactored to export `activateDrawMode`/
  `deactivateDrawMode` instead of managing its own toggle button and Escape
  listener (both removed — the broker now owns both). The doc-preview-banner
  `MutationObserver` (forces back to select + disables the segment while a
  transient sheet/staged doc is showing) also moved from `draw.js` into the
  broker, generalized to cover every tool instead of just draw.
- **`axibridge/static/js/pen.js`** (new) — `initPenMode()` /
  `activatePenMode()` / `deactivatePenMode()` / `handlePenEscape()` /
  `refreshPenOverlay()`, same capture-phase-on-`#canvas-wrap` shape as
  `draw.js`. Key behaviors:
  - Anchor placement is **entirely client-side** (rubber-band cubic preview
    from the last pending anchor to the pointer) until a subpath commits —
    no server call per anchor, only on close-click or Enter, exactly like
    draw.js commits a whole stroke atomically.
  - Plain click → corner anchor. Click-drag → smooth anchor, symmetric
    handles from the drag vector (clamped to 60mm). **Option-drag chord
    decision** (plan left this open): Option-drag sets an asymmetric
    one-sided `out_handle` (leaves `in_handle: null`) at placement time. To
    give an anchor independent, non-mirrored handles on BOTH sides, re-drag
    its handle knobs afterward via the post-commit overlay — this reuses the
    anchor-editing machinery instead of inventing a second placement-time
    chord (e.g. "drag again while still held").
  - Clicking back on the first pending anchor closes the subpath; `Enter`
    commits it open; `Backspace` drops the last pending anchor; pen mode
    stays active after a commit and starts a fresh pending subpath (multiple
    shapes accumulate into one layer per session, mirroring draw.js).
  - **Post-commit overlay**: anchor circles + handle-knob/line pairs for the
    selected pen layer, always rendered while pen mode is active. Dragging an
    anchor moves it; dragging a handle knob moves that handle independently
    (in/out are always independently draggable post-commit — this is also
    how Option-drag's one-sided placement gets its other handle added
    later). Hit-testing is in **screen pixels** via
    `editor.world.getScreenCTM()` (zoom-invariant — a fixed mm tolerance
    would drift with zoom), 9px radius.
  - Escape: first press clears a pending gesture/subpath without exiting the
    tool (`handlePenEscape`, consumed → the broker doesn't switch modes);
    second press (nothing pending) falls through to the broker, which exits
    to select — two stacked meanings on one key, as specced.
  - Undo discipline: an anchor/handle re-edit drag regenerates with
    `coalesce=true` on every move AND on the final pointerup frame (folds
    the whole drag into one ⌘Z, matching `session._checkpoint`'s per-layer
    key semantics — verified below); a finished subpath's commit omits
    `coalesce` (its own undo entry).

## A real bug found and fixed during verification

The anchor/handle overlay only redrew from pen.js's own actions (place,
commit, drag). **Undo/redo and any other external state change never
touched it** — after a ⌘Z, the overlay kept showing stale (pre-undo) anchor
positions even though the underlying layer had reverted. Fixed by exporting
`refreshPenOverlay()` and calling it from `main.js`'s `refreshResolved()` —
the one chokepoint every mutation path (regenerate, undo, layer edits)
already flows through, so the overlay now always tracks real state.

## Verification (Playwright, throwaway server, ports 8971/8972 — never 2942)

1. Toolbar: select→draw→pen exclusivity (clicking pen turns draw off and
   vice versa) — **PASS**. Escape returns to select — **PASS**.
2. Closed rounded shape: 4 smooth (drag) anchors + close-click on the first
   anchor → one layer, curved (not faceted) closed path, exactly 4 anchors
   (no stray 5th from the closing click) — **PASS** (screenshot, visually
   inspected).
3. Open zigzag: 5 corner (plain click) anchors + Enter → straight segments,
   no curvature, appended as a SECOND subpath to the SAME layer (2 lifts in
   the estimate panel) — **PASS** (screenshot, visually inspected).
4. Anchor re-edit drag: dragging an existing committed anchor moves it live,
   no console/global errors — **PASS**.
5. **Coalesce correctness** (the trap this plan called out): committed two
   subpaths, ⌘Z removed exactly the second (not both) — **PASS**. Then
   dragged an anchor through 5 intermediate frames + release (all
   `coalesce=true`), confirmed the server-side anchor position actually
   changed, then a SINGLE ⌘Z reverted it to exactly the pre-drag value in
   one step — **PASS**. This is what caught the overlay-staleness bug above:
   the first version of this test failed with "no pen layer found" because
   the overlay's stale anchor screen-position (never refreshed after the
   first ⌘Z) meant my synthetic drag's hit-test never found the anchor to
   drag in the first place — the drag silently did nothing, and a SECOND ⌘Z
   undid one checkpoint further back than intended (correct undo behavior,
   wrong test premise). Once the overlay redraw hook was added, real anchor
   screen positions matched again and the drag/undo round-trip verified
   clean.
6. No server-log tracebacks/errors across all runs.

Note on the test harness: the app's default view is **portrait**
(`translate(H 0) rotate(90)` on the world group) — a naive mm→screen helper
that assumes a plain linear landscape mapping silently produces wrong screen
coordinates under portrait, without erroring (round-trip through the app's
own `toBed()`/CTM still lands *some* valid on-bed point, just not the
intended one). Placement-only checks (shapes 2–3 above) are insensitive to
this since they only need self-consistent synthetic input. Hit-testing
checks are NOT — reading the real rendered anchor's `getBoundingClientRect()`
and dragging from there (rather than re-deriving a screen position from an
assumed mm value) is the reliable way to test re-editing under any view.

## What I'd tune

- Rubber-band hover preview's curve shape only reuses the last anchor's
  `out_handle` as the shaping influence, with the pointer as a degenerate
  `p2==p3` — a reasonable approximation, not a byte-accurate preview of what
  the NEXT anchor's own incoming curve would look like (that depends on
  choices not yet made). Fine for "what shape roughly comes next," not meant
  to be pixel-exact.
- `MAX_HANDLE_MM = 60` and `HIT_PX = 9` are first-pass numbers, not bench-
  tuned against a real mouse/trackpad session.
- Anchor/handle regenerate-per-pointermove (no client-preview fallback) —
  fine at pen's flattening cost (no shapely), unlike what's expected for
  brush's heavier per-move shapely buffer/union.

## Open questions

None blocking. Brush (Part 2) is next, on its own branch/pass.
