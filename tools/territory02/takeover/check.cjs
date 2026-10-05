// A disabled pass must preserve its source; an enabled pass must actually rewrite it.
// Mutation, unstable randomness and out-of-frame geometry would break reuse/export.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {rewriteChannels} = require('./rewrite.cjs');
const fixture = [
 {id:0, cls:'trunk', present:[[30,70],[80,25],[135,45],[180,100],[145,155],[220,185],[270,130]]},
 {id:1, cls:'minor', present:[[45,185],[75,130],[130,105],[175,145],[225,115],[265,35]]},
 {id:2, cls:'minor', present:[[85,190],[125,160],[155,105],[135,75],[185,35]]}
];
const deepFreeze = value => { if(value && typeof value==='object'){Object.freeze(value); for(const v of Object.values(value))deepFreeze(v);} return value; };
deepFreeze(fixture);
assert.deepEqual(rewriteChannels(fixture,13,0).strokes,fixture.map(c=>c.present));
const edited=rewriteChannels(fixture,13,2);
assert.notDeepEqual(edited.strokes,fixture.map(c=>c.present),'The enabled takeover must rewrite source geometry');
assert.deepEqual(edited,rewriteChannels(fixture,13,2),'Repeatability');
for(const stage of [1,2])for(const seed of [5,13,18,24,47,82]){
 const res=rewriteChannels(fixture,seed,stage);let mm=0,points=0;
 assert(res.strokes.length>0);
 for(const st of res.strokes){assert(st.length>1);points+=st.length;
  for(let i=0;i<st.length;i++){const [x,y]=st[i];assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218);if(i)mm+=Math.hypot(x-st[i-1][0],y-st[i-1][1]);}
 }
 assert(mm<=100000&&points<=250000);
}
// A real subsequent pass must accept frozen output geometry, including pieces
// left by earlier edits; this catches stale splice indices and accidental writes.
for(const seed of [5,13,18,24,47,82]){
 const first=rewriteChannels(fixture,seed,1);
 deepFreeze(first.courses);
 const second=rewriteChannels(first.courses,seed,2);
 assert(second.strokes.length>0);
 assert.deepEqual(second,rewriteChannels(first.courses,seed,2));
 assert.notDeepEqual(second.strokes,first.strokes);
}
console.log('Synthetic takeover checks passed: off preserves geometry; on rewrites; frozen inputs, repeatability and physical bounds.');
