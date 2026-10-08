const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {prepare,E}=require('./common.cjs'),hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const args=process.argv.slice(2),fresh=args.includes('--holdouts'),seeds=fresh?[1009,1061]:[13,24],bases=['opening','pressure','unravel'],only=args.find(x=>x.startsWith('--only='))?.split('=')[1],modes=only?[only]:['continuity','interference','independent'];
const root=path.join(__dirname,'evidence');fs.mkdirSync(root,{recursive:true});
const svg=(strokes,b=[0,0,300,218])=>`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${b.join(' ')}"><rect x="${b[0]}" y="${b[1]}" width="${b[2]}" height="${b[3]}" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round">${strokes.map(P=>`<path d="M${P.map(p=>p.map(x=>x.toFixed(3)).join(' ')).join(' L')}"/>`).join('')}</g></svg>`;
const records=[];
for(const seed of seeds)for(const base of bases){
 const I=prepare(seed,base),before=hash([I.base,I.smooth,I.I.bare,I.I.texture]),data={rough:{strokes:I.base.strokes},smooth:{strokes:I.smooth.map(s=>s.P)}};
 assert(I.smooth.length>0,`No smooth passage ${seed}/${base}`);
 for(const mode of modes){const {develop}=require('./'+mode+'.cjs');data[mode]=develop(I);assert.equal(hash([I.base,I.smooth,I.I.bare,I.I.texture]),before,`${mode} input mutation`);if(!args.includes('--quick'))assert.equal(hash(data[mode]),hash(develop(I)),`${mode} repeatability`);}
 const focus=I.smooth[0].P[Math.floor(I.smooth[0].P.length/2)],box=[Math.max(0,Math.min(200,focus[0]-50)),Math.max(0,Math.min(148,focus[1]-35)),100,70];
 for(const[mode,result]of Object.entries(data)){
  let points=0,inkMm=0;for(const P of result.strokes){assert(P.length>1);points+=P.length;inkMm+=E.polyLen(P);for(const[x,y]of P)assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218,`${seed}/${base}/${mode}`);}
  assert(points<250000&&inkMm<100000);for(const close of [false,true])fs.writeFileSync(path.join(root,`${seed}-${base}-${mode}${close?'-close':''}.svg`),svg(result.strokes,close?box:undefined));
  for(const s of result.stages||[]){assert(/^[a-z-]+$/.test(s.key));for(const P of s.strokes){assert(P.length>1);for(const[x,y]of P)assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218);}fs.writeFileSync(path.join(root,`${seed}-${base}-${mode}-${s.key}.svg`),svg(s.strokes));}
  if(mode==='independent')assert.equal(hash(result.strokes.slice(0,I.base.strokes.length)),hash(I.base.strokes),'Independent coexistence changes rough drawing');
  records.push({seed,base,mode,fresh,points,inkMm,strokes:result.strokes.length,geometryHash:hash(result.strokes),inputHash:before,closeWindow:box,events:result.events||[],info:result.info||{}});
 }
 console.log(`${seed}/${base}: ${Object.keys(data).join(', ')} checked.`);
}
fs.writeFileSync(path.join(root,`checks${only?'-'+only:''}${fresh?'-heldout':''}.json`),JSON.stringify(records,null,2)+'\n');
