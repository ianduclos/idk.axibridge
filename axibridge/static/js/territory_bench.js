// Territory bench: the meander drawing (tools/territory-prototype, Version 10) with every dial live.
// The engine runs in a worker (territory/worker.js); Keep sends the drawn strokes and their recipe to
// the `territory` source, which only replays them — what you see on the stage is exactly what is kept.
import { openBenchShell, closeBenchShell, clearBenchError, showBenchError } from './bench_host.js';

const $ = id => document.getElementById(id);
const ENGINE = 'meander-v10';
// [key, label, min, max, [randomize range], note, group]; defaults below. Mirrors the prototype page.
const DIALS = [
  ['complexity', 'Complexity', 0, 1, [0.2, 0.9], 'How many channels, and whether a second river crosses the first.', 'Drawing'],
  ['drift', 'Drift', 0.2, 1, [0.35, 0.9], 'How far the bends migrate from where they started.', 'Drawing'],
  ['band', 'Band', 0.5, 2, [0.7, 1.5], 'Width of the strand bundles; low is nearly single lines.', 'Drawing'],
  ['chaos', 'Chaos', 0, 1, [0.2, 0.8], 'Tangles and searching passes, kept to a few places; the rest stays deliberate.', 'Drawing'],
  ['accents', 'Accents', 0, 1, [0.2, 0.9], 'Tight stated arcs beside sharp bends and next to the chaos.', 'Drawing'],
  ['bridges', 'Bridges', 0, 1, [0.2, 0.9], 'Curves that join lines where they cross or nearly meet.', 'Drawing'],
  ['history', 'History', 0, 1, [0.3, 0.9], 'Traces of where a channel used to be.', 'Drawing'],
  ['density', 'Density', 0, 1.5, [0.3, 1.2], 'How busy the sheet gets. 0 is the calm drawing; past 1 is over.', 'Density'],
  ['continue', 'Continue', 0, 2, [0.2, 1.6], 'Bands run past their ends and cross the sheet as ribbons. Past 1 is over.', 'sub'],
  ['cover', 'Cover', 0, 1, [0.3, 0.55], 'How much of the ground gets filled; some voids stay dark.', 'sub'],
  ['planes', 'Planes', 0, 1, [0, 0.6], '0: fields grow out of the lines. Higher: brushed planes, crossing lines as rare events; 1 is all planes.', 'sub'],
  ['mutate', 'Mutate', 0, 1.5, [0.3, 1.3], 'Changes inside the grown fields, passed on echo to echo. Past 1 is over.', 'sub'],
  ['slash', 'Slash', 0, 2, [0, 1.6], 'Straight cuts and shard wedges across the forms. Past 1 is over.', 'sub'],
  ['surprise', 'Surprise', 0, 2, [0, 1.6], 'A region in another register; past 1 is over, past 1.3 there are two.', 'sub'],
  ['ink', 'Ink limit (m)', 5, 100, [20, 80], 'Most ink the sheet may use. Plot time grows with ink and pen lifts.', 'sub'],
];
const OVER = new Set(['density', 'continue', 'mutate', 'slash', 'surprise']);   // dials whose range runs past 1 ('over')
const DEF = { complexity: 0.5, drift: 0.6, band: 1, chaos: 0.5, accents: 0.5, bridges: 0.5, history: 0.6,
  density: 0, continue: 0.5, cover: 0.45, planes: 0.15, mutate: 1, slash: 0.5, surprise: 0.5, ink: 40 };
// Lucide (ISC): lock, lock-open, shuffle, undo-2, chevron-left/right, copy
const ICON = {
  lock: ['M5 11h14v10H5z', 'M7 11V7a5 5 0 0 1 10 0v4'],
  open: ['M5 11h14v10H5z', 'M7 11V7a5 5 0 0 1 9.9-1'],
  shuffle: ['m18 14 4 4-4 4', 'm18 2 4 4-4 4', 'M2 18h1.973a4 4 0 0 0 3.3-1.7l5.454-8.6a4 4 0 0 1 3.3-1.7H22', 'M2 6h1.972a4 4 0 0 1 3.6 2.2', 'M22 18h-6.041a4 4 0 0 1-3.3-1.8l-.359-.45'],
  back: ['M9 14 4 9l5-5', 'M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5 5.5 5.5 0 0 1-5.5 5.5H11'],
  left: ['m15 18-6-6 6-6'], right: ['m9 18 6-6-6-6'],
  copy: ['M9 9h12v12H9Z', 'M5 15H3V3h12v2'],
};
const svg = paths => `<svg class="tool-icon" viewBox="0 0 24 24" aria-hidden="true">${paths.map(d => `<path d="${d}"/>`).join('')}</svg>`;
const store = { get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private window */ } } };
const clampSeed = v => Math.max(1, Math.min(999999, Math.floor(Number(v) || 1)));
const fmt = (k, v) => k === 'ink' ? String(Math.round(v)) : (+v).toFixed(2);

let wired = false, active = null, worker = null, jobId = 0, thumbGen = 0;

function getWorker() {
  if (worker) return worker;
  worker = new Worker(new URL('./territory/worker.js', import.meta.url), { type: 'module' });
  worker.onmessage = e => { const r = e.data; if (!active) return; if (r.kind === 'sheet') onSheet(r); else onThumb(r); };
  worker.onerror = e => { if (active) { showBenchError(new Error(e.message || 'The drawing engine failed to load'), () => render()); setStatus('Engine unavailable'); } };
  return worker;
}

function init() {
  if (wired) return;
  wired = true;
  const side = document.createElement('div');
  side.id = 'process-territory'; side.hidden = true;
  side.innerHTML = `
    <section class="tb-seed" aria-label="Seed">
      <label for="tb-seed">Seed</label>
      <div class="tb-row">
        <button id="tb-prev" class="tb-icon" aria-label="Previous seed" title="Previous seed (←)">${svg(ICON.left)}</button>
        <input id="tb-seed" type="number" min="1" max="999999" step="1" inputmode="numeric">
        <button id="tb-next" class="tb-icon" aria-label="Next seed" title="Next seed (→)">${svg(ICON.right)}</button>
        <button id="tb-lock-seed" class="tb-lock" data-lock="seed" aria-pressed="false" aria-label="Lock seed" title="Keep the seed when surprising">${svg(ICON.open)}</button>
      </div>
      <div class="tb-row">
        <button id="tb-surprise" title="New seed and dials, except locked ones (R)">${svg(ICON.shuffle)}<span>Surprise</span></button>
        <button id="tb-back" title="Back to the previous drawing (Backspace)">${svg(ICON.back)}<span>Back</span></button>
      </div>
      <p class="hint tb-lock-hint">Surprise changes seed and dials; locked ones stay put.</p>
    </section>
    <div id="tb-dials"></div>
    <details class="tb-settings"><summary>Settings as text</summary>
      <p id="tb-recipe" class="hint tb-recipe"></p>
      <button id="tb-copy">${svg(ICON.copy)}<span>Copy settings</span></button>
      <input id="tb-paste" type="text" placeholder="Paste settings and press Enter" aria-label="Paste settings">
      <p id="tb-msg" class="hint" aria-live="polite"></p>
    </details>`;
  $('bench-controls').append(side);
  const dials = side.querySelector('#tb-dials');
  let sub = null, lastGrp = null;
  for (const [k, label, lo, hi, , note, grp] of DIALS) {
    if (grp !== 'sub' && grp !== lastGrp) { lastGrp = grp; const h = document.createElement('h3'); h.className = 'tb-group'; h.textContent = grp; dials.append(h); }
    const row = document.createElement('div');
    row.className = 'tb-dial';
    row.innerHTML = `<label for="tb-d-${k}" title="Double-click to reset">${label}</label><output id="tb-v-${k}"></output>
      <button class="tb-lock" data-lock="${k}" aria-pressed="false" aria-label="Lock ${label.toLowerCase()}" title="Lock: Surprise me leaves it alone">${svg(ICON.open)}</button>
      <input id="tb-d-${k}" type="range" min="${lo}" max="${hi}" step="any">
      <small>${note}</small>`;
    if (grp === 'sub') {
      if (!sub) { sub = document.createElement('div'); sub.id = 'tb-sub'; sub.innerHTML = '<p class="hint tb-idle-hint">Turn up Density to use these.</p>'; dials.append(sub); }
      sub.append(row);
    } else dials.append(row);
    const input = row.querySelector('input');
    input.addEventListener('pointerdown', () => remember());
    input.addEventListener('keydown', e => { if (e.key.startsWith('Arrow') || e.key === 'Home' || e.key === 'End' || e.key.startsWith('Page')) remember(); });
    input.addEventListener('input', () => { if (!active) return; active.dials[k] = +input.value; sync(); render(90); });
    input.addEventListener('change', () => { if (!active) return; refreshThumbs(true); });
    row.querySelector('label').addEventListener('dblclick', () => { if (!active) return; remember(); active.dials[k] = DEF[k]; sync(); render(); refreshThumbs(true); });
  }
  for (const b of side.querySelectorAll('.tb-lock')) b.addEventListener('click', () => {
    if (!active) return; const k = b.dataset.lock; active.locks[k] = !active.locks[k]; store.set('territory.locks', active.locks); sync();
  });
  $('tb-prev').onclick = () => stepSeed(-1);
  $('tb-next').onclick = () => stepSeed(1);
  $('tb-seed').onchange = () => { if (!active) return; remember(); active.seed = clampSeed($('tb-seed').value); sync(); render(); refreshThumbs(true); };
  $('tb-surprise').onclick = surprise;
  $('tb-back').onclick = back;
  $('tb-copy').onclick = () => { try { navigator.clipboard.writeText(recipeText()).then(() => say('Copied the settings.'), () => say('The clipboard is not available here.')); } catch { say('The clipboard is not available here.'); } };
  $('tb-paste').onkeydown = e => { if (e.key !== 'Enter' || !active) return; e.preventDefault(); paste($('tb-paste').value); };

  const stage = document.querySelector('#process-popup .preview-stage');
  const canvas = document.createElement('canvas');
  canvas.id = 'territory-canvas'; canvas.hidden = true; canvas.setAttribute('role', 'img'); canvas.setAttribute('aria-label', 'Territory drawing');
  stage.append(canvas);
  new ResizeObserver(() => { if (active) draw(); }).observe(stage);

  const strip = document.createElement('div');
  strip.id = 'territory-variations'; strip.hidden = true;
  strip.innerHTML = `<span class="hint tb-strip-label">Next seeds</span><button id="tb-thumbs-prev" class="tb-icon" aria-label="Previous six seeds">${svg(ICON.left)}</button>
    <div id="tb-thumbs" role="list" aria-label="Other seeds with these dials"></div>
    <button id="tb-thumbs-next" class="tb-icon" aria-label="Next six seeds">${svg(ICON.right)}</button>`;
  const bar = document.createElement('div');
  bar.id = 'territory-actions'; bar.hidden = true;
  bar.innerHTML = `<span id="tb-status" class="hint" aria-live="polite"></span><span id="tb-kept" class="hint" aria-live="polite"></span>
    <span class="hint tb-keys" aria-hidden="true">← → seed · R surprise · ⌫ back · ⏎ keep</span>
    <button id="tb-keep" class="primary" title="Keep this drawing as a new layer (Enter)">Keep as layer</button>`;
  const main = document.querySelector('.bench-main');
  main.append(strip, bar);
  $('tb-thumbs-prev').onclick = () => { if (!active) return; active.thumbFrom = Math.max(1, active.thumbFrom - 6); refreshThumbs(); };
  $('tb-thumbs-next').onclick = () => { if (!active) return; active.thumbFrom += 6; refreshThumbs(); };
  $('tb-keep').onclick = keep;
  // window capture runs before the shell's document-capture guard (which swallows Backspace)
  window.addEventListener('keydown', onKey, true);
  document.addEventListener('bench-project-reset', () => closeTerritoryBench(false));
}

export function openTerritoryBench({ mod, params, contextKey, onKeep, onClose }) {
  init(); closeTerritoryBench(false);
  const fromLayer = contextKey?.startsWith('layer:');
  const rec = (fromLayer ? params?.recipe : null) || store.get('territory.settings', null) || params?.recipe || {};
  const dials = { ...DEF };
  for (const [k] of DIALS) { const v = rec[k] ?? (k === 'continue' ? rec.cont : undefined); if (Number.isFinite(+v) && v !== null) dials[k] = +v; }
  active = { seed: clampSeed(rec.seed ?? 22), dials, locks: store.get('territory.locks', {}), history: [], onKeep, onClose,
    rendered: null, keeping: false, pending: 0, thumbFrom: 0, thumbs: new Map(), mod };
  active.thumbFrom = active.seed + 1;
  const popup = $('process-popup');
  popup.classList.remove('magnetic-field', 'second-reading', 'watch-only', 'mosca-bench');
  popup.classList.add('territory-bench');
  for (const id of ['process-params', 'process-second-reading', 'process-generic-save-gallery', 'process-play', 'process-prev', 'process-next',
    'process-scrub', 'process-readout', 'process-telemetry-row', 'process-create', 'process-reroll', 'process-reference', 'process-canvas', 'process-status']) $(id)?.setAttribute('hidden', '');
  for (const id of ['process-territory', 'territory-canvas', 'territory-variations', 'territory-actions']) { $(id).hidden = false; $(id).inert = false; }
  $('process-title').textContent = 'Territory';
  $('tb-kept').textContent = ''; $('tb-msg').textContent = ''; $('tb-paste').value = '';
  openBenchShell({ close: () => closeTerritoryBench(), origin: fromLayer ? 'Reopened from a kept layer · Keep creates a new layer' : 'Meander drawing · Keep creates a new layer' });
  $('bench-controls').scrollTop = 0;
  sync(); draw(); render(0); refreshThumbs(true);
}

export function closeTerritoryBench(notify = true) {
  if (!active) return;
  const owner = active; active = null; clearTimeout(owner.timer);
  worker?.postMessage({ kind: 'cancel-thumbs', gen: ++thumbGen });
  for (const id of ['process-territory', 'territory-canvas', 'territory-variations', 'territory-actions']) $(id).hidden = true;
  for (const id of ['process-canvas', 'process-status']) $(id)?.removeAttribute('hidden');
  $('process-popup').classList.remove('territory-bench');
  if (notify) { closeBenchShell(); owner.onClose?.(); }
}

// ---- state ----
const snapshot = () => ({ seed: active.seed, dials: { ...active.dials } });
function remember() {
  if (!active) return; const s = snapshot(), last = active.history.at(-1);
  if (last && JSON.stringify(last) === JSON.stringify(s)) return;
  active.history.push(s); if (active.history.length > 20) active.history.shift();
}
function back() {
  if (!active || !active.history.length || active.keeping) return;
  const s = active.history.pop(); active.seed = s.seed; active.dials = s.dials; sync(); render(); refreshThumbs(true);
}
function stepSeed(d) {
  if (!active || active.keeping) return; remember(); active.seed = clampSeed(active.seed + d); sync(); render();
}
function surprise() {
  if (!active || active.keeping) return; remember();
  for (const [k, , , , [a, b]] of DIALS) if (!active.locks[k]) active.dials[k] = +(a + (b - a) * Math.random()).toFixed(k === 'ink' ? 0 : 2);
  if (!active.locks.seed) active.seed = 1 + Math.floor(Math.random() * 9999);
  active.thumbFrom = active.seed + 1; sync(); render(); refreshThumbs(true);
}
function recipeText() {
  return `seed ${active.seed} · ` + DIALS.map(([k]) => `${k} ${fmt(k, active.dials[k])}`).join(' · ');
}
function paste(text) {
  const o = {}; for (const m of String(text).matchAll(/([a-z]+)\s+(-?[\d.]+)/gi)) o[m[1].toLowerCase()] = +m[2];
  if (!Object.keys(o).length) return say('No settings found in that text.');
  remember();
  if (o.seed) active.seed = clampSeed(o.seed);
  for (const [k, , lo, hi] of DIALS) if (Number.isFinite(o[k])) active.dials[k] = Math.max(lo, Math.min(hi, o[k]));
  $('tb-paste').value = ''; say('Loaded the settings.'); active.thumbFrom = active.seed + 1; sync(); render(); refreshThumbs(true);
}
const say = t => { $('tb-msg').textContent = t; };
const setStatus = t => { $('tb-status').textContent = t; };

function sync() {
  if (!active) return; const o = active;
  $('tb-seed').value = String(o.seed);
  for (const [k] of DIALS) {
    const inp = $('tb-d-' + k); if (+inp.value !== o.dials[k]) inp.value = String(o.dials[k]);
    inp.style.setProperty('--fill', `${Math.max(0, Math.min(100, (+inp.value - +inp.min) / (+inp.max - +inp.min) * 100))}%`);   // the app paints fills on input events only
    $('tb-v-' + k).textContent = fmt(k, o.dials[k]);
    $('tb-v-' + k).classList.toggle('over', OVER.has(k) && o.dials[k] > 1);
  }
  for (const b of document.querySelectorAll('#process-territory .tb-lock')) {
    const on = Boolean(o.locks[b.dataset.lock]); b.setAttribute('aria-pressed', String(on)); b.innerHTML = svg(on ? ICON.lock : ICON.open);
  }
  $('tb-sub').classList.toggle('tb-idle', !(o.dials.density > 0));
  for (const b of document.querySelectorAll('.tb-thumb')) b.classList.toggle('current', b.dataset.seed === String(o.seed));
  $('tb-back').disabled = !o.history.length || o.keeping;
  $('tb-recipe').textContent = recipeText();
  $('tb-keep').disabled = o.keeping || !o.rendered || o.rendered.key !== key();
  $('tb-keep').textContent = o.keeping ? 'Keeping…' : 'Keep as layer';
  $('process-territory').inert = o.keeping;
  store.set('territory.settings', { seed: o.seed, ...o.dials });
}
const key = () => JSON.stringify(snapshot());

// ---- rendering ----
function render(delay = 0) {
  if (!active) return; clearTimeout(active.timer);
  $('tb-kept').textContent = ''; setStatus('Drawing…'); sync();
  active.timer = setTimeout(() => {
    if (!active) return; clearBenchError();
    active.pending = ++jobId;
    getWorker().postMessage({ kind: 'sheet', id: jobId, seed: active.seed, dials: { ...active.dials }, key: key() });
  }, delay);
}
function onSheet(r) {
  if (r.id !== active.pending) return;
  if (r.error) { showBenchError(new Error(r.error), () => render()); setStatus('Drawing failed'); return; }
  active.rendered = { key: r.key, xy: r.xy, lens: r.lens, ink: r.ink };
  if (r.key === key()) setStatus(`Seed ${active.seed} · ${(r.ink / 1000).toFixed(1)} m ink · ${r.lens.length.toLocaleString()} strokes`);
  $('territory-canvas').dataset.renderedRecipe = r.key;
  $('territory-canvas').dataset.strokes = String(r.lens.length);
  draw(); sync();
}
function paint(cv, xy, lens, thin) {
  const r = cv.getBoundingClientRect(), dpr = Math.min(3, window.devicePixelRatio || 1);
  const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.width * 218 / 300 * dpr));
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
  const g = cv.getContext('2d'), k = w / 300, css = getComputedStyle(cv);
  g.setTransform(1, 0, 0, 1, 0, 0); g.fillStyle = css.getPropertyValue('--sheet').trim() || '#FFFCF0'; g.fillRect(0, 0, w, h);
  if (!xy) return;
  g.setTransform(k, 0, 0, k, 0, 0); g.lineJoin = 'round'; g.lineCap = 'round';
  g.strokeStyle = css.getPropertyValue('--sheet-ink').trim() || '#100F0F';
  g.lineWidth = thin ? 0.35 / k : Math.max(0.6, 0.3 * k) / k;   // the 0.3 mm pen, never thinner than a hairline on screen
  g.globalAlpha = thin ? 0.75 : 1;   // thumbnails: dense fields stay readable at a tenth of the size
  let o = 0; g.beginPath();
  for (const n of lens) { g.moveTo(xy[o], xy[o + 1]); for (let i = 1; i < n; i++) g.lineTo(xy[o + 2 * i], xy[o + 2 * i + 1]); o += 2 * n; }
  g.stroke();
}
function draw() { if (active) paint($('territory-canvas'), active.rendered?.xy, active.rendered?.lens, false); }

// ---- variations: the next six seeds at these dials ----
function refreshThumbs(reset = false) {
  if (!active) return;
  if (reset) active.thumbFrom = active.seed + 1;
  const gen = ++thumbGen, host = $('tb-thumbs'); host.replaceChildren(); active.thumbs.clear();
  for (let i = 0; i < 6; i++) {
    const sd = active.thumbFrom + i, b = document.createElement('button');
    b.className = 'tb-thumb'; b.dataset.seed = String(sd); b.setAttribute('role', 'listitem'); b.title = `Load seed ${sd}`; b.setAttribute('aria-label', `Load seed ${sd}`);
    const cv = document.createElement('canvas'), cap = document.createElement('span'); cap.textContent = String(sd);
    b.append(cv, cap); host.append(b); active.thumbs.set(sd, cv);
    b.onclick = () => { if (!active || active.keeping) return; remember(); active.seed = sd; sync(); render(); };
    paint(cv, null, null, true);
    getWorker().postMessage({ kind: 'thumb', gen, seed: sd, dials: { ...active.dials } });
  }
  $('tb-thumbs-prev').disabled = active.thumbFrom <= 1; sync();
}
function onThumb(r) {
  if (r.gen !== thumbGen || r.error) return;
  const cv = active.thumbs.get(r.seed); if (cv) paint(cv, r.xy, r.lens, true);
}

// ---- keep: simplify invisibly (0.05 mm at a 0.3 mm pen), round to 0.01 mm ----
function rdp(pts, tol) {
  if (pts.length < 3) return pts;
  const keepMask = new Uint8Array(pts.length); keepMask[0] = keepMask[pts.length - 1] = 1;
  const stack = [[0, pts.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop(); let idx = -1, dmax = tol;
    const [ax, ay] = pts[a], [bx, by] = pts[b], dx = bx - ax, dy = by - ay, L = Math.hypot(dx, dy) || 1e-9;
    for (let i = a + 1; i < b; i++) { const d = Math.abs((pts[i][0] - ax) * dy - (pts[i][1] - ay) * dx) / L; if (d > dmax) { dmax = d; idx = i; } }
    if (idx > 0) { keepMask[idx] = 1; stack.push([a, idx], [idx, b]); }
  }
  return pts.filter((_, i) => keepMask[i]);
}
export function territoryStrokes(xy, lens, tol = 0.05) {
  const out = []; let o = 0;
  for (const n of lens) {
    const pts = []; for (let i = 0; i < n; i++) pts.push([xy[o + 2 * i], xy[o + 2 * i + 1]]); o += 2 * n;
    const s = rdp(pts, tol).map(p => [Math.round(p[0] * 100) / 100, Math.round(p[1] * 100) / 100]);
    if (s.length > 1) out.push(s);
  }
  return out;
}
async function keep() {
  if (!active || $('tb-keep').disabled) return;
  const owner = active, r = owner.rendered; owner.keeping = true; sync(); clearBenchError();
  try {
    const recipe = { seed: owner.seed, ...owner.dials };
    await owner.onKeep({ recipe, strokes: territoryStrokes(r.xy, r.lens), engine: ENGINE });
    if (active === owner) $('tb-kept').textContent = 'Kept as a new layer';
  } catch (error) { if (active === owner) showBenchError(error, keep); }
  finally { owner.keeping = false; if (active === owner) sync(); }
}

function onKey(e) {
  if (!active || $('process-popup').hidden || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.target.matches?.('input[type=text],input[type=number],textarea,select')) return;
  const onRange = e.target.matches?.('input[type=range]');
  if (e.key === 'ArrowLeft' && !onRange) { e.preventDefault(); stepSeed(-1); }
  else if (e.key === 'ArrowRight' && !onRange) { e.preventDefault(); stepSeed(1); }
  else if (e.key === 'r' || e.key === 'R') { e.preventDefault(); surprise(); }
  else if (e.key === 'Backspace') { e.preventDefault(); e.stopImmediatePropagation(); back(); }
  else if (e.key === 'Enter' && !e.target.matches?.('button,summary')) { e.preventDefault(); keep(); }
}
