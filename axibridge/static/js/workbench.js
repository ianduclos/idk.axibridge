// Generation workbench: a stateless playground popup (docs/IDEAS-oehlen-pass.md §0).
//
// Pick a generator + candidate effect stack, tweak with the same auto-forms,
// reroll seeds darkroom-style, and either save the result to the global scrap
// library (frozen SVG + recipe metadata, machine-level like the pen library)
// or import into the current project — fresh results as a LIVE generator
// layer (re-runnable, tweenable), saved scraps as baked SVG layers (exactly
// what you saw, however module code evolves). Server side is /api/workbench/
// preview, which touches no session/undo state; nothing plots from here.

import { api } from "./api.js";
import { S, actions } from "./main.js";
import { renderForm } from "./forms.js";

const $ = (id) => document.getElementById(id);

const wb = {
  module: null,
  params: {},
  effects: [],        // [{effect, enabled, params}] — same shape as layer stacks
  ok: false,          // last preview succeeded (guards save/import)
  busy: false, queued: false, timer: null,
};

export function initWorkbench() {
  if ($("workbench-modal")) return; // refreshAll re-inits tabs; build once
  const nav = $("tabs");
  const btn = document.createElement("button");
  btn.id = "workbench-open";
  btn.textContent = "⚗ Bench";
  btn.title = "Generation workbench — riff on generators outside the project";
  btn.onclick = open;
  nav.appendChild(btn);

  const modal = document.createElement("div");
  modal.id = "workbench-modal";
  modal.className = "modal-backdrop";
  modal.hidden = true;
  modal.innerHTML = `
    <div class="preview-modal wb-modal">
      <div class="preview-head">
        <h2>Workbench — generation playground (outside the project)</h2>
        <button id="wb-close" title="Close">✕</button>
      </div>
      <div class="wb-body">
        <div class="wb-controls form">
          <div class="field"><label><span>Generator</span></label>
            <div class="ctl">
              <select id="wb-source"></select>
              <button id="wb-reroll" title="Reroll every seed in the recipe">🎲</button>
            </div>
          </div>
          <div id="wb-form"></div>
          <div class="field"><label><span>Effects</span></label>
            <div class="ctl">
              <select id="wb-fx-add"></select>
              <button id="wb-fx-plus">+ add</button>
            </div>
          </div>
          <div id="wb-fx-list"></div>
        </div>
        <div class="wb-right">
          <div class="preview-stage wb-stage"><svg id="wb-svg"></svg></div>
          <div class="wb-actions">
            <span id="wb-status" class="hint"></span>
            <input id="wb-name" type="text" placeholder="scrap name…">
            <button id="wb-save" title="Freeze SVG + recipe to the global scrap library">Save scrap</button>
            <button id="wb-import" class="primary"
              title="Add to the project as a live generator layer (params editable)">Import live</button>
          </div>
          <div id="wb-scraps" class="wb-scraps"></div>
        </div>
      </div>
    </div>`;
  document.body.appendChild(modal);

  $("wb-close").onclick = close;
  modal.onclick = (e) => { if (e.target === modal) close(); };
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) { e.stopPropagation(); close(); }
  }, true);

  $("wb-source").onchange = () => selectModule($("wb-source").value);
  $("wb-reroll").onclick = rerollSeeds;
  $("wb-fx-plus").onclick = () => {
    const id = $("wb-fx-add").value;
    if (!id) return;
    wb.effects.push({ effect: id, enabled: true, params: {} });
    renderFx();
    schedule();
  };
  $("wb-save").onclick = saveScrap;
  $("wb-import").onclick = importLive;
}

function open() {
  fillPickers();
  drawSheet();  // blank paper immediately — the stage is never a dark void
  if (!wb.module) {
    // default to a self-contained generator — image-driven ones 400 without an asset
    const standalone = S.state.modules.sources.find(
      (m) => !Object.values(m.schema.properties || {}).some((s) => s.format === "asset"));
    selectModule((standalone || S.state.modules.sources[0])?.id);
  } else renderParamForm();
  renderFx();
  updateActions();
  $("workbench-modal").hidden = false;
  refreshScraps();
  schedule(0);
}

// blank sheet at bed proportions; optional message rendered ON the paper
function drawSheet(message) {
  const svg = $("wb-svg");
  svg.innerHTML = "";
  const w = 300, h = 218;
  svg.setAttribute("viewBox", `-5 -5 ${w + 10} ${h + 10}`);
  const sheet = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  sheet.setAttribute("x", 0); sheet.setAttribute("y", 0);
  sheet.setAttribute("width", w); sheet.setAttribute("height", h);
  sheet.setAttribute("class", "wb-sheet");
  svg.appendChild(sheet);
  if (message) {
    const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", w / 2); t.setAttribute("y", h / 2);
    t.setAttribute("class", "wb-msg");
    t.textContent = message;
    svg.appendChild(t);
  }
}

function updateActions() {
  $("wb-save").disabled = !wb.ok;
  $("wb-import").disabled = !wb.ok;
}

function close() { $("workbench-modal").hidden = true; }

function fillPickers() {
  const src = $("wb-source");
  src.innerHTML = "";
  for (const m of S.state.modules.sources) {
    const o = document.createElement("option");
    o.value = m.id; o.textContent = m.label;
    src.appendChild(o);
  }
  if (wb.module) src.value = wb.module;
  const fx = $("wb-fx-add");
  fx.innerHTML = "";
  for (const m of S.state.modules.effects) {
    const o = document.createElement("option");
    o.value = m.id; o.textContent = m.label;
    if (m.unavailable) { o.disabled = true; o.textContent += " (unavailable)"; }
    fx.appendChild(o);
  }
}

function sourceModule() {
  return S.state.modules.sources.find((m) => m.id === wb.module);
}

function selectModule(id) {
  if (!id) return;
  wb.module = id;
  wb.params = {};
  const m = sourceModule();
  for (const [k, spec] of Object.entries(m.schema.properties || {})) {
    if (spec.default !== undefined) wb.params[k] = spec.default;
  }
  $("wb-source").value = id;
  renderParamForm();
  schedule();
}

function renderParamForm() {
  const m = sourceModule();
  if (m) renderForm($("wb-form"), m.schema, wb.params, () => schedule(), { onLive: () => schedule() });
}

function renderFx() {
  const list = $("wb-fx-list");
  list.innerHTML = "";
  wb.effects.forEach((step, i) => {
    const mod = S.state.modules.effects.find((m) => m.id === step.effect);
    const box = document.createElement("div");
    box.className = "wb-fx-step form";
    const head = document.createElement("div");
    head.className = "wb-fx-head";
    const on = document.createElement("input");
    on.type = "checkbox"; on.checked = step.enabled;
    on.title = "Enable/disable this step";
    on.onchange = () => { step.enabled = on.checked; schedule(); };
    const name = document.createElement("strong");
    name.textContent = mod?.label || step.effect;
    const del = document.createElement("button");
    del.textContent = "✕"; del.title = "Remove step";
    del.onclick = () => { wb.effects.splice(i, 1); renderFx(); schedule(); };
    head.append(on, name, del);
    box.appendChild(head);
    if (mod) {
      const form = document.createElement("div");
      box.appendChild(form);
      // seed defaults so the recipe round-trips deterministically
      for (const [k, spec] of Object.entries(mod.schema.properties || {})) {
        if (step.params[k] === undefined && spec.default !== undefined) step.params[k] = spec.default;
      }
      renderForm(form, mod.schema, step.params, () => schedule(), { onLive: () => schedule() });
    }
    list.appendChild(box);
  });
}

function rerollSeeds() {
  let hit = false;
  const roll = (schema, params) => {
    const seed = schema.properties?.seed;
    if (!seed) return;
    const hi = seed.maximum ?? 99999;
    params.seed = Math.floor(Math.random() * (hi + 1));
    hit = true;
  };
  const m = sourceModule();
  if (m) roll(m.schema, wb.params);
  for (const step of wb.effects) {
    const mod = S.state.modules.effects.find((x) => x.id === step.effect);
    if (mod) roll(mod.schema, step.params);
  }
  if (!hit) { $("wb-status").textContent = "no seed params in this recipe"; return; }
  renderParamForm();
  renderFx();
  schedule(0);
}

function recipe() {
  return { module: wb.module, params: wb.params, effects: wb.effects };
}

// debounced + serialized: at most one preview request in flight
function schedule(delay = 150) {
  clearTimeout(wb.timer);
  wb.timer = setTimeout(run, delay);
}

async function run() {
  if (wb.busy) { wb.queued = true; return; }
  wb.busy = true;
  $("wb-status").textContent = "generating…";
  try {
    const p = await api.post("/api/workbench/preview", recipe());
    drawPreview(p);
    wb.ok = true;
    $("wb-status").textContent =
      `${p.points} pts${p.decimated ? " (preview decimated)" : ""}`;
  } catch (e) {
    wb.ok = false;
    drawSheet(e.message);  // failure stays legible on the paper itself
    $("wb-status").textContent = e.message;
  } finally {
    updateActions();
    wb.busy = false;
    if (wb.queued) { wb.queued = false; schedule(0); }
  }
}

function drawPreview(p) {
  const svg = $("wb-svg");
  svg.innerHTML = "";
  let { width: w, height: h } = p;
  if (!w || !h) {
    let mx = 0, my = 0;
    for (const line of p.lines) for (const [x, y] of line) { mx = Math.max(mx, x); my = Math.max(my, y); }
    w = Math.max(mx, 10); h = Math.max(my, 10);
  }
  const pad = Math.max(w, h) * 0.03;
  svg.setAttribute("viewBox", `${-pad} ${-pad} ${w + 2 * pad} ${h + 2 * pad}`);
  const sheet = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  sheet.setAttribute("x", 0); sheet.setAttribute("y", 0);
  sheet.setAttribute("width", w); sheet.setAttribute("height", h);
  sheet.setAttribute("class", "wb-sheet");
  svg.appendChild(sheet);
  for (const line of p.lines) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    el.setAttribute("points", line.map(([x, y]) => `${x},${y}`).join(" "));
    el.setAttribute("class", "wb-line");
    svg.appendChild(el);
  }
}

async function saveScrap() {
  if (!wb.ok) return;
  try {
    await api.post("/api/scraps", { ...recipe(), name: $("wb-name").value });
    $("wb-name").value = "";
    await refreshScraps();
  } catch (e) { actions.oops(e); }
}

async function importLive() {
  if (!wb.ok) return;
  try {
    const layer = await api.post("/api/layers/generate",
      { module: wb.module, params: wb.params });
    if (wb.effects.length) {
      await api.patch(`/api/layers/${layer.id}`, { effects: wb.effects });
    }
    await actions.refreshProject();
    await actions.refreshResolved();
    $("wb-status").textContent = `imported as layer “${layer.name}”`;
  } catch (e) { actions.oops(e); }
}

async function refreshScraps() {
  const box = $("wb-scraps");
  let scraps = [];
  try { scraps = (await api.get("/api/scraps")).scraps; }
  catch (e) { actions.oops(e); return; }
  box.innerHTML = "";
  for (const s of scraps) {
    const card = document.createElement("div");
    card.className = "wb-scrap";
    const img = document.createElement("img");
    img.src = `/api/scraps/${s.id}.svg`;
    img.loading = "lazy";
    img.title = `${s.module} · ${s.points} pts · ${s.created}`;
    const name = document.createElement("span");
    name.textContent = s.name;
    const row = document.createElement("div");
    row.className = "wb-scrap-row";
    const imp = document.createElement("button");
    imp.textContent = "Import";
    imp.title = "Insert into the project as a baked SVG layer (frozen geometry)";
    imp.onclick = async () => {
      try {
        await api.post(`/api/scraps/${s.id}/import`);
        await actions.refreshProject();
        await actions.refreshResolved();
        $("wb-status").textContent = `imported scrap “${s.name}”`;
      } catch (e) { actions.oops(e); }
    };
    const load = document.createElement("button");
    load.textContent = "Recipe";
    load.title = "Load this scrap's generator + effects back into the workbench";
    load.onclick = () => {
      wb.module = s.module;
      wb.params = { ...s.params };
      wb.effects = s.effects.map((e) => ({ enabled: true, ...e, params: { ...e.params } }));
      fillPickers();
      renderParamForm();
      renderFx();
      schedule(0);
    };
    const del = document.createElement("button");
    del.textContent = "✕";
    del.title = "Delete scrap (library-wide, not undoable)";
    del.onclick = async () => {
      try { await api.del(`/api/scraps/${s.id}`); await refreshScraps(); }
      catch (e) { actions.oops(e); }
    };
    row.append(imp, load, del);
    card.append(img, name, row);
    box.appendChild(card);
  }
  if (!scraps.length) {
    box.innerHTML = '<span class="hint">no scraps yet — save one to start a library</span>';
  }
}
