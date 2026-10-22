// The pen's editing gestures on a committed pen layer (pen v2 E1–E6):
//   click a line          → add a point there (de Casteljau, shape unchanged)
//   drag a line           → bend that segment (one undo step per drag); a
//                           grab near an end (t < 0.05 / > 0.95) moves the
//                           nearer point instead, where a bend has no leverage
//   click a point         → select it (ring); J cycles its join, Backspace/
//                           Delete removes it with a refit of its neighbours
//   double-click a point  → corner ⇄ smooth
//   click an open end     → continue the line from there (Bézier/curvature
//                           modes; sketch and knife only select); clicking an
//                           open end (its own other end, or another line's) joins
// A curvature-pen subpath (`kind: "curvature"`) is edited the same way, but
// its arms are always the curvature rule's: every edit that changes one
// re-runs curvatureHandles (editSubpaths) before it is queued, a corner is
// only an explicit `join: "corner"`, and a drag on its line adds a point
// there and moves it (the curvature pen's push-pull) instead of bending.
// Every committed edit is one regenerate (pen_queue.js); edits write the
// point's classified `join` explicitly so a later edit keeps what the user saw.
//
// pen.js owns the drawing state (on, pending, gesture, committing) and the
// pointer dispatch; this module owns the edit state (the selected point, the
// continue, the last click) and is called from that dispatch. Like every pen
// gesture it works in bed mm: subpaths are read with bedSubpaths and written
// with editSubpaths (pen_space.js), never through the layer's params directly.

import { actions } from "./main.js";
import { applyArmDrag, bendSegment, classifyJoin, curvatureHandles, deleteAnchor, joinEnds,
         nearestOnSubpath, reverseSubpath, splitSegment } from "./pen_ops.js";
import { HIT_PX, activeLayer, committing, gesture, hitDist, isTyping, on, pending, penMode, redraw,
         setCommitting, setGesture, setPending, shapedPending } from "./pen.js";
import { queueRegenerate, whenIdle } from "./pen_queue.js";
import { bedSubpaths, setBedSubpaths } from "./pen_space.js";
import { endRefit } from "./pen_sketch.js";

export const DBL_MS = 400;        // a second click on the same spot within this is a double-click
const BEND_END_T = 0.05;   // a segment grab closer than this (in t) to an end drags that point instead
const NEXT_JOIN = { corner: "smooth", smooth: "symmetric", symmetric: "corner" }; // J's cycle

export let selected = null; // {layerId, si, ai}: the committed point J / Backspace act on
export let cont = null;     // {layerId, si, end: "start"|"end"}: continuing that open line —
                            // pending[0] is then a copy of its end point, oriented so
                            // new points append after it
let lastClick = null;       // {at, x, y}: the previous plain click, for double-click detection
/** @param {any} v */ export const setSelected = (v) => { selected = v; };
/** @param {any} v */ export const setCont = (v) => { cont = v; };
export const forgetClick = () => { lastClick = null; };

let dragSeq = 0;
// per page load, so a token never matches one from before a reload
const DRAG_NONCE = Math.random().toString(36).slice(2, 10);
/** A fresh coalesce token: every drag is its own undo step (Ruling 10). */
export const dragToken = () => `pen-${DRAG_NONCE}-${++dragSeq}`;

// The active layer when it is a PEN layer — the editing gestures (insert,
// bend, joins, delete, continue) only make sense on pen subpaths.
function penLayer() {
  const l = activeLayer();
  return l && l.source?.type === "generator" && l.source.generator === "pen" ? l : null;
}

// The committed point under the pointer (no arm knobs) — what a double-click flips.
export function hitAnchor(editor, e) {
  const layer = penLayer();
  if (!layer) return null;
  const subpaths = bedSubpaths(layer);
  for (let si = 0; si < subpaths.length; si++) {
    const anchors = subpaths[si].anchors;
    for (let ai = 0; ai < anchors.length; ai++) {
      if (hitDist(editor, anchors[ai].x, anchors[ai].y, e) <= HIT_PX) return { si, ai };
    }
  }
  return null;
}

// The nearest committed segment within HIT_PX screen px: {si, seg, t}.
export function hitSegment(editor, e) {
  const layer = penLayer();
  if (!layer) return null;
  const bed = editor.toBed(e);
  const pxPerMm = editor.pxPerMm();
  let best = null;
  bedSubpaths(layer).forEach((sp, si) => {
    const r = nearestOnSubpath(sp, bed.x, bed.y);
    if (r.segIndex < 0) return;
    const px = r.dist * pxPerMm;
    if (px <= HIT_PX && (!best || px < best.px)) best = { si, seg: r.segIndex, t: r.t, px };
  });
  return best;
}

// An open line's end point under the pointer, other than `skip` — a join target.
export function hitOpenEnd(editor, e, skip) {
  const layer = penLayer();
  if (!layer) return null;
  const subpaths = bedSubpaths(layer);
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

/** A curvature subpath with its arms re-derived; any other one as it is. */
const reshape = (sp) => (sp.kind === "curvature" ? curvatureHandles(sp) : sp);

// Replace one subpath list (bed mm) on the local project and queue its
// regenerate. Every subpath the edit replaced is reshaped first, so a
// curvature line's arms always follow its points; untouched ones (the same
// views bedSubpaths handed out) are left exactly as they are.
function editSubpaths(layer, subpaths, { coalesce = false } = {}) {
  const before = new Set(bedSubpaths(layer));
  setBedSubpaths(layer, subpaths.map((s) => (before.has(s) ? s : reshape(s))));
  queueRegenerate(layer, { coalesce });
}

// A copy of `sp` with the anchors at `indices` carrying their classified join
// explicitly, so the edit about to happen keeps the point type the user saw.
// Not on a curvature subpath: there only an explicit corner is a corner, and
// labelling a one-armed open end "corner" would stick once it is continued.
function withJoins(sp, indices) {
  if (sp.kind === "curvature") return sp;
  const n = sp.anchors.length;
  // a closed line wraps; an open one has nothing before its start or after its end
  const pick = new Set(sp.closed ? indices.map((i) => ((i % n) + n) % n)
    : indices.filter((i) => i >= 0 && i < n));
  return { ...sp, anchors: sp.anchors.map((a, i) => (pick.has(i) ? { ...a, join: classifyJoin(a) } : a)) };
}

const isOpenEnd = (sp, ai) => !sp.closed && (ai === 0 || ai === sp.anchors.length - 1);

// -- E1 insert / E3 bend ---------------------------------------------------------

export function insertPoint(g) {
  const layer = penLayer();
  const sp = bedSubpaths(layer)[g.si];
  if (!sp) { redraw(); return; }
  const split = splitSegment(withJoins(sp, [g.seg, g.seg + 1]), g.seg, g.t);
  editSubpaths(layer, bedSubpaths(layer).map((s, i) => (i === g.si ? split : s)));
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
export function startBend(g) {
  const layer = penLayer();
  const sp = bedSubpaths(layer)[g.si];
  if (!sp) { setGesture(null); return false; }
  if (g.t < BEND_END_T || g.t > 1 - BEND_END_T) {
    const ai = g.t < BEND_END_T ? g.seg : (g.seg + 1) % sp.anchors.length;
    const a = sp.anchors[ai];
    Object.assign(g, { kind: "anchor", target: "committed", si: g.si, ai,
                       offset: [a.x - g.downBed[0], a.y - g.downBed[1]], moved: true });
    return false;
  }
  if (sp.kind === "curvature") {
    // the curvature pen's push-pull: a point is added where the line was
    // grabbed and the drag moves it (same token: insert + drag = one undo)
    const split = splitSegment(sp, g.seg, g.t);
    const ai = g.seg + 1;
    const a = split.anchors[ai];
    editSubpaths(layer, bedSubpaths(layer).map((s, i) => (i === g.si ? split : s)),
                 { coalesce: g.token });
    selected = { layerId: layer.id, si: g.si, ai };
    Object.assign(g, { kind: "anchor", target: "committed", si: g.si, ai,
                       offset: [a.x - g.downBed[0], a.y - g.downBed[1]], moved: true });
    return false;
  }
  g.base = withJoins(sp, [g.seg, g.seg + 1]);
  const grabbed = segPoint(g.base, g.seg, g.t);
  g.grabOff = [grabbed[0] - g.downBed[0], grabbed[1] - g.downBed[1]];
  return true;
}

export function applyBend(g, bx, by) {
  const layer = penLayer();
  if (!layer || !bedSubpaths(layer)[g.si]) return;
  // always from the grab-time shape, so the bend tracks the pointer exactly
  const bent = bendSegment(g.base, g.seg, g.t, [bx + g.grabOff[0], by + g.grabOff[1]]);
  g.dirty = true;
  editSubpaths(layer, bedSubpaths(layer).map((s, i) => (i === g.si ? bent : s)),
               { coalesce: g.token });
}

// -- E2 corner ⇄ smooth, E4 select + J, E5 delete ------------------------------

// Double-clicks are detected from pointer clicks (noteClick), not the native
// event: pointer capture and the overlay re-render between the two clicks
// (the first one's target is gone) keep Chromium from firing `dblclick` at
// all. Where a browser does fire it, it must still never reach canvas.js
// (reset view / enter group) while the pen is up — and never flip twice.
export function onDblClick(e) {
  if (!on) return;
  e.preventDefault();
  e.stopPropagation();
}

// Record a plain click; true when it completes a double-click (the same
// spot within DBL_MS). A pair is consumed, so a triple click is not two.
// Only a point double-click means anything, and only when nothing is being
// drawn: mid-draw, two quick clicks are just two placed points.
export function noteClick(e) {
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
  const subpaths = bedSubpaths(layer).map((s, i) => (i === si
    ? { ...s, anchors: s.anchors.map((a, j) => (j === ai ? anchor : a)) }
    : s));
  editSubpaths(layer, subpaths);
}

// A curvature point is a corner only when it says so; the rule draws its arms.
const flipCurvatureJoin = (a) => ({ ...a, join: a.join === "corner" ? "smooth" : "corner" });

export function flipCornerSmooth(si, ai) {
  const layer = penLayer();
  const sp = bedSubpaths(layer)[si];
  if (!sp?.anchors[ai]) { redraw(); return; }
  const a = sp.anchors[ai];
  const next = sp.kind === "curvature" ? flipCurvatureJoin(a)
    : classifyJoin(a) === "corner"
      ? { ...a, ...curvatureArms(sp, ai), join: "smooth" }
      : { ...a, join: "corner" }; // arms stay: the drawn shape doesn't change
  setPoint(layer, si, ai, next);
  selected = { layerId: layer.id, si, ai };
  redraw();
}

function cycleJoin(si, ai) {
  const layer = penLayer();
  const sp = bedSubpaths(layer)[si];
  const a = sp.anchors[ai];
  const join = NEXT_JOIN[classifyJoin(a)];
  let next;
  if (sp.kind === "curvature") {
    next = flipCurvatureJoin(a); // corner ⇄ smooth only: symmetric means nothing here
  } else if (join === "corner") {
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
  const sp = bedSubpaths(layer)[si];
  const rest = deleteAnchor(withJoins(sp, [ai - 1, ai + 1]), ai);
  // a line left with fewer than two points is gone; an emptied layer stays
  // as an empty pen layer (a blank target, like the "＋ empty layer" button)
  const subpaths = rest.anchors.length < 2
    ? bedSubpaths(layer).filter((_, i) => i !== si)
    : bedSubpaths(layer).map((s, i) => (i === si ? rest : s));
  setPending([]);
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
    ? bedSubpaths(layer)[selected.si]?.anchors[selected.ai] : null;
  if (!a) { selected = null; return null; }
  return selected;
}

export function onPointKeydown(e) {
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
  endRefit(); // a key edit is the next pen action
  if (isJ) cycleJoin(sel.si, sel.ai);
  else deletePoint(sel.si, sel.ai);
}

// -- E6 continue / join ------------------------------------------------------------

/** Select a committed point; `arm` (the mode places points) also arms a
 *  continue when it is an open end. */
export function clickPoint(si, ai, { arm = true } = {}) {
  const layer = penLayer();
  const sp = bedSubpaths(layer)[si];
  if (!sp?.anchors[ai]) { redraw(); return; }
  selected = { layerId: layer.id, si, ai };
  if (arm && isOpenEnd(sp, ai) && sp.anchors.length >= 2) armContinue(layer, si, ai === 0 ? "start" : "end");
  redraw();
}

// pending = [the line's end point], oriented so placed points follow it
function armContinue(layer, si, end) {
  const sp = bedSubpaths(layer)[si];
  const a = end === "start" ? sp.anchors[0] : sp.anchors[sp.anchors.length - 1];
  const copy = { ...a, in_handle: a.in_handle ? [...a.in_handle] : null,
                 out_handle: a.out_handle ? [...a.out_handle] : null };
  setPending([end === "start" ? { ...copy, in_handle: copy.out_handle, out_handle: copy.in_handle } : copy]);
  cont = { layerId: layer.id, si, end };
}

// The continued line with the placed points spliced onto its end (or, from
// the start, prepended — the line keeps its direction). The placed points
// come from shapedPending, the same arms the preview showed. A curvature
// line continued in curvature mode stays one (editSubpaths re-bends it
// whole, which is what shapedPending previewed); any other mix — or points
// kept from Bézier mode (`fixed`) — is a Bézier line that keeps its shape.
function mergedContinue(sp) {
  const oriented = cont.end === "start" ? reverseSubpath(sp) : sp;
  const curvature = sp.kind === "curvature" && penMode === "curvature" && !pending.some((a) => a.fixed);
  const anchors = [...oriented.anchors.slice(0, -1), ...shapedPending()];
  const merged = reshape({ ...oriented, anchors, kind: curvature ? "curvature" : "bezier" });
  return cont.end === "start" ? reverseSubpath(merged) : merged;
}

/** @param {{stay?: boolean}} [opts] stay: keep the pen up afterwards */
export async function commitContinue({ stay = false } = {}) {
  const layer = penLayer();
  if (!layer || !cont || !bedSubpaths(layer)[cont.si]) {
    setPending([]); cont = null; redraw(); return;
  }
  const si = cont.si;
  const subpaths = bedSubpaths(layer).map((s, i) => (i === si ? mergedContinue(s) : s));
  await commitEdit(layer, subpaths, { stay });
}

// Continue the line into an open end: a straight segment from the last
// placed point to that end, then joinEnds merges the two coincident points.
// Its own other end closes the line; another line's end makes them one.
export async function joinInto(g) {
  const layer = penLayer();
  const subpaths = layer ? bedSubpaths(layer) : null;
  if (!cont || !subpaths?.[cont.si] || !subpaths[g.si]) { redraw(); return; }
  const target = subpaths[g.si];
  const C = g.end === "start" ? target.anchors[0] : target.anchors[target.anchors.length - 1];
  const meet = { x: C.x, y: C.y, in_handle: null, out_handle: null, join: "corner" };
  const merged = mergedContinue(subpaths[cont.si]);
  merged.anchors = cont.end === "end" ? [...merged.anchors, meet] : [meet, ...merged.anchors];
  // a curvature result has no corner where the ends met: it is smooth like
  // every other point the curvature pen placed
  const smoothMeet = (sp, i) => (sp.kind === "curvature"
    ? { ...sp, anchors: sp.anchors.map((a, j) => (j === i ? { ...a, join: null } : a)) } : sp);
  let next;
  if (g.si === cont.si) {
    // same object on both sides: joinEnds closes it. Closing fewer than
    // three points would only draw the same line back on itself — ignore it.
    if (merged.anchors.length - 1 < 3) { redraw(); return; }
    const closed = smoothMeet(joinEnds(merged, cont.end, merged, cont.end === "end" ? "start" : "end"), 0);
    next = subpaths.map((s, i) => (i === g.si ? closed : s));
  } else {
    // joining a curvature line to a Bézier one gives a Bézier line: it keeps
    // the drawn shape of both
    const kind = merged.kind === "curvature" && target.kind === "curvature" ? "curvature" : "bezier";
    const joined = smoothMeet({ ...joinEnds(merged, cont.end, target, g.end), kind },
                              merged.anchors.length - 1);
    const keep = Math.min(cont.si, g.si);
    next = subpaths.flatMap((s, i) => (i === keep ? [joined] : (i === cont.si || i === g.si) ? [] : [s]));
  }
  await commitEdit(layer, next);
}

// A continue/join is a commit like a finished path: one regenerate (one undo
// step), then the drawing tool completes. A failed write keeps the draft.
async function commitEdit(layer, subpaths, { stay = false } = {}) {
  const draft = { pending, cont };
  setPending([]);
  cont = null;
  selected = null;
  setGesture(null);
  setCommitting(true);
  editSubpaths(layer, subpaths);
  redraw();
  const ok = await whenIdle();
  setCommitting(false);
  if (!ok) {
    setPending(draft.pending);
    cont = draft.cont;
    redraw();
    return;
  }
  redraw();
  if (!stay) actions.completeDrawingTool(layer.id, "pen");
}

// Drop a point selection or a continue that no longer points at anything —
// the target layer changed, or an undo took the point/line away.
export function validateEditState(layer) {
  if (selected) selectedPoint();
  if (cont && !committing) {
    const sp = layer?.id === cont.layerId ? bedSubpaths(layer)[cont.si] : null;
    if (!sp || sp.closed || sp.anchors.length < 2) { cont = null; setPending([]); }
  }
}
