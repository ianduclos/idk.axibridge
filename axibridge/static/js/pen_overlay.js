// The pen tool's on-canvas overlay: committed anchors and arms of the active
// layer, the pending subpath, and the live previews of the gesture in flight.
// Pure rendering — pen.js owns all state and hit testing, and hands it here
// through the one entry point, renderPenOverlay(state).
//
// Everything is drawn in bed mm inside editor.world, but glyphs are sized in
// SCREEN pixels: a glyph's mm size is PX / editor.pxPerMm(), so points stay
// the same size at any zoom (pen.js re-renders on every view change), and
// strokes use vector-effect: non-scaling-stroke with px widths (style.css).
// Point shape shows the point type: a corner is a square, a smooth or
// symmetric point is a circle (symmetric filled, smooth hollow).

import { classifyJoin } from "./pen_ops.js";

const NS = "http://www.w3.org/2000/svg";

/** Screen-pixel glyph sizes: anchor width/diameter, the pending subpath's
 *  first anchor (the close target), an arm knob's diameter, and the gap
 *  between a selected point and its ring. */
export const PX = { anchor: 7, anchorFirst: 9, knob: 5, ringGap: 3 };

/**
 * @typedef {{x:number, y:number, in_handle:number[]|null, out_handle:number[]|null, join?:string}} Anchor
 * @typedef {{kind:"place", anchor:Anchor} | {kind:"close", first:Anchor} | null} GestureView
 *   the previewable part of the gesture in flight: the anchor being placed
 *   (as it would commit), or the first anchor carrying the closing segment's
 *   tentative in-arm. Any other gesture renders nothing extra.
 * @typedef {{
 *   editor: any,
 *   layerSubpaths: {anchors: Anchor[], closed?: boolean, kind?: string}[] | null,
 *   pending: Anchor[],
 *   gesture: GestureView,
 *   hover: number[] | null,
 *   subtract: boolean,
 *   selected?: {si: number, ai: number} | null,
 *   continuing?: boolean,
 *   curvature?: boolean,
 *   sketch?: number[][] | null,
 * }} PenOverlayState
 *   selected: the committed point J / Delete act on — drawn with a ring.
 *   continuing: pending[0] is an existing line's end being continued, not a
 *   close target, so it is drawn at the ordinary point size.
 *   curvature: the pending path is a curvature-pen path — its arms are
 *   derived, so they are not drawn (nor are a committed curvature
 *   subpath's: `kind: "curvature"`).
 *   sketch: the freehand stroke being dragged in sketch mode (bed mm
 *   samples), drawn as a thin polyline until it is fitted.
 */

/** @type {SVGGElement | null} */
let overlay = null; // persistent <g> appended to editor.world (NOT canvas.js's
                    // own this.overlay, which _renderSelection() repopulates)

function svgEl(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

function ensureOverlay(editor) {
  if (overlay && overlay.isConnected) return overlay;
  overlay = /** @type {SVGGElement} */ (svgEl("g", { class: "pen-overlay" }));
  editor.world.appendChild(overlay);
  return overlay;
}

// One cubic segment between two anchors — SVG draws it directly (native "C"
// commands), no need to flatten client-side like the server does for the
// real Path geometry.
function segmentD(a, b) {
  const p1 = a.out_handle ? [a.x + a.out_handle[0], a.y + a.out_handle[1]] : [a.x, a.y];
  const p2 = b.in_handle ? [b.x + b.in_handle[0], b.y + b.in_handle[1]] : [b.x, b.y];
  return `C ${p1[0]},${p1[1]} ${p2[0]},${p2[1]} ${b.x},${b.y}`;
}

// The already-placed segments of the pending subpath. This is what makes
// the shape visible AS you place each anchor, not just once it commits.
function pendingSegmentsD(anchors) {
  if (anchors.length < 2) return null;
  let d = `M ${anchors[0].x},${anchors[0].y}`;
  for (let i = 0; i < anchors.length - 1; i++) d += ` ${segmentD(anchors[i], anchors[i + 1])}`;
  return d;
}

/**
 * Render the overlay for `state`, or clear it when `state` is null (pen
 * mode off). The single entry point: later features (a selected-anchor
 * ring, the knife preview) extend the state object, not the API.
 * @param {PenOverlayState | null} state
 */
export function renderPenOverlay(state) {
  if (!state) { if (overlay) overlay.innerHTML = ""; return; }
  const { editor, layerSubpaths, pending, gesture, hover, subtract, selected, continuing, curvature,
          sketch } = state;
  const g = ensureOverlay(editor);
  g.innerHTML = "";
  g.classList.toggle("subtracting", subtract); // pending paths render rust

  const mm = 1 / Math.max(editor.pxPerMm(), 1e-6); // one screen px, in bed mm
  const knobR = (PX.knob / 2) * mm;

  const drawArm = (a, h) => {
    const hx = a.x + h[0], hy = a.y + h[1];
    g.appendChild(svgEl("line", { x1: a.x, y1: a.y, x2: hx, y2: hy, class: "pen-handle-line" }));
    g.appendChild(svgEl("circle", { cx: hx, cy: hy, r: knobR, class: "pen-handle-knob" }));
  };
  const drawArms = (a) => {
    if (a.out_handle) drawArm(a, a.out_handle);
    if (a.in_handle) drawArm(a, a.in_handle);
  };
  // corner → square; smooth / symmetric → circle (CSS fills symmetric,
  // leaves smooth hollow)
  const drawAnchor = (a, px, cls) => {
    const join = classifyJoin(a);
    const size = px * mm;
    const attrs = join === "corner"
      ? { x: a.x - size / 2, y: a.y - size / 2, width: size, height: size }
      : { cx: a.x, cy: a.y, r: size / 2 };
    g.appendChild(svgEl(join === "corner" ? "rect" : "circle", { ...attrs, class: `${cls} ${join}` }));
  };

  // committed anchors/arms of the active (selected) layer — the overlay that
  // makes re-editing possible
  for (const sp of layerSubpaths || []) {
    if (sp.kind !== "curvature") for (const a of sp.anchors) drawArms(a);
    for (const a of sp.anchors) drawAnchor(a, PX.anchor, "pen-anchor");
  }
  const sel = selected ? layerSubpaths?.[selected.si]?.anchors[selected.ai] : null;
  if (sel) {
    g.appendChild(svgEl("circle", { cx: sel.x, cy: sel.y, r: (PX.anchor / 2 + PX.ringGap) * mm,
                                    class: "pen-selected-ring" }));
  }

  // the current uncommitted subpath: the segments placed so far, then
  // anchors/arms on top
  const pendingD = pendingSegmentsD(pending);
  if (pendingD) g.appendChild(svgEl("path", { d: pendingD, class: "pen-pending-path", fill: "none" }));
  if (!curvature) for (const a of pending) drawArms(a);
  pending.forEach((a, i) => drawAnchor(a, i === 0 && !continuing ? PX.anchorFirst : PX.anchor,
                                       "pen-pending-anchor"));

  if (sketch && sketch.length >= 2) {
    g.appendChild(svgEl("polyline", { points: sketch.map((p) => `${p[0]},${p[1]}`).join(" "),
                                      class: "pen-sketch-path" }));
  }

  if (gesture?.kind === "place") {
    // live preview of the anchor being placed: the actual curve segment from
    // the last placed anchor (with exactly the handles commit will use),
    // plus its own arm guide
    const t = gesture.anchor;
    if (pending.length) {
      const last = pending[pending.length - 1];
      g.appendChild(svgEl("path", {
        d: `M ${last.x},${last.y} ${segmentD(last, t)}`, class: "pen-pending-path", fill: "none",
      }));
    }
    if (t.out_handle && !curvature) drawArm(t, t.out_handle);
    drawAnchor(t, PX.anchor, "pen-pending-anchor");
  } else if (gesture?.kind === "close" && pending.length >= 2) {
    // live preview of the closing segment (last anchor → first anchor),
    // curved by the first anchor's tentative in-arm — the first anchor's OWN
    // out-arm (first segment) is left as-is, so only this one spline moves
    const first = gesture.first;
    const last = pending[pending.length - 1];
    g.appendChild(svgEl("path", {
      d: `M ${last.x},${last.y} ${segmentD(last, first)}`, class: "pen-pending-path", fill: "none",
    }));
    if (first.in_handle && !curvature) drawArm(first, first.in_handle);
  } else if (!gesture && pending.length && hover) {
    // hover rubber-band: preview the next segment from the last pending
    // anchor to the pointer, shaped by that anchor's own out-arm
    const last = pending[pending.length - 1];
    const p1 = last.out_handle ? [last.x + last.out_handle[0], last.y + last.out_handle[1]] : [last.x, last.y];
    g.appendChild(svgEl("path", {
      d: `M ${last.x},${last.y} C ${p1[0]},${p1[1]} ${hover[0]},${hover[1]} ${hover[0]},${hover[1]}`,
      class: "pen-rubber-band", fill: "none",
    }));
  }
}
