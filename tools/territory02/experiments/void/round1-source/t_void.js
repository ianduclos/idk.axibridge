// Local empty-space experiment. A bend owns a pocket, but its opposite lip is
// incomplete and unequal. Selection measures geometry/occupancy, never beauty.
function bendPocket(geo, chans, seed) {
  const rng = rngFor(seed, 7301), candidates = [];
  for (const [id, g] of geo) {
    const P = resample(g.C, 2);
    for (let i = 0; i < P.length - 35; i += 8) for (const span of [40, 55, 70]) {
      const j = Math.min(P.length - 1, i + span), a = P[i], b = P[j];
      const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy);
      if (len < 35 || len > 150 || j - i < 35) continue;
      const arc = P.slice(i, j + 1), mid = centroid(arc), nx = -dy / len, ny = dx / len;
      const sag = (mid[0] - (a[0] + b[0]) / 2) * nx + (mid[1] - (a[1] + b[1]) / 2) * ny;
      if (Math.abs(sag) < 10 || Math.abs(sag) > 55) continue;
      const c = [(a[0] + b[0]) / 2 + nx * sag * 0.3, (a[1] + b[1]) / 2 + ny * sag * 0.3];
      const poly = arc.concat([c]), inside = p => {
        let hit = false; for (let u = 0, v = poly.length - 1; u < poly.length; v = u++) {
          const A = poly[u], B = poly[v]; if ((A[1] > p[1]) !== (B[1] > p[1]) && p[0] < (B[0] - A[0]) * (p[1] - A[1]) / (B[1] - A[1]) + A[0]) hit = !hit;
        } return hit;
      };
      let conflict = 0; for (const [other, q] of geo) if (other !== id) for (let k = 0; k < q.C.length; k += 10) if (inside(q.C[k])) conflict++;
      const area = len * Math.abs(sag);
      candidates.push({ id, arc, a, b, c, sag, nx, ny, poly, inside, merit: area / (1 + conflict * 0.6) * (0.8 + 0.4 * rng()) });
    }
  }
  candidates.sort((a, b) => b.merit - a.merit);
  const p = candidates[0]; if (!p) return null;
  // The return is a short shelf then a tightening turn. Its ends stay open;
  // both do not politely agree with the inherited arc.
  const mix = (a,b,t) => [a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t];
  const a = mix(p.a,p.b,0.12), b = mix(p.a,p.b,0.82), c = p.c;
  const shoulder = mix(a,c,0.72), lip = [a, shoulder, c, mix(c,b,0.55), b];
  p.lip = catmullRom(resample(lip,2),0.5);
  p.mask = new Uint8Array(N);
  for (let y=3;y<H-3;y++) for(let x=3;x<W-3;x++) if(p.inside([x+0.5,y+0.5])) p.mask[y*GW+x]=1;
  return p;
}
