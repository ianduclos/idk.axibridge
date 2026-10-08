const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),assert=require('node:assert/strict');
const names=['t_head.js','t_flood.js','t_body.js','t_hand.js','t_forms.js','t_graph.js','t_v5.js','t_meander.js','t_density.js'];
const baselineDir=path.join(__dirname,'../../experiments/baseline');
function originalSource(){return names.map(f=>fs.readFileSync(path.join(baselineDir,f),'utf8')).join('');}
function makeEngine(){
 let code=originalSource();const marker='  if (prm.debug) this.meanderDebug =';assert.equal(code.split(marker).length,2);
 code=code.replace(marker,'  if (prm.debug) this.textureContext = { seed, prm, geo, chans, snaps, chi, junc, Ar, chiC };\n'+marker);
 code+='\nmodule.exports.texture = {densityPass,boxFilter,wrap,pointHash,workMap,renderField,activityField};\n';
 const filename=path.join(__dirname,'in-memory-engine.cjs'),local=new Module(filename,module);local.filename=filename;local._compile(code,filename);return local.exports;
}
const E=makeEngine();
const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
function geometry(P){
 const C=E.resample(P,.5),n=C.length,th=C.map((p,i)=>{const a=C[Math.max(0,i-2)],b=C[Math.min(n-1,i+2)];return Math.atan2(b[1]-a[1],b[0]-a[0]);});
 const kap=E.texture.boxFilter(th.map((t,i)=>E.texture.wrap(th[Math.min(n-1,i+4)]-th[Math.max(0,i-4)])/((Math.min(n-1,i+4)-Math.max(0,i-4))*.5||1)),16),major=E.texture.boxFilter(kap,120);
 return {C,th,nx:th.map(t=>-Math.sin(t)),ny:th.map(t=>Math.cos(t)),b:major.map(k=>Math.sign(k)||1)};
}
function regrowTexture(context,bare,first,seed,mode='grown'){
 assert(['grown','led'].includes(mode));if(!bare.courses.length)return{strokes:[],info:{}};
 const geo=new Map(bare.courses.map(c=>[c.id,geometry(c.present)]));
 const chans=bare.courses.map(c=>({...c,present:c.present.map(p=>p.slice()),drawn:true,abandoned:false}));
 const nearestCourse=P=>{const p=P[P.length>>1];let best=-1,minimum=Infinity;for(const[id,g]of geo)for(let i=0;i<g.C.length;i+=8){const d=distance(p,g.C[i]);if(d<minimum){minimum=d;best=id;}}return best;};
 const out=bare.strokes.map(P=>({core:-1,kind:'takeover-base',ch:nearestCourse(P),strokes:[P.map(p=>p.slice())]})),baseCount=out.length;
 const points=[];for(const[id,g]of geo)for(let i=0;i<g.C.length;i+=4)points.push([...g.C[i],id]);
 const grid=E.texture.pointHash(points,12),junc=(x,y,id,r=12)=>{const gx=Math.floor(x/12),gy=Math.floor(y/12);for(let u=-1;u<=1;u++)for(let v=-1;v<=1;v++)for(const q of(grid.get((gx+u)*4096+gy+v)||[]))if(q[2]!==id&&Math.hypot(q[0]-x,q[1]-y)<r)return true;return false;};
 let snaps=context.snaps,Ar=context.Ar,chi=context.chi,chiC=context.chiC;
 if(mode==='led'){
  snaps=[];
  for(const c of chans){
   const candidates=first.courses.filter(old=>old.sourceIds.some(id=>c.sourceIds.includes(id))),prior=(candidates.length?candidates:first.courses).map(old=>({old,P:E.resample(old.present,4)}));
   const C=geo.get(c.id).C;
   // This is geometric change since the first rewrite, not simulation velocity.
   const speed=C.map(p=>{let d=30;for(const old of prior)for(const q of old.P)d=Math.min(d,distance(p,q));return .1+d;});
   snaps.push({ch:c.id,t:2,pts:C.map(p=>p.slice()),speed});
   const middle=C[C.length>>1],ancestor=prior.sort((a,b)=>distance(middle,a.P[a.P.length>>1])-distance(middle,b.P[b.P.length>>1]))[0];
   if(ancestor)snaps.push({ch:c.id,t:1,pts:ancestor.P.map(p=>p.slice()),speed:ancestor.P.map(()=>.1)});
  }
  const work=E.texture.workMap(snaps,{x0:0,y0:0,x1:300,y1:218});Ar=(x,y)=>.12+.88*work.at(x,y)**2;
  const pivot=bare.pivot||[150,109];chiC=[{x:pivot[0],y:pivot[1],r:35}];chi=(x,y)=>Math.max(0,1-Math.hypot(x-pivot[0],y-pivot[1])/35);
 }
 // Keep the earlier texture generator, its finish and full recipe unchanged.
 // Rebuild its geometry and occupancy from the actual new drawing. The led
 // alternative additionally replaces inherited activity/history coordinates.
 const info=E.texture.densityPass({seed,prm:{...context.prm,density:1},out,geo,chans,snaps,Ar,chi,chiC,junc});
 return {strokes:out.slice(baseCount).flatMap(l=>l.strokes),layers:out.slice(baseCount).map(l=>({kind:l.kind,strokes:l.strokes})),info};
}
module.exports={E,originalSource,regrowTexture};
