// The canvas editor: the bed (300×218 mm machine frame) as an interactive
// SVG workspace. What you see is where it plots — layer geometry arrives
// RESOLVED from the server (transform+effects+occlusion already applied), so
// the picture is exactly what the pen will draw. During a drag we apply a
// client-side *delta* matrix to the layer's <g> for instant feedback, then
// commit delta∘transform to the server and re-fetch the resolve.
//
// View orientation is display-only: one outer <g> rotates the whole bed;
// pointer math goes through getScreenCTM().inverse(), so hit-testing and
// handles are orientation-agnostic. Geometry never changes.

const NS = "http://www.w3.org/2000/svg";

// ---- 2D affine helpers: m = [a, b, c, d, e, f] (SVG matrix order) ----------

export const I = [1, 0, 0, 1, 0, 0];

export function mul(m, n) { // m ∘ n  (apply n first, then m)
  return [
    m[0] * n[0] + m[2] * n[1],
    m[1] * n[0] + m[3] * n[1],
    m[0] * n[2] + m[2] * n[3],
    m[1] * n[2] + m[3] * n[3],
    m[0] * n[4] + m[2] * n[5] + m[4],
    m[1] * n[4] + m[3] * n[5] + m[5],
  ];
}
export const translate = (x, y) => [1, 0, 0, 1, x, y];
export const scale = (sx, sy) => [sx, 0, 0, sy, 0, 0];
export const rotate = (rad) => [Math.cos(rad), Math.sin(rad), -Math.sin(rad), Math.cos(rad), 0, 0];
export const matStr = (m) => `matrix(${m.map((v) => +v.toFixed(6)).join(" ")})`;
export const objToMat = (t) => [t.a, t.b, t.c, t.d, t.e, t.f];
export const matToObj = (m) => ({ a: m[0], b: m[1], c: m[2], d: m[3], e: m[4], f: m[5] });

function el(tag, attrs = {}) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

const HANDLE = 2.6; // handle half-size in bed mm (visual)

export class CanvasEditor {
  /**
   * @param svg     the #canvas <svg>
   * @param cb      callbacks: onSelect(ids), onTransform(ids, deltaMat),
   *                onGuideMove({x,y}), onDoubleClick(id)
   */
  constructor(svg, cb) {
    this.svg = svg;
    this.cb = cb;
    this.bed = { width: 300, height: 218 };
    this.layers = [];          // resolved layer payloads from /api/compose/resolved
    this.guide = null;         // {x,y,width,height}
    this.view = "portrait";
    this.mode = "schematic";   // | "ink"
    this.showTravel = false;
    this.showOrder = false;
    this.showGuide = true;
    this.plan = null;          // PlannedJob for travel overlay + playback
    this.selection = new Set();
    this.machinePos = null;
    this.machinePenDown = false;
    this.anim = null;
    this._drag = null;
    svg.addEventListener("pointerdown", (e) => this._onDown(e));
    svg.addEventListener("pointermove", (e) => this._onMove(e));
    svg.addEventListener("pointerup", (e) => this._onUp(e));
    svg.addEventListener("dblclick", (e) => this._onDbl(e));
  }

  setData({ layers, bed, guide, view, images }) {
    if (layers) this.layers = layers;
    if (bed) this.bed = bed;
    if (guide) this.guide = guide;
    if (view) this.view = view;
    if (images) this.images = images; // ghosted source/depth maps (preview only)
    this.selection = new Set([...this.selection].filter((id) => this.layers.some((l) => l.id === id)));
    this.render();
  }

  setPlan(plan) { this.plan = plan; this._renderTravel(); }
  setSelection(ids) { this.selection = new Set(ids); this._renderSelection(); }

  // -- coordinates -----------------------------------------------------------

  toBed(e) {
    const pt = this.svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const ctm = this.world.getScreenCTM();
    const p = pt.matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }

  // -- render ------------------------------------------------------------------

  render() {
    const { width: W, height: H } = this.bed;
    const pad = 8;
    const portrait = this.view === "portrait";
    this.svg.innerHTML = "";
    this.svg.setAttribute(
      "viewBox",
      portrait ? `${-pad} ${-pad} ${H + 2 * pad} ${W + 2 * pad}` : `${-pad} ${-pad} ${W + 2 * pad} ${H + 2 * pad}`
    );
    // display-only rotation: machine (0,0) sits top-right in portrait view
    this.world = el("g", portrait ? { transform: `translate(${H} 0) rotate(90)` } : {});
    this.svg.appendChild(this.world);

    this.world.appendChild(el("rect", { x: 0, y: 0, width: W, height: H, class: "bed-rect" }));
    this.world.appendChild(el("circle", { cx: 0, cy: 0, r: 1.4, class: "bed-origin" }));

    if (this.guide && this.showGuide) {
      this.guideEl = el("rect", {
        x: this.guide.x, y: this.guide.y,
        width: this.guide.width, height: this.guide.height,
        class: "guide-rect", "data-guide": "1",
      });
      this.world.appendChild(this.guideEl);
    }

    // ghosted image maps (depth maps / hatch sources) under the geometry
    for (const im of this.images || []) {
      const img = el("image", {
        href: im.href, x: im.x, y: im.y, width: im.width, height: im.height,
        class: "map-ghost", preserveAspectRatio: "none",
      });
      if (im.transform) img.setAttribute("transform", matStr(im.transform));
      this.world.appendChild(img);
    }

    this.layersGroup = el("g", {});
    this.world.appendChild(this.layersGroup);
    this.layerEls = {};
    let globalIdx = 0;
    const totalPaths = this.layers.reduce((n, l) => n + (l.visible ? l.paths.length : 0), 0);
    for (const layer of this.layers) {
      if (!layer.visible) continue;
      const g = el("g", { class: "layer", "data-id": layer.id });
      const ds = [];
      for (const p of layer.paths) {
        const d = "M " + p.points.map(([x, y]) => `${x.toFixed(3)} ${y.toFixed(3)}`).join(" L ");
        ds.push(d);
        const path = el("path", {
          d, fill: "none",
          stroke: layer.color,
          "stroke-linecap": "round", "stroke-linejoin": "round",
        });
        if (this.mode === "ink") {
          path.setAttribute("stroke-width", layer.line_diameter_mm);
          path.setAttribute("stroke-opacity", layer.opacity);
        } else {
          path.setAttribute("stroke-width", 0.35);
          if (this.showOrder) {
            path.setAttribute("stroke-opacity",
              (0.15 + 0.85 * (globalIdx / Math.max(totalPaths - 1, 1))).toFixed(3));
          }
        }
        globalIdx++;
        g.appendChild(path);
      }
      // one wide transparent hit path per layer — easy grabbing without a
      // bbox rect stealing clicks from layers underneath
      if (ds.length) {
        g.appendChild(el("path", { d: ds.join(" "), class: "layer-hit", "data-id": layer.id }));
      }
      this.layersGroup.appendChild(g);
      this.layerEls[layer.id] = g;
    }

    this.travelGroup = el("g", {});
    this.world.appendChild(this.travelGroup);
    this.overlay = el("g", {});
    this.world.appendChild(this.overlay);
    this.animMarker = el("circle", { r: 1.6, class: "anim-marker", visibility: "hidden" });
    this.machineMarker = el("circle", { r: 1.6, class: "machine-marker", visibility: "hidden" });
    this.world.appendChild(this.animMarker);
    this.world.appendChild(this.machineMarker);

    this._renderTravel();
    this._renderSelection();
    this.updateMachineMarker();
  }

  _renderTravel() {
    if (!this.travelGroup) return;
    this.travelGroup.innerHTML = "";
    if (!this.showTravel || !this.plan) return;
    for (const move of this.plan.moves) {
      if (move.pen_down) continue;
      this.travelGroup.appendChild(el("polyline", {
        points: move.points.map(([x, y]) => `${x},${y}`).join(" "),
        class: "travel-path",
      }));
    }
  }

  selectionBBox() {
    let xs = [], ys = [];
    for (const layer of this.layers) {
      if (!this.selection.has(layer.id) || !layer.visible) continue;
      for (const p of layer.paths) for (const [x, y] of p.points) { xs.push(x); ys.push(y); }
    }
    if (!xs.length) return null;
    return {
      x: Math.min(...xs), y: Math.min(...ys),
      w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys),
    };
  }

  _renderSelection() {
    if (!this.overlay) return;
    this.overlay.innerHTML = "";
    for (const g of Object.values(this.layerEls)) g.classList.remove("selected");
    const box = this.selectionBBox();
    if (!box) return;
    for (const id of this.selection) this.layerEls[id]?.classList.add("selected");
    const { x, y, w, h } = box;
    this.overlay.appendChild(el("rect", { x, y, width: w, height: h, class: "sel-box" }));
    const corners = [
      [x, y, "nw"], [x + w / 2, y, "n"], [x + w, y, "ne"],
      [x, y + h / 2, "w"], [x + w, y + h / 2, "e"],
      [x, y + h, "sw"], [x + w / 2, y + h, "s"], [x + w, y + h, "se"],
    ];
    for (const [hx, hy, dir] of corners) {
      this.overlay.appendChild(el("rect", {
        x: hx - HANDLE / 2, y: hy - HANDLE / 2, width: HANDLE, height: HANDLE,
        class: "handle", "data-handle": dir,
      }));
    }
    // rotate handle floats off the top edge (bed frame)
    this.overlay.appendChild(el("line", {
      x1: x + w / 2, y1: y, x2: x + w / 2, y2: y - 7, class: "sel-box",
    }));
    this.overlay.appendChild(el("circle", {
      cx: x + w / 2, cy: y - 7, r: HANDLE / 1.4, class: "handle rot", "data-handle": "rotate",
    }));
    this._selBox = box;
  }

  updateMachineMarker() {
    if (!this.machineMarker) return;
    if (this.machinePos) {
      this.machineMarker.setAttribute("cx", this.machinePos[0]);
      this.machineMarker.setAttribute("cy", this.machinePos[1]);
      this.machineMarker.setAttribute("r", this.machinePenDown ? 1.0 : 1.7);
      this.machineMarker.setAttribute("visibility", "visible");
    } else {
      this.machineMarker.setAttribute("visibility", "hidden");
    }
  }

  setMachinePos(pos, penDown) {
    this.machinePos = pos;
    this.machinePenDown = penDown;
    this.updateMachineMarker();
  }

  // -- interaction --------------------------------------------------------------

  _onDown(e) {
    if (this.anim) return; // playback owns the canvas
    const p = this.toBed(e);
    const handle = e.target.getAttribute?.("data-handle");
    const layerId = e.target.getAttribute?.("data-id");
    this.svg.setPointerCapture(e.pointerId);

    if (handle && this.selection.size) {
      const box = this._selBox;
      const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
      this._drag = handle === "rotate"
        ? { kind: "rotate", start: p, center: { x: cx, y: cy }, ids: [...this.selection] }
        : {
            kind: "scale", start: p, dir: handle, ids: [...this.selection],
            anchor: {
              x: handle.includes("w") ? box.x + box.w : handle.includes("e") ? box.x : cx,
              y: handle.includes("n") ? box.y + box.h : handle.includes("s") ? box.y : cy,
            },
          };
      return;
    }
    if (e.target.getAttribute?.("data-guide")) {
      this._drag = { kind: "guide", start: p, orig: { ...this.guide } };
      return;
    }
    if (layerId) {
      if (e.shiftKey) {
        this.selection.has(layerId) ? this.selection.delete(layerId) : this.selection.add(layerId);
        this._renderSelection();
        this.cb.onSelect([...this.selection]);
        this._drag = { kind: "move", start: p, ids: [...this.selection] };
        return;
      }
      // Drag moves the CURRENT selection, whatever geometry sits under the
      // pointer — overlapping layers can't steal the drag. Selection only
      // changes on a clean click (pointerup without movement, see _onUp).
      if (!this.selection.size) {
        this.selection = new Set([layerId]);
        this._renderSelection();
        this.cb.onSelect([...this.selection]);
      }
      this._drag = { kind: "move", start: p, ids: [...this.selection], clickTarget: layerId };
      return;
    }
    // empty bed: clear selection, start a marquee
    if (!e.shiftKey) {
      this.selection.clear();
      this._renderSelection();
      this.cb.onSelect([]);
    }
    this._drag = { kind: "marquee", start: p };
    this._marqueeEl = el("rect", { class: "marquee" });
    this.overlay.appendChild(this._marqueeEl);
  }

  _onMove(e) {
    if (!this._drag) return;
    const d = this._drag;
    const p = this.toBed(e);

    if (d.kind === "move") {
      // dead zone: a twitch while clicking must not commit a micro-translate
      if (!d.moved && Math.hypot(p.x - d.start.x, p.y - d.start.y) < 0.3) return;
      d.moved = true;
      d.delta = translate(p.x - d.start.x, p.y - d.start.y);
      this._applyDelta(d.ids, d.delta);
    } else if (d.kind === "scale") {
      const sx0 = d.start.x - d.anchor.x, sy0 = d.start.y - d.anchor.y;
      let sx = Math.abs(sx0) > 0.5 && "ew".split("").some((c) => d.dir.includes(c))
        ? (p.x - d.anchor.x) / sx0 : 1;
      let sy = Math.abs(sy0) > 0.5 && "ns".split("").some((c) => d.dir.includes(c))
        ? (p.y - d.anchor.y) / sy0 : 1;
      if (e.shiftKey && d.dir.length === 2) { // corner + shift = uniform
        const s = Math.max(Math.abs(sx), Math.abs(sy));
        sx = Math.sign(sx || 1) * s; sy = Math.sign(sy || 1) * s;
      }
      sx = Math.abs(sx) < 0.02 ? 0.02 * Math.sign(sx || 1) : sx;
      sy = Math.abs(sy) < 0.02 ? 0.02 * Math.sign(sy || 1) : sy;
      d.delta = mul(translate(d.anchor.x, d.anchor.y), mul(scale(sx, sy), translate(-d.anchor.x, -d.anchor.y)));
      this._applyDelta(d.ids, d.delta);
    } else if (d.kind === "rotate") {
      const a0 = Math.atan2(d.start.y - d.center.y, d.start.x - d.center.x);
      const a1 = Math.atan2(p.y - d.center.y, p.x - d.center.x);
      d.delta = mul(translate(d.center.x, d.center.y), mul(rotate(a1 - a0), translate(-d.center.x, -d.center.y)));
      this._applyDelta(d.ids, d.delta);
    } else if (d.kind === "guide") {
      const g = this.guide;
      g.x = Math.round(d.orig.x + (p.x - d.start.x));
      g.y = Math.round(d.orig.y + (p.y - d.start.y));
      this.guideEl.setAttribute("x", g.x);
      this.guideEl.setAttribute("y", g.y);
    } else if (d.kind === "marquee") {
      const x = Math.min(d.start.x, p.x), y = Math.min(d.start.y, p.y);
      const w = Math.abs(p.x - d.start.x), h = Math.abs(p.y - d.start.y);
      Object.entries({ x, y, width: w, height: h }).forEach(([k, v]) => this._marqueeEl.setAttribute(k, v));
      d.rect = { x, y, w, h };
    }
  }

  _applyDelta(ids, delta) {
    for (const id of ids) this.layerEls[id]?.setAttribute("transform", matStr(delta));
    this.overlay.setAttribute("transform", matStr(delta)); // selection box rides along
  }

  _onUp(e) {
    const d = this._drag;
    this._drag = null;
    if (!d) return;
    if (d.kind === "marquee") {
      this._marqueeEl?.remove();
      if (d.rect && (d.rect.w > 1 || d.rect.h > 1)) {
        const hit = this.layers.filter((l) =>
          l.visible && l.paths.some((p) => p.points.some(([x, y]) =>
            x >= d.rect.x && x <= d.rect.x + d.rect.w && y >= d.rect.y && y <= d.rect.y + d.rect.h)));
        this.selection = new Set(hit.map((l) => l.id));
        this._renderSelection();
        this.cb.onSelect([...this.selection]);
      }
      return;
    }
    if (d.kind === "guide") {
      this.cb.onGuideMove({ x: this.guide.x, y: this.guide.y });
      return;
    }
    if (d.kind === "move" && !d.moved && d.clickTarget) {
      // clean click: select the layer under the pointer
      this.selection = new Set([d.clickTarget]);
      this._renderSelection();
      this.cb.onSelect([...this.selection]);
      return;
    }
    if (d.delta) {
      this.overlay.removeAttribute("transform");
      this.cb.onTransform(d.ids, d.delta); // server commit; refresh resets <g>s
    }
  }

  _onDbl(e) {
    const layerId = e.target.getAttribute?.("data-id");
    if (layerId) this.cb.onDoubleClick(layerId);
  }

  // -- playback: replay the planned job on its estimated clock --------------------

  startAnimation(speed, onDone) {
    if (!this.plan || !this.plan.moves.length) return;
    this.stopAnimation();
    this.layersGroup.setAttribute("opacity", 0.12);
    this.travelGroup.setAttribute("opacity", 0.3);
    this.animGroup = el("g", {});
    this.world.insertBefore(this.animGroup, this.animMarker);
    const cum = [];
    let t = 0;
    for (const m of this.plan.moves) { cum.push([t, t + m.duration]); t += m.duration; }
    this.anim = { speed, t0: performance.now(), cum, idx: 0, onDone, curEl: null };
    this.animMarker.setAttribute("visibility", "visible");
    this._tick();
  }

  _moveColor(move) {
    const layer = this.layers[ (move.layer_id ?? 1) - 1 ];
    return layer ? layer.color : "var(--sheet-ink)"; // marks land on the white sheet, not the dark chrome
  }

  _tick() {
    if (!this.anim) return;
    const a = this.anim;
    const simT = ((performance.now() - a.t0) / 1000) * a.speed;
    const moves = this.plan.moves;
    while (a.idx < moves.length && simT >= a.cum[a.idx][1]) {
      this._finishMove(a.idx);
      a.idx++;
      a.curEl = null;
    }
    if (a.idx >= moves.length) { this.stopAnimation(true); return; }
    const move = moves[a.idx];
    const [start, end] = a.cum[a.idx];
    const frac = move.duration > 0 ? Math.min(Math.max((simT - start) / (end - start), 0), 1) : 1;
    const pos = pointAlong(move.points, frac);
    this.animMarker.setAttribute("cx", pos[0]);
    this.animMarker.setAttribute("cy", pos[1]);
    this.animMarker.setAttribute("r", move.pen_down ? 1.0 : 1.7);
    if (move.pen_down) {
      if (!a.curEl) {
        a.curEl = el("polyline", {
          fill: "none", stroke: this._moveColor(move), "stroke-width": 0.4,
          "stroke-linecap": "round",
        });
        this.animGroup.appendChild(a.curEl);
      }
      a.curEl.setAttribute("points", sliceAlong(move.points, frac).map(([x, y]) => `${x},${y}`).join(" "));
    }
    this.animRaf = requestAnimationFrame(() => this._tick());
  }

  _finishMove(idx) {
    const move = this.plan.moves[idx];
    if (!move.pen_down) return;
    const elp = this.anim?.curEl || el("polyline", {
      fill: "none", stroke: this._moveColor(move), "stroke-width": 0.4, "stroke-linecap": "round",
    });
    elp.setAttribute("points", move.points.map(([x, y]) => `${x},${y}`).join(" "));
    if (!elp.parentNode) this.animGroup.appendChild(elp);
  }

  stopAnimation(finished = false) {
    if (this.animRaf) cancelAnimationFrame(this.animRaf);
    this.animRaf = null;
    const done = this.anim?.onDone;
    this.anim = null;
    this.animGroup?.remove();
    this.animGroup = null;
    this.layersGroup?.removeAttribute("opacity");
    this.travelGroup?.removeAttribute("opacity");
    this.animMarker?.setAttribute("visibility", "hidden");
    if (finished && done) done();
  }

  get animating() { return !!this.anim; }
}

// -- polyline walking (shared with playback) -----------------------------------

function lengths(points) {
  const out = [];
  for (let i = 1; i < points.length; i++) {
    out.push(Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]));
  }
  return out;
}

export function pointAlong(points, frac) {
  if (points.length === 1) return points[0];
  const segs = lengths(points);
  const total = segs.reduce((a, b) => a + b, 0);
  let target = frac * total;
  for (let i = 0; i < segs.length; i++) {
    if (target <= segs[i] || i === segs.length - 1) {
      const t = segs[i] > 0 ? Math.min(target / segs[i], 1) : 1;
      const [a, b] = [points[i], points[i + 1]];
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    }
    target -= segs[i];
  }
  return points[points.length - 1];
}

export function sliceAlong(points, frac) {
  if (frac >= 1 || points.length === 1) return points;
  const segs = lengths(points);
  const total = segs.reduce((a, b) => a + b, 0);
  let target = frac * total;
  const out = [points[0]];
  for (let i = 0; i < segs.length; i++) {
    if (target <= segs[i]) {
      const t = segs[i] > 0 ? target / segs[i] : 1;
      const [a, b] = [points[i], points[i + 1]];
      out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
      return out;
    }
    out.push(points[i + 1]);
    target -= segs[i];
  }
  return out;
}
