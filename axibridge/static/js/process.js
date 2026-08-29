// The process popup: watch a layer whose generator declares a TIME AXIS —
// and, in BENCH mode, tune one before any layer exists.
//
// Two modes, one popup:
//   watch  — opened from a layer's detail panel. Read-only: it plays and
//            scrubs the layer's axis and never touches the project.
//   bench  — opened from the Generate panel's ▷ Bench button. The generator's
//            params sit beside the stage and edit the SAME object the panel
//            form edits, so tuning here is tuning there; the scrub bar is the
//            time axis's control (that field is dropped from the bench form —
//            two widgets for one param is how they drift apart), and
//            ＋ Create layer commits exactly the moment on screen.
//
// The invariant both modes keep: this popup never mutates an EXISTING layer.
// Watch mode patches nothing at all; bench mode's one write is creating a new
// layer, through the same call the Generate panel's own button makes. The
// acceptance suite asserts the watch half by snapshotting /api/project across
// a scrub.
//
// It adds no API. /api/generators/preview already runs a generator with no
// layer, no undo checkpoint and no session lock — which is exactly what a
// scrub needs — and with the trajectory cached server-side (gencache keys the
// run WITHOUT the axis, see ARCHITECTURE.md "Caching") each step is a prefix
// slice of one run rather than a re-run. Editing any OTHER param does pay for
// a fresh run, which is why the bench form debounces mid-drag values.

import { api } from "./api.js";
import { S, actions } from "./main.js";
import { renderForm } from "./forms.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";

let layerId = null;      //: watch mode: the layer being played (null in bench mode)
let benchSrc = null;     //: bench mode: { mod, params } — params is the CALLER's live object
let benchHooks = null;   //: bench mode: { onCreate, onReroll, onClose }
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

/** The param a module descriptor calls time, or null if it is instantaneous.
 *  The server's own answer (`time_axis`, shipped on every source descriptor),
 *  never a guess from the schema: the `frame` fallback means an image
 *  generator is watchable without declaring anything, and a second opinion
 *  here would drift from Session.time_axis the first time that rule changed. */
export function moduleAxis(mod) {
  return mod?.time_axis || null;
}

/** Same question, asked of a committed layer. */
export function watchableAxis(layer) {
  return moduleAxis(moduleFor(layer));
}

/** What the popup is previewing right now, resolved fresh every render:
 *  in watch mode from the live project (so an edit elsewhere shows up, and a
 *  deleted layer reads as gone), in bench mode from the caller's own params
 *  object (so the Generate panel and the bench are never two copies). */
function currentSource() {
  if (layerId) {
    const layer = (S.state?.project?.layers || []).find((l) => l.id === layerId);
    if (!layer) return null;
    return { mod: moduleFor(layer), params: layer.source.params || {} };
  }
  return benchSrc;
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
  const create = $("process-create");
  if (create) create.onclick = commit;
  const reroll = $("process-reroll");
  if (reroll) reroll.onclick = () => {
    if (!benchSrc || !benchHooks?.onReroll) return;
    benchHooks.onReroll(benchSrc.params);
    renderBenchForm();
    render();
  };
  // click the backdrop (never the modal itself) to dismiss, same as a scrim
  $("process-popup").addEventListener("mousedown", (e) => {
    if (e.target === $("process-popup")) close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("process-popup").hidden) { close(); e.stopPropagation(); }
  });
}

/** Shared opening tail: the axis's own schema decides the scrub's range and
 *  granularity, so an integer step count steps by 1 and a float axis gets 200
 *  positions across whatever its bounds are. */
function openWith(mod, startValue, title) {
  const schema = mod.schema?.properties?.[axis] || {};
  bounds = [schema.minimum ?? 0, schema.maximum ?? 100];
  const scrub = $("process-scrub");
  scrub.min = String(bounds[0]);
  scrub.max = String(bounds[1]);
  scrub.step = String(schema.type === "integer" ? 1 : (bounds[1] - bounds[0]) / 200);
  scrub.value = String(clamp(Number(startValue ?? bounds[0])));
  $("process-title").textContent = title;
  $("process-popup").hidden = false;
  seen = new Map();
  drawTelemetry();
  return render();
}

export async function openProcessPopup(id) {
  if (!$("process-popup")) return;
  const layer = (S.state?.project?.layers || []).find((l) => l.id === id);
  axis = watchableAxis(layer);
  if (!axis) return;
  layerId = id;
  benchSrc = null;
  benchHooks = null;
  setBenchChrome(false);
  await openWith(moduleFor(layer), layer.source.params?.[axis], `${layer.name} — ${axis}`);
}

/** Bench mode. `params` is used BY REFERENCE on purpose: the Generate panel
 *  hands over its own live object, so every edit made here — including the
 *  scrub, which writes the axis back — is already in the panel when the bench
 *  closes, and ＋ Create layer needs no second copy to reconcile. */
export async function openProcessBench({ mod, params, onCreate, onReroll, onClose }) {
  if (!$("process-popup")) return;
  axis = moduleAxis(mod);
  if (!axis) return;
  layerId = null;
  benchSrc = { mod, params };
  benchHooks = { onCreate, onReroll, onClose };
  setBenchChrome(true);
  renderBenchForm();
  await openWith(mod, params[axis], `${mod.label} — bench`);
}

function setBenchChrome(on) {
  for (const id of ["process-params", "process-create"]) {
    const el = $(id);
    if (el) el.hidden = !on;
  }
  const reroll = $("process-reroll");
  if (reroll) {
    const spec = on ? benchSrc?.mod?.schema?.properties?.seed : null;
    reroll.hidden = !(benchHooks?.onReroll
      && (spec?.type === "integer" || spec?.type === "number"));
  }
}

// The bench form is the generator's own auto-form minus the time axis — the
// scrub bar is that param's control, and a second widget for it would let the
// two disagree mid-drag. Mid-drag values are debounced (each one invalidates
// the server's trajectory and pays for a whole fresh run); a committed value
// redraws at once.
let liveTimer = null;
function renderBenchForm() {
  const host = $("process-params");
  if (!host || !benchSrc) return;
  const { mod, params } = benchSrc;
  const props = { ...(mod.schema?.properties || {}) };
  delete props[axis];
  const schema = { ...mod.schema, properties: props };
  const later = () => {
    clearTimeout(liveTimer);
    liveTimer = setTimeout(() => render(), 140);
  };
  renderForm(host, schema, params, () => { clearTimeout(liveTimer); render(); },
             { onLive: later, stateKey: `bench:${mod.id}` });
}

async function commit() {
  if (!benchSrc || !benchHooks?.onCreate) return;
  stop();
  const params = { ...benchSrc.params, [axis]: Number($("process-scrub").value) };
  const btn = $("process-create");
  if (btn) btn.disabled = true;
  try {
    await benchHooks.onCreate(params);
    close();
  } catch (e) {
    actions.oops(e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function close() {
  stop();
  queued = false;
  clearTimeout(liveTimer);
  $("process-popup").hidden = true;
  layerId = null;
  const onClose = benchHooks?.onClose;
  benchSrc = null;
  benchHooks = null;
  if (onClose) onClose();   // the panel re-reads params the bench moved
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
  const cur = currentSource();
  // the watched layer went away under us (deleted from the layer list while
  // the popup was open): close rather than return, or a running Play leaves
  // its 40 ms timer ticking as a silent no-op until someone closes the popup
  if (!cur || !cur.mod) { close(); return; }
  if (pending) { queued = true; return; }
  const value = Number($("process-scrub").value);
  $("process-readout").textContent = String(value);
  // bench mode: the scrub IS the axis field, so write it back — the panel form
  // and ＋ Create layer both read this object
  if (benchSrc) benchSrc.params[axis] = value;
  pending = true;
  try {
    const params = { ...cur.params, [axis]: value };
    const out = await api.post("/api/generators/preview",
                               { module: cur.mod.id, params });
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
