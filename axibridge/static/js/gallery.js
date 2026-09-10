import { api } from "./api.js";
import { S, actions } from "./main.js";

const galleryState = { query: "", tag: "", generator: "", thumb: 180, scroll: 0 };
let activeDialog = null;

function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function field(label, control) {
  const wrap = node("label", "gallery-field");
  wrap.append(node("span", "gallery-label", label), control);
  return wrap;
}

function errorText(error) {
  if (error?.status === 405) return "The running server does not have this gallery endpoint. Restart the AxiBridge backend, then reopen this dialog.";
  return error?.message || "The gallery request failed.";
}

function showError(el, error) {
  el.textContent = errorText(error);
  el.hidden = false;
}

function makeDialog(className, title, onClose) {
  if (activeDialog) activeDialog.close();
  const backdrop = node("div", `gallery-backdrop ${className}`);
  const dialog = node("section", "gallery-dialog");
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-label", title);
  const closeButton = node("button", "gallery-close", "Close");
  closeButton.type = "button";
  closeButton.setAttribute("aria-label", `Close ${title}`);
  dialog.append(closeButton);
  backdrop.append(dialog);
  document.body.append(backdrop);
  const background = [...document.body.children].filter((el) => el !== backdrop)
    .map((el) => [el, el.inert]);
  for (const [el] of background) el.inert = true;
  const opener = document.activeElement;
  let closed = false;
  const keydown = (event) => {
    if (dialog.contains(event.target)) event.target.__galleryKeydown?.(event);
    event.stopPropagation();
    if (event.key === "Escape") { event.preventDefault(); close(); return; }
    if (event.key !== "Tab") return;
    const focusable = [...dialog.querySelectorAll("button,input,select,textarea,[tabindex]")]
      .filter((el) => !el.disabled && el.tabIndex >= 0);
    if (!focusable.length) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  function close() {
    if (closed) return;
    closed = true;
    window.removeEventListener("keydown", keydown, true);
    backdrop.remove();
    for (const [el, wasInert] of background) el.inert = wasInert;
    if (activeDialog?.element === backdrop) activeDialog = null;
    onClose?.();
    if (opener?.isConnected) opener.focus();
  }
  closeButton.onclick = close;
  backdrop.onclick = (event) => { if (event.target === backdrop) close(); };
  window.addEventListener("keydown", keydown, true);
  activeDialog = { element: backdrop, dialog, close, get closed() { return closed; } };
  queueMicrotask(() => closeButton.focus());
  return activeDialog;
}

function svgPreview(svg, alt) {
  const img = node("img", "gallery-preview-image");
  img.alt = alt;
  if (!svg) return img;
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  img.src = url;
  img.addEventListener("load", () => URL.revokeObjectURL(url), { once: true });
  img.addEventListener("error", () => URL.revokeObjectURL(url), { once: true });
  return img;
}

function tagString(tags) { return (tags || []).join(", "); }

function tagEditor(initialTags = []) {
  const root = node("div", "gallery-tag-editor");
  const chips = node("div", "gallery-tag-chips");
  const input = node("input", "gallery-tag-draft");
  input.type = "search";
  input.placeholder = "Add tags";
  input.setAttribute("aria-label", "Add tags");
  const popular = node("div", "gallery-popular-tags");
  const tags = [];
  let popularTags = [];
  let disabled = false;

  function add(value) {
    const clean = value.trim();
    if (!clean || tags.some((tag) => tag.toLocaleLowerCase() === clean.toLocaleLowerCase())) return false;
    tags.push(clean); render(); return true;
  }
  function remove(index) { tags.splice(index, 1); render(); input.focus(); }
  function render() {
    chips.replaceChildren();
    for (const [index, tag] of tags.entries()) {
      const chip = node("span", "gallery-tag-chip");
      chip.append(node("span", "", tag));
      const removeButton = node("button", "gallery-tag-remove", "×");
      removeButton.type = "button"; removeButton.setAttribute("aria-label", `Remove tag ${tag}`);
      removeButton.disabled = disabled;
      removeButton.onclick = () => remove(index);
      chip.append(removeButton); chips.append(chip);
    }
    popular.replaceChildren();
    const available = popularTags.filter(({ tag }) => !tags.some((selected) => selected.toLocaleLowerCase() === tag.toLocaleLowerCase())).slice(0, 8);
    if (available.length) popular.append(node("span", "gallery-popular-label", "Most used"));
    for (const item of available) {
      const suggestion = node("button", "gallery-tag-suggestion", `${item.tag} ${item.count}`);
      suggestion.type = "button"; suggestion.title = `${item.count} gallery asset${item.count === 1 ? "" : "s"}`;
      suggestion.disabled = disabled;
      suggestion.onclick = () => add(item.tag); popular.append(suggestion);
    }
  }
  function commitDraft() {
    const parts = input.value.split(",");
    input.value = "";
    for (const part of parts) add(part);
  }
  input.oninput = () => {
    if (!input.value.includes(",")) return;
    const parts = input.value.split(",");
    input.value = parts.pop() || "";
    for (const part of parts) add(part);
  };
  input.__galleryKeydown = (event) => {
    if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); commitDraft(); }
    else if (event.key === "Backspace" && !input.value && tags.length) { event.preventDefault(); remove(tags.length - 1); }
  };
  root.append(chips, input, popular);
  for (const tag of initialTags) add(tag);
  api.get("/api/gallery").then((payload) => {
    popularTags = payload.tag_counts || []; render();
  }).catch(() => {});
  return {
    element: root,
    getTags() {
      const result = [...tags];
      const draft = input.value.trim();
      if (draft && !result.some((tag) => tag.toLocaleLowerCase() === draft.toLocaleLowerCase())) result.push(draft);
      return result;
    },
    setDisabled(value) { disabled = value; input.disabled = value; for (const button of root.querySelectorAll("button")) button.disabled = value; },
  };
}

function originText(origin) {
  if (!origin) return "Unknown origin";
  return origin.label || origin.module || origin.kind || "Unknown origin";
}

function metadataLine(item) {
  const date = item.created_at ? new Date(item.created_at).toLocaleString() : "Unknown date";
  const size = Number.isFinite(item.width_mm) && Number.isFinite(item.height_mm)
    ? `${item.width_mm.toFixed(1)} × ${item.height_mm.toFixed(1)} mm` : "Unknown size";
  return `${date} · ${originText(item.origin)} · ${size}`;
}

export async function openGallery() {
  let selectedId = null;
  let loadNumber = 0;
  const modal = makeDialog("gallery-browser", "Asset gallery", () => {
    galleryState.scroll = grid.scrollTop;
  });
  const { dialog } = modal;
  const header = node("header", "gallery-header");
  header.append(node("h1", "", "Gallery"));
  const search = node("input", "gallery-search");
  search.type = "search"; search.placeholder = "Search assets"; search.value = galleryState.query;
  search.setAttribute("aria-label", "Search assets");
  const tag = node("select", "gallery-filter"); tag.setAttribute("aria-label", "Filter by tag");
  const generator = node("select", "gallery-filter"); generator.setAttribute("aria-label", "Filter by generator");
  const size = node("input", "gallery-size");
  size.type = "range"; size.min = "120"; size.max = "260"; size.step = "10"; size.value = String(galleryState.thumb);
  size.setAttribute("aria-label", "Thumbnail size");
  const controls = node("div", "gallery-controls");
  controls.append(search, tag, generator, size);
  header.append(controls);
  const body = node("div", "gallery-body");
  const grid = node("div", "gallery-grid"); grid.setAttribute("role", "listbox");
  const detail = node("aside", "gallery-detail"); detail.setAttribute("aria-live", "polite");
  const status = node("div", "gallery-status"); status.setAttribute("role", "status");
  body.append(grid, detail); dialog.append(header, body, status);

  function fillSelect(select, allLabel, entries, current, valueOf, labelOf) {
    select.replaceChildren();
    const all = node("option", "", allLabel); all.value = ""; select.append(all);
    for (const entry of entries) {
      const option = node("option", "", labelOf(entry)); option.value = valueOf(entry); select.append(option);
    }
    select.value = current;
  }

  async function refreshFacets() {
    const payload = await api.get("/api/gallery");
    fillSelect(tag, "All tags", payload.tags || [], galleryState.tag, String, String);
    fillSelect(generator, "All generators", payload.generators || [], galleryState.generator,
      (entry) => entry.id, (entry) => entry.label);
  }

  async function showDetail(id) {
    selectedId = id;
    for (const card of grid.querySelectorAll(".gallery-card")) {
      card.setAttribute("aria-selected", String(card.dataset.id === id));
    }
    detail.replaceChildren(node("div", "gallery-loading", "Loading…"));
    try {
      const item = await api.get(`/api/gallery/${encodeURIComponent(id)}`);
      if (selectedId !== id) return;
      const preview = node("div", "gallery-detail-preview");
      const img = node("img", "gallery-preview-image");
      img.loading = "lazy"; img.alt = `Preview of ${item.name}`;
      img.src = `/api/gallery/${encodeURIComponent(id)}/thumbnail`;
      preview.append(img);
      const name = node("input"); name.type = "text"; name.value = item.name;
      const tags = tagEditor(item.tags);
      const note = node("textarea"); note.value = item.note || ""; note.rows = 4;
      const facts = node("p", "gallery-facts", metadataLine(item));
      const inlineError = node("div", "gallery-error"); inlineError.hidden = true; inlineError.setAttribute("role", "alert");
      const save = node("button", "", "Save details"); save.type = "button";
      const add = node("button", "primary", "Add as layer"); add.type = "button";
      const remove = node("button", "danger", "Delete"); remove.type = "button";
      const buttons = node("div", "gallery-detail-actions"); buttons.append(save, add, remove);
      detail.replaceChildren(preview, field("Name", name), field("Tags", tags.element), field("Note", note), facts, inlineError, buttons);
      const lock = (value) => { for (const control of [name, note, save, add, remove]) control.disabled = value; tags.setDisabled(value); };
      save.onclick = async () => {
        lock(true); inlineError.hidden = true;
        try {
          const updated = await api.patch(`/api/gallery/${encodeURIComponent(id)}`, {
            name: name.value.trim(), tags: tags.getTags(), note: note.value,
          });
          const card = grid.querySelector(`.gallery-card[data-id="${CSS.escape(id)}"]`);
          if (card) {
            card.querySelector(".gallery-card-name").textContent = updated.name;
            card.querySelector(".gallery-card-meta").textContent = `${originText(updated.origin)} · ${tagString(updated.tags)}`;
          }
          try { await refreshFacets(); } catch (facetError) { actions.oops(facetError); }
        } catch (error) { showError(inlineError, error); }
        finally { lock(false); }
      };
      add.onclick = async () => {
        lock(true); inlineError.hidden = true;
        try {
          const inserted = await api.post(`/api/gallery/${encodeURIComponent(id)}/insert`, {});
          const refresh = async () => {
            await actions.refreshProject();
            await actions.refreshResolved();
            actions.setSelection([inserted.id]);
            document.querySelector('#tabs button[data-tab="compose"]')?.click();
            modal.close();
          };
          try { await refresh(); }
          catch (refreshError) {
            showError(inlineError, new Error(`Layer added, but Compose could not refresh: ${errorText(refreshError)}`));
            add.textContent = "Refresh Compose";
            add.disabled = false;
            add.onclick = async () => {
              add.disabled = true; inlineError.hidden = true;
              try { await refresh(); }
              catch (retryError) { showError(inlineError, retryError); add.disabled = false; }
            };
          }
        } catch (error) { showError(inlineError, error); lock(false); }
      };
      remove.onclick = async () => {
        if (!confirm(`Delete “${item.name}” from the gallery? Existing layers will remain unchanged.`)) return;
        lock(true); inlineError.hidden = true;
        try { await api.del(`/api/gallery/${encodeURIComponent(id)}`); selectedId = null; await load(); }
        catch (error) { showError(inlineError, error); lock(false); }
      };
    } catch (error) {
      if (selectedId === id) detail.replaceChildren(node("div", "gallery-error", errorText(error)));
    }
  }

  async function load(preferId = selectedId) {
    const current = ++loadNumber;
    status.textContent = "Loading gallery…";
    const params = new URLSearchParams();
    if (galleryState.query) params.set("q", galleryState.query);
    if (galleryState.tag) params.set("tag", galleryState.tag);
    if (galleryState.generator) params.set("generator", galleryState.generator);
    try {
      const payload = await api.get(`/api/gallery?${params}`);
      if (current !== loadNumber) return;
      const items = [...(payload.items || [])].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
      fillSelect(tag, "All tags", payload.tags || [], galleryState.tag, String, String);
      fillSelect(generator, "All generators", payload.generators || [], galleryState.generator,
        (entry) => entry.id, (entry) => entry.label);
      grid.replaceChildren(); grid.style.setProperty("--gallery-thumb", `${galleryState.thumb}px`);
      for (const item of items) {
        const card = node("button", "gallery-card"); card.type = "button"; card.dataset.id = item.id;
        card.setAttribute("role", "option"); card.setAttribute("aria-selected", "false");
        const preview = node("span", "gallery-card-preview");
        const img = node("img", "gallery-preview-image"); img.loading = "lazy";
        img.alt = ""; img.src = `/api/gallery/${encodeURIComponent(item.id)}/thumbnail`;
        preview.append(img);
        card.append(preview, node("span", "gallery-card-name", item.name),
          node("span", "gallery-card-meta", `${originText(item.origin)} · ${tagString(item.tags)}`));
        card.onclick = () => showDetail(item.id);
        grid.append(card);
      }
      const countText = items.length ? `${items.length} asset${items.length === 1 ? "" : "s"} · newest first` : "No gallery assets match these filters.";
      const warningText = (payload.warnings || []).map((warning) => typeof warning === "string" ? warning : warning.message).filter(Boolean).join(" · ");
      status.textContent = warningText ? `${countText} · ${warningText}` : countText;
      requestAnimationFrame(() => { grid.scrollTop = galleryState.scroll; });
      const nextId = items.some((item) => item.id === preferId) ? preferId : items[0]?.id;
      if (nextId) await showDetail(nextId); else detail.replaceChildren(node("p", "gallery-empty", "Select an asset to see its details."));
    } catch (error) { showError(status, error); status.setAttribute("role", "alert"); }
  }

  let searchTimer;
  search.oninput = () => {
    galleryState.query = search.value;
    clearTimeout(searchTimer); searchTimer = setTimeout(() => { galleryState.scroll = 0; load(null); }, 250);
  };
  tag.onchange = () => { galleryState.tag = tag.value; galleryState.scroll = 0; load(null); };
  generator.onchange = () => { galleryState.generator = generator.value; galleryState.scroll = 0; load(null); };
  size.oninput = () => { galleryState.thumb = Number(size.value); grid.style.setProperty("--gallery-thumb", `${galleryState.thumb}px`); };
  grid.onscroll = () => { galleryState.scroll = grid.scrollTop; };
  await load();
  search.focus();
}

export async function openGallerySave(source, suggestedName = "Untitled asset") {
  let resolveClosed;
  const closed = new Promise((resolve) => { resolveClosed = resolve; });
  const modal = makeDialog("gallery-save", "Save to gallery", resolveClosed);
  const { dialog } = modal;
  const title = node("h1", "", "Save to gallery");
  const layout = node("div", "gallery-save-layout");
  const preview = node("div", "gallery-save-preview");
  const previewState = node("div", "gallery-preview-unavailable", "Preparing full-resolution geometry…");
  preview.append(previewState);
  const form = node("form", "gallery-save-form");
  const name = node("input"); name.type = "text"; name.required = true; name.value = suggestedName || "Untitled asset";
  const tags = tagEditor();
  const note = node("textarea"); note.rows = 3;
  const error = node("div", "gallery-error"); error.setAttribute("role", "alert"); error.hidden = true;
  const cancel = node("button", "", "Cancel"); cancel.type = "button"; cancel.onclick = () => modal.close();
  const save = node("button", "primary", "Save"); save.type = "submit"; save.disabled = true;
  const actionsRow = node("div", "gallery-save-actions"); actionsRow.append(cancel, save);
  form.append(field("Name", name), field("Tags (optional)", tags.element), field("Note (optional)", note), error, actionsRow);
  layout.append(preview, form); dialog.append(title, layout);
  let prepared = null;
  form.onsubmit = async (event) => {
    event.preventDefault();
    if (!prepared || save.disabled) return;
    save.disabled = true; tags.setDisabled(true); error.hidden = true;
    try {
      await api.post("/api/gallery", { capture_id: prepared.capture_id, name: name.value.trim(), tags: tags.getTags(), note: note.value });
      modal.close();
    } catch (requestError) {
      showError(error, requestError);
      tags.setDisabled(false);
      save.disabled = false;
    }
  };
  name.focus(); name.select();
  try {
    prepared = await api.post("/api/gallery/prepare", source);
    if (!modal.closed) {
      preview.replaceChildren(svgPreview(prepared.thumbnail, `Preview of ${name.value}`));
      save.disabled = false;
    }
  } catch (prepareError) {
    if (!modal.closed) {
      previewState.textContent = "Preview unavailable";
      showError(error, prepareError);
    }
  }
  await closed;
}
