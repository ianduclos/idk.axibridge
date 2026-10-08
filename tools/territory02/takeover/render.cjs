// One frozen input population, then two stages of the exploratory rewrite.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const E=require('../experiments/baseline/territory-engine.js'),{rewriteChannels}=require('./rewrite.cjs');
const out=path.join(__dirname,'evidence');fs.mkdirSync(out,{recursive:true});
const recipe=JSON.parse(fs.readFileSync(path.join(__dirname,'../sparse.json'))).prm;
const seeds=process.argv.includes('--holdouts')?[107,173,227,281]:[5,13,18,24,47,82];
const stroke=P=>`<path d="M${P.map(p=>p.map(x=>x.toFixed(3)).join(' ')).join(' L')}"/>`;
const svg=(strokes,box=[0,0,300,218])=>`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box.join(' ')}"><rect x="${box[0]}" y="${box[1]}" width="${box[2]}" height="${box[3]}" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round">${strokes.map(stroke).join('')}</g></svg>`;
const cells=[[],[],[]],records=[];
for(const seed of seeds){
 const sheet=E.randomSheet(seed),before=JSON.stringify(sheet.cores),params={...recipe,camps:Math.max(2,sheet.camps),debug:true,density:0};
 const source=E.runTerritory(sheet.cores,params,seed,'reversed');assert.equal(JSON.stringify(sheet.cores),before);
 const channels=source.T.meanderDebug.chans;
 const original=source.lines.flatMap(l=>l.strokes),first=rewriteChannels(channels,seed,1);
 const data=[{strokes:original,edits:[]},first,rewriteChannels(first.courses,seed,2)];
 assert.deepEqual(data[1],rewriteChannels(channels,seed,1));assert.deepEqual(data[2],rewriteChannels(first.courses,seed,2));
 const record={seed,holdout:process.argv.includes('--holdouts'),stages:[]};
 for(let stage=0;stage<3;stage++){
  const item=data[stage];let mm=0,points=0;
  for(const P of item.strokes){assert(P.length>1);points+=P.length;for(let i=0;i<P.length;i++){const[x,y]=P[i];assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218);if(i)mm+=Math.hypot(x-P[i-1][0],y-P[i-1][1]);}}
  assert(mm<=100000&&points<=250000);
  const picture=svg(item.strokes);fs.writeFileSync(path.join(out,`${seed}-${stage}.svg`),picture);
  cells[stage].push(`<figure>${picture}<figcaption>${seed} · stage ${stage}</figcaption></figure>`);
  const pivot=data[2].pivot||[150,109],box=[Math.max(0,Math.min(200,pivot[0]-50)),Math.max(0,Math.min(148,pivot[1]-35)),100,70];
  fs.writeFileSync(path.join(out,`${seed}-${stage}-close.svg`),svg(item.strokes,box));
  record.stages.push({stage,points,strokes:item.strokes.length,inkMm:Math.round(mm),edits:item.edits,closeWindow:box});
 }
 records.push(record);
}
const suffix=process.argv.includes('--holdouts')?'-holdouts':'';
for(let stage=0;stage<3;stage++)fs.writeFileSync(path.join(out,`stage-${stage}${suffix}.html`),`<!doctype html><meta charset="utf-8"><title>Takeover · ${stage}</title><style>body{background:#fff;font:13px system-ui;margin:18px;color:#100F0F}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}figure{margin:0}svg{width:100%;display:block;border:1px solid #CECDC3}figcaption{margin:5px 0}h1{font-size:16px}</style><h1>Takeover · stage ${stage}${suffix}</h1><div class="grid">${cells[stage].join('')}</div>`);
fs.writeFileSync(path.join(out,`checks${suffix}.json`),JSON.stringify(records,null,2)+'\n');
console.log(`${records.length*3} stage/seed cases rendered and checked: repeatability, unchanged inputs, finite geometry, bed and budgets.`);
