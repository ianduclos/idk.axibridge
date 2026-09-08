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
import { homeostatFormSchema } from "./homeostat_bench.js";
import { renderForm } from "./forms.js";
import { benchAdapter, benchDescriptor, benchUnavailableReason, registerBenchAdapter } from "./bench_registry.js";
import { initBenchHost, openBenchShell, closeBenchShell, clearBenchError, showBenchError } from "./bench_host.js";
import {
  closeSecondReadingBench,
  initSecondReadingBench,
  isSecondReadingBenchOpen,
  isSecondReadingModule,
  openSecondReadingBench,
  stopSecondReadingPlay,
  toggleSecondReadingPlay,
} from "./second_reading_bench.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";

let layerId = null;      //: watch mode: the layer being played (null in bench mode)
let benchSrc = null;     //: bench mode: { mod, params } — params is the CALLER's live object
let benchHooks = null;   //: bench mode: { onCreate, onReroll, onClose }
let axis = null;
let bounds = [0, 100];
let playing = null;
let wired = false;
let renderedKey = null;
let telemetry = new Map();
let telemetryRecipe = null;
let creating = false;
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

export function interventionBenchable(layer) {
  return isSecondReadingModule(moduleFor(layer));
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
  initSecondReadingBench();
  initBenchHost();
  $("process-trace").onchange = drawTelemetry;
  $("process-play").onclick = () => isSecondReadingBenchOpen()
    ? toggleSecondReadingPlay() : (playing ? stop() : play());
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

}

/** Shared opening tail: the axis's own schema decides the scrub's range and
 *  granularity, so an integer step count steps by 1 and a float axis gets 200
 *  positions across whatever its bounds are. */
let viewSession = 0;
function openWith(mod, startValue, title) {
  viewSession++;
  renderSerial++;
  $("process-canvas").setAttribute("viewBox", "0 0 300 218");
  $("process-canvas").style.aspectRatio = "300 / 218";
  $("process-canvas").style.setProperty("--process-aspect", String(300 / 218));
  $("process-play").disabled = false;
  const schema = mod.schema?.properties?.[axis] || {};
  bounds = [schema.minimum ?? 0, schema.maximum ?? 100];
  const scrub = $("process-scrub");
  scrub.min = String(bounds[0]);
  scrub.max = String(bounds[1]);
  scrub.step = String(schema.type === "integer" ? 1 : (bounds[1] - bounds[0]) / 200);
  scrub.value = String(clamp(Number(startValue ?? bounds[0])));
  $("process-title").textContent = title;
  const entry = benchSrc ? { ...benchSrc, ...benchHooks } : null;
  const watchedId = layerId;
  openBenchShell({ close, reopen: entry ? () => openProcessBench(entry) : () => openProcessPopup(watchedId),
    origin: benchSrc ? 'New material · creates a new layer' : 'Watch · read-only layer preview' });
  seen = new Map();
  telemetry = new Map();
  renderedKey = null;
  const trace = $('process-trace');
  trace.replaceChildren(new Option('Point count', 'points'));
  $('process-values').replaceChildren();
  $('process-status').textContent = 'Preview pending';
  $('process-origin').title = axis ? `Time axis: ${axis}` : 'Non-temporal bench';
  for (const id of ['process-scrub','process-prev','process-next','process-play','process-readout']) $(id).hidden = !axis;
  drawTelemetry();
  return render();
}

export async function openProcessPopup(id) {
  if (!$("process-popup")) return;
  closeSecondReadingBench(false);
  stop();
  const layer = (S.state?.project?.layers || []).find((l) => l.id === id);
  axis = watchableAxis(layer);
  if (!axis) return;
  layerId = id;
  benchSrc = null;
  benchHooks = null;
  setBenchChrome(false);
  await openWith(moduleFor(layer), layer.source.params?.[axis], `${layer.name} — ${axis}`);
}

/** Resume an intervention-capable kept layer as a new working draft. Its
 *  recipe is copied before the popup opens; Keep always creates another
 *  ordinary layer and this source layer is never patched. */
export function openProcessLayerBench(id) {
  if (!$('process-popup')) return;
  const layer = (S.state?.project?.layers || []).find((l) => l.id === id);
  const mod = moduleFor(layer);
  if (!layer || !isSecondReadingModule(mod)) return;
  stop();
  renderSerial++;
  queued = false;
  clearTimeout(liveTimer);
  const moduleId = mod.id;
  const params = JSON.parse(JSON.stringify(layer.source.params || {}));
  openSecondReadingBench({
    mod, params, contextKey: `layer:${layer.id}`,
    onKeep: async (exact) => {
      const kept = await api.post("/api/layers/generate", { module: moduleId, params: exact });
      await actions.refreshProject();
      await actions.refreshResolved();
      actions.setSelection([kept.id]);
      return kept;
    },
  });
}

/** Bench mode. `params` is used BY REFERENCE on purpose: the Generate panel
 *  hands over its own live object, so every edit made here — including the
 *  scrub, which writes the axis back — is already in the panel when the bench
 *  closes, and ＋ Create layer needs no second copy to reconcile. */
export async function openProcessBench(entry) {
  if (!$("process-popup")) return;
  const adapter = benchAdapter(entry.mod, 'new');
  if (!adapter) {
    $('process-title').textContent = entry.mod.label;
    openBenchShell({ close, origin: 'Bench unavailable' });
    setBenchChrome(false);
    showBenchError(benchUnavailableReason(entry.mod));
    return;
  }
  stop();
  renderSerial++;
  queued = false;
  clearTimeout(liveTimer);
  return adapter.open(entry);
}

async function openGenericBench({ mod, params, onCreate, onReroll, onClose }) {
  closeSecondReadingBench(false);
  axis = moduleAxis(mod);
  layerId = null;
  benchSrc = { mod, params };
  benchHooks = { onCreate, onReroll, onClose };
  setBenchChrome(true);
  renderBenchForm();
  await openWith(mod, axis ? params[axis] : null, `${mod.label} — bench`);
}
registerBenchAdapter('process', 1, { open: openGenericBench });
registerBenchAdapter('homeostat', 1, { open: entry => openGenericBench({
  ...entry, mod: { ...entry.mod, schema: homeostatFormSchema(entry.mod.schema) },
}) });
registerBenchAdapter('second-reading', 1, { open: ({ mod, params, onCreate, onClose }) => {
  openSecondReadingBench({ mod, params, contextKey: `new:${mod.id}`, onKeep: onCreate, onClose });
} });

function setBenchChrome(on) {
  $("process-popup")?.classList.remove("second-reading");
  $("process-popup")?.classList.toggle("watch-only", !on);
  $("process-status").hidden = false;
  const special = $("process-second-reading");
  if (special) special.hidden = true;
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
  // Source-owned group metadata stays authoritative. Core scalar fields remain
  // visible; existing advanced groups use the ordinary schema renderer.
  const schema = { ...mod.schema, properties: props };
  const later = () => {
    renderSerial++;
    renderedKey = null;
    $('process-create').disabled = true;
    $('process-status').textContent = 'Parameters changed · preview pending';
    clearTimeout(liveTimer);
    liveTimer = setTimeout(() => render(), 140);
  };
  renderForm(host, schema, params, () => { clearTimeout(liveTimer); render(); },
             { onLive: later, stateKey: `bench:${mod.id}` });
}

function currentParams() {
  const cur = currentSource();
  if (!cur) return null;
  return axis ? { ...cur.params, [axis]: Number($('process-scrub').value) } : { ...cur.params };
}
function currentKey() {
  return JSON.stringify({ module: currentSource()?.mod?.id, params: currentParams() });
}
async function commit() {
  if (!benchSrc || !benchHooks?.onCreate || creating || renderedKey !== currentKey()) return;
  stop();
  const onCreate = benchHooks.onCreate;
  const params = JSON.parse(JSON.stringify(currentParams()));
  const key = currentKey();
  const ownerSession = viewSession;
  const btn = $('process-create');
  creating = true;
  btn.disabled = true;
  clearBenchError();
  try {
    await onCreate(params);
    // A completed write cannot be canceled by closing the popup. Never close
    // a different bench that opened while this command was in flight.
    if (ownerSession === viewSession && renderedKey === key && !isSecondReadingBenchOpen()) close();
  } catch (e) {
    if (ownerSession === viewSession && !$("process-popup").hidden && renderedKey === key)
      showBenchError(e); // no automatic retry of an uncertain project write
  } finally {
    creating = false;
    btn.disabled = renderedKey !== currentKey();
  }
}

function close() {
  viewSession++;
  renderSerial++; // orphan a preview reply from the view being closed
  if (isSecondReadingBenchOpen()) {
    closeSecondReadingBench();
    return;
  }
  stop();
  queued = false;
  clearTimeout(liveTimer);
  closeBenchShell();
  renderedKey = null;
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
  stopSecondReadingPlay();
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
let renderSerial = 0;
async function render() {
  if (isSecondReadingBenchOpen() || $('process-popup').hidden) return;
  const cur = currentSource();
  if (!cur || !cur.mod) { close(); return; }
  const serial = ++renderSerial;
  const value = Number($('process-scrub').value);
  $('process-readout').textContent = String(value);
  if (benchSrc && axis) benchSrc.params[axis] = value;
  renderedKey = null;
  $('process-create').disabled = true;
  $('process-status').textContent = 'Resolving · previous preview may be shown';
  if (pending) { queued = true; return; }
  pending = true;
  const params = JSON.parse(JSON.stringify(currentParams()));
  const base = { ...params }; delete base[axis];
  const runKey = JSON.stringify({ module: cur.mod.id, params: base });
  if (runKey !== telemetryRecipe) { seen.clear(); telemetry.clear(); telemetryRecipe = runKey; }
  const key = JSON.stringify({ module: cur.mod.id, params });
  clearBenchError();
  try {
    const out = await api.post('/api/generators/preview', { module: cur.mod.id, params });
    if (serial === renderSerial && !$("process-popup").hidden && !isSecondReadingBenchOpen() && key === currentKey()) {
      draw(out.lines || []);
      renderedKey = key;
      $('process-status').textContent = axis ? `Preview current · ${axis} ${value}` : 'Preview current';
      $('process-create').disabled = creating;
      seen.set(value, out.points || 0);
      recordTelemetry(value, out.process?.telemetry || {});
      drawTelemetry();
    }
  } catch (e) {
    if (serial === renderSerial && !$("process-popup").hidden && !isSecondReadingBenchOpen()) {
      stop();
      $('process-status').textContent = 'Preview unavailable · previous drawing may be shown';
      showBenchError(e, render);
    }
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
function recordTelemetry(value, data) {
  const numeric = Object.fromEntries(Object.entries(data).filter(([,v]) => typeof v === 'number' && Number.isFinite(v)));
  telemetry.set(value, numeric);
  const select = $('process-trace');
  const previous = select.value;
  const keys = [...new Set([...telemetry.values()].flatMap(x => Object.keys(x)))];
  select.replaceChildren(new Option('Point count', 'points'));
  keys.forEach(key => select.add(new Option(key.replaceAll('_', ' '), key)));
  select.value = keys.includes(previous) || previous === 'points' ? previous : 'points';
  const values = $('process-values'); values.replaceChildren();
  for (const [key, value] of Object.entries(numeric)) {
    const dt = document.createElement('dt'); dt.textContent = key.replaceAll('_', ' ');
    const dd = document.createElement('dd'); dd.textContent = Number(value.toFixed(3)).toString();
    values.append(dt, dd);
  }
}
function drawTelemetry() {
  const svg = $('process-telemetry');
  if (!svg) return;
  svg.replaceChildren();
  const metric = $('process-trace').value;
  const samples = metric === 'points' ? [...seen] : [...telemetry].filter(([,v]) => metric in v).map(([x,v]) => [x,v[metric]]);
  samples.sort((a,b) => a[0]-b[0]);
  const span = bounds[1] - bounds[0] || 1;
  const low = Math.min(0,...samples.map(([,v])=>v));
  const high = Math.max(1,...samples.map(([,v])=>v));
  const y = v => 58 - (v-low)/(high-low)*56;
  const cur = currentSource();
  // A band is meaningful only for the source's measured variable; no generic
  // target or quality judgement is inferred for unrelated telemetry.
  if (metric === 'variable' && typeof cur?.params.target === 'number' && typeof cur?.params.tolerance === 'number') {
    const band = document.createElementNS(NS,'rect');
    band.setAttribute('x','0'); band.setAttribute('width','300');
    const hi = Math.min(high,cur.params.target+cur.params.tolerance), lo = Math.max(low,cur.params.target-cur.params.tolerance);
    band.setAttribute('y',String(y(hi))); band.setAttribute('height',String(Math.max(0,y(lo)-y(hi))));
    band.setAttribute('fill','var(--flexoki-green-950)'); svg.appendChild(band);
  }
  if (samples.length) {
    const el = document.createElementNS(NS,'polyline');
    el.setAttribute('points',samples.map(([v,n])=>`${((v-bounds[0])/span)*300},${y(n)}`).join(' '));
    svg.appendChild(el);
  }
  const x = ((Number($('process-scrub').value)-bounds[0])/span)*300;
  const cursor = document.createElementNS(NS,'line');
  for (const [k,v] of Object.entries({x1:x,x2:x,y1:0,y2:60})) cursor.setAttribute(k,String(v));
  svg.appendChild(cursor);
  $('process-telemetry-note').textContent = `${metric.replaceAll('_',' ')} · ${samples.length} observed preview samples · range ${low.toFixed(2)}–${high.toFixed(2)}. Unvisited steps are not measured here.`;
}
