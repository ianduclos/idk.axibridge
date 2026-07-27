// Brush mode: a circle brush painted on the main canvas becomes a "brush"
// generator layer — a filled mass, not a line (docs/plans/pen-brush-tools.md
// Part 2). Same capture-phase interception as draw.js: listeners on
// #canvas-wrap with stopPropagation, so canvas.js's own drag/marquee code
// (bubble phase, on #canvas) never sees the events while the mode is on, and
// pointer -> mm goes through CanvasEditor.toBed so portrait/landscape both
// land correctly with no second mapping.
//
// Live feedback is CLIENT-SIDE and the commit happens once on pointer-up —
// the split the pen tool settled after trying it the other way. Regenerating
// mid-drag would put a shapely buffer + union of the whole accumulated mass
// on every pointermove; the SVG preview here costs nothing and looks the same.
//
// Erase is a stroke, not an undo: it is stored in the layer's history and
// replays (and animates) with everything else. Cmd-Z removes the last stroke
// you captured, whichever kind it was.

import { api } from "./api.js";
import { S, actions } from "./main.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const BED = { w: 300, h: 218 };

// mirrors BrushStroke.radius's Pydantic bounds — the server is the authority,
// this only keeps the cursor from advertising a size that would 422
const R_MIN = 0.3;
const R_MAX = 50;
const R_STEP = 1.15; // geometric, so [ / ] feel even across the whole range

let on = false;
let activeBrushLayerId = null;
let radius = 5;
let erasing = false;
let drag = null; // { pts: [[x,y,t]], t0, pointerId, liveEl }
let cursorEl = null;
let wired = false; // initTabs() re-runs on every SSE reconnect — wire once

export function initBrushMode() {
  if (wired) return;
  const wrap = $("canvas-wrap");
  if (!wrap) return; // stale cached index.html: degrade silently
  wired = true;

  const eraseBtn = $("brush-erase");
  if (eraseBtn) {
    eraseBtn.onclick = () => setErasing(!erasing);
  }

  wrap.addEventListener("pointerdown", (e) => onDown(e, wrap), true);
  wrap.addEventListener("pointermove", (e) => onMove(e), true);
  wrap.addEventListener("pointerup", (e) => onUp(e), true);
  wrap.addEventListener("pointercancel", (e) => onUp(e), true);
  wrap.addEventListener("pointerleave", () => hideCursor(), true);

  // [ / ] resize the live brush, the raster-paint-tool gesture. Captured on
  // the document because the canvas is not focusable; guarded on `on` so the
  // keys stay free everywhere else.
  document.addEventListener("keydown", (e) => {
    if (!on || e.metaKey || e.ctrlKey || e.altKey) return;
    const tag = (e.target?.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if (e.key === "[") setRadius(radius / R_STEP);
    else if (e.key === "]") setRadius(radius * R_STEP);
    else if (e.key.toLowerCase() === "e") setErasing(!erasing);
    else return;
    e.preventDefault();
  });
}

export function activateBrushMode() {
  on = true;
  $("canvas-wrap")?.classList.add("brush-mode");
  const bar = $("brush-bar");
  if (bar) bar.hidden = false;
  syncBar();
}

export function deactivateBrushMode() {
  on = false;
  $("canvas-wrap")?.classList.remove("brush-mode");
  const bar = $("brush-bar");
  if (bar) bar.hidden = true;
  hideCursor();
  // mode switched mid-stroke: a half-painted blob is not worth committing,
  // and unlike the pen there is no "unfinished path" worth rescuing
  if (drag) { drag.liveEl.remove(); drag = null; }
}

// Escape while painting abandons the stroke but stays in the tool; a second
// Escape (nothing pending) falls through to the broker and exits to select.
export function handleBrushEscape() {
  if (!drag) return false;
  drag.liveEl.remove();
  drag = null;
  return true;
}

function setRadius(r) {
  radius = Math.min(R_MAX, Math.max(R_MIN, r));
  syncBar();
  if (cursorEl) cursorEl.setAttribute("r", String(radius));
}

function setErasing(v) {
  erasing = v;
  syncBar();
  if (cursorEl) cursorEl.classList.toggle("erasing", erasing);
}

function syncBar() {
  const label = $("brush-size");
  if (label) label.textContent = `${radius.toFixed(1)} mm`;
  const btn = $("brush-erase");
  if (btn) {
    btn.classList.toggle("on", erasing);
    btn.title = erasing ? "Erasing — click or press E to paint" : "Painting — click or press E to erase";
  }
}

// -- targeting: which layer (if any) strokes append to -------------------------

function currentTargetLayerId() {
  const project = S.state?.project;
  if (!project) return null;
  if (activeBrushLayerId && !project.layers.some((l) => l.id === activeBrushLayerId)) {
    activeBrushLayerId = null; // the active layer was deleted — never assume
  }
  const sel = S.selection.length === 1 ? project.layers.find((l) => l.id === S.selection[0]) : null;
  if (sel && sel.source?.type === "generator" && sel.source?.generator === "brush") {
    activeBrushLayerId = sel.id; // selecting a different brush layer retargets
    return sel.id;
  }
  return activeBrushLayerId;
}

function clampBed([x, y, t]) {
  return [Math.min(BED.w, Math.max(0, x)), Math.min(BED.h, Math.max(0, y)), Math.max(0, t)];
}

// -- the circle cursor ---------------------------------------------------------

function showCursor(editor, x, y) {
  if (!cursorEl) {
    cursorEl = document.createElementNS(NS, "circle");
    cursorEl.setAttribute("class", "brush-cursor");
    cursorEl.classList.toggle("erasing", erasing);
    cursorEl.setAttribute("r", String(radius));
  }
  if (cursorEl.parentNode !== editor.world) editor.world.appendChild(cursorEl);
  cursorEl.setAttribute("cx", String(x));
  cursorEl.setAttribute("cy", String(y));
}

function hideCursor() {
  cursorEl?.remove();
}

// -- pointer capture -----------------------------------------------------------

function onDown(e, wrap) {
  if (!on || e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  wrap.setPointerCapture(e.pointerId);
  const editor = actions.canvas();
  const p = editor.toBed(e);
  const pt = clampBed([p.x, p.y, 0]);
  // the live mass: a fat round-capped polyline at 2x radius reads as the same
  // swept area shapely will buffer server-side, without asking it to
  const live = document.createElementNS(NS, "polyline");
  live.setAttribute("class", `brush-live${erasing ? " erasing" : ""}`);
  live.setAttribute("stroke-width", String(radius * 2));
  live.setAttribute("points", `${pt[0]},${pt[1]}`);
  editor.world.appendChild(live);
  drag = { pts: [pt], t0: performance.now(), pointerId: e.pointerId, liveEl: live };
}

function onMove(e) {
  if (!on) return;
  const editor = actions.canvas();
  const p = editor.toBed(e);
  showCursor(editor, p.x, p.y);
  if (!drag) return;
  e.preventDefault();
  e.stopPropagation();
  const t = (performance.now() - drag.t0) / 1000;
  const pt = clampBed([p.x, p.y, t]);
  drag.pts.push(pt);
  drag.liveEl.setAttribute("points", drag.pts.map(([x, y]) => `${x},${y}`).join(" "));
}

function onUp(e) {
  if (!drag) return;
  e.preventDefault();
  e.stopPropagation();
  const d = drag;
  drag = null;
  d.liveEl.remove();
  commitStroke({ points: resample(d.pts, 0.8), mode: erasing ? "erase" : "paint", radius });
}

// Resample at a fixed arc-length step so pointer-event density (a fast flick
// vs a slow crawl) doesn't change how many points a stroke costs — the same
// thing draw.js's server-side `resample_mm` does, applied here because the
// brush has no resample param of its own to do it later.
function resample(pts, step) {
  if (pts.length < 2) return pts;
  const out = [pts[0]];
  let acc = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    let [x0, y0, t0] = pts[i];
    const [x1, y1, t1] = pts[i + 1];
    let seg = Math.hypot(x1 - x0, y1 - y0);
    while (seg > 0 && acc + seg >= step) {
      const frac = (step - acc) / seg;
      x0 += (x1 - x0) * frac;
      y0 += (y1 - y0) * frac;
      t0 += (t1 - t0) * frac;
      out.push([x0, y0, t0]);
      seg = Math.hypot(x1 - x0, y1 - y0);
      acc = 0;
    }
    acc += seg;
  }
  out.push(pts[pts.length - 1]);
  return out;
}

// -- commit: one stroke -> append to the active brush layer, or create one -----

async function commitStroke(stroke) {
  try {
    const id = currentTargetLayerId();
    if (id) {
      const layer = S.state.project.layers.find((l) => l.id === id);
      const strokes = [...(layer.source.params.strokes || []), stroke];
      // no coalesce: per-stroke undo is the point (⌘Z removes exactly one
      // stroke, paint or erase) — the same call draw.js makes
      await api.post(`/api/layers/${id}/regenerate`, { params: { ...layer.source.params, strokes } });
    } else {
      if (stroke.mode === "erase") return; // nothing to erase from yet
      const layer = await api.post("/api/layers/generate",
                                   { module: "brush", params: { strokes: [stroke] } });
      activeBrushLayerId = layer.id;
      actions.setSelection([layer.id]);
    }
    await actions.refreshProject();
    await actions.refreshResolved();
  } catch (e) { actions.oops(e); }
}
