// Compose tab: sources (generate / upload), the layer list (z-order,
// visibility, pen, occlusion), and the selected layer's detail editor
// (transform numerics, effect stack, generator params).

import { api } from "./api.js";
import { renderForm } from "./forms.js";
import { S, actions } from "./main.js";
import { mul, translate, rotate, scale, matToObj, objToMat } from "./canvas.js";

const $ = (id) => document.getElementById(id);
let genParams = {};
const expandedSteps = new Set(); // "layerId:index" — effect steps open in the UI

export function initComposeTab() {
  $("tab-compose").innerHTML = `
    <div class="panel">
      <h2>Add layer</h2>
      <div class="row">
        <select id="gen-select"></select>
        <button id="btn-generate" class="primary">Generate</button>
      </div>
      <div id="gen-form" class="form"></div>
      <div class="row" style="margin-top:10px">
        <input type="file" id="svg-file" accept=".svg,image/svg+xml" style="flex:1">
      </div>
      <div class="row">
        <label>flatten tol.</label>
        <input type="number" id="quant" value="0.1" min="0.01" max="5" step="0.01" style="width:5em">
        <span class="hint">mm</span>
        <button id="btn-upload" class="primary">Upload</button>
      </div>
      <div class="hint">An uploaded SVG contributes its layers as layers.</div>
      <div class="row" style="margin-top:10px">
        <input type="file" id="asset-file" accept="image/png,image/jpeg" style="flex:1">
        <button id="btn-asset">Add depth map</button>
      </div>
      <div class="hint" id="asset-list"></div>
    </div>
    <div class="panel">
      <h2>Layers <span class="hint">(top of list = drawn on top / occludes below)</span></h2>
      <div id="layer-list"></div>
    </div>
    <div class="panel" id="layer-detail-panel" hidden>
      <h2>Layer: <span id="detail-name"></span></h2>
      <div id="layer-detail"></div>
    </div>`;

  const sel = $("gen-select");
  for (const m of S.state.modules.sources) {
    const o = document.createElement("option");
    o.value = m.id; o.textContent = m.label; o.title = m.description;
    sel.appendChild(o);
  }
  sel.onchange = renderGenForm;
  renderGenForm();

  $("btn-generate").onclick = async () => {
    try {
      await api.post("/api/layers/generate", { module: sel.value, params: genParams });
      await actions.refreshProject();
      await actions.refreshResolved();
    } catch (e) { actions.oops(e); }
  };

  $("btn-upload").onclick = async () => {
    const file = $("svg-file").files[0];
    if (!file) return actions.oops(new Error("choose an SVG file first"));
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.upload(`/api/layers/upload?quantization_mm=${Number($("quant").value) || 0.1}`, fd);
      await actions.refreshProject();
      await actions.refreshResolved();
    } catch (e) { actions.oops(e); }
  };

  $("btn-asset").onclick = async () => {
    const file = $("asset-file").files[0];
    if (!file) return actions.oops(new Error("choose a PNG/JPEG first"));
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api.upload("/api/assets", fd);
      S.state.assets = r.assets;
      renderAssetList();
      renderLayerDetail(); // asset selects in effect forms pick up the new name
    } catch (e) { actions.oops(e); }
  };
  renderAssetList();
}

function renderAssetList() {
  const el = $("asset-list");
  if (!el) return;
  const names = (S.state.assets || []).map((a) => a.name ?? a);
  el.textContent = names.length
    ? `image assets: ${names.join(", ")} — used by "Depth map displace" and "Image hatch"`
    : "Image assets feed the depth-displace effect and the image-hatch generator.";
}

function renderGenForm() {
  const m = S.state.modules.sources.find((x) => x.id === $("gen-select").value);
  if (!m) return;
  genParams = { ...m.defaults };
  renderForm($("gen-form"), m.schema, genParams, () => {});
}

// ---- layer list ------------------------------------------------------------

export function renderLayerList() {
  const wrap = $("layer-list");
  if (!wrap) return;
  wrap.innerHTML = "";
  const layers = S.state.project.layers;
  const resolvedById = Object.fromEntries((S.resolved?.layers || []).map((l) => [l.id, l]));
  // top layer first in the list
  [...layers].reverse().forEach((layer) => {
    const r = resolvedById[layer.id];
    const row = document.createElement("div");
    row.className = "layer-row" + (S.selection.includes(layer.id) ? " selected" : "");

    const eye = btn(layer.visible ? "👁" : "—", "visible", () =>
      actions.patchLayer(layer.id, { visible: !layer.visible }));
    eye.className = "eye" + (layer.visible ? "" : " off");

    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = r?.color || "#26241f";
    swatch.title = penName(layer.pen_id);

    const name = document.createElement("span");
    name.className = "lname";
    name.textContent = layer.name;
    name.title = `${layer.name} — double-click to rename`;
    name.ondblclick = (e) => {
      e.stopPropagation();
      const v = prompt("Layer name", layer.name);
      if (v) actions.patchLayer(layer.id, { name: v });
    };

    const est = document.createElement("span");
    est.className = "est";
    est.textContent = r?.stats?.est_s ? fmtTime(r.stats.est_s) : "";
    est.title = "estimated plot time for this layer's resolved geometry";

    const occ = btn("◼", "occluder: masks layers below", () =>
      actions.patchLayer(layer.id, { occluder: !layer.occluder }));
    occ.className = "occ " + (layer.occluder ? "on" : "off");

    const up = btn("↑", "raise (towards top/occluding)", () => move(layer.id, +1));
    const down = btn("↓", "lower", () => move(layer.id, -1));
    const dup = btn("⧉", "duplicate layer", async () => {
      try {
        await api.post(`/api/layers/${layer.id}/duplicate`);
        await actions.refreshProject();
        await actions.refreshResolved();
      } catch (e) { actions.oops(e); }
    });
    // two-click delete — native confirm() dialogs are blockable/suppressible
    // by the browser, which reads as "the button does nothing"
    const del = btn("✕", "delete layer (click twice)", async () => {
      if (!del.dataset.armed) {
        del.dataset.armed = "1";
        del.textContent = "sure?";
        del.style.color = "var(--rust)";
        setTimeout(() => {
          delete del.dataset.armed;
          del.textContent = "✕";
          del.style.color = "";
        }, 2500);
        return;
      }
      try {
        await api.del(`/api/layers/${layer.id}`);
        await actions.refreshProject();
        await actions.refreshResolved();
      } catch (e) { actions.oops(e); }
    });

    row.append(eye, swatch, name, est, occ, up, down, dup, del);
    row.onclick = (e) => {
      if (e.target.tagName === "BUTTON") return;
      actions.setSelection(e.shiftKey ? toggle(S.selection, layer.id) : [layer.id]);
    };
    wrap.appendChild(row);
  });
  renderLayerDetail();
}

function toggle(arr, id) {
  return arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id];
}

function btn(txt, title, fn) {
  const b = document.createElement("button");
  b.textContent = txt;
  b.title = title;
  b.onclick = (e) => { e.stopPropagation(); fn(); };
  return b;
}

async function move(id, dir) {
  const ids = S.state.project.layers.map((l) => l.id);
  const i = ids.indexOf(id);
  const j = i + dir;
  if (j < 0 || j >= ids.length) return;
  [ids[i], ids[j]] = [ids[j], ids[i]];
  try {
    await api.post("/api/layers/order", { ids });
    await actions.refreshProject();
    await actions.refreshResolved();
  } catch (e) { actions.oops(e); }
}

function penName(penId) {
  const pen = (S.state.pens || []).find((p) => p.id === penId);
  return pen ? pen.name : "no pen assigned";
}

function fmtTime(s) {
  const m = Math.floor(s / 60);
  return m >= 1 ? `${m}m${Math.round(s % 60)}s` : `${s.toFixed(0)}s`;
}

// ---- selected layer detail ---------------------------------------------------

export function renderLayerDetail() {
  const panel = $("layer-detail-panel");
  const wrap = $("layer-detail");
  if (!panel || !wrap) return;
  if (S.selection.length === 2) { // pair selected: offer interpolation
    const [a, b] = S.selection.map((id) => S.state.project.layers.find((l) => l.id === id));
    if (a && b) {
      panel.hidden = false;
      $("detail-name").textContent = `${a.name} + ${b.name}`;
      wrap.innerHTML = `
        <div class="row"><button id="btn-tween" class="primary">⇄ Create interpolation layer</button></div>
        <div class="hint">A new layer that morphs between the two selected layers (t slider,
        sweep stamping). Needs the same generator on both sides, or identical path structure
        (what "duplicate layer" gives you). Edits to either layer update the morph live.</div>`;
      wrap.querySelector("#btn-tween").onclick = async () => {
        try {
          await api.post("/api/layers/tween", { a: a.id, b: b.id });
          await actions.refreshProject();
          await actions.refreshResolved();
        } catch (e) { actions.oops(e); }
      };
      return;
    }
  }
  const layer = S.state.project.layers.find((l) => l.id === S.selection[0]);
  if (S.selection.length !== 1 || !layer) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  $("detail-name").textContent = layer.name;
  wrap.innerHTML = "";

  // -- placement numerics (decomposed from the matrix; re-composed on edit)
  const t = layer.transform;
  const sc = Math.hypot(t.a, t.b) || 1;
  const rot = Math.atan2(t.b, t.a) * 180 / Math.PI;
  const place = document.createElement("div");
  place.innerHTML = `
    <h3>Placement</h3>
    <div class="row">
      <label>x</label><input type="number" step="0.5" id="tf-x" value="${t.e.toFixed(1)}" style="width:5.5em">
      <label>y</label><input type="number" step="0.5" id="tf-y" value="${t.f.toFixed(1)}" style="width:5.5em">
      <label>scale</label><input type="number" step="0.05" id="tf-s" value="${sc.toFixed(2)}" style="width:5em">
      <label>rot°</label><input type="number" step="1" id="tf-r" value="${rot.toFixed(0)}" style="width:5em">
    </div>`;
  wrap.appendChild(place);
  const commitPlacement = () => {
    const x = +$("tf-x").value, y = +$("tf-y").value;
    const s = Math.max(+$("tf-s").value, 0.02), r = (+$("tf-r").value) * Math.PI / 180;
    const m = mul(translate(x, y), mul(rotate(r), scale(s, s)));
    actions.patchLayer(layer.id, { transform: matToObj(m) });
  };
  for (const id of ["tf-x", "tf-y", "tf-s", "tf-r"]) $(id).onchange = commitPlacement;

  // -- pen + occlusion
  const occ = document.createElement("div");
  occ.innerHTML = `
    <h3>Pen & occlusion</h3>
    <div class="row">
      <label>pen</label>
      <select id="ld-pen"><option value="">— none —</option></select>
    </div>
    <div class="row">
      <label><input type="checkbox" id="ld-occluder" ${layer.occluder ? "checked" : ""}> occluder (masks below)</label>
      <label><input type="checkbox" id="ld-receives" ${layer.receives_occlusion ? "checked" : ""}> receives occlusion</label>
    </div>
    <div class="row">
      <label>margin</label>
      <input type="number" id="ld-margin" value="${layer.occlusion_margin_mm}" step="0.25" min="-20" max="20" style="width:5.5em">
      <span class="hint">mm — + opens a gap, − bleeds under</span>
    </div>`;
  wrap.appendChild(occ);
  const penSel = occ.querySelector("#ld-pen");
  for (const pen of S.state.pens || []) {
    const o = document.createElement("option");
    o.value = pen.id;
    o.textContent = `${pen.name} (⌀${pen.barrel_diameter_mm})`;
    if (pen.id === layer.pen_id) o.selected = true;
    penSel.appendChild(o);
  }
  penSel.onchange = () => actions.patchLayer(layer.id, { pen_id: penSel.value || null });
  occ.querySelector("#ld-occluder").onchange = (e) => actions.patchLayer(layer.id, { occluder: e.target.checked });
  occ.querySelector("#ld-receives").onchange = (e) => actions.patchLayer(layer.id, { receives_occlusion: e.target.checked });
  occ.querySelector("#ld-margin").onchange = (e) => actions.patchLayer(layer.id, { occlusion_margin_mm: +e.target.value });

  // -- effect stack
  const fx = document.createElement("div");
  fx.innerHTML = `<h3>Effects <span class="hint">(paper-space, non-destructive)</span></h3>
    <div class="row">
      <select id="fx-select"></select><button id="fx-add">＋ Add</button>
      <button id="fx-consolidate" title="Bake transform + effects into the source geometry (undoable; regenerate also reverts a generated layer)">⤓ Consolidate</button>
    </div>
    <div id="fx-steps"></div>`;
  wrap.appendChild(fx);
  fx.querySelector("#fx-consolidate").onclick = async () => {
    try {
      await api.post(`/api/layers/${layer.id}/consolidate`);
      await actions.refreshProject();
      await actions.refreshResolved();
      renderLayerDetail();
    } catch (e) { actions.oops(e); }
  };
  const fxSel = fx.querySelector("#fx-select");
  for (const m of S.state.modules.effects) {
    const o = document.createElement("option");
    o.value = m.id; o.textContent = m.label; o.title = m.description;
    if (!m.available) { o.disabled = true; o.textContent += " (unavailable)"; }
    fxSel.appendChild(o);
  }
  fx.querySelector("#fx-add").onclick = () => {
    const mod = S.state.modules.effects.find((m) => m.id === fxSel.value);
    if (!mod) return;
    expandedSteps.add(`${layer.id}:${layer.effects.length}`); // open the new step
    const effects = [...layer.effects, { effect: mod.id, enabled: true, params: { ...mod.defaults } }];
    actions.patchLayer(layer.id, { effects });
  };
  const steps = fx.querySelector("#fx-steps");
  layer.effects.forEach((step, i) => {
    const mod = S.state.modules.effects.find((m) => m.id === step.effect);
    const key = `${layer.id}:${i}`;
    const open = expandedSteps.has(key);
    const div = document.createElement("div");
    div.className = "step" + (step.enabled ? "" : " disabled");
    const head = document.createElement("div");
    head.className = "head";
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = step.enabled;
    cb.onchange = () => commitEffects(layer, i, { enabled: cb.checked });
    const nm = document.createElement("span");
    nm.className = "name";
    nm.textContent = `${open ? "▾" : "▸"} ${mod?.label || step.effect}`;
    nm.title = "click to expand / collapse";
    nm.onclick = () => {
      open ? expandedSteps.delete(key) : expandedSteps.add(key);
      renderLayerDetail();
    };
    const up = btn("↑", "earlier", () => swapEffects(layer, i, i - 1));
    const dn = btn("↓", "later", () => swapEffects(layer, i, i + 1));
    const rm = btn("✕", "remove", () => {
      const effects = layer.effects.filter((_, j) => j !== i);
      actions.patchLayer(layer.id, { effects });
    });
    head.append(cb, nm, up, dn, rm);
    div.appendChild(head);
    if (open && mod) {
      const form = document.createElement("div");
      form.className = "form";
      const values = { ...mod.defaults, ...step.params };
      renderForm(form, mod.schema, values, () => commitEffects(layer, i, { params: values }));
      div.appendChild(form);
    }
    steps.appendChild(div);
  });

  // -- interpolation controls (tween layers)
  if (layer.source.type === "tween") {
    const p = layer.source.params || {};
    const nameOf = (id) => S.state.project.layers.find((l) => l.id === id)?.name || `${id} (missing!)`;
    const tw = document.createElement("div");
    tw.innerHTML = `<h3>Interpolation</h3>
      <div class="hint">A: ${nameOf(p.a)} → B: ${nameOf(p.b)} — edits to A/B update this layer live.
      Non-blendable differences (seeds, toggles, mismatched stacks) jump at t = 0.5.</div>
      <div class="form" id="tw-form"></div>`;
    wrap.appendChild(tw);
    const schema = JSON.parse(JSON.stringify(S.state.schemas.tween));
    delete schema.properties.a;
    delete schema.properties.b;
    const values = {
      t: p.t ?? 0.5, sweep: p.sweep ?? 1,
      sweep_from: p.sweep_from ?? 0, sweep_to: p.sweep_to ?? 1,
    };
    const commit = actions.debounce(async () => {
      try {
        layer.source.params = { ...p, ...values }; // optimistic
        await api.put(`/api/layers/${layer.id}/tween`, values);
        await actions.refreshResolved();
      } catch (e) { actions.oops(e); }
    }, 250);
    renderForm(tw.querySelector("#tw-form"), schema, values, commit);
  }

  // -- generator params (regenerate; baked layers can return to live output)
  if (layer.source.generator && ["generator", "baked"].includes(layer.source.type)) {
    const mod = S.state.modules.sources.find((m) => m.id === layer.source.generator);
    if (mod) {
      const baked = layer.source.type === "baked";
      const gen = document.createElement("div");
      gen.innerHTML = `<h3>Generator: ${mod.label}${baked ? ' <span class="hint">(baked — regenerating discards the bake)</span>' : ""}</h3>
        <div class="form" id="regen-form"></div>
        <button id="btn-regen" class="primary">Regenerate</button>`;
      wrap.appendChild(gen);
      const values = { ...mod.defaults, ...(layer.source.params || {}) };
      renderForm(gen.querySelector("#regen-form"), mod.schema, values, () => {});
      gen.querySelector("#btn-regen").onclick = async () => {
        try {
          await api.post(`/api/layers/${layer.id}/regenerate`, { params: values });
          await actions.refreshProject();
          await actions.refreshResolved();
        } catch (e) { actions.oops(e); }
      };
    }
  }
}

function commitEffects(layer, i, patch) {
  const effects = layer.effects.map((s, j) => (j === i ? { ...s, ...patch } : s));
  actions.patchLayer(layer.id, { effects }, { debounce: true });
}

function swapEffects(layer, i, j) {
  if (j < 0 || j >= layer.effects.length) return;
  const effects = [...layer.effects];
  [effects[i], effects[j]] = [effects[j], effects[i]];
  actions.patchLayer(layer.id, { effects });
}
