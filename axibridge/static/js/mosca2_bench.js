// Mosca 2: a page of physical strokes offered to a fresh neural bout.
import { api } from './api.js';
import { openBenchShell, closeBenchShell, clearBenchError, showBenchError } from './bench_host.js';
import { territoryStrokes } from './territory_bench.js';

const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const clone = value => JSON.parse(JSON.stringify(value));
const DEFAULT = { seed: 31, duration_s: 6, gesture_scale: 1, contact_hz: 25, start_x: 150, start_y: 109, heading_deg: 0 };
const LIMITS = { seed:[1,999999], duration_s:[1,12], gesture_scale:[.5,2], contact_hz:[0,100], start_x:[2,298], start_y:[2,216], heading_deg:[-180,180] };
const DIALS = [['seed','Neural seed',1],['duration_s','Duration · seconds',1],['gesture_scale','Gesture size',.05],['contact_hz','Contact · Hz',1],['start_x','Start X · mm',.1],['start_y','Start Y · mm',.1],['heading_deg','Heading · degrees',1]];
const validStrokes = value => (Array.isArray(value) ? value : []).filter(s => Array.isArray(s) && s.length > 1 && s.every(p => Array.isArray(p) && p.length >= 2 && Number.isFinite(+p[0]) && Number.isFinite(+p[1]))).map(s => s.map(p => [+p[0],+p[1]]));
const allStrokes = parts => parts.filter(p => p.visible).flatMap(p => p.strokes);
const unique = prefix => `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`;
let active = null, wired = false, worker = null, workerSerial = 0;

function normalizedPart(raw, kind = 'flowing') {
  return { id: String(raw?.id || unique(kind)), label: String(raw?.label || raw?.title || kind), kind: ['territory','flowing','response'].includes(raw?.kind) ? raw.kind : kind,
    visible: raw?.visible !== false, strokes: validStrokes(raw?.strokes), provenance: String(raw?.provenance || '') };
}
function normalizedSettings(raw) {
  const source = { ...DEFAULT, ...raw }; const result = {};
  for (const [key, [min,max]] of Object.entries(LIMITS)) { const n = Number(source[key]); result[key] = Number.isFinite(n) ? Math.max(min,Math.min(max,key === 'seed' ? Math.round(n) : n)) : DEFAULT[key]; }
  return result;
}
function snapshot(o) { return { parts: clone(o.parts), history: clone(o.history), settings: clone(o.settings), selected: o.selected }; }
function remember(o) { o.undo.push(snapshot(o)); if (o.undo.length > 30) o.undo.shift(); }
function selected(o) { return o.parts.find(p => p.id === o.selected); }
function setStatus(message) { $('m2-status').textContent = message; }
function safe(o) { return active === o && !o.closed; }
function busy(o) { return Boolean(o.job || o.keeping || o.generating); }

function init() {
  if (wired) return; wired = true;
  const panel = document.createElement('div'); panel.id = 'process-mosca2'; panel.hidden = true;
  panel.innerHTML = `<section class="m2-section"><h3>Starting page</h3><label>Provided piece<select id="m2-piece"><option value="">Choose a piece</option></select></label><button id="m2-load-piece">Load piece as page</button><p class="hint" id="m2-source-note"></p></section>
    <section class="m2-section"><h3>Add to page</h3><div class="m2-grid"><label>Territory seed<input id="m2-territory-seed" type="number" min="1" max="999999" step="1" value="22"></label><button id="m2-generate">Generate Territory</button></div><label>Earlier flowing material<select id="m2-material"><option value="">Choose material</option></select></label><button id="m2-add-material">Add original material</button></section>
    <section class="m2-section"><h3>Page parts</h3><div id="m2-parts" role="group" aria-label="Page parts"></div><div class="m2-row"><button id="m2-hide">Hide / show selected</button><button id="m2-remove">Remove</button><button id="m2-undo">Undo edit</button></div><div class="m2-grid"><label>Move X · mm<input id="m2-move-x" type="number" step="0.1" value="0"></label><label>Move Y · mm<input id="m2-move-y" type="number" step="0.1" value="0"></label><label>Rotate · degrees<input id="m2-rotate" type="number" step="1" value="0"></label><label>Scale<input id="m2-scale" type="number" min="0.1" max="5" step="0.05" value="1"></label></div><button id="m2-transform">Apply to selected part</button><p class="hint">Transforms fit inside a 2 mm sheet margin.</p></section>
    <section class="m2-section"><h3>Fresh response</h3><p class="hint">Click or drag the arrow on the page to choose the starting point and direction. Each Run starts a new neural bout; Resume reopens this page, not a saved brain.</p><div class="m2-grid" id="m2-settings"></div><button id="m2-run" class="primary">Run fresh bout</button><button id="m2-cancel" hidden>Cancel run</button><p id="m2-progress" class="hint" aria-live="polite"></p></section>
    <section class="m2-section"><h3>Run history</h3><label>Inspect a run<select id="m2-history"><option value="">Current page</option></select></label><label>View<select id="m2-history-view"><option value="combined">Combined</option><option value="before">Before</option><option value="added">Added only</option></select></label><p id="m2-history-note" class="hint"></p><div id="m2-history-detail"></div><button id="m2-undo-step">Undo last response</button></section>`;
  $('bench-controls').append(panel);
  const stage = document.querySelector('#process-popup .preview-stage');
  const svg = document.createElementNS(NS,'svg'); svg.id = 'mosca2-stage'; svg.setAttribute('viewBox','0 0 300 218'); svg.setAttribute('role','img'); svg.setAttribute('aria-label','Mosca 2 page and start arrow'); svg.hidden = true; stage.append(svg);
  const bar = document.createElement('div'); bar.id = 'mosca2-actions'; bar.hidden = true;
  bar.innerHTML = `<span id="m2-status" class="hint" aria-live="polite"></span><span id="m2-kept" class="hint" aria-live="polite"></span><button id="m2-svg">Download current page SVG</button><button id="m2-keep" class="primary">Keep current page</button>`;
  document.querySelector('.bench-main').append(bar);
  for (const [key,label,step] of DIALS) { const [min,max] = LIMITS[key]; const wrap = document.createElement('label'); wrap.textContent = label; const input = document.createElement('input'); input.id = `m2-${key}`; input.type = 'number'; input.min = min; input.max = max; input.step = step; wrap.append(input); $('m2-settings').append(wrap); input.addEventListener('change', () => changeSetting(key,input)); }
  $('m2-load-piece').onclick = loadPiece; $('m2-generate').onclick = generateTerritory; $('m2-add-material').onclick = addMaterial;
  $('m2-hide').onclick = toggleSelected; $('m2-remove').onclick = removeSelected; $('m2-undo').onclick = undoEdit; $('m2-transform').onclick = transformSelected;
  $('m2-run').onclick = run; $('m2-cancel').onclick = cancelRun; $('m2-keep').onclick = keep; $('m2-svg').onclick = downloadSvg; $('m2-undo-step').onclick = undoStep;
  $('m2-history').onchange = () => { if (active) { active.inspect = $('m2-history').value; sync(); render(); } };
  $('m2-history-view').onchange = render;
  svg.addEventListener('pointerdown', pointerDown);
  svg.addEventListener('pointermove', pointerMove);
  svg.addEventListener('pointerup', pointerUp);
  svg.addEventListener('pointercancel', pointerUp);
  document.addEventListener('bench-project-reset', () => closeMosca2Bench(false));
}

export function openMosca2Bench({ mod, params, contextKey, onKeep, onClose }) {
  init(); closeMosca2Bench(false);
  const raw = params || {}; const o = active = { mod, onKeep, onClose, contextKey, parts:(raw.parts || []).map(p => normalizedPart(p,p.kind)), history:Array.isArray(raw.history) ? clone(raw.history).slice(-12) : [],
    settings:normalizedSettings(raw.settings), selected:null, undo:[], inspect:'', materials:[], pieces:[], job:null, keeping:false, generating:false, closed:false, listing:0, territoryToken:0, pointer:null };
  o.selected = o.parts.at(-1)?.id || null;
  const popup = $('process-popup'); popup.classList.remove('territory-bench','mosca-bench','magnetic-field','second-reading','watch-only','linedraw'); popup.classList.add('mosca2-bench');
  for (const id of ['process-params','process-second-reading','process-generic-save-gallery','process-play','process-prev','process-next','process-scrub','process-readout','process-telemetry-row','process-create','process-reroll','process-reference','process-canvas','process-status']) $(id)?.setAttribute('hidden','');
  for (const id of ['process-mosca2','mosca2-stage','mosca2-actions']) $(id).hidden = false;
  $('process-title').textContent = 'Mosca 2 — page and response'; $('m2-kept').textContent = '';
  openBenchShell({ close:() => closeMosca2Bench(), origin:contextKey?.startsWith('layer:') ? 'Resume a kept page · new Run starts a fresh brain' : 'Compose a page · new Run starts a fresh brain' });
  $('bench-controls').scrollTop = 0; sync(); render(); loadLibrary(o);
}
export function closeMosca2Bench(notify = true) {
  if (!active) return;
  const o = active; o.closed = true; active = null; clearTimeout(o.pollTimer); o.abort?.abort();
  if (o.job?.id) api.del(`/api/mosca2/jobs/${encodeURIComponent(o.job.id)}`).catch(() => {});
  for (const id of ['process-mosca2','mosca2-stage','mosca2-actions']) $(id).hidden = true;
  for (const id of ['process-canvas','process-status']) $(id)?.removeAttribute('hidden');
  $('process-popup').classList.remove('mosca2-bench');
  if (notify) { closeBenchShell(); o.onClose?.(); }
}

async function loadLibrary(o) {
  const token = ++o.listing;
  try {
    const [status, library] = await Promise.all([api.get('/api/mosca2/status'),api.get('/api/mosca2/materials')]);
    if (!safe(o) || token !== o.listing) return;
    o.available = Boolean(status.available); o.reason = status.reason || '';
    o.materials = Array.isArray(library.materials) ? library.materials : [];
    o.pieces = Array.isArray(library.pieces) ? library.pieces.slice(0,6) : [];
    const pieceSelect = $('m2-piece'); pieceSelect.replaceChildren(new Option('Choose a piece',''));
    for (const piece of o.pieces) pieceSelect.add(new Option(piece.title || piece.id, piece.id));
    const materialSelect = $('m2-material'); materialSelect.replaceChildren(new Option('Choose material',''));
    for (const material of o.materials) materialSelect.add(new Option(material.label || material.id,material.id));
    $('m2-source-note').textContent = o.available ? 'Provided pieces use original material and Territory drawings.' : `Brain unavailable: ${o.reason || 'backend unavailable'}`;
    if (!o.parts.length && o.pieces.length && !o.contextKey?.startsWith('layer:')) { pieceSelect.value = o.pieces[0].id; loadPiece(false); }
    sync();
  } catch (error) { if (safe(o)) { showBenchError(error, () => loadLibrary(o)); setStatus('Library unavailable'); } }
}
function materialPart(o,id) { const raw = o.materials.find(m => m.id === id); return raw ? normalizedPart({ ...raw, id:unique('flowing'), kind:'flowing' },'flowing') : null; }
function loadPiece(recordUndo = true) {
  const o = active; if (!o || busy(o)) return;
  const piece = o.pieces.find(p => p.id === $('m2-piece').value); if (!piece) return;
  const parts = (piece.parts || []).map(item => typeof item === 'string' ? materialPart(o,item) : item?.strokes ? normalizedPart({...item,id:unique(item.kind || 'flowing')},item.kind || 'flowing') : materialPart(o,item?.id)).filter(Boolean);
  if (!parts.length) { showBenchError(new Error('This piece has no usable strokes.')); return; }
  if (recordUndo) remember(o); o.history = []; o.parts = parts; o.selected = parts.at(-1).id; o.inspect = ''; $('m2-history').value = ''; clearBenchError(); sync(); render(); setStatus(`${piece.title || 'Piece'} loaded · ${allStrokes(parts).length} strokes`);
}
function addMaterial() { const o=active; if (!o || busy(o)) return; const part=materialPart(o,$('m2-material').value); if (!part) return; if (o.parts.length >= 32) return showBenchError(new Error('Page holds at most 32 parts. Remove one before adding.')); remember(o); o.parts.push(part); o.selected=part.id; o.inspect=''; $('m2-history').value=''; sync(); render(); }
function workerForTerritory() { if (!worker) worker = new Worker(new URL('./territory/worker.js',import.meta.url),{type:'module'}); return worker; }
function generateTerritory() {
  const o=active; if (!o || busy(o)) return; if (o.parts.length >= 32) return showBenchError(new Error('Page holds at most 32 parts.'));
  const seed=Number($('m2-territory-seed').value); if (!Number.isInteger(seed)||seed<1||seed>999999) { $('m2-territory-seed').reportValidity(); return; }
  o.generating=true; const id=++workerSerial; o.territoryToken=id; setStatus('Generating Territory…'); sync();
  const w=workerForTerritory();
  w.onmessage=e => { const r=e.data; if (!safe(o)||r.kind!=='sheet'||r.id!==id||o.territoryToken!==id) return; o.generating=false;
    if (r.error) { showBenchError(new Error(r.error)); sync(); return; }
    const strokes=territoryStrokes(r.xy,r.lens); remember(o); const part=normalizedPart({ id:unique('territory'), label:`Territory · seed ${seed}`, kind:'territory', visible:true, strokes, provenance:`Territory meander-v10 · seed ${seed}` },'territory');
    o.parts.push(part); o.selected=part.id; o.inspect=''; $('m2-history').value=''; sync(); render(); setStatus(`Territory added · ${strokes.length} strokes`);
  };
  w.onerror=e => { if (safe(o)) { o.generating=false; showBenchError(new Error(e.message || 'Territory worker failed')); sync(); } };
  w.postMessage({kind:'sheet',id,seed,dials:{ complexity:.5,drift:.6,band:1,chaos:.5,accents:.5,bridges:.5,history:.6,density:0,continue:.5,cover:.45,planes:.15,mutate:1,slash:.5,surprise:.5,ink:40 }});
}
function editPart(mutator) { const o=active,p=o&&selected(o); if (!p||busy(o)) return; remember(o); mutator(p,o); o.inspect=''; $('m2-history').value=''; sync(); render(); }
function toggleSelected() { editPart(p => {p.visible=!p.visible;}); }
function removeSelected() { editPart((p,o) => {o.parts=o.parts.filter(q=>q!==p); o.selected=o.parts.at(-1)?.id||null;}); }
function undoEdit() { const o=active; if (!o||busy(o)||!o.undo.length) return; const s=o.undo.pop(); o.parts=s.parts; o.history=s.history; o.settings=s.settings; o.selected=s.selected; o.inspect=''; $('m2-history').value=''; sync(); render(); }
function bounds(strokes) { const b={minX:Infinity,maxX:-Infinity,minY:Infinity,maxY:-Infinity}; for(const line of strokes)for(const [x,y] of line){b.minX=Math.min(b.minX,x);b.maxX=Math.max(b.maxX,x);b.minY=Math.min(b.minY,y);b.maxY=Math.max(b.maxY,y);}return b; }
function transformSelected() {
  const o=active,p=o&&selected(o); if (!p||busy(o)||!p.strokes.length) return;
  const dx=+$('m2-move-x').value,dy=+$('m2-move-y').value,deg=+$('m2-rotate').value,scale=+$('m2-scale').value;
  if (![dx,dy,deg,scale].every(Number.isFinite)||scale<=0||scale>5) return showBenchError(new Error('Use finite movement, rotation and scale values; scale must be 0–5.'));
  const box=bounds(p.strokes),cx=(box.minX+box.maxX)/2,cy=(box.minY+box.maxY)/2,a=deg*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
  let transformed=p.strokes.map(line=>line.map(([x,y])=>{const u=(x-cx)*scale,v=(y-cy)*scale;return [cx+dx+u*c-v*s,cy+dy+u*s+v*c];}));
  const b=bounds(transformed),width=b.maxX-b.minX,height=b.maxY-b.minY;
  if (width>296||height>214) return showBenchError(new Error('This transform cannot fit inside the 2 mm page margin.'));
  const shiftX=Math.max(2-b.minX,Math.min(298-b.maxX,0)),shiftY=Math.max(2-b.minY,Math.min(216-b.maxY,0));
  transformed=transformed.map(line=>line.map(([x,y])=>[+((x+shiftX).toFixed(3)),+((y+shiftY).toFixed(3))]));
  editPart(part=>{part.strokes=transformed;});
  for (const key of ['move-x','move-y','rotate']) $(`m2-${key}`).value='0'; $('m2-scale').value='1'; clearBenchError();
}
function changeSetting(key,input) { const o=active;if(!o||busy(o))return;const v=Number(input.value),[min,max]=LIMITS[key];if(!Number.isFinite(v)||v<min||v>max||key==='seed'&&!Number.isInteger(v)){input.reportValidity();input.value=String(o.settings[key]);return;}remember(o);o.settings[key]=v;sync();render(); }
function point(evt) { const svg=$('mosca2-stage'),pt=svg.createSVGPoint();pt.x=evt.clientX;pt.y=evt.clientY;const p=pt.matrixTransform(svg.getScreenCTM().inverse());return [Math.max(2,Math.min(298,p.x)),Math.max(2,Math.min(216,p.y))]; }
function pointerDown(e) { const o=active;if(!o||busy(o)||o.inspect)return;const [x,y]=point(e);remember(o);o.settings.start_x=+x.toFixed(1);o.settings.start_y=+y.toFixed(1);o.pointer={id:e.pointerId,x,y};e.currentTarget.setPointerCapture(e.pointerId);sync();render(); }
function pointerMove(e) { const o=active;if(!o?.pointer||o.pointer.id!==e.pointerId)return;const [x,y]=point(e),dx=x-o.pointer.x,dy=y-o.pointer.y;if(Math.hypot(dx,dy)>1){o.settings.heading_deg=+((Math.atan2(dy,dx)*180/Math.PI).toFixed(1));sync();render();} }
function pointerUp(e) { const o=active;if(o?.pointer?.id===e.pointerId)o.pointer=null; }
function currentParams(o) { return { engine:'mosca2-v1',parts:clone(o.parts),history:clone(o.history),settings:clone(o.settings) }; }
function sync() {
  const o=active;if(!o)return;const lock=busy(o);
  for(const [key] of DIALS) $(`m2-${key}`).value=String(o.settings[key]);
  const list=$('m2-parts');list.replaceChildren();
  for(const p of o.parts){const row=document.createElement('button');row.type='button';row.className='m2-part';row.setAttribute('aria-pressed',String(o.selected===p.id));row.disabled=lock;row.textContent=`${p.visible?'●':'○'} ${p.label} · ${p.strokes.length} strokes`;row.onclick=()=>{o.selected=p.id;sync();render();};list.append(row);}
  if(!o.parts.length)list.textContent='The page is empty.';
  const hist=$('m2-history');const desired=o.inspect;hist.replaceChildren(new Option('Current page',''));
  for(const h of o.history)hist.add(new Option(h.label||h.id,h.id));hist.value=desired;
  const h=o.history.find(item=>item.id===desired);renderHistoryDetail(h);
  $('m2-undo-step').disabled=lock||!o.history.length;
  $('m2-cancel').hidden=!o.job;$('m2-cancel').disabled=!o.job||Boolean(o.job.cancelling||o.job.cancelRequested);
  $('m2-run').disabled=lock||Boolean(o.inspect)||!o.available||!allStrokes(o.parts).length||o.history.length>=12||o.parts.length>=32;
  $('m2-keep').disabled=lock;$('m2-svg').disabled=lock||!allStrokes(o.parts).length;
  $('m2-hide').disabled=lock||!selected(o);$('m2-remove').disabled=lock||!selected(o);$('m2-transform').disabled=lock||!selected(o);$('m2-undo').disabled=lock||!o.undo.length;
  $('m2-load-piece').disabled=lock;$('m2-add-material').disabled=lock;$('m2-generate').disabled=lock;
  for(const control of $('process-mosca2').querySelectorAll('button,input,select')) if(control.id!=='m2-cancel') control.disabled ||= lock;
  if(!lock) { for(const control of $('process-mosca2').querySelectorAll('input,select')) control.disabled=false; $('m2-history').disabled=false; $('m2-history-view').disabled=false; }
  if(!lock&&(o.history.length>=12||o.parts.length>=32)) $('m2-progress').textContent=o.history.length>=12?'History holds 12 runs. Keep this page or undo the last run before starting another.':'Page holds 32 parts. Remove a part before starting another run.';
  if(!o.available&&o.reason)setStatus(`Brain unavailable · ${o.reason}`);
}
function renderHistoryDetail(h) {
  const note=$('m2-history-note'), host=$('m2-history-detail');
  if(!h){note.textContent='History inspection does not change the kept page.';host.replaceChildren();host.dataset.historyId='';return;}
  const counts={drawing:0,lifted:0,outside:0};
  for(const event of h.events||[]) if(Object.hasOwn(counts,event.kind)) counts[event.kind]++;
  note.textContent=`${h.summary||'Recorded run'} · ${counts.drawing} drawing, ${counts.lifted} lifted, ${counts.outside} outside transitions. Return to Current page to run.`;
  if(host.dataset.historyId===h.id)return;
  host.dataset.historyId=h.id;host.replaceChildren();
  const events=document.createElement('details'),summary=document.createElement('summary');summary.textContent=`Pen events (${(h.events||[]).length})`;events.append(summary);
  const list=document.createElement('ol');list.className='m2-event-list';
  for(const event of h.events||[]){const item=document.createElement('li');item.textContent=`${(Number(event.t_ms)/1000).toFixed(2)} s · ${event.kind}${event.detail?' · '+event.detail:''}`;list.append(item);}events.append(list);host.append(events);
  if(h.provenance){const meta=document.createElement('details'),title=document.createElement('summary'),body=document.createElement('pre');title.textContent='Run provenance';body.textContent=h.provenance;meta.append(title,body);host.append(meta);}
}
function svgPath(line){return line.map((p,i)=>`${i?'L':'M'}${p[0]} ${p[1]}`).join(' ');}
function render() {
  const o=active;if(!o)return;const svg=$('mosca2-stage');svg.replaceChildren();let parts=o.parts;
  const h=o.history.find(item=>item.id===o.inspect);
  if(h){const view=$('m2-history-view').value,lines=view==='before'?h.before:view==='added'?h.added:[...h.before,...h.added];parts=[{kind:'flowing',visible:true,strokes:validStrokes(lines)}];}
  for(const part of parts.filter(p=>p.visible!==false)){const g=document.createElementNS(NS,'g');g.setAttribute('class',`m2-ink m2-${part.kind||'flowing'}${!h&&part.id===o.selected?' selected':''}`);for(const line of validStrokes(part.strokes)){const path=document.createElementNS(NS,'path');path.setAttribute('d',svgPath(line));g.append(path);}svg.append(g);}
  if(!h&&o.job&&o.preview?.length){const g=document.createElementNS(NS,'g');g.setAttribute('class','m2-preview');for(const line of o.preview){const path=document.createElementNS(NS,'path');path.setAttribute('d',svgPath(line));g.append(path);}svg.append(g);}
  if(!h){const {start_x:x,start_y:y,heading_deg:heading}=o.settings,rad=heading*Math.PI/180,ex=x+11*Math.cos(rad),ey=y+11*Math.sin(rad),arrow=document.createElementNS(NS,'g');arrow.setAttribute('class','m2-arrow');const stem=document.createElementNS(NS,'path');stem.setAttribute('d',`M${x} ${y} L${ex} ${ey}`);const tip=document.createElementNS(NS,'path');tip.setAttribute('d',`M${ex-3*Math.cos(rad-.5)} ${ey-3*Math.sin(rad-.5)} L${ex} ${ey} L${ex-3*Math.cos(rad+.5)} ${ey-3*Math.sin(rad+.5)}`);const dot=document.createElementNS(NS,'circle');dot.setAttribute('cx',x);dot.setAttribute('cy',y);dot.setAttribute('r','1.5');arrow.append(stem,tip,dot);svg.append(arrow);}
  svg.dataset.strokes=String(allStrokes(o.parts).length);
}
async function run() {
  const o=active;if(!o||o.inspect||$('m2-run').disabled)return;clearBenchError();const before=clone(o.parts),settings=clone(o.settings),strokes=clone(allStrokes(before));
  const runToken=unique('run');o.job={token:runToken,id:null,before,settings};o.preview=[];setStatus('Starting fresh neural bout…');$('m2-progress').textContent='';sync();
  try{const result=await api.post('/api/mosca2/jobs',{strokes,settings});if(!safe(o)||o.job?.token!==runToken){if(result?.id)api.del(`/api/mosca2/jobs/${encodeURIComponent(result.id)}`).catch(()=>{});return;}o.job.id=result.id;if(o.job.cancelRequested)cancelRun();else poll(o,runToken);}
  catch(error){if(safe(o)&&o.job?.token===runToken){o.job=null;showBenchError(error,run);sync();setStatus('Run could not start');}}
}
async function poll(o,token) {
  if(!safe(o)||o.job?.token!==token||!o.job.id)return;
  try{const result=await api.get(`/api/mosca2/jobs/${encodeURIComponent(o.job.id)}`);if(!safe(o)||o.job?.token!==token||o.job.cancelling)return;
    o.pollFailures=0;clearBenchError();const state=result.status;$('m2-progress').textContent=`${state} · ${Math.round((Number(result.progress)||0)*100)}%${result.state?' · '+result.state:''}`;
    if(state==='running'){o.preview=validStrokes(result.preview);render();o.pollTimer=setTimeout(()=>poll(o,token),750);return;}
    if(state==='completed'){completeRun(o,result);return;}
    o.job=null;o.preview=[];render();sync();if(state==='failed')showBenchError(new Error(result.error||'Neural run failed'),run);setStatus(state==='cancelled'?'Run cancelled':'Run failed');
  }catch(error){if(safe(o)&&o.job?.token===token){o.pollFailures=(o.pollFailures||0)+1;const delay=Math.min(5000,750*2**Math.min(3,o.pollFailures));$('m2-progress').textContent=`Status connection lost · retrying in ${(delay/1000).toFixed(1)} s`;setStatus('Run still owned · status retrying');showBenchError(error);o.pollTimer=setTimeout(()=>poll(o,token),delay);sync();}}
}
function completeRun(o,result) {
  const job=o.job;const output=result.result||{},strokes=validStrokes(output.strokes),provenance=String(output.provenance||'');let partProvenance='Mosca 2 · fresh neural bout';try{const meta=JSON.parse(provenance);if(meta.input_sha256)partProvenance+=` · input SHA256 ${String(meta.input_sha256).slice(0,64)}`;}catch{/* Keep raw provenance only in history. */}const added=strokes.length?[normalizedPart({id:unique('response'),label:`Response ${o.history.length+1}`,kind:'response',visible:true,strokes,provenance:partProvenance},'response')]:[];
  const summary=strokes.length?`${strokes.length} response strokes`:'No response strokes';
  remember(o);o.history.push({id:unique('history'),label:`Run ${o.history.length+1} · ${summary}`,before:clone(allStrokes(job.before)),added:clone(strokes),settings:job.settings,summary,provenance,events:Array.isArray(output.events)?clone(output.events):[]});
  o.parts.push(...added);if(added.length)o.selected=added[0].id;o.job=null;o.preview=[];o.inspect='';$('m2-history').value='';$('m2-progress').textContent=summary;setStatus(summary);sync();render();
}
async function cancelRun() {
  const o=active,job=o?.job;if(!job||job.cancelling)return;
  if(!job.id){job.cancelRequested=true;setStatus('Cancelling when the job starts…');sync();return;}
  clearTimeout(o.pollTimer);job.cancelling=true;setStatus('Cancelling run…');sync();
  try{await api.del(`/api/mosca2/jobs/${encodeURIComponent(job.id)}`);if(!safe(o)||o.job!==job)return;o.job=null;o.preview=[];render();sync();setStatus('Run cancelled');}
  catch(error){if(!safe(o)||o.job!==job)return;job.cancelling=false;job.cancelRequested=false;showBenchError(error);setStatus('Cancel failed · checking run status');sync();o.pollTimer=setTimeout(()=>poll(o,job.token),750);}
}
function undoStep(){const o=active;if(!o||busy(o)||!o.history.length)return;const h=o.history.at(-1);if(h.added.length){const index=o.parts.findLastIndex(p=>p.kind==='response'&&JSON.stringify(p.strokes)===JSON.stringify(h.added));if(index<0)return showBenchError(new Error('The last response was edited or removed; use Undo edit to restore it before undoing the run.'));remember(o);o.parts.splice(index,1);}else remember(o);o.history.pop();o.selected=o.parts.at(-1)?.id||null;o.inspect='';$('m2-history').value='';sync();render();setStatus('Last response removed');}
async function keep(){const o=active;if(!o||busy(o))return;o.keeping=true;sync();clearBenchError();try{await o.onKeep(currentParams(o));if(safe(o))$('m2-kept').textContent='Kept as a layer';}catch(error){if(safe(o))showBenchError(error,keep);}finally{if(safe(o)){o.keeping=false;sync();}}}
function downloadSvg(){const o=active;if(!o||busy(o))return;const strokes=allStrokes(o.parts);const paths=strokes.map(line=>`<path d="${svgPath(line)}"/>`).join('');const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="300mm" height="218mm" viewBox="0 0 300 218"><g fill="none" stroke="#100F0F" stroke-width="0.25" stroke-linecap="round" stroke-linejoin="round">${paths}</g></svg>`;const url=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'}));const a=document.createElement('a');a.href=url;a.download='mosca2-page.svg';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
