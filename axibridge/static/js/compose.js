// Compose tab: sources (generate / upload), the layer list (z-order,
// visibility, pen, occlusion), and the selected layer's detail editor
// (transform numerics, effect stack, generator params).

import { api } from "./api.js";
import { renderForm } from "./forms.js";
import { S, actions, rememberDetails } from "./main.js";
import { mul, translate, rotate, scale, matToObj, objToMat } from "./canvas.js";
import { applyViewDefaults } from "./viewmap.js";

const $ = (id) => document.getElementById(id);
let genParams = {};
// the bench latch: after "＋ Create layer" the SAME form live-edits the new
// layer (auto-apply on slider release, coalesced into one undo entry) until
// "＋ New layer" unlatches or another layer gets selected. null = unlatched.
let latch = null;
// generator-switch carry-over: these keys survive into the next generator's
// params when its schema declares them (same image, same placement intent)
const STICKY_FIELDS = ["image", "rotate", "width", "frame"];
const expandedSteps = new Set(); // "layerId:index" — effect steps open in the UI
const collapsedTweens = new Set(JSON.parse(localStorage.getItem("axb-collapsed-tweens") || "[]"));
let selAnchor = null;            // last plain/cmd-clicked layer id, for shift-range
let busyBtn = null;              // Generate/Regenerate button awaiting the server
let depthProStatus = null;
let depthProSource = "";
const depthProFrames = {};

// SSE "gen" events land here (main.js dispatches) while a generate request
// is in flight; the request itself completing is what ends the busy state.
export function setGenProgress(frac, msg) {
  const bar = $("gen-progress-bar");
  if (bar) bar.style.width = `${Math.round(frac * 100)}%`;
  const m = $("gen-progress-msg");
  if (m) { m.hidden = !msg; m.textContent = msg || ""; }
  if (busyBtn) busyBtn.textContent = `${Math.round(frac * 100)}%${msg ? " · " + msg : ""}`;
}

function genBusy(on, btn = $("btn-generate")) {
  busyBtn = on ? btn : null;
  if (btn) {
    btn.disabled = on;
    if (!on) btn.textContent = btn.dataset.label || btn.textContent;
    else { btn.dataset.label = btn.textContent; btn.textContent = "…"; }
  }
  const p = $("gen-progress");
  if (p) p.hidden = !on;
  if (on) setGenProgress(0, "");
  else { const m = $("gen-progress-msg"); if (m) m.hidden = true; }
}

// Same bar, for callers with no "Generate"-style button to repurpose (the
// forms.js inline sequence-asset upload). Same guard as the live-preview
// code below: a real generate in flight keeps ownership of the bar.
export function setSeqProgress(on) {
  const p = $("gen-progress");
  if (p && !busyBtn) p.hidden = !on;
  if (on) setGenProgress(0, "");
  else { const m = $("gen-progress-msg"); if (m) m.hidden = true; }
}

// ---- live generator preview --------------------------------------------------
//
// Debounced + strictly serialized: at most one /generators/preview request in
// flight, the latest params always win, stale responses are dropped by
// sequence number — sliders can move as fast as they like without piling
// work on the server or racing the overlay. The endpoint never touches the
// project, so previewing can't pollute undo history or corrupt state.

let livePreview = localStorage.getItem("axb-live-preview") === "1";

const preview = {
  timer: null, inflight: false, next: null, seq: 0,
  key: null,  // "new" (add panel) or a layer id — stale ghosts clear on switch
  schedule(req) {                       // req = {key, url, body, transform|null}
    if (!livePreview) return;
    this.key = req.key || null;
    this.next = req;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this._run(), 250);
  },
  async _run() {
    if (this.inflight || !this.next) return;
    const req = this.next;
    this.next = null;
    this.inflight = true;
    const seq = ++this.seq;
    const p = $("gen-progress");
    if (p && !busyBtn) p.hidden = false;  // ride the same bar, unless a real generate owns it
    try {
      const r = await api.post(req.url, req.body);
      if (seq === this.seq) {
        actions.canvas().setGenPreview({ lines: r.lines, transform: req.transform || null });
        note(r.decimated ? `preview decimated (${Math.round(r.points / 1000)}k pts — the real thing is exact)` : "");
      }
    } catch (e) {
      if (seq === this.seq) note(e.message); // quiet inline note, no toast spam mid-drag
    } finally {
      this.inflight = false;
      if (p && !busyBtn) p.hidden = true;
      if (this.next) this._run();           // params moved meanwhile: run once more
    }
  },
  clear() {
    clearTimeout(this.timer);
    this.next = null;
    this.key = null;
    this.seq++;                             // orphan any in-flight response
    actions.canvas().setGenPreview(null);
    note("");
  },
};

function note(msg) {
  const el = $("gen-live-note");
  if (el) el.textContent = msg;
}

// ---- master timeline scrub ---------------------------------------------------
//
// One /compose/resolved?t= request in flight at a time; the latest slider value
// always wins (coalesce, no timer) — same in-flight-guard shape as the live
// preview above. Pure UI state: never PATCHes, never touches undo/history.

const scrub = {
  inflight: false, pending: false,
  request(v) {
    S.masterT = v;  // shared: every refreshResolved() now stays on this frame
    this.pending = true;
    if (!this.inflight) this._run();
  },
  async _run() {
    if (!this.pending) return;
    this.pending = false;
    this.inflight = true;
    try {
      await actions.refreshResolved();
    } catch (e) {
      actions.oops(e);
    } finally {
      this.inflight = false;
      if (this.pending) this._run();  // moved meanwhile: run once more
    }
  },
};

// Selecting a keyframe (the A or B sublayer of a follow_master tween) jumps
// the master timeline to where that keyframe shows, so clicking "▸ B" to edit
// it also previews it in the animation. A → the window's start, B → its end
// (the linear/cosine default; a ping-pong tween reaches B mid-window, so we
// leave those be rather than guess — scrub manually). No-op for a layer that
// isn't a following tween's keyframe, or when the timeline panel is hidden.
function jumpTimelineToKeyframe(layerId) {
  const slider = $("master-t");
  if (!slider || $("timeline-panel")?.hidden) return;
  for (const l of S.state?.project?.layers || []) {
    if (l.source.type !== "tween") continue;
    const p = l.source.params || {};
    if (!p.follow_master || (p.time_curve && p.time_curve !== "linear" && p.time_curve !== "cosine")) continue;
    let target = null;
    if (p.a === layerId) target = p.window_from ?? 0;
    else if (p.b === layerId) target = p.window_to ?? 1;
    if (target === null) continue;
    slider.value = target;
    const val = $("master-t-val");
    if (val) val.textContent = `t = ${Number(target).toFixed(3)}`;
    scrub.request(target);
    return;
  }
}

// Show the timeline panel when there's anything for it to drive: a tween
// layer (whether or not it follows yet) or a frame-clip source (sequence
// asset name ends "#"). Inside, a hint nudges the "follow timeline" opt-in
// when the panel is showing but nothing actually follows the scrubber yet.
export function renderTimeline() {
  const panel = $("timeline-panel");
  if (!panel) return;
  const layers = S.state?.project?.layers || [];
  const hasTween = layers.some((l) => l.source.type === "tween");
  const hasFrameClip = layers.some((l) => {
    const img = (l.source.params || {}).image;
    return typeof img === "string" && img.endsWith("#");
  });
  panel.hidden = !(hasTween || hasFrameClip);
  const hasFollow = layers.some(
    (l) => (l.source.type === "tween" && (l.source.params || {}).follow_master)
        || l.frame_follow);
  const hint = $("timeline-hint");
  if (hint) hint.hidden = panel.hidden || hasFollow;
}

const genPreviewReq = (key, module, params, transform = null) => ({
  key, url: "/api/generators/preview", body: { module, params }, transform,
});

export function initComposeTab() {
  $("tab-compose").innerHTML = `
    <div class="panel">
      <h2>Generate</h2>
      <div class="row">
        <select id="gen-select" style="flex:1"></select>
      </div>
      <div id="gen-form" class="form"></div>
      <div class="row" id="lineart-stack-row" hidden>
        <select id="lineart-stack-flavor">
          <option value="faithful">faithful</option>
          <option value="artistic">artistic</option>
        </select>
        <button id="btn-lineart-stack">★ Create stack</button>
      </div>
      <div id="gen-progress" class="progress" hidden><div id="gen-progress-bar"></div></div>
      <div id="gen-progress-msg" class="hint" hidden></div>
      <div class="row" style="margin-top:8px">
        <button id="btn-generate" class="primary">＋ Create layer</button>
        <!-- with the other create button, not with the list: making a layer is
             a Compose act, the list is only where you pick one -->
        <button id="btn-empty-layer"
          title="blank layer the pen/brush/draw tools draw onto (a shape layer both pen and brush can add to and subtract from when those tools are active) — an explicit fresh target instead of appending to the last drawn layer">＋ empty</button>
        <button id="gen-latch" class="latch-chip" hidden
          title="the sliders above edit this layer live — click to select it"></button>
        <label class="hint" style="cursor:pointer;margin-left:auto"
          title="ghost the result of generator/effect sliders while you drag, before committing">
          <input type="checkbox" id="gen-live"> live preview
        </label>
      </div>
      <div id="gen-live-note" class="hint"></div>
    </div>
    <div class="panel" data-collapse-default="1">
      <h2>Import &amp; assets</h2>
      <div class="row">
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
        <input type="file" id="asset-file" multiple
          accept="image/png,image/jpeg,video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-msvideo"
          style="flex:1">
        <button id="btn-asset">Add image asset</button>
      </div>
      <div class="row">
        <label>max frames</label><input type="number" id="asset-frames" min="1" max="240" placeholder="all" style="width:4.5em">
        <label>start</label><input type="number" id="asset-start" min="0" placeholder="0" style="width:4.5em">
        <label>every</label><input type="number" id="asset-every" min="1" placeholder="—" style="width:4.5em">
        <span class="hint">optional max / start / every — video or multiple files import as a frame sequence</span>
      </div>
      <div class="row">
        <button id="btn-clear-assets" title="Remove image assets no layer currently uses (referenced assets are kept)">Clear unused assets</button>
      </div>
      <div class="hint">tip: dropping an image or video on the canvas imports it too</div>
      <div id="asset-list"></div>
    </div>
    <div class="panel" id="timeline-panel" hidden>
      <h2>Timeline <span class="hint">(scrubs every tween set to "follow timeline")</span></h2>
      <div class="row">
        <input type="range" id="master-t" min="0" max="1" step="0.001" value="0" style="flex:1">
        <span class="hint" id="master-t-val" style="min-width:5em">t = 0.000</span>
      </div>
      <div class="hint">Live scrub only — not saved to the project.</div>
      <div class="hint" id="timeline-hint" hidden>nothing follows the timeline yet — check
        "clip follows timeline" on a clip layer, ⏱ Animate a layer, or check "Follow
        timeline" on an interpolation layer</div>
    </div>
    <div class="panel" id="layer-detail-panel" hidden>
      <h2>Layer: <span id="detail-name"></span></h2>
      <div id="layer-detail"></div>
    </div>`;

  const sel = $("gen-select");
  // image-driven generators (any param with format:"asset") group separately
  const usesImage = (m) => Object.values(m.schema.properties || {}).some(
    (p) => (p.format || ((p.anyOf || []).find((a) => a.format) || {}).format) === "asset");
  const optgroups = { false: group("Procedural"), true: group("📷 Image-driven") };
  function group(label) {
    const g = document.createElement("optgroup");
    g.label = label;
    sel.appendChild(g);
    return g;
  }
  for (const m of S.state.modules.sources) {
    const o = document.createElement("option");
    o.value = m.id; o.textContent = m.label; o.title = m.description;
    optgroups[usesImage(m)].appendChild(o);
  }
  sel.onchange = renderGenForm;
  const live = $("gen-live");
  live.checked = livePreview;
  live.onchange = () => {
    livePreview = live.checked;
    localStorage.setItem("axb-live-preview", livePreview ? "1" : "0");
    if (livePreview) benchPreview();
    else preview.clear();
  };
  $("gen-latch").onclick = () => { if (latch) actions.setSelection([latch]); };
  renderGenForm();

  $("btn-generate").onclick = async () => {
    if (latch) { unlatch(); return; }  // "＋ New layer": keep params, arm a fresh create
    genBusy(true);
    try {
      const layer = await api.post("/api/layers/generate", { module: sel.value, params: genParams });
      preview.clear(); // the real layer replaces the dashed ghost
      await actions.refreshProject();
      await actions.refreshResolved();
      latch = layer.id;               // the form now live-edits what it made
      actions.setSelection([layer.id]);
    } catch (e) { actions.oops(e); }
    finally { genBusy(false); renderBenchAction(); }  // after genBusy restores the label
  };
  initCanvasDrop();

  $("btn-empty-layer").onclick = async () => {
    // pen/brush tools get the tool-agnostic shape layer (both commit ops into
    // it, add or subtract); the draw tool keeps its stroke-capturing module
    const tool = document.querySelector("#tool-toggle button.on")?.dataset.tool;
    const isShapeTool = tool === "pen" || tool === "brush";
    const module = isShapeTool ? "shape" : "drawing";
    const params = isShapeTool ? { ops: [] } : { strokes: [] };
    try {
      const layer = await api.post("/api/layers/generate", { module, params });
      await actions.refreshProject();
      await actions.refreshResolved();
      actions.setSelection([layer.id]); // selected + module match = the tools target it
    } catch (e) { actions.oops(e); }
  };

  $("btn-lineart-stack").onclick = async () => {
    const btn = $("btn-lineart-stack");
    const flavor = $("lineart-stack-flavor").value;
    genBusy(true, btn);
    try {
      const r = await api.post("/api/layers/lineart_stack", {
        image: genParams.image,
        flavor,
        rotate: genParams.rotate ?? 0,
        width: genParams.width ?? 150,
      });
      preview.clear(); // the real layers replace the dashed ghost
      await actions.refreshProject();
      await actions.refreshResolved();
      actions.log(`created lineart stack (${flavor}, ${r.layers.length} layers)`);
    } catch (e) { actions.oops(e); }
    finally { genBusy(false, btn); }
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
    const files = [...$("asset-file").files];
    if (!files.length) return actions.oops(new Error("choose a PNG/JPEG (or a video, or several images) first"));
    try {
      await uploadAssetFiles(files, {
        frames: $("asset-frames").value,
        start: $("asset-start").value,
        every: $("asset-every").value,
      }, $("btn-asset"));
    } catch (e) { actions.oops(e); }
  };

  $("btn-clear-assets").onclick = async () => {
    if (!confirm("Remove image assets not referenced by any layer's source or effects? "
      + "Assets still in use are kept; this cannot be undone.")) return;
    const btn = $("btn-clear-assets");
    btn.disabled = true;
    try {
      const r = await api.del("/api/assets");
      S.state.assets = (await api.get("/api/assets")).assets;
      renderAssetList();
      renderLayerDetail(); // asset selects in effect forms drop any removed name
      actions.log(r.removed.length
        ? `cleared ${r.removed.length} unused asset(s)`
        : "no unused assets to clear");
    } catch (e) { actions.oops(e); }
    finally { btn.disabled = false; }
  };
  renderAssetList();
  refreshDepthProStatus();

  const mt = $("master-t");
  if (mt) {
    const cur = S.masterT ?? 0;
    mt.value = String(cur);
    $("master-t-val").textContent = `t = ${cur.toFixed(3)}`;
    mt.oninput = () => {
      const v = Number(mt.value);
      $("master-t-val").textContent = `t = ${v.toFixed(3)}`;
      scrub.request(v);
    };
  }
  renderTimeline();
}

// One upload path for the panel button and the canvas drop: several files or
// a single video import as a frame sequence, one image as a plain asset.
async function uploadAssetFiles(files, { frames, start, every } = {}, busyEl = null) {
  const isVideo = files.length === 1 && /\.(mp4|mov|webm|mkv|avi|m4v)$/i.test(files[0].name);
  const isSequence = files.length > 1 || isVideo;
  if (isSequence) genBusy(true, busyEl); // sequence import emits gen-progress SSE
  try {
    let r;
    if (isSequence) {
      const fd = new FormData();
      for (const f of files) fd.append("files", f);
      if (frames) fd.append("frames", frames);
      if (start) fd.append("start", start);
      if (every) fd.append("every", every);
      r = await api.upload("/api/assets/sequence", fd);
    } else {
      const fd = new FormData();
      fd.append("file", files[0]);
      r = await api.upload("/api/assets", fd);
    }
    S.state.assets = r.assets;
    renderAssetList();
    renderLayerDetail(); // asset selects in effect forms pick up the new name
    return r;
  } finally { if (isSequence) genBusy(false, busyEl); }
}

// Drop an image/video anywhere on the canvas: import it as an asset and, if
// the bench generator is image-driven, point the form at it right away.
function initCanvasDrop() {
  const wrap = document.getElementById("canvas-wrap");
  if (!wrap) return;
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
  wrap.addEventListener("dragover", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    wrap.classList.add("dropping");
  });
  wrap.addEventListener("dragleave", () => wrap.classList.remove("dropping"));
  wrap.addEventListener("drop", async (e) => {
    wrap.classList.remove("dropping");
    if (!hasFiles(e)) return;
    e.preventDefault();
    const files = [...e.dataTransfer.files].filter((f) =>
      /^(image|video)\//.test(f.type) || /\.(png|jpe?g|mp4|mov|webm|mkv|avi|m4v)$/i.test(f.name));
    if (!files.length) return actions.oops(new Error("drop a PNG/JPEG image or a video"));
    try {
      const r = await uploadAssetFiles(files);
      actions.log(`asset added: ${r.name}`);
      const m = S.state.modules.sources.find((x) => x.id === $("gen-select").value);
      if (m && "image" in (m.schema.properties || {})) {
        genParams.image = r.name;
        const sched = bindGenForm(m); // re-render: the asset dropdown shows the pick
        sched();
        if (latch) applyLatched();
      }
    } catch (err) { actions.oops(err); }
  });
}

function renderAssetList() {
  const el = $("asset-list");
  if (!el) return;
  const assets = S.state.assets || [];
  const names = assets.map((a) => a.name ?? a);
  el.innerHTML = "";

  const summary = document.createElement("div");
  summary.className = "hint";
  summary.textContent = names.length
    ? `image assets: ${names.join(", ")} — feed the image-driven generators and depth effects`
    : "Image assets feed the image-driven generators and depth effects.";
  el.appendChild(summary);
  if (!assets.length) return;

  if (!depthProSource || !assets.some((a) => (a.name ?? a) === depthProSource)) {
    depthProSource = names[0] || "";
  }
  const selected = assets.find((a) => (a.name ?? a) === depthProSource) || assets[0];
  const selectedName = selected?.name ?? selected ?? "";
  const frames = Math.max(Number(selected?.frames || 1), 1);
  const maxFrame = Math.max(frames - 1, 0);
  const frameValue = Math.min(Math.max(Number(depthProFrames[selectedName] || 0), 0), maxFrame);

  const tool = document.createElement("div");
  tool.className = "asset-tool";
  const row = document.createElement("div");
  row.className = "row";

  const label = document.createElement("label");
  label.textContent = "Depth Pro";
  const select = document.createElement("select");
  select.id = "depth-pro-source";
  for (const asset of assets) {
    const name = asset.name ?? asset;
    const o = document.createElement("option");
    o.value = name;
    o.textContent = asset.frames > 1 ? `${name} (${asset.frames} frames)` : name;
    select.appendChild(o);
  }
  select.value = selectedName;
  select.onchange = () => {
    depthProSource = select.value;
    renderAssetList();
  };

  const frameLabel = document.createElement("label");
  frameLabel.textContent = "frame";
  const frame = document.createElement("input");
  frame.type = "number";
  frame.min = "0";
  frame.max = String(maxFrame);
  frame.step = "1";
  frame.value = String(frameValue);
  frame.disabled = frames <= 1;
  frame.onchange = () => {
    depthProFrames[selectedName] = Math.min(Math.max(Number(frame.value) || 0, 0), maxFrame);
  };

  const nearLabel = document.createElement("label");
  nearLabel.title = "Foreground / nearer surfaces become white in the generated map";
  const near = document.createElement("input");
  near.type = "checkbox";
  near.checked = localStorage.getItem("axb-depth-pro-near-white") !== "0";
  near.onchange = () => localStorage.setItem("axb-depth-pro-near-white", near.checked ? "1" : "0");
  nearLabel.append(near, " near = white");

  const btn = document.createElement("button");
  btn.id = "btn-depth-pro";
  btn.textContent = "Create depth map";
  btn.disabled = !depthProStatus?.available;
  btn.title = depthProStatus?.detail || "Checking Depth Pro";
  btn.onclick = async () => {
    const frameIndex = Math.min(Math.max(Number(frame.value) || 0, 0), maxFrame);
    const t = frames > 1 ? frameIndex / maxFrame : 0;
    genBusy(true, btn);
    try {
      const r = await api.post("/api/assets/depth-pro", {
        image: selectedName,
        frame: t,
        near_white: near.checked,
      });
      S.state.assets = r.assets;
      renderAssetList();
      renderLayerDetail();
      actions.log(`created depth map: ${r.name}`);
    } catch (e) { actions.oops(e); }
    finally {
      genBusy(false, btn);
      refreshDepthProStatus();
    }
  };

  row.append(label, select, frameLabel, frame, nearLabel, btn);
  const status = document.createElement("div");
  status.className = "hint";
  status.textContent = depthProStatus?.detail || "Checking Depth Pro...";
  tool.append(row, status);
  el.appendChild(tool);
}

async function refreshDepthProStatus() {
  try {
    depthProStatus = await api.get("/api/assets/depth-pro/status");
  } catch (e) {
    depthProStatus = { available: false, detail: e.message || "Depth Pro status unavailable" };
  }
  renderAssetList();
}

// The lineart v2 generators (lineart_edges / lineart_hatch) get a one-click
// "Create stack" row: runs session.add_lineart_stack instead of a single
// "＋ Create layer", building the whole tonal-band + edges family at once.
const LINEART_STACK_IDS = new Set(["lineart_edges", "lineart_hatch"]);

function updateLineartStackRow(m) {
  const row = $("lineart-stack-row");
  if (!row) return;
  row.hidden = !LINEART_STACK_IDS.has(m.id);
  if (row.hidden) return;
  const btn = $("btn-lineart-stack");
  const hasImage = !!genParams.image;
  btn.disabled = !hasImage;
  btn.title = hasImage
    ? "Generate the full lineart layer stack (tonal bands + edges) from this image"
    : "choose an image first";
}

// ---- the bench latch ---------------------------------------------------------

function latchedLayer() {
  const layer = latch && (S.state.project?.layers || []).find((l) => l.id === latch);
  if (latch && !layer) { latch = null; renderBenchAction(); } // deleted under us
  return layer || null;
}

export function unlatch() {
  if (!latch) return;
  latch = null;
  preview.clear();
  renderBenchAction();
  renderLayerDetail(); // the selected layer's generator section comes back
}

function renderBenchAction() {
  const chip = $("gen-latch"), btn = $("btn-generate");
  if (!chip || !btn) return;
  const layer = latch && (S.state.project?.layers || []).find((l) => l.id === latch);
  if (layer) {
    chip.hidden = false;
    chip.textContent = `⟿ editing “${layer.name}”`;
    btn.textContent = "＋ New layer";
    btn.title = "unlatch — keep these params and arm a fresh layer";
  } else {
    chip.hidden = true;
    btn.textContent = "＋ Create layer";
    btn.title = "create a layer from these params — the sliders then edit it live";
  }
}

// slider release while latched: regenerate the layer with the new params.
// coalesce=true folds the whole slider run into ONE undo entry server-side.
// (hand-rolled debounce: `actions` isn't initialized at module-eval time —
// compose.js evaluates before main.js in their import cycle)
let applyTimer = null;
function applyLatched() {
  clearTimeout(applyTimer);
  applyTimer = setTimeout(async () => {
    const layer = latchedLayer();
    if (!layer) return;
    genBusy(true, null); // progress bar only — no button to repurpose per tweak
    try {
      await api.post(`/api/layers/${layer.id}/regenerate`, { params: { ...genParams }, coalesce: true });
      preview.clear();
      await actions.refreshProject();
      await actions.refreshResolved();
    } catch (e) { actions.oops(e); }
    finally { genBusy(false, null); }
  }, 300);
}

// dashed ghost for the bench form: in the layer's frame while latched
// (the candidate replaces the layer), in the machine frame when arming new
function benchPreview() {
  const m = S.state.modules.sources.find((x) => x.id === $("gen-select").value);
  if (!m) return;
  const layer = latchedLayer();
  if (layer) {
    preview.schedule(genPreviewReq(layer.id, layer.source.generator, { ...genParams },
      objToMat(layer.transform)));
  } else {
    preview.schedule(genPreviewReq("new", m.id, { ...genParams }));
  }
}

// Renders the gen-form DOM against whatever `genParams` currently holds
// (machine-frame, unchanged) — the shared tail of renderGenForm (new
// generator picked) and rerenderForView (view toggled, params untouched).
function bindGenForm(m) {
  const sched = () => { benchPreview(); updateLineartStackRow(m); };
  const commit = () => { sched(); if (latch) applyLatched(); };
  renderForm($("gen-form"), m.schema, genParams, commit, { onLive: sched, stateKey: `gen:${m.id}` });
  return sched;
}

function renderGenForm() {
  const m = S.state.modules.sources.find((x) => x.id === $("gen-select").value);
  if (!m) return;
  unlatch(); // picking a generator arms a new layer — never retargets a latched one
  const prev = genParams;
  genParams = { ...m.defaults };
  // roll a fresh seed on layer creation — the rolled value is stored in the
  // project, so saved layers stay reproducible (seed 0 means nothing special)
  const seedSpec = m.schema.properties?.seed;
  if (seedSpec) genParams.seed = Math.floor(Math.random() * ((seedSpec.maximum ?? 99999) + 1));
  // portrait view: viewRotate/viewAngle-tagged defaults get remapped so what
  // reads "0" (or whatever the schema default is) to the user is the same
  // physical result regardless of view — see static/js/viewmap.js.
  applyViewDefaults(m.schema, genParams, S.state?.project?.view === "portrait");
  // sticky carry-over AFTER the view remap: previous values are already
  // machine-frame, remapping them again would double-map
  for (const k of STICKY_FIELDS) {
    if (k in (m.schema.properties || {}) && prev[k] !== undefined) genParams[k] = prev[k];
  }
  preview.clear();
  const sched = bindGenForm(m);
  sched();
  updateLineartStackRow(m);
}

// Called after the view toggles (main.js): re-renders any open forms so
// viewRotate/viewAngle/viewSize-tagged fields re-map for display — params
// themselves are untouched (still machine-frame), so nothing is reset.
export function rerenderForView() {
  const sel = $("gen-select");
  if (sel) {
    const m = S.state.modules.sources.find((x) => x.id === sel.value);
    if (m) bindGenForm(m);
  }
  renderLayerDetail(); // re-derives placement + any open effect-step forms
}

// ---- layer list ------------------------------------------------------------

// While a name is being edited the list must not be rebuilt under the cursor.
// Selecting a row kicks off an async refresh that ends in renderLayerList(),
// and that used to replace the open field a beat after it appeared — the edit
// looked like it simply never opened. `prompt()` never hit this because it is
// modal and synchronous.
let renaming = null;

// ---- the layers dock ---------------------------------------------------------
//
// Collapse and height are per-machine preferences, not project data, so they
// live in localStorage and never touch the project or undo. Idempotent: it is
// wired once and survives every initTabs(), because the dock is static markup
// in index.html rather than something a tab body rebuilds.

const DOCK_H = "axb-layers-dock-h";
const DOCK_COLLAPSED = "axb-layers-dock-collapsed";
const DOCK_MIN = 110;          // below this the list shows nothing useful
const TAB_BODY_MIN = 220;      // the tab above must stay usable

function dockMax() {
  const inspector = document.getElementById("inspector");
  return Math.max(DOCK_MIN, (inspector?.clientHeight || 800) - TAB_BODY_MIN);
}

export function initLayersDock() {
  const dock = $("layers-dock");
  if (!dock || dock.dataset.dockInit) return;
  dock.dataset.dockInit = "1";

  if (localStorage.getItem(DOCK_COLLAPSED) === "1") dock.classList.add("collapsed");
  const saved = Number(localStorage.getItem(DOCK_H));
  if (saved) dock.style.setProperty("--layers-dock-h", `${saved}px`);

  $("layers-dock-title").onclick = () => {
    const collapsed = dock.classList.toggle("collapsed");
    localStorage.setItem(DOCK_COLLAPSED, collapsed ? "1" : "0");
  };

  // drag the top edge. Pointer capture rather than document-level listeners:
  // the pointer stays ours even when it leaves the 10px strip, which is what
  // happens the moment you actually drag.
  const grip = $("layers-dock-resize");
  let start = null;
  grip.addEventListener("pointerdown", (e) => {
    start = { y: e.clientY, h: dock.getBoundingClientRect().height };
    grip.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  grip.addEventListener("pointermove", (e) => {
    if (!start) return;
    // dragging UP makes it taller: the dock grows from its top edge
    const h = Math.min(dockMax(), Math.max(DOCK_MIN, start.h - (e.clientY - start.y)));
    dock.style.setProperty("--layers-dock-h", `${Math.round(h)}px`);
  });
  const end = (e) => {
    if (!start) return;
    start = null;
    grip.releasePointerCapture?.(e.pointerId);
    const h = Math.round(dock.getBoundingClientRect().height);
    localStorage.setItem(DOCK_H, String(h));
  };
  grip.addEventListener("pointerup", end);
  grip.addEventListener("pointercancel", end);
}

export function renderLayerList() {
  if (renaming) return;
  const wrap = $("layer-list");
  if (!wrap) return;
  wrap.innerHTML = "";
  const layers = S.state.project.layers;
  const resolvedById = Object.fromEntries((S.resolved?.layers || []).map((l) => [l.id, l]));
  const keyframeOwner = new Map();
  const childrenByTween = new Map();
  const animateTweens = new Set();
  for (const l of layers) {
    if (l.source.type !== "tween") continue;
    const p = l.source.params || {};
    const kids = [p.a, p.b].filter(Boolean);
    childrenByTween.set(l.id, kids);
    const isAnimateGroup = kids.length === 2 && kids.every((id) => {
      const kid = layers.find((candidate) => candidate.id === id);
      return kid && !kid.visible && /▸\s*[AB]$/.test(kid.name || "");
    });
    if (isAnimateGroup) {
      animateTweens.add(l.id);
      for (const kid of kids) keyframeOwner.set(kid, l.id);
    }
  }
  // top layer first in the list
  [...layers].reverse().forEach((layer) => {
    const r = resolvedById[layer.id];
    const owner = keyframeOwner.get(layer.id);
    if (owner && collapsedTweens.has(owner) && !S.selection.includes(layer.id)) return;
    const row = document.createElement("div");
    const isTween = layer.source.type === "tween";
    const childIds = childrenByTween.get(layer.id) || [];
    const isAnimateTween = animateTweens.has(layer.id);
    const isAnimateKeyframe = keyframeOwner.has(layer.id)
      && (!layer.visible || /▸\s*[AB]$/.test(layer.name || ""));
    row.className = [
      "layer-row",
      isTween ? "tween-row" : "",
      isAnimateKeyframe ? "keyframe-row" : "",
      S.selection.includes(layer.id) ? "selected" : "",
    ].filter(Boolean).join(" ");

    const fold = isAnimateTween && childIds.length
      ? btn(collapsedTweens.has(layer.id) ? "▸" : "▾",
          collapsedTweens.has(layer.id) ? "show animation keyframes" : "collapse animation keyframes",
          () => {
            if (collapsedTweens.has(layer.id)) collapsedTweens.delete(layer.id);
            else collapsedTweens.add(layer.id);
            localStorage.setItem("axb-collapsed-tweens", JSON.stringify([...collapsedTweens]));
            renderLayerList();
          })
      : document.createElement("span");
    fold.className = "fold";

    const eye = btn("", layer.visible ? "visible — click to hide" : "hidden — click to show",
      () => actions.patchLayer(layer.id, { visible: !layer.visible }));
    eye.append(icon(layer.visible ? EYE : EYE_OFF));
    eye.className = "eye" + (layer.visible ? "" : " off");

    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = r?.color || "#26241f";
    swatch.title = penName(layer.pen_id);

    const name = document.createElement("span");
    name.className = "lname";

    name.textContent = layer.name;
    name.title = `${layer.name} — double-click to rename`;
    // Inline, not `prompt()`: a native prompt is modal, is blockable by the
    // browser (a rename that silently does nothing), loses the row you were
    // looking at, and cannot be escaped back to the old name reliably.
    //
    // Driven by the click COUNTER, not by `dblclick`. The first click selects
    // the layer, which kicks off an async refresh that rebuilds this row — so
    // the second click lands on a different element and the browser never
    // pairs the two into a dblclick. It fired reliably for `prompt()` only
    // because that path predates the rebuild. `e.detail` counts the click
    // sequence rather than the element, so it survives the swap.
    name.onclick = (e) => {
      if (e.detail !== 2) return;       // let a single click select as usual
      const input = document.createElement("input");
      input.className = "lname-edit";
      input.value = layer.name;
      let done = false;
      renaming = layer.id;
      const finish = (commit) => {
        if (done) return;               // blur fires after Enter/Escape too
        done = true;
        renaming = null;
        const v = input.value.trim();
        input.replaceWith(name);
        if (commit && v && v !== layer.name) actions.patchLayer(layer.id, { name: v });
        else renderLayerList();         // pick up whatever changed while editing
      };
      input.onkeydown = (ev) => {
        ev.stopPropagation();           // tool letters must not fire while typing
        if (ev.key === "Enter") finish(true);
        else if (ev.key === "Escape") finish(false);
      };
      input.onblur = () => finish(true);
      input.onclick = (ev) => ev.stopPropagation();   // clicking it isn't selecting
      name.replaceWith(input);
      input.focus();
      input.select();
    };
    name.ondblclick = (e) => e.stopPropagation();   // no text-selection flash

    const est = document.createElement("span");
    est.className = "est";
    est.textContent = r?.stats?.est_s ? fmtTime(r.stats.est_s) : "";
    est.title = "estimated plot time for this layer's resolved geometry";

    const occ = btn("◼", "occluder: masks layers below", () =>
      actions.patchLayer(layer.id, { occluder: !layer.occluder }));
    occ.className = "occ " + (layer.occluder ? "on" : "off");
    if ((layer.occlude_groups || []).length) {
      occ.textContent = layer.occlude_groups.join("");
      occ.title = `occluder into group(s) ${layer.occlude_groups.join(", ")}: masks only their receivers`;
    }

    const dup = btn("⧉", "duplicate layer (or ⌥-drag)", () => duplicate(layer.id));
    // two-click delete — native confirm() dialogs are blockable/suppressible
    // by the browser, which reads as "the button does nothing"
    const deleteTitle = isAnimateKeyframe
      ? "delete keyframe (click twice) — removes the whole animation group"
      : isAnimateTween
        ? "un-animate (click twice) — restores keyframe A as the original layer"
        : isTween
          ? "delete interpolation layer (click twice)"
        : "delete layer (click twice)";
    const del = btn("✕", deleteTitle, async () => {
      if (!del.dataset.armed) {
        del.dataset.armed = "1";
        del.textContent = isAnimateTween ? "restore?" : "sure?";
        del.style.color = "var(--rust)";
        setTimeout(() => {
          delete del.dataset.armed;
          del.textContent = "✕";
          del.style.color = "";
        }, 2500);
        return;
      }
      try {
        const r = await api.del(`/api/layers/${layer.id}`);
        for (const id of r.deleted || []) collapsedTweens.delete(id);
        localStorage.setItem("axb-collapsed-tweens", JSON.stringify([...collapsedTweens]));
        await actions.refreshProject();
        await actions.refreshResolved();
        logDeleted([layer.name], r.deleted || [layer.id]);
      } catch (e) { actions.oops(e); }
    });

    row.append(fold, eye, swatch, name, est, occ, dup, del);
    makeDraggable(row, layer);
    row.onclick = (e) => {
      if (e.target.tagName === "BUTTON") return;
      if (renaming) return;             // the second click of a double-click
      const displayed = [...S.state.project.layers].reverse().map((l) => l.id);
      if (e.shiftKey && selAnchor && displayed.includes(selAnchor)) {
        // range select, file-manager style: anchor … clicked (inclusive)
        const i = displayed.indexOf(selAnchor);
        const j = displayed.indexOf(layer.id);
        const range = displayed.slice(Math.min(i, j), Math.max(i, j) + 1);
        actions.setSelection([...new Set([...S.selection, ...range])]);
      } else if (e.metaKey || e.ctrlKey) {
        actions.setSelection(toggle(S.selection, layer.id)); // individual toggle
        selAnchor = layer.id;
      } else {
        actions.setSelection([layer.id]);
        selAnchor = layer.id;
        jumpTimelineToKeyframe(layer.id);
      }
    };
    row.title = "click: select — shift-click: range — ⌘-click: toggle (select two layers to interpolate)";
    wrap.appendChild(row);
  });
  renderBenchAction(); // latch chip follows renames; a deleted latch target clears
  renderTimeline();
  renderLayerDetail();
}

function toggle(arr, id) {
  return arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id];
}

// Shared by every delete path: `names` describes what the user directly
// asked to delete (one name, or "N layers"); `deletedIds` is the server's
// full cascaded set. Extra ids beyond the direct ask were cascade-swept
// (tween <-> keyframe pairs) — call that out so undo's scope is obvious.
export function logDeleted(names, deletedIds) {
  const extra = deletedIds.length - names.length;
  const subject = names.length === 1 ? `"${names[0]}"` : `${names.length} layers`;
  if (extra > 0) {
    actions.log(`deleted ${subject} + ${extra} linked animation layer${extra === 1 ? "" : "s"} (undo restores)`);
  } else {
    actions.log(`deleted ${subject}`);
  }
}

/* Vendored Lucide path data (ISC — see THIRD-PARTY-NOTICES.md). Inline SVG,
   never an emoji: an emoji is a colour glyph the OS picks for you, so it
   ignores currentColor, changes shape between machines and reads as a
   sticker on an instrument panel. These inherit the button's colour, so the
   hidden state and the row's selected state theme for free. Stroke geometry
   is in `.tool-icon` (style.css), not here, so the icon set stays one system. */
const EYE = ['M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0'];
const EYE_OFF = [
  'M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49',
  'M14.084 14.158a3 3 0 0 1-4.242-4.242',
  'M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143',
  'm2 2 20 20',
];

function icon(paths) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "tool-icon");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  for (const d of paths) {
    const el = document.createElementNS(NS, "path");
    el.setAttribute("d", d);
    svg.append(el);
  }
  // the pupil: a circle rather than a path, exactly as Lucide draws it
  if (paths === EYE) {
    const c = document.createElementNS(NS, "circle");
    c.setAttribute("cx", "12"); c.setAttribute("cy", "12"); c.setAttribute("r", "3");
    svg.append(c);
  }
  return svg;
}

function btn(txt, title, fn) {
  const b = document.createElement("button");
  b.textContent = txt;
  b.title = title;
  b.onclick = (e) => { e.stopPropagation(); fn(); };
  return b;
}

// Drag to reorder, with a drop line. Replaces the per-row ↑ ↓: moving a layer
// across fifteen cost fourteen clicks and fourteen resolves, because each one
// was a separate reorder round-trip. A drag is one.
//
// The list is drawn TOP-FIRST (the topmost layer draws last and occludes), so
// screen order is the reverse of `project.layers`. All the arithmetic here is
// in screen order and reversed exactly once, at the end, which is the only
// place that can get it wrong.
let dragging = null;

function makeDraggable(row, layer) {
  row.draggable = true;
  row.dataset.layerId = layer.id;

  row.addEventListener("dragstart", (e) => {
    dragging = { id: layer.id, copy: e.altKey };
    e.dataTransfer.effectAllowed = "copyMove";
    e.dataTransfer.setData("text/plain", layer.id);  // Firefox needs a payload
    row.classList.add("dragging");
  });
  row.addEventListener("dragend", () => {
    dragging = null;
    row.classList.remove("dragging");
    for (const r of document.querySelectorAll(".layer-row"))
      r.classList.remove("drop-above", "drop-below");
  });
  row.addEventListener("dragover", (e) => {
    if (!dragging || dragging.id === layer.id) return;
    e.preventDefault();
    // ⌥ is read continuously, not just at dragstart: you decide to copy
    // mid-drag as often as before it
    dragging.copy = e.altKey;
    e.dataTransfer.dropEffect = dragging.copy ? "copy" : "move";
    const box = row.getBoundingClientRect();
    const above = e.clientY < box.top + box.height / 2;
    row.classList.toggle("drop-above", above);
    row.classList.toggle("drop-below", !above);
  });
  row.addEventListener("dragleave", () => {
    row.classList.remove("drop-above", "drop-below");
  });
  row.addEventListener("drop", async (e) => {
    if (!dragging || dragging.id === layer.id) return;
    e.preventDefault();
    const box = row.getBoundingClientRect();
    const above = e.clientY < box.top + box.height / 2;
    const { id, copy } = dragging;
    dragging = null;
    await dropLayer(id, layer.id, above, copy);
  });
}

async function dropLayer(movedId, targetId, above, copy) {
  try {
    if (copy) {
      const r = await api.post(`/api/layers/${movedId}/duplicate`);
      movedId = r.id || r.layer?.id || movedId;
      await actions.refreshProject();
    }
    // screen order: top of the list first
    const screen = [...S.state.project.layers].reverse().map((l) => l.id);
    const from = screen.indexOf(movedId);
    if (from >= 0) screen.splice(from, 1);
    let at = screen.indexOf(targetId);
    if (at < 0) return;
    screen.splice(above ? at : at + 1, 0, movedId);
    await api.post("/api/layers/order", { ids: screen.reverse() });  // back to draw order
    await actions.refreshProject();
    await actions.refreshResolved();
  } catch (e) { actions.oops(e); }
}

async function duplicate(id) {
  try {
    await api.post(`/api/layers/${id}/duplicate`);
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
  // selecting a DIFFERENT layer unlatches the bench — its sliders must never
  // silently retarget; selecting the latched layer itself keeps the latch
  if (latch && S.selection.length && !(S.selection.length === 1 && S.selection[0] === latch)) {
    latch = null;
    renderBenchAction();
  }
  // a regen preview ghost belongs to one layer: drop it when focus moves on
  if (preview.key && preview.key !== "new" && !S.selection.includes(preview.key)) {
    preview.clear();
  }
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

  // -- frame offset (only for generators that expose a 'frame' axis — i.e. a
  // layer driven by an image sequence). Time-shifts this layer's clip so
  // duplicates trail and animations lerp the shift A→B.
  const genMod = layer.source.generator
    && S.state.modules.sources.find((m) => m.id === layer.source.generator);
  const hasFrame = !!(genMod && genMod.schema && genMod.schema.properties
    && "frame" in genMod.schema.properties);
  if (hasFrame) {
    // a sequence-backed image ("clip#") shows/edits the offset in FRAME units,
    // which the user actually thinks in; other frame-capable sources (no
    // discrete frame count to anchor to) keep the plain normalized 0..1 input
    const imgName = (layer.source.params || {}).image;
    const seqAsset = (S.state.assets || []).find((a) => (a.name ?? a) === imgName && a.frames > 1);
    const frames = seqAsset?.frames;
    const label = frames ? "frame offset (frames)" : "frame offset";
    const step = frames ? 1 : 0.01;
    const min = frames ? -(frames - 1) : -1;
    const max = frames ? frames - 1 : 1;
    const shown = frames ? Math.round((layer.frame_offset ?? 0) * (frames - 1)) : (layer.frame_offset ?? 0);
    const title = frames
      ? `time-shift this layer's clip by N frames of the ${frames}-frame clip — duplicates can trail, and animations lerp it A→B (+6 = six frames later in the clip)`
      : "time-shift this layer's clip (added to 'frame', clamped 0..1) — duplicates can trail, and animations lerp it A→B";
    const foff = document.createElement("div");
    foff.innerHTML = `
      <h3>Frame displacement</h3>
      <div class="row">
        <label>${label}</label>
        <input type="number" id="ld-frame-offset" step="${step}" min="${min}" max="${max}"
          value="${shown}" style="width:5.5em" title="${title}">
      </div>
      ${frames ? `<label class="hint" style="cursor:pointer"
        title="the master scrubber / frame rendering advances this layer's clip one-for-one; positions never move">
        <input type="checkbox" id="ld-frame-follow" ${layer.frame_follow ? "checked" : ""}>
        clip follows timeline</label>` : ""}`;
    wrap.appendChild(foff);
    foff.querySelector("#ld-frame-offset").onchange = async (e) => {
      let v = Number(e.target.value);
      if (frames) v = Math.max(-1, Math.min(1, v / (frames - 1)));
      try {
        await api.patch(`/api/layers/${layer.id}`, { frame_offset: v });
        await actions.refreshProject();
        await actions.refreshResolved();
        renderLayerDetail();
      } catch (err) { actions.oops(err); }
    };
    const followBox = foff.querySelector("#ld-frame-follow");
    if (followBox) {
      followBox.onchange = async () => {
        try {
          await api.patch(`/api/layers/${layer.id}`, { frame_follow: followBox.checked });
          await actions.refreshProject();
          await actions.refreshResolved();
          renderTimeline(); // the panel counts following clips as scrub-able
        } catch (err) { actions.oops(err); }
      };
    }
  }

  // -- pen + occlusion
  const occ = document.createElement("div");
  occ.innerHTML = `
    <h3>Pen & occlusion</h3>
    <div class="row">
      <label>pen</label>
      <select id="ld-pen"><option value="">— none —</option></select>
    </div>
    <div class="row">
      <label><input type="checkbox" id="ld-draw" ${layer.draw !== false ? "checked" : ""}> draw strokes</label>
      <label><input type="checkbox" id="ld-occluder" ${layer.occluder ? "checked" : ""}> occluder (masks below)</label>
      <label><input type="checkbox" id="ld-receives" ${layer.receives_occlusion ? "checked" : ""}> receives occlusion</label>
    </div>
    <div class="row">
      <label title="Adjustment-layer mode: this layer's silhouette becomes a mask and its EFFECT STACK is applied to the layers below it, clipped to the region. The layer itself is never drawn or plotted (dashed on canvas).">
        <input type="checkbox" id="ld-region" ${layer.region ? "checked" : ""}> region — effects apply to layers below</label>
      ${layer.region ? `<label title="Instead of lifting the pen at the region edge, each path below is stitched back into one continuous path — outside sections verbatim, effected sections spliced in, the seam a drawn connection.">
        <input type="checkbox" id="ld-region-cont" ${layer.region_boundary === "continuous" ? "checked" : ""}> continuous lines</label>` : ""}
    </div>
    <div class="row">
      <label>margin</label>
      <input type="number" id="ld-margin" value="${layer.occlusion_margin_mm}" step="0.25" min="-20" max="20" style="width:5.5em">
      <span class="hint">mm — + opens a gap, − bleeds under</span>
    </div>
    <div class="row">
      <label title="When this layer occludes: which groups it masks. None checked = mask EVERY layer below (the classic global occluder).">occludes into</label>
      <div class="seg group-seg">${["A", "B", "C", "D"].map((g) =>
        `<button type="button" class="ld-og${(layer.occlude_groups || []).includes(g) ? " on" : ""}" value="${g}">${g}</button>`).join("")}</div>
      <span class="hint">none = all layers</span>
    </div>
    <div class="row">
      <label title="Group channels this receiver listens to, on top of the global mask. None checked = receives only ungrouped occlusion.">receives from</label>
      <div class="seg group-seg">${["A", "B", "C", "D"].map((g) =>
        `<button type="button" class="ld-rg${(layer.receives_groups || []).includes(g) ? " on" : ""}" value="${g}">${g}</button>`).join("")}</div>
      <span class="hint">none = global only</span>
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
  occ.querySelector("#ld-draw").onchange = (e) => actions.patchLayer(layer.id, { draw: e.target.checked });
  occ.querySelector("#ld-occluder").onchange = (e) => actions.patchLayer(layer.id, { occluder: e.target.checked });
  occ.querySelector("#ld-receives").onchange = (e) => actions.patchLayer(layer.id, { receives_occlusion: e.target.checked });
  occ.querySelector("#ld-region").onchange = (e) => actions.patchLayer(layer.id, { region: e.target.checked });
  const cont = occ.querySelector("#ld-region-cont");
  if (cont) cont.onchange = (e) => actions.patchLayer(layer.id, {
    region_boundary: e.target.checked ? "continuous" : "cut" });
  occ.querySelector("#ld-margin").onchange = (e) => actions.patchLayer(layer.id, { occlusion_margin_mm: +e.target.value });
  // Two four-segment groups instead of eight loose single-letter checkboxes.
  // The letters are channels, not independent settings — they read as one
  // control per row, and a `.seg` says so where eight tickboxes said "eight
  // unrelated things". State lives on the button's `.on` class, the same way
  // every other multi-select segment in the app carries it, so nothing here
  // needs a hidden input to be the truth.
  const groupPatch = (cls, field) => {
    const vals = [...occ.querySelectorAll(`${cls}.on`)].map((b) => b.value);
    actions.patchLayer(layer.id, { [field]: vals });
  };
  for (const [cls, field] of [[".ld-og", "occlude_groups"], [".ld-rg", "receives_groups"]]) {
    occ.querySelectorAll(cls).forEach((b) => {
      b.onclick = () => { b.classList.toggle("on"); groupPatch(cls, field); };
    });
  }

  // -- effect stack
  const fx = document.createElement("div");
  fx.innerHTML = `<h3>Effects <span class="hint">${layer.region
      ? "(region: applied to the layers below, inside this silhouette)"
      : "(paper-space, non-destructive)"}</span></h3>
    <div class="row">
      <select id="fx-select"></select><button id="fx-add">＋ Add</button>
      <button id="fx-consolidate" title="Bake transform + effects into the source geometry (undoable; regenerate also reverts a generated layer)">⤓ Consolidate</button>
      ${layer.source.type !== "tween" ? `<button id="fx-animate"
        title="Turn this layer into a keyframed A/B animation that follows the master timeline">⏱ Animate</button>` : ""}
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
  const animateBtn = fx.querySelector("#fx-animate");
  if (animateBtn) {
    animateBtn.onclick = async () => {
      try {
        const tw = await api.post(`/api/layers/${layer.id}/animate`);
        await actions.refreshProject();
        await actions.refreshResolved();
        actions.setSelection([tw.id]);
      } catch (e) { actions.oops(e); }
    };
  }
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
    const params = { ...mod.defaults };
    // portrait view: same viewRotate/viewAngle default remap as generators —
    // image-driven effects (depth maps) default to what reads upright.
    applyViewDefaults(mod.schema, params, S.state?.project?.view === "portrait");
    const effects = [...layer.effects, { effect: mod.id, enabled: true, params }];
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
      // drag = ghost the candidate stack (read-only server-side); release =
      // clear the ghost and commit for real (one resolve, one undo step)
      const sched = () => preview.schedule({
        key: layer.id,
        url: `/api/layers/${layer.id}/effects/preview`,
        body: { effects: layer.effects.map((s, j) => (j === i ? { ...s, params: { ...values } } : s)) },
        transform: null, // effects output paper space already
      });
      renderForm(form, mod.schema, values, () => {
        preview.clear();
        commitEffects(layer, i, { params: values });
      }, { onLive: sched, stateKey: `fx:${layer.id}:${i}` });
      div.appendChild(form);
      // A pen belongs to a LAYER, so hatching with a different pen from the
      // outline it fills means two layers. One click builds that pair.
      if (step.effect === "hatch_fill") {
        const split = document.createElement("button");
        split.className = "step-action";
        split.textContent = "Split hatch onto its own layer";
        split.title = "Fill moves to a new layer above (outline off, no pen yet — "
          + "pick one to give it its own plot pass); this layer keeps the outline. One undo step.";
        split.onclick = async () => {
          try {
            const fill = await api.post(`/api/layers/${layer.id}/split-hatch?step=${i}`);
            await actions.refreshProject();
            await actions.refreshResolved();
            actions.setSelection([fill.id]); // land on the new layer to pick its pen
          } catch (e) { actions.oops(e); }
        };
        div.appendChild(split);
      }
    }
    steps.appendChild(div);
  });

  // -- interpolation controls (tween layers)
  if (layer.source.type === "tween") {
    const p = layer.source.params || {};
    const nameOf = (id) => S.state.project.layers.find((l) => l.id === id)?.name || `${id} (missing!)`;
    const tw = document.createElement("div");
    tw.innerHTML = `<h3>Interpolation</h3>
      <div class="hint">A: ${nameOf(p.a)} → B: ${nameOf(p.b)} — interpolates generator params,
      effect params and position/rotation/scale. Pen/drawing shapes morph anchor-by-anchor
      when A and B share structure (same point count — what "animate" gives). Edits to A/B
      update live. Non-blendable differences (seeds, toggles, mismatched stacks/structure)
      jump at t = 0.5.</div>
      <div class="form" id="tw-form"></div>
      <details id="tw-stamping" class="form-group" ${p.sweep > 1 ? "open" : ""}>
        <summary>Stamping (sweep)</summary>
        <div class="hint">N in-between copies of the morph, evenly spaced BETWEEN A and B —
          the endpoints stay their own layers. For a frame ladder, check "clip follows
          timeline" on A and B.</div>
        <div class="row">
          <label>copies</label>
          <input type="number" id="tw-sweep" min="1" max="60" step="1" style="width:4.5em">
        </div>
      </details>
      <details id="tw-timeline" class="form-group" ${p.follow_master ? "open" : ""}>
        <summary>Timeline</summary>
        <div class="hint">scrubbing morphs A→B (single tween). Frame ladders advance
          via "clip follows timeline" on the layers instead.</div>
        <label class="hint" style="cursor:pointer"
          title="the master timeline scrubber (and later frame rendering) drives this tween's t">
          <input type="checkbox" id="tw-follow"> Follow timeline
        </label>
        <details id="tw-advanced" class="form-group">
          <summary>advanced timing</summary>
          <div class="row" id="tw-curve-row">
            <label>curve</label>
            <select id="tw-time-curve" style="flex:1">
              <option value="linear">linear A→B</option>
              <option value="cosine">cosine A→B (eased)</option>
              <option value="cosine_pingpong">cosine A→B→A</option>
            </select>
          </div>
          <div class="row" id="tw-window-row" title="this tween holds A before 'active from', animates inside the window, holds B after 'active to' — overlap windows to overlap clips">
            <label>active from</label>
            <input type="number" id="tw-window-from" min="0" max="1" step="0.01" style="width:4.5em">
            <label>to</label>
            <input type="number" id="tw-window-to" min="0" max="1" step="0.01" style="width:4.5em">
          </div>
        </details>
      </details>
      <div class="row">
        <button id="tw-edit-a" title="select keyframe A (${nameOf(p.a)})">edit A</button>
        <button id="tw-edit-b" title="select keyframe B (${nameOf(p.b)})">edit B</button>
        <button id="tw-explode"
          title="bake each sweep step into its own layer (pen/occlusion editable per step); the tween stays, hidden">÷ Split into layers</button>
      </div>`;
    wrap.appendChild(tw);
    // sub-sections keep whatever the user last left them at; the `open`
    // attributes above are only the first-time default (sweep/follow-driven)
    for (const id of ["tw-stamping", "tw-timeline", "tw-advanced"])
      rememberDetails(tw.querySelector(`#${id}`), id);
    tw.querySelector("#tw-edit-a").onclick = () => actions.setSelection([p.a]);
    tw.querySelector("#tw-edit-b").onclick = () => actions.setSelection([p.b]);

    // -- the auto-rendered form now carries only `t`; sweep/window are plain
    // bound inputs below, committed through the same debounced PUT merge
    const schema = JSON.parse(JSON.stringify(S.state.schemas.tween));
    delete schema.properties.a;
    delete schema.properties.b;
    delete schema.properties.follow_master; // rendered under "Timeline", not a form field
    delete schema.properties.time_curve;    // rendered under "Timeline", not a form field
    delete schema.properties.window_from;   // rendered under "Timeline", not a form field
    delete schema.properties.window_to;
    delete schema.properties.sweep;         // rendered under "Stamping (sweep)", not a form field
    const values = { t: p.t ?? 0.5, sweep: p.sweep ?? 1 };
    const commit = actions.debounce(async () => {
      try {
        layer.source.params = { ...p, ...values }; // optimistic
        await api.put(`/api/layers/${layer.id}/tween`, values);
        await actions.refreshResolved();
      } catch (e) { actions.oops(e); }
    }, 250);
    renderForm(tw.querySelector("#tw-form"), schema, values, commit, { stateKey: `tw:${layer.id}` });

    // -- stamping (sweep): plain inputs, bound into the same `values` +
    // debounced commit the t-slider uses (one PUT code path, not two)
    const bindNum = (id, key, min, max) => {
      const el = tw.querySelector(id);
      el.value = values[key];
      el.onchange = () => {
        let v = Number(el.value);
        v = Math.max(min, Math.min(max, v));
        el.value = v;
        values[key] = v;
        commit();
      };
    };
    bindNum("#tw-sweep", "sweep", 1, 60);

    // -- timeline: follow-master checkbox + an "advanced timing" fold (curve +
    // window) that only matters, and only shows, once the layer follows the
    // scrubber. The fold opens itself when either field is off its default, so
    // stored projects that set them stay visible.
    const follow = tw.querySelector("#tw-follow");
    follow.checked = !!p.follow_master;
    const advanced = tw.querySelector("#tw-advanced");
    advanced.hidden = !follow.checked;
    advanced.open = (p.time_curve && p.time_curve !== "linear")
      || (p.window_from ?? 0) !== 0 || (p.window_to ?? 1) !== 1;
    follow.onchange = async () => {
      advanced.hidden = !follow.checked;
      try {
        layer.source.params = { ...layer.source.params, follow_master: follow.checked };
        await api.put(`/api/layers/${layer.id}/tween`, { follow_master: follow.checked });
        renderTimeline(); // panel visibility follows the opt-in set
      } catch (e) { actions.oops(e); }
    };
    const winFrom = tw.querySelector("#tw-window-from");
    const winTo = tw.querySelector("#tw-window-to");
    const timeCurve = tw.querySelector("#tw-time-curve");
    timeCurve.value = p.time_curve || "linear";
    timeCurve.onchange = async () => {
      try {
        const time_curve = timeCurve.value;
        layer.source.params = { ...layer.source.params, time_curve };
        await api.put(`/api/layers/${layer.id}/tween`, { time_curve });
        await actions.refreshResolved();
      } catch (e) { actions.oops(e); }
    };
    winFrom.value = p.window_from ?? 0;
    winTo.value = p.window_to ?? 1;
    const commitWindow = async () => {
      try {
        const window_from = +winFrom.value, window_to = +winTo.value;
        layer.source.params = { ...layer.source.params, window_from, window_to };
        await api.put(`/api/layers/${layer.id}/tween`, { window_from, window_to });
        await actions.refreshResolved();
      } catch (e) { actions.oops(e); }
    };
    winFrom.onchange = commitWindow;
    winTo.onchange = commitWindow;

    tw.querySelector("#tw-explode").onclick = async () => {
      try {
        await api.post(`/api/layers/${layer.id}/explode`);
        await actions.refreshProject();
        await actions.refreshResolved();
      } catch (e) { actions.oops(e); }
    };
  } else {
    const hint = document.createElement("div");
    hint.className = "hint";
    hint.textContent = "⌘-click a second layer in the list to create a static interpolation (⇄)";
    wrap.appendChild(hint);
  }

  // -- generator params (regenerate; baked layers can return to live output).
  // While this layer is latched on the bench, the form lives THERE — two live
  // editors for the same params would drift.
  if (latch === layer.id) {
    const h = document.createElement("div");
    h.className = "hint";
    h.textContent = "⟿ generator params are latched on the bench (Generate panel)";
    wrap.appendChild(h);
  } else if (layer.source.generator && ["generator", "baked"].includes(layer.source.type)) {
    const mod = S.state.modules.sources.find((m) => m.id === layer.source.generator);
    if (mod) {
      const baked = layer.source.type === "baked";
      const gen = document.createElement("div");
      gen.innerHTML = `<h3>Generator: ${mod.label}${baked ? ' <span class="hint">(baked — regenerating discards the bake)</span>' : ""}</h3>
        <div class="form" id="regen-form"></div>
        <button id="btn-regen" class="primary">Regenerate</button>`;
      wrap.appendChild(gen);
      const values = { ...mod.defaults, ...(layer.source.params || {}) };
      // live preview ghosts the would-be geometry in the layer's frame;
      // Regenerate commits it (one undo checkpoint, not one per slider move)
      const sched = () => preview.schedule(
        genPreviewReq(layer.id, layer.source.generator, { ...values }, objToMat(layer.transform)));
      renderForm(gen.querySelector("#regen-form"), mod.schema, values, sched, { onLive: sched, stateKey: `gen:${layer.id}` });
      const regenBtn = gen.querySelector("#btn-regen");
      regenBtn.onclick = async () => {
        genBusy(true, regenBtn);
        try {
          await api.post(`/api/layers/${layer.id}/regenerate`, { params: values });
          preview.clear();
          await actions.refreshProject();
          await actions.refreshResolved();
        } catch (e) { actions.oops(e); }
        finally { genBusy(false, regenBtn); }
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
