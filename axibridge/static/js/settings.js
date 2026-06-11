// Settings tab: machine-level configuration (estimator calibration, holder
// vector, projects root, host/port) and project file operations
// (new / load / export / import). The paper guide size lives here too since
// paper presets are machine-level.

import { api } from "./api.js";
import { renderForm } from "./forms.js";
import { S, actions } from "./main.js";

const $ = (id) => document.getElementById(id);
let settingsValues = {};

export function initSettingsTab() {
  $("tab-settings").innerHTML = `
    <div class="panel">
      <h2>Project</h2>
      <div class="row">
        <select id="proj-list" style="flex:1"></select>
        <button id="btn-proj-load">Load</button>
      </div>
      <div class="row">
        <button id="btn-proj-new">New project</button>
        <a id="btn-proj-export" href="/api/project/export.zip" download><button>Export .zip</button></a>
        <label class="row" style="margin:0">
          <input type="file" id="proj-import-file" accept=".zip" hidden>
          <button id="btn-proj-import">Import .zip</button>
        </label>
      </div>
      <div class="hint" id="proj-dir-hint"></div>
    </div>

    <div class="panel">
      <h2>Paper guide</h2>
      <div class="row">
        <select id="paper-preset"></select>
        <label><input type="checkbox" id="paper-rotate" checked> rotate to fit bed</label>
      </div>
      <div class="row">
        <label>w</label><input type="number" id="guide-w" step="1" style="width:5.5em">
        <label>h</label><input type="number" id="guide-h" step="1" style="width:5.5em">
        <label>x</label><input type="number" id="guide-x" step="1" style="width:5.5em">
        <label>y</label><input type="number" id="guide-y" step="1" style="width:5.5em">
      </div>
      <div class="hint">A4 portrait does not fit the 300×218 bed un-rotated — its long edge
        only fits along machine X. Drag the rectangle on the canvas to position it.</div>
    </div>

    <div class="panel">
      <h2>Machine settings <span class="hint">(~/.axibridge/settings.json)</span></h2>
      <div id="settings-form" class="form"></div>
      <div class="row"><button id="btn-settings-save" class="primary">Save settings</button></div>
      <div class="hint">Estimator constants calibrate the ±15% time estimate to your machine.
        Host/port apply on next start. No authentication — bind wisely.</div>
      <div class="row"><button id="btn-cal-reset" class="danger">Reset holder calibration (disable compensation)</button></div>
    </div>

    <div class="panel">
      <h2>Server</h2>
      <div class="row"><button id="btn-restart">⟳ Restart server</button></div>
      <div class="hint">Re-executes the server process in place (picks up code changes).
        Unsaved project changes are lost — save first. Refused while plotting.
        The page reconnects by itself.</div>
    </div>`;

  const restart = $("btn-restart");
  restart.onclick = async () => {
    if (!restart.dataset.armed) { // two-click arm, same pattern as layer delete
      restart.dataset.armed = "1";
      restart.textContent = "sure? unsaved work is lost";
      restart.style.color = "var(--rust)";
      setTimeout(() => {
        delete restart.dataset.armed;
        restart.textContent = "⟳ Restart server";
        restart.style.color = "";
      }, 2500);
      return;
    }
    try {
      await api.post("/api/server/restart");
      restart.textContent = "restarting…";
      restart.disabled = true;
      // the SSE stream drops, auto-reconnects, and onReconnect re-hydrates
    } catch (e) { actions.oops(e); }
  };

  $("btn-proj-new").onclick = async () => {
    if (!confirm("Start a new empty project? Unsaved changes are lost.")) return;
    try {
      await api.post("/api/project/new");
      await actions.refreshAll();
    } catch (e) { actions.oops(e); }
  };
  $("btn-proj-load").onclick = async () => {
    const name = $("proj-list").value;
    if (!name) return;
    try {
      await api.post("/api/project/load", { name });
      await actions.refreshAll();
      actions.log(`loaded project: ${name}`);
    } catch (e) { actions.oops(e); }
  };
  $("btn-proj-import").onclick = () => $("proj-import-file").click();
  $("proj-import-file").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.upload("/api/project/import", fd);
      await actions.refreshAll();
      actions.log(`imported: ${file.name}`);
    } catch (err) { actions.oops(err); }
  };

  // paper guide
  $("paper-preset").onchange = applyPreset;
  $("paper-rotate").onchange = applyPreset;
  const pushGuide = actions.debounce(async () => {
    const guide = {
      x: +$("guide-x").value, y: +$("guide-y").value,
      width: +$("guide-w").value, height: +$("guide-h").value,
    };
    try {
      await api.put("/api/project", { guide });
      S.state.project.guide = guide;
      actions.canvas().setData({ guide });
    } catch (e) { actions.oops(e); }
  }, 250);
  for (const id of ["guide-w", "guide-h", "guide-x", "guide-y"]) $(id).onchange = pushGuide;

  $("btn-settings-save").onclick = async () => {
    try {
      await api.put("/api/settings", settingsValues);
      await actions.refreshState();
      actions.log("settings saved");
    } catch (e) { actions.oops(e); }
  };
  $("btn-cal-reset").onclick = async () => {
    try {
      await api.put("/api/settings", { holder_calibration: { dx_per_mm: 0, dy_per_mm: 0 } });
      await actions.refreshState();
      actions.log("holder calibration reset — compensation off");
    } catch (e) { actions.oops(e); }
  };

  renderSettingsTab();
  refreshProjectList();
}

function applyPreset() {
  const preset = (S.state.settings.paper_presets || []).find((p) => p.name === $("paper-preset").value);
  if (!preset) return;
  const rotate = $("paper-rotate").checked;
  const bed = S.state.bed;
  const w = rotate ? Math.max(preset.width, preset.height) : preset.width;
  const h = rotate ? Math.min(preset.width, preset.height) : preset.height;
  $("guide-w").value = w;
  $("guide-h").value = h;
  $("guide-x").value = Math.max(Math.round((bed.width - w) / 2), 0);
  $("guide-y").value = Math.max(Math.round((bed.height - h) / 2), 0);
  $("guide-x").onchange();
}

async function refreshProjectList() {
  try {
    const names = await api.get("/api/projects");
    const sel = $("proj-list");
    if (!sel) return;
    sel.innerHTML = names.length ? "" : '<option value="">— no saved projects —</option>';
    for (const n of names) {
      const o = document.createElement("option");
      o.value = n; o.textContent = n;
      sel.appendChild(o);
    }
  } catch (e) { actions.oops(e); }
}

export function renderSettingsTab() {
  if (!$("settings-form")) return;
  const schema = structuredClone(S.state.schemas.settings);
  // composite fields get dedicated UI elsewhere (wizard, presets)
  for (const k of ["holder_calibration", "paper_presets"]) delete schema.properties[k];
  settingsValues = { ...S.state.settings };
  delete settingsValues.holder_calibration;
  delete settingsValues.paper_presets;
  renderForm($("settings-form"), schema, settingsValues, () => {});

  const g = S.state.project.guide;
  $("guide-w").value = g.width; $("guide-h").value = g.height;
  $("guide-x").value = g.x; $("guide-y").value = g.y;
  const presets = $("paper-preset");
  presets.innerHTML = "";
  for (const p of S.state.settings.paper_presets || []) {
    const o = document.createElement("option");
    o.value = p.name; o.textContent = `${p.name} (${p.width}×${p.height})`;
    presets.appendChild(o);
  }
  $("proj-dir-hint").textContent = S.state.project_dir
    ? `saved at: ${S.state.project_dir}` : "not saved yet";
  refreshProjectList();
}
