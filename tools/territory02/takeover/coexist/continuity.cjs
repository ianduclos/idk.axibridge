// A real rough interval is exchanged, then a few real neighbouring fibers
// carry the changed direction for a while before releasing it.
const {E,rng,measure,at,nearest,add,sub,mul,dot,dist,unit,clamp,clip}=require('./common.cjs');
const clone=P=>P.map(p=>p.slice());
const ease=t=>{t=clamp(t,0,1);return t*t*(3-2*t);};
function frame(P,S,u){
 const x=clamp(u,0,1)*S.at(-1);let lo=1,hi=S.length-1;
 while(lo<hi){const m=(lo+hi)>>1;if(S[m]<x)lo=m+1;else hi=m;}
 const i=lo,t=(x-S[i-1])/(S[i]-S[i-1]||1),q=add(P[i-1],mul(sub(P[i],P[i-1]),t));
 const tangent=unit(sub(P[Math.min(P.length-1,i+1)],P[Math.max(0,i-2)]));
 return {q,tangent,normal:[-tangent[1],tangent[0]]};
}
// Subdivision inserts vertices without throwing away any existing donor grain.
function subdivide(P,step=.6){
 const Q=[P[0].slice()],origins=[0];
 for(let i=1;i<P.length;i++){const n=Math.max(1,Math.ceil(dist(P[i-1],P[i])/step));
  for(let j=1;j<=n;j++){Q.push(add(P[i-1],mul(sub(P[i],P[i-1]),j/n)));origins.push(i-1+j/n);}
 }
 return {P:Q,origins};
}
function develop(prepared){
 const {seed,base,baseName,I,smooth}=prepared,R=rng(seed^0x636f6e74),events=[],out=base.strokes.map(P=>[clone(P)]),used=new Set(smooth.map(s=>s.sourceIndex));
 const sourceOnly=base.strokes.map(clone),changed=[];
 // Bases emit bare courses before material, but prior clipping can remove or
 // split strokes. This prefix is only an approximate exclusion: donors are
 // actual surviving base strokes; material-versus-bare attribution is inferred.
 const barePrefix=I.bare.strokes.length;
 for(const [passageIndex,s] of smooth.entries()){
  const raw=base.strokes[s.sourceIndex],a=nearest(raw,s.P[0]),b=nearest(raw,s.P.at(-1));
  let replacement,sourceRange;
  if(b.index>=a.index){
   replacement=clone(raw.slice(0,a.index+1)).concat(clone(s.P),clone(raw.slice(b.index+1)));
   sourceRange={originalVertexRange:[a.index,b.index+1],startSegmentFraction:a.t,endSegmentFraction:b.t};
  }else{
   // Ordered prepared indices provide a safe fallback on an exact self-crossing.
   replacement=clone(s.source.slice(0,s.start)).concat(clone(s.P),clone(s.source.slice(s.end+1)));
   sourceRange={preparedVertexRange:[s.start,s.end],resampledOutsideInterval:true};
  }
  out[s.sourceIndex]=[replacement];sourceOnly[s.sourceIndex]=clone(replacement);
  const old=E.resample(s.oldInterval,1),OS=measure(old),NS=measure(s.P),candidates=[];
  for(let index=barePrefix;index<base.strokes.length;index++){
   if(used.has(index))continue;const P=base.strokes[index],length=E.polyLen(P);if(length<8||length>145)continue;
   const probes=[];
   for(let j=0;j<7;j++){const p=P[Math.floor((P.length-1)*j/6)],n=nearest(old,p),arc=OS[n.index]+n.t*(OS[n.index+1]-OS[n.index]);probes.push({d:n.distance,u:arc/OS.at(-1)});}
   const nearby=probes.filter(p=>p.d<11&&p.u>.035&&p.u<.965);
   if(nearby.length<5)continue;
   const lo=Math.min(...nearby.map(p=>p.u)),hi=Math.max(...nearby.map(p=>p.u)),span=(hi-lo)*OS.at(-1);
   if(span<7||span>85)continue;
   const mean=nearby.reduce((n,p)=>n+p.d,0)/nearby.length;
   candidates.push({index,P,length,lo,hi,mean,rank:span/(2+mean)+R()*.7});
  }
  candidates.sort((a,b)=>b.rank-a.rank);const selected=[];
  for(const c of candidates){
   if(selected.length>=10)break;
   // Sparse, uneven strands instead of a new parallel fill family.
   if(selected.filter(d=>Math.abs((d.lo+d.hi)-(c.lo+c.hi))<.10).length>=3)continue;
   selected.push(c);
  }
  const donorRecords=[];
  for(const [f,c] of selected.entries()){
   const dense=subdivide(c.P),Q=dense.P,S=measure(Q),length=S.at(-1),onset=.04+R()*.19,release=.58+R()*.25,reach=.75+R()*.25;
   const shifted=[],weights=[],stations=[];
   for(let j=0;j<Q.length;j++){
    const p=Q[j],n=nearest(old,p),arc=OS[n.index]+n.t*(OS[n.index+1]-OS[n.index]),u=arc/OS.at(-1),t=S[j]/length;
    const oldFrame=frame(old,OS,u),newFrame=frame(s.P,NS,u),residual=sub(p,n.point);
    const mapped=add(newFrame.q,add(mul(newFrame.tangent,dot(residual,oldFrame.tangent)),mul(newFrame.normal,dot(residual,oldFrame.normal))));
    // Capture and release disagree among donors. A delayed second snag allows
    // some real fibers to approach again after starting to tear away.
    const capture=ease((t-onset)/.17),letGo=1-ease((t-release)/(.13+f%3*.035));
    const snag=f%3===1?.35*ease((t-.73)/.065)*(1-ease((t-.88)/.07)):0;
    const w=Math.max(capture*letGo,snag)*reach*(1-ease((n.distance-11)/5));
    shifted.push(add(p,mul(sub(mapped,p),w)));weights.push(w);stations.push(arc);
   }
   // Contract the whole donor's displacement if necessary; never clamp points
   // to the rectangle, which would create artificial straight boundary runs.
   let factor=1;
   for(let j=0;j<Q.length;j++)for(let axis=0;axis<2;axis++){
    const d=shifted[j][axis]-Q[j][axis],low=1.2,high=axis?216.8:298.8;
    if(d>0)factor=Math.min(factor,(high-Q[j][axis])/d);else if(d<0)factor=Math.min(factor,(low-Q[j][axis])/d);
   }
   factor=clamp(factor,0,1);if(factor<.18)continue;
   const P=shifted.map((p,j)=>add(Q[j],mul(sub(p,Q[j]),factor))),fragments=[],ranges=[],discardedFragments=[];
   let part=[],first=0,removedMm=0;
   const flush=last=>{if(part.length){const record={originalVertexRange:[dense.origins[first],dense.origins[last]],points:part.length,lengthMm:E.polyLen(part)};if(part.length>1&&record.lengthMm>.12){fragments.push(part);ranges.push(record);}else discardedFragments.push(record);}part=[];};
   const tear=f%3===0,tearAt=release+.035,tearWidth=.012+R()*.018;
   for(let j=0;j<P.length;j++){
    const t=S[j]/length,gap=tear&&t>tearAt&&t<tearAt+tearWidth;
    const fold=j>0&&Math.abs(stations[j]-stations[j-1])>5;
    if(gap||fold){flush(j-1);if(gap&&j>0)removedMm+=dist(Q[j-1],Q[j]);}
    if(gap)continue;if(!part.length)first=j;part.push(P[j]);
   }
   flush(P.length-1);
   if(!fragments.length||Math.max(...P.map((p,j)=>dist(p,Q[j])))<.5)continue;
   used.add(c.index);out[c.index]=fragments;changed.push(...fragments);
   donorRecords.push({sourceStroke:c.index,sourceClassification:'material-inferred-from-approximate-prefix',sourceVertexRange:[0,c.P.length-1],originalLengthMm:c.length,passageStationRange:[c.lo,c.hi],meanSourceDistanceMm:c.mean,captureAt:onset,releaseAt:release,tearFractionRange:tear?[tearAt,tearAt+tearWidth]:null,displacementFactor:factor,removedGapMm:removedMm,changedFragments:ranges,discardedFragments});
  }
  events.push({kind:'source-interval-continuity',passage:passageIndex,sourceStroke:s.sourceIndex,...sourceRange,preparedVertexRange:[s.start,s.end],removedSourceMm:E.polyLen(s.oldInterval),smoothReplacementMm:E.polyLen(s.P),smoothDisplacementFactor:s.factor,donorRecords});
 }
 const strokes=clip(out.flat(),.05);
 return {strokes,events,info:{mechanism:'real source interval exchanged; sparse actual surviving base fibers follow, release and sometimes snag again',baseName,sourceIntervals:events.length,changedBaseStrokes:events.reduce((n,e)=>n+e.donorRecords.length,0),donorClassification:'material-versus-bare inferred from an approximate unclipped bare-stroke prefix; prior clipping can remove or split strokes',approximateExcludedPrefix:barePrefix,baseElsewhereRetained:true,donorVerticesPreservedExceptRecordedTearsAndTinyFragments:true,limitation:'long capture transitions can become stretched fibers; projection folds are split, not connected; donor material attribution is inferred'},stages:[{key:'source-exchanged',strokes:sourceOnly},{key:'following-fragments',strokes:clip(changed,.12)}]};
}
module.exports={develop};
