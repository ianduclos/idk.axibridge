// Two physical fill constructions share boundaries taken from actual rewritten
// courses. No inherited Territory tone field or independently placed fill stamp.
const add=(a,b)=>[a[0]+b[0],a[1]+b[1]],sub=(a,b)=>[a[0]-b[0],a[1]-b[1]],mul=(a,s)=>[a[0]*s,a[1]*s],dot=(a,b)=>a[0]*b[0]+a[1]*b[1];
const dist=(a,b)=>Math.hypot(...sub(a,b)),unit=a=>mul(a,1/(Math.hypot(...a)||1));
function random(seed){let a=seed>>>0;return()=>{a+=0x6D2B79F5;let t=a;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296;};}
function measure(P){const d=[0];for(let i=1;i<P.length;i++)d.push(d.at(-1)+dist(P[i],P[i-1]));return d;}
function at(P,d,s){s=Math.max(0,Math.min(d.at(-1),s));let i=1;while(i<d.length-1&&d[i]<s)i++;return add(P[i-1],mul(sub(P[i],P[i-1]),(s-d[i-1])/(d[i]-d[i-1]||1)));}
function sample(P,step=2){const d=measure(P),n=Math.max(2,Math.ceil(d.at(-1)/step));return Array.from({length:n+1},(_,i)=>at(P,d,d.at(-1)*i/n));}
function area(P){return Math.abs(P.reduce((s,p,i)=>{const q=P[(i+1)%P.length];return s+p[0]*q[1]-p[1]*q[0];},0))/2;}
function regionsFrom(courses,seed){
 const rng=random(seed^0x93217),cs=courses.filter(c=>c.present?.length>1).map(c=>({...c,P:sample(c.present)})),options=[];
 for(let a=0;a<cs.length;a++)for(let b=a+1;b<cs.length;b++){
  const A=cs[a].P,B=cs[b].P;
  for(let i=5;i<A.length-5;i+=3)for(let j=5;j<B.length-5;j+=3){
   const gap=dist(A[i],B[j]);if(gap<5||gap>38)continue;
   const u=unit(sub(A[i+2],A[i-2])),v=unit(sub(B[j+2],B[j-2]));
   options.push({a,b,i,j,p:mul(add(A[i],B[j]),.5),reverse:dot(u,v)<0,score:gap+14*(1-Math.abs(dot(u,v)))+.035*dist(A[i],[150,109])});
  }
 }
 options.sort((a,b)=>a.score-b.score);const selected=[],used=new Set();
 for(const site of options){
  const pair=`${site.a}:${site.b}`;if(used.has(pair)||selected.some(r=>dist(r.center,site.p)<40))continue;
  const A=cs[site.a].P,B=site.reverse?cs[site.b].P.slice().reverse():cs[site.b].P,da=measure(A),db=measure(B),j=site.reverse?B.length-1-site.j:site.j;
  const half=Math.min(70,25+rng()*40,da.at(-1)*.32,db.at(-1)*.32);if(half<14)continue;
  const da0=Math.max(0,da[site.i]-half),da1=Math.min(da.at(-1),da[site.i]+half),db0=Math.max(0,db[j]-half),db1=Math.min(db.at(-1),db[j]+half);
  const count=Math.max(40,Math.ceil(Math.max(da1-da0,db1-db0)/.65));
  const left=Array.from({length:count},(_,k)=>at(A,da,da0+(da1-da0)*k/(count-1))),right=Array.from({length:count},(_,k)=>at(B,db,db0+(db1-db0)*k/(count-1)));
  const polygon=left.concat(right.slice().reverse()),surface=area(polygon);if(surface<100||surface>6500)continue;
  selected.push({courseIds:[cs[site.a].id,cs[site.b].id],center:site.p,left,right,polygon,areaMm2:surface});used.add(pair);if(selected.length>=3)break;
 }
 return selected;
}
function maskFor(courses){
 const grid=new Map(),cell=2;
 for(const c of courses)for(const p of sample(c.present,.5)){const key=`${Math.floor(p[0]/cell)},${Math.floor(p[1]/cell)}`;if(!grid.has(key))grid.set(key,[]);grid.get(key).push(p);}
 return p=>{const x=Math.floor(p[0]/cell),y=Math.floor(p[1]/cell);for(let i=-1;i<=1;i++)for(let j=-1;j<=1;j++)for(const q of grid.get(`${x+i},${y+j}`)||[])if(dist(p,q)<.55)return true;return false;};
}
function clipped(P,blocked){
 const pieces=[];let cur=[];for(const p of sample(P,.35)){
  if(p[0]<1||p[0]>299||p[1]<1||p[1]>217||blocked(p)){if(cur.length>5)pieces.push(cur);cur=[];}else cur.push(p);
 }
 if(cur.length>5)pieces.push(cur);return pieces.filter(s=>measure(s).at(-1)>2);
}
function bandStrokes(region,spacing){
 const {left:A,right:B}=region,gap=A.reduce((m,p,i)=>Math.max(m,dist(p,B[i])),0),count=Math.ceil(gap/spacing),strokes=[];
 for(let k=1;k<count;k++){
  const t=k/count;
  // Skew the interpolation along the span: it draws through a shared interval,
  // not an equal-width echo pasted beside either individual course.
  const P=A.map((p,i)=>{const s=i/(A.length-1),u=t+.18*Math.sin(Math.PI*s)*Math.sin(Math.PI*t)*(t-.5);return add(mul(p,1-u),mul(B[i],u));});
  strokes.push(P);
 }
 return strokes;
}
function pocketStrokes(region,spacing){
 const {polygon:P,left:A,right:B}=region,u=unit(sub(add(A.at(-1),B.at(-1)),add(A[0],B[0]))),v=[-u[1],u[0]],Q=P.map(p=>[dot(p,u),dot(p,v)]);
 const lo=Math.min(...Q.map(p=>p[1])),hi=Math.max(...Q.map(p=>p[1])),strokes=[];
 for(let y=lo+spacing;y<hi;y+=spacing){
  const xs=[];for(let i=0;i<Q.length;i++){const a=Q[i],b=Q[(i+1)%Q.length];if((a[1]>y)!==(b[1]>y))xs.push(a[0]+(b[0]-a[0])*(y-a[1])/(b[1]-a[1]));}
  xs.sort((a,b)=>a-b);for(let i=0;i+1<xs.length;i+=2)if(xs[i+1]-xs[i]>2){const left=add(mul(u,xs[i]),mul(v,y)),right=add(mul(u,xs[i+1]),mul(v,y));strokes.push([left,right]);}
 }
 return strokes;
}
function bindFill(courses,seed,mode='bands',budgetMm=8000){
 if(!budgetMm||!courses.length)return{strokes:[],regions:[]};
 const regions=regionsFrom(courses,seed),blocked=maskFor(courses),strokes=[],records=[];
 const weights=[.55,.3,.15],total=weights.slice(0,regions.length).reduce((a,b)=>a+b,0);let used=0;
 for(let i=0;i<regions.length;i++){
  const region=regions[i],share=budgetMm*weights[i]/total,spacing=Math.max(.2,Math.min(1.2,region.areaMm2/share)),all=mode==='bands'?bandStrokes(region,spacing):pocketStrokes(region,spacing);
  let local=0,count=0;for(const P of all)for(const piece of clipped(P,blocked)){
   const mm=measure(piece).at(-1);if(local+mm>share||used+mm>budgetMm)continue;strokes.push(piece);local+=mm;used+=mm;count++;
  }
  records.push({courseIds:region.courseIds,center:region.center,areaMm2:region.areaMm2,spacingMm:spacing,inkMm:local,strokes:count,polygon:region.polygon});
 }
 return{strokes,regions:records};
}
module.exports={bindFill};
