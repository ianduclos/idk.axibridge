const assert=require('node:assert/strict'),crypto=require('node:crypto'),baseline=require('../../experiments/baseline/territory-engine.js'),{E,regrowTexture}=require('./regrow.cjs'),{rewriteChannels}=require('../rewrite.cjs');
const recipe=require('../../full.json').prm,hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const freeze=x=>{if(x&&typeof x==='object'){Object.freeze(x);Object.values(x).forEach(freeze);}return x;};
for(const seed of [13,24]){
 const sheet=E.randomSheet(seed),prm={...recipe,camps:Math.max(2,sheet.camps),debug:true};
 assert.equal(hash(E.runTerritory(sheet.cores,prm,seed,'reversed').lines),hash(baseline.runTerritory(sheet.cores,prm,seed,'reversed').lines),'Context capture must leave the full original baseline identical');
 const source=E.runTerritory(sheet.cores,{...prm,density:0},seed,'reversed'),first=freeze(rewriteChannels(source.T.meanderDebug.chans,seed,1)),bare=freeze(rewriteChannels(first.courses,seed,2)),before=hash([source.lines,source.T.meanderDebug,bare]);
 for(const mode of ['grown','led']){
  const a=regrowTexture(source.T.textureContext,bare,first,seed,mode),b=regrowTexture(source.T.textureContext,bare,first,seed,mode);
  assert.equal(hash(a),hash(b),'Regrowth must repeat');assert(a.strokes.length>0,'Regrowth must restore nonempty physical texture');
  let mm=0,points=0;for(const P of a.strokes){assert(P.length>1);points+=P.length;for(let i=0;i<P.length;i++){const[x,y]=P[i];assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218);if(i)mm+=Math.hypot(x-P[i-1][0],y-P[i-1][1]);}}
  assert(mm>1000&&mm<100000&&points<250000,'Physical texture must have substantive ink within safety limits');
  assert.equal(hash([source.lines,source.T.meanderDebug,bare]),before,'Texture must not mutate the earlier drawing or frozen new courses');
 }
}
console.log('Original full baseline parity, substantive physical texture, repeatability, frozen-course purity, bounds and budgets passed.');
