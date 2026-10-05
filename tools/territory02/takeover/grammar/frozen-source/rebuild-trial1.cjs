// A separate exploratory path process. The old cubic inflation, contact hub,
// restatement and radial-thorn routines are not called by this constructor.
const {E,rng,measure,at,add,sub,mul,unit,dot,dist,clamp,clip}=require('../material/common.cjs');
const {regrowTexture}=require('../texture/regrow.cjs');
const wrap=a=>Math.atan2(Math.sin(a),Math.cos(a));
function rebuild(I){
 const R=rng(I.seed^0x7ac82),sources=I.bare.courses,paths=[],courses=[],events=[],occupied=[];
 const count=5+Math.floor(R()*5);
 for(let k=0;k<count;k++){
  const source=sources[Math.floor(R()*sources.length)],S=measure(source.present),u=.12+R()*.76,origin=at(source.present,S,S.at(-1)*u);
  const a=at(source.present,S,S.at(-1)*u-2),b=at(source.present,S,S.at(-1)*u+2);
  let heading=Math.atan2(b[1]-a[1],b[0]-a[0])+(R()-.5)*1.8;
  // Source location is a memory, not an endpoint constraint. New courses can
  // migrate, stop early, or encounter an unrelated earlier course.
  let p=[clamp(origin[0]+(R()-.5)*65,30,270),clamp(origin[1]+(R()-.5)*55,25,193)],P=[p.slice()];
  const episodes=3+Math.floor(R()*6),turnBias=R()<.5?-1:1;let prevTurn=0;
  for(let phase=0;phase<episodes;phase++){
   const length=8+Math.pow(R(),1.5)*85,turn=(R()<.25?0:(R()<.64?turnBias:-turnBias)*(.35+R()*3.1));
   const concentration=.15+R()*.73,centre=.12+R()*.76,power=.8+R()*3.5;
   const steps=Math.ceil(length/.45),weights=Array.from({length:steps},(_,i)=>Math.exp(-Math.pow(Math.abs((i/(steps-1)-centre)/concentration),power)*2));
   const sum=weights.reduce((a,b)=>a+b,0)||1;
   const corner=phase>0&&R()<.18?(R()<.5?-1:1)*(.35+R()*1.5):0;
   heading+=corner;const start=p.slice();let contact=null;
   for(let j=0;j<steps;j++){
    heading+=turn*weights[j]/sum;
    // Earlier material alters a local passage without creating a shared hub.
    let nearest=null,d=7;
    for(const q of occupied){const dd=dist(q.p,p);if(dd<d){d=dd;nearest=q;}}
    if(nearest&&j%3===0){
     const direction=dot([Math.cos(heading),Math.sin(heading)],nearest.t)<0?mul(nearest.t,-1):nearest.t;
     const target=Math.atan2(direction[1],direction[0]);heading+=wrap(target-heading)*.10*(1-d/7);
     if(!contact)contact={at:p.slice(),other:nearest.id};
    }
    const step=length/steps,q=add(p,mul([Math.cos(heading),Math.sin(heading)],step));
    if(q[0]<6||q[0]>294||q[1]<6||q[1]>212)break;
    p=q;P.push(p.slice());
   }
   events.push({course:k,phase,start,end:p.slice(),length,turn,concentration,corner,contact});
   if(dist(start,p)<.2)break;
   // A decision to leave is allowed; no endpoint is forced back to its source.
   if(phase>1&&R()<.12)break;
   prevTurn=turn;
  }
  if(E.polyLen(P)<18)continue;
  paths.push(P);courses.push({id:courses.length,cls:k<2?'trunk':'branch',present:P,sourceIds:source.sourceIds.slice()});
  for(let j=2;j<P.length;j+=6)occupied.push({id:k,p:P[j],t:unit(sub(P[j],P[j-2]))});
 }
 return {strokes:clip(paths,.8),courses,pivot:courses[0]?.present[Math.floor(courses[0].present.length*.5)]||[150,109],events};
}
function develop(I){
 const bare=rebuild(I),context={...I.context,prm:{...I.context.prm,continue:0,slash:0,surprise:0,planes:0,cover:.32,ink:24}};
 const texture=regrowTexture(context,bare,I.bare,I.seed,'led');
 return {bare,texture,strokes:bare.strokes.concat(texture.strokes),events:bare.events,info:{textureLayers:texture.layers.map(l=>l.kind),thorn:false,oldCurveFitter:false}};
}
module.exports={rebuild,develop};
