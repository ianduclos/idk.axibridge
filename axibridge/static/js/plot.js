// Plot tab: backend selection (capability-advertised), connection, jog & pen,
// motion params (schema-driven from the active backend), the manual multi-pen
// plot flow (target selector: all / one layer), plot-pass optimisation, the
// raw EBB trapdoor, soft limits, and the two calibration routines.

import { api } from "./api.js";
import { renderForm } from "./forms.js";
import { S, actions } from "./main.js";

const $ = (id) => document.getElementById(id);

export function initPlotTab() {
  $("tab-plot").innerHTML = `
    <div class="panel">
      <h2>Backend</h2>
      <div id="backend-list"></div>
      <div class="row">
        <select id="port-select" style="flex:1"></select>
        <button id="ports-refresh" title="Rescan serial ports">⟳</button>
      </div>
      <div class="row">
        <button id="btn-connect" class="primary">Connect</button>
        <button id="btn-disconnect">Disconnect</button>
      </div>
      <div id="connect-info" class="hint"></div>
      <div id="backend-notes" class="hint warn"></div>
    </div>

    <div class="panel">
      <h2>Plot</h2>
      <div class="row">
        <label>target</label>
        <select id="plot-target" style="flex:1"></select>
      </div>
      <div class="hint" id="target-pen-hint"></div>
      <div class="row" style="justify-content:center; margin-top:6px">
        <button id="btn-plot" class="primary big">Plot</button>
        <button id="btn-pause">Pause</button>
        <button id="btn-resume">Resume</button>
        <button id="btn-stop" class="danger">Stop</button>
      </div>
      <div class="progress"><div id="progress-bar"></div></div>
      <div id="job-log" class="log"></div>
      <h3>Plot-pass optimisation <span class="hint">(applies to resolved geometry)</span></h3>
      <div id="plotopt-form" class="form"></div>
    </div>

    <div class="panel">
      <h2>Animation</h2>
      <details id="anim-details">
        <summary>Frame sequence — SVG export, plot stepper, contact-sheet bake</summary>
        <div class="row">
          <label>frames</label><input type="number" id="anim-frames" min="2" max="240" step="1" style="width:5em">
          <label>t from</label><input type="number" id="anim-t-from" min="0" max="1" step="0.01" style="width:5.5em">
          <label>t to</label><input type="number" id="anim-t-to" min="0" max="1" step="0.01" style="width:5.5em">
        </div>
        <div class="hint">for one clip-frame per rendered frame, set frames = the clip's length</div>
        <div class="row">
          <a id="anim-export-link" download><button type="button">Export SVG frames (zip)</button></a>
        </div>

        <h3>Frame stepper <span class="hint">(swap paper between frames — never auto-plots)</span></h3>
        <div class="row"><span id="anim-frame-label"></span></div>
        <div class="row">
          <button id="anim-plot-frame" class="primary">Plot frame</button>
          <button id="anim-skip">Skip →</button>
          <button id="anim-reset">Reset</button>
        </div>

        <h3>Contact sheet <span class="hint">(bake the frame range into a grid on one sheet)</span></h3>
        <div class="row">
          <label>cols</label><input type="number" id="anim-cols" min="1" max="12" step="1" style="width:4em">
          <label>rows</label><input type="number" id="anim-rows" min="1" max="12" step="1" style="width:4em">
          <label>margin</label><input type="number" id="anim-margin" min="0" max="30" step="0.5" style="width:5em">
          <span class="hint">mm</span>
        </div>
        <div class="row"><button id="anim-bake" class="primary">Bake contact sheet</button></div>
      </details>
    </div>

    <div class="panel">
      <h2>Motion parameters <span class="tag" id="motion-backend-tag"></span></h2>
      <div id="motion-form" class="form"></div>
    </div>

    <div class="panel" id="panel-jog">
      <h2>Jog & pen</h2>
      <div class="jog-grid">
        <span></span><button data-jog="0,-1">▲</button><span></span>
        <button data-jog="-1,0">◀</button><button id="btn-goto-origin" title="Go to origin">⌂</button><button data-jog="1,0">▶</button>
        <span></span><button data-jog="0,1">▼</button><span></span>
      </div>
      <div class="row">
        <label>step</label>
        <select id="jog-step"><option>0.1</option><option>1</option><option selected>10</option><option>50</option></select>
        <span class="hint">mm · position: <span id="pos-readout">—</span></span>
      </div>
      <div class="row">
        <button id="btn-pen-up">Pen up</button>
        <button id="btn-pen-down">Pen down</button>
        <button id="btn-set-origin" title="Declare current position (0,0)">Set origin</button>
        <button id="btn-origin-guide" title="Jog to the paper guide corner first, then press">Origin = guide corner</button>
      </div>
      <h3>Pen height test <span class="hint">(live — tweak heights above, then:)</span></h3>
      <div class="row">
        <button id="btn-pen-cycle">Cycle ↓↑</button>
        <button id="btn-test-stroke">Test stroke (20mm)</button>
        <select id="save-heights-pen"><option value="">save heights to pen…</option></select>
      </div>
    </div>

    <div class="panel" id="panel-raw">
      <h2>Raw EBB <span class="tag">trapdoor</span></h2>
      <div class="hint warn">Bypasses planner & soft limits. Motion commands desync dead reckoning — re-set origin after.</div>
      <div id="raw-log" class="log"></div>
      <div class="row">
        <input id="raw-input" placeholder="QM  /  SP,1  /  SM,1000,500,500" spellcheck="false" style="flex:1">
        <button id="raw-send">Send</button>
      </div>
    </div>

    <div class="panel">
      <h2>Soft limits</h2>
      <label class="row"><input type="checkbox" id="limits-enabled"> guard envelope</label>
      <div class="row">
        <input type="number" id="limits-w" step="1" min="10" style="width:5.5em"> ×
        <input type="number" id="limits-h" step="1" min="10" style="width:5.5em"> <span class="hint">mm</span>
      </div>
      <div class="hint">No limit switches — past the envelope the carriage grinds the frame.</div>
    </div>

    <div class="panel">
      <h2>Holder calibration <span class="tag">once per holder</span></h2>
      <div class="hint">The V-cradle self-centres every barrel: nib offset = vector × barrel ⌀.
        1) load pen A, plot the mark. 2) load pen B, plot again.
        3) caliper the displacement of mark B relative to mark A (machine axes) and enter everything below.</div>
      <div class="row"><button id="btn-cal-mark">Plot registration mark</button></div>
      <div class="row">
        <label>⌀A</label><input type="number" id="cal-d1" step="0.05" style="width:5em">
        <label>⌀B</label><input type="number" id="cal-d2" step="0.05" style="width:5em">
        <label>Δx</label><input type="number" id="cal-dx" step="0.05" style="width:5em">
        <label>Δy</label><input type="number" id="cal-dy" step="0.05" style="width:5em">
      </div>
      <div class="row"><button id="btn-cal-compute" class="primary">Compute & save vector</button></div>
      <div class="hint" id="cal-current"></div>
    </div>`;

  // ---- backends / connection
  $("ports-refresh").onclick = refreshPorts;
  $("btn-connect").onclick = async () => {
    try {
      const info = await api.post("/api/connect", { port: $("port-select").value || null });
      $("connect-info").textContent = `port: ${info.port} · firmware: ${info.firmware}`;
      await actions.refreshState();
    } catch (e) { actions.oops(e); }
  };
  $("btn-disconnect").onclick = async () => {
    try {
      await api.post("/api/disconnect");
      $("connect-info").textContent = "";
      await actions.refreshState();
    } catch (e) { actions.oops(e); }
  };

  // ---- plot controls
  $("plot-target").onchange = () => {
    S.plotTarget = $("plot-target").value;
    actions.refreshPlan();
    renderTargetHint();
  };
  $("btn-plot").onclick = () =>
    api.post("/api/plot/start", { target: S.plotTarget })
      .then(() => actions.log(`▶ plot started (${targetLabel()})`))
      .catch(actions.oops);
  $("btn-pause").onclick = () => api.post("/api/plot/pause").catch(actions.oops);
  $("btn-resume").onclick = () => api.post("/api/plot/resume").catch(actions.oops);
  $("btn-stop").onclick = () => api.post("/api/plot/stop").catch(actions.oops);

  // ---- animation: SVG export, plot-frame stepper, contact-sheet bake
  $("anim-frames").value = anim.n;
  $("anim-t-from").value = anim.tFrom;
  $("anim-t-to").value = anim.tTo;
  $("anim-cols").value = 4;
  $("anim-rows").value = 2;
  $("anim-margin").value = 5;

  const pullAnimRange = () => {
    anim.n = Math.max(2, Math.min(240, Math.round(Number($("anim-frames").value) || 2)));
    anim.tFrom = Math.max(0, Math.min(1, Number($("anim-t-from").value)));
    anim.tTo = Math.max(0, Math.min(1, Number($("anim-t-to").value)));
    anim.i = Math.min(anim.i, anim.n - 1);
  };
  const updateExportLink = () => {
    $("anim-export-link").href =
      `/api/animation/export.zip?frames=${anim.n}&t_from=${anim.tFrom}&t_to=${anim.tTo}`;
  };
  const refreshAnimPanel = () => { pullAnimRange(); updateExportLink(); renderAnimStepper(); };

  for (const id of ["anim-frames", "anim-t-from", "anim-t-to"]) $(id).onchange = refreshAnimPanel;

  $("anim-reset").onclick = () => {
    anim.i = 0; anim.plotting = false; anim.wasBusy = false;
    renderAnimStepper();
  };
  $("anim-skip").onclick = () => {
    anim.i = Math.min(anim.i + 1, anim.n - 1);
    renderAnimStepper();
  };
  // explicit, one frame at a time — the UX guard against auto-plotting a
  // whole sequence unattended while paper needs manual swapping between sheets.
  $("anim-plot-frame").onclick = async () => {
    pullAnimRange();
    const t = animT(anim.i);
    anim.plotting = true;
    anim.wasBusy = false;
    renderAnimStepper();
    try {
      await api.post("/api/plot/start", { target: S.plotTarget, master_t: t });
      actions.log(`▶ plotting frame ${anim.i + 1}/${anim.n} (t=${t.toFixed(3)}, ${targetLabel()})`);
    } catch (e) {
      anim.plotting = false;
      renderAnimStepper();
      actions.oops(e);
    }
  };
  $("anim-bake").onclick = async () => {
    try {
      pullAnimRange();
      const cols = Math.max(1, Math.min(12, Math.round(Number($("anim-cols").value) || 1)));
      const rows = Math.max(1, Math.min(12, Math.round(Number($("anim-rows").value) || 1)));
      const margin_mm = Math.max(0, Math.min(30, Number($("anim-margin").value) || 0));
      await api.post("/api/animation/contact_sheet", {
        cols, rows, frames: anim.n, margin_mm, t_from: anim.tFrom, t_to: anim.tTo,
      });
      await actions.refreshProject();
      await actions.refreshResolved();
      actions.log(`baked ${anim.n}-frame contact sheet (${cols}×${rows})`);
    } catch (e) { actions.oops(e); }
  };
  refreshAnimPanel();

  // ---- jog / pen
  for (const b of document.querySelectorAll("[data-jog]")) {
    b.onclick = async () => {
      const [sx, sy] = b.dataset.jog.split(",").map(Number);
      const step = Number($("jog-step").value);
      try {
        const r = await api.post("/api/machine/jog", { dx: sx * step, dy: sy * step });
        setPos(r.position);
      } catch (e) { actions.oops(e); }
    };
  }
  $("btn-goto-origin").onclick = () =>
    api.post("/api/machine/goto", { x: 0, y: 0 }).then((r) => setPos(r.position)).catch(actions.oops);
  $("btn-pen-up").onclick = () => api.post("/api/machine/pen", { down: false }).catch(actions.oops);
  $("btn-pen-down").onclick = () => api.post("/api/machine/pen", { down: true }).catch(actions.oops);
  $("btn-set-origin").onclick = () =>
    api.post("/api/machine/origin", { x: 0, y: 0 }).then(actions.refreshState).catch(actions.oops);
  // jog the carriage to the physical corner of the taped sheet, then press:
  // the design frame binds so the guide rectangle IS the paper.
  $("btn-origin-guide").onclick = () => {
    const g = S.state.project.guide;
    api.post("/api/machine/origin", { x: g.x, y: g.y }).then(actions.refreshState).catch(actions.oops);
  };
  $("btn-pen-cycle").onclick = async () => {
    try {
      await api.post("/api/machine/pen", { down: true });
      setTimeout(() => api.post("/api/machine/pen", { down: false }).catch(actions.oops), 700);
    } catch (e) { actions.oops(e); }
  };
  $("btn-test-stroke").onclick = () =>
    api.post("/api/calibration/teststroke", {}).then(() => actions.log("test stroke started")).catch(actions.oops);
  $("save-heights-pen").onchange = async (e) => {
    const penId = e.target.value;
    e.target.value = "";
    if (!penId) return;
    const pen = S.state.pens.find((p) => p.id === penId);
    const params = S.state.project.backend_params?.[S.state.machine.backend] || {};
    const motion = currentMotionValues();
    try {
      await api.post("/api/pens", {
        ...pen,
        pen_pos_down: motion.pen_pos_down ?? params.pen_pos_down ?? null,
        pen_pos_up: motion.pen_pos_up ?? params.pen_pos_up ?? null,
      });
      await actions.refreshState();
      actions.log(`saved heights to pen “${pen.name}”`);
    } catch (err) { actions.oops(err); }
  };

  // ---- raw console
  const sendRaw = async () => {
    const cmd = $("raw-input").value.trim();
    if (!cmd) return;
    rawLog(`> ${cmd}`, "tx");
    $("raw-input").value = "";
    try {
      const r = await api.post("/api/machine/raw", { command: cmd, expect_reply: true });
      rawLog(r.reply || "(no reply)");
    } catch (e) { rawLog(`✗ ${e.message}`, "err"); }
  };
  $("raw-send").onclick = sendRaw;
  $("raw-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendRaw(); });

  // ---- limits
  const pushLimits = actions.debounce(async () => {
    try {
      await api.put("/api/limits", {
        enabled: $("limits-enabled").checked,
        width: Number($("limits-w").value),
        height: Number($("limits-h").value),
      });
      await actions.refreshPlan();
    } catch (e) { actions.oops(e); }
  }, 250);
  $("limits-enabled").onchange = pushLimits;
  $("limits-w").onchange = pushLimits;
  $("limits-h").onchange = pushLimits;

  // ---- calibration
  $("btn-cal-mark").onclick = () =>
    api.post("/api/calibration/holder/mark").then(() => actions.log("plotting registration mark")).catch(actions.oops);
  $("btn-cal-compute").onclick = async () => {
    try {
      const cal = await api.post("/api/calibration/holder/compute", {
        diameter_1: +$("cal-d1").value, diameter_2: +$("cal-d2").value,
        dx_mm: +$("cal-dx").value, dy_mm: +$("cal-dy").value,
      });
      await actions.refreshState();
      actions.log(`holder vector saved: (${cal.dx_per_mm.toFixed(4)}, ${cal.dy_per_mm.toFixed(4)}) mm/mm`);
    } catch (e) { actions.oops(e); }
  };

  refreshPorts();
  renderPlotTab();
}

let motionValues = {};
const currentMotionValues = () => motionValues;

// ---- Animation: frame stepper state ------------------------------------------
// Module-level (survives initPlotTab's innerHTML rebuilds, e.g. on project
// switch) so the SSE-driven completion check in applyCapabilities() can
// advance it without needing its own wiring. Sequencing is entirely
// browser-side — the server has no notion of "frame N of an animation".
const anim = { n: 8, tFrom: 0, tTo: 1, i: 0, plotting: false, wasBusy: false };

function animT(i) {
  return anim.n <= 1 ? anim.tFrom : anim.tFrom + (anim.tTo - anim.tFrom) * i / (anim.n - 1);
}

function renderAnimStepper() {
  if (!$("anim-frame-label")) return;
  $("anim-frame-label").textContent =
    `frame ${anim.i + 1} of ${anim.n} (t=${animT(anim.i).toFixed(3)})`;
  const btn = $("anim-plot-frame");
  if (btn) {
    btn.textContent = anim.plotting ? `Plotting frame ${anim.i + 1}…` : `Plot frame ${anim.i + 1}`;
    const basePlotDisabled = $("btn-plot") ? $("btn-plot").disabled : true;
    btn.disabled = anim.plotting || basePlotDisabled;
  }
  const skip = $("anim-skip");
  if (skip) skip.disabled = anim.plotting || anim.i >= anim.n - 1;
}

export function renderPlotTab() {
  if (!$("backend-list")) return;
  renderBackends();
  renderTargets();
  renderMotionForm();
  renderPlotOptions();
  renderLimits();
  renderCalibration();
  applyCapabilities();
}

function renderBackends() {
  const list = $("backend-list");
  list.innerHTML = "";
  for (const b of S.state.backends) {
    const card = document.createElement("div");
    card.className = "backend-card" + (b.active ? " active" : "") + (b.available ? "" : " unavailable");
    const caps = b.capabilities;
    const capTags = [
      caps.raw_ebb ? "<b>raw EBB</b>" : "no raw",
      caps.jog ? "<b>jog</b>" : "no jog",
      caps.pause_resume ? "<b>pause</b>" : "no pause",
      `progress: ${caps.progress_granularity}`,
    ].join(" · ");
    card.innerHTML = `<div class="name">${b.label}</div>
      <div class="desc">${b.available ? b.description : b.unavailable_reason}</div>
      <div class="caps">${capTags}</div>`;
    if (b.available && !b.active) {
      card.onclick = async () => {
        try {
          await api.post("/api/backend/select", { backend: b.id });
          await actions.refreshState();
          await actions.refreshPlan();
        } catch (e) { actions.oops(e); }
      };
    }
    list.appendChild(card);
  }
}

async function refreshPorts() {
  const sel = $("port-select");
  if (!sel) return;
  sel.innerHTML = '<option value="">auto-detect port</option>';
  try {
    for (const p of await api.get("/api/ports")) {
      const o = document.createElement("option");
      o.value = p.device;
      o.textContent = `${p.device} — ${p.description}`;
      sel.appendChild(o);
    }
  } catch (e) { actions.oops(e); }
}

function renderTargets() {
  const sel = $("plot-target");
  const prev = S.plotTarget;
  sel.innerHTML = '<option value="all">all layers</option>';
  for (const layer of S.state.project.layers) {
    const o = document.createElement("option");
    o.value = layer.id;
    o.textContent = `layer: ${layer.name}`;
    sel.appendChild(o);
  }
  sel.value = [...sel.options].some((o) => o.value === prev) ? prev : "all";
  S.plotTarget = sel.value;
  renderTargetHint();
}

function targetLabel() {
  if (S.plotTarget === "all") return "all layers";
  const l = S.state.project.layers.find((x) => x.id === S.plotTarget);
  return l ? l.name : S.plotTarget;
}

function renderTargetHint() {
  const hint = $("target-pen-hint");
  if (S.plotTarget === "all") {
    hint.textContent = "Manual multi-pen: pick a layer, plot, swap the pen, pick the next.";
    return;
  }
  const layer = S.state.project.layers.find((x) => x.id === S.plotTarget);
  const pen = S.state.pens.find((p) => p.id === layer?.pen_id);
  hint.textContent = pen
    ? `Load pen: ${pen.name} (⌀${pen.barrel_diameter_mm}mm)` +
      (pen.pen_pos_down != null ? ` — pen heights override: ↓${pen.pen_pos_down} ↑${pen.pen_pos_up ?? "–"}` : "")
    : "No pen assigned to this layer (no offset compensation, default ink).";
}

function renderMotionForm() {
  const b = S.state.backends.find((x) => x.active);
  if (!b) return;
  $("motion-backend-tag").textContent = b.label;
  motionValues = { ...b.params_defaults, ...(S.state.project.backend_params?.[b.id] || {}) };
  renderForm($("motion-form"), b.params_schema, motionValues, actions.debounce(async () => {
    try {
      await api.put(`/api/params/${b.id}`, motionValues);
      await actions.refreshPlan(); // the core loop: tweak → fresh estimate
    } catch (e) { actions.oops(e); }
  }, 300));
}

function renderPlotOptions() {
  const values = { ...S.state.project.plot_options };
  renderForm($("plotopt-form"), S.state.schemas.plot_options, values, actions.debounce(async () => {
    try {
      await api.put("/api/project", { plot_options: values });
      S.state.project.plot_options = values;
      actions.refreshCropFrame(); // crop mode/margin/rect fields may have changed
      await actions.refreshPlan();
    } catch (e) { actions.oops(e); }
  }, 300));
}

function renderLimits() {
  const lim = S.state.machine.limits;
  $("limits-enabled").checked = lim.enabled;
  $("limits-w").value = lim.width;
  $("limits-h").value = lim.height;
}

function renderCalibration() {
  const cal = S.state.settings.holder_calibration;
  $("cal-current").textContent =
    cal.dx_per_mm === 0 && cal.dy_per_mm === 0
      ? "current vector: zero — compensation OFF (raw seating misregistration visible)"
      : `current vector: (${cal.dx_per_mm.toFixed(4)}, ${cal.dy_per_mm.toFixed(4)}) mm per mm of barrel ⌀`;
  const sel = $("save-heights-pen");
  sel.innerHTML = '<option value="">save heights to pen…</option>';
  for (const pen of S.state.pens) {
    const o = document.createElement("option");
    o.value = pen.id; o.textContent = pen.name;
    sel.appendChild(o);
  }
}

export function applyCapabilities() {
  const b = S.state.backends.find((x) => x.active);
  if (!b || !$("backend-list")) return;
  const caps = b.capabilities;
  const m = S.state.machine;
  const connected = m.connected;
  const idle = m.job_state === "idle";

  $("panel-jog").style.display = caps.jog || caps.pen_control ? "" : "none";
  $("panel-raw").style.display = caps.raw_ebb ? "" : "none";
  for (const btn of document.querySelectorAll("[data-jog]")) btn.disabled = !(caps.jog && connected && idle);
  $("btn-goto-origin").disabled = !(caps.jog && connected && idle);
  $("btn-set-origin").disabled = $("btn-origin-guide").disabled = !(caps.set_origin && connected && idle);
  $("btn-pen-up").disabled = $("btn-pen-down").disabled = $("btn-pen-cycle").disabled =
    !(caps.pen_control && connected && idle);
  $("btn-test-stroke").disabled = $("btn-cal-mark").disabled = !(connected && idle);
  $("raw-send").disabled = $("raw-input").disabled = !(caps.raw_ebb && connected && idle);
  $("btn-plot").disabled = !(connected && idle);
  $("btn-pause").disabled = !(caps.pause_resume && m.job_state === "plotting");
  $("btn-resume").disabled = !(m.job_state === "paused");
  $("btn-stop").disabled = idle;
  $("port-select").disabled = $("ports-refresh").disabled = !caps.requires_serial_port;
  $("backend-notes").textContent = caps.notes || "";
  // reflect server-side connections too (auto-connect at startup)
  const info = m.connect_info || {};
  if (connected && info.firmware) {
    $("connect-info").textContent = `port: ${info.port} · firmware: ${info.firmware}`;
  } else if (!connected) {
    $("connect-info").textContent = "";
  }
  if (m.position) setPos(m.position);

  // frame stepper: advance to "swap paper -> next frame" once THIS job (a
  // frame plot we started via anim-plot-frame) reaches idle again. Never
  // auto-plots the next frame — only unlocks the button for a fresh press.
  if (anim.plotting) {
    if (!idle) {
      anim.wasBusy = true;
    } else if (anim.wasBusy) {
      anim.wasBusy = false;
      anim.plotting = false;
      anim.i = Math.min(anim.i + 1, anim.n - 1);
    }
  }
  renderAnimStepper();
}

function setPos(pos) {
  const el = $("pos-readout");
  if (el) el.textContent = `${pos[0].toFixed(1)}, ${pos[1].toFixed(1)} mm`;
  actions.canvas().setMachinePos(pos, false);
}

function rawLog(text, cls = "") {
  const div = $("raw-log");
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = text;
  div.appendChild(line);
  while (div.childNodes.length > 200) div.removeChild(div.firstChild);
  div.scrollTop = div.scrollHeight;
}
