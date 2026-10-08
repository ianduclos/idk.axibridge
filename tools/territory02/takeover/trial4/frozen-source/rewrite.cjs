// Experimental contact/tension regime. No prescribed fold, loop or silhouette template.
// Input courses form a temporary network; contact pressures and exchanged continuations
// create the construction. Cubic fitting translates its unequal tensions into curves.
const add=(a,b)=>[a[0]+b[0],a[1]+b[1]],sub=(a,b)=>[a[0]-b[0],a[1]-b[1]],mul=(a,s)=>[a[0]*s,a[1]*s];
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]),unit=v=>mul(v,1/(Math.hypot(...v)||1));
const rotate=(v,a)=>[v[0]*Math.cos(a)-v[1]*Math.sin(a),v[0]*Math.sin(a)+v[1]*Math.cos(a)];
const dot=(a,b)=>a[0]*b[0]+a[1]*b[1],frame=p=>[Math.max(9,Math.min(291,p[0])),Math.max(9,Math.min(209,p[1]))];
function random(seed){let a=seed>>>0;return()=>{a+=0x6D2B79F5;let t=a;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296;};}
function measure(P){const d=[0];for(let i=1;i<P.length;i++)d.push(d.at(-1)+dist(P[i],P[i-1]));return d;}
function at(P,d,s){s=Math.max(0,Math.min(d.at(-1),s));let i=1;while(i<d.length-1&&d[i]<s)i++;const t=(s-d[i-1])/(d[i]-d[i-1]||1);return add(P[i-1],mul(sub(P[i],P[i-1]),t));}
function sample(P,step=6){const d=measure(P),n=Math.max(2,Math.ceil(d.at(-1)/step));return Array.from({length:n+1},(_,i)=>at(P,d,d.at(-1)*i/n));}
function near(P,p){let i=0;for(let j=1;j<P.length;j++)if(dist(P[j],p)<dist(P[i],p))i=j;return i;}
function contacts(courses,rng,count){
 const options=[];
 for(let a=0;a<courses.length;a++)for(let b=a+1;b<courses.length;b++){
  const A=courses[a].P,B=courses[b].P;
  for(let i=2;i<A.length-2;i++)for(let j=2;j<B.length-2;j++){
   const gap=dist(A[i],B[j]);if(gap>27)continue;
   const p=mul(add(A[i],B[j]),.5);if(p[0]<28||p[0]>272||p[1]<24||p[1]>194)continue;
   const u=unit(sub(A[i+1],A[i-1])),v=unit(sub(B[j+1],B[j-1]));
   // This prioritizes a geometric encounter, not a beauty score.
   options.push({a,b,i,j,p,u,v,score:gap+.08*dist(p,[150,109])-3*(1-Math.abs(dot(u,v)))});
  }
 }
 options.sort((a,b)=>a.score-b.score);const found=[];
 while(options.length&&found.length<count){
  const pick=options.splice(Math.floor(rng()*Math.min(7,options.length)),1)[0];
  if(found.some(x=>dist(x.p,pick.p)<28))continue;found.push(pick);
 }
 return found;
}
function pressure(courses,sites,rng,phase){
 const forcing=courses.map(c=>c.P.map(p=>({sum:[0,0],w:0,hinge:0})));
 const records=[];
 for(const site of sites){
  const direction=rotate(unit(add(site.u,site.v)),(.35+rng()*1.1)*(rng()<.5?-1:1));
  const reach=phase===1?20+rng()*22:30+rng()*42;
  const destination=frame(add(site.p,mul(direction,reach))),radius=24+rng()*33;
  const separation=(phase===1?4:2)+rng()*7;
  const normal=rotate(direction,Math.PI/2);
  for(const [id,index,side] of [[site.a,site.i,-1],[site.b,site.j,1]]){
   const c=courses[id],d=measure(c.P),target=frame(add(destination,mul(normal,side*separation)));
   const displacement=sub(target,c.P[index]);
   const crossing=Math.atan2(site.u[0]*site.v[1]-site.u[1]*site.v[0],dot(site.u,site.v));
   const torque=(crossing||.7)*side*(phase===1?.7:1.25);
   for(let i=0;i<c.P.length;i++){
    const arclength=Math.abs(d[i]-d[index]),t=Math.max(0,1-arclength/radius);
    const w=t*t*(3-2*t);if(!w)continue;
    const f=forcing[id][i];const relative=sub(c.P[i],c.P[index]);
    const demand=add(add(c.P[i],displacement),sub(rotate(relative,torque*t*t),relative));
    f.sum=add(f.sum,mul(demand,w));f.w+=w;
    f.hinge=Math.max(f.hinge,Math.pow(t,4));
   }
  }
  records.push({...site,target:destination,radius,separation});
 }
 // The elastic course negotiates inherited shape, local contact demands and
 // variable resistance to bending. Low stiffness at a contact concentrates turn.
 return {records,courses:courses.map((c,id)=>{
  const r=random((Math.imul(c.id+1,71317)^phase^Math.imul(Math.floor(rng()*1e8),37))>>>0);
  const rest=c.P.map(p=>p.slice()),f=forcing[id];let P=rest.map(p=>p.slice());
  const bias=r()-.5,wave=.55+r()*.7;
  for(let step=0;step<38;step++){
   P=P.map((p,i)=>{
    const demand=f[i],stiffness=(.8+wave*Math.sin(i*.18+bias)**2)*(1-.94*demand.hinge);
    const prior=phase===1?.5:.18,force=demand.w*(phase===1?2.8:4.2);
    let total=mul(rest[i],prior),denom=prior;
    if(force){total=add(total,mul(demand.sum,force/demand.w));denom+=force;}
    for(const j of [i-1,i+1])if(j>=0&&j<P.length){total=add(total,mul(P[j],stiffness));denom+=stiffness;}
    const q=mul(total,1/denom);return frame(add(mul(p,.22),mul(q,.78)));
   });
  }
  return {...c,P,hinges:f.map(x=>x.hinge)};
 })};
}
function simplify(P,error){
 if(P.length<3)return P.map(p=>p.slice());const A=P[0],B=P.at(-1),u=sub(B,A),u2=dot(u,u)||1;let best=error,idx=-1;
 for(let i=1;i<P.length-1;i++){const t=Math.max(0,Math.min(1,dot(sub(P[i],A),u)/u2)),d=dist(P[i],add(A,mul(u,t)));if(d>best){best=d;idx=i;}}
 if(idx<0)return[A.slice(),B.slice()];return simplify(P.slice(0,idx+1),error).slice(0,-1).concat(simplify(P.slice(idx),error));
}
function fit(P,rng,joints=[]){
 const nodes=simplify(P,.55);if(nodes.length<2)return [];
 const turns=nodes.map((p,i)=>i===0||i===nodes.length-1?0:Math.acos(Math.max(-1,Math.min(1,dot(unit(sub(p,nodes[i-1])),unit(sub(nodes[i+1],p)))))));
 const tangent=nodes.map((p,i)=>unit(sub(nodes[Math.min(nodes.length-1,i+1)],nodes[Math.max(0,i-1)])));
 const authority=nodes.map(()=>.8+rng()*.45),out=[];
 for(let i=0;i<nodes.length-1;i++){
  const A=nodes[i],B=nodes[i+1],L=dist(A,B);if(L<.02)continue;
  const exit=tangent[i],entry=tangent[i+1];
  // Short controls at concentrated turns, longer controls along held reaches.
  // Their inequality comes from adjacent route lengths and local resistance.
  const previous=i?dist(A,nodes[i-1]):L,next=i+2<nodes.length?dist(B,nodes[i+2]):L;
  const h1=Math.min(L*.85,Math.sqrt(previous*L)*(.48-.38*Math.min(1,turns[i]/2.4))*authority[i]);
  const h2=Math.min(L*.8,Math.sqrt(next*L)*(.43-.36*Math.min(1,turns[i+1]/2.4))/authority[i+1]);
  const C=[A,frame(add(A,mul(exit,h1))),frame(sub(B,mul(entry,h2))),B];
  const length=dist(C[0],C[1])+dist(C[1],C[2])+dist(C[2],C[3]),n=Math.max(5,Math.ceil(length/.35));
  for(let k=0;k<=n;k++){if(i&&k===0)continue;const t=k/n,s=1-t;out.push([0,1].map(axis=>s*s*s*C[0][axis]+3*s*s*t*C[1][axis]+3*s*t*t*C[2][axis]+t*t*t*C[3][axis]));}
 }
 return out;
}
function restatements(P,pivot,rng,count){
 const d=measure(P),mid=d[near(P,pivot)],span=Math.min(40,d.at(-1)*.2),out=[];
 for(let k=0;k<count;k++){
  const start=Math.max(0,mid-span*(.3+.5*rng())),end=Math.min(d.at(-1),mid+span*(.3+.6*rng()));
  const Q=sample(Array.from({length:60},(_,i)=>at(P,d,start+(end-start)*i/59)),.45),side=rng()<.5?-1:1;
  const tangents=Q.map((p,i)=>unit(sub(Q[Math.min(i+2,Q.length-1)],Q[Math.max(0,i-2)]))),breaks=new Set();
  for(let i=1;i<Q.length;i++)if(dot(tangents[i],tangents[i-1])<-.25)for(let j=Math.max(0,i-4);j<=Math.min(Q.length-1,i+4);j++)breaks.add(j);
  let piece=[];for(let i=0;i<Q.length;i++){
   if(breaks.has(i)){if(piece.length>6)out.push(piece);piece=[];continue;}
   const u=i/(Q.length-1),width=side*(k+1)*(.45+.75*Math.sin(u*Math.PI))*(.3+.7*u);
   piece.push(frame(add(Q[i],mul(rotate(tangents[i],Math.PI/2),width))));
  }
  if(piece.length>6)out.push(piece);
 }
 return out;
}
function rewriteChannels(channels,seed,phase=2){
 const source=channels.filter(c=>c.present&&c.present.length>1);
 if(phase===0)return{strokes:source.map(c=>c.present.map(p=>p.slice())),edits:[]};
 const rng=random((seed^Math.imul(phase,81871)^0x628391)>>>0);
 let courses=source.filter(c=>measure(c.present).at(-1)>10).map((c,i)=>({id:i,cls:c.cls,P:sample(c.present,6),sourceIds:c.sourceIds||[c.id],joints:[]}));
 if(!courses.length)return{strokes:[],courses:[],edits:[]};
 courses=courses.slice(0,18);
 const sites=contacts(courses,rng,phase===1?3:4),solved=pressure(courses,sites,rng,phase);
 courses=solved.courses;const edits=solved.records.map(x=>({kind:'contact-pressure',sourceIds:[...courses[x.a].sourceIds,...courses[x.b].sourceIds],from:x.p,target:x.target,radius:x.radius}));
 if(phase===2){
  // Exchange actual continuations. No new geometric motif is inserted at a join.
  const used=[];
  for(let step=0;step<2;step++){
   // A splice changes sample indices and course lengths. Find the next
   // encounter on that changed network rather than reusing a stale plan.
   const site=contacts(courses,rng,8).find(s=>!used.some(p=>dist(p,s.p)<28));
   if(!site)break;
   used.push(site.p);
   if(rng()<.2)continue;const A=courses[site.a],B=courses[site.b],q=mul(add(A.P[site.i],B.P[site.j]),.5);
   const a=A.P.slice(0,site.i),b=B.P.slice(site.j+1),c=B.P.slice(0,site.j),d=A.P.slice(site.i+1);
   courses[site.a]={...A,P:a.concat([q],b),sourceIds:[...A.sourceIds,...B.sourceIds],joints:[...A.joints,q,...B.joints]};
   courses[site.b]={...B,P:c.concat([q],d),sourceIds:[...B.sourceIds,...A.sourceIds],joints:[...B.joints,q,...A.joints]};
   edits.push({kind:'exchange-continuations',sourceIds:[...A.sourceIds,...B.sourceIds],at:q});
  }
 }
 const pivot=solved.records[0]?.target||[150,109],strokes=[],nextCourses=[];
 for(let k=0;k<courses.length;k++){
  const c=courses[k],r=random((seed^Math.imul(k+1,61331)^Math.imul(phase,96373))>>>0),P=fit(c.P,r,c.joints);
  if(P.length<2)continue;
  let pieces=[P];
  if(phase===2&&k>1&&r()<.3){
   const atIndex=near(P,pivot),gap=8+Math.floor(r()*22);
   if(atIndex>15&&atIndex<P.length-15){pieces=[P.slice(0,Math.max(2,atIndex-gap)),P.slice(Math.min(P.length-2,atIndex+gap))];edits.push({kind:'cut',sourceIds:c.sourceIds,at:P[atIndex]});}
  }
  for(const piece of pieces){if(piece.length<2)continue;strokes.push(piece);nextCourses.push({id:nextCourses.length,cls:c.cls,present:piece.map(p=>p.slice()),sourceIds:[...new Set(c.sourceIds)]});}
  if(sites.some(s=>s.a===k||s.b===k)&&r()<.8)strokes.push(...restatements(P,pivot,r,phase===1?1:1+Math.floor(r()*3)));
 }
 return{strokes,courses:nextCourses,edits,pivot};
}
module.exports={rewriteChannels};
