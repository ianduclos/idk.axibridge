'use strict';
require('./load-join.cjs');require('./geometry.js');
const assert=require('node:assert/strict'),R=globalThis.RibbonStudy;
const inputs=[[[0,0],[600,0]],[[0,80],[300,80]],[[0,160],[120,160]]];
const opts={rhythm:'phrased',steps:10,width:30,seed:7,seedB:19,seedBlend:.5};
const snapshot=JSON.stringify(inputs);
const trimmed=R.generateMany(inputs,{...opts,widthByLength:true});
assert.deepEqual(trimmed.retainedSteps,[10,5,2]);
for(let i=0;i<inputs.length;i++) {
 const full=R.generate(inputs[i],opts),k=trimmed.retainedSteps[i];
 assert.deepEqual(trimmed.items[i].strands,full.strands.slice(10-k,10+k+1),'trim only removes outer strands; it never moves survivors');
}
assert.equal(JSON.stringify(inputs),snapshot);
assert.deepEqual(R.generateMany(inputs,opts).retainedSteps,[10,10,10]);
assert.deepEqual(R.generateMany([inputs[2]],{...opts,widthByLength:true}).retainedSteps,[10],'one input retains full width');
const corner=R.fixtures.corner;
const full=R.generate(corner,opts),half=R.generate(corner,{...opts,retainedSteps:5});
assert.deepEqual(half.strands,full.strands.slice(5,16),'retained corner strands preserve existing geometry');
assert.deepEqual(half.left,full.strands[5]);
assert.deepEqual(half.right,full.strands[15]);
console.log('length-width-check: proportional pair removal, exact survivor spacing, single-path and corner behaviour passed');
