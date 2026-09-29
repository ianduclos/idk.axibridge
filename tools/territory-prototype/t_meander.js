
// ======================= meander: width from lines, history as traces =======================
// See docs/research/meander/synthesis-brief.md. The v2 territory is input only (a source of
// centrelines); none of its ink is drawn.
//  M1 migrate and remember: curvature-driven migration (Howard–Knutson upstream recurrence,
//     ω = −1, γ = 2.5), a neck editor (cut / refuse / stall), capture between channels, one
//     reversal, and a per-channel present time (heterochrony). Geometry only, no ink.
//  M2 bundle: each present centreline is drawn as 1–6 strands. Spread swells after the apex,
//     pinches at inflections, fans on the concave side; one firm strand holds the convex side.
//     A gap quantizer keeps sibling gaps out of the 0.6–1.3 mm "railway" zone.
//  M3 erode and keep: event-dated history, concave side only, drawn newest-first and clipped
//     where a later sweep passed; oxbows as open hooked arcs; abandoned reaches single and fading.
// Deviations from the brief: the meander spread is `band` (v2 owns `spread`); strands are exact
// geometry clipped against occupancy, not walkLine pursuits (the walker would scramble spacing).

const MEANDER_DEFAULTS = { source: 'territory', channels: 8, drift: 0.6, band: 1, history: 0.6, activity: 0.9, events: 2, white: 0, hetero: 0.6, search: 1, tangle: 1, work: 0.5, graft: 0.5, window: 0 };
// Round 3 page dials (0–1). Each fans out to the older keys; a recipe without them is unchanged.
const MEANDER_MACROS = { complexity: 0.5, drift: 0.6, band: 1, chaos: 0.5, accents: 0.5, bridges: 0.5, history: 0.6, density: 0, continue: 0.5, cover: 0.5, slash: 0.5, surprise: 0.5, ink: 40 };
function expandMacros(p) {
  const q = { ...p };
  if (p.complexity !== undefined) q.channels = Math.round(5 + 6 * clamp(p.complexity, 0, 1));
  if (p.chaos !== undefined) { const h = clamp(p.chaos, 0, 1); q.tangle = Math.min(1, 2 * h); q.search = 2 * h; q.events = Math.round(4 * h); q.hetero = 1.2 * h; }
  return q;
}
const MIG_E = 4;          // mm of displacement per unit R1 per step (calibrated at CP1)
const V_ABS = 0.075;      // absolute floor for a band's swell speed: p95 of lagged speed on seed 21's trunk (round 2 CP1)

const SHEET_F = { x0: 0, y0: 0, x1: W, y1: H };
function boxFilter(a, w) {
  const n = a.length, out = new Float64Array(n), h = Math.max(1, w >> 1);
  let s = 0, c = 0;
  for (let i = 0; i < Math.min(n, h); i++) { s += a[i]; c++; }
  for (let i = 0; i < n; i++) {
    if (i + h < n) { s += a[i + h]; c++; }
    if (i - h - 1 >= 0) { s -= a[i - h - 1]; c--; }
    out[i] = s / c;
  }
  return out;
}
function segDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy || 1, t = clamp(((px - ax) * dx + (py - ay) * dy) / l2, 0, 1);
  return Math.hypot(px - ax - dx * t, py - ay - dy * t);
}

// A(x,y): two or three broad blobs plus one sharp ridge; `contrast` 0 = flat 0.5.
function activityField(seed, contrast, F = SHEET_F) {
  const FW = F.x1 - F.x0, FH = F.y1 - F.y0;
  const r = rngFor(seed, 6160), cs = 5, gw = Math.ceil(FW / cs) + 1, gh = Math.ceil(FH / cs) + 1, g = new Float32Array(gw * gh);
  const blobs = [], nb = 2 + (r() < 0.5 ? 1 : 0);
  for (let k = 0; k < nb; k++) blobs.push({ x: F.x0 + 30 + r() * (FW - 60), y: F.y0 + 25 + r() * (FH - 50), s: 30 + r() * 45, w: k > 0 && r() < 0.35 ? -0.7 : 1 });
  const ra = r() * Math.PI, rl = 80 + 80 * r(), rx = F.x0 + 50 + r() * (FW - 100), ry = F.y0 + 40 + r() * (FH - 80), rw = 5 + 5 * r();
  const ax = rx - Math.cos(ra) * rl / 2, ay = ry - Math.sin(ra) * rl / 2, bx = rx + Math.cos(ra) * rl / 2, by = ry + Math.sin(ra) * rl / 2;
  let lo = 1e9, hi = -1e9;
  for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) {
    const x = F.x0 + i * cs, y = F.y0 + j * cs; let v = 0;
    for (const b of blobs) v += b.w * Math.exp(-((x - b.x) ** 2 + (y - b.y) ** 2) / (2 * b.s * b.s));
    const d = segDist(x, y, ax, ay, bx, by); v += 0.9 * Math.exp(-d * d / (2 * rw * rw));
    g[j * gw + i] = v; lo = Math.min(lo, v); hi = Math.max(hi, v);
  }
  for (let c = 0; c < g.length; c++) g[c] = 0.5 + ((g[c] - lo) / (hi - lo || 1) - 0.5) * contrast;
  return (x, y) => {
    const fx = clamp((x - F.x0) / cs, 0, gw - 1.001), fy = clamp((y - F.y0) / cs, 0, gh - 1.001), i = Math.floor(fx), j = Math.floor(fy), u = fx - i, v = fy - j;
    const c = j * gw + i;
    return (g[c] * (1 - u) + g[c + 1] * u) * (1 - v) + (g[c + gw] * (1 - u) + g[c + gw + 1] * u) * v;
  };
}

// ---- round 2: where the river actually worked ----
// Wk: accumulated migration speed of every snapshot on a 5 mm grid over the field F, blurred ~10 mm,
// normalised by its p98. The render field Ar = (1 - mu)·A + mu·Wk² puts weight where migration happened
// (A stays the simulation field). docs/research/meander2/synthesis-brief.md §1.1
function workMap(snaps, F) {
  const cs = 5, gw = Math.ceil((F.x1 - F.x0) / cs) + 1, gh = Math.ceil((F.y1 - F.y0) / cs) + 1;
  let g = new Float32Array(gw * gh);
  for (const s of snaps) for (let i = 0; i < s.pts.length; i++) {
    const x = Math.floor((s.pts[i][0] - F.x0) / cs), y = Math.floor((s.pts[i][1] - F.y0) / cs);
    if (x >= 0 && y >= 0 && x < gw && y < gh) g[y * gw + x] += s.speed[i] || 0;
  }
  for (let pass = 0; pass < 3; pass++) {
    const t = new Float32Array(gw * gh);
    for (let y = 0; y < gh; y++) for (let x = 0; x < gw; x++) {
      let v = 0, n = 0; for (let v2 = -1; v2 <= 1; v2++) for (let u = -1; u <= 1; u++) { const X = x + u, Y = y + v2; if (X >= 0 && Y >= 0 && X < gw && Y < gh) { v += g[Y * gw + X]; n++; } }
      t[y * gw + x] = v / n;
    }
    g = t;
  }
  const nz = Array.from(g).filter(v => v > 0).sort((a, b) => a - b), top = nz.length ? nz[Math.floor(nz.length * 0.98)] || 1 : 1;
  for (let c = 0; c < g.length; c++) g[c] = clamp(g[c] / top, 0, 1);
  const at = (x, y) => {
    const fx = clamp((x - F.x0) / cs, 0, gw - 1.001), fy = clamp((y - F.y0) / cs, 0, gh - 1.001), i = Math.floor(fx), j = Math.floor(fy), u = fx - i, v = fy - j, c = j * gw + i;
    return (g[c] * (1 - u) + g[c + 1] * u) * (1 - v) + (g[c + gw] * (1 - u) + g[c + gw + 1] * u) * v;
  };
  return { at, g, gw, gh, cs, F };
}
// Found window (round 2): the sheet is a frame chosen on a 1.6× field. Score: work centroid off-centre,
// empty ground 25–55 %, more work preferred; hard gates: 1–5 centreline crossings of the frame (0 is the
// old inset, more is an excerpt), top-decile work cut by ≤ 2 edges, a protagonist ≥ 3.5× the median;
// a zoomed frame (s < 1) needs ≥ 2 channels inside. Returns sim→sheet: p' = (p − o) / s.
function findWindow(Wk, polys, F, rng) {
  const { g, gw, gh, cs } = Wk, SW = gw + 1;
  const sat = f => { const a = new Float64Array(SW * (gh + 1)); for (let j = 0; j < gh; j++) { let row = 0; for (let i = 0; i < gw; i++) { row += f(g[j * gw + i], i, j); a[(j + 1) * SW + i + 1] = a[j * SW + i + 1] + row; } } return a; };
  const Sw = sat(v => v), Sx = sat((v, i) => v * (i + 0.5)), Sy = sat((v, i, j) => v * (j + 0.5)), Se = sat(v => v < 0.02 ? 1 : 0);
  const box = (a, i0, j0, i1, j1) => a[j1 * SW + i1] - a[j0 * SW + i1] - a[j1 * SW + i0] + a[j0 * SW + i0];
  const nz = Array.from(g).filter(v => v > 0.02).sort((a, b) => a - b); if (nz.length < 10) return null;
  const med = nz[Math.floor(nz.length / 2)], tdec = nz[Math.floor(nz.length * 0.9)];
  let best = null, bestW = 0;
  const cand = [];
  for (const sc of [1, 0.8, 0.65]) {
    const ww = W * sc, wh = H * sc, iw = Math.round(ww / cs), jh = Math.round(wh / cs);
    for (let oy = F.y0; oy + wh <= F.y1; oy += 15) for (let ox = F.x0; ox + ww <= F.x1; ox += 15) {
      const i0 = Math.round((ox - F.x0) / cs), j0 = Math.round((oy - F.y0) / cs), i1 = Math.min(gw, i0 + iw), j1 = Math.min(gh, j0 + jh);
      const work = box(Sw, i0, j0, i1, j1); if (work <= 0) continue;
      cand.push({ sc, ox, oy, i0, j0, i1, j1, work }); bestW = Math.max(bestW, work);
    }
  }
  for (const c of cand) {
    if (c.work < 0.3 * bestW) continue;
    const { i0, j0, i1, j1 } = c, cells = (i1 - i0) * (j1 - j0);
    const cx = box(Sx, i0, j0, i1, j1) / c.work, cy = box(Sy, i0, j0, i1, j1) / c.work;
    const d = Math.hypot(cx - (i0 + i1) / 2, cy - (j0 + j1) / 2) / Math.hypot(i1 - i0, j1 - j0);
    const a = d >= 0.15 && d <= 0.35 ? 1 : Math.exp(-(((d < 0.15 ? 0.15 - d : d - 0.35) / 0.08) ** 2));
    const ef = box(Se, i0, j0, i1, j1) / cells, b = ef >= 0.25 && ef <= 0.55 ? 1 : Math.exp(-(((ef < 0.25 ? 0.25 - ef : ef - 0.55) / 0.1) ** 2));
    // hard gates
    let hot = 0; for (const [ii0, jj0, ii1, jj1] of [[i0, j0, i1, j0 + 1], [i0, j1 - 1, i1, j1], [i0, j0, i0 + 1, j1], [i1 - 1, j0, i1, j1]]) { let h = false; for (let j = jj0; j < jj1 && !h; j++) for (let i = ii0; i < ii1; i++) if (g[j * gw + i] >= tdec) { h = true; break; } if (h) hot++; }
    if (hot > 2) continue;
    let peak = 0; for (let j = j0; j + 8 <= j1; j += 2) for (let i = i0; i + 8 <= i1; i += 2) peak = Math.max(peak, box(Sw, i, j, i + 8, j + 8) / 64);
    if (peak < 3.5 * med) continue;
    const X0 = c.ox, Y0 = c.oy, X1 = c.ox + W * c.sc, Y1 = c.oy + H * c.sc, inside = p => p[0] > X0 && p[0] < X1 && p[1] > Y0 && p[1] < Y1;
    let cross = 0, inCh = 0;
    for (const P of polys) { let k = 0, prev = null; for (const p of P) { const q = inside(p); if (q) k++; if (prev !== null && q !== prev) cross++; prev = q; } if (k > 0.5 * P.length) inCh++; }
    if (cross < 1 || cross > 5 || (c.sc < 1 && inCh < 2)) continue;
    const score = a * b * (0.5 + 0.5 * c.work / bestW) + 1e-6 * rng();
    if (!best || score > best.score) best = { s: c.sc, ox: c.ox, oy: c.oy, score, cross };
  }
  return best;
}
const renderField = (A, Wk, mu) => (x, y) => { const w = Wk.at(x, y); return (1 - mu) * A(x, y) + mu * w * w; };

// ---- seeding ----
function chainGraph(G, turnMax) {
  const used = new Uint8Array(G.edges.length), chains = [];
  const tangentOut = (eid, n) => { const P = edgeFrom(G, eid, n), k = Math.min(P.length - 1, 3); return Math.atan2(P[k][1] - P[0][1], P[k][0] - P[0][0]); };
  const extend = (pts, end) => {
    for (let tr = 0; tr < 4; tr++) {
      const node = G.nodes[end], m = pts.length; if (node.degree < 2 || m < 4) break;
      const inA = Math.atan2(pts[m - 1][1] - pts[m - 4][1], pts[m - 1][0] - pts[m - 4][0]);
      let best = null, bs = 1e9;
      for (const eid of node.edges) { if (used[eid]) continue; const t = Math.abs(wrap(tangentOut(eid, end) - inA)); if (t < bs) { bs = t; best = eid; } }
      if (best === null || bs > rad(turnMax)) break;
      used[best] = 1; pts = pts.concat(edgeFrom(G, best, end).slice(1)); end = otherEnd(G, best, end);
    }
    return pts;
  };
  for (const e of G.edges.slice().sort((a, b) => b.len - a.len || a.id - b.id)) {
    if (used[e.id]) continue; used[e.id] = 1;
    let pts = extend(e.pts.map(p => [p[0], p[1]]), e.b);
    pts = extend(pts.reverse(), e.a).reverse();
    chains.push(pts);
  }
  return chains;
}
// Cut a tail back until its last 40 mm turn by no more than `limit` degrees: some ends keep a hook, none spiral.
function uncoil(P, limit) {
  let Q = P;
  for (let guard = 0; guard < 40 && Q.length > 30; guard++) {
    let s = 0, t = 0;
    for (let i = Q.length - 2; i > 1 && s < 40; i--) {
      s += Math.hypot(Q[i + 1][0] - Q[i][0], Q[i + 1][1] - Q[i][1]);
      t += wrap(Math.atan2(Q[i + 1][1] - Q[i][1], Q[i + 1][0] - Q[i][0]) - Math.atan2(Q[i][1] - Q[i - 1][1], Q[i][0] - Q[i - 1][0]));
    }
    if (Math.abs(t) * 180 / Math.PI <= limit) break;
    Q = Q.slice(0, Q.length - Math.max(2, Math.round(Q.length * 0.04)));
  }
  return Q;
}
function trimToSheet(P, m, F = SHEET_F) { const r = trimRun(P, m, F); return P.slice(r[0], r[1] + 1); }
// [i0, i1] of the longest run of P inside F less a margin
function trimRun(P, m, F = SHEET_F) {
  const ok = p => p[0] > F.x0 + m && p[0] < F.x1 - m && p[1] > F.y0 + m && p[1] < F.y1 - m;
  let b0 = 0, b1 = -1, c0 = -1;
  for (let i = 0; i <= P.length; i++) {
    if (i < P.length && ok(P[i])) { if (c0 < 0) c0 = i; continue; }
    if (c0 >= 0 && i - 1 - c0 > b1 - b0) { b0 = c0; b1 = i - 1; }
    c0 = -1;
  }
  return [b0, b1];
}
function noiseWalk(rng, len, x, y, h, F = SHEET_F) {
  const nz = noise1(rng), ph = rng() * 100, pts = [[x, y]];
  for (let s = 0; s < len; s += 2) {
    h += nz(ph + s / 45) * 0.12;
    const cx = (F.x0 + F.x1) / 2 - x, cy = (F.y0 + F.y1) / 2 - y;           // steer home near the margin
    if (x < F.x0 + 25 || x > F.x1 - 25 || y < F.y0 + 22 || y > F.y1 - 22) h += clamp(wrap(Math.atan2(cy, cx) - h), -0.25, 0.25);
    x += Math.cos(h) * 2; y += Math.sin(h) * 2; pts.push([x, y]);
  }
  return pts;
}
// A faint low-frequency displacement so near-straight centrelines have curvature to grow from.
function wiggle(P, rng) {
  const nz = noise1(rng), ph = rng() * 100, lam = 18 + 22 * rng(), n = P.length;
  let s = 0;
  return P.map((p, i) => {
    if (i) s += Math.hypot(p[0] - P[i - 1][0], p[1] - P[i - 1][1]);
    const a = P[Math.max(0, i - 1)], b = P[Math.min(n - 1, i + 1)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, d = 1.6 * nz(ph + s / lam) * smooth(0, 10, Math.min(i, n - 1 - i));
    return [p[0] - (b[1] - a[1]) / l * d, p[1] + (b[0] - a[0]) / l * d];
  });
}
function crossings(P, Q) {
  let n = 0;
  for (let i = 1; i < P.length; i++) for (let j = 1; j < Q.length; j++) {
    const a = P[i - 1], b = P[i], c = Q[j - 1], d = Q[j];
    if (Math.max(a[0], b[0]) < Math.min(c[0], d[0]) || Math.max(c[0], d[0]) < Math.min(a[0], b[0]) || Math.max(a[1], b[1]) < Math.min(c[1], d[1]) || Math.max(c[1], d[1]) < Math.min(a[1], b[1])) continue;
    const o = (p, q, r) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
    if (o(a, b, c) !== o(a, b, d) && o(c, d, a) !== o(c, d, b)) n++;
  }
  return n;
}
function seedChannels(T, prm, rng, F = SHEET_F) {
  const nCh = clamp(Math.round(prm.channels), 2, 12), out = [];
  const mk = (cls, pts) => {
    const trunk = cls === 'trunk';
    return { id: out.length, cls, ds: trunk ? 2 : 1.2, lag: trunk ? 25 + 15 * rng() : 8 + 7 * rng(), kl: 1, neckW: trunk ? 5 : 3.5,
      pts: wiggle(resample(smoothPts(resample(pts, trunk ? 2 : 1.2), 2), trunk ? 2 : 1.2), rng), alive: true, speed: null, born: 0, parent: -1 };
  };
  let chains = [];
  if (prm.source === 'territory') {
    const L = T.labels(), polys = [];
    const inside = p => p[0] > 6 && p[0] < W - 6 && p[1] > 6 && p[1] < H - 6;
    for (const c of T.contours(T.S, L)) {
      let cur = [];
      for (const p of c.pts) { if (inside(p)) cur.push([p[0], p[1]]); else { if (cur.length > 8) polys.push(cur); cur = []; } }
      if (cur.length > 8) polys.push(cur);
    }
    chains = chainGraph(contourGraph(polys, 3.5), 110).map(P => {
      P = trimToSheet(P, 12);
      // an almost-closed chain opens: drop its last fifth
      if (P.length > 20 && Math.hypot(P[0][0] - P[P.length - 1][0], P[0][1] - P[P.length - 1][1]) < 15) { const k = Math.floor(P.length * (0.25 + 0.2 * rng())); P = P.slice(k).concat(P.slice(0, Math.floor(k * 0.3))).slice(0, Math.floor(P.length * 0.62)); }
      return P;
    }).filter(P => P.length > 10).sort((a, b) => polyLen(b) - polyLen(a));
  }
  const near = (P, Q, r) => { const h = pointHash(Q, r); let k = 0; for (const p of P) { const gx = Math.floor(p[0] / r), gy = Math.floor(p[1] / r); let f = false; for (let u = -1; u <= 1 && !f; u++) for (let v = -1; v <= 1 && !f; v++) for (const q of (h.get((gx + u) * 4096 + gy + v) || [])) if (Math.hypot(q[0] - p[0], q[1] - p[1]) < r) { f = true; break; } if (f) k++; } return k / P.length; };
  if (chains.length && polyLen(chains[0]) >= 60) out.push(mk('trunk', chains[0]));
  else {
    const FW = F.x1 - F.x0, FH = F.y1 - F.y0, a = rng() * Math.PI * 2, x = (F.x0 + F.x1) / 2 + Math.cos(a) * FW * 0.3 * rng(), y = (F.y0 + F.y1) / 2 + Math.sin(a) * FH * 0.3 * rng();
    out.push(mk('trunk', trimToSheet(noiseWalk(rng, 160 + 120 * rng(), x, y, rng() * Math.PI * 2, F), 12, F)));
  }
  // round 3 (brief §2.4): a second river at a different heading, crossing the first exactly once
  if (prm.complexity !== undefined && out.length) {
    const r2 = rngFor(T.seed, 6167);
    if (r2() < smooth(0.25, 0.85, prm.complexity)) {
      const tp = out[0].pts, m = tp[Math.floor(tp.length / 2)], e0 = tp[0], e1 = tp[tp.length - 1], th = Math.atan2(e1[1] - e0[1], e1[0] - e0[0]);
      for (let tries = 0; tries < 8; tries++) {
        const side = r2() < 0.5 ? 1 : -1, d = (0.35 + 0.25 * r2()) * W, x = m[0] - Math.sin(th) * d * side, y = m[1] + Math.cos(th) * d * side;
        const turn = (50 + 60 * r2()) * Math.PI / 180, h0 = th + (r2() < 0.5 ? turn : -turn);
        const toward = Math.sin(th) * side * Math.cos(h0) - Math.cos(th) * side * Math.sin(h0);   // heading · (−normal·side)
        const h = toward > 0 ? h0 : h0 + Math.PI;
        const P = trimToSheet(noiseWalk(r2, 180 + 120 * r2(), clamp(x, 20, W - 20), clamp(y, 20, H - 20), h, F), 12, F);
        if (polyLen(P) < 100 || crossings(P, tp) !== 1) continue;
        const c = mk('trunk', P); c.S0 = 5; c.second = true;
        // junction sprouts (§2.4, D3): two short minors start near the crossing, the seed-22 knot on purpose
        let X = null; for (let i = 1; i < c.pts.length && !X; i++) for (let j = 1; j < tp.length; j++) if (crossings([c.pts[i - 1], c.pts[i]], [tp[j - 1], tp[j]])) { X = { p: c.pts[i], i, j }; break; }
        if (!X || X.p[0] < 0.2 * W || X.p[0] > 0.8 * W || X.p[1] < 0.2 * H || X.p[1] > 0.8 * H) continue;   // r1 (F5): the crossing sits in the middle 60 %
        out.push(c);
        if (X) {
          out[0].crossAt = X.p; const rj = rngFor(T.seed, 6172);
          for (let k = 0; k < 2 && out.length < nCh; k++) {
            const host = rj() < 0.5 ? c.pts : tp, hi = host === tp ? X.j : X.i, q = clamp(hi + Math.round((rj() - 0.5) * 16), 1, host.length - 2);
            const hh = Math.atan2(host[q + 1][1] - host[q - 1][1], host[q + 1][0] - host[q - 1][0]) + (rj() < 0.5 ? 1 : -1) * (0.6 + 0.8 * rj());
            const S = trimToSheet(noiseWalk(rj, 40 + 50 * rj(), host[q][0] + Math.cos(hh) * 6, host[q][1] + Math.sin(hh) * 6, hh, F), 12, F);
            if (polyLen(S) >= 30) out.push(mk('minor', S));
          }
        }
        break;
      }
    }
  }
  // graft (round 2): below 1, only inherited minors that touch the trunk's neighbourhood are kept, a share g of
  // the minors; the rest sprout at the trunk's bends. graft 1 is round 1's territory topology exactly.
  const graft = prm.source === 'territory' ? clamp(prm.graft ?? 1, 0, 1) : 1;
  if (graft < 1 && out.length) { const tp = out[0].pts; chains = [chains[0], ...chains.slice(1).filter(P => near(P, tp, 25) > 0.15)]; }
  const inheritCap = graft < 1 ? 1 + Math.round(graft * (nCh - 1)) : nCh;
  for (const P0 of chains.slice(1)) {
    if (out.length >= nCh || out.length >= inheritCap) break;
    let P = P0; const len = polyLen(P); if (len < 30) continue;
    if (len > 120) { const k = Math.floor((P.length - 120) * rng()); P = P.slice(k, k + 121); }
    if (out.some(c => near(P, c.pts, 5) > 0.35)) continue;
    out.push(mk('minor', P));
  }
  // top up (and 'nothing'): minors sprout off the trunk
  const tr = out[0].pts; let trK = null;
  for (let tries = 0; out.length < nCh && tries < 12; tries++) {
    let i = 5 + Math.floor(rng() * Math.max(1, tr.length - 10));
    if (graft < 1) { if (!trK) { trK = curvatureOf(tr).map(Math.abs); } let tot = 0; for (let q = 5; q < tr.length - 5; q++) tot += trK[q] + 0.01; let u = rng() * tot; for (let q = 5; q < tr.length - 5; q++) { u -= trK[q] + 0.01; if (u <= 0) { i = q; break; } } }
    const p = tr[Math.min(i, tr.length - 2)], q = tr[Math.min(i + 1, tr.length - 1)];
    const h = Math.atan2(q[1] - p[1], q[0] - p[0]) + (rng() < 0.5 ? 1 : -1) * (0.6 + 0.8 * rng());
    const P = trimToSheet(noiseWalk(rng, 40 + 80 * rng(), p[0] + Math.cos(h) * 8, p[1] + Math.sin(h) * 8, h, F), 12, F);
    if (polyLen(P) < 35 || out.some(c => near(P, c.pts, 6) > 0.25)) continue;
    out.push(mk('minor', P));
  }
  out.forEach((c, i) => { c.id = i; c.maxLen = Math.min(c.cls === 'trunk' ? 460 : 230, 1.9 * polyLen(c.pts)); });
  return out;
}

// ---- M1: migration ----
function curvatureOf(P) {
  const n = P.length, k = new Float64Array(n);
  for (let i = 1; i < n - 1; i++) {
    const ax = P[i][0] - P[i - 1][0], ay = P[i][1] - P[i - 1][1], bx = P[i + 1][0] - P[i][0], by = P[i + 1][1] - P[i][1];
    k[i] = wrap(Math.atan2(by, bx) - Math.atan2(ay, ax)) / (((Math.hypot(ax, ay) + Math.hypot(bx, by)) / 2) || 1);
  }
  if (n > 2) { k[0] = k[1]; k[n - 1] = k[n - 2]; }
  let s = k;
  for (let p = 0; p < 2; p++) { const t = new Float64Array(n); for (let i = 0; i < n; i++) t[i] = (s[Math.max(0, i - 1)] + 2 * s[i] + s[Math.min(n - 1, i + 1)]) / 4; s = t; }
  return s;
}
function inflCount(k) { let c = 0, sg = 0; for (let i = 0; i < k.length; i++) { const s = k[i] > 0.004 ? 1 : k[i] < -0.004 ? -1 : 0; if (s && sg && s !== sg) c++; if (s) sg = s; } return c; }

function migrate(chans, A, prm, rng, F = SHEET_F) {
  const steps = Math.round(180 + 420 * prm.drift), ev = clamp(Math.round(prm.events), 0, 3);
  const cap = { cut: [0, 1, 2, 3][ev], refuse: [0, 1, 2, 2][ev], capture: [0, 1, 2, 2][ev] }, used = { cut: 0, refuse: 0, capture: 0 };
  const snaps = [], events = [], stalls = [], pairs = [];
  let rev = null;
  if (ev >= 1 && rng() < 0.5) {
    const ch = rng() < 0.6 ? 0 : Math.floor(rng() * chans.length), f0 = 0.1 + 0.4 * rng();
    rev = { ch, f0, f1: f0 + 0.25 + 0.15 * rng(), t: Math.round(steps * (0.55 + 0.2 * rng())) };
  }
  const stallW = (x, y) => { let d = 1e9; for (const s of stalls) { const dx = s[0] - x, dy = s[1] - y; if (dx >= 10 || dx <= -10 || dy >= 10 || dy <= -10) continue; d = Math.min(d, Math.hypot(dx, dy)); } return smooth(4, 10, d); };   // exact early-out: smooth(4,10,≥10) = 1
  const step = (ch, t) => {
    const P = ch.pts, n = P.length; if (n < 10) return;
    const kap = curvatureOf(P), R0 = new Float64Array(n), R1 = new Float64Array(n);
    for (let i = 0; i < n; i++) R0[i] = ch.kl * (0.25 + 1.15 * A(P[i][0], P[i][1])) * kap[i];
    const dec = Math.exp(-ch.ds / ch.lag);
    let num = 0, den = 0;
    for (let i = 0; i < n; i++) { num = R0[i] + dec * num; den = 1 + dec * den; R1[i] = -R0[i] + 2.5 * num / den; }
    if (rev && rev.ch === ch.id && t >= rev.t) {
      num = 0; den = 0; const i0 = Math.floor(rev.f0 * n), i1 = Math.min(n - 1, Math.floor(rev.f1 * n));
      for (let i = n - 1; i >= i0; i--) { num = R0[i] + dec * num; den = 1 + dec * den; if (i <= i1) R1[i] = -R0[i] + 2.5 * num / den; }
    }
    const sp = new Float32Array(n), lim = 0.5 * ch.ds, Q = P.map(p => p.slice());
    for (let i = 1; i < n - 1; i++) {
      // the downstream end tapers over 25 mm: the upstream-weighted rate otherwise piles up there and coils it
      const pin = smooth(0, 6, i) * smooth(0, 25 / ch.ds, n - 1 - i), x = P[i][0], y = P[i][1];
      const edge = smooth(6, 20, Math.min(x - F.x0, F.x1 - x, y - F.y0, F.y1 - y));
      const d = clamp(MIG_E * R1[i], -lim, lim) * pin * edge * (stalls.length ? stallW(x, y) : 1);
      const tx = P[i + 1][0] - P[i - 1][0], ty = P[i + 1][1] - P[i - 1][1], tl = Math.hypot(tx, ty) || 1;
      Q[i][0] = clamp(x + d * ty / tl, F.x0 + 6, F.x1 - 6); Q[i][1] = clamp(y - d * tx / tl, F.y0 + 6, F.y1 - 6);   // right normal = outward for κ > 0
      sp[i] = Math.abs(d);
    }
    ch.pts = Q; ch.speed = sp;
  };
  const snap = (ch, t) => { const k = curvatureOf(ch.pts); snaps.push({ ch: ch.id, t, pts: ch.pts.map(p => [p[0], p[1]]), speed: ch.speed ? Array.from(ch.speed) : ch.pts.map(() => 0), infl: inflCount(k) }); };
  const nearStall = (x, y) => stalls.some(s => Math.hypot(s[0] - x, s[1] - y) < 12);
  const findNecks = () => {
    const cell = 6, h = new Map(), key = (x, y) => Math.floor(x / cell) * 4096 + Math.floor(y / cell);
    chans.forEach((ch, ci) => ch.pts.forEach((p, i) => { if (i % 2) return; const k = key(p[0], p[1]); let b = h.get(k); if (!b) h.set(k, b = []); b.push(ci, i); }));
    const found = new Map();
    chans.forEach((ch, ci) => {
      if (!ch.alive) return;
      const n = ch.pts.length;
      for (let i = 6; i < n - 6; i += 2) {
        const p = ch.pts[i], gx = Math.floor(p[0] / cell), gy = Math.floor(p[1] / cell);
        for (let u = -1; u <= 1; u++) for (let v = -1; v <= 1; v++) {
          const b = h.get((gx + u) * 4096 + gy + v); if (!b) continue;
          for (let q = 0; q < b.length; q += 2) {
            const cj = b[q], j = b[q + 1], o = chans[cj], pk = ci < cj ? ci + ':' + cj : cj + ':' + ci;
            if (found.has(pk)) continue;
            if (cj === ci) { if ((j - i) * ch.ds < 40) continue; }
            else { if (o.alive && cj < ci) continue; if (j < 3 || j > o.pts.length - 4) continue; }
            const w = cj === ci ? ch.neckW : Math.max(ch.neckW, o.neckW);
            const d = Math.hypot(o.pts[j][0] - p[0], o.pts[j][1] - p[1]);
            if (d >= w || nearStall((p[0] + o.pts[j][0]) / 2, (p[1] + o.pts[j][1]) / 2)) continue;
            found.set(pk, { ci, i, cj, j });
          }
        }
      }
    });
    return [...found.values()];
  };
  const stall = (x, y, t, kind, a, b) => {
    stalls.push([x, y]);
    if (kind === 'refuse' && used.refuse < cap.refuse) { used.refuse++; events.push({ kind: 'refuse', ch: a, other: b, t, at: [x, y] }); if (a !== b) pairs.push([a, b]); }
  };
  const editor = (nk, t) => {
    const a = chans[nk.ci], b = chans[nk.cj], p = a.pts[nk.i], q = b.pts[nk.j], mx = (p[0] + q[0]) / 2, my = (p[1] + q[1]) / 2;
    if (nk.ci === nk.cj) {
      const loop = a.pts.slice(nk.i, nk.j + 1), c = centroid(loop);
      let od = 1e9; for (const o of chans) if (o !== a) for (let k = 0; k < o.pts.length; k += 3) od = Math.min(od, Math.hypot(o.pts[k][0] - c[0], o.pts[k][1] - c[1]));
      if (used.cut < cap.cut && od > 12 && A(c[0], c[1]) < 0.8) {
        used.cut++;
        a.pts = a.pts.slice(0, nk.i + 1).concat(a.pts.slice(nk.j));
        events.push({ kind: 'cutoff', ch: a.id, t, at: [mx, my], loop });
      } else stall(mx, my, t, 'refuse', a.id, a.id);
      return;
    }
    if (a.cls === 'trunk' && b.cls === 'trunk') { stalls.push([mx, my]); return; }   // round 3: two rivers hold their crossing, no event
    const trunk = a.cls === 'trunk' ? a : b.cls === 'trunk' ? b : null, minor = trunk === a ? b : a, m = trunk === a ? nk.j : nk.i;
    if (trunk && minor.alive && !minor.captured && used.capture < cap.capture && m > 10 && minor.pts.length - m > 12 && rng() < 0.7) {
      used.capture++;
      const up = minor.pts.slice(0, m + 1), down = minor.pts.slice(m + 2);
      minor.pts = up; minor.captured = true;
      const ab = { id: chans.length, cls: 'minor', ds: minor.ds, lag: minor.lag, kl: minor.kl, neckW: minor.neckW, pts: down, alive: false, abandoned: true, born: t, parent: minor.id, speed: null };
      chans.push(ab); pairs.push([trunk.id, minor.id], [minor.id, ab.id]);
      events.push({ kind: 'capture', ch: minor.id, other: trunk.id, t, at: [mx, my] });
      return;
    }
    stall(mx, my, t, 'refuse', a.id, b.id);
  };
  for (let t = 0; t <= steps; t++) {
    for (const ch of chans) if (ch.alive && !(ch.maxLen && t % 3 === 0 && polyLen(ch.pts) > ch.maxLen && (ch.full = true)) && !ch.full) step(ch, t);
    if (rev && t === rev.t) events.push({ kind: 'reversal', ch: rev.ch, t, at: chans[rev.ch].pts[Math.floor(chans[rev.ch].pts.length * (rev.f0 + rev.f1) / 2)] || [0, 0] });
    if (t % 8 === 0 || t === steps) for (const ch of chans) if (ch.alive) snap(ch, t);
    if (t % 5 === 0) { const edited = new Set(); for (const nk of findNecks()) { if (edited.has(nk.ci) || edited.has(nk.cj)) continue; edited.add(nk.ci).add(nk.cj); if (t < 15) { const p = chans[nk.ci].pts[nk.i], q = chans[nk.cj].pts[nk.j]; stalls.push([(p[0] + q[0]) / 2, (p[1] + q[1]) / 2]); } else editor(nk, t); } }
    if (t % 3 === 0) for (const ch of chans) if (ch.alive) ch.pts = resample(ch.pts, ch.ds);
    if (t % 6 === 0) for (const ch of chans) if (ch.alive) ch.pts = smoothPts(ch.pts, 1);
  }
  return { steps, snaps, events, pairs, rev };
}

// ---- M2: the bundle ----
function bundleGeom(ch, present, speed, A, prm, rng, loose, tg, chiF) {
  const C = catmullRom(resample(present, 2), 0.5), n = C.length; if (n < 30) return null;
  const nx = new Float64Array(n), ny = new Float64Array(n), th = new Float64Array(n);
  for (let i = 0; i < n; i++) { const a = C[Math.max(0, i - 2)], b = C[Math.min(n - 1, i + 2)]; th[i] = Math.atan2(b[1] - a[1], b[0] - a[0]); nx[i] = -Math.sin(th[i]); ny[i] = Math.cos(th[i]); }
  let kap = new Float64Array(n);
  for (let i = 0; i < n; i++) { const i0 = Math.max(0, i - 4), i1 = Math.min(n - 1, i + 4); kap[i] = wrap(th[i1] - th[i0]) / (((i1 - i0) * 0.5) || 1); }
  kap = boxFilter(kap, 16);
  // bend-scale sign: 60 mm majority, then sign runs shorter than 30 mm fold into their neighbours
  const kmaj = boxFilter(kap, 120), sgn = new Int8Array(n);
  for (let i = 0; i < n; i++) sgn[i] = kmaj[i] >= 0 ? 1 : -1;
  for (let pass = 0; pass < 3; pass++) {
    let i = 0;
    while (i < n) { let j = i; while (j + 1 < n && sgn[j + 1] === sgn[i]) j++; if (j - i < 60 && (i > 0 || j < n - 1)) for (let q = i; q <= j; q++) sgn[q] = -sgn[q]; i = j + 1; }
  }
  const infl = []; for (let i = 1; i < n; i++) if (sgn[i] !== sgn[i - 1]) infl.push(i);
  const dInf = new Float64Array(n);
  for (let i = 0; i < n; i++) { let d = 1e9; for (const q of infl) d = Math.min(d, Math.abs(q - i) * 0.5); dInf[i] = d; }
  // migration speed, lagged downstream so the swell sits after the apex
  const lagW = 8 + 7 * rng(), a = Math.exp(-0.5 / lagW), vl = new Float64Array(n);
  for (let i = 0; i < n; i++) { const v = speed.length ? speed[Math.round(i / (n - 1) * (speed.length - 1))] : 0; vl[i] = i ? a * vl[i - 1] + (1 - a) * v : v; }
  const vs = Array.from(vl).sort((x, y) => x - y), vlo = vs[Math.floor(n * 0.15)], vhiOwn = vs[Math.floor(n * 0.95)], vhi = Math.max(vhiOwn, V_ABS) + 1e-9;
  // a gentle arc (radius > 80 mm) earns at most a third of its swell: per-channel speed quantiles otherwise manufacture one
  const cg = new Float64Array(n); for (let i = 0; i < n; i++) cg[i] = smooth(0.012, 0.035, Math.abs(kap[i]));
  // S0: trunk 8; only the two most active minors get a band, the rest are single lines (Fable advice 1, §3)
  const trunk = ch.cls === 'trunk', S0 = ch.S0 || (trunk ? 8 : 1.4), Smax = trunk ? 9 : 5.5;
  const S = new Float64Array(n), b = new Float64Array(n), K = new Int8Array(n);
  let Kmax = 1;
  // meander3 r2: outside χ a channel is single-line, 3 or 5 strands (fat about one channel in three), so bends differ
  const capOut = chiF ? [1, 3, 3, 5, 5, 5][Math.floor(rng() * 6)] : 8;
  for (let i = 0; i < n; i++) {
    const dEnd = Math.min(i, n - 1 - i) * 0.5, Ai = A(C[i][0], C[i][1]);
    let s = clamp(S0 * (0.2 + 0.8 * Ai) * 1.7 * Math.pow(smooth(vlo, vhi, vl[i]), 0.8) * (0.35 + 0.65 * cg[i]) * prm.band, 0.3, Smax);
    s = 0.3 + (s - 0.3) * smooth(0, 6, dInf[i]) * smooth(0, 15, dEnd);
    S[i] = s; b[i] = sgn[i] * smooth(0, 6, dInf[i]);
    // a channel is one line or a band of ≥ 3: a pair is an outline at any gap
    const out3 = chiF && chiF(C[i][0], C[i][1]) < 0.5 && !(tg && tg.junc && tg.junc(C[i][0], C[i][1], ch.id));
    K[i] = s < 1.6 || (out3 && capOut === 1) ? 1 : clamp(1 + Math.round(s / 0.9), 3, out3 ? capOut : 8); Kmax = Math.max(Kmax, K[i]);
  }
  // strands fill the whole band: k = 0 is the firm core on the concave side, higher k walk toward
  // the convex edge and drop first as S falls; an inactive strand rides its inward neighbour, so
  // ends peel off and merge in rather than stopping (Fable advice 1, A2)
  const own = [], shared = noise1(rng), shared2 = noise1(rng), ph = rng() * 100;
  for (let k = 0; k < Kmax; k++) own.push(noise1(rng));
  const off = [], act = [], steady = new Float64Array(n).fill(1);
  if (chiF) for (let i = 0; i < n; i++) steady[i] = 0.45 + 0.55 * chiF(C[i][0], C[i][1]);   // round 3: the ragged edge steadies outside χ
  for (let k = 0; k < Kmax; k++) {
    const o = new Float64Array(n), ac = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      ac[i] = k === 0 || K[i] > k ? 1 : 0;
      const drift = steady[i] * 0.45 * loose.A * shared(ph + i * 0.5 / 30) + (0.03 + 0.04 * k) * S[i] * shared2(ph + i * 0.5 / 25);
      const mine = steady[i] * 0.25 * loose.A * own[k](ph + 37 * k + i * 0.5 / 10) + (k ? steady[i] * 0.11 * S[i] * own[k](ph + 211 + 53 * k + i * 0.5 / 18) : 0);
      o[i] = ac[i] ? drift + mine + b[i] * S[i] / 2 * (1 - 2 * Math.pow((k + 0.5) / K[i], 1.5)) : off[k - 1][i];
    }
    off.push(boxFilter(o, 20)); act.push(ac);
  }
  // ---- round 2: the tangle is the band's own strands losing rank, spacing and continuity along a
  //      stretch while keeping the channel's heading (coherence dial; meander2 brief §1.2)
  const coh = new Float64Array(n).fill(1), zones = [];
  if (tg && tg.on && tg.left > 0 && Kmax >= 3 && prm.tangle > 0) {
    const P = new Float64Array(n);
    for (let i = 0; i < n; i++) P[i] = (dInf[i] < 8 || Math.min(i, n - 1 - i) * 0.5 < 20) ? 0 : A(C[i][0], C[i][1]) * S[i] / Smax * vl[i] / vhi;
    const dips = []; let bi = -1, bv = 0;
    for (let i = 0; i < n; i++) if (P[i] > bv) { bv = P[i]; bi = i; }
    if (bi >= 0 && K[bi] >= 3) dips.push({ i: bi, depth: 1 });
    for (const e of tg.refuse.filter(e => e.ch === ch.id || e.other === ch.id)) {        // the plait: a half-depth dip at a refused neck
      let j = -1, jd = 12; for (let i = 0; i < n; i++) { const d = Math.hypot(C[i][0] - e.at[0], C[i][1] - e.at[1]); if (d < jd) { jd = d; j = i; } }
      if (j >= 0 && K[j] >= 3 && P[j] > 0 && !dips.some(d => Math.abs(d.i - j) < 80)) dips.push({ i: j, depth: 0.5 });
    }
    const R3 = prm.chaos !== undefined;
    for (const d of dips.slice(0, Math.min(2, tg.left))) {
      // meander2 r1: 20–45 mm read as nothing; meander3 r1 (Fable F1): 59–114 mm × 2 read as one stamp, so 25–55 mm × 1
      let L = R3 ? Math.round((10 + 12 * tg.rng() + 6 * A(C[d.i][0], C[d.i][1])) / 0.5) : Math.round((18 + 30 * tg.rng() + 20 * A(C[d.i][0], C[d.i][1])) / 0.5);
      L = Math.max(L, Math.round(3 * 1.6 * S[d.i] / 0.5 / 2));
      let i0 = Math.max(0, d.i - L), i1 = Math.min(n - 1, d.i + L), Lm = L, Lp = L;
      if (prm.chaos > 0.5 && d.depth === 1) {   // round 3: a long tangle that runs out toward the nearer end and thins
        L = Math.round((30 + 20 * tg.rng()) / 0.5);
        if (d.i < n - 1 - d.i) { Lm = Math.round(1.5 * L); Lp = L; } else { Lm = L; Lp = Math.round(1.5 * L); }
        i0 = Math.max(0, d.i - Lm); i1 = Math.min(n - 1, d.i + Lp);
      } else if (R3) {   // the knot sits ≥ 25 mm from either end: slide it inward (r2: dropping it left most cells tidy)
        if (n < 2 * L + 101) continue;
        const ci = clamp(d.i, 50 + L, n - 51 - L); d.i = ci; i0 = ci - L; i1 = ci + L; Lm = L; Lp = L;
      }
      const depth = d.depth * clamp(prm.tangle, 0, 1) / 0.6;
      for (let i = i0; i <= i1; i++) { const Li = i < d.i ? Lm : Lp; coh[i] = Math.min(coh[i], 1 - Math.min(0.95, depth * 0.5 * (1 + Math.cos(Math.PI * (i - d.i) / Li)))); }
      zones.push({ ch: ch.id, i0, i1, depth }); tg.left--;
    }
  }
  if (zones.length) {
    for (let k = 0; k < Kmax; k++) {
      const wz = noise1(tg.rng), lam = prm.chaos !== undefined ? 12 + 18 * tg.rng() : 12 + 13 * tg.rng(), ph2 = tg.rng() * 100;
      for (const z of zones) {
        for (let i = z.i0; i <= z.i1; i++) {
          const w = 1 - coh[i]; if (w <= 0) continue;
          const env = (1.0 * S[i] + 1.2) * (1 + 0.6 * w);
          off[k][i] = coh[i] * off[k][i] + w * env * wz(ph2 + i * 0.5 / lam);
          if (w > 0.3 && (prm.chaos === undefined || k < 4)) act[k][i] = 1;                                    // dropped strands revive
        }
        const seg = boxFilter(off[k].slice(z.i0, z.i1 + 1), 8); for (let i = z.i0; i <= z.i1; i++) off[k][i] = seg[i - z.i0];
      }
    }
    // spacing stop: an outer strand riding within 0.35 mm of a sibling for > 8 mm lets go
    for (const z of zones) for (let k = 1; k < Kmax; k++) {
      let run = 0;
      for (let i = z.i0; i <= z.i1; i++) {
        if (!act[k][i]) { run = 0; continue; }
        let near = false; for (let q = 0; q < k; q++) if (act[q][i] && Math.abs(off[q][i] - off[k][i]) < 0.35) { near = true; break; }
        run = near ? run + 1 : 0; if (run > 16) act[k][i] = 0;
      }
    }
  }
  const inZ = i => zones.some(z => i >= z.i0 && i <= z.i1);
  // exactly-two-strand pairs at 0.6–3 mm (the railway), over the channel's length
  let dead = 0, tot = 0;
  for (let i = 0; i < n; i += 2) { tot++; if (K[i] === 2 || (Kmax > 1 && act[1][i] && !(Kmax > 2 && act[2][i]))) { const g = Math.abs(off[1][i] - off[0][i]); if (g > 0.6 && g < 3) dead++; } }
  // pieces: the core stays continuous; strands k ≥ 1 break into 30–70 mm pieces with 3–9 mm gaps,
  // breaks kept ≥ 8 mm from the inward neighbour's
  const strands = [], breaksOf = [], cover = [];
  for (let k = 0; k < Kmax; k++) {
    const brk = [], cv = new Int32Array(n).fill(-1);
    let i = 0;
    while (i < n) {
      if (!act[k][i]) { i++; continue; }
      let j = i; while (j + 1 < n && act[k][j + 1]) j++;
      let a0 = i + (k ? Math.round((1 + 4 * rng()) * 2) : 0);
      while (a0 < j) {
        const zoned = inZ(a0);
        let len = zoned ? Math.round((10 + 15 * rng()) * 2) : k ? Math.round((30 + 40 * rng()) * (1 - 0.07 * k) * (0.55 + 0.45 * cg[a0]) * 2) : j - a0;
        if (k === 0 && !zoned) { const z = zones.find(z => z.i0 > a0 && z.i0 <= j); if (z) len = z.i0 - a0; }
        let e = Math.min(j, a0 + len);
        if (zoned) { for (let t = 0; t < 4 && strands.some(q => q.k !== k && (Math.abs(q.i1 - e) < 8 || Math.abs(q.i0 - a0) < 8)); t++) e = Math.min(j, e + 6); }
        if (k && e < j && (breaksOf[k - 1] || []).some(q => Math.abs(q - e) < 16)) e = Math.min(j, e + 20);
        if (e - a0 >= 16) {
          const pts = []; for (let q = a0; q <= e; q++) { pts.push([C[q][0] + nx[q] * off[k][q], C[q][1] + ny[q] * off[k][q]]); cv[q] = strands.length; }
          strands.push({ k, i0: a0, i1: e, pts, side: Math.sign(off[k][Math.floor((a0 + e) / 2)]) || 1, zoned: inZ(Math.floor((a0 + e) / 2)) });
        }
        brk.push(e); a0 = e + (inZ(e) ? Math.round((2 + 4 * rng()) * 2) : Math.round((3 + 6 * rng()) * (2 - cg[Math.min(e, n - 1)]) * 2));
      }
      i = j + 1;
    }
    breaksOf.push(brk); cover.push(cv);
  }
  // longest run of one piece as the convex-most active strand
  let edgeRun = 0, runId = -1, run = 0;
  for (let i = 0; i < n; i++) {
    let id = -1; for (let k = Kmax - 1; k >= 0; k--) if (cover[k][i] >= 0) { id = cover[k][i]; break; }
    if (Kmax >= 3 && K[i] >= 3 && id >= 0 && id === runId) run++; else { run = 0; runId = id; }
    edgeRun = Math.max(edgeRun, run * 0.5);
  }
  // width ratio away from the pinches
  const Sv = []; for (let i = 0; i < n; i++) if (dInf[i] > 6 && Math.min(i, n - 1 - i) > 30) Sv.push(S[i]);
  Sv.sort((x, y) => x - y);
  const ratio = Sv.length > 10 ? Sv[Math.floor(Sv.length * 0.9)] / Sv[Math.floor(Sv.length * 0.1)] : 1;
  let rail = 0, banded = 0; for (let i = 0; i < n; i++) if (K[i] >= 3) { banded++; if (cg[i] < 0.3) rail++; }
  return { C, nx, ny, th, S, b, strands, zones, dead, tot, ratio, Kmax, edgeRun, vhiOwn, railFrac: banded ? rail / banded : 0, len: n * 0.5, Kfrac3: K.reduce((x, v) => x + (v >= 3 ? 1 : 0), 0) / n };
}

// Hook of 2–5 mm curling toward `toward` (a direction vector) from the end of a stroke.
function hookFrom(P, toward, rng, curl = 0.35) {
  const m = P.length; if (m < 3) return null;
  const e = P[m - 1], p = P[Math.max(0, m - 4)], tx = e[0] - p[0], ty = e[1] - p[1];
  const sgn = Math.sign(tx * toward[1] - ty * toward[0]) || 1, len = 2 + 3 * rng(), out = [[e[0], e[1]]];
  let a = Math.atan2(ty, tx), x = e[0], y = e[1];
  for (let t = 0; t < len; t += 0.5) { a += sgn * curl; x += Math.cos(a) * 0.5; y += Math.sin(a) * 0.5; out.push([x, y]); }
  return out;
}

Territory.prototype.meander = function (cores) {
  const prm = expandMacros({ ...MEANDER_DEFAULTS, ...this.prm }), seed = this.seed;
  const F = prm.window ? { x0: -0.3 * W, y0: -0.3 * H, x1: 1.3 * W, y1: 1.3 * H } : SHEET_F;
  const A0 = activityField(seed, prm.activity, F);
  const rM = rngFor(seed, 6161); let rB = rngFor(seed, 6162); const rH = rngFor(seed, 6163), rE = rngFor(seed, 6164);
  const chans = seedChannels(this, prm, rM, F);
  const sim = migrate(chans, A0, prm, rM, F);
  const { steps, snaps, events } = sim;
  // heterochrony: each channel's present is its own moment; the widest pair differ by ≥ 40 % when hetero is high
  const hetero = clamp(prm.hetero, 0, 1), live = chans.filter(c => !c.abandoned);
  live.forEach(c => { c.tDraw = steps; });
  if (hetero > 0 && live.length > 1) {
    const order = live.map((c, i) => ({ c, u: rE() })).sort((a, b) => a.u - b.u || a.c.id - b.c.id);
    order.forEach((o, i) => { const u = i === 0 ? 0 : i === order.length - 1 ? 1 : o.u; o.c.tDraw = Math.round(steps * (1 - 0.55 * hetero * u)); });
  }
  const snapAt = (id, t) => { let best = null; for (const s of snaps) if (s.ch === id && s.t <= t && (!best || s.t > best.t)) best = s; return best; };
  // found window: choose the frame on the field, then carry everything into sheet millimetres
  let win = { s: 1, ox: 0, oy: 0, score: 0, cross: 0 };
  if (prm.window) {
    const polys = chans.map(c => c.abandoned ? c.pts : (snapAt(c.id, c.tDraw) || {}).pts).filter(Boolean);
    win = findWindow(workMap(snaps, F), polys, F, rngFor(seed, 6166)) || { s: 1, ox: 0, oy: 0, score: 0, cross: 0 };
    const tf = p => [(p[0] - win.ox) / win.s, (p[1] - win.oy) / win.s];
    for (const sn of snaps) { sn.pts = sn.pts.map(tf); sn.speed = sn.speed.map(v => v / win.s); }
    for (const e of events) { if (e.at) e.at = tf(e.at); if (e.loop) e.loop = e.loop.map(tf); }
    for (const c of chans) c.pts = c.pts.map(tf);
  }
  const A = prm.window ? (x, y) => A0(win.ox + x * win.s, win.oy + y * win.s) : A0;
  const mTrim = prm.window ? 3 : 10;
  for (const c of chans) {
    if (c.abandoned) { const par = chans[c.parent]; c.drawn = par.tDraw >= c.born; c.present = c.pts; c.presentSpeed = []; continue; }
    const s = snapAt(c.id, c.tDraw); c.drawn = !!s;
    if (s) { const [i0, i1] = trimRun(s.pts, mTrim); c.present = uncoil(s.pts.slice(i0, i1 + 1), 60 + 90 * rE()); c.presentSpeed = s.speed.slice(i0, i0 + c.present.length); if (c.present.length < 10) c.drawn = false; }
  }
  const Wk = workMap(snaps, { x0: 0, y0: 0, x1: W, y1: H }), Ar = renderField(A, Wk, clamp(prm.work, 0, 1));
  const hands = makeHands(seed, { sway: prm.sway ?? 1, overshoot: prm.overshoot ?? 1, lifts: prm.lifts ?? 1, tremor: prm.tremor ?? 1 });
  const loose = hands[0], firm = hands[1];
  const strandHand = { ...loose, A: loose.A * 0.3, lift: 0, over: 0 }, edgeHand = { ...firm, lift: 0 };

  // ---- ink sheet with lineage ----
  const sheet = new Sheet(), erased = new Sheet(), lin = new Map(), rel = new Set();
  for (const [a, b] of sim.pairs) { rel.add(a + ':' + b); rel.add(b + ':' + a); }
  for (const c of chans) if (c.parent >= 0) { rel.add(c.id + ':' + c.parent); rel.add(c.parent + ':' + c.id); }
  sheet.related = (a, b) => { const x = lin.get(a), y = lin.get(b); return x !== undefined && y !== undefined && (x === y || rel.has(x + ':' + y)); };
  let sid = 10; const newId = ch => { const id = ++sid; lin.set(id, ch); return id; };
  const out = []; let hooksAt = [];
  // Draw a hand-made stroke into the sheet, cut where it meets unrelated ink (or erased ground).
  const calm = { ...firm, A: firm.A * 0.4, over: 0.5, lift: 0.05, tremor: 0.01 };
  const calmed = (P, hand) => {
    let m = 0, k = 0; for (let i = 0; i < P.length; i += 4) { m += chi(P[i][0], P[i][1]); k++; } m = k ? m / k : 0;
    const h = { ...hand }; for (const f of ['A', 'lift', 'tremor']) h[f] = calm[f] + (hand[f] - calm[f]) * m; return h;
  };
  const put = (P, ch, hand, rng, o = {}) => {
    const id = newId(ch), pieces = [];
    if (r3 && !o.keepHand) hand = calmed(P, hand);
    for (const Q of handLine(P, hand, rng)) {
      let cur = [], s = 0, startT = false;
      for (let i = 0; i < Q.length; i++) {
        const p = Q[i]; if (i) s += Math.hypot(p[0] - Q[i - 1][0], p[1] - Q[i - 1][1]);
        let h = o.cross ? (p[0] < MARGIN || p[0] > W - MARGIN || p[1] < MARGIN || p[1] > H - MARGIN ? 'edge' : 0) : sheet.hit(p[0], p[1], id, s, false);
        if (h === 'self') h = 0;
        if (!h && o.erase && erased.owner[cellOf(p[0], p[1])]) h = 'erased';
        if (h) { if (cur.length > 1) pieces.push({ pts: cur, startT, endT: h !== 'edge' }); cur = []; startT = h !== 'edge'; continue; }
        cur.push(p); sheet.mark(p[0], p[1], id, s, 0.4);
      }
      if (cur.length > 1) pieces.push({ pts: cur, startT, endT: false });
    }
    return pieces.filter(pc => polyLen(pc.pts) > 3);
  };
  const addHook = (pc, toward, rng, ch = -1) => {
    const e = pc.pts[pc.pts.length - 1], atJ = r3 && junc && junc(e[0], e[1], ch, 8);   // a junction hook is the seed-22 drip: v6 spacing and curl
    if (hooksAt.some(h => Math.hypot(h[0] - e[0], h[1] - e[1]) < (r3 && !atJ ? 45 : 25))) return null;
    const hk = r3 ? hookFrom(pc.pts, toward, rng, atJ ? 0.35 : 0.2 + 0.25 * rng()) : hookFrom(pc.pts, toward, rng); if (hk) hooksAt.push(e); return hk;
  };
  const ink = { all: 0, chaos: 0 };
  const emit = (kind, strokes, extra) => {
    if (!strokes.length) return;
    for (const st of strokes) { const L = polyLen(st), q = st[Math.floor(st.length / 2)]; ink.all += L; if (chi(q[0], q[1]) > 0.5) ink.chaos += L; }
    out.push({ core: -1, kind, strokes, ...extra });
  };

  // ---- M2: present bundles ----
  { const ms = chans.filter(c => c.cls === 'minor' && !c.abandoned && c.drawn && c.present && c.present.length > 10).map(c => ({ c, a: c.present.reduce((x, p) => x + Ar(p[0], p[1]), 0) / c.present.length })).sort((x, y) => y.a - x.a || x.c.id - y.c.id);
    ms.forEach((m, i) => { m.c.S0 = i < 2 ? 4 : 1.4; });
    // meander3 r1 (F5): a banded minor that never meets the trunk reads as a second drawing
    const tp0 = chans[0].present; if (prm.chaos !== undefined && tp0) { const h = pointHash(tp0, 6); for (const m of ms) if (m.c.S0 === 4 && !m.c.present.some(p => { const gx = Math.floor(p[0] / 6), gy = Math.floor(p[1] / 6); for (let u = -1; u <= 1; u++) for (let v = -1; v <= 1; v++) for (const q of (h.get((gx + u) * 4096 + gy + v) || [])) if (Math.hypot(q[0] - p[0], q[1] - p[1]) < 6) return true; return false; })) m.c.S0 = 1.4; } }
  const geo = new Map(); this._geo = geo; let dead = 0, tot = 0; const tangleZones = [];
  let junc = null;
  const bundles = (presentOf, chiF) => {
    const rT = rngFor(seed, 6165), tg = { junc, rng: rT, on: rT() >= 0.2, left: prm.chaos !== undefined ? 1 : 2, refuse: events.filter(e => e.kind === 'refuse') };
    for (const c of chans) {
      if (!c.drawn || c.abandoned || !c.present || c.present.length < 10) continue;
      const g = bundleGeom(c, presentOf(c), c.presentSpeed, Ar, prm, rB, loose, tg, chiF);
      if (g) { geo.set(c.id, g); dead += g.dead; tot += g.tot; tangleZones.push(...g.zones); }
    }
  };
  bundles(c => c.present);
  // ---- round 3 (brief §2.1): the chaos field χ, centred on the tangle zones (else the busiest ground).
  //      Outside it the centreline is pre-smoothed, the band edge steadies and the hand calms, so the
  //      chaos is concentrated in one or two places. Recipes without `chaos` (pre-round-3) skip all of it.
  const r3 = prm.chaos !== undefined, chaosD = r3 ? clamp(prm.chaos, 0, 1) : 0, chiC = [];
  let chi = () => 0;
  if (r3) {
    const rX = rngFor(seed, 6168);
    if (chaosD > 0) {
      const nC = chaosD > 0.6 ? 2 : 1;   // one place of chaos by default, two when the dial is high
      if (chans[0].crossAt) chiC.push({ x: chans[0].crossAt[0], y: chans[0].crossAt[1], r: 20 + 15 * rX() });
      for (const z of tangleZones.slice().sort((p, q) => q.depth - p.depth).slice(0, nC - chiC.length)) { const g = geo.get(z.ch), q = g.C[Math.round((z.i0 + z.i1) / 2)]; chiC.push({ x: q[0], y: q[1], r: 20 + 15 * rX() }); }
      if (!chiC.length) {
        let best = null; for (let y = 25; y < H - 25; y += 5) for (let x = 25; x < W - 25; x += 5) { const a = Ar(x, y); if (!best || a > best.a) best = { x, y, a }; }
        if (best) chiC.push({ x: best.x, y: best.y, r: 20 + 15 * rX() });
      }
    }
    chi = (x, y) => { let m = 0; for (const c of chiC) { const d = Math.hypot(x - c.x, y - c.y); if (d < c.r) m = Math.max(m, smooth(c.r, 0.4 * c.r, d)); } return m; };
    // second pass on pre-smoothed centrelines, same streams as the first
    geo.clear(); dead = 0; tot = 0; tangleZones.length = 0; rB = rngFor(seed, 6162);
    // meander4 (Ian: "i stopped seeing these sexy shapes"): no band cap within 12 mm of another channel,
    // so restatement piles up at junctions as in v6 and his first sketch
    const jp = []; for (const c of chans) if (c.drawn && !c.abandoned && c.present) for (let i = 0; i < c.present.length; i += 2) jp.push([c.present[i][0], c.present[i][1], c.id]);
    const jh = pointHash(jp, 12);
    junc = (x, y, id, r = 12) => { const gx = Math.floor(x / 12), gy = Math.floor(y / 12); for (let u = -1; u <= 1; u++) for (let v = -1; v <= 1; v++) for (const q of (jh.get((gx + u) * 4096 + gy + v) || [])) if (q[2] !== id && Math.hypot(q[0] - x, q[1] - y) < r) return true; return false; };
    bundles(c => { const P = resample(c.present, 2), Ps = smoothPts(P, 6); return P.map((p, i) => { const w = junc(p[0], p[1], c.id) ? 1 : chi(p[0], p[1]);   // junctions keep their cusps (the seed-22 drip)
      return [Ps[i][0] + (p[0] - Ps[i][0]) * w, Ps[i][1] + (p[1] - Ps[i][1]) * w]; }); }, chi);
  }
  // white channel: the trunk's bundle is withheld; its strip is a wall nobody drew
  const trunkG = geo.get(0);
  const traceCount = ch => snaps.filter(s => s.ch === ch && events.some(e => e.ch === ch && Math.abs(e.t - s.t) <= 16)).length;
  const white = !!trunkG && prm.white > 0 && (prm.white >= 1 || (rE() < prm.white && traceCount(0) >= 2));
  if (white) { lin.set(1, -1); trunkG.C.forEach((p, i) => { if (i % 2 === 0) sheet.mark(p[0], p[1], 1, 0, Math.max(2, trunkG.S[i] / 2)); }); events.push({ kind: 'white', ch: 0, t: steps, at: trunkG.C[Math.floor(trunkG.C.length / 2)] }); }
  const byTrunkFirst = [...geo.keys()].sort((a, b) => a - b);
  for (const id of byTrunkFirst) {
    const g = geo.get(id), c = chans[id];
    g.C.forEach((p, i) => { if (i % 2 === 0) erased.mark(p[0], p[1], 1, 0, g.S[i] / 2 + 1); });
    if (white && id === 0) continue;
    const strokes = [];
    for (const st of g.strands) {
      const mid = st.pts[Math.floor(st.pts.length / 2)], cross = st.zoned || Ar(mid[0], mid[1]) > 0.72;
      const pieces = put(st.pts, id, st.k === 0 ? (rB() < 0.5 ? { ...edgeHand, over: 0 } : edgeHand) : strandHand, rB, { cross });
      for (const pc of pieces) {
        strokes.push(pc.pts);
        if (pc.endT && st.k === 0 && polyLen(pc.pts) > 15 && (!r3 || rB() < 0.75 || junc(pc.pts[pc.pts.length - 1][0], pc.pts[pc.pts.length - 1][1], id, 8))) { const q = Math.min(st.i1, st.i0 + pc.pts.length); const hk = addHook(pc, [-g.nx[q] * st.side, -g.ny[q] * st.side], rB, id); if (hk) strokes.push(hk); }
      }
      // the downstream end of the convex strand usually curls inward
      if (st.k === 0 && st.i1 >= g.C.length - 40 && pieces.length && rB() < 0.3) {
        const last = pieces[pieces.length - 1], q = g.C.length - 1, sg = rB() < 0.5 ? 1 : -1;
        const hk = addHook(last, [g.nx[q] * sg, g.ny[q] * sg], rB, id); if (hk) strokes.push(hk);
      }
    }
    emit('strand', strokes, { ch: id, t: c.tDraw });
  }

  // ---- round 3 (brief §2.2): accents. Beside a sharp bend near the chaos, 3–5 stated arcs on the convex
  //      side: uneven gaps, lengths growing outward, each leaning downstream, so they neither nest nor ring.
  const accents = [];
  if (r3 && prm.accents > 0 && chiC.length) {
    const rA = rngFor(seed, 6169), nA = Math.min(2, Math.round(3 * clamp(prm.accents, 0, 1))), sites = [];
    for (const [id, g] of geo) {
      const n = g.C.length, kp = new Float64Array(n);
      for (let i = 6; i < n - 6; i++) kp[i] = wrap(g.th[i + 6] - g.th[i - 6]) / 6;          // rad per mm
      for (let i = 20; i < n - 20; i++) {
        const a = Math.abs(kp[i]); if (a < 1 / 14 || a < Math.abs(kp[i - 1]) || a < Math.abs(kp[i + 1])) continue;
        let i0 = i, i1 = i; while (i0 > 1 && Math.abs(kp[i0 - 1]) > a * 0.4) i0--; while (i1 < n - 2 && Math.abs(kp[i1 + 1]) > a * 0.4) i1++;
        const turn = Math.abs(wrap(g.th[i1] - g.th[i0])) * 180 / Math.PI; if (turn < 55 || turn > 150 || junc(g.C[i][0], g.C[i][1], id, 5) || g.S.slice(Math.max(0, i0 - 20), i1 + 21).some(v => v >= 1.6) || tangleZones.some(z => z.ch === id && i >= z.i0 - 10 && i <= z.i1 + 10)) continue;
        const p = g.C[i], dc = Math.min(...chiC.map(c => Math.hypot(p[0] - c.x, p[1] - c.y))); sites.push({ id, i, i0, i1, a, far: dc > 60, sg: Math.sign(kp[i]), c: chiC.findIndex(c => Math.hypot(p[0] - c.x, p[1] - c.y) === dc) });
      }
    }
    sites.sort((x, y) => y.a - x.a || x.id - y.id || x.i - y.i);
    const byC = new Set(); let far = 0;
    for (const pass of [0, 1]) for (const st of sites) {   // r1: the far pass put arcs on every bend
      if (accents.length >= nA) break;
      if (st.far !== (pass === 2) || (pass === 2 && far >= 1)) continue;   // near the chaos first; at most one elsewhere
      if (pass === 0 && byC.has(st.c)) continue;
      const g = geo.get(st.id), p = g.C[st.i];
      if (accents.some(q => Math.hypot(q.at[0] - p[0], q.at[1] - p[1]) < 30)) continue;
      const cnt = 3 + Math.floor(2 * rA()), set = [0.6, 0.9, 1.5];
      let gaps;
      for (let t = 0; t < 20; t++) {
        const pool = set.slice().sort(() => rA() - 0.5); gaps = []; for (let j = 0; j < cnt - 1; j++) gaps.push(j < 3 ? pool[j] : set[Math.floor(rA() * 3)]);
        const m = gaps.reduce((x, y) => x + y, 0) / gaps.length, cv = Math.sqrt(gaps.reduce((x, y) => x + (y - m) ** 2, 0) / gaps.length) / m;
        const mono = gaps.every((x, j) => !j || x >= gaps[j - 1]) || gaps.every((x, j) => !j || x <= gaps[j - 1]);
        if (cv >= 0.3 && (!mono || gaps.length < 3)) break;
        if (t === 19) gaps = gaps.map((x, j) => j % 2 ? 1.5 : 0.6);
      }
      const lean = 0.1 + 0.1 * rA(), half = Math.min(14, (st.i1 - st.i0) / 2),   // ≤ 7 mm core: a stated arc, not a ruled run
        mid = (st.i0 + st.i1) / 2, dir = st.id === 0 || rA() < 0.5 ? 1 : -1;
      const nx = i => -st.sg * g.nx[i], ny = i => -st.sg * g.ny[i];                          // convex side
      const arcs = []; let d = g.S[st.i] / 2 + 0.8, cover = 0, samp = 0;
      for (let j = 0; j < cnt; j++) {
        if (j) d += gaps[j - 1];
        const h = half * (0.9 + 0.25 * j) + 4, c0 = mid + dir * j * Math.max(3, lean * h * 2);   // ≥ 1.5 mm of lean per arc
        const a0 = Math.max(1, Math.round(c0 - h)), a1 = Math.min(g.C.length - 2, Math.round(c0 + h)), P = [];
        for (let i = a0; i <= a1; i++) { const taper = Math.min(1, (i - a0) / 8, (a1 - i) / 8); P.push([g.C[i][0] + nx(i) * d * (0.7 + 0.3 * taper), g.C[i][1] + ny(i) * d * (0.7 + 0.3 * taper)]); }
        if (j === cnt - 1) for (let q = 0; q < P.length; q += 3) { samp++; const o = sheet.owner[cellOf(P[q][0], P[q][1])]; if (o && lin.get(o) !== st.id) cover++; }
        arcs.push(P);
      }
      if (samp && cover / samp > 0.3) continue;
      // the outermost arc is broken once
      const last = arcs[arcs.length - 1], cut = Math.floor(last.length * (0.3 + 0.4 * rA())), gapN = Math.round((1 + rA()) * 2);
      arcs.splice(arcs.length - 1, 1, last.slice(0, cut), last.slice(cut + gapN));
      const hand = { ...firm, A: firm.A * 0.3, tremor: 0, over: 0, lift: 0 }, strokes = [];
      for (const P of arcs) if (P.length > 4) for (const pc of put(P, st.id, hand, rA, { cross: true, keepHand: true })) strokes.push(pc.pts);
      // centre spread: curvature centres of each arc's middle (guard against bullseye / tree rings)
      const cen = arcs.slice(0, cnt - 1).map(P => { const q = Math.floor(P.length / 2), A0 = P[Math.max(0, q - 6)], B0 = P[q], C0 = P[Math.min(P.length - 1, q + 6)];
        const ax = B0[0] - A0[0], ay = B0[1] - A0[1], bx = C0[0] - B0[0], by = C0[1] - B0[1], den = 2 * (ax * by - ay * bx) || 1e-9;
        const ux = ((ax * ax + ay * ay) * by - (bx * bx + by * by) * ay) / den, uy = ((bx * bx + by * by) * ax - (ax * ax + ay * ay) * bx) / den; return [A0[0] + ux, A0[1] + uy]; });
      let spread = 0; for (const u of cen) for (const v of cen) spread = Math.max(spread, Math.hypot(u[0] - v[0], u[1] - v[1]));
      const gm = gaps.reduce((x, y) => x + y, 0) / gaps.length, gcv = Math.sqrt(gaps.reduce((x, y) => x + (y - gm) ** 2, 0) / gaps.length) / gm;
      if (st.far) far++;
      accents.push({ ch: st.id, at: p, far: st.far, n: cnt, spread: +spread.toFixed(1), gapCv: +gcv.toFixed(2) }); byC.add(st.c);
      emit('accent', strokes, { ch: st.id, t: chans[st.id].tDraw });
    }
  }

  // ---- a second register: 1–3 single-line reaches in busy ground are restated 2–5 times,
  //      each pass drifting on its own and disagreeing with the others (Ian's sketch; review r1 #4)
  const searchSpots = [];
  if (prm.search > 0) {
    // 2–3 patches of lognormal size: the largest gets the most passes (review r2 #4; brief §1.4)
    const cand = [], inZone = (id, i) => (tangleZones || []).some(z => z.ch === id && i >= z.i0 - 20 && i <= z.i1 + 20);
    for (const [id, g] of geo) for (let i = 30; i < g.C.length - 30; i += 20) { const p = g.C[i]; if (g.S[i] < 3 && Ar(p[0], p[1]) > 0.5 && !inZone(id, i) && (!r3 || chi(p[0], p[1]) > 0.3)) cand.push({ id, i, band: g.S[i] >= 1.6, a: Ar(p[0], p[1]) + 0.3 * rE() }); }
    cand.sort((x, y) => y.a - x.a || x.id - y.id || x.i - y.i);
    const want = r3 ? Math.round((1 + (rE() < 0.5 ? 1 : 0)) * Math.min(1, prm.search)) : Math.round((2 + (rE() < 0.5 ? 1 : 0)) * prm.search);
    let onBand = 0;
    for (const c of cand) {
      if (searchSpots.length >= want) break;
      if (r3 && ink.chaos > (0.10 + 0.15 * chaosD) * ink.all) break;
      if (c.band && onBand >= 1) continue;
      const g = geo.get(c.id), p = g.C[c.i];
      if (searchSpots.some(q => Math.hypot(q[0] - p[0], q[1] - p[1]) < 35)) continue;
      searchSpots.push(p); if (c.band) onBand++;
      const gauss = Math.sqrt(-2 * Math.log(1 - rE())) * Math.cos(2 * Math.PI * rE());
      const halfMm = clamp(8 * Math.exp(0.6 * gauss), 6, r3 ? 25 : 40), half = Math.round(halfMm * 2), passes = Math.min(r3 ? 4 : 9, 2 + Math.floor(5 * rE() * halfMm / 40)), strokes = [];
      for (let r = 0; r < passes; r++) {
        const nz = noise1(rE), ph = rE() * 100, amp = 0.6 + 1.4 * rE(), bias = (rE() - 0.5) * 1.6;
        const i0 = clamp(c.i - half + Math.round((rE() - 0.5) * 20), 0, g.C.length - 1), i1 = clamp(c.i + half + Math.round((rE() - 0.5) * 20), 0, g.C.length - 1);
        const P = []; for (let q = i0; q <= i1; q++) { const d = bias + amp * nz(ph + q * 0.5 / 15); P.push([g.C[q][0] + g.nx[q] * d, g.C[q][1] + g.ny[q] * d]); }
        for (const pc of put(P, c.id, { ...loose, lift: 0.4 }, rE, { cross: true })) strokes.push(pc.pts);
      }
      emit('search', strokes, { ch: c.id, t: chans[c.id].tDraw });
    }
  }

  // ---- round 3 (brief §2.3): bridges. Where lines of unrelated channels cross, or a line's end points at
  //      another, a calm tangent-continuous curve joins them: a fillet in the corner of a crossing (A1) or a
  //      continuation that bends and lands along the other line (A3). Few, and never where the ink is thick.
  const bridges = [];
  if (r3 && prm.bridges > 0) {
    const rG = rngFor(seed, 6170), bd = clamp(prm.bridges, 0, 1);
    const nB = Math.round(bd * (1 + 2 * rG())), capInk = (0.03 + 0.05 * bd) * ink.all;
    const idx = new Map(), SI = [];
    for (const e of out) for (const st of e.strokes) {
      const P = resample(st, 1); if (P.length < 4) continue;
      const si = SI.length; SI.push({ P, ch: e.ch, kind: e.kind });
      P.forEach((p, i) => { const a = P[Math.max(0, i - 2)], b = P[Math.min(P.length - 1, i + 2)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, k = Math.floor(p[0] / 2) * 4096 + Math.floor(p[1] / 2); let bb = idx.get(k); if (!bb) idx.set(k, bb = []); bb.push({ si, i, x: p[0], y: p[1], tx: (b[0] - a[0]) / l, ty: (b[1] - a[1]) / l }); });
    }
    const nearest = (x, y, r, ok) => { let best = null, d2 = r * r; const gx = Math.floor(x / 2), gy = Math.floor(y / 2), R = Math.ceil(r / 2); for (let u = -R; u <= R; u++) for (let v = -R; v <= R; v++) for (const q of (idx.get((gx + u) * 4096 + gy + v) || [])) { const d = (q.x - x) ** 2 + (q.y - y) ** 2; if (d < d2 && ok(q)) { d2 = d; best = q; } } return best; };
    const foreign = (a, b) => a !== b && !rel.has(a + ':' + b);
    const chOf = (x, y) => { if (x < 0 || y < 0 || x >= W || y >= H) return -2; const o = sheet.owner[cellOf(x, y)]; return o ? lin.get(o) : -1; };
    const inkDisc = (x, y, r) => { let c = 0, t = 0; for (let u = -r; u <= r; u++) for (let v = -r; v <= r; v++) { if (u * u + v * v > r * r) continue; t++; if (chOf(x + u, y + v) >= 0) c++; } return c / t; };
    const hermite = (P, tP, Q, tQ, k) => { const L = Math.hypot(Q[0] - P[0], Q[1] - P[1]), m = Math.max(4, Math.round(L / 0.5)), h = k * L, B = []; for (let j = 0; j <= m; j++) { const t = j / m, t2 = t * t, t3 = t2 * t, a = 2 * t3 - 3 * t2 + 1, b = t3 - 2 * t2 + t, c = -2 * t3 + 3 * t2, d = t3 - t2; B.push([a * P[0] + b * h * tP[0] + c * Q[0] + d * h * tQ[0], a * P[1] + b * h * tP[1] + c * Q[1] + d * h * tQ[1]]); } return B; };
    const along = (q, sg, mm) => { const P = SI[q.si].P, j = clamp(q.i + sg * Math.round(mm), 1, P.length - 2); if (Math.abs(j - q.i) < mm * 0.7) return null; const a = P[j - 1], b = P[j + 1], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1; return { p: P[j], t: [sg * (b[0] - a[0]) / l, sg * (b[1] - a[1]) / l] }; };
    // candidate sites from stroke ends: X (a foreign line within 2.5 mm: the corner of a crossing) and E (the end's ray meets one 8–40 mm on)
    const cands = [];
    SI.forEach((S, si) => {
      if (S.kind !== 'strand' || S.P.length < 15) return;
      for (const end of [0, 1]) {
        const P = end ? S.P : S.P.slice().reverse(), n = P.length, e = P[n - 1], a = P[n - 4], l = Math.hypot(e[0] - a[0], e[1] - a[1]) || 1, t = [(e[0] - a[0]) / l, (e[1] - a[1]) / l];
        const qx = nearest(e[0], e[1], 2.5, q => foreign(S.ch, SI[q.si].ch));
        if (qx) { const dot = t[0] * qx.tx + t[1] * qx.ty; if (Math.abs(dot) < Math.cos(rad(25))) cands.push({ kind: 'fillet', si, P, t, q: qx, at: [qx.x, qx.y] }); continue; }
        for (let s2 = 3; s2 <= 40; s2++) {
          const x = e[0] + t[0] * s2, y = e[1] + t[1] * s2, c = chOf(x, y);
          if (c === -2 || c === S.ch) break;
          if (c < 0) continue;
          if (!foreign(S.ch, c) || s2 < 8) break;
          const q = nearest(x, y, 3, q => SI[q.si].ch === c);
          if (q && Math.abs(t[0] * q.tx + t[1] * q.ty) <= Math.sin(rad(45)) + 0.25) cands.push({ kind: 'cont', si, P, t, q, s: s2, at: [(e[0] + x) / 2, (e[1] + y) / 2] });
          break;
        }
      }
    });
    const check = (B, chA, chB) => {
      const R = resample(B, 1); if (R.length < 4) return false;
      let turn = 0, kmax = 0, cross = 0, prev = -1;
      for (let i = 1; i < R.length - 1; i++) { const d = wrap(Math.atan2(R[i + 1][1] - R[i][1], R[i + 1][0] - R[i][0]) - Math.atan2(R[i][1] - R[i - 1][1], R[i][0] - R[i - 1][0])); turn += d; kmax = Math.max(kmax, Math.abs(d)); }
      if (kmax > 1 / 3 || Math.abs(turn) > Math.PI) return false;
      for (let i = 0; i < R.length; i++) {
        const p = R[i]; if (p[0] < 3 || p[1] < 3 || p[0] > W - 3 || p[1] > H - 3) return false;
        if (i < 3 || i > R.length - 4) continue;
        const c = chOf(p[0], p[1]), f = c >= 0 && c !== chA && c !== chB; if (f && !prev) cross++; prev = f ? 1 : 0;
      }
      return cross === 0;
    };
    const bean = (B, P, q, sg) => {   // bridge + 15 mm of each host nearly closing on 30–400 mm²
      const hostB = []; for (let j = 0; j <= 40; j++) { const r = along(q, sg, j + 1); if (r) hostB.push(r.p); }
      const poly = P.slice(Math.max(0, P.length - 41)).concat(B, hostB); if (poly.length < 6) return false;
      const f = poly[0], l = poly[poly.length - 1]; if (Math.hypot(f[0] - l[0], f[1] - l[1]) > 8) return false;
      let A2 = 0; for (let i = 0; i < poly.length; i++) { const u = poly[i], v = poly[(i + 1) % poly.length]; A2 += u[0] * v[1] - v[0] * u[1]; }
      const area = Math.abs(A2) / 2; return area >= 30 && area <= 1200;
    };
    const hand = { ...firm, A: firm.A * 0.5, tremor: 0, lift: 0, over: 0 };
    let used = 0, echoN = 0; const busy = [...hooksAt, ...searchSpots], rE6 = rngFor(seed, 6171);
    while (bridges.length < nB && cands.length) {
      let bi = -1, bs = 0;
      cands.forEach((c, i) => {
        if (c.dead) return;
        if (chi(c.at[0], c.at[1]) > 0.4) { c.dead = true; return; }
        if (bridges.some(b => Math.hypot(b.at[0] - c.at[0], b.at[1] - c.at[1]) < 40 || b.kind === c.kind)) { c.dead = true; return; }
        if (c.cover === undefined) c.cover = inkDisc(Math.round(c.at[0]), Math.round(c.at[1]), 10);
        if (c.cover > 0.25) { c.dead = true; return; }
        const rare = [...busy, ...bridges.map(b => b.at)].some(b => Math.hypot(b[0] - c.at[0], b[1] - c.at[1]) < 30) ? 0.3 : 1;
        const sc = (0.3 + Ar(c.at[0], c.at[1])) * rare * (1 - c.cover) * (c.kind === 'cont' ? 1 : 0.9) + 0.01 * rG();
        if (sc > bs) { bs = sc; bi = i; }
      });
      if (bi < 0) break;
      const c = cands[bi]; c.dead = true;
      const chA = SI[c.si].ch, chB = SI[c.q.si].ch, u = rG(), k = 0.35 + 0.2 * u;
      let B = null, sg = 1, P0, tP, dist;
      if (c.kind === 'fillet') {
        // corner of a crossing: back along A, out along B on the acute side
        const L = 8 + 10 * rG(), n = c.P.length; P0 = c.P[Math.max(0, n - 1 - Math.round(L))];
        const dA = [P0[0] - c.q.x, P0[1] - c.q.y], lA = Math.hypot(dA[0], dA[1]) || 1;
        sg = (dA[0] * c.q.tx + dA[1] * c.q.ty) / lA > 0 ? 1 : -1;            // the acute sector
        tP = [-dA[0] / lA, -dA[1] / lA]; dist = L;
      } else {
        // continuation: leave along the end's heading, land along the other line 0.4–0.9 × the gap further on
        sg = (c.t[0] * c.q.tx + c.t[1] * c.q.ty) >= 0 ? 1 : -1;
        P0 = c.P[c.P.length - 1]; tP = c.t; dist = c.s * (0.4 + 0.5 * rG());
      }
      const r = along(c.q, sg, dist); if (!r) continue;
      B = hermite(P0, tP, r.p, r.t, k);
      if (c.kind === 'cont' && rG() < 0.5) B = B.slice(0, Math.max(4, B.length - Math.round((1 + 2 * rG()) * 2)));   // stops short
      if (!check(B, chA, chB) || bean(B, c.P, c.q, sg)) continue;
      const L = polyLen(B); if (used + L > capInk || (c.kind === 'cont' && L > 35)) continue;
      const strokes = []; for (const pc of put(B, chA, hand, rG, { cross: true, keepHand: true })) strokes.push(pc.pts);
      if (!strokes.length) continue;
      used += L; B.forEach(p => erased.mark(p[0], p[1], 1, 0, 1.2));
      // echoes (A6): 1–3 parallel traces beside it, each landing somewhere else along the other line
      let echoes = 0;
      if (echoN < 2 && rE6() < 0.3) {
        const want = Math.min(2 - echoN, 1), side = rE6() < 0.5 ? 1 : -1, nP = [-tP[1] * side, tP[0] * side], lens = [L];
        let d = 0, prevGap = 0;
        for (let j = 0; j < want; j++) {
          let gap; do { gap = 0.9 + 1.3 * rE6(); } while (prevGap && Math.abs(gap - prevGap) / prevGap < 0.35); prevGap = gap; d += gap;
          const rr = along(c.q, sg, Math.max(3, dist + (rE6() < 0.5 ? -1 : 1) * (5 + 10 * rE6()) * (j + 1) * 0.7)); if (!rr) continue;
          const Pj = [P0[0] + nP[0] * d, P0[1] + nP[1] * d], Qj = [rr.p[0] + nP[0] * d * 0.3, rr.p[1] + nP[1] * d * 0.3];
          const Bj = hermite(Pj, tP, Qj, rr.t, k * (0.9 + 0.2 * rE6())), Lj = polyLen(Bj);
          if (lens.some(x => Math.abs(x - Lj) / Math.max(x, Lj) < 0.15) || !check(Bj, chA, chB) || used + Lj > capInk) continue;
          const pcs = put(Bj, chA, hand, rE6, { cross: true, keepHand: true }); if (!pcs.length) continue;
          for (const pc of pcs) strokes.push(pc.pts);
          lens.push(Lj); used += Lj; echoes++; echoN++; Bj.forEach(p => erased.mark(p[0], p[1], 1, 0, 1.2));
        }
      }
      bridges.push({ kind: c.kind, at: c.at, a: chA, b: chB, mm: Math.round(L), echoes });
      emit('bridge', strokes, { ch: chA, t: chans[chA] ? chans[chA].tDraw : steps });
    }
    bridges.ink = used; bridges.cap = capInk;
  }

  // ---- M3: history (event-dated, concave side, displacement thresholds) ----
  const kept = [];
  for (const [id, g] of geo) {
    const c = chans[id], evT = events.filter(e => e.ch === id || e.other === id).map(e => e.t);
    let prevInfl = -1;
    const cands = [];
    for (const s of snaps) { if (s.ch !== id) continue; const flip = prevInfl >= 0 && s.infl !== prevInfl; prevInfl = s.infl; if (s.t < c.tDraw - 8 && (flip || evT.some(t => Math.abs(t - s.t) <= 16))) cands.push(s); }
    cands.sort((a, b) => b.t - a.t);
    const cHash = new Map(), ck = (x, y) => Math.floor(x / 8) * 4096 + Math.floor(y / 8);
    g.C.forEach((p, i) => { if (i % 2) return; const k = ck(p[0], p[1]); let bb = cHash.get(k); if (!bb) cHash.set(k, bb = []); bb.push(i); });
    let keptPts = [];
    for (const s of cands) {
      const mid = s.pts[Math.floor(s.pts.length / 2)];
      if (rH() > prm.history * 1.4 * Ar(mid[0], mid[1]) ** 2) continue;
      const thr = 0.6 + 3.4 * rH(), P = resample(s.pts, 1), kh = pointHash(keptPts, 4);
      const keep = P.map(p => {
        const gx = Math.floor(p[0] / 8), gy = Math.floor(p[1] / 8); let bi = -1, bd = 24;
        for (let u = -3; u <= 3; u++) for (let v = -3; v <= 3; v++) for (const i of (cHash.get((gx + u) * 4096 + gy + v) || [])) { const d = Math.hypot(g.C[i][0] - p[0], g.C[i][1] - p[1]); if (d < bd) { bd = d; bi = i; } }
        if (bi < 0 || Math.abs(g.b[bi]) < 0.2 || g.S[bi] < 1.6 || bd < thr) return false;
        if (((p[0] - g.C[bi][0]) * g.nx[bi] + (p[1] - g.C[bi][1]) * g.ny[bi]) * g.b[bi] <= 0) return false;
        const hx = Math.floor(p[0] / 4), hy = Math.floor(p[1] / 4);
        for (let u = -1; u <= 1; u++) for (let v = -1; v <= 1; v++) for (const q of (kh.get((hx + u) * 4096 + hy + v) || [])) if (Math.hypot(q[0] - p[0], q[1] - p[1]) < thr) return false;
        return true;
      });
      const runs = []; let i = 0;
      while (i < P.length) {
        if (!keep[i]) { i++; continue; }
        let j = i; while (j + 1 < P.length && keep[j + 1]) j++;
        let a0 = i;
        while (j - a0 >= 15) { const L = Math.min(j - a0, 15 + Math.floor(45 * rH())); runs.push(P.slice(a0, a0 + L + 1)); a0 += L + 2 + Math.floor(6 * rH()); }
        i = j + 1;
      }
      if (runs.length) { kept.push({ ch: id, t: s.t, runs }); keptPts = keptPts.concat(runs.flat()); if (kept.filter(k => k.ch === id).length >= 4) break; }
    }
  }
  // tree-ring guard: ≥ 4 evenly spaced traces along a concave normal → drop the middle one
  const ringTest = () => {
    const tp = []; kept.forEach((k, ki) => k.runs.forEach(r => r.forEach(p => tp.push([p[0], p[1], ki]))));
    const h = pointHash(tp, 2); let fired = null;
    for (const [id, g] of geo) {
      for (let i = 30; i < g.C.length - 30; i += 10) {
        if (Math.abs(g.b[i]) < 0.5) continue;
        const sg = Math.sign(g.b[i]), hits = [];
        for (let d = 0.5; d <= 20; d += 0.5) {
          const x = g.C[i][0] + g.nx[i] * sg * d, y = g.C[i][1] + g.ny[i] * sg * d, gx = Math.floor(x / 2), gy = Math.floor(y / 2);
          let ki = -1; for (let u = -1; u <= 1 && ki < 0; u++) for (let v = -1; v <= 1 && ki < 0; v++) for (const q of (h.get((gx + u) * 4096 + gy + v) || [])) if (Math.hypot(q[0] - x, q[1] - y) < 0.6) { ki = q[2]; break; }
          if (ki >= 0 && (!hits.length || d - hits[hits.length - 1][0] > 0.8)) hits.push([d, ki]);
        }
        if (hits.length >= 4) {
          const gaps = hits.slice(1).map((hh, q) => hh[0] - hits[q][0]), m = gaps.reduce((x, y) => x + y, 0) / gaps.length;
          const cv = Math.sqrt(gaps.reduce((x, y) => x + (y - m) ** 2, 0) / gaps.length) / (m || 1);
          if (cv < 0.35) { fired = hits[Math.floor(hits.length / 2)][1]; break; }
        }
      }
      if (fired !== null) break;
    }
    return fired;
  };
  let rings = 0;
  for (let pass = 0; pass < 3; pass++) { const f = ringTest(); if (f === null) break; rings++; kept.splice(f, 1); }
  const ringStill = ringTest() !== null;

  // history items newest-first: traces, oxbows, abandoned reaches
  const items = kept.map(k => ({ kind: 'trace', t: k.t, k }));
  let oxDirs = [];
  for (const e of events) if (e.kind === 'cutoff' && chans[e.ch].tDraw >= e.t && chans[e.ch].drawn) items.push({ kind: 'oxbow', t: e.t, e });
  for (const c of chans) if (c.abandoned && c.drawn) items.push({ kind: 'abandoned', t: c.born, c });
  items.sort((a, b) => b.t - a.t || (a.kind < b.kind ? -1 : 1));
  for (const it of items) {
    if (it.kind === 'trace') {
      const strokes = [];
      for (const r of it.k.runs) {
        for (const pc of put(r, it.k.ch, loose, rH, { erase: true })) {
          strokes.push(pc.pts);
          if (pc.endT && !r3) { const g = geo.get(it.k.ch), e = pc.pts[pc.pts.length - 1]; const c0 = g.C[Math.floor(g.C.length / 2)]; const hk = addHook(pc, [c0[0] - e[0], c0[1] - e[1]], rH); if (hk) strokes.push(hk); }
        }
      }
      for (const r of it.k.runs) r.forEach(p => erased.mark(p[0], p[1], 1, 0, 1.2));
      emit('trace', strokes, { ch: it.k.ch, t: it.t });
    } else if (it.kind === 'oxbow') {
      let L = resample(it.e.loop, 0.5); if (L.length < 30) continue;
      const c = centroid(L), dir = Math.atan2(it.e.at[1] - c[1], it.e.at[0] - c[0]);
      if (oxDirs.some(d => Math.abs(wrap(d - dir)) < rad(60))) continue;
      oxDirs.push(dir);
      const a0 = Math.round((2 + 3 * rH()) * 2), a1 = Math.round((2 + 3 * rH()) * 2);
      L = L.slice(a0, L.length - a1); if (L.length < 20) continue;
      { const keep = Math.floor(L.length * (0.55 + 0.25 * rH())), k0 = rH() < 0.5 ? 0 : L.length - keep; L = L.slice(k0, k0 + keep); }
      const strokes = [];
      for (const pc of put(L, it.e.ch, loose, rH, { erase: true })) strokes.push(pc.pts);
      const toC = p => [c[0] - p[0], c[1] - p[1]];
      if (strokes.length) {
        const f = strokes[0], l = strokes[strokes.length - 1];
        const h1 = hookFrom(f.slice().reverse(), toC(f[0]), rH), h2 = hookFrom(l, toC(l[l.length - 1]), rH);
        if (h1) strokes.push(h1); if (h2) strokes.push(h2);
      }
      if (rH() < 0.3) {
        const n = L.length, s0 = Math.floor(n * 0.15 * rH()), s1 = Math.min(n - 1, s0 + Math.floor(n * (0.4 + 0.3 * rH()))), off = (1.5 + 1.5 * rH());
        const seg = L.slice(s0, s1 + 1).map((p, i, Q) => { const a = Q[Math.max(0, i - 2)], b = Q[Math.min(Q.length - 1, i + 2)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, v = toC(p), sg = Math.sign(-(b[1] - a[1]) * v[0] + (b[0] - a[0]) * v[1]) || 1; return [p[0] - (b[1] - a[1]) / l * off * sg, p[1] + (b[0] - a[0]) / l * off * sg]; });
        for (const pc of put(seg, it.e.ch, loose, rH, { erase: true })) strokes.push(pc.pts);
      }
      L.forEach(p => erased.mark(p[0], p[1], 1, 0, 1.2));
      emit('oxbow', strokes, { ch: it.e.ch, t: it.t });
    } else {
      const P = trimToSheet(it.c.pts, mTrim); if (polyLen(P) < 20) continue;
      const strokes = [];
      for (const pc of put(P, it.c.id, loose, rH, { erase: true, keepHand: true })) {
        // the far end breaks up and stops in open ground
        const tot = polyLen(pc.pts), cut = tot * 0.65; let s = 0, cur = [], mode = 0, left = 0;
        for (let i = 0; i < pc.pts.length; i++) {
          const p = pc.pts[i]; if (i) s += Math.hypot(p[0] - pc.pts[i - 1][0], p[1] - pc.pts[i - 1][1]);
          if (s < cut) { cur.push(p); continue; }
          if (left <= 0) { if (mode === 0 && cur.length > 1) strokes.push(cur); cur = []; mode ^= 1; left = mode ? 2 + 3 * rH() : Math.max(1.5, (4 + 6 * rH()) * (1 - (s - cut) / (tot - cut + 1e-9))); }
          left -= i ? Math.hypot(p[0] - pc.pts[i - 1][0], p[1] - pc.pts[i - 1][1]) : 0;
          if (mode === 0) cur.push(p);
        }
        if (cur.length > 1 && mode === 0) strokes.push(cur);
      }
      P.forEach(p => erased.mark(p[0], p[1], 1, 0, 1.2));
      emit('abandoned', strokes, { ch: it.c.id, t: it.t });
    }
  }

  // tangle metric per zone (anti-hairball): principal-axis aspect, tangent deviation from the channel, tight curls
  const tangles = tangleZones.map(z => {
    const g = geo.get(z.ch), pts = [], devs = []; let curl = 0, len = 0;
    for (const st of g.strands) {
      if (st.i1 < z.i0 || st.i0 > z.i1) continue;
      for (let q = 1; q < st.pts.length - 1; q++) {
        const i = st.i0 + q; if (i < z.i0 || i > z.i1) continue;
        const a = st.pts[q - 1], b = st.pts[q], c2 = st.pts[q + 1];
        pts.push(b); len += 0.5;
        devs.push(Math.abs(wrap(Math.atan2(c2[1] - a[1], c2[0] - a[0]) - g.th[i])));
        const turnA = Math.abs(wrap(Math.atan2(c2[1] - b[1], c2[0] - b[0]) - Math.atan2(b[1] - a[1], b[0] - a[0])));
        if (turnA > 0.5 / 3) curl += 0.5;
      }
    }
    if (pts.length < 10) return { ch: z.ch, aspect: 0, angle: 0, curl: 0, ink: 0, K: false };
    const m = centroid(pts); let xx = 0, yy = 0, xy = 0; for (const p of pts) { xx += (p[0] - m[0]) ** 2; yy += (p[1] - m[1]) ** 2; xy += (p[0] - m[0]) * (p[1] - m[1]); }
    const tr = xx + yy, det = xx * yy - xy * xy, d = Math.sqrt(Math.max(0, tr * tr / 4 - det)), aspect = Math.sqrt((tr / 2 + d) / Math.max(1e-9, tr / 2 - d));
    const angle = devs.reduce((x, y) => x + y, 0) / devs.length * 180 / Math.PI, curlF = curl / len;
    const fails = (aspect < 3) + (angle > 35) + (curlF > 0.1);
    return { ch: z.ch, depth: +z.depth.toFixed(2), mm: Math.round((z.i1 - z.i0) * 0.5), aspect: +aspect.toFixed(1), angle: Math.round(angle), curl: +curlF.toFixed(2), ink: Math.round(len), K: fails >= 2 };
  });
  this.lines = out;
  this.meanderInfo = meanderRecipe(out, chans, geo, events, steps, { dead, tot, white, rings, ringStill, prm, tangles, win });
  if (r3) Object.assign(this.meanderInfo, { accents, bridges, bridgeInk: +((bridges.ink || 0) / (ink.all || 1)).toFixed(3), chaosShare: +(ink.chaos / (ink.all || 1)).toFixed(3), chiC: chiC.map(c => [+c.x.toFixed(1), +c.y.toFixed(1), +c.r.toFixed(1)]) });
  if (prm.debug) this.meanderDebug = { chans: chans.map(c => ({ id: c.id, cls: c.cls, present: c.present, tDraw: c.tDraw })), snaps, events };
};

// Metrics for the kill table; flags are one letter per failing row.
function meanderRecipe(out, chans, geo, events, steps, o) {
  const strokes = out.flatMap(l => l.strokes);
  const inkMm = Math.round(strokes.reduce((a, s) => a + polyLen(s), 0));
  const cs = 10, gw = Math.ceil(W / cs), gh = Math.ceil(H / cs), dens = new Float64Array(gw * gh), occ = new Sheet();
  for (const s of strokes) for (let i = 1; i < s.length; i++) {
    const p = s[i], l = Math.hypot(p[0] - s[i - 1][0], p[1] - s[i - 1][1]);
    dens[clamp(Math.floor(p[1] / cs), 0, gh - 1) * gw + clamp(Math.floor(p[0] / cs), 0, gw - 1)] += l; occ.mark(p[0], p[1], 1, 0, 0.5);
  }
  const nz = Array.from(dens).filter(v => v > 0).sort((a, b) => a - b);
  const contrast = nz.length ? nz[Math.floor(nz.length * 0.9)] / (nz[Math.floor(nz.length / 2)] || 1) : 0;
  let hair = 0; for (let j = 0; j < gh - 1; j++) for (let i = 0; i < gw - 1; i++) hair = Math.max(hair, dens[j * gw + i] + dens[j * gw + i + 1] + dens[(j + 1) * gw + i] + dens[(j + 1) * gw + i + 1]);
  const D = distField(occ); let empty = 0; for (let c = 0; c < N; c++) if (D[c] > 8) empty++;
  const deadFrac = o.tot ? o.dead / o.tot : 0;
  const ratios = [...geo.entries()].filter(([, g]) => g.len >= 60 && g.Kmax >= 3).map(([id, g]) => ({ ch: id, ratio: +g.ratio.toFixed(2), K3: +g.Kfrac3.toFixed(2), edge: Math.round(g.edgeRun), rail: +g.railFrac.toFixed(2), vhi: +g.vhiOwn.toFixed(3) }));
  let through = false;
  for (const [, g] of geo) {
    if (g.Kmax < 2) continue;
    const e = new Set(); for (const p of g.C) { if (p[0] < 6) e.add('l'); if (p[0] > W - 6) e.add('r'); if (p[1] < 6) e.add('t'); if (p[1] > H - 6) e.add('b'); }
    if (e.size >= 2) through = true;
  }
  const flags = [
    o.ringStill ? 'T' : '', deadFrac > 0.10 ? 'R' : '', ratios.some(r => r.edge > 60) ? 'O' : '', ratios.some(r => r.ratio < 2.5) ? 'P' : '', ratios.some(r => r.rail > 0.2) ? 'L' : '', o.prm.window && o.win && !o.win.score ? 'W' : '', (o.tangles || []).some(t => t.K) ? 'K' : '', through && !o.prm.window ? 'F' : '',
    ratios.some(r => r.K3 > 0.6) ? 'H' : '', hair > 400 ? 'X' : '', contrast < 4 ? 'N' : '', empty / N < 0.35 ? 'E' : '',
  ].join('');
  return {
    steps, white: o.white, inkMm, deadFrac: +deadFrac.toFixed(3), contrast: +contrast.toFixed(2), hairball: Math.round(hair), empty: +(empty / N).toFixed(2),
    ringsDropped: o.rings, ratios, flags, tangles: o.tangles || [], window: o.win ? { s: o.win.s, origin: [Math.round(o.win.ox), Math.round(o.win.oy)], score: +o.win.score.toFixed(3), cross: o.win.cross } : null,
    channels: chans.map(c => ({ id: c.id, cls: c.cls, tDraw: c.tDraw, drawn: !!c.drawn, abandoned: !!c.abandoned, len: c.present ? Math.round(polyLen(c.present)) : 0 })),
    events: events.map(e => ({ kind: e.kind, ch: e.ch, t: e.t, at: e.at.map(v => Math.round(v)) })),
  };
}
if (typeof module !== 'undefined') { module.exports.MEANDER_DEFAULTS = MEANDER_DEFAULTS; module.exports.MEANDER_MACROS = MEANDER_MACROS; }
