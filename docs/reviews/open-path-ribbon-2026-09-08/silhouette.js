(function(root) {
  "use strict";

  const EPS = 1e-9;
  const copyPoint = p => [Number(p[0]), Number(p[1])];
  const same = (a, b) => Math.abs(a[0] - b[0]) <= EPS && Math.abs(a[1] - b[1]) <= EPS;
  const finitePoint = p => Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]);
  const area2 = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);

  function closeRing(points) {
    const ring = points.filter(finitePoint).map(copyPoint);
    if (ring.length && !same(ring[0], ring[ring.length - 1])) ring.push(copyPoint(ring[0]));
    return ring;
  }

  function cleanMultiPolygon(value) {
    if (!Array.isArray(value)) return [];
    return value.map(polygon => Array.isArray(polygon)
      ? polygon.map(closeRing).filter(ring => ring.length >= 4)
      : []).filter(polygon => polygon.length);
  }

  function nodePoint(node) {
    return Array.isArray(node) ? node : node && node.p;
  }

  function validNodes(nodes) {
    return Array.isArray(nodes) && nodes.every(node => finitePoint(nodePoint(node)) && Number.isFinite(node.s));
  }

  // At a repeated station, choose the occurrence nearest the caller's index hint.
  // This makes the two sides of a corner fan attach to the corresponding spine
  // occurrence rather than collapsing every duplicate s onto one point.
  function spineAt(spine, s, hint) {
    let exact = [];
    for (let i = 0; i < spine.length; i++) if (Math.abs(spine[i].s - s) <= EPS) exact.push(i);
    if (exact.length) {
      let index = exact[0];
      if (Number.isFinite(hint)) index = exact.reduce((best, i) => Math.abs(i - hint) < Math.abs(best - hint) ? i : best, index);
      return copyPoint(nodePoint(spine[index]));
    }
    for (let i = 0; i + 1 < spine.length; i++) {
      const a = spine[i], b = spine[i + 1];
      if (s >= a.s - EPS && s <= b.s + EPS && b.s > a.s + EPS) {
        const t = Math.max(0, Math.min(1, (s - a.s) / (b.s - a.s)));
        const p = nodePoint(a), q = nodePoint(b);
        return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
      }
    }
    return copyPoint(nodePoint(s <= spine[0].s ? spine[0] : spine[spine.length - 1]));
  }

  function sweepTriangles(nodes, spine) {
    const triangles = [];
    const denom = Math.max(1, nodes.length - 1);
    for (let i = 0; i + 1 < nodes.length; i++) {
      const a = copyPoint(nodePoint(nodes[i])), b = copyPoint(nodePoint(nodes[i + 1]));
      const hintA = i / denom * Math.max(0, spine.length - 1);
      const hintB = (i + 1) / denom * Math.max(0, spine.length - 1);
      const sa = spineAt(spine, nodes[i].s, hintA), sb = spineAt(spine, nodes[i + 1].s, hintB);
      for (const triangle of [[sa, sb, b], [sa, b, a]]) {
        if (Math.abs(area2(triangle[0], triangle[1], triangle[2])) > EPS) triangles.push([closeRing(triangle)]);
      }
    }
    return triangles;
  }

  function fromNodes(leftNodes, rightNodes, spineNodes, options) {
    const mergeOverlaps = !!(options && options.mergeOverlaps);
    if (!validNodes(leftNodes) || !validNodes(rightNodes) || !validNodes(spineNodes) ||
        !leftNodes.length || !rightNodes.length || !spineNodes.length) return [];
    if (!mergeOverlaps) {
      const raw = leftNodes.map(nodePoint).concat(rightNodes.slice().reverse().map(nodePoint));
      const ring = closeRing(raw);
      return ring.length >= 4 ? [[ring]] : [];
    }
    if (!root.polygonClipping) throw new Error("Ribbon silhouette polygon helper missing");
    const pieces = sweepTriangles(leftNodes, spineNodes).concat(sweepTriangles(rightNodes, spineNodes));
    if (!pieces.length) return [];
    return cleanMultiPolygon(root.polygonClipping.union(...pieces));
  }

  function union(polygons) {
    const inputs = (Array.isArray(polygons) ? polygons : []).map(cleanMultiPolygon).filter(p => p.length);
    if (!inputs.length) return [];
    if (!root.polygonClipping) throw new Error("Ribbon silhouette polygon helper missing");
    return cleanMultiPolygon(root.polygonClipping.union(...inputs));
  }

  function pointInRing(point, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = ring[j], b = ring[i];
      if (((a[1] > point[1]) !== (b[1] > point[1])) &&
          point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
    }
    return inside;
  }

  function pointOnSegment(point, a, b) {
    if (Math.abs(area2(a, b, point)) > EPS) return false;
    return point[0] >= Math.min(a[0], b[0]) - EPS && point[0] <= Math.max(a[0], b[0]) + EPS &&
      point[1] >= Math.min(a[1], b[1]) - EPS && point[1] <= Math.max(a[1], b[1]) + EPS;
  }

  function inFill(point, multiPolygon) {
    for (const polygon of multiPolygon) {
      for (const ring of polygon) {
        for (let i = 0; i + 1 < ring.length; i++) if (pointOnSegment(point, ring[i], ring[i + 1])) return true;
      }
    }
    return multiPolygon.some(polygon => polygon.reduce((inside, ring) => inside !== pointInRing(point, ring), false));
  }

  function intersectionTs(a, b, c, d) {
    const rx = b[0] - a[0], ry = b[1] - a[1], sx = d[0] - c[0], sy = d[1] - c[1];
    const den = rx * sy - ry * sx;
    const qx = c[0] - a[0], qy = c[1] - a[1];
    if (Math.abs(den) <= EPS) {
      if (Math.abs(qx * ry - qy * rx) > EPS) return [];
      const length2 = rx * rx + ry * ry;
      if (length2 <= EPS) return [];
      const t0 = (qx * rx + qy * ry) / length2;
      const t1 = ((d[0] - a[0]) * rx + (d[1] - a[1]) * ry) / length2;
      return [Math.max(0, Math.min(t0, t1)), Math.min(1, Math.max(t0, t1))]
        .filter(t => t > EPS && t < 1 - EPS);
    }
    const t = (qx * sy - qy * sx) / den, u = (qx * ry - qy * rx) / den;
    return t > EPS && t < 1 - EPS && u >= -EPS && u <= 1 + EPS ? [t] : [];
  }

  function clipPaths(paths, multiPolygon) {
    const shape = cleanMultiPolygon(multiPolygon);
    const boundaries = shape.flatMap(polygon => polygon.flatMap(ring => ring.slice(1).map((p, i) => [ring[i], p])));
    const output = [];
    for (const path of Array.isArray(paths) ? paths : []) {
      if (!Array.isArray(path) || path.length < 2 || !path.every(finitePoint)) continue;
      let current = null;
      for (let i = 0; i + 1 < path.length; i++) {
        const a = copyPoint(path[i]), b = copyPoint(path[i + 1]);
        const ts = [0, 1];
        for (const edge of boundaries) {
          ts.push(...intersectionTs(a, b, edge[0], edge[1]));
        }
        ts.sort((x, y) => x - y);
        const unique = ts.filter((t, j) => !j || Math.abs(t - ts[j - 1]) > EPS);
        for (let j = 0; j + 1 < unique.length; j++) {
          const t0 = unique[j], t1 = unique[j + 1], tm = (t0 + t1) / 2;
          const p = [a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0];
          const q = [a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1];
          const mid = [a[0] + (b[0] - a[0]) * tm, a[1] + (b[1] - a[1]) * tm];
          if (!inFill(mid, shape) && !same(p, q)) {
            if (current && same(current[current.length - 1], p)) current.push(q);
            else { current = [p, q]; output.push(current); }
          } else current = null;
        }
      }
    }
    return output;
  }

  root.RibbonSilhouette = {fromNodes, union, clipPaths};
})(globalThis);
