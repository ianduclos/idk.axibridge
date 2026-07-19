// Draw mode: pointer strokes on the main canvas become a "drawing" generator
// layer (docs/plans/draw-mode.md). Capture-phase listeners on #canvas-wrap
// intercept pointer events (with stopPropagation) while the mode is active,
// so canvas.js's own selection/drag/marquee code — registered on #canvas
// itself, bubble phase — never sees them; when the mode is off, events pass
// through untouched. Pointer -> mm goes through the SAME conversion the
// drag/marquee code uses (CanvasEditor.toBed, via getScreenCTM().inverse()
// on the view-rotated <g>), so portrait/landscape both land correctly with
// no reimplementation of the mapping.

import { api } from "./api.js";
import { S, actions } from "./main.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const BED = { w: 300, h: 218 };

// THIS SHAPE IS THE CONTRACT (docs/plans/draw-mode.md Part 3) — a follow-up
// plan appends an entry with a `source` override, so both keys must exist
// on every brush even when unused.
const BRUSHES = [
  { id: "plain", label: "plain", source: {}, effects: [] },
  { id: "sketchy", label: "sketchy", source: {}, effects: [{ effect: "freehand", enabled: true, params: {} }] },
  { id: "tube", label: "tube", source: {}, effects: [{ effect: "fat_tube", enabled: true, params: { width: 5 } }] },
  { id: "wobble", label: "wobble", source: {}, effects: [{ effect: "coherent_jitter", enabled: true, params: { amplitude: 2 } }] },
  // response: decorations target the OPEN centerline only (on_closed:false) —
  // on the closed velocity outline they double up and its width wiggles read
  // as corners, chaining rings along the whole tube. ORDER MATTERS: eyelets
  // must run BEFORE parasite_line, or at_ends rings every 1.2mm parasite
  // dash (hundreds of beads); parasite in turn skips the eyelet circles
  // because they're closed. Hand strokes are jittery even after smoothing,
  // so eyelets run less sensitive/wider-spaced than the module defaults
  // tuned on clean synthetic paths.
  // keep_centerline: the tube alone is the stroke by default (source default
  // false); response opts back in because the open centerline is the skeleton
  // its decorations ride (on_closed:false ignores the outline) — drop it and
  // parasite/eyelets have nothing to decorate.
  { id: "response", label: "response",
    source: { render: "velocity_tube", keep_centerline: true },
    effects: [
      { effect: "eyelets", enabled: true, params: { on_closed: false, sensitivity: 0.7, spacing: 18 } },
      { effect: "parasite_line", enabled: true, params: { on_closed: false } },
    ] },
];

let on = false;
let activeDrawLayerId = null;
let pendingBrush = BRUSHES[0];
let drag = null; // { pts: [[x,y,t]], t0, pointerId, liveEl }
let wired = false; // initTabs() re-runs on every SSE reconnect — wire listeners once

export function initDrawMode() {
  if (wired) return;
  const toggle = $("draw-toggle");
  const brushSelect = $("brush-select");
  const wrap = $("canvas-wrap");
  if (!toggle || !brushSelect || !wrap) return; // stale cached index.html: degrade silently
  wired = true;

  fillBrushSelect(brushSelect);

  toggle.onclick = () => setOn(!on, toggle, brushSelect, wrap);
  brushSelect.onchange = () => {
    pendingBrush = BRUSHES.find((b) => b.id === brushSelect.value) || BRUSHES[0];
    const id = currentTargetLayerId();
    if (id) applyBrushToLayer(id, pendingBrush);
  };

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && on) setOn(false, toggle, brushSelect, wrap);
  });

  // the doc-preview banner has no event of its own — watch its `hidden`
  // attribute so the toggle disables the instant a transient sheet/staged
  // document takes over the canvas, and re-enables when it clears
  const banner = $("doc-preview-banner");
  if (banner) {
    const sync = () => {
      const previewing = !banner.hidden;
      toggle.disabled = previewing;
      if (previewing && on) setOn(false, toggle, brushSelect, wrap);
    };
    new MutationObserver(sync).observe(banner, { attributes: true, attributeFilter: ["hidden"] });
    sync();
  }

  wrap.addEventListener("pointerdown", (e) => onDown(e, wrap), true);
  wrap.addEventListener("pointermove", (e) => onMove(e), true);
  wrap.addEventListener("pointerup", (e) => onUp(e), true);
  wrap.addEventListener("pointercancel", (e) => onUp(e), true);
}

function setOn(v, toggle, brushSelect, wrap) {
  if (v && toggle.disabled) return; // doc-preview banner active
  on = v;
  toggle.classList.toggle("on", on);
  wrap.classList.toggle("draw-mode", on);
  brushSelect.hidden = !on;
}

function fillBrushSelect(sel) {
  sel.innerHTML = "";
  for (const b of BRUSHES) {
    const o = document.createElement("option");
    o.value = b.id;
    o.textContent = b.label;
    sel.appendChild(o);
  }
  sel.value = pendingBrush.id;
}

// -- targeting: which layer (if any) strokes append to -----------------------

function currentTargetLayerId() {
  const project = S.state?.project;
  if (!project) return null;
  if (activeDrawLayerId && !project.layers.some((l) => l.id === activeDrawLayerId)) {
    activeDrawLayerId = null; // the active layer was deleted — never assume
  }
  const sel = S.selection.length === 1 ? project.layers.find((l) => l.id === S.selection[0]) : null;
  if (sel && sel.source?.type === "generator" && sel.source?.generator === "drawing") {
    activeDrawLayerId = sel.id; // selecting a different drawing layer retargets to it
    return sel.id;
  }
  return activeDrawLayerId;
}

function clampBed([x, y, t]) {
  return [Math.min(BED.w, Math.max(0, x)), Math.min(BED.h, Math.max(0, y)), Math.max(0, t)];
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
  const live = document.createElementNS(NS, "polyline");
  live.setAttribute("class", "wb-line wb-draw-live");
  live.setAttribute("points", `${pt[0]},${pt[1]}`);
  editor.world.appendChild(live);
  drag = { pts: [pt], t0: performance.now(), pointerId: e.pointerId, liveEl: live };
}

function onMove(e) {
  if (!drag) return;
  e.preventDefault();
  e.stopPropagation();
  const editor = actions.canvas();
  const p = editor.toBed(e);
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
  commitStroke(d.pts);
}

// -- commit: one stroke -> append to the active drawing layer, or create one ---

async function commitStroke(stroke) {
  try {
    const id = currentTargetLayerId();
    if (id) {
      const layer = S.state.project.layers.find((l) => l.id === id);
      const strokes = [...(layer.source.params.strokes || []), stroke];
      // no coalesce: per-stroke undo is the point (⌘Z removes exactly one stroke)
      await api.post(`/api/layers/${id}/regenerate`, { params: { ...layer.source.params, strokes } });
    } else {
      const params = { strokes: [stroke], ...pendingBrush.source };
      const layer = await api.post("/api/layers/generate", { module: "drawing", params });
      activeDrawLayerId = layer.id;
      actions.setSelection([layer.id]);
      if (pendingBrush.effects.length) {
        actions.patchLayer(layer.id, { effects: resolveEffects(pendingBrush.effects) });
      }
    }
    await actions.refreshProject();
    await actions.refreshResolved();
  } catch (e) { actions.oops(e); }
}

// -- brush presets --------------------------------------------------------------

// `params: {}` means module defaults — describe_modules() ships them
// pre-resolved as `defaults` on each module descriptor.
function resolveEffects(steps) {
  return steps.map((step) => {
    const mod = (S.state.modules.effects || []).find((m) => m.id === step.effect);
    const defaults = mod ? mod.defaults : {};
    return { effect: step.effect, enabled: step.enabled !== false, params: { ...defaults, ...step.params } };
  });
}

async function applyBrushToLayer(id, brush) {
  actions.patchLayer(id, { effects: resolveEffects(brush.effects) });
  if (Object.keys(brush.source).length === 0) return;
  try {
    const layer = S.state.project.layers.find((l) => l.id === id);
    if (!layer) return;
    const params = { ...layer.source.params, ...brush.source };
    await api.post(`/api/layers/${id}/regenerate`, { params });
    await actions.refreshProject();
    await actions.refreshResolved();
  } catch (e) { actions.oops(e); }
}
