// pen_space.js — the pen works where the ink is seen: in BED mm.
//
// A layer's pen params (`subpaths`: anchors + relative arms) are in the
// layer's LOCAL frame; the compositor places them with the layer's transform,
// inside its groups' (compose.py `transform(source)`, groups.placed_project).
// Every pen gesture — the overlay, hit tests, placing, bending, the knife,
// sketch fits, continue/join — reads and writes subpaths through this module,
// so none of them ever sees a local coordinate:
//
//   bedSubpaths(layer)          READ: the layer's subpaths placed on the bed.
//                               Frozen views, cached per local subpath, so the
//                               same subpath reads as the same object (edits
//                               tell untouched lines by identity) and nothing
//                               can edit a view in place behind this module.
//   setBedSubpaths(layer, sps)  WRITE: bed subpaths back into the local
//                               project; a view read here and handed back
//                               unchanged keeps its exact local original.
//   toLocal(layer, sps)         the same mapping for a payload sent directly
//                               (commitPenSubpath's append / shape op).
//
// A layer whose placement cannot be inverted (squashed flat) can be drawn but
// not edited: `editable` says so, and the write side refuses it.

import { S } from "./main.js";
import { invertAffine, mapSubpath, mulAffine } from "./pen_ops.js";

const IDENTITY = { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 };

/** The layer's placement on the bed: its groups' transforms (outermost
 *  first), then its own — groups.placed_project for a generator layer. */
export function placement(layer) {
  const groups = new Map((S.state?.project?.groups || []).map((g) => [g.id, g]));
  let m = layer?.transform || IDENTITY;
  const seen = new Set();
  for (let gid = layer?.group_id; gid && !seen.has(gid); gid = groups.get(gid)?.parent_id) {
    seen.add(gid);
    const g = groups.get(gid);
    if (!g) break;
    m = mulAffine(g.transform || IDENTITY, m);
  }
  return m;
}

/** Whether the pen can edit this layer: its placement can be undone. */
export const editable = (layer) => !!invertAffine(placement(layer));

const keyOf = (m) => `${m.a},${m.b},${m.c},${m.d},${m.e},${m.f}`;

// local subpath → {key, view}; view → {key, local}. Weak: a refreshed
// project's new objects simply miss and are mapped afresh.
const views = new WeakMap();
const locals = new WeakMap();

function freeze(sp) {
  for (const a of sp.anchors) {
    if (a.in_handle) Object.freeze(a.in_handle);
    if (a.out_handle) Object.freeze(a.out_handle);
    Object.freeze(a);
  }
  Object.freeze(sp.anchors);
  return Object.freeze(sp);
}

function link(local, view, key) {
  views.set(local, { key, view });
  locals.set(view, { key, local });
  return view;
}

/** READ: the layer's subpaths placed on the bed (a new array of cached,
 *  frozen views). No layer → []. */
export function bedSubpaths(layer) {
  const subs = layer?.source?.params?.subpaths || [];
  if (!subs.length) return [];
  const m = placement(layer);
  const key = keyOf(m);
  return subs.map((sp) => {
    const v = views.get(sp);
    return v && v.key === key ? v.view : link(sp, freeze(mapSubpath(sp, m)), key);
  });
}

/** Bed subpaths in the layer's local frame — null when the layer is squashed
 *  flat. A view that came from bedSubpaths returns its own local original. */
export function toLocal(layer, subpaths) {
  const m = placement(layer);
  const inv = invertAffine(m);
  if (!inv) return null;
  const key = keyOf(m);
  return subpaths.map((sp) => {
    const l = locals.get(sp);
    if (l && l.key === key) return l.local;
    const local = mapSubpath(sp, inv);
    // what was written reads back exactly as written (no round-trip error)
    link(local, freeze(mapSubpath(sp, IDENTITY)), key);
    return local;
  });
}

/** WRITE: replace the layer's subpaths (given in bed mm) on the local
 *  project. Throws on a layer squashed flat — callers only edit layers
 *  that `editable` allows. */
export function setBedSubpaths(layer, subpaths) {
  const local = toLocal(layer, subpaths);
  if (!local) throw new Error("this layer is flattened — the pen can't edit it");
  layer.source.params.subpaths = local;
}
