// Two editors over one score. The server owns validation and played geometry;
// the bench owns whole-score history, selection, and the preview lifecycle.
import { api } from './api.js';
import { actions } from './main.js';
import { benchProjectEpoch, openBenchShell, closeBenchShell } from './bench_host.js';

const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const copy = value => JSON.parse(JSON.stringify(value));
const randomSeed = () => Math.floor(Math.random() * 2147483647);
const pick = values => values[Math.floor(Math.random() * values.length)];
const ICON = {
  die: ['M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', 'M8 8h.01', 'M16 8h.01', 'M12 12h.01', 'M8 16h.01', 'M16 16h.01'],
  lock: ['M5 11h14v10H5z', 'M7 11V7a5 5 0 0 1 10 0v4'],
  open: ['M5 11h14v10H5z', 'M7 11V7a5 5 0 0 1 9.9-1'],
};
const icon = name => `<svg class="tool-icon" viewBox="0 0 24 24" aria-hidden="true">${ICON[name].map(d => `<path d="${d}"/>`).join('')}</svg>`;
let active = null;
let catalogue = null;
let wired = false;
const drafts = new Map();
const previews = new Map();
const keyOf = score => JSON.stringify(score);
const bench = score => (score.decisions ||= {}).bench ||= {};
const relSpec = kind => catalogue.relations.find(r => r.id === kind);
const lockedControls = score => bench(score).control_locks || [];
const lockedRelations = score => bench(score).locked_relations || [];
const libOf = owner => ({ library: owner.library, pins: owner.pins });
const paramsOf = owner => ({ score: copy(owner.draft.score), ...libOf(owner) });
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}
function svg(tag, attrs = {}) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}
function button(label, fn, glyph) {
  const b = el('button', '', glyph ? null : label); b.type = 'button';
  b.setAttribute('aria-label', label); b.title = label;
  if (glyph) b.innerHTML = icon(glyph);
  b.onclick = e => { e.stopPropagation(); fn(e); };
  return b;
}
function select(label, options, value, change, multiple = false) {
  const s = el('select'); s.setAttribute('aria-label', label); s.multiple = multiple;
  for (const option of options) {
    const id = typeof option === 'object' ? option.id : option;
    const o = el('option', '', typeof option === 'object' ? option.label || id : id === '*' ? 'all' : id);
    o.value = id; o.selected = multiple ? (value || []).includes(id) : String(value) === String(id); s.append(o);
  }
  s.onchange = () => change(multiple ? [...s.selectedOptions].map(o => o.value) : s.value);
  return s;
}
function fieldLabel(label, control) {
  const wrap = el('label', 'sy-label'); wrap.append(el('span', '', label), control); return wrap;
}
function fail(error) {
  if (!active) return;
  $('sy-error').textContent = error.message || String(error); $('sy-error').hidden = false;
}
function updateReady() {
  if (!active) return;
  const ready = active.loaded && !active.busy && active.rendered === keyOf(active.draft.score);
  $('sy-keep').disabled = !ready; $('sy-keep-new').disabled = !ready; $('sy-save').disabled = !ready;
  $('sy-undo').disabled = active.busy || !active.draft.undo.length;
  $('sy-redo').disabled = active.busy || !active.draft.redo.length;
  $('sy-editors').inert = Boolean(active.busy || !active.loaded);
  document.querySelector('#process-synthesis .sy-toolbar').inert = Boolean(active.busy || !active.loaded);
  $('sy-gallery-grid').inert = Boolean(active.busy || !active.loaded);
  $('sy-save-name').disabled = Boolean(active.busy);
  $('sy-shuffle').disabled = active.busy || !active.draft.score;
  $('sy-recompose').disabled = active.busy || !active.draft.score?.decisions?.writers?.length;
  $('sy-recompose').title = active.draft.score?.decisions?.writers?.length ? 'Ask the writer for a new score around locks' : 'This sealed score has no writer to ask';
}
// Mutations are serialized. A hold always sees the score immediately before
// its edit, and stale responses from a closed bench cannot replace a new draft.
function transact(task) {
  const owner = active;
  if (!owner) return Promise.resolve();
  owner.queue = owner.queue.then(async () => {
    if (active !== owner) return;
    owner.busy = true; updateReady(); $('sy-error').hidden = true;
    try {
      const score = await task(copy(owner.draft.score), owner);
      if (score && active === owner) commit(score);
    } catch (error) { if (active === owner) { fail(error); if (owner.draft.score) render(); } }
    finally { owner.busy = false; if (active === owner) updateReady(); }
  });
  return owner.queue;
}
function change(mutator, edited = null) {
  return transact(async (score, owner) => {
    const ripple = bench(score).ripple || 'all';
    if (edited && ripple !== 'all') score = (await api.post('/api/synthesis/hold', { score, edited, ripple, ...libOf(owner) })).score;
    if (active !== owner) return null;
    mutator(score);
    return (await api.post('/api/synthesis/validate', { score, ...libOf(owner) })).score;
  });
}
function rememberPreview(score) {
  const d = active.draft, key = keyOf(score);
  let index = d.history.findIndex(item => keyOf(item.score) === key);
  if (index < 0) {
    d.history.push({ score: copy(score), thumb: null });
    if (d.history.length > 16) d.history.shift();
    index = d.history.length - 1;
  }
  d.cursor = index;
}
function commit(score) {
  bench(score);
  const d = active.draft;
  if (d.score && keyOf(d.score) === keyOf(score)) return;
  if (d.score) d.undo.push(copy(d.score));
  if (d.undo.length > 64) d.undo.shift();
  d.redo = []; d.score = copy(score);
  rememberPreview(score); render(); schedulePreview();
}
function restore(index) {
  if (!active || active.busy || !active.draft.history[index]) return;
  commit(copy(active.draft.history[index].score));
  active.relation = null; active.pending = null; renderRelation();
}
function undo(redo = false) {
  if (!active || active.busy) return;
  const d = active.draft, from = redo ? d.redo : d.undo, to = redo ? d.undo : d.redo;
  if (!from.length) return;
  to.push(copy(d.score)); d.score = from.pop(); rememberPreview(d.score);
  active.relation = null; active.pending = null; render(); schedulePreview();
}

function schedulePreview() {
  const owner = active;
  owner.serial++; owner.abort?.abort(); clearTimeout(owner.debounce); clearInterval(owner.timer);
  owner.rendered = null; $('sy-canvas').classList.add('sy-pending');
  owner.started = performance.now();
  const status = () => { if (active === owner) $('sy-status').textContent = `Drawing… ${((performance.now() - owner.started) / 1000).toFixed(1)} s`; };
  status(); owner.timer = setInterval(status, 250); updateReady();
  owner.debounce = setTimeout(() => preview(owner), 180);
}
async function preview(owner) {
  const serial = owner.serial, exact = paramsOf(owner), key = keyOf(exact.score);
  const cacheKey = JSON.stringify(exact);
  const controller = new AbortController(); owner.abort = controller;
  try {
    let output = previews.get(cacheKey);
    if (!output) {
      output = await api.post('/api/generators/preview', { module: 'synthesis', params: exact }, { signal: controller.signal });
      previews.set(cacheKey, output);
      while (previews.size > 18) previews.delete(previews.keys().next().value);
    }
    if (active !== owner || serial !== owner.serial) return;
    owner.output = output; owner.rendered = key;
    draw(output); $('sy-canvas').dataset.renderedScore = JSON.stringify(exact.score);
    $('sy-canvas').classList.remove('sy-pending');
    const item = owner.draft.history[owner.draft.cursor];
    if (item && keyOf(item.score) === key) item.thumb = thumbnail(output);
    $('sy-status').textContent = `${exact.score.layers.length} layers · ${exact.score.relations.length} relations · ${output.lines.length} paths · ${((performance.now() - owner.started) / 1000).toFixed(1)} s`;
    renderStack(); renderArcs(); renderRelation(); renderHistory(); deviceNotes();
  } catch (error) {
    if (error.name !== 'AbortError' && active === owner && serial === owner.serial) { fail(error); $('sy-status').textContent = 'Preview failed'; }
  } finally {
    if (active === owner && serial === owner.serial) { clearInterval(owner.timer); updateReady(); }
  }
}
function draw(output) {
  const canvas = $('sy-canvas'); canvas.replaceChildren();
  canvas.setAttribute('viewBox', `0 0 ${output.width} ${output.height}`);
  canvas.style.aspectRatio = `${output.width} / ${output.height}`;
  canvas.append(svg('rect', { width: output.width, height: output.height, class: 'sy-paper' }));
  const layers = output.layers?.length ? output.layers : [{ paths: output.lines.length }];
  const runs = output.styles?.length ? output.styles : layers;
  let at = 0, ri = 0, remaining = runs[0]?.paths || 0;
  layers.forEach((layer, i) => {
    const id = output.synthesis?.layers?.[i]?.id || layer.name || 'Measure';
    const g = svg('g', { class: 'sy-ink', 'data-layer': id, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
    for (const line of output.lines.slice(at, at + layer.paths)) {
      while (remaining <= 0 && ri < runs.length - 1) remaining = runs[++ri].paths;
      const run = runs[ri] || {};
      const p = svg('polyline', { points: line.map(([x, y]) => `${x},${y}`).join(' '), 'stroke-width': run.width || 0.4 });
      p.style.stroke = run.color || layer.color || 'var(--flexoki-black)';
      g.append(p); remaining--;
    }
    at += layer.paths; canvas.append(g);
  });
  highlight();
}
function thumbnail(output) {
  const drawing = svg('svg', { viewBox: `0 0 ${output.width} ${output.height}` });
  const paper = svg('rect', { width: output.width, height: output.height });
  paper.setAttribute('fill', getComputedStyle(document.documentElement).getPropertyValue('--flexoki-paper').trim()); drawing.append(paper);
  const stride = Math.max(1, Math.ceil(output.lines.reduce((n, line) => n + line.length, 0) / 2500));
  const runs = output.styles?.length ? output.styles : output.layers;
  let at = 0;
  for (const run of runs || [{ paths: output.lines.length }]) {
    const d = output.lines.slice(at, at + run.paths).map(line => {
      const points = line.filter((_, i) => i % stride === 0 || i === line.length - 1);
      return points.length > 1 ? `M${points.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join('L')}` : '';
    }).join('');
    at += run.paths;
    const path = svg('path', { d, fill: 'none', stroke: run.color || catalogue.inks.black, 'stroke-width': Math.max(run.width || 0.4, output.width / 500), 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
    drawing.append(path);
  }
  return new XMLSerializer().serializeToString(drawing);
}

function highlight() {
  if (!active) return;
  document.querySelectorAll('#sy-stack [data-layer], #sy-arcs [data-layer]').forEach(node => {
    const selected = node.dataset.layer === active.selected;
    node.classList.toggle('selected', selected); node.setAttribute('aria-selected', String(selected));
  });
  $('sy-canvas').querySelectorAll('.sy-ink').forEach(g => g.classList.toggle('sy-dim', Boolean(active.selected && g.dataset.layer !== active.selected)));
}
function chooseLayer(id) { active.selected = id; highlight(); }
function revealRelation() { $('sy-relation-panel').scrollIntoView({ block: 'start', behavior: 'smooth' }); }
function relationStats(id) { return active.output?.synthesis?.relations?.[id]; }
function relationLabel(r) { return `${r.kind} ${Array.isArray(r.src) ? r.src.join(' + ') : r.src === '*' ? 'all' : r.src}`; }
function toggleControl(key) {
  change(score => { const b = bench(score), locks = new Set(b.control_locks || []); locks.has(key) ? locks.delete(key) : locks.add(key); b.control_locks = [...locks]; });
}
function controlLock(key, label) {
  const locked = lockedControls(active.draft.score).includes(key);
  const b = button(`${locked ? 'Unlock' : 'Lock'} control ${label}`, () => toggleControl(key), locked ? 'lock' : 'open');
  b.setAttribute('aria-pressed', String(locked)); return b;
}
function layerEdit(id, apply) { return change(score => apply(score.layers.find(l => l.id === id)), id); }
function rollHand(id) {
  const layer = active.draft.score.layers.find(l => l.id === id);
  if (!layer?.part?.voice?.hand || layer.lock) return;
  layerEdit(id, l => { l.part.voice.hand = pick(catalogue.library.hand.filter(h => h.id !== l.part.voice.hand)).id; });
}
function renderStack() {
  const host = $('sy-stack'); host.replaceChildren();
  const score = active.draft.score, held = bench(score).held || [];
  for (const layer of score.layers) {
    const row = el('article', 'sy-layer'); row.dataset.layer = layer.id;
    row.onclick = e => { if (!e.target.closest('button,input,select')) chooseLayer(layer.id); };
    row.classList.toggle('sy-unseen', layer.role === 'unseen'); row.classList.toggle('sy-locked', Boolean(layer.lock));
    const head = el('div', 'sy-row');
    head.append(button(`${layer.id} · ${layer.label || layer.role}`, () => chooseLayer(layer.id)));
    head.append(button(`${layer.lock ? 'Unlock' : 'Lock'} ${layer.id}`, () => transact(async (s, o) => (await api.post(`/api/synthesis/${layer.lock ? 'unlock' : 'lock'}`, { score: s, ids: [layer.id], ...libOf(o) })).score), layer.lock ? 'lock' : 'open'));
    if (held.includes(layer.id)) head.append(button(`Release ${layer.id}`, () => transact(async (s, o) => (await api.post('/api/synthesis/unlock', { score: s, ids: [layer.id], ...libOf(o) })).score)));
    const die = button(`Roll ${layer.id}`, e => e.shiftKey || e.altKey ? rollHand(layer.id) : layerEdit(layer.id, l => { l.seed = randomSeed(); }), 'die');
    die.disabled = Boolean(layer.lock); die.title = layer.lock ? 'Locked geometry: unlock to vary' : 'Roll layer seed; Shift or Alt rolls its hand'; head.append(die, controlLock(`L:${layer.id}:seed`, `Seed ${layer.id}`)); row.append(head);
    if (held.includes(layer.id)) row.append(el('p', 'sy-note', 'held · Ripple keeps this layer still'));
    const controls = el('div', 'sy-layer-controls');
    const role = select(`Role ${layer.id}`, [...new Set([...catalogue.roles, layer.role])], layer.role, value => layerEdit(layer.id, l => { l.role = value; }));
    controls.append(fieldLabel('Role', role));
    if (layer.part) {
      const voice = layer.part.voice;
      const technique = select(`Technique ${layer.id}`, catalogue.techniques.voice, voice.id, value => layerEdit(layer.id, l => { l.part.voice = { id: value }; }));
      technique.disabled = Boolean(layer.lock); controls.append(fieldLabel('Technique', technique));
      if (voice.hand != null) {
        const h = el('div', 'sy-hand');
        const hands = select(`Hand ${layer.id}`, catalogue.library.hand, voice.hand, value => layerEdit(layer.id, l => { l.part.voice.hand = value; }));
        hands.disabled = Boolean(layer.lock);
        h.append(fieldLabel('Hand', hands));
        const roll = button(`Roll hand ${layer.id}`, () => rollHand(layer.id), 'die'); roll.disabled = Boolean(layer.lock); h.append(roll, controlLock(`L:${layer.id}:hand`, `Hand ${layer.id}`)); controls.append(h);
      }
    } else controls.append(el('span', 'sy-technique', layer.composer ? 'sealed · composer' : layer.lines ? 'literal lines' : 'grown by relations'));
    const pen = el('div', 'sy-pen'); const swatch = el('span', 'sy-swatch'); swatch.style.background = catalogue.inks[layer.pen];
    pen.append(swatch, select(`Pen ${layer.id}`, Object.keys(catalogue.inks), layer.pen, value => layerEdit(layer.id, l => { l.pen = value; })), button(`Roll pen ${layer.id}`, () => layerEdit(layer.id, l => { l.pen = pick(Object.keys(catalogue.inks)); }), 'die'), controlLock(`L:${layer.id}:pen`, `Pen ${layer.id}`)); controls.append(fieldLabel('Pen', pen));
    row.append(controls);
    if (layer.role === 'unseen') row.append(el('p', 'sy-note', 'heard, never inked'));
    if (layer.lock) row.append(el('p', 'sy-note', 'Locked · geometry stays through Recompose'));
    const chips = el('div', 'sy-chips');
    for (const r of score.relations.filter(r => r.dst === layer.id || (r.dst === '*' && layer.role !== 'unseen'))) {
      const chip = button(relationLabel(r), () => { active.relation = r.id; active.pending = null; renderRelation(); revealRelation(); });
      chip.dataset.relation = r.id; chip.className = 'sy-chip';
      chip.classList.toggle('sy-silent', relationStats(r.id)?.fired === 0); chips.append(chip);
    }
    row.append(chips); host.append(row);
  }
  highlight();
}
function renderArcs() {
  const host = $('sy-arcs'); host.replaceChildren();
  const score = active.draft.score, count = score.layers.length;
  const width = Math.max(640, (count + 1) * 72), y = 124;
  host.setAttribute('viewBox', `0 0 ${width} 260`); host.style.minWidth = `${Math.min(width, 1800)}px`;
  const x = id => id === '*' ? width - 34 : 38 + score.layers.findIndex(l => l.id === id) * (width - 110) / Math.max(1, count - 1);
  host.append(svg('line', { x1: 30, y1: y, x2: width - 25, y2: y, class: 'sy-baseline' }));
  score.relations.forEach((r, i) => {
    const sources = Array.isArray(r.src) ? r.src : [r.src];
    sources.forEach(src => {
      const a = x(src), b = x(r.dst), direction = relSpec(r.kind)?.phase === 'grow' ? -1 : 1;
      const crown = direction * Math.min(115, 30 + Math.abs(a - b) * 0.19 + i % 6 * 9);
      const path = `M ${a} ${y} C ${a - (a === b ? 32 : 0)} ${y + crown}, ${b + (a === b ? 32 : 0)} ${y + crown}, ${b} ${y}`;
      const fired = relationStats(r.id)?.fired;
      const g = svg('g', { class: `sy-arc${fired === 0 ? ' sy-silent' : ''}`, 'data-relation': r.id, tabindex: 0, role: 'button', 'aria-label': `${r.id}: ${relationLabel(r)} to ${r.dst === '*' ? 'all' : r.dst}` });
      const title = svg('title'); title.textContent = `${r.kind} · ${fired ?? '…'} fired`; g.append(title);
      g.append(svg('path', { d: path, class: 'sy-arc-hit' }));
      g.append(svg('path', { d: path, class: 'sy-arc-line', 'stroke-width': 1 + Math.min(3, Math.log2(1 + (fired || 0))), opacity: fired === 0 ? 0.4 : Math.min(1, 0.55 + (fired || 0) * 0.05) }));
      const edit = () => { active.relation = r.id; active.pending = null; renderRelation(); revealRelation(); };
      g.onclick = edit; g.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); edit(); } }; host.append(g);
    });
  });
  for (const layer of [...score.layers, { id: '*', role: 'all' }]) {
    const g = svg('g', { class: 'sy-node', 'data-layer': layer.id, role: 'button', tabindex: 0, 'aria-label': `Layer ${layer.id === '*' ? 'all' : layer.id}` });
    g.append(svg('circle', { cx: x(layer.id), cy: y, r: 13 }));
    const label = svg('text', { x: x(layer.id), y: y + 33, 'text-anchor': 'middle' }); label.textContent = layer.id === '*' ? 'all' : layer.id; g.append(label);
    const role = svg('text', { x: x(layer.id), y: y + 48, 'text-anchor': 'middle', class: 'sy-node-role' }); role.textContent = layer.role; g.append(role);
    g.onclick = () => chooseLayer(layer.id === '*' ? null : layer.id);
    g.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); chooseLayer(layer.id); } };
    g.onpointerdown = e => beginArcDrag(e, layer.id, false);
    if (layer.id !== '*') {
      const grip = svg('rect', { x: x(layer.id) - 15, y: y + 55, width: 30, height: 10, rx: 3, class: 'sy-order-grip', 'aria-label': `Reorder ${layer.id}` });
      grip.onpointerdown = e => { e.stopPropagation(); beginArcDrag(e, layer.id, true); }; g.append(grip);
    }
    host.append(g);
  }
  highlight();
}
function beginArcDrag(event, src, reorder) {
  if (event.button !== 0 || active.busy) return;
  event.preventDefault();
  const owner = active, host = $('sy-arcs'), start = { x: event.clientX, y: event.clientY };
  const ghost = svg('line', { class: 'sy-drag-line' }); host.append(ghost);
  const point = e => { const p = new DOMPoint(e.clientX, e.clientY); return p.matrixTransform(host.getScreenCTM().inverse()); };
  const a = point(event);
  const move = e => { const b = point(e); for (const [k, v] of Object.entries({ x1: a.x, y1: a.y, x2: b.x, y2: b.y })) ghost.setAttribute(k, String(v)); };
  const up = e => {
    document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', up); ghost.remove();
    if (active !== owner || Math.hypot(e.clientX - start.x, e.clientY - start.y) < 8) return;
    const target = document.elementFromPoint(e.clientX, e.clientY)?.closest('#sy-arcs [data-layer]')?.dataset.layer;
    if (reorder) {
      const p = point(e), n = owner.draft.score.layers.length;
      const index = Math.max(0, Math.min(n - 1, Math.round((p.x - 38) / ((Number(host.viewBox.baseVal.width) - 110) / Math.max(1, n - 1)))));
      change(score => { const from = score.layers.findIndex(l => l.id === src); const [layer] = score.layers.splice(from, 1); score.layers.splice(index, 0, layer); });
    } else if (target && target !== src) { owner.pending = { src, dst: target }; owner.relation = null; renderRelation(); revealRelation(); }
  };
  document.addEventListener('pointermove', move); document.addEventListener('pointerup', up, { once: true });
}
// Catalogue controls are shared by relation, writer and device panels. Values
// with an optional list shape retain their JSON shape through validation.
function randomValue(spec, current) {
  if (spec.type === 'bool') return !current;
  if (spec.type === 'choice') return pick(spec.choices.filter(v => v !== current).length ? spec.choices.filter(v => v !== current) : spec.choices);
  if (spec.type === 'int' || spec.type === 'float') {
    if (spec.min == null || spec.max == null) return current;
    const v = spec.min + Math.random() * (spec.max - spec.min);
    return spec.type === 'int' ? Math.round(v) : Number(v.toFixed(3));
  }
  if (spec.type === 'weights' && current) return Object.fromEntries(Object.keys(current).map(k => [k, Number(Math.random().toFixed(2))]));
  return current;
}
function paramControl(spec, value, changeValue, key = null, disabled = false) {
  const wrap = el('div', 'sy-field');
  const name = spec.label || spec.name, row = el('div', 'sy-field-head');
  row.append(el('span', '', name)); wrap.append(row); wrap.title = spec.doc || spec.help || '';
  if (key) {
    row.append(button(`Roll ${name}`, () => changeValue(randomValue(spec, value)), 'die'), controlLock(key, name));
    row.querySelector('button').disabled = disabled || !['int', 'float', 'bool', 'choice', 'weights'].includes(spec.type);
  }
  value = value ?? spec.default;
  let input;
  if (spec.type === 'choice') input = select(name, spec.choices || [], value, changeValue);
  else if (spec.type === 'bool') {
    input = el('input'); input.type = 'checkbox'; input.checked = Boolean(value); input.onchange = () => changeValue(input.checked);
  } else if (['int', 'float'].includes(spec.type)) {
    input = el('input'); input.type = 'number'; input.value = value;
    if (spec.min != null) input.min = spec.min;
    if (spec.max != null) input.max = spec.max;
    input.step = spec.type === 'int' ? '1' : 'any';
    input.onchange = () => { if (input.checkValidity()) changeValue(Number(input.value)); else input.reportValidity(); };
    if (spec.min != null && spec.max != null) {
      const range = el('input'); range.type = 'range'; range.min = spec.min; range.max = spec.max;
      range.step = spec.type === 'int' ? '1' : String(Math.max(0.0001, (spec.max - spec.min) / 1000));
      range.value = value; range.disabled = disabled; range.setAttribute('aria-label', `${name} slider`);
      range.oninput = () => { input.value = range.value; };
      range.onchange = () => changeValue(Number(range.value)); wrap.append(range);
    }
  } else if (spec.type === 'weights') {
    const keys = [...new Set([...Object.keys(spec.default || {}), ...Object.keys(value || {}), ...(spec.keys || []), ...(spec.choices || [])])];
    if (!keys.length) {
      // The crossing catalogue's optional weights override has no keys until
      // supplied; its five w_ controls name the same known outcomes.
      keys.push('gap_under', 'gap_over', 'cross', 'stop', 'sympathy');
    }
    for (const name of keys) wrap.append(paramControl({ name, type: 'float', min: spec.min ?? 0, max: spec.max ?? 1, default: 0 }, value?.[name] || 0, v => changeValue({ ...(value || {}), [name]: v }), key ? `${key}:${name}` : null, disabled));
    return wrap;
  } else {
    input = el('input'); input.type = 'text';
    const structured = ['floats', 'ints', 'strings', 'hands', 'points'].includes(spec.type) || Array.isArray(value) || (value && typeof value === 'object');
    input.value = structured ? JSON.stringify(value) : value ?? '';
    input.onchange = () => {
      try { changeValue(structured ? JSON.parse(input.value) : input.value); }
      catch { input.setCustomValidity('Enter a JSON list'); input.reportValidity(); }
    };
    input.oninput = () => input.setCustomValidity('');
  }
  input.setAttribute('aria-label', name); input.disabled = disabled; wrap.append(input); return wrap;
}
function relationEdit(id, mutate) {
  const r = active.draft.score.relations.find(r => r.id === id);
  const target = r.dst === '*' ? null : r.dst;
  return change(score => mutate(score.relations.find(r => r.id === id), score), target);
}
function renderRelation() {
  const host = $('sy-relation-panel'); host.replaceChildren();
  const score = active.draft.score;
  if (active.pending) {
    host.hidden = false;
    const { src, dst } = active.pending;
    host.append(el('h3', '', `New relation · ${src === '*' ? 'all' : src} → ${dst === '*' ? 'all' : dst}`));
    const earlier = src === '*' || score.layers.findIndex(l => l.id === src) < score.layers.findIndex(l => l.id === dst);
    const kinds = catalogue.relations.filter(r => r.phase === 'contact' || (earlier && dst !== '*'));
    const picker = select('Relation kind', kinds, kinds[0]?.id, () => {});
    host.append(fieldLabel('Kind', picker));
    const add = button('Add relation', () => {
      const kind = picker.value;
      change(s => {
        let n = 1; while (s.relations.some(r => r.id === `R${n}`)) n++;
        const id = `R${n}`;
        s.relations.push({ id, kind, src, dst, p: 1, params: {}, seed: randomSeed() });
        active.relation = id; active.pending = null;
      }, dst === '*' ? null : dst);
    });
    host.append(add, button('Cancel relation', () => { active.pending = null; renderRelation(); })); return;
  }
  const relation = score.relations.find(r => r.id === active.relation);
  host.hidden = !relation;
  if (!relation) return;
  const r = relation, spec = relSpec(r.kind), stats = relationStats(r.id);
  const head = el('div', 'sy-row'); head.append(el('h3', '', `${r.kind} · ${r.id}`), button('Close relation editor', () => { active.relation = null; renderRelation(); })); host.append(head);
  host.append(el('p', 'sy-note', spec.doc));
  if (stats) {
    const note = el('p', `sy-note${stats.fired === 0 ? ' sy-silent-note' : ''}`, stats.fired === 0 ? 'Never fired: no change between these layers. They may not meet, or a filter, probability or budget kept the relation silent.' : `${stats.fired} fired · ${Object.entries(stats.outcomes || {}).map(([k, v]) => `${k}: ${v}`).join(' · ')}`);
    host.append(note);
    if (stats.pairs?.length) host.append(el('p', 'sy-note', `Pairs: ${stats.pairs.map(p => p.join(' → ')).join(', ')}`));
  }
  const sourceOptions = ['*', ...score.layers.map(l => l.id)];
  const src = select('Relation source', sourceOptions, Array.isArray(r.src) ? r.src : [r.src], value => relationEdit(r.id, rel => { rel.src = value.length === 1 ? value[0] : value; }), spec.phase === 'grow');
  if (spec.phase !== 'grow') { src.value = r.src; src.onchange = () => relationEdit(r.id, rel => { rel.src = src.value; }); }
  host.append(fieldLabel(spec.phase === 'grow' ? 'Source (select several to merge)' : 'Source', src));
  host.append(fieldLabel('Destination', select('Relation destination', spec.phase === 'grow' ? sourceOptions.slice(1) : sourceOptions, r.dst, value => relationEdit(r.id, rel => { rel.dst = value; }))));
  host.append(paramControl({ name: 'Probability', type: 'float', min: 0, max: 1, default: 1 }, r.p, value => relationEdit(r.id, rel => { rel.p = value; }), `R:${r.id}:p`));
  const params = el('details', stats?.fired === 0 ? 'sy-dormant' : ''); params.open = true; params.append(el('summary', '', 'Parameters'));
  for (const p of spec.params) params.append(paramControl(p, r.params[p.name], value => relationEdit(r.id, rel => { rel.params[p.name] = value; }), `R:${r.id}:${p.name}`));
  host.append(params);
  const filters = el('details'); filters.append(el('summary', '', 'Filters and budgets'));
  for (const prefix of ['', 'src_', 'dst_']) for (const key of ['except', 'roles', 'not_roles']) {
    const name = prefix + key;
    filters.append(fieldLabel(name.replaceAll('_', ' '), select(name, key === 'except' ? score.layers.map(l => l.id) : catalogue.roles, r[name] || [], value => relationEdit(r.id, rel => { if (value.length) rel[name] = value; else delete rel[name]; }), true)));
  }
  const budget = el('input'); budget.type = 'number'; budget.min = '0'; budget.max = '100000'; budget.step = '1'; budget.value = r.budget ?? ''; budget.setAttribute('aria-label', 'Relation budget');
  budget.onchange = () => relationEdit(r.id, rel => { if (budget.value === '') delete rel.budget; else rel.budget = Number(budget.value); });
  filters.append(fieldLabel('Budget (empty = unlimited)', budget));
  const group = el('input'); group.type = 'text'; group.value = r.budget_group || ''; group.setAttribute('aria-label', 'Budget group');
  group.onchange = () => relationEdit(r.id, (rel, s) => { if (group.value.trim()) { rel.budget_group = group.value.trim(); (s.budget_groups ||= {})[rel.budget_group] ??= 10; } else delete rel.budget_group; });
  filters.append(fieldLabel('Budget group', group));
  if (r.budget_group) filters.append(paramControl({ name: 'Group budget', type: 'int', min: 0, max: 100000 }, score.budget_groups?.[r.budget_group] ?? 10, value => change(s => { (s.budget_groups ||= {})[r.budget_group] = value; })));
  host.append(filters);
  const locked = lockedRelations(score).includes(r.id), row = el('div', 'sy-row');
  row.append(button('Roll relation seed', () => relationEdit(r.id, rel => { rel.seed = randomSeed(); }), 'die'), controlLock(`R:${r.id}:seed`, 'Relation seed'));
  const lock = button(`${locked ? 'Unlock' : 'Lock'} relation`, () => change(s => { const b = bench(s), ids = new Set(b.locked_relations || []); ids.has(r.id) ? ids.delete(r.id) : ids.add(r.id); b.locked_relations = [...ids]; }), locked ? 'lock' : 'open');
  lock.setAttribute('aria-pressed', String(locked)); row.append(lock, el('span', 'sy-note', locked ? 'Kept through Recompose' : 'Lock to keep through Recompose'));
  host.append(row, button('Delete relation', () => change(s => { s.relations = s.relations.filter(rel => rel.id !== r.id); active.relation = null; })));
}
function renderHistory() {
  const strip = $('sy-history'); strip.replaceChildren();
  active.draft.history.forEach((item, index) => {
    const b = button(`Preview ${index + 1}: ${item.score.label || 'Synthesis'} · seed ${item.score.seed}`, () => restore(index));
    b.className = 'sy-history-item'; b.setAttribute('aria-current', String(index === active.draft.cursor));
    if (item.thumb) b.innerHTML = item.thumb; else b.textContent = String(index + 1);
    strip.append(b);
  });
}
function renderMeasure() {
  const host = $('sy-devices');
  const open = [...host.querySelectorAll('details[open]')].map(n => n.dataset.device);
  host.replaceChildren();
  for (const device of catalogue.devices) {
    const current = (active.draft.score.devices || []).find(d => d.id === device.id);
    const row = el('details', 'sy-device'); row.dataset.device = device.id; row.open = open.includes(device.id);
    const summary = el('summary');
    const check = el('input'); check.type = 'checkbox'; check.checked = Boolean(current); check.setAttribute('aria-label', `Measure: ${device.label}`);
    check.onclick = e => e.stopPropagation();
    check.onchange = () => change(score => { score.devices = (score.devices || []).filter(d => d.id !== device.id); if (check.checked) score.devices.push(copy(device.default)); });
    const label = el('label'); label.append(check, document.createTextNode(device.label)); summary.append(label); row.append(summary);
    row.append(el('p', 'sy-note', device.doc));
    if (current) {
      const edit = (name, value) => change(score => { score.devices.find(d => d.id === device.id)[name] = value; });
      row.append(fieldLabel('Placement', select(`Placement ${device.label}`, ['over', 'under', 'margin', 'beside'], current.place, value => change(score => {
        const d = score.devices.find(d => d.id === device.id); d.place = value;
        if (['margin', 'beside'].includes(value)) { d.side ||= 'right'; d.size ||= 35; } else { delete d.side; delete d.size; }
      }))));
      if (['margin', 'beside'].includes(current.place)) {
        row.append(fieldLabel('Side', select(`Side ${device.label}`, ['left', 'right', 'top', 'bottom'], current.side, value => edit('side', value))));
        row.append(paramControl({ name: 'Size', type: 'float', min: 5, max: 200, default: 35 }, current.size, value => edit('size', value)));
      }
      for (const spec of device.shown) row.append(paramControl(spec, current[spec.name], value => edit(spec.name, value), `D:${device.id}:${spec.name}`));
      if (device.slow) row.append(el('p', 'sy-note', device.slow));
    }
    row.append(el('p', 'sy-device-note sy-note')); host.append(row);
  }
  deviceNotes();
}
function deviceNotes() {
  if (!active) return;
  for (const row of $('sy-devices').children) {
    const reading = active.output?.synthesis?.devices?.find(d => d.id === row.dataset.device);
    const entry = catalogue.devices.find(d => d.id === row.dataset.device);
    row.querySelector('.sy-device-note').textContent = reading ? reading.error || (reading.inks ? `${reading.inks} inks drawn` : entry.empty) : '';
  }
}
function render() {
  if (!active?.draft.score) return;
  const s = active.draft.score;
  if (!s.layers.some(l => l.id === active.selected)) active.selected = null;
  $('sy-name').textContent = s.label || 'Synthesis'; $('sy-seed').value = s.seed;
  $('sy-sheet-lock').innerHTML = icon(lockedControls(s).includes('sheet:seed') ? 'lock' : 'open');
  $('sy-sheet-lock').setAttribute('aria-pressed', String(lockedControls(s).includes('sheet:seed')));
  const ripple = bench(s).ripple || 'all';
  document.querySelectorAll('#sy-ripple-buttons button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === ripple)));
  renderStack(); renderArcs(); renderRelation(); renderHistory(); renderMeasure(); updateReady();
}
async function shuffle() {
  return transact(async (score, owner) => {
    const locks = new Set(lockedControls(score));
    if (!locks.has('sheet:seed')) score.seed = randomSeed();
    for (const layer of score.layers) {
      if (layer.lock) continue;
      const target = score.layers.find(l => l.id === layer.id);
      if (!locks.has(`L:${layer.id}:seed`)) target.seed = randomSeed();
      if (target.part?.voice?.hand && !locks.has(`L:${layer.id}:hand`)) target.part.voice.hand = pick(catalogue.library.hand).id;
      if (!locks.has(`L:${layer.id}:pen`)) target.pen = pick(Object.keys(catalogue.inks).filter(p => !p.includes('-')));
    }
    for (const r of score.relations) {
      if (!locks.has(`R:${r.id}:seed`)) r.seed = randomSeed();
      if (!locks.has(`R:${r.id}:p`)) r.p = Number(Math.random().toFixed(2));
      for (const spec of relSpec(r.kind).params) if (!locks.has(`R:${r.id}:${spec.name}`)) {
        const old = r.params[spec.name], value = randomValue(spec, old);
        if (spec.type === 'weights' && value) for (const k of Object.keys(value)) {
          if (locks.has(`R:${r.id}:${spec.name}:${k}`)) value[k] = old[k];
        }
        r.params[spec.name] = value;
      }
    }
    for (const device of score.devices || []) for (const spec of catalogue.devices.find(d => d.id === device.id).shown) {
      if (!locks.has(`D:${device.id}:${spec.name}`)) device[spec.name] = randomValue(spec, device[spec.name] ?? spec.default);
    }
    return (await api.post('/api/synthesis/validate', { score, ...libOf(owner) })).score;
  });
}
function recompose() {
  transact(async (score, owner) => {
    const result = await api.post('/api/synthesis/recompose', { score, seed: randomSeed(), locked: score.layers.filter(l => l.lock).map(l => l.id), locked_relations: lockedRelations(score), ...libOf(owner) });
    if (active !== owner) return null;
    result.score.decisions ||= {}; result.score.decisions.bench = { ...bench(score), ...result.score.decisions.bench };
    if (result.dropped?.length) $('sy-notice').textContent = `Relations released because their ends changed: ${result.dropped.join(', ')}`;
    return result.score;
  });
}
let thumbPoll = null;
function closeGallery() { clearTimeout(thumbPoll); $('sy-gallery').hidden = true; }
async function openGallery() {
  if (!active || !catalogue) return;
  const owner = active, host = $('sy-gallery-grid'); host.replaceChildren(); $('sy-gallery').hidden = false;
  const entries = [...catalogue.gallery, ...catalogue.saved.map(s => ({ ...s, id: s.gallery }))];
  const groups = [...new Set(entries.map(e => e.family || 'Studies as one sealed layer'))];
  for (const family of groups) {
    const section = el('section'); section.append(el('h3', '', family)); const grid = el('div', 'sy-cards');
    for (const entry of entries.filter(e => (e.family || 'Studies as one sealed layer') === family)) {
      const card = el('article', 'sy-card'); card.dataset.gallery = entry.id;
      const sheet = el('div', 'sy-card-sheet'); sheet.textContent = 'Thumbnail pending';
      if (entry.thumb) { const img = el('img'); img.src = entry.thumb; img.alt = ''; sheet.replaceChildren(img); }
      const open = button(entry.label, () => start(entry.id, values)); open.className = 'sy-card-open'; open.append(sheet, el('strong', '', entry.label)); card.append(open);
      card.append(el('p', 'sy-note', entry.notes));
      const values = {};
      if (entry.kind === 'writer') {
        const details = el('details'); details.append(el('summary', '', 'Writer settings'));
        for (const spec of catalogue.writers.find(w => w.id === entry.writer)?.params || []) {
          values[spec.name] = copy(spec.default);
          details.append(paramControl(spec, values[spec.name], value => { values[spec.name] = value; }));
        }
        details.append(button(`Compose ${entry.writer}`, () => start(entry.id, values))); card.append(details);
      }
      grid.append(card);
    }
    section.append(grid); host.append(section);
  }
  $('sy-gallery-close').focus();
  const ids = entries.filter(e => e.thumb_study).map(e => e.thumb_study);
  const show = states => {
    let waiting = false;
    for (const entry of entries) {
      if (!entry.thumb_study) continue;
      const state = states?.[entry.thumb_study];
      const card = [...host.querySelectorAll('[data-gallery]')].find(c => c.dataset.gallery === entry.id);
      if (state?.state === 'ready' && card) {
        const sheet = card.querySelector('.sy-card-sheet');
        if (sheet.dataset.key !== state.key) { const img = el('img'); img.alt = ''; img.src = `/api/gesture-studies/thumbnail/${encodeURIComponent(state.key)}`; sheet.replaceChildren(img); sheet.dataset.key = state.key; }
      } else if (state?.state === 'failed' && card) card.querySelector('.sy-card-sheet').textContent = 'No thumbnail';
      else waiting = true;
    }
    return waiting;
  };
  const poll = async initial => {
    try {
      const res = initial ? await api.post('/api/gesture-studies/thumbnails', { ids }) : await api.get('/api/gesture-studies/thumbnails');
      if (active === owner && !$('sy-gallery').hidden && show(res.thumbnails)) thumbPoll = setTimeout(() => poll(false), 1500);
    } catch { /* Starting points remain usable without thumbnails. */ }
  };
  clearTimeout(thumbPoll); poll(true);
}
function start(gallery, params = {}) {
  closeGallery();
  transact(async (_score, owner) => {
    const result = await api.post('/api/synthesis/start', { gallery, params, ...(gallery.startsWith('writer:') ? { seed: owner.draft.score?.seed ?? randomSeed() } : {}), ...libOf(owner) });
    if (active !== owner) return null;
    bench(result.score).from = gallery; owner.selected = null; owner.relation = null; owner.pending = null;
    return result.score;
  });
}
async function pngThumbnail(output) {
  const source = thumbnail(output), image = new Image();
  const url = URL.createObjectURL(new Blob([source], { type: 'image/svg+xml' }));
  try {
    image.src = url; await image.decode();
    const canvas = document.createElement('canvas'); canvas.width = 260; canvas.height = Math.round(260 * output.height / output.width);
    canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/png');
  } finally { URL.revokeObjectURL(url); }
}
async function save() {
  if (!active || $('sy-save').disabled) return;
  const owner = active, score = copy(owner.draft.score), label = $('sy-save-name').value.trim() || score.label || 'Synthesis';
  owner.busy = true; updateReady();
  try {
    await api.post('/api/synthesis/saved', { label, score, thumb: await pngThumbnail(owner.output) });
    const saved = await api.get('/api/synthesis/saved'); if (active === owner) catalogue.saved = saved.items;
    if (active === owner) $('sy-notice').textContent = `Saved · ${label}`;
  } catch (error) { if (active === owner) fail(error); }
  finally { owner.busy = false; if (active === owner) updateReady(); }
}
async function keep(replace = false) {
  if (!active || $('sy-keep').disabled) return;
  const owner = active, params = paramsOf(owner); owner.busy = true; updateReady();
  try {
    const result = await api.post('/api/synthesis/keep', { params, ...(replace && owner.group ? { replace: owner.group } : {}) });
    await actions.refreshProject(); await actions.refreshResolved();
    actions.setSelectionTargets([{ kind: 'group', id: result.group.id }]);
    if (active === owner) $('sy-notice').textContent = `${replace ? 'Replaced' : 'Kept'} · ${result.group.name} · ${result.layers.length} layers${result.layers.some(l => l.name === 'Measure') ? ' · with Measure' : ''}`;
  } catch (error) { if (active === owner) fail(error); }
  finally { owner.busy = false; if (active === owner) updateReady(); }
}
export function initSynthesisBench() {
  if (wired || !$('process-popup')) return;
  wired = true;
  const panel = el('section'); panel.id = 'process-synthesis'; panel.hidden = true;
  panel.innerHTML = `
    <div class="sy-toolbar">
      <div class="sy-title"><strong id="sy-name">Synthesis</strong><span class="sy-note">A score of layers and relations</span></div>
      <button id="sy-gallery-open">Gallery</button>
      <label class="sy-seed-label">Sheet seed <input id="sy-seed" aria-label="Sheet seed" type="number" min="0" max="2147483647" step="1"></label>
      <button id="sy-sheet-die" aria-label="Roll sheet seed" title="Roll sheet seed">${icon('die')}</button>
      <button id="sy-sheet-lock" aria-label="Lock control Sheet seed" title="Keep sheet seed through Shuffle">${icon('open')}</button>
      <button id="sy-shuffle">Shuffle</button><button id="sy-recompose">Recompose</button>
      <div class="sy-ripple"><span>Ripple</span><div id="sy-ripple-buttons" role="group" aria-label="Ripple">
        <button data-value="all" aria-pressed="true" title="Let all layers follow edits">all</button><button data-value="direct" aria-pressed="false" title="Only direct listeners follow">direct</button><button data-value="none" aria-pressed="false" title="Hold every other layer">none</button></div>
      </div>
    </div>
    <div id="sy-editors">
      <div class="sy-work">
        <div id="sy-status" class="sy-note" role="status">Loading synthesis…</div>
        <div class="sy-stage"><svg id="sy-canvas" aria-label="Synthesis drawing" viewBox="0 0 250 175"></svg></div>
        <section class="sy-arc-editor" aria-label="Arc diagram editor"><div class="sy-arc-heading"><strong>Score</strong><span class="sy-note">Grow above · contact below · drag between circles to relate · drag the small grips to reorder</span><button id="sy-add-relation">Add relation…</button></div><div class="sy-arc-scroll"><svg id="sy-arcs" aria-label="Score arc diagram"></svg></div></section>
        <div id="sy-history" role="group" aria-label="Recent scores"></div>
      </div>
      <aside class="sy-sidebar" aria-label="Score editors">
        <div class="sy-section-head"><strong>Layers</strong><button id="sy-clear-selection">Show all</button></div>
        <div id="sy-stack" aria-label="Layer stack"></div>
        <section id="sy-relation-panel" aria-label="Relation editor" hidden></section>
        <details id="sy-measure"><summary>Measure</summary><p class="sy-note">Optional readings of this score. Keep puts their ink on a separate Measure layer.</p><div id="sy-devices"></div></details>
      </aside>
    </div>
    <div id="sy-error" role="alert" hidden></div>
    <div class="sy-actions"><button id="sy-undo">Undo</button><button id="sy-redo">Redo</button><span id="sy-notice" class="sy-note" aria-live="polite"></span><label class="sy-save-label"><span class="sr-only">Saved synthesis name</span><input id="sy-save-name" aria-label="Saved synthesis name" placeholder="Name this score" maxlength="120"></label><button id="sy-save" disabled>Save</button><button id="sy-keep-new" hidden disabled>Keep as new</button><button id="sy-keep" class="primary" disabled>Keep</button></div>
    <section id="sy-gallery" aria-label="Synthesis gallery" hidden><div class="sy-gallery-head"><div><h3>Starting points</h3><p class="sy-note">Writers open an editable score. Studies enter as one sealed layer.</p></div><button id="sy-gallery-close">Back to score</button></div><div id="sy-gallery-grid"></div></section>`;
  document.querySelector('#process-popup .bench-layout').append(panel);
  $('sy-gallery-open').onclick = openGallery; $('sy-gallery-close').onclick = closeGallery;
  $('sy-clear-selection').onclick = () => chooseLayer(null);
  $('sy-sheet-die').onclick = () => change(s => { s.seed = randomSeed(); });
  $('sy-seed').onchange = () => { if ($('sy-seed').checkValidity()) change(s => { s.seed = Number($('sy-seed').value); }); };
  $('sy-sheet-lock').onclick = () => toggleControl('sheet:seed');
  $('sy-shuffle').onclick = shuffle; $('sy-recompose').onclick = recompose;
  $('sy-undo').onclick = () => undo(); $('sy-redo').onclick = () => undo(true);
  $('sy-save').onclick = save; $('sy-keep').onclick = () => keep(Boolean(active.group)); $('sy-keep-new').onclick = () => keep(false);
  const ripple = value => change(s => { bench(s).ripple = value; });
  $('sy-ripple-buttons').querySelectorAll('button').forEach(b => { b.onclick = () => ripple(b.dataset.value); });
  $('sy-add-relation').onclick = () => { const layers = active.draft.score.layers; active.pending = { src: active.selected || layers[0].id, dst: layers.at(-1).id }; active.relation = null; renderRelation(); revealRelation(); };
  // Register before the host's document shortcut guard.
  document.addEventListener('keydown', e => {
    if (!active || !$('process-popup').contains(document.activeElement)) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.target.matches('input,textarea,select,[contenteditable="true"]')) {
      e.preventDefault(); e.stopImmediatePropagation(); undo(e.shiftKey);
    }
  }, true);
  document.addEventListener('bench-project-reset', () => { closeSynthesisBench(false); drafts.clear(); });
}
export async function openSynthesisBench({ mod, params, contextKey, onKeep, onClose }) {
  initSynthesisBench(); closeSynthesisBench(false);
  const original = { mod, params, contextKey, onKeep, onClose };
  const input = copy({ ...mod.defaults, ...params });
  const context = `${benchProjectEpoch()}:${contextKey || 'new:synthesis'}`;
  let draft = drafts.get(context);
  const inputKey = JSON.stringify(input.score);
  if (!draft || (draft.inputKey !== inputKey && keyOf(draft.score) !== inputKey)) {
    draft = { score: null, history: [], cursor: -1, undo: [], redo: [], inputKey }; drafts.set(context, draft);
  }
  const owner = { draft, external: params, onClose, library: input.library || null, pins: input.pins || [], serial: 0, queue: Promise.resolve(), busy: true, loaded: false, selected: null, relation: null, pending: null, output: null, rendered: null, group: null };
  active = owner; updateReady();
  $('process-popup').classList.add('synthesis'); $('process-synthesis').hidden = false;
  $('process-title').textContent = 'Synthesis — working bench'; $('sy-notice').textContent = ''; $('sy-error').hidden = true;
  $('sy-gallery').hidden = true; $('sy-canvas').replaceChildren(); $('sy-stack').replaceChildren(); $('sy-arcs').replaceChildren(); $('sy-history').replaceChildren(); $('sy-relation-panel').replaceChildren(); $('sy-relation-panel').hidden = true; $('sy-devices').replaceChildren();
  $('sy-name').textContent = 'Synthesis'; $('sy-status').textContent = 'Loading synthesis…'; $('sy-keep').textContent = 'Keep'; $('sy-keep-new').hidden = true;
  openBenchShell({ close: () => closeSynthesisBench(), origin: contextKey?.startsWith('layer:') ? 'From kept synthesis · editing the whole score' : 'Working score · Keep creates a group', reopen: () => openSynthesisBench(original), cancelGesture: () => {
    if (!$('sy-gallery').hidden) { closeGallery(); return true; }
    if (owner.relation || owner.pending) { owner.relation = null; owner.pending = null; renderRelation(); return true; }
    return false;
  } });
  $('process-popup').classList.add('expanded'); $('process-expand').textContent = 'Restore'; $('process-expand').setAttribute('aria-pressed', 'true');
  try {
    const loaded = await api.get('/api/synthesis');
    if (active !== owner) return;
    catalogue = loaded;
    if (owner.library && owner.library !== catalogue.snapshot) {
      const pinned = await api.get(`/api/gesture-studies/library/${encodeURIComponent(owner.library)}`);
      if (active !== owner) return;
      catalogue.library = pinned.library;
    }
    if (contextKey?.startsWith('layer:')) {
      const project = await api.get('/api/project');
      if (active !== owner) return;
      const layer = project.layers.find(l => l.id === contextKey.slice(6));
      owner.group = layer?.group_id || null;
      $('sy-keep').textContent = owner.group ? 'Replace group' : 'Keep'; $('sy-keep-new').hidden = !owner.group;
    }
    owner.loaded = true;
    if (!draft.score) {
      const result = await api.post('/api/synthesis/validate', { score: input.score, ...libOf(owner) });
      if (active !== owner) return;
      commit(result.score);
    }
    else { render(); schedulePreview(); }
  } catch (error) { if (active === owner) fail(error); }
  finally { owner.busy = false; if (active === owner) updateReady(); }
}
export function closeSynthesisBench(notify = true) {
  if (!active) return;
  const owner = active; active = null; owner.serial++; owner.abort?.abort();
  clearTimeout(owner.debounce); clearInterval(owner.timer); closeGallery();
  if (owner.draft.score) Object.assign(owner.external, { score: copy(owner.draft.score), library: owner.library, pins: copy(owner.pins) });
  $('process-synthesis').hidden = true; $('process-popup').classList.remove('synthesis');
  if (notify) { closeBenchShell(); owner.onClose?.(); }
}
