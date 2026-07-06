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
let selAnchor = null;            // last plain/cmd-clicked layer id, for shift-range
let busyBtn = null;              // Generate/Regenerate button awaiting the server

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
    (l) => l.source.type === "tween" && (l.source.params || {}).follow_master);
  const hint = $("timeline-hint");
  if (hint) hint.hidden = panel.hidden || hasFollow;
}

const genPreviewReq = (key, module, params, transform = null) => ({
  key, url: "/api/generators/preview", body: { module, params }, transform,
});

export function initComposeTab() {
  $("tab-compose").innerHTML = `
    <div class="panel">
      <h2>Add layer</h2>
      <div class="row">
        <select id="gen-select"></select>
        <button id="btn-generate" class="primary">Convert to layer</button>
      </div>
      <div id="gen-form" class="form"></div>
      <div id="gen-progress" class="progress" hidden><div id="gen-progress-bar"></div></div>
      <div id="gen-progress-msg" class="hint" hidden></div>
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
        <input type="file" id="asset-file" multiple
          accept="image/png,image/jpeg,video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-msvideo"
          style="flex:1">
        <button id="btn-asset">Add image asset</button>
      </div>
      <div class="row">
        <label>frames</label><input type="number" id="asset-frames" min="2" max="240" placeholder="24" style="width:4.5em">
        <label>start</label><input type="number" id="asset-start" min="0" placeholder="0" style="width:4.5em">
        <label>every</label><input type="number" id="asset-every" min="1" placeholder="—" style="width:4.5em">
        <span class="hint">frames / start / every — a video or multiple files import as a frame sequence</span>
      </div>
      <div class="hint" id="asset-list"></div>
    </div>
    <div class="panel">
      <h2>Layers <span class="hint">(top of list = drawn on top / occludes below)</span></h2>
      <label class="hint" style="cursor:pointer" title="ghost the result of generator/effect sliders while you drag, before committing">
        <input type="checkbox" id="gen-live"> live preview (generators &amp; effects)
      </label>
      <div id="gen-live-note" class="hint"></div>
      <div id="layer-list"></div>
    </div>
    <div class="panel" id="timeline-panel" hidden>
      <h2>Timeline <span class="hint">(scrubs every tween set to "follow timeline")</span></h2>
      <div class="row">
        <input type="range" id="master-t" min="0" max="1" step="0.001" value="0" style="flex:1">
        <span class="hint" id="master-t-val" style="min-width:5em">t = 0.000</span>
      </div>
      <div class="hint">Live scrub only — not saved to the project.</div>
      <div class="hint" id="timeline-hint" hidden>nothing follows the timeline yet — ⏱ Animate a layer,
        or check "Follow timeline" on an interpolation layer</div>
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
    if (livePreview) preview.schedule(genPreviewReq("new", sel.value, { ...genParams }));
    else preview.clear();
  };
  renderGenForm();

  $("btn-generate").onclick = async () => {
    genBusy(true);
    try {
      await api.post("/api/layers/generate", { module: sel.value, params: genParams });
      preview.clear(); // the real layer replaces the dashed ghost
      await actions.refreshProject();
      await actions.refreshResolved();
    } catch (e) { actions.oops(e); }
    finally { genBusy(false); }
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
    const isVideo = files.length === 1 && /\.(mp4|mov|webm|mkv|avi|m4v)$/i.test(files[0].name);
    try {
      let r;
      if (files.length > 1 || isVideo) {
        const fd = new FormData();
        for (const f of files) fd.append("files", f);
        const frames = $("asset-frames").value, start = $("asset-start").value, every = $("asset-every").value;
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
    } catch (e) { actions.oops(e); }
  };
  renderAssetList();

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

function renderAssetList() {
  const el = $("asset-list");
  if (!el) return;
  const names = (S.state.assets || []).map((a) => a.name ?? a);
  el.textContent = names.length
    ? `image assets: ${names.join(", ")} — feed the 📷 generators and the depth-displace effect`
    : "Image assets feed the 📷 image-driven generators and the depth-displace effect.";
}

function renderGenForm() {
  const m = S.state.modules.sources.find((x) => x.id === $("gen-select").value);
  if (!m) return;
  genParams = { ...m.defaults };
  // portrait view draws the bed rotated 90° CW, so a y-down image reads
  // sideways at rotate=0 — pre-rotate 270 ("CW on paper") to read upright
  if ("rotate" in genParams && S.state?.project?.view === "portrait") genParams.rotate = 270;
  preview.clear();
  const sched = () => preview.schedule(genPreviewReq("new", m.id, { ...genParams }));
  renderForm($("gen-form"), m.schema, genParams, sched, { onLive: sched });
  sched();
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
        const r = await api.del(`/api/layers/${layer.id}`);
        await actions.refreshProject();
        await actions.refreshResolved();
        logDeleted([layer.name], r.deleted || [layer.id]);
      } catch (e) { actions.oops(e); }
    });

    row.append(eye, swatch, name, est, occ, up, down, dup, del);
    row.onclick = (e) => {
      if (e.target.tagName === "BUTTON") return;
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
      }
    };
    row.title = "click: select — shift-click: range — ⌘-click: toggle (select two layers to interpolate)";
    wrap.appendChild(row);
  });
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
    const foff = document.createElement("div");
    foff.innerHTML = `
      <h3>Frame displacement</h3>
      <div class="row">
        <label>frame offset</label>
        <input type="number" id="ld-frame-offset" step="0.01" min="-1" max="1"
          value="${layer.frame_offset ?? 0}" style="width:5.5em"
          title="time-shift this layer's clip (added to 'frame', clamped 0..1) — duplicates can trail, and animations lerp it A→B">
      </div>`;
    wrap.appendChild(foff);
    foff.querySelector("#ld-frame-offset").onchange = async (e) => {
      try {
        await api.patch(`/api/layers/${layer.id}`, { frame_offset: +e.target.value });
        await actions.refreshProject();
        await actions.refreshResolved();
        renderLayerDetail();
      } catch (err) { actions.oops(err); }
    };
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
    // portrait view draws the bed rotated 90° CW: image-driven effects (depth
    // maps) default to rotate 270 so the map reads upright, like generators
    if ("rotate" in params && "image" in params && S.state?.project?.view === "portrait") {
      params.rotate = 270;
    }
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
      }, { onLive: sched });
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
      <div class="hint">A: ${nameOf(p.a)} → B: ${nameOf(p.b)} — interpolates generator params,
      effect params and position/rotation/scale (not a shape morph). Edits to A/B update live.
      Non-blendable differences (seeds, toggles, mismatched stacks) jump at t = 0.5.</div>
      <div class="form" id="tw-form"></div>
      <label class="hint" style="cursor:pointer"
        title="the master timeline scrubber (and later frame rendering) drives this tween's t">
        <input type="checkbox" id="tw-follow"> Follow timeline
      </label>
      <div class="row" title="this tween holds A before 'from', animates inside the window, holds B after 'to' — overlap windows to overlap clips">
        <label>window from</label>
        <input type="number" id="tw-window-from" min="0" max="1" step="0.01" style="width:4.5em">
        <label>to</label>
        <input type="number" id="tw-window-to" min="0" max="1" step="0.01" style="width:4.5em">
      </div>
      <div class="row">
        <button id="tw-edit-a" title="select keyframe A (${nameOf(p.a)})">edit A</button>
        <button id="tw-edit-b" title="select keyframe B (${nameOf(p.b)})">edit B</button>
      </div>
      <div class="row">
        <button id="tw-static" title="a second interpolation over the same A/B: fixed-t in-between or sweep stamping, independent of the timeline">＋ Static in-between</button>
      </div>
      <div class="row"><button id="tw-explode"
        title="bake each sweep step into its own layer (pen/occlusion editable per step); the tween stays, hidden">
        ÷ Split into layers</button></div>`;
    wrap.appendChild(tw);
    tw.querySelector("#tw-edit-a").onclick = () => actions.setSelection([p.a]);
    tw.querySelector("#tw-edit-b").onclick = () => actions.setSelection([p.b]);
    const follow = tw.querySelector("#tw-follow");
    follow.checked = !!p.follow_master;
    follow.onchange = async () => {
      try {
        layer.source.params = { ...layer.source.params, follow_master: follow.checked };
        await api.put(`/api/layers/${layer.id}/tween`, { follow_master: follow.checked });
        renderTimeline(); // panel visibility follows the opt-in set
      } catch (e) { actions.oops(e); }
    };
    const winFrom = tw.querySelector("#tw-window-from");
    const winTo = tw.querySelector("#tw-window-to");
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
    tw.querySelector("#tw-static").onclick = async () => {
      try {
        const created = await api.post("/api/layers/tween", { a: p.a, b: p.b });
        await actions.refreshProject();
        await actions.refreshResolved();
        actions.setSelection([created.id]);
      } catch (e) { actions.oops(e); }
    };
    tw.querySelector("#tw-explode").onclick = async () => {
      try {
        await api.post(`/api/layers/${layer.id}/explode`);
        await actions.refreshProject();
        await actions.refreshResolved();
      } catch (e) { actions.oops(e); }
    };
    const schema = JSON.parse(JSON.stringify(S.state.schemas.tween));
    delete schema.properties.a;
    delete schema.properties.b;
    delete schema.properties.follow_master; // rendered as the checkbox below, not a form field
    delete schema.properties.window_from;   // rendered as the number inputs below, not a form field
    delete schema.properties.window_to;
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
  } else {
    const hint = document.createElement("div");
    hint.className = "hint";
    hint.textContent = "⌘-click a second layer in the list to create a static interpolation (⇄)";
    wrap.appendChild(hint);
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
      // live preview ghosts the would-be geometry in the layer's frame;
      // Regenerate commits it (one undo checkpoint, not one per slider move)
      const sched = () => preview.schedule(
        genPreviewReq(layer.id, layer.source.generator, { ...values }, objToMat(layer.transform)));
      renderForm(gen.querySelector("#regen-form"), mod.schema, values, sched, { onLive: sched });
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
