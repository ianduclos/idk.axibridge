// Pens tab: the global pen library (the physical pen drawer — machine-level,
// shared across projects). Layers reference pens by id; projects snapshot
// the pens they use so files survive moving between machines.

import { api } from "./api.js";
import { renderForm } from "./forms.js";
import { S, actions } from "./main.js";

const $ = (id) => document.getElementById(id);
let editingId = null;

export function initPensTab() {
  $("tab-pens").innerHTML = `
    <div class="panel">
      <h2>Pen library <span class="hint">(global — your physical drawer)</span></h2>
      <div id="pen-list"></div>
      <div class="row"><button id="btn-pen-new" class="primary">＋ New pen</button></div>
    </div>
    <div class="panel" id="pen-editor-panel" hidden>
      <h2 id="pen-editor-title">Edit pen</h2>
      <div class="row">
        <label>name</label><input id="pen-name" style="flex:1">
        <label>colour</label><input type="color" id="pen-color">
      </div>
      <div id="pen-form" class="form"></div>
      <div class="hint">Barrel ⌀ drives registration: nib offset = holder vector × ⌀.
        Optional pen heights override motion params when this pen's layer plots.</div>
      <div class="row">
        <button id="btn-pen-save" class="primary">Save</button>
        <button id="btn-pen-delete" class="danger">Delete</button>
      </div>
    </div>`;

  $("btn-pen-new").onclick = () => {
    editingId = null;
    openEditor({
      name: "new pen", color: "#26241f", barrel_diameter_mm: 10,
      line_diameter_mm: 0.4, opacity: 1, pen_pos_down: null, pen_pos_up: null,
    });
  };
  renderPensTab();
}

let penValues = {};

export function renderPensTab() {
  const list = $("pen-list");
  if (!list) return;
  list.innerHTML = "";
  for (const pen of S.state.pens) {
    const row = document.createElement("div");
    row.className = "pen-row" + (pen.id === editingId ? " selected" : "");
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = pen.color;
    sw.style.opacity = pen.opacity;
    const nm = document.createElement("span");
    nm.textContent = pen.name;
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = `⌀${pen.barrel_diameter_mm} · line ${pen.line_diameter_mm}mm` +
      (pen.pen_pos_down != null ? ` · ↓${pen.pen_pos_down}` : "");
    row.append(sw, nm, meta);
    row.onclick = () => { editingId = pen.id; openEditor(pen); renderPensTab(); };
    list.appendChild(row);
  }
}

function openEditor(pen) {
  $("pen-editor-panel").hidden = false;
  $("pen-editor-title").textContent = editingId ? `Edit: ${pen.name}` : "New pen";
  $("pen-name").value = pen.name;
  $("pen-color").value = pen.color;
  // schema-driven numeric fields; name/colour handled above so strip them
  const schema = structuredClone(S.state.schemas.pen);
  for (const k of ["id", "name", "color"]) delete schema.properties[k];
  penValues = { ...pen };
  renderForm($("pen-form"), schema, penValues, () => {});

  $("btn-pen-save").onclick = async () => {
    const body = {
      ...penValues,
      name: $("pen-name").value || "unnamed pen",
      color: $("pen-color").value,
    };
    if (editingId) body.id = editingId; else delete body.id;
    // empty-string from cleared optional fields -> null
    for (const k of ["pen_pos_down", "pen_pos_up"]) {
      if (body[k] === "" || body[k] === undefined) body[k] = null;
    }
    try {
      const saved = await api.post("/api/pens", body);
      editingId = saved.id;
      await actions.refreshState();
      await actions.refreshResolved(); // pen colours/widths feed the canvas
      actions.log(`pen saved: ${saved.name}`);
    } catch (e) { actions.oops(e); }
  };
  $("btn-pen-delete").onclick = async () => {
    if (!editingId) { $("pen-editor-panel").hidden = true; return; }
    if (!confirm("Delete this pen? Layers referencing it fall back to default ink.")) return;
    try {
      await api.del(`/api/pens/${editingId}`);
      editingId = null;
      $("pen-editor-panel").hidden = true;
      await actions.refreshState();
      await actions.refreshResolved();
    } catch (e) { actions.oops(e); }
  };
}
