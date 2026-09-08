'use strict';
require('./geometry.js');
const assert=require('node:assert/strict');
const R=globalThis.RibbonStudy;
for(const seed of [7,8,19,43]) {
 const p=R.crestProfile(620,{seed,wavelength:120,spacingVariation:1,heightVariation:1,phrasing:.7});
 const raw=at=>{let i=0;while(i<p.knots.length-2&&p.knots[i+1].s<at)i++;const a=p.knots[i],b=p.knots[i+1];const t=Math.max(0,Math.min(1,(at-a.s)/(b.s-a.s)));return a.v+(b.v-a.v)*t*t*(3-2*t);};
 assert.equal(p(0),0);assert.equal(p(620),0);
 let before=0,after=0;
 for(let s=.1;s<620;s+=.1){before=Math.max(before,Math.abs(raw(s)-raw(s-.1))/.1);after=Math.max(after,Math.abs(p(s)-p(s-.1))/.1);}
 assert.ok(after<before*.97,'steepest transition is softened');
 const d2=(s,h)=>(p(s+h)-2*p(s)+p(s-h))/(h*h);
 for(const k of p.knots.slice(1,-1)) {
   assert.ok(Math.abs(d2(k.s-.001,.0005)-d2(k.s+.001,.0005))<.0001,'curvature joins continuously at former knots');
 }
 for(let s=0;s<=620;s+=.25)assert.ok(p(s)>=0&&p(s)<=1,'smoothing preserves width bounds');
}
console.log('crest-smoothing-check: lower maximum slopes, continuous knot curvature, endpoints and bounds passed');
