import readline from 'node:readline';
import { bundleGeom, growField, rngFor, MEANDER_DEFAULTS, polyLen } from './renderer-engine.mjs';

export function render(input) {
  const P=input.points, cap=input.cap_mm;
  if (!Array.isArray(P) || P.some(p=>p.length!==2 || p.some(x=>!Number.isFinite(x)))) throw Error('invalid spine');
  if (P.length<2 || polyLen(P)<.001) return {bands:[],echoes:[],metrics:{reason:'degenerate',band_mm:0,echo_mm:0}};
  const speed=P.map((p,i)=>i?Math.hypot(p[0]-P[i-1][0],p[1]-P[i-1][1]):0);
  const seed=(input.seed*10007+input.batch)>>>0;
  const g=bundleGeom({id:0,cls:'trunk',S0:4},P,speed,()=>1,
    {...MEANDER_DEFAULTS,band:1,tangle:0},rngFor(seed,6165),{A:.35},null,null);
  const bands=g?g.strands.map(s=>s.pts):[];
  const base=bands.reduce((a,p)=>a+polyLen(p),0);
  const info={};
  const echoes=growField({seed,cap:Math.min(Math.max(0,cap-base),base*.75),mu:1,
    out:[{strokes:bands.length?bands:[P]}],layers:{},voidM:new Uint8Array(300*218),
    isJ:()=>false,T0:()=>1,Db:{d:new Float64Array(300*218).fill(1e3)},info});
  return {bands,echoes,metrics:{reason:g?'rendered':'short spine',band_mm:base,
    echo_mm:echoes.reduce((a,p)=>a+polyLen(p),0),grow:info.grow,recipe:'bundleGeom + growField'}};
}
if (process.argv[1]?.endsWith('/renderer.mjs')) {
  const rl=readline.createInterface({input:process.stdin});
  for await (const line of rl) {
    try { process.stdout.write(JSON.stringify(render(JSON.parse(line)))+'\n'); }
    catch(e) { process.stdout.write(JSON.stringify({error:e.stack})+'\n'); }
  }
}
