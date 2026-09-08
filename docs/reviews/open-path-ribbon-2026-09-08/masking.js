(function (root) {
  "use strict";

  const EPS = 1e-9;
  const cross = (ax, ay, bx, by) => ax * by - ay * bx;
  const clamp01 = t => Math.max(0, Math.min(1, t));

  function validPoint(p) {
    return Array.isArray(p) && Number.isFinite(+p[0]) && Number.isFinite(+p[1]);
  }

  function preparePolygon(input) {
    if (!Array.isArray(input)) return null;
    const points = input.filter(validPoint).map(p => [+p[0], +p[1]]);
    if (points.length < 3) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of points) {
      minX = Math.min(minX, p[0]); minY = Math.min(minY, p[1]);
      maxX = Math.max(maxX, p[0]); maxY = Math.max(maxY, p[1]);
    }
    return { points, minX, minY, maxX, maxY };
  }

  function boxesOverlap(a, b) {
    return !(a.maxX < b.minX - EPS || a.minX > b.maxX + EPS ||
             a.maxY < b.minY - EPS || a.minY > b.maxY + EPS);
  }

  function pointOnSegment(p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const scale = Math.max(1, Math.abs(dx), Math.abs(dy));
    if (Math.abs(cross(p[0] - a[0], p[1] - a[1], dx, dy)) > EPS * scale) return false;
    return p[0] >= Math.min(a[0], b[0]) - EPS && p[0] <= Math.max(a[0], b[0]) + EPS &&
           p[1] >= Math.min(a[1], b[1]) - EPS && p[1] <= Math.max(a[1], b[1]) + EPS;
  }

  // Boundary counts as inside. Otherwise use the even-odd rule, so concave
  // polygons need no triangulation and winding direction is irrelevant.
  function contains(p, polygon) {
    if (p[0] < polygon.minX - EPS || p[0] > polygon.maxX + EPS ||
        p[1] < polygon.minY - EPS || p[1] > polygon.maxY + EPS) return false;
    let inside = false;
    const points = polygon.points;
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
      const a = points[j], b = points[i];
      if (pointOnSegment(p, a, b)) return true;
      if ((a[1] > p[1]) !== (b[1] > p[1])) {
        const x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]);
        if (x > p[0]) inside = !inside;
      }
    }
    return inside;
  }

  function edgeParameters(a, dx, dy, c, d) {
    const ex = d[0] - c[0], ey = d[1] - c[1];
    const qx = c[0] - a[0], qy = c[1] - a[1];
    const denom = cross(dx, dy, ex, ey);
    const scale = Math.max(1, Math.abs(dx), Math.abs(dy), Math.abs(ex), Math.abs(ey));
    if (Math.abs(denom) > EPS * scale) {
      const t = cross(qx, qy, ex, ey) / denom;
      const u = cross(qx, qy, dx, dy) / denom;
      return t >= -EPS && t <= 1 + EPS && u >= -EPS && u <= 1 + EPS ? [clamp01(t)] : [];
    }
    if (Math.abs(cross(qx, qy, dx, dy)) > EPS * scale) return [];
    const length2 = dx * dx + dy * dy;
    const t0 = ((c[0] - a[0]) * dx + (c[1] - a[1]) * dy) / length2;
    const t1 = ((d[0] - a[0]) * dx + (d[1] - a[1]) * dy) / length2;
    const lo = Math.max(0, Math.min(t0, t1)), hi = Math.min(1, Math.max(t0, t1));
    return hi < lo - EPS ? [] : [clamp01(lo), clamp01(hi)];
  }

  function visibleIntervals(a, b, polygonInputs) {
    if (!validPoint(a) || !validPoint(b)) return [];
    a = [+a[0], +a[1]]; b = [+b[0], +b[1]];
    const polygons = (Array.isArray(polygonInputs) ? polygonInputs : []).map(preparePolygon).filter(Boolean);
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const length2 = dx * dx + dy * dy;
    // A point segment is visible for its full parameter domain unless the
    // point lies inside or on a blocker. This keeps the return type uniform.
    if (length2 <= EPS * EPS) return polygons.some(p => contains(a, p)) ? [] : [[0, 1]];

    const segmentBox = {
      minX: Math.min(a[0], b[0]), minY: Math.min(a[1], b[1]),
      maxX: Math.max(a[0], b[0]), maxY: Math.max(a[1], b[1])
    };
    const relevant = polygons.filter(p => boxesOverlap(segmentBox, p));
    if (!relevant.length) return [[0, 1]];

    const cuts = [0, 1];
    for (const polygon of relevant) {
      const points = polygon.points;
      for (let i = 0; i < points.length; i++) {
        cuts.push(...edgeParameters(a, dx, dy, points[i], points[(i + 1) % points.length]));
      }
    }
    cuts.sort((x, y) => x - y);
    const unique = cuts.filter((t, i) => i === 0 || t - cuts[i - 1] > EPS);
    const visible = [];
    for (let i = 0; i + 1 < unique.length; i++) {
      const lo = unique[i], hi = unique[i + 1];
      if (hi - lo <= EPS) continue;
      const mid = (lo + hi) / 2;
      const point = [a[0] + dx * mid, a[1] + dy * mid];
      if (!relevant.some(p => contains(point, p))) {
        const previous = visible[visible.length - 1];
        if (previous && Math.abs(previous[1] - lo) <= EPS) previous[1] = hi;
        else visible.push([lo, hi]);
      }
    }
    return visible;
  }

  const api = Object.freeze({ visibleIntervals });
  root.RibbonMask = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
