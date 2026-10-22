// Pen mode: click/drag anchors on the main canvas become a Bezier subpath
// (docs/plans/pen-brush-tools.md Part 1). Same canvas-mode JS shape as
// draw.js: capture-phase listeners on #canvas-wrap intercept pointer events
// while pen is the active tool (main.js's setToolMode broker), so canvas.js's
// own drag/marquee code — bubble phase on #canvas — never sees them.
//
// Anchor placement is entirely client-side (rubber-band preview only) until
// a subpath COMMITS (close-click or Enter) — only then does a PenSubpath
// reach the server, exactly like draw.js commits a whole stroke at once.
// Once committed, re-editing an anchor/handle on the SELECTED pen layer is a
// live, coalesced regenerate per drag (one ⌘Z per drag), mirroring canvas.js's
// own drag-then-commit split. The anchors/handles of the CURRENT, still-
// uncommitted subpath are ALSO re-editable the same way (same
// arm-drag scheme) before you ever commit — pure local state, no server
// round-trip, so you can tune a curve while still drawing it rather than
// only after it's already a real layer.
//
// Editing gestures on a committed pen layer (insert, bend, corner/smooth,
// select + J / Delete, continue/join — pen v2 E1–E6) live in pen_edit.js,
// sketch mode's capture, fit and live re-fit (P3) in pen_sketch.js, the
// knife (K1) in pen_knife.js, and the
// ordered regenerate queue every committed edit goes through in
// pen_queue.js. This file keeps the drawing state, placement and the pointer
// dispatch that routes each gesture to its handler.

import { api } from "./api.js";
import { S, actions } from "./main.js";
import { renderPenOverlay } from "./pen_overlay.js";
import { DBL_MS, clickPoint, commitContinue, cont, dragToken, flipCornerSmooth, forgetClick, hitSegment,
         hitOpenEnd, hitAnchor, insertPoint, joinInto, noteClick, onDblClick, onPointKeydown,
         selected, setCont, setSelected, startBend, applyBend, validateEditState } from "./pen_edit.js";
import { applyArmDrag, classifyJoin, curvatureHandles, reverseSubpath, snapAngle } from "./pen_ops.js";
import { kickRegen, queueRegenerate, whenIdle } from "./pen_queue.js";
import { addSketchSamples, endRefit, finishSketch, initSketch, sketchView, startSketch } from "./pen_sketch.js";
import { finishKnife, knifeView, moveKnife, startKnife } from "./pen_knife.js";

const $ = (id) => document.getElementById(id);
const BED = { w: 300, h: 218 };
export const HIT_PX = 9;   // screen-pixel hit radius for anchor/handle knobs (zoom-invariant)
export const DRAG_PX = 3;  // pointer movement past this counts as a drag, not a plain click
const MAX_HANDLE_MM = 400; // UI-side clamp, past the bed diagonal (~371 mm): arms stretch freely, only a runaway drag is caught

// Drawing state is owned here and read live by pen_edit.js / pen_queue.js
// (ES module bindings); they change it only through the setters below.
export let on = false;
let wired = false;
let activePenLayerId = null;
export let subtract = false; // add/subtract mode — subtract commits as a bite via shape_op
// The pen bar's drawing mode, kept for the session: "bezier" (click a
// corner, drag out arms), "curvature" (click the points the line passes
// through; curvatureHandles shapes the bends), "sketch" (drag freehand;
// the stroke is fitted into a Bézier line) or "knife" (drag a straight cut
// across the active pen layer's lines). It decides how NEW points are
// placed; a committed subpath carries its own `kind`, which decides how it
// is edited — switching modes never reshapes a layer.
export let penMode = "bezier";
let lastPendingClick = null; // {at, x, y}: curvature mode's previous plain click on the canvas,
                             // so a second one on that point makes it a corner
export let pending = [];   // uncommitted PenAnchor-shaped objects: {x,y,in_handle,out_handle}
let hoverPt = null;  // last known bed-mm pointer position, for the hover rubber-band
export let gesture = null;  // in-progress pointer gesture — see onDown
export let committing = false;
/** @param {any[]} v */ export const setPending = (v) => { pending = v; };
/** @param {any} v */ export const setGesture = (v) => { gesture = v; };
/** @param {boolean} v */ export const setCommitting = (v) => { committing = v; };

export function initPenMode() {
  if (wired) return;
  const wrap = $("canvas-wrap");
  if (!wrap) return; // stale cached index.html: degrade silently
  wired = true;
  wrap.addEventListener("pointerdown", (e) => onDown(e, wrap), true);
  wrap.addEventListener("pointermove", (e) => onMove(e), true);
  wrap.addEventListener("pointerup", (e) => onUp(e), true);
  wrap.addEventListener("pointercancel", () => onCancel(), true);
  wrap.addEventListener("dblclick", (e) => onDblClick(e), true);
  document.addEventListener("keydown", onKeydown);
  // capture phase: a selected point owns J / Backspace / Delete before any
  // other document listener (the app's own Backspace deletes LAYERS)
  document.addEventListener("keydown", onPointKeydown, true);
  // Space during a place drag slides the point itself (P4). Capture phase on
  // window so it beats every other Space handler (page scroll, a focused
  // button's click, the canvas's own pan); only while a place drag is live.
  window.addEventListener("keydown", (e) => onPlaceSpace(e, true), true);
  window.addEventListener("keyup", (e) => onPlaceSpace(e, false), true);
  const sub = $("pen-subtract");
  if (sub) sub.onclick = () => setSubtract(!subtract);
  for (const b of document.querySelectorAll("#pen-mode [data-pen-mode]")) {
    /** @type {HTMLElement} */ (b).onclick = () => setPenMode(/** @type {HTMLElement} */ (b).dataset.penMode);
  }
  initSketch();
  // glyphs are sized in screen px, so any change to px-per-mm (zoom, pan
  // clamp, window resize) re-renders them
  const onView = () => { if (on) redraw(); };
  document.addEventListener("canvas-view-change", onView);
  window.addEventListener("resize", onView);
}

/** @param {KeyboardEvent} e @param {boolean} down */
function onPlaceSpace(e, down) {
  if (!on || gesture?.kind !== "place" || e.code !== "Space") return;
  e.preventDefault();
  e.stopPropagation();
  gesture.space = down;
}

function setSubtract(v) {
  subtract = v;
  endRefit();
  const b = $("pen-subtract");
  if (b) {
    b.classList.toggle("on", subtract);
    b.title = subtract
      ? "Subtracting — click or press E to go back to adding"
      : "Adding — click or press E to subtract this shape out of the target layer";
  }
  redraw(); // pending path flips to rust while subtracting
}

/** @param {string | undefined} mode */
function setPenMode(mode) {
  if (!["bezier", "curvature", "sketch", "knife"].includes(mode)) return;
  if (mode !== penMode) endRefit();
  // sketch and knife modes place no points: a path being drawn is finished
  // first, the way a tool switch finishes it (Ruling 14) — committed while
  // the mode it was drawn in still shapes it, and the pen stays up
  if ((mode === "sketch" || mode === "knife") && mode !== penMode && !committing) finishPending(true);
  // a path being drawn keeps the shape it shows; only new points follow the
  // new mode. Leaving curvature mode freezes its bends into ordinary arms;
  // entering it, the points placed so far become corners that keep their
  // own arms (`fixed`) — the curvature rule never reshapes them. (A
  // continued line's own end, pending[0], is the line's, not a placed point.)
  if (!committing && mode !== penMode) {
    pending = mode === "curvature"
      ? pending.map((a, i) => (cont && i === 0 ? a : { ...a, join: "corner", fixed: true }))
      : shapedPending();
  }
  penMode = mode;
  lastPendingClick = null;
  for (const b of document.querySelectorAll("#pen-mode [data-pen-mode]")) {
    const isOn = /** @type {HTMLElement} */ (b).dataset.penMode === penMode;
    b.classList.toggle("on", isOn);
    b.setAttribute("aria-pressed", String(isOn));
  }
  const detail = $("pen-detail-wrap");
  if (detail) detail.hidden = penMode !== "sketch";
  redraw();
}

/** @param {any} a */
const bare = ({ fixed, ...a }) => a; // pending-only marker, never sent

/** The line being continued, oriented to end at the continued end. */
function continuedLine() {
  const sp = cont ? activeLayer()?.source.params.subpaths?.[cont.si] : null;
  if (!sp) return null;
  return cont.end === "start" ? reverseSubpath(sp) : sp;
}

/**
 * The pending anchors with the arms they commit with — the ONE source of
 * both the overlay's preview and every commit (commitSubpath, pen_edit's
 * mergedContinue), so the two cannot drift. Bézier mode: pending as it is.
 * Curvature mode: pending holds bare on-curve points (plus `extra`: a point
 * being placed, or the pointer) and the curvature rule draws their arms,
 * except points placed in Bézier mode before the switch (`fixed`), which
 * keep their own. Continuing a curvature line, the rule runs over the
 * line's points as well, so the junction bends exactly as the commit
 * re-bends the whole line; continuing a Bézier line, the junction keeps its
 * arm into the line and, at a smooth end, its new arm carries straight on.
 * @param {any[]} [extra] @param {boolean} [closed]
 */
export function shapedPending(extra = [], closed = false) {
  const pts = [...pending, ...extra];
  if (penMode !== "curvature" || !pts.length) return pts.map(bare);
  const line = continuedLine();
  let shaped;
  if (line?.kind === "curvature") {
    const head = line.anchors.slice(0, -1);
    shaped = curvatureHandles({ anchors: [...head, ...pts], closed: false, kind: "curvature" })
      .anchors.slice(head.length);
  } else {
    shaped = curvatureHandles({ anchors: pts, closed, kind: "curvature" }).anchors;
    if (cont) shaped[0] = junctionArms(pts, shaped[0]);
  }
  return shaped.map((a, i) => bare(pts[i].fixed ? pts[i] : a));
}

// A Bézier line's end continued in curvature mode: the arm into the line
// stays; a smooth/symmetric end's new arm leaves straight opposite it (a
// third of the new chord), so the line carries on without a kink.
function junctionArms(pts, shaped0) {
  const end = pts[0], inArm = end.in_handle;
  const out = { ...shaped0, in_handle: inArm };
  const li = inArm ? Math.hypot(inArm[0], inArm[1]) : 0;
  if (li > 1e-9 && pts.length > 1 && classifyJoin(end) !== "corner") {
    const L = Math.hypot(pts[1].x - end.x, pts[1].y - end.y) / 3;
    out.out_handle = [(-inArm[0] / li) * L, (-inArm[1] / li) * L];
  }
  return out;
}

export function activatePenMode() {
  on = true;
  $("canvas-wrap")?.classList.add("pen-mode");
  redraw();
}

export function deactivatePenMode() {
  on = false;
  $("canvas-wrap")?.classList.remove("pen-mode");
  gesture = null;
  endRefit();
  kickRegen(); // a sync may be owed that only a released gesture lets run
  hoverPt = null;
  setSelected(null);
  // The request owns this draft until it resolves. If the user changes tools
  // meanwhile, keep it available for retry when the Pen tool is reopened.
  if (committing) { renderPenOverlay(null); announcePending(); return; }
  // A direct tool switch still finishes a usable open path. The successful
  // commit path clears pending before it asks the broker to select, and the
  // committing guard prevents that automatic deactivation from saving twice.
  if (!finishPending()) renderPenOverlay(null);
}

/** Commit the pending path as an open line, as leaving the tool does (a
 *  lone point, or a continue that placed nothing, is dropped). `stay` keeps
 *  the pen up afterwards. Returns whether a commit started. */
function finishPending(stay = false) {
  if (!committing && pending.length >= 2) {
    if (cont) commitContinue({ stay });
    else commitSubpath(false, { stay });
    return true;
  }
  pending = [];
  setCont(null);
  return false;
}

// The broker calls this before leaving for Select, so one Escape both clears
// the pending work and exits the tool.
// Re-render the anchor/handle overlay against whatever S.state.project now
// holds — called after ANY external state change (undo, redo, an unrelated
// layer edit), since none of those otherwise touch pen.js. A no-op if pen
// mode isn't active.
export function refreshPenOverlay() {
  redraw();
}

/**
 * ⌘Z / ⇧⌘Z (or Edit ▸ Undo/Redo) while the pen is up. Returns true when the
 * pen consumed it: ⌘Z drops the last PLACED point of a pending path (never
 * pending[0] while continuing — that is the line's own end), ⇧⌘Z is a no-op
 * mid-path, and both wait while a gesture or commit is in flight. Otherwise
 * the caller runs a normal history step — after `penSettled()`, so no queued
 * edit lands on top of the undo. That step can move or remove the selected
 * point or the continued line, so both are let go here.
 * @param {boolean} redo
 */
export function handlePenHistoryKey(redo) {
  if (!on) return false;
  endRefit();
  if (gesture || committing) return true;
  if (pending.length > (cont ? 1 : 0)) {
    if (!redo) { pending.pop(); redraw(); }
    return true;
  }
  pending = [];
  setCont(null);
  setSelected(null);
  redraw();
  return false;
}

/** Resolves once every queued pen edit has landed (and the project synced). */
export function penSettled() {
  return whenIdle();
}

/** The layer selection changed: a point selection or a continue belongs to
 *  the layer it was made on, so both go. */
export function penLayerSelectionChanged() {
  endRefit();
  if (cont) pending = [];
  setCont(null);
  setSelected(null);
  redraw();
}

export function handlePenEscape() {
  endRefit();
  if (gesture) { gesture = null; kickRegen(); redraw(); return true; }
  if (pending.length) { pending = []; setCont(null); setSelected(null); redraw(); return true; }
  if (selected) { setSelected(null); redraw(); return true; }
  return false;
}

/** Finish the pending subpath as an open line — what Enter does, exposed for
 *  the toolbar's Commit button. Closing into a shape stays the on-canvas
 *  gesture (click the first anchor), which is where the closing curve drag
 *  lives; a button can't express that. */
export function commitPendingPath() {
  if (!on || gesture || !pending.length || committing) return;
  if (pending.length < 2) {
    // a lone anchor — or a continue that never placed a point — ends empty
    pending = [];
    setCont(null);
    redraw();
    actions.completeDrawingTool(null, "pen");
    return;
  }
  if (cont) commitContinue();
  else commitSubpath(false);
}

export const isTyping = (t) => t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" ||
                              t.tagName === "SELECT" || t.isContentEditable);

function onKeydown(e) {
  if (!on || committing) return;
  // ⌘Backspace / ⌘Enter / ⌘E are not these keys
  if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
  if (e.key === "Enter" && pending.length && !gesture) {
    e.preventDefault();
    endRefit();
    commitPendingPath();
  } else if (e.key === "Backspace" && pending.length && !gesture) {
    e.preventDefault();
    endRefit();
    // continuing: pending[0] is the line's own end, not a placed point
    if (pending.length > (cont ? 1 : 0)) pending.pop();
    redraw();
  } else if ((e.key === "e" || e.key === "E") && !gesture) {
    e.preventDefault();
    setSubtract(!subtract);
  }
}

// -- targeting: which layer (if any) anchor re-editing applies to ------------

function currentTargetLayerId() {
  const project = S.state?.project;
  if (!project) return null;
  if (activePenLayerId && !project.layers.some((l) => l.id === activePenLayerId)) {
    activePenLayerId = null; // the active layer was deleted — never assume
  }
  const sel = S.selection.length === 1 ? project.layers.find((l) => l.id === S.selection[0]) : null;
  // pen, shape AND brush layers are targets: a brush layer converts to a
  // shape layer on commit (the pen silhouette unions/bites into the blob)
  if (sel && sel.source?.type === "generator" &&
      (sel.source?.generator === "pen" || sel.source?.generator === "shape" ||
       sel.source?.generator === "brush")) {
    activePenLayerId = sel.id; // selecting a different pen layer retargets to it
    return sel.id;
  }
  return activePenLayerId;
}

export function activeLayer() {
  const id = currentTargetLayerId();
  return id ? S.state.project.layers.find((l) => l.id === id) : null;
}

function clampBed(x, y) {
  return [Math.min(BED.w, Math.max(0, x)), Math.min(BED.h, Math.max(0, y))];
}

export function clampHandle(dx, dy) {
  const len = Math.hypot(dx, dy);
  if (len <= MAX_HANDLE_MM || len === 0) return [dx, dy];
  const s = MAX_HANDLE_MM / len;
  return [dx * s, dy * s];
}

// -- screen-space hit testing (zoom-invariant) --------------------------------

function toScreen(editor, x, y) {
  const pt = editor.svg.createSVGPoint();
  pt.x = x; pt.y = y;
  return pt.matrixTransform(editor.world.getScreenCTM());
}

export function hitDist(editor, x, y, e) {
  const s = toScreen(editor, x, y);
  return Math.hypot(s.x - e.clientX, s.y - e.clientY);
}

// An existing (committed) anchor or handle knob under the pointer, on the
// active pen layer — how re-editing an already-committed shape is found.
// Handle knobs are found regardless of modifiers: a plain drag on one moves
// the arm, Option breaks the point to a corner (see onMove).
function hitExisting(editor, e) {
  const layer = activeLayer();
  if (!layer) return null;
  const subpaths = layer.source.params.subpaths || [];
  for (let si = 0; si < subpaths.length; si++) {
    const anchors = subpaths[si].anchors;
    const knobs = subpaths[si].kind !== "curvature"; // a curvature line shows no arm knobs
    for (let ai = 0; ai < anchors.length; ai++) {
      const a = anchors[ai];
      if (knobs && a.out_handle && hitDist(editor, a.x + a.out_handle[0], a.y + a.out_handle[1], e) <= HIT_PX) {
        return { kind: "handle", side: "out", si, ai };
      }
      if (knobs && a.in_handle && hitDist(editor, a.x + a.in_handle[0], a.y + a.in_handle[1], e) <= HIT_PX) {
        return { kind: "handle", side: "in", si, ai };
      }
      if (hitDist(editor, a.x, a.y, e) <= HIT_PX) {
        // Option/Alt-drag on the anchor itself pulls a NEW out_handle out of
        // it (Illustrator-style "convert a corner into a curve"), rather
        // than moving the anchor — the way to give an anchor a handle it
        // doesn't have yet, since there's no knob to grab until one exists.
        return e.altKey ? { kind: "handle", side: "out", si, ai } : { kind: "anchor", si, ai };
      }
    }
  }
  return null;
}

// Same idea as hitExisting, but over the CURRENT uncommitted subpath —
// anchors/handles you've placed but haven't finished yet are just as
// re-editable, entirely locally (nothing here touches the server).
function hitPending(editor, e) {
  // curvature mode: the points are all there is — their arms are derived
  const arms = penMode !== "curvature";
  for (let ai = 0; ai < pending.length; ai++) {
    const a = pending[ai];
    if (arms && a.out_handle && hitDist(editor, a.x + a.out_handle[0], a.y + a.out_handle[1], e) <= HIT_PX) {
      return { kind: "handle", side: "out", ai };
    }
    if (arms && a.in_handle && hitDist(editor, a.x + a.in_handle[0], a.y + a.in_handle[1], e) <= HIT_PX) {
      return { kind: "handle", side: "in", ai };
    }
    if (hitDist(editor, a.x, a.y, e) <= HIT_PX) {
      return e.altKey && arms ? { kind: "handle", side: "out", ai } : { kind: "anchor", ai };
    }
  }
  return null;
}

// -- pointer capture -----------------------------------------------------------

function onDown(e, wrap) {
  if (!on || committing || e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  wrap.setPointerCapture(e.pointerId);
  endRefit(); // any press on the canvas is the next pen action
  const editor = actions.canvas();
  const downScreen = { x: e.clientX, y: e.clientY };

  // knife mode: every press is a cut line, wherever it starts
  if (penMode === "knife") {
    setSelected(null);
    const bed = editor.toBed(e);
    gesture = startKnife(bed.x, bed.y, e);
    return;
  }

  // closing click: back on the first pending anchor. A plain click commits
  // closed immediately; a click-DRAG curves JUST the closing segment by
  // pulling the first anchor's in_handle — one spline, so the already-drawn
  // first segment (governed by the first anchor's out_handle) is untouched.
  // (Not while continuing: pending[0] is then the line's own end.)
  if (!cont && pending.length >= 2 && hitDist(editor, pending[0].x, pending[0].y, e) <= HIT_PX) {
    gesture = { kind: "close", moved: false, downScreen };
    return;
  }

  // continuing a line: an open end — its own other end or another line's —
  // joins into it (E6)
  if (cont) {
    const end = hitOpenEnd(editor, e, cont);
    if (end) {
      gesture = { kind: "join", ...end, downScreen };
      return;
    }
  }

  // re-edit an anchor/handle — the CURRENT uncommitted subpath if one is in
  // progress, else an already-committed one on the active layer. Never both
  // at once (one gesture surface at a time), so a pending shape's own points
  // take priority and committed-layer edits stay off-limits mid-draw.
  if (pending.length) {
    const hit = hitPending(editor, e);
    if (hit) {
      gesture = { ...hit, target: "pending", downScreen: { x: e.clientX, y: e.clientY } };
      return;
    }
  } else {
    const hit = hitExisting(editor, e);
    if (hit) {
      gesture = { ...hit, target: "committed", downScreen, token: dragToken() };
      return;
    }
    // on a line of the active pen layer: a click adds a point, a drag bends
    // it — which one is only known once the pointer moves (or doesn't).
    // Not in sketch mode: there a stroke may start anywhere, lines included.
    const seg = penMode === "sketch" ? null : hitSegment(editor, e);
    if (seg) {
      const bed = editor.toBed(e);
      gesture = { kind: "segment", si: seg.si, seg: seg.seg, t: seg.t, downBed: [bed.x, bed.y],
                  moved: false, downScreen, token: dragToken() };
      return;
    }
  }

  // otherwise: start placing a new pending anchor (a click in empty space
  // also drops the point selection)
  setSelected(null);
  const bed = editor.toBed(e);
  const [x, y] = clampBed(bed.x, bed.y);
  // sketch mode: the drag is a freehand stroke (Shift / Space aids don't apply)
  if (penMode === "sketch") { gesture = startSketch(x, y); redraw(); return; }
  gesture = { kind: "place", x, y, alt: e.altKey, moved: false, downScreen,
              shift: e.shiftKey, space: false, lastBed: [x, y] };
}

const movedPast = (g, e) => Math.hypot(e.clientX - g.downScreen.x, e.clientY - g.downScreen.y) > DRAG_PX;

function onMove(e) {
  if (!on || committing) return;
  const editor = actions.canvas();
  if (!gesture) {
    const bed = editor.toBed(e);
    hoverPt = clampBed(bed.x, bed.y);
    if (pending.length) redraw();
    return;
  }
  e.preventDefault();
  e.stopPropagation();
  if (gesture.kind === "sketch") {
    addSketchSamples(gesture, editor, e, clampBed);
    redraw();
    return;
  }
  if (gesture.kind === "knife") {
    const bed = editor.toBed(e);
    moveKnife(gesture, bed.x, bed.y, e);
    redraw();
    return;
  }

  const bed = editor.toBed(e);
  const [bx, by] = clampBed(bed.x, bed.y);

  if (gesture.kind === "place" || gesture.kind === "close") {
    if (movedPast(gesture, e)) gesture.moved = true;
    if (gesture.kind === "place") {
      gesture.shift = e.shiftKey;
      if (gesture.space) {
        // Space: the pointer carries the point; the arm keeps its vector
        // because the arm tip follows the pointer by the same delta
        const [sx, sy] = clampBed(gesture.x + bx - gesture.lastBed[0], gesture.y + by - gesture.lastBed[1]);
        gesture.x = sx; gesture.y = sy;
      }
      gesture.lastBed = [bx, by];
    }
    gesture.dragTo = [bx, by];
    redraw();
    return;
  }

  if (gesture.kind === "join") return; // a join is a click; a wobble doesn't cancel it

  if (gesture.kind === "segment") {
    if (!gesture.moved) {
      if (!movedPast(gesture, e)) return;
      gesture.moved = true;
      startBend(gesture);
      if (!gesture) return;
    }
    if (gesture.kind === "segment") {
      applyBend(gesture, bx, by);
      redraw();
      return;
    }
    // startBend routed a near-end grab to the nearer point: fall through to
    // the point drag below
  }

  if (gesture.kind === "anchor") {
    // a dead zone, so a click on a point (select / continue) never nudges it
    if (!gesture.moved) {
      if (!movedPast(gesture, e)) return;
      gesture.moved = true;
    }
    if (gesture.target === "pending") {
      applyPendingEditDrag(gesture, bx, by, null);
    } else {
      applyEditDrag(gesture, bx, by, null);
      gesture.dirty = true;
      const layer = activeLayer();
      if (layer) queueRegenerate(layer, { coalesce: gesture.token });
    }
    redraw();
    return;
  }

  // gesture.kind === "handle": a plain drag moves the arm, following the
  // point's join (symmetric mirrors, smooth keeps the other arm's length,
  // corner leaves it); Option, read continuously so toggling it mid-drag
  // works, breaks the point to a corner; Shift snaps the arm's angle to 15°.
  // Identical whether the anchor is still pending or already committed —
  // only WHERE the edit lands (locally vs. a server regenerate) differs.
  if (gesture.target === "pending") {
    applyPendingEditDrag(gesture, bx, by, e);
  } else {
    applyEditDrag(gesture, bx, by, e);
    gesture.dirty = true;
    const layer = activeLayer();
    if (layer) queueRegenerate(layer, { coalesce: gesture.token });
  }
  redraw();
}

function onUp(e) {
  if (!on || !gesture) return;
  e.preventDefault();
  e.stopPropagation();
  const g = gesture;
  gesture = null;
  kickRegen(); // every path below ends the gesture, so any owed project sync runs now

  if (g.kind === "sketch") { forgetClick(); finishSketch(g); return; }
  if (g.kind === "knife") { forgetClick(); finishKnife(g, e); return; }

  if (g.kind === "place") {
    forgetClick();
    g.shift = e.shiftKey; // the commit follows Shift as it is at release
    pending.push(tentativeAnchor(g));
    lastPendingClick = penMode === "curvature" ? { at: performance.now(), x: e.clientX, y: e.clientY } : null;
    redraw();
    return;
  }

  // curvature mode: a second click on a point just clicked (a double-click)
  // makes it a corner, or a corner smooth again
  if (g.kind === "anchor" && g.target === "pending" && !g.moved && penMode === "curvature") {
    const prev = lastPendingClick;
    const now = performance.now();
    if (prev && now - prev.at < DBL_MS && Math.hypot(e.clientX - prev.x, e.clientY - prev.y) <= HIT_PX) {
      const a = pending[g.ai];
      pending[g.ai] = { ...a, join: a.join === "corner" ? null : "corner" };
      lastPendingClick = null;
    } else {
      lastPendingClick = { at: now, x: e.clientX, y: e.clientY };
    }
    redraw();
    return;
  }

  if (g.kind === "close") {
    // drag on the closing click curves the closing segment via the first
    // anchor's in_handle only; a plain click (no drag) closes straight
    if (g.moved && g.dragTo && penMode !== "curvature") {
      const first = pending[0];
      first.in_handle = clampHandle(g.dragTo[0] - first.x, g.dragTo[1] - first.y);
    }
    commitSubpath(true);
    return;
  }

  if (g.kind === "join") { joinInto(g); return; }

  if (g.kind === "segment" && !g.moved) { noteClick(e); insertPoint(g); return; }

  // a plain click on a point: the second of a pair flips corner ⇄ smooth,
  // a single one selects it (and arms a continue on an open end). The
  // continued end itself is pending[0], so its double-click arrives here too.
  if (g.kind === "anchor" && !g.moved) {
    if (noteClick(e)) {
      const hit = hitAnchor(actions.canvas(), e);
      if (hit) {
        pending = [];
        setCont(null);
        flipCornerSmooth(hit.si, hit.ai);
        return;
      }
    }
    if (g.target === "committed") { clickPoint(g.si, g.ai); return; }
  }

  // a drag's last move already queued its final frame — nothing is
  // re-snapshotted here (a refresh that landed after that move would make a
  // re-snapshot the OLDER frame). The project sync the drag deferred runs now.
  kickRegen();
  redraw();
}

function onCancel() {
  gesture = null;
  kickRegen();
  redraw();
}

// What a "place" gesture's anchor would look like if committed right now —
// used both to finalize it on pointerup AND to preview it live during the
// drag, so the two never drift apart.
function tentativeAnchor(g) {
  let [x, y] = [g.x, g.y];
  const prev = pending[pending.length - 1];
  if (g.shift && prev) {
    // Shift: the new point's direction from the previous point snaps to 15°
    // (distance kept)
    const [sx, sy] = snapAngle(x - prev.x, y - prev.y, 15);
    [x, y] = clampBed(prev.x + sx, prev.y + sy);
  }
  const anchor = { x, y, in_handle: null, out_handle: null };
  // curvature mode places a bare point: a drag pulls no arms
  if (g.moved && g.dragTo && penMode !== "curvature") {
    let [dx, dy] = g.shift ? snapAngle(g.dragTo[0] - x, g.dragTo[1] - y, 15)
                           : [g.dragTo[0] - x, g.dragTo[1] - y];
    [dx, dy] = clampHandle(dx, dy);
    anchor.out_handle = [dx, dy];
    if (!g.alt) anchor.in_handle = [-dx, -dy]; // symmetric unless Option broke it
  }
  return anchor;
}

// Core edit math, shared by committed-layer and pending-subpath editing —
// only how the anchor OBJECT is located (and whether a server round-trip
// follows) differs between the two callers below.
function applyAnchorEdit(anchor, g, bx, by, e, isEnd = false) {
  if (g.kind === "anchor") {
    // offset: a point grabbed from its line (a near-end bend) keeps the
    // grab's distance instead of jumping onto the pointer
    const off = g.offset || [0, 0];
    const [x, y] = clampBed(bx + off[0], by + off[1]);
    anchor.x = x; anchor.y = y;
    return;
  }
  let [dx, dy] = [bx - anchor.x, by - anchor.y];
  if (e?.shiftKey) [dx, dy] = snapAngle(dx, dy, 15);
  const next = applyArmDrag(anchor, g.side, clampHandle(dx, dy), !!e?.altKey, { isEnd });
  // the join is written explicitly: the result is what the point now is
  next.join = classifyJoin(next);
  anchor.in_handle = next.in_handle;
  anchor.out_handle = next.out_handle;
  anchor.join = next.join;
}

function applyEditDrag(g, bx, by, e) {
  const layer = activeLayer();
  if (!layer) return;
  const subpaths = layer.source.params.subpaths;
  const sp = subpaths[g.si];
  // an arm pulled by hand makes a curvature line an ordinary Bézier one,
  // which keeps the arms it has — the rule would undo the pull
  if (g.kind === "handle" && sp.kind === "curvature") sp.kind = "bezier";
  const n = sp.anchors.length;
  applyAnchorEdit(sp.anchors[g.ai], g, bx, by, e, !sp.closed && (g.ai === 0 || g.ai === n - 1));
  // a curvature point moved: its neighbours re-bend around it
  if (sp.kind === "curvature") subpaths[g.si] = curvatureHandles(sp);
}

function applyPendingEditDrag(g, bx, by, e) {
  applyAnchorEdit(pending[g.ai], g, bx, by, e, g.ai === 0 || g.ai === pending.length - 1);
}

// -- commit: one finished subpath -> append to the active pen layer, or create one --

// Exported because the SHAPE tool (shapes.js) produces the very same thing by
// a different gesture — a rectangle is four corner anchors, an ellipse is four
// with kappa handles. The targeting rules below (subtract needs a target,
// a non-pen target converts to a shape layer, otherwise append or create) are
// subtle enough that a second copy of them would drift; there is one.
export async function commitPenSubpath(subpath, opts = {}) {
  const bite = opts.subtract ?? subtract;
  let committedId = null;
  try {
    const id = currentTargetLayerId();
    const target = id ? S.state.project.layers.find((l) => l.id === id) : null;
    const gen = target?.source?.type === "generator" ? target.source.generator : null;
    if (bite && !target) {
      actions.log("subtract: nothing to bite into — select a pen, brush or shape layer");
      return null;
    }
    if (target && (bite || gen !== "pen")) {
      // region semantics: one op onto the mass. A plain pen/brush target
      // converts to a shape layer inside the same server-side undo step
      // (session.append_shape_op) — "erase from a pen shape commits the shape".
      await api.post(`/api/layers/${target.id}/shape_op`,
                     { op: { kind: "pen", mode: bite ? "subtract" : "add",
                             anchors: subpath.anchors, closed: subpath.closed } });
      activePenLayerId = target.id;
      committedId = target.id;
    } else if (target) {
      const subpaths = [...(target.source.params.subpaths || []), subpath];
      // no coalesce: one finished shape = one ⌘Z, exactly like draw.js's per-stroke commit
      await api.post(`/api/layers/${target.id}/regenerate`, { params: { ...target.source.params, subpaths } });
      committedId = target.id;
    } else {
      const created = await api.post("/api/layers/generate", { module: "pen", params: { subpaths: [subpath] } });
      activePenLayerId = created.id;
      committedId = created.id;
      actions.setSelection([created.id]);
    }
    if (committedId) actions.setSelection([committedId]);
  } catch (e) { actions.oops(e); return null; }
  try {
    await actions.refreshProject();
    await actions.refreshResolved();
  } catch (e) { actions.oops(e); }
  return committedId;
}

async function commitSubpath(closed, { stay = false } = {}) {
  if (!pending.length || committing) return;
  // points kept from Bézier mode (`fixed`) keep their arms only on a Bézier line
  const subpath = penMode === "curvature"
    ? { anchors: shapedPending([], closed), closed,
        kind: pending.some((a) => a.fixed) ? "bezier" : "curvature" }
    : { anchors: pending.map(bare), closed };
  gesture = null;
  redraw();
  committing = true;
  const id = await commitPenSubpath(subpath);
  committing = false;
  if (!id) { redraw(); return; }
  pending = [];
  redraw();
  if (!stay) actions.completeDrawingTool(id, "pen");
}

// -- overlay: rendering lives in pen_overlay.js; this side only gathers state --

// Every mutation of `pending` goes through redraw(), so this is the one place
// that has to announce "there is / isn't something to commit" — the toolbar's
// Commit button enables off it rather than polling.
function announcePending() {
  document.dispatchEvent(new CustomEvent("pen-pending-change",
    { detail: { count: on ? pending.length : 0 } }));
}

// What the overlay should preview of the gesture in flight — computed HERE,
// from the same tentativeAnchor/clampHandle the commit uses, so the preview
// and the committed result never drift apart.
function gestureView() {
  if (gesture?.kind === "place") return { kind: "place", anchor: tentativeAnchor(gesture) };
  if (gesture?.kind === "close" && pending.length >= 2) {
    const first = { ...pending[0] };
    if (gesture.moved && gesture.dragTo) {
      first.in_handle = clampHandle(gesture.dragTo[0] - first.x, gesture.dragTo[1] - first.y);
    }
    return { kind: "close", first };
  }
  return null;
}

// Curvature mode's preview: every pending point re-bends as the next one
// moves, so the whole pending path is reshaped with the point being placed
// (or the pointer, or the closing click) included, then split back into the
// placed points and the previewed one.
function curvatureView() {
  if (gesture?.kind === "place") {
    const shaped = shapedPending([tentativeAnchor(gesture)]);
    return { pending: shaped.slice(0, -1), gesture: { kind: "place", anchor: shaped[shaped.length - 1] } };
  }
  if (gesture?.kind === "close" && pending.length >= 2) {
    const shaped = shapedPending([], true);
    return { pending: shaped, gesture: { kind: "close", first: shaped[0] } };
  }
  if (!gesture && hoverPt && pending.length) {
    return { pending: shapedPending([{ x: hoverPt[0], y: hoverPt[1], in_handle: null, out_handle: null }])
      .slice(0, -1), gesture: null };
  }
  return { pending: shapedPending(), gesture: null };
}

export function redraw() {
  if (!on) { renderPenOverlay(null); announcePending(); return; }
  const layer = activeLayer();
  validateEditState(layer);
  const view = penMode === "curvature" ? curvatureView() : { pending, gesture: gestureView() };
  renderPenOverlay({
    editor: actions.canvas(),
    layerSubpaths: layer ? layer.source.params.subpaths || [] : null,
    pending: view.pending,
    gesture: view.gesture,
    curvature: penMode === "curvature",
    // no hover rubber-band while any gesture is in flight
    hover: gesture ? null : hoverPt,
    subtract,
    selected: selected && layer?.id === selected.layerId ? { si: selected.si, ai: selected.ai } : null,
    continuing: !!cont,
    sketch: sketchView(gesture),
    knife: knifeView(gesture),
  });
  announcePending();
}
