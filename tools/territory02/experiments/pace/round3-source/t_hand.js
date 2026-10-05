
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
