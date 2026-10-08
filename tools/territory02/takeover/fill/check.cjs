const assert=require('node:assert/strict'),{bindFill}=require('./bind-fill.cjs');
const fixture=[{id:0,present:[[30,45],[90,45],[160,65],[230,60]]},{id:1,present:[[35,72],[95,72],[155,100],[235,84]]},{id:2,present:[[50,130],[100,110],[170,120],[235,155]]}];
const freeze=x=>{if(x&&typeof x==='object'){Object.freeze(x);Object.values(x).forEach(freeze);}return x;};freeze(fixture);
assert.deepEqual(bindFill(fixture,13,'bands',0).strokes,[]);
assert.deepEqual(bindFill([],13,'pockets',5000).strokes,[]);
for(const mode of ['bands','pockets'])for(const seed of [5,13,18,24]){
 const result=bindFill(fixture,seed,mode,8000);
 assert(result.strokes.length>0,'Enabled fill must produce physical strokes from these nearby courses');
 assert.deepEqual(result,bindFill(fixture,seed,mode,8000));
 let mm=0,points=0;for(const P of result.strokes){assert(P.length>1);points+=P.length;for(let i=0;i<P.length;i++){const[x,y]=P[i];assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218);if(i)mm+=Math.hypot(x-P[i-1][0],y-P[i-1][1]);}}
 assert(mm<=8000.01&&points<250000);
 assert(result.regions.every(r=>r.courseIds.every(id=>fixture.some(c=>c.id===id))));
}
console.log('Fill checks passed: physical nonempty fills, off/empty behavior, frozen-input purity, repeatability, source associations, bed and budgets.');
