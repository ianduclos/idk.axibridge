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
  mark(x, y, id, s) {
    const r = INK_R;
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
function walk(sheet, dests, id, prm, rng, D) {
  if (dests.length < 3) return null;
  // Start at the first destination that is free.
  let k0 = dests.findIndex(p => !sheet.hit(p[0], p[1], id, 0, false) && sheet.clear(p[0], p[1], id, 0, 1.2));
  if (k0 < 0) return { strokes: [], status: 'blocked', breaks: 0 };
  const ring = dests.slice(k0).concat(dests.slice(0, k0));
  const target = ring.concat([ring[0]]);
  const nz = noise1(rng);
  let [x, y] = ring[0];
  let h = Math.atan2(ring[1][1] - y, ring[1][0] - x) + (rng() - 0.5) * 0.6;
  let best = 1e9, stuck = 0, turn = 0;
  let di = 1, s = 0, pen = true, cur = [[x, y]], strokes = [], breaks = 0, under = 0, freeRun = 0, since = 0, ended = false;
  sheet.mark(x, y, id, 0);
  for (let step = 0; step < 6000 && di < target.length; step++) {
    const [tx, ty] = target[di];
    const ctx = D ? smooth(1.5, 18, D[cellOf(x, y)]) : 1;
    const L = clamp(prm.loose * (0.3 + 0.7 * ctx), 0, 1);
    const len = 0.6 + 1.9 * L, maxT = rad(30 - 20 * L);
    const closing = di === target.length - 1;
    const h0 = h;
    h += clamp(wrap(Math.atan2(ty - y, tx - x) - h), -maxT, maxT) + nz(s * 0.08) * rad(4 + 26 * L) * prm.wander;
    let nx = x + Math.cos(h) * len, ny = y + Math.sin(h) * len;
    if (pen) {
      const hit = sheet.segHit(x, y, nx, ny, id, s, closing);
      if (hit) {
        let found = false;
        for (let k = 1; k <= 7 && !found; k++) for (const sg of (rng() < 0.5 ? [1, -1] : [-1, 1])) {
          const a = h + sg * k * rad(13), ax = x + Math.cos(a) * len, ay = y + Math.sin(a) * len;
          if (!sheet.segHit(x, y, ax, ay, id, s, closing)) { h = a; nx = ax; ny = ay; found = true; break; }
        }
        if (!found) {
          if (hit === 'edge' || rng() >= prm.yieldP) { ended = true; break; }
          pen = false; breaks++; if (cur.length > 1) strokes.push(cur); cur = null; under = 0; freeRun = 0;
        }
      }
    }
    turn += wrap(h - h0);
    x = nx; y = ny; s += len;
    if (pen) { cur.push([x, y]); sheet.mark(x, y, id, s); }
    else {
      under += len;
      if (x < MARGIN || x > W - MARGIN || y < MARGIN || y > H - MARGIN || under > 45) { ended = true; break; }
      freeRun = sheet.clear(x, y, id, s, 1.8) ? freeRun + 1 : 0;
      if (freeRun >= 2) { pen = true; cur = [[x, y]]; sheet.mark(x, y, id, s); }
    }
    const dt = Math.hypot(tx - x, ty - y);
    if (dt < best - 0.3) { best = dt; stuck = 0; } else stuck++;
    if (dt < 1.2 + 3.5 * L || stuck > 28 || Math.abs(turn) > Math.PI * 1.5) {
      // Arrived, or orbiting a destination it cannot reach: move on.
      di++; since = 0; stuck = 0; best = 1e9; turn = 0;
      if (di === target.length && pen && dt < 1.2 + 3.5 * L + 0.5 && dt > 0.3) cur.push([tx, ty]);
    } else if (++since > 240) { di++; since = 0; }
  }
  if (cur && cur.length > 1) strokes.push(cur);
  if (di < target.length) ended = true;
  const status = ended ? 'open' : breaks ? 'broken' : 'closed';
  return { strokes: strokes.filter(st => polyLen(st) > 1.5), status, breaks };
}

// Destinations around a core: out along one side, round the end, back along
// the other. Offsets vary; Departure skips stretches and flings the odd point.
function ringDests(core, prm, rng, D, scale = 1) {
  const base = (2.5 + 9 * prm.loose) * scale;
  // The skin follows the gross form: smooth the core at the scale of the offset,
  // so zigzags and scrawls get one body instead of interleaved sides.
  const P = smoothPts(resample(core, 2), Math.max(2, Math.round(base * 1.2)));
  const nz = noise1(rng);
  const crowd = p => D ? 0.55 + 0.45 * smooth(2, 20, D[cellOf(p[0], p[1])]) : 1;
  const fling = () => rng() < prm.dep * 0.09 ? 2 + rng() * 1.3 : 1;
  let out = [];
  if (polyLen(P) < 8) {
    const [cx, cy] = centroid(P), r = base * (0.8 + 0.5 * rng()), a0 = rng() * 7, n = 7;
    for (let k = 0; k < n; k++) { const a = a0 + k / n * Math.PI * 2, rr = r * (0.7 + 0.6 * nz(k)) * fling(); out.push([cx + Math.cos(a) * rr, cy + Math.sin(a) * rr]); }
    return out;
  }
  const n = P.length, T = P.map((p, i) => {
    const a = P[Math.max(0, i - 1)], b = P[Math.min(n - 1, i + 1)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
    return [(b[0] - a[0]) / l, (b[1] - a[1]) / l];
  });
  const stride = Math.max(1, Math.round((3.5 + 8 * prm.loose) / 2));
  const off = (i, side) => base * (0.65 + 0.7 * Math.abs(nz(i * 0.15 + side * 60))) * crowd(P[i]) * fling();
  const push = (i, side) => { const o = off(i, side); out.push([P[i][0] - T[i][1] * o * side, P[i][1] + T[i][0] * o * side]); };
  for (let i = 0; i < n; i += stride) push(i, 1);
  const e = n - 1, oe = base * 0.9 * crowd(P[e]);
  out.push([P[e][0] + T[e][0] * oe, P[e][1] + T[e][1] * oe]);
  for (let i = e; i >= 0; i -= stride) push(i, -1);
  const o0 = base * 0.9 * crowd(P[0]);
  out.push([P[0][0] - T[0][0] * o0, P[0][1] - T[0][1] * o0]);
  // Skip stretches: the skin cuts across and ignores part of its core.
  if (prm.dep > 0 && out.length > 8) {
    const kept = [];
    for (let i = 0; i < out.length; i++) {
      if (i > 0 && rng() < prm.dep * 0.12 && out.length - i > 3) { i += 1 + Math.floor(rng() * 4); if (i < out.length) kept.push(out[i]); continue; }
      kept.push(out[i]);
    }
    if (kept.length >= 5) out = kept;
  }
  return out;
}

// ---------- B: shared territory field ----------
function contribution(core, r) {
  const P = resample(core, 2), f = new Float32Array(N);
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (const [x, y] of P) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  const pad = r * 2.6;
  const i0 = clamp(Math.floor(x0 - pad), 0, GW - 1), i1 = clamp(Math.ceil(x1 + pad), 0, GW - 1);
  const j0 = clamp(Math.floor(y0 - pad), 0, GH - 1), j1 = clamp(Math.ceil(y1 + pad), 0, GH - 1);
  const r2 = r * r;
  for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
    const cx = i + 0.5, cy = j + 0.5; let m = 1e9;
    for (const p of P) { const dx = p[0] - cx, dy = p[1] - cy, d = dx * dx + dy * dy; if (d < m) m = d; }
    f[j * GW + i] = Math.exp(-m / r2);
  }
  return f;
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
// Marching squares on (F - level) restricted to mask; returns the longest loop.
function contourLoop(F, level, mask) {
  const v = i => mask[i] ? F[i] - level : -1;
  const segs = [], pos = new Map();
  const edgePt = (id) => {
    if (pos.has(id)) return pos.get(id);
    const c = id >> 1, i = c % GW, j = (c / GW) | 0, horiz = !(id & 1);
    const a = v(c), b = horiz ? v(c + 1) : v(c + GW), t = a / (a - b);
    const p = horiz ? [i + 0.5 + t, j + 0.5] : [i + 0.5, j + 0.5 + t];
    pos.set(id, p); return p;
  };
  for (let j = 1; j < GH - 2; j++) for (let i = 1; i < GW - 2; i++) {
    const c = j * GW + i;
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
  segs.forEach((s, k) => { for (const id of s) { if (!adj.has(id)) adj.set(id, []); adj.get(id).push(k); } });
  const used = new Uint8Array(segs.length); let best = null, bestLen = 0;
  for (let k = 0; k < segs.length; k++) {
    if (used[k]) continue;
    used[k] = 1; const loop = [segs[k][0], segs[k][1]]; let end = segs[k][1];
    for (;;) {
      const nxt = (adj.get(end) || []).find(q => !used[q]);
      if (nxt === undefined) break;
      used[nxt] = 1; end = segs[nxt][0] === end ? segs[nxt][1] : segs[nxt][0]; loop.push(end);
    }
    const pts = loop.map(edgePt), L = polyLen(pts);
    if (L > bestLen) { bestLen = L; best = pts; }
  }
  return best;
}

// ---------- the three proposals ----------
function runA(cores, order, prm, seed) {
  const sheet = new Sheet(), skins = [];
  for (const i of order) {
    const rng = rngFor(seed, i + 1, 11), D = distField(sheet);
    const sk = walk(sheet, ringDests(cores[i], prm, rng, D), i + 1, prm, rng, D);
    if (sk) skins.push({ core: i, ...sk });
  }
  return { skins, sheet };
}

function runB(cores, order, prm, seed) {
  const sheet = new Sheet(), skins = [], F = new Float32Array(N), gen = new Map();
  const tau = 0.5; let sid = 1000;
  const seen = [];
  for (const i of order) {
    const rng = rngFor(seed, i + 1, 22);
    const r = prm.reach * (0.6 + 1.1 * Math.pow(rng(), 2.2));
    const f = contribution(cores[i], r);
    for (let c = 0; c < N; c++) F[c] += f[c];
    seen.push(i);
    const P = resample(cores[i], 2);
    let seedCell = cellOf(P[0][0], P[0][1]);
    for (const p of P) { const c = cellOf(p[0], p[1]); if (F[c] > F[seedCell]) seedCell = c; }
    const comp = flood(F, tau, seedCell);
    const members = seen.filter(j => resample(cores[j], 3).some(p => comp[cellOf(p[0], p[1])]));
    let level = tau, mode = 'new';
    if (members.length > 1) {
      const g = Math.max(...members.map(j => gen.get(j) || 0)) + 1;
      members.forEach(j => gen.set(j, g));
      if (rng() < 0.15 + prm.dep * 0.6) {
        let mx = 0, mc = seedCell;
        for (let c = 0; c < N; c++) if (comp[c] && F[c] > mx) { mx = F[c]; mc = c; }
        level = Math.min(mx * 0.85, tau * (1.5 + 0.5 * g)); seedCell = mc; mode = 'inner';
      } else { level = tau * Math.pow(0.7, g); mode = 'ring'; }
    }
    const mask = flood(F, level, seedCell);
    const loop = contourLoop(F, level, mask);
    if (!loop || polyLen(loop) < 6) continue;
    const D = distField(sheet), nz = noise1(rng);
    const spacing = 3.5 + 8 * prm.loose, R = resample(loop, spacing);
    const [cx, cy] = centroid(R);
    let dests = R.map((p, k) => {
      const dx = p[0] - cx, dy = p[1] - cy, l = Math.hypot(dx, dy) || 1, j = nz(k * 0.3) * prm.dep * (3 + 6 * prm.loose);
      const fl = rng() < prm.dep * 0.06 ? 1 + rng() * 0.5 : 1;
      return [cx + dx * fl + dx / l * j, cy + dy * fl + dy / l * j];
    });
    // start where the new request is
    let k0 = 0, bd = 1e9;
    dests.forEach((p, k) => { const d = Math.hypot(p[0] - P[0][0], p[1] - P[0][1]); if (d < bd) { bd = d; k0 = k; } });
    dests = dests.slice(k0).concat(dests.slice(0, k0));
    const sk = walk(sheet, dests, ++sid, prm, rng, D);
    if (sk) skins.push({ core: i, mode, members: members.length, ...sk });
  }
  return { skins, sheet, field: F };
}

function transformCore(core, c, s, th, tx, ty) {
  const cs = Math.cos(th), sn = Math.sin(th);
  return core.map(([x, y]) => { const dx = (x - c[0]) * s, dy = (y - c[1]) * s; return [tx + dx * cs - dy * sn, ty + dx * sn + dy * cs]; });
}
function runC(cores, order, prm, seed) {
  const sheet = new Sheet(), skins = [], placed = [];
  let sid = 2000;
  for (const i of order) {
    const rng = rngFor(seed, i + 1, 33), D = distField(sheet);
    const core = resample(cores[i], 2), c0 = centroid(core);
    const need = s => (2.5 + 9 * prm.loose) * s * 0.9 + 1.4;
    let best = null;
    for (let k = 0; k < 260; k++) {
      let tx = c0[0], ty = c0[1], s = 1, th = 0;
      if (k > 0) {
        s = [1, 0.8, 0.65, 0.5, 0.38][Math.floor(rng() * 5)];
        th = (rng() - 0.5) * rad(80) * prm.dep;
        if (rng() < 0.55) { tx += (rng() + rng() + rng() - 1.5) * 50; ty += (rng() + rng() + rng() - 1.5) * 50; }
        else { tx = 10 + rng() * (W - 20); ty = 10 + rng() * (H - 20); }
      }
      const T = transformCore(core, c0, s, th, tx, ty);
      let fit = 1e9;
      for (const p of T) {
        if (p[0] < 6 || p[0] > W - 6 || p[1] < 6 || p[1] > H - 6) { fit = -1; break; }
        fit = Math.min(fit, D[cellOf(p[0], p[1])] - need(s));
      }
      if (fit <= 0) continue;
      const shift = Math.hypot(tx - c0[0], ty - c0[1]);
      const score = s * 30 - shift * prm.attend * 0.8 + Math.min(fit, 20) * 0.4 + rng() * 6;
      if (!best || score > best.score) best = { score, T, s, shift, c1: [tx, ty] };
    }
    if (best) {
      const sk = walk(sheet, ringDests(best.T, prm, rng, D, best.s), ++sid, prm, rng, D);
      placed.push({ core: i, T: best.T, s: best.s });
      if (sk) skins.push({ core: i, moved: best.shift > 3 || best.s < 1, tether: [c0, best.c1], placedCore: best.T, ...sk });
    } else if (placed.length) {
      // Nothing fits: answer an older core instead, drawn again at another carefulness.
      const old = placed[Math.floor(rng() * placed.length)];
      const alt = { ...prm, loose: clamp(1 - prm.loose + (rng() - 0.5) * 0.3, 0.05, 1) };
      const sk = walk(sheet, ringDests(old.T, alt, rng, D, old.s * 1.5), ++sid, alt, rng, D);
      if (sk) skins.push({ core: i, reread: old.core, tether: [c0, centroid(old.T)], ...sk });
      else skins.push({ core: i, reread: old.core, strokes: [], status: 'deferred', breaks: 0 });
    } else skins.push({ core: i, strokes: [], status: 'deferred', breaks: 0 });
  }
  return { skins, sheet };
}

function runProposal(prop, cores, prm, seed, reverse = false) {
  const order = cores.map((_, i) => i);
  if (reverse) order.reverse();
  const res = prop === 'B' ? runB(cores, order, prm, seed) : prop === 'C' ? runC(cores, order, prm, seed) : runA(cores, order, prm, seed);
  if (prop === 'C') res.D = distField(res.sheet);
  return res;
}

function stats(res) {
  const s = { skins: 0, closed: 0, open: 0, broken: 0, moved: 0, reread: 0, deferred: 0 };
  for (const k of res.skins) {
    if (k.status === 'deferred' || k.status === 'blocked') { s.deferred++; continue; }
    s.skins++; s[k.status]++;
    if (k.moved) s.moved++;
    if (k.reread !== undefined) s.reread++;
  }
  return s;
}

// ---------- core vocabularies for examples and population sheets ----------
function makeCore(type, L, x, y, a, rng) {
  const pts = [], n = Math.max(6, Math.round(L / 1.5));
  const ca = Math.cos(a), sa = Math.sin(a);
  const put = (u, v) => pts.push([x + u * ca - v * sa, y + u * sa + v * ca]);
  for (let k = 0; k <= n; k++) {
    const t = k / n, u = (t - 0.5) * L;
    if (type === 'arc') put(u, Math.sin(t * Math.PI) * L * 0.28);
    else if (type === 'hook') { const b = Math.max(0, t - 0.65) / 0.35; put(u * (1 - b * 0.8), -b * b * L * 0.35); }
    else if (type === 'zig') put(u, ((k % Math.max(2, Math.round(n / 5))) / Math.max(2, Math.round(n / 5)) - 0.5) * L * 0.22);
    else if (type === 'loop') { const th = t * Math.PI * 2 * 1.15; put(Math.cos(th) * L * 0.18 + u * 0.35, Math.sin(th) * L * 0.18); }
    else if (type === 'scrawl') put(u, Math.sin(t * 17 + rng() * 0.3) * L * 0.07 + Math.sin(t * 5) * L * 0.12);
    else put(u, 0);
  }
  return smoothPts(pts, 1).map(([px, py]) => [clamp(px, 4, W - 4), clamp(py, 4, H - 4)]);
}
function randomCores(seed) {
  const rng = mulberry32(seed * 7919 + 13), types = ['arc', 'hook', 'zig', 'loop', 'scrawl', 'line'];
  const n = 3 + Math.floor(rng() * 6), out = [];
  for (let k = 0; k < n; k++) {
    const L = 8 + 95 * Math.pow(rng(), 2.2);
    out.push(makeCore(types[Math.floor(rng() * types.length)], L, 30 + rng() * (W - 60), 25 + rng() * (H - 50), rng() * Math.PI * 2, rng));
  }
  return out;
}
function exampleCores() {
  const r = mulberry32(5);
  return [
    makeCore('arc', 90, 120, 95, -0.25, r),
    makeCore('hook', 38, 205, 70, 0.9, r),
    makeCore('zig', 55, 95, 150, 0.15, r),
    makeCore('loop', 26, 215, 150, 0.4, r),
    makeCore('line', 12, 60, 60, 1.2, r),
    makeCore('scrawl', 70, 170, 118, -0.6, r),
  ];
}

if (typeof module !== 'undefined') module.exports = { runProposal, stats, randomCores, exampleCores, makeCore, mulberry32, W, H };
