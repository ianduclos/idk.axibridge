// ======================= meander 4: density =======================
// See docs/research/meander4/synthesis-brief.md. One dial (density D) with four weights (continue,
// cover, slash, surprise) and an ink limit. Everything here runs only when D > 0, after the base
// drawing is complete: the base is never changed, only reserved (a jittered white halo) and added to.
// Layers clip against a z-mask M (a Sheet marked top-first with id = z): chords 6, base 5,
// surprise 4, ribbons 3, fans 2, ground 1 (never marks). A stroke at z is cut where M.owner > z.

const DZ = { chord: 6, base: 5, surprise: 4, ribbon: 3, fan: 2, ground: 1 };

// 2D value noise on a lattice, from one rng (smooth, cheap, deterministic)
function noise2(rng) {
  const v = new Float32Array(4096); for (let i = 0; i < 4096; i++) v[i] = rng() * 2 - 1;
  const at = (i, j) => v[(((i * 73856093) ^ (j * 19349663)) >>> 0) % 4096];
  return (x, y) => {
    const i = Math.floor(x), j = Math.floor(y), fx = x - i, fy = y - j, u = fx * fx * (3 - 2 * fx), w = fy * fy * (3 - 2 * fy);
    const a = at(i, j), b = at(i + 1, j), c = at(i, j + 1), d = at(i + 1, j + 1);
    return a + (b - a) * u + (c - a) * w + (a - b - c + d) * u * w;
  };
}
// chamfer distance (mm) on the 1 mm grid from cells where src[c] is set; lab carries the nearest source's label
function chamferLab(src, lab) {
  const d = new Float32Array(N).fill(1e9), L = lab ? Int32Array.from(lab) : null;
  for (let c = 0; c < N; c++) if (src[c]) d[c] = 0;
  const pass = (y0, y1, dy, x0, x1, dx) => {
    for (let y = y0; y !== y1; y += dy) for (let x = x0; x !== x1; x += dx) {
      const c = y * GW + x;
      for (const [ox, oy, w] of [[-dx, 0, 1], [0, -dy, 1], [-dx, -dy, 1.4142], [dx, -dy, 1.4142]]) {
        const X = x + ox, Y = y + oy; if (X < 0 || Y < 0 || X >= GW || Y >= GH) continue;
        const q = Y * GW + X, v = d[q] + w; if (v < d[c]) { d[c] = v; if (L) L[c] = L[q]; }
      }
    }
  };
  pass(0, GH, 1, 0, GW, 1); pass(GH - 1, -1, -1, GW - 1, -1, -1);
  return { d, L };
}

function densityPass(o) {
  const { seed, prm, out, geo, chans, snaps, chi, junc, Ar } = o;
  // meander 5: a recipe without `planes` is a Version 8 recipe and runs exactly as before (planes only, dials capped at 1)
  const legacy = prm.planes === undefined, mu = legacy ? 0 : clamp(prm.mutate ?? 1, 0, 1.5), trainShare = legacy ? 0 : Math.pow(1 - clamp(prm.planes, 0, 1), 1.3);
  const D = clamp(prm.density || 0, 0, legacy ? 1 : 1.5);
  const effOf = k => clamp(D * 2 * (prm[k] ?? 0.5), 0, legacy ? 1 : 3), cov = D * 2 * (prm.cover ?? 0.5);
  const L = clamp(prm.ink ?? 40, 5, 100) * 1000;
  const baseInk = out.reduce((a, l) => a + l.strokes.reduce((b, s) => b + polyLen(s), 0), 0);
  const Istar = baseInk + Math.max(0, L - baseInk) * Math.pow(Math.min(1, D), 1.5), room = Math.max(0, Istar - baseInk);
  const ov = k => Math.max(1, effOf(k)), caps = { slash: 0.03 * room * ov('slash'), surprise: 0.12 * room * ov('surprise'), cont: 0.15 * room * ov('continue'), fans: 0.12 * room };   // 'over' dials (> 1 effective) get more room
  const info = { D, target: Math.round(Istar), layers: {} };

  // ---- fields (§2.1), rngFor(seed, 6180)
  const layers = {};
  const dry = noise2(rngFor(seed, 6182)), chiC_ = o.chiC || [];
  const dryBrushL = (P, thr0) => { const a = P[0], b = P[Math.min(P.length - 1, 40)], h = Math.atan2(b[1] - a[1], b[0] - a[0]), c = Math.cos(h), sn = Math.sin(h), pcs = []; let cur = []; for (const p of P) { if (dry((p[0] * c + p[1] * sn) / 40 + 11, (-p[0] * sn + p[1] * c) / 5) > thr0) { if (cur.length > 8) pcs.push(cur); cur = []; } else cur.push(p); } if (cur.length > 8) pcs.push(cur); return pcs; };
  const rF = rngFor(seed, 6180), G = 4, FX = Math.ceil(W / G) + 1, FY = Math.ceil(H / G) + 1;
  // base occupancy and nearest channel
  const baseSrc = new Uint8Array(N), baseLab = new Int32Array(N).fill(-1);
  for (const l of out) for (const st of l.strokes) for (const p of resample(st, 0.7)) { const c = cellOf(p[0], p[1]); baseSrc[c] = 1; baseLab[c] = l.ch ?? -1; }
  const Db = chamferLab(baseSrc, baseLab);
  // θ: doubled-angle tangents from present centrelines and all snapshots, two blur scales
  const cx = new Float32Array(FX * FY), cy = new Float32Array(FX * FY);
  const splat = (x, y, th, w) => { const i = Math.round(x / G), j = Math.round(y / G); if (i < 0 || j < 0 || i >= FX || j >= FY) return; cx[j * FX + i] += w * Math.cos(2 * th); cy[j * FX + i] += w * Math.sin(2 * th); };
  for (const [, g] of geo) for (let i = 0; i < g.C.length; i += 4) splat(g.C[i][0], g.C[i][1], g.th[i], 1);
  for (const s of snaps) for (let i = 2; i < s.pts.length - 2; i += 3) { const a = s.pts[i - 2], b = s.pts[i + 2]; splat(s.pts[i][0], s.pts[i][1], Math.atan2(b[1] - a[1], b[0] - a[0]), 0.25); }
  const blur = (A, r) => { let B = A; for (let pass = 0; pass < 3; pass++) { const C = new Float32Array(B.length); for (let j = 0; j < FY; j++) for (let i = 0; i < FX; i++) { let s = 0, n = 0; for (let u = -r; u <= r; u++) { const x = i + u; if (x < 0 || x >= FX) continue; s += B[j * FX + x]; n++; } C[j * FX + i] = s / n; } const E = new Float32Array(B.length); for (let j = 0; j < FY; j++) for (let i = 0; i < FX; i++) { let s = 0, n = 0; for (let u = -r; u <= r; u++) { const y = j + u; if (y < 0 || y >= FY) continue; s += C[y * FX + i]; n++; } E[j * FX + i] = s / n; } B = E; } return B; };
  const fx1 = blur(cx, 2), fy1 = blur(cy, 2), fx2 = blur(cx, 6), fy2 = blur(cy, 6);
  const nA = noise1(rF), nB = noise1(rF), ph = rF() * 100, lamN = 60 + 30 * rF();
  const tiltSign = new Map(); for (const c of chans) tiltSign.set(c.id, rF() < 0.5 ? 1 : -1);
  const bil = (A, x, y) => { const u = clamp(x / G, 0, FX - 1.001), v = clamp(y / G, 0, FY - 1.001), i = Math.floor(u), j = Math.floor(v), a = u - i, b = v - j; return (A[j * FX + i] * (1 - a) + A[j * FX + i + 1] * a) * (1 - b) + (A[(j + 1) * FX + i] * (1 - a) + A[(j + 1) * FX + i + 1] * a) * b; };
  const theta = (x, y) => {
    const bg = Math.PI * (nA(ph + 300 + (x + y) / 170) + nB(ph + 400 + (x - y) / 190));
    const X = bil(fx1, x, y) + 1.2 * bil(fx2, x, y) + 0.12 * Math.cos(2 * bg), Y = bil(fy1, x, y) + 1.2 * bil(fy2, x, y) + 0.12 * Math.sin(2 * bg);   // coarse field and a faint background flow carry where the fine one cancels
    let t = 0.5 * Math.atan2(Y, X) + rad(20) * (nA(ph + x / lamN) + nB(ph + 50 + y / lamN)) * 0.7;
    const c = cellOf(x, y), db = Db.d[c];
    if (db < 12) t += (1 - smooth(4, 12, db)) * rad(40) * (tiltSign.get(Db.L[c]) || 1);
    return t;
  };
  // junction pools J (2 mm grid): within 14 mm of a point where two channels' present lines meet within 12 mm
  const jpts = []; for (const c of chans) if (c.drawn && !c.abandoned && c.present) for (let i = 0; i < c.present.length; i += 3) { const p = c.present[i]; if (junc && junc(p[0], p[1], c.id)) jpts.push(p); }
  const jr = 14 + 10 * D, Jh = pointHash(jpts, jr + 12), jDist = (x, y) => { let m = 1e9; const gx = Math.floor(x / (jr + 12)), gy = Math.floor(y / (jr + 12)); for (let u = -1; u <= 1; u++) for (let v = -1; v <= 1; v++) for (const q of (Jh.get((gx + u) * 4096 + gy + v) || [])) m = Math.min(m, Math.hypot(q[0] - x, q[1] - y)); return m; }, inJ = (x, y) => jDist(x, y) < jr;   // r1: a quiet zone around knots that grows with D
  const Jg = new Uint8Array(FX * FY), Jring = new Float32Array(FX * FY).fill(1); for (let j = 0; j < FY; j++) for (let i = 0; i < FX; i++) { const d = jDist(i * G, j * G); Jg[j * FX + i] = d < jr ? 1 : 0; Jring[j * FX + i] = 0.3 + 0.7 * smooth(jr, jr + 12, d); }
  const isJ = (x, y) => Jg[Math.round(clamp(y / G, 0, FY - 1)) * FX + Math.round(clamp(x / G, 0, FX - 1))] === 1;

  // ---- the mask: base marked with a jittered halo (§3)
  const M = new Sheet(), nH = noise1(rF);
  for (const l of out) for (const st of l.strokes) { let s = 0; const P = resample(st, 0.7); for (let i = 0; i < P.length; i++) { if (i) s += 0.7; const p = P[i], r = isJ(p[0], p[1]) ? 3 + 2 * D : (0.8 + D) * (0.6 + 0.8 * (0.5 + 0.5 * nH(s / 20 + i * 0.001))); M.mark(p[0], p[1], DZ.base, 0, r); } }
  // ---- continue (§2.5): continuations of band ends and ribbons from old trunk courses, extended off the sheet
  const extend = (P, dirSign, Lmax, rng) => {             // run on from P's end with decaying curvature, steered a little toward θ
    const n = P.length; if (n < 6) return [];
    const e = P[n - 1], a = P[Math.max(0, n - 6)]; let h = Math.atan2(e[1] - a[1], e[0] - a[0]);
    let k0 = 0; { const m = Math.min(n - 1, 60), b = P[n - 1 - m], c = P[n - 1 - Math.floor(m / 2)]; const t1 = Math.atan2(c[1] - b[1], c[0] - b[0]), t2 = Math.atan2(e[1] - c[1], e[0] - c[0]); k0 = wrap(t2 - t1) / (polyLen(P.slice(n - 1 - m)) / 2 || 1); }
    const Ld = 60 + 60 * rng(), out2 = []; let x = e[0], y = e[1], turn = 0;
    for (let s2 = 0; s2 < Lmax; s2 += 1) {
      const th = theta(x, y); let d = wrap(2 * (th - h)) / 2; const k = k0 * Math.exp(-s2 / Ld) + 0.3 * d / 25;
      h += k; turn += Math.abs(k); if (turn > rad(200)) break;
      x += Math.cos(h); y += Math.sin(h); if (x < -5 || y < -5 || x > W + 5 || y > H + 5) break; out2.push([x, y]);
    }
    return out2;
  };
  const effC = effOf('continue'), effS = effOf('slash'), effX = effOf('surprise');
  const L_ = { cont: [], ribbonRails: [], ribbonBody: [], chords: [], wedges: [], fans: [], surprise: [] };
  if (effC > 0) {
    const rC = rngFor(seed, 6185), nCt = Math.round(effC * (1 + 1.5 * rC())), ends = [];
    for (const [id, g] of geo) for (const end of [0, 1]) { const C = end ? g.C : g.C.slice().reverse(), e = C[C.length - 1]; if (!isJ(e[0], e[1]) && e[0] > 8 && e[1] > 8 && e[0] < W - 8 && e[1] < H - 8) ends.push({ id, C, u: rC() }); }
    ends.sort((a, b) => a.u - b.u);
    for (const en of ends.slice(0, nCt)) {
      const ext = extend(en.C, 1, 40 + 110 * rC(), rC); if (ext.length < 20) continue;
      const k = 1 + Math.floor(3 * rC()), g = geo.get(en.id);
      for (let j = 0; j < k; j++) { const off = (j - (k - 1) / 2) * (0.9 + 0.8 * rC()); L_.cont.push(ext.map((p, i) => { const a2 = ext[Math.max(0, i - 2)], b2 = ext[Math.min(ext.length - 1, i + 2)], l = Math.hypot(b2[0] - a2[0], b2[1] - a2[1]) || 1, taper = Math.min(1, i / 30); return [p[0] - (b2[1] - a2[1]) / l * off * taper, p[1] + (b2[0] - a2[0]) / l * off * taper]; }).slice(0, Math.floor(ext.length * (0.7 + 0.3 * rC())))); }
    }
    const rR = rngFor(seed, 6184), nR = Math.round(effC * (1 + 2 * rR())), tp = (chans[0] && chans[0].present) || [], th0 = pointHash(tp, 10);
    const far = P => { let s2 = 0, k = 0; for (let i = 0; i < P.length; i += 6) { let bd = 60; const p = P[i], gx = Math.floor(p[0] / 10), gy = Math.floor(p[1] / 10); for (let u = -3; u <= 3; u++) for (let v = -3; v <= 3; v++) for (const q of (th0.get((gx + u) * 4096 + gy + v) || [])) bd = Math.min(bd, Math.hypot(q[0] - p[0], q[1] - p[1])); s2 += bd; k++; } return s2 / (k || 1); };
    const olds = snaps.filter(sn => sn.ch === 0 && sn.pts.length > 30).map(sn => ({ sn, f: far(sn.pts) })).filter(o => o.f > 25).sort((a, b) => b.f - a.f);
    for (let r = 0; r < nR; r++) {
      let spine;
      if (olds.length) { const o = olds[Math.floor(rR() * Math.min(olds.length, 4))]; olds.splice(olds.indexOf(o), 1); const P = o.sn.pts; spine = extend(P.slice().reverse(), 1, 400, rR).reverse().concat(P, extend(P, 1, 400, rR)); }
      else { const a = rR() * Math.PI * 2; spine = noiseWalk(rR, 420, W / 2 + Math.cos(a) * W * 0.6, H / 2 + Math.sin(a) * H * 0.6, a + Math.PI + (rR() - 0.5), { x0: -W, y0: -H, x1: 2 * W, y1: 2 * H }); }
      spine = resample(spine, 1); if (spine.length < 60) continue;
      const w = 5 + 9 * rR(), nz = noise1(rR), ph2 = rR() * 100, per = 60 + 60 * rR(), lit = rR() < 0.55;
      // twists at up to two inflections: the rails cross over 10–20 mm
      const kap = curvatureOf(spine), tw = []; for (let i = 20; i < spine.length - 20 && tw.length < 2; i++) if (Math.sign(kap[i]) !== Math.sign(kap[i - 1]) && rR() < 0.15) { tw.push({ i, h: 5 + 5 * rR() }); i += 60; }
      const sideOf = i => { let c = 1; for (const t of tw) c *= i < t.i - t.h ? 1 : i > t.i + t.h ? -1 : Math.cos(Math.PI * (i - t.i + t.h) / (2 * t.h)); return c; };
      const rail = sg => spine.map((p, i) => { const a2 = spine[Math.max(0, i - 2)], b2 = spine[Math.min(spine.length - 1, i + 2)], l = Math.hypot(b2[0] - a2[0], b2[1] - a2[1]) || 1, ww = w / 2 * (0.8 + 0.4 * nz(ph2 + i / per)) * sideOf(i) * sg; return [p[0] - (b2[1] - a2[1]) / l * ww, p[1] + (b2[0] - a2[0]) / l * ww]; });
      L_.ribbonRails.push(rail(1), rail(-1));
      if (lit) { const k = 3 + Math.floor(5 * rR()), sg = rR() < 0.5 ? 1 : -1; for (let j = 0; j < k; j++) { const f = 0.15 + 0.5 * rR(), c = []; for (let i = 0; i < spine.length; i++) { const a2 = spine[Math.max(0, i - 2)], b2 = spine[Math.min(spine.length - 1, i + 2)], l = Math.hypot(b2[0] - a2[0], b2[1] - a2[1]) || 1, ww = w / 2 * (1 - f) * sideOf(i) * sg; c.push([spine[i][0] - (b2[1] - a2[1]) / l * ww, spine[i][1] + (b2[0] - a2[0]) / l * ww]); } L_.ribbonRails.push(...dryBrushL(c, 0.35)); } }
      else L_.ribbonBody.push({ spine, w });
    }
  }
  // ---- slash (§2.6): restated chords, shard wedges, rarely an X
  if (effS > 0) {
    const rS = rngFor(seed, 6187), nC = Math.round(effS * (1 + 2 * rS())), cands = [];
    for (let t = 0; t < 60; t++) {
      const x = 20 + (W - 40) * rS(), y = 20 + (H - 40) * rS(), a = rS() * Math.PI, len = 40 + 100 * rS(), dx = Math.cos(a), dy = Math.sin(a);
      const P = []; for (let s2 = -len / 2; s2 <= len / 2; s2 += 1) { const px = x + dx * s2, py = y + dy * s2; if (px > 3 && py > 3 && px < W - 3 && py < H - 3) P.push([px, py]); }
      if (P.length < 60) continue;
      const labs = new Set(); let inJmm = 0, cut = 0, k = 0;
      for (let i = 0; i < P.length; i += 2) { const c = cellOf(P[i][0], P[i][1]); if (Db.d[c] < 1.2) labs.add(Db.L[c]); if (isJ(P[i][0], P[i][1])) inJmm += 2; const th = theta(P[i][0], P[i][1]); cut += Math.abs(Math.sin(th - a)); k++; }
      if (inJmm > 20 || labs.size < 2) continue;
      cands.push({ P, a, sc: labs.size + 2 * cut / k + rS() });
    }
    cands.sort((p, q) => q.sc - p.sc);
    for (const c of cands.slice(0, nC)) {
      const m = 2 + Math.floor(3 * rS()); let off = 0;
      for (let j = 0; j < m; j++) { off += j ? 0.2 + 0.6 * rS() : 0; const da = rad((rS() - 0.5) * 2.4), s0 = Math.floor((3 + 12 * rS()) * (rS() < 0.5 ? 1 : 0)), s1 = c.P.length - 1 - Math.floor(3 + 12 * rS()); const mid = c.P[Math.floor(c.P.length / 2)];
        L_.chords.push(c.P.slice(s0, s1).map(p => { const dx = p[0] - mid[0], dy = p[1] - mid[1]; return [mid[0] + dx * Math.cos(da) - dy * Math.sin(da) - Math.sin(c.a) * off, mid[1] + dx * Math.sin(da) + dy * Math.cos(da) + Math.cos(c.a) * off]; })); }
    }
    // wedges: in gaps 6–20 mm from the drawing between two lineages, 5–14 converging lines as one zig-zag
    const rW = rngFor(seed, 6188), nW = Math.round(effS * (2 + 4 * rW()));
    for (let t = 0, made = 0; t < 200 && made < nW; t++) {
      const x = 10 + (W - 20) * rW(), y = 10 + (H - 20) * rW(), c = cellOf(x, y); if (Db.d[c] < 6 || Db.d[c] > 20 || isJ(x, y)) continue;
      const labs = new Set(); for (let q = 0; q < 12; q++) { const a = q * Math.PI / 6, cc = cellOf(x + Math.cos(a) * (Db.d[c] + 2), y + Math.sin(a) * (Db.d[c] + 2)); if (Db.d[cc] < 1.5) labs.add(Db.L[cc]); }
      if (labs.size < 2) continue;
      const a = rW() * Math.PI * 2, len = 20 + 50 * rW(), wd = 4 + 10 * rW(), n = 5 + Math.floor(10 * rW()), apex = [x + Math.cos(a) * len, y + Math.sin(a) * len], Z = [];
      for (let i = 0; i < n; i++) { const f = Math.pow(i / (n - 1), 0.7 + 0.8 * rW()) - 0.5, bx = x - Math.sin(a) * wd * f, by = y + Math.cos(a) * wd * f; if (i % 2) Z.push([bx, by], apex.slice()); else Z.push(apex.slice(), [bx, by]); }
      L_.wedges.push(resample(Z, 0.7)); made++;
    }
    if (rW() < 0.35 * effS && chiC_.length) { const c = chiC_[0], a = rW() * Math.PI, b = a + rad(35 + 25 * rW()); for (const an of [a, b]) { const len = 40 + 35 * rW(), k = 3 + Math.floor(3 * rW()); for (let j = 0; j < k; j++) { const o2 = (rW() - 0.5) * 1.2, e = rad((rW() - 0.5) * 3); L_.chords.push(resample([[c.x - Math.cos(an + e) * len / 2 - Math.sin(an) * o2, c.y - Math.sin(an + e) * len / 2 + Math.cos(an) * o2], [c.x + Math.cos(an + e) * len / 2 - Math.sin(an) * o2, c.y + Math.sin(an + e) * len / 2 + Math.cos(an) * o2]], 1)); } } info.X = 1; }
  }
  // ---- fans (§2.4): radiating strokes from inside the strongest bends
  if (cov > 0) {
    const rN = rngFor(seed, 6186), nF = cov > 1.5 ? 1 : 0   /* r1–r2: rosettes read stamped; only at the top of cover */, bends = [], used = new Set();
    for (const [id, g] of geo) { const n = g.C.length; for (let i = 20; i < n - 20; i += 4) { const k = wrap(g.th[Math.min(n - 1, i + 8)] - g.th[Math.max(0, i - 8)]) / 8, r = 1 / (Math.abs(k) || 1e-9); if (r >= 8 && r <= 35) bends.push({ id, i, r, k }); } }
    bends.sort((a, b) => a.r - b.r);
    for (const b of bends) {
      if (L_.fans.length >= nF) break; if (used.has(b.id)) continue;
      const g = geo.get(b.id), p = g.C[b.i], sg = Math.sign(b.k), ctr = [p[0] + g.nx[b.i] * sg * b.r, p[1] + g.ny[b.i] * sg * b.r];
      if (isJ(ctr[0], ctr[1]) || isJ(p[0], p[1])) continue;
      const pv = [p[0] + (ctr[0] - p[0]) * (0.3 + 0.3 * rN()) * 1.6, p[1] + (ctr[1] - p[1]) * (0.3 + 0.3 * rN()) * 1.6];
      let rays; do { rays = 12 + Math.floor(29 * rN()); } while (L_.fans.some(f => f.rays === rays));
      const base = Math.atan2(p[1] - pv[1], p[0] - pv[0]), Z = []; let ang = base - rays / 2 * rad(3.5);
      for (let q = 0; q < rays; q++) {
        ang += rad(2 + 3 * rN()) * (q ? 1 : 0); const reach = Math.hypot(p[0] - pv[0], p[1] - pv[1]) * (0.6 + 0.4 * rN()) + b.r * 0.4, sag = (0.04 + 0.06 * rN()) * reach, R = [];
        for (let t = 0; t <= 1.0001; t += 0.05) { const d = reach * t, bow = Math.sin(Math.PI * t) * sag; R.push([pv[0] + Math.cos(ang) * d - Math.sin(ang) * bow, pv[1] + Math.sin(ang) * d + Math.cos(ang) * bow]); }
        Z.push(...(q % 2 ? R.reverse() : R));
      }
      L_.fans.push(Object.assign(resample(Z, 0.7), { rays })); used.add(b.id);
    }
  }
  // ---- surprise (§2.7): one region that switches register, touching the drawing
  if (effX > 0) {
    const rX = rngFor(seed, 6189);
    for (let q5 = 0; q5 < (!legacy && effX > 1.3 ? 2 : 1); q5++) if (rX() < 0.6 * effX) {   // over 1.3: a second one, elsewhere
      const kind = legacy ? (rX() < 0.35 ? 'thorn' : 'black') : 'thorn';   // r1 (m5): the crosshatched disc read as a stamp   // r2: rings read as dotted arcs
      const at = chiC_.length && !q5 ? [chiC_[0].x + (rX() - 0.5) * 30, chiC_[0].y + (rX() - 0.5) * 30] : [W * (0.2 + 0.6 * rX()), H * (0.2 + 0.6 * rX())];
      if (kind === 'thorn') { const n = 5 + Math.floor(7 * rX()), a0 = rX() * Math.PI * 2; for (let q = 0; q < n; q++) { if (rX() < 0.12) continue; const a = a0 + q * 2 * Math.PI / n + rad((rX() - 0.5) * 30), len = 12 + 33 * rX(), wd = 1.5 + 3 * rX(), tip = [at[0] + Math.cos(a) * len, at[1] + Math.sin(a) * len];
          for (const sg of [1, -1]) { const b0 = [at[0] - Math.sin(a) * wd * sg, at[1] + Math.cos(a) * wd * sg], R = []; for (let t = 0; t <= 1.0001; t += 0.05) { const bow = -Math.sin(Math.PI * t) * wd * 0.3 * sg; R.push([b0[0] + (tip[0] - b0[0]) * t - Math.sin(a) * bow, b0[1] + (tip[1] - b0[1]) * t + Math.cos(a) * bow]); } L_.surprise.push(R); } } }
      else if (kind === 'rings') { const n = 3 + Math.floor(5 * rX()); for (let q = 0; q < n; q++) { const r = 3 + 6 * rX(), c = [at[0] + (rX() - 0.5) * 30, at[1] + (rX() - 0.5) * 30], a0 = rX() * Math.PI * 2, R = []; for (let t = 0; t < 1.75 * Math.PI; t += 0.15) R.push([c[0] + Math.cos(a0 + t) * r, c[1] + Math.sin(a0 + t) * r]); L_.surprise.push(R); } }
      else { const r = 14 + 12 * rX(); for (const a of [rad(30 + 20 * rX()), rad(-40 - 30 * rX())]) for (let o2 = -r; o2 <= r; o2 += 0.45 + 0.2 * rX()) { const h = Math.sqrt(Math.max(0, r * r - o2 * o2)) * (0.8 + 0.3 * rX()); L_.surprise.push([[at[0] - Math.cos(a) * h - Math.sin(a) * o2, at[1] - Math.sin(a) * h + Math.cos(a) * o2], [at[0] + Math.cos(a) * h - Math.sin(a) * o2, at[1] + Math.sin(a) * h + Math.cos(a) * o2]].map((p, i, A) => p)); } }
      info.surprise = kind;
    }
  }
  // ---- mark top-first, then clip each layer against higher z (§3)
  const markAll = (S, z, r) => { for (const P of S) for (const p of resample(P, 0.7)) M.mark(p[0], p[1], z, 0, r); };
  markAll(L_.chords, DZ.chord, 0.5);
  markAll(L_.cont, DZ.base, 0.8);
  markAll(L_.surprise, DZ.surprise, 0.8);
  for (const b of L_.ribbonBody) for (const p of b.spine) M.mark(p[0], p[1], DZ.ribbon, 0, b.w / 2);
  markAll(L_.ribbonRails, DZ.ribbon, 0.8);
  markAll(L_.fans, DZ.fan, 0.6);
  const clip = (S, z) => { const outS = []; for (const P of S) { let cur = []; for (const p of resample(P, 0.5)) { const o2 = p[0] < 1 || p[1] < 1 || p[0] > W - 1 || p[1] > H - 1 ? 99 : M.owner[cellOf(p[0], p[1])]; if (o2 > z) { if (cur.length > 3) outS.push(cur); cur = []; } else cur.push(p); } if (cur.length > 3) outS.push(cur); } return outS.filter(q => polyLen(q) > 3); };
  const capTo = (S, cap) => { const outS = []; let s2 = 0; for (const P of S) { const l = polyLen(P); if (s2 + l > cap) break; s2 += l; outS.push(P); } return outS; };
  layers.chord = capTo(clip(L_.chords, DZ.chord), caps.slash * 0.6);
  layers.wedge = capTo(clip(L_.wedges, DZ.fan), caps.slash * 0.4 + caps.fans * 0.3);
  layers.cont = capTo(clip(L_.cont, DZ.base), caps.cont * 0.4);
  layers.ribbon = capTo(clip(L_.ribbonRails, DZ.ribbon), caps.cont * 0.6);
  layers.fan = capTo(clip(L_.fans, DZ.fan), caps.fans * 0.7);
  layers.surprise = capTo(clip(L_.surprise, DZ.surprise), caps.surprise);
  // tone T (4 mm grid): activity × chaos × lobe; 0 in J; stretched until p90/p50 ≥ 4
  const Tg = new Float32Array(FX * FY), gh = []; for (const [id, g] of geo) for (let i = 0; i < g.C.length; i += 6) gh.push([g.C[i][0], g.C[i][1], id, i]);
  const GH8 = pointHash(gh, 8);
  for (let j = 0; j < FY; j++) for (let i = 0; i < FX; i++) {
    const x = i * G, y = j * G; if (Jg[j * FX + i]) continue;
    let best = null, bd = 25; const gx = Math.floor(x / 8), gy = Math.floor(y / 8);
    for (let u = -3; u <= 3; u++) for (let v = -3; v <= 3; v++) for (const q of (GH8.get((gx + u) * 4096 + gy + v) || [])) { const d = Math.hypot(q[0] - x, q[1] - y); if (d < bd) { bd = d; best = q; } }
    let lobe = 1;
    if (best) { const g = geo.get(best[2]), k = best[3]; if (Math.abs(g.b[k]) > 0.2) lobe = ((x - g.C[k][0]) * g.nx[k] + (y - g.C[k][1]) * g.ny[k]) * g.b[k] > 0 ? 1.5 : 0.6; }
    Tg[j * FX + i] = (0.35 + Ar(clamp(x, 0, W - 1), clamp(y, 0, H - 1))) * (1 + 0.4 * chi(x, y)) * lobe * Jring[j * FX + i];
  }
  { const vals = Array.from(Tg).filter(v => v > 0).sort((a, b) => a - b), want = cov > 1 ? 6 : 4;
    if (vals.length > 10) { const p = q => vals[Math.floor(q * (vals.length - 1))], mx = vals[vals.length - 1]; let lo = 1, hi = 8;
      for (let it = 0; it < 20; it++) { const gm = (lo + hi) / 2; if (Math.pow(p(0.9), gm) / Math.pow(p(0.5), gm) >= want) hi = gm; else lo = gm; }
      const gm = Math.min(hi, cov > 1 ? 3 : 2.2);   // cover the field: a floor, and the peaks stretched only so far
      for (let c = 0; c < Tg.length; c++) Tg[c] = Tg[c] > 0 ? 0.12 + 0.88 * Math.pow(Tg[c] / mx, gm) : 0; } }
  // r1 → facets: the ground is laid in planes (Voronoi cells 25–50 mm), each with its own direction and
  // weight, so tone changes at edges like brushed planes instead of combing one smooth flow (the hair look)
  const rP = rngFor(seed, 6190), fac = [];
  for (let t = 0; t < 400 && fac.length < 70; t++) { const x = W * rP(), y = H * rP(), sp = 25 + 25 * rP(); if (fac.some(f => Math.hypot(f.x - x, f.y - y) < Math.min(sp, f.sp))) continue; fac.push({ x, y, sp, dth: rad((rP() - 0.5) * 50), w: 0.25 + 1.2 * rP() * rP() + 0.3 * rP() }); }
  const FG = 2, FW = Math.ceil(W / FG), FH = Math.ceil(H / FG), facId = new Int16Array(FW * FH);
  for (let j = 0; j < FH; j++) for (let i = 0; i < FW; i++) { const x = i * FG + 1, y = j * FG + 1 + 3 * nA(ph + 700 + x / 25); let b = 0, bd = 1e18; fac.forEach((f, k) => { const d = (f.x - x) ** 2 + (f.y - y) ** 2; if (d < bd) { bd = d; b = k; } }); facId[j * FW + i] = b; }
  const facAt = (x, y) => facId[clamp(Math.floor(y / FG), 0, FH - 1) * FW + clamp(Math.floor(x / FG), 0, FW - 1)];
  const Tg0 = Tg.slice(), T0 = (x, y) => bil(Tg0, x, y);   // tone before the planes' weights, for the grown field
  for (let j = 0; j < FY; j++) for (let i = 0; i < FX; i++) Tg[j * FX + i] *= fac[facAt(i * G, j * G)].w;
  const T = (x, y) => bil(Tg, x, y);
  // voids (§2.3, r1): hard-edged shards carved out of where the fill would be densest, like the monoprint's cut-outs
  const voidM = new Uint8Array(N);
  if (cov > 0) {
    const rV = rngFor(seed, 6183), cand = [], want = 1 + Math.round(Math.min(1, cov) * 3), kept = [];
    for (let y = 20; y < H - 20; y += 12) for (let x = 20; x < W - 20; x += 12) { const t = T(x, y); if (t > 0.45 && jDist(x, y) > jr + 20 && Db.d[cellOf(x, y)] > 6) cand.push({ x: x + (rV() - 0.5) * 8, y: y + (rV() - 0.5) * 8, t: t + 0.3 * rV() }); }
    cand.sort((a, b) => b.t - a.t);
    for (const c of cand) { if (kept.length >= want) break; if (kept.some(k => Math.hypot(k.x - c.x, k.y - c.y) < 70)) continue; kept.push(c); }
    for (const c of kept) {
      const n = 5 + Math.floor(3 * rV()), R = 12 + 23 * rV(), a0 = rV() * Math.PI * 2, stretch = 1 + 1.2 * rV(), rot = theta(c.x, c.y), poly = [];
      for (let q = 0; q < n; q++) { const a = a0 + q * 2 * Math.PI / n + (rV() - 0.5) * 0.5, r = R * (0.5 + 0.6 * rV()), lx = Math.cos(a) * r * stretch, ly = Math.sin(a) * r; poly.push([c.x + lx * Math.cos(rot) - ly * Math.sin(rot), c.y + lx * Math.sin(rot) + ly * Math.cos(rot)]); }
      const xs = poly.map(p => p[0]), ys = poly.map(p => p[1]);
      for (let y = Math.max(0, Math.floor(Math.min(...ys))); y < Math.min(H, Math.ceil(Math.max(...ys))); y++) for (let x = Math.max(0, Math.floor(Math.min(...xs))); x < Math.min(W, Math.ceil(Math.max(...xs))); x++) {
        let inside = false; for (let a = 0, b = n - 1; a < n; b = a++) { const [xa, ya] = poly[a], [xb, yb] = poly[b]; if ((ya > y + 0.5) !== (yb > y + 0.5) && x + 0.5 < (xb - xa) * (y + 0.5 - ya) / (yb - ya) + xa) inside = !inside; }
        if (inside) voidM[y * GW + x] = 1;
      }
    }
    info.voids = kept.length;
  }

  // ---- ground (§2.2): scrubs, one pen-down path of 3–9 passes along θ; candidates fixed per cell so the dial only adds
  const lognorm = (r, med, s) => med * Math.exp(s * Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r()));
  const scrub = (x0, y0, r, dth) => {
    const f0 = facAt(x0, y0), bleed = r() < 0.1;
    { const th0 = theta(x0, y0) + dth + fac[f0].dth; for (let b = 0; b < 160; b++) { const bx = x0 - Math.cos(th0) * 0.5, by = y0 - Math.sin(th0) * 0.5; if (bx < 3 || by < 3 || bx > W - 3 || by > H - 3 || facAt(bx, by) !== f0 || M.owner[cellOf(bx, by)] > zG || voidM[cellOf(bx, by)]) break; x0 = bx; y0 = by; } }   // r2: both ends on the plane's edge
    const u0 = r(), passes = u0 < 0.4 ? 1 : u0 < 0.8 ? 2 : 3, dir0 = 1, side = r() < 0.5 ? 1 : -1, adv = () => 0.15 + 0.45 * r();   // r1: long drags that overlap for tone
    const nz = noise1(r), nph = r() * 100; let x = x0, y = y0, dir = 1, P = [], s = 0; r();
    for (let k = 0; k < passes; k++) {
      const len = clamp(lognorm(r, 50, 0.5), 20, 130) * (k ? 0.5 + 0.4 * r() : 1); let t = 0, moved = 0;
      while (t < len) {
        const th = theta(x, y) + dth + fac[f0].dth, lat = nz(nph + s / 18) * 0.06;
        const nx = x + dir * Math.cos(th) * 0.5 - Math.sin(th) * lat, ny = y + dir * Math.sin(th) * 0.5 + Math.cos(th) * lat;
        if (nx < 3 || ny < 3 || nx > W - 3 || ny > H - 3 || M.owner[cellOf(nx, ny)] > zG || (evt ? 0.6 : T(nx, ny)) < 0.06 + 0.12 * (0.5 + 0.5 * dry(nx / 9, ny / 9)) || isJ(nx, ny) || voidM[cellOf(nx, ny)] || (facAt(nx, ny) !== f0 && !bleed)) break;
        x = nx; y = ny; P.push([x, y]); t += 0.5; s += 0.5; moved++;
      }
      if (moved < 4 && k === 0) return null;
      if (moved < 4) break;
      const th = theta(x, y) + dth + fac[f0].dth, a = adv(), hx = dir * Math.cos(th), hy = dir * Math.sin(th), qx = -Math.sin(th) * side, qy = Math.cos(th) * side;
      x += qx * a + hx * 0.4; y += qy * a + hy * 0.4; P.push([x, y]); dir = -dir;   // a sharp turn, the return shorter: ends stagger instead of pills
    }
    return P.length > 30 ? P : null;
  };
  // dry-brush: noise stretched 8:1 along the scrub's heading breaks neighbouring passes in aligned skips
  const dryBrush = P => {
    const a = P[0], b = P[Math.min(P.length - 1, 40)], h = Math.atan2(b[1] - a[1], b[0] - a[0]), c = Math.cos(h), sn = Math.sin(h), pieces = []; let cur = [];
    for (const p of P) {
      const u = (p[0] * c + p[1] * sn) / 40, v = (-p[0] * sn + p[1] * c) / 5, thr = 0.55 - 0.45 * T(p[0], p[1]);
      if (dry(u, v) > thr) { if (cur.length) pieces.push(cur); cur = []; } else cur.push(p);
    }
    if (cur.length) pieces.push(cur);
    const merged = []; for (const q of pieces) { const l = merged[merged.length - 1]; if (l && Math.hypot(q[0][0] - l[l.length - 1][0], q[0][1] - l[l.length - 1][1]) < 1) l.push(...q); else merged.push(q); }
    return merged.filter(q => polyLen(q) >= 6);
  };
  const otherInk = ['chord', 'wedge', 'cont', 'ribbon', 'fan', 'surprise'].reduce((t, k) => t + (layers[k] || []).reduce((u, P) => u + polyLen(P), 0), 0);
  const groundCap = Math.max(0, room - otherInk) * smooth(0, 1, cov);   // what the other layers left
  // ---- grow (meander 5): the field grown out of the lines as echo trains; planes get what's left
  const pv5 = legacy ? 1 : clamp(prm.planes, 0, 1), growCap = legacy ? 0 : pv5 < 0.5 ? groundCap - Math.min(groundCap * (0.05 + 0.4 * pv5), 1500 + 5000 * pv5) : groundCap * trainShare;   // below 0.5 the planes are only events: a small share
  if (growCap > 0) { const g5 = growField({ seed, cap: growCap, mu, out, layers, voidM, isJ: (x, y) => jDist(x, y) < 0.4 * jr, T0, Db, info }); /* grown fields may come closer to knots than planes */ layers.grow = g5; for (const P of g5) for (const p of P) M.mark(p[0], p[1], DZ.fan, 0, 0.7); }
  // below planes 0.5 the planes are events: a few facets that cross the lines (and the grown field), laid over them
  const planesV = legacy ? 1 : clamp(prm.planes, 0, 1), evt = !legacy && planesV < 0.5, zG = evt ? DZ.base : DZ.ground;
  let evtF = null;
  if (evt) { const rE = rngFor(seed, 6195), fs = fac.map((f, k) => ({ k, d: Db.d[cellOf(clamp(f.x, 0, W - 1), clamp(f.y, 0, H - 1))], u: rE() })).filter(f => f.d < 10 && !isJ(fac[f.k].x, fac[f.k].y) && chi(fac[f.k].x, fac[f.k].y) < 0.3)   /* r2: events in the chaos zone read as hairballs */.sort((a, b) => a.u - b.u); evtF = new Set(fs.slice(0, 1 + Math.round(4 * planesV)).map(f => f.k)); info.events = evtF.size; }
  const planeCap = groundCap - growCap;
  if (planeCap > 0) {
    const C = 10, cells = [];
    for (let cy2 = 0; cy2 < Math.ceil(H / C); cy2++) for (let cx2 = 0; cx2 < Math.ceil(W / C); cx2++) {
      const x = cx2 * C + C / 2, y = cy2 * C + C / 2, t = evt ? Math.max(0.5, T(x, y)) : T(x, y); if (t <= 0.02 || (evtF && !evtF.has(facAt(x, y)))) continue;
      const cross = chi(x, y) > 0.5 || cov > 1 || dry(x / 30 + 7, y / 30 + 3) > 0.45 && t > 0.6;
      cells.push({ i: cy2 * 100 + cx2, x0: cx2 * C, y0: cy2 * C, w: Math.pow(t, 1.3), cross });
    }
    // candidate j of a cell is kept when its fixed uniform < expected share: raising dmax only adds
    const cand = [];
    for (const c of cells) { const r = rngFor(seed, 6181, c.i); for (let j = 0; j < 14; j++) cand.push({ c, j, u: r(), x: c.x0 + C * r(), y: c.y0 + C * r(), cr: c.cross && r() < 0.5 }); }
    const made = new Map(), make = q => { const k = q.c.i * 16 + q.j; if (!made.has(k)) { const r = rngFor(seed, 6181, q.c.i, q.j + 1); const P = scrub(q.x, q.y, r, q.cr ? rad(25 + 15 * r()) : 0); made.set(k, P ? dryBrush(P) : []); } return made.get(k); };
    const inkAt = dm => { let s = 0; const keep = []; for (const q of cand) if (q.u < clamp(dm * q.c.w, 0, 1)) { const ps = make(q); if (ps.length) { keep.push(ps); for (const p of ps) s += polyLen(p); } } return { s, keep }; };
    let lo = 0, hi = 1, res = inkAt(hi); while (res.s < planeCap && hi < 64) { lo = hi; hi *= 2; res = inkAt(hi); }
    for (let it = 0; it < 7; it++) { const mid = (lo + hi) / 2, r2 = inkAt(mid); if (r2.s > planeCap) hi = mid; else { lo = mid; res = r2; } }
    layers.ground = res.keep.flat();
  }

  // ---- order density strokes (greedy nearest end, with reversal), then emit per layer
  const order = S => {
    const left = S.slice(), outS = []; let cur = [0, 0];
    while (left.length) {
      let bi = 0, bd = 1e18, rev = false;
      for (let i = 0; i < left.length; i++) { const P = left[i], a = P[0], b = P[P.length - 1], da = (a[0] - cur[0]) ** 2 + (a[1] - cur[1]) ** 2, db = (b[0] - cur[0]) ** 2 + (b[1] - cur[1]) ** 2; if (da < bd) { bd = da; bi = i; rev = false; } if (db < bd) { bd = db; bi = i; rev = true; } }
      const P = left.splice(bi, 1)[0], Q = rev ? P.slice().reverse() : P; const l = outS[outS.length - 1];
      if (l && Math.hypot(Q[0][0] - l[l.length - 1][0], Q[0][1] - l[l.length - 1][1]) < 1.2) l.push(...Q); else outS.push(Q);
      cur = Q[Q.length - 1];
    }
    return outS;
  };
  const added = [];
  for (const k of ['grow', 'ground', 'fan', 'wedge', 'ribbon', 'cont', 'surprise', 'chord']) if (layers[k] && layers[k].length) { const S = order(layers[k]); added.push({ core: -1, kind: 'd-' + k, strokes: S }); info.layers[k] = { mm: Math.round(S.reduce((a, s) => a + polyLen(s), 0)), strokes: S.length }; }
  // metrics
  const inkAll = baseInk + added.reduce((a, l) => a + l.strokes.reduce((b, s) => b + polyLen(s), 0), 0);
  info.inkM = +(inkAll / 1000).toFixed(1); info.lifts = out.reduce((a, l) => a + l.strokes.length, 0) + added.reduce((a, l) => a + l.strokes.length, 0);
  { let vis = 0, tot = 0; const dm = new Uint8Array(N); for (const l of added) for (const st of l.strokes) for (const p of st) dm[cellOf(p[0], p[1])] = 1;
    for (const l of out) for (const st of l.strokes) for (let i = 0; i < st.length; i += 3) { tot++; if (!dm[cellOf(st[i][0], st[i][1])]) vis++; }
    info.baseVis = +(vis / (tot || 1)).toFixed(3);
    let jc = 0, jt = 0; for (let y = 1; y < H; y += 2) for (let x = 1; x < W; x += 2) if (isJ(x, y)) { jt++; if (!dm[cellOf(x, y)]) jc++; } info.juncClear = +(jc / (jt || 1)).toFixed(3); }
  out.push(...added);
  return info;
}

// ======================= meander 5: the grown field =======================
// See docs/research/meander5/brainstorm.md. Echo trains: each echo is offset from the PREVIOUS echo (never the
// source), so whatever happens to one echo is inherited by every later one. Curvature-driven migration (the
// outside of a bend moves faster) keeps trains from reading as tree rings; mutations (swale, buckle → oxbow,
// chute, fan, split) arise, peak and fade under accumulating smoothing. Trains stop at other lines, at other
// trains (so sets truncate each other like scroll-bar generations), at voids, knots' quiet zones and low tone.
function growField(o) {
  const { seed, cap, mu, out, layers, voidM, isJ, T0, Db, info } = o;
  const rG = rngFor(seed, 6191), occ = new Int32Array(N).fill(-1), gOwn = new Int32Array(N).fill(-1), gK = new Int32Array(N), src = [];
  const addSrc = (P, seedable) => { if (P.length < 3) return; const id = src.length; src.push({ P, seedable, id });
    for (const p of resample(P, 0.5)) for (const [a, b] of [[-0.5, -0.5], [0.5, -0.5], [-0.5, 0.5], [0.5, 0.5]]) { const x = Math.floor(p[0] + a), y = Math.floor(p[1] + b); if (x >= 0 && y >= 0 && x < GW && y < GH) occ[y * GW + x] = id; } };
  for (const l of out) for (const st of l.strokes) addSrc(st, polyLen(st) >= 25);
  for (const k of ['cont', 'ribbon']) for (const st of (layers[k] || [])) addSrc(st, polyLen(st) >= 25);
  for (const k of ['chord', 'wedge', 'fan', 'surprise']) for (const st of (layers[k] || [])) addSrc(st, false);
  const cellOk = (x, y) => x >= 3 && y >= 3 && x <= W - 3 && y <= H - 3;
  const lognorm = (r, med, s) => med * Math.exp(s * Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r()));
  // seeds: sub-arcs centred on bends (point-bar side) or straight reaches (alternating), ranked by bend × open ground × tone
  const cands = [];
  for (const s of src) {
    if (!s.seedable) continue;
    const R = resample(s.P, 1), k = curvatureOf(R), n = R.length; let alt = rG() < 0.5 ? 1 : -1;
    for (let i = 8 + Math.floor(rG() * 15); i < n - 8; i += 15 + Math.floor(15 * rG())) {
      let bi = i, bk = 0; for (let j = Math.max(0, i - 12); j < Math.min(n, i + 12); j++) if (Math.abs(k[j]) > bk) { bk = Math.abs(k[j]); bi = j; }
      const bend = bk > 0.02; for (const pref of [1, 0]) { const sg = (bend ? Math.sign(k[bi]) : (pref ? (alt = -alt) : alt)) * (pref ? 1 : -1);
      const a = R[Math.max(0, bi - 1)], b = R[Math.min(n - 1, bi + 1)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, nx = -(b[1] - a[1]) / l * sg, ny = (b[0] - a[0]) / l * sg;
      let open = 0; for (const d of [1.5, 5, 10, 16]) { const x = R[bi][0] + nx * d, y = R[bi][1] + ny * d; if (!cellOk(x, y)) break; const c = cellOf(x, y), oc = occ[c]; if ((oc >= 0 && oc !== s.id) || isJ(x, y) || voidM[c]) break; open++; }
      if (open < 2) continue;
      const len = clamp(lognorm(rG, bend ? Math.max(60, 0.9 * Math.PI / (bk || 1)) : 90, 0.4), 40, 220);
      cands.push({ s, ci: bi, len, sg, sc: (0.4 + Math.min(1, bk * 30)) * open * (0.3 + T0(R[bi][0], R[bi][1])) * (0.4 + rG()) * (pref ? 1 : 0.45), u: rG(), R }); }
    }
  }
  cands.sort((a, b) => b.sc - a.sc);
  const stop = {}, covered = new Map(), log = { stop, trains: 0, echoes: 0, swale: 0, buckle: 0, oxbow: 0, chute: 0, fan: 0, split: 0 }, trainsOut = [];
  let ink = 0, tid = 0;
  const ring = { ink: 0, plain: 0 };
  const echoTrain = (P0, sg, st) => {
    const rT = rngFor(seed, 6192, st.tid, st.gen || 0), nzT = noise1(rT), outP = [], slideInit = 0, gaps = []; let slide = 0, cur = resample(P0, 0.5), g = st.g, muts = 0, oxb = 0, L0 = polyLen(P0), chutes = [], bumpAt = -1, active = 0, inkT = 0;
    const queue = [];
    let endWhy = 'end';
    for (let k = st.k0 || 0; k < (st.k0 || 0) + st.K && ink + inkT < cap; k++) {
      const kk = k - (st.k0 || 0);
      const n = cur.length; if (n < 16) { stop.short = (stop.short || 0) + 1; break; }
      let kap = curvatureOf(cur); for (let pass = 0; pass < 2; pass++) { const t = new Float64Array(n); let acc = 0; const w = 16; for (let i = -w; i < n + w; i++) { if (i + w < n) acc += kap[Math.min(n - 1, i + w)]; if (i - w - 1 >= 0) acc -= kap[i - w - 1]; if (i >= 0 && i < n) t[i] = acc / (Math.min(n - 1, i + w) - Math.max(0, i - w) + 1); } kap = t; }   // bend scale (~16 mm), not the hand's tremor
      let km = 0; for (let i = 0; i < n; i++) km += Math.abs(kap[i]); km = Math.max(km / n, 0.004);
      if (km > 1 / 12) { stop.ring = (stop.ring || 0) + 1; break; }   // closing on a point: a target, not a field
      // mutations: rolled once per echo after the second, capped per train
      let bump = null;
      if (kk >= 2 && muts < st.mcap) {
        const r = rT();
        if (r < 0.06 * mu) { g = clamp(g * (rT() < 0.35 ? 0.45 : 1.6 + 0.9 * rT()), 0.35, 2.2); muts++; log.swale++; active = 8; }
        else if (r < 0.11 * mu) { let bi = 0, bk = 1e9; for (let t = 0; t < 6; t++) { const i = Math.floor(n * (0.2 + 0.6 * rT())); if (Math.abs(kap[i]) < bk) { bk = Math.abs(kap[i]); bi = i; } } bump = { i: bi, w: (15 + 30 * rT()) / 0.5, a: g * (1 + 2 * rT()), lam: 14 + 22 * rT() /* r2: short wavelengths amplified into cloud scallops */ }; muts++; log.buckle++; active = 30; }
        else if (r < 0.15 * mu) { const p = cur[Math.floor(n * (0.15 + 0.7 * rT()))]; chutes.push({ x: p[0], y: p[1], w: 3 + 5 * rT(), gr: 1.15 + 0.25 * rT() }); muts++; log.chute++; }
        else if (r < 0.18 * mu && !st.child && n > 120) { const i = Math.floor(n * (0.35 + 0.3 * rT())); queue.push({ P: cur.slice(i), g: clamp(g * (0.6 + rT()), 0.35, 2.2) }); cur = cur.slice(0, i + 1); muts++; log.split++; continue; }
      }
      g = clamp(g * (1 + (rT() - 0.5) * 0.16) * st.open, 0.3, 2.2); gaps.push(g);   // r1: tight at the source, opening outward
      // offset with curvature-driven migration and the train's fan hinge
      const sAt = new Float32Array(n); for (let i = 1; i < n; i++) sAt[i] = sAt[i - 1] + Math.hypot(cur[i][0] - cur[i - 1][0], cur[i][1] - cur[i - 1][1]); slide += (rT() - 0.5) * 3;
      let E = [];
      for (let i = 0; i < n; i++) {
        const a = cur[Math.max(0, i - 2)], b = cur[Math.min(n - 1, i + 2)], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, nx = -(b[1] - a[1]) / l * sg, ny = (b[0] - a[0]) / l * sg;
        let d = g * (1 - st.beta * clamp(kap[i] * sg / km, -2, 2) * 0.5) * (1 + st.phi * (i / (n - 1) - 0.5)) * (1 + st.pinch * nzT(st.ph + (sAt[i] + slide) / st.lam));   // pinch: gap varies along the arc and accumulates, so sets pinch and open like grain
        if (bump && Math.abs(i - bump.i) < bump.w / 2) { const t = (i - bump.i) / (bump.w / 2); d += bump.a * 0.5 * (1 + Math.cos(Math.PI * t)) * Math.sin(2 * Math.PI * (i - bump.i) * 0.5 / bump.lam); }
        d = clamp(d, 0.3, 5);
        E.push([cur[i][0] + nx * d, cur[i][1] + ny * d]);
      }
      // cusps: drop points whose step runs backwards against the parent's
      E = E.filter((p, i) => { if (i === 0 || i === n - 1) return true; const q = E[i + 1], r0 = E[i - 1], dx = q[0] - r0[0], dy = q[1] - r0[1], ex = cur[i + 1][0] - cur[i - 1][0], ey = cur[i + 1][1] - cur[i - 1][1]; return dx * ex + dy * ey > 0; });
      // accumulating smoothing, then even spacing
      for (let pass = 0, np = Math.min(9, 3 + (k >> 3)); pass < np; pass++) E = E.map((p, i) => i === 0 || i === E.length - 1 ? p : [p[0] + 0.22 * ((E[i - 1][0] + E[i + 1][0]) / 2 - p[0]), p[1] + 0.22 * ((E[i - 1][1] + E[i + 1][1]) / 2 - p[1])]);
      E = resample(E, 0.5); if (E.length < 16) break;
      // staggered ends: each end trimmed on its own
      const endAdj = (Q, atEnd) => { const e = Math.round((rT() - 0.42) * 7); if (e < 0) return atEnd ? Q.slice(0, Q.length + e) : Q.slice(-e); if (!e) return Q;   // each end trims or runs on by itself: ends stagger, sets can lengthen
        const m = Q.length, a = atEnd ? Q[m - 4] : Q[3], b = atEnd ? Q[m - 1] : Q[0], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, ext = []; for (let j = 1; j <= e; j++) ext.push([b[0] + (b[0] - a[0]) / l * 0.5 * j, b[1] + (b[1] - a[1]) / l * 0.5 * j]); return atEnd ? Q.concat(ext) : ext.reverse().concat(Q); };
      E = endAdj(endAdj(E, true), false); if (E.length < 16) break;
      // cutoff: a neck (two points far apart along the echo, close in space) is spliced; the loop left behind is an oxbow
      if (active > 0 && oxb < 2) { active--;
        outer: for (let i = 0; i < E.length - 40; i += 2) for (let j = i + 40; j < E.length; j += 2) if (Math.abs(E[i][0] - E[j][0]) < 1.6 && Math.hypot(E[i][0] - E[j][0], E[i][1] - E[j][1]) < Math.max(0.8, 1.5 * g)) {
          const loop = E.slice(i, j + 1); loop.push(E[i].slice()); let mnx = 1e9, mxx = -1e9, mny = 1e9, mxy = -1e9; for (const p of loop) { mnx = Math.min(mnx, p[0]); mxx = Math.max(mxx, p[0]); mny = Math.min(mny, p[1]); mxy = Math.max(mxy, p[1]); }
          if (Math.max(mxx - mnx, mxy - mny) >= 6) { outP.push(loop); log.oxbow++; oxb++; }
          E = E.slice(0, i + 1).concat(E.slice(j)); break outer; } }
      // clip: other lines, other trains, voids, quiet zones, low tone, inherited chutes
      const blocked = p => { if (!cellOk(p[0], p[1])) return true; const c = cellOf(p[0], p[1]), oc = occ[c], go = gOwn[c]; if ((oc >= 0 && oc !== st.src) || (go >= 0 && (go !== st.tid || gK[c] < k - Math.max(3, Math.ceil(2.2 / g)))) || voidM[c] || isJ(p[0], p[1])) return true; for (const ch of chutes) if (Math.hypot(p[0] - ch.x, p[1] - ch.y) < ch.w / 2) return true; return false; };
      const runs = []; let rc = [];
      for (const p of E) { if (blocked(p)) { if (rc.length >= 8) runs.push(rc); rc = []; } else rc.push(p); }
      if (rc.length >= 8) runs.push(rc);
      // chutes follow the echo and widen
      for (const ch of chutes) { let bd = 1e9, bp = null; for (const p of E) { const d = Math.hypot(p[0] - ch.x, p[1] - ch.y); if (d < bd) { bd = d; bp = p; } } if (bp && bd < 6) { ch.x = bp[0]; ch.y = bp[1]; ch.w = Math.min(ch.w * ch.gr, 30); } }
      if (!runs.length) { stop.blocked = (stop.blocked || 0) + 1; break; }
      runs.sort((a, b) => b.length - a.length);
      // r1: ends cut by an obstacle feather back (each echo by its own amount) instead of stopping on the mask's edge
      for (let q = 0; q < runs.length; q++) { let rn = runs[q]; const fa = Math.floor(lognorm(rT, 9, 0.8)), fb = Math.floor(lognorm(rT, 9, 0.8)); const a = rn[0] !== E[0] ? Math.min(fa, rn.length / 3 | 0) : 0, b = rn[rn.length - 1] !== E[E.length - 1] ? Math.min(fb, rn.length / 3 | 0) : 0; runs[q] = rn.slice(a, rn.length - b); }
      const late = (kk + 1) / st.K, drop = late > 0.7 && rT() < (late - 0.7) * 1.6;   // r1: trains thin out toward their end (the echo is still inherited)
      for (const rn of runs) { for (const p of rn) { const c = cellOf(p[0], p[1]); gOwn[c] = st.tid; gK[c] = k; } if (drop) continue; const l = (rn.length - 1) * 0.5; inkT += l; outP.push(k % 2 ? rn.slice().reverse() : rn); }
      for (const rn of runs.slice(1)) if (rn.length > 40 && queue.length < 6) queue.push({ P: rn, g });
      log.echoes++;
      cur = runs[0]; if (cur.length < 20) { stop.run = (stop.run || 0) + 1; break; } if ((cur.length - 1) * 0.5 > 1.6 * L0 + 20) { stop.long = (stop.long || 0) + 1; endWhy = 'long'; break; }
      if (kk === st.K - 1) { stop.K = (stop.K || 0) + 1; endWhy = 'K'; }
    }
    return { outP, inkT, queue, gaps, muts, why: endWhy, cur, kEnd: (st.k0 || 0) + st.K };
  };
  for (const c of cands) {
    if (ink >= cap) break;
    const key = c.s.id * 2 + (c.sg > 0 ? 1 : 0), cv = covered.get(key) || 0, L0 = (c.R.length - 1); if (cv + c.len > 0.8 * L0 + 30) continue;
    const i0 = Math.max(0, Math.round(c.ci - c.len / 2)), i1 = Math.min(c.R.length, Math.round(c.ci + c.len / 2)); if (i1 - i0 < 25) continue;
    covered.set(key, cv + (i1 - i0));
    const rS = rngFor(seed, 6193, tid), young = log.trains < 4;
    const st = { tid: tid++, src: c.s.id, open: 1 + 0.035 * rS() * rS() * (rS() < 0.75 ? 1 : 0), g: 0.35 + 1.0 * rS() * rS(), beta: (0.15 + 0.45 * mu) * (0.6 + 0.8 * rS()), phi: rS() < 0.3 + 0.4 * mu ? (rS() < 0.5 ? -1 : 1) * (0.3 + 0.6 * rS()) * Math.min(1, mu + 0.3) : 0, mcap: 1 + Math.round(3 * mu * (young ? 1.5 : 0.7)), K: Math.round(clamp(lognorm(rS, young ? 45 : 24, 0.5), 6, 110)), pinch: 0.25 + 0.45 * rS(), lam: 15 + 35 * rS(), ph: rS() * 100 };
    if (st.phi) log.fan++;
    const todo = [{ P: c.R.slice(i0, i1), st }];
    while (todo.length && ink < cap) {
      const t = todo.shift(), r = echoTrain(t.P, c.sg, t.st);
      if (r.outP.length) { trainsOut.push(...r.outP); ink += r.inkT; log.trains++; ring.ink += r.inkT; if (r.muts === 0 && r.gaps.length >= 6) { const m = r.gaps.reduce((a, b) => a + b, 0) / r.gaps.length, sd = Math.sqrt(r.gaps.reduce((a, b) => a + (b - m) ** 2, 0) / r.gaps.length); if (sd / m < 0.2) ring.plain += r.inkT; } }
      for (const q of r.queue) todo.push({ P: q.P, st: { ...t.st, tid: tid++, g: q.g, child: true, K: Math.max(4, Math.round(t.st.K * 0.6)) } });
      if (r.why !== 'end' && (t.st.gen || 0) < 3 && r.cur.length > 40) {   // a new generation: same train, re-rolled gap, migration, fan and mutation cap
        const rN = rngFor(seed, 6194, t.st.tid, t.st.gen || 0); log.gen = (log.gen || 0) + 1;
        todo.push({ P: r.cur, st: { ...t.st, gen: (t.st.gen || 0) + 1, k0: r.kEnd, g: clamp(t.st.g * (0.5 + 0.9 * rN()), 0.4, 1.3), pinch: 0.2 + 0.5 * rN(), lam: 15 + 35 * rN(), ph: rN() * 100, beta: (0.15 + 0.45 * mu) * (0.4 + 1.2 * rN()), phi: rN() < 0.4 ? (rN() - 0.5) * 1.4 * Math.min(1, mu + 0.3) : 0, mcap: 1 + Math.round(3 * mu * rN()), K: Math.round(clamp(lognorm(rN, 22, 0.5), 6, 60)) } });
      }
    }
  }
  log.mm = Math.round(ink); log.ring = +(ring.plain / (ring.ink || 1)).toFixed(2); log.cands = cands.length;
  info.grow = log;
  return trainsOut;
}
