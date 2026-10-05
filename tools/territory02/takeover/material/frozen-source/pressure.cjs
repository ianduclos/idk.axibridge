// Measured material resistance, confined to this experimental takeover study.
const {E,add,sub,mul,dot,dist,unit,clamp,measure,nearest,clip}=require('./common.cjs');
const CELL=2.5,REACH=8;
function occupancy(strokes){
 const grid=new Map();
 for(const P of strokes){const Q=E.resample(P,1.25);for(let i=1;i<Q.length;i++){
  const p=mul(add(Q[i-1],Q[i]),.5),key=`${Math.floor(p[0]/CELL)},${Math.floor(p[1]/CELL)}`;
  const cell=grid.get(key)||{p:[(Math.floor(p[0]/CELL)+.5)*CELL,(Math.floor(p[1]/CELL)+.5)*CELL],ink:0};
  cell.ink+=dist(Q[i-1],Q[i]);grid.set(key,cell);
 }}
 function mass(p,r=REACH){
  const gx=Math.floor(p[0]/CELL),gy=Math.floor(p[1]/CELL),n=Math.ceil(r/CELL);let ink=0,moment=[0,0],peak=0;
  for(let x=gx-n;x<=gx+n;x++)for(let y=gy-n;y<=gy+n;y++){
   const c=grid.get(`${x},${y}`);if(!c)continue;const d=dist(p,c.p);if(d>=r)continue;
   const w=(1-d/r)**2,z=c.ink*w;ink+=z;moment=add(moment,mul(c.p,z));peak=Math.max(peak,c.ink);
  }
  return{ink,center:ink?mul(moment,1/ink):p.slice(),peak};
 }
 return {mass,cells:grid.size};
}
function develop({seed,bare,texture}){
 const material=occupancy(texture.strokes),courses=bare.courses.map(c=>({...c,P:E.resample(c.present,1.2)}));
 const candidates=[];
 for(let k=0;k<courses.length;k++){
  const c=courses[k],s=measure(c.P);c.arc=s;
  for(let i=4;i<c.P.length-4;i+=3){
   if(s[i]<7||s.at(-1)-s[i]<7)continue;
   const p=c.P[i],t=unit(sub(c.P[i+2],c.P[i-2])),n=[-t[1],t[0]],body=material.mass(p);
   const left=material.mass(add(p,mul(n,5))).ink,right=material.mass(sub(p,mul(n,5))).ink;
   const contrast=Math.abs(left-right)/(left+right+1);
   // Resistance chooses the escape side. A balanced body has no arbitrary push.
   if(contrast<.12)continue;
   const side=left>right?-1:1,normal=mul(n,side),score=body.ink*(.35+.65*contrast);
   candidates.push({course:k,index:i,p:p.slice(),s:s[i],normal,tangent:t,body,left,right,contrast,score});
  }
 }
 const densities=candidates.map(c=>c.body.ink).sort((a,b)=>a-b),threshold=Math.max(12,densities[Math.floor(densities.length*.7)]||Infinity);
 const sites=[];
 for(const c of candidates.sort((a,b)=>b.score-a.score)){
  if(c.body.ink<threshold||sites.some(q=>dist(q.p,c.p)<22||(q.course===c.course&&Math.abs(q.s-c.s)<42)))continue;
  sites.push(c);if(sites.length>=10)break;
 }
 const peak=Math.max(threshold,...sites.map(s=>s.body.ink)),events=[];
 for(const site of sites){
  const c=courses[site.course],strength=17+11*Math.sqrt(site.body.ink/peak);
  // The material's measured off-axis centroid drags the encounter unequally.
  const along=clamp(dot(sub(site.p,site.body.center),site.tangent),-3.5,3.5);
  site.demand=add(mul(site.normal,strength),mul(site.tangent,along*1.8));
  const before=material.mass(c.P[Math.max(0,site.index-15)]).ink,after=material.mass(c.P[Math.min(c.P.length-1,site.index+15)]).ink;
  site.before=18+12*before/(site.body.ink+before+1);site.after=18+12*after/(site.body.ink+after+1);
  events.push({kind:'material-pressure',courseId:c.id,sourceIds:c.sourceIds,at:site.p,materialCenter:site.body.center,weightedInkMm:site.body.ink,sideInkMm:[site.left,site.right],demand:site.demand,arclengthReach:[site.before,site.after]});
 }
 for(let k=0;k<courses.length;k++){
  const c=courses[k],local=sites.filter(s=>s.course===k),forcing=c.P.map((p,i)=>{
   let target=[0,0],weight=0;
   for(const site of local){const d=c.arc[i]-site.s,r=d<0?site.before:site.after,u=Math.abs(d)/r;if(u>=1)continue;
    const w=(1-u)**2*(1+2*u);target=add(target,mul(site.demand,w));weight+=w;
   }
   return{target:weight?mul(target,1/Math.max(1,weight)):target,weight};
  });
  let D=c.P.map(()=>[0,0]);
  // Diffuse displacement, not positions: quiet original passages retain their bends.
  // Dense shoulders resist bending less than long clear bridges, concentrating turn.
  const stiffness=c.P.map(p=>1.1+4.5/(1+material.mass(p,5).ink/12));
  for(let iteration=0;iteration<44;iteration++)D=D.map((d,i)=>{
   if(i===0||i===D.length-1)return[0,0];
   const f=forcing[i],spring=.25+f.weight*3.8,bend=stiffness[i];
   const value=mul(add(mul(f.target,spring),mul(add(D[i-1],D[i+1]),bend)),1/(spring+2*bend));
   const edge=clamp(Math.min(c.arc[i],c.arc.at(-1)-c.arc[i])/9,0,1);return mul(value,edge);
  });
  c.D=D;c.after=c.P.map((p,i)=>add(p,D[i]));
 }
 function displacement(c,p){const hit=nearest(c.P,p),i=hit.index,t=hit.t||0;return add(mul(c.D[i],1-t),mul(c.D[i+1]||c.D[i],t));}
 function owner(P){
  let best=courses[0],score=Infinity;
  for(const c of courses){let sum=0;for(let j=0;j<7;j++)sum+=nearest(c.P,P[Math.floor((P.length-1)*j/6)]).distance;
   if(sum<score){score=sum;best=c;}
  }return best;
 }
 const movedBare=bare.strokes.map(P=>{const c=owner(P);return E.resample(P,.65).map(p=>add(p,displacement(c,p)));});
 // A small spatial index transfers course motion only to physically nearby material.
 const courseGrid=new Map(),spacing=8;
 for(const c of courses)for(let i=0;i<c.P.length;i++){
  const p=c.P[i],key=`${Math.floor(p[0]/spacing)},${Math.floor(p[1]/spacing)}`,bucket=courseGrid.get(key)||[];
  bucket.push({p,d:c.D[i],id:c.id});courseGrid.set(key,bucket);
 }
 let yieldedPoints=0;
 const movedTexture=texture.strokes.map(P=>P.map(p=>{
  const gx=Math.floor(p[0]/spacing),gy=Math.floor(p[1]/spacing),closest=new Map();let minimum=15;
  for(let x=gx-2;x<=gx+2;x++)for(let y=gy-2;y<=gy+2;y++)for(const q of courseGrid.get(`${x},${y}`)||[]){
   const d=dist(p,q.p);if(d>=15)continue;minimum=Math.min(minimum,d);
   if(!closest.has(q.id)||closest.get(q.id).distance>d)closest.set(q.id,{...q,distance:d});
  }
  let motion=[0,0],weight=0;
  for(const q of closest.values()){const w=(1-q.distance/15)**2/(2+q.distance)**2;motion=add(motion,mul(q.d,w));weight+=w;}
  if(!weight)return p.slice();motion=mul(motion,1/weight);if(Math.hypot(...motion)<.02)return p.slice();
  // Dense bodies stay stubborn; thin exits carry more motion. All variation is ink-led.
  const resistance=material.mass(p,5).ink,yielding=(.12+.7/(1+resistance/14))*(1-minimum/15)**2;
  const q=add(p,mul(motion,yielding));if(dist(p,q)>.1)yieldedPoints++;return q;
 }));
 const before=clip(bare.strokes.concat(texture.strokes),.05),fixed=clip(movedBare.concat(texture.strokes),.05),final=clip(movedBare.concat(movedTexture),.05);
 for(const event of events){const c=courses.find(c=>c.id===event.courseId),p=event.at;event.after=add(p,displacement(c,p));event.displacementMm=dist(p,event.after);}
 return {strokes:final,events,info:{mechanism:'measured texture ink resists courses; sparse exits yield',seed,occupiedCells:material.cells,densityThresholdInkMm:threshold,encounters:sites.length,yieldedTexturePoints:yieldedPoints,regrowth:false},stages:[{key:'occupied-material',strokes:before},{key:'curves-displaced',strokes:fixed},{key:'filaments-yield',strokes:final}]};
}
module.exports={develop};
