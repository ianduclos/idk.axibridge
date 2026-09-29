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
    if (o !== id) return 'ink';
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
      if (o && !(o === id && s - this.arc[c] <= SELFWIN)) return false;
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
function flood(F, level, seed) {
  const mask = new Uint8Array(N);
  if (F[seed] <= level) return mask;
  const st = [seed]; mask[seed] = 1;
  while (st.length) {
    const c = st.pop(), i = c % GW, j = (c / GW) | 0;
    const nb = [i > 0 ? c - 1 : -1, i < GW - 1 ? c + 1 : -1, j > 0 ? c - GW : -1, j < GH - 1 ? c + GW : -1];
    for (const q of nb) if (q >= 0 && !mask[q] && F[q] > level) { mask[q] = 1; st.push(q); }
  }
  return mask;
}

// ======================= Territory v2 =======================
// Camps compete through sharp log-sum-exp fields; borders are traced where the
// winning camp changes. Voids are a camp that is never drawn and cannot be
// entered. Ink stays while the field moves: after each arriving core only the
// parts of the new contours that moved clear of existing ink are drawn, and
// small moves are held back until they add up or the topology changes.

const BETA = 8, TAU_OUT = 0.4;
const CAMP_WEIGHT = [0, 1, 0.6, 0.3];

function normal(rng) { return Math.sqrt(-2 * Math.log(1 - rng())) * Math.cos(2 * Math.PI * rng()); }

// Unclamped chamfer distance from seed cells.
function chamfer(seedMask) {
  const d = new Float32Array(N), D2 = Math.SQRT2;
  for (let c = 0; c < N; c++) d[c] = seedMask[c] ? 0 : 1e6;
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
    d[c] = v;
  }
  return d;
}
const coreDistCache = new WeakMap();
function coreDist(core) {
  let d = coreDistCache.get(core.pts);
  if (d) return d;
  const m = new Uint8Array(N);
  for (const [x, y] of resample(core.pts, 0.5)) m[cellOf(x, y)] = 1;
  d = chamfer(m); coreDistCache.set(core.pts, d); return d;
}

// Large-scale value noise, one field per camp: auto camps come in territories.
function campNoise(seed, camp) {
  const rng = rngFor(seed, 900 + camp), step = 90, gx = Math.ceil(W / step) + 2, gy = Math.ceil(H / step) + 2;
  const g = []; for (let k = 0; k < gx * gy; k++) g.push(rng());
  const ox = rng() * step, oy = rng() * step;
  return (x, y) => {
    const u = (x + ox) / step, v = (y + oy) / step, i = Math.floor(u), j = Math.floor(v), fu = u - i, fv = v - j;
    const s = t => t * t * (3 - 2 * t), a = g[j * gx + i], b = g[j * gx + i + 1], c = g[(j + 1) * gx + i], d = g[(j + 1) * gx + i + 1];
    return (a + (b - a) * s(fu)) * (1 - s(fv)) + (c + (d - c) * s(fu)) * s(fv);
  };
}
function resolveCores(cores, prm, seed) {
  const noises = [null, campNoise(seed, 1), campNoise(seed, 2), campNoise(seed, 3)];
  return cores.map((c, i) => {
    const rng = rngFor(seed, i + 1, 77);
    const r = prm.reach * clamp(Math.exp(prm.spread * normal(rng)), 0.5, 4) * (c.kind === 'void' ? 2.2 : 1);
    let camp = c.kind === 'void' ? 0 : c.camp;
    if (camp === 'auto' || camp === undefined) {
      const [x, y] = centroid(c.pts); let best = -1e9;
      for (let k = 1; k <= prm.camps; k++) {
        const s = noises[k](x, y) + Math.log(CAMP_WEIGHT[k]) * 0.12 + (rng() - 0.5) * 0.2;
        if (s > best) { best = s; camp = k; }
      }
    }
    return { ...c, camp, r, i };
  });
}

// Open or closed pursuit of destinations [x, y, loose?]. `touch` lets the first
// stretch start against old ink; `cross` ignores other ink entirely.
function walkLine(sheet, dests, id, prm, rng, D, o = {}) {
  if (dests.length < 2) return null;
  let k0 = 0;
  if (!o.cross && !o.touch) {
    k0 = dests.findIndex((p, k) => k < dests.length - 1 && sheet.clear(p[0], p[1], id, 0, 1.2));
    if (k0 < 0) return null;
  }
  const T = dests.slice(k0);
  if (o.closed) T.push(T[0]);
  if (T.length < 2) return null;
  const nz = noise1(rng);
  let [x, y] = T[0], h = Math.atan2(T[1][1] - y, T[1][0] - x);
  let di = 1, s = 0, pen = true, cur = [[x, y]], strokes = [], breaks = 0, under = 0, freeRun = 0;
  let best = 1e9, stuck = 0, turn = 0, ended = false;
  const hitAt = (ax, ay, bx, by, closing) => {
    if (o.cross) return (bx < MARGIN || bx > W - MARGIN || by < MARGIN || by > H - MARGIN) ? 'edge' : 0;
    const hh = sheet.segHit(ax, ay, bx, by, id, s, closing);
    return (hh === 'ink' && o.touch && s < 3) ? 0 : hh;
  };
  sheet.mark(x, y, id, 0, o.r);
  for (let step = 0; step < 8000 && di < T.length; step++) {
    const [tx, ty, lo] = T[di];
    const ctx = (D && !o.cross) ? smooth(1.5, 18, D[cellOf(x, y)]) : 1;
    const L = clamp((lo ?? prm.loose) * (0.3 + 0.7 * ctx), 0, 1);
    const len = 0.6 + 1.9 * L, maxT = rad(30 - 20 * L);
    const closing = !!o.closed && di === T.length - 1;
    const h0 = h;
    h += clamp(wrap(Math.atan2(ty - y, tx - x) - h), -maxT, maxT) + nz(s * 0.08) * rad(4 + 26 * L) * prm.wander;
    let nx = x + Math.cos(h) * len, ny = y + Math.sin(h) * len;
    if (pen) {
      const hit = hitAt(x, y, nx, ny, closing);
      if (hit) {
        if (o.noSwerve) { ended = true; break; }
        // Running into old ink near the end of an open line: it has arrived.
        if (hit === 'ink' && !o.closed && di === T.length - 1 && Math.hypot(tx - x, ty - y) < 7) break;
        let found = false;
        for (let k = 1; k <= 7 && !found; k++) for (const sg of (rng() < 0.5 ? [1, -1] : [-1, 1])) {
          const a = h + sg * k * rad(13), ax = x + Math.cos(a) * len, ay = y + Math.sin(a) * len;
          if (!hitAt(x, y, ax, ay, closing)) { h = a; nx = ax; ny = ay; found = true; break; }
        }
        if (!found) {
          if (hit === 'edge' || rng() >= prm.yieldP) { ended = true; break; }
          pen = false; breaks++; if (cur.length > 1) strokes.push(cur); cur = null; under = 0; freeRun = 0;
        }
      }
    }
    turn += wrap(h - h0);
    x = nx; y = ny; s += len;
    if (pen) { cur.push([x, y]); sheet.mark(x, y, id, s, o.r); }
    else {
      under += len;
      if (x < MARGIN || x > W - MARGIN || y < MARGIN || y > H - MARGIN || under > 45) { ended = true; break; }
      freeRun = sheet.clear(x, y, id, s, 1.8) ? freeRun + 1 : 0;
      if (freeRun >= 2) { pen = true; cur = [[x, y]]; sheet.mark(x, y, id, s, o.r); }
    }
    const dt = Math.hypot(tx - x, ty - y);
    if (dt < best - 0.3) { best = dt; stuck = 0; } else stuck++;
    const behind = dt < 10 && Math.abs(wrap(Math.atan2(ty - y, tx - x) - h)) > 1.9;
    if (dt < 1.2 + 3.5 * L || stuck > 28 || behind || Math.abs(turn) > Math.PI * 1.5) { di++; stuck = 0; best = 1e9; turn = 0; }
  }
  if (cur && cur.length > 1) strokes.push(cur);
  return { strokes: strokes.filter(st => polyLen(st) > 5), breaks, ended };
}

// Heavy-tailed destination spacing: mostly short, sometimes a long chord.
function chordDests(run, rng) {
  const out = [run[0]]; let k = 0;
  while (k < run.length - 1) {
    k = Math.min(run.length - 1, k + Math.max(2, Math.round(3 + 37 * Math.pow(rng(), 3))));
    out.push(run[k]);
  }
  return out;
}

class Territory {
  constructor(prm, seed) {
    this.prm = prm; this.seed = seed;
    this.S = [0, 1, 2, 3].map(() => new Float64Array(N));   // S[0] = voids
    this.present = new Set();
    this.sheet = new Sheet();
    this.lines = [];
    this.pending = 0;
    this.sig = '';
    this.inkLen = { border: 0, outer: 0, interior: 0 };
    this.regions = new Map();   // region key -> { authority, treatment, marks, camp, c }
    this.sid = 5000;
  }
  add(core, cores) {
    const d = coreDist(core), inv = BETA / (core.r * core.r), S = this.S[core.camp];
    for (let c = 0; c < N; c++) { const g = d[c] * d[c] * inv; if (g < 700) S[c] += Math.exp(-g); }
    this.present.add(core.camp);
  }
  sub(core) {
    const d = coreDist(core), inv = BETA / (core.r * core.r), S = this.S[core.camp];
    for (let c = 0; c < N; c++) { const g = d[c] * d[c] * inv; if (g < 700) S[c] = Math.max(0, S[c] - Math.exp(-g)); }
  }
  labels(S = this.S) {
    const L = new Int8Array(N), thr = Math.pow(this.prm.eps, BETA), voids = this.prm.voids;
    for (let c = 0; c < N; c++) {
      let b = 0, bv = thr;
      for (let k = 1; k <= 3; k++) if (S[k][c] > bv) { bv = S[k][c]; b = k; }
      if (voids && S[0][c] > thr && S[0][c] * 3 > bv) b = -1;
      L[c] = b;
    }
    return L;
  }
  signature(L) {
    const seen = new Uint8Array(N), counts = [0, 0, 0, 0], pairs = new Set();
    for (let c = 0; c < N; c++) {
      const l = L[c];
      if (l > 0) {
        const i = c % GW;
        if (i < GW - 1 && L[c + 1] > 0 && L[c + 1] !== l) pairs.add(Math.min(l, L[c + 1]) + '' + Math.max(l, L[c + 1]));
        if (c + GW < N && L[c + GW] > 0 && L[c + GW] !== l) pairs.add(Math.min(l, L[c + GW]) + '' + Math.max(l, L[c + GW]));
      }
      if (l <= 0 || seen[c]) continue;
      counts[l]++;
      const st = [c]; seen[c] = 1;
      while (st.length) {
        const q = st.pop(), qi = q % GW;
        for (const n of [qi > 0 ? q - 1 : -1, qi < GW - 1 ? q + 1 : -1, q - GW, q + GW]) if (n >= 0 && n < N && !seen[n] && L[n] === l) { seen[n] = 1; st.push(n); }
      }
    }
    return counts.slice(1).join(',') + '|' + [...pairs].sort().join(',');
  }
  // Contours of the current field: borders between camps and, optionally, outer limits.
  contours(S, L) {
    const out = [], prm = this.prm, thr = Math.pow(prm.eps, BETA);
    const logS = k => { const a = new Float32Array(N); for (let c = 0; c < N; c++) a[c] = Math.log(S[k][c] + 1e-300); return a; };
    const lg = [null, 1, 2, 3].map(k => k && this.present.has(k) ? logS(k) : null);
    const inf = (k, c) => Math.pow(S[k][c], 1 / BETA);
    if (prm.borders) {
      for (let k = 1; k <= 3; k++) {
        if (!lg[k]) continue;
        const others = [1, 2, 3].filter(j => j !== k && lg[j]);
        if (!others.length) continue;
        const val = new Float32Array(N), valid = new Uint8Array(N);
        for (let c = 0; c < N; c++) {
          if (L[c] <= 0) continue;
          let m = -1e30; for (const j of others) if (lg[j][c] > m) m = lg[j][c];
          val[c] = lg[k][c] - m; valid[c] = 1;
        }
        for (const line of isolines(val, valid, 0, 4)) {
          out.push({ kind: 'border', closed: line.closed, pts: resample(line.pts, 1).map(([x, y]) => {
            const c = cellOf(x, y); let m = 0; for (const j of others) m = Math.max(m, inf(j, c));
            return [x, y, Math.min(inf(k, c), m)];
          }) });
        }
      }
    }
    if (prm.outer) {
      for (let k = 1; k <= 3; k++) {
        if (!lg[k]) continue;
        const val = new Float32Array(N), valid = new Uint8Array(N), lv = BETA * Math.log(TAU_OUT);
        for (let c = 0; c < N; c++) { if (L[c] === k || L[c] === 0) { valid[c] = 1; val[c] = lg[k][c] - lv; } }
        for (const line of isolines(val, valid, 0, 6)) out.push({ kind: 'outer', closed: line.closed, pts: resample(line.pts, 1).map(([x, y]) => [x, y, TAU_OUT]) });
      }
    }
    return out;
  }
  // Stochastic fading plus the diff against existing ink.
  runs(contours, rng, D) {
    const prm = this.prm, X = 2 + 4 * prm.loose, eps = prm.eps, out = [];
    for (const ct of contours) {
      const P = ct.pts, keep = new Uint8Array(P.length);
      let gap = 0;
      const fade = ct.kind === 'outer' ? (rng() < 0.4 ? 0.15 : 1.6) : (rng() < 0.5 ? 0.3 : 1.2);
      const gapScale = 0.35 + 2.2 * rng() * rng();
      for (let q = 0; q < P.length; q++) {
        const s = P[q][2];
        if (gap > 0) { gap--; if (s < 3 * eps || ct.kind === 'outer') continue; }
        const pEnd = fade * ((ct.kind === 'outer' ? 0.02 : 0.004) + 0.04 * (1 - smooth(eps, 3 * eps, s)));
        if (rng() < pEnd) { gap = Math.round(gapScale * (ct.kind === 'outer' ? 10 + 50 * rng() : 4 + 22 * rng())); continue; }
        keep[q] = D[cellOf(P[q][0], P[q][1])] > X ? 1 : 0;
      }
      // Runs of kept points; drop short ones; extend 2 mm to touch old ink.
      let q = 0;
      while (q < P.length) {
        if (!keep[q]) { q++; continue; }
        let e = q; while (e + 1 < P.length && keep[e + 1]) e++;
        if (e - q + 1 >= 12) {
          const a = Math.max(0, q - 2), b = Math.min(P.length - 1, e + 2);
          const run = P.slice(a, b + 1).map(([x, y, s]) => {
            const contest = ct.kind === 'outer' ? 0.35 : smooth(eps, 0.4, s);
            return [x, y, clamp(prm.loose * (0.45 + 1.1 * (1 - contest)) + (ct.kind === 'outer' ? 0.15 : 0), 0.05, 1)];
          });
          out.push({ kind: ct.kind, run, touch: a < q || b > e });
        }
        q = e + 1;
      }
    }
    return out;
  }
  forbid(L) {
    const o = this.sheet.owner;
    for (let c = 0; c < N; c++) if (L[c] === -1 && !o[c]) o[c] = -1;
  }
  arrive(core, cores, done) {
    const prm = this.prm, rng = rngFor(this.seed, core.i + 1, 44);
    this.add(core, cores);
    const L = this.labels();
    if (prm.voids) this.forbid(L);
    const sig = this.signature(L), topo = sig !== this.sig;
    this.sig = sig;
    if (core.camp === 0) return;
    // Disregard: sometimes draw this arrival's borders as if one rival core were absent.
    let S = this.S, Lx = L, disregard = null;
    const rivals = done.filter(o => o.camp > 0 && o.camp !== core.camp);
    if (rivals.length && rng() < prm.disregard) {
      disregard = rivals[Math.floor(rng() * rivals.length)];
      this.sub(disregard); S = this.S.map(a => a.slice()); this.add(disregard, cores);
      Lx = this.labels(S);
    }
    const D = distField(this.sheet);
    const cand = this.runs(this.contours(S, Lx), rng, D);
    const moved = cand.reduce((a, r) => a + r.run.length, 0);
    this.pending += moved;
    if (topo || disregard || this.pending >= prm.hyst) {
      this.pending = 0;
      const [cx, cy] = centroid(core.pts);
      cand.sort((a, b) => Math.hypot(a.run[0][0] - cx, a.run[0][1] - cy) - Math.hypot(b.run[0][0] - cx, b.run[0][1] - cy));
      for (const r of cand) {
        const res = walkLine(this.sheet, chordDests(r.run, rng), ++this.sid, prm, rng, D, { touch: r.touch });
        if (res && res.strokes.length) {
          this.lines.push({ core: core.i, kind: r.kind, disregard: !!disregard, ...res });
          this.inkLen[r.kind] += res.strokes.reduce((a, s) => a + polyLen(s), 0);
        }
      }
    }
    if (prm.interior) this.interior(core, cores, done, L, rng);
  }
  interior(core, cores, done, L, rng) {
    const prm = this.prm;
    const P = resample(core.pts, 2);
    let seedCell = -1; for (const p of P) { const c = cellOf(p[0], p[1]); if (L[c] === core.camp) { seedCell = c; break; } }
    if (seedCell < 0) return;
    const comp = flood(Float32Array.from(L, v => v === core.camp ? 1 : 0), 0.5, seedCell);
    const members = done.concat([core]).filter(o => o.camp === core.camp && resample(o.pts, 3).some(p => comp[cellOf(p[0], p[1])]));
    const key = Math.min(...members.map(m => m.i));
    let reg = this.regions.get(key);
    if (!reg) {
      const has2 = [...this.regions.values()].some(r => r.authority === 2);
      const u = rng();
      reg = { authority: !has2 && u < 0.2 ? 2 : u < 0.5 ? 1 : 0, treatment: null, marks: 0, camp: core.camp, c: centroid(core.pts) };
      this.regions.set(key, reg);
    }
    reg.c = centroid(core.pts);
    const total = [...this.regions.values()].reduce((a, r) => a + r.marks, 0);
    if (reg.authority === 0 || reg.marks >= 1 || total >= 2) return;
    const borderLen = this.inkLen.border + this.inkLen.outer;
    if (this.inkLen.interior > 0.4 * borderLen) return;
    // Neighbouring camps, from the component's edge.
    const nbCamps = new Set(); let edgeCells = [];
    for (let c = 0; c < N; c++) {
      if (!comp[c]) continue;
      const i = c % GW;
      for (const n of [i > 0 ? c - 1 : -1, i < GW - 1 ? c + 1 : -1, c - GW, c + GW]) if (n >= 0 && n < N && L[n] > 0 && L[n] !== core.camp) { nbCamps.add(L[n]); edgeCells.push([c, n]); }
    }
    if (!reg.treatment) {
      const used = new Set([...this.regions.values()].filter(r => r !== reg && r.treatment && nbCamps.has(r.camp) && Math.hypot(r.c[0] - reg.c[0], r.c[1] - reg.c[1]) < 90).map(r => r.treatment));
      let opts = ['traverse', 'traverse', 'traverse', 'shadow', 'spine'].filter(t => !used.has(t));
      if (!nbCamps.size) opts = opts.filter(t => t === 'spine');
      if (!opts.length) opts = nbCamps.size ? ['traverse'] : ['spine'];
      reg.treatment = opts[Math.floor(rng() * opts.length)];
    }
    const D = distField(this.sheet), tight = reg.authority === 2 ? 0.12 : prm.loose;
    const emit = (dests, o = {}) => {
      const res = walkLine(this.sheet, dests, ++this.sid, { ...prm, loose: tight }, rng, D, o);
      if (res && res.strokes.length) {
        this.lines.push({ core: core.i, kind: 'interior', treatment: reg.treatment, ...res });
        this.inkLen.interior += res.strokes.reduce((a, s) => a + polyLen(s), 0);
      }
      reg.marks++;
    };
    const [cx, cy] = centroid(core.pts);
    if (reg.treatment === 'spine') {
      // Chain the region's cores from the newest outward: the hidden structure surfaces once.
      const order = [core], rest = members.filter(m => m !== core);
      while (rest.length) {
        const last = order[order.length - 1].pts, e = last[last.length - 1];
        rest.sort((a, b) => Math.hypot(a.pts[0][0] - e[0], a.pts[0][1] - e[1]) - Math.hypot(b.pts[0][0] - e[0], b.pts[0][1] - e[1]));
        order.push(rest.shift());
        if (order.length > 4) break;
      }
      const chain = smoothPts(resample(order.flatMap(m => m.pts), 1), 6);
      const reps = 1;
      for (let k = 0; k < reps && reg.marks < 3; k++) {
        const off = (k - (reps - 1) / 2) * 1.6;
        const line = chain.map((p, q) => {
          const a = chain[Math.max(0, q - 1)], b = chain[Math.min(chain.length - 1, q + 1)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
          return [p[0] - (b[1] - a[1]) / l * off, p[1] + (b[0] - a[0]) / l * off, tight];
        });
        emit(chordDests(line, rng), { touch: true });
      }
    } else if (reg.treatment === 'traverse' && edgeCells.length) {
      // From the new core, across the nearest border, 15 mm into the neighbour.
      let best = null, bd = 1e9;
      for (const [, n] of edgeCells) { const x = n % GW + 0.5, y = ((n / GW) | 0) + 0.5, d = Math.hypot(x - cx, y - cy); if (d < bd) { bd = d; best = [x, y]; } }
      const ang = Math.atan2(best[1] - cy, best[0] - cx), total = bd + 15, dests = [];
      for (let t = 0; t <= total; t += 6) dests.push([cx + Math.cos(ang) * t, cy + Math.sin(ang) * t, tight]);
      emit(dests, { cross: true });
    } else if (reg.treatment === 'shadow' && edgeCells.length) {
      // A shorter echo of the border, 4 mm into the neighbour's side.
      const cand = this.contours(this.S, L).filter(c => c.kind === 'border');
      let best = null, bd = 1e9;
      for (const ct of cand) for (const p of ct.pts) { const d = Math.hypot(p[0] - cx, p[1] - cy); if (d < bd) { bd = d; best = ct; } }
      if (!best || best.pts.length < 12) return;
      const Pp = best.pts, a = Math.floor(Pp.length * 0.2), b = Math.floor(Pp.length * 0.8), line = [];
      for (let q = a; q <= b; q++) {
        const u = Pp[Math.max(0, q - 1)], v = Pp[Math.min(Pp.length - 1, q + 1)], l = Math.hypot(v[0] - u[0], v[1] - u[1]) || 1;
        const nx = -(v[1] - u[1]) / l, ny = (v[0] - u[0]) / l;
        const side = L[cellOf(Pp[q][0] + nx * 4, Pp[q][1] + ny * 4)] !== core.camp ? 1 : -1;
        line.push([Pp[q][0] + nx * 4 * side, Pp[q][1] + ny * 4 * side, tight]);
      }
      emit(chordDests(smoothPts(line, 3), rng));
    }
  }
}

// ---- volume: the field read as a lit landscape ----
// Height is the winning camp's influence, so every territory is a hill and every
// border a valley. Volume is built from many traces, never from fill.
Territory.prototype.surface = function () {
  const prm = this.prm, H = new Float32Array(N), S = this.S;
  const L = this.labels();
  for (let c = 0; c < N; c++) { const l = L[c]; H[c] = l > 0 ? Math.pow(S[l][c], 1 / BETA) : 0; }
  // light blur keeps creases but removes grid stair-steps
  const B = new Float32Array(N);
  for (let pass = 0; pass < 2; pass++) {
    for (let j = 1; j < GH - 1; j++) for (let i = 1; i < GW - 1; i++) { const c = j * GW + i; B[c] = (H[c] * 4 + H[c - 1] + H[c + 1] + H[c - GW] + H[c + GW]) / 8; }
    H.set(B);
  }
  const az = rad(prm.lightAz), el = rad(prm.lightEl), lx = Math.cos(az) * Math.cos(el), ly = Math.sin(az) * Math.cos(el), lz = Math.sin(el);
  const dark = new Float32Array(N), steep = new Float32Array(N), gx = new Float32Array(N), gy = new Float32Array(N), k = prm.relief;
  for (let j = 1; j < GH - 1; j++) for (let i = 1; i < GW - 1; i++) {
    const c = j * GW + i;
    if (L[c] <= 0) continue;
    const hx = (H[c + 1] - H[c - 1]) / 2, hy = (H[c + GW] - H[c - GW]) / 2;
    gx[c] = hx; gy[c] = hy;
    const nx = -k * hx, ny = -k * hy, nl = Math.hypot(nx, ny, 1);
    const shade = (nx * lx + ny * ly + lz) / nl;
    dark[c] = smooth(0.15, 0.95, 1 - shade);
    steep[c] = smooth(0.08, 0.6, Math.hypot(hx, hy) * k);
  }
  return { H, L, dark, gx, gy, steep };
};
Territory.prototype.volume = function (rng) {
  const prm = this.prm;
  if (!prm.restate && !prm.hatch) return;
  const surf = this.surface(), { L, dark, gx, gy, steep } = surf;
  this.surf = surf;
  const darkAt = (x, y) => dark[cellOf(x, y)];
  const R = 0.45;
  // Each territory gets its own appetite for shading; some stay bare.
  const comp = new Int32Array(N), appetite = [1];
  for (let c = 0; c < N; c++) {
    if (L[c] <= 0 || comp[c]) continue;
    const id = appetite.length, u = rng();
    appetite.push(u < 0.22 ? 0 : u < 0.5 ? 0.55 : u < 0.85 ? 1 : 1.6);
    const st = [c]; comp[c] = id;
    while (st.length) {
      const q = st.pop(), qi = q % GW;
      for (const n of [qi > 0 ? q - 1 : -1, qi < GW - 1 ? q + 1 : -1, q - GW, q + GW]) if (n >= 0 && n < N && !comp[n] && L[n] === L[c]) { comp[n] = id; st.push(n); }
    }
  }
  const want = (x, y) => appetite[comp[cellOf(x, y)]] ?? 0;
  const clump = campNoise(this.seed, 61), stretch = campNoise(this.seed, 62);
  if (prm.restate) {
    const base = this.lines.filter(l => l.kind === 'border' || l.kind === 'outer').flatMap(l => l.strokes);
    const D = distField(this.sheet);
    for (const st of base) {
      const P = resample(st, 1);
      if (P.length < 8) continue;
      const nrm = P.map((p, q) => { const a = P[Math.max(0, q - 2)], b = P[Math.min(P.length - 1, q + 2)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1; return [-(b[1] - a[1]) / l, (b[0] - a[0]) / l]; });
      const sideRaw = P.map((p, q) => darkAt(p[0] + nrm[q][0] * 2.5, p[1] + nrm[q][1] * 2.5) - darkAt(p[0] - nrm[q][0] * 2.5, p[1] - nrm[q][1] * 2.5));
      // settle the shadow side over a window, so traces do not flip back and forth
      const side = sideRaw.map((_, q) => { let s = 0; for (let t = Math.max(0, q - 10); t <= Math.min(P.length - 1, q + 10); t++) s += sideRaw[t]; return s >= 0 ? 1 : -1; });
      const nz = noise1(rng);
      const count = P.map((p, q) => {
        const d = Math.max(darkAt(p[0] + nrm[q][0] * 2.5 * side[q], p[1] + nrm[q][1] * 2.5 * side[q]), 0);
        return Math.floor(d * prm.traces * Math.min(1, want(p[0] + nrm[q][0] * 2.5 * side[q], p[1] + nrm[q][1] * 2.5 * side[q])) + 0.6 * nz(q * 0.06));
      });
      for (let k = 1; k <= prm.traces; k++) {
        let q = 0;
        while (q < P.length) {
          if (count[q] < k) { q++; continue; }
          let e = q; while (e + 1 < P.length && count[e + 1] >= k) e++;
          if (e - q >= 6) {
            const off = prm.traceGap * (k + 0.35 * (rng() - 0.5) * k);
            const len = e - q, q2 = q + Math.floor(len * 0.3 * rng() * rng()), e2 = e - Math.floor(len * 0.3 * rng());
            if (e2 - q2 < 6) { q = e + 1; continue; }
            const run = [];
            for (let t = q2; t <= e2; t++) run.push([P[t][0] + nrm[t][0] * off * side[t], P[t][1] + nrm[t][1] * off * side[t], 0.12]);
            const dests = [run[0]]; for (let t = 2; t < run.length; t += 2 + Math.floor(rng() * 3)) dests.push(run[t]); dests.push(run[run.length - 1]);
            const res = walkLine(this.sheet, dests, ++this.sid, { ...prm, wander: 0.5 }, rng, D, { touch: true, r: R, noSwerve: true });
            if (res && res.strokes.length) { this.lines.push({ core: -1, kind: 'restate', ...res }); this.inkLen.interior += 0; }
          }
          q = e + 1;
        }
      }
    }
  }
  if (prm.hatch) {
    const D = distField(this.sheet);
    const b = [Math.cos(rad(prm.hatchAngle)), Math.sin(rad(prm.hatchAngle))];
    const dirAt = (x, y) => {
      const c = cellOf(x, y); let ix = -gy[c], iy = gx[c]; const g = Math.hypot(ix, iy);
      if (g > 1e-9) { ix /= g; iy /= g; if (ix * b[0] + iy * b[1] < 0) { ix = -ix; iy = -iy; } }
      const s = Math.min(1, g * prm.relief * 1.5) * prm.bend;
      const dx = b[0] + s * ix, dy = b[1] + s * iy, l = Math.hypot(dx, dy) || 1; return [dx / l, dy / l];
    };
    const seeds = [];
    for (let y = 3; y < H - 3; y += 1.6) for (let x = 3; x < W - 3; x += 1.6) {
      const px = x + (rng() - 0.5) * 1.6, py = y + (rng() - 0.5) * 1.6, c = cellOf(px, py);
      if (L[c] <= 0 || D[c] < prm.clearance) continue;
      const cl = 0.25 + 1.5 * Math.pow(clump(px * 0.6, py * 0.6), 2);
      if (rng() < Math.pow(dark[c] * steep[c], 1.4) * prm.hatchDensity * 0.35 * want(px, py) * cl) seeds.push([px, py, rng()]);
    }
    seeds.sort((a, b2) => a[2] - b2[2]);
    let n = 0;
    for (const [sx, sy] of seeds) {
      if (n > 1400) break;
      const c0 = cellOf(sx, sy), lab = L[c0];
      if (this.sheet.owner[c0]) continue;
      const maxLen = (4 + 30 * Math.pow(rng(), 2.5)) * (0.5 + 1.2 * stretch(sx * 0.5, sy * 0.5));
      const trace = sgn => {
        const out = []; let x = sx, y = sy, len = 0;
        while (len < maxLen / 2) {
          const [dx, dy] = dirAt(x, y); x += dx * sgn; y += dy * sgn; len += 1;
          const c = cellOf(x, y);
          if (x < 3 || y < 3 || x > W - 3 || y > H - 3 || L[c] !== lab || dark[c] * steep[c] < 0.1 || D[c] < prm.clearance * 0.7) break;
          out.push([x, y, 0.15]);
        }
        return out;
      };
      const line = trace(-1).reverse().concat([[sx, sy, 0.15]], trace(1));
      if (line.length < 4) continue;
      const dests = []; for (let t = 0; t < line.length; t += 3) dests.push(line[t]); if (dests[dests.length - 1] !== line[line.length - 1]) dests.push(line[line.length - 1]);
      const res = walkLine(this.sheet, dests, ++this.sid, { ...prm, wander: 0.25, yieldP: 0 }, rng, D, { r: R, noSwerve: true });
      if (res && res.strokes.length) { this.lines.push({ core: -1, kind: 'hatch', ...res }); n++; }
    }
  }
};

function arrivalOrder(cores, mode) {
  const idx = cores.map((_, i) => i);
  if (mode === true || mode === 'reversed') return idx.reverse();
  if (mode === 'largest' || mode === 'smallest') {
    const size = i => polyLen(cores[i].pts) * cores[i].r;
    idx.sort((a, b) => mode === 'largest' ? size(b) - size(a) : size(a) - size(b));
  }
  return idx;
}
function runTerritory(rawCores, prm, seed, order = 'drawn') {
  prm = { lightAz: -135, lightEl: 35, relief: 30, restate: false, hatch: false, traces: 3, traceGap: 1.3, hatchAngle: 35, bend: 2.2, hatchDensity: 0.8, clearance: 2.5,
    render: 'lines', forms: 'territories', tubeScale: 1, spacing: 1, budget: 14, terminator: false, sway: 1, overshoot: 1, lifts: 1, tremor: 1, quality: 'full', keepLines: false, ...prm };
  const cores = resolveCores(rawCores, prm, seed);
  const T = new Territory(prm, seed), done = [];
  T.order = arrivalOrder(cores, order);
  for (const i of T.order) { T.arrive(cores[i], cores, done); done.push(cores[i]); }
  if (['wrap', 'wound', 'growth', 'auto'].includes(prm.render)) T.organic(cores);
  else T.volume(rngFor(seed, 991));
  const L = T.labels();
  return { lines: T.lines, cores, L, inkLen: T.inkLen, regions: T.regions, surf: T.surf, forms: T.forms };
}

function tStats(res) {
  const s = { lines: res.lines.length, border: 0, outer: 0, interior: 0, restate: 0, hatch: 0, silhouette: 0, wrap: 0, wound: 0, growth: 0, broken: 0, disregard: 0 };
  for (const l of res.lines) { s[l.kind]++; if (l.breaks) s.broken++; if (l.disregard) s.disregard++; }
  s.mm = Math.round(res.lines.reduce((a, l) => a + l.strokes.reduce((u, st) => u + polyLen(st), 0), 0));
  return s;
}

// ---- core vocabularies ----
function makeCore(type, L, x, y, a, rng) {
  const pts = [], n = Math.max(6, Math.round(L / 1.5)), ca = Math.cos(a), sa = Math.sin(a);
  const put = (u, v) => pts.push([x + u * ca - v * sa, y + u * sa + v * ca]);
  for (let k = 0; k <= n; k++) {
    const t = k / n, u = (t - 0.5) * L;
    if (type === 'arc') put(u, Math.sin(t * Math.PI) * L * 0.28);
    else if (type === 'hook') { const b = Math.max(0, t - 0.65) / 0.35; put(u * (1 - b * 0.8), -b * b * L * 0.35); }
    else if (type === 'zig') put(u, ((k % Math.max(2, Math.round(n / 5))) / Math.max(2, Math.round(n / 5)) - 0.5) * L * 0.22);
    else if (type === 'loop') { const th = t * Math.PI * 2 * 1.15; put(Math.cos(th) * L * 0.18 + u * 0.35, Math.sin(th) * L * 0.18); }
    else if (type === 'scrawl') put(u, Math.sin(t * 17) * L * 0.07 + Math.sin(t * 5) * L * 0.12);
    else put(u, 0);
  }
  return smoothPts(pts, 1).map(([px, py]) => [clamp(px, 4, W - 4), clamp(py, 4, H - 4)]);
}
const TYPES = ['arc', 'hook', 'zig', 'loop', 'scrawl', 'line'];
// A population sheet: 8-12 cores; 40% two camps, 40% three, 20% one camp + 2 voids.
function randomSheet(seed) {
  const rng = mulberry32(seed * 7919 + 13), u = rng();
  const mix = u < 0.4 ? 2 : u < 0.8 ? 3 : 1;
  const n = 8 + Math.floor(rng() * 5), cores = [];
  for (let k = 0; k < n; k++) {
    const L = 8 + 95 * Math.pow(rng(), 2.2);
    cores.push({ pts: makeCore(TYPES[Math.floor(rng() * TYPES.length)], L, 25 + rng() * (W - 50), 20 + rng() * (H - 40), rng() * Math.PI * 2, rng), camp: 'auto', kind: 'attract' });
  }
  if (mix === 1) for (let k = 0; k < 2; k++) cores.splice(2 + Math.floor(rng() * (cores.length - 2)), 0, { pts: makeCore(TYPES[Math.floor(rng() * TYPES.length)], 30 + 60 * rng(), 40 + rng() * (W - 80), 30 + rng() * (H - 60), rng() * Math.PI * 2, rng), camp: 'auto', kind: 'void' });
  return { cores, camps: mix };
}
function exampleSheet() {
  const r = mulberry32(5), mk = (t, L, x, y, a, camp, kind = 'attract') => ({ pts: makeCore(t, L, x, y, a, r), camp, kind });
  return [
    mk('arc', 90, 120, 95, -0.25, 1), mk('hook', 38, 205, 70, 0.9, 2), mk('zig', 55, 95, 150, 0.15, 1),
    mk('loop', 26, 215, 150, 0.4, 3), mk('line', 12, 60, 60, 1.2, 2), mk('scrawl', 70, 170, 118, -0.6, 2),
    mk('arc', 60, 250, 110, 1.4, 3), mk('line', 50, 150, 40, 0.1, 1, 'void'), mk('hook', 30, 40, 120, 2.2, 3),
  ];
}

if (typeof module !== 'undefined') module.exports = { runTerritory, tStats, randomSheet, exampleSheet, makeCore, mulberry32, W, H, polyLen };

// ======================= The hand =======================
// A shared final pass: every polyline is re-curved (Catmull-Rom through a
// sparser set of control points, so the curve is the hand's, not the grid's),
// then given character. Character is low-frequency displacement correlated
// with the geometry; wobble is uncorrelated high frequency, kept tiny.

function catmullRom(P, step = 0.5) {
  if (P.length < 3) return P.map(p => [p[0], p[1]]);
  const out = [];
  for (let i = 0; i < P.length - 1; i++) {
    const p0 = P[Math.max(0, i - 1)], p1 = P[i], p2 = P[i + 1], p3 = P[Math.min(P.length - 1, i + 2)];
    const n = Math.max(1, Math.ceil(Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / step));
    for (let k = 0; k < n; k++) {
      const t = k / n, t2 = t * t, t3 = t2 * t;
      const f = (a, b, c, d) => 0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
      out.push([f(p0[0], p1[0], p2[0], p3[0]), f(p0[1], p1[1], p2[1], p3[1])]);
    }
  }
  const e = P[P.length - 1]; out.push([e[0], e[1]]);
  return out;
}

// Two contrasting hands per sheet: loose (sways on straights, firm on curves)
// and firm (the inverse, with a faint tremor).
function makeHands(seed, prm) {
  const r = rngFor(seed, 700);
  return [
    { name: 'loose', A: 0.45 * prm.sway * (0.8 + 0.4 * r()), l1: 25 + 35 * r(), l2: 8 + 7 * r(), gate: 1, over: 2.5 * prm.overshoot, curl: 0.1 + 0.3 * r(), lift: 0.3 * prm.lifts, tremor: 0, step: 2 },
    { name: 'firm', A: 0.18 * prm.sway * (0.8 + 0.4 * r()), l1: 25 + 35 * r(), l2: 8 + 7 * r(), gate: -1, over: 1.0 * prm.overshoot, curl: 0.1 + 0.3 * r(), lift: 0.15 * prm.lifts, tremor: 0.03 * prm.tremor, step: 2 },
  ];
}

function handLine(P, hand, rng, closed = false) {
  if (P.length < 2 || polyLen(P) < 1.5) return [];
  const ctrl = resample(P, hand.step);
  if (ctrl.length < 2) return [];
  let Q = catmullRom(ctrl, 0.5);
  // Overshoot with a quadratic curl that usually continues the last bend.
  if (!closed && hand.over > 0.1 && Q.length > 6) {
    const ext = (A, B, C) => {
      const bend = wrap(Math.atan2(C[1] - B[1], C[0] - B[0]) - Math.atan2(B[1] - A[1], B[0] - A[0]));
      const sgn = (rng() < 0.7 ? Math.sign(bend) || 1 : -(Math.sign(bend) || 1));
      let a = Math.atan2(C[1] - B[1], C[0] - B[0]), [x, y] = C; const pts = [];
      const len = hand.over * (0.4 + 0.8 * rng());
      for (let t = 0.5; t <= len; t += 0.5) { a += sgn * hand.curl * (2 * t) * 0.5; x += Math.cos(a) * 0.5; y += Math.sin(a) * 0.5; pts.push([x, y]); }
      return pts;
    };
    const n = Q.length;
    const tail = ext(Q[n - 5], Q[n - 3], Q[n - 1]);
    const head = ext(Q[4], Q[2], Q[0]).reverse();
    Q = head.concat(Q, tail);
  }
  // Curvature-gated sway, two octaves; faint tremor.
  const n = Q.length, kap = new Float32Array(n);
  for (let i = 2; i < n - 2; i++) {
    const a = Math.atan2(Q[i][1] - Q[i - 2][1], Q[i][0] - Q[i - 2][0]), b = Math.atan2(Q[i + 2][1] - Q[i][1], Q[i + 2][0] - Q[i][0]);
    kap[i] = Math.abs(wrap(b - a)) / 2;   // rad per mm (samples 0.5 mm apart)
  }
  const ph = rng() * 100, n1 = noise1(rng), n2 = noise1(rng), n3 = noise1(rng);
  let s = 0;
  const out = Q.map((p, i) => {
    if (i > 0) s += Math.hypot(p[0] - Q[i - 1][0], p[1] - Q[i - 1][1]);
    const a = Q[Math.max(0, i - 1)], b = Q[Math.min(n - 1, i + 1)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
    const nx = -(b[1] - a[1]) / l, ny = (b[0] - a[0]) / l;
    const g = smooth(0, 0.15, kap[i]);
    const gate = hand.gate > 0 ? 1 - 0.7 * g : 0.3 + 0.7 * g;
    const d = hand.A * gate * (n1(ph + s / hand.l1) + 0.4 * n2(ph + s / hand.l2)) + hand.tremor * n3(ph + s / 1.5);
    return [p[0] + nx * d, p[1] + ny * d];
  });
  // One lift on long lines: a short gap, re-entry slightly off and 1 mm back, so strokes overlap.
  if (!closed && hand.lift > 0 && polyLen(out) > 40 && rng() < hand.lift) {
    const k = Math.floor(out.length * (0.3 + 0.4 * rng())), gap = Math.round((1.5 + 1.5 * rng()) / 0.5);
    if (k + gap < out.length - 4) {
      const A = out.slice(0, k), back = Math.max(0, k + gap - 2);
      const a = out[back], b = out[Math.min(out.length - 1, back + 1)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
      const off = (rng() < 0.5 ? -1 : 1) * 0.3, nx = -(b[1] - a[1]) / l * off, ny = (b[0] - a[0]) / l * off;
      const B = out.slice(back).map(p => [p[0] + nx, p[1] + ny]);
      return [A, B].filter(p => p.length > 1);
    }
  }
  return [out];
}

// ======================= Bodies =======================
// The composition becomes soft bodies: territories inflated by a Poisson solve
// (true round sections, no medial crease), or cores swept into tubes. Depth is
// actual height minus a rank offset, so a fat rear body can crest over a thin
// front tube. Volume is drawn by one of three renderers, in the hand.

function bboxOf(mask, pad = 0) {
  let x0 = GW, y0 = GH, x1 = -1, y1 = -1;
  for (let c = 0; c < N; c++) if (mask[c]) { const i = c % GW, j = (c / GW) | 0; if (i < x0) x0 = i; if (i > x1) x1 = i; if (j < y0) y0 = j; if (j > y1) y1 = j; }
  if (x1 < 0) return null;
  return [Math.max(0, x0 - pad), Math.max(0, y0 - pad), Math.min(GW - 1, x1 + pad), Math.min(GH - 1, y1 + pad)];
}

function inflate(mask, bb, iters, puff) {
  const p = new Float32Array(N), [x0, y0, x1, y1] = bb, w = 1.9;
  for (let it = 0; it < iters; it++) for (let col = 0; col < 2; col++) {
    for (let j = Math.max(1, y0); j <= Math.min(GH - 2, y1); j++) for (let i = Math.max(1, x0) + ((j + col + Math.max(1, x0)) & 1); i <= Math.min(GW - 2, x1); i += 2) {
      const c = j * GW + i; if (!mask[c]) continue;
      p[c] = (1 - w) * p[c] + w * (p[c - 1] + p[c + 1] + p[c - GW] + p[c + GW] + 1) / 4;
    }
  }
  const H = new Float32Array(N), Hmax = 15;
  for (let j = y0; j <= y1; j++) for (let i = x0; i <= x1; i++) { const c = j * GW + i; if (mask[c] && p[c] > 0) H[c] = Hmax * Math.tanh(puff * Math.sqrt(4 * p[c]) / Hmax); }
  return H;
}

function gaussSmooth(P, sigma) {
  const k = Math.ceil(sigma * 2.5), w = []; for (let t = -k; t <= k; t++) w.push(Math.exp(-t * t / (2 * sigma * sigma)));
  return P.map((_, i) => { let x = 0, y = 0, s = 0; for (let t = -k; t <= k; t++) { const q = P[clamp(i + t, 0, P.length - 1)]; x += q[0] * w[t + k]; y += q[1] * w[t + k]; s += w[t + k]; } return [x / s, y / s]; });
}

function tubeOf(core, rng, scale) {
  const S = gaussSmooth(resample(core.pts, 1), 3), L = polyLen(S);
  if (L < 3) return null;
  const nz = noise1(rng), r0 = clamp(core.r * 0.45 * scale * clamp(Math.exp(0.7 * normal(rng)), 0.4, 2.5), 2, 26), Lend = Math.max(1, 0.15 * L);
  const H = new Float32Array(N); let s = 0;
  for (let q = 0; q < S.length; q++) {
    if (q) s += Math.hypot(S[q][0] - S[q - 1][0], S[q][1] - S[q - 1][1]);
    const e = s < Lend ? (Lend - s) / Lend : s > L - Lend ? (s - (L - Lend)) / Lend : 0;
    const r = r0 * Math.sqrt(Math.max(0.04, 1 - e * e)) * (1 + 0.25 * nz(s / 25));
    const [cx, cy] = S[q];
    for (let j = Math.max(0, Math.floor(cy - r)); j <= Math.min(GH - 1, Math.ceil(cy + r)); j++) for (let i = Math.max(0, Math.floor(cx - r)); i <= Math.min(GW - 1, Math.ceil(cx + r)); i++) {
      const d2 = (i + 0.5 - cx) ** 2 + (j + 0.5 - cy) ** 2; if (d2 >= r * r) continue;
      const v = Math.sqrt(r * r - d2), c = j * GW + i; if (v > H[c]) H[c] = v;
    }
  }
  return { H, skel: S };
}

// Several isoline levels in one pass over a bounding box.
function isoLevels(val, valid, bb, levels) {
  const [x0, y0, x1, y1] = bb, nL = levels.length, segs = [], pos = new Map();
  if (!nL) return [];
  const pt = (id, k) => {
    const key = id * nL + k; let p = pos.get(key); if (p) return p;
    const c = id >> 1, i = c % GW, j = (c / GW) | 0, horiz = !(id & 1), L = levels[k];
    const a = val[c] - L, b = (horiz ? val[c + 1] : val[c + GW]) - L, t = clamp(a / (a - b), 0, 1);
    p = horiz ? [i + 0.5 + t, j + 0.5] : [i + 0.5, j + 0.5 + t]; pos.set(key, p); return p;
  };
  const lower = v => { let lo = 0, hi = nL; while (lo < hi) { const m = (lo + hi) >> 1; if (levels[m] < v) lo = m + 1; else hi = m; } return lo; };
  for (let j = y0; j < Math.min(y1, GH - 1); j++) for (let i = x0; i < Math.min(x1, GW - 1); i++) {
    const c = j * GW + i;
    if (!(valid[c] && valid[c + 1] && valid[c + GW] && valid[c + GW + 1])) continue;
    const a = val[c], b = val[c + 1], d = val[c + GW + 1], e = val[c + GW];
    const mn = Math.min(a, b, d, e), mx = Math.max(a, b, d, e);
    for (let k = lower(mn); k < nL && levels[k] < mx; k++) {
      const L = levels[k], tl = a > L, tr = b > L, br = d > L, bl = e > L, E = [];
      if (tl !== tr) E.push(c * 2); if (tr !== br) E.push((c + 1) * 2 + 1); if (br !== bl) E.push((c + GW) * 2); if (bl !== tl) E.push(c * 2 + 1);
      if (E.length === 2) segs.push([E[0] * nL + k, E[1] * nL + k, k]);
      else if (E.length === 4) { segs.push([E[0] * nL + k, E[1] * nL + k, k]); segs.push([E[2] * nL + k, E[3] * nL + k, k]); }
    }
  }
  const adj = new Map();
  segs.forEach((s, q) => { for (const id of [s[0], s[1]]) { let a = adj.get(id); if (!a) adj.set(id, a = []); a.push(q); } });
  const used = new Uint8Array(segs.length), out = [];
  const ext = (chain, end) => { for (;;) { const nx = (adj.get(end) || []).find(q => !used[q]); if (nx === undefined) return end; used[nx] = 1; end = segs[nx][0] === end ? segs[nx][1] : segs[nx][0]; chain.push(end); } };
  for (let q = 0; q < segs.length; q++) {
    if (used[q]) continue; used[q] = 1;
    const fw = [segs[q][0], segs[q][1]], endF = ext(fw, segs[q][1]), closed = endF === segs[q][0];
    let ids = fw; if (!closed) { const bk = [segs[q][0]]; ext(bk, segs[q][0]); ids = bk.reverse().concat(fw.slice(1)); }
    const k = segs[q][2];
    out.push({ k, closed, pts: ids.map(key => pt(Math.floor(key / nL), k)) });
  }
  return out;
}

Territory.prototype.organic = function (cores) {
  const prm = this.prm, seed = this.seed, rng = rngFor(seed, 4242), thumb = prm.quality === 'thumb';
  // ---- forms ----
  const forms = [];
  const rankOf = new Map(this.order.map((ci, r) => [ci, r]));
  if (prm.forms === 'tubes') {
    for (const c of cores) {
      if (c.camp === 0) continue;
      const t = tubeOf(c, rngFor(seed, c.i + 1, 55), prm.tubeScale);
      if (!t) continue;
      const mask = new Uint8Array(N); for (let q = 0; q < N; q++) if (t.H[q] > 0) mask[q] = 1;
      const bb = bboxOf(mask, 1); if (!bb) continue;
      forms.push({ kind: 'tube', H: t.H, mask, bb, rank: rankOf.get(c.i), skel: t.skel, cores: [c] });
    }
  } else {
    const L = this.labels(), seen = new Uint8Array(N);
    for (let c0 = 0; c0 < N; c0++) {
      if (L[c0] <= 0 || seen[c0]) continue;
      const mask = new Uint8Array(N), st = [c0]; seen[c0] = 1; mask[c0] = 1; let area = 1;
      while (st.length) { const q = st.pop(), qi = q % GW; for (const n of [qi > 0 ? q - 1 : -1, qi < GW - 1 ? q + 1 : -1, q - GW, q + GW]) if (n >= 0 && n < N && !seen[n] && L[n] === L[c0]) { seen[n] = 1; mask[n] = 1; area++; st.push(n); } }
      if (area < 60) continue;
      const members = cores.filter(o => o.camp === L[c0] && resample(o.pts, 3).some(p => mask[cellOf(p[0], p[1])]));
      const rank = members.length ? Math.min(...members.map(m => rankOf.get(m.i))) : 999;
      const bb = bboxOf(mask, 1);
      const H = inflate(mask, bb, thumb ? 60 : 150, 0.6 + 0.7 * rng());
      forms.push({ kind: 'pillow', H, mask, bb, rank, cores: members, skel: members.length ? gaussSmooth(resample(members[0].pts, 1), 3) : null });
    }
  }
  forms.sort((a, b) => a.rank - b.rank);
  // ---- ownership by actual height ----
  const owner = new Int16Array(N).fill(-1), zb = new Float32Array(N).fill(-1e9);
  forms.forEach((f, i) => {
    const [x0, y0, x1, y1] = f.bb, off = 1.5 * i;
    for (let j = y0; j <= y1; j++) for (let x = x0; x <= x1; x++) { const c = j * GW + x; if (!f.mask[c]) continue; const z = f.H[c] - off; if (z > zb[c]) { zb[c] = z; owner[c] = i; } }
  });
  // ---- light ----
  const az = rad(prm.lightAz), el = rad(prm.lightEl), lx = Math.cos(az) * Math.cos(el), ly = Math.sin(az) * Math.cos(el), lz = Math.sin(el), k = prm.relief / 30;
  const dark = new Float32Array(N);
  for (let j = 1; j < GH - 1; j++) for (let i = 1; i < GW - 1; i++) {
    const c = j * GW + i, o = owner[c]; if (o < 0) continue;
    const H = forms[o].H, hx = (H[c + 1] - H[c - 1]) / 2 * k, hy = (H[c + GW] - H[c - GW]) / 2 * k;
    dark[c] = smooth(0.15, 0.95, 1 - (-hx * lx - hy * ly + lz) / Math.hypot(hx, hy, 1));
  }
  // ---- per-form metrics, renderer choice ----
  forms.forEach((f, i) => {
    let A = 0, P = 0, sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
    const [x0, y0, x1, y1] = f.bb;
    for (let j = y0; j <= y1; j++) for (let x = x0; x <= x1; x++) {
      const c = j * GW + x; if (owner[c] !== i) continue;
      A++; sx += x; sy += j; sxx += x * x; syy += j * j; sxy += x * j;
      if (owner[c - 1] !== i || owner[c + 1] !== i || owner[c - GW] !== i || owner[c + GW] !== i) P++;
    }
    f.A = A; f.P = Math.max(1, P);
    if (A < 20) { f.render = 'none'; return; }
    const mx = sx / A, my = sy / A, cxx = sxx / A - mx * mx, cyy = syy / A - my * my, cxy = sxy / A - mx * my;
    const tr = cxx + cyy, det = cxx * cyy - cxy * cxy, disc = Math.sqrt(Math.max(0, tr * tr / 4 - det));
    const l1 = tr / 2 + disc, l2 = Math.max(1e-6, tr / 2 - disc);
    f.axis = Math.atan2(l1 - cxx, cxy || 1e-9); if (!cxy) f.axis = cxx >= cyy ? 0 : Math.PI / 2;
    f.E = Math.sqrt(l1 / l2); f.C = 4 * Math.PI * A / (f.P * f.P); f.center = [mx + 0.5, my + 0.5];
    if (prm.render !== 'auto') { f.render = prm.render; return; }
    f.render = (f.kind === 'tube' || f.E > 2.2) ? 'wrap' : (f.C > 0.6 && A < 2500) ? 'wound' : (A > 2500 && f.C < 0.6) ? 'growth' : 'wrap';
  });
  if (prm.render === 'auto') {
    // Touching forms never share a renderer; the most-connected form stays bare.
    const nb = forms.map(() => new Set());
    for (let c = 0; c < N - GW; c++) { const o = owner[c]; if (o < 0) continue; for (const n of [c + 1, c + GW]) { const p = owner[n]; if (p >= 0 && p !== o) { nb[o].add(p); nb[p].add(o); } } }
    let big = -1, bigA = 0; forms.forEach((f, i) => { if (f.A > bigA && f.render !== 'none') { bigA = f.A; big = i; } });
    forms.forEach((f, i) => {
      if (f.render === 'none') return;
      if (i === big) { f.render = 'wound'; return; }
      if (f.kind === 'tube') f.render = rng() < 0.6 ? 'wrap' : 'growth';
      const used = new Set([...nb[i]].filter(j => j < i).map(j => forms[j].render));
      if (used.has(f.render)) f.render = ['wrap', 'growth', 'wound'].find(r => !used.has(r) && (r !== 'wound')) || f.render;
    });
    let hub = -1, best = 2; forms.forEach((f, i) => { if (nb[i].size > best && i !== big) { best = nb[i].size; hub = i; } });
    if (hub >= 0) forms[hub].render = 'none';
  }
  // ---- terminator: a straight line beyond which nothing is shaded ----
  let term = () => true;
  if (prm.terminator) {
    const px = 60 + rng() * 180, py = 40 + rng() * 138, a = rng() * Math.PI * 2, nx = Math.cos(a), ny = Math.sin(a);
    term = (x, y) => (x - px) * nx + (y - py) * ny > 0;
  }
  // ---- draw ----
  const hands = makeHands(seed, prm), lines = [];
  let budget = prm.budget * 1000;
  let formBudget = 0;
  const emit = (kind, P, hand, closed = false, costs = true) => {
    for (const piece of handLine(P, hand, rng, closed)) {
      const len = polyLen(piece);
      if (costs) { if (formBudget <= 0) return; formBudget -= len; budget -= len; }
      lines.push({ core: -1, kind, strokes: [piece], breaks: 0 });
    }
  };
  const runsWhere = (pts, keep, minLen = 4) => {
    const out = []; let cur = [];
    for (const p of pts) { if (keep(p)) cur.push(p); else { if (cur.length > 1 && polyLen(cur) >= minLen) out.push(cur); cur = []; } }
    if (cur.length > 1 && polyLen(cur) >= minLen) out.push(cur);
    return out;
  };
  forms.forEach((f, i) => {
    const hand = hands[(i + (rng() < 0.5 ? 0 : 1)) % 2];
    const vis = new Uint8Array(N); for (let j = f.bb[1]; j <= f.bb[3]; j++) for (let x = f.bb[0]; x <= f.bb[2]; x++) { const c = j * GW + x; if (owner[c] === i) vis[c] = 1; }
    // silhouette: the visible boundary, drawn once where it borders an earlier form
    const sil = isolines(Float32Array.from(vis), new Uint8Array(N).fill(1), 0.5, 4);
    for (const s of sil) {
      const pts = s.pts.filter((p, q) => {
        const a = s.pts[Math.max(0, q - 1)], b = s.pts[Math.min(s.pts.length - 1, q + 1)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
        const nx = -(b[1] - a[1]) / l, ny = (b[0] - a[0]) / l;
        const o1 = owner[cellOf(p[0] + nx * 0.9, p[1] + ny * 0.9)], o2 = owner[cellOf(p[0] - nx * 0.9, p[1] - ny * 0.9)];
        const other = o1 === i ? o2 : o1;
        return !(other >= 0 && other < i);
      });
      if (pts.length > 3) for (const r of runsWhere(pts, () => true, 2)) emit('silhouette', r, hand, false, false);
    }
    if (f.render === 'none') return;
    formBudget = Math.max(0, budget) * 0.45;
    const shadeOK = (x, y) => term(x, y);
    if (f.render === 'wrap') this.wrapForm(f, i, vis, dark, rng, (P) => { for (const r of runsWhere(P, p => shadeOK(p[0], p[1]))) emit('wrap', r, hand); }, thumb);
    else if (f.render === 'wound') this.woundForm(f, i, vis, dark, rng, (P, closed) => { for (const r of runsWhere(P, p => shadeOK(p[0], p[1]))) emit('wound', r, hand, false); }, thumb);
    else if (f.render === 'growth') this.growthForm(f, i, vis, dark, rng, (P) => { for (const r of runsWhere(P, p => shadeOK(p[0], p[1]))) emit('growth', r, { ...hand, step: 1, A: hand.A * 0.3, over: 0 }); }, thumb);
  });
  this.lines = prm.keepLines ? this.lines.concat(lines) : lines;
  this.forms = forms; this.owner = owner;
};

// Cross-contours: isolines of u·x + k·h bow over the body; tone by golden-hash thinning.
Territory.prototype.wrapForm = function (f, i, vis, dark, rng, out, thumb) {
  const a = f.axis + (rng() - 0.5) * rad(40), ux = Math.cos(a), uy = Math.sin(a);
  const [x0, y0, x1, y1] = f.bb, H = f.H;
  const slopes = [];
  for (let j = y0 + 1; j < y1; j++) for (let x = x0 + 1; x < x1; x++) { const c = j * GW + x; if (vis[c]) slopes.push(Math.abs((H[c + 1] - H[c - 1]) / 2 * ux + (H[c + GW] - H[c - GW]) / 2 * uy)); }
  if (!slopes.length) return;
  slopes.sort((p, q) => p - q);
  const kk = 0.7 / Math.max(0.05, slopes[Math.floor(slopes.length * 0.9)]);
  const g = new Float32Array(N); let mn = 1e9, mx = -1e9;
  for (let j = y0; j <= y1; j++) for (let x = x0; x <= x1; x++) { const c = j * GW + x; g[c] = (x + 0.5) * ux + (j + 0.5) * uy + kk * H[c]; if (vis[c]) { mn = Math.min(mn, g[c]); mx = Math.max(mx, g[c]); } }
  const sp = (0.8 + 0.7 * rng()) * (thumb ? 1.6 : 1) * this.prm.spacing;
  const levels = []; for (let v = mn + sp * rng(); v < mx; v += sp) levels.push(v);
  const valid = new Uint8Array(N); for (let j = y0; j <= y1; j++) for (let x = x0; x <= x1; x++) { const c = j * GW + x; if (vis[c]) valid[c] = 1; }
  for (const line of isoLevels(g, valid, f.bb, levels)) {
    const hsh = (line.k * 0.618034) % 1; let tail = 0; const keep = [];
    for (const p of line.pts) {
      const d = dark[cellOf(p[0], p[1])], w = d < 0.15 ? 0 : 0.25 + 0.75 * d;
      if (hsh < w) { tail = 3; keep.push(p); } else if (tail > 0) { tail -= 0.5; keep.push(p); } else keep.push(null);
    }
    let cur = [];
    for (const p of keep) { if (p) cur.push(p); else { if (cur.length > 1) out(cur); cur = []; } }
    if (cur.length > 1) out(cur);
  }
};

// Wound line: rings of a darkness-weighted distance from the highlight, spliced into one thread.
Territory.prototype.woundForm = function (f, i, vis, dark, rng, out, thumb) {
  const [x0, y0, x1, y1] = f.bb, nz = campNoise(this.seed + i, 71);
  const inside = chamfer(Uint8Array.from(vis, v => v ? 0 : 1));
  let dmax = 0; for (let j = y0; j <= y1; j++) for (let x = x0; x <= x1; x++) dmax = Math.max(dmax, inside[j * GW + x]);
  let sc = -1, sd = 1e9;
  for (let j = y0; j <= y1; j++) for (let x = x0; x <= x1; x++) { const c = j * GW + x; if (!vis[c] || inside[c] < dmax * 0.35) continue; const s = dark[c] - 0.3 * inside[c] / dmax; if (s < sd) { sd = s; sc = c; } }
  if (sc < 0) return;
  const T = new Float32Array(N).fill(1e9); T[sc] = 0;
  const cost = new Float32Array(N);
  const sp = this.prm.spacing * (thumb ? 1.5 : 1);
  for (let j = y0; j <= y1; j++) for (let x = x0; x <= x1; x++) { const c = j * GW + x; if (vis[c]) cost[c] = 1 / ((2.5 - 1.7 * dark[c]) * sp * (0.75 + 0.5 * nz(x, j))); }
  const D2 = Math.SQRT2;
  for (let pass = 0; pass < (thumb ? 3 : 5); pass++) {
    for (let j = y0; j <= y1; j++) for (let x = x0; x <= x1; x++) { const c = j * GW + x; if (!vis[c]) continue; let v = T[c], w = cost[c];
      if (x > x0) v = Math.min(v, T[c - 1] + w); if (j > y0) { v = Math.min(v, T[c - GW] + w); if (x > x0) v = Math.min(v, T[c - GW - 1] + w * D2); if (x < x1) v = Math.min(v, T[c - GW + 1] + w * D2); } T[c] = v; }
    for (let j = y1; j >= y0; j--) for (let x = x1; x >= x0; x--) { const c = j * GW + x; if (!vis[c]) continue; let v = T[c], w = cost[c];
      if (x < x1) v = Math.min(v, T[c + 1] + w); if (j < y1) { v = Math.min(v, T[c + GW] + w); if (x < x1) v = Math.min(v, T[c + GW + 1] + w * D2); if (x > x0) v = Math.min(v, T[c + GW - 1] + w * D2); } T[c] = v; }
  }
  for (let pass = 0; pass < 6; pass++) {
    const B = T.slice();
    for (let j = y0 + 1; j < y1; j++) for (let x = x0 + 1; x < x1; x++) {
      const c = j * GW + x; if (!vis[c] || T[c] >= 1e8) continue;
      let s = T[c] * 2, n = 2; for (const q of [c - 1, c + 1, c - GW, c + GW, c - GW - 1, c - GW + 1, c + GW - 1, c + GW + 1]) if (vis[q] && T[q] < 1e8) { s += T[q]; n++; }
      B[c] = s / n;
    }
    T.set(B);
  }
  let mx = 0; for (let j = y0; j <= y1; j++) for (let x = x0; x <= x1; x++) { const c = j * GW + x; if (vis[c] && T[c] < 1e8) mx = Math.max(mx, T[c]); }
  const valid = new Uint8Array(N); for (let j = y0; j <= y1; j++) for (let x = x0; x <= x1; x++) { const c = j * GW + x; if (vis[c] && T[c] < 1e8) valid[c] = 1; }
  const levels = []; for (let v = 1; v < mx; v += 1) levels.push(v);
  const byLevel = new Map();
  for (const r of isoLevels(T, valid, f.bb, levels)) { if (polyLen(r.pts) < 6) continue; if (!byLevel.has(r.k)) byLevel.set(r.k, []); byLevel.get(r.k).push(r); }
  const dir = (i % 2) ? 1 : -1;
  const orient = pts => { let a = 0; for (let q = 0; q < pts.length; q++) { const p = pts[q], r = pts[(q + 1) % pts.length]; a += p[0] * r[1] - r[0] * p[1]; } return Math.sign(a) === dir ? pts : pts.slice().reverse(); };
  let thread = [], prev = null;
  const flush = () => { if (thread.length > 2) out(thread, false); thread = []; };
  for (let k = 0; k < levels.length; k++) {
    const rings = (byLevel.get(k) || []).sort((a, b) => polyLen(b.pts) - polyLen(a.pts));
    if (!rings.length) { flush(); prev = null; continue; }
    const main = rings[0];
    for (const extra of rings.slice(1)) out(resample(extra.pts, 1), extra.closed);   // restarts
    let R = resample(main.pts, 1);
    if (main.closed) {
      R = orient(R);
      if (prev) { let bq = 0, bd = 1e9; R.forEach((p, q) => { const d = Math.hypot(p[0] - prev[0], p[1] - prev[1]); if (d < bd) { bd = d; bq = q; } }); R = R.slice(bq).concat(R.slice(0, bq)); if (bd > 4 * sp + 2) flush(); }
      const next = (byLevel.get(k + 1) || [])[0];
      const Nx = next && next.closed ? resample(next.pts, 1.5) : null;
      for (let q = 0; q < R.length; q++) {
        const t = q / R.length, p = R[q];
        if (Nx) { let bd = 1e9, bp = null; for (const n of Nx) { const d = (n[0] - p[0]) ** 2 + (n[1] - p[1]) ** 2; if (d < bd) { bd = d; bp = n; } } thread.push([p[0] * (1 - t) + bp[0] * t, p[1] * (1 - t) + bp[1] * t]); }
        else thread.push(p);
      }
    } else {
      // an open ring: continue from whichever end is nearer, like a thread turning back
      if (prev) {
        const d0 = Math.hypot(R[0][0] - prev[0], R[0][1] - prev[1]), d1 = Math.hypot(R[R.length - 1][0] - prev[0], R[R.length - 1][1] - prev[1]);
        if (d1 < d0) R.reverse();
        if (Math.min(d0, d1) > 4 * sp + 2) flush();
      }
      for (const p of R) thread.push(p);
    }
    prev = thread[thread.length - 1];
  }
  flush();
};

// Growth: an open strand along the core; only the young tip grows; stops at a fill target.
Territory.prototype.growthForm = function (f, i, vis, dark, rng, out, thumb) {
  const [x0, y0, x1, y1] = f.bb;
  // distance to the visible edge, for pushback
  const edge = new Uint8Array(N); for (let c = 0; c < N; c++) edge[c] = vis[c] ? 0 : 1;
  const dEdge = chamfer(edge);
  let seedPts = (f.cores || []).flatMap(c => gaussSmooth(resample(c.pts, 1), 3)).filter(p => vis[cellOf(p[0], p[1])]);
  if (!seedPts || seedPts.length < 3) {
    const [cx, cy] = f.center; seedPts = []; for (let t = -6; t <= 6; t++) seedPts.push([cx + Math.cos(f.axis) * t, cy + Math.sin(f.axis) * t]);
  }
  let P = resample(seedPts, 1.2).filter(p => vis[cellOf(p[0], p[1])]).map(p => ({ x: p[0], y: p[1], age: 0 }));
  if (P.length < 3) return;
  const maxN = thumb ? 900 : 2500, iters = thumb ? 90 : 250, target = 0.04 + 0.5 * Math.pow(rng(), 1.5), area = f.A;
  const nzx = noise1(rng);
  for (let it = 0; it < iters && P.length < maxN; it++) {
    const cell = 2.4, grid = new Map();
    P.forEach((p, q) => { const key = Math.floor(p.x / cell) * 1000 + Math.floor(p.y / cell); let a = grid.get(key); if (!a) grid.set(key, a = []); a.push(q); });
    const F = P.map(() => [0, 0]);
    for (let q = 0; q < P.length; q++) {
      const p = P[q]; if (p.age > 40) continue;
      const d = dark[cellOf(p.x, p.y)], R = 2.4 + 3.2 * (1 - d);
      const gx = Math.floor(p.x / cell), gy = Math.floor(p.y / cell);
      for (let a = -2; a <= 2; a++) for (let b = -2; b <= 2; b++) for (const o of (grid.get((gx + a) * 1000 + gy + b) || [])) {
        if (o === q || Math.abs(o - q) < 2) continue;
        const dx = p.x - P[o].x, dy = p.y - P[o].y, dd = Math.hypot(dx, dy);
        if (dd < R && dd > 1e-6) { const s = (R - dd) / R; F[q][0] += dx / dd * s; F[q][1] += dy / dd * s; }
      }
      // neighbours: stay near the midpoint (smooths), plus a push along the normal where it is dark
      const A = P[Math.max(0, q - 1)], B = P[Math.min(P.length - 1, q + 1)];
      F[q][0] += ((A.x + B.x) / 2 - p.x) * 0.5; F[q][1] += ((A.y + B.y) / 2 - p.y) * 0.5;
      const tx = B.x - A.x, ty = B.y - A.y, tl = Math.hypot(tx, ty) || 1;
      const push = (0.05 + 0.3 * d) * (0.5 + nzx(q * 0.05 + it * 0.01));
      F[q][0] += -ty / tl * push; F[q][1] += tx / tl * push;
    }
    for (let q = 0; q < P.length; q++) {
      const p = P[q]; p.age++; if (p.age > 41) continue;
      let nx = p.x + clamp(F[q][0], -0.6, 0.6), ny = p.y + clamp(F[q][1], -0.6, 0.6);
      const c = cellOf(nx, ny);
      if (!vis[c] || dEdge[c] < 1) {
        // push back inward along the distance gradient
        const gx = dEdge[c + 1] - dEdge[c - 1], gy = dEdge[c + GW] - dEdge[c - GW], gl = Math.hypot(gx, gy) || 1;
        nx = p.x + gx / gl * 0.4; ny = p.y + gy / gl * 0.4;
        if (!vis[cellOf(nx, ny)]) continue;
      }
      p.x = nx; p.y = ny;
    }
    // split long edges; new nodes are young
    const Q = [P[0]];
    for (let q = 1; q < P.length; q++) {
      const a = P[q - 1], b = P[q], d = Math.hypot(b.x - a.x, b.y - a.y);
      if (d > 2.2 && P.length + Q.length < maxN * 2) Q.push({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, age: 0 });
      Q.push(b);
    }
    P = Q;
    let len = 0; for (let q = 1; q < P.length; q++) len += Math.hypot(P[q].x - P[q - 1].x, P[q].y - P[q - 1].y);
    if (len * 2.4 / Math.max(1, area) > target) break;
  }
  out(P.map(p => [p.x, p.y]));
};
