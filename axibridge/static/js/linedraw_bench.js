// Local drafts only. Accepted results enter the ordinary source/layer pipeline.
import { api } from './api.js';
import { S } from './main.js';
import { renderForm } from './forms.js';
import { FaceRegions } from './linedraw_regions.js';
import { openBenchShell, closeBenchShell, showBenchError, clearBenchError, benchProjectEpoch } from './bench_host.js';
const $ = id => document.getElementById(id);
const copy = v => JSON.parse(JSON.stringify(v));
const NS = 'http://www.w3.org/2000/svg';
let active = null;
let regions = null;
let panel = null;
let workspace = null;
let serial = 0;
let hiddenBefore = [];

function init() {
  if (panel) return;
  panel = document.createElement('div'); panel.id = 'linedraw-panel'; panel.hidden = true;
  panel.innerHTML = `
    <label for="linedraw-style">Drawing style</label><select id="linedraw-style">
      <option value="contours">Contours</option><option value="light_form">Light form</option>
      <option value="shadow_shapes">Shadow shapes</option><option value="face_form">Face + form</option>
    </select>
    <div id="linedraw-form" class="form"></div>
    <div class="linedraw-actions"><button id="linedraw-analyze">Analyze / redetect faces</button><button id="linedraw-redraw">Redraw</button><button id="linedraw-cancel-job">Cancel analysis</button></div>
    <p id="linedraw-readiness" class="hint"></p>
    <details open><summary>Face regions</summary>
      <p class="hint">Drag an ellipse to move it; drag its corner dot to resize. These regions request detail, not landmark drawing strokes.</p>
      <label>Selected face<select id="linedraw-face-select"></select></label>
      <div class="linedraw-actions"><button id="linedraw-add-face">Add face region</button><button id="linedraw-delete-face">Delete face region</button></div>
      <div class="linedraw-face-fields">
        ${[['cx','Face center X (%)'],['cy','Face center Y (%)'],['rx','Face radius X (%)'],['ry','Face radius Y (%)']].map(([key,label]) => `<label>${label}<input id="linedraw-${key}" type="number" min="${key[0]==='r'?.5:0}" max="${key[0]==='r'?50:100}" step=".1"></label>`).join('')}
      </div><label><input id="linedraw-enabled" type="checkbox">Include selected face</label>
    </details>
    <p id="linedraw-message" class="hint" aria-live="polite"></p>
    <div class="linedraw-actions"><button id="linedraw-keep" class="primary">Keep as layer</button><button id="linedraw-apply">Apply to layer</button><button id="linedraw-close">Cancel draft</button></div>`;
  $('bench-controls').append(panel);
  workspace = document.createElement('div'); workspace.className = 'linedraw-workspace'; workspace.hidden = true;
  workspace.innerHTML = `<figure><figcaption>Source · face regions</figcaption><svg id="linedraw-source" aria-label="Face regions on source image"></svg></figure><figure><figcaption>Drawing · actual pen paths</figcaption><svg id="linedraw-drawing" aria-label="Linedraw pen paths"></svg></figure>`;
  $('process-canvas').closest('.process-body').append(workspace);
  regions = new FaceRegions($('linedraw-source'), faces => {
    if (!active) return; active.params.faces = faces; changed(); updateFaces();
  }, i => { if (active) { active.selected = i; updateFaces(); } });
  $('linedraw-style').onchange = () => { active.params.style = $('linedraw-style').value; changed(); };
  $('linedraw-face-select').onchange = () => { active.selected = Number($('linedraw-face-select').value); updateFaces(); };
  $('linedraw-add-face').onclick = () => {
    if (!active || active.params.faces.length >= 32) return;
    active.params.faces.push({ id: crypto.randomUUID(), cx:.5, cy:.3, rx:.1, ry:.15, enabled:true, origin:'manual' });
    active.selected = active.params.faces.length - 1; changed(); updateFaces();
  };
  $('linedraw-delete-face').onclick = () => {
    if (!active || active.selected < 0) return;
    active.params.faces.splice(active.selected,1); active.selected = Math.min(active.selected,active.params.faces.length-1); changed(); updateFaces();
  };
  for (const key of ['cx','cy','rx','ry']) $('linedraw-'+key).onchange = () => {
    const input = $('linedraw-'+key), f = active?.params.faces[active.selected];
    if (!f || !input.reportValidity() || input.value==='') { updateFaces(); return; }
    f[key] = Number(input.value)/100; f.origin = 'manual'; changed(); updateFaces();
  };
  $('linedraw-enabled').onchange = () => {
    const f = active?.params.faces[active.selected]; if (!f) return;
    f.enabled = $('linedraw-enabled').checked; changed(); updateFaces();
  };
  $('linedraw-analyze').onclick = () => run('analyze');
  $('linedraw-redraw').onclick = () => run('render');
  $('linedraw-cancel-job').onclick = cancelJob;
  $('linedraw-close').onclick = () => closeLinedrawBench();
  $('linedraw-keep').onclick = () => keep(false);
  $('linedraw-apply').onclick = () => keep(true);
}
function key() { return JSON.stringify(active?.params); }
function buttons() {
  if (!active) return;
  const busy = active.busy || active.keeping;
  $('linedraw-keep').disabled = busy || active.rendered !== key();
  $('linedraw-apply').disabled = busy || active.rendered !== key();
  $('linedraw-apply').hidden = !active.onApply;
  $('linedraw-analyze').disabled = busy || !active.params.image || !active.ready;
  $('linedraw-redraw').disabled = busy || !active.params.image || !active.ready;
  $('linedraw-cancel-job').disabled = !active.busy;
  $('linedraw-add-face').disabled = busy || active.params.faces.length >= 32;
  $('linedraw-delete-face').disabled = busy || active.selected < 0;
  regions.disabled = busy;
  panel.querySelectorAll('input,select').forEach(el => { el.disabled = !!active.keeping; });
  for (const name of ['cx','cy','rx','ry','enabled']) $('linedraw-'+name).disabled = busy || active.selected < 0;
}
function changed() {
  if (!active) return;
  if (active.busy) cancelJob();
  active.rendered = null; $('linedraw-message').textContent = 'Settings changed. Redraw to update the pen paths.'; buttons();
}
function imageChanged() {
  active.params.faces = []; active.params.image_identity = ''; active.params.model_identity = ''; active.selected = -1;
  regions.setImage(active.params.image ? `/api/assets/${encodeURIComponent(active.params.image)}?frame=${active.params.frame || 0}` : '');
  updateFaces(); changed();
}
function updateFaces() {
  if (!active) return;
  const select = $('linedraw-face-select'); select.replaceChildren();
  active.params.faces.forEach((f,i) => { const o = document.createElement('option'); o.value=String(i); o.textContent=`Face ${i+1} · ${f.origin}`; select.append(o); });
  select.value = String(active.selected);
  const face = active.params.faces[active.selected];
  for (const key of ['cx','cy','rx','ry']) $('linedraw-'+key).value = face ? String(Math.round(face[key]*1000)/10) : '';
  $('linedraw-enabled').checked = !!face?.enabled;
  regions.setFaces(active.params.faces,active.selected); buttons();
}
function cancelJob() {
  if (!active) return;
  const identity = active.job; active.job = null; active.busy = false; active.token = ++serial;
  if (identity) api.del(`/api/linedraw/jobs/${identity}`).catch(() => {});
  $('linedraw-message').textContent = 'Analysis cancelled. Previous drawing retained.'; buttons();
}
async function run(operation) {
  if (!active || active.keeping) return;
  cancelJob(); clearBenchError();
  const draft=active, token=++serial; draft.token=token; draft.busy=true; draft.rendered=null; buttons();
  const valid = () => active===draft && draft.token===token && draft.epoch===benchProjectEpoch();
  try {
    let job=await api.post('/api/linedraw/jobs',{ revision:String(token),params:copy(draft.params),operation });
    if (!valid()) { await api.del(`/api/linedraw/jobs/${job.id}`); return; }
    draft.job=job.id;
    while (['queued','running'].includes(job.state)) {
      $('linedraw-message').textContent = `${job.message || 'Waiting'} · ${Math.round(job.progress*100)}%`;
      await new Promise(resolve => setTimeout(resolve,250));
      if (!valid()) return;
      job=await api.get(`/api/linedraw/jobs/${job.id}`);
      if (!valid()) return;
    }
    if (job.state==='failed') throw new Error(job.error);
    if (job.state!=='complete') return;
    draft.params=copy(job.result.params); draft.selected=draft.params.faces.length?0:-1;
    draft.rendered=key(); draft.job=null;
    renderControls(); updateFaces(); draw(job.result.preview);
    $('linedraw-message').textContent=['Drawing ready.',...job.result.warnings].join(' ');
  } catch (error) { if (valid()) showBenchError(error,() => run(operation)); }
  finally { if (valid()) { draft.busy=false; buttons(); } }
}
function draw(preview) {
  const svg=$('linedraw-drawing'); svg.replaceChildren();
  const width = preview.width || 1, height = preview.height || 1;
  const portrait = S.state?.project?.view === 'portrait';
  svg.setAttribute('viewBox', `0 0 ${portrait ? height : width} ${portrait ? width : height}`);
  const group = document.createElementNS(NS, 'g');
  if (portrait) group.setAttribute('transform', `translate(${height} 0) rotate(90)`);
  svg.append(group);
  const path=document.createElementNS(NS,'path');
  path.setAttribute('d',preview.lines.map(line => line.map(([x,y],i) => `${i?'L':'M'}${x},${y}`).join(' ')).join(' '));
  path.setAttribute('fill','none'); path.setAttribute('stroke','currentColor'); path.setAttribute('stroke-width','.2'); group.append(path);
}
function renderControls() {
  const schema=copy(active.mod.schema); delete schema.properties.style;
  renderForm($('linedraw-form'),schema,active.params,key => {
    if (key==='image' || key==='frame') imageChanged(); else changed();
  });
  $('linedraw-style').value=active.params.style;
}
async function keep(apply) {
  if (!active || active.busy || active.keeping || active.rendered!==key()) return;
  const draft=active; draft.keeping=true; buttons(); clearBenchError();
  try {
    await (apply ? draft.onApply : draft.onCreate)(copy(draft.params));
    if (active===draft) $('linedraw-message').textContent=apply?'Layer updated.':'Kept as a layer.';
  } catch(error) { if (active===draft) showBenchError(error); }
  finally { if (active===draft) { draft.keeping=false; buttons(); } }
}
export async function openLinedrawBench(entry) {
  closeLinedrawBench(false); init();
  const params={};
  for (const [k,spec] of Object.entries(entry.mod.schema.properties)) if ('default' in spec) params[k]=copy(spec.default);
  Object.assign(params,copy(entry.params)); params.faces ||= [];
  active={...entry,params,selected:params.faces.length?0:-1,epoch:benchProjectEpoch(),job:null,busy:false,keeping:false,ready:false,rendered:null,token:++serial};
  $('process-title').textContent='Linedraw v3';
  hiddenBefore=[...$('bench-controls').children,$('process-canvas').closest('.preview-stage'),...document.querySelectorAll('#process-popup .bench-transport,#process-popup .process-generic-actions,#process-popup .second-only'),$('process-telemetry-row')]
    .filter(el => el && el!==panel).map(el => [el,el.hidden]);
  hiddenBefore.forEach(([el]) => { el.hidden=true; });
  panel.hidden=false; workspace.hidden=false; $('process-popup').classList.add('linedraw');
  openBenchShell({close:closeLinedrawBench,cancelGesture:() => regions.cancel(),origin:'Image → local drawing → layer'});
  renderControls(); regions.setImage(params.image ? `/api/assets/${encodeURIComponent(params.image)}?frame=${params.frame || 0}` : ''); updateFaces();
  $('linedraw-drawing').replaceChildren(); $('linedraw-message').textContent='Analyze to find faces, or add regions and Redraw.';
  const draft=active;
  try {
    const readiness=await api.get('/api/linedraw/status');
    if (active!==draft) return;
    draft.ready=readiness.available; $('linedraw-readiness').textContent=readiness.detail;
    if (!readiness.faces) $('linedraw-readiness').textContent+=' Automatic faces unavailable; manual regions remain available.';
    buttons();
  } catch(error) { if (active===draft) showBenchError(error); }
}
export function closeLinedrawBench(notify=true) {
  if (!active) return;
  // A commit already dispatched is atomic; keep the draft present until it settles.
  if (active.keeping) return;
  const callback=active.onClose; cancelJob(); regions.cancel(); active=null;
  panel.hidden=true; workspace.hidden=true; hiddenBefore.forEach(([el,hidden]) => { el.hidden=hidden; }); hiddenBefore=[];
  $('process-popup').classList.remove('linedraw'); closeBenchShell();
  if (notify) callback?.();
}
