
// ======================= Contour graph =======================
// The v2 composition lines (borders + outer edges) become a graph: polylines
// split at junctions (an end that lands on another line, or two ends that meet),
// so a stroke can later travel from one lobe's contour onto its neighbour's.

function contourGraph(polys, snap = 3.5) {
  const P = polys.map(p => resample(p, 1)).filter(p => p.length >= 3);
  // Spatial hash of every sample.
  const cell = snap, hash = new Map(), key = (x, y) => Math.floor(x / cell) * 4096 + Math.floor(y / cell);
  P.forEach((pl, a) => pl.forEach((p, i) => { const k = key(p[0], p[1]); let b = hash.get(k); if (!b) hash.set(k, b = []); b.push([a, i]); }));
  const near = (x, y, r, skip) => {
    let best = null, bd = r * r;
    const gx = Math.floor(x / cell), gy = Math.floor(y / cell);
    for (let u = -1; u <= 1; u++) for (let v = -1; v <= 1; v++) for (const [a, i] of (hash.get((gx + u) * 4096 + gy + v) || [])) {
      if (a === skip) continue;
      const q = P[a][i], d = (q[0] - x) ** 2 + (q[1] - y) ** 2; if (d < bd) { bd = d; best = [a, i]; }
    }
    return best;
  };
  // Cut points: each polyline end that lands near another polyline cuts it there.
  const cuts = P.map(() => new Set());
  P.forEach((pl, a) => {
    cuts[a].add(0); cuts[a].add(pl.length - 1);
    for (const e of [0, pl.length - 1]) { const hit = near(pl[e][0], pl[e][1], snap, a); if (hit) cuts[hit[0]].add(hit[1]); }
  });
  // Nodes: cluster cut points.
  const nodes = [], nodeAt = (x, y) => {
    for (const n of nodes) if (Math.hypot(n.x - x, n.y - y) < snap) { n.x = (n.x * n.k + x) / (n.k + 1); n.y = (n.y * n.k + y) / (n.k + 1); n.k++; return n.id; }
    nodes.push({ id: nodes.length, x, y, k: 1, edges: [] }); return nodes.length - 1;
  };
  const edges = [];
  P.forEach((pl, a) => {
    const cs = [...cuts[a]].sort((u, v) => u - v);
    for (let t = 0; t < cs.length - 1; t++) {
      const i0 = cs[t], i1 = cs[t + 1]; if (i1 - i0 < 2) continue;
      const pts = pl.slice(i0, i1 + 1), n0 = nodeAt(pts[0][0], pts[0][1]), n1 = nodeAt(pts[pts.length - 1][0], pts[pts.length - 1][1]);
      const e = { id: edges.length, pts, a: n0, b: n1, len: polyLen(pts), src: a };
      edges.push(e); nodes[n0].edges.push(e.id); if (n1 !== n0) nodes[n1].edges.push(e.id);
    }
  });
  nodes.forEach(n => { n.degree = n.edges.length; });
  return { nodes, edges };
}

// Edge points oriented away from node n.
function edgeFrom(g, eid, n) { const e = g.edges[eid]; return e.a === n ? e.pts : e.pts.slice().reverse(); }
function otherEnd(g, eid, n) { const e = g.edges[eid]; return e.a === n ? e.b : e.a; }
