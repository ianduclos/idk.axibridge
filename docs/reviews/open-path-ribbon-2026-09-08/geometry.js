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

  const cross = (a,b) => a[0]*b[1]-a[1]*b[0];
  const sub = (a,b) => [a[0]-b[0],a[1]-b[1]];
  function sharpCorners(points, ss) {
    const result=[];
    for(let i=1;i<points.length-1;i++) {
      const a=sub(points[i],points[i-1]),b=sub(points[i+1],points[i]);
      const turn=Math.atan2(cross(a,b),a[0]*b[0]+a[1]*b[1]);
      if(Math.abs(turn)>.4)result.push({s:ss[i],turn});
    }
    return result;
  }

  function maskPassages(paths,left,right,stations,corners,width,reverse) {
    if(!root.RibbonMask)throw new Error('Ribbon masking helper is missing');
    function resample(nodes) {
      let i=0;
      return stations.map(s=>{
        while(i+1<nodes.length-1 && nodes[i+1].s<s)i++;
        const a=nodes[i],b=nodes[Math.min(i+1,nodes.length-1)];
        const t=clamp((s-a.s)/(b.s-a.s||1),0,1);
        return [mix(a.p[0],b.p[0],t),mix(a.p[1],b.p[1],t)];
      });
    }
    const l=resample(left),r=resample(right),faces=[],grid=new Map();
    const cell=Math.max(16,width*2);
    function keys(x0,y0,x1,y1) {
      const out=[];
      for(let x=Math.floor(x0/cell);x<=Math.floor(x1/cell);x++)
        for(let y=Math.floor(y0/cell);y<=Math.floor(y1/cell);y++)out.push(x+','+y);
      return out;
    }
    for(let i=0;i<stations.length-1;i++) {
      const polygon=[l[i],l[i+1],r[i+1],r[i]];
      const x0=Math.min(...polygon.map(p=>p[0])),x1=Math.max(...polygon.map(p=>p[0]));
      const y0=Math.min(...polygon.map(p=>p[1])),y1=Math.max(...polygon.map(p=>p[1]));
      faces.push({polygon,start:stations[i],end:stations[i+1],x0,x1,y0,y1});
      for(const key of keys(x0,y0,x1,y1)) {if(!grid.has(key))grid.set(key,[]);grid.get(key).push(i);}
    }
    const joinRegions=corners.map(c=>({s:c.s,reach:width*Math.min(4,Math.abs(Math.tan(c.turn/2)))*2+8}));
    const strands=[],strandIndices=[];
    paths.forEach((nodes,strandIndex)=>{
      let run=[];
      const finish=()=>{if(run.length>1){strands.push(run);strandIndices.push(strandIndex);}run=[];};
      for(let i=0;i<nodes.length-1;i++) {
        const a=nodes[i],b=nodes[i+1];
        const x0=Math.min(a.p[0],b.p[0]),x1=Math.max(a.p[0],b.p[0]);
        const y0=Math.min(a.p[1],b.p[1]),y1=Math.max(a.p[1],b.p[1]);
        const candidates=new Set(keys(x0,y0,x1,y1).flatMap(k=>grid.get(k)||[]));
        const blockers=[];
        for(const j of candidates) {
          const f=faces[j];
          // Adjacent cross sections belong to this passage, not an overpass.
          if(reverse ? f.end>=a.s-4 : f.start<=b.s+4)continue;
          if(f.x1<x0 || f.x0>x1 || f.y1<y0 || f.y0>y1)continue;
          if(joinRegions.some(c=>Math.abs((a.s+b.s)/2-c.s)<c.reach && Math.abs((f.start+f.end)/2-c.s)<c.reach))continue;
          blockers.push(f.polygon);
        }
        const intervals=blockers.length?root.RibbonMask.visibleIntervals(a.p,b.p,blockers):[[0,1]];
        if(!intervals.length){finish();continue;}
        for(const [lo,hi] of intervals) {
          const first=[mix(a.p[0],b.p[0],lo),mix(a.p[1],b.p[1],lo)];
          const last=[mix(a.p[0],b.p[0],hi),mix(a.p[1],b.p[1],hi)];
          if(lo>1e-9 || (run.length && dist(run.at(-1),first)>1e-7))finish();
          if(!run.length)run.push(first);
          if(dist(run.at(-1),last)>1e-9)run.push(last);
          if(hi<1-1e-9)finish();
        }
      }
      finish();
    });
    return {strands,strandIndices};
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

  // A phrase shares a small rhythmic motif, with bounded local departures.
  // Independent random streams keep height edits from moving crest stations.
  function crestProfile(total, options) {
    const opts = Object.assign({}, defaults, options || {});
    const amount = key => clamp(+(opts[key] ?? opts.variation) || 0, 0, 1);
    const spacing = amount('spacingVariation'), height = amount('heightVariation');
    const phrasing = clamp(+(opts.phrasing ?? .7) || 0, 0, 1);
    // Reserve the upper half for stronger contrast; the lower half is unchanged.
    const spacingPush = smooth(clamp((spacing-.5)*2,0,1));
    const heightPush = smooth(clamp((height-.5)*2,0,1));
    const heightContrast = v => {
      const power=1+2.5*heightPush, a=Math.pow(v,power), b=Math.pow(1-v,power);
      return clamp(a/(a+b),.015,1);
    };
    const wave = Math.max(1, +opts.wavelength || defaults.wavelength);
    const seed = (opts.seed >>> 0);
    const rhythm = rng(seed ^ 0xA341316C), heights = rng(seed ^ 0xC8013EA4);
    const structure = rng(seed ^ 0xAD90777D);
    // Use a whole number of lobes, including short paths. Distribute the
    // terminal remainder across the path instead of chopping the last lobe.
    const count = Math.max(1, Math.min(4096, Math.round(total / wave)));
    const motif = Array.from({length: 3}, () => .4 + structure() * 1.1);
    const events = [];
    let phraseLeft = 0, phraseSize = 0, accent = 0, phraseGain = 1, pace = 1;
    for (let i = 0; i < count; i++) {
      if (phraseLeft === 0) {
        phraseSize = 3 + Math.floor(structure() * 3);
        phraseLeft = phraseSize;
        accent = Math.floor(structure() * Math.min(phraseSize, count-i));
        phraseGain = .82 + structure() * .18;
        pace = .65 + structure() * .7;
      }
      const position = phraseSize - phraseLeft--;
      const localSpan = .25 + rhythm() * 1.5;
      const phraseSpan = pace * motif[position % motif.length];
      const span = clamp(Math.pow(mix(1, mix(localSpan, phraseSpan, phrasing), spacing),
        1+2.5*spacingPush),.18,3.5);
      const skew = (rhythm() - .5) * .5 * spacing;
      const freeHeight = .08 + heights() * .92;
      const hierarchy = phraseGain * (position === accent ? 1 : .12 + heights() * .73);
      const peak = heightContrast(mix(.86, mix(freeHeight, hierarchy, phrasing), height));
      const trough = heightContrast(mix(.21, .07 + heights() * .2, height));
      events.push({span, skew, peak, trough});
    }
    // Quiet crests can now be very small; keep their neighbouring troughs
    // below both peaks rather than accidentally introducing extra extrema.
    events.forEach((e,i)=>{e.trough=Math.min(e.trough,.65*e.peak,.65*(events[i+1]?.peak??e.peak));});
    const scale = Math.max(0, total) / events.reduce((sum,e) => sum+e.span, 0);
    const knots = [{s:0,v:0}];
    let s = 0;
    for (let i=0; i<events.length; i++) {
      const e=events[i], length=e.span*scale;
      knots.push({s:s+length*(.5+e.skew),v:e.peak});
      s+=length;
      knots.push({s:i===events.length-1?total:s,v:i===events.length-1?0:e.trough});
    }
    return profileFromKnots(knots, Math.min(wave*.055,total*.04));
  }

  function profileFromKnots(knots, radius=0) {
    // Average the width profile over a small arc-length neighbourhood. Exact
    // cubic integration gives continuous curvature across the old knot seams.
    // Odd reflection at the ends keeps the shared endpoint width exactly zero.
    const areas=[0];
    for(let i=1;i<knots.length;i++) {
      const a=knots[i-1],b=knots[i];
      areas.push(areas[i-1]+(b.s-a.s)*(a.v+b.v)/2);
    }
    const total=knots.at(-1).s;
    function interval(at) {
      let lo=0,hi=knots.length-1;
      while(hi-lo>1) {const mid=(lo+hi)>>1;if(knots[mid].s<at)lo=mid;else hi=mid;}
      return lo;
    }
    function integral(at) {
      if(at<0)at=-at;
      if(at>total)at=2*total-at;
      const i=interval(at),a=knots[i],b=knots[i+1],len=b.s-a.s;
      const t=clamp((at-a.s)/(len||1),0,1);
      return areas[i]+len*(a.v*t+(b.v-a.v)*(t*t*t-.5*t*t*t*t));
    }
    return Object.assign(function(at) {
      at=clamp(at,0,total);
      if(radius>0)return clamp((integral(at+radius)-integral(at-radius))/(2*radius),0,1);
      const i=interval(at),a=knots[i],b=knots[i+1];
      return mix(a.v,b.v,smooth(clamp((at-a.s)/(b.s-a.s||1),0,1)));
    },{knots,smoothingRadius:radius});
  }

  function relatedCrests(left, total, opts) {
    const random=rng((opts.seed>>>0)^0x85EBCA6B);
    const spacing=clamp(+(opts.spacingVariation??opts.variation)||0,0,1);
    const height=clamp(+(opts.heightVariation??opts.variation)||0,0,1);
    // Perturb corresponding stations, never cumulative intervals: the two
    // sides can answer off-beat without drifting into unrelated rhythms.
    const knots=left.knots.map((k,i,all)=>{
      if(i===0||i===all.length-1)return {s:k.s,v:0};
      const room=Math.min(k.s-all[i-1].s,all[i+1].s-k.s);
      return {s:k.s+(random()-.5)*.55*spacing*room,
        v:clamp(k.v*(1+(random()-.5)*.55*height),.035,1)};
    });
    for(let i=2;i<knots.length-1;i+=2)
      knots[i].v=Math.min(knots[i].v,.65*knots[i-1].v,.65*knots[i+1].v);
    return profileFromKnots(knots,left.smoothingRadius);
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
    const corners = sharpCorners(spine,sampled.ss);
    function profiles(seed) {
      const opts={...optionsForProfiles,seed};
      const leftRandom = rng(opts.seed);
      const phrased = opts.rhythm === "phrased";
      const leftProfile = phrased ? crestProfile(sampled.total, opts) : knotProfile(sampled.total, opts, leftRandom);
      const rightOpts={...opts,wavelength:opts.independentWavelengths ? Math.max(1,+opts.wavelengthRight||opts.wavelength) : opts.wavelength};
      const rightBase=rightOpts.wavelength===opts.wavelength ? leftProfile :
        (phrased ? crestProfile(sampled.total,rightOpts) : knotProfile(sampled.total,rightOpts,rng(opts.seed)));
      let rightProfile;
      if (opts.relation === "mirrored") rightProfile = rightBase;
      else if (opts.relation === "independent") rightProfile = phrased
        ? crestProfile(sampled.total, {...rightOpts,seed:(opts.seed>>>0)^0x9E3779B9})
        : knotProfile(sampled.total, rightOpts, rng((opts.seed >>> 0) ^ 0x9E3779B9));
      else if (phrased) rightProfile = relatedCrests(rightBase, sampled.total, rightOpts);
      else {
        const relatedRandom = rng((opts.seed >>> 0) ^ 0x85EBCA6B);
        const guide = rightBase.knots.slice(1).map(k => ({
          spacing: clamp(k.spacing + (relatedRandom() - 0.5) * 0.16 * opts.variation, 0.65, 1.35),
          amplitude: clamp(k.amplitude * (1 + (relatedRandom() - 0.5) * 0.28 * opts.variation), 0.12, 1)
        }));
        rightProfile = knotProfile(sampled.total, rightOpts, relatedRandom, guide);
      }

      return [leftProfile,rightProfile];
    }
    const optionsForProfiles=opts;
    const blend=clamp(+opts.seedBlend||0,0,1);
    const seedB=opts.seedB ?? opts.seed;
    const aProfiles=profiles(blend===1?seedB:opts.seed);
    const bProfiles=blend>0&&blend<1 ? profiles(seedB) : aProfiles;
    const [leftProfile,rightProfile]=aProfiles.map((a,i)=>
      blend>0&&blend<1 ? s=>mix(a(s),bProfiles[i](s),blend) : a);

    function outerWidths(profile, sideIndex) {
      const widths = spine.map((p, i) => {
        if (i === 0 || i === spine.length - 1) return 0;
        const base = profile(sampled.ss[i]);
        const requested = opts.width * base * taperAt(sampled.ss[i], sampled.total, opts.taper);
        return requested;
      });
      if(blend>0&&blend<1&&opts.seed!==seedB) {
        let peakA=0,peakB=0,peakMixed=0;
        for(let i=1;i<spine.length-1;i++) {
          const s=sampled.ss[i], envelope=opts.width*taperAt(s,sampled.total,opts.taper);
          peakA=Math.max(peakA,aProfiles[sideIndex](s)*envelope);
          peakB=Math.max(peakB,bProfiles[sideIndex](s)*envelope);
          peakMixed=Math.max(peakMixed,widths[i]);
        }
        // Misaligned peaks otherwise cancel during a profile crossfade. One
        // gain per side preserves the local rhythm and strand spacing.
        const gain=peakMixed>1e-12 ? mix(peakA,peakB,blend)/peakMixed : 1;
        return widths.map(w=>w*gain);
      }
      return widths;
    }

    const leftWidths = outerWidths(leftProfile,0);
    const rightWidths = outerWidths(rightProfile,1);
    function side(sign, widths, level) {
      const nodes=spine.map((p, i) => {
        if (i === 0) return {p:source[0].slice(),s:sampled.ss[i]};
        if (i === spine.length - 1) return {p:source[source.length - 1].slice(),s:sampled.ss[i]};
        const width = widths[i] * level;
        return {p:[p[0] + sign * frame[i].nx * width, p[1] + sign * frame[i].ny * width],s:sampled.ss[i]};
      });
      return corners.length ? root.RibbonJoin.envelope(nodes,spine,sampled.ss,corners,opts.width) : nodes;
    }

    const retained = clamp(Math.floor(opts.retainedSteps ?? opts.steps),1,opts.steps);
    const leftLevels = [], rightLevels = [];
    for (let i = retained; i >= 1; i--) leftLevels.push(side(1, leftWidths, i / opts.steps));
    for (let i = 1; i <= retained; i++) rightLevels.push(side(-1, rightWidths, i / opts.steps));
    const leftNodes=leftLevels[0],rightNodes=rightLevels[rightLevels.length-1];
    const paths=leftLevels.concat([spine.map((p,i)=>({p,s:sampled.ss[i]}))],rightLevels);
    const left=leftNodes.map(n=>n.p),right=rightNodes.map(n=>n.p);
    let result;
    if(opts.maskLoops) {
      const visible=maskPassages(paths,leftNodes,rightNodes,sampled.ss,corners,opts.width,!!opts.reverseOrder);
      result={...visible,left,right,spine,diagnostics};
    } else result={strands:paths.map(nodes=>nodes.map(n=>n.p)),left,right,spine,diagnostics};
    const mode=opts.outputMode||'strands';
    if(mode!=='strands'||opts.solidOccluder) {
      if(!root.RibbonSilhouette)throw Error('Ribbon silhouette helper missing');
      const spineNodes=spine.map((p,i)=>({p,s:sampled.ss[i]}));
      result.silhouette=root.RibbonSilhouette.fromNodes(leftNodes,rightNodes,spineNodes,{mergeOverlaps:true});
      const outline=opts.mergeOverlaps||mode==='solid' ? result.silhouette :
        root.RibbonSilhouette.fromNodes(leftNodes,rightNodes,spineNodes,{mergeOverlaps:false});
      result.drawingPaths=mode==='strands'?result.strands:outline.flat();
      result.occluders=opts.solidOccluder||mode==='solid' ? result.silhouette.flat().map(points=>({points,filled:true})) : [];
    }
    return result;
  }

  function generateMany(inputs,options={}) {
    const length=points=>points.slice(1).reduce((sum,p,i)=>sum+dist(points[i],p),0);
    const lengths=inputs.map(p=>{const clean=sanitize(p);return clean.length>1&&!same(clean[0],clean.at(-1))?length(clean):0;});
    const longest=Math.max(0,...lengths), steps=Math.max(1,Math.floor(+options.steps||defaults.steps));
    const counts=lengths.map(l=>options.widthByLength&&longest>0 ? Math.max(1,Math.ceil(steps*l/longest-1e-10)) : steps);
    const items=inputs.map((p,i)=>generate(p,{...options,retainedSteps:counts[i]}));
    const result={items,retainedSteps:counts,strands:items.flatMap(r=>r.strands),
      spines:items.map(r=>r.spine),drawingPaths:items.flatMap(r=>r.drawingPaths??r.strands)};
    if(items.some(r=>r.silhouette)) {
      result.silhouette=root.RibbonSilhouette.union(items.map(r=>r.silhouette??[]));
      if(options.outputMode==='solid'||options.outputMode==='outline'&&options.mergeOverlaps)
        result.drawingPaths=result.silhouette.flat().concat(items.filter(r=>r.diagnostics.skipped).flatMap(r=>r.strands));
      result.occluders=options.solidOccluder||options.outputMode==='solid' ? result.silhouette.flat().map(points=>({points,filled:true})) : [];
    }
    return result;
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
    loop: join(
      cubic([60,180],[220,155],[440,55],[620,40],100),
      // Collinear handles at both seams: this fixture is a smooth loop, not
      // two hidden corners. The tight return also gets finer input sampling.
      cubic([620,40],[740,30],[740,202],[620,190],260),
      cubic([620,190],[470,175],[200,70],[60,50],100)
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
    limitations: ["corner strips use a local union boundary with round outer turns", "no global intersection guarantee", "closed paths bypassed"]
  });

  const api = Object.freeze({ generate, generateMany, fixtures, profile, crestProfile });
  root.RibbonStudy = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
