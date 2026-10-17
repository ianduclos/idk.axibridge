// Hand Drift bench: one line whose hand drifts along a route of learned hands.
// Every switch is a visible control; geometry always comes from the registered
// source through the existing preview endpoint (no client engine, no new API).
// Keep creates a new layer through the normal creation path; Resume copies a
// kept layer's recipe into a fresh draft.
import { api } from './api.js';
import { benchProjectEpoch, openBenchShell, closeBenchShell, clearBenchError, showBenchError } from './bench_host.js';
import { openGallerySave } from './gallery.js';
import { createPresetControls } from './module_library.js';

const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const copy = value => JSON.parse(JSON.stringify(value));
const drafts = new Map();
let active = null;
let wired = false;
let presetControls = null;

const HANDS = [
  ['matisse', 'Matisse'], ['hokusai', 'Hokusai'], ['ingres', 'Ingres'],
  ['shikasta', 'Shikasta'], ['nastaliq', 'Nasta’liq'],
  ['marden', 'Marden'], ['lichtenberg', 'Lichtenberg'], ['bubble', 'Bubble chamber'],
];
const TEMPI = [
  ['cmu_49_10', 'CMU 49 · fold in, curl'], ['cmu_55_mantis', 'CMU 55 · praying mantis'],
  ['staccato', 'Staccato'], ['levitation', 'Levitation'], ['fluidity', 'Fluidity'], ['particles', 'Particles'],
];
// [param, choices [value, label, hint]] — rendered as segmented switches.
const SWITCHES = {
  blend: [['mixture', 'Mixture', 'Each token from one hand, chosen by weight'],
          ['interp', 'Interpolate', 'Tokens moved toward the other hand: tokens neither hand has']],
  joins: [['smooth', 'Smooth', 'Chunks start fresh; curvature continuous at the joint'],
          ['chain', 'Chain', 'Chunks continue the previous context: straight runs and corners break in']],
  route_per_line: [['same', 'Same', 'Every line follows the route'], ['rotate', 'Rotate', 'Line i starts at hand i'],
                   ['shuffle', 'Shuffle', 'A seeded order per line'],
                   ['each', 'Each', 'Every line keeps ONE hand whole: no drift, grammars side by side']],
  regimes: [['off', 'Off', 'Wire: the centreline only'],
            ['timing', 'Timing', 'A dancer’s tempo: stillness pools into masses, flow leaves a nib'],
            ['field', 'Field', 'A noise-front field over the frame decides line, nib and mass']],
  ink: [['a', 'Outline', 'Ribbon outline and mass fill only'], ['b+', 'Insets', 'Concentric insets fill every nib'],
        ['c', 'Lanes', 'Passes along the stroke'], ['e', 'Nib traces', 'Paths of points along the nib edge'],
        ['c+e', 'Lanes + traces', 'Both pass families']],
};
const SLIDERS = [
  ['plateau', 'Plateau', 'hd-route-group', 0.01],
  ['length', 'Length (R)', 'hd-line-group', 0.1],
  ['lines', 'Lines', 'hd-line-group', 1],
  ['amount', 'Regime amount', 'hd-regime-group', 0.05],
  ['nib_width', 'Nib width (mm)', 'hd-regime-group', 0.1],
  ['mass_width', 'Mass width (mm)', 'hd-regime-group', 0.5],
  ['nib_angle', 'Nib angle (°)', 'hd-regime-group', 1],
  ['pen', 'Pen width (mm)', 'hd-ink-group', 0.05],
];

function key() { return JSON.stringify(active?.draft.params); }
function remember(before) {
  active.draft.undo.push(before);
  if (active.draft.undo.length > 80) active.draft.undo.shift();
  active.draft.redo = [];
}
function change(fn) {
  if (!active || active.keeping) return;
  const before = copy(active.draft.params);
  fn(active.draft.params);
  if (JSON.stringify(before) === key()) { renderControls(); return; }
  remember(before);
  invalidate();
  requestPreview();
}
function undo(redo = false) {
  if (!active || active.keeping) return;
  const from = redo ? active.draft.redo : active.draft.undo;
  const to = redo ? active.draft.undo : active.draft.redo;
  if (!from.length) return;
  to.push(copy(active.draft.params));
  active.draft.params = from.pop();
  invalidate(); requestPreview();
}
function invalidate() {
  active.renderedKey = null;
  $('hand-drift-kept').textContent = '';
  $('process-canvas').classList.add('hand-drift-pending');
  renderControls();
}

function segmented(name, choices) {
  const group = document.createElement('div');
  group.className = 'hd-switch';
  group.setAttribute('role', 'group');
  group.id = `hd-${name}`;
  for (const [value, label, hint] of choices) {
    const b = document.createElement('button');
    b.type = 'button';
    b.id = `hd-${name}-${value.replace('+', 'plus')}`;
    b.dataset.value = value;
    b.textContent = label;
    b.title = hint;
    b.setAttribute('aria-pressed', 'false');
    b.onclick = () => change(p => { p[name] = value; });
    group.append(b);
  }
  return group;
}
function field(label, control, id) {
  const wrap = document.createElement('label');
  wrap.className = 'hd-field';
  if (id) wrap.id = id;
  const span = document.createElement('span');
  span.textContent = label;
  wrap.append(span, control);
  return wrap;
}
function select(id, options) {
  const s = document.createElement('select');
  s.id = id;
  for (const [value, label] of options) s.add(new Option(label, value));
  return s;
}

export function initHandDriftBench() {
  if (wired || !$('bench-controls')) return;
  wired = true;
  const panel = document.createElement('div');
  panel.id = 'process-hand-drift'; panel.hidden = true;
  panel.innerHTML = `
    <details open id="hd-route-group"><summary>Route</summary>
      <p class="hint">The line starts in hand 1 and drifts through the others; each hand speaks pure on its plateau.</p>
      <div class="hd-hands" id="hd-hands"></div></details>
    <details open id="hd-line-group"><summary>Line</summary>
      <div class="hd-label">Blend</div><div id="hd-blend-slot"></div>
      <div class="hd-label">Joins</div><div id="hd-joins-slot"></div>
      <p class="hint" id="hd-joins-hint"></p>
      <div class="hd-label" id="hd-rpl-label">Route per line</div><div id="hd-route_per_line-slot"></div>
      <p class="hint" id="hd-route-hint"></p></details>
    <details open id="hd-regime-group"><summary>Regimes</summary>
      <div id="hd-regimes-slot"></div>
      <p class="hint" id="hd-regimes-hint"></p>
      <div id="hd-timing-fields"></div></details>
    <details open id="hd-ink-group"><summary>Ink</summary>
      <div id="hd-ink-slot"></div>
      <p class="hint">Only with regimes on. Every pass runs along the stroke or round it; nothing hatches.</p></details>
    <details id="hd-frame-group"><summary>Frame and seed</summary><div class="hd-grid">
      <label class="hd-field">Width (mm)<input id="hd-width" type="number" min="40" max="300" step="1"></label>
      <label class="hd-field">Height (mm)<input id="hd-height" type="number" min="40" max="218" step="1"></label>
      <label class="hd-field">Seed<input id="hd-seed" type="number" min="0" max="2147483647" step="1"></label>
      </div><button id="hd-next-seed" type="button">Next seed</button>
      <p class="hint">Line i uses seed + i. Fitted to the bed when kept.</p></details>`;
  $('bench-controls').append(panel);
  for (const name of Object.keys(SWITCHES)) $(`hd-${name}-slot`).replaceWith(segmented(name, SWITCHES[name]));
  const hands = $('hd-hands');
  for (let i = 1; i <= 4; i++) {
    const opts = (i > 2 ? [['none', '— none —']] : []).concat(HANDS);
    const s = select(`hd-hand_${i}`, opts);
    s.onchange = () => change(p => { p[`hand_${i}`] = s.value; });
    hands.append(field(`Hand ${i}`, s));
  }
  const tempo = select('hd-timing', TEMPI);
  tempo.onchange = () => change(p => { p.timing = tempo.value; });
  const wrist = document.createElement('input');
  wrist.type = 'checkbox'; wrist.id = 'hd-wrist_nib';
  wrist.onchange = () => change(p => { p.wrist_nib = wrist.checked; });
  const wristLabel = document.createElement('label');
  wristLabel.className = 'hd-check'; wristLabel.id = 'hd-wrist-label';
  wristLabel.append(wrist, document.createTextNode('Wrist holds the nib'));
  $('hd-timing-fields').append(field('Tempo', tempo, 'hd-tempo-label'), wristLabel);
  for (const [name, label, group, step] of SLIDERS) {
    const input = document.createElement('input');
    input.type = 'range'; input.id = `hd-${name}`; input.step = String(step);
    const out = document.createElement('output'); out.id = `hd-${name}-value`;
    const wrap = field(label, input, `hd-${name}-label`);
    wrap.append(out);
    input.oninput = () => { out.textContent = input.value; };
    input.onchange = () => change(p => { p[name] = Number(input.value); });
    const host = name === 'plateau' ? hands.parentElement : $(group);
    if (name === 'lines') $('hd-rpl-label').before(wrap);
    else if (name === 'length') $('hd-joins-hint').after(wrap);
    else if (name === 'pen') $('hd-ink').after(wrap);
    else host.append(wrap);
  }
  for (const name of ['width', 'height', 'seed']) {
    const input = $(`hd-${name}`);
    input.onchange = () => {
      if (!input.reportValidity() || input.value === '') { renderControls(); return; }
      change(p => { p[name] = Number(input.value); });
    };
  }
  $('hd-next-seed').onclick = () => change(p => { p.seed = (p.seed + 1) % 2147483648; });
  const bar = document.createElement('div');
  bar.id = 'hand-drift-actions'; bar.hidden = true;
  bar.innerHTML = `<button id="hand-drift-undo">Undo</button><button id="hand-drift-redo">Redo</button><span id="hand-drift-kept" class="hint" aria-live="polite"></span><button id="hand-drift-save-gallery" disabled>Save to gallery</button><button id="hand-drift-keep" class="primary" disabled>Keep as layer</button>`;
  document.querySelector('.bench-main').append(bar);
  $('hand-drift-undo').onclick = () => undo();
  $('hand-drift-redo').onclick = () => undo(true);
  $('hand-drift-keep').onclick = keep;
  $('hand-drift-save-gallery').onclick = saveToGallery;
  // Installed before the host's capture handler, so undo stays in this draft.
  document.addEventListener('keydown', e => {
    if (!active || e.target.matches('input,textarea,select,[contenteditable="true"]')) return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault(); e.stopImmediatePropagation(); undo(e.shiftKey);
    }
  }, true);
  document.addEventListener('bench-project-reset', () => { closeHandDriftBench(false); drafts.clear(); });
}

export function openHandDriftBench({ mod, params, contextKey, onKeep, onClose }) {
  initHandDriftBench(); closeHandDriftBench(false);
  const original = { mod, params, contextKey, onKeep, onClose };
  const input = copy({ ...mod.defaults, ...params });
  const inputKey = JSON.stringify(input);
  const context = `${benchProjectEpoch()}:${contextKey || `new:${mod.id}`}`;
  let draft = drafts.get(context);
  if (!draft || (inputKey !== draft.inputKey && inputKey !== JSON.stringify(draft.params))) {
    draft = { params: input, inputKey, undo: [], redo: [] };
    drafts.set(context, draft);
  }
  active = { mod, draft, external: params, onKeep, onClose, renderedKey: null, inFlight: false,
             queued: false, keeping: false, savingGallery: false, output: null, error: false };
  for (const [name, , , step] of SLIDERS) {
    const spec = mod.schema?.properties?.[name] || {};
    const el = $(`hd-${name}`);
    el.min = String(spec.minimum ?? 0); el.max = String(spec.maximum ?? 1); el.step = String(step);
  }
  installPresetControls();
  const popup = $('process-popup');
  popup.classList.remove('second-reading', 'watch-only', 'magnetic-field');
  popup.classList.add('hand-drift');
  $('process-reference').setAttribute('hidden', '');
  $('process-canvas').closest('.preview-stage').classList.remove('comparing');
  $('process-title').textContent = 'Hand Drift — working bench';
  $('process-hand-drift').hidden = false; $('hand-drift-actions').hidden = false;
  $('hand-drift-kept').textContent = '';
  for (const id of ['process-params', 'process-second-reading', 'process-play', 'process-prev', 'process-next', 'process-scrub', 'process-readout', 'process-telemetry-row', 'process-create', 'process-reroll']) {
    const el = $(id); if (el) el.hidden = true;
  }
  $('process-status').hidden = false;
  openBenchShell({ close: () => closeHandDriftBench(),
    reopen: () => openHandDriftBench(original),
    origin: contextKey?.startsWith('layer:') ? 'From kept layer · Keep creates a new layer' : 'Working draft · Keep creates a new layer' });
  $('process-canvas').replaceChildren();
  invalidate(); requestPreview();
}

export function closeHandDriftBench(notify = true) {
  if (!active) return;
  const closing = active;
  Object.assign(closing.external, copy(closing.draft.params));
  active = null;
  presetControls?.remove(); presetControls = null;
  $('process-popup').classList.remove('hand-drift');
  $('process-canvas').classList.remove('hand-drift-pending');
  $('process-hand-drift').hidden = true; $('process-hand-drift').inert = false;
  $('hand-drift-actions').hidden = true;
  if (notify) { closeBenchShell(); closing.onClose?.(); }
}

function installPresetControls() {
  presetControls?.remove();
  const owner = active;
  presetControls = createPresetControls({
    kind: 'source',
    mod: owner.mod,
    getParams: () => copy(owner.draft.params),
    isBusy: () => active !== owner || owner.keeping || owner.savingGallery || owner.inFlight,
    onApply: async (params) => {
      if (active !== owner || owner.keeping || owner.savingGallery || owner.inFlight) {
        throw new Error('The working bench changed before this preset could be applied.');
      }
      remember(copy(owner.draft.params));
      owner.draft.params = copy(params);
      invalidate();
      await requestPreview();
    },
  });
  presetControls.id = 'hand-drift-module-presets';
  $('bench-controls')?.prepend(presetControls);
}

function renderControls() {
  if (!active) return;
  const p = active.draft.params;
  for (const name of Object.keys(SWITCHES)) {
    for (const b of $(`hd-${name}`).querySelectorAll('button')) b.setAttribute('aria-pressed', String(b.dataset.value === p[name]));
  }
  for (let i = 1; i <= 4; i++) $(`hd-hand_${i}`).value = p[`hand_${i}`];
  $('hd-timing').value = p.timing;
  $('hd-wrist_nib').checked = !!p.wrist_nib;
  for (const [name] of SLIDERS) {
    $(`hd-${name}`).value = String(p[name]);
    $(`hd-${name}-value`).textContent = String(p[name]);
  }
  for (const name of ['width', 'height', 'seed']) $(`hd-${name}`).value = String(p[name]);
  const regimes = p.regimes !== 'off';
  $('hd-tempo-label').hidden = p.regimes !== 'timing';
  $('hd-wrist-label').hidden = p.regimes !== 'timing';
  for (const name of ['amount', 'nib_width', 'mass_width']) $(`hd-${name}-label`).hidden = !regimes;
  $('hd-nib_angle-label').hidden = !regimes || (p.regimes === 'timing' && p.wrist_nib);
  $('hd-ink-group').classList.toggle('hd-inactive', !regimes);
  const hint = (name) => SWITCHES[name].find(([v]) => v === p[name])?.[2] || '';
  $('hd-joins-hint').textContent = hint('joins');
  $('hd-route-hint').textContent = hint('route_per_line');
  $('hd-regimes-hint').textContent = hint('regimes');
  const busy = active.keeping || active.savingGallery || active.inFlight || active.renderedKey !== key();
  $('hand-drift-undo').disabled = !active.draft.undo.length || active.keeping;
  $('hand-drift-redo').disabled = !active.draft.redo.length || active.keeping;
  $('process-hand-drift').inert = active.keeping;
  $('hand-drift-keep').disabled = busy;
  $('hand-drift-save-gallery').disabled = busy;
  $('hand-drift-keep').textContent = active.keeping ? 'Keeping…' : 'Keep as layer';
  const route = [p.hand_1, p.hand_2, p.hand_3, p.hand_4].filter(h => h !== 'none')
    .map(h => HANDS.find(([v]) => v === h)?.[1] || h);
  const routeText = p.route_per_line === 'each' ? route.join(' | ') : route.join(' → ');
  $('process-status').textContent = active.error ? 'Preview unavailable — retry below'
    : active.renderedKey !== key() ? `Drawing ${routeText}…`
      : `${routeText} · ${active.output.lines.length.toLocaleString()} ink paths · ${active.output.points.toLocaleString()} points${active.output.decimated ? ' · simplified preview' : ''}`;
}

async function requestPreview() {
  if (!active) return;
  const owner = active;
  if (owner.inFlight) { owner.queued = true; return; }
  const exact = copy(owner.draft.params), expected = JSON.stringify(exact);
  owner.inFlight = true; owner.queued = false; owner.error = false;
  clearBenchError(); renderControls();
  try {
    const output = await api.post('/api/generators/preview', { module: owner.mod.id, params: exact });
    if (active !== owner || key() !== expected) return;
    owner.output = output; owner.renderedKey = expected;
    const svg = $('process-canvas');
    svg.setAttribute('viewBox', `0 0 ${exact.width} ${exact.height}`);
    svg.style.aspectRatio = `${exact.width} / ${exact.height}`;
    svg.style.setProperty('--process-aspect', String(exact.width / exact.height));
    svg.replaceChildren();
    const frame = document.createElementNS(NS, 'rect');
    frame.setAttribute('class', 'hand-drift-frame');
    for (const [k, v] of Object.entries({ x: 0, y: 0, width: exact.width, height: exact.height })) frame.setAttribute(k, String(v));
    const ink = document.createElementNS(NS, 'g');
    ink.classList.add('hand-drift-ink');
    // Drawn at the pen's width: what the plotter will lay down.
    ink.style.strokeWidth = String(exact.pen);
    for (const line of output.lines) {
      const el = document.createElementNS(NS, 'polyline');
      el.setAttribute('points', line.map(([x, y]) => `${x},${y}`).join(' '));
      el.setAttribute('class', 'draw-line');
      ink.append(el);
    }
    svg.append(frame, ink);
    svg.dataset.renderedRecipe = expected;
    svg.classList.remove('hand-drift-pending');
  } catch (error) {
    if (active === owner && key() === expected) { owner.error = true; showBenchError(error, requestPreview); }
  } finally {
    owner.inFlight = false;
    if (active === owner) {
      renderControls();
      if (owner.queued) requestPreview();
    }
  }
}

async function keep() {
  if (!active || $('hand-drift-keep').disabled) return;
  const owner = active, exact = copy(owner.draft.params);
  owner.keeping = true; clearBenchError(); renderControls();
  try {
    const layer = await owner.onKeep(exact);
    if (active === owner) $('hand-drift-kept').textContent = `Kept · ${layer?.name || 'layer'}`;
  } catch (error) {
    if (active === owner) showBenchError(error); // no automatic retry of writes
  } finally {
    owner.keeping = false; if (active === owner) renderControls();
  }
}

async function saveToGallery() {
  if (!active || $('hand-drift-save-gallery').disabled) return;
  const owner = active, exact = copy(owner.draft.params), expected = key();
  owner.savingGallery = true; clearBenchError(); renderControls();
  try {
    await openGallerySave({ kind: 'generator', module: owner.mod.id, params: exact }, owner.mod.label);
  } catch (error) {
    if (active === owner && key() === expected) showBenchError(error);
  } finally {
    owner.savingGallery = false;
    if (active === owner) renderControls();
  }
}
