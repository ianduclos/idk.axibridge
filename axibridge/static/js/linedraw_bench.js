// Local drafts only. Accepted results enter the ordinary source/layer pipeline.
import { api } from './api.js';
import { S } from './main.js';
import { renderForm } from './forms.js';
import { FaceRegions } from './linedraw_regions.js';
import { DetailRegions } from './linedraw_detail_regions.js';
import { beginDrawingUpdate } from './drawing_status.js';
import { openBenchShell, closeBenchShell, showBenchError, clearBenchError, benchProjectEpoch } from './bench_host.js';
const $ = id => document.getElementById(id);
const copy = v => JSON.parse(JSON.stringify(v));
const NS = 'http://www.w3.org/2000/svg';
let active = null;
let regions = null;
let detailEditor = null;
let panel = null;
let workspace = null;
let serial = 0;
let hiddenBefore = [];
let redrawTimer = null;
const square = [[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9]];
const wholeFrame = [[0,0],[1,0],[1,1],[0,1]];
const categories = [['hands_feet','Hands + feet'],['clothing','Clothing'],['hair','Hair'],['body','Body']];
const id = () => crypto.randomUUID();

function init() {
  if (panel) return;
  panel = document.createElement('div'); panel.id = 'linedraw-panel'; panel.hidden = true;
  panel.innerHTML = `
    <label for="linedraw-style">Drawing style</label><select id="linedraw-style">
      <option value="contours">Contours</option><option value="light_form">Light form</option>
      <option value="shadow_shapes">Shadow shapes</option><option value="face_form">Face + form</option>
      <option value="light_support">Light form support</option><option value="regional_form">Regional face + form</option>
    </select>
    <div id="linedraw-form" class="form"></div>
    <div id="linedraw-categories"><p>Detail categories</p>${categories.map(([key,label]) => `<label><input type="checkbox" data-category="${key}" aria-label="Include ${label.toLowerCase()}"> ${label}</label>`).join('')}<p class="hint">Material form shading requires a face region. Assign each detail region to its person.</p></div>
    <div class="linedraw-actions"><button id="linedraw-analyze">Analyze / redetect faces</button><button id="linedraw-redraw">Redraw</button><button id="linedraw-cancel-job">Cancel analysis</button></div>
    <p id="linedraw-readiness" class="hint"></p>
    <label>Edit source guides<select id="linedraw-edit-mode"><option value="faces">Face regions</option><option value="people">People / owners</option><option value="details">Detail regions</option></select></label>
    <details id="linedraw-face-controls" open><summary>Face regions</summary>
      <p class="hint">Drag an ellipse to move it; drag its corner dot to resize. These regions request detail, not landmark drawing strokes.</p>
      <label>Selected face<select id="linedraw-face-select"></select></label>
      <div class="linedraw-actions"><button id="linedraw-add-face">Add face region</button><button id="linedraw-delete-face">Delete face region</button></div>
      <div class="linedraw-face-fields">
        ${[['cx','Face center X (%)'],['cy','Face center Y (%)'],['rx','Face radius X (%)'],['ry','Face radius Y (%)']].map(([key,label]) => `<label>${label}<input id="linedraw-${key}" type="number" min="${key[0]==='r'?.5:0}" max="${key[0]==='r'?50:100}" step=".1"></label>`).join('')}
      </div><label><input id="linedraw-enabled" type="checkbox">Include selected face</label>
    </details>
    <div id="linedraw-person-controls" hidden>
      <p class="hint">Owner polygons give each person an independent detail allowance. Link a face to each person when several faces are present.</p>
      <label>Selected person<select id="linedraw-person-select"></select></label>
      <div class="linedraw-actions"><button id="linedraw-add-person">Add person region</button><button id="linedraw-delete-person">Delete person region</button></div>
      <label>Person face<select id="linedraw-person-face"></select></label>
      <label>Person vertices (normalized x,y per line)<textarea id="linedraw-person-polygon" rows="4" spellcheck="false"></textarea></label>
      <div class="linedraw-actions"><button id="linedraw-draw-person">Draw person polygon</button><button id="linedraw-finish-person">Finish polygon</button></div>
    </div>
    <div id="linedraw-detail-controls" hidden>
      <p class="hint">No detail guides yet. Add a region on the source image to request regional strokes.</p>
      <label>Selected detail<select id="linedraw-detail-select"></select></label>
      <div class="linedraw-actions"><button id="linedraw-add-detail">Add detail region</button><button id="linedraw-delete-detail">Delete detail region</button></div>
      <label>Detail owner<select id="linedraw-detail-person"></select></label>
      <label>Detail category<select id="linedraw-detail-category"></select></label>
      <label><input id="linedraw-detail-enabled" type="checkbox"> Include selected detail</label>
      <label>Detail vertices (normalized x,y per line)<textarea id="linedraw-detail-polygon" rows="4" spellcheck="false"></textarea></label>
      <label>Excluded polygons (JSON normalized coordinates)<textarea id="linedraw-detail-exclusions" rows="3" spellcheck="false"></textarea></label>
      <div class="linedraw-actions"><button id="linedraw-draw-detail">Draw detail polygon</button><button id="linedraw-finish-detail">Finish polygon</button></div>
    </div>
    <p id="linedraw-message" class="hint" aria-live="polite"></p>
    <div class="linedraw-actions"><button id="linedraw-keep" class="primary">Keep as layer</button><button id="linedraw-apply">Apply to layer</button><button id="linedraw-close">Cancel draft</button></div>`;
  $('bench-controls').append(panel);
  workspace = document.createElement('div'); workspace.className = 'linedraw-workspace'; workspace.hidden = true;
  workspace.innerHTML = `<figure><figcaption>Source · editable guides</figcaption><svg id="linedraw-source" aria-label="Editable regions on source image"></svg></figure><figure><figcaption>Drawing · actual pen paths</figcaption><svg id="linedraw-drawing" aria-label="Linedraw pen paths"></svg></figure>`;
  $('process-canvas').closest('.process-body').append(workspace);
  regions = new FaceRegions($('linedraw-source'), faces => {
    if (!active) return; active.params.faces = faces; changed(); updateFaces();
  }, i => { if (active) { active.selected = i; updateFaces(); } });
  detailEditor = new DetailRegions($('linedraw-source'), (people, details) => {
    if (!active) return;
    active.params.people = people; active.params.detail_regions = details; changed(); updateGuides();
  }, i => { if (!active) return; active[active.editMode === 'people' ? 'selectedPerson' : 'selectedDetail'] = i; updateGuides(); });
  $('linedraw-style').onchange = () => {
    active.params.style = $('linedraw-style').value;
    if (active.params.style === 'regional_form' && !active.params.people.length && active.params.faces.length <= 1) ensurePerson();
    if (active.params.style === 'regional_form') active.editMode='details';
    renderControls(); updateGuides(); changed();
  };
  $('linedraw-edit-mode').onchange = () => { active.editMode = $('linedraw-edit-mode').value; updateGuides(); };
  panel.querySelectorAll('[data-category]').forEach(box => box.onchange = () => {
    const name = box.dataset.category, set = new Set(active.params.detail_categories);
    if (box.checked) set.add(name); else set.delete(name);
    active.params.detail_categories = categories.map(([key]) => key).filter(key => set.has(key)); changed();
  });
  $('linedraw-face-select').onchange = () => { active.selected = Number($('linedraw-face-select').value); updateFaces(); };
  $('linedraw-add-face').onclick = () => {
    if (!active || active.params.faces.length >= 32) return;
    active.params.faces.push({ id: crypto.randomUUID(), cx:.5, cy:.3, rx:.1, ry:.15, enabled:true, origin:'manual' });
    active.selected = active.params.faces.length - 1; changed(); updateFaces();
  };
  $('linedraw-delete-face').onclick = () => {
    if (!active || active.selected < 0) return;
    const [removed]=active.params.faces.splice(active.selected,1);
    active.params.people.forEach(person => { if (person.face_id === removed.id) person.face_id=''; });
    active.selected = Math.min(active.selected,active.params.faces.length-1); changed(); updateFaces();
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
  $('linedraw-person-select').onchange = () => { active.selectedPerson = Number($('linedraw-person-select').value); updateGuides(); };
  $('linedraw-detail-select').onchange = () => { active.selectedDetail = Number($('linedraw-detail-select').value); updateGuides(); };
  $('linedraw-add-person').onclick = () => { if (!active || active.params.people.length >= 32) return; addPerson(); changed(); updateGuides(); };
  $('linedraw-delete-person').onclick = () => {
    if (!active || active.selectedPerson < 0) return;
    const [person] = active.params.people.splice(active.selectedPerson, 1);
    active.params.detail_regions = active.params.detail_regions.filter(r => r.person_id !== person.id);
    active.selectedPerson = Math.min(active.selectedPerson, active.params.people.length-1);
    active.selectedDetail = Math.min(active.selectedDetail, active.params.detail_regions.length-1);
    changed(); updateGuides();
  };
  $('linedraw-add-detail').onclick = () => {
    if (!active || active.params.detail_regions.length >= 64) return;
    if (!active.params.people.length) ensurePerson();
    const person = active.params.people[Math.max(0, active.selectedPerson)];
    active.params.detail_regions.push({id:id(),person_id:person.id,category:'hands_feet',polygon:copy(square),exclude_polygons:[],enabled:true});
    active.selectedDetail = active.params.detail_regions.length-1; active.editMode='details'; changed(); updateGuides();
  };
  $('linedraw-delete-detail').onclick = () => {
    if (!active || active.selectedDetail < 0) return;
    active.params.detail_regions.splice(active.selectedDetail,1);
    active.selectedDetail = Math.min(active.selectedDetail,active.params.detail_regions.length-1); changed(); updateGuides();
  };
  $('linedraw-person-face').onchange = () => {
    const p=selectedPerson(); if (!p) return;
    const faceId=$('linedraw-person-face').value;
    if (faceId && active.params.people.some(other => other !== p && other.face_id === faceId)) {
      $('linedraw-message').textContent='That face is already assigned to another person.'; updateGuides(); return;
    }
    p.face_id=faceId; changed(); updateGuides();
  };
  $('linedraw-detail-person').onchange = () => { const r=selectedDetail(); if (!r) return; r.person_id=$('linedraw-detail-person').value; changed(); updateGuides(); };
  $('linedraw-detail-category').onchange = () => { const r=selectedDetail(); if (!r) return; r.category=$('linedraw-detail-category').value; changed(); updateGuides(); };
  $('linedraw-detail-enabled').onchange = () => { const r=selectedDetail(); if (!r) return; r.enabled=$('linedraw-detail-enabled').checked; changed(); updateGuides(); };
  for (const [key, get] of [['person-polygon',selectedPerson],['detail-polygon',selectedDetail]]) $('linedraw-'+key).onchange = () => {
    const region=get(); if (!region) return;
    const value=parseVertices($('linedraw-'+key).value);
    if (!value) { $('linedraw-message').textContent='Enter at least three x,y points from 0 to 1.'; updateGuides(); return; }
    region.polygon=value; changed(); updateGuides();
  };
  $('linedraw-detail-exclusions').onchange = () => {
    const region=selectedDetail(); if (!region) return;
    try {
      const value=JSON.parse($('linedraw-detail-exclusions').value || '[]');
      if (!Array.isArray(value) || !value.every(p => validPolygon(p))) throw new Error();
      region.exclude_polygons=value; changed(); updateGuides();
    } catch { $('linedraw-message').textContent='Exclusions must be JSON polygons with at least three x,y points from 0 to 1.'; updateGuides(); }
  };
  for (const kind of ['person','detail']) {
    $('linedraw-draw-'+kind).onclick = () => { detailEditor.beginPolygon(); $('linedraw-message').textContent='Click source points, then Finish polygon.'; };
    $('linedraw-finish-'+kind).onclick = () => { if (!detailEditor.endPolygon()) $('linedraw-message').textContent='Add at least three points before finishing.'; };
  }
  $('linedraw-analyze').onclick = () => run('analyze');
  $('linedraw-redraw').onclick = () => run('render');
  $('linedraw-cancel-job').onclick = cancelJob;
  $('linedraw-close').onclick = () => closeLinedrawBench();
  $('linedraw-keep').onclick = () => keep(false);
  $('linedraw-apply').onclick = () => keep(true);
}
function key() { return JSON.stringify(active?.params); }
function selectedPerson() { return active?.params.people[active.selectedPerson]; }
function selectedDetail() { return active?.params.detail_regions[active.selectedDetail]; }
function validPolygon(value) { return Array.isArray(value) && value.length >= 3 && value.every(p => Array.isArray(p) && p.length === 2 && p.every(n => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1)); }
function parseVertices(text) {
  const value=text.trim().split(/\n+/).map(line => line.split(',').map(v => Number(v.trim())));
  return validPolygon(value) ? value : null;
}
function vertices(value) { return (value || []).map(([x,y]) => `${x},${y}`).join('\n'); }
function addPerson() {
  const faces=active.params.faces;
  const onlyFace=faces.length === 1 && !active.params.people.some(person => person.face_id === faces[0].id);
  const person={id:id(),face_id:onlyFace ? faces[0].id : '',polygon:copy(wholeFrame)};
  active.params.people.push(person); active.selectedPerson=active.params.people.length-1; return person;
}
function ensurePerson() { return active.params.people[0] || addPerson(); }
function fillSelect(element, values, selected) {
  element.replaceChildren();
  values.forEach(([value,label]) => { const option=document.createElement('option'); option.value=value; option.textContent=label; element.append(option); });
  element.value=selected;
}
function updateGuides() {
  if (!active) return;
  const mode=active.editMode;
  $('linedraw-edit-mode').value=mode;
  $('linedraw-face-controls').hidden=mode !== 'faces';
  $('linedraw-person-controls').hidden=mode !== 'people';
  $('linedraw-detail-controls').hidden=mode !== 'details';
  regions.setActive(mode === 'faces');
  detailEditor.setMode(mode, mode === 'people' ? active.selectedPerson : active.selectedDetail);
  detailEditor.setData(active.params.people,active.params.detail_regions);
  const people=active.params.people, details=active.params.detail_regions;
  fillSelect($('linedraw-person-select'),people.map((p,i) => [String(i),`Person ${i+1}`]),String(active.selectedPerson));
  fillSelect($('linedraw-detail-select'),details.map((r,i) => [String(i),`${r.category.replace('_',' + ')} ${i+1}`]),String(active.selectedDetail));
  fillSelect($('linedraw-person-face'),[['','— unlinked —'],...active.params.faces.map((f,i) => [f.id,`Face ${i+1}`])],selectedPerson()?.face_id || '');
  const usedFaces=new Set(people.filter(person => person !== selectedPerson()).map(person => person.face_id));
  [...$('linedraw-person-face').options].forEach(option => { option.disabled=!!option.value && usedFaces.has(option.value); });
  fillSelect($('linedraw-detail-person'),people.map((p,i) => [p.id,`Person ${i+1}`]),selectedDetail()?.person_id || '');
  fillSelect($('linedraw-detail-category'),categories,selectedDetail()?.category || 'hands_feet');
  $('linedraw-person-polygon').value=vertices(selectedPerson()?.polygon);
  $('linedraw-detail-polygon').value=vertices(selectedDetail()?.polygon);
  $('linedraw-detail-exclusions').value=JSON.stringify(selectedDetail()?.exclude_polygons || []);
  $('linedraw-detail-enabled').checked=!!selectedDetail()?.enabled;
  $('linedraw-detail-controls').querySelector('.hint').textContent=details.length
    ? 'Drag a region or vertex on the source; edit coordinates below for precision. Exclusions remove detail within a region.'
    : 'No detail guides yet. Add a region on the source image to request regional strokes.';
  const busy=active.busy || active.keeping;
  for (const name of ['delete-person','person-face','person-polygon','draw-person','finish-person']) $('linedraw-'+name).disabled=busy || !selectedPerson();
  for (const name of ['delete-detail','detail-person','detail-category','detail-enabled','detail-polygon','detail-exclusions','draw-detail','finish-detail']) $('linedraw-'+name).disabled=busy || !selectedDetail();
  $('linedraw-add-person').disabled=busy || people.length >= 32;
  $('linedraw-add-detail').disabled=busy || details.length >= 64;
  if (mode === 'faces') regions.draw();
}
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
  detailEditor.disabled = busy;
  panel.querySelectorAll('input,select').forEach(el => { el.disabled = !!active.keeping; });
  for (const name of ['cx','cy','rx','ry','enabled']) $('linedraw-'+name).disabled = busy || active.selected < 0;
  updateGuideButtons();
}
function updateGuideButtons() {
  if (!active) return;
  const busy=active.busy || active.keeping;
  for (const name of ['delete-person','person-face','person-polygon','draw-person','finish-person']) $('linedraw-'+name).disabled=busy || !selectedPerson();
  for (const name of ['delete-detail','detail-person','detail-category','detail-enabled','detail-polygon','detail-exclusions','draw-detail','finish-detail']) $('linedraw-'+name).disabled=busy || !selectedDetail();
  $('linedraw-add-person').disabled=busy || active.params.people.length >= 32;
  $('linedraw-add-detail').disabled=busy || active.params.detail_regions.length >= 64;
}
function changed(auto=true) {
  if (!active) return;
  clearTimeout(redrawTimer); redrawTimer=null;
  if (active.busy) cancelJob();
  active.rendered = null; $('linedraw-message').textContent = 'Settings changed. Updating drawing…';
  $('process-status').textContent='Drawing update pending'; buttons();
  if (auto && active.params.image && active.ready) redrawTimer=setTimeout(() => {
    redrawTimer=null; if (active && !active.busy && !active.keeping) run('render');
  },350);
}
function imageChanged() {
  active.params.faces = []; active.params.people=[]; active.params.detail_regions=[];
  active.params.image_identity = ''; active.params.model_identity = '';
  active.selected = -1; active.selectedPerson=-1; active.selectedDetail=-1;
  const url=active.params.image ? `/api/assets/${encodeURIComponent(active.params.image)}?frame=${active.params.frame || 0}` : '';
  regions.setImage(url); detailEditor.setImage(url);
  updateFaces(); updateGuides(); changed(false);
}
function updateFaces() {
  if (!active) return;
  const select = $('linedraw-face-select'); select.replaceChildren();
  active.params.faces.forEach((f,i) => { const o = document.createElement('option'); o.value=String(i); o.textContent=`Face ${i+1} · ${f.origin}`; select.append(o); });
  select.value = String(active.selected);
  const face = active.params.faces[active.selected];
  for (const key of ['cx','cy','rx','ry']) $('linedraw-'+key).value = face ? String(Math.round(face[key]*1000)/10) : '';
  $('linedraw-enabled').checked = !!face?.enabled;
  regions.setFaces(active.params.faces,active.selected); buttons(); updateGuides();
}
function cancelJob() {
  if (!active) return;
  clearTimeout(redrawTimer); redrawTimer=null;
  active.finishDrawing?.(); active.finishDrawing=null;
  const identity = active.job; active.job = null; active.busy = false; active.token = ++serial;
  if (identity) api.del(`/api/linedraw/jobs/${identity}`).catch(() => {});
  $('linedraw-message').textContent = 'Analysis cancelled. Previous drawing retained.';
  $('process-status').textContent='Drawing update cancelled'; buttons();
}
async function run(operation) {
  if (!active || active.keeping) return;
  cancelJob(); clearBenchError();
  const draft=active, token=++serial, finishDrawing=beginDrawingUpdate();
  draft.finishDrawing=finishDrawing; draft.token=token; draft.busy=true; draft.rendered=null; buttons();
  $('process-status').textContent='Analyzing · 0%';
  const valid = () => active===draft && draft.token===token && draft.epoch===benchProjectEpoch();
  try {
    let job=await api.post('/api/linedraw/jobs',{ revision:String(token),params:copy(draft.params),operation });
    if (!valid()) { await api.del(`/api/linedraw/jobs/${job.id}`); return; }
    draft.job=job.id;
    while (['queued','running'].includes(job.state)) {
      $('linedraw-message').textContent = `${job.message || 'Waiting'} · ${Math.round(job.progress*100)}%`;
      $('process-status').textContent=`${job.message || 'Analyzing'} · ${Math.round((job.progress || 0)*100)}%`;
      await new Promise(resolve => setTimeout(resolve,250));
      if (!valid()) return;
      job=await api.get(`/api/linedraw/jobs/${job.id}`);
      if (!valid()) return;
    }
    if (job.state==='failed') throw new Error(job.error);
    if (job.state!=='complete') return;
    draft.params=copy(job.result.params); draft.params.people ||= []; draft.params.detail_regions ||= [];
    draft.selected=draft.params.faces.length?0:-1;
    draft.selectedPerson=Math.min(draft.selectedPerson,draft.params.people.length-1);
    draft.selectedDetail=Math.min(draft.selectedDetail,draft.params.detail_regions.length-1);
    draft.rendered=key(); draft.job=null;
    renderControls(); updateFaces(); updateGuides(); draw(job.result.preview);
    $('process-status').textContent=`Drawing current · ${job.result.preview?.lines?.length || 0} pen paths`;
    $('linedraw-message').textContent=['Drawing ready.', ...(job.result.diagnostics?.device ? [`Processed locally on ${job.result.diagnostics.device.toUpperCase()}.`] : []), ...job.result.warnings].join(' ');
  } catch (error) { if (valid()) { $('process-status').textContent='Drawing unavailable · retry below'; showBenchError(error,() => run(operation)); } }
  finally {
    finishDrawing();
    if (draft.finishDrawing === finishDrawing) draft.finishDrawing=null;
    if (valid()) { draft.busy=false; buttons(); }
  }
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
  const common=['image','frame','rotate','width','show_map'];
  const keys=active.params.style === 'light_support'
    ? [...common,'contour_budget']
    : active.params.style === 'regional_form'
      ? [...common,'contour_budget','face_budget','detail_budget']
      : null;
  if (keys) schema.properties=Object.fromEntries(Object.entries(schema.properties).filter(([key]) => keys.includes(key)));
  // The detail controls are dedicated because the array is edited on the source SVG.
  if (active.params.style === 'regional_form' && !schema.properties.detail_budget) schema.properties.detail_budget={type:'integer',minimum:0,maximum:1024,title:'Strokes per detail region'};
  renderForm($('linedraw-form'),schema,active.params,key => {
    if (key==='image' || key==='frame') imageChanged(); else changed();
  });
  $('linedraw-style').value=active.params.style;
  $('linedraw-categories').hidden=active.params.style !== 'regional_form';
  panel.querySelectorAll('[data-category]').forEach(box => { box.checked=active.params.detail_categories.includes(box.dataset.category); });
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
  Object.assign(params,copy(entry.params)); params.faces ||= []; params.people ||= []; params.detail_regions ||= [];
  params.detail_categories ||= ['hands_feet','clothing','hair']; params.detail_budget ??= 192;
  active={...entry,params,selected:params.faces.length?0:-1,selectedPerson:params.people.length?0:-1,
    selectedDetail:params.detail_regions.length?0:-1,editMode:'faces',epoch:benchProjectEpoch(),job:null,busy:false,keeping:false,ready:false,rendered:null,token:++serial};
  $('process-title').textContent='Linedraw v3';
  hiddenBefore=[...$('bench-controls').children,$('process-canvas').closest('.preview-stage'),...document.querySelectorAll('#process-popup .bench-transport,#process-popup .process-generic-actions,#process-popup .second-only'),$('process-telemetry-row')]
    .filter(el => el && el!==panel).map(el => [el,el.hidden]);
  hiddenBefore.forEach(([el]) => { el.hidden=true; });
  panel.hidden=false; workspace.hidden=false; $('process-popup').classList.add('linedraw');
  openBenchShell({close:closeLinedrawBench,cancelGesture:() => regions.cancel() || detailEditor.cancel(),origin:'Image → local drawing → layer'});
  if (params.style === 'regional_form' && !params.people.length && params.faces.length <= 1) ensurePerson();
  renderControls();
  const url=params.image ? `/api/assets/${encodeURIComponent(params.image)}?frame=${params.frame || 0}` : '';
  regions.setImage(url); detailEditor.setImage(url); updateFaces(); updateGuides();
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
  clearTimeout(redrawTimer); redrawTimer=null;
  panel.hidden=true; workspace.hidden=true; hiddenBefore.forEach(([el,hidden]) => { el.hidden=hidden; }); hiddenBefore=[];
  $('process-popup').classList.remove('linedraw'); closeBenchShell();
  if (notify) callback?.();
}
