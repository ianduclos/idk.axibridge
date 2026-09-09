// Pure arrangement operations; the registered Python source remains the field solver.
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
export function fit(m, p) {
  if (m.kind === 'bar') {
    const a = m.rotation * Math.PI / 180;
    const extent = () => [
      (Math.abs(Math.cos(a))*m.length + Math.abs(Math.sin(a))*m.thickness)/2,
      (Math.abs(Math.sin(a))*m.length + Math.abs(Math.cos(a))*m.thickness)/2,
    ];
    let [ex, ey] = extent();
    const scale = Math.min(1, (p.width-1)/(2*ex), (p.height-1)/(2*ey));
    m.length = Math.max(8, m.length*scale);
    m.thickness = Math.max(4, m.thickness*scale);
    [ex, ey] = extent();
    m.x = clamp(m.x, ex+.05, p.width-ex-.05);
    m.y = clamp(m.y, ey+.05, p.height-ey-.05);
  } else {
    m.x = clamp(m.x, 4.05, p.width-4.05);
    m.y = clamp(m.y, 4.05, p.height-4.05);
  }
  return m;
}


export function hasPresets(p) { return p.presets.some(Boolean); }
export function withPresetSize(m,p,i) {
  const size = p.preset_sizes?.[i] ?? p.presets.find(Boolean)?.[i];
  return size ? {...m,length:size.length,thickness:size.thickness} : {...m};
}
export function completePresets(p) { return p.presets.every(Boolean); }

// Consume the same random draws for each slot, including locked slots.
export function scattered(p, count, type) {
  let state = p.seed >>> 0;
  const random = () => {
    state = (Math.imul(state, 1664525)+1013904223) >>> 0;
    return state / 4294967296;
  };
  const fixed = hasPresets(p);
  return Array.from({length: fixed ? p.magnets.length : count}, (_, i) => {
    const x = p.width*random(), y = p.height*random(), rotation = random()*360-180;
    const flipped = random() > .5;
    const strength = p.scatter_strength_min + random()*(p.scatter_strength_max-p.scatter_strength_min);
    const previous = p.magnets[i];
    if (previous?.locked) return {...previous};
    const kind = type === 'bars' ? 'bar' : type === 'poles'
      ? (i % 2 ? 'south' : 'north') : ['bar','north','south'][i % 3];
    return fit(fixed ? withPresetSize({...previous,x,y,rotation,strength},p,i)
      : {kind,x,y,rotation,strength,flipped,length:Math.min(48,p.width*.3),thickness:12,locked:false},p);
  });
}

const wrap = angle => ((angle+180)%360+360)%360-180;
const near = (angle, reference) => reference+wrap(angle-reference);
export function interpolated(p, x, y) {
  const weights = [(1-x)*(1-y),x*(1-y),(1-x)*y,x*y];
  return p.magnets.map((current,i) => {
    const corners = p.presets.map(corner => corner[i]);
    const exact = weights.indexOf(1);
    if (exact >= 0) return fit(withPresetSize({...corners[exact],locked:!!current.locked},p,i),p);
    const result = withPresetSize({...corners[0],locked:!!current.locked},p,i);
    for (const field of ['x','y','strength']) {
      result[field] = corners.reduce((sum,m,k) => sum+weights[k]*m[field],0);
    }
    // Unwrap once for the whole square, avoiding a seam as a slider moves.
    // B and C take the short turn from A; D takes the turn nearest their mean.
    const a = corners[0].rotation;
    const b = near(corners[1].rotation,a), c = near(corners[2].rotation,a);
    const d = near(corners[3].rotation,(b+c)/2);
    result.rotation = wrap(weights[0]*a+weights[1]*b+weights[2]*c+weights[3]*d);
    result.strength = clamp(result.strength,.1,3);
    result.length = clamp(result.length,8,80); result.thickness = clamp(result.thickness,4,24);
    return fit(result,p);
  });
}
