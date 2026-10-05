const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {E,regrowTexture}=require('./regrow.cjs'),baseline=require('../../experiments/baseline/territory-engine.js'),{rewriteChannels}=require('../rewrite.cjs');
const dir=path.join(__dirname,'evidence');fs.mkdirSync(dir,{recursive:true});
const recipe=require('../../full.json').prm,holdout=process.argv.includes('--holdouts'),seeds=holdout?[331,389,419,463]:[5,13,18,24,47,82],hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const svg=(strokes,box=[0,0,300,218])=>`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box.join(' ')}"><rect x="${box[0]}" y="${box[1]}" width="${box[2]}" height="${box[3]}" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round">${strokes.map(P=>`<path d="M${P.map(p=>p.map(x=>x.toFixed(3)).join(' ')).join(' L')}"/>`).join('')}</g></svg>`;
const records=[];
for(const seed of seeds){
 const sheet=E.randomSheet(seed),prm={...recipe,camps:Math.max(2,sheet.camps),debug:true},original=E.runTerritory(sheet.cores,prm,seed,'reversed');
 assert.equal(hash(original.lines),hash(baseline.runTerritory(sheet.cores,prm,seed,'reversed').lines));
 const source=E.runTerritory(sheet.cores,{...prm,density:0},seed,'reversed'),first=rewriteChannels(source.T.meanderDebug.chans,seed,1),bare=rewriteChannels(first.courses,seed,2),frozen=hash([source.lines,source.T.meanderDebug,bare]);
 const data={baseline:{strokes:original.lines.flatMap(l=>l.strokes),info:original.T.meanderInfo.density},bare:{strokes:bare.strokes,info:{}}};
 for(const mode of ['grown','led']){
  const a=regrowTexture(source.T.textureContext,bare,first,seed,mode),b=regrowTexture(source.T.textureContext,bare,first,seed,mode);assert.equal(hash(a),hash(b));assert.equal(hash([source.lines,source.T.meanderDebug,bare]),frozen);
  data[mode]={strokes:bare.strokes.concat(a.strokes),info:a.info,cropStrokes:a.layers.find(l=>l.kind==='d-grow')?.strokes||[],layers:a.layers.map(l=>({kind:l.kind,strokes:l.strokes.length,inkMm:l.strokes.reduce((n,P)=>n+E.polyLen(P),0)})),textureHash:hash(a.strokes)};
 }
 // Frame physical grown ink rather than a pressure site that may contain no
 // texture. This matched detail can still miss important bare-line encounters.
 const tiles=new Map();for(const P of data.grown.cropStrokes)for(let i=1;i<P.length;i++){
  const p=P[i],key=`${Math.floor(p[0]/20)},${Math.floor(p[1]/20)}`;tiles.set(key,(tiles.get(key)||0)+Math.hypot(p[0]-P[i-1][0],p[1]-P[i-1][1]));
 }
 const tile=[...tiles].sort((a,b)=>b[1]-a[1])[0],pivot=tile?tile[0].split(',').map(x=>Number(x)*20+10):(bare.pivot||[150,109]),box=[Math.max(0,Math.min(200,pivot[0]-50)),Math.max(0,Math.min(148,pivot[1]-35)),100,70];
 for(const [mode,d]of Object.entries(data)){
  let points=0,mm=0;for(const P of d.strokes){assert(P.length>1);points+=P.length;mm+=E.polyLen(P);for(const[x,y]of P)assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218);}
  assert(mm<100000&&points<250000,`Physical limits ${mode}/${seed}: ${mm}mm ${points}points`);
  fs.writeFileSync(path.join(dir,`${seed}-${mode}.svg`),svg(d.strokes));fs.writeFileSync(path.join(dir,`${seed}-${mode}-close.svg`),svg(d.strokes,box));
  records.push({seed,mode,holdout,nominalInkMm:60000,inkMm:mm,points,strokes:d.strokes.length,closeWindow:box,baseHash:mode==='baseline'?null:hash(bare.strokes),textureHash:d.textureHash||null,layers:d.layers||[],info:d.info});
 }
 console.log(`Checked seed ${seed}: original full baseline parity, repeated regrowth, unchanged base, physical bounds.`);
}
fs.writeFileSync(path.join(dir,holdout?'checks-holdouts.json':'checks.json'),JSON.stringify(records,null,2)+'\n');
console.log(`${records.length} texture cases checked at the original nominal 60m recipe.`);
