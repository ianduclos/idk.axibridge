// The pen's knife mode (pen v2 K1): drag a straight cut line across the
// active pen layer; on release every subpath it crosses is cut there (an
// open line splits, a closed one opens) and the pieces replace it — one
// regenerate, so one undo step. Shift snaps the cut's direction to 15°.
//
// pen.js owns the pointer dispatch and calls startKnife / moveKnife /
// finishKnife for a "knife" gesture; the overlay draws knifeView().

import { actions } from "./main.js";
import { DRAG_PX, activeLayer, redraw } from "./pen.js";
import { knife, knifeCrossings, snapAngle } from "./pen_ops.js";
import { queueRegenerate } from "./pen_queue.js";
import { bedSubpaths, setBedSubpaths } from "./pen_space.js";

/** The knife cuts pen layers only (a shape or brush layer has no lines to cut). */
function penLayer() {
  const l = activeLayer();
  return l?.source?.type === "generator" && l.source.generator === "pen" ? l : null;
}

/** A new knife gesture from bed-mm (x, y). @param {PointerEvent} e */
export function startKnife(x, y, e) {
  return { kind: "knife", a: [x, y], to: [x, y], shift: e.shiftKey, moved: false,
           downScreen: { x: e.clientX, y: e.clientY } };
}

/** @param {any} g @param {number} x @param {number} y @param {PointerEvent} e */
export function moveKnife(g, x, y, e) {
  g.to = [x, y];
  g.shift = e.shiftKey;
  if (Math.hypot(e.clientX - g.downScreen.x, e.clientY - g.downScreen.y) > DRAG_PX) g.moved = true;
}

/** The cut's far end: the pointer, or with Shift its direction snapped to 15°. */
function cutEnd(g) {
  if (!g.shift) return g.to;
  const [dx, dy] = snapAngle(g.to[0] - g.a[0], g.to[1] - g.a[1], 15);
  return [g.a[0] + dx, g.a[1] + dy];
}

/** What the overlay draws for a knife gesture: the cut line and where it
 *  crosses the active pen layer — the points the release will cut at. */
export function knifeView(g) {
  if (g?.kind !== "knife" || !g.moved) return null;
  const b = cutEnd(g);
  const subpaths = bedSubpaths(penLayer());
  return { a: g.a, b, dots: subpaths.flatMap((sp) => knifeCrossings(sp, g.a, b)) };
}

/** The knife was released: cut every subpath it crosses. @param {PointerEvent} e */
export function finishKnife(g, e) {
  g.shift = e.shiftKey; // the cut follows Shift as it is at release
  const layer = penLayer();
  if (!layer) {
    actions.hint("Select a pen layer to cut");
    redraw();
    return;
  }
  if (!g.moved) { redraw(); return; }
  const b = cutEnd(g);
  let cut = false;
  // the cut is drawn on the bed: it cuts the lines where they are seen
  const subpaths = bedSubpaths(layer).flatMap((sp) => {
    if (!knifeCrossings(sp, g.a, b).length) return [sp];
    cut = true;
    // the pieces keep the cubics they had: a curvature line's pieces become
    // Bézier, since re-deriving their arms would reshape what was cut
    return knife(sp, g.a, b).map((p) => ({ ...p, kind: "bezier" }));
  });
  if (cut) {
    setBedSubpaths(layer, subpaths);
    queueRegenerate(layer, { coalesce: false }); // one cut = one undo step
  }
  redraw();
}
