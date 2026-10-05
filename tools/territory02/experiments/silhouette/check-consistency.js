const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={module:{exports:{}}};
vm.runInNewContext(fs.readFileSync('territory-engine.js','utf8')+'\nmodule.exports.silhouetteWarp = silhouetteWarp;',context);
const warpPopulation=context.module.exports.silhouetteWarp;
const P=Array.from({length:90},(_,i)=>[45+i*1.7,70+Math.sin(i/25)*23]);
const clone=P=>P.map(p=>p.slice());
const chans=[{id:0,cls:'trunk',pts:clone(P)}];
const snaps=[{ch:0,t:0,pts:clone(P),speed:P.map(()=>0)},{ch:0,t:20,pts:clone(P),speed:P.map(()=>0)}];
const events=[{at:P[40].slice(),loop:clone(P)}];
const warp=warpPopulation(chans,snaps,events,13,{x0:0,y0:0,x1:300,y1:218});
const encode=p=>JSON.stringify(p);
assert.strictEqual(encode(chans[0].pts),encode(snaps[0].pts));
assert.strictEqual(encode(chans[0].pts),encode(snaps[1].pts));
assert.strictEqual(encode(chans[0].pts),encode(events[0].loop));
assert.strictEqual(encode(events[0].at),encode(snaps[0].pts[40]));
for(let y=0;y<=218;y+=2)for(let x=0;x<=300;x+=2){
 const p=warp([x,y]);assert(p.every(Number.isFinite));assert(p[0]>=0&&p[0]<=300&&p[1]>=0&&p[1]<=218);
 assert.strictEqual(encode(p),encode(warp([x,y])));
}
console.log('Shared coordinates agree across snapshots, channels, event points and cutoff loops; grid finite/bounded/deterministic.');
