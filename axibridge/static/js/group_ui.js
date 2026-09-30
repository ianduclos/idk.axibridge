// Compose hierarchy rows for projects with named groups. Project.layers remains
// the flat bottom-to-top drawing order; groups only define editing context.
import { api } from "./api.js";

const targetKey = target => `${target.kind}:${target.id}`;
const layerMap = project => new Map((project.layers || []).map(layer => [layer.id, layer]));
const groupMap = project => new Map((project.groups || []).map(group => [group.id, group]));

function ancestors(groups, groupId) {
  const result = [];
  const seen = new Set();
  while (groupId && !seen.has(groupId)) {
    seen.add(groupId);
    result.push(groupId);
    groupId = groups.get(groupId)?.parent_id || null;
  }
  return result;
}

function familyOwner(layers, layerId) {
  const layer = layers.get(layerId);
  return layer?.animation_owner_id && layers.has(layer.animation_owner_id)
    ? layer.animation_owner_id : layerId;
}

/** Remove duplicates, nested selections, and owned keyframe selections. */
export function normalizeTargets(project, targets) {
  const layers = layerMap(project), groups = groupMap(project);
  const unique = [];
  const seen = new Set();
  for (const target of targets || []) {
    if (!target || !["group", "layer"].includes(target.kind)) continue;
    const id = target.kind === "layer" ? familyOwner(layers, target.id) : target.id;
    if (!(target.kind === "group" ? groups : layers).has(id)) continue;
    const normalized = { kind: target.kind, id };
    const key = targetKey(normalized);
    if (!seen.has(key)) { unique.push(normalized); seen.add(key); }
  }
  const selectedGroups = new Set(unique.filter(target => target.kind === "group").map(target => target.id));
  return unique.filter(target => {
    const parentId = target.kind === "group"
      ? groups.get(target.id).parent_id : layers.get(target.id).group_id;
    return !ancestors(groups, parentId).some(id => selectedGroups.has(id));
  });
}

/** Map canvas layer hits to one editable target at the current group depth. */
export function targetsForLayerIds(project, ids, context = null) {
  const layers = layerMap(project), groups = groupMap(project);
  const targets = [];
  for (const id of ids || []) {
    const ownerId = familyOwner(layers, id);
    const layer = layers.get(ownerId);
    if (!layer) continue;
    const chain = ancestors(groups, layer.group_id).reverse();
    if (context && !chain.includes(context)) continue;
    const childGroup = context ? chain[chain.indexOf(context) + 1] : chain[0];
    targets.push(childGroup ? { kind: "group", id: childGroup } : { kind: "layer", id: ownerId });
  }
  return normalizeTargets(project, targets);
}

/** Expand selected groups and animation families to flat drawing layer IDs. */
export function memberIds(project, targets) {
  const layers = layerMap(project), groups = groupMap(project);
  const selected = normalizeTargets(project, targets);
  const groupIds = new Set(selected.filter(target => target.kind === "group").map(target => target.id));
  const ownerIds = new Set(selected.filter(target => target.kind === "layer").map(target => target.id));
  return (project.layers || []).filter(layer =>
    ancestors(groups, layer.group_id).some(id => groupIds.has(id))
    || ownerIds.has(familyOwner(layers, layer.id))
  ).map(layer => layer.id);
}

export function siblingTargets(project, context = null) {
  const groups = groupMap(project);
  const found = [], seen = new Set();
  for (const layer of project.layers || []) {
    if (layer.animation_owner_id) continue; // a family is one editing unit
    const chain = ancestors(groups, layer.group_id).reverse();
    if (context && !chain.includes(context)) continue;
    const childGroup = context ? chain[chain.indexOf(context) + 1] : chain[0];
    const target = childGroup ? { kind: "group", id: childGroup } : { kind: "layer", id: layer.id };
    const key = targetKey(target);
    if (!seen.has(key)) { found.push(target); seen.add(key); }
  }
  return found; // bottom-to-top, matching Project.layers
}

function button(label, title, click) {
  const element = document.createElement("button");
  element.type = "button";
  element.textContent = label;
  element.title = title;
  element.setAttribute("aria-label", title);
  element.addEventListener("click", event => { event.stopPropagation(); click(event); });
  return element;
}

/** Render immediate children of `context`, highest drawing row first.
 *
 * Callbacks: {project, context, selection, onSelect, onEnter, onExit,
 * onRefresh, onError, renderLayer}. `onSelect` receives typed targets; the caller derives
 * canvas leaf IDs with memberIds(). `onRefresh` reloads project/resolved state.
 */
export function renderHierarchy(container, callbacks) {
  const {
    project, context = null, selection = [], onSelect = () => {},
    onEnter = () => {}, onExit = () => {}, onRefresh = () => {}, onError, renderLayer,
  } = callbacks;
  const groups = groupMap(project), layers = layerMap(project);
  const order = siblingTargets(project, context);
  const selected = new Set(normalizeTargets(project, selection).map(targetKey));
  container.replaceChildren();

  const run = async operation => {
    try { await operation(); await onRefresh(); }
    catch (error) { if (onError) onError(error); else throw error; }
  };

  if (context) {
    const breadcrumb = document.createElement("div");
    breadcrumb.className = "group-breadcrumb";
    breadcrumb.append(button("←", "Exit group", () => onExit()));
    const label = document.createElement("span");
    label.textContent = groups.get(context)?.name || "Group";
    breadcrumb.append(label);
    container.append(breadcrumb);
  }

  for (const target of [...order].reverse()) {
    const isGroup = target.kind === "group";
    if (!isGroup && renderLayer) {
      const rendered = renderLayer(target);
      if (Array.isArray(rendered)) container.append(...rendered.filter(Boolean));
      else if (rendered) container.append(rendered);
      continue;
    }
    const item = isGroup ? groups.get(target.id) : layers.get(target.id);
    if (!item) continue;
    const row = document.createElement("div");
    row.className = `layer-row${isGroup ? " group-row" : ""}${selected.has(targetKey(target)) ? " selected" : ""}`;
    row.dataset.kind = target.kind;
    row.dataset.id = target.id;

    const name = button(item.name || (isGroup ? "Group" : "Layer"), item.name || "Layer", event => {
      if (event.detail >= 2) {
        const renamed = window.prompt(`Rename ${isGroup ? "group" : "layer"}`, item.name || "");
        const value = renamed?.trim();
        if (value && value !== item.name) {
          const path = isGroup ? `/api/compose/groups/${target.id}` : `/api/layers/${target.id}`;
          run(() => api.patch(path, { name: value }));
        }
      } else {
        const current = normalizeTargets(project, selection);
        const next = (event.metaKey || event.ctrlKey || event.shiftKey)
          ? (selected.has(targetKey(target))
            ? current.filter(other => targetKey(other) !== targetKey(target))
            : [...current, target])
          : [target];
        onSelect(normalizeTargets(project, next));
      }
    });
    name.className = "lname";
    row.append(name);

    const shown = item.visible && item.inherited_visible !== false;
    const eye = button(shown ? "◉" : "○", `${shown ? "Hide" : "Show"} ${item.name}`,
      () => run(() => api.patch(isGroup ? `/api/compose/groups/${target.id}` : `/api/layers/${target.id}`,
        { visible: !shown })));
    eye.className = `eye${shown ? "" : " off"}`;
    row.append(eye);

    if (isGroup) {
      row.append(button("Enter", `Enter ${item.name}`, () => onEnter(target.id)));
      row.append(button("Ungroup", `Ungroup ${item.name}`,
        () => run(() => api.post(`/api/compose/groups/${target.id}/ungroup`, {}))));
    }

    const move = direction => {
      const index = order.findIndex(other => targetKey(other) === targetKey(target));
      const destination = index + direction;
      if (destination < 0 || destination >= order.length) return;
      const arranged = order.filter(other => targetKey(other) !== targetKey(target));
      arranged.splice(destination, 0, target);
      const after = arranged[destination + 1];
      run(() => api.post("/api/compose/selection/reparent", {
        targets: [target], parent_id: context, before_id: after?.id || null,
      }));
    };
    const up = button("↑", `Move ${item.name} up`, () => move(1));
    const down = button("↓", `Move ${item.name} down`, () => move(-1));
    up.disabled = order.at(-1)?.id === target.id;
    down.disabled = order[0]?.id === target.id;
    row.append(up, down);
    row.append(button("Duplicate", `Duplicate ${item.name}`,
      () => run(() => api.post("/api/compose/selection/duplicate", { targets: [target] }))));

    const remove = button("Delete", `Delete ${item.name}`, () => {
      if (remove.dataset.armed !== "1") {
        remove.dataset.armed = "1";
        remove.textContent = "Confirm";
        return;
      }
      run(() => api.post("/api/compose/selection/delete", { targets: [target] }));
    });
    row.append(remove);
    container.append(row);
  }
}
