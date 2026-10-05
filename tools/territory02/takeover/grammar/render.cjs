const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {input,E}=require('../material/common.cjs'),{develop}=require('./rebuild.cjs'),{regrowTexture}=require('../texture/regrow.cjs');
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const fresh=process.argv.includes('--holdouts'),seeds=fresh?[739,797,853,911]:[5,13,18,24,47,82],root=path.join(__dirname,'evidence');fs.mkdirSync(root,{recursive:true});
const svg=(strokes,b=[0,0,300,218])=>`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${b.join(' ')}"><rect x="${b[0]}" y="${b[1]}" width="${b[2]}" height="${b[3]}" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round">${strokes.map(P=>`<path d="M${P.map(p=>p.map(x=>x.toFixed(3)).join(' ')).join(' L')}"/>`).join('')}</g></svg>`;
const records=[];
for(const seed of seeds){
 const I=input(seed),before=hash([I.bare,I.first,I.texture]),R=develop(I);
 assert.equal(hash(R),hash(develop(I)));assert.equal(hash([I.bare,I.first,I.texture]),before);
 assert(R.bare.courses.length>0);assert(!R.texture.layers.some(l=>['d-surprise','d-chord','d-wedge','d-ribbon','d-cont'].includes(l.kind)));
 const stripped=regrowTexture({...I.context,prm:{...I.context.prm,continue:0,slash:0,surprise:0,planes:0,cover:.32,ink:24}},I.bare,I.first,seed,'led');
 const data={prior:I.bare.strokes,reference:I.bare.strokes.concat(I.texture.strokes),stripped:I.bare.strokes.concat(stripped.strokes),bare:R.bare.strokes,led:R.strokes};
 // A common close frame selected from actual new course occupancy. Whole sheets
 // remain primary; this is not a best-case selection of the texture outcome.
 const bins=new Map();for(const P of R.bare.strokes)for(const p of E.resample(P,2)){const key=`${Math.floor(p[0]/30)},${Math.floor(p[1]/30)}`;bins.set(key,(bins.get(key)||0)+1);}
 const cell=[...bins].sort((a,b)=>b[1]-a[1])[0][0].split(',').map(Number),box=[Math.max(0,Math.min(200,cell[0]*30+15-50)),Math.max(0,Math.min(148,cell[1]*30+15-35)),100,70];
 for(const[mode,strokes]of Object.entries(data)){
  let inkMm=0,points=0;for(const P of strokes){assert(P.length>1);inkMm+=E.polyLen(P);points+=P.length;for(const[x,y]of P)assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218);}
  assert(points<250000&&inkMm<100000);for(const close of [false,true])fs.writeFileSync(path.join(root,`${seed}-${mode}${close?'-close':''}.svg`),svg(strokes,close?box:undefined));
  records.push({seed,mode,fresh,inkMm,points,strokes:strokes.length,geometryHash:hash(strokes),closeWindow:box,events:mode==='bare'?R.events:undefined,textureLayers:mode==='led'?R.info.textureLayers:undefined});
 }
 console.log(`Checked ${seed}: five comparisons; repeated output, input purity, bounds, budgets, no decorative layers in new texture.`);
}
fs.writeFileSync(path.join(root,`checks${fresh?'-heldout':''}.json`),JSON.stringify(records,null,2)+'\n');
