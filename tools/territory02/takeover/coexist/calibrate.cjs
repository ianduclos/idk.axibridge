const fs=require('fs'),path=require('path'),{prepare}=require('./common.cjs'),{develop}=require('./continuity.cjs');
const I=prepare(24,'unravel'),N=develop(I),W=require('./independent.cjs').develop(I),root=path.join(__dirname,'evidence');
const variants={D:N.strokes,E:N.stages.find(s=>s.key==='source-exchanged').strokes,F:W.strokes};
const focus=I.smooth[0].P[Math.floor(I.smooth[0].P.length/2)],box=[Math.max(0,Math.min(200,focus[0]-50)),Math.max(0,Math.min(148,focus[1]-35)),100,70];
for(const[label,strokes]of Object.entries(variants))for(const close of [false,true]){const b=close?box:[0,0,300,218];fs.writeFileSync(path.join(root,`calibration-${label}${close?'-close':''}.svg`),`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${b.join(' ')}"><rect x="${b[0]}" y="${b[1]}" width="${b[2]}" height="${b[3]}" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width="0.1">${strokes.map(P=>`<path d="M${P.map(p=>p.map(x=>x.toFixed(3)).join(' ')).join(' L')}"/>`).join('')}</g></svg>`);}
