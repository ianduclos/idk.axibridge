// Independent scaffold. No original Territory courses or ornament layers survive.
// The old generator is used only as a source of cropped d-grow grain.
const {input,rng,dist,add,sub,mul,unit,dot,measure,at,clip,E}=require('../material/common.cjs');
const cache=new Map();
function grain(seed){
  if(!cache.has(seed)){
    const I=input(seed),layer=I.texture.layers.find(x=>x.kind==='d-grow');
    cache.set(seed,(layer?.strokes||[]).map(P=>P.map(p=>p.slice())));
  }
  return cache.get(seed);
}
function cubic(a,b,c,d,n=100){return Array.from({length:n+1},(_,i)=>{
  const t=i/n,u=1-t;return[0,1].map(j=>u*u*u*a[j]+3*u*u*t*b[j]+3*u*t*t*c[j]+t*t*t*d[j]);
});}
const rotate=(p,a)=>[p[0]*Math.cos(a)-p[1]*Math.sin(a),p[0]*Math.sin(a)+p[1]*Math.cos(a)];
function length(P){return E.polyLen(P);}
function cut(P,lo,hi){const S=measure(P),out=[at(P,S,lo)];for(let i=1;i<P.length;i++)if(S[i]>lo&&S[i]<hi)out.push(P[i]);out.push(at(P,S,hi));return out;}
function makeScaffold(R,mode){
  const count=mode==='open'?3+Math.floor(R()*3):2+Math.floor(R()*3),paths=[];
  for(let k=0;k<count;k++){
    const n=3+Math.floor(R()*6),V=[[0,0]];let h=R()*Math.PI*2;
    for(let j=1;j<n;j++){
      // Directional runs, reversals, and discontinuities have no fixed alternation.
      const turn=R();h+=(turn<.26?(R()-.5)*.18:turn<.72?(R()-.5)*2.6:(R()<.5?-1:1)*(1.8+R()*1.1));
      V.push(add(V.at(-1),rotate([18+R()*62,0],h)));
    }
    const closed=mode==='body'&&R()<.60;
    if(closed)V.push(V[0].slice());
    let P=[V[0]],corners=0,straight=0;
    const tangents=V.map((v,i)=>unit(sub(V[Math.min(V.length-1,i+1)],V[Math.max(0,i-1)])));
    for(let j=1;j<V.length;j++){
      const a=V[j-1],b=V[j],d=dist(a,b),v=unit(sub(b,a)),normal=[-v[1],v[0]];
      const corner=R()<.36,kind=R();let Q;
      if(kind<.19){Q=[a,b];straight++;
      }else{
        const ia=corner?v:tangents[j-1],ib=R()<.35?v:tangents[j],side=R()<.5?-1:1;
        const bend=(kind<.48?.05:.25+R()*.75)*d*side;
        const c=add(add(a,mul(ia,d*(.06+Math.pow(R(),1.8)*1.05))),mul(normal,bend));
        const e=add(sub(b,mul(ib,d*(.025+Math.pow(R(),2)*.9))),mul(normal,bend*(R()<.35?-.4:.2+R())));
        Q=cubic(a,c,e,b,Math.max(25,Math.ceil(d/.35)));
      }
      if(corner)corners++;P.push(...Q.slice(1));
    }
    // Place the entire new course; old territory anchors are not constraints.
    const angle=(R()-.5)*Math.PI,P0=P.map(p=>rotate(p,angle));
    const xs=P0.map(p=>p[0]),ys=P0.map(p=>p[1]),xmin=Math.min(...xs),ymin=Math.min(...ys),w=Math.max(...xs)-xmin,hgt=Math.max(...ys)-ymin;
    const desiredW=65+R()*155,desiredH=60+R()*115,s=Math.min(desiredW/(w||1),desiredH/(hgt||1));
    const x=12+R()*(276-w*s),y=12+R()*(194-hgt*s);
    P=P0.map(p=>[x+(p[0]-xmin)*s,y+(p[1]-ymin)*s]);
    paths.push({P,closed,corners,straight});
  }
  return paths;
}
function cropGrain(source,R){
  // Rectangular source crop does not add rectangle outlines or close fragments.
  const pick=source[Math.floor(R()*source.length)];if(!pick)return[];
  const centre=pick[Math.floor(R()*pick.length)],angle=R()*Math.PI,halfX=7+R()*12,halfY=8+R()*14,out=[];
  for(const P of source){let Q=[];const flush=()=>{if(Q.length>1&&length(Q)>.25)out.push(Q);Q=[];};
    for(const p of P){const q=rotate(sub(p,centre),angle);if(Math.abs(q[0])<halfX&&Math.abs(q[1])<halfY)Q.push([(q[0]/halfX+1)*.5,q[1]/halfY]);else flush();}flush();
  }
  return out;
}
function generate(seed,mode='open'){
  if(!['open','body'].includes(mode))throw Error('Unknown mode');
  const R=rng(seed^(mode==='open'?0x67256a:0x267cdc)),routes=makeScaffold(R,mode),source=grain(seed),lines=[],material=[],events=[];
  for(let k=0;k<routes.length;k++){
    const route=routes[k],P=route.P,S=measure(P),L=S.at(-1);
    // Some lines stop or disappear inside the material. Not every body receives
    // a complete enclosing contour, and no new radial hub is constructed.
    const omit=mode==='body'&&R()<.3;
    if(!omit)lines.push(P);
    else{lines.push(cut(P,0,L*.26));lines.push(cut(P,L*.63,L));}
    const patches=mode==='open'?1+Math.floor(R()*3):2+Math.floor(R()*3);
    for(let m=0;m<patches;m++){
      const span=Math.min(L*.75,mode==='open'?18+R()*60:32+R()*85),start=R()*Math.max(0,L-span),side=R()<.5?-1:1;
      const width=mode==='open'?3+R()*14:13+R()*30,offset=mode==='open'?(R()<.5?0:10+R()*14):0;
      const phase=R()*6.28,bite=R()*.6,slant=(R()-.5)*.48,tiles=cropGrain(source,R);
      const frame=t=>{const x=start+t*span,p=at(P,S,x),v=unit(sub(at(P,S,x+.7),at(P,S,x-.7)));return{p,n:[-v[1],v[0]],v};};
      const widthAt=t=>width*(.42+.5*Math.sin(Math.PI*(t*.82+.08))+.19*Math.sin(t*9+phase))*(t>.38&&t<.61?1-bite:1);
      const warp=(t,u)=>{const f=frame(Math.max(0,Math.min(1,t))),w=widthAt(t),away=offset+(u+1)*.5*w;
        return add(add(f.p,mul(f.n,side*away)),mul(f.v,slant*u*w));};
      const moved=tiles.map(Q=>Q.map(([t,u])=>warp(t,u)));
      material.push(...moved);
      // A partial counter-edge makes one broad body without outlining every tile.
      if(mode==='body'&&R()<.56){const edge=[];for(let j=0;j<=100;j++)edge.push(warp(j/100,1));lines.push(edge);}
      events.push({route:k,start,span,width,offset,sourceFragments:tiles.length});
    }
  }
  // Short rough lines can escape a body along its own tangent. They are actual
  // atlas fragments, not spokes issuing from a common random centre.
  const cleanLines=clip(lines,.8),cleanMaterial=clip(material,.2);
  return {strokes:cleanLines.concat(cleanMaterial),lines:cleanLines,material:cleanMaterial,
    info:{seed,mode,routes:routes.length,corners:routes.reduce((n,r)=>n+r.corners,0),straightSpans:routes.reduce((n,r)=>n+r.straight,0),closed:routes.filter(r=>r.closed).length,events,sourceLayer:'d-grow only',oldScaffoldRetained:false,thornLayerRetained:false,slashLayerRetained:false}};
}
module.exports={generate};
