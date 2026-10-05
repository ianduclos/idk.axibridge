const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={module:{exports:{}}};
vm.runInNewContext(fs.readFileSync('territory-engine.js','utf8')+'\nmodule.exports.bez= silhouetteBezier; module.exports.hand= handLine; module.exports.rng= rngFor;',ctx);
const E=ctx.module.exports;
const P=Array.from({length:120},(_,i)=>[45+i*1.7,82+Math.sin(i/43)*38]),before=JSON.stringify(P);
let changed=0;
for(const seed of [5,13,18,24,47,82]){
 const a=E.bez(P,seed,0,true,{x0:0,y0:0,x1:300,y1:218});
 const b=E.bez(P,seed,0,true,{x0:0,y0:0,x1:300,y1:218});
 assert.strictEqual(JSON.stringify(a),JSON.stringify(b));assert.strictEqual(JSON.stringify(P),before);
 if(JSON.stringify(a)!==before)changed++;
 const strokes=E.hand(a,{A:0,step:2,over:0,lift:0,tremor:0,gate:1,l1:30,l2:10},E.rng(seed,700));
 assert(strokes.length&&strokes[0].length>20);
 for(const st of strokes)for(const [x,y]of st){assert(Number.isFinite(x)&&Number.isFinite(y));assert(x>=0&&x<=300&&y>=0&&y<=218);}
}
assert(changed===6);
console.log('Explicit cubic departures are deterministic/pure in six synthetic cases and remain finite/within bed after the actual 2 mm hand controls.');
