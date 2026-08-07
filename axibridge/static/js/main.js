// axibridge v2 frontend orchestrator. Zero-build ES modules on purpose: no
// toolchain on the Pi, view-source debuggable, and every control surface is
// rendered from server-declared schemas (see forms.js).
//
// Data flow: hydrate from /api/state → tabs render → canvas shows RESOLVED
// geometry from /api/compose/resolved (the same resolve the plotter consumes)
// → SSE pushes machine status & job progress one-way.

import { api, subscribe } from "./api.js";
import { CanvasEditor, mul, objToMat, matToObj } from "./canvas.js";
import { initComposeTab, renderLayerList, renderLayerDetail, setGenProgress, setSeqProgress, logDeleted, rerenderForView } from "./compose.js";
import { initPlotTab, renderPlotTab, applyCapabilities } from "./plot.js";
import { initPensTab, renderPensTab } from "./pens.js";
import { initSettingsTab, renderSettingsTab } from "./settings.js";
import { initMenu } from "./menu.js";
import { initDrawMode, activateDrawMode, deactivateDrawMode } from "./draw.js";
import { initBrushMode, activateBrushMode, deactivateBrushMode, handleBrushEscape } from "./brush.js";
import { initPenMode, activatePenMode, deactivatePenMode, handlePenEscape, refreshPenOverlay,
         commitPendingPath } from "./pen.js";

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
  docPreview: null, // { label, query } while the centre canvas is showing a
                    // transient sheet/staged document instead of the live
                    // project. Any live refresh supersedes it (see below).
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

// Tear down the doc-preview banner + state (the canvas itself is repainted by
// whatever live refresh triggered this).
function clearDocPreviewState() {
  S.docPreview = null;
  const banner = $("doc-preview-banner");
  if (banner) banner.hidden = true;
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
      if (!group || !sheet) {
        S.stagedPlan = null;
        actions.exitDocPreview();  // its staged preview (if up) can't stand
      }
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
    // A live refresh (edits, SSE re-hydrate) supersedes any transient sheet
    // preview — drop it and its banner rather than fight over the canvas.
    if (S.docPreview) clearDocPreviewState();
    S.masterT = master_t;
    const q = master_t == null ? "" : `?t=${encodeURIComponent(master_t)}`;
    S.resolved = await api.get(`/api/compose/resolved${q}`);
    canvas.setData({ layers: S.resolved.layers, images: mapGhosts() });
    renderLayerList();
    renderSelReadout();
    refreshPenOverlay(); // pen's anchor/handle overlay tracks undo/redo and any other external edit
    if (opts.plan !== false) await actions.refreshPlan();
  },

  // Swap the centre canvas to a transient sheet/staged document (grid-sheet
  // page or staged tray sheet). ``query`` is the /api/preview/sheet query string
  // (already-encoded ``sheet=`` or ``staged=``). The plan overlay/estimate keep
  // running off S.sheetPlan/S.stagedPlan — this only fills the canvas geometry
  // the travel overlay draws on top of.
  async showDocPreview(label, query) {
    try {
      const data = await api.get(`/api/preview/sheet?${query}`);
      S.docPreview = { label, query };
      canvas.setData({ layers: data.layers, images: [] });
      const banner = $("doc-preview-banner");
      if (banner) { $("doc-preview-label").textContent = label; banner.hidden = false; }
    } catch (e) { oops(e); }
  },

  // Leave preview mode and restore the live project view. refreshResolved does
  // the actual banner/state teardown, so this is the single exit path.
  exitDocPreview() {
    if (S.docPreview) actions.refreshResolved();
  },

  refreshPlan: debounce(async () => {
    try {
      const sheet = S.sheetPlan ? `&sheet=${encodeURIComponent(JSON.stringify(S.sheetPlan))}` : "";
      const staged = S.stagedPlan ? `&staged=${encodeURIComponent(JSON.stringify(S.stagedPlan))}` : "";
      const r = await api.get(`/api/plan?target=${encodeURIComponent(S.plotTarget)}${sheet}${staged}`);
      S.plan = r.job;
      canvas.setPlan(r.job);
      updatePlayback();
      $("estimate").textContent =
        `est. ${fmtTime(r.job.total_duration)} · ${(r.job.pen_down_distance / 1000).toFixed(2)}m ink · ` +
        `${r.job.pen_lifts} lifts`;
      $("plan-warnings").textContent = (r.warnings || []).join("; ");
    } catch (e) {
      if (e.message?.includes("nothing") || e.message?.includes("unknown layer")) {
        $("estimate").textContent = "";
        // S.plan was left stale here, which only ever fed a readout nobody
        // re-read. It gates the playback strip now, so it has to be true.
        S.plan = null;
        canvas.setPlan(null);
        updatePlayback();
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

// ---- undo / redo -------------------------------------------------------------------
//
// One implementation, three entry points: the Edit menu items, ⌘Z / ⇧⌘Z, and
// nothing else. The server owns the history (session.py: two stacks, redo
// cleared by any real edit); this just re-reads the project afterwards, drops
// selection of layers that no longer exist, and repaints.

async function historyStep(direction) {
  try {
    await api.post(`/api/${direction}`);
    await actions.refreshProject();
    // selection may reference layers the step removed
    actions.setSelection(S.selection.filter((id) => S.state.project.layers.some((l) => l.id === id)));
    await actions.refreshResolved();
    renderLayerDetail();
  } catch (err) {
    // "nothing to undo/redo" is an answer, not a failure — say so where the
    // click happened rather than popping an error or doing nothing at all.
    if (new RegExp(`nothing to ${direction}`).test(err.message || "")) log(`nothing to ${direction}`);
    else oops(err);
  }
}
const undoStep = () => historyStep("undo");
const redoStep = () => historyStep("redo");
$("btn-undo").onclick = undoStep;
$("btn-redo").onclick = redoStep;

// ---- canvas toolbar ----------------------------------------------------------------

for (const btn of document.querySelectorAll("#view-toggle button")) {
  btn.onclick = async () => {
    document.querySelectorAll("#view-toggle button").forEach((b) => b.classList.toggle("on", b === btn));
    canvas.setData({ view: btn.dataset.view });
    try {
      await api.put("/api/project", { view: btn.dataset.view });
      S.state.project.view = btn.dataset.view; // params stay machine-frame; only display re-maps
      rerenderForView();
    } catch (e) { oops(e); }
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
// The playback strip shows only when there is a job to replay. The condition
// is `moves.length`, not "a plan exists" and not "a timeline exists": it is
// the same guard canvas.startAnimation() uses, so the strip can never offer a
// play the canvas would decline. (The redesign plan said "a timeline or staged
// series exists" — that gate is wrong for this control, which replays the
// PLANNED JOB and is just as useful on a static drawing. Flagged, not silently
// followed.)
function updatePlayback() {
  const strip = $("playback");
  if (!strip) return;
  const playable = !!S.plan?.moves?.length;
  strip.hidden = !playable;
  if (!playable && canvas.animating) canvas.stopAnimation();
}

$("zoom-fit").onclick = () => canvas.resetView();
$("doc-preview-exit").onclick = () => actions.exitDocPreview();
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
  initMenu(); // no-op after first call; the menu bar is static across project switches
  initDrawMode(); // no-op after first call (returns early if already wired)
  initPenMode();  // no-op after first call (returns early if already wired)
  initBrushMode();
  renderLayerList();
  applyPanelCollapse();
}

// ---- tool mode broker (select / draw / pen) ----------------------------------
//
// Exactly one canvas tool is active at a time. Each mode's activate()/
// deactivate() lives in its own module (draw.js, pen.js, brush.js); "select" is a no-op
// pair — it's just canvas.js's existing drag/marquee behavior with no capture
// listener stealing events. See docs/plans/pen-brush-tools.md Part 0.

const TOOL_MODES = {
  select: {},
  draw: { activate: activateDrawMode, deactivate: deactivateDrawMode },
  pen: { activate: activatePenMode, deactivate: deactivatePenMode, handleEscape: handlePenEscape },
  brush: { activate: activateBrushMode, deactivate: deactivateBrushMode, handleEscape: handleBrushEscape },
};

let toolMode = "select";

function setToolMode(mode) {
  if (!TOOL_MODES[mode] || mode === toolMode) return;
  TOOL_MODES[toolMode].deactivate?.();
  toolMode = mode;
  TOOL_MODES[toolMode].activate?.();
  document.querySelectorAll("#tool-toggle button").forEach((b) => {
    b.classList.toggle("on", b.dataset.tool === toolMode);
  });
  // per-tool companion controls sit outside the segment, so they can appear
  // beside it without disturbing the segment's joined-button styling
  const commit = $("pen-commit");
  if (commit) commit.hidden = toolMode !== "pen";
  const penBar = $("pen-bar");
  if (penBar) penBar.hidden = toolMode !== "pen";
  const brushBar = $("brush-bar");
  if (brushBar) brushBar.hidden = toolMode !== "brush";
}

{
  const seg = $("tool-toggle");
  if (seg) {
    for (const btn of seg.querySelectorAll("button")) {
      btn.onclick = () => setToolMode(btn.dataset.tool);
    }
  }

  const commit = $("pen-commit");
  if (commit) {
    commit.onclick = () => commitPendingPath();
    // pen.js owns the pending state and announces every change; the button is
    // dead weight until there is actually something to finish
    document.addEventListener("pen-pending-change", (e) => {
      commit.disabled = !e.detail?.count;
    });
  }

  // Escape: the active tool gets first refusal (e.g. pen clears a pending
  // anchor/drag without leaving the tool); only when it declines does Escape
  // fall through to "exit to select" — two stacked meanings on one key.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || toolMode === "select") return;
    if (TOOL_MODES[toolMode].handleEscape?.()) return;
    setToolMode("select");
  });

  // the doc-preview banner has no event of its own — watch its `hidden`
  // attribute so every tool forces back to select the instant a transient
  // sheet/staged document takes over the canvas (drawing on top of a
  // preview doc makes sense for none of them), re-enabling when it clears
  const banner = $("doc-preview-banner");
  if (banner && seg) {
    const sync = () => {
      const previewing = !banner.hidden;
      seg.querySelectorAll("button").forEach((b) => { b.disabled = previewing; });
      if (previewing) setToolMode("select");
    };
    new MutationObserver(sync).observe(banner, { attributes: true, attributeFilter: ["hidden"] });
    sync();
  }
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
  // a panel is a collapse level in its own right — no <details> wrapper inside
  // one. Panes whose behaviour keys off "am I visible?" (plot.js's sheet-plan
  // overlay) listen for this instead of a <details> toggle event.
  panel.dispatchEvent(new CustomEvent("panel-toggle", { bubbles: true }));
});

// Collapse state that survives a reload, for the <details> sections *inside*
// panels (form groups, tween sub-sections, the server log). `key` must be
// stable across re-renders; `dflt` only applies until the user touches it.
// Setting .open fires a toggle event, so wire any ontoggle handler that must
// run on restore BEFORE calling this.
const detailsKey = (key) => "details:" + key;

export function rememberDetails(det, key, dflt = det.open) {
  const stored = localStorage.getItem(detailsKey(key));
  const open = stored === null ? dflt : stored === "1";
  if (det.open !== open) det.open = open;
  det.addEventListener("toggle", () =>
    localStorage.setItem(detailsKey(key), det.open ? "1" : "0"));
}

// ---- app shell: double-click the header band to zoom -------------------------
//
// The transparent title bar means our header IS the title-bar band, so macOS
// never sees the double-click that would normally zoom the window — the web
// view swallows it. Only the bar's own empty space counts (same target rule as
// the drag region), and it is a no-op in a browser tab, where window.pywebview
// doesn't exist.

document.addEventListener("dblclick", (e) => {
  const header = document.querySelector("header");
  if (!header || e.target !== header) return;
  window.pywebview?.api?.zoom_window?.();
});

// ---- sliders: filled track + shift fine-tune --------------------------------
//
// One delegated implementation covers every range in the app — the ones
// forms.js generates from a schema and the hand-written ones in plot.js —
// so a new slider needs no wiring. Two jobs:
//
//   paint    the CSS custom property --fill drives the track's filled portion
//            (a pure-CSS fill can't know the value).
//   fine     holding shift while dragging or arrowing moves at a tenth of the
//            normal increment. Bounded params on an open-loop machine are
//            often tuned in fractions of a millimetre, and a 5px-wide sidebar
//            slider can't resolve that by pointer alone.

const rangeSpan = (el) => {
  const span = Number(el.max) - Number(el.min);
  return Number.isFinite(span) && span > 0 ? span : 1;
};

// The smallest increment worth making. A schema slider's track is continuous
// (step="any") while its committed value is quantized, so forms.js stamps the
// real quantum on data-fine-step — nudging by less than that is rounded away
// the moment the value commits, which reads as "shift does nothing".
const fineStep = (el) => {
  const stamped = Number(el.dataset.fineStep);
  if (Number.isFinite(stamped) && stamped > 0) return stamped;
  const step = Number(el.step);
  if (Number.isFinite(step) && step > 0) return step / 10;
  return rangeSpan(el) / 1000;
};

function paintRange(el) {
  const min = Number(el.min) || 0;
  const max = Number(el.max);
  if (!Number.isFinite(max) || max === min) return;
  const pct = ((Number(el.value) - min) / (max - min)) * 100;
  el.style.setProperty("--fill", `${Math.max(0, Math.min(100, pct))}%`);
}

function paintAllRanges(root = document) {
  for (const el of root.querySelectorAll?.('input[type="range"]') || []) paintRange(el);
}

// value changed by any route (drag, arrows, or a form re-render writing .value)
document.addEventListener("input", (e) => {
  if (e.target?.type === "range") paintRange(e.target);
}, true);

// forms re-render constantly; repaint whatever ranges appear
new MutationObserver((records) => {
  for (const r of records) {
    for (const node of r.addedNodes) {
      if (node.nodeType !== 1) continue;
      if (node.matches?.('input[type="range"]')) paintRange(node);
      else paintAllRanges(node);
    }
  }
}).observe(document.documentElement, { childList: true, subtree: true });

// shift = fine. Setting .value directly bypasses the element's own listeners,
// so dispatch input/change ourselves — forms.js commits on change, and its
// oninput drives live preview.
const emit = (el, type) => el.dispatchEvent(new Event(type, { bubbles: true }));

function nudge(el, dir, inc) {
  const min = Number(el.min), max = Number(el.max);
  let v = Number(el.value) + dir * inc;
  if (Number.isFinite(min)) v = Math.max(min, v);
  if (Number.isFinite(max)) v = Math.min(max, v);
  // trim float dust from repeated fractional adds (0.30000000000000004)
  el.value = Number(v.toPrecision(12));
  emit(el, "input");
  emit(el, "change");
}

document.addEventListener("keydown", (e) => {
  const el = e.target;
  if (el?.type !== "range" || !e.shiftKey) return;
  const dir = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 }[e.key];
  if (!dir) return;
  e.preventDefault();          // native shift+arrow is just a normal step
  nudge(el, dir, fineStep(el));
});

// shift-drag: take over the pointer so the thumb doesn't jump to the click,
// and map horizontal travel to a tenth of the track's normal range.
document.addEventListener("pointerdown", (e) => {
  const el = e.target;
  if (el?.type !== "range" || !e.shiftKey || e.button !== 0) return;
  const min = Number(el.min), max = Number(el.max);
  if (!Number.isFinite(min) || !Number.isFinite(max) || max === min) return;
  e.preventDefault();
  el.classList.add("fine");
  el.focus();
  const startX = e.clientX;
  const startV = Number(el.value);
  const perPx = ((max - min) / Math.max(1, el.getBoundingClientRect().width)) * 0.1;
  const move = (ev) => {
    const v = Math.max(min, Math.min(max, startV + (ev.clientX - startX) * perPx));
    el.value = Number(v.toPrecision(12));
    emit(el, "input");
  };
  const up = () => {
    el.classList.remove("fine");
    document.removeEventListener("pointermove", move);
    document.removeEventListener("pointerup", up);
    emit(el, "change");       // commit once, like a native drag release
  };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", up);
});

// shift held (or released) while hovering — reflect the mode on the thumb
for (const type of ["keydown", "keyup"]) {
  document.addEventListener(type, (e) => {
    if (e.key !== "Shift") return;
    const el = document.activeElement;
    if (el?.type === "range") el.classList.toggle("fine", e.shiftKey);
  });
}

function applyPanelCollapse() {
  paintAllRanges();
  document.querySelectorAll(".panel > h2").forEach((h2) => {
    const stored = localStorage.getItem(panelKey(h2));
    const collapsed = stored === null
      ? h2.parentElement.dataset.collapseDefault === "1" // panel's declared default
      : stored === "1";
    h2.parentElement.classList.toggle("collapsed", collapsed);
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
  } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
    e.preventDefault();
    await (e.shiftKey ? redoStep() : undoStep());
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
