
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
    const cts = this.contours(S, Lx);
    // Keep the whole border state at every arrival: the history v5 draws from.
    if (prm.keepHistory) (this.snapshots = this.snapshots || []).push({ arrival: done.length, core: core.i, camp: core.camp, disregard: !!disregard, topo, contours: cts.map(c => ({ kind: c.kind, closed: c.closed, pts: c.pts })) });
    const cand = this.runs(cts, rng, D);
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
  if (prm.render === 'v5') prm.keepHistory = true;
  const cores = resolveCores(rawCores, prm, seed);
  const T = new Territory(prm, seed), done = [];
  T.order = arrivalOrder(cores, order);
  for (const i of T.order) { T.arrive(cores[i], cores, done); done.push(cores[i]); }
  if (prm.render === 'v5') T.v5(cores, rngFor(seed, 5151));
  else if (['wrap', 'wound', 'growth', 'auto'].includes(prm.render)) T.organic(cores);
  else T.volume(rngFor(seed, 991));
  const L = T.labels();
  return { lines: T.lines, cores, L, inkLen: T.inkLen, regions: T.regions, surf: T.surf, forms: T.forms, snapshots: T.snapshots || [], v5: T.v5info, T };
}

function tStats(res) {
  const s = { lines: res.lines.length, border: 0, outer: 0, interior: 0, restate: 0, hatch: 0, silhouette: 0, wrap: 0, wound: 0, growth: 0, broken: 0, disregard: 0 };
  for (const l of res.lines) { s[l.kind] = (s[l.kind] || 0) + 1; if (l.breaks) s.broken++; if (l.disregard) s.disregard++; }
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
