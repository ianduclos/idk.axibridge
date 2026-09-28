// Person ownership and requested-detail polygons in canonical source coordinates.
const NS = 'http://www.w3.org/2000/svg';
const copy = value => JSON.parse(JSON.stringify(value));
const clamp = value => Math.max(0, Math.min(1, value));
function node(tag, attrs) {
  const el = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
  return el;
}

export class DetailRegions {
  constructor(svg, onChange, onSelect) {
    this.svg = svg; this.onChange = onChange; this.onSelect = onSelect;
    this.people = []; this.details = []; this.mode = 'people'; this.selected = -1;
    this.width = 1000; this.height = 1000; this.url = ''; this.epoch = 0;
    this.active = false; this.gesture = null; this.drawing = null;
    svg.addEventListener('pointerdown', e => this.down(e));
    svg.addEventListener('pointermove', e => this.move(e));
    svg.addEventListener('pointerup', () => this.finishGesture());
    svg.addEventListener('pointercancel', () => this.cancel());
  }
  setImage(url) {
    const epoch = ++this.epoch; this.url = url; this.draw();
    if (!url) return;
    const image = new Image();
    image.onload = () => {
      if (this.epoch !== epoch) return;
      this.width = image.naturalWidth; this.height = image.naturalHeight; this.draw();
    };
    image.src = url;
  }
  setMode(mode, selected) { this.mode = mode; this.selected = selected; this.active = mode !== 'faces'; this.drawing = null; this.draw(); }
  setData(people, details, selected = this.selected) {
    this.people = copy(people); this.details = copy(details); this.selected = selected; this.draw();
  }
  get items() { return this.mode === 'people' ? this.people : this.details; }
  point(e) {
    const pt = this.svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    const p = pt.matrixTransform(this.svg.getScreenCTM().inverse());
    return [clamp(p.x / this.width), clamp(p.y / this.height)];
  }
  beginPolygon() { if (this.selected >= 0 && !this.disabled) { this.drawing = []; this.draw(); } }
  endPolygon() {
    if (!this.drawing) return false;
    if (this.drawing.length < 3) return false;
    this.items[this.selected].polygon = this.drawing; this.drawing = null;
    this.onChange(copy(this.people), copy(this.details)); this.draw(); return true;
  }
  down(e) {
    if (!this.active || this.disabled || e.button !== 0) return;
    if (this.drawing) { this.drawing.push(this.point(e)); this.draw(); e.preventDefault(); return; }
    const index = Number(e.target.dataset.index);
    if (!Number.isInteger(index) || !this.items[index]) return;
    this.selected = index; this.onSelect(index);
    this.gesture = { before: copy(this.items[index].polygon), start: this.point(e), vertex: e.target.dataset.vertex };
    this.svg.setPointerCapture(e.pointerId); e.preventDefault();
  }
  move(e) {
    if (!this.gesture) return;
    const polygon = this.items[this.selected].polygon, pt = this.point(e);
    const vertex = Number(this.gesture.vertex);
    if (this.gesture.vertex !== undefined && Number.isInteger(vertex)) polygon[vertex] = pt;
    else {
      const dx = pt[0] - this.gesture.start[0], dy = pt[1] - this.gesture.start[1];
      const xs = this.gesture.before.map(p => p[0]), ys = this.gesture.before.map(p => p[1]);
      const safeDx = Math.max(-Math.min(...xs), Math.min(1 - Math.max(...xs), dx));
      const safeDy = Math.max(-Math.min(...ys), Math.min(1 - Math.max(...ys), dy));
      this.items[this.selected].polygon = this.gesture.before.map(p => [p[0] + safeDx, p[1] + safeDy]);
    }
    this.draw();
  }
  finishGesture() {
    if (!this.gesture) return;
    this.gesture = null; this.onChange(copy(this.people), copy(this.details));
  }
  cancel() {
    if (this.drawing) { this.drawing = null; this.draw(); return true; }
    if (!this.gesture) return false;
    this.items[this.selected].polygon = this.gesture.before;
    this.gesture = null; this.draw(); return true;
  }
  draw() {
    if (!this.active) return;
    const w = this.width, h = this.height;
    this.svg.setAttribute('viewBox', `0 0 ${w} ${h}`); this.svg.replaceChildren();
    if (this.url) this.svg.append(node('image', { href: this.url, width: w, height: h }));
    this.items.forEach((item, index) => {
      if (!item.polygon?.length) return;
      const points = item.polygon.map(([x,y]) => `${x*w},${y*h}`).join(' ');
      this.svg.append(node('polygon', { points, 'data-index':index,
        class:`linedraw-region ${this.mode} ${index === this.selected ? 'selected' : ''}`,
        opacity:item.enabled === false ? .35 : 1 }));
      if (index === this.selected) item.polygon.forEach(([x,y], vertex) => this.svg.append(node('circle', {
        cx:x*w, cy:y*h, r:Math.max(w,h)*.012, 'data-index':index, 'data-vertex':vertex,
        class:'linedraw-region-handle',
      })));
    });
    if (this.drawing?.length) this.svg.append(node('polyline', {
      points:this.drawing.map(([x,y]) => `${x*w},${y*h}`).join(' '),
      class:'linedraw-region in-progress',
    }));
  }
}
