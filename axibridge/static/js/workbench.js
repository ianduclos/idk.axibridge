// Generation workbench: a stateless playground popup (docs/IDEAS-oehlen-pass.md §0).
//
// Pick a generator + candidate effect stack, tweak with the same auto-forms,
// reroll seeds darkroom-style, and either save the result to the global scrap
// library (frozen SVG + recipe metadata, machine-level like the pen library)
// or import into the current project — fresh results as a LIVE generator
// layer (re-runnable, tweenable), saved scraps as baked SVG layers (exactly
// what you saw, however module code evolves). Server side is /api/workbench/
// preview, which touches no session/undo state; nothing plots from here.
//
// ✏ Draw mode: pointer strokes on the stage (mm via the viewBox) become the
// recipe's base instead of a generator — shaped by a drawing mode (smooth,
// steps, zigzag, stitch), run through the same effect stack, saved/imported
// through the same scrap machinery (module "drawing", geometry frozen).

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
  draw: { on: false, mode: "smooth", strokes: [], drag: null }, // raw strokes, mm
};

const BED = { w: 300, h: 218 };

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
          <div class="wb-drawbar">
            <button id="wb-draw" title="Draw on the sheet with the pointer">✏ Draw</button>
            <select id="wb-draw-mode" title="Drawing mode — re-shapes every stroke, not just new ones">
              <option value="raw">raw</option>
              <option value="smooth" selected>smooth</option>
              <option value="steps">steps</option>
              <option value="zigzag">zigzag</option>
              <option value="stitch">stitch</option>
            </select>
            <button id="wb-draw-undo" title="Undo last stroke">↩</button>
            <button id="wb-draw-clear" title="Clear the drawing — back to the generator">✕</button>
            <span id="wb-draw-hint" class="hint"></span>
          </div>
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

  $("wb-draw").onclick = () => { wb.draw.on = !wb.draw.on; updateDrawUI(); };
  $("wb-draw-mode").onchange = () => {
    wb.draw.mode = $("wb-draw-mode").value;
    updateDrawUI();
    if (wb.draw.strokes.length) schedule(0);  // re-shape existing strokes too
  };
  $("wb-draw-undo").onclick = () => {
    wb.draw.strokes.pop();
    updateDrawUI();
    schedule(0);
  };
  $("wb-draw-clear").onclick = () => {
    wb.draw.strokes = [];
    updateDrawUI();
    schedule(0);
  };
  initDrawInput($("wb-svg"));
}

// ---- mouse drawing: pointer input on the stage (mm via the viewBox) ----------------

function mmPoint(svg, evt) {
  const p = new DOMPoint(evt.clientX, evt.clientY).matrixTransform(svg.getScreenCTM().inverse());
  return [Math.min(BED.w, Math.max(0, p.x)), Math.min(BED.h, Math.max(0, p.y))];
}

function initDrawInput(svg) {
  let live = null; // in-progress overlay polyline (survives until preview redraw)
  svg.addEventListener("pointerdown", (e) => {
    if (!wb.draw.on || e.button !== 0) return;
    e.preventDefault();
    svg.setPointerCapture(e.pointerId);
    wb.draw.drag = [mmPoint(svg, e)];
    live = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    live.setAttribute("class", "wb-line wb-draw-live");
    svg.appendChild(live);
  });
  svg.addEventListener("pointermove", (e) => {
    if (!wb.draw.drag) return;
    const p = mmPoint(svg, e);
    const last = wb.draw.drag[wb.draw.drag.length - 1];
    if (Math.hypot(p[0] - last[0], p[1] - last[1]) < 1.0) return; // ~1 mm spacing
    wb.draw.drag.push(p);
    if (live) live.setAttribute("points", wb.draw.drag.map(([x, y]) => `${x},${y}`).join(" "));
  });
  const finish = () => {
    if (!wb.draw.drag) return;
    wb.draw.strokes.push(wb.draw.drag);
    wb.draw.drag = null;
    live = null;
    updateDrawUI();
    schedule(0);  // the server preview redraws everything, shaped
  };
  svg.addEventListener("pointerup", finish);
  svg.addEventListener("pointercancel", finish);
}

function updateDrawUI() {
  $("wb-draw").classList.toggle("active", wb.draw.on);
  $("wb-svg").closest(".wb-stage").classList.toggle("wb-drawing", wb.draw.on);
  const n = wb.draw.strokes.length;
  $("wb-draw-undo").disabled = !n;
  $("wb-draw-clear").disabled = !n;
  $("wb-draw-hint").textContent =
    n ? `${n} stroke${n > 1 ? "s" : ""} · ${wb.draw.mode} — drawing replaces the generator`
      : (wb.draw.on ? "drag on the sheet to draw" : "");
}

// ---- drawing modes: shape raw strokes into the machine vocabulary ------------------
// One raw stroke → one or more shaped paths; shaping is functional (raw strokes
// are kept), so a mode change re-shapes the whole drawing.

function chaikin(pts) {
  if (pts.length < 3) return pts;
  const out = [pts[0]];
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i], [x1, y1] = pts[i + 1];
    out.push([x0 * 0.75 + x1 * 0.25, y0 * 0.75 + y1 * 0.25]);
    out.push([x0 * 0.25 + x1 * 0.75, y0 * 0.25 + y1 * 0.75]);
  }
  out.push(pts[pts.length - 1]);
  return out;
}

// even resampling along arc length — zigzag/stitch need constant rhythm
function resample(pts, step) {
  if (pts.length < 2) return pts;
  const out = [pts[0]];
  let acc = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    let [x0, y0] = pts[i];
    const [x1, y1] = pts[i + 1];
    let seg = Math.hypot(x1 - x0, y1 - y0);
    while (acc + seg >= step) {
      const t = (step - acc) / seg;
      const nx = x0 + (x1 - x0) * t, ny = y0 + (y1 - y0) * t;
      out.push([nx, ny]);
      x0 = nx; y0 = ny;
      seg = Math.hypot(x1 - x0, y1 - y0);
      acc = 0;
    }
    acc += seg;
  }
  out.push(pts[pts.length - 1]);
  return out;
}

// Manhattan quantize — the client-side twin of the bitmap effect's lines math
function manhattan(pts, cellMm) {
  const snap = (v) => Math.round(v / cellMm) * cellMm;
  const out = [[snap(pts[0][0]), snap(pts[0][1])]];
  const push = (p) => {
    const l = out[out.length - 1];
    if (l[0] !== p[0] || l[1] !== p[1]) out.push(p);
  };
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
    const xFirst = Math.abs(bx - ax) >= Math.abs(by - ay);
    const n = Math.max(1, Math.ceil(Math.hypot(bx - ax, by - ay) / (cellMm / 3)));
    for (let k = 1; k <= n; k++) {
      const t = k / n;
      const qx = snap(ax + (bx - ax) * t), qy = snap(ay + (by - ay) * t);
      const [px, py] = out[out.length - 1];
      if (qx === px && qy === py) continue;
      if (qx !== px && qy !== py) push(xFirst ? [qx, py] : [px, qy]);
      push([qx, qy]);
    }
  }
  return out;
}

function zigzag(pts, step, amp) {
  const rs = resample(pts, step);
  if (rs.length < 3) return rs;
  return rs.map((p, i) => {
    if (i === 0 || i === rs.length - 1) return p;
    const [ax, ay] = rs[i - 1], [bx, by] = rs[i + 1];
    const len = Math.hypot(bx - ax, by - ay) || 1;
    const s = (i % 2 ? 1 : -1) * amp;
    return [p[0] + (-(by - ay) / len) * s, p[1] + ((bx - ax) / len) * s];
  });
}

function stitch(pts, dash, gap) {
  const rs = resample(pts, 0.5);
  const paths = [];
  let cur = [];
  let s = 0;
  for (let i = 0; i < rs.length; i++) {
    if (i) s += Math.hypot(rs[i][0] - rs[i - 1][0], rs[i][1] - rs[i - 1][1]);
    if (s % (dash + gap) < dash) cur.push(rs[i]);
    else if (cur.length > 1) { paths.push(cur); cur = []; }
    else cur = [];
  }
  if (cur.length > 1) paths.push(cur);
  return paths.length ? paths : [rs];
}

const DRAW_MODES = {
  raw:    (pts) => [pts],
  smooth: (pts) => [chaikin(chaikin(chaikin(pts)))],
  steps:  (pts) => [manhattan(pts, 3.0)],
  zigzag: (pts) => [zigzag(pts, 3.0, 2.0)],
  stitch: (pts) => stitch(pts, 3.0, 2.0),
};

function shapedPaths() {
  const clamp = ([x, y]) => [
    Math.round(Math.min(BED.w, Math.max(0, x)) * 100) / 100,
    Math.round(Math.min(BED.h, Math.max(0, y)) * 100) / 100,
  ];
  const out = [];
  for (const stroke of wb.draw.strokes) {
    for (const path of DRAW_MODES[wb.draw.mode](stroke)) out.push(path.map(clamp));
  }
  return out;
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
  updateDrawUI();
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
  if (wb.draw.strokes.length) {
    // a drawing replaces the generator as the base; the effect stack still applies
    return { module: "drawing", params: {}, effects: wb.effects, paths: shapedPaths() };
  }
  return { module: wb.module, params: wb.params, effects: wb.effects };
}

// debounced + serialized: at most one preview request in flight
function schedule(delay = 150) {
  clearTimeout(wb.timer);
  wb.timer = setTimeout(run, delay);
}

async function run() {
  if (wb.draw.drag) return; // mid-stroke: pointerup reschedules, keep the overlay
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
    if (wb.draw.strokes.length) {
      // drawings have no generator to re-run: freeze to a scrap, then reuse
      // the scrap-import path — arrives as a baked SVG layer
      const scrap = await api.post("/api/scraps",
        { ...recipe(), name: $("wb-name").value || "drawing" });
      await api.post(`/api/scraps/${scrap.id}/import`);
      await actions.refreshProject();
      await actions.refreshResolved();
      await refreshScraps();
      $("wb-status").textContent = `imported drawing “${scrap.name}” (baked layer; kept as scrap)`;
      return;
    }
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
      wb.effects = s.effects.map((e) => ({ enabled: true, ...e, params: { ...e.params } }));
      if (s.module === "drawing") {
        // a drawing's geometry is frozen in the SVG — only its stack reloads
        renderFx();
        $("wb-status").textContent = "drawing scrap — effects loaded; geometry stays frozen (use Import)";
        return;
      }
      wb.module = s.module;
      wb.params = { ...s.params };
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
