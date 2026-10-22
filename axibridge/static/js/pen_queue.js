// The pen's committed-edit queue: every edit to a committed pen layer lands
// through POST /api/layers/{id}/regenerate, one request at a time, in order.
// Split out of pen.js; the gesture code (pen.js, pen_edit.js) only calls
// queueRegenerate / kickRegen / whenIdle.

import { api } from "./api.js";
import { S, actions } from "./main.js";
import { gesture, redraw } from "./pen.js";

// Requests go out one at
// a time, in order, each carrying a SNAPSHOT of the params as the edit left
// them, so a quick insert-then-flip can never arrive flipped-then-inserted.
// Consecutive coalesced frames of one drag collapse into the latest (a drag
// is one undo step either way); a discrete edit is always its own request and
// its own undo step.

let regenQueue = []; // [{layerId, params, coalesce}] — coalesce: false | drag token
let regenBusy = false;
let syncOwed = false; // posted edits the local project hasn't been re-read after
let idleWaiters = [];

export function queueRegenerate(layer, { coalesce }) {
  const params = JSON.parse(JSON.stringify(layer.source.params));
  const last = regenQueue[regenQueue.length - 1];
  if (coalesce && last && last.coalesce === coalesce && last.layerId === layer.id) last.params = params;
  else regenQueue.push({ layerId: layer.id, params, coalesce });
  kickRegen();
}

export function kickRegen() {
  if (!regenBusy) drainRegen();
}

// The local project is AHEAD of the server while edits are queued, so it is
// only replaced by a fresh read when nothing is queued and no gesture is in
// flight; mid-run, only the ink repaints (refreshResolved). An edit made
// during that final read is put back on top of it (reapplyQueued).
async function drainRegen() {
  regenBusy = true;
  let ok = true;
  while (regenQueue.length || (syncOwed && !gesture)) {
    if (regenQueue.length) {
      const job = regenQueue.shift();
      try {
        await api.post(`/api/layers/${job.layerId}/regenerate`, { params: job.params, coalesce: job.coalesce });
      } catch (e) {
        actions.oops(e);
        regenQueue = []; // later snapshots build on the one that failed
        ok = false;
      }
      syncOwed = true;
      if (regenQueue.length || gesture) {
        if (job.coalesce) {
          try { await actions.refreshResolved(); } catch (e) { actions.oops(e); } // live drag repaint
        }
        continue;
      }
    }
    syncOwed = false;
    try {
      await actions.refreshProject();
      reapplyQueued();
      await actions.refreshResolved();
    } catch (e) { actions.oops(e); }
  }
  regenBusy = false;
  const waiters = idleWaiters;
  idleWaiters = [];
  for (const w of waiters) w(ok);
}

// Each queued job's params are the newest local state of its layer: lay them
// back over a just-read project so a refresh never erases a queued edit.
function reapplyQueued() {
  const layers = S.state?.project?.layers || [];
  for (const job of regenQueue) {
    const layer = layers.find((l) => l.id === job.layerId);
    if (layer) layer.source.params = JSON.parse(JSON.stringify(job.params));
  }
  if (regenQueue.length) redraw();
}

/** Resolves (true = every queued edit landed) once the queue is empty. */
export function whenIdle() {
  return regenBusy ? new Promise((r) => idleWaiters.push(r)) : Promise.resolve(true);
}
