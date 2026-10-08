// Exploratory screen probe. Territory supplies material, not protected topology.
// No ordinary Territory hand/bundle/density pass follows this new construction.
const frame = p => [Math.max(9,Math.min(291,p[0])),Math.max(9,Math.min(209,p[1]))];
const add=(a,b)=>[a[0]+b[0],a[1]+b[1]], sub=(a,b)=>[a[0]-b[0],a[1]-b[1]], mul=(a,s)=>[a[0]*s,a[1]*s];
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const unit=v=>mul(v,1/(Math.hypot(...v)||1));
const rotate=(v,a)=>[v[0]*Math.cos(a)-v[1]*Math.sin(a),v[0]*Math.sin(a)+v[1]*Math.cos(a)];
function random(seed){let a=seed>>>0;return()=>{a+=0x6D2B79F5;let t=a;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296;};}
function measure(P){const d=[0];for(let i=1;i<P.length;i++)d.push(d.at(-1)+dist(P[i],P[i-1]));return d;}
function at(P,d,s){s=Math.max(0,Math.min(d.at(-1),s));let i=1;while(i<d.length-1&&d[i]<s)i++;const t=(s-d[i-1])/(d[i]-d[i-1]||1);return add(P[i-1],mul(sub(P[i],P[i-1]),t));}
function sample(P,step=5){const d=measure(P),n=Math.max(2,Math.ceil(d.at(-1)/step));return Array.from({length:n+1},(_,i)=>at(P,d,d.at(-1)*i/n));}
function encounter(courses,rng){
 const candidates=[];
 for(let a=0;a<courses.length;a++)for(let b=a+1;b<courses.length;b++){
  const A=sample(courses[a].present,9),B=sample(courses[b].present,9);
  for(let i=2;i<A.length-2;i++)for(let j=2;j<B.length-2;j++){
   const p=mul(add(A[i],B[j]),.5);if(p[0]<35||p[0]>265||p[1]<28||p[1]>190)continue;
   const gap=dist(A[i],B[j]),score=gap+.075*dist(p,[150,109]);
   candidates.push({a,b,p,score});
  }
 }
 candidates.sort((a,b)=>a.score-b.score);
 return candidates.length?candidates[Math.floor(rng()*Math.min(8,candidates.length))]:{a:0,b:Math.min(1,courses.length-1),p:sample(courses[0].present,20)[2]||courses[0].present[0]};
}
function nearestIndex(P,p){let best=0;for(let i=1;i<P.length;i++)if(dist(P[i],p)<dist(P[best],p))best=i;return best;}
function knots(P,rng,phase){
 const d=measure(P),L=d.at(-1),n=Math.max(4,Math.min(9,Math.round(L/48)));
 const fractions=[0];for(let i=1;i<n;i++)fractions.push((i+(rng()-.5)*.5)/n);fractions.push(1);
 return fractions.map((f,i)=>({p:at(P,d,f*L),role:'flow',hold:.27+rng()*.35,source:f}));
}
// A course changes construction at an encounter: a displaced shoulder, a compressed
// return, a broad release. Dimensions depend on its inherited approach and room.
function articulate(nodes,pivot,rng,phase,kind){
 let j=Math.max(1,Math.min(nodes.length-2,nearestIndex(nodes.map(n=>n.p),pivot)));
 const A=nodes[j-1].p,B=nodes[j+1].p,original=nodes[j].p;
 const u=unit(sub(B,A)),n=rotate(u,Math.PI/2),chord=dist(A,B);
 const sag=sub(original,mul(add(A,B),.5));
 const sign=(sag[0]*n[0]+sag[1]*n[1])>=0?1:-1;
 const room=Math.min(52,Math.max(16,chord*.55)),strength=phase===1?.72:1;
 const centre=add(mul(add(original,pivot),.5),mul(n,sign*(rng()-.4)*room*.3));
 const point=(x,y)=>frame(add(centre,add(mul(u,x*room*strength),mul(n,y*room*strength*sign))));
 let inserted;
 if(kind==='recoil'){
  inserted=[{p:point(-.7,.75),role:'flow',hold:.62},
   {p:point(.7,-.23),role:'pinch',hold:.4},
   {p:point(-.15,1.2),role:'flow',hold:.72},
   {p:point(-.55,.04),role:'turn',hold:.28}];
 }else if(kind==='crosswise'){
  inserted=[{p:point(-.55,.9),role:'flow',hold:.65},
   {p:point(.45,-.65),role:'pinch',hold:.33},
   {p:point(.8,.75),role:'flow',hold:.7},
   {p:point(-.22,-.35),role:'hinge',hold:.2}];
 }else{
  inserted=[{p:point(-.6,.5),role:'flow',hold:.6},
   {p:point(.3,-.27),role:'hinge',hold:.1},
   {p:point(-.15,.85),role:'flow',hold:.57}];
 }
 nodes.splice(j,1,...inserted);
 return {node:j,kind,inserted:inserted.length};
}
function construct(nodes,rng){
 const directions=nodes.map((node,i)=>{
  const before=nodes[Math.max(0,i-1)].p,after=nodes[Math.min(nodes.length-1,i+1)].p;
  const incoming=unit(sub(node.p,before)),outgoing=unit(sub(after,node.p));
  let a=unit(sub(after,before)),b=a;
  if(node.role==='pinch'){a=rotate(incoming,(rng()-.5)*.28);b=rotate(mul(a,-1),.16+rng()*.38);}
  else if(node.role==='turn'){a=rotate(incoming,.25);b=rotate(outgoing,-.7);}
  else if(node.role==='hinge'){a=incoming;b=outgoing;}
  return {a,b};
 });
 const P=[],segments=[];
 for(let i=0;i<nodes.length-1;i++){
  const left=nodes[i],right=nodes[i+1],L=dist(left.p,right.p);
  if(L<.3)continue;
  let h1=L*left.hold,h2=L*right.hold;
  if(left.role==='pinch')h1=L*(.09+rng()*.13);
  if(right.role==='pinch')h2=L*(.04+rng()*.1);
  if(left.role==='hinge')h1=L*.15;
  const C=[left.p,frame(add(left.p,mul(directions[i].b,h1))),frame(sub(right.p,mul(directions[i+1].a,h2))),right.p];
  const length=dist(C[0],C[1])+dist(C[1],C[2])+dist(C[2],C[3]),count=Math.max(8,Math.ceil(length/.4));
  const start=P.length;
  for(let k=0;k<=count;k++){
   if(i&&k===0)continue;const t=k/count,s=1-t;
   P.push([0,1].map(axis=>s*s*s*C[0][axis]+3*s*s*t*C[1][axis]+3*s*t*t*C[2][axis]+t*t*t*C[3][axis]));
  }
  segments.push({start,end:P.length-1,role:left.role,next:right.role});
 }
 return {P,segments};
}
function echoes(P,pivot,rng,count){
 // Short unequal restatements around a real turn; ends are free to diverge.
 const d=measure(P),mid=d[nearestIndex(P,pivot)],span=Math.min(55,d.at(-1)*.23),out=[];
 for(let strand=1;strand<=count;strand++){
  const a=Math.max(0,mid-span*(.55+.2*rng())),b=Math.min(d.at(-1),mid+span*(.35+.45*rng()));
  const Q=sample(Array.from({length:81},(_,i)=>at(P,d,a+(b-a)*i/80)),.45);
  const side=rng()<.5?-1:1;
  const tangents=Q.map((p,i)=>unit(sub(Q[Math.min(i+2,Q.length-1)],Q[Math.max(0,i-2)])));
  const breaks=new Set();for(let i=1;i<tangents.length;i++)if(tangents[i][0]*tangents[i-1][0]+tangents[i][1]*tangents[i-1][1]<-.25){for(let j=Math.max(0,i-4);j<=Math.min(Q.length-1,i+4);j++)breaks.add(j);}
  const offset=Q.map((p,i)=>{const u=i/(Q.length-1),n=rotate(tangents[i],Math.PI/2);
   const offset=side*strand*(.65+.3*Math.sin(u*Math.PI))*(.35+.65*Math.sin(u*Math.PI));
   return frame(add(p,mul(n,offset)));});
  let piece=[];for(let i=0;i<offset.length;i++){if(breaks.has(i)){if(piece.length>5)out.push(piece);piece=[];}else piece.push(offset[i]);}if(piece.length>5)out.push(piece);
 }
 return out;
}
function rewriteChannels(channels,seed,phase=2){
 const source=channels.filter(c=>c.present&&c.present.length>1);
 if(phase===0)return {strokes:source.map(c=>c.present.map(p=>p.slice())),edits:[]};
 const rng=random((seed^0x62ae9387)>>>0);
 let courses=source.filter(c=>measure(c.present).at(-1)>38).map(c=>({...c,present:c.present.map(p=>p.slice())}));
 if(!courses.length)return {strokes:[],edits:[]};
 courses.sort((a,b)=>(a.id===0?-1:b.id===0?1:measure(b.present).at(-1)-measure(a.present).at(-1)));
 courses=courses.slice(0,phase===1?7:5+Math.floor(rng()*2));
 const meet=encounter(courses,rng),edits=[],strokes=[],nextCourses=[];
 const affected=new Set([meet.a,meet.b]);
 let consumed=-1;
 for(let k=0;k<courses.length;k++){
  if(k===consumed)continue;
  const c=courses[k],r=random((seed^Math.imul(c.id+1,92717)^0x29103)>>>0);
  let nodes=knots(c.present,r,phase),origins=c.sourceIds||[c.id];
  const remember=P=>nextCourses.push({id:nextCourses.length,cls:c.cls,present:P.map(p=>p.slice()),sourceIds:origins.slice()});
  if(phase===1&&!affected.has(k)){const P=c.present.map(p=>p.slice());strokes.push(P);remember(P);continue;}
  if(phase===2){
   // Whole-course re-anchoring permits endpoint movement and new enclosing air.
   const centre=mul(nodes.reduce((a,n)=>add(a,n.p),[0,0]),1/nodes.length);
   const angle=(r()-.5)*.32,stretch=.82+r()*.45;
   nodes=nodes.map(node=>({...node,p:frame(add(centre,rotate([sub(node.p,centre)[0]*stretch,sub(node.p,centre)[1]*(1.2-.35*r())],angle)))}));
  }
  // Occasionally splice material from two existing courses; their old join is released.
  if(phase===2&&k===meet.a&&meet.b>k&&r()>.35){
   const other=knots(courses[meet.b].present,r,phase),ia=Math.max(2,Math.min(nodes.length-2,nearestIndex(nodes.map(n=>n.p),meet.p)));
   let ib=Math.max(1,Math.min(other.length-2,nearestIndex(other.map(n=>n.p),meet.p)));
   nodes=nodes.slice(0,ia+1).concat(other.slice(ib));consumed=meet.b;origins=origins.concat(courses[meet.b].sourceIds||[courses[meet.b].id]);
  }
  const kind=['recoil','crosswise','lean'][Math.floor(r()*3)];
  const intervention=affected.has(k)||k===0||r()<.28
   ?articulate(nodes,affected.has(k)?meet.p:nodes[Math.floor(nodes.length*.55)].p,r,phase,kind)
   :{kind:'re-anchored',inserted:0};
  if(phase===2&&k===0&&nodes.length>7&&r()>.25){
   // A second change of construction is remote from the first; no compulsory paired motif.
   const j=Math.max(1,nodes.length-3);nodes[j].role=r()>.5?'hinge':'pinch';nodes[j].hold=.18;
  }
  const made=construct(nodes,r),main=made.P;
  if(main.length<2)continue;
  // One interrupted course can survive as separate material, not hidden old topology.
  if(phase===2&&k>1&&r()>.6){
   const cut=Math.floor(main.length*(.35+r()*.3)),gap=Math.max(3,Math.floor(main.length*.025));
   const A=main.slice(0,cut),B=main.slice(cut+gap);strokes.push(A,B);remember(A);remember(B);
  }else{strokes.push(main);remember(main);}
  if(affected.has(k)||k===0)strokes.push(...echoes(main,meet.p,r,phase===1?1:2+Math.floor(r()*2)));
  edits.push({sourceIds:origins,kind:intervention.kind,nodes:nodes.map(n=>({p:n.p,role:n.role})),spliced:origins.length>1});
 }
 return {strokes:strokes.filter(P=>P.length>1),courses:nextCourses,edits,pivot:meet.p};
}
module.exports={rewriteChannels};
