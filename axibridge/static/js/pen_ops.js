// pen_ops.js — pure curve-editing operations for the pen tool (pen v2).
//
// No DOM, no imports: every function takes plain data and returns NEW objects,
// never mutating its inputs. The data shapes mirror axibridge/sources/pen.py:
//
//   anchor  = {x, y, in_handle, out_handle, join}
//             handles are RELATIVE [dx, dy] or null; join is
//             "corner" | "smooth" | "symmetric" | null (null = infer)
//   subpath = {anchors, closed, kind}   kind: "bezier" | "curvature"
//
// Segment k runs anchor k -> anchor k+1; a closed subpath adds the closing
// segment (last -> first) as segment n-1. A null handle puts that control
// point ON its anchor, exactly as pen.py's _flatten_subpath does, so every
// cubic here is the cubic the server flattens.

/** @typedef {[number, number]} Vec */
/** @typedef {{x:number, y:number, in_handle:Vec|null, out_handle:Vec|null, join?:string|null}} Anchor */
/** @typedef {{anchors:Anchor[], closed:boolean, kind?:string}} Subpath */

const ANGLE_EPS = 1e-6;   // rad: "collinear-opposite"
const LEN_EPS = 1e-6;     // mm: "equal length"
const T_EPS = 1e-9;       // a crossing this close to a segment end IS the anchor
const JOINS = new Set(["corner", "smooth", "symmetric"]);

// ---------------------------------------------------------------- helpers

const hyp = (v) => Math.hypot(v[0], v[1]);
const copyH = (h) => (h ? [h[0], h[1]] : null);
const isZero = (h) => !h || (h[0] === 0 && h[1] === 0);

/** @returns {Anchor} */
function cloneAnchor(a) {
  return { ...a, x: a.x, y: a.y, in_handle: copyH(a.in_handle), out_handle: copyH(a.out_handle),
           join: a.join ?? null };
}

/** @returns {Subpath} */
function cloneSubpath(sp, anchors = sp.anchors.map(cloneAnchor)) {
  return { ...sp, anchors, closed: !!sp.closed, kind: sp.kind ?? "bezier" };
}

function segCount(sp) {
  const n = sp.anchors.length;
  if (n < 2) return 0;
  return sp.closed ? n : n - 1;
}

/** The four control points of segment k (absolute). */
function segCtrl(sp, k) {
  const n = sp.anchors.length;
  const a = sp.anchors[k], b = sp.anchors[(k + 1) % n];
  const p0 = [a.x, a.y], p3 = [b.x, b.y];
  const p1 = a.out_handle ? [a.x + a.out_handle[0], a.y + a.out_handle[1]] : p0;
  const p2 = b.in_handle ? [b.x + b.in_handle[0], b.y + b.in_handle[1]] : p3;
  return [p0, p1, p2, p3];
}

function bern(t) {
  const u = 1 - t;
  return [u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t];
}

function bez(c, t) {
  const w = bern(t);
  return [
    w[0] * c[0][0] + w[1] * c[1][0] + w[2] * c[2][0] + w[3] * c[3][0],
    w[0] * c[0][1] + w[1] * c[1][1] + w[2] * c[2][1] + w[3] * c[3][1],
  ];
}

function bezD1(c, t) {
  const u = 1 - t;
  return [0, 1].map((d) => 3 * u * u * (c[1][d] - c[0][d]) + 6 * u * t * (c[2][d] - c[1][d])
    + 3 * t * t * (c[3][d] - c[2][d]));
}

function bezD2(c, t) {
  return [0, 1].map((d) => 6 * (1 - t) * (c[2][d] - 2 * c[1][d] + c[0][d])
    + 6 * t * (c[3][d] - 2 * c[2][d] + c[1][d]));
}

const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const dist = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]);

function reverseSubpath(sp) {
  const anchors = sp.anchors.slice().reverse().map((a) => {
    const c = cloneAnchor(a);
    return { ...c, in_handle: c.out_handle, out_handle: c.in_handle };
  });
  return cloneSubpath(sp, anchors);
}

// ---------------------------------------------------------------- joins

/**
 * Explicit `join` wins; else both handles present and collinear-opposite
 * (within 1e-6 rad) → "symmetric" if their lengths match within 1e-6 mm,
 * "smooth" otherwise; anything else is a "corner".
 * @param {Anchor} anchor
 * @returns {"corner"|"smooth"|"symmetric"}
 */
export function classifyJoin(anchor) {
  if (JOINS.has(anchor.join)) return /** @type {any} */ (anchor.join);
  const a = anchor.in_handle, b = anchor.out_handle;
  if (!a || !b) return "corner";
  const la = hyp(a), lb = hyp(b);
  if (la < LEN_EPS || lb < LEN_EPS) return "corner";
  const angle = Math.atan2(Math.abs(a[0] * b[1] - a[1] * b[0]), a[0] * b[0] + a[1] * b[1]);
  if (Math.PI - angle > ANGLE_EPS) return "corner";
  return Math.abs(la - lb) <= LEN_EPS ? "symmetric" : "smooth";
}

/**
 * Set one arm to `vec` and move the other per the anchor's join:
 * symmetric → exact opposite; smooth → opposite angle at its own length
 * (an absent other arm stays absent); corner → untouched.
 * `breakJoin` leaves the other arm alone and returns join "corner".
 * @param {Anchor} anchor @param {"in"|"out"} which @param {Vec} vec @param {boolean} breakJoin
 * @returns {Anchor}
 */
export function applyArmDrag(anchor, which, vec, breakJoin) {
  const out = cloneAnchor(anchor);
  const key = which === "in" ? "in_handle" : "out_handle";
  const otherKey = which === "in" ? "out_handle" : "in_handle";
  const v = [vec[0], vec[1]];
  out[key] = v;
  if (breakJoin) {
    out.join = "corner";
    return out;
  }
  const kind = classifyJoin(anchor);
  if (kind === "symmetric") {
    out[otherKey] = [-v[0], -v[1]];
  } else if (kind === "smooth") {
    const other = anchor[otherKey], vl = hyp(v);
    if (other && vl > 1e-12) {
      const L = hyp(other);
      out[otherKey] = [(-v[0] / vl) * L, (-v[1] / vl) * L];
    }
  }
  return out;
}

// ---------------------------------------------------------------- split / nearest / bend

/**
 * Insert an anchor at parameter t of segment segIndex (de Casteljau); the
 * drawn shape is unchanged. The new anchor's join is "smooth". A straight
 * segment (both inner arms absent) stays straight: its new anchor has no arms.
 * @param {Subpath} subpath @param {number} segIndex @param {number} t
 * @returns {Subpath}
 */
export function splitSegment(subpath, segIndex, t) {
  const sp = cloneSubpath(subpath);
  const n = sp.anchors.length;
  if (segIndex < 0 || segIndex >= segCount(sp)) return sp;
  const i = segIndex, j = (segIndex + 1) % n;
  const A = sp.anchors[i], B = sp.anchors[j];
  const [p0, p1, p2, p3] = segCtrl(sp, i);
  const q0 = lerp(p0, p1, t), q1 = lerp(p1, p2, t), q2 = lerp(p2, p3, t);
  const r0 = lerp(q0, q1, t), r1 = lerp(q1, q2, t);
  const s = lerp(r0, r1, t);
  const straight = !A.out_handle && !B.in_handle;
  if (A.out_handle) A.out_handle = [q0[0] - p0[0], q0[1] - p0[1]];
  if (B.in_handle) B.in_handle = [q2[0] - p3[0], q2[1] - p3[1]];
  const mid = {
    x: s[0], y: s[1],
    in_handle: straight ? null : [r0[0] - s[0], r0[1] - s[1]],
    out_handle: straight ? null : [r1[0] - s[0], r1[1] - s[1]],
    join: "smooth",
  };
  sp.anchors.splice(i + 1, 0, mid);
  return sp;
}

/**
 * Closest point of the subpath to (x, y). `t` is the cubic parameter of
 * segment `segIndex` (what splitSegment/bendSegment take). A subpath with no
 * segment reports segIndex -1 and the distance to its single anchor.
 * @param {Subpath} subpath @param {number} x @param {number} y
 * @returns {{segIndex:number, t:number, dist:number}}
 */
export function nearestOnSubpath(subpath, x, y) {
  const P = [x, y];
  const segs = segCount(subpath);
  if (!segs) {
    const a = subpath.anchors[0];
    return { segIndex: -1, t: 0, dist: a ? dist(P, [a.x, a.y]) : Infinity };
  }
  const N = 64;
  let best = { segIndex: 0, t: 0, dist: Infinity };
  for (let k = 0; k < segs; k++) {
    const c = segCtrl(subpath, k);
    let bt = 0, bd = Infinity;
    for (let i = 0; i <= N; i++) {
      const d = dist(P, bez(c, i / N));
      if (d < bd) { bd = d; bt = i / N; }
    }
    // golden-section refine inside the winning sample's neighbourhood
    let lo = Math.max(0, bt - 1 / N), hi = Math.min(1, bt + 1 / N);
    const g = (Math.sqrt(5) - 1) / 2;
    let m1 = hi - g * (hi - lo), m2 = lo + g * (hi - lo);
    let f1 = dist(P, bez(c, m1)), f2 = dist(P, bez(c, m2));
    for (let it = 0; it < 60; it++) {
      if (f1 < f2) { hi = m2; m2 = m1; f2 = f1; m1 = hi - g * (hi - lo); f1 = dist(P, bez(c, m1)); }
      else { lo = m1; m1 = m2; f1 = f2; m2 = lo + g * (hi - lo); f2 = dist(P, bez(c, m2)); }
    }
    const tm = (lo + hi) / 2, dm = dist(P, bez(c, tm));
    if (dm < bd) { bd = dm; bt = tm; }
    if (bd < best.dist) best = { segIndex: k, t: bt, dist: bd };
  }
  return best;
}

/**
 * Drag the curve point at parameter t of segment segIndex onto `target`,
 * moving only that segment's two inner control points by the least total
 * change (Δp1 = b1·d/(b1²+b2²), Δp2 = b2·d/(b1²+b2²)). The two anchors'
 * other arms are then re-mirrored per their joins. t is clamped away from
 * the ends, where the inner controls lose all leverage.
 * @param {Subpath} subpath @param {number} segIndex @param {number} t @param {Vec} target
 * @returns {Subpath}
 */
export function bendSegment(subpath, segIndex, t, target) {
  const sp = cloneSubpath(subpath);
  const n = sp.anchors.length;
  if (segIndex < 0 || segIndex >= segCount(sp)) return sp;
  const tt = Math.min(1 - 1e-3, Math.max(1e-3, t));
  const c = segCtrl(sp, segIndex);
  const cur = bez(c, tt), w = bern(tt);
  const d = [target[0] - cur[0], target[1] - cur[1]];
  const den = w[1] * w[1] + w[2] * w[2];
  const k1 = w[1] / den, k2 = w[2] / den;
  const p1 = [c[1][0] + k1 * d[0], c[1][1] + k1 * d[1]];
  const p2 = [c[2][0] + k2 * d[0], c[2][1] + k2 * d[1]];
  const i = segIndex, j = (segIndex + 1) % n;
  const A = sp.anchors[i], B = sp.anchors[j];
  sp.anchors[i] = applyArmDrag(A, "out", [p1[0] - A.x, p1[1] - A.y], false);
  sp.anchors[j] = applyArmDrag(sp.anchors[j], "in", [p2[0] - B.x, p2[1] - B.y], false);
  return sp;
}

// ---------------------------------------------------------------- curvature pen

/**
 * Curvature-pen handles. Every non-corner anchor with two neighbours gets a
 * tangent parallel to (next − prev), each arm a third of its own side's
 * chord, and join "smooth". Corners (join "corner") and open ends point
 * their arms a third of the way along their own chord(s).
 * @param {Subpath} subpath
 * @returns {Subpath}
 */
export function curvatureHandles(subpath) {
  const sp = cloneSubpath(subpath);
  const src = subpath.anchors, n = src.length;
  if (n < 2) return sp;
  sp.anchors = src.map((a, i) => {
    const out = cloneAnchor(a);
    const hasPrev = sp.closed || i > 0, hasNext = sp.closed || i < n - 1;
    const prev = hasPrev ? src[(i - 1 + n) % n] : null;
    const next = hasNext ? src[(i + 1) % n] : null;
    const toPrev = prev ? [prev.x - a.x, prev.y - a.y] : null;
    const toNext = next ? [next.x - a.x, next.y - a.y] : null;
    if (prev && next && a.join !== "corner") {
      const tan = [next.x - prev.x, next.y - prev.y], tl = hyp(tan);
      if (tl > 1e-12) {
        const u = [tan[0] / tl, tan[1] / tl], lo = hyp(toNext) / 3, li = hyp(toPrev) / 3;
        out.out_handle = [u[0] * lo, u[1] * lo];
        out.in_handle = [-u[0] * li, -u[1] * li];
        out.join = "smooth";
        return out;
      }
    }
    out.out_handle = toNext ? [toNext[0] / 3, toNext[1] / 3] : null;
    out.in_handle = toPrev ? [toPrev[0] / 3, toPrev[1] / 3] : null;
    return out;
  });
  return sp;
}

// ---------------------------------------------------------------- delete with refit

/** Unit direction a segment leaves p0 in (first control distinct from p0). */
function startDir(c) {
  for (const q of [c[1], c[2], c[3]]) {
    const v = [q[0] - c[0][0], q[1] - c[0][1]], l = hyp(v);
    if (l > 1e-9) return [v[0] / l, v[1] / l];
  }
  return null;
}

/**
 * Least-squares fit of one cubic P0..P3 to `pts` keeping both arm
 * DIRECTIONS (d1 out of P0, d2 out of P3 back along the curve); only the two
 * arm lengths are free (Schneider's fit). Returns [alpha, beta].
 */
function fitArmLengths(pts, P0, P3, d1, d2) {
  // chord-length parametrisation, then a few Newton reparametrisations
  const u = [0];
  for (let k = 1; k < pts.length; k++) u.push(u[k - 1] + dist(pts[k], pts[k - 1]));
  const total = u[u.length - 1] || 1;
  for (let k = 0; k < u.length; k++) u[k] /= total;
  const chord = dist(P0, P3);
  let alpha = chord / 3, beta = chord / 3;
  for (let iter = 0; iter < 6; iter++) {
    let c11 = 0, c12 = 0, c22 = 0, x1 = 0, x2 = 0;
    for (let k = 0; k < pts.length; k++) {
      const w = bern(u[k]);
      const a1 = [d1[0] * w[1], d1[1] * w[1]], a2 = [d2[0] * w[2], d2[1] * w[2]];
      const base = [(w[0] + w[1]) * P0[0] + (w[2] + w[3]) * P3[0], (w[0] + w[1]) * P0[1] + (w[2] + w[3]) * P3[1]];
      const r = [pts[k][0] - base[0], pts[k][1] - base[1]];
      c11 += a1[0] * a1[0] + a1[1] * a1[1];
      c12 += a1[0] * a2[0] + a1[1] * a2[1];
      c22 += a2[0] * a2[0] + a2[1] * a2[1];
      x1 += r[0] * a1[0] + r[1] * a1[1];
      x2 += r[0] * a2[0] + r[1] * a2[1];
    }
    const det = c11 * c22 - c12 * c12;
    let a = det ? (x1 * c22 - x2 * c12) / det : 0;
    let b = det ? (c11 * x2 - c12 * x1) / det : 0;
    if (!(a > 1e-6 * chord) || !(b > 1e-6 * chord)) { a = chord / 3; b = chord / 3; }
    alpha = a; beta = b;
    const c = [P0, [P0[0] + d1[0] * a, P0[1] + d1[1] * a], [P3[0] + d2[0] * b, P3[1] + d2[1] * b], P3];
    for (let k = 1; k < u.length - 1; k++) {   // Newton step on (B(u) − Q)·B'(u) = 0
      const q = bez(c, u[k]), d1v = bezD1(c, u[k]), d2v = bezD2(c, u[k]);
      const e = [q[0] - pts[k][0], q[1] - pts[k][1]];
      const num = e[0] * d1v[0] + e[1] * d1v[1];
      const den = d1v[0] * d1v[0] + d1v[1] * d1v[1] + e[0] * d2v[0] + e[1] * d2v[1];
      if (Math.abs(den) > 1e-12) u[k] = Math.min(1, Math.max(0, u[k] - num / den));
    }
  }
  return [alpha, beta];
}

/**
 * Remove anchor i. An open end is just dropped (the neighbour's arm toward it
 * goes too); otherwise the two segments through it are refit as one: 64
 * samples of the old pair, least-squares on the new segment's two arm
 * lengths with the outer arms' directions kept. Neighbours are re-mirrored
 * per their joins. A closed subpath wraps its neighbours around. A result
 * with < 2 anchors is returned as-is — the caller drops it.
 * @param {Subpath} subpath @param {number} i
 * @returns {Subpath}
 */
export function deleteAnchor(subpath, i) {
  const sp = cloneSubpath(subpath);
  const n = sp.anchors.length;
  if (i < 0 || i >= n) return sp;
  if (n <= 2) {
    sp.anchors.splice(i, 1);
    sp.closed = sp.closed && sp.anchors.length >= 2;
    return sp;
  }
  if (!sp.closed && (i === 0 || i === n - 1)) {
    sp.anchors.splice(i, 1);
    if (i === 0) sp.anchors[0].in_handle = null;
    else sp.anchors[sp.anchors.length - 1].out_handle = null;
    return sp;
  }
  const pi = (i - 1 + n) % n, ni = (i + 1) % n;
  const prev = sp.anchors[pi], cur = sp.anchors[i], next = sp.anchors[ni];
  let newOut = null, newIn = null;
  if (prev.out_handle || cur.in_handle || cur.out_handle || next.in_handle) {
    const ca = segCtrl(sp, pi), cb = segCtrl(sp, i);
    const pts = [];
    for (let k = 0; k < 32; k++) pts.push(bez(ca, k / 32));
    for (let k = 1; k <= 32; k++) pts.push(bez(cb, k / 32));
    const P0 = [prev.x, prev.y], P3 = [next.x, next.y];
    const d1 = isZero(prev.out_handle) ? startDir(ca) : [prev.out_handle[0] / hyp(prev.out_handle), prev.out_handle[1] / hyp(prev.out_handle)];
    const rb = [cb[3], cb[2], cb[1], cb[0]];
    const d2 = isZero(next.in_handle) ? startDir(rb) : [next.in_handle[0] / hyp(next.in_handle), next.in_handle[1] / hyp(next.in_handle)];
    if (d1 && d2 && dist(P0, P3) > 1e-9) {
      const [alpha, beta] = fitArmLengths(pts, P0, P3, d1, d2);
      newOut = [d1[0] * alpha, d1[1] * alpha];
      newIn = [d2[0] * beta, d2[1] * beta];
    }
  }
  sp.anchors[pi] = newOut ? applyArmDrag(prev, "out", newOut, false) : { ...prev, out_handle: null };
  sp.anchors[ni] = newIn ? applyArmDrag(next, "in", newIn, false) : { ...next, in_handle: null };
  sp.anchors.splice(i, 1);
  return sp;
}

// ---------------------------------------------------------------- snap

/**
 * Same length, angle rounded to the nearest multiple of stepDeg.
 * @param {number} dx @param {number} dy @param {number} [stepDeg]
 * @returns {Vec}
 */
export function snapAngle(dx, dy, stepDeg = 15) {
  const len = Math.hypot(dx, dy);
  if (len === 0) return [0, 0];
  const step = (stepDeg * Math.PI) / 180;
  const ang = Math.round(Math.atan2(dy, dx) / step) * step;
  return [len * Math.cos(ang), len * Math.sin(ang)];
}

// ---------------------------------------------------------------- knife

/** Crossings of segment k's cubic with the line segment a–b, as cubic t values. */
function segCrossings(c, a, b) {
  const ab = [b[0] - a[0], b[1] - a[1]], L2 = ab[0] * ab[0] + ab[1] * ab[1];
  const side = (t) => { const p = bez(c, t); return ab[0] * (p[1] - a[1]) - ab[1] * (p[0] - a[0]); };
  const N = 128, out = [];
  let t0 = 0, s0 = side(0);
  for (let i = 1; i <= N; i++) {
    const t1 = i / N, s1 = side(t1);
    // half-open: a zero at the START of an interval belongs to the previous one
    if ((s0 < 0 && s1 >= 0) || (s0 > 0 && s1 <= 0)) {
      let lo = t0, hi = t1, slo = s0;
      if (s1 === 0) lo = hi = t1;
      for (let it = 0; it < 80 && hi - lo > 1e-15; it++) {
        const m = (lo + hi) / 2, sm = side(m);
        if ((slo < 0) === (sm < 0) && sm !== 0) { lo = m; slo = sm; } else hi = m;
      }
      const t = (lo + hi) / 2, p = bez(c, t);
      const s = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / L2;
      if (s >= -1e-9 && s <= 1 + 1e-9) out.push(t);
    }
    t0 = t1; s0 = s1;
  }
  return out;
}

/**
 * Cut the subpath along segment a–b. Every crossing becomes a shared end
 * point (split via de Casteljau, so the drawn shape is unchanged); all
 * results are open. A closed subpath with one crossing becomes one open
 * subpath starting and ending there. Pieces with < 2 anchors are dropped.
 * No crossing → [copy of the subpath].
 * @param {Subpath} subpath @param {Vec} a @param {Vec} b
 * @returns {Subpath[]}
 */
export function knife(subpath, a, b) {
  const n0 = subpath.anchors.length;
  if (dist(a, b) < 1e-12 || segCount(subpath) === 0) return [cloneSubpath(subpath)];
  const marks = [];   // anchor indices that are cut points
  const splits = [];  // {k, t} interior crossings
  for (let k = 0; k < segCount(subpath); k++) {
    for (const t of segCrossings(segCtrl(subpath, k), a, b)) {
      if (t > 1 - T_EPS) marks.push((k + 1) % n0);
      else if (t < T_EPS) marks.push(k);
      else splits.push({ k, t });
    }
  }
  if (!marks.length && !splits.length) return [cloneSubpath(subpath)];
  // split last-first so earlier indices stay valid; same-segment splits
  // rescale t onto the left piece that remains at index k
  splits.sort((p, q) => q.k - p.k || q.t - p.t);
  let cur = cloneSubpath(subpath);
  let cuts = marks.slice();
  let lastK = -1, lastT = 1;
  for (const s of splits) {
    const t = s.k === lastK ? s.t / lastT : s.t;
    cur = splitSegment(cur, s.k, t);
    const ins = s.k + 1;
    cuts = cuts.map((m) => (m >= ins ? m + 1 : m));
    cuts.push(ins);
    lastK = s.k; lastT = s.t;
  }
  cuts = [...new Set(cuts)].sort((p, q) => p - q);
  const A = cur.anchors, n = A.length;
  let seq, bounds;
  if (cur.closed) {
    const c0 = cuts[0];
    seq = [];
    for (let k = 0; k <= n; k++) seq.push((c0 + k) % n);
    bounds = [...new Set([0, ...cuts.map((c) => (c - c0 + n) % n), n])].sort((p, q) => p - q);
  } else {
    seq = A.map((_, k) => k);
    bounds = [...new Set([0, ...cuts, n - 1])].sort((p, q) => p - q);
  }
  const isCut = (pos) => cur.closed || cuts.includes(seq[pos]);
  const pieces = [];
  for (let k = 0; k + 1 < bounds.length; k++) {
    const s = bounds[k], e = bounds[k + 1];
    if (e - s < 1) continue;
    const anchors = seq.slice(s, e + 1).map((idx) => cloneAnchor(A[idx]));
    if (isCut(s)) { anchors[0].in_handle = null; anchors[0].join = "corner"; }
    if (isCut(e)) { const l = anchors[anchors.length - 1]; l.out_handle = null; l.join = "corner"; }
    pieces.push(cloneSubpath({ ...cur, closed: false }, anchors));
  }
  return pieces;
}

// ---------------------------------------------------------------- join

/**
 * Merge two open subpaths: subpath's `otherEnd` meets subpath2's `end2`.
 * The meeting anchors become one "corner" anchor at their midpoint, keeping
 * the arm each side had away from the meeting point. Joining a subpath's
 * own start to its own end (same object) closes it instead.
 * @param {Subpath} subpath @param {"start"|"end"} otherEnd
 * @param {Subpath} subpath2 @param {"start"|"end"} end2
 * @returns {Subpath}
 */
export function joinEnds(subpath, otherEnd, subpath2, end2) {
  if (subpath === subpath2) {
    const sp = cloneSubpath(subpath);
    const A = sp.anchors;
    if (A.length < 3 || otherEnd === end2) return sp;
    const f = A[0], l = A[A.length - 1];
    const m = { ...f, x: (f.x + l.x) / 2, y: (f.y + l.y) / 2, in_handle: l.in_handle,
                out_handle: f.out_handle, join: "corner" };
    sp.anchors = [m, ...A.slice(1, -1)];
    sp.closed = true;
    return sp;
  }
  const s1 = otherEnd === "start" ? reverseSubpath(subpath) : cloneSubpath(subpath);
  const s2 = end2 === "end" ? reverseSubpath(subpath2) : cloneSubpath(subpath2);
  const L = s1.anchors[s1.anchors.length - 1], F = s2.anchors[0];
  const m = { ...L, x: (L.x + F.x) / 2, y: (L.y + F.y) / 2, in_handle: L.in_handle,
              out_handle: F.out_handle, join: "corner" };
  const anchors = [...s1.anchors.slice(0, -1), m, ...s2.anchors.slice(1)];
  return cloneSubpath({ ...s1, closed: false }, anchors);
}
