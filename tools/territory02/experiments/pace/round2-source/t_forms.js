
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
