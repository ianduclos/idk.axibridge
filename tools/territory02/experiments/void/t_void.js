// Local empty-space experiment. A bend owns a pocket, but its opposite lip is
// incomplete and unequal. Selection measures geometry/occupancy, never beauty.
function bendPocket(geo, chans, seed, out, prm) {
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
  // Start with actual plotted coordinates, following twelve millimetres of
  // the inherited strand backwards. The departure inherits its tangent before
  // a blunt shelf changes the character; the far end cuts a second boundary.
  const mix = (a,b,t) => [a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t];
  let host = null, hi = 0, bd = 1e9;
  for (const l of out) if(l.ch===p.id && l.kind==='strand') for(const P of l.strokes) for(let i=0;i<P.length;i++){
    const d=Math.hypot(P[i][0]-p.a[0],P[i][1]-p.a[1]);if(d<bd){bd=d;host=P;hi=i;}
  }
  if(!host || bd>7) return null;
  const toward=p.arc[Math.min(6,p.arc.length-1)], prev=host[Math.max(0,hi-1)], next=host[Math.min(host.length-1,hi+1)];
  const dir=((next[0]-prev[0])*(toward[0]-p.a[0])+(next[1]-prev[1])*(toward[1]-p.a[1]))>0?1:-1;
  let end=hi, walked=0;
  while(end+dir>=0&&end+dir<host.length&&walked<12){walked+=Math.hypot(host[end+dir][0]-host[end][0],host[end+dir][1]-host[end][1]);end+=dir;}
  const prefix=[];for(let i=end;;i-=dir){prefix.push(host[i].slice());if(i===hi)break;}
  if(prefix.length<3) return null;
  const a=prefix[prefix.length-1], before=prefix[Math.max(0,prefix.length-9)], tl=Math.hypot(a[0]-before[0],a[1]-before[1])||1;
  const depart=[a[0]+(a[0]-before[0])/tl*10,a[1]+(a[1]-before[1])/tl*10];
  const shelf=p.c, aim=mix(p.a,p.b,0.82); let target=p.b, targetId=p.id, near=30;
  for(const [id,g] of geo) if(id!==p.id) for(let i=0;i<g.C.length;i+=2){const q=g.C[i],d=Math.hypot(q[0]-aim[0],q[1]-aim[1]);if(d<near){near=d;target=q;targetId=id;}}
  // Retain the incompatibility: the shelf does not ease politely into the
  // second curve. Its last few millimetres pass through, changing the exit gap.
  const v=[target[0]-shelf[0],target[1]-shelf[1]], vl=Math.hypot(...v)||1;
  const tail=[target[0]+v[0]/vl*9-p.nx*4,target[1]+v[1]/vl*9-p.ny*4];
  const first=catmullRom([before,a,depart,mix(depart,shelf,0.65),shelf],0.5);
  // Remove the before-a interpolation: prefix already contains this course.
  let ai=0, ad=1e9;first.forEach((q,i)=>{const d=Math.hypot(q[0]-a[0],q[1]-a[1]);if(d<ad){ad=d;ai=i;}});
  const blunt=resample([shelf,target],0.5), turn=catmullRom([shelf,target,tail],0.5);
  let ti=0,td=1e9;turn.forEach((q,i)=>{const d=Math.hypot(q[0]-target[0],q[1]-target[1]);if(d<td){td=d;ti=i;}});
  p.lip=prefix.concat(first.slice(ai+1),blunt.slice(1),turn.slice(ti+1)).map(q=>[clamp(q[0],3,W-3),clamp(q[1],3,H-3)]);
  p.targetId=targetId;
  p.mask = new Uint8Array(N);
  for (let y=3;y<H-3;y++) for(let x=3;x<W-3;x++) if(p.inside([x+0.5,y+0.5])) p.mask[y*GW+x]=1;
  return p;
}
