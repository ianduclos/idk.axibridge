// Canonical image coordinates: editing never depends on paper rotation or scale.
const NS = 'http://www.w3.org/2000/svg';
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const copy = value => JSON.parse(JSON.stringify(value));
function node(tag, attrs) {
  const el = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
  return el;
}
export class FaceRegions {
  constructor(svg, onChange, onSelect) {
    this.svg = svg; this.onChange = onChange; this.onSelect = onSelect;
    this.faces = []; this.selected = -1; this.width = 1000; this.height = 1000;
    this.gesture = null; this.url = ''; this.imageEpoch = 0; this.active = true;
    svg.addEventListener('pointerdown', e => this.down(e));
    svg.addEventListener('pointermove', e => this.move(e));
    svg.addEventListener('pointerup', () => this.finish());
    svg.addEventListener('pointercancel', () => this.cancel());
  }
  setImage(url) {
    const epoch = ++this.imageEpoch;
    this.url = url; this.draw();
    if (!url) return;
    const image = new Image();
    image.onload = () => {
      if (epoch !== this.imageEpoch) return;
      this.width = image.naturalWidth; this.height = image.naturalHeight; this.draw();
    };
    image.src = url;
  }
  setFaces(faces, selected = this.selected) {
    this.faces = copy(faces); this.selected = Math.min(selected, faces.length - 1); this.draw();
  }
  setActive(active) { this.active = active; if (active) this.draw(); }
  point(e) {
    const pt = this.svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    const p = pt.matrixTransform(this.svg.getScreenCTM().inverse());
    return { x: p.x / this.width, y: p.y / this.height };
  }
  down(e) {
    if (e.button !== 0 || this.disabled || !this.active) return;
    const index = Number(e.target.dataset.index);
    if (!Number.isInteger(index) || !this.faces[index]) return;
    this.selected = index;
    this.gesture = { start: this.point(e), faces: copy(this.faces), action: e.target.dataset.action };
    this.svg.setPointerCapture(e.pointerId); this.onSelect(index); e.preventDefault();
  }
  move(e) {
    if (!this.gesture) return;
    const pt = this.point(e), before = this.gesture.faces[this.selected];
    const face = this.faces[this.selected];
    if (this.gesture.action === 'resize') {
      face.rx = clamp(Math.abs(pt.x - before.cx), .005, .5);
      face.ry = clamp(Math.abs(pt.y - before.cy), .005, .5);
    } else {
      face.cx = clamp(before.cx + pt.x - this.gesture.start.x, 0, 1);
      face.cy = clamp(before.cy + pt.y - this.gesture.start.y, 0, 1);
    }
    face.origin = 'manual'; this.draw();
  }
  finish() {
    if (!this.gesture) return;
    this.gesture = null; this.onChange(copy(this.faces));
  }
  cancel() {
    if (!this.gesture) return false;
    this.faces = this.gesture.faces; this.gesture = null; this.draw(); return true;
  }
  draw() {
    if (!this.active) return;
    const w = this.width, h = this.height;
    this.svg.setAttribute('viewBox', `0 0 ${w} ${h}`); this.svg.replaceChildren();
    if (this.url) this.svg.append(node('image', { href: this.url, width: w, height: h }));
    this.faces.forEach((f, i) => {
      this.svg.append(node('ellipse', { cx: f.cx*w, cy: f.cy*h, rx: f.rx*w, ry: f.ry*h,
        'data-index': i, 'data-action': 'move', class: `linedraw-face ${i === this.selected ? 'selected' : ''}`,
        opacity: f.enabled ? 1 : .35 }));
      if (i === this.selected) this.svg.append(node('circle', { cx: (f.cx+f.rx)*w, cy: (f.cy+f.ry)*h,
        r: Math.max(w,h)*.012, 'data-index':i, 'data-action':'resize', class:'linedraw-face-handle' }));
    });
  }
}
