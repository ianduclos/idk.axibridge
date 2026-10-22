# Pen v2, fill tool, and a hand that draws your line — design

Date: 2026-10-22. Brainstormed with Ian in one session; his marks were made
item by item on the Pen Lab page
(https://claude.ai/artifact/EddXaN1PjMpfKhyESiukND — a throwaway playground,
not a reference implementation; its store holds his verdicts per idea id).
Idea ids below (P1, E3, F2 …) are the ids he marked.

Three separate pieces of work, built in this order: **A. pen v2**, **B. fill
tool**, **C. hand effect**. Each ships on its own. B reuses one thing from A
(the curve fitter); C is independent.

## Why

The pen tool works (docs/plans/pen-brush-tools*.md) but it reads as a first
pass: Ian wants it to look and feel like a professional vector pen, and he
wants new ways to make shapes and lines that suit the plotter — a fill that
builds a shape from lines already on the page, and a way for a precise pen
line to land on paper with a drawn quality.

What success looks like to Ian: drawing and editing curves in AxiBridge feels
as direct as Illustrator/Figma; clicking inside an area enclosed by existing
lines gives him a shape he can fill however he likes; and a clean pen line can
be redrawn by one of his gesture-research hands.

## Constraints (from the repo; don't break)

- Everything in CLAUDE.md "Conventions & invariants" — in particular the
  single resolve path, effect purity + `Path.filled`/closure preservation,
  bounded numeric params, the undo discipline (one `_checkpoint()` per
  mutation; coalesced keys for a drag), and "the MCP follows the API".
- The pen's established structure: `axibridge/sources/pen.py` (a
  geometry-as-params source: `PenParams.subpaths` → `PenSubpath.anchors` →
  `PenAnchor{x, y, in_handle, out_handle}`), `axibridge/static/js/pen.js`
  (canvas-mode module, capture-phase listeners, client-side pending subpath,
  coalesced live re-edit after commit). Existing pen layers in saved projects
  must keep loading and drawing identically.
- No emoji in the UI (Lucide SVG via `.tool-icon`); Flexoki palette tokens.
- Source stays plain ES modules in `axibridge/static/`; `npm run build`
  produces what the server serves.

## A. Pen v2

### A1. Look (Ian: yes to both)

1. **Constant on-screen size.** Anchor squares/circles, arm knobs, arm lines
   and the in-progress path stroke render at a fixed screen-pixel size at any
   zoom (today they are bed-mm sizes in `pen.js`/`style.css` and swell or
   shrink with zoom). Hit radii are already screen-pixel (`HIT_PX`).
2. **Point shape says the point type.** Smooth points are round, corner points
   are square (the Illustrator/Glyphs convention). Today both are squares,
   distinguished by fill.

Not chosen: separate colours for line / arms / corners, and the
"click-to-close" ring on the first point. Leave colours as they are (`--live`
etc.).

### A2. Feel

- **Maybe — grab arms directly (Ian: "perhaps").** Today an arm end only moves
  with ⌥ held. Proposed: with the pen tool active, a plain drag on an arm end
  moves it, the opposite arm mirrors (angle and length, as Shift+⌥ does now),
  and ⌥ during the drag breaks the mirror. Build it behind the rest of A, as
  its own commit, so Ian can try it and keep or revert it.

### A3. New ways to draw (kept)

- **P1 Curvature pen.** A second pen mode: you click points the line passes
  through; the tool shapes the bends (each smooth point's tangent follows its
  neighbours; arms a third of the chord — the lab's mode B is the reference
  feel). Corners by double-click. Points can be dragged; neighbours re-bend.
  Ian dropped the smooth-spline and Hobby/tension variants (P2, P7): don't
  build them.
- **P3 Sketch, then fit.** Drag freehand while in the pen tool's sketch mode;
  on release the stroke is fitted into an editable pen path (Bézier fitting,
  e.g. Schneider's algorithm), with a control for how closely it follows
  (fewer/more points). The fitter is a reusable server-side function — B uses
  it to turn found shapes into editable pen paths.
- **P4 Space moves the point you're placing.** While dragging out arms for a
  new point, hold Space to slide the anchor itself; release Space to go back
  to pulling arms.
- **P5 Angle snapping** (my call, from Ian's "think it's worth it?" — yes,
  cheap): while *placing*, Shift snaps the new point's direction from the last
  point, and dragged-out arms, to 15° steps. Shift's existing meaning during
  *editing* (Shift+⌥ = full mirror) stays.

### A4. Editing (kept)

- **E1** Click on a segment to add a point there without changing the shape
  (de Casteljau split).
- **E2** Corner ⇄ smooth on any existing point (double-click). Going to
  smooth gives it sensible arms (tangent from its neighbours).
- **E3** Bend a segment by dragging its middle; the arms at both ends adjust
  (Figma bend / Curvature-pen push-pull).
- **E4** Arm mirroring as a visible per-point setting: none / angle / angle
  and length, shown on the point and switchable (today it is a modifier you
  hold).
- **E5** Delete a point and keep the curve close: neighbours' arms are refit
  so the shape changes as little as possible.
- **E6** Continue an open line by clicking its end; join two open ends into
  one line.

### A5. Knife (kept)

- **K1** Drag a straight line across pen paths to cut them where it crosses
  (open paths split; a closed path cut twice becomes two open paths or is
  opened). Applies to pen layers.

### A — maybe / later / out

- Maybe, later: **P6** snap to existing geometry (points, ends, crossings,
  bed centre lines) — Ian marked maybe. Not in this build.
- Out: E7 numeric entry (unmarked), S1 curvature comb ("perhaps overkill"),
  S2 plot-order arrows (no), K2 branching lines (Ian unsure what it was; not
  pursued), P2/P7.

## B. Fill tool (F1, F3; F2 per Ian's note; F4 maybe; F5 no)

- **F1** A fill tool: click inside any area enclosed by lines visible on the
  canvas — from any layer — and that area becomes a new closed, filled shape
  on a new layer. The area is found from the lines themselves as geometry
  (lines noded where they cross, enclosed faces found — shapely
  `unary_union` + `polygonize` or equivalent), not from pixels. Holes inside
  the area (an enclosed island) are holes in the shape. Lines are read from
  the resolved geometry (`session.resolved*()`), i.e. what the canvas shows —
  never a second geometry path.
- **F3** Gap tolerance in mm: lines that nearly meet still enclose an area.
- **F5 — frozen, not live (Ian: "not for now").** The shape is a snapshot of
  the area at the moment of the click; moving the lines later does not move
  the fill. The new layer is an ordinary pen layer (its boundary fitted into
  editable pen anchors by A's fitter), so it can be edited with the pen tool
  afterwards.
- **F2 — the fill itself is not automatic (Ian's note: "Not automatically.
  Perhaps make it easy to do, have different fills, stroke outline or not").**
  Clicking makes the shape. Choosing how it's filled is then one easy step
  from the fill tool: a small picker of the existing line fills (hatch, offset
  fill, cymatic/eigen fill, and whatever other fill effects exist), plus
  "outline drawn: yes / no". The picker applies ordinary effects to the new
  layer, so everything stays editable as usual.
- **F4 — maybe, later (Ian: "needs to be well implemented").** Drag across
  several areas to fill them as one shape; ⌥-drag to subtract. Not in the
  first build.

## C. Hand effect (S3)

Ian: "mainly the original line, with a knob for how far it strays", plus my
second idea as an extra toggle.

- A new effect that redraws any input line with one of the frozen gesture
  library hands (the Gesture Studies library: `sources/_gesture_studies/`,
  content-addressed entries; kept layers pin entry hashes, as Gesture Studies
  does). It differs from the existing `freehand` effect (a generic simulated
  spring hand) by using Ian's real research hands, each with its own
  character.
- Default behaviour: **the hand follows your line.** Controls: which hand,
  **how far it may stray (mm)**, seed.
- **Extra toggle: "let it wander".** The hand takes the line as a suggestion
  and goes its own way (looser, longer departures, its own tempo), still
  anchored to the line's start, end and general route.
- **Maybe, later:** a relay of hands along one line (as in the `passage`
  study). Not in the first build.
- Works on any layer, not just pen paths. Must preserve closure and
  `filled` as effects must.

## Non-goals

- Live fills that follow their lines (F5).
- New curve families beyond Bézier and the curvature pen (P2, P7).
- Branching paths / vector networks (K2).
- Changing anything about how other tools (draw, shapes, text) work, beyond
  the pen layer that B creates.

## Anti-goals (a failure even if it technically works)

- Any existing pen layer drawing differently after the change.
- Fill or hand building their own geometry path to the plotter outside the
  single resolve path.
- Handles/points that still change size with zoom.
- A fill that silently picks the wrong area (e.g. a gap-tolerance that leaks
  into the neighbouring area without showing it).

## Settled after the builder check (the lead's calls, not Ian's — he can overturn any)

1. **One point setting, three values.** Each anchor has a `join`:
   `corner` (arms independent, or none), `smooth` (arms stay opposite in
   angle, lengths free) or `symmetric` (opposite and equal). Round = smooth or
   symmetric; square = corner. E2's double-click flips corner ⇄ smooth; E4's
   switch cycles all three. Every arm drag (A2's plain drag and the existing ⌥
   drag) obeys the point's `join`; holding ⌥ during the drag breaks it for that
   drag and sets the point to `corner`. Old anchors have no `join` and are
   classified on load for display and editing only — both arms present,
   collinear and equal length (within 1e-6) → symmetric; collinear → smooth;
   otherwise corner — never changing their geometry.
2. **The fit control is live for the most recent result only.** A "detail"
   slider in the pen tool's options sets how closely sketch-then-fit (and B's
   fitted boundary) follows. Moving it right after a sketch or a fill click
   re-fits that result in place (the browser keeps the raw stroke or area
   outline only until the next action; nothing raw is saved in the project).
   Each re-fit is one coalesced undo step.
3. **The hand never lifts the pen.** One input path in, one continuous path
   out; a closed path stays closed (seek + snap, as `freehand` does) and keeps
   `filled`. Only hands that produce a continuous line are offered; tempo
   entries may vary speed (the density of the hand's own wobble) but never
   insert lifts or retraces. "Let it wander" stays one continuous path.
4. **Knife and join act on the active pen layer only**, like every other pen
   gesture. Joining ends from different layers is out of scope.
5. **Stray is a tendency with a ceiling.** The knob is a soft band the hand
   tends to stay within (its character is kept); a hard ceiling at 2× the knob
   is never crossed. "Let it wander" widens the soft band to 3× the knob and
   the ceiling to 5×.

## C, settled with Ian before planning (2026-10-22)

- **All 44 library hands are offered, as they are** (Ian). Nine of them
  sometimes turn back on themselves (near-180° corner tokens); those turns
  stay. This narrows Settled 3: the hand still never lifts the pen (one path
  in, one continuous path out, closed stays closed), but near-retraces inside
  the line are allowed.
- **Two equal knobs: "stray" and "bend size"** (Ian). Stray is how far the
  line may depart (soft band + ceiling, Settled 5); bend size is the scale of
  the hand's own bends, independent of stray.
- **Corners round a little** (Ian): a sharp corner in the input softens the
  way a real hand would, always within the stray ceiling.
- Lead's calls: the default mode follows the line by offsetting it sideways
  with the hand's own turning (fast, exact ceiling); "let it wander" uses the
  same engine with a wider band and longer departures, not a slow pursuit
  search; wander's tempo is the hand's own (no extra dropdown); the dropdown
  shows labels; each subpath gets its own seed; a kept layer pins the hand's
  hash and keeps it across refreezes, as Gesture Studies does.

## Left to the builder

- The data model for curvature-pen subpaths (e.g. a per-subpath mode, points
  stored on-curve with corner flags, Béziers derived at resolve time), and
  whether/how a curvature subpath converts to a Bézier one — as long as old
  pen params load unchanged.
- The fitting algorithm details, the gap-tolerance method, the knife's
  handling of closed paths, keyboard choices not named above, the picker's
  exact UI, and how the hand effect maps the library hands onto an arbitrary
  input line.
- Splitting A into commits/stages; B and C each in their own stages.
