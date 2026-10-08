const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto'),{input,E,measure,at}=require('./common.cjs');
const out=path.join(__dirname,'evidence');fs.mkdirSync(out,{recursive:true});
const args=process.argv.slice(2),arg=k=>args.find(a=>a.startsWith(k+'='))?.slice(k.length+1),heldout=args.includes('--holdouts'),seeds=arg('--seeds')?.split(',').map(Number)||(heldout?[521,587,631,683]:[5,13,18,24,47,82]),modes=arg('--mode')?[arg('--mode')]:['opening','pressure','unravel'];
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex'),svg=(strokes,box=[0,0,300,218])=>`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box.join(' ')}"><rect x="${box[0]}" y="${box[1]}" width="${box[2]}" height="${box[3]}" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round">${strokes.map(P=>`<path d="M${P.map(p=>p.map(x=>x.toFixed(3)).join(' ')).join(' L')}"/>`).join('')}</g></svg>`;
const records=[];
for(const seed of seeds){
 const I=input(seed),before=hash([I.bare,I.first,I.texture]),data={bare:{strokes:I.bare.strokes},led:{strokes:I.bare.strokes.concat(I.texture.strokes)}};
 for(const mode of modes){const {develop}=require('./'+mode+'.cjs');data[mode]=develop(I);assert.equal(hash([I.bare,I.first,I.texture]),before,`${mode} mutates inputs`);if(!args.includes('--quick'))assert.equal(hash(data[mode]),hash(develop(I)),`${mode} repeatability`);}
 // Same detail for every variant: actual curve encounter from the fixed input.
 const pivot=I.bare.pivot||[150,109],box=[Math.max(0,Math.min(200,pivot[0]-50)),Math.max(0,Math.min(148,pivot[1]-35)),100,70];
 for(const[mode,result]of Object.entries(data)){
  let points=0,inkMm=0;for(const P of result.strokes){assert(P.length>1);points+=P.length;inkMm+=E.polyLen(P);for(const[x,y]of P)assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218,`${mode}/${seed} invalid point`);}
  assert(points<250000&&inkMm<100000,`${mode}/${seed}: ${points}points ${inkMm}mm`);
  fs.writeFileSync(path.join(out,`${seed}-${mode}.svg`),svg(result.strokes));fs.writeFileSync(path.join(out,`${seed}-${mode}-close.svg`),svg(result.strokes,box));
  for(const stage of result.stages||[]){
   assert(/^[a-z-]+$/.test(stage.key));for(const P of stage.strokes){assert(P.length>1);for(const[x,y]of P)assert(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=300&&y>=0&&y<=218);}
   fs.writeFileSync(path.join(out,`${seed}-${mode}-${stage.key}.svg`),svg(stage.strokes));
  }
  const event=result.events?.[0];let eventCenter=event?.at||event?.root;
  if(event?.kind==='opening'){const P=I.bare.courses.find(c=>c.id===event.course).present;eventCenter=at(P,measure(P),(event.startMm+event.endMm)/2);}
  if(eventCenter){const focus=[Math.max(0,Math.min(200,eventCenter[0]-50)),Math.max(0,Math.min(148,eventCenter[1]-35)),100,70];
   fs.writeFileSync(path.join(out,`${seed}-${mode}-event.svg`),svg(result.strokes,focus));
   fs.writeFileSync(path.join(out,`${seed}-${mode}-event-before.svg`),svg(data[mode==='opening'?'bare':'led'].strokes,focus));
   result.info={...result.info,eventWindow:focus,eventSelection:'first recorded event, not best-looking event'};
  }
  records.push({seed,mode,heldout,inkMm,points,strokes:result.strokes.length,geometryHash:hash(result.strokes),inputHash:before,closeWindow:box,events:result.events||[],info:result.info||{}});
 }
 console.log(`Checked ${seed}: ${Object.keys(data).join(', ')}; input purity, ${args.includes('--quick')?'repeat check skipped':'repeatability'}, bounds and physical limits.`);
}
const name=arg('--mode')?`checks-${arg('--mode')}`:(heldout?'checks-heldout':'checks');fs.writeFileSync(path.join(out,name+'.json'),JSON.stringify(records,null,2)+'\n');
