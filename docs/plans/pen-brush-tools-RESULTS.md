# Results: pen tool (brush deferred)

Implements `docs/plans/pen-brush-tools.md` Parts 0 and 1 (toolbar segment +
pen tool). **Part 2 (brush) was deliberately deferred to a separate pass** —
Ian asked to start with pen only. Branch `feat/pen-tool`, 7 commits (source +
tests, toolbar/JS, then five hands-on-testing fixup commits — see "Post-ship
fixes" below).

## Post-ship fixes, round 4: closing-drag bezier, keyframe jump, full mirror

Three more from hands-on use:

- **Closing click-DRAG curves the closing segment** — a plain click on the
  first anchor still closes straight, but a click-drag now pulls ONLY the
  first anchor's `in_handle`, curving just the closing segment and leaving
  its `out_handle` (the already-drawn first segment) untouched — "one spline,
  no distortion." New `close` gesture with its own live preview.
- **Selecting a keyframe jumps the master timeline** — clicking the ▸ A / ▸ B
  sublayer of a follow_master tween scrubs the timeline to where that
  keyframe shows (A→window start, B→window end), so selecting B to edit it
  also previews it. Only for linear/cosine follow_master tweens; non-keyframe
  layers (including the tween row itself) don't move the scrubber.
  `compose.js::jumpTimelineToKeyframe`.
- **Shift+Option is now a FULL symmetric mirror** — this SUPERSEDES round 2's
  angle-only choice below: Ian asked for the length to mirror too, so the
  opposite handle now becomes an exact reflection (same angle AND length —
  the classic smooth node). Option-drag still moves one handle independently.

Verified live: closing drag sets `first.in_handle` with `out_handle` still
null and the other anchors clean; select B → master-t 1.000, A → 0.000, tween
row unchanged; Shift+Option gives `in == -out` exactly.

## Post-ship fix, round 3: editing before commit

"Allow me to edit splines before consolidating" — until this fix, Option-
drag re-editing only worked on an already-committed pen layer; an anchor
placed earlier in the CURRENT, still-in-progress subpath had no way back to
adjust its handle once you'd moved on to place the next point. `hitPending()`
mirrors `hitExisting()` over the local `pending` array instead of a
committed layer's subpaths; `applyAnchorEdit()` factors the shared
anchor/handle math out of `applyEditDrag` so both paths use identical
Option/Shift+Option semantics — only WHERE the edit lands differs (local
mutation, no network call, vs. a coalesced server regenerate). In `onDown`,
a pending subpath's own points take over re-editing entirely while one is in
progress; committed-layer editing only applies once nothing is pending.
Verified live: editing a pending anchor's handle never hits the server (no
pen layer exists in the project yet), and the edit is exactly what lands in
the subpath once it's finally committed.

## Post-ship fixes, round 2 (asked to plan before implementing)

Three more issues from hands-on use, planned via `AskUserQuestion` before
touching code (two genuine design forks, not derivable from the existing
code or plan):

- **Unfinished shape lost on tool switch.** `deactivatePenMode()` cleared
  `pending` unconditionally with no commit. Asked: auto-commit as an open
  line, or keep the pending state alive (hidden) until you switch back to
  pen? Answer: auto-commit (with "resume/extend an existing open line
  later" flagged as a separate future idea, not built now). Leaving the
  tool with 2+ pending anchors now commits them open, same as pressing
  Enter; Escape remains the deliberate discard gesture — a tool switch
  reads as "I'm done," not "throw it away." A lone anchor with nothing to
  connect is still dropped.
- **Handle modifier scheme redesigned.** Previously a plain drag on an
  existing handle knob moved it; now handles are inert without Option
  (checked continuously every pointermove, so toggling Option mid-drag
  works — not just at the initial grab). Option+drag moves one handle
  independently; Shift+Option+drag also mirrors the OPPOSITE handle onto
  the same line through the anchor. Asked which mirror semantics: angle-only
  (each handle keeps its own length) vs. full mirror (forces equal length
  too). Answer at the time: angle-only. **(Superseded in round 4 above — Ian
  later asked for length to mirror too, so Shift+Option is now a full
  symmetric mirror.)** The same Option/Shift+Option split applies uniformly to
  pulling a brand-new handle out of a bare corner anchor (one-sided vs.
  symmetric-both-sides) — one code path (`applyEditDrag`'s `mirror` flag)
  covers both origins. A handle gesture that never had Option held skips
  the regenerate call entirely (no wasted network round-trip or empty undo
  checkpoint for a drag that changed nothing).
- **Anchor markers → small hollow squares** (Photoshop-style), replacing
  circles, so they read as visually distinct from the round handle knobs.
  The corner/smooth fill distinction (hollow vs. accent-filled) was kept —
  useful information, orthogonal to the shape change that was actually
  requested.

Verified live (Playwright against the real dev flow, not just pytest): a
2-anchor line auto-commits open with no Enter press; a plain handle-knob
drag leaves `out_handle` unchanged; Option-drag moves it while `in_handle`
stays untouched; Shift+Option-drag mirrors `in_handle` to exactly opposite
(`cos(angle) ≈ -1.0`) while preserving its own prior length instead of
snapping to the dragged handle's length.

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

## Post-ship fixes (found by Ian using the real dev server, not caught by the Playwright pass)

- **No line while placing the second point.** `redraw()` drew anchor circles
  and the hover rubber-band to the pointer, but never the segment connecting
  two anchors *already* placed — so committing a second anchor (plain click
  or drag) left nothing visible until the whole subpath committed. Fixed:
  the pending subpath's placed segments now render as solid native SVG "C"
  curves as each anchor lands (`pendingSegmentsD`/`segmentD`); the hover
  preview to the pointer stays dashed to read as "not committed yet."
- **No curve visible while dragging a new anchor's handle out**, and
  **Option-drag appeared to do nothing.** Two related gaps: (1) the live
  drag-preview only drew the bare handle-guide line, never the actual curve
  segment leading into the in-progress anchor, so there was nothing to
  distinguish a productive drag from a dead one; (2) Option-drag was only
  wired for the CURRENT anchor's own handle at placement time — re-editing a
  committed corner anchor (no handle yet) with Option held did nothing,
  because hit-testing only matched handle knobs that already existed (no
  knob to grab until a handle exists). Fixed: factored `tentativeAnchor()`
  out of `onUp` so the live preview during a drag and the actual commit
  compute the SAME anchor and can't drift apart; `hitExisting` now treats an
  Option-drag starting ON an anchor (not an existing handle) as "pull a new
  one-sided `out_handle` out of it" (Illustrator's corner-to-curve
  convention), leaving `in_handle` untouched.
- Verified both live: a committed anchor placed via plain click-drag has
  symmetric mirrored handles; one placed via Option-drag has `out_handle`
  set and `in_handle: null`; the pending path's SVG `d` attribute updates on
  every intermediate drag frame instead of staying `null` until release.

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
