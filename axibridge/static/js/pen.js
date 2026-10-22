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
// uncommitted subpath are ALSO re-editable the same way (same Option /
// Shift+Option scheme) before you ever commit — pure local state, no server
// round-trip, so you can tune a curve while still drawing it rather than
// only after it's already a real layer.
//
// Editing gestures on the active pen layer (nothing pending), pen v2 E1–E6:
//   click a line          → add a point there (de Casteljau, shape unchanged)
//   drag a line           → bend that segment (one coalesced undo step); a
//                           grab near an end (t < 0.05 / > 0.95) moves the
//                           nearer point instead, where a bend has no leverage
//   click a point         → select it (ring); J cycles its join, Backspace/
//                           Delete removes it with a refit of its neighbours
//   double-click a point  → corner ⇄ smooth
//   click an open end     → continue the line from there; clicking an open
//                           end (its own other end, or another line's) joins
// Every committed edit is one regenerate; edits write the point's classified
// `join` explicitly so a later edit keeps what the user saw.

import { api } from "./api.js";
import { S, actions } from "./main.js";
import { renderPenOverlay } from "./pen_overlay.js";
import { applyArmDrag, bendSegment, classifyJoin, curvatureHandles, deleteAnchor, joinEnds,
         nearestOnSubpath, reverseSubpath, splitSegment } from "./pen_ops.js";

const $ = (id) => document.getElementById(id);
const BED = { w: 300, h: 218 };
const HIT_PX = 9;          // screen-pixel hit radius for anchor/handle knobs (zoom-invariant)
const DRAG_PX = 3;         // pointer movement past this counts as a drag, not a plain click
const MAX_HANDLE_MM = 400; // UI-side clamp, past the bed diagonal (~371 mm): arms stretch freely, only a runaway drag is caught
const DBL_MS = 400;        // a second click on the same spot within this is a double-click
const BEND_END_T = 0.05;   // a segment grab closer than this (in t) to an end drags that point instead
const NEXT_JOIN = { corner: "smooth", smooth: "symmetric", symmetric: "corner" }; // J's cycle

let on = false;
let wired = false;
let activePenLayerId = null;
let subtract = false; // add/subtract mode — subtract commits as a bite via shape_op
let pending = [];   // uncommitted PenAnchor-shaped objects: {x,y,in_handle,out_handle}
let hoverPt = null;  // last known bed-mm pointer position, for the hover rubber-band
let gesture = null;  // in-progress pointer gesture — see onDown
let committing = false;
let selected = null; // {layerId, si, ai}: the committed point J / Backspace act on
let dragSeq = 0;
// per page load, so a token never matches one from before a reload
const DRAG_NONCE = Math.random().toString(36).slice(2, 10);
/** A fresh coalesce token: every drag is its own undo step (Ruling 10). */
const dragToken = () => `pen-${DRAG_NONCE}-${++dragSeq}`;
let lastClick = null; // {at, x, y}: the previous plain click, for double-click detection
let cont = null;     // {layerId, si, end: "start"|"end"}: continuing that open line —
                     // pending[0] is then a copy of its end point, oriented so
                     // new points append after it

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
  const sub = $("pen-subtract");
  if (sub) sub.onclick = () => setSubtract(!subtract);
  // glyphs are sized in screen px, so any change to px-per-mm (zoom, pan
  // clamp, window resize) re-renders them
  const onView = () => { if (on) redraw(); };
  document.addEventListener("canvas-view-change", onView);
  window.addEventListener("resize", onView);
}

function setSubtract(v) {
  subtract = v;
  const b = $("pen-subtract");
  if (b) {
    b.classList.toggle("on", subtract);
    b.title = subtract
      ? "Subtracting — click or press E to go back to adding"
      : "Adding — click or press E to subtract this shape out of the target layer";
  }
  redraw(); // pending path flips to rust while subtracting
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
  hoverPt = null;
  selected = null;
  // The request owns this draft until it resolves. If the user changes tools
  // meanwhile, keep it available for retry when the Pen tool is reopened.
  if (committing) { renderPenOverlay(null); announcePending(); return; }
  // A direct tool switch still finishes a usable open path. The successful
  // commit path clears pending before it asks the broker to select, and the
  // committing guard prevents that automatic deactivation from saving twice.
  if (!committing && pending.length >= 2) {
    if (cont) commitContinue();
    else commitSubpath(false);
  } else {
    pending = [];
    cont = null;
    renderPenOverlay(null);
  }
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
  if (gesture || committing) return true;
  if (pending.length > (cont ? 1 : 0)) {
    if (!redo) { pending.pop(); redraw(); }
    return true;
  }
  pending = [];
  cont = null;
  selected = null;
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
  if (cont) pending = [];
  cont = null;
  selected = null;
  redraw();
}

export function handlePenEscape() {
  if (gesture) { gesture = null; redraw(); return true; }
  if (pending.length) { pending = []; cont = null; selected = null; redraw(); return true; }
  if (selected) { selected = null; redraw(); return true; }
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
    cont = null;
    redraw();
    actions.completeDrawingTool(null, "pen");
    return;
  }
  if (cont) commitContinue();
  else commitSubpath(false);
}

const isTyping = (t) => t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" ||
                              t.tagName === "SELECT" || t.isContentEditable);

function onKeydown(e) {
  if (!on || committing) return;
  // ⌘Backspace / ⌘Enter / ⌘E are not these keys
  if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
  if (e.key === "Enter" && pending.length && !gesture) {
    e.preventDefault();
    commitPendingPath();
  } else if (e.key === "Backspace" && pending.length && !gesture) {
    e.preventDefault();
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

function activeLayer() {
  const id = currentTargetLayerId();
  return id ? S.state.project.layers.find((l) => l.id === id) : null;
}

function clampBed(x, y) {
  return [Math.min(BED.w, Math.max(0, x)), Math.min(BED.h, Math.max(0, y))];
}

function clampHandle(dx, dy) {
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

function hitDist(editor, x, y, e) {
  const s = toScreen(editor, x, y);
  return Math.hypot(s.x - e.clientX, s.y - e.clientY);
}

// An existing (committed) anchor or handle knob under the pointer, on the
// active pen layer — how re-editing an already-committed shape is found.
// Handle knobs are always FOUND here regardless of modifiers (so a plain
// drag that starts on one doesn't fall through and accidentally begin a new
// anchor) — but onMove only applies the edit while Option is held (handles
// only move with Option; see the modifier scheme note on onMove).
function hitExisting(editor, e) {
  const layer = activeLayer();
  if (!layer) return null;
  const subpaths = layer.source.params.subpaths || [];
  for (let si = 0; si < subpaths.length; si++) {
    const anchors = subpaths[si].anchors;
    for (let ai = 0; ai < anchors.length; ai++) {
      const a = anchors[ai];
      if (a.out_handle && hitDist(editor, a.x + a.out_handle[0], a.y + a.out_handle[1], e) <= HIT_PX) {
        return { kind: "handle", side: "out", si, ai };
      }
      if (a.in_handle && hitDist(editor, a.x + a.in_handle[0], a.y + a.in_handle[1], e) <= HIT_PX) {
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
  for (let ai = 0; ai < pending.length; ai++) {
    const a = pending[ai];
    if (a.out_handle && hitDist(editor, a.x + a.out_handle[0], a.y + a.out_handle[1], e) <= HIT_PX) {
      return { kind: "handle", side: "out", ai };
    }
    if (a.in_handle && hitDist(editor, a.x + a.in_handle[0], a.y + a.in_handle[1], e) <= HIT_PX) {
      return { kind: "handle", side: "in", ai };
    }
    if (hitDist(editor, a.x, a.y, e) <= HIT_PX) {
      return e.altKey ? { kind: "handle", side: "out", ai } : { kind: "anchor", ai };
    }
  }
  return null;
}

// The active layer when it is a PEN layer — the editing gestures (insert,
// bend, joins, delete, continue) only make sense on pen subpaths.
function penLayer() {
  const l = activeLayer();
  return l && l.source?.type === "generator" && l.source.generator === "pen" ? l : null;
}

// The committed point under the pointer (no arm knobs) — what a double-click flips.
function hitAnchor(editor, e) {
  const layer = penLayer();
  if (!layer) return null;
  const subpaths = layer.source.params.subpaths || [];
  for (let si = 0; si < subpaths.length; si++) {
    const anchors = subpaths[si].anchors;
    for (let ai = 0; ai < anchors.length; ai++) {
      if (hitDist(editor, anchors[ai].x, anchors[ai].y, e) <= HIT_PX) return { si, ai };
    }
  }
  return null;
}

// The nearest committed segment within HIT_PX screen px: {si, seg, t}.
function hitSegment(editor, e) {
  const layer = penLayer();
  if (!layer) return null;
  const bed = editor.toBed(e);
  const pxPerMm = editor.pxPerMm();
  let best = null;
  (layer.source.params.subpaths || []).forEach((sp, si) => {
    const r = nearestOnSubpath(sp, bed.x, bed.y);
    if (r.segIndex < 0) return;
    const px = r.dist * pxPerMm;
    if (px <= HIT_PX && (!best || px < best.px)) best = { si, seg: r.segIndex, t: r.t, px };
  });
  return best;
}

// An open line's end point under the pointer, other than `skip` — a join target.
function hitOpenEnd(editor, e, skip) {
  const layer = penLayer();
  if (!layer) return null;
  const subpaths = layer.source.params.subpaths || [];
  for (let si = 0; si < subpaths.length; si++) {
    const sp = subpaths[si];
    if (sp.closed || sp.anchors.length < 2) continue;
    for (const end of /** @type {const} */ (["start", "end"])) {
      if (skip && skip.si === si && skip.end === end) continue;
      const a = end === "start" ? sp.anchors[0] : sp.anchors[sp.anchors.length - 1];
      if (hitDist(editor, a.x, a.y, e) <= HIT_PX) return { si, end };
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
  const editor = actions.canvas();
  const downScreen = { x: e.clientX, y: e.clientY };

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
    // it — which one is only known once the pointer moves (or doesn't)
    const seg = hitSegment(editor, e);
    if (seg) {
      const bed = editor.toBed(e);
      gesture = { kind: "segment", si: seg.si, seg: seg.seg, t: seg.t, downBed: [bed.x, bed.y],
                  moved: false, downScreen, token: dragToken() };
      return;
    }
  }

  // otherwise: start placing a new pending anchor (a click in empty space
  // also drops the point selection)
  selected = null;
  const bed = editor.toBed(e);
  const [x, y] = clampBed(bed.x, bed.y);
  gesture = { kind: "place", x, y, alt: e.altKey, moved: false, downScreen };
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
  const bed = editor.toBed(e);
  const [bx, by] = clampBed(bed.x, bed.y);

  if (gesture.kind === "place" || gesture.kind === "close") {
    if (movedPast(gesture, e)) gesture.moved = true;
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
      applyPendingEditDrag(gesture, bx, by, false);
    } else {
      applyEditDrag(gesture, bx, by, false);
      gesture.dirty = true;
      const layer = activeLayer();
      if (layer) queueRegenerate(layer, { coalesce: gesture.token });
    }
    redraw();
    return;
  }

  // gesture.kind === "handle": Option gates ALL handle manipulation, checked
  // continuously (every move, not just at the initial grab) so toggling it
  // mid-drag works — without it, this drag is inert (release harmlessly,
  // nothing has changed). Shift+Option additionally full-mirrors the OPPOSITE
  // handle (exact reflection — same angle AND length), the classic symmetric
  // smooth node. Applies identically whether the anchor is still pending or
  // already committed — only WHERE the edit lands (locally vs. a server
  // regenerate) differs.
  if (!e.altKey) return;
  if (gesture.target === "pending") {
    applyPendingEditDrag(gesture, bx, by, e.shiftKey);
  } else {
    applyEditDrag(gesture, bx, by, e.shiftKey);
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

  if (g.kind === "place") {
    lastClick = null;
    pending.push(tentativeAnchor(g));
    redraw();
    return;
  }

  if (g.kind === "close") {
    // drag on the closing click curves the closing segment via the first
    // anchor's in_handle only; a plain click (no drag) closes straight
    if (g.moved && g.dragTo) {
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
        cont = null;
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
  const anchor = { x: g.x, y: g.y, in_handle: null, out_handle: null };
  if (g.moved && g.dragTo) {
    const [dx, dy] = clampHandle(g.dragTo[0] - g.x, g.dragTo[1] - g.y);
    anchor.out_handle = [dx, dy];
    if (!g.alt) anchor.in_handle = [-dx, -dy]; // symmetric unless Option broke it
  }
  return anchor;
}

// Core edit math, shared by committed-layer and pending-subpath editing —
// only how the anchor OBJECT is located (and whether a server round-trip
// follows) differs between the two callers below.
function applyAnchorEdit(anchor, g, bx, by, mirror) {
  if (g.kind === "anchor") {
    // offset: a point grabbed from its line (a near-end bend) keeps the
    // grab's distance instead of jumping onto the pointer
    const off = g.offset || [0, 0];
    const [x, y] = clampBed(bx + off[0], by + off[1]);
    anchor.x = x; anchor.y = y;
    return;
  }
  const [dx, dy] = clampHandle(bx - anchor.x, by - anchor.y);
  const draggedKey = `${g.side}_handle`;
  const otherKey = `${g.side === "out" ? "in" : "out"}_handle`;
  anchor[draggedKey] = [dx, dy];
  if (!mirror) return;
  // Full symmetric mirror (Shift+Option): the opposite handle becomes an exact
  // reflection — same angle AND length — the classic smooth-node behaviour.
  anchor[otherKey] = [-dx, -dy];
}

function applyEditDrag(g, bx, by, mirror) {
  const layer = activeLayer();
  if (!layer) return;
  applyAnchorEdit(layer.source.params.subpaths[g.si].anchors[g.ai], g, bx, by, mirror);
}

function applyPendingEditDrag(g, bx, by, mirror) {
  applyAnchorEdit(pending[g.ai], g, bx, by, mirror);
}

// -- committed edits: one ordered regenerate queue -----------------------------
//
// Every committed edit lands through POST /regenerate. Requests go out one at
// a time, in order, each carrying a SNAPSHOT of the params as the edit left
// them, so a quick insert-then-flip can never arrive flipped-then-inserted.
// Consecutive coalesced frames of one drag collapse into the latest (a drag
// is one undo step either way); a discrete edit is always its own request and
// its own undo step.

let regenQueue = []; // [{layerId, params, coalesce}] — coalesce: false | drag token
let regenBusy = false;
let syncOwed = false; // posted edits the local project hasn't been re-read after
let idleWaiters = [];

function queueRegenerate(layer, { coalesce }) {
  const params = JSON.parse(JSON.stringify(layer.source.params));
  const last = regenQueue[regenQueue.length - 1];
  if (coalesce && last && last.coalesce === coalesce && last.layerId === layer.id) last.params = params;
  else regenQueue.push({ layerId: layer.id, params, coalesce });
  kickRegen();
}

function kickRegen() {
  if (!regenBusy) drainRegen();
}

// The local project is AHEAD of the server while edits are queued, so it is
// only replaced by a fresh read when nothing is queued and no gesture is in
// flight; mid-run, only the ink repaints (refreshResolved). An edit made
// during that final read is put back on top of it (reapplyQueued).
async function drainRegen() {
  regenBusy = true;
  let ok = true;
  while (regenQueue.length || (syncOwed && !gesture)) {
    if (regenQueue.length) {
      const job = regenQueue.shift();
      try {
        await api.post(`/api/layers/${job.layerId}/regenerate`, { params: job.params, coalesce: job.coalesce });
      } catch (e) {
        actions.oops(e);
        regenQueue = []; // later snapshots build on the one that failed
        ok = false;
      }
      syncOwed = true;
      if (regenQueue.length || gesture) {
        if (job.coalesce) {
          try { await actions.refreshResolved(); } catch (e) { actions.oops(e); } // live drag repaint
        }
        continue;
      }
    }
    syncOwed = false;
    try {
      await actions.refreshProject();
      reapplyQueued();
      await actions.refreshResolved();
    } catch (e) { actions.oops(e); }
  }
  regenBusy = false;
  const waiters = idleWaiters;
  idleWaiters = [];
  for (const w of waiters) w(ok);
}

// Each queued job's params are the newest local state of its layer: lay them
// back over a just-read project so a refresh never erases a queued edit.
function reapplyQueued() {
  const layers = S.state?.project?.layers || [];
  for (const job of regenQueue) {
    const layer = layers.find((l) => l.id === job.layerId);
    if (layer) layer.source.params = JSON.parse(JSON.stringify(job.params));
  }
  if (regenQueue.length) redraw();
}

/** Resolves (true = every queued edit landed) once the queue is empty. */
function whenIdle() {
  return regenBusy ? new Promise((r) => idleWaiters.push(r)) : Promise.resolve(true);
}

// Replace one subpath list on the local project and queue its regenerate.
function editSubpaths(layer, subpaths, { coalesce = false } = {}) {
  layer.source.params.subpaths = subpaths;
  queueRegenerate(layer, { coalesce });
}

// A copy of `sp` with the anchors at `indices` carrying their classified join
// explicitly, so the edit about to happen keeps the point type the user saw.
function withJoins(sp, indices) {
  const n = sp.anchors.length;
  // a closed line wraps; an open one has nothing before its start or after its end
  const pick = new Set(sp.closed ? indices.map((i) => ((i % n) + n) % n)
    : indices.filter((i) => i >= 0 && i < n));
  return { ...sp, anchors: sp.anchors.map((a, i) => (pick.has(i) ? { ...a, join: classifyJoin(a) } : a)) };
}

const isOpenEnd = (sp, ai) => !sp.closed && (ai === 0 || ai === sp.anchors.length - 1);

// -- E1 insert / E3 bend ---------------------------------------------------------

function insertPoint(g) {
  const layer = penLayer();
  const sp = layer?.source.params.subpaths?.[g.si];
  if (!sp) { redraw(); return; }
  const split = splitSegment(withJoins(sp, [g.seg, g.seg + 1]), g.seg, g.t);
  editSubpaths(layer, layer.source.params.subpaths.map((s, i) => (i === g.si ? split : s)));
  // the new point is selected: Backspace takes it straight back out
  selected = { layerId: layer.id, si: g.si, ai: g.seg + 1 };
  redraw();
}

function segPoint(sp, k, t) {
  const n = sp.anchors.length;
  const a = sp.anchors[k], b = sp.anchors[(k + 1) % n];
  const p1 = a.out_handle ? [a.x + a.out_handle[0], a.y + a.out_handle[1]] : [a.x, a.y];
  const p2 = b.in_handle ? [b.x + b.in_handle[0], b.y + b.in_handle[1]] : [b.x, b.y];
  const u = 1 - t, w = [u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t];
  return [w[0] * a.x + w[1] * p1[0] + w[2] * p2[0] + w[3] * b.x,
          w[0] * a.y + w[1] * p1[1] + w[2] * p2[1] + w[3] * b.y];
}

// First real movement of a segment grab. Near an end the cubic's inner
// controls have almost no leverage (a 1 mm drag would throw a huge arm), so
// the grab becomes a drag of the nearer point instead; returns false then
// with `g` rewritten into an "anchor" gesture.
function startBend(g) {
  const layer = penLayer();
  const sp = layer?.source.params.subpaths?.[g.si];
  if (!sp) { gesture = null; return false; }
  if (g.t < BEND_END_T || g.t > 1 - BEND_END_T) {
    const ai = g.t < BEND_END_T ? g.seg : (g.seg + 1) % sp.anchors.length;
    const a = sp.anchors[ai];
    Object.assign(g, { kind: "anchor", target: "committed", si: g.si, ai,
                       offset: [a.x - g.downBed[0], a.y - g.downBed[1]], moved: true });
    return false;
  }
  g.base = withJoins(sp, [g.seg, g.seg + 1]);
  const grabbed = segPoint(g.base, g.seg, g.t);
  g.grabOff = [grabbed[0] - g.downBed[0], grabbed[1] - g.downBed[1]];
  return true;
}

function applyBend(g, bx, by) {
  const layer = penLayer();
  if (!layer || !layer.source.params.subpaths?.[g.si]) return;
  // always from the grab-time shape, so the bend tracks the pointer exactly
  const bent = bendSegment(g.base, g.seg, g.t, [bx + g.grabOff[0], by + g.grabOff[1]]);
  g.dirty = true;
  editSubpaths(layer, layer.source.params.subpaths.map((s, i) => (i === g.si ? bent : s)),
               { coalesce: g.token });
}

// -- E2 corner ⇄ smooth, E4 select + J, E5 delete ------------------------------

// Double-clicks are detected from pointer clicks (noteClick), not the native
// event: pointer capture and the overlay re-render between the two clicks
// (the first one's target is gone) keep Chromium from firing `dblclick` at
// all. Where a browser does fire it, it must still never reach canvas.js
// (reset view / enter group) while the pen is up — and never flip twice.
function onDblClick(e) {
  if (!on) return;
  e.preventDefault();
  e.stopPropagation();
}

// Record a plain click; true when it completes a double-click (the same
// spot within DBL_MS). A pair is consumed, so a triple click is not two.
// Only a point double-click means anything, and only when nothing is being
// drawn: mid-draw, two quick clicks are just two placed points.
function noteClick(e) {
  const now = performance.now();
  const dbl = !!lastClick && now - lastClick.at < DBL_MS &&
    Math.hypot(e.clientX - lastClick.x, e.clientY - lastClick.y) <= HIT_PX &&
    pending.length <= (cont ? 1 : 0);
  lastClick = dbl ? null : { at: now, x: e.clientX, y: e.clientY };
  return dbl;
}

// The curvature rule's arms for ONE point: tangent ∥ next − prev, a third of
// each side's chord; an open end gets one arm along its chord.
function curvatureArms(sp, ai) {
  const probe = { ...sp, anchors: sp.anchors.map((a, i) => (i === ai ? { ...a, join: "smooth" } : a)) };
  const c = curvatureHandles(probe).anchors[ai];
  return { in_handle: c.in_handle, out_handle: c.out_handle };
}

function setPoint(layer, si, ai, anchor) {
  const subpaths = layer.source.params.subpaths.map((s, i) => (i === si
    ? { ...s, anchors: s.anchors.map((a, j) => (j === ai ? anchor : a)) }
    : s));
  editSubpaths(layer, subpaths);
}

function flipCornerSmooth(si, ai) {
  const layer = penLayer();
  const sp = layer?.source.params.subpaths?.[si];
  if (!sp?.anchors[ai]) { redraw(); return; }
  const a = sp.anchors[ai];
  const next = classifyJoin(a) === "corner"
    ? { ...a, ...curvatureArms(sp, ai), join: "smooth" }
    : { ...a, join: "corner" }; // arms stay: the drawn shape doesn't change
  setPoint(layer, si, ai, next);
  selected = { layerId: layer.id, si, ai };
  redraw();
}

function cycleJoin(si, ai) {
  const layer = penLayer();
  const sp = layer.source.params.subpaths[si];
  const a = sp.anchors[ai];
  const join = NEXT_JOIN[classifyJoin(a)];
  let next;
  if (join === "corner") {
    next = { ...a, join };
  } else {
    // re-mirror the arms to match the new join, led by the out arm
    const opts = { isEnd: isOpenEnd(sp, ai) };
    let src = { ...a, join };
    if (!a.out_handle && !a.in_handle) src = { ...src, ...curvatureArms(sp, ai) };
    next = src.out_handle ? applyArmDrag(src, "out", src.out_handle, false, opts)
      : src.in_handle ? applyArmDrag(src, "in", src.in_handle, false, opts)
        : src;
    next = { ...next, join };
  }
  setPoint(layer, si, ai, next);
  if (cont) armContinue(layer, cont.si, cont.end); // pending[0] mirrors the edited end
  redraw();
}

function deletePoint(si, ai) {
  const layer = penLayer();
  const sp = layer.source.params.subpaths[si];
  const rest = deleteAnchor(withJoins(sp, [ai - 1, ai + 1]), ai);
  // a line left with fewer than two points is gone; an emptied layer stays
  // as an empty pen layer (a blank target, like the "＋ empty layer" button)
  const subpaths = rest.anchors.length < 2
    ? layer.source.params.subpaths.filter((_, i) => i !== si)
    : layer.source.params.subpaths.map((s, i) => (i === si ? rest : s));
  pending = [];
  cont = null;
  selected = null;
  editSubpaths(layer, subpaths);
  redraw();
}

// The selected point, if it is still there on the still-active pen layer.
function selectedPoint() {
  if (!selected) return null;
  const layer = penLayer();
  const a = layer?.id === selected.layerId
    ? layer.source.params.subpaths?.[selected.si]?.anchors[selected.ai] : null;
  if (!a) { selected = null; return null; }
  return selected;
}

function onPointKeydown(e) {
  if (!on || committing || gesture) return;
  if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
  const isJ = e.key === "j" || e.key === "J";
  const isDel = e.key === "Backspace" || e.key === "Delete";
  if (!isJ && !isDel) return;
  // placed-but-uncommitted points are Backspace's (pop) — a continue that
  // has placed nothing yet only holds the selected end itself
  if (pending.length > (cont ? 1 : 0)) return;
  const sel = selectedPoint();
  if (!sel) return;
  e.preventDefault();
  e.stopPropagation();
  if (isJ) cycleJoin(sel.si, sel.ai);
  else deletePoint(sel.si, sel.ai);
}

// -- E6 continue / join ------------------------------------------------------------

function clickPoint(si, ai) {
  const layer = penLayer();
  const sp = layer?.source.params.subpaths?.[si];
  if (!sp?.anchors[ai]) { redraw(); return; }
  selected = { layerId: layer.id, si, ai };
  if (isOpenEnd(sp, ai) && sp.anchors.length >= 2) armContinue(layer, si, ai === 0 ? "start" : "end");
  redraw();
}

// pending = [the line's end point], oriented so placed points follow it
function armContinue(layer, si, end) {
  const sp = layer.source.params.subpaths[si];
  const a = end === "start" ? sp.anchors[0] : sp.anchors[sp.anchors.length - 1];
  const copy = { ...a, in_handle: a.in_handle ? [...a.in_handle] : null,
                 out_handle: a.out_handle ? [...a.out_handle] : null };
  pending = [end === "start" ? { ...copy, in_handle: copy.out_handle, out_handle: copy.in_handle } : copy];
  cont = { layerId: layer.id, si, end };
}

// The continued line with the placed points spliced onto its end (or, from
// the start, prepended — the line keeps its direction).
function mergedContinue(sp) {
  const oriented = cont.end === "start" ? reverseSubpath(sp) : sp;
  const anchors = [...oriented.anchors.slice(0, -1), ...pending.map((a) => ({ ...a }))];
  const merged = { ...oriented, anchors };
  return cont.end === "start" ? reverseSubpath(merged) : merged;
}

async function commitContinue() {
  const layer = penLayer();
  if (!layer || !cont || !layer.source.params.subpaths?.[cont.si]) {
    pending = []; cont = null; redraw(); return;
  }
  const si = cont.si;
  const subpaths = layer.source.params.subpaths.map((s, i) => (i === si ? mergedContinue(s) : s));
  await commitEdit(layer, subpaths);
}

// Continue the line into an open end: a straight segment from the last
// placed point to that end, then joinEnds merges the two coincident points.
// Its own other end closes the line; another line's end makes them one.
async function joinInto(g) {
  const layer = penLayer();
  const subpaths = layer?.source.params.subpaths;
  if (!cont || !subpaths?.[cont.si] || !subpaths[g.si]) { redraw(); return; }
  const target = subpaths[g.si];
  const C = g.end === "start" ? target.anchors[0] : target.anchors[target.anchors.length - 1];
  const meet = { x: C.x, y: C.y, in_handle: null, out_handle: null, join: "corner" };
  const merged = mergedContinue(subpaths[cont.si]);
  merged.anchors = cont.end === "end" ? [...merged.anchors, meet] : [meet, ...merged.anchors];
  let next;
  if (g.si === cont.si) {
    // same object on both sides: joinEnds closes it. Closing fewer than
    // three points would only draw the same line back on itself — ignore it.
    if (merged.anchors.length - 1 < 3) { redraw(); return; }
    const closed = joinEnds(merged, cont.end, merged, cont.end === "end" ? "start" : "end");
    next = subpaths.map((s, i) => (i === g.si ? closed : s));
  } else {
    const joined = joinEnds(merged, cont.end, target, g.end);
    const keep = Math.min(cont.si, g.si);
    next = subpaths.flatMap((s, i) => (i === keep ? [joined] : (i === cont.si || i === g.si) ? [] : [s]));
  }
  await commitEdit(layer, next);
}

// A continue/join is a commit like a finished path: one regenerate (one undo
// step), then the drawing tool completes. A failed write keeps the draft.
async function commitEdit(layer, subpaths) {
  const draft = { pending, cont };
  pending = [];
  cont = null;
  selected = null;
  gesture = null;
  committing = true;
  editSubpaths(layer, subpaths);
  redraw();
  const ok = await whenIdle();
  committing = false;
  if (!ok) {
    ({ pending, cont } = draft);
    redraw();
    return;
  }
  redraw();
  actions.completeDrawingTool(layer.id, "pen");
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

async function commitSubpath(closed) {
  if (!pending.length || committing) return;
  const subpath = { anchors: pending.map((a) => ({ ...a })), closed };
  gesture = null;
  redraw();
  committing = true;
  const id = await commitPenSubpath(subpath);
  committing = false;
  if (!id) { redraw(); return; }
  pending = [];
  redraw();
  actions.completeDrawingTool(id, "pen");
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

// Drop a point selection or a continue that no longer points at anything —
// the target layer changed, or an undo took the point/line away.
function validateEditState(layer) {
  if (selected) selectedPoint();
  if (cont && !committing) {
    const sp = layer?.id === cont.layerId ? layer.source.params.subpaths?.[cont.si] : null;
    if (!sp || sp.closed || sp.anchors.length < 2) { cont = null; pending = []; }
  }
}

function redraw() {
  if (!on) { renderPenOverlay(null); announcePending(); return; }
  const layer = activeLayer();
  validateEditState(layer);
  renderPenOverlay({
    editor: actions.canvas(),
    layerSubpaths: layer ? layer.source.params.subpaths || [] : null,
    pending,
    gesture: gestureView(),
    // no hover rubber-band while any gesture is in flight
    hover: gesture ? null : hoverPt,
    subtract,
    selected: selected && layer?.id === selected.layerId ? { si: selected.si, ai: selected.ai } : null,
    continuing: !!cont,
  });
  announcePending();
}
