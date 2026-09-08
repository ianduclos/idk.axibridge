require('./load-join.cjs');
const assert=require('node:assert/strict');
require('./masking.js');require('./geometry.js');
const R=globalThis.RibbonStudy;
const points=[[0,0],[200,200],[0,200],[200,0]];
const options={width:24,wavelength:180,seed:7,steps:4};
const raw=R.generate(points,options);
function directionsAtCrossing(result) {
  const directions=[];
  result.strands.forEach((path,index)=>{
    if(result.strandIndices[index]!==options.steps)return;
    for(let i=0;i<path.length-1;i++) {
      const a=path[i],b=path[i+1],dx=b[0]-a[0],dy=b[1]-a[1];
      if(Math.abs((100-a[0])*dy-(100-a[1])*dx)>1e-7)continue;
      if(100<Math.min(a[0],b[0])-1e-7 || 100>Math.max(a[0],b[0])+1e-7)continue;
      if(Math.hypot(dx,dy)>1e-8)directions.push(Math.sign(dx*dy));
    }
  });
  return [...new Set(directions)];
}
const later=R.generate(points,{...options,maskLoops:true});
const earlier=R.generate(points,{...options,maskLoops:true,reverseOrder:true});
assert.deepEqual(directionsAtCrossing(later),[-1],'only the later diagonal crosses above the centre');
assert.deepEqual(directionsAtCrossing(earlier),[1],'inverting order puts the earlier diagonal above');
for(const key of ['left','right','spine']) {
  assert.deepEqual(later[key],raw[key],'mask must not reshape the ribbon');
  assert.deepEqual(earlier[key],raw[key],'order inversion must not reshape the ribbon');
}
const length=result=>result.strands.reduce((n,p)=>n+p.slice(1).reduce((a,q,i)=>a+Math.hypot(q[0]-p[i][0],q[1]-p[i][1]),0),0);
assert.ok(length(later)<length(raw)-1,'masking removes actual drawing length');
assert.notDeepEqual(later.strands,earlier.strands,'order changes visible paths');
assert.deepEqual(later,R.generate(points,{...options,maskLoops:true}),'masking is deterministic');
assert.ok(later.strands.every(p=>p.length>=2&&p.every(q=>q.every(Number.isFinite))));
console.log('overlap-check: actual underpass cuts, inversion, unchanged shape and determinism passed');
