const fs=require('node:fs'),path=require('node:path'),{input}=require('./common.cjs'),{develop}=require('./unravel.cjs');
const I=input(5),R=develop(I),p=R.events[0].root,box=[Math.max(0,Math.min(200,p[0]-50)),Math.max(0,Math.min(148,p[1]-35)),100,70];
const variants={H:R.strokes,J:I.bare.strokes.concat(I.texture.strokes),P:R.stages.find(s=>s.key==='body-after').strokes};
for(const[label,strokes]of Object.entries(variants))for(const close of [false,true]){
 const b=close?box:[0,0,300,218],svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${b.join(' ')}"><rect x="${b[0]}" y="${b[1]}" width="${b[2]}" height="${b[3]}" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round">${strokes.map(P=>`<path d="M${P.map(p=>p.map(x=>x.toFixed(3)).join(' ')).join(' L')}"/>`).join('')}</g></svg>`;
 fs.writeFileSync(path.join(__dirname,'evidence',`calibration-${label}${close?'-close':''}.svg`),svg);
}
console.log('Calibration: same source, matched frame, altered continuation retained.');
