const H=require('../material/common.cjs');
const {E,rng,measure,at,nearest,add,sub,mul,unit,dot,dist,clip}=H;
const rotate=(v,a)=>[v[0]*Math.cos(a)-v[1]*Math.sin(a),v[0]*Math.sin(a)+v[1]*Math.cos(a)];
function cubic(A,B,C,D){const n=Math.max(16,Math.ceil((dist(A,B)+dist(B,C)+dist(C,D))/.35)),P=[];for(let i=0;i<=n;i++){const t=i/n,s=1-t;P.push([0,1].map(a=>s*s*s*A[a]+3*s*s*t*B[a]+3*s*t*t*C[a]+t*t*t*D[a]));}return P;}
function smoothPassage(P,a,b,R){
 const A=P[a],B=P[b],chord=sub(B,A),L=dist(A,B),t=unit(chord),n=[-t[1],t[0]],side=R()<.5?-1:1;
 const spread=35+R()*47,depth=26+R()*45;
 // These interior stations are unequal excursions away from an actual rough
 // interval. No reference-image points or fixed curve motif are reproduced.
 const stations=[A,add(add(A,mul(t,L*(.20+R()*.12))),mul(n,side*spread)),
  add(add(A,mul(t,L*(.43+R()*.18))),mul(n,-side*depth*.35)),
  add(add(A,mul(t,L*(.72+R()*.18))),mul(n,side*depth*(.4+R()*.7))),B];
 const tangent=stations.map((p,i)=>unit(sub(stations[Math.min(stations.length-1,i+1)],stations[Math.max(0,i-1)])));
 tangent[0]=unit(sub(P[Math.min(P.length-1,a+2)],P[Math.max(0,a-2)]));tangent[4]=unit(sub(P[Math.min(P.length-1,b+2)],P[Math.max(0,b-2)]));
 const corner=1+Math.floor(R()*3),turn=R()<.55?Math.PI*(.77+R()*.20):(.5+R()*.9),handles=[];let out=[];
 for(let i=0;i<stations.length-1;i++){
  const X=stations[i],Y=stations[i+1],d=dist(X,Y),u=i===corner?rotate(tangent[i],turn):tangent[i],v=i+1===corner?rotate(tangent[i+1],-turn*.35):tangent[i+1];
  const h1=d*(.18+R()*.99),h2=d*(i+1===corner?.025+R()*.07:.2+R()*.9);
  const C=add(X,mul(u,h1)),D=sub(Y,mul(v,h2));handles.push({C,D});out.push(...cubic(X,C,D,Y).slice(i?1:0));
 }
 // Uniformly contract displacement from the straight chord, not individual
 // coordinates, so the whole gesture fits without flattened boundary points.
 const S=measure(out);let factor=1;
 for(let i=0;i<out.length;i++){const q=add(A,mul(chord,S[i]/S.at(-1))),v=sub(out[i],q);for(let axis=0;axis<2;axis++){if(v[axis]>0)factor=Math.min(factor,((axis?211:293)-q[axis])/v[axis]);if(v[axis]<0)factor=Math.min(factor,((axis?7:7)-q[axis])/v[axis]);}}
 factor=Math.max(0,Math.min(1,factor));out=out.map((p,i)=>add(add(A,mul(chord,S[i]/S.at(-1))),mul(sub(p,add(A,mul(chord,S[i]/S.at(-1)))),factor)));
 return {P:out,factor,corner};
}
function prepare(seed,baseName){
 const I=H.input(seed),base=require('../material/'+baseName+'.cjs').develop(I),R=rng(seed^0x16acf3),smooth=[],used=new Set();
 const guides=I.bare.courses.slice().sort((a,b)=>E.polyLen(b.present)-E.polyLen(a.present));
 for(const guide of guides){
  if(smooth.length>=2)break;
  const targets=E.resample(guide.present,8);let best=null;
  for(let k=0;k<base.strokes.length;k++){
   if(used.has(k))continue;const P=base.strokes[k],L=E.polyLen(P);if(L<55||L>450||dist(P[0],P.at(-1))<20)continue;
   let error=0;for(let j=0;j<5;j++)error+=nearest(targets,P[Math.floor((P.length-1)*j/4)]).distance;
   if(!best||error<best.error)best={k,P,error};
  }
  if(!best)continue;used.add(best.k);const Q=E.resample(best.P,.7),S=measure(Q),L=S.at(-1);
  const start=L*(.08+R()*.08),end=L*(.78+R()*.14),a=S.findIndex(x=>x>=start),b=S.findIndex(x=>x>=end);if(b<=a||dist(Q[a],Q[b])<16)continue;
  const developed=smoothPassage(Q,a,b,R);if(developed.factor<.16)continue;
  smooth.push({...developed,sourceIndex:best.k,source:Q,start:a,end:b,oldInterval:Q.slice(a,b+1)});
 }
 return {seed,baseName,I,base,smooth};
}
module.exports={...H,prepare,cubic,rotate};
