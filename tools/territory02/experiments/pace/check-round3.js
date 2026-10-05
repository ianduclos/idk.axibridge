const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={module:{exports:{}},console};
vm.runInNewContext(fs.readFileSync('territory-engine.js','utf8')+'\nmodule.exports.bezierPace=bezierPace;module.exports.crossings=crossings;',context);
const H=context.module.exports,E=require('./territory-engine.js');
const P=Array.from({length:121},(_,i)=>[45+1.5*i,100+25*Math.sin(i/10)]),speed=P.map(()=>0.02),original=JSON.stringify(P);
const edit=H.bezierPace(P,speed,E.mulberry32(47)),again=H.bezierPace(P,speed,E.mulberry32(47));
assert.equal(JSON.stringify(edit),JSON.stringify(again));assert.equal(JSON.stringify(P),original);
assert.equal(edit.pts.length,edit.speed.length);
assert.equal(JSON.stringify(edit.pts[0]),JSON.stringify(P[0]));assert.equal(JSON.stringify(edit.pts.at(-1)),JSON.stringify(P.at(-1)));
assert.equal(JSON.stringify(edit.pts.slice(0,edit.range[0])),JSON.stringify(P.slice(0,edit.range[0])));
assert.equal(JSON.stringify(edit.pts.slice(-P.length+edit.range[1]+1)),JSON.stringify(P.slice(edit.range[1]+1)));
assert(edit.controls.every(p=>p.every(Number.isFinite)));
assert(edit.pts.every(p=>p[0]>=0&&p[0]<=300&&p[1]>=0&&p[1]<=218));
const report=[];
for(const recipe of ['sparse','full']) {
  const cfg=JSON.parse(fs.readFileSync('round3-'+recipe+'.json','utf8'));
  for(const c of cfg.cells) {
    const sh=E.randomSheet(c.random),prm={...cfg.prm,camps:Math.max(2,sh.camps),debug:true};
    const run=p=>E.runTerritory(sh.cores,p,c.random,c.order),res=run(prm),repeat=run(prm),baseline=run({...prm,bezier:0});
    assert.equal(JSON.stringify(res.lines),JSON.stringify(repeat.lines));
    assert.equal(JSON.stringify(res.meander.events),JSON.stringify(baseline.meander.events));
    let mm=0,points=0;
    for(const stroke of res.lines.flatMap(l=>l.strokes)) {
      mm+=E.polyLen(stroke);
      for(const p of stroke) {assert(p.every(Number.isFinite));assert(p[0]>=0&&p[0]<=300&&p[1]>=0&&p[1]<=218);points++;}
    }
    assert(mm<100000&&points<=250000);
    const now=res.T.meanderDebug.chans,old=baseline.T.meanderDebug.chans;
    for(const ch of now) if(!ch.bezier) assert.equal(JSON.stringify(ch.present),JSON.stringify(old.find(o=>o.id===ch.id).present));
    const inter=chans=>chans.slice(1).map(ch=>ch.present&&chans[0].present?H.crossings(chans[0].present,ch.present):0);
    report.push({recipe,seed:c.random,mm:Math.round(mm),points,deterministic:true,finite:true,withinBed:true,beforeCross:inter(old),afterCross:inter(now),cubics:now.filter(ch=>ch.bezier).map(ch=>({id:ch.id,...ch.bezier}))});
  }
}
fs.writeFileSync('round3-checks.json',JSON.stringify(report,null,2)+'\n');
console.log(report.map(r=>`${r.recipe}/${r.seed}: ${r.mm}mm ${r.points}pts; cubic ${r.cubics.map(c=>c.id+' ratio='+c.handleRatio.toFixed(1)).join(',')}; crossings ${r.beforeCross.join(',')} -> ${r.afterCross.join(',')}`).join('\n'));
