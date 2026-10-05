const E=require('./territory-engine.js'), fs=require('fs');
const report=[];
for (const recipe of ['sparse','full']) {
 const cfg=JSON.parse(fs.readFileSync('../../'+recipe+'.json'));
 for (const seed of [5,13,18,24,47,82]) {
  const sh=E.randomSheet(seed), prm={...cfg.prm,camps:Math.max(2,sh.camps)};
  const run=()=>E.runTerritory(sh.cores,prm,seed,'reversed');
  const a=run(), b=run(), strokes=a.lines.flatMap(l=>l.strokes);
  const ink=strokes.reduce((s,P)=>s+E.polyLen(P),0);
  const points=strokes.flat().length;
  const bad=strokes.flat().filter(p=>p.length!==2||!p.every(Number.isFinite)||p[0]<0||p[0]>300||p[1]<0||p[1]>218);
  for (const line of a.lines.filter(l=>l.kind==='pocket-lip')) {
   const prefix=line.strokes[0].slice(0,3), same=(p,q)=>p[0]===q[0]&&p[1]===q[1];
   const linked=a.lines.filter(l=>l.kind==='strand'&&l.ch===line.ch).some(l=>l.strokes.some(P=>P.some((p,i)=>same(p,prefix[0])&&[1,-1].some(d=>prefix.every((q,j)=>P[i+j*d]&&same(q,P[i+j*d]))))));
   if(!linked) throw Error('Passage prefix not inherited: '+recipe+' '+seed);
  }
  if(JSON.stringify(a.lines)!==JSON.stringify(b.lines)||bad.length||ink>100000||points>250000) throw Error(JSON.stringify({recipe,seed,ink,bad:bad.slice(0,3)}));
  report.push({recipe,seed,inkM:+(ink/1000).toFixed(2),strokes:strokes.length,points,finiteWithinBed:true,deterministic:true});
 }
}
fs.writeFileSync('round2-checks.json',JSON.stringify(report,null,2)); console.log(report);
