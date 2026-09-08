// A local arrangement editor. Geometry always comes from the registered source.
import { api } from './api.js';
import { benchProjectEpoch, openBenchShell, closeBenchShell, clearBenchError, showBenchError } from './bench_host.js';

const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const copy = value => JSON.parse(JSON.stringify(value));
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const drafts = new Map();
let active = null;
let wired = false;
let gesture = null;

function fit(m, p) {
  if (m.kind === 'bar') {
    const a = m.rotation * Math.PI / 180;
    const extent = () => [
      (Math.abs(Math.cos(a))*m.length + Math.abs(Math.sin(a))*m.thickness)/2,
      (Math.abs(Math.sin(a))*m.length + Math.abs(Math.cos(a))*m.thickness)/2,
    ];
    let [ex, ey] = extent();
    const scale = Math.min(1, (p.width-1)/(2*ex), (p.height-1)/(2*ey));
    m.length = Math.max(8, m.length*scale);
    m.thickness = Math.max(4, m.thickness*scale);
    [ex, ey] = extent();
    m.x = clamp(m.x, ex+.05, p.width-ex-.05);
    m.y = clamp(m.y, ey+.05, p.height-ey-.05);
  } else {
    m.x = clamp(m.x, 4.05, p.width-4.05);
    m.y = clamp(m.y, 4.05, p.height-4.05);
  }
  return m;
}

// Stable across browser sessions. Persist the resulting objects, not a recipe
// that another random generator would have to recreate during project loading.
function scattered(p, count, type) {
  let state = p.seed >>> 0;
  const random = () => {
    state = (Math.imul(state, 1664525)+1013904223) >>> 0;
    return state / 4294967296;
  };
  return Array.from({length: count}, (_, i) => {
    const kind = type === 'bars' ? 'bar' : type === 'poles'
      ? (i % 2 ? 'south' : 'north') : ['bar','north','south'][i % 3];
    return fit({ kind, x: p.width*random(), y: p.height*random(),
      rotation: random()*360-180, length: Math.min(48,p.width*.3), thickness: 12,
      strength: 1, flipped: random() > .5 }, p);
  });
}

function key() { return JSON.stringify(active?.draft.params); }
function selected() { return active?.draft.params.magnets[active.draft.selection]; }
function snapshot() { return copy({ params: active.draft.params, selection: active.draft.selection }); }
function remember(before = snapshot()) {
  active.draft.undo.push(before);
  if (active.draft.undo.length > 80) active.draft.undo.shift();
  active.draft.redo = [];
}
function invalidate() {
  active.renderedKey = null;
  $('magnetic-kept').textContent = '';
  $('process-canvas').classList.add('magnetic-pending');
  renderControls();
  drawHandles();
}
function change(fn) {
  if (!active || active.keeping || gesture) return;
  const before = snapshot();
  fn(active.draft.params);
  if (JSON.stringify(before.params) === key()) { renderControls(); return; }
  remember(before);
  invalidate();
  requestPreview();
}
function undo(redo = false) {
  if (!active || active.keeping) return;
  if (gesture) { cancelGesture(); return; }
  const from = redo ? active.draft.redo : active.draft.undo;
  const to = redo ? active.draft.undo : active.draft.redo;
  if (!from.length) return;
  to.push(snapshot());
  const old = from.pop();
  Object.assign(active.draft, copy(old));
  invalidate(); requestPreview();
}

export function initMagneticBench() {
  if (wired || !$('bench-controls')) return;
  wired = true;
  const controls = document.createElement('div');
  controls.id = 'process-magnetic'; controls.hidden = true;
  controls.innerHTML = `
    <details open><summary>Arrangement</summary>
      <div class="magnetic-row"><button id="magnetic-add-bar">＋ Bar</button><button id="magnetic-add-north">＋ N</button><button id="magnetic-add-south">＋ S</button></div>
      <label class="magnetic-field">Selected magnet<select id="magnetic-selection"></select></label>
      <fieldset id="magnetic-selected" class="magnetic-fields"><legend class="hint">Position and shape</legend>
        <label>x (mm)<input id="magnetic-x" type="number" min="0" max="300" step="0.5"></label>
        <label>y (mm)<input id="magnetic-y" type="number" min="0" max="218" step="0.5"></label>
        <label data-bar>Angle (°)<input id="magnetic-rotation" type="number" min="-180" max="180" step="1"></label>
        <label data-bar>Length (mm)<input id="magnetic-length" type="number" min="8" max="80" step="1"></label>
        <label data-bar>Thickness (mm)<input id="magnetic-thickness" type="number" min="4" max="24" step="0.5"></label>
        <label>Strength<input id="magnetic-strength" type="number" min="0.1" max="3" step="0.1"></label>
      </fieldset>
      <div class="magnetic-row"><button id="magnetic-flip">Flip poles</button><button id="magnetic-duplicate">Duplicate</button><button id="magnetic-remove">Remove</button></div>
      <p class="hint">Drag a magnet to move it; drag its round handle to rotate. Click the paper to clear handles. Hidden magnets remain selectable here.</p>
    </details>
    <details open><summary>Drawing</summary>
      <label class="magnetic-field">Marks<select id="magnetic-style"><option value="continuous">Continuous curves</option><option value="chains">Irregular chains</option><option value="filings">Loose filings</option></select></label>
      <label class="magnetic-field">Density<input id="magnetic-density" type="range" min="24" max="100" step="1"><output id="magnetic-density-value"></output></label>
      <label class="magnetic-check"><input id="magnetic-show" type="checkbox">Show magnets</label>
      <label id="magnetic-silhouettes-label" class="magnetic-check"><input id="magnetic-silhouettes" type="checkbox">Keep empty silhouettes</label>
      <label class="magnetic-check"><input id="magnetic-escaping" type="checkbox">Remove escaping lines</label>
      <p class="hint">Removes whole curves that leave the drawing frame. With magnets hidden, turn off empty silhouettes to let lines gather around the poles.</p>
    </details>
    <details open><summary>Scatter magnets</summary>
      <div class="magnetic-fields"><label>Count<input id="magnetic-count" type="number" min="1" max="16" step="1" value="4"></label>
      <label>Type<select id="magnetic-scatter-type"><option value="bars">Bars</option><option value="poles">Poles</option><option value="both">Both</option></select></label></div>
      <label class="magnetic-field">Seed<input id="magnetic-seed" type="number" min="0" max="2147483647" step="1"></label>
      <div class="magnetic-row"><button id="magnetic-scatter">Scatter</button><button id="magnetic-reshuffle">Reshuffle</button><button id="magnetic-clear">Clear</button></div>
      <p class="hint">Scatter replaces this arrangement. The same seed, count and type repeat it; Undo restores the previous one.</p>
    </details>
    <details><summary>Drawing frame</summary><div class="magnetic-fields">
      <label>Width (mm)<input id="magnetic-width" type="number" min="40" max="300" step="1"></label>
      <label>Height (mm)<input id="magnetic-height" type="number" min="40" max="218" step="1"></label>
    </div><p class="hint">Fitted to the bed when kept. Resizing the popup does not change this boundary.</p></details>`;
  $('bench-controls').append(controls);
  const bar = document.createElement('div');
  bar.id = 'magnetic-actions'; bar.hidden = true;
  bar.innerHTML = `<button id="magnetic-undo">Undo</button><button id="magnetic-redo">Redo</button><span id="magnetic-kept" class="hint" aria-live="polite"></span><button id="magnetic-keep" class="primary" disabled>Keep as layer</button>`;
  document.querySelector('.bench-main').append(bar);
  $('magnetic-undo').onclick = () => undo();
  $('magnetic-redo').onclick = () => undo(true);
  $('magnetic-keep').onclick = keep;
  $('magnetic-selection').onchange = () => {
    active.draft.selection = Number($('magnetic-selection').value);
    renderControls(); drawHandles();
  };
  for (const name of ['x','y','rotation','length','thickness','strength']) {
    const input = $(`magnetic-${name}`);
    input.onchange = () => {
      if (!input.reportValidity() || input.value === '') { renderControls(); return; }
      change(p => { const m = selected(); if (m) { m[name] = Number(input.value); fit(m,p); } });
    };
  }
  for (const name of ['width','height','seed','density']) {
    const input = $(`magnetic-${name}`);
    input.onchange = () => {
      if (!input.reportValidity() || input.value === '') { renderControls(); return; }
      change(p => {
        p[name] = Number(input.value);
        if (name === 'width' || name === 'height') p.magnets.forEach(m => fit(m,p));
      });
    };
  }
  $('magnetic-density').oninput = () => { $('magnetic-density-value').textContent = $('magnetic-density').value; };
  $('magnetic-style').onchange = () => change(p => { p.style = $('magnetic-style').value; });
  $('magnetic-show').onchange = () => change(p => { p.show_magnets = $('magnetic-show').checked; });
  $('magnetic-silhouettes').onchange = () => change(p => { p.keep_silhouettes = $('magnetic-silhouettes').checked; });
  $('magnetic-escaping').onchange = () => change(p => { p.remove_escaping = $('magnetic-escaping').checked; });
  for (const kind of ['bar','north','south']) $(`magnetic-add-${kind}`).onclick = () => change(p => {
    if (p.magnets.length >= 16) return;
    p.magnets.push(fit({kind, x:p.width/2, y:p.height/2, rotation:0, length:48, thickness:12, strength:1, flipped:false},p));
    active.draft.selection = p.magnets.length-1;
  });
  $('magnetic-flip').onclick = () => change(() => {
    const m = selected(); if (!m) return;
    if (m.kind === 'bar') m.flipped = !m.flipped;
    else m.kind = m.kind === 'north' ? 'south' : 'north';
  });
  $('magnetic-duplicate').onclick = () => change(p => {
    if (!selected() || p.magnets.length >= 16) return;
    const m = copy(selected()); m.x += 12; m.y += 12;
    p.magnets.push(fit(m,p)); active.draft.selection = p.magnets.length-1;
  });
  $('magnetic-remove').onclick = () => change(p => {
    if (!selected()) return;
    p.magnets.splice(active.draft.selection,1);
    active.draft.selection = Math.min(active.draft.selection,p.magnets.length-1);
  });
  $('magnetic-clear').onclick = () => change(p => { p.magnets = []; active.draft.selection = -1; });
  for (const id of ['magnetic-scatter','magnetic-reshuffle']) $(id).onclick = () => {
    const input = $('magnetic-count');
    if (!input.reportValidity() || input.value === '') return;
    change(p => {
      if (id === 'magnetic-reshuffle') p.seed = (p.seed+1) % 2147483648;
      p.magnets = scattered(p, Number(input.value), $('magnetic-scatter-type').value);
      active.draft.selection = 0;
    });
  };
  // Installed before the host's capture handler, so undo stays in this draft.
  document.addEventListener('keydown', e => {
    if (!active || e.target.matches('input,textarea,select,[contenteditable="true"]')) return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault(); e.stopImmediatePropagation(); undo(e.shiftKey);
    }
  },true);
  const svg = $('process-canvas');
  svg.addEventListener('pointerdown', pointerDown);
  svg.addEventListener('pointermove', pointerMove);
  svg.addEventListener('pointerup', pointerUp);
  svg.addEventListener('pointercancel', cancelGesture);
  svg.addEventListener('lostpointercapture', () => { if (gesture) cancelGesture(); });
  document.addEventListener('bench-project-reset', () => {
    closeMagneticBench(false); drafts.clear();
    $('magnetic-count').value = '4'; $('magnetic-scatter-type').value = 'bars';
  });
}

export function openMagneticBench({mod,params,contextKey,onKeep,onClose}) {
  initMagneticBench(); closeMagneticBench(false);
  const original = {mod,params,contextKey,onKeep,onClose};
  const input = copy({...mod.defaults,...params});
  input.magnets.forEach(m => fit(m,input));
  const inputKey = JSON.stringify(input);
  const context = `${benchProjectEpoch()}:${contextKey || `new:${mod.id}`}`;
  let draft = drafts.get(context);
  if (!draft || (inputKey !== draft.inputKey && inputKey !== JSON.stringify(draft.params))) {
    draft = {params:input, inputKey, selection:input.magnets.length ? 0 : -1, undo:[],redo:[]};
    drafts.set(context,draft);
  }
  active = {mod,draft,external:params,onKeep,onClose,renderedKey:null,inFlight:false,queued:false,keeping:false};
  $('process-popup').classList.remove('second-reading','watch-only');
  $('process-popup').classList.add('magnetic-field');
  $('process-reference').setAttribute('hidden','');
  $('process-canvas').closest('.preview-stage').classList.remove('comparing');
  $('process-title').textContent = 'Magnetic field — working bench';
  $('process-magnetic').hidden = false; $('magnetic-actions').hidden = false;
  $('magnetic-kept').textContent = '';
  for (const id of ['process-params','process-second-reading','process-play','process-prev','process-next','process-scrub','process-readout','process-telemetry-row','process-create','process-reroll']) $(id).hidden = true;
  $('process-status').hidden = false;
  openBenchShell({close:() => closeMagneticBench(),cancelGesture,
    reopen:() => openMagneticBench(original),
    origin: contextKey?.startsWith('layer:') ? 'From kept layer · Keep creates a new layer' : 'Working draft · Keep creates a new layer'});
  $('process-canvas').replaceChildren();
  invalidate(); requestPreview();
}

export function closeMagneticBench(notify = true) {
  if (!active) return;
  cancelGesture();
  const closing = active;
  Object.assign(closing.external,copy(closing.draft.params));
  active = null;
  $('process-popup').classList.remove('magnetic-field');
  $('process-canvas').classList.remove('magnetic-pending');
  $('process-magnetic').hidden = true; $('process-magnetic').inert = false;
  $('magnetic-actions').hidden = true;
  if (notify) { closeBenchShell(); closing.onClose?.(); }
}

function renderControls() {
  if (!active) return;
  const p = active.draft.params, m = selected();
  const selection = $('magnetic-selection');
  selection.replaceChildren(new Option(p.magnets.length ? 'No selection' : 'No magnets','-1'), ...p.magnets.map((magnet,i) => new Option(`${i+1} · ${magnet.kind === 'bar' ? 'Bar magnet' : magnet.kind === 'north' ? 'North pole' : 'South pole'}`,String(i))));
  selection.value = String(active.draft.selection);
  for (const name of ['x','y','rotation','length','thickness','strength']) $(`magnetic-${name}`).value = m ? String(Math.round(m[name]*100)/100) : '';
  for (const name of ['width','height','seed','density','style']) $(`magnetic-${name}`).value = String(p[name]);
  $('magnetic-density-value').textContent = String(p.density);
  $('magnetic-show').checked = p.show_magnets;
  $('magnetic-silhouettes').checked = p.keep_silhouettes;
  $('magnetic-silhouettes-label').hidden = p.show_magnets;
  $('magnetic-escaping').checked = p.remove_escaping;
  $('magnetic-selected').disabled = !m;
  document.querySelectorAll('#magnetic-selected [data-bar]').forEach(el => { el.hidden = m?.kind !== 'bar'; });
  for (const id of ['magnetic-remove','magnetic-flip']) $(id).disabled = !m;
  $('magnetic-duplicate').disabled = !m || p.magnets.length >= 16;
  for (const kind of ['bar','north','south']) $(`magnetic-add-${kind}`).disabled = p.magnets.length >= 16;
  $('magnetic-undo').disabled = !active.draft.undo.length || active.keeping;
  $('magnetic-redo').disabled = !active.draft.redo.length || active.keeping;
  $('process-magnetic').inert = active.keeping;
  $('magnetic-keep').disabled = active.keeping || Boolean(gesture) || active.inFlight || active.renderedKey !== key();
  $('magnetic-keep').textContent = active.keeping ? 'Keeping…' : 'Keep as layer';
  $('process-status').textContent = active.error ? 'Preview unavailable — retry below' : gesture ? 'Move the magnet; release to update the field' : active.renderedKey !== key()
    ? 'Updating field…' : `${active.output.lines.length.toLocaleString()} ink paths${p.style === 'continuous' ? ' · continuous' : ' · many pen lifts'}${active.output.decimated ? ' · simplified preview' : ''}${!p.magnets.length ? ' · add a magnet to begin' : ''}`;
}

async function requestPreview() {
  if (!active) return;
  const owner = active;
  if (owner.inFlight) { owner.queued = true; return; }
  const exact = copy(owner.draft.params), expected = JSON.stringify(exact);
  owner.inFlight = true; owner.queued = false; owner.error = false;
  clearBenchError(); renderControls();
  try {
    const output = await api.post('/api/generators/preview',{module:owner.mod.id,params:exact});
    if (active !== owner || key() !== expected || gesture) return;
    owner.output = output; owner.renderedKey = expected;
    const svg = $('process-canvas');
    svg.replaceChildren();
    const paths = document.createElementNS(NS,'g'); paths.classList.add('magnetic-ink');
    for (const line of output.lines) {
      const el = document.createElementNS(NS,'polyline');
      el.setAttribute('points',line.map(([x,y]) => `${x},${y}`).join(' '));
      el.setAttribute('class','draw-line'); paths.append(el);
    }
    svg.append(paths); svg.dataset.renderedRecipe = expected;
    svg.classList.remove('magnetic-pending'); drawHandles();
  } catch (error) {
    if (active === owner && key() === expected) { owner.error = true; showBenchError(error,requestPreview); }
  } finally {
    owner.inFlight = false;
    if (active === owner) {
      renderControls();
      if (owner.queued && !gesture) requestPreview();
    }
  }
}

function element(tag,attrs) {
  const el = document.createElementNS(NS,tag);
  for (const [name,value] of Object.entries(attrs)) el.setAttribute(name,String(value));
  return el;
}
function drawHandles() {
  if (!active) return;
  const p = active.draft.params, svg = $('process-canvas');
  svg.setAttribute('viewBox',`0 0 ${p.width} ${p.height}`);
  svg.style.aspectRatio = `${p.width} / ${p.height}`;
  svg.style.setProperty('--process-aspect',String(p.width/p.height));
  svg.querySelector('.magnetic-handles')?.remove();
  const group = element('g',{class:'magnetic-handles'});
  p.magnets.forEach((m,i) => {
    const box = element('g',{'data-magnet':i,transform:`translate(${m.x} ${m.y}) rotate(${m.kind === 'bar' ? m.rotation : 0})`,class:i === active.draft.selection ? 'magnetic-selected' : ''});
    const hit = m.kind === 'bar' ? element('rect',{x:-m.length/2,y:-m.thickness/2,width:m.length,height:m.thickness}) : element('circle',{cx:0,cy:0,r:4});
    hit.setAttribute('class','magnetic-hit'); box.append(hit);
    if (i === active.draft.selection) {
      box.append(element('path',{d:'M-1.5 0H1.5 M0 -1.5V1.5',class:'magnetic-center'}));
      if (m.kind === 'bar') {
        box.append(element('path',{d:`M0 0H${m.length/2+9}`,class:'magnetic-arm'}));
        box.append(element('circle',{cx:m.length/2+9,cy:0,r:2.4,class:'magnetic-rotate','data-rotate':'true'}));
      }
    }
    group.append(box);
  });
  svg.append(group);
}
function point(event) {
  const svg = $('process-canvas'), matrix = svg.getScreenCTM();
  if (!matrix) return null;
  return new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());
}
function pointerDown(event) {
  if (!active || active.keeping || gesture || event.button !== 0) return;
  const target = event.target.closest('[data-magnet]');
  if (!target) { active.draft.selection = -1; renderControls(); drawHandles(); return; }
  const at = point(event); if (!at) return;
  event.preventDefault();
  active.draft.selection = Number(target.dataset.magnet);
  gesture = {pointer:event.pointerId,start:at,before:snapshot(),magnet:copy(selected()),rotate:event.target.hasAttribute('data-rotate')};
  $('process-canvas').setPointerCapture(event.pointerId);
  renderControls(); drawHandles();
}
function pointerMove(event) {
  if (!active || !gesture || gesture.pointer !== event.pointerId) return;
  const at = point(event); if (!at) return;
  const m = selected(), p = active.draft.params;
  if (gesture.rotate) m.rotation = Math.atan2(at.y-m.y,at.x-m.x)*180/Math.PI;
  else { m.x = gesture.magnet.x + at.x-gesture.start.x; m.y = gesture.magnet.y + at.y-gesture.start.y; }
  fit(m,p); invalidate();
}
function pointerUp(event) {
  if (!gesture || gesture.pointer !== event.pointerId) return;
  const before = gesture.before;
  gesture = null;
  $('process-canvas').releasePointerCapture(event.pointerId);
  if (JSON.stringify(before.params) !== key()) remember(before);
  drawHandles(); renderControls();
  if (active.renderedKey !== key()) requestPreview();
}
function cancelGesture() {
  if (!active || !gesture) return false;
  const before = gesture.before, pointer = gesture.pointer;
  gesture = null;
  Object.assign(active.draft,copy(before));
  if ($('process-canvas').hasPointerCapture(pointer)) $('process-canvas').releasePointerCapture(pointer);
  invalidate(); requestPreview();
  return true;
}
async function keep() {
  if (!active || $('magnetic-keep').disabled) return;
  const owner = active, exact = copy(owner.draft.params);
  owner.keeping = true; clearBenchError(); renderControls();
  try {
    const layer = await owner.onKeep(exact);
    if (active === owner) $('magnetic-kept').textContent = `Kept · ${layer?.name || 'layer'}`;
  } catch (error) {
    if (active === owner) showBenchError(error); // no automatic retry of writes
  } finally {
    owner.keeping = false; if (active === owner) renderControls();
  }
}
