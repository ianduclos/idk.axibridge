
// ======================= v5: searching lines on the v2 composition =======================
// A post-pass on the drawn v2 ink (see docs/research/territory-v5/synthesis-brief.md):
//  M1 sediment → reduction: a border's earlier positions become passes; keep oldest + newest.
//  M2 register field + good continuation: contest decides how a pass behaves; firm commits
//     carry on through junctions onto a neighbour's contour; knots at doubt nodes; hooks at T-ends.
//  M3 silent winner + protagonist economy: the largest camp stays nearly empty; one passage gets it all.
//  Events (rare): cancel stroke, aperture lip, net on one lobe, rigid chord.

function normalsOf(P) {
  return P.map((p, i) => { const a = P[Math.max(0, i - 2)], b = P[Math.min(P.length - 1, i + 2)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1; return [-(b[1] - a[1]) / l, (b[0] - a[0]) / l]; });
}
function pointHash(pts, cell) {
  const h = new Map();
  for (const p of pts) { const k = Math.floor(p[0] / cell) * 4096 + Math.floor(p[1] / cell); let b = h.get(k); if (!b) h.set(k, b = []); b.push(p); }
  return h;
}

Territory.prototype.v5 = function (cores, rng) {
  const prm = { budgetMul: 4, snapMax: 10, search: true, searchMax: 3, dStable: 1.5, dMax: 20, normalTol: 3, maxPasses: 5, transfers: 2, turnMax: 110, knots: 1, knotGap: 40, hookFrac: 0.25, hookGap: 25, economy: true, events: true, forceNet: false, forceAperture: false, ...this.prm };
  const thr = Math.pow(prm.eps, BETA), S = this.S;
  const L = this.labels();
  const inf = (k, c) => Math.pow(S[k][c], 1 / BETA);
  const contestAt = (x, y) => { const c = cellOf(x, y), v = [inf(1, c), inf(2, c), inf(3, c)].sort((a, b) => b - a); return smooth(prm.eps, 0.4, v[1]); };
  const hands = makeHands(this.seed, { sway: prm.sway ?? 1, overshoot: prm.overshoot ?? 1, lifts: prm.lifts ?? 1, tremor: prm.tremor ?? 1 });
  const loose = hands[0], firm = hands[1];

  // ---- the base: v2 lines as a graph ----
  const baseLines = this.lines.filter(l => l.kind === 'border' || l.kind === 'outer');
  const baseInk = baseLines.reduce((a, l) => a + l.strokes.reduce((u, st) => u + polyLen(st), 0), 0);
  // The graph follows the final, unfaded contours: long continuous paths for the passes to travel;
  // the drawn v2 dashes stay exactly as they were.
  const inside = p => p[0] > 6 && p[0] < W - 6 && p[1] > 6 && p[1] < H - 6;
  const baseList = [];
  for (const c of this.contours(this.S, L)) {
    let cur = [];
    for (const p of c.pts) { if (inside(p)) cur.push([p[0], p[1]]); else { if (cur.length > 8) baseList.push({ pts: cur, kind: c.kind }); cur = []; } }
    if (cur.length > 8) baseList.push({ pts: cur, kind: c.kind });
  }
  const G = contourGraph(baseList.map(b => b.pts));
  for (const e of G.edges) {
    e.kind = baseList[e.src].kind;
    e.nrm = normalsOf(e.pts);
    let cs = 0, n = 0; for (let q = 0; q < e.pts.length; q += 4) { cs += contestAt(e.pts[q][0], e.pts[q][1]); n++; }
    e.contest = n ? cs / n : 0;
    e.passes = [];
  }
  // lineage: sheet rebuilt from the graph; edges sharing a node may touch each other's ink
  const sheet = new Sheet(), lin = new Map();
  const related = (a, b) => {
    const ea = lin.get(a), eb = lin.get(b); if (ea === undefined || eb === undefined) return false;
    if (ea === eb) return true;
    const A = G.edges[ea], B = G.edges[eb]; return A.a === B.a || A.a === B.b || A.b === B.a || A.b === B.b;
  };
  sheet.related = related;
  G.edges.forEach(e => { const id = 1 + e.id; lin.set(id, e.id); e.pts.forEach((p, i) => sheet.mark(p[0], p[1], id, i)); });
  if (prm.voids) this.forbid.call({ sheet }, L);
  let sid = 100000;
  const newId = eid => { const id = ++sid; lin.set(id, eid); return id; };

  // ---- camps: the silent winner ----
  const area = [0, 0, 0, 0]; for (let c = 0; c < N; c++) if (L[c] > 0) area[L[c]]++;
  const winner = prm.economy ? area.indexOf(Math.max(...area.slice(1))) : -1;
  const pairOf = e => { const m = e.pts[Math.floor(e.pts.length / 2)], n = e.nrm[Math.floor(e.pts.length / 2)]; return [L[cellOf(m[0] + n[0] * 1.5, m[1] + n[1] * 1.5)], L[cellOf(m[0] - n[0] * 1.5, m[1] - n[1] * 1.5)]]; };
  G.edges.forEach(e => { e.pair = pairOf(e); e.touchesWinner = e.pair.includes(winner); });

  // ---- M1 sediment: match topology-changing snapshots onto each edge ----
  const snaps = (this.snapshots || []).slice(0, -1).slice(-prm.snapMax);
  const hashes = snaps.map(s => ({ border: pointHash(s.contours.filter(c => c.kind === 'border').flatMap(c => c.pts), 5), outer: pointHash(s.contours.filter(c => c.kind === 'outer').flatMap(c => c.pts), 5) }));
  for (const e of G.edges) {
    if (e.pts.length < 12) continue;
    if (e.kind === 'outer' && prm.economy && e.pair.includes(winner)) continue;   // the winner's own edges stay single
    e.age = new Float32Array(e.pts.length);
    hashes.forEach((hs, t) => {
      const H = e.kind === 'outer' ? hs.outer : hs.border, d = new Float32Array(e.pts.length).fill(NaN);
      e.pts.forEach((p, i) => {
        const n = e.nrm[i], gx = Math.floor(p[0] / 5), gy = Math.floor(p[1] / 5);
        let best = NaN, bd = 1e9;
        for (let u = -4; u <= 4; u++) for (let v = -4; v <= 4; v++) for (const q of (H.get((gx + u) * 4096 + gy + v) || [])) {
          const dx = q[0] - p[0], dy = q[1] - p[1], along = dx * n[0] + dy * n[1];
          if (Math.abs(along) > prm.dMax) continue;
          const off = Math.hypot(dx - along * n[0], dy - along * n[1]); if (off > prm.normalTol) continue;
          if (Math.abs(along) < bd) { bd = Math.abs(along); best = along; }
        }
        d[i] = best;
      });
      // smooth over 5 mm, split into runs of at least 12 mm
      const sm = d.map((_, i) => { let s = 0, k = 0; for (let j = i - 2; j <= i + 2; j++) if (j >= 0 && j < d.length && !isNaN(d[j])) { s += d[j]; k++; } return k >= 3 ? s / k : NaN; });
      let i = 0;
      while (i < sm.length) {
        if (isNaN(sm[i])) { i++; continue; }
        let j = i; while (j + 1 < sm.length && !isNaN(sm[j + 1])) j++;
        if (j - i >= 12) {
          const seg = Array.from(sm.slice(i, j + 1)), med = seg.map(Math.abs).sort((a, b) => a - b)[Math.floor(seg.length / 2)];
          if (med < prm.dStable) { for (let q = i; q <= j; q++) e.age[q]++; e.passes.push({ t, kind: 'stable', i0: i, i1: j, d: seg.map(() => (rng() < 0.5 ? -1 : 1) * (0.3 + 0.3 * rng())), spread: 0 }); }
          else if (med <= prm.dMax) e.passes.push({ t, kind: 'ghost', i0: i, i1: j, d: seg, spread: Math.max(...seg.map(Math.abs)) });
        }
        i = j + 1;
      }
    });
    e.ageMean = e.age.reduce((a, b) => a + b, 0) / e.age.length;
  }
  // ---- M3 economy: the protagonist component ----
  const comp = new Int32Array(G.nodes.length).fill(-1); let nc = 0;
  for (const n of G.nodes) { if (comp[n.id] >= 0) continue; const st = [n.id]; comp[n.id] = nc; while (st.length) { const m = st.pop(); for (const eid of G.nodes[m].edges) { const o = otherEnd(G, eid, m); if (comp[o] < 0) { comp[o] = nc; st.push(o); } } } nc++; }
  const score = new Float32Array(nc); G.edges.forEach(e => { score[comp[e.a]] += ((e.ageMean || 0) + e.contest * 2 + 0.2) * e.len; });
  const protagonist = prm.economy ? score.indexOf(Math.max(...score)) : -1;
  // ---- reduction: oldest + newest + a few far-apart middles ----
  const plan = [];
  for (const e of G.edges) {
    if (!e.passes.length) continue;
    let cand = e.passes.slice().sort((a, b) => a.t - b.t);
    const isProt = !prm.economy || comp[e.a] === protagonist;
    // winner's ground stays empty: drop passes that sit inside it
    cand = cand.filter(p => { const m = Math.floor((p.i0 + p.i1) / 2), off = p.d[m - p.i0], pt = e.pts[m], nn = e.nrm[m]; return L[cellOf(pt[0] + nn[0] * off, pt[1] + nn[1] * off)] !== winner || !prm.economy; });
    if (!cand.length) continue;
    let keep;
    if (!isProt) keep = [cand[0]];
    else {
      const spread = Math.max(0, ...cand.map(p => p.spread));
      const middles = cand.slice(1, -1).sort((a, b) => b.spread - a.spread).slice(0, Math.round(spread / 8));
      keep = [cand[0], ...middles, cand[cand.length - 1]].filter((p, i, a) => a.indexOf(p) === i);
      const cap = Math.min(prm.maxPasses - 1, cand.length >= 3 ? Math.ceil(0.6 * cand.length) : cand.length);
      keep = keep.slice(0, cap);
    }
    for (const p of keep) plan.push({ e, p, prot: isProt });
  }
  // protagonist first, oldest first
  plan.sort((a, b) => (b.prot - a.prot) || (a.p.t - b.p.t));
  const out = [], budget = prm.budgetMul * baseInk; let spent = 0;
  const D = distField(sheet);
  const emit = (kind, strokes, extra = {}) => { for (const st of strokes) { const l = polyLen(st); spent += l; } if (strokes.length) out.push({ core: -1, kind, strokes, breaks: 0, ...extra }); };
  const drawPass = (pts, eid, hand, kind, extra, o = {}) => {
    if (pts.length < 4 || spent > budget) return null;
    const dests = []; for (let q = 0; q < pts.length; q += 3 + Math.floor(rng() * 4)) dests.push(pts[q]); dests.push(pts[pts.length - 1]);
    const res = walkLine(sheet, dests, newId(eid), { ...prm, wander: kind === 'commit' ? 0.3 : 0.6, yieldP: 0.6 }, rng, D, { touch: true, r: 0.4, ...o });
    if (!res || !res.strokes.length) return null;
    const strokes = res.strokes.flatMap(st => handLine(st, hand, rng));
    emit(kind, strokes, extra);
    return res;
  };
  // ---- draw sediment ----
  for (const { e, p } of plan) {
    const pts = [];
    for (let q = p.i0; q <= p.i1; q++) {
      const d = p.d[q - p.i0], pt = e.pts[q], nn = e.nrm[q], c = contestAt(pt[0], pt[1]);
      pts.push([pt[0] + nn[0] * d, pt[1] + nn[1] * d, clamp(prm.loose * (0.45 + 1.1 * (1 - c)), 0.05, 1)]);
    }
    drawPass(pts, e.id, loose, 'sediment', { snapshot: p.t, edge: e.id });
  }
  // ---- searching passes: each restatement answers the previous one, anchored at junctions ----
  if (prm.search) {
    const junction = n => G.nodes[n].degree >= 3;
    const order = G.edges.filter(e => e.len > 14 && !(e.kind === 'outer' && prm.economy && e.pair.includes(winner)))
      .map(e => {
        const jA = junction(e.a), jB = junction(e.b), prot = !prm.economy || comp[e.a] === protagonist;
        const w = clamp(0.45 * e.contest + 0.35 * Math.min(1, (e.ageMean || 0) / 2) + 0.35 * ((jA || jB) ? 1 : 0) + (prot ? 0.25 : -0.2), 0, 1);
        return { e, jA, jB, prot, w };
      }).sort((a, b) => b.w - a.w);
    for (const { e, jA, jB, prot, w } of order) {
      const n = prot ? Math.round(1 + (prm.searchMax - 1) * w * w) : Math.round(2 * w * w);
      if (!n) continue;
      const P = e.pts, nn = e.nrm, M = P.length, nz = [];
      let prev = new Float32Array(M);
      const anchorA = jA && (!jB || rng() < 0.5);
      for (let k = 0; k < n; k++) {
        const z = noise1(rng), amp = 1.2 + 3 * rng() * (0.6 + 0.4 * (1 - e.contest)), lam = 12 + 30 * rng();
        const cur = new Float32Array(M);
        for (let q = 0; q < M; q++) cur[q] = prev[q] * 0.55 + amp * z(q / lam);
        // span: from the anchored junction end toward the free end, shorter each pass
        const frac = clamp(1 - 0.12 * k - 0.35 * rng(), 0.25, 1), span = Math.max(8, Math.round(M * frac));
        const i0 = (jA || jB) ? (anchorA ? 0 : M - span) : Math.floor(rng() * (M - span + 1)), i1 = Math.min(M - 1, i0 + span - 1);
        const pts = [];
        for (let q = i0; q <= i1; q++) { const c = contestAt(P[q][0], P[q][1]); pts.push([P[q][0] + nn[q][0] * cur[q], P[q][1] + nn[q][1] * cur[q], clamp(prm.loose * (0.45 + 1.1 * (1 - c)), 0.05, 1)]); }
        const mid = pts[Math.floor(pts.length / 2)];
        if (prm.economy && L[cellOf(mid[0], mid[1])] === winner && e.kind === 'outer') break;
        if (!drawPass(pts, e.id, k === n - 1 && e.contest > 0.45 ? firm : loose, 'search', { edge: e.id, pass: k })) { if (spent > budget) break; }
        prev = cur;
      }
      if (spent > budget) break;
    }
  }
  // ---- M2 commits with good continuation through junctions ----
  const used = new Int32Array(G.edges.length);
  const tangentFrom = (eid, n) => { const P = edgeFrom(G, eid, n), k = Math.min(P.length - 1, 2); return Math.atan2(P[k][1] - P[0][1], P[k][0] - P[0][0]); };
  const commits = G.edges.filter(e => e.kind === 'border' && e.contest > 0.45 && (!prm.economy || comp[e.a] === protagonist)).sort((a, b) => b.contest - a.contest);
  for (const e of commits) {
    if (used[e.id]) continue;
    let path = e.pts.map(p => [p[0], p[1], 0.12]); used[e.id]++;
    let end = e.b, inA = Math.atan2(e.pts[e.pts.length - 1][1] - e.pts[e.pts.length - 3][1], e.pts[e.pts.length - 1][0] - e.pts[e.pts.length - 3][0]);
    for (let tr = 0; tr < prm.transfers; tr++) {
      const node = G.nodes[end]; if (node.degree < 3) break;
      let best = null, bs = 1e9;
      for (const eid of node.edges) {
        if (eid === e.id) continue;
        const turn = Math.abs(wrap(tangentFrom(eid, end) - inA)) - (used[eid] ? 0 : 0.15);
        if (turn < bs) { bs = turn; best = eid; }
      }
      if (best === null || bs > rad(prm.turnMax)) break;
      const P = edgeFrom(G, best, end); used[best]++;
      path = path.concat(P.map(p => [p[0], p[1], clamp(0.12 + 0.3 * (1 - G.edges[best].contest), 0.05, 1)]));
      end = otherEnd(G, best, end); inA = Math.atan2(P[P.length - 1][1] - P[P.length - 3][1], P[P.length - 1][0] - P[P.length - 3][0]);
    }
    // committed line sits 0.4 mm off the original so both read
    const nn = normalsOf(path), side = rng() < 0.5 ? -0.4 : 0.4;
    drawPass(path.map((p, i) => [p[0] + nn[i][0] * side, p[1] + nn[i][1] * side, p[2]]), e.id, firm, 'commit', { edge: e.id });
  }
  // ---- knots at doubt nodes ----
  const ends = out.flatMap(l => l.strokes.flatMap(st => [st[0], st[st.length - 1]]));
  const doubt = G.nodes.filter(n => n.degree >= 3).map(n => ({ n, v: ends.filter(p => Math.hypot(p[0] - n.x, p[1] - n.y) < 6).length + n.degree }));
  doubt.sort((a, b) => b.v - a.v);
  const knots = [];
  for (const d of doubt) {
    if (knots.length >= prm.knots) break;
    if (knots.some(k => Math.hypot(k.x - d.n.x, k.y - d.n.y) < prm.knotGap)) continue;
    if (prm.economy && comp[d.n.id] !== protagonist && knots.length) continue;
    knots.push(d.n);
    const eid = d.n.edges[0], inkLen = 120 + 260 * Math.min(1, d.v / 10), dests = [];
    let a0 = tangentFrom(eid, d.n.id), s = 0, R = 8;
    const Rk = 5 + 10 * rng(), asp = 0.35 + 0.65 * rng(), rot = rng() * Math.PI, spin = rng() < 0.5 ? 1 : -1, flip = 0.1 + 0.3 * rng();
    while (s < inkLen) { a0 += spin * (0.4 + 0.9 * rng()) * (rng() < flip ? -1 : 1); R = Math.max(1.5, Rk - (Rk - 2) * s / inkLen) * (0.5 + 0.9 * rng()); { const u = Math.cos(a0) * R, v = Math.sin(a0) * R * asp; dests.push([d.n.x + u * Math.cos(rot) - v * Math.sin(rot), d.n.y + u * Math.sin(rot) + v * Math.cos(rot), 0.2]); } s += R * 0.9; }
    const res = walkLine(sheet, dests, newId(eid), { ...prm, wander: 0.8, yieldP: 0.8 }, rng, D, { touch: true, r: 0.35 });
    if (res && res.strokes.length) emit('knot', res.strokes.flatMap(st => handLine(st, loose, rng)), { node: d.n.id });
  }
  // ---- hooks at T-ends ----
  const hookEnds = [];
  const lead = G.nodes.filter(n => n.degree === 1);
  for (const n of lead) {
    const eid = n.edges[0], P = edgeFrom(G, eid, n.id);
    if (P.length < 6) continue;
    const tx = P[0][0] - P[3][0], ty = P[0][1] - P[3][1], tl = Math.hypot(tx, ty) || 1;
    const ahead = [n.x + tx / tl * 2.5, n.y + ty / tl * 2.5], o = sheet.owner[cellOf(ahead[0], ahead[1])];
    if (!(o > 0 && !related(o, 1 + eid))) continue;     // not a T-end: a fade, leave it
    if (hookEnds.length >= Math.ceil(lead.length * prm.hookFrac) || hookEnds.some(h => Math.hypot(h[0] - n.x, h[1] - n.y) < prm.hookGap)) continue;
    const nx = -ty / tl, ny = tx / tl, sL = L[cellOf(n.x + nx * 2, n.y + ny * 2)], sR = L[cellOf(n.x - nx * 2, n.y - ny * 2)];
    const sgn = sL > 0 && sL !== winner ? 1 : sR > 0 ? -1 : 1, len = 2 + 3 * rng(), pts = [[n.x, n.y]];
    let a = Math.atan2(-ty, -tx), x = n.x, y = n.y;
    for (let t = 0; t < len; t += 0.5) { a += sgn * 0.35; x += Math.cos(a) * 0.5; y += Math.sin(a) * 0.5; pts.push([x, y]); }
    hookEnds.push([n.x, n.y]); emit('hook', [pts]);
  }
  // ---- events: two slots ----
  if (prm.events) {
    const er = rngFor(this.seed, 5152), spots = knots.map(k => [k.x, k.y]);
    const free = (x, y, r) => spots.every(s => Math.hypot(s[0] - x, s[1] - y) > r);
    let net = prm.forceNet, aperture = prm.forceAperture, cancel = false, chord = false;
    if (!prm.forceNet && !prm.forceAperture) {
      const u = er();
      if (u < 0.45) cancel = true;
      else if (u < 0.55) aperture = true;
      else if (u < 0.63) net = true;
      else if (u < 0.75) chord = true;
    }
    // cancel: one firm stroke across the heaviest bundle
    if (cancel) {
      const count = new Map(); out.forEach(l => { if (l.edge !== undefined) count.set(l.edge, (count.get(l.edge) || 0) + 1); });
      let be = -1, bc = 0; count.forEach((v, k) => { if (v > bc) { bc = v; be = k; } });
      if (be >= 0) {
        const e = G.edges[be], m = Math.floor(e.pts.length / 2), p = e.pts[m];
        if (free(p[0], p[1], 20)) {
          const ta = Math.atan2(e.nrm[m][1], e.nrm[m][0]) + (er() - 0.5) * rad(80), Lc = 15 + 25 * er();
          const pts = []; for (let t = -Lc / 2; t <= Lc / 2 + 3; t += 1) pts.push([p[0] + Math.cos(ta) * t, p[1] + Math.sin(ta) * t]);
          emit('cancel', handLine(pts, firm, er)); spots.push(p);
        }
      }
    }
    if (aperture) this.v5Aperture(L, sheet, G, out, emit, er, firm, loose, spots, free, comp, protagonist);
    if (net) this.v5Net(cores, L, winner, sheet, emit, er, loose, spots, free);
    if (chord) {
      const cands = G.edges.filter(e => e.kind === 'border' && e.len > 30);
      if (cands.length) {
        const e = cands[Math.floor(er() * cands.length)], pts = [];
        for (let q = 0; q < e.pts.length; q += Math.max(1, Math.round(15 + 15 * er()))) pts.push(e.pts[q]);
        pts.push(e.pts[e.pts.length - 1]);
        const n0 = normalsOf(e.pts)[Math.floor(e.pts.length / 2)], off = 3 + 4 * er();
        emit('chord', [catmullRom(resample(pts.map(p => [p[0] + n0[0] * off, p[1] + n0[1] * off]), 25), 0.5)]);
      }
    }
  }
  this.lines = this.lines.concat(out);
  this.v5info = { winner, protagonist, snaps: snaps.length, baseInk, spent, knots: knots.length, edges: G.edges.length };
};

// Aperture: a void (or the largest empty pocket) gets a lip of three restated arcs on the side facing the drama.
Territory.prototype.v5Aperture = function (L, sheet, G, out, emit, er, firm, loose, spots, free, comp, protagonist) {
  let mask = new Uint8Array(N), cnt = 0;
  for (let c = 0; c < N; c++) if (L[c] === -1) { mask[c] = 1; cnt++; }
  if (cnt < 150) {
    // no void: take an unclaimed pocket, the deepest empty cell of the sheet
    const empty = distField(sheet); let bc = -1, bv = 0;
    for (let c = 0; c < N; c++) if (L[c] > 0 && empty[c] > bv) { bv = empty[c]; bc = c; }
    if (bc < 0 || bv < 7) return;
    const cx = bc % GW + 0.5, cy = ((bc / GW) | 0) + 0.5, r = Math.min(bv * 0.7, 18), ax = r * (0.7 + 0.6 * er()), ay = r * (0.7 + 0.6 * er()), rot = er() * Math.PI;
    for (let j = Math.floor(cy - r * 1.5); j <= cy + r * 1.5; j++) for (let i = Math.floor(cx - r * 1.5); i <= cx + r * 1.5; i++) {
      if (i < 0 || j < 0 || i >= GW || j >= GH) continue;
      const dx = i + 0.5 - cx, dy = j + 0.5 - cy, u = dx * Math.cos(rot) + dy * Math.sin(rot), v = -dx * Math.sin(rot) + dy * Math.cos(rot);
      if ((u / ax) ** 2 + (v / ay) ** 2 < 1) mask[j * GW + i] = 1;
    }
  }
  const dist = chamfer(mask);
  let mx = 0, my = 0, mn = 0; for (let c = 0; c < N; c++) if (mask[c]) { mx += c % GW; my += (c / GW) | 0; mn++; }
  if (!mn) return; mx /= mn; my /= mn;
  if (!free(mx, my, 25)) return;
  // face the heaviest passage
  let hx = 0, hy = 0, hw = 0; for (const l of out) for (const st of l.strokes) { const m = st[Math.floor(st.length / 2)]; hx += m[0]; hy += m[1]; hw++; }
  const fa = hw ? Math.atan2(hy / hw - my, hx / hw - mx) : er() * 7;
  const all = new Uint8Array(N).fill(1);
  [2, 3.2, 4.6].forEach((lev, k) => {
    for (const line of isolines(dist, all, lev, 6)) {
      const keep = line.pts.filter(p => Math.cos(Math.atan2(p[1] - my, p[0] - mx) - fa) > 0.05 + 0.1 * k);
      const runs = []; let cur = [];
      for (const p of line.pts) { if (keep.includes(p)) cur.push(p); else { if (cur.length > 4) runs.push(cur); cur = []; } }
      if (cur.length > 4) runs.push(cur);
      for (const r of runs) emit('aperture', handLine(r, k === 0 ? firm : loose, er));
    }
  });
  spots.push([mx, my]);
};

// Net: one lobe of the last-arriving camp gets a slipped, frayed two-family mesh.
Territory.prototype.v5Net = function (cores, L, winner, sheet, emit, er, loose, spots, free) {
  const lastCamp = [...this.order].reverse().map(i => cores[i]).find(c => c.camp > 0 && c.camp !== winner)?.camp;
  if (!lastCamp) return;
  // the component of that camp holding its last core
  const core = [...this.order].reverse().map(i => cores[i]).find(c => c.camp === lastCamp);
  let seedC = -1; for (const p of resample(core.pts, 2)) { const c = cellOf(p[0], p[1]); if (L[c] === lastCamp) { seedC = c; break; } }
  if (seedC < 0) return;
  const mask = flood(Float32Array.from(L, v => v === lastCamp ? 1 : 0), 0.5, seedC);
  const bb = bboxOf(mask, 1); if (!bb) return;
  const H = inflate(mask, bb, 60, 0.8);
  let mx = 0, my = 0, n = 0; for (let c = 0; c < N; c++) if (mask[c]) { mx += c % GW; my += (c / GW) | 0; n++; }
  if (n < 300) return; mx /= n; my /= n;
  if (!free(mx, my, 25)) return;
  const slipX = (er() - 0.5) * 8, slipY = (er() - 0.5) * 8, rot = rad((er() - 0.5) * 6), cr = Math.cos(rot), sr = Math.sin(rot);
  const xf = p => { const dx = p[0] - mx, dy = p[1] - my; return [mx + dx * cr - dy * sr + slipX, my + dx * sr + dy * cr + slipY]; };
  const bare = er() * Math.PI * 2, bareCut = 0.3 + 0.2 * er();   // a third to a half left unnetted
  const netted = p => Math.cos(Math.atan2(p[1] - my, p[0] - mx) - bare) < 1 - 2 * bareCut;
  let hmax = 0; for (let c = 0; c < N; c++) if (mask[c]) hmax = Math.max(hmax, H[c]);
  const nA = 6 + Math.floor(er() * 5), levels = []; for (let k = 1; k <= nA; k++) levels.push(hmax * k / (nA + 1));
  const valid = mask;
  const pieces = pts => { const r = []; let cur = []; for (const p of pts) { if (netted(p)) cur.push(p); else { if (cur.length > 3) r.push(cur); cur = []; } } if (cur.length > 3) r.push(cur); return r; };
  for (const line of isoLevels(H, valid, bb, levels)) for (const r of pieces(line.pts)) emit('net', handLine(r.map(xf), { ...loose, A: loose.A * 0.6 }, er));
  // family B: gradient lines from the rim upward
  const rim = []; for (let c = 0; c < N; c++) if (mask[c] && (!mask[c - 1] || !mask[c + 1] || !mask[c - GW] || !mask[c + GW])) rim.push([c % GW + 0.5, ((c / GW) | 0) + 0.5]);
  const seeds = resample(rim.sort((a, b) => Math.atan2(a[1] - my, a[0] - mx) - Math.atan2(b[1] - my, b[0] - mx)), 5);
  for (const s of seeds) {
    if (er() < 0.45) continue;
    const pts = [s]; let [x, y] = s;
    for (let k = 0; k < 120; k++) {
      const c = cellOf(x, y), gx = H[c + 1] - H[c - 1], gy = H[c + GW] - H[c - GW], g = Math.hypot(gx, gy);
      if (g < 1e-4 || !mask[c] || H[c] > hmax * 0.55) break;
      x += gx / g; y += gy / g; pts.push([x, y]);
    }
    for (const r of pieces(pts)) if (polyLen(r) > 5) emit('net', handLine(r.map(xf), { ...loose, A: loose.A * 0.6 }, er));
  }
  spots.push([mx, my]);
};
