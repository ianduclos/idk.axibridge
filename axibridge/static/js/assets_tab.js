// Imports, image assets, frame sequences, Depth Pro, and the geometry Gallery.
// Compose can reuse uploadAssetFiles for canvas drops and update its own forms
// through onAssetsChanged without coupling this tab to Compose internals.
import { api } from "./api.js";
import { S, actions } from "./main.js";
import { openGallery } from "./gallery.js";

const $ = (id) => document.getElementById(id);
let depthProStatus = null;
let depthProSource = "";
const depthProFrames = {};
let onAssetsChanged = () => {};
let activeAssetOperation = null;

function assetBusy(on, button = null) {
  if (on) {
    if (activeAssetOperation) return false;
    activeAssetOperation = button || true;
    if (button) {
      button.dataset.label = button.textContent;
      button.disabled = true;
      button.textContent = "…";
    }
    const progress = $("assets-progress");
    if (progress) progress.hidden = false;
    setAssetProgress(0, "");
    return true;
  }
  const owner = activeAssetOperation;
  activeAssetOperation = null;
  if (owner instanceof HTMLElement) {
    owner.disabled = false;
    owner.textContent = owner.dataset.label || owner.textContent;
  }
  const progress = $("assets-progress");
  if (progress) progress.hidden = true;
  const msg = $("assets-progress-msg");
  if (msg) msg.hidden = true;
  return true;
}

// The SSE stream also carries generation progress; only an Assets request may
// paint this bar. The request completion ends ownership.
export function setAssetProgress(frac, msg) {
  if (!activeAssetOperation) return;
  const bar = $("assets-progress-bar");
  if (bar) bar.style.width = `${Math.round(frac * 100)}%`;
  const label = $("assets-progress-msg");
  if (label) {
    label.hidden = !msg;
    label.textContent = msg || "";
  }
  if (activeAssetOperation instanceof HTMLElement) {
    activeAssetOperation.textContent = `${Math.round(frac * 100)}%${msg ? " · " + msg : ""}`;
  }
}

export function initAssetsTab({ onAssetsChanged: changed = () => {} } = {}) {
  onAssetsChanged = changed;
  const root = $("tab-assets");
  if (!root) return;
  root.innerHTML = `
    <section class="panel">
      <h2>Gallery</h2>
      <div class="row"><button id="btn-gallery">Open Gallery</button></div>
    </section>
    <section class="panel">
      <h2>Import SVG</h2>
      <div class="row"><input type="file" id="svg-file" accept=".svg,image/svg+xml" style="flex:1"></div>
      <div class="row">
        <label for="quant">curve tolerance</label>
        <input type="number" id="quant" value="0.1" min="0.01" max="5" step="0.01" title="Lower is smoother. Maximum SVG curve approximation error in mm; higher values use fewer points and may show facets.">
        <span class="hint">mm</span>
        <button id="btn-upload" class="primary">Upload SVG</button>
      </div>
      <div class="hint">An uploaded SVG contributes its layers as layers. Lower tolerance gives smoother curves and more points.</div>
    </section>
    <section class="panel">
      <h2>Image and video assets</h2>
      <div class="row">
        <input type="file" id="asset-file" multiple accept="image/png,image/jpeg,video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-msvideo" style="flex:1">
        <button id="btn-asset">Add image asset</button>
      </div>
      <div class="row">
        <label for="asset-frames">max frames</label><input type="number" id="asset-frames" min="1" max="240" placeholder="all">
        <label for="asset-start">start</label><input type="number" id="asset-start" min="0" placeholder="0">
        <label for="asset-every">every</label><input type="number" id="asset-every" min="1" placeholder="—">
      </div>
      <div class="hint">Optional max / start / every; video or multiple files import as a frame sequence. Dropping an image or video on the canvas binds it to the current generator.</div>
      <div id="assets-progress" class="progress" hidden><div id="assets-progress-bar"></div></div>
      <div id="assets-progress-msg" class="hint" hidden></div>
      <div class="row"><button id="btn-clear-assets" title="Remove image assets no layer currently uses (referenced assets are kept)">Clear unused assets</button></div>
      <div id="asset-list"></div>
    </section>`;
  $("btn-gallery").onclick = () => openGallery();
  $("btn-upload").onclick = async () => {
    const file = $("svg-file").files[0];
    if (!file) return actions.oops(new Error("choose an SVG file first"));
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.upload(`/api/layers/upload?quantization_mm=${Number($("quant").value) || 0.1}`, fd);
      await actions.refreshProject();
      await actions.refreshResolved();
      // Preserve the current selection: an SVG can add many layers.
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
      const result = await api.del("/api/assets");
      S.state.assets = (await api.get("/api/assets")).assets;
      renderAssetList();
      onAssetsChanged();
      actions.log(result.removed.length
        ? `cleared ${result.removed.length} unused asset(s)`
        : "no unused assets to clear");
    } catch (e) { actions.oops(e); }
    finally { btn.disabled = false; }
  };
  renderAssetList();
  refreshDepthProStatus();
}

// Shared by the panel button and Compose's canvas drop.
export async function uploadAssetFiles(files, { frames, start, every } = {}, busyEl = null) {
  if (!files?.length) throw new Error("choose an image or video first");
  const isVideo = files.length === 1 && /\.(mp4|mov|webm|mkv|avi|m4v)$/i.test(files[0].name);
  const isSequence = files.length > 1 || isVideo;
  if (isSequence && !assetBusy(true, busyEl)) {
    throw new Error("wait for the current asset import to finish");
  }
  try {
    const fd = new FormData();
    let result;
    if (isSequence) {
      for (const file of files) fd.append("files", file);
      if (frames) fd.append("frames", frames);
      if (start) fd.append("start", start);
      if (every) fd.append("every", every);
      result = await api.upload("/api/assets/sequence", fd);
    } else {
      fd.append("file", files[0]);
      result = await api.upload("/api/assets", fd);
    }
    S.state.assets = result.assets;
    renderAssetList();
    onAssetsChanged();
    return result;
  } finally { if (isSequence) assetBusy(false); }
}

export function renderAssetList() {
  const el = $("asset-list");
  if (!el || !S.state) return;
  const assets = S.state.assets || [];
  const names = assets.map((a) => a.name ?? a);
  el.replaceChildren();
  const summary = document.createElement("div");
  summary.className = "hint";
  summary.textContent = names.length
    ? `image assets: ${names.join(", ")} — feed the image-driven generators and depth effects`
    : "Image assets feed the image-driven generators and depth effects.";
  el.appendChild(summary);
  if (!assets.length) return;
  if (!depthProSource || !assets.some((a) => (a.name ?? a) === depthProSource)) depthProSource = names[0];
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
    const option = document.createElement("option");
    option.value = name;
    option.textContent = asset.frames > 1 ? `${name} (${asset.frames} frames)` : name;
    select.appendChild(option);
  }
  select.value = selectedName;
  select.onchange = () => { depthProSource = select.value; renderAssetList(); };
  const frameLabel = document.createElement("label");
  frameLabel.textContent = "frame";
  const frame = document.createElement("input");
  frame.type = "number";
  frame.min = "0";
  frame.max = String(maxFrame);
  frame.step = "1";
  frame.value = String(frameValue);
  frame.disabled = frames <= 1;
  frame.onchange = () => { depthProFrames[selectedName] = Math.min(Math.max(Number(frame.value) || 0, 0), maxFrame); };
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
    if (!assetBusy(true, btn)) return;
    try {
      const result = await api.post("/api/assets/depth-pro", {
        image: selectedName, frame: t, near_white: near.checked,
      });
      S.state.assets = result.assets;
      renderAssetList();
      onAssetsChanged();
      actions.log(`created depth map: ${result.name}`);
    } catch (e) { actions.oops(e); }
    finally { assetBusy(false); refreshDepthProStatus(); }
  };
  row.append(label, select, frameLabel, frame, nearLabel, btn);
  const status = document.createElement("div");
  status.className = "hint";
  status.textContent = depthProStatus?.detail || "Checking Depth Pro...";
  tool.append(row, status);
  el.appendChild(tool);
}

export async function refreshDepthProStatus() {
  try {
    depthProStatus = await api.get("/api/assets/depth-pro/status");
  } catch (e) {
    depthProStatus = { available: false, detail: e.message || "Depth Pro status unavailable" };
  }
  renderAssetList();
}
