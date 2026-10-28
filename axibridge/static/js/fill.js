// A face is only a candidate until clicked. Raw rings belong to this editing
// run; saved geometry and effects use the ordinary pen/layer APIs.
import { api } from './api.js';
import { S, actions } from './main.js';
const $ = id => document.getElementById(id);
let on = false, wired = false, epoch = 0, lifecycle = 0, timer, abort;
let candidate = null, pointer = null, lastPointer = null, latest = null, busy = false, ownRefresh = false;
let read = null, intent = null;
let refitting = false, queuedFit = null, gestureToken = null;
const nonce = Math.random().toString(36).slice(2);
let serial = 0;
const idleWaiters = [];
function notifyIdle() { if (!busy && !refitting) idleWaiters.splice(0).forEach(resolve=>resolve()); }
export async function settleFillHistory() {
  clearCandidate(); endResult();
  if (busy || refitting) await new Promise(resolve=>idleWaiters.push(resolve));
}
const stamp = () => JSON.stringify([S.state?.project?.edit_rev, S.masterT]);
const detail = () => Math.max(0, Math.min(1, Number($('fill-detail').value)));
const gap = () => Math.max(0, Math.min(5, Number($('fill-gap').value)));
const layer = () => latest && S.state?.project.layers.find(l => l.id === latest.id);
function clearCandidate() {
  read = null; intent = null;
  ++epoch; clearTimeout(timer); abort?.abort(); abort = null; candidate = null;
  document.querySelector('.fill-candidate')?.remove();
  if (wired) $('fill-status').textContent = latest ? 'Boundary created — choose a fill' : 'Hover a bounded face';
}
function endResult() { latest = null; queuedFit = null; gestureToken = null; controls(); }
function controls() {
  const l = layer();
  const fx = l?.effects?.find(f => ['hatch_fill','offset_fill','offset_fill_v2','eigen_fill'].includes(f.effect));
  const locked = busy || refitting;
  $('fill-effect').disabled = !l || locked;
  $('fill-outline').disabled = !fx || locked;
  if (locked) return;
  $('fill-effect').value = fx?.effect || '';
  $('fill-outline').checked = fx ? fx.params.outline !== false : true;
}
export function refreshFillState() {
  if (!wired || !on) return;
  if ((read && read.stamp !== stamp()) || (intent && !currentIntent(intent))) clearCandidate();
  if (latest && ((!ownRefresh && latest.stamp !== stamp()) || latest.masterT !== S.masterT || S.selection.length !== 1 || S.selection[0] !== latest.id)) endResult();
  drawCandidate();
}
export function activateFillMode() { on = true; $('canvas-wrap').classList.add('fill-mode'); controls(); }
export function deactivateFillMode() { ++lifecycle; on = false; clearCandidate(); endResult(); pointer = lastPointer = null; $('canvas-wrap').classList.remove('fill-mode'); }
export function handleFillEscape() { clearCandidate(); endResult(); }
function drawCandidate() {
  document.querySelector('.fill-candidate')?.remove();
  if (!candidate || !on) return;
  const p = document.createElementNS('http://www.w3.org/2000/svg','path');
  p.setAttribute('class','fill-candidate'); p.setAttribute('fill-rule','evenodd');
  p.setAttribute('d', candidate.rings.map(r => `M ${r.map(pt=>pt.join(',')).join(' L ')} Z`).join(' '));
  actions.canvas().world.appendChild(p);
}
const faceBody = p => ({point:[...p], gap_mm:gap(), detail:detail(), master_t:S.masterT});
function sameFace(a, b, tolerance = 1e-9) {
  return a && b && Math.abs(a.point[0]-b.point[0]) < tolerance && Math.abs(a.point[1]-b.point[1]) < tolerance
    && a.gap_mm === b.gap_mm && a.detail === b.detail && a.master_t === b.master_t;
}
function currentIntent(i) {
  return on && !busy && !refitting && i.lifecycle === lifecycle && i.stamp === stamp()
    && i.selection === JSON.stringify(S.selection) && sameFace(i.body,faceBody(i.body.point));
}
function preview(p, review = false) {
  if (!on || busy || !p || !Number.isFinite(gap()) || !Number.isFinite(detail())) return;
  const body = faceBody(p), state = stamp();
  // A quick click reuses the exact hover already being read, including its
  // immutable options. Repeated clicks must not cancel or duplicate that read.
  if (read && read.stamp === state && sameFace(read.body,body)) {
    read.review ||= review;
    return;
  }
  clearCandidate();
  const mine = epoch, reading = {body, stamp:state, review}; read = reading;
  timer = setTimeout(async () => {
    const controller = new AbortController(); abort = controller;
    try {
      const result = await api.post('/api/geometry/face',body,{signal:controller.signal});
      if (!on || mine !== epoch || state !== stamp()) return;
      candidate = {...result, body, stamp:state}; drawCandidate();
      $('fill-status').textContent = reading.review
        ? 'Review repaired face — click again to create' : 'Click highlighted face';
      const queued = intent, shown = candidate;
      if (queued && currentIntent(queued) && sameFace(queued.body,body) && result.revision === S.state.project.edit_rev) {
        // Give the exact returned face a paint before writing it. Recheck all
        // captured intent after painting: movement or an edit may abandon it.
        requestAnimationFrame(()=>requestAnimationFrame(()=>{
          if (intent === queued && candidate === shown && currentIntent(queued)) writeCandidate(shown);
        }));
      }
    } catch(e) {
      if (mine !== epoch || !on || state !== stamp() || e.name === 'AbortError') return;
      intent = null; read = null;
      $('fill-status').textContent = e.message;
    }
  }, 80);
}
// Our write advances edit_rev exactly once. A greater revision means another
// edit landed during the refresh; selection and ephemeral t can change without
// a revision, so they remain checked even while our own refresh is in flight.
async function sync(run, expectedRev) {
  ownRefresh = true;
  try {
    await actions.refreshProject();
    if (run && latest === run && (S.state.project.edit_rev !== expectedRev || run.masterT !== S.masterT)) endResult();
    await actions.refreshResolved();
  } finally { ownRefresh = false; }
  if (run && latest === run) {
    if (S.state.project.edit_rev !== expectedRev || run.masterT !== S.masterT || S.selection.length !== 1 || S.selection[0] !== run.id) endResult();
    else run.stamp = stamp();
  }
  controls();
}
function commit(e) {
  if (!on || e.button !== 0) return;
  e.preventDefault(); e.stopPropagation();
  if (busy || refitting) return;
  refreshFillState();
  const p = actions.canvas().toBed(e), at = [p.x,p.y], body = faceBody(at);
  pointer = lastPointer = at;
  if (intent && currentIntent(intent) && sameFace(intent.body,body)) return;
  if (candidate && candidate.stamp === stamp() && sameFace(candidate.body,body,.01)) {
    writeCandidate(candidate);
    return;
  }
  preview(at,body.gap_mm > 0);
  if (body.gap_mm === 0) {
    intent = {body, stamp:stamp(), selection:JSON.stringify(S.selection), lifecycle};
    $('fill-status').textContent = 'Finding face for this click…';
  } else $('fill-status').textContent = 'Review repaired face before clicking again';
}
async function writeCandidate(c) {
  if (!on || busy || refitting || candidate !== c || c.stamp !== stamp()) return;
  intent = null;
  const run = lifecycle, selection = JSON.stringify(S.selection), expectedRev = S.state.project.edit_rev + 1;
  endResult();
  busy = true; controls();
  try {
    const created = await api.post('/api/layers/fill',{...c.body,revision:c.revision});
    clearCandidate();
    // A write already sent may finish after tool exit. It still belongs in
    // the project, but may never reopen controls or steal the new selection.
    if (on && run === lifecycle && c.body.master_t === S.masterT && selection === JSON.stringify(S.selection)) {
      ownRefresh = true;
      try { actions.setSelection([created.id]); } finally { ownRefresh = false; }
      latest = {id:created.id, rings:c.rings, stamp:stamp(), masterT:c.body.master_t};
    }
    await sync(latest, expectedRev);
    $('fill-status').textContent = on ? 'Boundary created — choose a fill' : '';
  } catch(e) { actions.oops(e); if (e.status === 409) clearCandidate(); }
  finally {
    busy = false; controls();
    if (latest && on && detail() !== c.body.detail) requestRefit();
    notifyIdle();
  }
}
function requestRefit() {
  if (!latest) return;
  // Capture the gesture now: release may happen before this request is run.
  queuedFit = {detail:detail(), token:gestureToken || `fill-detail-${nonce}-${++serial}`};
  refit();
}
async function refit() {
  if (!latest || busy || refitting || !queuedFit) return;
  const run = latest, request = queuedFit, state = stamp();
  queuedFit = null; refitting = true; controls();
  try {
    const fit = await api.post('/api/geometry/face/fit',{rings:run.rings,detail:request.detail});
    if (!on || latest !== run || state !== stamp() || queuedFit) return;
    const l = layer(), expectedRev = S.state.project.edit_rev + 1;
    busy = true; controls();
    await api.post(`/api/layers/${run.id}/regenerate`,{params:{...l.source.params,subpaths:fit.subpaths},coalesce:request.token});
    await sync(run, expectedRev);
  } catch(e) { if (latest === run && state === stamp()) actions.oops(e); }
  finally {
    busy = false; refitting = false; controls();
    if (queuedFit && latest === run) refit();
    notifyIdle();
  }
}
async function effectChange() {
  if (!latest || busy || refitting) return;
  const run = latest, expectedRev = S.state.project.edit_rev + 1;
  const l = layer(), id = $('fill-effect').value;
  const known = ['hatch_fill','offset_fill','offset_fill_v2','eigen_fill'];
  const old = l.effects.find(f=>known.includes(f.effect));
  const rest = l.effects.filter(f=>!known.includes(f.effect));
  const mod = S.state.modules.effects.find(m=>m.id === id);
  const fx = mod ? {effect:id,enabled:true,params:{...(old?.effect === id ? old.params : structuredClone(mod.defaults)),outline:$('fill-outline').checked}} : null;
  busy = true; controls(); clearCandidate();
  try { await api.patch(`/api/layers/${l.id}`,{effects:fx ? [...rest,fx] : rest}); await sync(run, expectedRev); }
  catch(e) { actions.oops(e); }
  finally { busy = false; controls(); if (queuedFit && latest === run) refit(); notifyIdle(); }
}
export function initFillMode() {
  if (wired || !$('fill-bar')) return; wired = true;
  const wrap = $('canvas-wrap');
  wrap.addEventListener('pointermove',e=>{
    if (!on) return;
    const p = actions.canvas().toBed(e);
    if (pointer && Math.hypot(pointer[0]-p.x,pointer[1]-p.y) < 0.01) return;
    pointer = lastPointer = [p.x,p.y];
    if (!busy) preview(pointer);
  },true);
  wrap.addEventListener('pointerdown',commit,true);
  wrap.addEventListener('dblclick',e=>{if(on){e.preventDefault();e.stopPropagation();}},true);
  wrap.addEventListener('pointerleave',()=>{if(on) {clearCandidate();pointer=null;}},true);
  $('fill-gap').addEventListener('input',()=>preview(lastPointer));
  const slider = $('fill-detail');
  slider.addEventListener('pointerdown',()=>{gestureToken=`fill-detail-${nonce}-${++serial}`;});
  slider.addEventListener('input',()=>{ if(intent) clearCandidate(); if(latest) requestRefit(); else preview(lastPointer); });
  slider.addEventListener('change',()=>{gestureToken=null;slider.blur();});
  slider.addEventListener('keydown',e=>{
    if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); requestRefit(); return; }
    if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== 'z') return;
    e.preventDefault(); e.stopPropagation(); slider.blur();
    document.body.dispatchEvent(new KeyboardEvent('keydown',{key:e.key,metaKey:e.metaKey,ctrlKey:e.ctrlKey,shiftKey:e.shiftKey,bubbles:true,cancelable:true}));
  });
  $('fill-effect').addEventListener('change',effectChange);
  $('fill-outline').addEventListener('change',effectChange);
  document.addEventListener('canvas-view-change',()=>{refreshFillState();drawCandidate();});
}
