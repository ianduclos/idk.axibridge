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
          <button id="anim-preview-render" class="primary">Render popup</button>
          <button id="anim-preview-toggle">Live play</button>
          <button id="anim-preview-step">Frame →</button>
          <label>fps</label><input type="number" id="anim-preview-fps" min="1" max="24" step="1" style="width:4em">
          <label class="hint" style="cursor:pointer"><input type="checkbox" id="anim-preview-loop"> loop</label>
        </div>
        <div class="row"><span id="anim-preview-label"></span></div>
        <div class="row">
          <label>per sheet</label>
          <select id="anim-per-sheet" style="width:4.5em">
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="4">4</option>
            <option value="16">16</option>
          </select>
          <label>margin</label><input type="number" id="anim-sheet-margin" min="0" max="30" step="0.5" style="width:5em">
          <span class="hint">mm · 2 = two A5 halves; frames tile many-up on one page</span>
        </div>
        <div class="row">
          <a id="anim-export-link" download><button type="button">Export SVG frames (zip)</button></a>
        </div>

        <h3>Frame stepper <span class="hint">(swap paper/pen between passes — never auto-plots)</span></h3>
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

    <div id="anim-preview-modal" class="modal-backdrop" hidden>
      <div class="preview-modal">
        <div class="preview-head">
          <h2>Animation preview</h2>
          <button id="anim-preview-close">Close</button>
        </div>
        <div class="preview-stage">
          <img id="anim-preview-img" alt="">
          <div id="anim-preview-empty" class="hint">rendering…</div>
        </div>
        <div class="row">
          <button id="anim-preview-popup-toggle" class="primary">Play</button>
          <button id="anim-preview-popup-prev">← Frame</button>
          <button id="anim-preview-popup-next">Frame →</button>
          <span id="anim-preview-popup-label" class="hint"></span>
        </div>
        <div class="progress"><div id="anim-preview-progress"></div></div>
      </div>
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
  $("anim-per-sheet").value = String(anim.perSheet);
  $("anim-sheet-margin").value = anim.margin;
  $("anim-preview-fps").value = anim.fps;
  $("anim-preview-loop").checked = anim.loop;
  $("anim-cols").value = 4;
  $("anim-rows").value = 2;
  $("anim-margin").value = 5;

  const pullAnimRange = () => {
    anim.n = Math.max(2, Math.min(240, Math.round(Number($("anim-frames").value) || 2)));
    anim.tFrom = Math.max(0, Math.min(1, Number($("anim-t-from").value)));
    anim.tTo = Math.max(0, Math.min(1, Number($("anim-t-to").value)));
    anim.margin = Math.max(0, Math.min(30, Number($("anim-sheet-margin").value) || 0));
    anim.i = Math.min(anim.i, anim.n - 1);
    anim.nPages = sheetPages();
    anim.sheet = Math.min(anim.sheet, anim.nPages - 1);
    renderAnimPreview();
  };
  const updateExportLink = () => {
    let href = `/api/animation/export.zip?frames=${anim.n}&t_from=${anim.tFrom}&t_to=${anim.tTo}`;
    if (anim.perSheet > 1) {
      const [cols, rows] = gridDims();
      href += `&cols=${cols}&rows=${rows}&margin_mm=${anim.margin}`;
    }
    $("anim-export-link").href = href;
    const btn = $("anim-export-link").querySelector("button");
    if (btn) btn.textContent = anim.perSheet > 1 ? "Export sheets (zip)" : "Export SVG frames (zip)";
  };
  // Panel refresh: pull inputs, refresh the export link, re-fetch the sheet's
  // pen passes, and sync the plan overlay to the current page (one plan path).
  const refreshAnimPanel = async () => {
    pullAnimRange();
    updateExportLink();
    await refreshSheetInfo();
    syncSheetPlan();
  };

  for (const id of ["anim-frames", "anim-t-from", "anim-t-to", "anim-sheet-margin"])
    $(id).onchange = refreshAnimPanel;
  $("anim-preview-fps").onchange = () => {
    anim.fps = Math.max(1, Math.min(24, Math.round(Number($("anim-preview-fps").value) || 8)));
    $("anim-preview-fps").value = anim.fps;
  };
  $("anim-preview-loop").onchange = () => {
    anim.loop = $("anim-preview-loop").checked;
  };
  $("anim-preview-render").onclick = () => renderRasterPreview();
  $("anim-preview-toggle").onclick = () => {
    pullAnimRange();
    anim.previewing ? stopPreview() : startPreview();
  };
  $("anim-preview-step").onclick = () => {
    pullAnimRange();
    stopPreview();
    anim.i = nextFrameIndex();
    previewScrub.request(anim.i);
  };
  $("anim-per-sheet").onchange = async () => {
    anim.perSheet = Number($("anim-per-sheet").value) || 1;
    anim.sheet = 0; anim.pass = 0;  // grid changed → restart the two-axis stepper
    await refreshAnimPanel();
  };
  // the plan overlay previews the page only while the panel is open (B3)
  $("anim-details").ontoggle = syncSheetPlan;

  $("anim-reset").onclick = () => {
    stopPreview();
    anim.i = 0; anim.sheet = 0; anim.pass = 0;
    anim.plotting = false; anim.wasBusy = false;
    renderAnimStepper();
    previewScrub.request(anim.i);
    if (anim.perSheet > 1) syncSheetPlan();  // back to page 0
  };
  $("anim-skip").onclick = () => {
    stopPreview();
    if (anim.perSheet <= 1) {
      anim.i = Math.min(anim.i + 1, anim.n - 1);
      renderAnimStepper();
      previewScrub.request(anim.i);
    } else {
      stepSheetPass();  // advance a pen pass, wrapping to the next sheet
    }
  };
  // explicit, one pass at a time — the UX guard against auto-plotting a whole
  // sequence unattended while paper (and pens) need manual swapping.
  $("anim-plot-frame").onclick = async () => {
    stopPreview();
    pullAnimRange();
    anim.plotting = true;
    anim.wasBusy = false;
    renderAnimStepper();
    try {
      if (anim.perSheet <= 1) {
        const t = animT(anim.i);
        await api.post("/api/plot/start", { target: S.plotTarget, master_t: t });
        actions.log(`▶ plotting frame ${anim.i + 1}/${anim.n} (t=${t.toFixed(3)}, ${targetLabel()})`);
      } else {
        const p = anim.passes[anim.pass];
        const spec = currentSheetSpec({ pen_id: p ? p.pen_id : "" });
        await api.post("/api/plot/start", { sheet: spec });
        actions.log(`▶ plotting sheet ${anim.sheet + 1}/${anim.nPages} · pass ${anim.pass + 1} (${p ? p.name : "?"})`);
      }
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
  $("anim-preview-close").onclick = closeRasterPreview;
  $("anim-preview-popup-toggle").onclick = () => {
    anim.popupPlaying ? stopRasterPlayback() : startRasterPlayback();
  };
  $("anim-preview-popup-prev").onclick = () => {
    stopRasterPlayback();
    showRasterFrame(anim.popupI <= 0 ? anim.previewFrames.length - 1 : anim.popupI - 1);
  };
  $("anim-preview-popup-next").onclick = () => {
    stopRasterPlayback();
    showRasterFrame((anim.popupI + 1) % Math.max(anim.previewFrames.length, 1));
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
// perSheet == 1: the classic one-frame-per-sheet stepper (i = frame index).
// perSheet > 1: the two-axis grid stepper — `sheet` (physical page) × `pass`
// (pen pass on that page, from sheet_info); `passes` holds the current page's
// [{pen_id, name, color}]. All sequencing is browser-side.
const anim = {
  n: 8, tFrom: 0, tTo: 1, margin: 5, perSheet: 1,
  i: 0, sheet: 0, pass: 0, passes: [], nPages: 1,
  fps: 8, loop: true,
  previewFrames: [], previewAbort: null, renderingPreview: false,
  popupI: 0, popupPlaying: false, popupTimer: null,
  previewing: false, plotting: false, wasBusy: false,
};

// per-sheet count → (cols, rows). 2 splits the landscape A4 into two portrait
// A5-ish halves; 4 = quads; 16 = a 4×4 flipbook strip page.
const GRID = { 1: [1, 1], 2: [2, 1], 4: [2, 2], 16: [4, 4] };
function gridDims() { return GRID[anim.perSheet] || [1, 1]; }
function sheetPages() {
  const [c, r] = gridDims();
  return Math.max(1, Math.ceil(anim.n / (c * r)));
}
function currentSheetSpec(extra = {}) {
  const [cols, rows] = gridDims();
  return { cols, rows, frames: anim.n, t_from: anim.tFrom, t_to: anim.tTo,
           margin_mm: anim.margin, page: anim.sheet, ...extra };
}

// The plan overlay/estimate previews the CURRENT page only while the Animation
// panel is open and per-sheet > 1; otherwise the plain target (one plan path).
function syncSheetPlan() {
  const open = $("anim-details") && $("anim-details").open;
  S.sheetPlan = open && anim.perSheet > 1 ? currentSheetSpec() : null;
  actions.refreshPlan();
}

// Re-fetch the current sheet's ordered pen passes (they differ per page).
async function refreshSheetInfo() {
  if (anim.perSheet <= 1) { anim.passes = []; anim.nPages = 1; renderAnimStepper(); return; }
  const [cols, rows] = gridDims();
  anim.nPages = sheetPages();
  anim.sheet = Math.min(anim.sheet, anim.nPages - 1);
  try {
    const q = `frames=${anim.n}&cols=${cols}&rows=${rows}` +
      `&t_from=${anim.tFrom}&t_to=${anim.tTo}&margin_mm=${anim.margin}&page=${anim.sheet}`;
    const info = await api.get(`/api/animation/sheet_info?${q}`);
    anim.nPages = info.sheets;
    anim.passes = info.passes || [];
    anim.pass = Math.min(anim.pass, Math.max(0, anim.passes.length - 1));
  } catch (e) {
    anim.passes = [];
  }
  renderAnimStepper();
}

// Advance one pen pass; at the last pass of a sheet, roll to the next sheet
// (refetching its passes) — never past the final pass of the final sheet.
async function stepSheetPass() {
  if (anim.pass < anim.passes.length - 1) {
    anim.pass += 1;
    renderAnimStepper();
  } else if (anim.sheet < anim.nPages - 1) {
    anim.sheet += 1;
    anim.pass = 0;
    await refreshSheetInfo();
    syncSheetPlan();  // plan overlay follows the new page
  } else {
    renderAnimStepper();
  }
}

function animT(i) {
  return anim.n <= 1 ? anim.tFrom : anim.tFrom + (anim.tTo - anim.tFrom) * i / (anim.n - 1);
}

function pullAnimControls() {
  if (!$("anim-frames")) return;
  anim.n = Math.max(2, Math.min(240, Math.round(Number($("anim-frames").value) || 2)));
  anim.tFrom = Math.max(0, Math.min(1, Number($("anim-t-from").value)));
  anim.tTo = Math.max(0, Math.min(1, Number($("anim-t-to").value)));
  anim.margin = Math.max(0, Math.min(30, Number($("anim-sheet-margin").value) || 0));
  anim.fps = Math.max(1, Math.min(24, Math.round(Number($("anim-preview-fps")?.value) || anim.fps || 8)));
  anim.loop = Boolean($("anim-preview-loop")?.checked);
  anim.i = Math.min(anim.i, anim.n - 1);
  anim.nPages = sheetPages();
  anim.sheet = Math.min(anim.sheet, anim.nPages - 1);
}

function nextFrameIndex() {
  const next = anim.i + 1;
  return next < anim.n ? next : 0;
}

function startPreview() {
  anim.previewing = true;
  renderAnimPreview();
  previewScrub.request(anim.i);
}

function stopPreview() {
  anim.previewing = false;
  previewScrub.clearTimer();
  renderAnimPreview();
}

function schedulePreviewNext() {
  previewScrub.clearTimer();
  if (!anim.previewing) return;
  previewScrub.timer = setTimeout(() => {
    const next = anim.i + 1;
    if (next >= anim.n && !anim.loop) {
      stopPreview();
      return;
    }
    previewScrub.request(next < anim.n ? next : 0);
  }, 1000 / anim.fps);
}

// One /compose/resolved?t= request in flight at a time. Playback waits for a
// frame to render before scheduling the next tick, so expensive frames slow the
// preview down instead of queuing stale geometry.
const previewScrub = {
  inflight: false, pending: false, timer: null,
  clearTimer() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  },
  request(i) {
    this.clearTimer();
    anim.i = Math.max(0, Math.min(anim.n - 1, Math.round(i)));
    S.masterT = animT(anim.i);
    renderAnimStepper();
    renderAnimPreview();
    this.pending = true;
    if (!this.inflight) this._run();
  },
  async _run() {
    if (!this.pending) return;
    this.pending = false;
    this.inflight = true;
    const t = animT(anim.i);
    S.masterT = t;
    try {
      await actions.refreshResolved(t, { plan: false });
    } catch (e) {
      stopPreview();
      actions.oops(e);
    } finally {
      this.inflight = false;
      if (this.pending) this._run();
      else schedulePreviewNext();
    }
  },
};

function renderAnimPreview() {
  const label = $("anim-preview-label");
  if (!label) return;
  const play = $("anim-preview-toggle");
  const step = $("anim-preview-step");
  const render = $("anim-preview-render");
  label.textContent = `preview frame ${anim.i + 1}/${anim.n} · t=${animT(anim.i).toFixed(3)}`;
  if (play) play.textContent = anim.previewing ? "Pause live" : "Live play";
  if (step) step.disabled = anim.previewing;
  if (render) {
    render.textContent = anim.renderingPreview ? "Rendering…" : "Render popup";
    render.disabled = anim.renderingPreview;
  }
}

function clearRasterFrames() {
  for (const frame of anim.previewFrames) URL.revokeObjectURL(frame.url);
  anim.previewFrames = [];
  anim.popupI = 0;
}

function setRasterProgress(done, total) {
  const bar = $("anim-preview-progress");
  if (bar) bar.style.width = total ? `${Math.round(100 * done / total)}%` : "0%";
}

function renderRasterControls(message = "") {
  const modal = $("anim-preview-modal");
  if (!modal || modal.hidden) return;
  const hasFrames = anim.previewFrames.length > 0;
  const img = $("anim-preview-img");
  const empty = $("anim-preview-empty");
  const play = $("anim-preview-popup-toggle");
  const prev = $("anim-preview-popup-prev");
  const next = $("anim-preview-popup-next");
  const label = $("anim-preview-popup-label");
  if (img) img.hidden = !hasFrames;
  if (empty) {
    empty.hidden = hasFrames && !message;
    empty.textContent = message || "";
  }
  if (play) {
    play.textContent = anim.popupPlaying ? "Pause" : "Play";
    play.disabled = anim.renderingPreview || !hasFrames;
  }
  if (prev) prev.disabled = anim.renderingPreview || !hasFrames;
  if (next) next.disabled = anim.renderingPreview || !hasFrames;
  if (label) {
    label.textContent = hasFrames
      ? `frame ${anim.popupI + 1}/${anim.previewFrames.length} · t=${anim.previewFrames[anim.popupI].t.toFixed(3)}`
      : message;
  }
  renderAnimPreview();
}

function showRasterFrame(i) {
  if (!anim.previewFrames.length) {
    renderRasterControls();
    return;
  }
  anim.popupI = Math.max(0, Math.min(anim.previewFrames.length - 1, i));
  const img = $("anim-preview-img");
  if (img) img.src = anim.previewFrames[anim.popupI].url;
  renderRasterControls();
}

function stopRasterPlayback() {
  anim.popupPlaying = false;
  if (anim.popupTimer) clearTimeout(anim.popupTimer);
  anim.popupTimer = null;
  renderRasterControls();
}

function startRasterPlayback() {
  if (!anim.previewFrames.length) return;
  anim.popupPlaying = true;
  renderRasterControls();
  const tick = () => {
    if (!anim.popupPlaying) return;
    const next = anim.popupI + 1;
    if (next >= anim.previewFrames.length && !anim.loop) {
      stopRasterPlayback();
      return;
    }
    showRasterFrame(next < anim.previewFrames.length ? next : 0);
    anim.popupTimer = setTimeout(tick, 1000 / anim.fps);
  };
  anim.popupTimer = setTimeout(tick, 1000 / anim.fps);
}

function closeRasterPreview() {
  anim.previewAbort?.abort();
  anim.previewAbort = null;
  anim.renderingPreview = false;
  stopRasterPlayback();
  clearRasterFrames();
  const modal = $("anim-preview-modal");
  if (modal) modal.hidden = true;
  setRasterProgress(0, 0);
  renderAnimPreview();
}

async function renderRasterPreview() {
  pullAnimControls();
  stopPreview();
  stopRasterPlayback();
  anim.previewAbort?.abort();
  const controller = new AbortController();
  anim.previewAbort = controller;
  anim.renderingPreview = true;
  clearRasterFrames();
  const modal = $("anim-preview-modal");
  if (modal) modal.hidden = false;
  setRasterProgress(0, anim.n);
  renderRasterControls(`rendering frame 0/${anim.n}`);

  try {
    for (let i = 0; i < anim.n; i++) {
      if (controller.signal.aborted) return;
      const t = animT(i);
      renderRasterControls(`rendering frame ${i + 1}/${anim.n}`);
      const url = `/api/animation/preview.png?t=${encodeURIComponent(t)}&width_px=1200`;
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      anim.previewFrames.push({ url: URL.createObjectURL(blob), t });
      setRasterProgress(i + 1, anim.n);
      if (i === 0) showRasterFrame(0);
    }
    anim.renderingPreview = false;
    anim.previewAbort = null;
    showRasterFrame(0);
    startRasterPlayback();
  } catch (e) {
    if (e.name !== "AbortError") actions.oops(e);
  } finally {
    if (anim.previewAbort === controller) {
      anim.previewAbort = null;
      anim.renderingPreview = false;
      renderRasterControls();
      renderAnimPreview();
    }
  }
}

function renderAnimStepper() {
  const label = $("anim-frame-label");
  if (!label) return;
  const btn = $("anim-plot-frame");
  const skip = $("anim-skip");
  const basePlotDisabled = $("btn-plot") ? $("btn-plot").disabled : true;

  if (anim.perSheet <= 1) {
    label.textContent = `frame ${anim.i + 1} of ${anim.n} (t=${animT(anim.i).toFixed(3)})`;
    if (btn) {
      btn.textContent = anim.plotting ? `Plotting frame ${anim.i + 1}…` : `Plot frame ${anim.i + 1}`;
      btn.disabled = anim.plotting || basePlotDisabled;
    }
    if (skip) { skip.textContent = "Skip →"; skip.disabled = anim.plotting || anim.i >= anim.n - 1; }
    return;
  }

  const nPasses = anim.passes.length;
  const p = anim.passes[anim.pass];
  const penName = p ? p.name : "…";
  label.textContent =
    `sheet ${anim.sheet + 1}/${anim.nPages} · pass ${anim.pass + 1}/${nPasses || 1} (${penName})`;
  if (btn) {
    btn.textContent = anim.plotting
      ? `Plotting sheet ${anim.sheet + 1} · pass ${anim.pass + 1}…`
      : `Plot pass ${anim.pass + 1} (${penName})`;
    btn.disabled = anim.plotting || basePlotDisabled || !nPasses;
  }
  if (skip) {
    const atEnd = anim.pass >= nPasses - 1 && anim.sheet >= anim.nPages - 1;
    skip.textContent = "Skip pass →";
    skip.disabled = anim.plotting || !nPasses || atEnd;
  }
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
  renderAnimPreview();
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

  // stepper: advance once THIS job (started via anim-plot-frame) reaches idle
  // again. Never auto-plots the next step — only unlocks the button for a fresh
  // press (swap paper → next frame/sheet, or swap pen → next pass).
  if (anim.plotting) {
    if (!idle) {
      anim.wasBusy = true;
    } else if (anim.wasBusy) {
      anim.wasBusy = false;
      anim.plotting = false;
      if (anim.perSheet <= 1) {
        anim.i = Math.min(anim.i + 1, anim.n - 1);
      } else {
        stepSheetPass();  // next pen pass, rolling to the next sheet at the end
      }
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
