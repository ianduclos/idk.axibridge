const {E,rng,measure,nearest,add,sub,mul,dot,unit,clamp,clip}=require('./common.cjs');

// Each opening is a local change in the material's relation to its course.
// The material is the actual d-grow strokes, including their gaps and returns.
function frame(C,x){
 const s=C.s,P=C.P;x=clamp(x,0,C.length);let lo=1,hi=s.length-1;
 while(lo<hi){const m=(lo+hi)>>1;if(s[m]<x)lo=m+1;else hi=m;}
 const i=lo,t=(x-s[i-1])/(s[i]-s[i-1]||1),q=add(P[i-1],mul(sub(P[i],P[i-1]),t));
 const tangent=unit(sub(P[Math.min(P.length-1,i+1)],P[Math.max(0,i-2)]));
 return {q,tangent,normal:[-tangent[1],tangent[0]]};
}
function profile(u,K){
 if(u<=0||u>=1)return 0;
 let i=1;while(i<K.length-1&&K[i][0]<u)i++;
 const [a,v]=K[i-1],[b,w]=K[i],t=(u-a)/(b-a);
 return v+(w-v)*t;
}
function develop({seed,bare,texture}){
 const R=rng(seed^0x6f70656e),events=[],material=[],bareStrokes=bare.strokes.map(P=>P.map(p=>p.slice()));
 const grow=texture.layers?.find(l=>l.kind==='d-grow')?.strokes||[];
 const courses=bare.courses.filter(c=>E.polyLen(c.present)>47)
  .sort((a,b)=>(a.cls==='trunk'?-1000:0)-E.polyLen(a.present)-(b.cls==='trunk'?-1000:0)+E.polyLen(b.present));
 // Four courses at most: the rest of the sheet retains the approved bare line.
 for(const [body,c] of courses.slice(0,4).entries()){
  const P=E.resample(c.present,.75),s=measure(P),length=s.at(-1),C={P,s,length};
  const span=Math.min(length*.48,43+R()*39);
  const donors=grow.map((raw,source)=>{
   const mid=raw[(raw.length/2)|0],n=nearest(P,mid);
   return {source,raw,distance:n.distance,arc:s[n.index]+n.t*(s[n.index+1]-s[n.index])};
  }).filter(d=>d.distance<44);
  // Find where the actual material can open, rather than announcing an empty
  // body in a random bare interval. A small jitter prevents fixed centre bins.
  let start=(length-span)*(.20+R()*.57),best=-1;
  for(let k=0;k<17;k++){
   const a=(length-span)*(.04+.92*k/16),middle=a+span*.5;
   const support=donors.reduce((n,d)=>n+Math.max(0,1-Math.abs(d.arc-middle)/(span*.65))*(.35+Math.min(70,E.polyLen(d.raw))/70),0);
   if(support>best){best=support;start=a;}
  }
  const end=start+span,side=R()<.5?-1:1;
  // Release shapes disagree across bodies. Staggered donor timing below also
  // prevents a shared pointed tip, even when a local course stays straight.
  const release=['late-fray','early-collapse','broken-shoulder'][(body+seed)%3];
  const K=release==='late-fray'?[[0,0],[.13,.4],[.31,1],[.55,.57],[.79,.83],[.97,.38],[1,0]]:
   release==='early-collapse'?[[0,0],[.09,.6],[.27,.96],[.48,1],[.62,.21],[.84,.09],[1,0]]:
   [[0,0],[.2,.23],[.34,.89],[.53,.42],[.7,1],[.86,.71],[.96,.06],[1,0]];
  const width=18+R()*11,added=[],sourceIds=[];let skipped=0,broken=0,thinned=0;
  for(const donor of donors){
   const {source,raw}=donor;if(raw.length<2)continue;
   // Restrict donation by a strand's coarse course relation, preventing distant
   // fill from being attracted to an opening. Its geometry remains the donor.
   const mid=raw[(raw.length/2)|0],ownership=nearest(P,mid);
   const ownerArc=s[ownership.index]+ownership.t*(s[ownership.index+1]-s[ownership.index]);
   if(ownership.distance>44||ownerArc<start-15||ownerArc>end+15)continue;
   // Keep whole donors instead of artificially dashing the texture. Uneven
   // selection opens air between the real grain-bearing families.
   if(R()>.42){thinned++;continue;}
   const lag=(R()-.5)*13,reach=.67+R()*.76;
   const onset=(R()-.5)*.13,duration=.76+R()*.45;
   const opposing=.40+R()*.20;
   let piece=[],lastArc=null,accepted=false;
   const flush=()=>{if(piece.length>1&&E.polyLen(piece)>1.1){added.push(piece);accepted=true;}piece=[];lastArc=null;};
   for(const p of raw){
    const n=nearest(P,p),arc=s[n.index]+n.t*(s[n.index+1]-s[n.index]),u=((arc-start+lag)/span-onset)/duration;
    if(n.distance>50||u<=0||u>=1){flush();continue;}
    if(lastArc!==null&&Math.abs(arc-lastArc)>3.5){flush();broken++;}
    const f=frame(C,arc),d=dot(sub(p,n.point),f.normal),open=profile(u,K);
    // Unequal flanks and the donor's own offsets form the body, rather than
    // parallel procedural offsets or a closed enclosing silhouette.
    const flank=d*side>=0?1:opposing;
    const normal=d*(width/36)*open*flank*reach;
    const q=add(f.q,add(mul(f.normal,normal),mul(f.tangent,lag*open*.22)));
    piece.push(q);lastArc=arc;
   }
   flush();if(accepted)sourceIds.push(source);else skipped++;
  }
  // Deliberately retain original dry skips: there is no joining across donors.
  material.push(...clip(added,.9));
  events.push({kind:'opening',course:c.id,startMm:+start.toFixed(2),endMm:+end.toFixed(2),
   widthMm:+width.toFixed(2),dominantSide:side,sourceStrokes:sourceIds.length,
   drawnFragments:added.length,projectionBreaks:broken,unusedNearbyStrokes:skipped,
   thinnedWholeDonors:thinned,release,sourceLayer:'d-grow'});
 }
 const strokes=clip(bareStrokes.concat(material),.8);
 return {strokes,events,info:{mechanism:'sparse actual grown strands broaden into unequal openings with staggered release',
  textureSource:'d-grow',materialFragments:material.length,bareCourses:bare.courses.length,
  limitation:'nearest-course mapping can split folded donor strands; no surrounding ground is retained'},
  stages:[{key:'material',strokes:material}]};
}
module.exports={develop};
