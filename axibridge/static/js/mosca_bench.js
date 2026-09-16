// A recorded trajectory editor; all ink comes from the registered Mosca source.
import { api } from './api.js';
import { openBenchShell, closeBenchShell, clearBenchError, showBenchError } from './bench_host.js';
const $ = id => document.getElementById(id);
const copy = x => JSON.parse(JSON.stringify(x));
let active = null;
let wired = false;

function init() {
  if (wired) return;
  wired = true;
  const controls = document.createElement('div');
  controls.id = 'process-mosca'; controls.hidden = true;
  controls.innerHTML = `<label>Find a recording<input id="mosca-search" type="search" placeholder="Experiment or drawing"></label>
    <button id="mosca-refresh">Refresh recordings</button><div id="mosca-recordings" aria-label="Mosca recordings"></div>
    <label>Curve tolerance (mm)<input id="mosca-tolerance" type="number" min="0" max="5" step="0.01" value="0.05"></label>
    <p class="hint">Lower values preserve finer detail. Zero retains every recorded sample.</p>
    <p class="hint">Recorded fruit fly trajectories · Mosca-draw. Connectome data: Janelia FlyEM / Google, CC-BY.</p>`;
  $('bench-controls').append(controls);
  const bar = document.createElement('div'); bar.id = 'mosca-actions'; bar.hidden = true;
  bar.innerHTML = `<span id="mosca-selected" class="hint"></span><div class="mosca-transport">
    <button id="mosca-play" disabled>Play</button><button id="mosca-prev" aria-label="Previous sample" disabled>‹</button>
    <input id="mosca-scrub" aria-label="Drawing progress" type="range" min="0" max="1" step="any" value="1" disabled>
    <button id="mosca-next" aria-label="Next sample" disabled>›</button><output id="mosca-readout">0%</output></div>
    <div class="mosca-transport"><span id="mosca-kept" class="hint" aria-live="polite"></span><button id="mosca-keep" class="primary" disabled>Keep as layer</button></div>`;
  document.querySelector('.bench-main').append(bar);
  $('mosca-search').oninput = renderList;
  $('mosca-refresh').onclick = refresh;
  $('mosca-scrub').oninput = () => { const value = Number($('mosca-scrub').value); stop(); change(value); };
  $('mosca-tolerance').onchange = () => {
    if (!active || active.keeping) return;
    if (!$('mosca-tolerance').reportValidity() || !$('mosca-tolerance').value) return;
    active.params.tolerance = Number($('mosca-tolerance').value); invalidate();
  };
  $('mosca-prev').onclick = () => step(-1);
  $('mosca-next').onclick = () => step(1);
  $('mosca-play').onclick = () => {
    if (!active) return;
    if (active.playing) { stop(); return; }
    active.playing = true;
    if (active.params.progress >= 1) change(0);
    else invalidate();
    update();
  };
  $('mosca-keep').onclick = keep;
  document.addEventListener('bench-project-reset', () => closeMoscaBench(false));
}
export function openMoscaBench({mod, params, onKeep, onClose, contextKey}) {
  init(); closeMoscaBench(false);
  const owner = active = {params: copy({...mod.defaults,...params}), external:params, onKeep,onClose,
    serial:0,selection:0,listing:0,records:[], keeping:false,rendered:null,meta:null,playing:false};
  $('process-popup').classList.remove('magnetic-field','second-reading','watch-only');
  $('process-popup').classList.add('mosca-bench');
  $('process-mosca').hidden = false; $('process-mosca').inert = false; $('mosca-actions').hidden = false;
  for (const id of ['process-params','process-second-reading','process-generic-save-gallery','process-play','process-prev','process-next','process-scrub','process-readout','process-telemetry-row','process-create','process-reroll','process-reference']) $(id)?.setAttribute('hidden','');
  $('process-canvas').closest('.preview-stage').classList.remove('comparing');
  $('process-title').textContent = 'Mosca — recording bench';
  $('process-status').hidden = false;
  $('process-canvas').replaceChildren();
  $('mosca-search').value = ''; $('mosca-kept').textContent = '';
  $('mosca-tolerance').value = String(owner.params.tolerance);
  openBenchShell({close: () => closeMoscaBench(), origin:contextKey?.startsWith('layer:')
    ? 'From kept layer · Keep creates a new layer' : 'Recorded drawings · Keep creates a new layer'});
  update();
  if (owner.params.recording) {
    api.get(`/api/mosca/info?recording=${encodeURIComponent(owner.params.recording)}`).then(meta => {
      if (active !== owner || owner.selection) return;
      owner.meta = meta; invalidate();
    }).catch(error => { if (active === owner && !owner.selection) showBenchError(error); });
  }
  refresh();
}
export function closeMoscaBench(notify = true) {
  if (!active) return;
  const owner = active; stop(); clearTimeout(owner.timer); owner.abort?.abort();
  Object.assign(owner.external,copy(owner.params)); active = null;
  $('process-mosca').hidden = true; $('mosca-actions').hidden = true;
  $('process-popup').classList.remove('mosca-bench');
  if (notify) { closeBenchShell(); owner.onClose?.(); }
}
async function refresh() {
  if (!active) return;
  const owner = active, serial = ++owner.listing;
  $('mosca-refresh').disabled = true;
  try {
    const result = await api.get('/api/mosca/recordings');
    if (active !== owner || serial !== owner.listing) return;
    owner.records = result.recordings; renderList();
  } catch (error) {
    if (active === owner && serial === owner.listing) showBenchError(error,refresh);
  } finally { if (active === owner && serial === owner.listing) $('mosca-refresh').disabled = owner.keeping; }
}
function renderList() {
  if (!active) return;
  const list = $('mosca-recordings'); list.replaceChildren();
  const q = $('mosca-search').value.trim().toLowerCase();
  let group, previous;
  for (const record of active.records.filter(r => `${r.experiment} ${r.label}`.toLowerCase().includes(q))) {
    if (record.experiment !== previous) {
      group = document.createElement('details'); group.open = Boolean(q);
      const title = document.createElement('summary'); title.textContent = record.experiment;
      group.append(title); list.append(group); previous = record.experiment;
    }
    const button = document.createElement('button'); button.className = 'mosca-recording'; button.disabled = active.keeping;
    const img = document.createElement('img'); img.alt = ''; img.loading = 'lazy';
    // Only fetch thumbnails when their experiment is opened.
    const ownGroup = group;
    ownGroup.addEventListener('toggle', () => { if (ownGroup.open && !img.src) img.src = `/api/mosca/thumbnail?id=${encodeURIComponent(record.id)}`; });
    if (q) img.src = `/api/mosca/thumbnail?id=${encodeURIComponent(record.id)}`;
    const label = document.createElement('span'); label.textContent = record.label;
    button.append(img,label); button.onclick = () => select(record); group.append(button);
  }
  if (!list.children.length) list.textContent = 'No matching recordings.';
}
async function select(record) {
  if (!active || active.keeping) return;
  stop(); const owner = active, selection = ++owner.selection;
  owner.abort?.abort(); clearTimeout(owner.timer); owner.serial++; owner.meta = null; owner.rendered = null;
  $('process-canvas').replaceChildren(); update(); clearBenchError();
  $('process-status').textContent = 'Loading recording…';
  try {
    const meta = await api.post('/api/mosca/prepare',{id:record.id});
    if (active !== owner || selection !== owner.selection) return;
    owner.params.recording = meta.recording; owner.params.progress = 1; owner.meta = meta;
    invalidate();
  } catch (error) { if (active === owner && selection === owner.selection) showBenchError(error, () => select(record)); }
}
function stop() {
  if (!active) return;
  active.playing = false; clearTimeout(active.playTimer); update();
}
function step(direction) {
  if (!active?.meta || active.keeping) return;
  stop(); const n = active.meta.samples - 1, index = active.params.progress * n;
  change((direction > 0 ? Math.floor(index + 1e-8) + 1 : Math.ceil(index - 1e-8) - 1) / Math.max(1,n));
}
function change(progress) {
  if (!active?.meta || active.keeping) return;
  active.params.progress = Math.max(0,Math.min(1,progress)); invalidate();
}
function invalidate() {
  if (!active) return;
  active.rendered = null; active.abort?.abort(); active.serial++;
  clearTimeout(active.timer); clearTimeout(active.playTimer);
  $('mosca-kept').textContent = ''; update();
  active.timer = setTimeout(preview,70);
}
function update() {
  if (!active) return;
  const o = active, p = o.params, ready = Boolean(o.meta);
  for (const id of ['mosca-play','mosca-prev','mosca-next','mosca-scrub']) $(id).disabled = !ready || o.keeping;
  $('process-mosca').inert = o.keeping;
  $('mosca-tolerance').disabled = o.keeping;
  $('mosca-play').textContent = o.playing ? 'Pause' : 'Play';
  $('mosca-scrub').value = String(p.progress);
  $('mosca-readout').textContent = `${(p.progress * 100).toFixed(2)}%${o.meta?.duration_ms != null ? ` · ${(p.progress * o.meta.duration_ms / 1000).toFixed(2)} s` : ''}`;
  $('mosca-selected').textContent = o.meta ? `${o.meta.experiment} / ${o.meta.label}` : 'Choose a recording';
  $('mosca-keep').disabled = o.keeping || !o.rendered || !o.output?.drawable;
  $('mosca-keep').textContent = o.keeping ? 'Keeping…' : 'Keep as layer';
  $('process-status').textContent = !ready ? 'Choose a recording to begin' : !o.rendered ? 'Updating drawing…'
    : `${o.output.points.toLocaleString()} points · ${o.output.lines.length} ink paths${o.output.decimated ? ' · simplified display' : ''}`;
}
async function preview() {
  if (!active?.meta) return;
  const owner = active, serial = ++owner.serial, exact = copy(owner.params);
  owner.abort = new AbortController(); clearBenchError();
  try {
    const output = await api.post('/api/mosca/preview',{params:exact},{signal:owner.abort.signal});
    if (active !== owner || serial !== owner.serial) return;
    owner.output = output; owner.rendered = JSON.stringify(exact);
    const svg = $('process-canvas'); svg.replaceChildren();
    svg.setAttribute('viewBox',`0 0 ${output.width} ${output.height}`);
    svg.style.aspectRatio = `${output.width} / ${output.height}`;
    svg.style.setProperty('--process-aspect',String(output.width/output.height));
    for (const line of output.lines) {
      const el = document.createElementNS('http://www.w3.org/2000/svg','polyline');
      el.setAttribute('points',line.map(p => p.join(',')).join(' ')); el.setAttribute('class','draw-line'); svg.append(el);
    }
    svg.dataset.renderedRecipe = owner.rendered;
    if (owner.playing) {
      if (exact.progress >= 1) owner.playing = false;
      else owner.playTimer = setTimeout(() => { if (active === owner) change(exact.progress + .01); },70);
    }
    update();
  } catch (error) {
    if (active === owner && serial === owner.serial && error.name !== 'AbortError') {
      stop(); showBenchError(error,preview); $('process-status').textContent = 'Preview unavailable';
    }
  }
}
async function keep() {
  if (!active || $('mosca-keep').disabled) return;
  stop(); const owner = active, exact = copy(owner.params); owner.keeping = true; update(); clearBenchError();
  try {
    await owner.onKeep(exact);
    if (active === owner) $('mosca-kept').textContent = 'Kept as a new layer';
  } catch (error) { if (active === owner) showBenchError(error); }
  finally { owner.keeping = false; if (active === owner) { $('process-mosca').inert = false; update(); } }
}
