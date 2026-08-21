// Shape mode: drag out a rectangle, an ellipse or a straight line.
//
// There is almost no new machinery here, deliberately. A rectangle is four
// corner anchors and an ellipse is four anchors with kappa handles, so both
// are ordinary PEN SUBPATHS produced by a different gesture — they commit
// through pen.js's own commitPenSubpath and therefore union, subtract and
// convert against brush blobs and pen shapes exactly as a hand-drawn pen path
// does, and their corners stay grabbable with the Pen tool afterwards.
//
// The straight line takes the other seam (Ian's call): a line has no interior
// to union, so it is a two-point STROKE committed through draw.js, landing on
// a drawing layer like anything else drawn. That is why Subtract greys out on
// Line — there is nothing to bite with.
//
// Same capture-phase interception as draw.js and brush.js: listeners on
// #canvas-wrap with stopPropagation, so canvas.js's own drag/marquee code
// never sees the events while the mode is on, and pointer -> mm goes through
// CanvasEditor.toBed so portrait and landscape both land correctly.

import { commitDrawStroke } from "./draw.js";
import { actions } from "./main.js";
import { commitPenSubpath } from "./pen.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const BED = { w: 300, h: 218 };

// The circle constant: control handles this fraction of the radius put a
// cubic Bezier within ~0.02% of a true quarter arc. Four of them is the
// standard circle, and it survives the layer transform as a curve rather
// than as a polygon approximation frozen at capture time.
const KAPPA = 0.5522847498307936;

// Below this the drag was a click, not a shape — committing it would leave a
// degenerate silhouette that shapely drops anyway, minus an undo step.
const MIN_SIZE = 0.5;

const KINDS = ["rect", "ellipse", "line"];

let on = false;
let kind = "rect";
let subtract = false;
let drag = null;  // { x0, y0, liveEl, groupEl, pointerId, t0 }
let wired = false; // initTabs() re-runs on every SSE reconnect — wire once

export function initShapeMode() {
  if (wired) return;
  const wrap = $("canvas-wrap");
  if (!wrap) return; // stale cached index.html: degrade silently
  wired = true;

  for (const k of KINDS) {
    const btn = $(`shape-${k}`);
    if (btn) btn.onclick = () => setKind(k);
  }
  const sub = $("shape-subtract");
  if (sub) sub.onclick = () => setSubtract(!subtract);
  syncBar();

  wrap.addEventListener("pointerdown", (e) => onDown(e, wrap), true);
  wrap.addEventListener("pointermove", (e) => onMove(e), true);
  wrap.addEventListener("pointerup", (e) => onUp(e), true);
  wrap.addEventListener("pointercancel", () => cancelDrag(), true);

  // R / O / L pick the primitive and E flips subtract — the same one-key
  // habits the brush ([ ] E) and pen (E) already teach. Guarded on `on`, so
  // the letters stay free everywhere else.
  document.addEventListener("keydown", (e) => {
    if (!on || e.metaKey || e.ctrlKey || e.altKey) return;
    const key = e.key.toLowerCase();
    const pick = { r: "rect", o: "ellipse", l: "line" }[key];
    if (pick) { e.preventDefault(); setKind(pick); }
    else if (key === "e") { e.preventDefault(); setSubtract(!subtract); }
  });
}

export function activateShapeMode() { on = true; syncBar(); }

export function deactivateShapeMode() {
  on = false;
  cancelDrag();
}

// Escape clears an in-flight drag without leaving the tool; only a second
// press (nothing pending) falls through to "exit to select".
export function handleShapeEscape() {
  if (!drag) return false;
  cancelDrag();
  return true;
}

function setKind(next) {
  if (!KINDS.includes(next) || next === kind) return;
  kind = next;
  syncBar();
}

function setSubtract(next) {
  subtract = next;
  syncBar();
}

function syncBar() {
  for (const k of KINDS) $(`shape-${k}`)?.classList.toggle("on", k === kind);
  const sub = $("shape-subtract");
  if (!sub) return;
  // a line has no interior, so there is nothing for it to bite with
  sub.disabled = kind === "line";
  sub.classList.toggle("on", subtract && kind !== "line");
  sub.title = subtract
    ? "Subtracting — click or press E to add instead"
    : "Adding — click or press E to subtract this shape out of the target layer";
}

const clamp = (v, hi) => Math.min(hi, Math.max(0, v));

// -- the drag rectangle, with the two modifiers every drawing app uses --------

function boxFor(e, editor) {
  const p = editor.toBed(e);
  let dx = p.x - drag.x0;
  let dy = p.y - drag.y0;
  if (e.shiftKey) {
    if (kind === "line") {
      // constrain to 45 degree steps, measured from the start point
      const a = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
      const r = Math.hypot(dx, dy);
      dx = r * Math.cos(a);
      dy = r * Math.sin(a);
    } else {
      const m = Math.max(Math.abs(dx), Math.abs(dy));
      dx = Math.sign(dx) * m || m;
      dy = Math.sign(dy) * m || m;
    }
  }
  if (kind === "line") {
    return { x0: drag.x0, y0: drag.y0, x1: clamp(drag.x0 + dx, BED.w), y1: clamp(drag.y0 + dy, BED.h) };
  }
  // Alt draws from the centre: the start point stays put and the box grows
  // around it, instead of the start being one corner.
  const a = e.altKey ? { x: drag.x0 - dx, y: drag.y0 - dy } : { x: drag.x0, y: drag.y0 };
  const b = { x: drag.x0 + dx, y: drag.y0 + dy };
  return {
    x0: clamp(Math.min(a.x, b.x), BED.w), y0: clamp(Math.min(a.y, b.y), BED.h),
    x1: clamp(Math.max(a.x, b.x), BED.w), y1: clamp(Math.max(a.y, b.y), BED.h),
  };
}

// -- primitives --------------------------------------------------------------

const anchor = (x, y, inH, outH) => ({ x, y, in_handle: inH, out_handle: outH });

export function rectAnchors(box) {
  const { x0, y0, x1, y1 } = box;
  return [anchor(x0, y0, null, null), anchor(x1, y0, null, null),
          anchor(x1, y1, null, null), anchor(x0, y1, null, null)];
}

export function ellipseAnchors(box) {
  const cx = (box.x0 + box.x1) / 2;
  const cy = (box.y0 + box.y1) / 2;
  const rx = (box.x1 - box.x0) / 2;
  const ry = (box.y1 - box.y0) / 2;
  const hx = KAPPA * rx;
  const hy = KAPPA * ry;
  // clockwise from the top in screen coords (y down): each handle is the
  // tangent at that quarter point, which is what makes the four arcs meet
  // smoothly instead of showing four corners
  return [
    anchor(cx, cy - ry, [-hx, 0], [hx, 0]),
    anchor(cx + rx, cy, [0, -hy], [0, hy]),
    anchor(cx, cy + ry, [hx, 0], [-hx, 0]),
    anchor(cx - rx, cy, [0, hy], [0, -hy]),
  ];
}

// -- pointer capture ---------------------------------------------------------

function onDown(e, wrap) {
  if (!on || e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  wrap.setPointerCapture(e.pointerId);
  const editor = actions.canvas();
  const p = editor.toBed(e);
  const g = document.createElementNS(NS, "g");
  g.classList.toggle("subtracting", subtract && kind !== "line");
  const live = document.createElementNS(NS, kind === "line" ? "line"
                                          : kind === "ellipse" ? "ellipse" : "rect");
  live.setAttribute("class", kind === "line" ? "draw-line draw-live" : "pen-pending-path");
  g.appendChild(live);
  editor.world.appendChild(g);
  drag = { x0: clamp(p.x, BED.w), y0: clamp(p.y, BED.h), liveEl: live, groupEl: g,
           pointerId: e.pointerId, t0: performance.now() };
}

function onMove(e) {
  if (!drag) return;
  e.preventDefault();
  e.stopPropagation();
  const box = boxFor(e, actions.canvas());
  const el = drag.liveEl;
  if (kind === "line") {
    el.setAttribute("x1", box.x0); el.setAttribute("y1", box.y0);
    el.setAttribute("x2", box.x1); el.setAttribute("y2", box.y1);
  } else if (kind === "ellipse") {
    el.setAttribute("cx", (box.x0 + box.x1) / 2);
    el.setAttribute("cy", (box.y0 + box.y1) / 2);
    el.setAttribute("rx", Math.max((box.x1 - box.x0) / 2, 0));
    el.setAttribute("ry", Math.max((box.y1 - box.y0) / 2, 0));
  } else {
    el.setAttribute("x", box.x0); el.setAttribute("y", box.y0);
    el.setAttribute("width", Math.max(box.x1 - box.x0, 0));
    el.setAttribute("height", Math.max(box.y1 - box.y0, 0));
  }
}

function onUp(e) {
  if (!drag) return;
  e.preventDefault();
  e.stopPropagation();
  const box = boxFor(e, actions.canvas());
  const t = (performance.now() - drag.t0) / 1000;
  cancelDrag();
  commitShape(box, t);
}

function cancelDrag() {
  if (!drag) return;
  drag.groupEl.remove();
  drag = null;
}

// -- commit: straight to the pen / draw seams, never a third path -------------

async function commitShape(box, seconds) {
  if (kind === "line") {
    if (Math.hypot(box.x1 - box.x0, box.y1 - box.y0) < MIN_SIZE) return;
    await commitDrawStroke([[box.x0, box.y0, 0], [box.x1, box.y1, seconds]]);
    return;
  }
  if (box.x1 - box.x0 < MIN_SIZE || box.y1 - box.y0 < MIN_SIZE) return;
  const anchors = kind === "ellipse" ? ellipseAnchors(box) : rectAnchors(box);
  await commitPenSubpath({ anchors, closed: true }, { subtract });
}
