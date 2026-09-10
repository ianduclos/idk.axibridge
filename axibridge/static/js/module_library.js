import { api } from "./api.js";

const API = "/api/module-library";
const browserState = {
  source: { query: "", filter: "all", scroll: 0 },
  effect: { query: "", filter: "all", scroll: 0 },
};
let activeDialog = null;
const selectedPresets = new Map();
const controlRefs = new Set();
window.addEventListener("module-library-change", () => {
  for (const ref of [...controlRefs]) {
    const root = ref.deref();
    if (!root || !root.isConnected) controlRefs.delete(ref);
    else root.__moduleLibraryRefresh();
  }
});

function el(tag, className = "", text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}

function message(error) {
  return error?.message || "The module library request failed.";
}

function emitChange() {
  const detail = { source: "module-library" };
  window.dispatchEvent(new CustomEvent("module-library-change", { detail }));
  document.dispatchEvent(new CustomEvent("module-library-change", { detail }));
}

async function library() {
  const payload = await api.get(API);
  return {
    presets: payload.presets || [],
    preferences: payload.preferences || [],
    warnings: payload.warnings || [],
  };
}

function preference(data, kind, module) {
  return data.preferences.find((p) => p.kind === kind && p.module === module)
    || { kind, module, starred: false, tags: [] };
}

function presetsFor(data, kind, module) {
  return data.presets.filter((p) => p.kind === kind && p.module === module);
}

function modal(className, label, onClose) {
  const previousDialog = activeDialog;
  const backdrop = el("div", `module-library-backdrop ${className}`);
  const dialog = el("section", "module-library-dialog");
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-label", label);
  const closeButton = el("button", "module-library-close", "Close");
  closeButton.type = "button";
  closeButton.setAttribute("aria-label", `Close ${label}`);
  dialog.append(closeButton); backdrop.append(dialog); document.body.append(backdrop);
  const background = [...document.body.children].filter((node) => node !== backdrop)
    .map((node) => [node, node.inert]);
  for (const [node] of background) node.inert = true;
  const opener = document.activeElement;
  let closed = false;
  const keydown = (event) => {
    if (activeDialog?.element !== backdrop) return;
    event.stopPropagation();
    if (event.key === "Escape") { event.preventDefault(); close(); return; }
    if (event.key !== "Tab") return;
    const focusable = [...dialog.querySelectorAll("button,input,select,textarea,[tabindex]")]
      .filter((node) => !node.disabled && node.tabIndex >= 0 && node.getClientRects().length);
    if (!focusable.length) return;
    const first = focusable[0], last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  function close() {
    if (closed) return;
    closed = true;
    window.removeEventListener("keydown", keydown, true);
    backdrop.remove();
    for (const [node, wasInert] of background) node.inert = wasInert;
    if (activeDialog?.element === backdrop) activeDialog = previousDialog?.element?.isConnected ? previousDialog : null;
    onClose?.();
    if (opener?.isConnected) opener.focus();
  }
  closeButton.onclick = close;
  backdrop.onclick = (event) => { if (event.target === backdrop) close(); };
  window.addEventListener("keydown", keydown, true);
  activeDialog = { element: backdrop, dialog, close, get closed() { return closed; } };
  return activeDialog;
}

function nameDialog({ title, value = "", action = "Save", confirmText, danger = false, onSubmit }) {
  return new Promise((resolve) => {
    const view = modal("module-library-name-dialog", title, () => resolve(null));
    const heading = el("h1", "", title);
    const form = el("form", "module-library-name-form");
    const input = el("input", "module-library-name-input");
    input.type = "text"; input.required = true; input.value = value;
    input.setAttribute("aria-label", "Preset name");
    if (confirmText) form.append(el("p", "module-library-confirm-text", confirmText));
    if (!confirmText) form.append(input);
    const cancel = el("button", "", "Cancel"); cancel.type = "button";
    const submit = el("button", danger ? "danger" : "primary", action); submit.type = "submit";
    const buttons = el("div", "module-library-dialog-actions"); buttons.append(cancel, submit);
    const error = el("div", "module-library-error"); error.hidden = true; error.setAttribute("role", "alert");
    form.append(error, buttons); view.dialog.append(heading, form);
    cancel.onclick = () => view.close();
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (submit.disabled) return;
      const result = confirmText ? true : input.value.trim();
      if (!result) return;
      submit.disabled = true; cancel.disabled = true; input.disabled = true; setError(error, null);
      try {
        const output = onSubmit ? await onSubmit(result) : result;
        resolve(output ?? result); resolve = () => {}; view.close();
      } catch (cause) {
        if (!view.closed) { setError(error, cause); submit.disabled = false; cancel.disabled = false; input.disabled = false; input.focus(); }
      }
    };
    queueMicrotask(() => { (confirmText ? submit : input).focus(); input.select?.(); });
  });
}

function setError(node, error) {
  node.textContent = error ? message(error) : "";
  node.hidden = !error;
}

/** Compact preset controls shared by generator and effect editors. */
export function createPresetControls({ kind, mod, getParams, onApply, applyLabel = "Load preset", isBusy = () => false }) {
  const root = el("div", "module-preset-controls");
  root.dataset.kind = kind; root.dataset.module = mod.id;
  const select = el("select", "module-preset-select");
  select.setAttribute("aria-label", "Preset");
  const apply = el("button", "module-preset-apply", applyLabel); apply.type = "button";
  const save = el("button", "module-preset-save", "Save as preset"); save.type = "button";
  const update = el("button", "module-preset-update", "Update selected"); update.type = "button";
  const error = el("span", "module-preset-error"); error.hidden = true; error.setAttribute("role", "alert");
  root.append(select, apply, save, update, error);
  let data = { presets: [], preferences: [], warnings: [] };
  let loadRevision = 0;
  let actionRevision = 0;
  let dataLoaded = false;
  let mutating = false;
  let desiredSelection = selectedPresets.get(`${kind}:${mod.id}`) ?? "";

  function selected() { return data.presets.find((p) => p.id === select.value) || null; }
  const selectionKey = `${kind}:${mod.id}`;
  function render(prefer) {
    const items = presetsFor(data, kind, mod.id);
    const desired = prefer !== undefined ? prefer : desiredSelection;
    select.replaceChildren();
    const defaults = el("option", "", "Defaults"); defaults.value = ""; select.append(defaults);
    for (const preset of items) { const option = el("option", "", preset.name); option.value = preset.id; select.append(option); }
    select.value = items.some((p) => p.id === desired) ? desired : "";
    if (dataLoaded) { desiredSelection = select.value; selectedPresets.set(selectionKey, select.value); }
    update.disabled = !selected();
  }
  function lock(value) {
    for (const node of [select, apply, save, update]) node.disabled = value;
    if (!value) update.disabled = !selected();
  }
  async function refresh(prefer) {
    if (mutating) return;
    const request = ++loadRevision;
    try {
      const next = await library();
      if (!root.isConnected || request !== loadRevision) return;
      data = next; dataLoaded = true; render(prefer);
    } catch (cause) { if (root.isConnected && request === loadRevision) setError(error, cause); }
  }
  root.__moduleLibraryRefresh = () => refresh(select.value);
  controlRefs.add(new WeakRef(root));
  select.onchange = () => { desiredSelection = select.value; selectedPresets.set(selectionKey, select.value); update.disabled = !selected() || isBusy(); setError(error, null); };
  apply.onclick = async () => {
    if (isBusy()) return;
    const chosen = select.value, request = ++actionRevision;
    mutating = true; lock(true); setError(error, null);
    try {
      const resolved = await api.post(`${API}/resolve`, {
        kind, module: mod.id, preset_id: chosen || null, current_params: getParams(),
      });
      if (!root.isConnected || request !== actionRevision || select.value !== chosen) return;
      if (isBusy()) throw new Error("Finish the current operation before applying a preset.");
      await onApply(resolved.params);
    } catch (cause) { if (root.isConnected && request === actionRevision) setError(error, cause); }
    finally { mutating = false; if (root.isConnected) lock(false); }
  };
  save.onclick = async () => {
    if (isBusy()) return;
    const params = structuredClone(getParams());
    const created = await nameDialog({ title: `Save ${mod.label} preset`, action: "Save preset", onSubmit: (name) => api.post(`${API}/presets`, { kind, module: mod.id, name, params }) });
    if (!created || !root.isConnected) return;
    emitChange(); await refresh(created.id);
  };
  update.onclick = async () => {
    const preset = selected();
    if (!preset || isBusy()) return;
    const chosen = preset.id; mutating = true; lock(true); setError(error, null);
    try {
      await api.patch(`${API}/presets/${encodeURIComponent(chosen)}`, { params: getParams() });
      if (!root.isConnected || select.value !== chosen) return;
      mutating = false; emitChange(); await refresh(chosen);
    } catch (cause) { if (root.isConnected && select.value === chosen) setError(error, cause); }
    finally { mutating = false; if (root.isConnected) lock(false); }
  };
  render(); queueMicrotask(() => refresh());
  return root;
}

export async function quickModules(kind, modules, currentModule) {
  try {
    const data = await library();
    const starred = modules.filter((mod) => preference(data, kind, mod.id).starred);
    const result = starred.length ? starred : [...modules];
    const current = modules.find((mod) => mod.id === currentModule);
    return current && !result.some((mod) => mod.id === current.id) ? [current, ...result] : result;
  } catch { return [...modules]; }
}

function kindTitle(kind) { return kind === "source" ? "Generators" : "Effects"; }

export async function openModuleBrowser({ kind, modules, currentModule, getCurrentParams, onUse }) {
  const state = browserState[kind] || (browserState[kind] = { query: "", filter: "all", scroll: 0 });
  let identifierObserver = null;
  let identifierClosed = false;
  let identifierQueue = [];
  let activeIdentifiers = 0;
  const view = modal("module-library-browser", kindTitle(kind), () => {
    state.scroll = list.scrollTop;
    identifierClosed = true;
    identifierQueue = [];
    identifierObserver?.disconnect();
  });
  const { dialog } = view;
  const header = el("header", "module-library-header");
  header.append(el("h1", "", kindTitle(kind)));
  const search = el("input", "module-library-search"); search.type = "search"; search.placeholder = "Search names, descriptions, tags, presets"; search.value = state.query; search.setAttribute("aria-label", "Search tools");
  const filter = el("select", "module-library-filter"); filter.setAttribute("aria-label", "Filter modules");
  for (const [value, label] of [["all", "All"], ["starred", "Starred"], ["tagged", "Tagged"]]) { const option = el("option", "", label); option.value = value; filter.append(option); }
  filter.value = state.filter; header.append(search, filter);
  const body = el("div", "module-library-body");
  const list = el("div", "module-library-list"); list.setAttribute("role", "listbox");
  const detail = el("aside", "module-library-detail"); detail.setAttribute("aria-live", "polite");
  const status = el("div", "module-library-status", "Loading…"); status.setAttribute("role", "status");
  body.append(list, detail); dialog.append(header, body, status);
  let data;
  try { data = await library(); }
  catch (cause) { status.textContent = message(cause); status.setAttribute("role", "alert"); return; }
  if (view.closed) return;
  const moduleMap = new Map(modules.map((mod) => [mod.id, mod]));
  const missingIds = [...new Set(data.presets.filter((p) => p.kind === kind && !moduleMap.has(p.module)).map((p) => p.module))];
  const entries = [...modules.map((mod) => ({ mod, unavailable: mod.available === false })), ...missingIds.map((id) => ({ mod: { id, label: id, description: "Module unavailable" }, unavailable: true }))];
  let selectedId = moduleMap.has(currentModule) ? currentModule : entries[0]?.mod.id;
  let renderRevision = 0;

  function pumpIdentifiers() {
    if (identifierClosed) return;
    while (activeIdentifiers < 2 && identifierQueue.length) {
      const img = identifierQueue.shift();
      if (!img?.isConnected || img.dataset.visible !== "true" || img.dataset.loading) continue;
      img.dataset.loading = "true";
      activeIdentifiers++;
      const done = () => {
        activeIdentifiers--;
        if (!img.naturalWidth) img.hidden = true;
        pumpIdentifiers();
      };
      img.addEventListener("load", done, { once: true });
      img.addEventListener("error", done, { once: true });
      img.src = img.dataset.src;
    }
  }
  identifierObserver = new IntersectionObserver((changes) => {
    for (const change of changes) {
      const img = change.target;
      img.dataset.visible = String(change.isIntersecting);
      if (change.isIntersecting && !img.dataset.loading && !identifierQueue.includes(img)) identifierQueue.push(img);
      else if (!change.isIntersecting) identifierQueue = identifierQueue.filter((queued) => queued !== img);
    }
    pumpIdentifiers();
  }, { root: list, rootMargin: "0px", threshold: 0.01 });

  async function savePreference(module, changes) {
    const old = preference(data, kind, module);
    const saved = await api.put(`${API}/preferences/${encodeURIComponent(kind)}/${encodeURIComponent(module)}`, {
      starred: changes.starred ?? old.starred, tags: changes.tags ?? old.tags,
    });
    data.preferences = data.preferences.filter((p) => !(p.kind === kind && p.module === module)); data.preferences.push(saved);
    emitChange(); render(); showDetail(module);
  }
  async function renamePreset(preset) {
    const saved = await nameDialog({ title: "Rename preset", value: preset.name, action: "Rename", onSubmit: (name) => api.patch(`${API}/presets/${encodeURIComponent(preset.id)}`, { name }) });
    if (!saved || view.closed) return;
    Object.assign(preset, saved); emitChange(); render(); showDetail(preset.module);
  }
  async function deletePreset(preset) {
    const yes = await nameDialog({ title: "Delete preset", action: "Delete", danger: true, confirmText: `Delete “${preset.name}”? This cannot be undone.` });
    if (!yes || view.closed) return;
    try { await api.del(`${API}/presets/${encodeURIComponent(preset.id)}`); data.presets = data.presets.filter((p) => p.id !== preset.id); emitChange(); render(); showDetail(preset.module); }
    catch (cause) { showDetail(preset.module, cause); }
  }
  function showDetail(moduleId, cause = null) {
    renderRevision++;
    selectedId = moduleId;
    for (const card of list.querySelectorAll(".module-library-card")) card.setAttribute("aria-selected", String(card.dataset.module === moduleId));
    const entry = entries.find((item) => item.mod.id === moduleId); if (!entry) return;
    const pref = preference(data, kind, moduleId), presets = presetsFor(data, kind, moduleId);
    const heading = el("div", "module-library-detail-heading");
    const title = el("h2", "", entry.mod.label || moduleId);
    const star = el("button", "module-library-star", pref.starred ? "★" : "☆"); star.type = "button"; star.setAttribute("aria-label", `${pref.starred ? "Unstar" : "Star"} ${entry.mod.label || moduleId}`); star.setAttribute("aria-pressed", String(pref.starred));
    star.onclick = async () => { star.disabled = true; try { await savePreference(moduleId, { starred: !pref.starred }); } catch (error) { showDetail(moduleId, error); } };
    heading.append(title, star);
    const description = el("p", "module-library-description", entry.mod.description || entry.mod.schema?.description || "No description available.");
    const tags = el("input", "module-library-tags"); tags.type = "text"; tags.value = (pref.tags || []).join(", "); tags.placeholder = "Tags, separated by commas"; tags.setAttribute("aria-label", `Tags for ${entry.mod.label || moduleId}`);
    const saveTags = el("button", "module-library-save-tags", "Save tags"); saveTags.type = "button";
    saveTags.onclick = async () => { saveTags.disabled = true; try { await savePreference(moduleId, { tags: tags.value.split(",").map((v) => v.trim()).filter(Boolean) }); } catch (error) { showDetail(moduleId, error); } };
    const presetHeading = el("h3", "", "Presets");
    const presetList = el("div", "module-library-presets");
    const presetSelect = el("select", "module-library-preset-select"); presetSelect.setAttribute("aria-label", "Preset");
    const defaults = el("option", "", "Defaults"); defaults.value = ""; presetSelect.append(defaults);
    for (const preset of presets) {
      const option = el("option", "", preset.name); option.value = preset.id; presetSelect.append(option);
    }
    const selectionKey = `${kind}:${moduleId}`;
    const remembered = selectedPresets.get(selectionKey) || "";
    presetSelect.value = presets.some((p) => p.id === remembered) ? remembered : "";
    const presetActions = el("div", "module-library-preset-actions");
    const use = el("button", "primary", "Use"); use.type = "button"; use.disabled = entry.unavailable; use.onclick = () => useSelection(entry, presetSelect.value || null, use);
    const rename = el("button", "", "Rename"); rename.type = "button";
    const remove = el("button", "danger", "Delete"); remove.type = "button";
    const syncActions = () => { const named = Boolean(presetSelect.value); rename.disabled = !named; remove.disabled = !named; selectedPresets.set(selectionKey, presetSelect.value); };
    presetSelect.onchange = () => { renderRevision++; syncActions(); };
    rename.onclick = () => { const preset = presets.find((p) => p.id === presetSelect.value); if (preset) renamePreset(preset); };
    remove.onclick = () => { const preset = presets.find((p) => p.id === presetSelect.value); if (preset) deletePreset(preset); };
    presetActions.append(use, rename, remove); presetList.append(presetSelect, presetActions); syncActions();
    const error = el("div", "module-library-error", cause ? message(cause) : ""); error.hidden = !cause; error.setAttribute("role", "alert");
    detail.replaceChildren(heading, description, tags, saveTags, presetHeading, presetList, error);
  }
  async function useSelection(entry, presetId, button) {
    if (entry.unavailable || view.closed) return;
    const request = ++renderRevision; button.disabled = true;
    try {
      const current = await getCurrentParams(entry.mod.id);
      if (view.closed || request !== renderRevision || selectedId !== entry.mod.id) return;
      const resolved = await api.post(`${API}/resolve`, { kind, module: entry.mod.id, preset_id: presetId, current_params: current || {} });
      if (view.closed || request !== renderRevision || selectedId !== entry.mod.id) return;
      const used = await onUse({ module: entry.mod.id, params: resolved.params, presetId });
      if (used !== false && !view.closed && request === renderRevision) view.close();
    } catch (cause) { if (!view.closed && request === renderRevision) { showDetail(entry.mod.id, cause); } }
    finally { if (button.isConnected) button.disabled = false; }
  }
  function render() {
    const query = state.query.trim().toLocaleLowerCase();
    const visible = entries.filter(({ mod }) => {
      const pref = preference(data, kind, mod.id), presets = presetsFor(data, kind, mod.id);
      if (state.filter === "starred" && !pref.starred) return false;
      if (state.filter === "tagged" && !(pref.tags || []).length) return false;
      return !query || [mod.label, mod.id, mod.description, mod.schema?.description, ...(pref.tags || []), ...presets.map((p) => p.name)].filter(Boolean).join(" ").toLocaleLowerCase().includes(query);
    });
    identifierObserver.disconnect();
    identifierQueue = [];
    list.replaceChildren();
    for (const entry of visible) {
      const card = el("button", "module-library-card"); card.type = "button"; card.dataset.module = entry.mod.id; card.setAttribute("role", "option"); card.setAttribute("aria-selected", String(entry.mod.id === selectedId));
      const thumb = el("img", "module-library-thumbnail"); thumb.alt = "";
      if (entry.unavailable) thumb.hidden = true;
      else {
        thumb.dataset.src = `${API}/modules/${encodeURIComponent(kind)}/${encodeURIComponent(entry.mod.id)}/thumbnail`;
        thumb.onerror = () => { thumb.hidden = true; };
        identifierObserver.observe(thumb);
      }
      const copy = el("span", "module-library-card-copy"); copy.append(el("span", "module-library-card-name", entry.mod.label || entry.mod.id), el("span", "module-library-card-meta", entry.unavailable ? "Unavailable · saved presets" : `${presetsFor(data, kind, entry.mod.id).length} saved · ${(preference(data, kind, entry.mod.id).tags || []).join(", ")}`));
      card.append(thumb, copy); card.onclick = () => showDetail(entry.mod.id); list.append(card);
    }
    status.textContent = `${visible.length} ${kind === "source" ? "generator" : "effect"}${visible.length === 1 ? "" : "s"}${data.warnings.length ? ` · ${data.warnings.map((w) => typeof w === "string" ? w : w.message).filter(Boolean).join(" · ")}` : ""}`;
    if (!visible.some((entry) => entry.mod.id === selectedId)) selectedId = visible[0]?.mod.id;
    if (selectedId) showDetail(selectedId); else detail.replaceChildren(el("p", "module-library-empty", "No modules match these filters."));
    requestAnimationFrame(() => { list.scrollTop = state.scroll; });
  }
  let timer;
  search.oninput = () => { state.query = search.value; clearTimeout(timer); timer = setTimeout(() => { state.scroll = 0; render(); }, 150); };
  filter.onchange = () => { state.filter = filter.value; state.scroll = 0; render(); };
  list.onscroll = () => { state.scroll = list.scrollTop; };
  render(); search.focus();
}
