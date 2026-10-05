// Contact between a smooth excursion and the actual surviving rough material.
const {E,add,sub,mul,dot,dist,unit,clamp,measure,nearest,clip}=require('./common.cjs');
const clone=P=>P.map(p=>p.slice());
const falloff=u=>u>=1?0:(1-u*u)**2;

function materialField(strokes,excluded,bareCourses){
 const cells=new Map(),size=2.5,indices=[];
 const guides=bareCourses.map(c=>E.resample(c.present,2));
 for(let k=0;k<strokes.length;k++){
  if(excluded.has(k))continue;
  const P=strokes[k],length=E.polyLen(P);
  // Final clipping can change the base stroke order. This is a conservative
  // grain inference, not a claim of literal donor-layer provenance: long
  // course-like runs and short strokes lying on a bare guide are left alone.
  if(length>70)continue;
  let guideDistance=0;
  for(let j=0;j<5;j++){
   const p=P[Math.floor((P.length-1)*j/4)];let d=Infinity;
   for(const guide of guides)d=Math.min(d,nearest(guide,p).distance);
   guideDistance+=d/5;
  }
  if(length>12&&guideDistance<.7)continue;
  indices.push(k);
  const Q=E.resample(strokes[k],1);
  for(let i=1;i<Q.length;i++){
   const p=mul(add(Q[i-1],Q[i]),.5),x=Math.floor(p[0]/size),y=Math.floor(p[1]/size),key=`${x},${y}`;
   const c=cells.get(key)||{p:[(x+.5)*size,(y+.5)*size],ink:0};
   c.ink+=dist(Q[i-1],Q[i]);cells.set(key,c);
  }
 }
 function mass(p,r=7){
  const x=Math.floor(p[0]/size),y=Math.floor(p[1]/size),reach=Math.ceil(r/size);let ink=0,moment=[0,0];
  for(let a=x-reach;a<=x+reach;a++)for(let b=y-reach;b<=y+reach;b++){
   const c=cells.get(`${a},${b}`);if(!c)continue;const d=dist(c.p,p);if(d>=r)continue;
   const w=c.ink*(1-d/r)**2;ink+=w;moment=add(moment,mul(c.p,w));
  }
  return {ink,center:ink?mul(moment,1/ink):p.slice()};
 }
 return {indices,mass};
}

function safeScale(P,D){
 let scale=1;
 for(let j=0;j<P.length;j++)for(let axis=0;axis<2;axis++){
  const v=D[j][axis];
  if(v>0)scale=Math.min(scale,((axis?216:298)-P[j][axis])/v);
  if(v<0)scale=Math.min(scale,((axis?2:2)-P[j][axis])/v);
 }
 return clamp(scale,0,1);
}

function develop(prepared){
 const {seed,baseName,base,smooth,I}=prepared,excluded=new Set(smooth.map(s=>s.sourceIndex));
 const field=materialField(base.strokes,excluded,I.bare.courses),sites=[];
 const curves=smooth.map((s,index)=>({...s,index,arc:measure(s.P)}));
 const candidates=[];
 for(const c of curves)for(let j=8;j<c.P.length-8;j+=8){
  const arc=c.arc[j],L=c.arc.at(-1);if(arc<22||L-arc<22)continue;
  const p=c.P[j],t=unit(sub(c.P[j+3],c.P[j-3])),n=[-t[1],t[0]],body=field.mass(p);
  // The source stroke is absent from the occupancy field: an encounter needs
  // other real material, rather than the curve finding its own former place.
  if(body.ink<7)continue;
  const left=field.mass(add(p,mul(n,4))).ink,right=field.mass(sub(p,mul(n,4))).ink;
  const asymmetry=Math.abs(left-right)/(left+right+1);
  const offset=dot(sub(body.center,p),n);
  const side=left===right?(offset>=0?-1:1):(left>right?-1:1);
  candidates.push({curve:c.index,index:j,arc,p:p.slice(),t,n:mul(n,side),body,left,right,score:body.ink*(.5+asymmetry)});
 }
 for(const candidate of candidates.sort((a,b)=>b.score-a.score)){
  if(sites.some(s=>s.curve===candidate.curve||dist(s.p,candidate.p)<29))continue;
  sites.push({...candidate,reach:20+Math.min(10,candidate.body.ink*.14),amount:6+Math.min(8,candidate.body.ink*.12)});
  if(sites.length===2)break;
 }
 for(const c of curves){
  const site=sites.find(s=>s.curve===c.index);
  if(!site){c.after=clone(c.P);continue;}
  const D=c.P.map((p,j)=>mul(site.n,site.amount*falloff(Math.abs(c.arc[j]-site.arc)/site.reach)));
  site.boundScale=safeScale(c.P,D);c.after=c.P.map((p,j)=>add(p,mul(D[j],site.boundScale)));
  site.after=c.after[site.index];site.motion=sub(site.after,site.p);
  // A short measured corridor, retaining the actual curved contact shape.
  site.contact=c.P.filter((p,j)=>Math.abs(c.arc[j]-site.arc)<=site.reach*.72);
  site.contactArc=measure(site.contact);
 }
 const materialSet=new Set(field.indices),moved=new Map();let affectedOriginalPoints=0,tornStrokes=0,transferredFragments=0;
 const fragmentRecords=[];
 for(const k of field.indices){
  const P=base.strokes[k];let pieces=[clone(P)],changed=false;
  for(const site of sites){
   const radius=8.5,low=[site.p[0]-site.reach-radius,site.p[1]-site.reach-radius],high=[site.p[0]+site.reach+radius,site.p[1]+site.reach+radius];
   const next=[];
   for(const Q of pieces){
    if(!Q.some(p=>p[0]>=low[0]&&p[0]<=high[0]&&p[1]>=low[1]&&p[1]<=high[1])){next.push(Q);continue;}
    const motion=[];let touched=0,best=null;
    for(let j=0;j<Q.length;j++){
     const p=Q[j],h=nearest(site.contact,p),arc=site.contactArc[h.index]+dist(site.contact[h.index],h.point),u=arc/site.contactArc.at(-1);
     const local=falloff(h.distance/radius)*Math.sin(Math.PI*u)**2;
     // Grain on the dense side yields back into its own body; grain crossing
     // the other side follows the curve weakly. Original internal bends stay.
     const signed=dot(sub(p,h.point),site.n),direction=signed<0?mul(site.n,-1):site.n;
     const strength=(signed<0?3.8:2.1)*local;
     const delta=add(mul(direction,strength),mul(site.t,(u-.5)*local*2));
     motion.push(delta);if(Math.hypot(...delta)>.12)touched++;
     // A tear can occur only at a real grain/course crossing in this window.
     if(j>1&&j<Q.length-2&&h.distance<.48&&local>.35&&(!best||local>best.local))best={index:j,local};
    }
    if(!touched){next.push(Q);continue;}
    const scale=safeScale(Q,motion),warped=Q.map((p,j)=>add(p,mul(motion[j],scale)));
    affectedOriginalPoints+=touched;changed=true;
    // At most four severed runs across the sheet. Both halves are emitted,
    // and a short loose half moves rigidly instead of becoming dotted hatch.
    if(best&&tornStrokes<4&&E.polyLen(Q)>3){
     const a=warped.slice(0,best.index+1),b=warped.slice(best.index),small=E.polyLen(a)<E.polyLen(b)?a:b;
     const pull=mul(site.n,dot(sub(Q[best.index],site.p),site.n)<0?-1.2:1.2);
     const shifts=small.map(()=>pull),limit=safeScale(small,shifts),loose=small.map(p=>add(p,mul(pull,limit)));
     next.push(small===a?loose:a,small===b?loose:b);tornStrokes++;transferredFragments++;
     fragmentRecords.push({sourceStroke:k,localFragmentVertex:best.index,contact:site.p,translation:mul(pull,limit),sourceFragmentMm:E.polyLen(small)});
    }else next.push(warped);
   }
   pieces=next;
  }
  if(changed)moved.set(k,pieces);
 }
 function drawing(respond){
  const out=[];
  for(let k=0;k<base.strokes.length;k++){
   const c=curves.find(s=>s.sourceIndex===k);
   if(c){out.push(clone(c.source.slice(0,c.start)).concat(clone(respond?c.after:c.P),clone(c.source.slice(c.end+1))));continue;}
   if(respond&&moved.has(k))out.push(...moved.get(k));else out.push(clone(base.strokes[k]));
  }
  return clip(out,.05);
 }
 const strokes=drawing(true),events=sites.map(s=>({kind:'mutual-material-contact',smoothSourceStroke:curves[s.curve].sourceIndex,at:s.p,after:s.after,weightedInkMm:s.body.ink,materialCenter:s.body.center,sideInkMm:[s.left,s.right],reachMm:s.reach,curveDisplacementMm:dist(s.p,s.after),boundaryScale:s.boundScale}));
 return {strokes,events,info:{mechanism:'measured existing material indents the smooth excursion; nearby original grain yields and a few real crossings tear',seed,baseName,contacts:sites.length,affectedMaterialStrokes:moved.size,materialStrokes:materialSet.size,affectedOriginalPoints,tornStrokes,transferredFragments,fragmentRecords,materialRegrown:false,materialClassification:'inferred short grain runs, excluding exact smooth source indices and strokes closely matching original bare guides',limitation:'long material is left intact; short displaced bare courses may enter the inferred grain set; contact may be absent when excursions miss dense material; no aesthetic acceptance inferred'},stages:[{key:'smooth-before-contact',strokes:drawing(false)},{key:'mutual-contact',strokes}]};
}
module.exports={develop};
