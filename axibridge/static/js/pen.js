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

import { api } from "./api.js";
import { S, actions } from "./main.js";
import { renderPenOverlay } from "./pen_overlay.js";

const $ = (id) => document.getElementById(id);
const BED = { w: 300, h: 218 };
const HIT_PX = 9;          // screen-pixel hit radius for anchor/handle knobs (zoom-invariant)
const DRAG_PX = 3;         // pointer movement past this counts as a drag, not a plain click
const MAX_HANDLE_MM = 400; // UI-side clamp, past the bed diagonal (~371 mm): arms stretch freely, only a runaway drag is caught

let on = false;
let wired = false;
let activePenLayerId = null;
let subtract = false; // add/subtract mode — subtract commits as a bite via shape_op
let pending = [];   // uncommitted PenAnchor-shaped objects: {x,y,in_handle,out_handle}
let hoverPt = null;  // last known bed-mm pointer position, for the hover rubber-band
let gesture = null;  // in-progress pointer gesture — see onDown
let committing = false;

export function initPenMode() {
  if (wired) return;
  const wrap = $("canvas-wrap");
  if (!wrap) return; // stale cached index.html: degrade silently
  wired = true;
  wrap.addEventListener("pointerdown", (e) => onDown(e, wrap), true);
  wrap.addEventListener("pointermove", (e) => onMove(e), true);
  wrap.addEventListener("pointerup", (e) => onUp(e), true);
  wrap.addEventListener("pointercancel", () => onCancel(), true);
  document.addEventListener("keydown", onKeydown);
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
  // The request owns this draft until it resolves. If the user changes tools
  // meanwhile, keep it available for retry when the Pen tool is reopened.
  if (committing) { renderPenOverlay(null); announcePending(); return; }
  // A direct tool switch still finishes a usable open path. The successful
  // commit path clears pending before it asks the broker to select, and the
  // committing guard prevents that automatic deactivation from saving twice.
  if (!committing && pending.length >= 2) {
    commitSubpath(false);
  } else {
    pending = [];
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

export function handlePenEscape() {
  if (gesture) { gesture = null; redraw(); return true; }
  if (pending.length) { pending = []; redraw(); return true; }
  return false;
}

/** Finish the pending subpath as an open line — what Enter does, exposed for
 *  the toolbar's Commit button. Closing into a shape stays the on-canvas
 *  gesture (click the first anchor), which is where the closing curve drag
 *  lives; a button can't express that. */
export function commitPendingPath() {
  if (!on || gesture || !pending.length || committing) return;
  if (pending.length < 2) {
    pending = [];
    redraw();
    actions.completeDrawingTool(null, "pen");
    return;
  }
  commitSubpath(false);
}

function onKeydown(e) {
  if (!on || committing) return;
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
  if (e.key === "Enter" && pending.length && !gesture) {
    e.preventDefault();
    commitPendingPath();
  } else if (e.key === "Backspace" && pending.length && !gesture) {
    e.preventDefault();
    pending.pop();
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

// -- pointer capture -----------------------------------------------------------

function onDown(e, wrap) {
  if (!on || committing || e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  wrap.setPointerCapture(e.pointerId);
  const editor = actions.canvas();

  // closing click: back on the first pending anchor. A plain click commits
  // closed immediately; a click-DRAG curves JUST the closing segment by
  // pulling the first anchor's in_handle — one spline, so the already-drawn
  // first segment (governed by the first anchor's out_handle) is untouched.
  if (pending.length >= 2 && hitDist(editor, pending[0].x, pending[0].y, e) <= HIT_PX) {
    gesture = { kind: "close", moved: false, downScreen: { x: e.clientX, y: e.clientY } };
    return;
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
      gesture = { ...hit, target: "committed", downScreen: { x: e.clientX, y: e.clientY } };
      return;
    }
  }

  // otherwise: start placing a new pending anchor
  const bed = editor.toBed(e);
  const [x, y] = clampBed(bed.x, bed.y);
  gesture = { kind: "place", x, y, alt: e.altKey, moved: false, downScreen: { x: e.clientX, y: e.clientY } };
}

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
    if (Math.hypot(e.clientX - gesture.downScreen.x, e.clientY - gesture.downScreen.y) > DRAG_PX) {
      gesture.moved = true;
    }
    gesture.dragTo = [bx, by];
    redraw();
    return;
  }

  if (gesture.kind === "anchor") {
    if (gesture.target === "pending") {
      applyPendingEditDrag(gesture, bx, by, false);
    } else {
      applyEditDrag(gesture, bx, by, false);
      gesture.dirty = true;
      regenerateActiveLayer({ coalesce: true });
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
    regenerateActiveLayer({ coalesce: true });
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

  // final frame closes out the coalesced drag run — still coalesce=true, so
  // it folds into the SAME undo entry as the moves during this drag rather
  // than opening a new one on release. Skipped entirely if nothing was ever
  // actually applied (e.g. a handle grabbed but Option never held) — no
  // point creating a checkpoint for a drag that changed nothing.
  if (g.dirty) regenerateActiveLayer({ coalesce: true });
  redraw();
}

function onCancel() {
  gesture = null;
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
    const [x, y] = clampBed(bx, by);
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

async function regenerateActiveLayer({ coalesce }) {
  const layer = activeLayer();
  if (!layer) return;
  try {
    await api.post(`/api/layers/${layer.id}/regenerate`, { params: layer.source.params, coalesce });
    await actions.refreshProject();
    await actions.refreshResolved();
  } catch (e) { actions.oops(e); }
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

function redraw() {
  if (!on) { renderPenOverlay(null); announcePending(); return; }
  const layer = activeLayer();
  renderPenOverlay({
    editor: actions.canvas(),
    layerSubpaths: layer ? layer.source.params.subpaths || [] : null,
    pending,
    gesture: gestureView(),
    // no hover rubber-band while any gesture is in flight
    hover: gesture ? null : hoverPt,
    subtract,
    selected: null,
  });
  announcePending();
}
