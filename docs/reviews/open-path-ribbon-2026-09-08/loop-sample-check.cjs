const assert=require('node:assert/strict');
require('./load-join.cjs');require('./masking.js');require('./geometry.js');
const R=globalThis.RibbonStudy,points=R.fixtures.loop;
for(const joint of [[620,40],[620,190]]) {
  const i=points.findIndex(p=>Math.hypot(p[0]-joint[0],p[1]-joint[1])<1e-9);
  assert.ok(i>0&&i<points.length-1);
  const a=[points[i][0]-points[i-1][0],points[i][1]-points[i-1][1]];
  const b=[points[i+1][0]-points[i][0],points[i+1][1]-points[i][1]];
  const turn=Math.abs(Math.atan2(a[0]*b[1]-a[1]*b[0],a[0]*b[0]+a[1]*b[1]));
  assert.ok(turn<.025,`loop sample joint ${joint} has a visible ${(turn*180/Math.PI).toFixed(2)} degree kink`);
}
for(const maskLoops of [false,true]) {
  const result=R.generate(points,{width:24,wavelength:180,variation:.75,steps:10,seed:7,maskLoops});
  assert.ok(result.strands.every(p=>p.length>=2&&p.every(q=>q.every(Number.isFinite))));
}
console.log('loop-sample-check: tangent continuity and both overlap modes passed');
