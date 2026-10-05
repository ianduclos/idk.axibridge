const E=require('./territory-engine.js'), fs=require('fs');
const report=[];
for (const recipe of ['sparse','full']) {
 const cfg=JSON.parse(fs.readFileSync('../../'+recipe+'.json'));
 for (const seed of [5,13,18,24]) {
  const sh=E.randomSheet(seed), prm={...cfg.prm,camps:Math.max(2,sh.camps)};
  const run=()=>E.runTerritory(sh.cores,prm,seed,'reversed');
  const a=run(), b=run(), strokes=a.lines.flatMap(l=>l.strokes);
  const ink=strokes.reduce((s,P)=>s+E.polyLen(P),0);
  const bad=strokes.flat().filter(p=>p.length!==2||!p.every(Number.isFinite)||p[0]<0||p[0]>300||p[1]<0||p[1]>218);
  if(JSON.stringify(a.lines)!==JSON.stringify(b.lines)||bad.length||ink>100000) throw Error(JSON.stringify({recipe,seed,ink,bad:bad.slice(0,3)}));
  report.push({recipe,seed,inkM:+(ink/1000).toFixed(2),strokes:strokes.length,finiteWithinBed:true,deterministic:true});
 }
}
fs.writeFileSync('round1-checks.json',JSON.stringify(report,null,2)); console.log(report);
