// Gesture Studies bench: saved pieces from the gesture research, each with its
// own few controls (spec: docs/superpowers/specs/2026-10-17-gesture-studies.md).
// Live preview through the registered `gesture_studies` source and the existing
// preview endpoint; Keep creates a new layer through the normal creation path
// (the server pins the frozen library then). Save as new study / delete / recipe
// validation use /api/gesture-studies. Hand / tempo / dance controls list every
// entry of the frozen library the server reports, never a hard-coded list.
//
// Studies v2 (2026-10-17):
// - a resumed layer STAYS PINNED to its library snapshot through every edit
//   (Ian: "stay pinned; explicit update"); its hand controls list that
//   snapshot's hands, and "Update to current library" re-pins on purpose;
// - a voices study (the chorus) previews each voice in its ink and Keep makes
//   a group with one layer per voice, each on its own pen (/api/gesture-studies/keep);
// - the Sampler shows the combination its seed picked (the sampler's summary).
//
// Bench v3 (2026-10-19, docs/superpowers/specs/2026-10-19-study-bench-v3.md):
// - opens full-screen, canvas first; the column reads study → seed + Shuffle →
//   the study's controls → Measure (empty for now) → Advanced (collapsed);
// - a control that does nothing right now is dimmed and says why (`when`);
// - a die on the seed and on every hand control, Shuffle varies every unlocked
//   control within its bounds, a lock on each control; all of it is undoable,
//   locks included (they are part of the draft);
// - the last 12 previews as thumbnails under the canvas, from the previews
//   already drawn (no server call); clicking one restores it (one undo step);
// - every ink in its pen colour at its width (the preview's `styles`); the
//   previous drawing stays, dimmed, while the next draws, with an elapsed
//   timer after 1 s; previews are cached by their params (history and undo
//   are instant); studies that drew in under ~1 s preview while dragging;
// - a gallery of every study as a thumbnail, grouped by family.
//
// Measure (bench v3 move G, 2026-10-19): the round-15 measuring devices as an
// optional layer — Ian: "a selection of these to be added as a separate layer",
// the pen's flight "has to be optional". Off by default; each device a toggle
// with its placement (over / under / margin / beside) and two or three params.
// The devices live in the params (`devices`), so undo, history and the preview
// cache include them; Keep with any device on makes a group (the drawing + a
// Measure layer on its own pen) through /api/gesture-studies/keep. A device
// that finds nothing to read in the study says so instead of drawing nothing.
import { api } from './api.js';
import { actions } from './main.js';
import { benchProjectEpoch, openBenchShell, closeBenchShell, clearBenchError, showBenchError } from './bench_host.js';
import { openGallerySave } from './gallery.js';
import { createPresetControls } from './module_library.js';

const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const copy = value => JSON.parse(JSON.stringify(value));
const KIND_OF = { hand: 'hand', hands: 'hand', tempo: 'tempo', trail: 'dance_trail' };
const LIBRARY_TYPES = new Set(['hand', 'hands', 'tempo', 'trail']);
const DRAFT = '__draft__';
const HISTORY = 12;
const LIVE_MS = 1000;            // a study that drew faster than this previews while a slider drags
const LIVE_EVERY_MS = 180;       // … at most this often
const FAMILIES = ['Hands and drift', 'Measurement', 'Several voices', 'Swell', 'After Oehlen', 'Rivers', 'Composers'];
// Lucide (ISC): dices, lock, lock-open, shuffle, layout-grid
const ICON = {
  die: ['M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', 'M16 8h.01', 'M8 8h.01', 'M8 16h.01', 'M16 16h.01', 'M12 12h.01'],
  lock: ['M5 11h14v10H5z', 'M7 11V7a5 5 0 0 1 10 0v4'],
  open: ['M5 11h14v10H5z', 'M7 11V7a5 5 0 0 1 9.9-1'],
  shuffle: ['m18 14 4 4-4 4', 'm18 2 4 4-4 4', 'M2 18h1.973a4 4 0 0 0 3.3-1.7l5.454-8.6a4 4 0 0 1 3.3-1.7H22', 'M2 6h1.972a4 4 0 0 1 3.6 2.2', 'M22 18h-6.041a4 4 0 0 1-3.3-1.8l-.359-.45'],
  grid: ['M3 3h7v7H3z', 'M14 3h7v7h-7z', 'M14 14h7v7h-7z', 'M3 14h7v7H3z'],
};
const svgIcon = paths => `<svg class="tool-icon" viewBox="0 0 24 24" aria-hidden="true">${paths.map(d => `<path d="${d}"/>`).join('')}</svg>`;

const drafts = new Map();
let active = null;
let wired = false;
let presetControls = null;
let catalogue = null;
const snapshots = new Map();   // pinned snapshot id -> {hand, tempo, dance_trail} options
// preview results by canonical params: history clicks and undo redraw without the server
const previews = new Map();
const PREVIEW_CACHE = 24;

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
// The params as sent and cached: values in key order, so the same values are the same request.
function canonParams(p) {
  const out = copy(p);
  out.values = Object.fromEntries(Object.keys(out.values || {}).sort().map(k => [k, out.values[k]]));
  return out;
}
const paramsKey = p => canon(p);
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
function keyOf(c) { return c.key || targets(c)[0]; }
function valueOf(params, c) {
  return Object.prototype.hasOwnProperty.call(params.values, keyOf(c)) ? params.values[keyOf(c)] : getAt(activeStudy(params).recipe, targets(c)[0]);
}
// ---------------------------------------------------------------- modes: one choice picks the recipe and controls
// (river_zoom's line source). The value lives under modes.key in the values; missing = the first choice,
// which is the study's own recipe and controls.
function modeOf(params) {
  const m = params.study?.modes;
  if (!m) return null;
  const v = params.values?.[m.key];
  return m.choices.some(x => x.id === v) ? v : m.choices[0].id;
}
// The study as the chosen mode draws it: that mode's recipe and controls, no modes.
function activeStudy(params, study = params.study) {
  const m = study?.modes;
  if (!m) return study;
  const { modes, ...rest } = study; // eslint-disable-line no-unused-vars
  const mode = m.choices.find(x => x.id === modeOf(params)) || m.choices[0];
  return mode.recipe ? { ...rest, recipe: mode.recipe, controls: mode.controls } : rest;
}
// the controls the bench shows (a resumed snapshot may predate the server spelling out choices)
function shownControls() {
  const params = active.draft.params;
  return activeStudy(params, catalogueEntry(params.study) || params.study).controls;
}
function modeControl(m, current) {
  const group = document.createElement('div');
  group.className = 'gs-switch'; group.setAttribute('role', 'group'); group.setAttribute('aria-label', m.label);
  for (const choice of m.choices) {
    const b = document.createElement('button');
    b.type = 'button'; b.dataset.value = JSON.stringify(choice.id); b.textContent = choice.label;
    b.setAttribute('aria-pressed', String(choice.id === current));
    b.onclick = () => chooseMode(choice.id);
    group.append(b);
  }
  const wrap = document.createElement('div');
  wrap.className = 'gs-field gs-mode-field'; wrap.dataset.modeKey = m.key;
  const head = document.createElement('div'); head.className = 'gs-field-head';
  const label = document.createElement('label'); label.textContent = m.label;
  label.addEventListener('click', () => group.querySelector('button')?.focus());
  head.append(label);
  wrap.append(head, group);
  if (m.help) wrap.title = m.help;
  return wrap;
}
// Switching mode swaps the controls: each mode remembers its own values in the draft.
function chooseMode(id) {
  if (!active) return;
  const params = active.draft.params, m = params.study.modes;
  if (!m || modeOf(params) === id) return;
  const memory = active.draft.memory, at = mode => `${params.study.id}#${mode}`;
  memory[at(modeOf(params))] = copy(params.values);
  change(p => {
    p.values = copy(memory[at(id)] || {});
    // the first mode is the study as it always was: no mode value at all
    if (id === m.choices[0].id) delete p.values[m.key]; else p.values[m.key] = id;
  }, { rebuild: true });
}
function penWidth(study) {
  const r = study.recipe || {};
  return Number(r.renderer?.pen ?? r.pen ?? 0.4) || 0.4;
}
function fmt(v) { return typeof v === 'number' ? String(Math.round(v * 1e6) / 1e6) : String(v); }
function labelOf(v) {
  if (v === true) return 'on';
  if (v === false) return 'off';
  if (Array.isArray(v)) return v.join(', ');
  return String(v);
}

// ---------------------------------------------------------------- `when`: does a control act now?
function holds(w, read) {
  if (!w) return true;
  if (w.all) return w.all.every(x => holds(x, read));
  if (w.any) return w.any.some(x => holds(x, read));
  const v = read(w.key);
  if ('is' in w) return canon(v) === canon(w.is);
  if ('not' in w) return canon(v) !== canon(w.not);
  return (w.in || []).some(x => canon(x) === canon(v));
}
function reasonOf(w, byKey) {
  if (w.say) return w.say;
  const part = x => {
    if (x.all) return x.all.map(part).join(' and ');
    if (x.any) return x.any.map(part).join(', or ');
    const name = byKey.get(x.key)?.label || x.key;
    if ('is' in x) return `${name} is ${labelOf(x.is)}`;
    if ('not' in x) return `${name} is not ${labelOf(x.not)}`;
    return `${name} is ${x.in.map(labelOf).join(' or ')}`;
  };
  return `acts when ${part(w)}`;
}
function acts(c) {
  const params = active.draft.params;
  const byKey = new Map(shownControls().map(x => [keyOf(x), x]));
  return holds(c.when, k => (byKey.has(k) ? valueOf(params, byKey.get(k)) : undefined));
}

// ---------------------------------------------------------------- draft state, undo
// The draft is {params, locks}: locks (per study, by control key) are part of undo.
const state = () => ({ params: copy(active.draft.params), locks: copy(active.draft.locks) });
const stateKey = () => JSON.stringify({ p: active?.draft.params, l: active?.draft.locks });
function key() { return paramsKey(canonParams(active.draft.params)); }
function locksOf() {
  const id = active.draft.params.study.id;
  return active.draft.locks[id] || [];
}
const locked = c => locksOf().includes(keyOf(c));
function remember(before) {
  active.draft.undo.push(before);
  if (active.draft.undo.length > 80) active.draft.undo.shift();
  active.draft.redo = [];
}
// An edit keeps a resumed layer's own library snapshot and pins: a control
// changes only what it controls. Only "Update to current library" re-pins.
function change(fn, { rebuild = false } = {}) {
  if (!active || active.keeping) return;
  endDrag();
  const before = state(), was = stateKey(), wasKey = key();
  fn(active.draft.params, active.draft.locks);
  if (stateKey() === was) { renderControls(); return; }
  remember(before);
  if (rebuild) buildControls();
  if (key() !== wasKey) { invalidate(); requestPreview(); } else renderControls();
}
function restore(snapshot) {
  active.draft.params = snapshot.params;
  active.draft.locks = snapshot.locks || {};
}
function undo(redo = false) {
  if (!active || active.keeping) return;
  endDrag();
  const from = redo ? active.draft.redo : active.draft.undo;
  const to = redo ? active.draft.undo : active.draft.redo;
  if (!from.length) return;
  to.push(state());
  restore(from.pop());
  buildControls(); invalidate(); requestPreview();
}
function invalidate() {
  active.renderedKey = null;
  $('gesture-studies-kept').textContent = '';
  $('process-canvas').classList.add('gesture-studies-pending');
  renderControls();
}
function setValue(c, v) { change(p => { p.values[keyOf(c)] = v; }); }
function toggleLock(c) {
  change((p, locks) => {
    const id = p.study.id, k = keyOf(c);
    const set = new Set(locks[id] || []);
    if (set.has(k)) set.delete(k); else set.add(k);
    locks[id] = [...set];
  });
}

// A slider drag is ONE undo step: the state before the drag is remembered on
// release. Studies that drew in under LIVE_MS preview while dragging (throttled).
function dragTo(c, v) {
  if (!active || active.keeping) return;
  if (!active.drag || active.drag.key !== keyOf(c)) { endDrag(); active.drag = { key: keyOf(c), before: state(), was: key() }; }
  active.draft.params.values[keyOf(c)] = v;
  if (!(active.lastMs != null && active.lastMs < LIVE_MS)) return;   // slower studies redraw on release
  const now = performance.now();
  if (now - (active.lastLive || 0) < LIVE_EVERY_MS) {
    clearTimeout(active.liveTimer);
    active.liveTimer = setTimeout(() => dragPreview(), LIVE_EVERY_MS);
    return;
  }
  dragPreview();
}
function dragPreview() {
  if (!active?.drag) return;
  active.lastLive = performance.now();
  invalidate(); requestPreview();
}
function endDrag() {
  const d = active?.drag;
  if (!d) return;
  active.drag = null;
  clearTimeout(active.liveTimer);
  if (key() !== d.was) remember(d.before);
}
function releaseDrag(c, v) {
  if (!active) return;
  if (!active.drag) { setValue(c, v); return; }
  active.draft.params.values[keyOf(c)] = v;
  endDrag();
  invalidate(); requestPreview();
}

// ---------------------------------------------------------------- random values
const rand = n => Math.floor(Math.random() * n);
const pick = list => list[rand(list.length)];
function quantiser(c) {
  const step = c.step || (c.type === 'int' ? 1 : (c.max - c.min) / 100);
  return raw => {
    let q = c.min + Math.round((Number(raw) - c.min) / step) * step;
    q = Math.min(c.max, Math.max(c.min, q));
    return c.type === 'int' ? Math.round(q) : Math.round(q * 1e9) / 1e9;
  };
}
function randomSeed(c) { return c.min + rand(Math.min(c.max, c.min + 999999) - c.min + 1); }
function libraryIds(c) { return libraryList(KIND_OF[c.type]).map(e => e.id); }
function randomHand(c, current) {
  const ids = libraryIds(c).filter(x => x !== current);
  if (c.allow_none && Math.random() < 0.15) return c.none_value ?? '';
  return ids.length ? pick(ids) : current;
}
function randomRoute(c, current) {
  const ids = libraryIds(c);
  if (c.join) {                           // a pool: a fresh handful
    const n = Math.min(ids.length, Math.max(c.min_len ?? 1, 3 + rand(5)));
    return [...ids].sort(() => Math.random() - 0.5).slice(0, n).join(' ');
  }
  const lo = c.min_len ?? 1, hi = c.max_len ?? 4;
  const n = Array.isArray(current) && current.length ? current.length : lo + rand(hi - lo + 1);
  const out = [];
  while (out.length < n && out.length < ids.length) {
    const h = pick(ids);
    if (h !== out.at(-1)) out.push(h);
  }
  return out;
}
// Shuffle: a value anywhere within the control's bounds.
function shuffled(c, v) {
  if (c.type === 'int' || c.type === 'float') {
    if (keyOf(c) === 'seed') return randomSeed(c);
    return quantiser(c)(c.min + Math.random() * (c.max - c.min));
  }
  if (c.type === 'bool') return Math.random() < 0.5;
  if (c.type === 'choice') return pick(c.choices || [v]);
  if (c.type === 'toggles') {
    const lo = c.min_len ?? 0, hi = c.max_len ?? c.choices.length;
    const n = lo + rand(hi - lo + 1);
    return [...c.choices].sort(() => Math.random() - 0.5).slice(0, n).join(c.join || ',');
  }
  if (c.type === 'hands') return randomRoute(c, v);
  return randomHand(c, v);
}
function shuffle() {
  if (!active) return;
  change(p => {
    for (const c of shownControls()) if (!locked(c)) p.values[keyOf(c)] = shuffled(c, valueOf(p, c));
  });
}
function roll(c) {
  change(p => {
    const v = valueOf(p, c);
    p.values[keyOf(c)] = keyOf(c) === 'seed' ? randomSeed(c) : c.type === 'hands' ? randomRoute(c, v) : randomHand(c, v);
  });
}

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
function iconButton(cls, icon, label) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = cls; b.innerHTML = svgIcon(icon);
  b.setAttribute('aria-label', label); b.title = label;
  return b;
}
function lockButton(c) {
  const b = iconButton('gs-lock', ICON.open, `Lock ${c.label}`);
  b.setAttribute('aria-pressed', 'false');
  b.title = 'Lock: Shuffle leaves it alone';
  b.onclick = e => { e.preventDefault(); toggleLock(c); };
  return b;
}
function dieButton(c) {
  const b = iconButton('gs-die', ICON.die, keyOf(c) === 'seed' ? 'Random seed' : `Random ${c.label.toLowerCase()}`);
  b.onclick = e => { e.preventDefault(); roll(c); };
  return b;
}
function field(label, control, c) {
  const wrap = document.createElement('div');
  wrap.className = 'gs-field';
  wrap.dataset.controlKey = keyOf(c);
  const head = document.createElement('div'); head.className = 'gs-field-head';
  const span = document.createElement('label');
  span.textContent = label;
  const tools = document.createElement('span'); tools.className = 'gs-tools';
  if (LIBRARY_TYPES.has(c.type)) tools.append(dieButton(c));
  tools.append(lockButton(c));
  head.append(span, tools);
  const why = document.createElement('p'); why.className = 'gs-why'; why.hidden = true;
  wrap.append(head, control, why);
  if (control.matches?.('input,select')) {
    const id = `gs-c-${keyOf(c).replace(/[^A-Za-z0-9_-]/g, '-')}`;
    control.id = id; span.htmlFor = id;
  } else span.addEventListener('click', () => control.querySelector('input,select,button')?.focus());
  if (c.help) wrap.title = c.help;
  return wrap;
}
// the app paints a slider's fill on input events only; a value set in code paints here
function paintFill(input) {
  input.style.setProperty('--fill', `${Math.max(0, Math.min(100, (+input.value - +input.min) / (+input.max - +input.min) * 100))}%`);
}
function numberControl(c, v) {
  const input = document.createElement('input');
  input.type = 'range'; input.min = String(c.min); input.max = String(c.max); input.step = 'any';
  input.value = String(v); paintFill(input);
  const out = document.createElement('output'); out.textContent = fmt(v);
  const quantise = quantiser(c);
  input.oninput = () => { const q = quantise(input.value); out.textContent = fmt(q); dragTo(c, q); };
  input.onchange = () => releaseDrag(c, quantise(input.value));
  const wrap = field(c.label, input, c);
  wrap.querySelector('.gs-field-head label').after(out);
  return wrap;
}
function seedControl(c, v) {
  const wrap = document.createElement('div');
  wrap.className = 'gs-field gs-seed-field'; wrap.dataset.controlKey = keyOf(c);
  const head = document.createElement('div'); head.className = 'gs-field-head';
  const label = document.createElement('label'); label.textContent = c.label; label.htmlFor = 'gs-seed-input';
  const tools = document.createElement('span'); tools.className = 'gs-tools'; tools.append(lockButton(c));
  head.append(label, tools);
  const box = document.createElement('div'); box.className = 'gs-seed';
  const num = document.createElement('input');
  num.type = 'number'; num.id = 'gs-seed-input'; num.min = String(c.min); num.max = String(c.max); num.step = '1'; num.value = String(v);
  num.onchange = () => { if (num.reportValidity() && num.value !== '') setValue(c, Math.round(Number(num.value))); };
  const die = dieButton(c); die.id = 'gs-seed-die';
  die.innerHTML += '<span>Random</span>';
  const next = document.createElement('button'); next.type = 'button'; next.textContent = '+1'; next.className = 'gs-next-seed';
  next.title = 'Next seed'; next.setAttribute('aria-label', 'Next seed');
  next.onclick = () => setValue(c, Number(valueOf(active.draft.params, c)) >= c.max ? c.min : Number(valueOf(active.draft.params, c)) + 1);
  box.append(num, die, next);
  wrap.append(head, box);
  if (c.help) wrap.title = c.help;
  return wrap;
}
function choiceControl(c, v) {
  const choices = c.choices || [v];
  if (choices.length <= 6) {
    const group = document.createElement('div');
    group.className = 'gs-switch'; group.setAttribute('role', 'group'); group.setAttribute('aria-label', c.label);
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
function togglesControl(c, v) {
  const sep = c.join || ',';
  const on = () => String(valueOf(active.draft.params, c) || '').split(sep).map(x => x.trim()).filter(Boolean);
  const group = document.createElement('div');
  group.className = 'gs-switch gs-toggles'; group.setAttribute('role', 'group'); group.setAttribute('aria-label', c.label);
  const now = String(v || '').split(sep).map(x => x.trim());
  for (const word of c.choices) {
    const b = document.createElement('button');
    b.type = 'button'; b.dataset.value = word; b.textContent = word;
    b.setAttribute('aria-pressed', String(now.includes(word)));
    // toggling keeps the order the words already have; a new one joins at the end
    b.onclick = () => { const cur = on(); setValue(c, (cur.includes(word) ? cur.filter(x => x !== word) : [...cur, word]).join(sep)); };
    group.append(b);
  }
  return field(c.label, group, c);
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
  const l = document.createElement('label'); l.className = 'gs-check';
  const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!v;
  cb.onchange = () => setValue(c, cb.checked);
  l.append(cb, document.createTextNode(c.label));
  const wrap = field('', l, c);
  wrap.classList.add('gs-bool');
  wrap.querySelector('.gs-field-head label').replaceWith(l);
  return wrap;
}
function controlEl(c, v) {
  if (keyOf(c) === 'seed') return seedControl(c, v);
  if (c.type === 'int' || c.type === 'float') return numberControl(c, v);
  if (c.type === 'bool') return boolControl(c, v);
  if (c.type === 'choice') return choiceControl(c, v);
  if (c.type === 'toggles') return togglesControl(c, v);
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
// One line of Ian's own words from a study's notes (a quoted phrase), for the card and the header.
function quoteOf(st) {
  const m = /Ian[^"“]{0,40}["“]([^"”]{2,90})["”]/.exec(st?.notes || '');
  return m ? `“${m[1].trim()}”` : '';
}
// Full rebuild: the study changed (or undo crossed a study change).
function buildControls() {
  if (!active) return;
  const params = active.draft.params;
  const st = params.study;
  const entry = catalogueEntry(st);
  buildStudySelect();
  $('gs-study').value = entry ? entry.id : DRAFT;
  $('gs-study-name').textContent = st.label;
  $('gs-study-family').textContent = [st.family, quoteOf(st)].filter(Boolean).join(' · ');
  $('gs-notes').textContent = st.notes || '';
  $('gs-source').textContent = [st.source, st.parent ? `forked from ${st.parent.id} v${st.parent.version}` : ''].filter(Boolean).join(' · ');
  const seedHost = $('gs-seed-host'), host = $('gs-controls');
  seedHost.replaceChildren(); host.replaceChildren();
  const groups = new Map();
  if (st.modes) host.append(modeControl(st.modes, modeOf(params)));
  for (const c of shownControls()) {
    if (keyOf(c) === 'seed') { seedHost.append(controlEl(c, valueOf(params, c))); continue; }
    const g = c.group || '';
    if (!groups.has(g)) {
      const d = document.createElement('div'); d.className = 'gs-group';
      if (g) { const h = document.createElement('h4'); h.textContent = g; d.append(h); }
      groups.set(g, d); host.append(d);
    }
    groups.get(g).append(controlEl(c, valueOf(params, c)));
  }
  $('gs-no-seed').hidden = shownControls().some(c => keyOf(c) === 'seed');
  $('gs-delete').hidden = !(entry && !entry.builtin);
  $('gs-save-name').value = `${st.label} — variation`;
  active.builtFor = null;
  active.info = null;
  $('gs-measure-devices').dataset.sig = '';
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
  change(p => { delete p.library; delete p.pins; delete p.sampled; }, { rebuild: true });
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
    const res = await api.post('/api/gesture-studies/validate', infoBody(canonParams(owner.draft.params)));
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
  const params = active.draft.params;
  const byKey = new Map(shownControls().map(x => [keyOf(x), x]));
  if (active.builtFor !== stateKey()) {
    // values changed: refresh the displayed values in place (no rebuild, no focus loss)
    for (const c of byKey.values()) {
      const el = document.querySelector(`#process-gesture-studies [data-control-key="${CSS.escape(keyOf(c))}"]`);
      if (!el) continue;
      const v = valueOf(params, c);
      if (keyOf(c) === 'seed') {
        const n = el.querySelector('input'); if (n && document.activeElement !== n) n.value = String(v);
      } else if (c.type === 'int' || c.type === 'float') {
        const r = el.querySelector('input'); if (r && document.activeElement !== r) { r.value = String(v); paintFill(r); }
        const out = el.querySelector('output'); if (out) out.textContent = fmt(v);
      } else if (c.type === 'bool') el.querySelector('input[type=checkbox]').checked = !!v;
      else if (c.type === 'choice') {
        for (const b of el.querySelectorAll('.gs-switch button')) b.setAttribute('aria-pressed', String(b.dataset.value === JSON.stringify(v)));
        const s = el.querySelector('select'); if (s) s.value = JSON.stringify(v);
      } else if (c.type === 'toggles') {
        const on = String(v || '').split(c.join || ',').map(x => x.trim());
        for (const b of el.querySelectorAll('.gs-switch button')) b.setAttribute('aria-pressed', String(on.includes(b.dataset.value)));
      } else if (c.type === 'hands' && c.join) {
        const chosen = new Set(String(v || '').split(/\s+/));
        for (const cb of el.querySelectorAll('.gs-pool input')) cb.checked = chosen.has(cb.value);
      } else if (c.type === 'hands') {
        [...el.querySelectorAll('.gs-route select')].forEach((s, i) => { s.value = v[i] ?? ''; });
      } else el.querySelector('select').value = v ?? '';
      // locks and dims
      const isLocked = locked(c);
      const lock = el.querySelector('.gs-lock');
      if (lock) {
        lock.setAttribute('aria-pressed', String(isLocked));
        lock.innerHTML = svgIcon(isLocked ? ICON.lock : ICON.open);
      }
      const die = el.querySelector('.gs-die'); if (die) die.disabled = isLocked;
      el.classList.toggle('gs-locked', isLocked);
      const on = holds(c.when, k => (byKey.has(k) ? valueOf(params, byKey.get(k)) : undefined));
      el.classList.toggle('gs-inactive', !on);
      const why = el.querySelector('.gs-why');
      if (why) { why.hidden = on; why.textContent = on ? '' : reasonOf(c.when, byKey); }
    }
    active.builtFor = stateKey();
  }
  const busy = active.keeping || active.savingGallery || active.inFlight || active.renderedKey !== key();
  $('gesture-studies-undo').disabled = !active.draft.undo.length || active.keeping;
  $('gesture-studies-redo').disabled = !active.draft.redo.length || active.keeping;
  $('process-gesture-studies').inert = active.keeping || active.saving;
  $('gesture-studies-keep').disabled = busy;
  $('gesture-studies-save-gallery').disabled = busy;
  $('gs-save').disabled = active.saving || active.inFlight;
  $('gs-shuffle').disabled = active.keeping;
  renderStatus();
  $('gesture-studies-keep').textContent = active.keeping ? 'Keeping…'
    : isVoices(active.draft.params.study) || devicesOn().length ? 'Keep as group' : 'Keep as layer';
  renderPinned();
  renderMeasure();
  renderHistory();
}
function renderStatus() {
  const label = active.draft.params.study.label;
  const out = active.output;
  const nVoices = (out?.layers || []).filter((_, i) => i !== out.measure_layer).length;
  const voices = isVoices(active.draft.params.study) && nVoices ? ` · ${nVoices} voices` : '';
  const measured = out?.measure_layer != null ? ' · with Measure' : '';
  let text;
  if (active.error) text = 'Preview unavailable — retry below';
  else if (active.renderedKey !== key()) {
    const s = active.startedAt ? (performance.now() - active.startedAt) / 1000 : 0;
    text = `Drawing ${label}…${s >= 1 ? ` ${Math.floor(s)} s` : ''}`;
  } else {
    const o = active.output;
    text = `${label}${voices}${measured} · ${o.lines.length.toLocaleString()} ink paths · ${o.points.toLocaleString()} points${o.decimated ? ' · simplified preview' : ''}`;
  }
  $('process-status').textContent = text;
}

// ---------------------------------------------------------------- Measure (devices)
const PLACES = ['over', 'under', 'margin', 'beside'];
const SIDES = { margin: ['bottom', 'top', 'left', 'right'], beside: ['right', 'bottom'] };
const SIZE = { margin: 22, beside: 60 };
const DEVICE_FAMILIES = [['process', "From the drawing's process"], ['general', 'General']];
const deviceList = () => catalogue?.devices || [];
const devicesOn = () => (active?.draft.params.devices || []);
const specOf = id => devicesOn().find(d => d.id === id) || null;
const deviceEntry = id => deviceList().find(d => d.id === id);
function paramValue(entry, spec, name) {
  if (spec && Object.prototype.hasOwnProperty.call(spec, name)) return spec[name];
  if (Object.prototype.hasOwnProperty.call(entry.default, name)) return entry.default[name];
  return entry.params.find(x => x.name === name)?.default;
}
// The devices in the catalogue's order, so the same set is the same request.
function setDevices(p, list) {
  const order = deviceList().map(d => d.id);
  p.devices = [...list].sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
  if (!p.devices.length) delete p.devices;
}
function toggleDevice(id, on) {
  const memory = active.draft.deviceMemory || (active.draft.deviceMemory = {});
  change(p => {
    const list = (p.devices || []).filter(d => d.id !== id);
    const was = (p.devices || []).find(d => d.id === id);
    if (was) memory[id] = copy(was);
    if (on) list.push(copy(memory[id] || deviceEntry(id).default));
    setDevices(p, list);
  });
}
function editDevice(id, fn) {
  change(p => {
    const list = copy(p.devices || []);
    const spec = list.find(d => d.id === id);
    if (!spec) return;
    fn(spec);
    setDevices(p, list);
  });
}
function placeDevice(entry, place) {
  editDevice(entry.id, spec => {
    spec.place = place;
    if (SIDES[place]) {
      const same = entry.default.place === place;
      spec.side = same ? entry.default.side : SIDES[place][0];
      spec.size = same ? entry.default.size : SIZE[place];
    } else { delete spec.side; delete spec.size; }
  });
}
// The one drawn_by-like string control: '' (straight) or a library hand.
function deviceParamEl(entry, spec, param) {
  const v = paramValue(entry, spec, param.name);
  const wrap = document.createElement('div');
  wrap.className = 'gs-field gs-device-param'; wrap.dataset.param = param.name;
  const head = document.createElement('div'); head.className = 'gs-field-head';
  const label = document.createElement('label'); label.textContent = param.label || param.name;
  wrap.title = param.help || '';
  const id = `gs-dev-${entry.id}-${param.name}`;
  label.htmlFor = id;
  head.append(label);
  let control;
  const set = value => editDevice(entry.id, s => { s[param.name] = value; });
  if (param.type === 'int' || param.type === 'float') {
    control = document.createElement('input');
    control.type = 'range'; control.min = String(param.min); control.max = String(param.max); control.step = 'any';
    control.value = String(v); paintFill(control);
    const out = document.createElement('output'); out.textContent = fmt(v); head.append(out);
    const q = quantiser({ ...param, step: param.type === 'int' ? 1 : (param.max - param.min) / 100 });
    control.oninput = () => { out.textContent = fmt(q(control.value)); paintFill(control); };
    control.onchange = () => set(q(control.value));
  } else if (param.type === 'bool') {
    control = document.createElement('input'); control.type = 'checkbox'; control.checked = !!v;
    control.onchange = () => set(control.checked);
    const l = document.createElement('label'); l.className = 'gs-check';
    l.append(control, document.createTextNode(param.label || param.name));
    head.replaceChildren(l);
    control.id = id;
    wrap.append(head);
    return wrap;
  } else if (param.type === 'choice') {
    control = document.createElement('div');
    control.className = 'gs-switch'; control.setAttribute('role', 'group'); control.setAttribute('aria-label', `${entry.label}: ${param.name}`);
    for (const c of param.choices) {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = c; b.dataset.value = c;
      b.setAttribute('aria-pressed', String(c === v));
      b.onclick = () => set(c);
      control.append(b);
    }
  } else {                                       // drawn_by: straight, or a hand of this library
    control = selectEl([['', 'straight (machine)'], ...libraryList('hand').map(h => [h.id, h.label])], v ?? '');
    control.value = v ?? '';
    control.onchange = () => set(control.value);
  }
  control.id = id;
  wrap.append(head, control);
  return wrap;
}
function deviceNote(entry) {
  const out = active.output;
  if (!out || active.renderedKey !== key()) return null;
  return (out.devices || []).find(n => n.id === entry.id) || null;
}
function deviceRow(entry) {
  const spec = specOf(entry.id);
  const row = document.createElement('div');
  row.className = 'gs-device'; row.dataset.device = entry.id;
  row.classList.toggle('gs-device-on', !!spec);
  const head = document.createElement('div'); head.className = 'gs-device-head';
  const l = document.createElement('label'); l.className = 'gs-check gs-device-toggle';
  const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!spec;
  cb.setAttribute('aria-label', `Measure: ${entry.label}`);
  cb.onchange = () => toggleDevice(entry.id, cb.checked);
  l.append(cb, document.createTextNode(entry.label));
  l.title = entry.doc;
  head.append(l);
  const slowText = entry.slow && (entry.id !== 'meas_ledger' || paramValue(entry, spec, 'drawn_by')) ? entry.slow : '';
  const note = spec ? deviceNote(entry) : null;
  const took = note?.seconds >= 2 ? ` · ${Math.round(note.seconds)} s` : '';
  if (slowText || took) {
    const b = document.createElement('span'); b.className = 'gs-badge gs-device-slow';
    b.textContent = `slow${took}`; b.title = slowText || 'This device took a while on this drawing';
    head.append(b);
  }
  row.append(head);
  if (spec) {
    const body = document.createElement('div'); body.className = 'gs-device-body';
    const place = document.createElement('div');
    place.className = 'gs-switch gs-place'; place.setAttribute('role', 'group'); place.setAttribute('aria-label', `${entry.label}: placement`);
    for (const pl of PLACES) {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = pl; b.dataset.value = pl;
      b.setAttribute('aria-pressed', String(spec.place === pl));
      b.onclick = () => { if (spec.place !== pl) placeDevice(entry, pl); };
      place.append(b);
    }
    body.append(place);
    if (SIDES[spec.place]) {
      const side = selectEl(SIDES[spec.place].map(x => [x, `${spec.place === 'beside' ? 'beside, ' : 'margin, '}${x}`]), spec.side);
      side.value = spec.side; side.className = 'gs-side'; side.setAttribute('aria-label', `${entry.label}: side`);
      side.onchange = () => editDevice(entry.id, s => { s.side = side.value; });
      body.append(side);
    }
    for (const param of entry.shown) body.append(deviceParamEl(entry, spec, param));
    row.append(body);
    if (note && (note.error || !note.inks)) {
      const why = document.createElement('p'); why.className = 'gs-why gs-device-note'; why.setAttribute('role', 'status');
      why.textContent = note.error ? `Could not draw here: ${note.error}` : entry.empty;
      row.append(why);
    }
  }
  return row;
}
function renderMeasure() {
  const host = $('gs-measure-devices');
  $('gs-measure').hidden = !deviceList().length;
  if (!host || !deviceList().length) return;
  const notes = active.renderedKey === key() ? active.output?.devices : null;
  const sig = JSON.stringify([devicesOn(), notes, pinnedSnapshot()]);
  if (host.dataset.sig === sig) return;
  const focused = document.activeElement?.closest?.('.gs-device')?.dataset.device;
  host.dataset.sig = sig;
  host.replaceChildren();
  for (const [family, title] of DEVICE_FAMILIES) {
    const list = deviceList().filter(d => d.family === family);
    if (!list.length) continue;
    const g = document.createElement('div'); g.className = 'gs-device-family'; g.setAttribute('role', 'group'); g.setAttribute('aria-label', title);
    const h = document.createElement('h5'); h.textContent = title; g.append(h);
    for (const entry of list) g.append(deviceRow(entry));
    host.append(g);
  }
  if (focused) host.querySelector(`.gs-device[data-device="${CSS.escape(focused)}"] input[type=checkbox]`)?.focus({ preventScroll: true });
}

// ---------------------------------------------------------------- history strip
// The last previews as small drawings made from the previews already drawn.
function thumbOf(output) {
  const W = output.width, H = output.height;
  const total = output.lines.reduce((n, l) => n + l.length, 0);
  const stride = Math.max(1, Math.ceil(total / 2500));
  const style = styleRuns(output);
  const parts = [];
  let i = 0;
  for (const run of style) {
    const lines = output.lines.slice(i, i + run.paths); i += run.paths;
    const d = lines.map(line => {
      const pts = line.filter((_, j) => j % stride === 0 || j === line.length - 1);
      return pts.length > 1 ? `M${pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join('L')}` : '';
    }).join('');
    if (d) parts.push(`<path d="${d}" stroke="${run.color || 'currentColor'}"/>`);
  }
  return `<svg viewBox="0 0 ${W} ${H}" aria-hidden="true"><rect class="gs-history-sheet" width="${W}" height="${H}"/>`
    + `<g fill="none" stroke-width="${Math.max(W, H) / 120}" stroke-linecap="round" stroke-linejoin="round">${parts.join('')}</g></svg>`;
}
function addHistory(params, output) {
  const k = paramsKey(params);
  const h = active.draft.history;
  // a preview already in the strip keeps its place (going back to it does not reorder the strip)
  if (h.some(x => x.key === k)) return;
  h.push({ key: k, params: copy(params), svg: thumbOf(output), label: params.study.label,
           seed: params.values.seed ?? activeStudy(params).recipe?.seed });
  while (h.length > HISTORY) h.shift();
}
function renderHistory() {
  const strip = $('gs-history');
  const h = active.draft.history;
  strip.hidden = !h.length;
  const now = key();
  const sig = h.map(x => x.key).join('|') + '#' + now;
  if (strip.dataset.sig === sig) return;
  strip.dataset.sig = sig;
  strip.replaceChildren();
  [...h].reverse().forEach((item, i) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'gs-history-item';
    b.innerHTML = item.svg;
    const name = `${item.label}${item.seed != null ? ` · seed ${item.seed}` : ''}`;
    b.title = i ? `Go back to: ${name}` : `Latest: ${name}`;
    b.setAttribute('aria-label', `Preview ${h.length - i}: ${name}`);
    if (item.key === now) b.setAttribute('aria-current', 'true');
    b.onclick = () => restoreHistory(item);
    strip.append(b);
  });
}
function restoreHistory(item) {
  if (!active || item.key === key()) return;
  const sameStudy = canon(item.params.study) === canon(active.draft.params.study);
  change(p => {
    for (const k of Object.keys(p)) delete p[k];
    Object.assign(p, copy(item.params));
  }, { rebuild: !sameStudy });
}

// ---------------------------------------------------------------- gallery
let thumbPoll = null;
function galleryGroups() {
  const byFamily = new Map();
  for (const st of catalogue.studies) {
    const fam = st.builtin ? (st.family || 'Other studies') : 'Saved studies';
    if (!byFamily.has(fam)) byFamily.set(fam, []);
    byFamily.get(fam).push(st);
  }
  const order = [...FAMILIES, ...[...byFamily.keys()].filter(f => !FAMILIES.includes(f) && f !== 'Saved studies').sort(), 'Saved studies'];
  return order.filter(f => byFamily.has(f)).map(f => [f, byFamily.get(f)]);
}
function openGallery() {
  if (!active || !catalogue) return;
  const box = $('gs-gallery-grid');
  box.replaceChildren();
  const current = catalogueEntry(active.draft.params.study)?.id;
  for (const [family, list] of galleryGroups()) {
    const sec = document.createElement('section'); sec.className = 'gs-family';
    const h = document.createElement('h3'); h.textContent = family; sec.append(h);
    const grid = document.createElement('div'); grid.className = 'gs-cards';
    for (const st of list) {
      const card = document.createElement('button');
      card.type = 'button'; card.className = 'gs-card'; card.dataset.studyId = st.id;
      if (st.id === current) card.setAttribute('aria-current', 'true');
      card.innerHTML = '<span class="gs-card-sheet"><span class="gs-card-wait">Drawing…</span></span>'
        + '<span class="gs-card-name"></span><span class="gs-card-words"></span>';
      card.querySelector('.gs-card-name').textContent = st.label;
      card.querySelector('.gs-card-words').textContent = quoteOf(st);
      card.title = st.notes || st.label;
      card.onclick = () => { closeGallery(); chooseStudy(st.id); };
      grid.append(card);
    }
    sec.append(grid); box.append(sec);
  }
  $('process-popup').classList.add('gs-gallery-open');
  $('gs-gallery').hidden = false;
  $('gs-gallery-close').focus({ preventScroll: true });
  const ids = galleryGroups().flatMap(([, list]) => list.map(s => s.id));
  requestThumbnails(ids);
}
function closeGallery() {
  clearTimeout(thumbPoll); thumbPoll = null;
  $('process-popup').classList.remove('gs-gallery-open');
  if ($('gs-gallery')) $('gs-gallery').hidden = true;
}
function showThumbs(states) {
  let waiting = false;
  for (const [id, s] of Object.entries(states || {})) {
    const card = document.querySelector(`#gs-gallery .gs-card[data-study-id="${CSS.escape(id)}"]`);
    if (!card) continue;
    const sheet = card.querySelector('.gs-card-sheet');
    if (s.state === 'ready') {
      if (sheet.dataset.key !== s.key) {
        sheet.dataset.key = s.key;
        const img = document.createElement('img');
        img.alt = ''; img.src = `/api/gesture-studies/thumbnail/${encodeURIComponent(s.key)}`; img.decoding = 'async';
        sheet.replaceChildren(img);
      }
      card.classList.toggle('gs-slow', !!s.slow);
      if (s.slow && !card.querySelector('.gs-badge')) {
        const b = document.createElement('span'); b.className = 'gs-badge';
        b.textContent = `slow · ${Math.round(s.seconds)} s`; b.title = 'This study takes a while to draw';
        card.querySelector('.gs-card-name').append(b);
      }
    } else if (s.state === 'failed') {
      sheet.replaceChildren(Object.assign(document.createElement('span'), { className: 'gs-card-wait', textContent: 'No thumbnail', title: s.error || '' }));
    } else waiting = true;
  }
  return waiting;
}
async function requestThumbnails(ids) {
  let res;
  try { res = await api.post('/api/gesture-studies/thumbnails', { ids }); } catch { return; }
  if ($('gs-gallery').hidden) return;
  if (showThumbs(res.thumbnails)) pollThumbs();
}
function pollThumbs() {
  clearTimeout(thumbPoll);
  thumbPoll = setTimeout(async () => {
    if ($('gs-gallery').hidden) return;
    let res;
    try { res = await api.get('/api/gesture-studies/thumbnails'); } catch { pollThumbs(); return; }
    if (!$('gs-gallery').hidden && showThumbs(res.thumbnails)) pollThumbs();
  }, 1500);
}
function chooseStudy(id) {
  if (!active || id === DRAFT) return;
  const entry = catalogue.studies.find(s => s.id === id);
  if (!entry) return;
  if (catalogueEntry(active.draft.params.study)?.id === id) { buildControls(); return; }
  const memory = active.draft.memory;
  memory[active.draft.params.study.id] = copy(active.draft.params.values);
  change(p => { p.study = studyOf(entry); p.values = copy(memory[entry.id] || {}); }, { rebuild: true });
}

// ---------------------------------------------------------------- shell
export function initGestureStudiesBench() {
  if (wired || !$('bench-controls')) return;
  wired = true;
  const panel = document.createElement('div');
  panel.id = 'process-gesture-studies'; panel.hidden = true;
  panel.innerHTML = `
    <section class="gs-section gs-study-section" aria-label="Study">
      <div class="gs-study-head">
        <div class="gs-study-title"><h3 id="gs-study-name"></h3><p class="hint" id="gs-study-family"></p></div>
        <button id="gs-gallery-open" type="button" title="Choose a study by eye">${svgIcon(ICON.grid)}<span>Gallery</span></button>
      </div>
      <label class="gs-study-field"><span class="sr-only">Study</span><select id="gs-study" aria-label="Study"></select></label>
      <div id="gs-pinned" class="gs-pinned" hidden><span id="gs-pinned-text"></span><br><button id="gs-update-library" type="button">Update to current library</button></div>
      <div id="gs-summary" class="gs-summary" aria-live="polite" hidden></div>
    </section>
    <section class="gs-section gs-vary" aria-label="Seed and shuffle">
      <div id="gs-seed-host"></div>
      <p id="gs-no-seed" class="hint" hidden>This study draws the same every time: it has no seed.</p>
      <button id="gs-shuffle" type="button" title="Vary every unlocked control within its bounds">${svgIcon(ICON.shuffle)}<span>Shuffle</span></button>
    </section>
    <section class="gs-section" aria-label="Controls"><div id="gs-controls"></div></section>
    <section id="gs-measure" class="gs-section gs-measure" aria-label="Measure" hidden><h4>Measure</h4>
      <p class="hint">Readings of this drawing, laid over, under, in a margin or beside it. Off until you turn one on; Keep puts them on their own Measure layer and pen.</p>
      <div id="gs-measure-devices"></div></section>
    <details id="gs-advanced" class="gs-advanced"><summary>Advanced</summary>
      <div id="gs-advanced-body">
      <details id="gs-about"><summary>About this study</summary><p class="hint" id="gs-notes"></p><p class="hint" id="gs-source"></p></details>
      <details id="gs-save-group"><summary>Save as new study</summary>
        <p class="hint">Saves this study with the current values as its recipe, on this machine (every project sees it). Kept layers never change when a study is edited or deleted.</p>
        <label class="gs-text"><span>Name</span><input id="gs-save-name" type="text" maxlength="120"></label>
        <div class="gs-row"><button id="gs-save" type="button">Save as new study</button><button id="gs-delete" type="button" hidden>Delete this saved study</button></div>
        <p class="hint" id="gs-save-status" aria-live="polite"></p></details>
      <details id="gs-recipe-group"><summary>Edit recipe</summary>
        <p class="hint">The full recipe with the current values written in. Apply validates it (every module, param and library id); the controls keep pointing into it.</p>
        <textarea id="gs-recipe" spellcheck="false" rows="14"></textarea>
        <div class="gs-row"><button id="gs-recipe-apply" type="button">Apply recipe</button><button id="gs-recipe-reload" type="button">Reload</button></div>
        <p class="gs-error" id="gs-recipe-error" role="alert" hidden></p></details>
      </div>
    </details>`;
  $('bench-controls').append(panel);
  $('gs-study').onchange = () => chooseStudy($('gs-study').value);
  $('gs-gallery-open').onclick = openGallery;
  $('gs-shuffle').onclick = shuffle;
  $('gs-recipe-group').addEventListener('toggle', () => { if ($('gs-recipe-group').open) loadRecipe(); });
  $('gs-recipe-reload').onclick = loadRecipe;
  $('gs-recipe-apply').onclick = applyRecipe;
  $('gs-save').onclick = saveStudy;
  $('gs-update-library').onclick = updateLibrary;
  $('gs-delete').onclick = deleteStudy;

  const history = document.createElement('div');
  history.id = 'gs-history'; history.className = 'gs-history'; history.hidden = true;
  history.setAttribute('role', 'group'); history.setAttribute('aria-label', 'Recent previews');
  document.querySelector('.bench-main .process-body').after(history);

  const gallery = document.createElement('div');
  gallery.id = 'gs-gallery'; gallery.className = 'gs-gallery'; gallery.hidden = true;
  gallery.setAttribute('role', 'region'); gallery.setAttribute('aria-label', 'Study gallery');
  gallery.innerHTML = `<div class="gs-gallery-head"><h3>Studies</h3><p class="hint">Each study at its defaults. Choose one to open it.</p>
    <button id="gs-gallery-close" type="button">Back to the study</button></div><div id="gs-gallery-grid"></div>`;
  document.querySelector('#process-popup .bench-layout').append(gallery);
  $('gs-gallery-close').onclick = closeGallery;

  const bar = document.createElement('div');
  bar.id = 'gesture-studies-actions'; bar.hidden = true;
  bar.innerHTML = `<button id="gesture-studies-undo">Undo</button><button id="gesture-studies-redo">Redo</button><span id="gesture-studies-kept" class="hint" aria-live="polite"></span><button id="gesture-studies-save-gallery" disabled>Save to gallery</button><button id="gesture-studies-keep" class="primary" disabled>Keep as layer</button>`;
  document.querySelector('.bench-main').append(bar);
  $('gesture-studies-undo').onclick = () => undo();
  $('gesture-studies-redo').onclick = () => undo(true);
  $('gesture-studies-keep').onclick = keep;
  $('gesture-studies-save-gallery').onclick = saveToGallery;
  document.addEventListener('keydown', e => {
    if (!active) return;
    if (e.key === 'Escape' && !$('gs-gallery').hidden) {
      e.preventDefault(); e.stopImmediatePropagation(); closeGallery(); return;
    }
    if (e.target.matches('input,textarea,select,[contenteditable="true"]')) return;
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
  delete input.show;               // a kept drawing / Measure layer resumes the whole measured study
  const inputKey = JSON.stringify(input);
  const context = `${benchProjectEpoch()}:${contextKey || `new:${mod.id}`}`;
  let draft = drafts.get(context);
  if (!draft || (inputKey !== draft.inputKey && inputKey !== JSON.stringify(draft.params))) {
    draft = { params: input, inputKey, undo: [], redo: [], memory: {}, locks: {}, history: [], deviceMemory: {} };
    drafts.set(context, draft);
  }
  active = { mod, draft, external: params, onKeep, onClose, renderedKey: null, inFlight: false, queued: false,
             keeping: false, saving: false, savingGallery: false, output: null, error: false, builtFor: null,
             lastMs: null, drag: null, startedAt: null };
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
    cancelGesture: () => { if ($('gs-gallery') && !$('gs-gallery').hidden) { closeGallery(); return true; } return false; },
    reopen: () => openGestureStudiesBench(original),
    origin: contextKey?.startsWith('layer:') ? 'From kept layer · Keep creates a new layer' : 'Working draft · Keep creates a new layer' });
  // the drawing comes first: the bench opens full-screen (Restore gives the old popup back)
  popup.classList.add('expanded');
  $('process-expand').textContent = 'Restore';
  $('process-expand').setAttribute('aria-pressed', 'true');
  $('process-canvas').replaceChildren();
  delete $('process-canvas').dataset.renderedRecipe;
  $('gs-history').dataset.sig = '';
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
  endDrag();
  clearInterval(closing.timer);
  closeGallery();
  Object.assign(closing.external, copy(closing.draft.params));
  active = null;
  presetControls?.remove(); presetControls = null;
  $('process-popup').classList.remove('gesture-studies');
  $('process-canvas').classList.remove('gesture-studies-pending');
  $('process-gesture-studies').hidden = true; $('process-gesture-studies').inert = false;
  $('gesture-studies-actions').hidden = true;
  $('gs-history').hidden = true;
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
      for (const k of ['library', 'pins', 'sampled', 'voice', 'show']) delete p[k];
      return p;
    },
    isBusy: () => active !== owner || owner.keeping || owner.savingGallery || owner.inFlight,
    onApply: async (params) => {
      if (active !== owner || owner.keeping || owner.savingGallery || owner.inFlight) {
        throw new Error('The working bench changed before this preset could be applied.');
      }
      endDrag();
      remember(state());
      owner.draft.params = { values: {}, ...copy(params) };
      buildControls(); invalidate();
      await requestPreview();
    },
  });
  presetControls.id = 'gesture-studies-module-presets';
  const h = document.createElement('h4'); h.textContent = 'Presets';
  presetControls.prepend(h);
  $('gs-advanced-body')?.prepend(presetControls);
}

// ---------------------------------------------------------------- preview
// One run of consecutive lines per ink: the server's `styles` (colour + pen
// width), within a chorus's voices (`layers`), else the study's one pen.
function styleRuns(output) {
  if (output.styles?.length) return output.styles.map(s => ({ ...s }));
  if (output.layers?.length) return output.layers.map(l => ({ color: l.color, width: null, paths: l.paths }));
  return [{ color: null, width: null, paths: output.lines.length }];
}
function draw(output, exact, expected) {
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
  ink.style.strokeWidth = String(penWidth(activeStudy(exact)));   // drawn at the pen's width
  // a chorus comes back as consecutive runs of lines, one per voice, each in its ink;
  // within (and outside) them, runs of one ink colour and pen width
  const voices = output.layers?.length ? output.layers : [{ paths: output.lines.length, color: null }];
  const runs = styleRuns(output);
  let at = 0, r = 0, left = runs[0]?.paths ?? 0;
  for (const voice of voices) {
    const g = document.createElementNS(NS, 'g');
    if (voice.color) {
      g.classList.add('gs-voice'); g.style.setProperty('--gs-voice', voice.color);
      g.dataset.voice = voice.name || '';
      if (voice === output.layers?.[output.measure_layer]) g.classList.add('gs-measure-ink');
    }
    let sub = null, subRun = -1;
    for (const line of output.lines.slice(at, at + voice.paths)) {
      while (left <= 0 && r < runs.length - 1) { r++; left = runs[r].paths; }
      if (subRun !== r) {
        sub = document.createElementNS(NS, 'g'); subRun = r;
        const run = runs[r];
        // a run's own colour wins (a voice's runs carry its ink; the Measure layer mixes inks)
        if (run?.color) { sub.classList.add('gs-ink'); sub.style.setProperty('--gs-ink', run.color); }
        if (run?.width) sub.style.strokeWidth = String(run.width);
        g.append(sub);
      }
      const el = document.createElementNS(NS, 'polyline');
      el.setAttribute('points', line.map(([x, y]) => `${x},${y}`).join(' '));
      el.setAttribute('class', 'draw-line');
      sub.append(el);
      left--;
    }
    at += voice.paths;
    ink.append(g);
  }
  svg.append(frame, ink);
  svg.dataset.renderedRecipe = JSON.stringify(exact);
  svg.dataset.renderedKey = expected;
  svg.classList.remove('gesture-studies-pending');
}
function cachePreview(k, output) {
  previews.delete(k); previews.set(k, output);
  let points = [...previews.values()].reduce((n, o) => n + (o.points || 0), 0);
  while (previews.size > PREVIEW_CACHE || (previews.size > 1 && points > 3_000_000)) {
    const [old, o] = previews.entries().next().value;
    previews.delete(old); points -= o.points || 0;
  }
}
async function requestPreview() {
  if (!active) return;
  const owner = active;
  if (owner.inFlight) { owner.queued = true; return; }
  const exact = canonParams(owner.draft.params), expected = paramsKey(exact);
  owner.error = false;
  clearBenchError();
  refreshInfo();
  const hit = previews.get(expected);
  if (hit) {                                  // drawn before: history, undo, a lock toggled back
    owner.output = hit; owner.renderedKey = expected;
    draw(hit, exact, expected);
    if (!owner.drag) addHistory(exact, hit);
    renderControls();
    return;
  }
  owner.inFlight = true; owner.queued = false;
  owner.startedAt = performance.now();
  clearInterval(owner.timer);
  owner.timer = setInterval(() => { if (active === owner && owner.inFlight) renderStatus(); }, 500);
  renderControls();
  try {
    const output = await api.post('/api/generators/preview', { module: owner.mod.id, params: exact });
    owner.lastMs = performance.now() - owner.startedAt;
    cachePreview(expected, output);
    // while a slider drags, the latest finished drawing shows even if the slider has moved on
    if (active !== owner || (key() !== expected && !owner.drag)) return;
    owner.output = output; owner.renderedKey = expected;
    draw(output, exact, expected);
    if (!owner.drag) addHistory(exact, output);      // the strip keeps settled previews, not every drag step
  } catch (error) {
    if (active === owner && key() === expected) { owner.error = true; showBenchError(error, requestPreview); }
  } finally {
    owner.inFlight = false; owner.startedAt = null;
    clearInterval(owner.timer);
    if (active === owner) {
      renderControls();
      // the latest values, unless a slow study's slider is still being dragged (it draws on release)
      const dragging = owner.drag && !(owner.lastMs != null && owner.lastMs < LIVE_MS);
      if (owner.queued || (owner.renderedKey !== key() && !dragging)) { owner.queued = false; if (!owner.error) requestPreview(); }
    }
  }
}

async function keep() {
  if (!active || $('gesture-studies-keep').disabled) return;
  const owner = active, exact = canonParams(owner.draft.params);
  owner.keeping = true; clearBenchError(); renderControls();
  try {
    if (isVoices(exact.study) || exact.devices?.length) {
      // one undo step on the server: a group named after the study, a layer per voice on its own pen,
      // and with devices on, a Measure layer of the device inks on its own pen
      const res = await api.post('/api/gesture-studies/keep', { params: exact });
      await actions.refreshProject();
      await actions.refreshResolved();
      actions.setSelectionTargets([{ kind: 'group', id: res.group.id }]);
      const pens = new Set(res.layers.map(l => l.pen_id || '')).size;
      const measure = res.layers.some(l => l.name === 'Measure') ? ' (with Measure)' : '';
      if (active === owner) $('gesture-studies-kept').textContent = `Kept · group ${res.group.name} · ${res.layers.length} layers on ${pens} pens${measure}`;
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
  const owner = active, exact = canonParams(owner.draft.params), expected = key();
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
    change(q => { q.study = studyOf(saved); q.values = {}; }, { rebuild: true });
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
    if (active && JSON.stringify(active.draft.params) === JSON.stringify(p)) $('gs-recipe').value = JSON.stringify(isSampler(p.study) ? res.run_recipe : res.recipe, null, 1);
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
    // a study with modes: the recipe edited is the chosen mode's, so the result is that mode as a study of its own
    const st = activeStudy(owner.draft.params);
    const study = isSampler(st) ? { ...st, engine: 'kit', recipe } : { ...st, recipe };
    const res = await api.post('/api/gesture-studies/validate', { ...infoBody(owner.draft.params), study, values: {}, sampled: null });
    if (active !== owner) return;
    change(q => { q.study = studyOf(res); q.values = {}; }, { rebuild: true });
  } catch (error) {
    if (active === owner) { $('gs-recipe-error').textContent = error.message || String(error); $('gs-recipe-error').hidden = false; }
  }
}
