// Plot tab: backend selection (capability-advertised), connection, jog & pen,
// motion params (schema-driven from the active backend), the manual multi-pen
// plot flow (target selector: all / one layer), plot-pass optimisation, the
// raw EBB trapdoor, soft limits, and the two calibration routines.

import { api } from "./api.js";
import { renderForm } from "./forms.js";
import { S, actions } from "./main.js";

const $ = (id) => document.getElementById(id);

// The machine panels — motion parameters, jog & pen, the raw EBB trapdoor,
// soft limits, holder calibration. They are built here because their handlers
// are (initPlotTab binds every id below), but they are APPENDED TO THE
// SETTINGS TAB: none of them is about running a plot, they are about the
// machine that runs it, and five of them buried the Plot tab's actual work
// ten panels deep. Settings already owned half of holder calibration (its
// reset button), so this reunites a control that was split across two tabs.
//
// Placement per panel, decided rather than defaulted: motion parameters and
// raw EBB are forms and could never be menu items; soft limits keeps its
// checkbox next to the millimetres it guards; holder calibration is a
// three-step procedure with measurements. Only the pure ACTIONS in jog & pen
// go to the Machine menu, which addresses these very buttons by id.
const MACHINE_PANELS = `    <div class="panel">
      <h2>Motion parameters <span class="tag" id="motion-backend-tag"></span></h2>
      <div id="motion-form" class="form"></div>
    </div>

    <div class="panel" id="panel-jog">
      <h2>Jog & pen</h2>
      <div class="jog-grid">
        <span></span><button id="jog-up" data-jog="0,-1">▲</button><span></span>
        <button id="jog-left" data-jog="-1,0">◀</button><button id="btn-goto-origin" title="Go to origin">⌂</button><button id="jog-right" data-jog="1,0">▶</button>
        <span></span><button id="jog-down" data-jog="0,1">▼</button><span></span>
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
        <button id="raw-block" title="Wait until the machine's motion queue drains (QG poll) — use after fire-and-forget raw motion before the next command">Wait idle</button>
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
        <button id="btn-stop" class="danger" title="Stop the job, then return the carriage to home (0,0)">Stop ⌂</button>
      </div>
      <div class="progress"><div id="progress-bar"></div></div>
      <div id="job-log" class="log"></div>
      <h3>Plot-pass optimisation <span class="hint">(applies to resolved geometry)</span></h3>
      <div id="plotopt-form" class="form"></div>
    </div>

    <div class="panel">
      <h2>Interrupted plot</h2>
      <div class="hint">bake a contiguous slice of the whole plot — random start, early stop,
        strokes cut mid-line where the pen lifted — into a new layer</div>
      <div class="row">
        <label>seed</label><input type="number" id="interrupt-seed" min="0" max="99999" step="1" style="width:6em">
        <button id="interrupt-reroll" title="new random seed">🎲</button>
        <label class="hint" style="cursor:pointer"
          title="slice in the order the machine would draw (plot-pass optimisation applied); off = layer z-order">
          <input type="checkbox" id="interrupt-optimized" checked> machine order</label>
      </div>
      <div class="row">
        <label>start</label><input type="range" id="interrupt-start" min="0" max="1" step="0.01" value="0" style="flex:1">
        <span class="hint" id="interrupt-start-val" style="min-width:3em">auto</span>
      </div>
      <div class="row">
        <label>stop</label><input type="range" id="interrupt-stop" min="0" max="1" step="0.01" value="1" style="flex:1">
        <span class="hint" id="interrupt-stop-val" style="min-width:3em">auto</span>
      </div>
      <div class="hint">"auto" = the seed picks; touch a slider to place the cut yourself</div>
      <div class="row">
        <button id="btn-interrupt" class="primary">Create interrupted layer</button>
      </div>
    </div>

    <div class="panel" id="anim-panel" data-collapse-default="1">
      <h2>Animation &amp; grid sheets</h2>
      <div class="hint">Frames on paper — preview, capture to tray, stepper, export</div>
      <div class="row">
        <label>frames</label><input type="number" id="anim-frames" min="2" max="240" step="1" style="width:5em">
        <label>t from</label><input type="number" id="anim-t-from" min="0" max="1" step="0.01" style="width:5.5em">
        <label>t to</label><input type="number" id="anim-t-to" min="0" max="1" step="0.01" style="width:5.5em">
      </div>
      <div class="hint">for one clip-frame per rendered frame, set frames = the clip's length</div>
      <div class="row">
        <label>layout</label>
        <span id="anim-presets" class="anim-presets">
          <button type="button" data-grid="1,1" title="one frame per sheet">1</button>
          <button type="button" data-grid="2,1" title="two A5-ish halves, scene flipped 90°">2</button>
          <button type="button" data-grid="2,2" title="quads">4</button>
          <button type="button" data-grid="4,2" title="eight, scene flipped 90°">8</button>
          <button type="button" data-grid="4,4" title="4×4 flipbook page">16</button>
        </span>
        <label>cols</label><input type="number" id="anim-cols" min="1" max="12" step="1" style="width:4em">
        <label>rows</label><input type="number" id="anim-rows" min="1" max="12" step="1" style="width:4em">
        <label>margin</label><input type="number" id="anim-sheet-margin" min="0" max="30" step="0.5" style="width:5em">
      </div>
      <div class="row">
        <label>framing</label>
        <select id="anim-framing" title="fixed = one shared window, motion stays motion; center = each frame centred by its own bounds (parameter sweeps)">
          <option value="fixed">fixed window (flipbook)</option>
          <option value="center">centre each frame (sweep)</option>
        </select>
        <label class="hint" style="cursor:pointer" title="small ＋ marks at the grid intersections, plotted with the first pass">
          <input type="checkbox" id="anim-marks"> crosshairs</label>
      </div>
      <div class="row"><span id="anim-layout-summary" class="hint"></span></div>
      <div class="row">
        <button id="anim-preview-render" class="primary">Render popup</button>
        <button id="anim-preview-toggle">Live play</button>
        <button id="anim-preview-step">Frame →</button>
        <label>fps</label><input type="number" id="anim-preview-fps" min="1" max="24" step="1" style="width:4em">
        <label class="hint" style="cursor:pointer"><input type="checkbox" id="anim-preview-loop"> loop</label>
      </div>
      <div class="row"><span id="anim-preview-label"></span></div>
      <div class="row">
        <button id="anim-capture" class="primary"
          title="Freeze this layout into the staging tray: per-pass geometry + a source snapshot. Tray sheets preview, plot, export, and interpolate (A ⇄ B) — the durable path.">
          Capture to tray</button>
        <a id="anim-export-link" download><button type="button">Export SVG frames (zip)</button></a>
      </div>

      <h3>Plot stepper <span class="hint">(transient — plots the layout above, one pass at a time; never auto-plots)</span></h3>
      <div class="row"><span id="anim-frame-label"></span></div>
      <div class="row">
        <button id="anim-plot-frame" class="primary">Plot frame</button>
        <button id="anim-skip">Skip →</button>
        <button id="anim-reset">Reset</button>
      </div>
    </div>

    <div class="panel">
      <h2>Staging</h2>
      <div class="row">
        <button id="stage-capture-plot">Capture plot</button>
        <button id="stage-capture-frame">Capture frame</button>
        <a id="stage-export-link" href="/api/staging/export.zip" download><button type="button">Export tray</button></a>
      </div>
      <div class="hint">grid layouts are captured from the Animation panel above (“Capture to tray”)</div>

      <h3>Quick A ⇄ B <span class="hint">(captures the current output — no need to name a tray group)</span></h3>
      <div class="row" id="ab-capture"
           title="Capture the current output as A, change anything, capture B, then ⇄ generates a staged series interpolating A → B">
        <div class="seg">
          <button id="cap-a">A</button>
          <button id="cap-b">B</button>
        </div>
        <label>steps</label>
        <input type="number" id="ab-steps" value="5" min="2" max="60" step="1"
               title="interpolation steps" style="width:4.5em">
        <button id="ab-series" disabled>⇄ series</button>
      </div>

      <h3>From the tray</h3>
      <div class="row">
        <label>A</label><select id="stage-a" style="flex:1"></select>
        <label>B</label><select id="stage-b" style="flex:1"></select>
      </div>
      <div class="row">
        <label>steps</label><input type="number" id="stage-steps" min="2" max="60" step="1" value="5" style="width:4.5em">
        <button id="stage-interp" class="primary">Generate batch</button>
      </div>
      <div class="hint">each step = one sheet; frames run across the sheet, steps run A→B between the two captures</div>
      <div id="stage-list" class="stage-list"></div>
    </div>

    <div id="anim-preview-modal" class="modal-backdrop" hidden>
      <div class="preview-modal">
        <div class="preview-head">
          <h2>Animation preview</h2>
          <button id="anim-preview-close">Close</button>
        </div>
        <div id="anim-preview-stage" class="preview-stage" style="position:relative">
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

`;


  // ---- backends / connection
  $("ports-refresh").onclick = refreshPorts;
  $("btn-connect").onclick = async () => {
    try {
      const info = await api.post("/api/connect", { port: $("port-select").value || null });
      $("connect-info").textContent = `port: ${info.port} · firmware: ${info.firmware}` +
        (info.voltage_warning ? " · ⚠ low PSU voltage (barrel-jack?) — motors won't move" : "");
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
  $("btn-stop").onclick = () => api.post("/api/plot/stop", { return_home: true }).catch(actions.oops);

  // ---- interrupted plot: bake a random pen-down slice of the whole plot
  let interruptManual = false;  // sliders untouched = the seed rolls start/stop
  const rollInterruptSeed = () => {
    $("interrupt-seed").value = Math.floor(Math.random() * 100000);
  };
  const syncInterruptLabels = (rolled) => {
    $("interrupt-start-val").textContent =
      interruptManual ? Number($("interrupt-start").value).toFixed(2)
                      : rolled != null ? rolled[0].toFixed(2) : "auto";
    $("interrupt-stop-val").textContent =
      interruptManual ? Number($("interrupt-stop").value).toFixed(2)
                      : rolled != null ? rolled[1].toFixed(2) : "auto";
  };
  rollInterruptSeed();
  for (const id of ["interrupt-start", "interrupt-stop"]) {
    $(id).oninput = () => { interruptManual = true; syncInterruptLabels(); };
  }
  $("interrupt-seed").onchange = () => { interruptManual = false; syncInterruptLabels(); };
  $("interrupt-reroll").onclick = () => {
    rollInterruptSeed();
    interruptManual = false;
    syncInterruptLabels();
  };
  $("btn-interrupt").onclick = async () => {
    const body = {
      seed: Math.max(0, Math.round(Number($("interrupt-seed").value) || 0)),
      optimized: $("interrupt-optimized").checked,
    };
    if (interruptManual) {
      body.start = Number($("interrupt-start").value);
      body.stop = Number($("interrupt-stop").value);
    }
    try {
      const r = await api.post("/api/layers/interrupt", body);
      $("interrupt-start").value = r.start;
      $("interrupt-stop").value = r.stop;
      syncInterruptLabels([r.start, r.stop]); // show what the seed picked
      await actions.refreshProject();
      await actions.refreshResolved();
      actions.setSelection([r.layer.id]);
      actions.log(`created "${r.layer.name}"`);
    } catch (e) { actions.oops(e); }
  };

  // ---- animation: one layout block feeds preview, capture, stepper, export
  $("anim-frames").value = anim.n;
  $("anim-t-from").value = anim.tFrom;
  $("anim-t-to").value = anim.tTo;
  $("anim-cols").value = anim.cols;
  $("anim-rows").value = anim.rows;
  $("anim-sheet-margin").value = anim.margin;
  $("anim-framing").value = anim.framing;
  $("anim-marks").checked = anim.marks;
  $("anim-preview-fps").value = anim.fps;
  $("anim-preview-loop").checked = anim.loop;

  const pullAnimRange = () => {
    anim.n = Math.max(2, Math.min(240, Math.round(Number($("anim-frames").value) || 2)));
    anim.tFrom = Math.max(0, Math.min(1, Number($("anim-t-from").value)));
    anim.tTo = Math.max(0, Math.min(1, Number($("anim-t-to").value)));
    anim.cols = Math.max(1, Math.min(12, Math.round(Number($("anim-cols").value) || 1)));
    anim.rows = Math.max(1, Math.min(12, Math.round(Number($("anim-rows").value) || 1)));
    anim.margin = Math.max(0, Math.min(30, Number($("anim-sheet-margin").value) || 0));
    anim.framing = $("anim-framing").value === "center" ? "center" : "fixed";
    anim.marks = $("anim-marks").checked;
    anim.i = Math.min(anim.i, anim.n - 1);
    anim.nPages = sheetPages();
    anim.sheet = Math.min(anim.sheet, anim.nPages - 1);
    renderAnimPreview();
  };
  const updateExportLink = () => {
    let href = `/api/animation/export.zip?frames=${anim.n}&t_from=${anim.tFrom}&t_to=${anim.tTo}`;
    if (gridCells() > 1) {
      href += `&cols=${anim.cols}&rows=${anim.rows}&margin_mm=${anim.margin}` +
              `&framing=${anim.framing}&marks=${anim.marks}`;
    }
    $("anim-export-link").href = href;
    const btn = $("anim-export-link").querySelector("button");
    if (btn) btn.textContent = gridCells() > 1 ? "Export sheets (zip)" : "Export SVG frames (zip)";
  };
  // Panel refresh: pull inputs, refresh the export link, re-fetch the sheet's
  // pen passes, and sync the plan overlay to the current page (one plan path).
  const refreshAnimPanel = async () => {
    pullAnimRange();
    updateExportLink();
    await refreshSheetInfo();
    syncSheetPlan();
  };

  const gridChanged = async () => {
    anim.sheet = 0; anim.pass = 0;  // layout changed → restart the two-axis stepper
    await refreshAnimPanel();
  };
  for (const id of ["anim-frames", "anim-t-from", "anim-t-to", "anim-sheet-margin",
                    "anim-framing", "anim-marks"])
    $(id).onchange = refreshAnimPanel;
  for (const id of ["anim-cols", "anim-rows"])
    $(id).onchange = gridChanged;
  for (const b of document.querySelectorAll("#anim-presets [data-grid]")) {
    b.onclick = async () => {
      const [c, r] = b.dataset.grid.split(",").map(Number);
      $("anim-cols").value = c;
      $("anim-rows").value = r;
      await gridChanged();
    };
  }
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
  // the plan overlay previews the page only while the panel is expanded (B3)
  $("anim-panel").addEventListener("panel-toggle", syncSheetPlan);

  $("anim-reset").onclick = () => {
    stopPreview();
    anim.i = 0; anim.sheet = 0; anim.pass = 0;
    anim.plotting = false; anim.wasBusy = false;
    renderAnimStepper();
    previewScrub.request(anim.i);
    if (gridCells() > 1) syncSheetPlan();  // back to page 0
  };
  $("anim-skip").onclick = () => {
    stopPreview();
    if (gridCells() <= 1) {
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
      if (gridCells() <= 1) {
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
  $("anim-capture").onclick = () => captureStaged("sheet");
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
  $("stage-capture-plot").onclick = () => captureStaged("plot");
  $("stage-capture-frame").onclick = () => captureStaged("frame");
  // append, never assign: initSettingsTab has already written its own body
  $("tab-settings").insertAdjacentHTML("beforeend", MACHINE_PANELS);

  $("stage-interp").onclick = () => interpolateStaged();
  bindAbCapture();   // rebinds after every innerHTML rebuild; `ab` outlives it
  refreshAnimPanel();
  renderStaging();

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
  $("raw-block").onclick = async () => {
    rawLog("… waiting for idle", "tx");
    try {
      await api.post("/api/machine/block", {});
      rawLog("idle (queue drained)");
    } catch (e) { rawLog(`✗ ${e.message}`, "err"); }
  };

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

// ---- A/B capture series: freeze the whole current output as A, change
// anything (params, effects, transforms), freeze B, then ⇄ generates a staged
// batch interpolating the two snapshots over N steps. Re-pressing a letter
// replaces that capture (the superseded staging group is deleted).
//
// This lived in main.js while the controls sat in the canvas toolbar. It moved
// here with them rather than staying behind as a remote handler: the toolbar
// is for tools, and everything this does is staging. `ab` is module-level for
// the reason the animation stepper below is — `initPlotTab` rebuilds the tab's
// innerHTML on every project load, so anything held in that closure would be
// lost while the captures it names still exist on the server.
const ab = { a: null, b: null };

function abRefresh() {
  if (!$("cap-a")) return;              // plot tab not built yet
  $("cap-a").classList.toggle("on", !!ab.a);
  $("cap-b").classList.toggle("on", !!ab.b);
  $("ab-series").disabled = !(ab.a && ab.b);
}

async function abCapture(which) {
  try {
    const r = await api.post("/api/staging/capture",
      { kind: "plot", target: "all", name: which.toUpperCase() });
    const old = ab[which];
    ab[which] = r.group.id;
    if (old) await api.del(`/api/staging/groups/${old}`).catch(() => {});
    await actions.refreshProject();
    actions.log(`captured ${which.toUpperCase()} — change something, capture the other, then ⇄`);
  } catch (e) { actions.oops(e); }
  abRefresh();
}

function bindAbCapture() {
  if (!$("cap-a")) return;
  $("cap-a").onclick = () => abCapture("a");
  $("cap-b").onclick = () => abCapture("b");
  $("ab-series").onclick = async () => {
    const steps = Math.max(2, Math.min(60, Math.round(Number($("ab-steps").value) || 5)));
    try {
      const r = await api.post("/api/staging/interpolate", { a: ab.a, b: ab.b, steps });
      await actions.refreshProject();
      actions.log(`⇄ series "${r.group.name}" (${steps} sheets) in the staging tray`);
    } catch (e) { actions.oops(e); }
  };
  abRefresh();                          // restore the lit letters after a rebuild
}

// ---- Animation: frame stepper state ------------------------------------------
// Module-level (survives initPlotTab's innerHTML rebuilds, e.g. on project
// switch) so the SSE-driven completion check in applyCapabilities() can
// advance it without needing its own wiring. Sequencing is entirely
// browser-side — the server has no notion of "frame N of an animation".
// cols*rows == 1: the classic one-frame-per-sheet stepper (i = frame index).
// cols*rows > 1: the two-axis grid stepper — `sheet` (physical page) × `pass`
// (pen pass on that page, from sheet_info); `passes` holds the current page's
// [{pen_id, name, color}]. One layout (cols/rows/margin/framing/marks) feeds
// the preview, the stepper, "Capture to tray" AND the export link — a single
// source of truth. All sequencing is browser-side.
const anim = {
  n: 8, tFrom: 0, tTo: 1, margin: 5, cols: 1, rows: 1,
  framing: "fixed", marks: false,
  i: 0, sheet: 0, pass: 0, passes: [], nPages: 1,
  fps: 8, loop: true,
  previewFrames: [], previewAbort: null, renderingPreview: false,
  popupI: 0, popupPlaying: false, popupTimer: null,
  previewing: false, plotting: false, wasBusy: false,
};
const stage = {
  selectedGroup: null,
  selectedSheet: null,
};

function gridDims() { return [anim.cols, anim.rows]; }
function gridCells() { return anim.cols * anim.rows; }
function sheetPages() {
  return Math.max(1, Math.ceil(anim.n / gridCells()));
}
function currentSheetSpec(extra = {}) {
  return { cols: anim.cols, rows: anim.rows, frames: anim.n,
           t_from: anim.tFrom, t_to: anim.tTo, margin_mm: anim.margin,
           framing: anim.framing, marks: anim.marks,
           page: anim.sheet, ...extra };
}

// The plan overlay/estimate previews the CURRENT page only while the Animation
// panel is expanded and per-sheet > 1; otherwise the plain target (one plan
// path). When active it ALSO swaps the centre canvas to the page's real
// geometry (the plan overlay alone only draws travel); collapsing the panel or
// dropping to a 1×1 grid exits that preview — a live staged-sheet preview is
// left alone.
function syncSheetPlan() {
  const panel = $("anim-panel");
  const open = panel && !panel.classList.contains("collapsed");
  const active = open && gridCells() > 1;
  S.sheetPlan = active ? currentSheetSpec() : null;
  if (S.sheetPlan) {
    S.stagedPlan = null;
    actions.showDocPreview(sheetPreviewLabel(),
      `sheet=${encodeURIComponent(JSON.stringify(S.sheetPlan))}`);
  } else if (S.docPreview && !S.stagedPlan) {
    actions.exitDocPreview();
  }
  actions.refreshPlan();
}

// Short human labels for the preview banner.
function sheetPreviewLabel() {
  return `${anim.n}f · ${anim.cols}×${anim.rows} · sheet ${anim.sheet + 1}/${anim.nPages}`;
}
function stagedPreviewLabel(groupId, sheetId) {
  const group = (S.state?.project?.staging || []).find((g) => g.id === groupId);
  const sheet = group?.sheets?.find((s) => !sheetId || s.id === sheetId);
  return `${group?.name || "staged"} · ${sheet?.name || "sheet"}`;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

function groupLabel(g) {
  const sheets = g.sheets?.length || 0;
  const fmt = g.format || {};
  const detail = fmt.source_kind || fmt.kind || g.kind;
  return `${g.name} · ${detail} · ${sheets} sheet${sheets === 1 ? "" : "s"}`;
}

// A/B picker label: kind + shape first, so compatible pairs are scannable.
function pickerLabel(g) {
  const f = g.format || {};
  if (g.kind === "sheet") return `${f.frames}f · ${f.cols}×${f.rows} sheet · ${g.name}`;
  return `${g.kind} · ${g.name}`;  // frame · …, plot · …, batch · …
}

// Client mirror of session._captures_compatible (plus the snapshot rule):
// returns the reason A/B can't interpolate, or null when they can. Pure —
// drives the ⇄ button's disabled state/title, the server re-validates.
function interpolateBlocker(ga, gb) {
  if (!ga || !gb) return "pick two captures";
  if (ga.id === gb.id) return "pick two different captures";
  if (ga.kind === "batch" || gb.kind === "batch") return "batch captures carry no source snapshot";
  if (ga.kind !== gb.kind) return `capture kinds differ (${ga.kind} vs ${gb.kind})`;
  if (ga.kind === "sheet") {
    for (const k of ["cols", "rows", "frames", "t_from", "t_to"]) {
      if ((ga.format || {})[k] !== (gb.format || {})[k]) {
        return `sheet layouts differ: ${k} (${ga.format?.[k]} vs ${gb.format?.[k]})`;
      }
    }
  }
  return null;
}

function updateInterpButton() {
  const btn = $("stage-interp");
  if (!btn) return;
  const groups = S.state?.project?.staging || [];
  const ga = groups.find((g) => g.id === $("stage-a")?.value);
  const gb = groups.find((g) => g.id === $("stage-b")?.value);
  const why = interpolateBlocker(ga, gb);
  btn.disabled = !!why;
  btn.title = why || "n sheets stepping A→B between the two captures";
}

async function captureStaged(kind) {
  try {
    pullAnimControls();  // module scope — pullAnimRange is initPlotTab's closure
    const body = {
      kind,
      target: S.plotTarget,
      name: kind === "frame" ? `frame ${anim.i + 1}` :
        kind === "sheet" ? `${anim.n}-frame grid` : `plot ${targetLabel()}`,
    };
    if (kind === "frame") body.master_t = animT(anim.i);
    if (kind === "sheet") {
      body.cols = anim.cols;
      body.rows = anim.rows;
      body.frames = anim.n;
      body.t_from = anim.tFrom;
      body.t_to = anim.tTo;
      body.margin_mm = anim.margin;
      body.framing = anim.framing;
      body.marks = anim.marks;
      body.name = `${anim.n}f · ${anim.cols}×${anim.rows} · ${anim.framing}`;
    }
    const r = await api.post("/api/staging/capture", body);
    await actions.refreshProject();
    actions.log(`captured ${r.group.name} to staging`);
    // immediately visible: select + canvas-preview the new group's first sheet
    await previewStaged(r.group.id, r.group.sheets[0]?.id);
  } catch (e) { actions.oops(e); }
}

async function interpolateStaged() {
  const a = $("stage-a")?.value;
  const b = $("stage-b")?.value;
  if (!a || !b || a === b) {
    actions.oops(new Error("pick two different compatible captures"));
    return;
  }
  const steps = Math.max(2, Math.min(60, Math.round(Number($("stage-steps").value) || 5)));
  try {
    const r = await api.post("/api/staging/interpolate", { a, b, steps });
    await actions.refreshProject();
    actions.log(`generated staged batch ${r.group.name}`);
    // immediately visible: select + canvas-preview the batch's first sheet
    await previewStaged(r.group.id, r.group.sheets[0]?.id);
  } catch (e) { actions.oops(e); }
}

async function previewStaged(groupId, sheetId) {
  S.sheetPlan = null;
  S.stagedPlan = { group_id: groupId, sheet_id: sheetId };
  stage.selectedGroup = groupId;
  stage.selectedSheet = sheetId;
  renderStaging();
  // swap the centre canvas to the staged sheet's actual geometry (the plan
  // overlay only draws travel); estimate/travel still ride S.stagedPlan below.
  await actions.showDocPreview(stagedPreviewLabel(groupId, sheetId),
    `staged=${encodeURIComponent(JSON.stringify(S.stagedPlan))}`);
  await actions.refreshPlan();
}

async function plotStaged(groupId, sheetId, penId) {
  try {
    await api.post("/api/plot/start", { staged: { group_id: groupId, sheet_id: sheetId, pen_id: penId } });
    actions.log(`▶ plotting staged sheet pass (${penId || "no pen"})`);
  } catch (e) { actions.oops(e); }
}

async function insertStaged(groupId, sheetId) {
  try {
    await api.post(`/api/staging/groups/${encodeURIComponent(groupId)}/sheets/${encodeURIComponent(sheetId)}/insert`, {});
    await actions.refreshProject();
    await actions.refreshResolved();
    renderStaging();
    actions.log("inserted staged sheet as editable layers");
  } catch (e) { actions.oops(e); }
}

async function deleteStaged(groupId) {
  try {
    await api.del(`/api/staging/groups/${encodeURIComponent(groupId)}`);
    if (stage.selectedGroup === groupId) {
      stage.selectedGroup = null;
      stage.selectedSheet = null;
      S.stagedPlan = null;
      actions.exitDocPreview();  // the previewed sheet is gone — back to project
    }
    await actions.refreshProject();
    renderStaging();
    await actions.refreshPlan();
  } catch (e) { actions.oops(e); }
}

async function duplicateStaged(groupId) {
  try {
    await api.post(`/api/staging/groups/${encodeURIComponent(groupId)}/duplicate`, {});
    await actions.refreshProject();
    renderStaging();
  } catch (e) { actions.oops(e); }
}

async function renameStaged(groupId) {
  const group = (S.state.project.staging || []).find((g) => g.id === groupId);
  const name = window.prompt("Capture name", group?.name || "");
  if (!name) return;
  try {
    await api.patch(`/api/staging/groups/${encodeURIComponent(groupId)}`, { name });
    await actions.refreshProject();
    renderStaging();
  } catch (e) { actions.oops(e); }
}

async function moveStaged(groupId, dir) {
  const groups = S.state.project.staging || [];
  const ids = groups.map((g) => g.id);
  const i = ids.indexOf(groupId);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= ids.length) return;
  [ids[i], ids[j]] = [ids[j], ids[i]];
  try {
    await api.post("/api/staging/reorder", { ids });
    await actions.refreshProject();
    renderStaging();
  } catch (e) { actions.oops(e); }
}

// Re-layout row for the SELECTED tray group, grid captures only (sheet, or a
// batch whose source was a sheet). Renders nothing otherwise — frame/plot
// captures have no cols/rows to change (the server refuses them too).
function relayoutRow(g) {
  const isGrid = g.kind === "sheet" || (g.kind === "batch" && g.format?.source_kind === "sheet");
  if (!isGrid || stage.selectedGroup !== g.id) return "";
  const f = g.format || {};
  return `
    <div class="row stage-relayout">
      <label>re-layout</label>
      <input type="number" data-rl-cols min="1" max="12" step="1" value="${Number(f.cols) || 1}" style="width:3.5em">
      <span>×</span>
      <input type="number" data-rl-rows min="1" max="12" step="1" value="${Number(f.rows) || 1}" style="width:3.5em">
      <button data-stage-relayout="${esc(g.id)}" title="re-render this capture at a new grid (new tray group)">apply</button>
    </div>`;
}

async function relayoutStaged(groupId, cols, rows) {
  try {
    const r = await api.post(
      `/api/staging/groups/${encodeURIComponent(groupId)}/relayout`, { cols, rows });
    await actions.refreshProject();
    actions.log(`re-laid ${r.group.name}`);
    await previewStaged(r.group.id, r.group.sheets[0]?.id);  // 2b machinery
  } catch (e) { actions.oops(e); }
}

function renderStaging() {
  const list = $("stage-list");
  if (!list || !S.state?.project) return;
  const groups = S.state.project.staging || [];
  for (const id of ["stage-a", "stage-b"]) {
    const sel = $(id);
    if (!sel) continue;
    const prior = sel.value;
    sel.innerHTML = `<option value="">—</option>` + groups.map((g) =>
      `<option value="${esc(g.id)}">${esc(pickerLabel(g))}</option>`).join("");
    sel.value = groups.some((g) => g.id === prior) ? prior : "";
    sel.onchange = updateInterpButton;
  }
  updateInterpButton();
  $("stage-export-link").href = "/api/staging/export.zip";
  if (!groups.length) {
    list.innerHTML = `<div class="hint">No staged captures yet.</div>`;
    return;
  }
  list.innerHTML = groups.map((g) => `
    <div class="stage-group">
      <div class="stage-head">
        <strong>${esc(g.name)}</strong>
        <span class="hint">${esc(g.kind)} · ${(g.sheets || []).length} sheet${(g.sheets || []).length === 1 ? "" : "s"}</span>
        <button data-stage-rename="${esc(g.id)}">Rename</button>
        <button data-stage-up="${esc(g.id)}">↑</button>
        <button data-stage-down="${esc(g.id)}">↓</button>
        <button data-stage-copy="${esc(g.id)}">Duplicate</button>
        <button data-stage-export="${esc(g.id)}">Export</button>
        <button class="danger" data-stage-delete="${esc(g.id)}">Delete</button>
      </div>
      ${(g.warnings || []).length ? `<div class="hint warn">${esc(g.warnings.join("; "))}</div>` : ""}
      ${relayoutRow(g)}
      ${(g.sheets || []).map((s) => `
        <div class="stage-sheet ${stage.selectedGroup === g.id && stage.selectedSheet === s.id ? "on" : ""}">
          <button data-stage-preview="${esc(g.id)}:${esc(s.id)}">Preview ${esc(s.name)}</button>
          <button data-stage-insert="${esc(g.id)}:${esc(s.id)}"
            title="bake this sheet into editable project layers (one per pen pass), hiding the current layers — the way to hand-edit a rendered grid">Insert as layers</button>
          ${(s.passes || []).map((p) =>
            `<button data-stage-plot="${esc(g.id)}:${esc(s.id)}:${esc(p.pen_id)}">${esc(p.name)} · ${p.paths} paths</button>`
          ).join("")}
        </div>
      `).join("")}
    </div>
  `).join("");
  list.querySelectorAll("[data-stage-preview]").forEach((b) => b.onclick = () => {
    const [g, s] = b.dataset.stagePreview.split(":");
    previewStaged(g, s);
  });
  list.querySelectorAll("[data-stage-plot]").forEach((b) => b.onclick = () => {
    const [g, s, p] = b.dataset.stagePlot.split(":");
    plotStaged(g, s, p || "");
  });
  list.querySelectorAll("[data-stage-insert]").forEach((b) => b.onclick = () => {
    const [g, s] = b.dataset.stageInsert.split(":");
    insertStaged(g, s);
  });
  list.querySelectorAll("[data-stage-relayout]").forEach((b) => b.onclick = () => {
    const row = b.closest(".stage-relayout");
    const cols = Math.max(1, Math.min(12, Math.round(Number(row.querySelector("[data-rl-cols]").value) || 1)));
    const rows = Math.max(1, Math.min(12, Math.round(Number(row.querySelector("[data-rl-rows]").value) || 1)));
    relayoutStaged(b.dataset.stageRelayout, cols, rows);
  });
  list.querySelectorAll("[data-stage-delete]").forEach((b) => b.onclick = () => deleteStaged(b.dataset.stageDelete));
  list.querySelectorAll("[data-stage-copy]").forEach((b) => b.onclick = () => duplicateStaged(b.dataset.stageCopy));
  list.querySelectorAll("[data-stage-rename]").forEach((b) => b.onclick = () => renameStaged(b.dataset.stageRename));
  list.querySelectorAll("[data-stage-up]").forEach((b) => b.onclick = () => moveStaged(b.dataset.stageUp, -1));
  list.querySelectorAll("[data-stage-down]").forEach((b) => b.onclick = () => moveStaged(b.dataset.stageDown, 1));
  list.querySelectorAll("[data-stage-export]").forEach((b) => b.onclick = () => {
    window.location.href = `/api/staging/export.zip?group_id=${encodeURIComponent(b.dataset.stageExport)}`;
  });
}

// Re-fetch the current sheet's ordered pen passes (they differ per page).
async function refreshSheetInfo() {
  if (gridCells() <= 1) {
    anim.passes = []; anim.nPages = 1;
    renderLayoutSummary(null);
    renderAnimStepper();
    return;
  }
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
    renderLayoutSummary(info);
  } catch (e) {
    anim.passes = [];
    renderLayoutSummary(null);
  }
  renderAnimStepper();
}

// One line that says what the layout MEANS physically, before anything plots.
function renderLayoutSummary(info) {
  const el = $("anim-layout-summary");
  if (!el) return;
  if (gridCells() <= 1) {
    el.textContent = `${anim.n} frames → ${anim.n} single-frame plots (stepper below)`;
    return;
  }
  const pages = info ? info.sheets : sheetPages();
  const passes = info && info.passes ? info.passes.map((p) => p.name).join(", ") : "…";
  el.textContent =
    `${anim.n} frames → ${pages} sheet${pages === 1 ? "" : "s"} of ${anim.cols}×${anim.rows}` +
    ` · page ${Math.min(anim.sheet, pages - 1) + 1}: ${passes}` +
    (anim.marks ? " · ✚ crosshairs on first pass" : "");
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
  anim.cols = Math.max(1, Math.min(12, Math.round(Number($("anim-cols").value) || 1)));
  anim.rows = Math.max(1, Math.min(12, Math.round(Number($("anim-rows").value) || 1)));
  anim.margin = Math.max(0, Math.min(30, Number($("anim-sheet-margin").value) || 0));
  anim.framing = $("anim-framing")?.value === "center" ? "center" : "fixed";
  anim.marks = Boolean($("anim-marks")?.checked);
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

// Swap the live frame set for a freshly-rendered one, revoking the old
// object URLs only now that their replacements are in hand. Frame count can
// change between renders, so popupI is reclamped to the new set.
function swapRasterFrames(newFrames) {
  const old = anim.previewFrames;
  anim.previewFrames = newFrames;
  anim.popupI = newFrames.length ? Math.min(anim.popupI, newFrames.length - 1) : 0;
  for (const frame of old) URL.revokeObjectURL(frame.url);
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
    // With frames already on screen, a re-render's progress message is a small
    // overlay badge — it must never blank the image the user is looking at.
    // With no frames yet (first-ever render), it's the full centered hint.
    empty.hidden = hasFrames && !message;
    empty.textContent = message || "";
    empty.classList.toggle("preview-overlay-badge", hasFrames && Boolean(message));
    if (hasFrames && message) {
      empty.style.position = "absolute";
      empty.style.left = "8px";
      empty.style.bottom = "8px";
      empty.style.right = "8px";
      empty.style.margin = "0";
      empty.style.padding = "3px 7px";
      empty.style.background = "color-mix(in srgb, var(--paper-deep) 88%, transparent)";
      empty.style.border = "1px solid var(--line)";
      empty.style.borderRadius = "4px";
      empty.style.pointerEvents = "none";
    } else {
      empty.style.cssText = "";
    }
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
  // Deliberately do NOT clear anim.previewFrames here: the last render stays
  // on screen (img + playback controls) while the new one renders into a
  // scratch buffer. It's only swapped in on success — see swapRasterFrames.
  const modal = $("anim-preview-modal");
  if (modal) modal.hidden = false;
  setRasterProgress(0, anim.n);
  renderRasterControls(`rendering frame 0/${anim.n}`);

  const newFrames = [];
  let swapped = false;
  try {
    for (let i = 0; i < anim.n; i++) {
      if (controller.signal.aborted) return;
      const t = animT(i);
      renderRasterControls(`rendering frame ${i + 1}/${anim.n}`);
      const url = `/api/animation/preview.png?t=${encodeURIComponent(t)}&width_px=1200`;
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      newFrames.push({ url: URL.createObjectURL(blob), t });
      setRasterProgress(i + 1, anim.n);
      if (!anim.previewFrames.length && newFrames.length === 1) {
        // first-ever render (no old set to keep showing): alias the scratch
        // buffer as the live set so frame 0 shows the moment it lands and the
        // remaining progress renders as the badge overlay, not a blank stage
        anim.previewFrames = newFrames;
        anim.popupI = 0;
        showRasterFrame(0);
      }
    }
    if (anim.previewFrames !== newFrames) swapRasterFrames(newFrames);
    swapped = true;
    anim.renderingPreview = false;
    anim.previewAbort = null;
    showRasterFrame(0);
    startRasterPlayback();
  } catch (e) {
    if (e.name !== "AbortError") actions.oops(e);
  } finally {
    // Render aborted, failed, or exited early partway through: drop whatever
    // scratch frames we'd fetched so far (revoke their URLs) and leave the
    // old, still-valid frame set exactly as it was — nothing new to show,
    // nothing to leak. On success the scratch buffer is already emptied by
    // swapRasterFrames, so this is a no-op. When a first-ever render aliased
    // the scratch buffer as the live set, its frames are on screen — keep them.
    if (!swapped && anim.previewFrames !== newFrames)
      for (const frame of newFrames) URL.revokeObjectURL(frame.url);
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

  if (gridCells() <= 1) {
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
  renderStaging();
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
  $("raw-send").disabled = $("raw-input").disabled = $("raw-block").disabled = !(caps.raw_ebb && connected && idle);
  $("btn-plot").disabled = !(connected && idle);
  // once connected, Connect is no longer the thing to do — stop styling it as
  // the primary path (it was the brightest control in the panel while idle)
  $("btn-connect").classList.toggle("primary", !connected);
  $("btn-pause").disabled = !(caps.pause_resume && m.job_state === "plotting");
  $("btn-resume").disabled = !(m.job_state === "paused");
  $("btn-stop").disabled = idle;
  $("port-select").disabled = $("ports-refresh").disabled = !caps.requires_serial_port;
  $("backend-notes").textContent = caps.notes || "";
  // reflect server-side connections too (auto-connect at startup)
  const info = m.connect_info || {};
  if (connected && info.firmware) {
    $("connect-info").textContent = `port: ${info.port} · firmware: ${info.firmware}` +
      (info.voltage_warning ? " · ⚠ low PSU voltage (barrel-jack?) — motors won't move" : "");
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
      if (gridCells() <= 1) {
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
