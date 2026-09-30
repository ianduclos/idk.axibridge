// Recovery choices are deliberate: reading candidates never mutates them,
// and project replacement only receives an action after its prerequisite
// (notably Save) has succeeded.
import { api } from "./api.js";
import { actions } from "./main.js";

let currentDialog = null;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function ensureStyle() {
  if (document.getElementById("recovery-ui-style")) return;
  const style = el("style");
  style.id = "recovery-ui-style";
  style.textContent = `
    .recovery-dialog {
      width: min(560px, calc(100vw - 32px)); max-height: min(80vh, 800px);
      overflow: auto; padding: 20px; color: var(--ink);
      background: var(--bench); border: 1px solid var(--bench-edge);
      border-radius: var(--r); box-shadow: var(--lift), 0 18px 52px rgba(0,0,0,.6);
      font: inherit;
    }
    .recovery-dialog::backdrop { background: rgba(10, 9, 8, .82); }
    .recovery-dialog h2 { margin: 0 0 12px; color: var(--ink-hi); }
    .recovery-dialog p { margin: 0 0 14px; line-height: 1.5; }
    .recovery-dialog .recovery-list {
      display: grid; gap: 8px; margin: 0 0 14px; padding: 0;
      border: 0; max-height: 36vh; overflow: auto;
    }
    .recovery-dialog .recovery-choice {
      display: flex; gap: 10px; align-items: flex-start; padding: 9px;
      border: 1px solid var(--bench-edge); border-radius: var(--r);
      cursor: pointer;
    }
    .recovery-dialog .recovery-choice:has(input:checked) { border-color: var(--live); }
    .recovery-dialog .recovery-choice span { display: grid; gap: 3px; }
    .recovery-dialog .recovery-choice small { color: var(--ink-soft); }
    .recovery-dialog .recovery-actions {
      display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 8px;
      margin-top: 18px;
    }
    .recovery-dialog [role=alert] { color: var(--rust); margin-top: 10px; }
  `;
  document.head.append(style);
}

function makeDialog(title, description) {
  ensureStyle();
  currentDialog?.close();
  const dialog = el("dialog", "recovery-dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-labelledby", "recovery-title");
  dialog.setAttribute("aria-describedby", "recovery-description");
  const heading = el("h2", "", title);
  heading.id = "recovery-title";
  const intro = el("p", "", description);
  intro.id = "recovery-description";
  const alert = el("p");
  alert.setAttribute("role", "alert");
  alert.hidden = true;
  const actionsRow = el("div", "recovery-actions");
  dialog.append(heading, intro);
  document.body.append(dialog);
  let finish;
  const result = new Promise((resolve) => { finish = resolve; });
  let settled = false;
  function close(value = null) {
    if (settled) return;
    settled = true;
    dialog.close();
    dialog.remove();
    if (currentDialog?.element === dialog) currentDialog = null;
    finish(value);
  }
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close(null);
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) close(null);
  });
  dialog.showModal();
  currentDialog = { element: dialog, close };
  return { dialog, alert, actionsRow, close, result };
}

function button(label, onClick, primary = false) {
  const control = el("button", primary ? "primary" : "", label);
  control.type = "button";
  control.onclick = onClick;
  return control;
}

function setBusy(dialog, busy) {
  for (const control of dialog.querySelectorAll("button,input")) control.disabled = busy;
}

function showError(alert, error) {
  alert.textContent = error?.message || "The recovery request failed.";
  alert.hidden = false;
}

function displayTime(value) {
  const date = new Date(typeof value === "number" && value < 10_000_000_000
    ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? String(value || "Unknown time")
    : date.toLocaleString();
}

// Called once during startup after the app has hydrated. The user may leave
// every candidate intact and continue the fresh session.
export async function initRecoveryUI({ force = false, replacement = {} } = {}) {
  let payload;
  try {
    payload = await api.get("/api/recovery");
  } catch (error) {
    actions.oops(error);
    return null;
  }
  const entries = payload?.entries || [];
  if ((!force && !payload?.offered) || !entries.length) return null;
  const modal = makeDialog(
    "Recover unfinished project",
    "Choose a saved recovery to restore, or start fresh. Only kept project content survives; unkept bench drafts are not included.",
  );
  const list = el("fieldset", "recovery-list");
  list.setAttribute("aria-label", "Recovery candidates");
  for (const [index, entry] of entries.entries()) {
    const choice = el("label", "recovery-choice");
    const radio = el("input");
    radio.type = "radio";
    radio.name = "recovery-candidate";
    radio.value = entry.id;
    radio.checked = index === 0;
    const details = el("span");
    details.append(
      el("strong", "", entry.name || "Untitled project"),
      el("small", "", displayTime(entry.created_at)),
    );
    choice.append(radio, details);
    list.append(choice);
  }
  modal.dialog.append(list);
  const selectedId = () => list.querySelector('input[name="recovery-candidate"]:checked')?.value;
  modal.actionsRow.append(
    button("Keep for later", () => modal.close(null)),
    button("Start fresh", async () => {
      const id = selectedId();
      if (!id) return;
      setBusy(modal.dialog, true);
      modal.alert.hidden = true;
      try {
        await api.post(`/api/recovery/${encodeURIComponent(id)}/discard`, {});
        modal.close({ action: "discard", id });
      } catch (error) {
        showError(modal.alert, error);
        setBusy(modal.dialog, false);
      }
    }),
    button("Restore", async () => {
      const id = selectedId();
      if (!id) return;
      setBusy(modal.dialog, true);
      modal.alert.hidden = true;
      try {
        await api.post(`/api/recovery/${encodeURIComponent(id)}/restore`, replacement);
        await actions.refreshAll();
        modal.close({ action: "restore", id });
      } catch (error) {
        showError(modal.alert, error);
        setBusy(modal.dialog, false);
      }
    }, true),
  );
  modal.dialog.append(modal.alert, modal.actionsRow);
  modal.dialog.querySelector('input[name="recovery-candidate"]')?.focus();
  // A failed fetch or render must not consume the one-time startup offer.
  // Explicit reopens do not consume it either.
  if (!force) api.post("/api/recovery/ack", {}).catch(() => {});
  return modal.result;
}

// Returns null on Cancel/Escape, so callers must leave the current project
// untouched. The server performs the replacement and interprets this action.
export async function resolveProjectReplacement() {
  let project;
  try {
    project = await api.get("/api/project");
  } catch (error) {
    actions.oops(error);
    return null;
  }
  if (!project?.dirty && !project?.metadata?.dirty) return {};
  const modal = makeDialog(
    "Replace unfinished project?",
    "This project has changes since its last save. Choose what happens to those changes before continuing.",
  );
  const addChoice = (label, value, primary = false) => {
    modal.actionsRow.append(button(label, () => modal.close({ recovery_action: value }), primary));
  };
  modal.actionsRow.append(button("Cancel", () => modal.close(null)));
  addChoice("Discard", "discard");
  addChoice("Continue with recovery", "recover");
  modal.actionsRow.append(button("Save", async () => {
    setBusy(modal.dialog, true);
    modal.alert.hidden = true;
    try {
      await api.post("/api/project/save", {});
      modal.close({ recovery_action: "save" });
    } catch (error) {
      showError(modal.alert, error);
      setBusy(modal.dialog, false);
    }
  }, true));
  modal.dialog.append(modal.alert, modal.actionsRow);
  modal.actionsRow.querySelector("button")?.focus();
  return modal.result;
}

// Settings entry point: resolve live changes before offering a recovery over
// the current project. Cancel leaves both the project and archives untouched.
export async function reopenRecoveries() {
  const replacement = await resolveProjectReplacement();
  if (replacement === null) return null;
  return initRecoveryUI({ force: true, replacement });
}
