const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const E=require('../../experiments/baseline/territory-engine.js'),{rewriteChannels}=require('../rewrite.cjs'),{bindFill}=require('./bind-fill.cjs');
const out=path.join(__dirname,'evidence');fs.mkdirSync(out,{recursive:true});
const recipe=JSON.parse(fs.readFileSync(path.join(__dirname,'../../sparse.json'))).prm;
const seeds=process.argv.includes('--holdouts')?[113,179,233,293]:[5,13,18,24,47,82],modes=['original','bare','bands','pockets'];
const length=strokes=>strokes.reduce((s,P)=>s+P.slice(1).reduce((n,p,i)=>n+Math.hypot(p[0]-P[i][0],p[1]-P[i][1]),0),0);
const svg=(strokes,box=[0,0,300,218])=>`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box.join(' ')}"><rect x="${box[0]}" y="${box[1]}" width="${box[2]}" height="${box[3]}" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round">${strokes.map(P=>`<path d="M${P.map(p=>p.map(x=>x.toFixed(3)).join(' ')).join(' L')}"/>`).join('')}</g></svg>`;
const records=[];
for(const seed of seeds){
 const sheet=E.randomSheet(seed),prm={...recipe,camps:Math.max(2,sheet.camps),density:0,debug:true},source=E.runTerritory(sheet.cores,prm,seed,'reversed'),first=rewriteChannels(source.T.meanderDebug.chans,seed,1),bare=rewriteChannels(first.courses,seed,2);
 const frozen=JSON.stringify(bare),baseHash=crypto.createHash('sha256').update(JSON.stringify(bare.strokes)).digest('hex');
 for(const [level,limit] of [['light',8000],['dense',18000]]){
  const original=E.runTerritory(sheet.cores,{...prm,density:1,ink:limit/1000},seed,'reversed').lines.flatMap(l=>l.strokes);
  const data={original:{strokes:original,regions:[]},bare:{strokes:bare.strokes,regions:[]}};
  for(const mode of ['bands','pockets']){
   const fill=bindFill(bare.courses,seed,mode,limit-length(bare.strokes)-10);assert.deepEqual(fill,bindFill(bare.courses,seed,mode,limit-length(bare.strokes)-10));
   data[mode]={strokes:bare.strokes.concat(fill.strokes),regions:fill.regions};assert.equal(JSON.stringify(bare),frozen);
  }
  const regions=data.bands.regions,pivot=regions[0]?.center||bare.pivot||[150,109],box=[Math.max(0,Math.min(200,pivot[0]-50)),Math.max(0,Math.min(148,pivot[1]-35)),100,70];
  for(const mode of modes){
   const {strokes,regions}=data[mode],mm=length(strokes);let points=0;
   // Original density ordering joins sub-1.2mm gaps after budgeting. Preserve
   // that ordinary reference; record its actual ink, while new fills obey strict caps.
   const cap=mode==='original'?100000:limit;
   assert(mm<=cap+.02,`Budget ${mode} ${seed} ${level}: ${mm}/${cap}`);
   for(const P of strokes){assert(P.length>1);points+=P.length;for(const[x,y]of P)assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218);}
   assert(points<250000);
   fs.writeFileSync(path.join(out,`${seed}-${level}-${mode}.svg`),svg(strokes));fs.writeFileSync(path.join(out,`${seed}-${level}-${mode}-close.svg`),svg(strokes,box));
   records.push({seed,level,mode,holdout:process.argv.includes('--holdouts'),inkMm:mm,points,strokes:strokes.length,baseHash:mode==='original'?null:baseHash,limitMm:cap,nominalInkMm:limit,closeWindow:box,regions});
  }
 }
}
fs.writeFileSync(path.join(out,process.argv.includes('--holdouts')?'checks-holdouts.json':'checks.json'),JSON.stringify(records,null,2)+'\n');
console.log(`${records.length} fill/seed/level cases checked: repeated physical fills, unchanged base curves, bed, strict new-fill caps and recorded original-reference ink.`);
