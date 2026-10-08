const {E,regrowTexture}=require('../texture/regrow.cjs'),{rewriteChannels}=require('../rewrite.cjs');
const add=(a,b)=>[a[0]+b[0],a[1]+b[1]],sub=(a,b)=>[a[0]-b[0],a[1]-b[1]],mul=(a,s)=>[a[0]*s,a[1]*s],dot=(a,b)=>a[0]*b[0]+a[1]*b[1],dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const unit=v=>mul(v,1/(Math.hypot(...v)||1)),clamp=(x,a,b)=>Math.max(a,Math.min(b,x)),copy=x=>JSON.parse(JSON.stringify(x));
function rng(seed){let a=seed>>>0;return()=>{a+=0x6D2B79F5;let t=a;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296;};}
function measure(P){const s=[0];for(let i=1;i<P.length;i++)s.push(s.at(-1)+dist(P[i],P[i-1]));return s;}
function at(P,s,x){x=clamp(x,0,s.at(-1));let i=1;while(i<s.length-1&&s[i]<x)i++;return add(P[i-1],mul(sub(P[i],P[i-1]),(x-s[i-1])/(s[i]-s[i-1]||1)));}
function nearest(P,p){let best={distance:Infinity,index:0,point:P[0]};for(let i=1;i<P.length;i++){const u=sub(P[i],P[i-1]),t=clamp(dot(sub(p,P[i-1]),u)/(dot(u,u)||1),0,1),q=add(P[i-1],mul(u,t)),d=dist(q,p);if(d<best.distance)best={distance:d,index:i-1,t,point:q,tangent:unit(u)};}return best;}
function clip(strokes,minLength=1){const out=[];for(const P of strokes){let piece=[];const flush=()=>{if(piece.length>1&&E.polyLen(piece)>=minLength)out.push(piece);piece=[];};for(const p of P){if(Number.isFinite(p[0])&&Number.isFinite(p[1])&&p[0]>=1&&p[0]<=299&&p[1]>=1&&p[1]<=217)piece.push(p.slice());else flush();}flush();}return out;}
function input(seed){const sheet=E.randomSheet(seed),prm={...require('../../full.json').prm,camps:Math.max(2,sheet.camps),density:0,debug:true},source=E.runTerritory(sheet.cores,prm,seed,'reversed'),first=rewriteChannels(source.T.meanderDebug.chans,seed,1),bare=rewriteChannels(first.courses,seed,2),context=source.T.textureContext,texture=regrowTexture(context,bare,first,seed,'led');return{seed,bare,first,texture,context};}
module.exports={E,regrowTexture,input,add,sub,mul,dot,dist,unit,clamp,copy,rng,measure,at,nearest,clip};
