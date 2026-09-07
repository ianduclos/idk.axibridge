// Plot tab: backend selection (capability-advertised), connection, pen & origin,
// motion params (schema-driven from the active backend), the manual multi-pen
// plot flow (target selector: all / one layer), plot-pass optimisation, the
// raw EBB trapdoor, soft limits, and the two calibration routines.

import { api } from "./api.js";
import { renderForm } from "./forms.js";
import { S, actions } from "./main.js";
// S5 (docs/plans/timeline-v2.md): recordFetchedFrame marks a grid tick lit in
// the bar; renderTimelineBar re-syncs the bar's shaded range after an
// Animation-panel edit to t-from/t-to/frames changes the grid under it.
// Circular with timeline.js (which imports stepFrame/renderRasterPreview
// below) — safe here the same way main.js<->timeline.js already is: every
// use is inside a function body, called long after both modules finished
// evaluating, never at module-top-level.
import { recordFetchedFrame, renderTimelineBar, jumpTo } from "./timeline.js";

const $ = (id) => document.getElementById(id);

// The machine panels — motion parameters, pen & origin, the raw EBB trapdoor,
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
// three-step procedure with measurements. Only the pure ACTIONS in pen &
// origin go to the Machine menu, which addresses these very buttons by id.
//
// Motion parameters is split out of MACHINE_PANELS (2026-08-11, Ian): it
// belongs right after Paper guide, not at the tail of the tab, so it is
// inserted separately after `#panel-paper-guide` (settings.js) instead of
// being appended with the rest — same handlers, same `initPlotTab`, just a
// different insertion point.
const MOTION_PANEL = `    <div class="panel">
      <h2>Motion parameters <span class="tag" id="motion-backend-tag"></span></h2>
      <div id="motion-form" class="form"></div>
    </div>`;

const MACHINE_PANELS = `    <div class="panel" id="panel-pen">
      <h2>Pen & origin</h2>
      <div class="row">
        <button id="btn-pen-up">Pen up</button>
        <button id="btn-pen-down">Pen down</button>
        <button id="btn-goto-origin" title="Return the carriage to 0,0">⌂ Go to origin</button>
      </div>
      <div class="row">
        <button id="btn-set-origin" title="Declare current position (0,0)">Set origin</button>
        <button id="btn-origin-guide" title="Put the carriage on the paper guide corner first, then press">Origin = guide corner</button>
        <span class="hint">position: <span id="pos-readout">—</span></span>
      </div>
      <details class="ld-section" data-fold="pen-height">
        <summary>Pen height test <span class="hint">(live — tweak heights above, then:)</span></summary>
        <div class="row">
          <button id="btn-pen-cycle">Cycle ↓↑</button>
          <button id="btn-test-stroke">Test stroke (20mm)</button>
          <select id="save-heights-pen"><option value="">save heights to pen…</option></select>
        </div>
      </details>
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
      <!-- What ▶ Plot will actually put on paper, stated in words, whenever
           that is NOT the plain live project (docs/plans/timeline-v2.md §2c
           "Plot flow"). Plot obeys the canvas view label, so on a sheet/tray
           view it plots what you are looking at rather than the live target —
           the mitigation Ian asked for is visibility, not a confirm dialog,
           so this line names the sheet and its pass count before the press. -->
      <div class="hint" id="plot-view-target"></div>
      <div class="row" style="justify-content:center; margin-top:6px">
        <button id="btn-plot" class="primary big">Plot</button>
        <span class="hint">pause and stop live in the status line under the sheet</span>
      </div>
      <div class="progress"><div id="progress-bar"></div></div>
      <div id="job-log" class="log"></div>
      <details class="ld-section" data-fold="plot-opt">
        <summary>Plot-pass optimisation <span class="hint">(applies to resolved geometry)</span></summary>
        <div id="plotopt-form" class="form"></div>
      </details>
    </div>

    <div class="panel">
      <h2>Interrupted plot</h2>
      <div class="hint">bake a contiguous slice of the whole plot — random start, early stop,
        strokes cut mid-line where the pen lifted — into a new layer</div>
      <div class="row">
        <label>seed</label><input type="number" id="interrupt-seed" min="0" max="99999" step="1" style="width:6em">
        <button id="interrupt-reroll" title="new random seed" aria-label="New random seed"><svg class="tool-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 8h.01M16 8h.01M12 12h.01M8 16h.01M16 16h.01"/></svg></button>
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
      <!-- P2: a follow_master tween whose window is narrower than one frame
           step can be skipped entirely by every output (export/sheets/popup
           all sample the same grid) — a mystifying blank sheet otherwise. -->
      <div class="hint warn" id="anim-narrow-tween-hint" hidden></div>
      <div class="row">
        <label>layout</label>
        <label>cols</label><input type="number" id="anim-cols" min="1" max="12" step="1" style="width:4em">
        <label>rows</label><input type="number" id="anim-rows" min="1" max="12" step="1" style="width:4em">
        <label>margin</label><input type="number" id="anim-sheet-margin" min="0" max="30" step="0.5" style="width:5em">
      </div>
      <div class="row">
        <label>crop</label>
        <select id="anim-crop" title="timeline = one shared window across every frame, so relative motion survives (the default); full = no crop, every frame keeps the whole page (negative space preserved)">
          <option value="timeline">timeline (motion survives)</option>
          <option value="full">full page (no crop)</option>
        </select>
        <label class="hint" style="cursor:pointer" title="small ＋ marks at the grid intersections, plotted with the first pass">
          <input type="checkbox" id="anim-marks"> crosshairs</label>
      </div>
      <div class="row"><span id="anim-layout-summary" class="hint"></span></div>
      <div class="row">
        <button id="anim-preview-render" class="primary">Render popup</button>
        <button id="anim-preview-toggle">Live play</button>
        <button id="anim-preview-step">Frame →</button>
        <label title="in-canvas Live play speed only — the render popup has its own fps for playback/export">live fps</label>
        <input type="number" id="anim-preview-fps" min="1" max="24" step="1" style="width:4em">
        <label class="hint" style="cursor:pointer"><input type="checkbox" id="anim-preview-loop"> loop</label>
      </div>
      <div class="row"><span id="anim-preview-label"></span></div>
      <div class="row">
        <button id="anim-capture" class="primary"
          title="Bake this layout into the tray: rows×cols frames per sheet, ⌈frames/cells⌉ sheets in ONE group, orientation auto-decided (rotated 90° inside each cell when that fits better). Tray sheets preview, plot, export, and interpolate (A ⇄ B) — the durable path.">
          Bake sheet</button>
        <a id="anim-export-link" download><button type="button">Export SVG frames (zip)</button></a>
      </div>

      <details class="ld-section" data-fold="plot-stepper">
        <summary>Plot stepper <span class="hint">(transient — one pass at a time; never auto-plots)</span></summary>
        <div class="row"><span id="anim-frame-label"></span></div>
        <div class="row" id="anim-start-frame-row">
          <label>frame</label>
          <input type="number" id="anim-start-frame" min="1" step="1" style="width:5em">
          <span class="hint">of <span id="anim-start-frame-n">…</span></span>
          <button id="anim-start-frame-go"
            title="jump the stepper to this frame and set it as your Reset point">Start here</button>
        </div>
        <div class="row" id="anim-start-sheet-row">
          <label>sheet</label>
          <input type="number" id="anim-start-sheet" min="1" step="1" style="width:5em">
          <span class="hint">of <span id="anim-start-sheet-n">…</span></span>
          <button id="anim-start-sheet-go"
            title="jump the stepper to this sheet and set it as your Reset point">Start here</button>
        </div>
        <div class="row">
          <button id="anim-plot-frame" class="primary">Plot frame</button>
          <button id="anim-skip">Skip →</button>
          <button id="anim-reset">Reset</button>
          <button id="anim-reset-true"
            title="the true beginning — sheet 1 / frame 1, ignoring any chosen start">⤒ 1</button>
        </div>
      </details>
    </div>

    <div class="panel">
      <h2>Staging</h2>
      <div class="row">
        <button id="stage-capture-plot">Capture plot</button>
        <button id="stage-capture-frame">Capture frame</button>
        <a id="stage-export-link" href="/api/staging/export.zip" download><button type="button">Export tray</button></a>
      </div>
      <div class="hint">grid layouts are captured from the Animation panel above (“Bake sheet”)</div>

      <details class="ld-section" data-fold="stage-ab" data-fold-open="1">
        <summary>Quick A ⇄ B <span class="hint">(captures the current output — no tray group needed)</span></summary>
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
      </details>

      <details class="ld-section" data-fold="stage-tray" data-fold-open="1">
        <summary>From the tray</summary>
        <div class="row">
          <label>A</label><select id="stage-a" style="flex:1"></select>
          <label>B</label><select id="stage-b" style="flex:1"></select>
        </div>
        <!-- P7: these pickers (any two existing tray captures) and Quick A⇄B
             above (capture-and-blend in one pass) both end at the same
             interpolate endpoint — deliberate, deliberate vs quick, but
             nothing on screen said so until now. -->
        <div class="hint">or use A · B · ⇄ above to capture and blend in one pass</div>
        <div class="row">
          <label>steps</label><input type="number" id="stage-steps" min="2" max="60" step="1" value="5" style="width:4.5em">
          <button id="stage-interp" class="primary">Generate batch</button>
        </div>
        <!-- P8: interpolateBlocker's reason, visible — it was already
             computed and sat invisibly in the button's title. -->
        <div class="hint warn" id="stage-interp-hint" hidden></div>
        <div class="hint">each step = one sheet; frames run across the sheet, steps run A→B between the two captures</div>
        <div id="stage-list" class="stage-list"></div>
      </details>
    </div>

`;
  // #anim-preview-modal (the render popup) is NOT built here — it's static
  // top-level markup in index.html now (Ian, 2026-08-11 bench check: it must
  // open from any tab, and a tab body that goes `hidden` on switch takes
  // every descendant with it, including a `position:fixed` modal). The
  // wiring below still addresses it by id; `initRasterZoomPan()` guards
  // itself against re-registering listeners on the now-persistent element
  // (see its own comment) since this whole function re-runs on every
  // project load.


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
  $("btn-plot").onclick = () => plotPressed();
  $("btn-pause").onclick = () => api.post("/api/plot/pause").catch(actions.oops);
  $("btn-resume").onclick = () => api.post("/api/plot/resume").catch(actions.oops);
  // Stop is the queue's cancel too: no queue state survives a stop, so the
  // next ▶ Plot starts from whatever the view says, never from a half-walked
  // pass list (docs/plans/timeline-v2.md §2c "Plot flow").
  $("btn-stop").onclick = () => {
    cancelPlotQueue();
    api.post("/api/plot/stop", { return_home: true }).catch(actions.oops);
  };

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
  $("anim-crop").value = anim.crop;
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
    anim.crop = $("anim-crop").value === "full" ? "full" : "timeline";
    anim.marks = $("anim-marks").checked;
    anim.i = Math.min(anim.i, anim.n - 1);
    anim.nPages = sheetPages();
    anim.sheet = Math.min(anim.sheet, anim.nPages - 1);
    renderAnimPreview();
    renderNarrowTweenHint(); // P2 — frames/t-from/t-to just moved the grid step
  };
  const updateExportLink = () => {
    let href = `/api/animation/export.zip?frames=${anim.n}&t_from=${anim.tFrom}&t_to=${anim.tTo}`;
    if (gridCells() > 1) {
      href += `&cols=${anim.cols}&rows=${anim.rows}&margin_mm=${anim.margin}` +
              `&crop=${anim.crop}&marks=${anim.marks}`;
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
    renderTimelineBar(); // S5: frames/t-from/t-to just moved the grid under the bar's shading+ticks
  };

  const gridChanged = async () => {
    anim.sheet = 0; anim.pass = 0;  // layout changed → restart the two-axis stepper
    await refreshAnimPanel();
  };
  for (const id of ["anim-frames", "anim-t-from", "anim-t-to", "anim-sheet-margin",
                    "anim-crop", "anim-marks"])
    $(id).onchange = refreshAnimPanel;
  for (const id of ["anim-cols", "anim-rows"])
    $(id).onchange = gridChanged;
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

  // S6 — start from sheet/frame N: sets anim.sheet/anim.i and remembers it as
  // the Reset point (P5), then re-fetches pass info + syncs the plan overlay
  // exactly as stepSheetPass() already does after a sheet change.
  $("anim-start-frame-go").onclick = () => {
    stopPreview();
    const n1 = Math.max(1, Math.min(anim.n, Math.round(Number($("anim-start-frame").value) || 1)));
    anim.i = anim.startI = n1 - 1;
    renderAnimStepper();
    previewScrub.request(anim.i);
  };
  $("anim-start-sheet-go").onclick = async () => {
    const n1 = Math.max(1, Math.min(anim.nPages, Math.round(Number($("anim-start-sheet").value) || 1)));
    anim.sheet = anim.startSheet = n1 - 1;
    anim.pass = 0;
    await refreshSheetInfo();
    syncSheetPlan();
  };
  // P5: Reset returns to the CHOSEN start (default 0/0 if none was ever set),
  // never to zero out from under a from-sheet-7 run — a separate ⤒1 control
  // covers the true beginning. Both re-fetch sheet info since the target page
  // may not be the one whose pass list is currently cached.
  $("anim-reset").onclick = async () => {
    stopPreview();
    anim.i = Math.min(anim.startI || 0, Math.max(0, anim.n - 1));
    anim.sheet = Math.min(anim.startSheet || 0, Math.max(0, anim.nPages - 1));
    anim.pass = 0;
    anim.plotting = false; anim.wasBusy = false;
    await refreshSheetInfo();
    previewScrub.request(anim.i);
    if (gridCells() > 1) syncSheetPlan();
  };
  $("anim-reset-true").onclick = async () => {
    stopPreview();
    anim.i = 0; anim.sheet = 0; anim.pass = 0;
    anim.plotting = false; anim.wasBusy = false;
    await refreshSheetInfo();
    previewScrub.request(anim.i);
    if (gridCells() > 1) syncSheetPlan();
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
  $("anim-preview-palindrome").checked = anim.palindrome;
  $("anim-preview-palindrome").onchange = () => {
    anim.palindrome = $("anim-preview-palindrome").checked;
    // ping-pong order changed under an active playback loop — resync position
    // to wherever the current frame actually sits in the new order
    if (anim.popupPlaying) startRasterPlayback();
    updateRasterExportLinks();
  };
  $("anim-preview-scale").value = String(anim.scale);
  $("anim-preview-scale").onchange = () => {
    anim.scale = Math.max(1, Math.min(4, Math.round(Number($("anim-preview-scale").value)) || 1));
    // 2026-08-11 ruling: a resolution change re-renders, it doesn't just wait
    // for the next manual "Render popup" press — the whole point of picking
    // a resolution is seeing it. renderRasterPreview() re-fetches every
    // frame at the new scale and its own flow already calls
    // updateRasterExportLinks() once the set lands.
    renderRasterPreview();
  };
  $("anim-preview-popup-fps").value = String(anim.popupFps);
  $("anim-preview-popup-fps").onchange = () => {
    anim.popupFps = Math.max(1, Math.min(24, Math.round(Number($("anim-preview-popup-fps").value)) || 8));
    $("anim-preview-popup-fps").value = String(anim.popupFps);
    updateRasterExportLinks();
  };
  initRasterZoomPan();
  $("stage-capture-plot").onclick = () => captureStaged("plot");
  $("stage-capture-frame").onclick = () => captureStaged("frame");
  // append, never assign: initSettingsTab has already written its own body.
  // Motion parameters goes right after Paper guide (Ian, 2026-08-11); the
  // rest tail the settings tab as before.
  $("panel-paper-guide").insertAdjacentHTML("afterend", MOTION_PANEL);
  $("tab-settings").insertAdjacentHTML("beforeend", MACHINE_PANELS);

  $("stage-interp").onclick = () => interpolateStaged();
  bindAbCapture();   // rebinds after every innerHTML rebuild; `ab` outlives it
  refreshAnimPanel();
  renderStaging();

  // ---- pen / origin
  $("btn-goto-origin").onclick = () =>
    api.post("/api/machine/goto", { x: 0, y: 0 }).then((r) => setPos(r.position)).catch(actions.oops);
  $("btn-pen-up").onclick = () => api.post("/api/machine/pen", { down: false }).catch(actions.oops);
  $("btn-pen-down").onclick = () => api.post("/api/machine/pen", { down: true }).catch(actions.oops);
  $("btn-set-origin").onclick = () =>
    api.post("/api/machine/origin", { x: 0, y: 0 }).then(actions.refreshState).catch(actions.oops);
  // put the carriage on the physical corner of the taped sheet, then press:
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
// [{pen_id, name, color}]. One layout (cols/rows/margin/crop/marks) feeds
// the preview, the stepper, "Bake sheet" AND the export link — a single
// source of truth. All sequencing is browser-side.
const anim = {
  n: 8, tFrom: 0, tTo: 1, margin: 5, cols: 1, rows: 1,
  crop: "timeline", marks: false,
  i: 0, sheet: 0, pass: 0, passes: [], nPages: 1,
  // S6 — the chosen "start here" (P5): what Reset returns to. 0/0 until the
  // user picks a start explicitly; ⤒1 always means true 0/0 regardless.
  startI: 0, startSheet: 0,
  fps: 8, loop: true,
  previewFrames: [], previewAbort: null, renderingPreview: false,
  popupI: 0, popupPos: 0, popupPlaying: false, popupTimer: null,
  previewing: false, plotting: false, wasBusy: false,
  // render-popup upgrades (E6): palindrome playback/export order, render
  // resolution multiplier (server-bounded 1-4x — see /api/animation/preview.png),
  // and CSS-transform zoom/pan state for the popup's <img> (view only — never
  // touches canvas.js's zoom machinery, which is a different coordinate space).
  palindrome: false, scale: 1,
  // popupFps is the render popup's OWN fps (playback + GIF/MP4 export) —
  // deliberately split from `fps` above (2026-08-11, Ian): that field still
  // drives the Animation panel's in-canvas Live play (schedulePreviewNext),
  // a different consumer with different needs, so one shared field would
  // fight itself the moment either control moved independently.
  popupFps: 8,
  zoom: 1, panX: 0, panY: 0,
};
const stage = {
  selectedGroup: null,
  selectedSheet: null,
};
// P6 — plotted-this-session marks: a client-side, unpersisted record of
// (group, sheet, pass) fired via plotStaged, so after a pen swap it's
// visible at a glance which of N staged sheets is still ahead. Cleared on
// reload by design (no persistence — Ian: "no persistence across project
// close needed").
const plottedThisSession = new Set();
const plottedKey = (groupId, sheetId, penId) => `${groupId}:${sheetId}:${penId}`;

// ---- ▶ Plot obeys the view label + the guided pass queue ---------------------
// docs/plans/timeline-v2.md §2c "Plot flow" (ruled 2026-08-11).
//
// ROUTING. The button plots exactly what the canvas shows, and the decision
// reads the SAME state the canvas status label reads — `S.docPreview`, whose
// only writers are main.js's showDocPreview/clearDocPreviewState. There is no
// second record of "which view is up", so the button cannot disagree with the
// label. Three cases, and only three, because docPreview has only three:
//   null            → the plain live project: today's behaviour, byte for byte,
//                     including the all/layer/pen target picker.
//   kind "sheet"    → the live grid-sheet preview: that page's pen passes.
//   kind "tray"     → a frozen staged sheet: that sheet's pen passes.
// The payloads are the EXISTING per-pass plot calls (`sheet=` / `staged=` on
// POST /api/plot/start) — this is client-side sequencing over calls the tray
// buttons and the stepper already made. No new geometry path, no server change.
//
// QUEUE. Multi-pass work needs a pen swap between passes, so the queue holds
// instead of auto-advancing:
//   idle --press--> plotting(0) --job goes idle--> waiting(0)  [N > 1]
//   waiting(k) --press--> plotting(k+1) --…--> waiting(k+1) … --> idle  [last]
// A start error, or Stop, drops straight back to idle with the passes cleared:
// nothing auto-advances past a failure, and no queue survives a stop.
// Completion is detected exactly the way the Animation stepper already does it
// (applyCapabilities, SSE-driven): saw-busy-then-idle. `wasBusy` is also set
// from the start call's own reply, which closes the race where a job finishes
// between the POST and the first status event.
const plotQueue = {
  passes: [],       // [{penName, body, mark?}] — body is the /api/plot/start payload
  i: 0,             // pass currently plotting (or the one just finished, while waiting)
  state: "idle",    // "idle" | "plotting" | "waiting"
  wasBusy: false,   // this pass's job was seen running
  desc: "",         // "tray \"x\" · sheet 2/4 · 3 passes"
};

const queueActive = () => plotQueue.state !== "idle";

// The tray sheet the canvas is showing, or null. S.stagedPlan is written in
// the same breath as the "tray" docPreview (previewStaged), so this is a
// lookup, not a second opinion about what is on screen.
function previewedTraySheet() {
  const groups = S.state?.project?.staging || [];
  const group = groups.find((g) => g.id === S.stagedPlan?.group_id);
  if (!group) return null;
  const sheet = group.sheets?.find((s) => s.id === S.stagedPlan?.sheet_id) || group.sheets?.[0];
  return sheet ? { group, sheet } : null;
}

// How many passes the current view will plot — pass-count only, from state
// already in hand, for the pre-flight line. The queue itself re-derives its
// passes at press time (viewPlotQueue) rather than trusting this.
function viewPassCount() {
  const dp = S.docPreview;
  if (!dp) return 0;
  if (dp.kind === "tray") return previewedTraySheet()?.sheet.passes?.length || 0;
  if (dp.kind === "sheet") return anim.passes.length;
  return 0;
}

// "tray \"x\" · sheet 2/4 · 3 passes" — built from the same docPreview fields
// renderViewLabel prints, so the stated target and the label agree by
// construction.
function viewTargetDesc() {
  const dp = S.docPreview;
  if (!dp) return null;
  const n = viewPassCount();
  const where = dp.kind === "tray"
    ? `tray "${dp.trayName || "?"}" · sheet ${dp.sheetIndex}/${dp.sheetCount}`
    : dp.kind === "sheet"
      ? `live · sheet ${dp.sheetIndex}/${dp.sheetCount}`
      : dp.label || "preview";
  return `${where} · ${n} pass${n === 1 ? "" : "es"}`;
}

// Build the pass list for whatever the canvas is showing. Returns null ONLY
// for the plain live view (which is not a queue — it stays a single job); any
// other view returns a (possibly empty) pass list, and an empty one is refused
// out loud rather than quietly falling back to plotting the live project.
// Falling back would be the one failure this whole change exists to prevent:
// the canvas showing one thing while the machine draws another.
async function viewPlotQueue() {
  const dp = S.docPreview;
  if (!dp) return null;
  if (dp.kind === "tray") {
    const found = previewedTraySheet();
    if (!found) return { passes: [], desc: viewTargetDesc() };
    const { group, sheet } = found;
    const passes = (sheet.passes || []).map((p) => ({
      penName: p.name || "no pen",
      body: { staged: { group_id: group.id, sheet_id: sheet.id, pen_id: p.pen_id || "" } },
      // same session mark the per-pass tray buttons set (P6)
      mark: () => plottedThisSession.add(plottedKey(group.id, sheet.id, p.pen_id || "")),
    }));
    return { passes, desc: viewTargetDesc() };
  }
  if (dp.kind === "sheet") {
    // Re-fetch the page's passes rather than trust the cached list: the panel
    // may have moved page or layout since the stepper last looked.
    await refreshSheetInfo();
    const passes = anim.passes.map((p) => ({
      penName: p.name || "no pen",
      body: { sheet: currentSheetSpec({ pen_id: p.pen_id || "" }) },
    }));
    return { passes, desc: viewTargetDesc() };
  }
  return { passes: [], desc: viewTargetDesc() };
}

// The ▶ Plot press. Three jobs in one handler, and that is the point: one
// button, one meaning ("plot what I'm looking at"), whatever is on screen.
async function plotPressed() {
  if (plotQueue.state === "plotting") return;          // button is disabled anyway
  if (plotQueue.state === "waiting") {                  // the button IS the continue
    await startQueuePass(plotQueue.i + 1);
    return;
  }
  let q = null;
  try {
    q = await viewPlotQueue();
  } catch (e) { actions.oops(e); return; }
  if (!q) {
    // Plain live view — unchanged: one job for the picked target, multi-pen or
    // not. (target="all" has always plotted every pen in a single pass; that
    // is deliberately NOT turned into a queue here.)
    try {
      await api.post("/api/plot/start", { target: S.plotTarget });
      actions.log(`▶ plot started (${targetLabel()})`);
    } catch (e) { actions.oops(e); }
    return;
  }
  if (!q.passes.length) {
    actions.oops(new Error(`${q.desc} — no pen passes to plot`));
    return;
  }
  plotQueue.passes = q.passes;
  plotQueue.desc = q.desc;
  await startQueuePass(0);
}

async function startQueuePass(i) {
  const p = plotQueue.passes[i];
  if (!p) { finishPlotQueue(); return; }
  plotQueue.i = i;
  plotQueue.state = "plotting";
  plotQueue.wasBusy = false;
  renderPlotViewControls();
  try {
    const status = await api.post("/api/plot/start", p.body);
    // the reply already says the job is running — don't depend on catching a
    // status event for a job that may be over before one arrives
    if (status && status.job_state && status.job_state !== "idle") plotQueue.wasBusy = true;
    if (p.mark) { p.mark(); renderStaging(); }
    actions.log(`▶ ${plotQueue.desc} — pass ${i + 1}/${plotQueue.passes.length} (${p.penName})`);
  } catch (e) {
    // an error stops the queue where it stands, with the error visible; the
    // per-pass tray buttons remain the way to resume out of order
    cancelPlotQueue();
    actions.oops(e);
  }
  renderPlotViewControls();
}

function finishPlotQueue() {
  const n = plotQueue.passes.length;
  const desc = plotQueue.desc;
  plotQueue.passes = [];
  plotQueue.i = 0;
  plotQueue.state = "idle";
  plotQueue.wasBusy = false;
  plotQueue.desc = "";
  if (n) actions.log(`✓ ${desc} — all ${n} pass${n === 1 ? "" : "es"} plotted`);
  renderPlotViewControls();
}

// Drop the queue without claiming it finished. Called by Stop (and by the SSE
// "stopped" job event, so a stop from anywhere clears it).
export function cancelPlotQueue() {
  if (!queueActive()) return;
  actions.log(`■ pass queue cancelled at pass ${plotQueue.i + 1}/${plotQueue.passes.length}`);
  plotQueue.passes = [];
  plotQueue.i = 0;
  plotQueue.state = "idle";
  plotQueue.wasBusy = false;
  plotQueue.desc = "";
  renderPlotViewControls();
}

// ONE renderer for everything that depends on "what will Plot do right now":
// the target picker's enabled state, the stated-target line under the button,
// the button's own label, and the always-visible queue line in the status
// strip. Exported so main.js's renderViewLabel — the other half of the same
// fact — can call it the moment the view changes.
export function renderPlotViewControls() {
  const sel = $("plot-target");
  if (!sel) return;                       // plot tab not built yet
  const dp = S.docPreview;
  const onSheetView = dp?.kind === "sheet" || dp?.kind === "tray";
  const n = plotQueue.passes.length;
  const cur = plotQueue.passes[plotQueue.i];
  const next = plotQueue.passes[plotQueue.i + 1];

  // 4: the all/layer/pen picker applies to the plain live view only.
  sel.disabled = onSheetView;
  sel.title = onSheetView ? "sheet passes carry their pens" : "";
  const penHint = $("target-pen-hint");
  if (penHint) {
    if (onSheetView) penHint.textContent = "sheet passes carry their pens — the target picker doesn't apply here";
    else renderTargetHint();
  }

  // the queue line: plotting / holding for a pen swap / nothing
  const line = $("plot-queue-status");
  let queueText = "";
  let holding = false;
  if (plotQueue.state === "plotting" && cur) {
    queueText = `pass ${plotQueue.i + 1}/${n} — ${cur.penName} — plotting…`;
  } else if (plotQueue.state === "waiting" && next) {
    queueText = `pass ${plotQueue.i + 1}/${n} done — swap to ${next.penName}, then ▶ continue`;
    holding = true;
  }
  if (line) {
    line.textContent = queueText;
    line.classList.toggle("holding", holding);
  }

  // 5: state what will plot, whenever that is not the plain live project
  const stated = $("plot-view-target");
  if (stated) {
    stated.textContent = queueText
      ? `${plotQueue.desc} — ${queueText}`
      : onSheetView ? `▶ Plot will plot: ${viewTargetDesc()}` : "";
    stated.classList.toggle("warn", holding);
  }

  const btn = $("btn-plot");
  if (btn) {
    btn.textContent = holding ? `▶ continue — swap to ${next.penName}` : "Plot";
    btn.title = holding
      ? `pass ${plotQueue.i + 2} of ${n}: load ${next.penName}, then press to continue`
      : onSheetView ? `plots what the canvas shows: ${viewTargetDesc()}` : "";
  }

  // Stop is the queue's abandon as well as the job's. A HELD queue sits on an
  // idle machine — that is the point, it is waiting for a pen swap — and the
  // plain "disabled while idle" rule would leave the only exit from a hold
  // being "plot the rest of it". The stop call is a no-op server-side with no
  // job running, so this buys the escape hatch with no second control and no
  // motion. Owned here, not in applyCapabilities, so it is decided AFTER the
  // queue has advanced (whether the queue is still active is the question).
  const stop = $("btn-stop");
  if (stop) {
    const jobIdle = (S.state?.machine?.job_state || "idle") === "idle";
    stop.disabled = jobIdle && !queueActive();
  }
}

// Grid-shaped tray group: a multi-sheet capture born from one Animation-
// panel setup (kind "sheet") or a batch interpolated from two such captures
// (kind "batch" with format.source_kind "sheet") — as opposed to a single
// loose plot/frame capture. Shared by relayoutRow's cols/rows availability
// check and renderStaging's P6-amendment visual grouping.
function isGridGroup(g) {
  return g.kind === "sheet" || (g.kind === "batch" && g.format?.source_kind === "sheet");
}

function gridDims() { return [anim.cols, anim.rows]; }
function gridCells() { return anim.cols * anim.rows; }
function sheetPages() {
  return Math.max(1, Math.ceil(anim.n / gridCells()));
}
function currentSheetSpec(extra = {}) {
  return { cols: anim.cols, rows: anim.rows, frames: anim.n,
           t_from: anim.tFrom, t_to: anim.tTo, margin_mm: anim.margin,
           crop: anim.crop, marks: anim.marks,
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
    // 7a: kind "sheet" + the numbers the always-visible view-label needs
    // ("live · sheet n/N") — see main.js's renderViewLabel.
    actions.showDocPreview("sheet", sheetPreviewLabel(),
      `sheet=${encodeURIComponent(JSON.stringify(S.sheetPlan))}`,
      { sheetIndex: anim.sheet + 1, sheetCount: anim.nPages });
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
//
// S7 (docs/plans/timeline-v2.md Q5, narrow ruling — "refuse chains only",
// video keeps blending): a capture's SNAPSHOT never rides the wire ("heavy
// source state never rides the wire" — every /api/staging payload excludes
// it), so this can't scan layers itself the way the server's
// _captures_compatible does. Session._store_capture_group stamps
// format.has_chain / format.chain_layer at capture time instead — the one
// place every stored group (capture, batch, relayout, rebake) passes
// through, so this reads the same bit the server will re-check.
function interpolateBlocker(ga, gb) {
  if (!ga || !gb) return "pick two captures";
  if (ga.id === gb.id) return "pick two different captures";
  if (ga.kind === "batch" || gb.kind === "batch") return "batch captures carry no source snapshot";
  if (ga.kind !== gb.kind) return `capture kinds differ (${ga.kind} vs ${gb.kind})`;
  if (ga.format?.has_chain || gb.format?.has_chain) {
    const name = ga.format?.has_chain ? ga.format?.chain_layer : gb.format?.chain_layer;
    return `"${name}" is a keyframe chain — chains don't tray-to-tray (video still does)`;
  }
  if (ga.kind === "sheet") {
    for (const k of ["cols", "rows", "frames", "t_from", "t_to"]) {
      if ((ga.format || {})[k] !== (gb.format || {})[k]) {
        return `sheet layouts differ: ${k} (${ga.format?.[k]} vs ${gb.format?.[k]})`;
      }
    }
  }
  return null;
}

// P8: the blocker's reason was only ever a button title, invisible on the
// way past. `updateInterpButton` now also writes it into the hint line
// under the row (added markup: #stage-interp-hint) so the ⇄ button explains
// itself before the click, not just on hover.
function updateInterpButton() {
  const btn = $("stage-interp");
  if (!btn) return;
  const groups = S.state?.project?.staging || [];
  const ga = groups.find((g) => g.id === $("stage-a")?.value);
  const gb = groups.find((g) => g.id === $("stage-b")?.value);
  const why = interpolateBlocker(ga, gb);
  btn.disabled = !!why;
  btn.title = why || "n sheets stepping A→B between the two captures";
  const hint = $("stage-interp-hint");
  if (hint) {
    hint.hidden = !why;
    hint.textContent = why || "";
  }
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
      body.crop = anim.crop;
      body.marks = anim.marks;
      body.name = `${anim.n}f · ${anim.cols}×${anim.rows} · ${anim.crop}`;
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
  const group = (S.state?.project?.staging || []).find((g) => g.id === groupId);
  const sheets = group?.sheets || [];
  if (!sheetId) sheetId = sheets[0]?.id;
  const idx = sheets.findIndex((s) => s.id === sheetId);
  S.sheetPlan = null;
  S.stagedPlan = { group_id: groupId, sheet_id: sheetId };
  stage.selectedGroup = groupId;
  stage.selectedSheet = sheetId;
  renderStaging();
  // swap the centre canvas to the staged sheet's actual geometry (the plan
  // overlay only draws travel); estimate/travel still ride S.stagedPlan below.
  // 7a: kind "tray" + the numbers the view-label needs (name + sheet n/N).
  await actions.showDocPreview("tray", stagedPreviewLabel(groupId, sheetId),
    `staged=${encodeURIComponent(JSON.stringify(S.stagedPlan))}`,
    { trayName: group?.name, sheetIndex: (idx >= 0 ? idx : 0) + 1, sheetCount: sheets.length || 1 });
  await actions.refreshPlan();
}

// "Plot targets the currently selected tray" (docs/plans/timeline-v2.md §2c
// "Sheet grid"): make the selection a group-level thing, not just a side
// effect of previewing one sheet — clicking a group's header (not one of its
// buttons) selects it and previews its currently-selected (or first) sheet.
// The per-sheet/pass buttons below stay the precise routing (Do not add a
// new resolve path); this only keeps "what's selected" honest so the label
// (7a) and the re-layout row (relayoutRow, already selection-gated) agree
// with what's on screen.
function selectGroup(groupId) {
  const group = (S.state?.project?.staging || []).find((g) => g.id === groupId);
  const keepSheet = stage.selectedGroup === groupId ? stage.selectedSheet : null;
  const sheetId = group?.sheets?.some((s) => s.id === keepSheet) ? keepSheet : group?.sheets?.[0]?.id;
  previewStaged(groupId, sheetId);
}

async function plotStaged(groupId, sheetId, penId) {
  try {
    await api.post("/api/plot/start", { staged: { group_id: groupId, sheet_id: sheetId, pen_id: penId } });
    plottedThisSession.add(plottedKey(groupId, sheetId, penId));
    // keep selection honest: plotting a pass is acting on that sheet, so it
    // becomes the selected one (7a's label follows).
    if (stage.selectedGroup !== groupId || stage.selectedSheet !== sheetId) {
      stage.selectedGroup = groupId;
      stage.selectedSheet = sheetId;
    }
    renderStaging();  // P6: dim/check this pass immediately, no reload needed
    actions.log(`▶ plotting staged sheet pass (${penId || "no pen"})`);
  } catch (e) { actions.oops(e); }
}

// 9a — re-bake a frozen tray group from CURRENT project state (client mirror
// of Session.rebake_blocked: same pattern as interpolateBlocker/P8 — compute
// the reason before the click, server re-validates). Only "sheet"/"frame"/
// "plot" captures are re-derivable this way; a "batch" (A⇄B interpolated)
// group is built from two OTHER captures' frozen snapshots, not live state.
function rebakeBlocked(g) {
  if (g.kind !== "sheet" && g.kind !== "frame" && g.kind !== "plot") {
    return `"${g.kind}" captures are derived from other captures, not the live project — re-bake those instead`;
  }
  return null;
}

async function rebakeStaged(groupId) {
  try {
    const r = await api.post(`/api/staging/groups/${encodeURIComponent(groupId)}/rebake`, {});
    await actions.refreshProject();
    actions.log(`re-baked "${r.group.name}" from the live project`);
    // sheet ids were replaced — re-preview if this group was on screen,
    // otherwise just repaint the list.
    if (stage.selectedGroup === groupId) {
      await previewStaged(groupId, r.group.sheets[0]?.id);
    } else {
      renderStaging();
    }
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
  if (!isGridGroup(g) || stage.selectedGroup !== g.id) return "";
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
  // P9 delivered here: groupLabel() surfaces the capture's actual shape
  // (frames · cols×rows · crop, or the source kind for a batch) instead of
  // the raw g.kind + count — it was already built (for the A/B pickers) and
  // just unused in this list. P6 amendment: a group born from one animation/
  // grid setup (isGridGroup) gets a distinct "animation set" tag + accent so
  // it reads apart from a standalone loose capture at a glance.
  list.innerHTML = groups.map((g) => {
    const gridGroup = isGridGroup(g);
    const selected = stage.selectedGroup === g.id;
    const rebakeReason = rebakeBlocked(g);
    return `
    <div class="stage-group${gridGroup ? " stage-group-anim" : ""}${selected ? " selected" : ""}">
      <div class="stage-head" data-stage-select="${esc(g.id)}" title="select this tray — plot targets the selected tray">
        <strong>${esc(groupLabel(g))}</strong>
        ${gridGroup ? `<span class="tag" title="captured from one animation/grid setup — these sheets belong together">animation set</span>` : ""}
        <button data-stage-rebake="${esc(g.id)}" ${rebakeReason ? "disabled" : ""}
          title="${esc(rebakeReason || "re-run this capture against the current project, replacing its sheets in place (one undo restores the old bake)")}">↻ Re-bake</button>
        <button data-stage-rename="${esc(g.id)}">Rename</button>
        <button data-stage-up="${esc(g.id)}">↑</button>
        <button data-stage-down="${esc(g.id)}">↓</button>
        <button data-stage-copy="${esc(g.id)}">Duplicate</button>
        <button data-stage-export="${esc(g.id)}">Export</button>
        <button class="danger" data-stage-delete="${esc(g.id)}">Delete</button>
      </div>
      ${(g.warnings || []).length ? `<div class="hint warn">${esc(g.warnings.join("; "))}</div>` : ""}
      ${relayoutRow(g)}
      ${(g.sheets || []).map((s) => {
        const passes = s.passes || [];
        // P6: dim/check sheets (and their individual passes) already plotted
        // this session — client-side only, never persisted (Ian's ruling).
        const allDone = passes.length > 0 &&
          passes.every((p) => plottedThisSession.has(plottedKey(g.id, s.id, p.pen_id)));
        return `
        <div class="stage-sheet ${stage.selectedGroup === g.id && stage.selectedSheet === s.id ? "on" : ""}${allDone ? " all-done" : ""}">
          <button data-stage-preview="${esc(g.id)}:${esc(s.id)}">Preview ${esc(s.name)}</button>
          <button data-stage-insert="${esc(g.id)}:${esc(s.id)}"
            title="bake this sheet into editable project layers (one per pen pass), hiding the current layers — the way to hand-edit a rendered grid">Insert as layers</button>
          ${passes.map((p) => {
            const done = plottedThisSession.has(plottedKey(g.id, s.id, p.pen_id));
            return `<button class="${done ? "plotted" : ""}" data-stage-plot="${esc(g.id)}:${esc(s.id)}:${esc(p.pen_id)}"
              title="${done ? "already plotted this session" : ""}">${done ? "✓ " : ""}${esc(p.name)} · ${p.paths} paths</button>`;
          }).join("")}
        </div>
      `;
      }).join("")}
    </div>
  `;
  }).join("");
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
  // group-header click selects the tray (item 4) — ignore clicks on any
  // button inside the header, which have their own handlers below.
  list.querySelectorAll("[data-stage-select]").forEach((head) => head.onclick = (e) => {
    if (e.target.closest("button")) return;
    selectGroup(head.dataset.stageSelect);
  });
  list.querySelectorAll("[data-stage-rebake]").forEach((b) => b.onclick = () => rebakeStaged(b.dataset.stageRebake));
  list.querySelectorAll("[data-stage-delete]").forEach((b) => b.onclick = () => deleteStaged(b.dataset.stageDelete));
  list.querySelectorAll("[data-stage-copy]").forEach((b) => b.onclick = () => duplicateStaged(b.dataset.stageCopy));
  list.querySelectorAll("[data-stage-rename]").forEach((b) => b.onclick = () => renameStaged(b.dataset.stageRename));
  list.querySelectorAll("[data-stage-up]").forEach((b) => b.onclick = () => moveStaged(b.dataset.stageUp, -1));
  list.querySelectorAll("[data-stage-down]").forEach((b) => b.onclick = () => moveStaged(b.dataset.stageDown, 1));
  list.querySelectorAll("[data-stage-export]").forEach((b) => b.onclick = () => {
    window.location.href = `/api/staging/export.zip?group_id=${encodeURIComponent(b.dataset.stageExport)}`;
  });
}

// P2 (docs/plans/timeline-v2.md): a follow_master tween whose window is
// narrower than one frame step ((tTo-tFrom)/(n-1)) can land BETWEEN two
// sampled frames and never get drawn on any output — export, sheets and the
// render popup all sample the same grid (F6). Reads windows straight off the
// project's layers (no server round trip: this is the same data the layer
// dock already has in S.state). M is the smallest frame count that would put
// a grid step on or inside the narrowest offending window.
function narrowTweenWarning() {
  if (anim.n <= 1) return null;
  const span = anim.tTo - anim.tFrom;
  const step = span / (anim.n - 1);
  if (!(step > 0)) return null;
  const layers = S.state?.project?.layers || [];
  const narrow = [];
  for (const l of layers) {
    if (l.source.type !== "tween") continue;
    const p = l.source.params || {};
    if (!p.follow_master) continue;
    const wf = p.window_from ?? 0, wt = p.window_to ?? 1;
    if (wt - wf < step) narrow.push(wt - wf);
  }
  if (!narrow.length) return null;
  const minWindow = Math.min(...narrow);
  const m = minWindow > 0 ? Math.ceil(span / minWindow) + 1 : null;
  const n = narrow.length;
  return m
    ? `${n} tween${n === 1 ? "" : "s"} narrower than one frame — raise frames to ≥ ${m}`
    : `${n} tween${n === 1 ? "" : "s"} narrower than one frame — window has zero width, ` +
      `unreachable at any frame count`;
}

function renderNarrowTweenHint() {
  const el = $("anim-narrow-tween-hint");
  if (!el) return;
  const msg = narrowTweenWarning();
  el.hidden = !msg;
  el.textContent = msg || "";
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

// P3: how much the layout costs, not just how many sheets it is. One
// /api/plan call per page (the same call the plan overlay already makes for
// the current page, `api.py`'s GET /plan?sheet=), summed for the total. Kept
// under a layout-signature cache so re-rendering the panel (every unrelated
// keystroke touches renderLayoutSummary indirectly) doesn't refire N HTTP
// calls per render — only a genuine layout change or invalidateLayoutCost()
// (wired into main.js's refreshProject, so any project mutation counts)
// throws it away. "Cheap, conservative" on purpose: a param edit that
// doesn't touch the layout still invalidates on the next refreshProject,
// which is more often than strictly necessary but never stale for long.
let layoutCostCache = null; // { key, perSheetS: number[] } | { key, pending: true }
let lastLayoutInfo = null; // re-render target once an async cost fetch lands

function layoutCostKey() {
  return JSON.stringify([anim.n, anim.tFrom, anim.tTo, anim.cols, anim.rows,
                          anim.margin, anim.crop, anim.marks]);
}

export function invalidateLayoutCost() {
  layoutCostCache = null;
}

async function ensureLayoutCost() {
  const key = layoutCostKey();
  if (layoutCostCache?.key === key) return; // cached (settled or already in flight)
  layoutCostCache = { key, pending: true };
  const pages = sheetPages();
  const perSheetS = [];
  try {
    for (let page = 0; page < pages; page++) {
      const spec = currentSheetSpec({ page });
      const r = await api.get(`/api/plan?sheet=${encodeURIComponent(JSON.stringify(spec))}`);
      perSheetS.push(r.job.total_duration);
    }
  } catch (e) {
    // Cache the FAILURE under this key too (nothing to plot, a transient
    // error, …) — otherwise every render that can't show a number retries
    // immediately, which is the exact per-render refire this cache exists to
    // avoid. A genuine layout change (new key) or invalidateLayoutCost()
    // (project mutation) is what earns a retry.
    layoutCostCache = { key, perSheetS: null };
    return;
  }
  if (layoutCostKey() !== key) return; // layout moved again while this was in flight; drop it
  layoutCostCache = { key, perSheetS };
  renderLayoutSummary(lastLayoutInfo); // the number just landed — show it
}

// One line that says what the layout MEANS physically, before anything plots.
function renderLayoutSummary(info) {
  const el = $("anim-layout-summary");
  if (!el) return;
  lastLayoutInfo = info;
  if (gridCells() <= 1) {
    el.textContent = `${anim.n} frames → ${anim.n} single-frame plots (stepper below)`;
    return;
  }
  const pages = info ? info.sheets : sheetPages();
  const passes = info && info.passes ? info.passes.map((p) => p.name).join(", ") : "…";
  let text =
    `${anim.n} frames → ${pages} sheet${pages === 1 ? "" : "s"} of ${anim.cols}×${anim.rows}` +
    ` · page ${Math.min(anim.sheet, pages - 1) + 1}: ${passes}` +
    (anim.marks ? " · ✚ crosshairs on first pass" : "");
  const key = layoutCostKey();
  if (layoutCostCache?.key === key && layoutCostCache.perSheetS) {
    const perSheetS = layoutCostCache.perSheetS;
    const cur = perSheetS[Math.min(anim.sheet, perSheetS.length - 1)];
    const total = perSheetS.reduce((a, b) => a + b, 0);
    text += ` · this sheet ~${fmtTime(cur)} · ~${fmtTime(total)} total`;
  } else {
    text += " · est. …";
    ensureLayoutCost(); // fire-and-forget: renderLayoutSummary runs again when it lands
  }
  el.textContent = text;
}

function fmtTime(s) {
  if (!isFinite(s)) return "—";
  const m = Math.floor(s / 60);
  return m >= 1 ? `${m}m ${Math.round(s % 60)}s` : `${s.toFixed(1)}s`;
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

// S5 (F6, docs/plans/timeline-v2.md): a thin accessor onto the exact grid
// animT/pullAnimControls already compute, so the timeline bar can snap its
// scrub to the same positions without a second copy of this math. No DOM
// pull here on purpose — the bar can be visible on tabs where the Animation
// panel's own inputs don't exist in the DOM (Compose/Pens/Settings); `anim`
// is module-level and survives tab switches, so it already holds the last
// values pulled from whichever panel last touched it.
export function frameGrid() {
  return { n: anim.n, tFrom: anim.tFrom, tTo: anim.tTo };
}

function pullAnimControls() {
  if (!$("anim-frames")) return;
  anim.n = Math.max(2, Math.min(240, Math.round(Number($("anim-frames").value) || 2)));
  anim.tFrom = Math.max(0, Math.min(1, Number($("anim-t-from").value)));
  anim.tTo = Math.max(0, Math.min(1, Number($("anim-t-to").value)));
  anim.cols = Math.max(1, Math.min(12, Math.round(Number($("anim-cols").value) || 1)));
  anim.rows = Math.max(1, Math.min(12, Math.round(Number($("anim-rows").value) || 1)));
  anim.margin = Math.max(0, Math.min(30, Number($("anim-sheet-margin").value) || 0));
  anim.crop = $("anim-crop")?.value === "full" ? "full" : "timeline";
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

// S4 (docs/plans/timeline-v2.md): the timeline bar's prev/next-frame
// steppers reuse this exact frame-grid stepping — pullAnimControls() for
// n/tFrom/tTo, previewScrub for the same no-PATCH partial refresh
// `Frame →` already uses — rather than a second copy of the math (F6).
// Clamped at the ends, not wrapped: the bar has its own jump-to-start/end.
export function stepFrame(delta) {
  pullAnimControls();
  stopPreview();
  anim.i = Math.max(0, Math.min(anim.n - 1, anim.i + delta));
  previewScrub.request(anim.i);
  return { i: anim.i, n: anim.n, t: animT(anim.i) };
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
    const i = anim.i;
    S.masterT = t;
    try {
      // scrub:true — the frame/sheet stepper is a timeline interaction, same
      // as the bottom bar's own scrub (§2c "Trays"): it may switch out of a
      // live sheet preview; 8a's stickiness is for param edits, not stepping.
      await actions.refreshResolved(t, { plan: false, stats: false, scrub: true });
      recordFetchedFrame(i); // S5: this frame's geometry has now been fetched this session
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

// Playback/export frame order: plain 0..n-1, or — with the palindrome toggle
// — that plus the reversed middle (A,B,C,D → A,B,C,D,C,B), matching the
// server's export.gif/.mp4 ordering exactly (see _frame_times in api.py) so
// what plays in the popup is what gets exported.
function playOrder() {
  const n = anim.previewFrames.length;
  const forward = Array.from({ length: n }, (_, i) => i);
  if (!anim.palindrome || n <= 2) return forward;
  const back = [];
  for (let i = n - 2; i >= 1; i--) back.push(i);
  return forward.concat(back);
}

// Keep the popup's GIF/MP4 export links pointed at the exact settings the
// popup is currently showing (frame range, fps, resolution, palindrome) —
// same source of truth as updateExportLink() for the SVG zip.
function updateRasterExportLinks() {
  const params = `frames=${anim.n}&t_from=${anim.tFrom}&t_to=${anim.tTo}` +
    `&fps=${anim.popupFps}&scale=${anim.scale}&palindrome=${anim.palindrome}`;
  const gif = $("anim-preview-export-gif");
  if (gif) gif.href = `/api/animation/export.gif?${params}`;
  const mp4 = $("anim-preview-export-mp4");
  if (mp4) mp4.href = `/api/animation/export.mp4?${params}`;
}

// The MP4 button disables itself with the server's own reason (ffmpeg is a
// machine-level install, not every axibridge host has one — see
// /api/state's ffmpeg_available) rather than failing silently on click.
function syncMp4ExportAvailability() {
  const btn = $("anim-preview-mp4-btn");
  const link = $("anim-preview-export-mp4");
  if (!btn || !link || !S.state) return;
  const available = S.state.ffmpeg_available !== false;
  const reason = "ffmpeg not found on this machine — install it (brew/apt), or use Export GIF instead";
  btn.disabled = !available;
  btn.title = link.title = available ? "" : reason;
  link.onclick = available ? null : (e) => e.preventDefault();
}

// scale() OUTER, translate() INNER (2026-08-11 fix — was the reverse): with
// `translate() scale()`, CSS composes translate in the element's own
// POST-scale coordinate system, so panX/panY are screen pixels regardless of
// zoom and the image visibly drifts slower than the cursor at high zoom —
// exactly Ian's "pan feels finicky" bench report. With `scale() translate()`,
// translate is expressed in the PRE-scale (local) coordinate system, so a
// given panX now moves the rendered pixel by `zoom * panX` on screen — which
// is why the drag handler below divides the mouse delta by anim.zoom before
// accumulating it into panX/panY: that conversion is what makes 1 mouse
// pixel move the image by exactly 1 screen pixel at any zoom level.
function applyZoomTransform() {
  const img = $("anim-preview-img");
  if (!img) return;
  img.style.transform = `scale(${anim.zoom}) translate(${anim.panX}px, ${anim.panY}px)`;
  img.style.cursor = anim.zoom > 1 ? "grab" : "";
}

function resetRasterZoom() {
  anim.zoom = 1;
  anim.panX = 0;
  anim.panY = 0;
  applyZoomTransform();
}

// Small CSS-transform pan/zoom on the popup <img> — deliberately NOT the
// canvas.js zoom machinery (different coordinate space: this is a raster
// bitmap view, not the mm-space vector canvas). Wheel zooms (clamped 1-4x,
// same ceiling as the render-resolution control since a display zoom past
// the render's own supersample just shows blur, not detail); dragging pans
// only once zoomed in; double-click resets.
//
// Guarded (stageEl.dataset.zoomPanInit) because #anim-preview-stage is now
// static top-level markup (index.html, moved 2026-08-11) instead of being
// rebuilt inside #tab-plot's innerHTML every project load — without the
// guard, every initPlotTab() call would pile on another set of `wheel`/
// `mousedown`/`dblclick` listeners on the same persistent element (and
// another `mousemove`/`mouseup` pair on `window`), each firing once per
// prior project load. Same idiom as timeline.js's `bar.dataset.tlInit`.
function initRasterZoomPan() {
  const stageEl = $("anim-preview-stage");
  if (!stageEl || stageEl.dataset.zoomPanInit) return;
  stageEl.dataset.zoomPanInit = "1";
  let dragging = false;
  let dragStart = null;
  stageEl.addEventListener("wheel", (e) => {
    if (!anim.previewFrames.length) return;
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.2 : -0.2;
    anim.zoom = Math.max(1, Math.min(4, +(anim.zoom + delta).toFixed(2)));
    if (anim.zoom === 1) { anim.panX = 0; anim.panY = 0; }
    applyZoomTransform();
  }, { passive: false });
  stageEl.addEventListener("mousedown", (e) => {
    if (anim.zoom <= 1) return;
    dragging = true;
    // Screen-space anchor only — panX/panY are now in the PRE-scale
    // coordinate system (see applyZoomTransform's comment), so the delta
    // gets divided by anim.zoom below rather than folded in here.
    dragStart = { x: e.clientX, y: e.clientY, panX: anim.panX, panY: anim.panY };
    stageEl.style.cursor = "grabbing";
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    // The fix (2026-08-11, Ian's bench report — "pan doesn't compensate for
    // zoom, drags feel wrong at high zoom"): divide the on-screen mouse
    // delta by the current zoom before accumulating it into panX/panY, which
    // now live in the pre-scale coordinate system. Undivided, the same mouse
    // delta produced the same panX at any zoom, so the rendered image moved
    // `zoom` times as many screen pixels as the cursor — the drag ran away
    // from the pointer at 2x/4x. Dividing makes 1 screen px of drag move the
    // image by exactly 1 screen px, at 1x/2x/4x alike.
    anim.panX = dragStart.panX + (e.clientX - dragStart.x) / anim.zoom;
    anim.panY = dragStart.panY + (e.clientY - dragStart.y) / anim.zoom;
    applyZoomTransform();
  });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    stageEl.style.cursor = anim.zoom > 1 ? "grab" : "";
  });
  stageEl.addEventListener("dblclick", () => resetRasterZoom());
  applyZoomTransform();
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
    // States the ACTUAL on-screen resolution (2026-08-11 ruling), not just
    // the scale multiplier: `frame.w`/`frame.h` are the decoded pixel
    // dimensions of the PNG that came back for this exact frame (see
    // renderRasterPreview), so "1800×2400 @2×" is what the machine really
    // rendered, immune to any rounding between width_px and scale.
    const f = anim.previewFrames[anim.popupI];
    label.textContent = hasFrames
      ? `frame ${anim.popupI + 1}/${anim.previewFrames.length} · t=${f.t.toFixed(3)} · ${f.w}×${f.h} @${f.scale}×`
      : message;
  }
  updateRasterExportLinks();
  syncMp4ExportAvailability();
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

// Plain playback steps popupI directly; palindrome playback walks a position
// through playOrder() instead (ping-pong: A,B,C,D,C,B,…) — see playOrder()
// for why the same order has to match the server's export ordering.
function startRasterPlayback() {
  if (!anim.previewFrames.length) return;
  anim.popupPlaying = true;
  const order = playOrder();
  const fromOrder = order.indexOf(anim.popupI);
  anim.popupPos = fromOrder >= 0 ? fromOrder : 0;
  renderRasterControls();
  const tick = () => {
    if (!anim.popupPlaying) return;
    const ord = playOrder();
    let nextPos = anim.popupPos + 1;
    if (nextPos >= ord.length) {
      if (!anim.loop) {
        stopRasterPlayback();
        return;
      }
      nextPos = 0;
    }
    anim.popupPos = nextPos;
    showRasterFrame(ord[nextPos]);
    anim.popupTimer = setTimeout(tick, 1000 / anim.popupFps);
  };
  anim.popupTimer = setTimeout(tick, 1000 / anim.popupFps);
}

function closeRasterPreview() {
  // P10 (docs/plans/timeline-v2.md): the popup and the bar shouldn't disagree
  // about "which frame" once the popup stops owning the screen. anim.popupI
  // is already a real forward-grid frame index (0..previewFrames.length-1)
  // even during palindrome playback — playOrder() walks POSITIONS through
  // the reversed tail, but showRasterFrame always resolves those back to an
  // index into previewFrames itself, which only ever holds the forward n
  // frames — so no separate clamp is needed here, just read it before the
  // teardown below clears it.
  const lastT = anim.previewFrames[anim.popupI]?.t;
  anim.previewAbort?.abort();
  anim.previewAbort = null;
  anim.renderingPreview = false;
  stopRasterPlayback();
  clearRasterFrames();
  resetRasterZoom();
  const modal = $("anim-preview-modal");
  if (modal) modal.hidden = true;
  setRasterProgress(0, 0);
  renderAnimPreview();
  if (lastT != null) jumpTo(lastT); // leave the master timeline on the frame that was on screen
}

export async function renderRasterPreview() {
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
      const costNote = anim.scale > 1 ? ` @${anim.scale}×` : "";
      renderRasterControls(`rendering frame ${i + 1}/${anim.n}${costNote}`);
      const url = `/api/animation/preview.png?t=${encodeURIComponent(t)}&width_px=1200&scale=${anim.scale}`;
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      // Decode dimensions now so the popup label can state the ACTUAL
      // on-screen resolution ("1800×2400 @2×") rather than recomputing the
      // server's width_px/scale/bed-aspect math a second time in JS — this
      // is the exact PNG the machine rendered, read back, not a guess.
      const bitmap = await createImageBitmap(blob);
      const frame = { url: URL.createObjectURL(blob), t, w: bitmap.width, h: bitmap.height, scale: anim.scale };
      bitmap.close?.();
      newFrames.push(frame);
      recordFetchedFrame(i); // S5: the popup render loop is the third of the three known-t fetch points
      setRasterProgress(i + 1, anim.n);
      if (!anim.previewFrames.length && newFrames.length === 1) {
        // first-ever render (no old set to keep showing): alias the scratch
        // buffer as the live set so the remaining progress renders as the
        // badge overlay (renderRasterControls above), not a blank stage
        anim.previewFrames = newFrames;
        anim.popupI = 0;
      }
      // Last-rendered frame stays visible throughout the loop (never a blank
      // or spinner-only state): paint whatever just landed straight onto the
      // stage. On a RE-render this runs ahead of the eventual swap below —
      // anim.previewFrames/popupI still point at the OLD, still-valid set
      // (so an abort mid-render leaves it untouched), but the pixels on
      // screen already show the newest completed frame.
      const stageImg = $("anim-preview-img");
      if (stageImg) { stageImg.src = frame.url; stageImg.hidden = false; }
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
  const resetBtn = $("anim-reset");
  const startFrameRow = $("anim-start-frame-row");
  const startSheetRow = $("anim-start-sheet-row");
  const basePlotDisabled = $("btn-plot") ? $("btn-plot").disabled : true;

  if (gridCells() <= 1) {
    label.textContent = `frame ${anim.i + 1} of ${anim.n} (t=${animT(anim.i).toFixed(3)})`;
    if (btn) {
      btn.textContent = anim.plotting ? `Plotting frame ${anim.i + 1}…` : `Plot frame ${anim.i + 1}`;
      btn.disabled = anim.plotting || basePlotDisabled;
    }
    if (skip) { skip.textContent = "Skip →"; skip.disabled = anim.plotting || anim.i >= anim.n - 1; }
    // S6/P5: the "start from frame N" affordance and Reset's tooltip naming
    // the chosen start (never let Reset read as "back to zero" unlabelled).
    if (startFrameRow) startFrameRow.hidden = false;
    if (startSheetRow) startSheetRow.hidden = true;
    if ($("anim-start-frame-n")) $("anim-start-frame-n").textContent = String(anim.n);
    if ($("anim-start-frame")) $("anim-start-frame").max = String(anim.n);
    if (resetBtn) resetBtn.title = `back to your chosen start (frame ${(anim.startI || 0) + 1})`;
    return;
  }

  if (startFrameRow) startFrameRow.hidden = true;
  if (startSheetRow) startSheetRow.hidden = false;
  if ($("anim-start-sheet-n")) $("anim-start-sheet-n").textContent = String(anim.nPages);
  if ($("anim-start-sheet")) $("anim-start-sheet").max = String(anim.nPages);
  if (resetBtn) resetBtn.title = `back to your chosen start (sheet ${(anim.startSheet || 0) + 1})`;

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
  renderNarrowTweenHint(); // P2 — a tween's window can have changed elsewhere (Compose tab)
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
      // `jog` is the capability name; what it buys you now that the arrow pad
      // is gone is Go to origin, so the tag says what the user can actually do
      caps.jog ? "<b>manual moves</b>" : "no manual moves",
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

// Targets, in the order you actually reach for them: everything, then each
// PEN, then each layer. Pen targets are how a multi-pen sheet is really
// plotted — load a pen, plot everything it draws, swap, repeat — and doing
// that by layer means remembering which four of fifteen layers were blue.
// Only pens that some visible layer actually uses are offered; an empty pass
// is a swap for nothing.
function renderTargets() {
  const sel = $("plot-target");
  const prev = S.plotTarget;
  sel.innerHTML = '<option value="all">all layers</option>';

  const counts = new Map();
  for (const layer of S.state.project.layers) {
    if (!layer.visible || !layer.pen_id) continue;
    counts.set(layer.pen_id, (counts.get(layer.pen_id) || 0) + 1);
  }
  for (const pen of S.state.pens) {
    const n = counts.get(pen.id);
    if (!n) continue;
    const o = document.createElement("option");
    o.value = `pen:${pen.id}`;
    o.textContent = `pen: ${pen.name} (${n} layer${n > 1 ? "s" : ""})`;
    sel.appendChild(o);
  }

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

function penTarget(target = S.plotTarget) {
  return target.startsWith("pen:")
    ? S.state.pens.find((p) => p.id === target.slice(4)) || null
    : null;
}

function targetLabel() {
  if (S.plotTarget === "all") return "all layers";
  const pen = penTarget();
  if (pen) return `pen ${pen.name}`;
  const l = S.state.project.layers.find((x) => x.id === S.plotTarget);
  return l ? l.name : S.plotTarget;
}

function renderTargetHint() {
  const hint = $("target-pen-hint");
  if (S.plotTarget === "all") {
    hint.textContent = "Manual multi-pen: pick a pen, plot, swap the pen, pick the next.";
    return;
  }
  const penned = penTarget();
  if (penned) {
    const layers = S.state.project.layers.filter(
      (l) => l.visible && l.pen_id === penned.id).map((l) => l.name);
    hint.textContent =
      `Load pen: ${penned.name} (⌀${penned.barrel_diameter_mm}mm) — plots ${layers.length} ` +
      `layer${layers.length > 1 ? "s" : ""}: ${layers.join(", ")}`;
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

  $("panel-pen").style.display = caps.pen_control || caps.set_origin ? "" : "none";
  $("panel-raw").style.display = caps.raw_ebb ? "" : "none";
  // Go to origin is an absolute move, and `jog` is still the flag that says a
  // backend will move the carriage between jobs — the jog ENDPOINT outlived
  // its UI (2026-08-08), so the capability still means what it says.
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
  // base rule; renderPlotViewControls (below, after the queue has advanced)
  // has the final word, because a HELD queue keeps Stop live on an idle machine
  $("btn-stop").disabled = idle;
  $("port-select").disabled = $("ports-refresh").disabled = !caps.requires_serial_port;
  $("backend-notes").textContent = caps.notes || "";
  syncMp4ExportAvailability();  // ffmpeg is a machine-level install, not a job capability
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

  // pass queue: same saw-busy-then-idle rule, but it HOLDS between passes
  // instead of just unlocking a button — the machine is idle and the status
  // line asks for a pen swap until ▶ continue is pressed. Never auto-advances.
  if (plotQueue.state === "plotting") {
    if (!idle) {
      plotQueue.wasBusy = true;
    } else if (plotQueue.wasBusy) {
      plotQueue.wasBusy = false;
      if (plotQueue.i + 1 < plotQueue.passes.length) plotQueue.state = "waiting";
      else finishPlotQueue();
    }
  }
  renderPlotViewControls();
  renderAnimStepper();
}

function setPos(pos) {
  const el = $("pos-readout");
  if (el) el.textContent = `${pos[0].toFixed(1)}, ${pos[1].toFixed(1)} mm`;
  actions.setMachineReadout({ pos });     // the always-visible copy
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
