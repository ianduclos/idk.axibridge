const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {generate}=require('./generate.cjs');
const args=process.argv.slice(2),fresh=args.includes('--holdouts'),seeds=fresh?[1151,1213,1277]:[13,24,47],root=path.join(__dirname,'evidence'),closeBox=[100,74,100,70];
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const colors=fs.readFileSync(path.join(__dirname,'../../../../axibridge/static/css/flexoki.css'),'utf8'),color=n=>colors.match(new RegExp(`--flexoki-${n}:\\s*(#[A-Fa-f0-9]+)`))[1];
fs.mkdirSync(root,{recursive:true});
const svg=(strokes,b=[0,0,300,218])=>`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${b.join(' ')}"><rect x="${b[0]}" y="${b[1]}" width="${b[2]}" height="${b[3]}" fill="${color('paper')}"/><g fill="none" stroke="${color('black')}" stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round">${strokes.map(P=>`<path d="M${P.map(p=>p.map(x=>x.toFixed(3)).join(' ')).join(' L')}"/>`).join('')}</g></svg>`;
function inspect(strokes,tag){
 let points=0,inkMm=0;assert(Array.isArray(strokes),tag);
 for(const P of strokes){assert(P.length>1,`${tag}: short stroke`);points+=P.length;
  for(let i=0;i<P.length;i++){assert(P[i].length===2,`${tag}: coordinate arity`);const[x,y]=P[i];assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218,`${tag}: invalid coordinates ${x},${y}`);if(i)inkMm+=Math.hypot(x-P[i-1][0],y-P[i-1][1]);}
 }
 assert(points<=250000&&inkMm<=100000,`${tag}: geometry budget`);return {points,inkMm,strokes:strokes.length,geometryHash:hash(strokes)};
}
function write(prefix,strokes){for(const detail of [false,true])fs.writeFileSync(path.join(root,`${prefix}${detail?'-close':''}.svg`),svg(strokes,detail?closeBox:undefined));}
const records=[];
for(const seed of seeds){
 if(fresh||!fs.existsSync(path.join(__dirname,`../coexist/evidence/${seed}-unravel-independent.svg`))){
  const {prepare}=require('../coexist/common.cjs'),{develop}=require('../coexist/independent.cjs'),I=prepare(seed,'unravel'),before=hash(I),old=develop(I);
  assert.equal(hash(I),before,'Earlier reference mutated its input');if(!args.includes('--quick'))assert.equal(hash(old),hash(develop(I)),'Earlier reference repeatability');
  records.push({seed,mode:'earlier',fresh,...inspect(old.strokes,`${seed}/earlier`),closeWindow:closeBox,info:old.info});write(`${seed}-earlier`,old.strokes);
 }else{
  const source=path.join(__dirname,`../coexist/evidence/${seed}-unravel-independent.svg`),text=fs.readFileSync(source,'utf8');
  const strokes=Array.from(text.matchAll(/<path d="([^"]+)"/g),m=>{const values=m[1].match(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/gi).map(Number);assert(values.length%2===0,'Earlier reference coordinate arity');return Array.from({length:values.length/2},(_,i)=>values.slice(i*2,i*2+2));});
  fs.copyFileSync(source,path.join(root,`${seed}-earlier.svg`));
  fs.writeFileSync(path.join(root,`${seed}-earlier-close.svg`),text.replace(/viewBox="[^"]+"/,'viewBox="100 74 100 70"').replace(/<rect\b[^>]*\/>/,`<rect x="100" y="74" width="100" height="70" fill="${color('paper')}"/>`));
  records.push({seed,mode:'earlier',fresh,...inspect(strokes,`${seed}/earlier`),source:'../coexist/evidence/'+path.basename(source),sourceHash:crypto.createHash('sha256').update(text).digest('hex'),closeWindow:closeBox,copiedUnchanged:true});
 }
 for(const mode of ['open','body']){
  const result=generate(seed,mode);if(!args.includes('--quick'))assert.equal(hash(result),hash(generate(seed,mode)),`${seed}/${mode}: repeatability`);
  const stats=inspect(result.strokes,`${seed}/${mode}`),lineStats=inspect(result.lines,`${seed}/${mode}/lines`),materialStats=inspect(result.material,`${seed}/${mode}/material`);
  assert(result.lines.length>0,`${seed}/${mode}: empty line drawing`);
  write(`${seed}-${mode}`,result.strokes);write(`${seed}-${mode}-lines`,result.lines);
  records.push({seed,mode,fresh,...stats,lineStats,materialStats,closeWindow:closeBox,info:result.info||{}});
 }
 console.log(`${seed}: earlier reference, open and body checked${args.includes('--quick')?' (repeatability skipped)':''}.`);
}
fs.writeFileSync(path.join(root,`checks${fresh?'-heldout':''}.json`),JSON.stringify({fresh,seeds,repeatability:!args.includes('--quick'),records},null,2)+'\n');
