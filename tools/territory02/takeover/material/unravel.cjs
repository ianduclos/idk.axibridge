// Extract already-grown material. The pull line is one of that material's
// original runs, displaced under tension; it is never generated independently.
const {E, add, sub, mul, dot, dist, unit, clamp, rng, measure, at, nearest, clip}=require('./common.cjs');
const clone=P=>P.map(p=>p.slice());
function runs(P, sourceIndex){
 const result=[];let start=0;
 const save=end=>{const Q=P.slice(start,end+1);const length=E.polyLen(Q);if(Q.length>5&&length>=16)result.push({P:clone(Q),sourceIndex,start,end,length});};
 for(let j=2;j<P.length;j++)if(dot(unit(sub(P[j],P[j-1])),unit(sub(P[j-1],P[j-2])))<0.45){save(j-1);start=j-1;}
 save(P.length-1);return result;
}
function station(P,S,p){const n=nearest(P,p);return {...n,s:S[n.index]+dist(P[n.index],n.point)};}
function develop({seed,bare,texture}){
 const random=rng(seed^0x756e7261), original=texture.strokes.map(clone), allBefore=bare.strokes.map(clone).concat(original);
 const grown=texture.layers?.find(L=>L.kind==='d-grow')?.strokes||[];
 // Layer strokes are references in the current input, but allow equal copied
 // representations as well. Provenance is always an index in texture.strokes.
 const ids=new Map(texture.strokes.map((P,i)=>[P,i]));
 let candidates=[];
 for(const P of grown){let id=ids.get(P);if(id===undefined)id=texture.strokes.findIndex(Q=>JSON.stringify(Q)===JSON.stringify(P));if(id<0)continue;candidates.push(...runs(P,id));}
 const pivot=bare.pivot||[150,109], courses=bare.strokes.map(P=>E.resample(P,1.5));
 const grainSamples=original.flatMap(P=>P.filter((_,i)=>i%5===0));
 const selected=[];
 for(const c of candidates){
  // Work with a finite developed passage, never turn a whole zigzag fill into
  // one enormous drawn cable. Exact original vertices survive this cropping.
  if(c.length>43){let total=0,j=1;for(;j<c.P.length;j++){total+=dist(c.P[j],c.P[j-1]);if(total>=43)break;}c.P=c.P.slice(0,j+1);c.end=c.start+j;c.length=E.polyLen(c.P);}
  c.S=measure(c.P);c.mid=at(c.P,c.S,c.length*0.5);
  c.density=grainSamples.reduce((n,p)=>n+(dist(p,c.mid)<7?1:0),0);
  c.rank=c.density*0.45+c.length*0.18-dist(c.mid,pivot)*0.34+random()*3;
 }
 candidates.sort((a,b)=>b.rank-a.rank);
 for(const c of candidates){if(selected.length>=4)break;if(c.density<10||selected.some(q=>dist(q.mid,c.mid)<29))continue;selected.push(c);}
 let body=original, pulls=[], scraps=[], events=[];
 for(let eventIndex=0;eventIndex<selected.length;eventIndex++){
  const c=selected[eventIndex];let P=c.P;
  // Root choice follows available paper, while the pull direction includes
  // the local approved course tangent. Both ends are real grown endpoints.
  let best;
  for(const reverse of [false,true]){
   const Q=reverse?P.slice().reverse():P, S=measure(Q), L=S.at(-1), mid=at(Q,S,L*0.5);
   let guide={distance:Infinity};for(const course of courses){const n=nearest(course,mid);if(n.distance<guide.distance)guide=n;}
   const sourceDirection=unit(sub(Q.at(-1),Q[0])), tangent=guide.tangent||sourceDirection;
   const courseDirection=dot(tangent,sourceDirection)<0?mul(tangent,-1):tangent;
   for(const side of [-1,1]){
    const normal=[-courseDirection[1],courseDirection[0]], inward=unit(sub([150,109],mid));
    const direction=unit(add(add(mul(sourceDirection,0.30),mul(courseDirection,0.28)),add(mul(normal,side*0.72),mul(inward,0.2))));
    const desired=52+random()*27;
    let room=desired;for(let j=1;j<Q.length;j++){const t=S[j]/L,p=Q[j],w=Math.pow(t,1.32);for(let axis=0;axis<2;axis++){const v=direction[axis]*w;if(v>0)room=Math.min(room,((axis?212:294)-p[axis])/v);else if(v<0)room=Math.min(room,((axis?6:6)-p[axis])/v);}}
    const score=room-dist(add(Q.at(-1),mul(direction,room)),pivot)*0.07;
    if(!best||score>best.score)best={Q,S,L,direction,amount:Math.max(0,room),score,side};
   }
  }
  if(best.amount<22)continue;
  // Lift the actual selected source run out before displacing it. Matching
  // exact vertices prevents a duplicate fiber being left in the rim material.
  // If a prior extraction already severed this run, leave it unresolved.
  let sourceFound=false;const withoutSource=[];
  for(const Q of body){
   let start=-1;
   for(let j=0;j<=Q.length-c.P.length;j++)if(dist(Q[j],c.P[0])<1e-8&&dist(Q[j+c.P.length-1],c.P.at(-1))<1e-8){
    if(c.P.every((p,k)=>dist(p,Q[j+k])<1e-8)){start=j;break;}
   }
   if(start<0){withoutSource.push(Q);continue;}
   sourceFound=true;
   const before=Q.slice(0,start+1),after=Q.slice(start+c.P.length-1);
   if(before.length>1)withoutSource.push(before);if(after.length>1)withoutSource.push(after);
  }
  if(!sourceFound)continue;body=withoutSource;
  P=best.Q;const S=best.S,L=best.L,dir=best.direction;
  const transverse=[-dir[1],dir[0]],bend=(eventIndex%2?-1:1)*(5+random()*6);
  // One coarse tension displacement, added to every original fine vertex.
  // Tiny irregularities are not regenerated or cleaned out.
  const displacement=t=>add(mul(dir,best.amount*Math.pow(clamp(t,0,1),1.32)),mul(transverse,bend*Math.sin(Math.PI*clamp(t,0,1))*Math.pow(clamp(t,0,1),0.8)));
  const warp=p=>{const n=station(P,S,p);return add(p,displacement(n.s/L));};
  const widthBase=3.6+random()*2.8;
  const width=t=>widthBase*(0.52+0.63*Math.sin(Math.PI*t))*(1+0.18*Math.sin(t*27+seed*0.4)+0.09*Math.sin(t*71));
  // A rooted wedge with a ragged grain-led boundary, not an oval mask. The
  // fixed first few millimetres preserve where the extracted fiber belonged.
  const inside=p=>{const n=station(P,S,p),t=n.s/L;return t>0.09&&t<0.97&&n.distance<width(t)&&dot(sub(p,P[0]),unit(sub(P[1],P[0])))>0;};
  const pulled=P.map((p,j)=>add(p,displacement(S[j]/L)));
  const next=[], cut=[];
  const low=[Math.min(...P.map(p=>p[0]))-widthBase*2,Math.min(...P.map(p=>p[1]))-widthBase*2],high=[Math.max(...P.map(p=>p[0]))+widthBase*2,Math.max(...P.map(p=>p[1]))+widthBase*2];
  for(let bodyIndex=0;bodyIndex<body.length;bodyIndex++){
   const Q=body[bodyIndex];
   // Broad phase avoids asking every distant fine grain vertex about this
   // corridor. None of the surviving material is resampled.
   if(!Q.some(p=>p[0]>=low[0]&&p[0]<=high[0]&&p[1]>=low[1]&&p[1]<=high[1])){next.push(Q);continue;}
   let part=[], extracting=null;
   const flush=()=>{if(part.length>1&&E.polyLen(part)>0.12)(extracting?cut:next).push(part);part=[];};
   for(let j=0;j<Q.length;j++){
    const state=inside(Q[j]);
    if(extracting!==null&&state!==extracting){
     // Bisect the actual existing segment at the irregular boundary. The
     // drawing receives both sides, with no connecting stroke across cavity.
     let a=Q[j-1],b=Q[j];for(let k=0;k<9;k++){const m=mul(add(a,b),0.5);if(inside(m)===extracting)a=m;else b=m;}
     const edge=mul(add(a,b),0.5);part.push(edge);flush();part=[edge];
    }
    extracting=state;part.push(Q[j].slice());
   }
   flush();
  }
  body=next;
  // Every adjacent cut fragment is accounted for below; the core was lifted
  // intact above, and is now emitted once as the tensioned strand.
  let movedMm=0,carriedMm=0,rimMm=0,carried=0;const fragmentRecords=[];
  cut.sort((a,b)=>E.polyLen(b)-E.polyLen(a));
  for(let i=0;i<cut.length;i++){
   const Q=cut[i], qs=measure(Q),qmid=at(Q,qs,qs.at(-1)*0.5),n=station(P,S,qmid),t=n.s/L;
   const radial=sub(qmid,n.point),normal=unit(radial),sourceLen=E.polyLen(Q);
   // Two small groups travel: a root scrap and a late snag. Rigid translation
   // preserves each scrap's actual irregular internal grain.
   const carry=carried<7&&sourceLen<10&&sourceLen>0.6&&((t>0.15&&t<0.32)||(t>0.68&&t<0.92))&&n.distance<width(t)*0.86;
   let delta,destination;
   if(carry){delta=displacement(t);carried++;carriedMm+=sourceLen;destination='carried';}
   else{
    // The cut remnants gather on the torn edge, moved coherently from their
    // place of extraction. This opens the cavity without deleting fill.
    const localTangent=n.tangent||unit(sub(P.at(-1),P[0]));
    delta=add(mul(normal,Math.max(0.7,width(t)-n.distance+0.6)),mul(localTangent,(t-0.5)*2.4));
    rimMm+=sourceLen;destination='rim';
   }
   const moved=Q.map(p=>add(p,delta));(carry?scraps:body).push(moved);movedMm+=sourceLen;
   if(fragmentRecords.length<12)fragmentRecords.push({sourceMid:qmid,sourceLengthMm:sourceLen,station:t,destination,translation:delta});
  }
  // Source-derived core line retains its initial fixed root and grain vertices.
  // Neighboring same-run return legs are treated as real torn-edge fragments.
  pulls.push(pulled);
  events.push({kind:'grown-strand-extraction',sourceLayer:'d-grow',sourceStroke:c.sourceIndex,sourceVertexRange:[c.start,c.end],sourceRun:P,root:P[0],tip:pulled.at(-1),pullMm:best.amount,sourceRunMm:L,pulledRunMm:E.polyLen(pulled),cavityHalfWidthMm:widthBase,cutFragments:cut.length,carriedFragments:carried,movedGrainMm:movedMm,carriedGrainMm:carriedMm,rimGrainMm:rimMm,fragmentRecords});
 }
 const strokes=clip(bare.strokes.map(clone).concat(body,pulls,scraps),0.12);
 return {strokes,events,info:{mechanism:'actual grown run displaced under tension; adjacent extracted grain carried rigidly or moved to torn edge',extractions:events.length,unchangedBareCourses:bare.strokes.length,grainResampled:false,limits:'Pulls retain grown micro-turns; rim fragments may thicken the cavity boundary. No aesthetic acceptance inferred.'},stages:[{key:'developed',strokes:allBefore},{key:'body-after',strokes:clip(bare.strokes.map(clone).concat(body),0.12)},{key:'extracted',strokes:clip(pulls.concat(scraps),0.12)}]};
}
module.exports={develop};
