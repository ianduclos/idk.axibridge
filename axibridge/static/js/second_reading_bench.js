// The intervention bench for process generators that declare both
// `intervene` and `branch`. Unlike the generic time-axis bench, this is a
// small score editor: every change that can affect a rendered drawing is an
// event at a turn, and the selected branch's exact recipe is what Preview and
// Keep receive.

import { api } from "./api.js";
import { actions } from "./main.js";
import {
  benchProjectEpoch,
  clearBenchError,
  closeBenchShell,
  openBenchShell,
  showBenchError,
} from "./bench_host.js";
import { benchDescriptor } from "./bench_registry.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const MAX_EVENTS = 128;
const MAX_POINTS = 20_000;
const CONTROL_KEYS = ["persistence", "reach", "recurrence", "attention", "departure", "scale", "reading"];
const ORDER = { controls: 0, branch: 1, stroke: 2 };

// Deliberately memory-only. A draft survives closing and reopening the popup
// during this app run, while a browser restart starts with the recipe saved in
// the layer (or the Generate form) and no client-side branch recovery.
const drafts = new Map();
let active = null;
let wired = false;
let playTimer = null;
let playSerial = 0;
let capture = null;
let openSerial = 0;

const copy = (v) => JSON.parse(JSON.stringify(v));
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export function isSecondReadingModule(mod) {
  const descriptor = benchDescriptor(mod);
  return descriptor?.adapter === "second-reading" && descriptor.version === 1;
}

export function isSecondReadingBenchOpen() {
  return Boolean(active);
}

function branch() {
  return active?.draft.branches.find((b) => b.id === active.draft.active) || null;
}

function normalizeEvents(events) {
  return copy(events || []).sort((a, b) =>
    Number(a.turn) - Number(b.turn) || (ORDER[a.kind] ?? 9) - (ORDER[b.kind] ?? 9));
}

function recipe(b = branch()) {
  return b ? { ...copy(b.params), turns: b.turn, events: normalizeEvents(b.params.events) } : null;
}

function recipeKey(b = branch()) {
  return JSON.stringify(recipe(b));
}

function snapshot() {
  return copy({
    branches: active.draft.branches.map(({ rendered, renderedKey, awaiting, ...b }) => ({
      ...b, rendered: null, renderedKey: null, awaiting: false,
    })),
    active: active.draft.active,
  });
}

function remember() {
  active.draft.undo.push(snapshot());
  if (active.draft.undo.length > 80) active.draft.undo.shift();
  active.draft.redo = [];
}

function restore(snap) {
  active.draft.branches = copy(snap.branches);
  active.draft.active = snap.active;
  stopSecondReadingPlay();
  cancelCapture();
  renderChrome();
  requestPreview();
}

function replaceEvent(b, event) {
  const events = normalizeEvents(b.params.events);
  const at = events.findIndex((e) => e.turn === event.turn && e.kind === event.kind);
  if (at >= 0) events[at] = copy(event);
  else {
    if (events.length >= MAX_EVENTS) return false;
    events.push(copy(event));
  }
  b.params.events = normalizeEvents(events);
  return true;
}

function pointCount(events) {
  return (events || []).reduce((n, e) => n + (e.kind === "stroke" ? (e.points || []).length : 0), 0);
}

function effectiveControls(b) {
  const base = {
    reading: b.params.reading ?? "responsive",
    attention: Number(b.params.attention ?? .5),
    departure: Number(b.params.departure ?? .5),
    scale: Number(b.params.scale ?? .5),
    persistence: Number(b.params.persistence ?? .5),
    reach: Number(b.params.reach ?? .5),
    recurrence: Number(b.params.recurrence ?? .5),
  };
  for (const e of normalizeEvents(b.params.events)) {
    if (e.turn > b.turn || e.kind !== "controls") continue;
    for (const k of Object.keys(base)) if (e[k] != null) base[k] = k === "reading" ? e[k] : Number(e[k]);
  }
  return base;
}

function ensureStaged(b) {
  if (!b.staged) b.staged = effectiveControls(b);
  return b.staged;
}

function commitStagedControls(b, turn) {
  const staged = ensureStaged(b);
  const current = effectiveControls(b);
  const changed = CONTROL_KEYS.some(
    (k) => staged[k] !== current[k]);
  return !changed || replaceEvent(b, { kind: "controls", turn, ...copy(staged) });
}

function controlsChanged(b) {
  const staged = ensureStaged(b);
  const current = effectiveControls(b);
  return CONTROL_KEYS.some(
    (k) => staged[k] !== current[k]);
}

function canRecord(b, kinds, turn) {
  const events = hasFuture(b) && kinds.length ? b.params.events.filter(e => e.turn <= b.turn) : (b.params.events || []);
  const needed = kinds.filter((kind) =>
    !events.some((e) => e.turn === turn && e.kind === kind)).length;
  return events.length + needed <= MAX_EVENTS;
}

function nextTurn(b) {
  return Math.min(64, Number(b.turn) + 1);
}

function hasFuture(b) {
  return b.turn < (b.furthest ?? b.turn) || b.params.events.some(e => e.turn > b.turn);
}

function forkPrefix(source, label) {
  const params = recipe(source);
  params.events = params.events.filter(e => e.turn <= source.turn);
  const next = freshBranch(params, `branch-${++active.draft.serial}`, label);
  next.staged = copy(ensureStaged(source));
  next.penSmoothing = source.penSmoothing ?? lastStrokeSmoothing(source);
  active.draft.branches.push(next);
  active.draft.active = next.id;
  return next;
}

function advance() {
  let b = branch();
  if (!b || b.turn >= 64 || b.awaiting) return Promise.resolve();
  cancelCapture();
  const turn = nextTurn(b);
  if (controlsChanged(b) && !canRecord(b, ["controls"], turn)) {
    actions.oops(new Error("This working recipe already has 128 events; keep it and start another."));
    return Promise.resolve();
  }
  remember();
  if (controlsChanged(b) && hasFuture(b)) b = forkPrefix(b, "Revised controls");
  commitStagedControls(b, turn);
  b.turn = turn;
  b.furthest = Math.max(b.furthest, turn);
  b.params.turns = turn;
  renderChrome();
  return requestPreview();
}

function updateReadout(id, value) {
  const out = $(`${id}-value`);
  if (out) out.textContent = Number(value).toFixed(2);
}

function wireRange(id, key) {
  const input = $(id);
  if (!input) return;
  input.oninput = () => updateReadout(id, input.value);
  input.onchange = () => {
    const b = branch();
    if (!b) return;
    remember();
    ensureStaged(b)[key] = clamp(Number(input.value), 0, 1);
    renderChrome();
  };
}

export function initSecondReadingBench() {
  if (wired || !$('process-second-reading')) return;
  wired = true;
  $("process-continue").onclick = () => advance().catch(actions.oops);
  $("process-your-turn").onclick = armCapture;
  $("process-try-another").onclick = tryAnother;
  $("process-branch-select").onchange = switchBranch;
  $("process-undo").onclick = undo;
  $("process-redo").onclick = redo;
  $("process-keep").onclick = keep;
  $("process-pin-reference").onclick = pinReference;
  $("process-compare").onclick = toggleComparison;
  $("process-discard-pending").onclick = discardPendingControls;
  $("process-new-drawing").onclick = newDrawing;
  $("process-randomize-seed").onclick = randomizePendingSeed;
  for (const id of ["process-boundary", "process-width", "process-height", "process-seed"]) {
    $(id).oninput = renderNewDrawingState;
    $(id).onchange = renderNewDrawingState;
  }
  $("process-turn-scrub").oninput = () => {
    const b = branch();
    if (!b) return;
    const turn = Number($("process-turn-scrub").value);
    stopSecondReadingPlay();
    cancelCapture();
    b.turn = turn;
    b.params.turns = turn;
    b.furthest = Math.max(b.furthest, turn);
    b.staged = effectiveControls(b);
    renderChrome();
    requestPreview();
  };
  wireRange("process-persistence", "persistence");
  wireRange("process-reach", "reach");
  wireRange("process-recurrence", "recurrence");
  for (const key of ["attention", "departure", "scale"]) wireRange(`process-${key}`, key);
  const smoothing = $("process-pen-smoothing");
  smoothing.oninput = () => updateReadout("process-pen-smoothing", smoothing.value);
  smoothing.onchange = () => {
    const b = branch();
    if (!b) return;
    b.penSmoothing = clamp(Number(smoothing.value), 0, 1);
    renderChrome();
  };
  $("process-reading").onchange = () => {
    const b = branch(); if (!b) return;
    remember(); ensureStaged(b).reading = $("process-reading").value; renderChrome();
  };

  const svg = $("process-canvas");
  svg.addEventListener("pointerdown", pointerDown);
  svg.addEventListener("pointermove", pointerMove);
  svg.addEventListener("pointerup", pointerUp);
  svg.addEventListener("pointercancel", cancelCapture);
  document.addEventListener("keydown", (e) => {
    if (!active) return;
    const editingText = e.target?.matches?.('input:not([type="range"]), textarea, [contenteditable="true"]');
    if (editingText) return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      e.stopImmediatePropagation();
      e.shiftKey ? redo() : undo();
    } else if (e.key === "Delete" || e.key === "Backspace") {
      // The project's selected layer is behind the modal, not the editing
      // target. A drawing gesture must never delete that unrelated layer.
      e.preventDefault();
      e.stopImmediatePropagation();
    }
  }, true);
  document.addEventListener("bench-project-reset", () => drafts.clear());
}

function freshBranch(params, id = "branch-1", label = "Reading 1") {
  const p = copy(params);
  p.events = normalizeEvents(p.events || []);
  const turn = clamp(Math.round(Number(p.turns ?? 12)), 0, 64);
  p.turns = turn;
  const b = { id, label, params: p, turn, furthest: turn,
    staged: null, renderedKey: null, rendered: null, awaiting: false };
  b.staged = effectiveControls(b);
  b.penSmoothing = lastStrokeSmoothing(b);
  return b;
}

function lastStrokeSmoothing(b) {
  const stroke = [...normalizeEvents(b.params.events)].reverse()
    .find((event) => event.kind === "stroke" && event.turn <= b.turn);
  return clamp(Number(stroke?.smoothing ?? .6), 0, 1);
}

export function openSecondReadingBench({ mod, params, contextKey, onKeep, onClose }) {
  const original = { mod, params, contextKey, onKeep, onClose };
  initSecondReadingBench();
  closeSecondReadingBench(false);
  const key = `${benchProjectEpoch()}:${contextKey || `new:${mod.id}`}`;
  let draft = drafts.get(key);
  if (!draft) {
    const first = freshBranch(params);
    draft = { branches: [first], active: first.id, undo: [], redo: [], serial: 1 };
    drafts.set(key, draft);
  }
  active = { mod, external: params, contextKey: key, draft, onKeep, onClose };
  loadPendingNewDrawing();
  openSerial++;
  $("process-popup").classList.add("second-reading");
  $("process-popup").hidden = false;
  $("process-title").textContent = `${mod.label} — working bench`;
  setSpecialChrome(true);
  openBenchShell({
    close: () => closeSecondReadingBench(),
    cancelGesture: () => {
      if (!capture) return false;
      cancelCapture();
      return true;
    },
    reopen: () => openSecondReadingBench(original),
    origin: contextKey?.startsWith("layer:")
      ? "From kept layer · new working draft" : "New material · working draft",
  });
  renderChrome();
  requestPreview();
}

export function closeSecondReadingBench(notify = true) {
  if (!active) return;
  stopSecondReadingPlay();
  cancelCapture();
  openSerial++;
  const closing = active;
  const b = branch();
  if (b && closing.external) Object.assign(closing.external, recipe(b));
  active = null;
  $("process-popup")?.classList.remove("second-reading");
  setSpecialChrome(false);
  if (notify && closing.onClose) closing.onClose();
  if (notify) closeBenchShell();
}

function setSpecialChrome(on) {
  $('process-status').hidden = on;
  if (on) $('process-popup').classList.remove('watch-only');
  if (!on) {
    $('process-reference').setAttribute('hidden', '');
    $('process-canvas').closest('.preview-stage').classList.remove('comparing');
  }
  const special = $("process-second-reading");
  if (special) special.hidden = !on;
  for (const id of ["process-params", "process-create", "process-reroll",
                    "process-prev", "process-next", "process-scrub",
                    "process-readout", "process-telemetry-row"]) {
    const el = $(id);
    if (el) el.hidden = on;
  }
  const play = $("process-play");
  if (play) play.hidden = false;
}

function renderChrome() {
  if (!active) return;
  const b = branch();
  if (!b) return;
  const staged = ensureStaged(b);
  const current = effectiveControls(b);
  $("process-turn-label").textContent = `Turn ${b.turn}`;
  $("process-turn-scrub").value = String(b.turn);
  const kept = $("process-kept-state");
  kept.hidden = b.keptKey !== recipeKey(b);
  kept.textContent = `Kept as layer · ${b.kept || ""}`;
  $("process-working-state").textContent = b.awaiting ? "Working · resolving…" : `Working · turn ${b.turn}`;
  $("process-working-state").classList.toggle("resolving", b.awaiting);
  const renderedPoints = b.renderedKey === recipeKey(b) ? b.rendered?.points : null;
  $("process-point-count").textContent = renderedPoints == null
    ? `${pointCount(b.params.events).toLocaleString()} drawn points`
    : `${Number(renderedPoints).toLocaleString()} points`;
  $("process-preview-state").textContent = b.awaiting ? "resolving" :
    (b.renderedKey === recipeKey(b) ? "rendered" : "not rendered");
  $("process-recipe").textContent = JSON.stringify(recipe(b));
  $("process-reading").value = staged.reading;
  const experimental = ["responsive", "shapes", "relations"].includes(staged.reading);
  for (const key of ["persistence", "reach", "recurrence"]) $(`process-${key}`).closest("label").hidden = experimental;
  for (const key of ["attention", "departure", "scale"]) $(`process-${key}`).closest("label").hidden = !experimental || (key === "attention" && !["relations", "responsive"].includes(staged.reading));
  for (const key of CONTROL_KEYS.filter(k => k !== "reading")) {
    const input = $(`process-${key}`);
    input.value = String(staged[key]);
    updateReadout(`process-${key}`, staged[key]);
    input.classList.toggle("staged", Number(staged[key]) !== Number(current[key]));
  }
  $("process-next-turn-note").textContent = controlsChanged(b)
    ? `control change queued for turn ${Math.min(64, b.turn + 1)}` : `controls at turn ${b.turn}`;
  $("process-discard-pending").hidden = !controlsChanged(b);

  const select = $("process-branch-select");
  select.replaceChildren();
  active.draft.branches.forEach((candidate, i) => {
    const option = document.createElement("option");
    option.value = candidate.id;
    option.textContent = `${i + 1}. ${candidate.label} · turn ${candidate.turn}`;
    option.selected = candidate.id === b.id;
    select.appendChild(option);
  });
  $("process-undo").disabled = active.draft.undo.length === 0;
  $("process-redo").disabled = active.draft.redo.length === 0;
  const atEnd = b.turn >= 64;
  const targetTurn = nextTurn(b);
  const controlKinds = controlsChanged(b) ? ["controls"] : [];
  $("process-continue").disabled = atEnd || b.awaiting || !canRecord(b, controlKinds, targetTurn);
  $("process-your-turn").disabled = atEnd || b.awaiting ||
    !canRecord(b, [...controlKinds, "stroke"], targetTurn) || pointCount(b.params.events.filter(e => e.turn <= b.turn)) >= MAX_POINTS - 1;
  $("process-try-another").disabled = atEnd || b.awaiting ||
    !canRecord(b, [...controlKinds, "branch"], targetTurn);
  $("process-new-drawing").disabled = b.awaiting;
  $("process-branch-select").disabled = b.awaiting;
  $("process-keep").disabled = b.awaiting || Boolean(capture) || Boolean(active.keeping) || b.renderedKey !== recipeKey(b);
  $("process-keep").title = $("process-keep").disabled
    ? "wait until this exact working recipe is on screen" : "keep the drawing on screen as an ordinary layer";
  $("process-play").disabled = !playTimer && (atEnd || b.awaiting);
  $("process-play").textContent = playTimer ? "Pause" : "Play";
  const reference = active.draft.reference;
  $("process-pin-reference").disabled = b.awaiting || Boolean(capture) || b.renderedKey !== recipeKey(b);
  $("process-compare").disabled = !reference;
  $("process-compare").setAttribute("aria-pressed", String(Boolean(active.draft.comparing)));
  $("process-compare").textContent = active.draft.comparing ? "Stop comparing" : "Compare";
  $("process-comparison-note").textContent = reference
    ? (active.draft.comparing ? `Left: working turn ${recipe(b).turns}. Right: pinned turn ${reference.recipe.turns}. Same frame scale.`
      : "Reference pinned. Compare it with the working drawing.")
    : "Pin a reading, then inspect another at the same frame scale.";
  $("process-pen-smoothing").value = String(b.penSmoothing ?? lastStrokeSmoothing(b));
  updateReadout("process-pen-smoothing", b.penSmoothing ?? lastStrokeSmoothing(b));
  renderNewDrawingState();
  syncExternal();
}

function boundaryLabel(value) {
  return ({ clip: "Clip", contain: "Turn inside", fit: "Overshoot + fit element" })[value] || value;
}

function loadPendingNewDrawing() {
  if (!active) return;
  const b = branch();
  const pending = active.draft.pendingNewDrawing ||= {
    boundary: b?.params.boundary ?? "clip",
    width: b?.params.width ?? 280,
    height: b?.params.height ?? 198,
    seed: b?.params.seed ?? 0,
  };
  $("process-boundary").value = pending.boundary;
  $("process-width").value = String(pending.width);
  $("process-height").value = String(pending.height);
  $("process-seed").value = String(pending.seed);
}

function pendingNewDrawing() {
  if (!active) return null;
  const pending = active.draft.pendingNewDrawing ||= {};
  pending.boundary = $("process-boundary").value;
  pending.width = clamp(Math.round(Number($("process-width").value) || 280), 40, 300);
  pending.height = clamp(Math.round(Number($("process-height").value) || 198), 40, 218);
  pending.seed = clamp(Math.round(Number($("process-seed").value) || 0), 0, 2147483647);
  return pending;
}

function renderNewDrawingState() {
  if (!active) return;
  const pending = pendingNewDrawing();
  const b = branch();
  if (!pending || !b) return;
  $("process-boundary-note").textContent =
    `Active: ${boundaryLabel(b.params.boundary ?? "clip")}. Selected for new drawing: ${boundaryLabel(pending.boundary)} — press New drawing.`;
}

function syncExternal() {
  const b = branch();
  if (active?.external && b) Object.assign(active.external, recipe(b));
}

function discardPendingControls() {
  const b = branch();
  if (!b || !controlsChanged(b)) return;
  remember();
  b.staged = effectiveControls(b);
  renderChrome();
}

function pinReference() {
  const b = branch();
  if (!active || !b || b.awaiting || b.renderedKey !== recipeKey(b)) return;
  active.draft.reference = { output: copy(b.rendered), recipe: recipe(b) };
  active.draft.comparing = false;
  renderComparison();
  renderChrome();
}

function toggleComparison() {
  if (!active?.draft.reference) return;
  cancelCapture();
  active.draft.comparing = !active.draft.comparing;
  renderComparison();
  renderChrome();
}

function stopComparison() {
  if (!active?.draft.comparing) return;
  active.draft.comparing = false;
  renderComparison();
}

export function toggleSecondReadingPlay() {
  if (!active) return;
  if (playTimer) { stopSecondReadingPlay(); return; }
  cancelCapture();
  const serial = ++playSerial;
  const tick = async () => {
    if (!active || serial !== playSerial || branch()?.turn >= 64) { stopSecondReadingPlay(); return; }
    try { await advance(); }
    catch (e) { stopSecondReadingPlay(); actions.oops(e); return; }
    if (active && serial === playSerial) playTimer = setTimeout(tick, 360);
  };
  playTimer = setTimeout(tick, 0);
  renderChrome();
}

export function stopSecondReadingPlay() {
  playSerial++;
  if (playTimer) clearTimeout(playTimer);
  playTimer = null;
  if (active) renderChrome();
}

function randomSeed() {
  return Math.floor(Math.random() * 2147483648);
}

function randomizePendingSeed() {
  const pending = pendingNewDrawing();
  if (!pending) return;
  let seed = randomSeed();
  if (seed === pending.seed) seed = (seed + 1) % 2147483648;
  pending.seed = seed;
  $("process-seed").value = String(seed);
  renderNewDrawingState();
}

function tryAnother() {
  const source = branch();
  if (!source || source.turn >= 64 || source.awaiting) return;
  const turn = nextTurn(source);
  const kinds = [...(controlsChanged(source) ? ["controls"] : []), "branch"];
  if (!canRecord(source, kinds, turn)) return;
  remember();
  stopSecondReadingPlay();
  cancelCapture();
  const next = forkPrefix(source, `Alternative ${active.draft.branches.length + 1}`);
  let seed = randomSeed();
  const priorSeed = [...source.params.events].reverse().find(e => e.kind === "branch" && e.turn <= source.turn)?.seed ?? 0;
  if (seed === priorSeed) seed = (seed + 1) % 2147483648;
  commitStagedControls(next, turn);
  replaceEvent(next, { kind: "branch", turn, seed });
  next.turn = next.furthest = turn;
  next.params.turns = turn;
  renderChrome();
  requestPreview();
}

function switchBranch() {
  if (!active) return;
  const selected = $("process-branch-select").value;
  stopSecondReadingPlay();
  cancelCapture();
  active.draft.active = selected;
  openSerial++; // immediately orphans the previous branch's response
  renderChrome();
  requestPreview();
}

function undo() {
  if (!active?.draft.undo.length) return;
  active.draft.redo.push(snapshot());
  restore(active.draft.undo.pop());
}

function redo() {
  if (!active?.draft.redo.length) return;
  active.draft.undo.push(snapshot());
  restore(active.draft.redo.pop());
}

async function keep() {
  const b = branch();
  if (!active || !b || b.awaiting || capture || active.keeping || b.renderedKey !== recipeKey(b)) return;
  stopSecondReadingPlay();
  const owner = active;
  owner.keeping = true;
  const exact = recipe(b);
  const key = recipeKey(b);
  const button = $("process-keep");
  button.disabled = true;
  try {
    const layer = active.onKeep
      ? await active.onKeep(copy(exact))
      : await api.post("/api/layers/generate", { module: active.mod.id, params: copy(exact) });
    if (!active || branch() !== b || recipeKey(b) !== key) return;
    b.kept = layer?.name || "layer";
    b.keptKey = key;
    const kept = $("process-kept-state");
    kept.hidden = false;
    kept.textContent = `Kept · ${b.kept}`;
    clearBenchError();
  } catch (e) {
    if (active === owner && branch() === b && recipeKey(b) === key) {
      // A lost write response may have created the layer. Do not present a
      // preview-style automatic retry for a potentially completed mutation.
      showBenchError(e);
    }
  }
  finally { owner.keeping = false; if (active) renderChrome(); }
}

function newDrawing() {
  const old = branch();
  if (!old || old.awaiting) return;
  const pending = pendingNewDrawing();
  const { width, height, seed, boundary } = pending;
  const controls = copy(ensureStaged(old));
  remember();
  stopSecondReadingPlay();
  cancelCapture();
  const params = copy(old.params);
  Object.assign(params, controls, { width, height, seed, boundary });
  params.turns = 0;
  params.events = [];
  const first = freshBranch(params, `branch-${++active.draft.serial}`, "New drawing");
  first.penSmoothing = old.penSmoothing ?? lastStrokeSmoothing(old);
  active.draft.branches = [first];
  active.draft.active = first.id;
  active.draft.pendingNewDrawing = { width, height, seed, boundary };
  $("process-kept-state").hidden = true;
  renderChrome();
  requestPreview();
}

function armCapture() {
  const b = branch();
  if (!b || b.turn >= 64 || b.awaiting) return;
  stopSecondReadingPlay();
  cancelCapture();
  stopComparison();
  capture = { armed: true, pointerId: null, points: [], line: null };
  $("process-your-turn").classList.add("on");
  $("process-your-turn").textContent = "Draw on the paper";
  $("process-canvas").classList.add("taking-turn");
  renderChrome();
}

function svgPoint(e) {
  const svg = $("process-canvas");
  const matrix = svg.getScreenCTM();
  if (!matrix) return null;
  const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(matrix.inverse());
  const b = branch();
  return [
    Number(clamp(p.x, b.params.boundary === "fit" ? -b.params.width*.5 : 0, Number(b.params.width ?? 280)*(b.params.boundary === "fit" ? 1.5 : 1)).toFixed(2)),
    Number(clamp(p.y, b.params.boundary === "fit" ? -b.params.height*.5 : 0, Number(b.params.height ?? 198)*(b.params.boundary === "fit" ? 1.5 : 1)).toFixed(2)),
  ];
}

function pointerDown(e) {
  if (!capture?.armed || capture.pointerId !== null || e.button !== 0) return;
  const p = svgPoint(e);
  if (!p) return;
  e.preventDefault();
  capture.pointerId = e.pointerId;
  capture.points = [p];
  const line = document.createElementNS(NS, "polyline");
  line.setAttribute("class", "draw-line draw-live process-live-stroke");
  line.setAttribute("points", `${p[0]},${p[1]}`);
  $("process-canvas").appendChild(line);
  capture.line = line;
  $("process-canvas").setPointerCapture(e.pointerId);
}

function pointerMove(e) {
  if (!capture || capture.pointerId !== e.pointerId) return;
  const p = svgPoint(e);
  const last = capture.points.at(-1);
  if (!p || (last && Math.hypot(p[0] - last[0], p[1] - last[1]) < .2)) return;
  const b = branch();
  const remaining = MAX_POINTS - pointCount(b.params.events.filter(e => e.turn <= b.turn));
  if (capture.points.length >= remaining) {
    cancelCapture();
    actions.oops(new Error("This stroke would exceed 20,000 captured points. It was not added; keep the drawing and start another."));
    return;
  }
  capture.points.push(p);
  capture.line.setAttribute("points", smoothLivePoints(capture.points, branch()?.penSmoothing ?? .6).map((q) => q.join(",")).join(" "));
}

function smoothLivePoints(points, amount) {
  if (points.length < 3 || amount <= 0) return points;
  return points.map((point, index) => {
    if (index === 0 || index === points.length - 1) return point;
    const before = points[index - 1], after = points[index + 1];
    const ax = point[0] - before[0], ay = point[1] - before[1];
    const bx = after[0] - point[0], by = after[1] - point[1];
    const lengths = Math.hypot(ax, ay) * Math.hypot(bx, by);
    // A sharp turn is intentional. Smooth only shallow, hand-drawn corners.
    if (!lengths || (ax * bx + ay * by) / lengths < .5) return point;
    const midpoint = [(before[0] + after[0]) / 2, (before[1] + after[1]) / 2];
    return [point[0] + (midpoint[0] - point[0]) * amount, point[1] + (midpoint[1] - point[1]) * amount];
  });
}

function pointerUp(e) {
  if (!capture || capture.pointerId !== e.pointerId) return;
  pointerMove(e);
  if (!capture) return;
  const points = capture.points;
  cancelCapture();
  if (points.length < 2) return;
  let b = branch();
  if (!b || b.turn >= 64) return;
  const turn = nextTurn(b);
  const kinds = [...(controlsChanged(b) ? ["controls"] : []), "stroke"];
  if (!canRecord(b, kinds, turn)) return;
  remember();
  if (hasFuture(b)) b = forkPrefix(b, "Human revision");
  commitStagedControls(b, turn);
  replaceEvent(b, { kind: "stroke", turn, points, smoothing: b.penSmoothing ?? lastStrokeSmoothing(b) });
  b.turn = turn;
  b.furthest = Math.max(b.furthest, turn);
  b.params.turns = turn;
  renderChrome();
  requestPreview();
}

function cancelCapture() {
  if (!capture) return;
  capture.line?.remove();
  const svg = $("process-canvas");
  if (capture.pointerId !== null && svg?.hasPointerCapture(capture.pointerId)) svg.releasePointerCapture(capture.pointerId);
  capture = null;
  $("process-your-turn")?.classList.remove("on");
  if ($("process-your-turn")) $("process-your-turn").textContent = "Your turn";
  $("process-canvas")?.classList.remove("taking-turn");
  if (active) renderChrome();
}

async function requestPreview() {
  const b = branch();
  if (!active || !b) return;
  const serial = ++openSerial;
  const branchId = b.id;
  const exact = recipe(b);
  const key = JSON.stringify(exact);
  b.awaiting = true;
  b.renderedKey = null;
  clearBenchError();
  renderChrome();
  try {
    const out = await api.post("/api/generators/preview", { module: active.mod.id, params: copy(exact) });
    if (!active || serial !== openSerial || active.draft.active !== branchId) return;
    b.awaiting = false;
    b.renderedKey = key;
    b.rendered = out;
    clearBenchError();
    drawPreview(out);
    renderProcessDetails(out.process || null);
  } catch (e) {
    if (!active || serial !== openSerial || active.draft.active !== branchId) return;
    b.awaiting = false;
    showBenchError(e, () => {
      if (active && active.draft.active === branchId && recipeKey(branch()) === key) requestPreview();
    });
  } finally {
    if (active && serial === openSerial && active.draft.active === branchId) renderChrome();
  }
}

function drawPreview(out) {
  const svg = $("process-canvas");
  const b = branch();
  drawOutput(svg, out, recipe(b), false);
  renderComparison();
}

function outputFrame(out, sourceRecipe) {
  const width = Number(out.width ?? sourceRecipe.width ?? 280);
  const height = Number(out.height ?? sourceRecipe.height ?? 198);
  return out.process?.work_frame || [0, 0, width, height];
}

function drawOutput(svg, out, sourceRecipe, sharedFrame) {
  const width = Number(out.width ?? sourceRecipe.width ?? 280);
  const height = Number(out.height ?? sourceRecipe.height ?? 198);
  const frame = sharedFrame || outputFrame(out, sourceRecipe);
  const [scale, dx, dy] = out.process?.element_transform || [1, 0, 0];
  svg.setAttribute("viewBox", frame.join(" "));
  svg.dataset.renderedRecipe = JSON.stringify(sourceRecipe);
  svg.style.aspectRatio = `${frame[2]} / ${frame[3]}`;
  svg.style.setProperty("--process-aspect", String(frame[2] / frame[3]));
  svg.replaceChildren();
  if (sourceRecipe.boundary === "fit") {
    const sheet = document.createElementNS(NS, "rect");
    sheet.setAttribute("class", "process-nominal-sheet");
    sheet.setAttribute("x", "0"); sheet.setAttribute("y", "0");
    sheet.setAttribute("width", String(width)); sheet.setAttribute("height", String(height));
    svg.appendChild(sheet);
  }
  for (const line of out.lines || []) {
    if (line.length < 2) continue;
    const el = document.createElementNS(NS, "polyline");
    el.setAttribute("points", line.map(([x, y]) => `${(x-dx)/scale},${(y-dy)/scale}`).join(" "));
    el.setAttribute("class", "draw-line");
    svg.appendChild(el);
  }
}

function unionFrame(a, b) {
  const x = Math.min(a[0], b[0]), y = Math.min(a[1], b[1]);
  const right = Math.max(a[0] + a[2], b[0] + b[2]);
  const bottom = Math.max(a[1] + a[3], b[1] + b[3]);
  return [x, y, right - x, bottom - y];
}

function renderComparison() {
  const stage = $("process-canvas")?.closest(".preview-stage");
  const referenceSvg = $("process-reference");
  const b = branch();
  const reference = active?.draft.reference;
  const comparing = Boolean(active?.draft.comparing && reference && b?.rendered
    && b.renderedKey === recipeKey(b));
  stage?.classList.toggle("comparing", comparing);
  referenceSvg.toggleAttribute('hidden', !comparing);
  if (!comparing) {
    referenceSvg.replaceChildren();
    if (b?.rendered && b.renderedKey === recipeKey(b)) drawOutput($("process-canvas"), b.rendered, recipe(b), false);
    return;
  }
  const currentRecipe = recipe(b);
  const frame = unionFrame(
    outputFrame(b.rendered, currentRecipe),
    outputFrame(reference.output, reference.recipe),
  );
  drawOutput($("process-canvas"), b.rendered, currentRecipe, frame);
  drawOutput(referenceSvg, reference.output, reference.recipe, frame);
}

function renderProcessDetails(process) {
  $("process-action").textContent = process?.action || "—";
  const targets = process?.target_passage_ids || [];
  $("process-targets").textContent = targets.length ? targets.join(", ") : "—";
  const telemetry = $("process-internal-telemetry");
  telemetry.replaceChildren();
  for (const [key, value] of Object.entries(process?.telemetry || {})) {
    const dt = document.createElement("dt"); dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = typeof value === "number" ? Number(value.toFixed(3)).toString() : String(value);
    telemetry.append(dt, dd);
  }
}
