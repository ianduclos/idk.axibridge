// The process popup: watch a layer whose generator declares a TIME AXIS.
//
// It adds no API. /api/generators/preview already runs a generator with no
// layer, no undo checkpoint and no session lock — which is exactly what a
// scrub needs — and with the trajectory cached server-side (gencache keys the
// run WITHOUT the axis, see ARCHITECTURE.md "Caching") each step is a prefix
// slice of one run rather than a re-run.
//
// It never PATCHes the project. Same rule the timeline bar keeps: this is a
// viewer of a param, and committing a step means typing it into the form. The
// acceptance suite asserts it by snapshotting /api/project across a scrub.

import { api } from "./api.js";
import { S, actions } from "./main.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";

let layerId = null;
let axis = null;
let bounds = [0, 100];
let playing = null;
let wired = false;
//: axis value -> point count, for the telemetry strip. Only ever positions
//: actually previewed, so the curve is a record of the watch, not a claim.
let seen = new Map();

function moduleFor(layer) {
  const gen = layer?.source?.type === "generator" ? layer.source.generator : null;
  if (!gen) return null;
  return (S.state?.modules?.sources || []).find((m) => m.id === gen) || null;
}

/** The param this layer's generator calls time, or null if it is
 *  instantaneous — which is most of them. The server's own answer
 *  (`effective_time_axis`, shipped on every source descriptor), never a guess
 *  from the schema: the `frame` fallback means an image generator is watchable
 *  without declaring anything, and a second opinion here would drift from
 *  Session.time_axis the first time that rule changed. */
export function watchableAxis(layer) {
  const mod = moduleFor(layer);
  return mod?.time_axis || null;
}

export function initProcessPopup() {
  if (wired) return;
  if (!$("process-popup")) return; // stale cached index.html: degrade silently
  wired = true;
  $("process-close").onclick = close;
  $("process-play").onclick = () => (playing ? stop() : play());
  $("process-prev").onclick = () => nudge(-1);
  $("process-next").onclick = () => nudge(+1);
  $("process-scrub").addEventListener("input", () => render());
  // click the backdrop (never the modal itself) to dismiss, same as a scrim
  $("process-popup").addEventListener("mousedown", (e) => {
    if (e.target === $("process-popup")) close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("process-popup").hidden) { close(); e.stopPropagation(); }
  });
}

export async function openProcessPopup(id) {
  if (!$("process-popup")) return;
  const layer = (S.state?.project?.layers || []).find((l) => l.id === id);
  axis = watchableAxis(layer);
  if (!axis) return;
  layerId = id;
  seen = new Map();
  const mod = moduleFor(layer);
  const schema = mod.schema?.properties?.[axis] || {};
  bounds = [schema.minimum ?? 0, schema.maximum ?? 100];
  const scrub = $("process-scrub");
  scrub.min = String(bounds[0]);
  scrub.max = String(bounds[1]);
  scrub.step = String(schema.type === "integer" ? 1 : (bounds[1] - bounds[0]) / 200);
  scrub.value = String(layer.source.params?.[axis] ?? bounds[0]);
  $("process-title").textContent = `${layer.name} — ${axis}`;
  $("process-popup").hidden = false;
  drawTelemetry();
  await render();
}

function close() {
  stop();
  queued = false;
  $("process-popup").hidden = true;
  layerId = null;
}

function clamp(v) {
  return Math.min(Math.max(v, bounds[0]), bounds[1]);
}

function nudge(dir) {
  const scrub = $("process-scrub");
  scrub.value = String(clamp(Number(scrub.value) + dir * Number(scrub.step || 1)));
  return render();
}

function play() {
  $("process-play").textContent = "Pause";
  const tick = async () => {
    const scrub = $("process-scrub");
    if (Number(scrub.value) >= Number(scrub.max)) { stop(); return; }
    await nudge(+1);
    if (playing) playing = setTimeout(tick, 40);
  };
  playing = setTimeout(tick, 0);
}

function stop() {
  if (playing) clearTimeout(playing);
  playing = null;
  const btn = $("process-play");
  if (btn) btn.textContent = "Play";
}

// One request in flight at a time, with a TRAILING re-run rather than a
// dropped one: a scrub that lands while a reply is outstanding must still be
// what the canvas ends up showing. (Dropping it — the obvious guard — loses
// exactly the last position of every fast drag, which is the one that matters.)
let pending = false;
let queued = false;
async function render() {
  const layer = (S.state?.project?.layers || []).find((l) => l.id === layerId);
  // the watched layer went away under us (deleted from the layer list while
  // the popup was open): close rather than return, or a running Play leaves
  // its 40 ms timer ticking as a silent no-op until someone closes the popup
  if (!layer) { close(); return; }
  if (pending) { queued = true; return; }
  const value = Number($("process-scrub").value);
  $("process-readout").textContent = String(value);
  pending = true;
  try {
    const params = { ...(layer.source.params || {}), [axis]: value };
    const out = await api.post("/api/generators/preview",
                               { module: layer.source.generator, params });
    draw(out.lines || []);
    seen.set(value, out.points || 0);
    drawTelemetry();
  } catch (e) {
    stop();
    actions.oops(e);
  } finally {
    pending = false;
  }
  if (queued) { queued = false; await render(); }
}

function draw(lines) {
  const svg = $("process-canvas");
  svg.replaceChildren();
  for (const line of lines) {
    if (line.length < 2) continue;
    const el = document.createElementNS(NS, "polyline");
    el.setAttribute("points", line.map(([x, y]) => `${x},${y}`).join(" "));
    el.setAttribute("class", "draw-line");
    svg.appendChild(el);
  }
}

// Points-so-far against the axis, over the positions actually previewed: a
// process that is still growing climbs, one that has converged flattens, and
// that difference is the thing you open this popup to see. Costs no extra
// request — every reply already carries its own point count.
function drawTelemetry() {
  const svg = $("process-telemetry");
  if (!svg) return;
  svg.replaceChildren();
  const span = bounds[1] - bounds[0] || 1;
  const xs = [...seen.keys()].sort((a, b) => a - b);
  const peak = Math.max(1, ...seen.values());
  if (xs.length > 1) {
    const el = document.createElementNS(NS, "polyline");
    el.setAttribute("points", xs.map((v) =>
      `${((v - bounds[0]) / span) * 300},${60 - (seen.get(v) / peak) * 58}`).join(" "));
    svg.appendChild(el);
  }
  const here = Number($("process-scrub").value);
  const x = ((here - bounds[0]) / span) * 300;
  const cursor = document.createElementNS(NS, "line");
  cursor.setAttribute("x1", String(x)); cursor.setAttribute("x2", String(x));
  cursor.setAttribute("y1", "0"); cursor.setAttribute("y2", "60");
  svg.appendChild(cursor);
}
