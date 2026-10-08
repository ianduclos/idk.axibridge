// Geometry and provenance checks only. No aesthetic acceptance thresholds.
const assert=require('node:assert/strict');const fs=require('node:fs'),path=require('node:path');
const root=__dirname, prm=JSON.parse(fs.readFileSync(path.join(root,'full.json'))).prm;
const names=['baseline','pace','silhouette','void'], seeds=[5,13,18,24,47,82],results=[];
const baseline=require('./experiments/baseline/territory-engine.js');
for(const name of names){const E=require(path.join(root,'experiments',name,'territory-engine.js'));
 for(const mode of ['sparse','full'])for(const seed of seeds){
  const sh=E.randomSheet(seed);assert.deepEqual(sh,baseline.randomSheet(seed),`Same input cores ${name}/${seed}`);const input=JSON.stringify(sh.cores);const params={...prm,camps:Math.max(2,sh.camps),density:mode==='sparse'?0:1};
  const a=E.runTerritory(sh.cores,params,seed,'reversed');assert.equal(JSON.stringify(sh.cores),input,`Input purity ${name}/${seed}`);
  const b=E.runTerritory(sh.cores,params,seed,'reversed');assert.deepEqual(a.lines,b.lines,`Determinism ${name}/${mode}/${seed}`);
  const strokes=a.lines.flatMap(l=>l.strokes);assert.ok(strokes.length);let mm=0,points=0;
  for(const st of strokes){assert.ok(st.length>=2);points+=st.length;for(let i=0;i<st.length;i++){const [x,y]=st[i];assert.ok(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218,`Bed bounds ${name}/${seed}`);if(i)mm+=Math.hypot(x-st[i-1][0],y-st[i-1][1]);}}
  assert.ok(mm<=100000.01);assert.ok(points<=250000,`Kept source point budget ${name}/${seed}`);
  results.push({name,mode,seed,points,strokes:strokes.length,inkMm:Math.round(mm)});
 }
}
const out=path.join(root,'evidence',process.argv[2]||'round2','verification.json');fs.writeFileSync(out,JSON.stringify(results,null,2)+'\n');console.log(`${results.length} cases passed: identical inputs, purity, deterministic output, finite within-bed geometry, 100m ink and frozen-source point budget.`);
