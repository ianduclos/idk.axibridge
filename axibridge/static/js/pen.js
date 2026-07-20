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
// own drag-then-commit split.

import { api } from "./api.js";
import { S, actions } from "./main.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const BED = { w: 300, h: 218 };
const HIT_PX = 9;          // screen-pixel hit radius for anchor/handle knobs (zoom-invariant)
const DRAG_PX = 3;         // pointer movement past this counts as a drag, not a plain click
const MAX_HANDLE_MM = 60;  // UI-side clamp: a wild drag can't produce an absurd handle length

let on = false;
let wired = false;
let activePenLayerId = null;
let pending = [];   // uncommitted PenAnchor-shaped objects: {x,y,in_handle,out_handle}
let overlay = null; // persistent <g> appended to editor.world (NOT canvas.js's own
                     // this.overlay, which _renderSelection() clears/repopulates itself)
let hoverPt = null;  // last known bed-mm pointer position, for the hover rubber-band
let gesture = null;  // in-progress pointer gesture — see onDown

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
}

export function activatePenMode() {
  on = true;
  $("canvas-wrap")?.classList.add("pen-mode");
  redraw();
}

export function deactivatePenMode() {
  on = false;
  $("canvas-wrap")?.classList.remove("pen-mode");
  pending = [];
  gesture = null;
  hoverPt = null;
  clearOverlay();
}

// First Escape clears a pending (uncommitted) subpath/in-progress drag
// without leaving the tool; second Escape (nothing pending) falls through to
// main.js's broker, which exits to select mode — two stacked Esc meanings on
// one key, per docs/plans/pen-brush-tools.md Part 0.
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

function onKeydown(e) {
  if (!on) return;
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
  if (e.key === "Enter" && pending.length && !gesture) {
    e.preventDefault();
    commitSubpath(false);
  } else if (e.key === "Backspace" && pending.length && !gesture) {
    e.preventDefault();
    pending.pop();
    redraw();
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
  if (sel && sel.source?.type === "generator" && sel.source?.generator === "pen") {
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

// -- pointer capture -----------------------------------------------------------

function onDown(e, wrap) {
  if (!on || e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  wrap.setPointerCapture(e.pointerId);
  const editor = actions.canvas();

  // closing click: back on the first pending anchor commits the subpath closed
  if (pending.length >= 2 && hitDist(editor, pending[0].x, pending[0].y, e) <= HIT_PX) {
    gesture = null;
    commitSubpath(true);
    return;
  }

  // re-edit an existing committed anchor/handle — only when nothing is
  // pending (finish or Esc-cancel the current shape first: one gesture at a time)
  if (!pending.length) {
    const hit = hitExisting(editor, e);
    if (hit) {
      gesture = { ...hit, downScreen: { x: e.clientX, y: e.clientY } };
      return;
    }
  }

  // otherwise: start placing a new pending anchor
  const bed = editor.toBed(e);
  const [x, y] = clampBed(bed.x, bed.y);
  gesture = { kind: "place", x, y, alt: e.altKey, moved: false, downScreen: { x: e.clientX, y: e.clientY } };
}

function onMove(e) {
  if (!on) return;
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

  if (gesture.kind === "place") {
    if (Math.hypot(e.clientX - gesture.downScreen.x, e.clientY - gesture.downScreen.y) > DRAG_PX) {
      gesture.moved = true;
    }
    gesture.dragTo = [bx, by];
    redraw();
    return;
  }

  applyEditDrag(gesture, bx, by);
  regenerateActiveLayer({ coalesce: true });
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

  // anchor/handle re-edit: final frame closes out the coalesced drag run —
  // still coalesce=true, so it folds into the SAME undo entry as the moves
  // during this drag rather than opening a new one on release.
  regenerateActiveLayer({ coalesce: true });
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

function applyEditDrag(g, bx, by) {
  const layer = activeLayer();
  if (!layer) return;
  const anchor = layer.source.params.subpaths[g.si].anchors[g.ai];
  if (g.kind === "anchor") {
    const [x, y] = clampBed(bx, by);
    anchor.x = x; anchor.y = y;
  } else {
    const [dx, dy] = clampHandle(bx - anchor.x, by - anchor.y);
    if (g.side === "out") anchor.out_handle = [dx, dy];
    else anchor.in_handle = [dx, dy];
  }
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

async function commitSubpath(closed) {
  if (!pending.length) return;
  const subpath = { anchors: pending.map((a) => ({ ...a })), closed };
  pending = [];
  gesture = null;
  redraw();
  try {
    const id = currentTargetLayerId();
    if (id) {
      const layer = S.state.project.layers.find((l) => l.id === id);
      const subpaths = [...(layer.source.params.subpaths || []), subpath];
      // no coalesce: one finished shape = one ⌘Z, exactly like draw.js's per-stroke commit
      await api.post(`/api/layers/${id}/regenerate`, { params: { ...layer.source.params, subpaths } });
    } else {
      const layer = await api.post("/api/layers/generate", { module: "pen", params: { subpaths: [subpath] } });
      activePenLayerId = layer.id;
      actions.setSelection([layer.id]);
    }
    await actions.refreshProject();
    await actions.refreshResolved();
    redraw();
  } catch (e) { actions.oops(e); }
}

// -- overlay: committed anchors/handles (re-edit) + pending shape + rubber-band --

function svgEl(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}
const svgLine = (x1, y1, x2, y2, cls) => svgEl("line", { x1, y1, x2, y2, class: cls });
const svgCircle = (cx, cy, r, cls) => svgEl("circle", { cx, cy, r, class: cls });
const cubicPath = (p0, p1, p2, p3, cls) =>
  svgEl("path", { d: `M ${p0[0]},${p0[1]} C ${p1[0]},${p1[1]} ${p2[0]},${p2[1]} ${p3[0]},${p3[1]}`, class: cls, fill: "none" });

// One cubic segment between two anchors — SVG draws it directly (native "C"
// commands), no need to flatten client-side like the server does for the
// real Path geometry.
function segmentD(a, b) {
  const p1 = a.out_handle ? [a.x + a.out_handle[0], a.y + a.out_handle[1]] : [a.x, a.y];
  const p2 = b.in_handle ? [b.x + b.in_handle[0], b.y + b.in_handle[1]] : [b.x, b.y];
  return `C ${p1[0]},${p1[1]} ${p2[0]},${p2[1]} ${b.x},${b.y}`;
}

// The already-placed segments of the pending subpath. This is what makes
// the shape visible AS you place each anchor, not just once it commits.
function pendingSegmentsD(anchors) {
  if (anchors.length < 2) return null;
  let d = `M ${anchors[0].x},${anchors[0].y}`;
  for (let i = 0; i < anchors.length - 1; i++) d += ` ${segmentD(anchors[i], anchors[i + 1])}`;
  return d;
}

function ensureOverlay(editor) {
  if (overlay && overlay.isConnected) return overlay;
  overlay = svgEl("g", { class: "pen-overlay" });
  editor.world.appendChild(overlay);
  return overlay;
}

function clearOverlay() {
  if (overlay) overlay.innerHTML = "";
}

function drawHandle(g, a, h) {
  const hx = a.x + h[0], hy = a.y + h[1];
  g.appendChild(svgLine(a.x, a.y, hx, hy, "pen-handle-line"));
  g.appendChild(svgCircle(hx, hy, 0.7, "pen-handle-knob"));
}

function redraw() {
  if (!on) { clearOverlay(); return; }
  const editor = actions.canvas();
  const g = ensureOverlay(editor);
  g.innerHTML = "";

  // committed anchors/handles for the active (selected) pen layer — the
  // "post-commit overlay" that makes re-editing possible
  const layer = activeLayer();
  if (layer) {
    for (const sp of layer.source.params.subpaths || []) {
      for (const a of sp.anchors) {
        if (a.out_handle) drawHandle(g, a, a.out_handle);
        if (a.in_handle) drawHandle(g, a, a.in_handle);
      }
      for (const a of sp.anchors) {
        g.appendChild(svgCircle(a.x, a.y, 1.3, "pen-anchor" + ((a.in_handle || a.out_handle) ? " smooth" : "")));
      }
    }
  }

  // the current uncommitted subpath: the segments placed so far, then
  // anchors/handles on top
  const pendingD = pendingSegmentsD(pending);
  if (pendingD) g.appendChild(svgEl("path", { d: pendingD, class: "pen-pending-path", fill: "none" }));
  for (const a of pending) {
    if (a.out_handle) drawHandle(g, a, a.out_handle);
    if (a.in_handle) drawHandle(g, a, a.in_handle);
  }
  for (let i = 0; i < pending.length; i++) {
    const a = pending[i];
    g.appendChild(svgCircle(a.x, a.y, i === 0 ? 1.6 : 1.3, "pen-pending-anchor"));
  }

  if (gesture?.kind === "place") {
    // live preview of the anchor being placed: the actual curve segment
    // from the last already-placed anchor (using tentativeAnchor's in/out
    // handles, exactly what commit will use), plus its own handle guide —
    // not just a bare drag-handle line with no sense of the resulting shape
    const tentative = tentativeAnchor(gesture);
    if (pending.length) {
      const last = pending[pending.length - 1];
      g.appendChild(svgEl("path", {
        d: `M ${last.x},${last.y} ${segmentD(last, tentative)}`, class: "pen-pending-path", fill: "none",
      }));
    }
    if (tentative.out_handle) drawHandle(g, tentative, tentative.out_handle);
    g.appendChild(svgCircle(tentative.x, tentative.y, 1.3, "pen-pending-anchor"));
  } else if (!gesture && pending.length && hoverPt) {
    // hover rubber-band: preview the next segment from the last pending
    // anchor to the pointer, shaped by that anchor's own out_handle
    const last = pending[pending.length - 1];
    const p1 = last.out_handle ? [last.x + last.out_handle[0], last.y + last.out_handle[1]] : [last.x, last.y];
    g.appendChild(cubicPath([last.x, last.y], p1, hoverPt, hoverPt, "pen-rubber-band"));
  }
}
