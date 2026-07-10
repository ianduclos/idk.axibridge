// axibridge v2 frontend orchestrator. Zero-build ES modules on purpose: no
// toolchain on the Pi, view-source debuggable, and every control surface is
// rendered from server-declared schemas (see forms.js).
//
// Data flow: hydrate from /api/state → tabs render → canvas shows RESOLVED
// geometry from /api/compose/resolved (the same resolve the plotter consumes)
// → SSE pushes machine status & job progress one-way.

import { api, subscribe } from "./api.js";
import { CanvasEditor, mul, objToMat, matToObj } from "./canvas.js";
import { initComposeTab, renderLayerList, renderLayerDetail, setGenProgress, setSeqProgress, logDeleted } from "./compose.js";
import { initPlotTab, renderPlotTab, applyCapabilities } from "./plot.js";
import { initPensTab, renderPensTab } from "./pens.js";
import { initSettingsTab, renderSettingsTab } from "./settings.js";
import { initWorkbench } from "./workbench.js";

const $ = (id) => document.getElementById(id);

export const S = {
  state: null,      // /api/state snapshot
  resolved: null,   // /api/compose/resolved payload
  selection: [],    // selected layer ids
  plotTarget: "all",
  plan: null,
  masterT: null,    // master-timeline scrub (0..1); null = no scrub. UI-only.
  sheetPlan: null,  // grid-sheet spec for the CURRENT page, or null. When set,
                    // refreshPlan estimates/overlays that page instead of the
                    // plain target. Owned by the Plot tab's Animation panel.
  stagedPlan: null, // staged-sheet spec for the tray preview, or null.
};

// The active crop rectangle, mirroring Session._crop_rect client-side (mode ->
// rect, inset by crop_margin_mm on all four sides), or null when crop is off
// or the margin collapses it — same rule the server uses, so the dashed
// canvas frame always matches what plot/estimate/export will actually clip.
function cropRectFor(project) {
  const opts = project.plot_options;
  if (!opts || opts.crop === "off") return null;
  let x, y, w, h;
  if (opts.crop === "guide") {
    ({ x, y, width: w, height: h } = project.guide);
  } else if (opts.crop === "bed") {
    x = 0; y = 0; w = S.state.bed.width; h = S.state.bed.height;
  } else {
    x = opts.crop_x; y = opts.crop_y; w = opts.crop_w; h = opts.crop_h;
  }
  const m = opts.crop_margin_mm || 0;
  x += m; y += m; w -= 2 * m; h -= 2 * m;
  if (w <= 0 || h <= 0) return null;
  return { x, y, width: w, height: h };
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function log(text, cls = "") {
  const div = $("job-log");
  if (!div) return;
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = text;
  div.appendChild(line);
  while (div.childNodes.length > 200) div.removeChild(div.firstChild);
  div.scrollTop = div.scrollHeight;
}

let errTimer;
const oops = (e) => {
  console.error(e);
  log(`✗ ${e.message}`, "err");
  // also surface where it's visible from ANY tab (the job log lives in Plot)
  const g = $("global-error");
  if (g) {
    g.textContent = `✗ ${e.message}`;
    clearTimeout(errTimer);
    errTimer = setTimeout(() => { g.textContent = ""; }, 8000);
  }
};

// ---- canvas ------------------------------------------------------------------

const canvas = new CanvasEditor($("canvas"), {
  onSelect(ids) {
    S.selection = ids;
    renderLayerList();
    renderSelReadout();
  },
  async onTransform(ids, delta) {
    // commit delta ∘ transform for each dragged layer, then re-resolve
    try {
      for (const id of ids) {
        const layer = S.state.project.layers.find((l) => l.id === id);
        if (!layer) continue;
        const next = matToObj(mul(delta, objToMat(layer.transform)));
        layer.transform = next; // optimistic, server confirms via refresh
        await api.patch(`/api/layers/${id}`, { transform: next });
      }
      await actions.refreshProject();
      await actions.refreshResolved();
      renderLayerDetail(); // placement numerics track the drag
    } catch (e) { oops(e); }
  },
  async onGuideMove(pos) {
    try {
      const guide = { ...S.state.project.guide, ...pos };
      await api.put("/api/project", { guide });
      S.state.project.guide = guide;
      renderSettingsTab();
      actions.refreshCropFrame(); // crop="guide" tracks the guide rect
    } catch (e) { oops(e); }
  },
  onDoubleClick(id) {
    S.selection = [id];
    renderLayerList();
    document.querySelector('#tabs button[data-tab="compose"]').click();
  },
});

// ---- shared actions (imported by the tab modules) ------------------------------

export const actions = {
  oops,
  log,
  debounce,
  canvas: () => canvas,
  setSeqProgress, // forms.js's inline sequence-asset upload rides the same gen-progress bar

  async refreshAll() {
    await actions.refreshState();
    initTabs();          // re-init tab DOM against the new project
    await actions.refreshResolved();
  },

  async refreshState() {
    S.state = await api.get("/api/state");
    renderHeader();
    renderPlotTab();
    renderPensTab();
    renderSettingsTab();
    canvas.setData({
      bed: S.state.bed,
      guide: S.state.project.guide,
      crop: cropRectFor(S.state.project),
      view: S.state.project.view,
    });
  },

  // re-derive the dashed crop frame from current state and push it to the
  // canvas — call after anything that can change crop mode/margin/fields OR
  // the guide (crop="guide" tracks the guide rect).
  refreshCropFrame() {
    canvas.setData({ crop: cropRectFor(S.state.project) });
  },

  async refreshProject() {
    S.state.project = await api.get("/api/project");
    if (S.stagedPlan) {
      const group = (S.state.project.staging || []).find((g) => g.id === S.stagedPlan.group_id);
      const sheet = group?.sheets?.find((s) => !S.stagedPlan.sheet_id || s.id === S.stagedPlan.sheet_id);
      if (!group || !sheet) S.stagedPlan = null;
    }
    canvas.setData({
      guide: S.state.project.guide,
      crop: cropRectFor(S.state.project),
      view: S.state.project.view,
    });
    renderPlotTab(); // target list may have changed
  },

  // master_t (0..1) is the ephemeral master-timeline scrub; null = no scrub.
  // Same single resolve path — just forwards ?t= so tweens that follow the
  // master reflect the scrubbed frame. Not persisted (UI state only).
  // Defaults to the current scrub so ANY refresh (layer edits, drags) stays
  // on the scrubbed frame instead of snapping back to the stored t.
  async refreshResolved(master_t = S.masterT, opts = {}) {
    S.masterT = master_t;
    const q = master_t == null ? "" : `?t=${encodeURIComponent(master_t)}`;
    S.resolved = await api.get(`/api/compose/resolved${q}`);
    canvas.setData({ layers: S.resolved.layers, images: mapGhosts() });
    renderLayerList();
    renderSelReadout();
    if (opts.plan !== false) await actions.refreshPlan();
  },

  refreshPlan: debounce(async () => {
    try {
      const sheet = S.sheetPlan ? `&sheet=${encodeURIComponent(JSON.stringify(S.sheetPlan))}` : "";
      const staged = S.stagedPlan ? `&staged=${encodeURIComponent(JSON.stringify(S.stagedPlan))}` : "";
      const r = await api.get(`/api/plan?target=${encodeURIComponent(S.plotTarget)}${sheet}${staged}`);
      S.plan = r.job;
      canvas.setPlan(r.job);
      $("estimate").textContent =
        `est. ${fmtTime(r.job.total_duration)} · ${(r.job.pen_down_distance / 1000).toFixed(2)}m ink · ` +
        `${r.job.pen_lifts} lifts`;
      $("plan-warnings").textContent = (r.warnings || []).join("; ");
    } catch (e) {
      if (e.message?.includes("nothing") || e.message?.includes("unknown layer")) {
        $("estimate").textContent = "";
        canvas.setPlan(null);
      } else { oops(e); }
    }
  }, 200),

  patchLayer: (() => {
    const debounced = debounce(commitPatch, 350);
    return (id, patch, opts = {}) => {
      // optimistic local update so the UI doesn't flicker
      const layer = S.state.project.layers.find((l) => l.id === id);
      if (layer) Object.assign(layer, patch);
      renderLayerList();
      if (opts.debounce) debounced(id, patch);
      else commitPatch(id, patch);
    };
  })(),

  setSelection(ids) {
    S.selection = ids;
    canvas.setSelection(ids);
    renderLayerList();
    renderSelReadout();
  },
};

// Collect "show map" ghost images: depth-displace effects place their map in
// paper space; image-threshold generators place it in the layer's local frame
// (so it rides the layer transform).
function mapGhosts() {
  const dims = Object.fromEntries((S.state.assets || []).map((a) => [a.name, a]));
  const clamp01 = (v) => Math.max(0, Math.min(1, v));
  const generatorGhostParams = (p, layer) => {
    if (p.frame == null) return p;
    let shift = layer.frame_offset || 0;
    if (S.masterT != null && layer.frame_follow) shift += S.masterT;
    if (!shift) return p;
    return { ...p, frame: clamp01((p.frame || 0) + shift) };
  };
  // aspect of the placed (possibly rotated) image: 90/270 swap the sides
  const ghost = (p, x, y, transform) => {
    const d = dims[p.image];
    const w = p.width ?? 150;
    const rot = p.rotate || 0;
    const aspect = rot % 180 ? d.width / d.height : d.height / d.width;
    // encode: sequence prefixes contain '#', which a raw URL would truncate.
    // ?frame= keeps the overlay on the SAME frame the generator samples —
    // without it a sequence ghost is stuck on its first frame.
    const frame = p.frame != null ? `?frame=${encodeURIComponent(p.frame)}` : "";
    return { href: `/api/assets/${encodeURIComponent(p.image)}${frame}`, x, y, width: w, height: w * aspect,
             rot, transform };
  };
  const out = [];
  for (const layer of S.state.project.layers) {
    if (!layer.visible) continue;
    for (const step of layer.effects || []) {
      const p = step.params || {};
      if (step.effect === "depth_displace" && step.enabled && p.show_map && dims[p.image]) {
        // layer-anchored maps ride the layer's translation (matches the server)
        const anchored = (p.anchor ?? "layer") === "layer";
        const tx = anchored ? layer.transform.e : 0;
        const ty = anchored ? layer.transform.f : 0;
        out.push(ghost(p, (p.x ?? 0) + tx, (p.y ?? 0) + ty, null));
      }
    }
    // any image-driven generator (image + show_map params) ghosts its source
    // in the layer's local frame, so it rides the layer transform
    const sp = layer.source?.params || {};
    if (layer.source?.generator && sp.show_map && sp.image && dims[sp.image]) {
      out.push(ghost(generatorGhostParams(sp, layer), 0, 0, objToMat(layer.transform)));
    }
  }
  return out;
}

async function commitPatch(id, patch) {
  try {
    await api.patch(`/api/layers/${id}`, patch);
    await actions.refreshResolved();
    renderLayerDetail();
  } catch (e) { oops(e); }
}

// ---- header / status -------------------------------------------------------------

function renderHeader() {
  const m = S.state.machine;
  const backend = S.state.backends.find((b) => b.active);
  const pill = $("status-pill");
  let cls = "";
  if (m.connected) cls = m.job_state === "idle" ? "ok" : "busy";
  pill.textContent = `${backend?.label || m.backend} · ${m.connected ? m.job_state : "disconnected"}`;
  pill.className = `pill ${cls}`;
  $("project-name").value = S.state.project.name;
  // toolbar toggles reflect server state (view is saved in the project)
  document.querySelectorAll("#view-toggle button").forEach((b) =>
    b.classList.toggle("on", b.dataset.view === S.state.project.view));
}

function renderSelReadout() {
  const el = $("sel-readout");
  if (!S.selection.length) { el.textContent = "nothing selected"; return; }
  const names = S.selection.map((id) =>
    S.state.project.layers.find((l) => l.id === id)?.name || id);
  const box = canvas.selectionBBox();
  el.textContent = `${names.join(", ")}` +
    (box ? ` — ${box.w.toFixed(1)}×${box.h.toFixed(1)}mm at (${box.x.toFixed(1)}, ${box.y.toFixed(1)})` : "");
}

function fmtTime(s) {
  if (!isFinite(s)) return "—";
  const m = Math.floor(s / 60);
  return m >= 1 ? `${m}m ${Math.round(s % 60)}s` : `${s.toFixed(1)}s`;
}

// ---- header controls ---------------------------------------------------------------

$("project-name").onchange = async () => {
  try {
    await api.put("/api/project", { name: $("project-name").value });
    S.state.project.name = $("project-name").value;
  } catch (e) { oops(e); }
};
async function saveProject() {
  const btn = $("btn-save");
  try {
    const r = await api.post("/api/project/save", {});
    log(`saved: ${r.saved}`);
    renderSettingsTab();
    // visible confirmation where the click happened — the job log lives on
    // the Plot tab, so from Compose a bare save looks like it did nothing
    btn.textContent = "saved ✓";
    setTimeout(() => { btn.textContent = "Save"; }, 1500);
  } catch (e) { oops(e); }
}
$("btn-save").onclick = saveProject;

// ---- canvas toolbar ----------------------------------------------------------------

for (const btn of document.querySelectorAll("#view-toggle button")) {
  btn.onclick = async () => {
    document.querySelectorAll("#view-toggle button").forEach((b) => b.classList.toggle("on", b === btn));
    canvas.setData({ view: btn.dataset.view });
    try { await api.put("/api/project", { view: btn.dataset.view }); } catch (e) { oops(e); }
  };
}
for (const btn of document.querySelectorAll("#mode-toggle button")) {
  btn.onclick = () => {
    document.querySelectorAll("#mode-toggle button").forEach((b) => b.classList.toggle("on", b === btn));
    canvas.mode = btn.dataset.mode;
    canvas.render();
  };
}
$("show-travel").onchange = () => { canvas.showTravel = $("show-travel").checked; canvas.render(); };
$("show-order").onchange = () => { canvas.showOrder = $("show-order").checked; canvas.render(); };
$("show-guide").onchange = () => { canvas.showGuide = $("show-guide").checked; canvas.render(); };
$("zoom-fit").onclick = () => canvas.resetView();
$("btn-animate").onclick = () => {
  if (canvas.animating) {
    canvas.stopAnimation();
    $("btn-animate").textContent = "▶ Animate";
  } else if (S.plan) {
    canvas.startAnimation(Number($("anim-speed").value) || 20, () => {
      $("btn-animate").textContent = "▶ Animate";
    });
    $("btn-animate").textContent = "■ Stop";
  }
};

// ---- A/B capture series: freeze the whole current output as A, change
// anything (params, effects, transforms), freeze B, then ⇄ generates a
// staged batch interpolating the two snapshots over N steps. Re-pressing a
// letter replaces that capture (the superseded staging group is deleted).
const ab = { a: null, b: null };
function abRefresh() {
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
    log(`captured ${which.toUpperCase()} — change something, capture the other, then ⇄`);
  } catch (e) { oops(e); }
  abRefresh();
}
$("cap-a").onclick = () => abCapture("a");
$("cap-b").onclick = () => abCapture("b");
$("ab-series").onclick = async () => {
  const steps = Math.max(2, Math.min(60, Math.round(Number($("ab-steps").value) || 5)));
  try {
    const r = await api.post("/api/staging/interpolate", { a: ab.a, b: ab.b, steps });
    await actions.refreshProject();
    log(`⇄ series "${r.group.name}" (${steps} sheets) in the staging tray — Plot tab`);
  } catch (e) { oops(e); }
};

// ---- tabs -------------------------------------------------------------------------

for (const btn of document.querySelectorAll("#tabs button")) {
  btn.onclick = () => {
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b === btn));
    for (const tab of ["compose", "plot", "pens", "settings"]) {
      $(`tab-${tab}`).hidden = tab !== btn.dataset.tab;
    }
  };
}

function initTabs() {
  initComposeTab();
  initPlotTab();
  initPensTab();
  initSettingsTab();
  initWorkbench(); // no-op after first call; the modal survives re-inits
  renderLayerList();
  applyPanelCollapse();
}

// ---- sidebar: drag-resize + collapsible panels (state in localStorage) -------------

{
  const saved = localStorage.getItem("sidebar-w");
  if (saved) document.documentElement.style.setProperty("--sidebar-w", saved);
  const rz = $("sidebar-resize");
  // guard: a stale cached index.html may predate the element — a missing
  // handle must degrade to "no resizing", never to a dead UI
  if (rz) rz.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    rz.setPointerCapture(e.pointerId);
    const onMove = (ev) => {
      const w = Math.min(Math.max(window.innerWidth - ev.clientX, 340), window.innerWidth * 0.7);
      document.documentElement.style.setProperty("--sidebar-w", `${Math.round(w)}px`);
    };
    rz.addEventListener("pointermove", onMove);
    rz.addEventListener("pointerup", () => {
      rz.removeEventListener("pointermove", onMove);
      localStorage.setItem("sidebar-w",
        getComputedStyle(document.documentElement).getPropertyValue("--sidebar-w").trim());
    }, { once: true });
  });
}

// ---- fast tooltips: surface title text instantly instead of the ~1 s native delay

{
  const tip = document.createElement("div");
  tip.id = "tooltip";
  tip.hidden = true;
  document.body.appendChild(tip);
  let timer = null;
  document.addEventListener("pointerover", (e) => {
    clearTimeout(timer);
    tip.hidden = true;
    const el = e.target.closest?.("[title], [data-tip]");
    if (!el) return;
    if (el.getAttribute("title")) { // move title → data-tip: suppress the native bubble
      el.dataset.tip = el.getAttribute("title");
      el.removeAttribute("title");
    }
    if (!el.dataset.tip) return;
    timer = setTimeout(() => {
      tip.textContent = el.dataset.tip;
      tip.hidden = false;
      const r = el.getBoundingClientRect();
      tip.style.left = `${Math.max(4, Math.min(r.left, window.innerWidth - tip.offsetWidth - 8))}px`;
      tip.style.top = `${Math.min(r.bottom + 6, window.innerHeight - tip.offsetHeight - 4)}px`;
    }, 500);
  });
  document.addEventListener("pointerout", () => { clearTimeout(timer); tip.hidden = true; });
  document.addEventListener("pointerdown", () => { clearTimeout(timer); tip.hidden = true; });
}

const panelKey = (h2) => "panel:" + h2.textContent.trim().slice(0, 24);

document.addEventListener("click", (e) => {
  const h2 = e.target.closest?.(".panel > h2");
  if (!h2 || e.target.closest("button, input, select, a")) return;
  const panel = h2.parentElement;
  panel.classList.toggle("collapsed");
  localStorage.setItem(panelKey(h2), panel.classList.contains("collapsed") ? "1" : "");
});

function applyPanelCollapse() {
  document.querySelectorAll(".panel > h2").forEach((h2) => {
    h2.parentElement.classList.toggle("collapsed", localStorage.getItem(panelKey(h2)) === "1");
  });
}

// ---- keyboard -----------------------------------------------------------------------

document.addEventListener("keydown", async (e) => {
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
  if ((e.key === "Backspace" || e.key === "Delete") && S.selection.length) {
    e.preventDefault();
    try {
      const names = S.selection.map((id) =>
        S.state.project.layers.find((l) => l.id === id)?.name || id);
      const r = await api.post("/api/layers/delete", { ids: S.selection }); // one undo step
      actions.setSelection([]);
      await actions.refreshProject();
      await actions.refreshResolved();
      logDeleted(names, r.deleted || S.selection);
    } catch (err) { oops(err); }
  } else if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === "z") {
    e.preventDefault();
    try {
      await api.post("/api/undo");
      await actions.refreshProject();
      // selection may reference layers the undo removed
      actions.setSelection(S.selection.filter((id) => S.state.project.layers.some((l) => l.id === id)));
      await actions.refreshResolved();
      renderLayerDetail();
    } catch (err) {
      if (!/nothing to undo/.test(err.message || "")) oops(err);
    }
  } else if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === "s") {
    e.preventDefault(); // the browser's save-page dialog is never what's wanted here
    await saveProject();
  }
});

// ---- SSE ---------------------------------------------------------------------------

function onEvent(ev) {
  if (ev.type === "status") {
    if (S.state) {
      S.state.machine = ev;
      renderHeader();
      applyCapabilities();
      if (ev.position) canvas.setMachinePos(ev.position, false);
    }
  } else if (ev.type === "backend") {
    actions.refreshState().catch(oops);
  } else if (ev.type === "job") {
    onJobEvent(ev);
  } else if (ev.type === "gen") {
    setGenProgress(ev.frac ?? 0, ev.msg || "");
  }
}

function onJobEvent(ev) {
  const bar = $("progress-bar");
  switch (ev.kind) {
    case "started":
      if (bar) bar.style.width = "0%";
      log(`started${ev.paths_total ? ` · ${ev.paths_total} paths` : ""}`);
      break;
    case "position":
      canvas.setMachinePos(ev.position, ev.pen_down);
      if (bar && ev.progress !== undefined) bar.style.width = `${ev.progress * 100}%`;
      if (ev.remaining !== undefined) $("estimate").textContent = `remaining ${fmtTime(ev.remaining)}`;
      break;
    case "progress":
      if (bar && ev.progress !== undefined) bar.style.width = `${ev.progress * 100}%`;
      if (ev.position) canvas.setMachinePos(ev.position, !!ev.pen_down);
      if (ev.paths_done !== undefined) log(`path ${ev.paths_done}/${ev.paths_total}`);
      break;
    case "message":
      log(ev.message);
      break;
    case "finished":
      if (bar) bar.style.width = "100%";
      log("✓ finished");
      actions.refreshPlan();
      break;
    case "stopped":
      log("■ stopped");
      break;
    case "error":
      log(`✗ ${ev.message}`, "err");
      break;
  }
}

// ---- boot --------------------------------------------------------------------------

subscribe(onEvent, () => actions.refreshAll().catch(oops));
(async () => {
  try {
    await actions.refreshState();
    initTabs();
    await actions.refreshResolved();
  } catch (e) {
    $("status-pill").textContent = "backend unreachable";
    $("status-pill").className = "pill err";
    console.error(e);
  }
})();
