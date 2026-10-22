// The pen's sketch mode (pen v2 P3, "sketch, then fit"): a freehand drag is
// sampled in bed mm and, on release, fitted server-side
// (POST /api/geometry/fit) into an ordinary editable pen subpath, committed
// exactly as a drawn path is (commitPenSubpath). The Detail slider re-fits
// the MOST RECENT sketch in place, live, until any other pen action ends
// that (pen.js calls endRefit). The raw samples live only here, in memory —
// nothing raw is saved in the project (spec, Settled 2).
//
// pen.js owns the pointer dispatch and calls startSketch / addSketchSamples /
// finishSketch for a "sketch" gesture.

import { api } from "./api.js";
import { S, actions } from "./main.js";
import { commitPenSubpath, on, redraw, setCommitting, subtract } from "./pen.js";
import { queueRegenerate, whenIdle } from "./pen_queue.js";

const $ = (id) => document.getElementById(id);
const MIN_STEP_MM = 0.2;   // a sample closer than this to the last kept one is dropped
const MIN_LENGTH_MM = 1;   // a shorter drag (a click, a wobble) does nothing
const CLOSE_MM = 2;        // ends this close make a closed stroke…
const CLOSE_MIN_MM = 8;    // …once the stroke is long enough to be a loop at all
const MAX_POINTS = 20000;  // what /api/geometry/fit accepts

/** The most recent sketch, re-fittable until the next pen action:
 *  {layerId, si, points, closed, token, seq}. */
let lastFit = null;
let refitBusy = false;   // one fit request in flight at a time…
let refitAgain = false;  // …and the slider moved meanwhile: fit its latest value next
let shown = null;        // a released stroke still on screen while it is fitted and committed
let seq = 0;
// per page load, so a coalesce token never matches one from before a reload
const NONCE = Math.random().toString(36).slice(2, 10);

/** Any other pen action (click, drag, key edit, mode or layer change, undo)
 *  ends the live re-fit of the last sketch. */
export function endRefit() {
  lastFit = null;
  refitAgain = false;
}

export function initSketch() {
  const detail = $("pen-detail");
  if (detail) detail.addEventListener("input", onDetailInput);
}

function detailValue() {
  const v = Number(/** @type {HTMLInputElement | null} */ ($("pen-detail"))?.value);
  return Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0.5;
}

/** The stroke the overlay should draw: the one being dragged, or one being fitted. */
export function sketchView(gesture) {
  return gesture?.kind === "sketch" ? gesture.points : shown;
}

// -- capture ---------------------------------------------------------------------

/** A new sketch gesture starting at bed-mm (x, y). */
export function startSketch(x, y) {
  return { kind: "sketch", points: [[x, y]], length: 0 };
}

/** Add the pointer samples of one move (every coalesced event, for fidelity),
 *  keeping only those at least MIN_STEP_MM from the last kept one.
 *  @param {any} g @param {any} editor @param {PointerEvent} e
 *  @param {(x: number, y: number) => number[]} clamp */
export function addSketchSamples(g, editor, e, clamp) {
  const coalesced = typeof e.getCoalescedEvents === "function" ? e.getCoalescedEvents() : [];
  for (const ev of coalesced.length ? coalesced : [e]) {
    const bed = editor.toBed(ev);
    const [x, y] = clamp(bed.x, bed.y);
    const last = g.points[g.points.length - 1];
    const d = Math.hypot(x - last[0], y - last[1]);
    if (d < MIN_STEP_MM) continue;
    g.points.push([x, y]);
    g.length += d;
  }
}

// at most MAX_POINTS samples, evenly thinned, the last one always kept
function capped(points) {
  if (points.length <= MAX_POINTS) return points;
  const k = Math.ceil(points.length / (MAX_POINTS - 1));
  const out = points.filter((_, i) => i % k === 0);
  if (out[out.length - 1] !== points[points.length - 1]) out.push(points[points.length - 1]);
  return out;
}

const fit = (points, closed) =>
  api.post("/api/geometry/fit", { points, closed, detail: detailValue() }).then((r) => r.anchors);

// -- commit ----------------------------------------------------------------------

/** The sketch gesture was released: fit it and commit it as a new subpath. */
export async function finishSketch(g) {
  if (g.points.length < 2 || g.length < MIN_LENGTH_MM) { redraw(); return; }
  const points = capped(g.points);
  const [f, l] = [points[0], points[points.length - 1]];
  const closed = g.length >= CLOSE_MIN_MM && Math.hypot(l[0] - f[0], l[1] - f[1]) <= CLOSE_MM;
  const bite = subtract;
  if (bite && !closed) {
    actions.log("sketch: only a closed stroke can be subtracted — end it where it began");
    redraw();
    return;
  }
  shown = points;
  setCommitting(true);
  redraw();
  let id = null;
  try {
    const anchors = await fit(points, closed);
    await whenIdle(); // a queued edit (a re-fit) lands before this commit reads the layer
    id = await commitPenSubpath({ anchors, closed, kind: "bezier" }, { subtract: bite });
  } catch (e) { actions.oops(e); }
  setCommitting(false);
  shown = null;
  // a pen subpath appended to (or starting) a pen layer is re-fittable; a
  // bite or a shape-layer union is a shape op, not a subpath, and is not
  const layer = id ? S.state?.project?.layers.find((x) => x.id === id) : null;
  const subpaths = layer?.source?.generator === "pen" ? layer.source.params.subpaths || [] : [];
  if (on && !bite && subpaths.length) {
    lastFit = { layerId: id, si: subpaths.length - 1, points, closed,
                token: `pen-refit-${id.slice(0, 16)}-${NONCE}-${++seq}`, seq: 0 };
  }
  redraw();
}

// -- live re-fit -------------------------------------------------------------------

function onDetailInput() {
  if (!lastFit) return;
  if (refitBusy) { refitAgain = true; return; }
  runRefit();
}

async function runRefit() {
  const run = lastFit;
  if (!run) return;
  refitBusy = true;
  refitAgain = false;
  const mine = ++run.seq;
  let anchors = null;
  try { anchors = await fit(run.points, run.closed); } catch (e) { actions.oops(e); }
  refitBusy = false;
  // a response another action (or a newer re-fit) has overtaken is dropped
  if (anchors && lastFit === run && run.seq === mine) applyRefit(run, anchors);
  if (refitAgain && lastFit) runRefit();
}

// The re-fitted anchors replace that subpath in place. Every re-fit of one
// sketch carries the sketch's token, so the whole run is one undo step.
function applyRefit(run, anchors) {
  const layer = S.state?.project?.layers.find((x) => x.id === run.layerId);
  const sp = layer?.source?.generator === "pen" ? layer.source.params.subpaths?.[run.si] : null;
  if (!sp) { endRefit(); return; }
  layer.source.params.subpaths = layer.source.params.subpaths.map(
    (s, i) => (i === run.si ? { ...s, anchors, kind: "bezier" } : s));
  queueRegenerate(layer, { coalesce: run.token });
  redraw();
}
