'use strict';
require('./load-join.cjs');require('./masking.js');require('./silhouette.js');require('./geometry.js');
const assert=require('node:assert/strict'),R=globalThis.RibbonStudy;
const opts={rhythm:'phrased',width:24,steps:4,seed:7,seedB:19,seedBlend:.5,relation:'related'};
let cases=0;
for(const [name,source] of Object.entries(R.fixtures)) {
 const before=JSON.stringify(source);
 for(const outputMode of ['outline','solid']) {
  const r=R.generate(source,{...opts,outputMode,mergeOverlaps:true,solidOccluder:true});
  assert.ok(r.drawingPaths.length>0,name);
  assert.deepEqual(r.drawingPaths,r.silhouette.flat());
  assert.ok(r.drawingPaths.every(p=>JSON.stringify(p[0])===JSON.stringify(p.at(-1))),name+' closed boundaries only');
  assert.ok(r.drawingPaths.flat().flat().every(Number.isFinite));
  assert.ok(r.occluders.every(p=>p.filled===true));
  assert.deepEqual(r.occluders.map(p=>p.points),r.drawingPaths);
  cases++;
 }
 const raw=R.generate(source,{...opts,outputMode:'outline',mergeOverlaps:false});
 assert.equal(raw.drawingPaths.length,1,'raw outline follows the two edges in one ring');
 assert.equal(JSON.stringify(source),before,'source stays unchanged');
}
const crossing=[[[0,0],[100,100]],[[0,100],[100,0]]];
const merged=R.generateMany(crossing,{...opts,wavelength:140,outputMode:'outline',mergeOverlaps:true});
const separate=R.generateMany(crossing,{...opts,wavelength:140,outputMode:'outline',mergeOverlaps:false});
assert.equal(separate.drawingPaths.length,2);
assert.equal(merged.drawingPaths.length,1,'overlapping ribbons have one external boundary');
const closed=[[0,0],[20,0],[20,20],[0,0]];
assert.deepEqual(R.generate(closed,{...opts,outputMode:'outline'}).strands,[closed],'closed source bypass still applies');
const mixed=R.generateMany([R.fixtures.straight,closed],{...opts,outputMode:'outline',mergeOverlaps:true});
assert.ok(mixed.drawingPaths.some(p=>JSON.stringify(p)===JSON.stringify(closed)),'mixed open/closed collections retain bypassed paths');
const band=R.generate(R.fixtures.straight,{...opts,relation:'independent',interpolation:'edges',retainedSteps:1,outputMode:'outline',mergeOverlaps:true});
for(const i of [50,100,150,200]) {
 const x=band.left[i][0],low=Math.min(band.left[i][1],band.right[i][1]),high=Math.max(band.left[i][1],band.right[i][1]);
 const visible=globalThis.RibbonSilhouette.clipPaths([[[x,low-1],[x,high+1]]],band.silhouette);
 const visibleLength=visible.reduce((n,p)=>n+p.slice(1).reduce((d,q,j)=>d+Math.hypot(q[0]-p[j][0],q[1]-p[j][1]),0),0);
 assert.ok(Math.abs(visibleLength-2)<1e-6,'trimmed edge silhouette follows its shifted band, not original source');
}
console.log(`output-check: ${cases} silhouette cases, raw outlines, filled metadata, union and closed bypass passed`);
