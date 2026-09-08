(function (root) {
  "use strict";

  const defaults = Object.freeze({
    seed: 7, width: 24, wavelength: 90, variation: 0.5,
    relation: "related", steps: 10, taper: 0.12
  });

  function rng(seed) {
    let a = (Number(seed) || 0) >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
  const mix = (a, b, t) => a + (b - a) * t;
  const smooth = t => t * t * (3 - 2 * t); // horizontal tangents at knots
  const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);
  const same = (a, b) => a[0] === b[0] && a[1] === b[1];

  function sanitize(points) {
    const out = [];
    if (!Array.isArray(points)) return out;
    for (const p of points) {
      if (!Array.isArray(p) || !Number.isFinite(+p[0]) || !Number.isFinite(+p[1])) continue;
      const q = [+p[0], +p[1]];
      if (!out.length || !same(q, out[out.length - 1])) out.push(q);
    }
    return out;
  }

  function samplePolyline(points, spacing) {
    const out = [points[0].slice()];
    const ss = [0];
    let total = 0;
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1], b = points[i], len = dist(a, b);
      const n = Math.max(1, Math.ceil(len / spacing));
      for (let j = 1; j <= n; j++) {
        const t = j / n;
        out.push([mix(a[0], b[0], t), mix(a[1], b[1], t)]);
        total += len / n;
        ss.push(total);
      }
    }
    return { points: out, ss, total };
  }

  function frames(points) {
    const result = [];
    for (let i = 0; i < points.length; i++) {
      const prev = points[Math.max(0, i - 1)], here = points[i], next = points[Math.min(points.length - 1, i + 1)];
      let ax = here[0] - prev[0], ay = here[1] - prev[1];
      let bx = next[0] - here[0], by = next[1] - here[1];
      if (i === 0) { ax = bx; ay = by; }
      if (i === points.length - 1) { bx = ax; by = ay; }
      const al = Math.hypot(ax, ay) || 1, bl = Math.hypot(bx, by) || 1;
      ax /= al; ay /= al; bx /= bl; by /= bl;
      const n1 = [-ay, ax], n2 = [-by, bx];
      let nx = n1[0] + n2[0], ny = n1[1] + n2[1];
      const nl = Math.hypot(nx, ny);
      if (nl < 1e-6) { nx = n2[0]; ny = n2[1]; }
      else { nx /= nl; ny /= nl; }
      // Miter reaches the requested perpendicular distance; cap sharp joins.
      const denom = Math.max(0.35, nx * n2[0] + ny * n2[1]);
      const miter = Math.min(2.4, 1 / denom);
      result.push({ nx: nx * miter, ny: ny * miter });
    }
    return result;
  }

  function knotProfile(total, opts, random, guide) {
    if (total <= 0) return () => 0;
    const knots = [{ s: 0, v: 0 }];
    let s = 0, index = 0;
    while (s < total) {
      const g = guide && guide[index];
      const spacingJitter = g ? g.spacing : 1 + (random() - 0.5) * 0.5 * opts.variation;
      s = Math.min(total, s + opts.wavelength * 0.5 * spacingJitter);
      const crest = index % 2 === 0;
      const regular = crest ? 0.86 : 0.21;
      let amplitude = g ? g.amplitude : regular + (random() - 0.5) * (crest ? 0.28 : 0.14) * opts.variation;
      // Higher variation occasionally suppresses a crest into a quiet phrase.
      if (!g && crest && random() < 0.22 * opts.variation) amplitude *= 0.45 + random() * 0.2;
      amplitude = clamp(amplitude, crest ? 0.3 : 0.12, crest ? 1 : 0.3);
      knots.push({ s, v: amplitude, spacing: spacingJitter, amplitude });
      index++;
    }
    knots[knots.length - 1].s = total;
    knots[knots.length - 1].v = 0;
    return Object.assign(function (at) {
      let i = 0;
      while (i + 1 < knots.length && at > knots[i + 1].s) i++;
      const a = knots[i], b = knots[Math.min(i + 1, knots.length - 1)];
      const t = b.s === a.s ? 0 : clamp((at - a.s) / (b.s - a.s), 0, 1);
      return mix(a.v, b.v, smooth(t));
    }, { knots });
  }

  function taperAt(s, total, taper) {
    const edge = Math.max(1e-9, total * clamp(taper, 0, 0.49));
    return Math.min(1, smooth(clamp(s / edge, 0, 1)), smooth(clamp((total - s) / edge, 0, 1)));
  }

  function generate(input, options) {
    const opts = Object.assign({}, defaults, options || {});
    opts.width = Math.max(0, +opts.width || 0);
    opts.wavelength = Math.max(1e-6, +opts.wavelength || defaults.wavelength);
    opts.variation = clamp(+opts.variation || 0, 0, 1);
    opts.steps = Math.max(1, Math.floor(+opts.steps || defaults.steps));
    opts.taper = clamp(+opts.taper || 0, 0, 0.49);
    const source = sanitize(input);
    const diagnostics = { skipped: false, reason: null, sourcePoints: source.length };
    if (source.length < 2) {
      diagnostics.skipped = true; diagnostics.reason = "degenerate";
      const pass = source.map(p => p.slice());
      return { strands: pass.length ? [pass] : [], left: pass, right: pass, spine: pass, diagnostics };
    }
    if (same(source[0], source[source.length - 1])) {
      diagnostics.skipped = true; diagnostics.reason = "closed-path-bypass";
      const pass = source.map(p => p.slice());
      return { strands: [pass], left: pass, right: pass, spine: pass, diagnostics };
    }

    const sampled = samplePolyline(source, Math.min(2, opts.wavelength / 12));
    const spine = sampled.points.map(p => p.slice());
    const frame = frames(spine);
    const leftRandom = rng(opts.seed);
    const leftProfile = knotProfile(sampled.total, opts, leftRandom);
    let rightProfile;
    if (opts.relation === "mirrored") rightProfile = leftProfile;
    else if (opts.relation === "independent") rightProfile = knotProfile(sampled.total, opts, rng((opts.seed >>> 0) ^ 0x9E3779B9));
    else {
      const relatedRandom = rng((opts.seed >>> 0) ^ 0x85EBCA6B);
      const guide = leftProfile.knots.slice(1).map(k => ({
        spacing: clamp(k.spacing + (relatedRandom() - 0.5) * 0.16 * opts.variation, 0.65, 1.35),
        amplitude: clamp(k.amplitude * (1 + (relatedRandom() - 0.5) * 0.28 * opts.variation), 0.12, 1)
      }));
      rightProfile = knotProfile(sampled.total, opts, relatedRandom, guide);
    }

    function outerWidths(profile) {
      return spine.map((p, i) => {
        if (i === 0 || i === spine.length - 1) return 0;
        const base = profile(sampled.ss[i]);
        const requested = opts.width * base * taperAt(sampled.ss[i], sampled.total, opts.taper);
        return requested;
      });
    }

    const leftWidths = outerWidths(leftProfile);
    const rightWidths = outerWidths(rightProfile);
    function side(sign, widths, level) {
      return spine.map((p, i) => {
        if (i === 0) return source[0].slice();
        if (i === spine.length - 1) return source[source.length - 1].slice();
        const width = widths[i] * level;
        return [p[0] + sign * frame[i].nx * width, p[1] + sign * frame[i].ny * width];
      });
    }

    const leftLevels = [], rightLevels = [];
    for (let i = opts.steps; i >= 1; i--) leftLevels.push(side(1, leftWidths, i / opts.steps));
    for (let i = 1; i <= opts.steps; i++) rightLevels.push(side(-1, rightWidths, i / opts.steps));
    const left = leftLevels[0], right = rightLevels[rightLevels.length - 1];
    return { strands: leftLevels.concat([spine], rightLevels), left, right, spine, diagnostics };
  }

  function cubic(a, b, c, d, count) {
    const out = [];
    for (let i = 0; i <= count; i++) {
      const t = i / count, u = 1 - t;
      out.push([
        u * u * u * a[0] + 3 * u * u * t * b[0] + 3 * u * t * t * c[0] + t * t * t * d[0],
        u * u * u * a[1] + 3 * u * u * t * b[1] + 3 * u * t * t * c[1] + t * t * t * d[1]
      ]);
    }
    return out;
  }

  function join() {
    const out = [];
    for (const segment of arguments) out.push(...segment.slice(out.length ? 1 : 0));
    return out;
  }

  const fixtures = Object.freeze({
    straight: [[40, 115], [660, 115]],
    arch: cubic([35, 175], [175, 20], [520, 20], [665, 175], 140),
    sCurve: join(
      cubic([35, 165], [125, 45], [245, 45], [350, 115], 75),
      cubic([350, 115], [455, 190], [575, 190], [665, 70], 75)
    ),
    corner: join(
      cubic([35, 180], [135, 80], [330, 55], [430, 142], 120),
      [[430, 142], [655, 42]]
    ),
    hairpin: join(
      cubic([35, 185], [120, 50], [310, 25], [490, 55], 80),
      cubic([490, 55], [610, 75], [600, 190], [490, 195], 60),
      cubic([490, 195], [390, 200], [300, 155], [245, 125], 50)
    )
  });

  const profile = Object.freeze({
    description: "Alternating crest/trough knots joined by cubic smoothstep segments",
    widthMeaning: "Approximate maximum outer-side distance from the spine",
    variationMeaning: "Amount of spacing, height, quiet-phrase, and related-side irregularity; zero is regular",
    limitations: ["sharp corners use a capped miter and may fold at extreme widths", "no global intersection guarantee", "closed paths bypassed"]
  });

  const api = Object.freeze({ generate, fixtures, profile });
  root.RibbonStudy = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
