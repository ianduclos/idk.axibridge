// Gesture Studies bench: saved pieces from the gesture research, each with its
// own few controls (spec: docs/superpowers/specs/2026-10-17-gesture-studies.md).
// A study dropdown; only the chosen study's controls; live preview through the
// registered `gesture_studies` source and the existing preview endpoint; Keep
// creates a new layer through the normal creation path (the server pins the
// frozen library then). Save as new study / delete / recipe validation use
// /api/gesture-studies. Hand / tempo / dance controls list every entry of the
// frozen library the server reports, never a hard-coded list.
//
// Studies v2 (2026-10-17):
// - a resumed layer STAYS PINNED to its library snapshot through every edit
//   (Ian: "stay pinned; explicit update"); its hand controls list that
//   snapshot's hands, and "Update to current library" re-pins on purpose;
// - a voices study (the chorus) previews each voice in its ink and Keep makes
//   a group with one layer per voice, each on its own pen (/api/gesture-studies/keep);
// - the Sampler shows the combination its seed picked (the sampler's summary).
import { api } from './api.js';
import { actions } from './main.js';
import { benchProjectEpoch, openBenchShell, closeBenchShell, clearBenchError, showBenchError } from './bench_host.js';
import { openGallerySave } from './gallery.js';
import { createPresetControls } from './module_library.js';

const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const copy = value => JSON.parse(JSON.stringify(value));
const KIND_OF = { hand: 'hand', hands: 'hand', tempo: 'tempo', trail: 'dance_trail' };
const DRAFT = '__draft__';
const drafts = new Map();
let active = null;
let wired = false;
let presetControls = null;
let catalogue = null;
const snapshots = new Map();   // pinned snapshot id -> {hand, tempo, dance_trail} options

// A study as the source takes it (the catalogue adds display-only fields).
function studyOf(entry) {
  // the catalogue and /validate add display-only fields; the source takes the study alone
  const { builtin, defaults, run_recipe, summary, voices, ...study } = entry; // eslint-disable-line no-unused-vars
  return copy(study);
}
async function loadCatalogue() {
  catalogue = await api.get('/api/gesture-studies');
  return catalogue;
}
// Key-order-independent JSON, so a resumed snapshot matches its catalogue study.
function canon(v) {
  if (Array.isArray(v)) return `[${v.map(canon).join(',')}]`;
  if (v && typeof v === 'object') return `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canon(v[k])}`).join(',')}}`;
  return JSON.stringify(v);
}
// The snapshot a resumed layer is pinned to, when it is not the current one.
function pinnedSnapshot() {
  const sid = active?.draft.params.library;
  return sid && sid !== catalogue?.snapshot ? sid : null;
}
function libraryList(kind) {
  const sid = pinnedSnapshot();
  return (sid && snapshots.get(sid)?.[kind]) || catalogue?.library?.[kind] || [];
}
async function ensureSnapshot() {
  const sid = pinnedSnapshot();
  if (!sid || snapshots.has(sid)) return;
  const res = await api.get(`/api/gesture-studies/library/${encodeURIComponent(sid)}`);
  snapshots.set(sid, res.library);
}
const isVoices = study => study?.keep === 'voices';
const isSampler = study => study?.engine === 'sampler';
function catalogueEntry(study) {
  return catalogue?.studies.find(s => s.id === study.id && s.version === study.version
    && canon(s.recipe) === canon(study.recipe)) || null;
}
function getAt(obj, path) {
  return path.split('.').reduce((cur, step) => (cur == null ? undefined : cur[/^\d+$/.test(step) ? Number(step) : step]), obj);
}
function targets(c) { return c.path ? [c.path] : c.paths; }
function valueOf(params, c) {
  return Object.prototype.hasOwnProperty.call(params.values, c.key) ? params.values[c.key] : getAt(params.study.recipe, targets(c)[0]);
}
function penWidth(study) {
  const r = study.recipe || {};
  return Number(r.renderer?.pen ?? r.pen ?? 0.4) || 0.4;
}
function fmt(v) { return typeof v === 'number' ? String(Math.round(v * 1e6) / 1e6) : String(v); }

function key() { return JSON.stringify(active?.draft.params); }
function remember(before) {
  active.draft.undo.push(before);
  if (active.draft.undo.length > 80) active.draft.undo.shift();
  active.draft.redo = [];
}
// An edit keeps a resumed layer's own library snapshot and pins: a control
// changes only what it controls. Only "Update to current library" re-pins.
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
  buildControls(); invalidate(); requestPreview();
}
function invalidate() {
  active.renderedKey = null;
  $('gesture-studies-kept').textContent = '';
  $('process-canvas').classList.add('gesture-studies-pending');
  renderControls();
}
function setValue(c, v) { change(p => { p.values[c.key] = v; }); }

// ---------------------------------------------------------------- controls
function libraryOptions(c) {
  const list = libraryList(KIND_OF[c.type]).map(e => [e.id, e.label]);
  return c.allow_none ? [[c.none_value ?? '', `— ${c.none_label || 'none'} —`], ...list] : list;
}
function selectEl(options, current) {
  const s = document.createElement('select');
  for (const [value, label] of options) s.add(new Option(label, value));
  if (current != null && ![...s.options].some(o => o.value === String(current))) s.add(new Option(String(current), String(current)));
  return s;
}
function field(label, control, c) {
  const wrap = document.createElement('label');
  wrap.className = 'gs-field';
  wrap.dataset.controlKey = c.key;
  const span = document.createElement('span');
  span.textContent = label;
  wrap.append(span, control);
  if (c.help) wrap.title = c.help;
  return wrap;
}
function numberControl(c, v) {
  const input = document.createElement('input');
  input.type = 'range'; input.min = String(c.min); input.max = String(c.max); input.step = 'any';
  input.value = String(v);
  const out = document.createElement('output'); out.textContent = fmt(v);
  const step = c.step || (c.type === 'int' ? 1 : (c.max - c.min) / 100);
  const quantise = raw => {
    let q = c.min + Math.round((Number(raw) - c.min) / step) * step;
    q = Math.min(c.max, Math.max(c.min, q));
    return c.type === 'int' ? Math.round(q) : Math.round(q * 1e9) / 1e9;
  };
  input.oninput = () => { out.textContent = fmt(quantise(input.value)); };
  input.onchange = () => setValue(c, quantise(input.value));
  const wrap = field(c.label, input, c);
  wrap.append(out);
  if (c.key === 'seed') {
    const box = document.createElement('div'); box.className = 'gs-seed';
    const num = document.createElement('input');
    num.type = 'number'; num.min = String(c.min); num.max = String(c.max); num.step = '1'; num.value = String(v);
    num.setAttribute('aria-label', c.label);
    num.onchange = () => { if (num.reportValidity() && num.value !== '') setValue(c, Math.round(Number(num.value))); };
    const next = document.createElement('button'); next.type = 'button'; next.textContent = 'Next seed'; next.className = 'gs-next-seed';
    next.onclick = () => setValue(c, Number(valueOf(active.draft.params, c)) >= c.max ? c.min : Number(valueOf(active.draft.params, c)) + 1);
    input.replaceWith(num); box.append(next);
    out.remove();
    wrap.append(box);
  }
  return wrap;
}
function choiceControl(c, v) {
  const choices = c.choices || [v];
  if (choices.length <= 6) {
    const group = document.createElement('div');
    group.className = 'gs-switch'; group.setAttribute('role', 'group');
    for (const value of choices) {
      const b = document.createElement('button');
      b.type = 'button'; b.dataset.value = JSON.stringify(value); b.textContent = String(value);
      b.setAttribute('aria-pressed', String(value === v));
      b.onclick = () => setValue(c, value);
      group.append(b);
    }
    return field(c.label, group, c);
  }
  const s = selectEl(choices.map(x => [JSON.stringify(x), String(x)]), JSON.stringify(v));
  s.value = JSON.stringify(v);
  s.onchange = () => setValue(c, JSON.parse(s.value));
  return field(c.label, s, c);
}
function refControl(c, v) {
  const s = selectEl(libraryOptions(c), v ?? '');
  s.value = v ?? '';
  s.onchange = () => setValue(c, c.allow_none && s.value === (c.none_value ?? '') ? (c.none_value ?? null) : s.value);
  return field(c.label, s, c);
}
function routeControl(c, v) {
  const items = Array.isArray(v) ? v : String(v || '').split(/\s+/).filter(Boolean);
  const lo = c.min_len ?? 1, hi = c.max_len ?? 4;
  const box = document.createElement('div'); box.className = 'gs-route';
  const read = () => [...box.querySelectorAll('select')].map(s => s.value).filter(Boolean);
  for (let i = 0; i < hi; i++) {
    const opts = (i >= lo ? [['', '— none —']] : []).concat(libraryOptions({ ...c, type: 'hand', allow_none: false }));
    const s = selectEl(opts, items[i] ?? '');
    s.value = items[i] ?? ''; s.setAttribute('aria-label', `${c.label} ${i + 1}`);
    s.onchange = () => setValue(c, read());
    box.append(s);
  }
  return field(c.label, box, c);
}
function poolControl(c, v) {
  const chosen = new Set(String(v || '').split(/\s+/).filter(Boolean));
  const box = document.createElement('div'); box.className = 'gs-pool';
  const hands = libraryList('hand');
  for (const h of hands) {
    const l = document.createElement('label'); l.className = 'gs-check';
    const cb = document.createElement('input'); cb.type = 'checkbox'; cb.value = h.id; cb.checked = chosen.has(h.id);
    cb.onchange = () => setValue(c, hands.filter(x => box.querySelector(`input[value="${x.id}"]`)?.checked).map(x => x.id).join(' '));
    l.append(cb, document.createTextNode(h.label));
    box.append(l);
  }
  const wrap = field(c.label, box, c);
  wrap.classList.add('gs-wide');
  return wrap;
}
function boolControl(c, v) {
  const l = document.createElement('label'); l.className = 'gs-check'; l.dataset.controlKey = c.key;
  const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!v;
  cb.onchange = () => setValue(c, cb.checked);
  l.append(cb, document.createTextNode(c.label));
  return l;
}
function controlEl(c, v) {
  if (c.type === 'int' || c.type === 'float') return numberControl(c, v);
  if (c.type === 'bool') return boolControl(c, v);
  if (c.type === 'choice') return choiceControl(c, v);
  if (c.type === 'hands') return c.join ? poolControl(c, v) : routeControl(c, v);
  return refControl(c, v);
}

function buildStudySelect() {
  const s = $('gs-study');
  s.replaceChildren();
  const groups = [['Studies', catalogue.studies.filter(x => x.builtin)], ['Saved studies', catalogue.studies.filter(x => !x.builtin)]];
  for (const [label, list] of groups) {
    if (!list.length) continue;
    const g = document.createElement('optgroup'); g.label = label;
    for (const st of list) { const o = new Option(st.label, st.id); o.title = st.source || ''; g.append(o); }
    s.append(g);
  }
  if (active && !catalogueEntry(active.draft.params.study)) {
    const st = active.draft.params.study;
    s.add(new Option(`${st.label} (this draft)`, DRAFT), 0);
  }
}
// Full rebuild: the study changed (or undo crossed a study change).
function buildControls() {
  if (!active) return;
  const params = active.draft.params;
  const st = params.study;
  const entry = catalogueEntry(st);
  buildStudySelect();
  $('gs-study').value = entry ? entry.id : DRAFT;
  $('gs-notes').textContent = st.notes || '';
  $('gs-source').textContent = [st.source, st.parent ? `forked from ${st.parent.id} v${st.parent.version}` : ''].filter(Boolean).join(' · ');
  const host = $('gs-controls');
  host.replaceChildren();
  const groups = new Map();
  // a resumed snapshot may predate the server spelling out choices: render the catalogue's controls
  for (const c of (entry || st).controls) {
    const g = c.group || '';
    if (!groups.has(g)) {
      const d = document.createElement('details'); d.open = true; d.className = 'gs-group';
      const sum = document.createElement('summary'); sum.textContent = g || 'Controls'; d.append(sum);
      groups.set(g, d); host.append(d);
    }
    groups.get(g).append(controlEl(c, valueOf(params, c)));
  }
  $('gs-delete').hidden = !(entry && !entry.builtin);
  $('gs-save-name').value = `${st.label} — variation`;
  active.builtFor = JSON.stringify(params);
  active.info = null;
  renderPinned(); renderInfo();
  renderControls();
}

// The pinned-library notice and its one way out.
function renderPinned() {
  const sid = pinnedSnapshot();
  $('gs-pinned').hidden = !sid;
  if (!sid) return;
  const mine = snapshots.get(sid)?.hand?.length, now = catalogue?.library?.hand?.length;
  $('gs-pinned-text').textContent = `This layer is pinned to library ${sid}${mine ? ` (${mine} hands)` : ''}; `
    + `the current library has ${now ?? '?'} hands. Edits keep the layer's own hands.`;
}
function updateLibrary() {
  if (!active || !pinnedSnapshot()) return;
  change(p => { delete p.library; delete p.pins; delete p.sampled; });
  buildControls();
}

// What the resolved study draws: the Sampler's combination, a chorus's voices.
function renderInfo() {
  const st = active?.draft.params.study;
  const box = $('gs-summary');
  const info = active?.info;
  box.hidden = !(isSampler(st) || isVoices(st));
  if (box.hidden) return;
  box.replaceChildren();
  if (!info) { box.textContent = isSampler(st) ? 'Sampling…' : ''; return; }
  if (isSampler(st) && info.summary) {
    const p = document.createElement('p'); p.className = 'hint gs-summary-text';
    p.textContent = info.summary; box.append(p);
  }
  if (info.voices?.length) {
    const ul = document.createElement('ul'); ul.className = 'gs-voices'; ul.setAttribute('aria-label', 'Voices and their pens');
    for (const v of info.voices) {
      const li = document.createElement('li'); li.title = v.label || '';
      const sw = document.createElement('span'); sw.className = 'gs-swatch'; sw.style.setProperty('--gs-voice', v.color);
      li.append(sw, document.createTextNode(`${v.index + 1} · ${v.ink}`));
      ul.append(li);
    }
    box.append(ul);
  }
}
function infoBody(p) {
  return { study: p.study, values: p.values, library: p.library || null, pins: p.pins || [], sampled: p.sampled || null };
}
async function refreshInfo() {
  if (!active) return;
  const owner = active, st = owner.draft.params.study;
  if (!(isSampler(st) || isVoices(st))) return;
  const expected = key();
  try {
    const res = await api.post('/api/gesture-studies/validate', infoBody(copy(owner.draft.params)));
    if (active !== owner || key() !== expected) return;
    owner.info = { summary: res.summary, voices: res.voices, run_recipe: res.run_recipe };
  } catch {
    if (active !== owner || key() !== expected) return;
    owner.info = null;
  }
  renderInfo();
}

function renderControls() {
  if (!active) return;
  if (active.builtFor !== JSON.stringify(active.draft.params)) {
    // values changed: refresh the displayed values in place (no rebuild, no focus loss)
    const params = active.draft.params;
    for (const c of params.study.controls) {
      const el = $('gs-controls').querySelector(`[data-control-key="${CSS.escape(c.key)}"]`);
      if (!el) continue;
      const v = valueOf(params, c);
      if (c.type === 'int' || c.type === 'float') {
        const r = el.querySelector('input'); if (r && document.activeElement !== r) r.value = String(v);
        const out = el.querySelector('output'); if (out) out.textContent = fmt(v);
      } else if (c.type === 'bool') el.querySelector('input').checked = !!v;
      else if (c.type === 'choice') {
        for (const b of el.querySelectorAll('button')) b.setAttribute('aria-pressed', String(b.dataset.value === JSON.stringify(v)));
        const s = el.querySelector('select'); if (s) s.value = JSON.stringify(v);
      } else if (c.type === 'hands' && c.join) {
        const chosen = new Set(String(v || '').split(/\s+/));
        for (const cb of el.querySelectorAll('input')) cb.checked = chosen.has(cb.value);
      } else if (c.type === 'hands') {
        [...el.querySelectorAll('select')].forEach((s, i) => { s.value = v[i] ?? ''; });
      } else el.querySelector('select').value = v ?? '';
    }
    active.builtFor = JSON.stringify(params);
  }
  const busy = active.keeping || active.savingGallery || active.inFlight || active.renderedKey !== key();
  $('gesture-studies-undo').disabled = !active.draft.undo.length || active.keeping;
  $('gesture-studies-redo').disabled = !active.draft.redo.length || active.keeping;
  $('process-gesture-studies').inert = active.keeping || active.saving;
  $('gesture-studies-keep').disabled = busy;
  $('gesture-studies-save-gallery').disabled = busy;
  $('gs-save').disabled = active.saving || active.inFlight;
  const label = active.draft.params.study.label;
  const voices = active.output?.layers?.length ? ` · ${active.output.layers.length} voices` : '';
  $('process-status').textContent = active.error ? 'Preview unavailable — retry below'
    : active.renderedKey !== key() ? `Drawing ${label}…`
      : `${label}${voices} · ${active.output.lines.length.toLocaleString()} ink paths · ${active.output.points.toLocaleString()} points${active.output.decimated ? ' · simplified preview' : ''}`;
  $('gesture-studies-keep').textContent = active.keeping ? 'Keeping…'
    : isVoices(active.draft.params.study) ? 'Keep as group' : 'Keep as layer';
  renderPinned();
}

// ---------------------------------------------------------------- shell
export function initGestureStudiesBench() {
  if (wired || !$('bench-controls')) return;
  wired = true;
  const panel = document.createElement('div');
  panel.id = 'process-gesture-studies'; panel.hidden = true;
  panel.innerHTML = `
    <label class="gs-field gs-study-field"><span>Study</span><select id="gs-study"></select></label>
    <div id="gs-pinned" class="gs-pinned" hidden><span id="gs-pinned-text"></span><br><button id="gs-update-library" type="button">Update to current library</button></div>
    <div id="gs-summary" class="gs-summary" aria-live="polite" hidden></div>
    <details id="gs-about"><summary>About this study</summary><p class="hint" id="gs-notes"></p><p class="hint" id="gs-source"></p></details>
    <div id="gs-controls"></div>
    <details id="gs-save-group"><summary>Save as new study</summary>
      <p class="hint">Saves this study with the current values as its recipe, on this machine (every project sees it). Kept layers never change when a study is edited or deleted.</p>
      <label class="gs-field"><span>Name</span><input id="gs-save-name" type="text" maxlength="120"></label>
      <div class="gs-row"><button id="gs-save" type="button">Save as new study</button><button id="gs-delete" type="button" hidden>Delete this saved study</button></div>
      <p class="hint" id="gs-save-status" aria-live="polite"></p></details>
    <details id="gs-recipe-group"><summary>Edit recipe</summary>
      <p class="hint">Advanced: the full recipe with the current values written in. Apply validates it (every module, param and library id); the controls keep pointing into it.</p>
      <textarea id="gs-recipe" spellcheck="false" rows="14"></textarea>
      <div class="gs-row"><button id="gs-recipe-apply" type="button">Apply recipe</button><button id="gs-recipe-reload" type="button">Reload</button></div>
      <p class="gs-error" id="gs-recipe-error" role="alert" hidden></p></details>`;
  $('bench-controls').append(panel);
  $('gs-study').onchange = () => {
    const id = $('gs-study').value;
    if (id === DRAFT || !active) return;
    const entry = catalogue.studies.find(s => s.id === id);
    if (!entry) return;
    const memory = active.draft.memory;
    memory[active.draft.params.study.id] = copy(active.draft.params.values);
    change(p => { p.study = studyOf(entry); p.values = copy(memory[entry.id] || {}); });
    buildControls();
  };
  $('gs-recipe-group').addEventListener('toggle', () => { if ($('gs-recipe-group').open) loadRecipe(); });
  $('gs-recipe-reload').onclick = loadRecipe;
  $('gs-recipe-apply').onclick = applyRecipe;
  $('gs-save').onclick = saveStudy;
  $('gs-update-library').onclick = updateLibrary;
  $('gs-delete').onclick = deleteStudy;
  const bar = document.createElement('div');
  bar.id = 'gesture-studies-actions'; bar.hidden = true;
  bar.innerHTML = `<button id="gesture-studies-undo">Undo</button><button id="gesture-studies-redo">Redo</button><span id="gesture-studies-kept" class="hint" aria-live="polite"></span><button id="gesture-studies-save-gallery" disabled>Save to gallery</button><button id="gesture-studies-keep" class="primary" disabled>Keep as layer</button>`;
  document.querySelector('.bench-main').append(bar);
  $('gesture-studies-undo').onclick = () => undo();
  $('gesture-studies-redo').onclick = () => undo(true);
  $('gesture-studies-keep').onclick = keep;
  $('gesture-studies-save-gallery').onclick = saveToGallery;
  document.addEventListener('keydown', e => {
    if (!active || e.target.matches('input,textarea,select,[contenteditable="true"]')) return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault(); e.stopImmediatePropagation(); undo(e.shiftKey);
    }
  }, true);
  document.addEventListener('bench-project-reset', () => { closeGestureStudiesBench(false); drafts.clear(); });
}

export async function openGestureStudiesBench({ mod, params, contextKey, onKeep, onClose }) {
  initGestureStudiesBench(); closeGestureStudiesBench(false);
  const original = { mod, params, contextKey, onKeep, onClose };
  const input = copy({ ...mod.defaults, ...params });
  input.values = input.values || {};
  delete input.voice;              // a chorus voice layer resumes the whole chorus
  const inputKey = JSON.stringify(input);
  const context = `${benchProjectEpoch()}:${contextKey || `new:${mod.id}`}`;
  let draft = drafts.get(context);
  if (!draft || (inputKey !== draft.inputKey && inputKey !== JSON.stringify(draft.params))) {
    draft = { params: input, inputKey, undo: [], redo: [], memory: {} };
    drafts.set(context, draft);
  }
  active = { mod, draft, external: params, onKeep, onClose, renderedKey: null, inFlight: false, queued: false,
             keeping: false, saving: false, savingGallery: false, output: null, error: false, builtFor: null };
  const owner = active;
  const popup = $('process-popup');
  popup.classList.remove('second-reading', 'watch-only', 'magnetic-field', 'hand-drift');
  popup.classList.add('gesture-studies');
  $('process-reference').setAttribute('hidden', '');
  $('process-canvas').closest('.preview-stage').classList.remove('comparing');
  $('process-title').textContent = 'Gesture Studies — working bench';
  $('process-gesture-studies').hidden = false; $('gesture-studies-actions').hidden = false;
  $('gesture-studies-kept').textContent = '';
  for (const id of ['process-params', 'process-second-reading', 'process-hand-drift', 'process-play', 'process-prev', 'process-next', 'process-scrub', 'process-readout', 'process-telemetry-row', 'process-create', 'process-reroll']) {
    const el = $(id); if (el) el.hidden = true;
  }
  $('process-status').hidden = false;
  $('process-status').textContent = 'Loading studies…';
  openBenchShell({ close: () => closeGestureStudiesBench(),
    reopen: () => openGestureStudiesBench(original),
    origin: contextKey?.startsWith('layer:') ? 'From kept layer · Keep creates a new layer' : 'Working draft · Keep creates a new layer' });
  $('process-canvas').replaceChildren();
  delete $('process-canvas').dataset.renderedRecipe;
  for (const id of ['gesture-studies-keep', 'gesture-studies-save-gallery', 'gesture-studies-undo', 'gesture-studies-redo']) $(id).disabled = true;
  try {
    await loadCatalogue();
  } catch (error) {
    if (active === owner) showBenchError(error, () => openGestureStudiesBench(original));
    return;
  }
  if (active !== owner) return;
  try { await ensureSnapshot(); } catch { /* the current library's lists stand in */ }
  if (active !== owner) return;
  installPresetControls();
  buildControls(); invalidate(); requestPreview();
}

export function closeGestureStudiesBench(notify = true) {
  if (!active) return;
  const closing = active;
  Object.assign(closing.external, copy(closing.draft.params));
  active = null;
  presetControls?.remove(); presetControls = null;
  $('process-popup').classList.remove('gesture-studies');
  $('process-canvas').classList.remove('gesture-studies-pending');
  $('process-gesture-studies').hidden = true; $('process-gesture-studies').inert = false;
  $('gesture-studies-actions').hidden = true;
  if (notify) { closeBenchShell(); closing.onClose?.(); }
}

function installPresetControls() {
  presetControls?.remove();
  const owner = active;
  presetControls = createPresetControls({
    kind: 'source',
    mod: owner.mod,
    getParams: () => {
      const p = copy(owner.draft.params);
      for (const k of ['library', 'pins', 'sampled', 'voice']) delete p[k];
      return p;
    },
    isBusy: () => active !== owner || owner.keeping || owner.savingGallery || owner.inFlight,
    onApply: async (params) => {
      if (active !== owner || owner.keeping || owner.savingGallery || owner.inFlight) {
        throw new Error('The working bench changed before this preset could be applied.');
      }
      remember(copy(owner.draft.params));
      owner.draft.params = { values: {}, ...copy(params) };
      buildControls(); invalidate();
      await requestPreview();
    },
  });
  presetControls.id = 'gesture-studies-module-presets';
  $('bench-controls')?.prepend(presetControls);
}

// ---------------------------------------------------------------- preview
async function requestPreview() {
  if (!active) return;
  const owner = active;
  if (owner.inFlight) { owner.queued = true; return; }
  const exact = copy(owner.draft.params), expected = JSON.stringify(exact);
  owner.inFlight = true; owner.queued = false; owner.error = false;
  clearBenchError(); renderControls();
  refreshInfo();
  try {
    const output = await api.post('/api/generators/preview', { module: owner.mod.id, params: exact });
    if (active !== owner || key() !== expected) return;
    owner.output = output; owner.renderedKey = expected;
    const svg = $('process-canvas');
    const W = output.width, H = output.height;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.style.aspectRatio = `${W} / ${H}`;
    svg.style.setProperty('--process-aspect', String(W / H));
    svg.replaceChildren();
    const frame = document.createElementNS(NS, 'rect');
    frame.setAttribute('class', 'gesture-studies-frame');
    for (const [k, v] of Object.entries({ x: 0, y: 0, width: W, height: H })) frame.setAttribute(k, String(v));
    const ink = document.createElementNS(NS, 'g');
    ink.classList.add('gesture-studies-ink');
    ink.style.strokeWidth = String(penWidth(exact.study));   // drawn at the pen's width
    // a chorus comes back as consecutive runs of lines, one per voice, each in its ink
    const runs = output.layers?.length ? output.layers : [{ paths: output.lines.length, color: null }];
    let at = 0;
    for (const run of runs) {
      const g = document.createElementNS(NS, 'g');
      if (run.color) {
        g.classList.add('gs-voice'); g.style.setProperty('--gs-voice', run.color);
        g.dataset.voice = run.name || '';
      }
      for (const line of output.lines.slice(at, at + run.paths)) {
        const el = document.createElementNS(NS, 'polyline');
        el.setAttribute('points', line.map(([x, y]) => `${x},${y}`).join(' '));
        el.setAttribute('class', 'draw-line');
        g.append(el);
      }
      at += run.paths;
      ink.append(g);
    }
    svg.append(frame, ink);
    svg.dataset.renderedRecipe = expected;
    svg.classList.remove('gesture-studies-pending');
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
  if (!active || $('gesture-studies-keep').disabled) return;
  const owner = active, exact = copy(owner.draft.params);
  owner.keeping = true; clearBenchError(); renderControls();
  try {
    if (isVoices(exact.study)) {
      // one undo step on the server: a group named after the study, a layer per voice on its own pen
      const res = await api.post('/api/gesture-studies/keep', { params: exact });
      await actions.refreshProject();
      await actions.refreshResolved();
      actions.setSelectionTargets([{ kind: 'group', id: res.group.id }]);
      const pens = new Set(res.layers.map(l => l.pen_id)).size;
      if (active === owner) $('gesture-studies-kept').textContent = `Kept · group ${res.group.name} · ${res.layers.length} layers on ${pens} pens`;
    } else {
      const layer = await owner.onKeep(exact);
      if (active === owner) $('gesture-studies-kept').textContent = `Kept · ${layer?.name || 'layer'}`;
    }
  } catch (error) {
    if (active === owner) showBenchError(error); // no automatic retry of writes
  } finally {
    owner.keeping = false; if (active === owner) renderControls();
  }
}

async function saveToGallery() {
  if (!active || $('gesture-studies-save-gallery').disabled) return;
  const owner = active, exact = copy(owner.draft.params), expected = key();
  owner.savingGallery = true; clearBenchError(); renderControls();
  try {
    await openGallerySave({ kind: 'generator', module: owner.mod.id, params: exact }, exact.study.label);
  } catch (error) {
    if (active === owner && key() === expected) showBenchError(error);
  } finally {
    owner.savingGallery = false;
    if (active === owner) renderControls();
  }
}

// ---------------------------------------------------------------- studies
async function saveStudy() {
  if (!active || active.saving) return;
  const owner = active, p = copy(owner.draft.params);
  const label = $('gs-save-name').value.trim();
  if (!label) { $('gs-save-status').textContent = 'Give the study a name.'; return; }
  owner.saving = true; renderControls(); $('gs-save-status').textContent = 'Saving…';
  try {
    const saved = await api.post('/api/gesture-studies', { label, ...infoBody(p) });
    await loadCatalogue();
    if (active !== owner) return;
    owner.saving = false;
    change(q => { q.study = studyOf(saved); q.values = {}; });
    buildControls();
    $('gs-save-status').textContent = `Saved · ${saved.label}`;
  } catch (error) {
    if (active === owner) $('gs-save-status').textContent = error.message || String(error);
  } finally {
    owner.saving = false; if (active === owner) renderControls();
  }
}

async function deleteStudy() {
  if (!active) return;
  const owner = active, st = owner.draft.params.study;
  if (!window.confirm(`Delete the saved study “${st.label}”? Kept layers keep their own copy.`)) return;
  try {
    await api.del(`/api/gesture-studies/${encodeURIComponent(st.id)}`);
    await loadCatalogue();
    if (active === owner) { buildControls(); $('gs-save-status').textContent = `Deleted · ${st.label} (this draft keeps it)`; }
  } catch (error) {
    if (active === owner) $('gs-save-status').textContent = error.message || String(error);
  }
}

async function loadRecipe() {
  if (!active) return;
  const p = copy(active.draft.params);
  $('gs-recipe-error').hidden = true;
  try {
    const res = await api.post('/api/gesture-studies/validate', infoBody(p));
    // a sampler shows the combination it drew; applying it makes a kit study of it
    if (active && key() === JSON.stringify(p)) $('gs-recipe').value = JSON.stringify(isSampler(p.study) ? res.run_recipe : res.recipe, null, 1);
  } catch (error) {
    $('gs-recipe-error').textContent = error.message || String(error); $('gs-recipe-error').hidden = false;
  }
}

async function applyRecipe() {
  if (!active) return;
  const owner = active;
  let recipe;
  $('gs-recipe-error').hidden = true;
  try { recipe = JSON.parse($('gs-recipe').value); } catch (error) {
    $('gs-recipe-error').textContent = `Not valid JSON: ${error.message}`; $('gs-recipe-error').hidden = false; return;
  }
  try {
    const st = owner.draft.params.study;
    const study = isSampler(st) ? { ...st, engine: 'kit', recipe } : { ...st, recipe };
    const res = await api.post('/api/gesture-studies/validate', { ...infoBody(owner.draft.params), study, values: {}, sampled: null });
    if (active !== owner) return;
    change(q => { q.study = studyOf(res); q.values = {}; });
    buildControls();
  } catch (error) {
    if (active === owner) { $('gs-recipe-error').textContent = error.message || String(error); $('gs-recipe-error').hidden = false; }
  }
}
