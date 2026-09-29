// Cores & skins engine. Pure functions of (cores, proposal, params, seed).
// Units: millimetres on the 300 x 218 AxiDraw bed. Grid: 1 mm cells.
const W = 300, H = 218, GW = 300, GH = 218, N = GW * GH;
const MARGIN = 2, SELFWIN = 8, CLOSEARC = 10, INK_R = 1.0;

function mulberry32(a) {
  return function () {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
function rngFor(seed, ...keys) {
  let h = (seed >>> 0) ^ 0x9e3779b9;
  for (const k of keys) { h = Math.imul(h ^ k, 2654435761); h ^= h >>> 13; }
  return mulberry32(h);
}
function noise1(rng) {
  const v = new Float32Array(512);
  for (let i = 0; i < 512; i++) v[i] = rng() * 2 - 1;
  return t => {
    const i = Math.floor(t), f = t - i, u = f * f * (3 - 2 * f);
    const a = v[((i % 512) + 512) % 512], b = v[(((i + 1) % 512) + 512) % 512];
    return a + (b - a) * u;
  };
}
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const wrap = a => Math.atan2(Math.sin(a), Math.cos(a));
const rad = d => d * Math.PI / 180;
const cellOf = (x, y) => clamp(Math.floor(y), 0, GH - 1) * GW + clamp(Math.floor(x), 0, GW - 1);

function polyLen(P) { let s = 0; for (let i = 1; i < P.length; i++) s += Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]); return s; }
function resample(P, step) {
  if (P.length < 2) return P.slice();
  const out = [P[0].slice()]; let carry = 0;
  for (let i = 1; i < P.length; i++) {
    const [x0, y0] = P[i - 1], [x1, y1] = P[i];
    const seg = Math.hypot(x1 - x0, y1 - y0);
    let d = step - carry;
    while (d <= seg) { const t = d / seg; out.push([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t]); d += step; }
    carry = seg - (d - step);
  }
  const last = P[P.length - 1];
  if (Math.hypot(last[0] - out[out.length - 1][0], last[1] - out[out.length - 1][1]) > step * 0.3) out.push(last.slice());
  return out;
}
function smoothPts(P, passes = 2) {
  let Q = P;
  for (let p = 0; p < passes; p++) {
    Q = Q.map((q, i) => (i === 0 || i === Q.length - 1) ? q : [(Q[i - 1][0] + q[0] * 2 + Q[i + 1][0]) / 4, (Q[i - 1][1] + q[1] * 2 + Q[i + 1][1]) / 4]);
  }
  return Q;
}
function centroid(P) { let x = 0, y = 0; for (const p of P) { x += p[0]; y += p[1]; } return [x / P.length, y / P.length]; }

// ---------- the sheet: ink occupancy ----------
class Sheet {
  constructor() { this.owner = new Int32Array(N); this.arc = new Float32Array(N); }
  mark(x, y, id, s, r = INK_R) {
    for (let j = Math.floor(y - r); j <= Math.floor(y + r); j++) {
      if (j < 0 || j >= GH) continue;
      for (let i = Math.floor(x - r); i <= Math.floor(x + r); i++) {
        if (i < 0 || i >= GW) continue;
        if (Math.hypot(i + 0.5 - x, j + 0.5 - y) > r + 0.2) continue;
        const c = j * GW + i;
        if (!this.owner[c]) { this.owner[c] = id; this.arc[c] = s; }
      }
    }
  }
  hit(x, y, id, s, closing) {
    if (x < MARGIN || x > W - MARGIN || y < MARGIN || y > H - MARGIN) return 'edge';
    const c = cellOf(x, y), o = this.owner[c];
    if (!o) return 0;
    if (o !== id) return (this.related && o > 0 && this.related(o, id)) ? 0 : 'ink';
    if (s - this.arc[c] > SELFWIN) return (closing && this.arc[c] < CLOSEARC) ? 0 : 'self';
    return 0;
  }
  segHit(x0, y0, x1, y1, id, s0, closing) {
    const len = Math.hypot(x1 - x0, y1 - y0), n = Math.max(1, Math.ceil(len / 0.4));
    for (let k = 1; k <= n; k++) {
      const t = k / n, h = this.hit(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, id, s0 + len * t, closing);
      if (h) return h;
    }
    return 0;
  }
  clear(x, y, id, s, r) {
    if (x < MARGIN || x > W - MARGIN || y < MARGIN || y > H - MARGIN) return false;
    for (let j = Math.floor(y - r); j <= Math.floor(y + r); j++) for (let i = Math.floor(x - r); i <= Math.floor(x + r); i++) {
      if (i < 0 || j < 0 || i >= GW || j >= GH) continue;
      const c = j * GW + i, o = this.owner[c];
      if (o && !(o === id && s - this.arc[c] <= SELFWIN) && !(this.related && o > 0 && o !== id && this.related(o, id))) return false;
    }
    return true;
  }
}

// Distance (mm) from every cell to the nearest ink or the bed edge. Chamfer 1/1.414.
function distField(sheet) {
  const d = new Float32Array(N), D2 = Math.SQRT2;
  for (let c = 0; c < N; c++) d[c] = sheet.owner[c] ? 0 : 1e6;
  for (let j = 0; j < GH; j++) for (let i = 0; i < GW; i++) {
    const c = j * GW + i; let v = d[c];
    if (i > 0) v = Math.min(v, d[c - 1] + 1);
    if (j > 0) { v = Math.min(v, d[c - GW] + 1); if (i > 0) v = Math.min(v, d[c - GW - 1] + D2); if (i < GW - 1) v = Math.min(v, d[c - GW + 1] + D2); }
    d[c] = v;
  }
  for (let j = GH - 1; j >= 0; j--) for (let i = GW - 1; i >= 0; i--) {
    const c = j * GW + i; let v = d[c];
    if (i < GW - 1) v = Math.min(v, d[c + 1] + 1);
    if (j < GH - 1) { v = Math.min(v, d[c + GW] + 1); if (i < GW - 1) v = Math.min(v, d[c + GW + 1] + D2); if (i > 0) v = Math.min(v, d[c + GW - 1] + D2); }
    d[c] = Math.min(v, i + 0.5 - MARGIN, W - i - 0.5 - MARGIN, j + 0.5 - MARGIN, H - j - 0.5 - MARGIN);
  }
  return d;
}

// ---------- the walker: pursuit of imaginary destinations under never-overlap ----------
// Carefulness comes from context: near other ink or the edge it slows, samples
// densely and steers hard; in open space it lopes. Boxed in, it either stops
// (an open skin) or passes under and resurfaces (a visible interruption).
// Isolines of `val` at `level`, only through cells where all four corners are
// valid. Returns open and closed polylines (bidirectional stitching), each
// with {pts, closed}. Grid point (i,j) sits at (i+0.5, j+0.5) mm.
function isolines(val, valid, level, minLen = 4) {
  const v = c => val[c] - level;
  const pos = new Map();
  const edgePt = id => {
    let p = pos.get(id); if (p) return p;
    const c = id >> 1, i = c % GW, j = (c / GW) | 0, horiz = !(id & 1);
    const a = v(c), b = horiz ? v(c + 1) : v(c + GW), t = clamp(a / (a - b), 0, 1);
    p = horiz ? [i + 0.5 + t, j + 0.5] : [i + 0.5, j + 0.5 + t];
    pos.set(id, p); return p;
  };
  const segs = [];
  for (let j = 0; j < GH - 1; j++) for (let i = 0; i < GW - 1; i++) {
    const c = j * GW + i;
    if (!(valid[c] && valid[c + 1] && valid[c + GW] && valid[c + GW + 1])) continue;
    const tl = v(c) > 0, tr = v(c + 1) > 0, br = v(c + GW + 1) > 0, bl = v(c + GW) > 0;
    const e = [];
    if (tl !== tr) e.push(c * 2);
    if (tr !== br) e.push((c + 1) * 2 + 1);
    if (br !== bl) e.push((c + GW) * 2);
    if (bl !== tl) e.push(c * 2 + 1);
    if (e.length === 2) segs.push([e[0], e[1]]);
    else if (e.length === 4) { segs.push([e[0], e[1]]); segs.push([e[2], e[3]]); }
  }
  const adj = new Map();
  segs.forEach((s, k) => { for (const id of s) { let a = adj.get(id); if (!a) adj.set(id, a = []); a.push(k); } });
  const used = new Uint8Array(segs.length), out = [];
  const extend = (chain, end) => {
    for (;;) {
      const nxt = (adj.get(end) || []).find(q => !used[q]);
      if (nxt === undefined) return end;
      used[nxt] = 1; end = segs[nxt][0] === end ? segs[nxt][1] : segs[nxt][0]; chain.push(end);
    }
  };
  for (let k = 0; k < segs.length; k++) {
    if (used[k]) continue;
    used[k] = 1;
    const fwd = [segs[k][0], segs[k][1]];
    const endF = extend(fwd, segs[k][1]);
    const closed = endF === segs[k][0];
    let ids = fwd;
    if (!closed) { const back = [segs[k][0]]; extend(back, segs[k][0]); ids = back.reverse().concat(fwd.slice(1)); }
    const pts = ids.map(edgePt);
    if (polyLen(pts) >= minLen) out.push({ pts, closed });
  }
  return out;
}
