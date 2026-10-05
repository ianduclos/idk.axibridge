const fs=require('node:fs'),path=require('node:path');const root=__dirname;
const E=require('./experiments/baseline/territory-engine.js');const prm=JSON.parse(fs.readFileSync(path.join(root,'sparse.json'))).prm;
const sh=E.randomSheet(13),res=E.runTerritory(sh.cores,{...prm,camps:Math.max(2,sh.camps)},13,'reversed');const original=res.lines.flatMap(l=>l.strokes);
const sparse=original.map(st=>{if(st.length<6)return st;let q=E.resample(st,9);for(let pass=0;pass<3;pass++)q=q.map((p,i)=>i===0||i===q.length-1?p:[(q[i-1][0]+2*p[0]+q[i+1][0])/4,(q[i-1][1]+2*p[1]+q[i+1][1])/4]);return q;});
const agitated=original.map((st,k)=>st.map((p,i)=>[Math.min(298,Math.max(2,p[0]+3*Math.sin(i*.5+k))),Math.min(216,Math.max(2,p[1]+2*Math.cos(i*.4+k)))]));
const cut=process.argv[2]==='calibration-r2'?[105,110,22]:[190,150,34];
const removed=[];for(const st of original){let q=[];for(const p of st){if(Math.hypot(p[0]-cut[0],p[1]-cut[1])<cut[2]){if(q.length>1)removed.push(q);q=[];}else q.push(p);}if(q.length>1)removed.push(q);}
const variants=[['C',removed],['A',original],['D',agitated],['B',sparse]];
const svg=st=>`<svg viewBox="0 0 300 218"><rect width="300" height="218" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width=".1" stroke-linecap="round" stroke-linejoin="round">${st.map(s=>`<path d="M${s.map(p=>p.map(n=>n.toFixed(2)).join(' ')).join(' L')}"/>`).join('')}</g></svg>`;
const out=path.join(root,'evidence',process.argv[2]||'calibration');fs.mkdirSync(out,{recursive:true});
fs.writeFileSync(path.join(out,'sheet.html'),`<!doctype html><meta charset="utf-8"><style>body{margin:0;padding:16px;font:14px system-ui}.g{display:grid;grid-template-columns:1fr 1fr;gap:16px}figure{margin:0}svg{width:100%;border:1px solid #CECDC3}</style><div class="g">${variants.map(([id,st])=>`<figure>${svg(st)}<figcaption>${id}</figcaption></figure>`).join('')}</div>`);
fs.writeFileSync(path.join(out,'withheld.json'),JSON.stringify({A:'original sparse seed 13',B:'coarsened and smoothed trajectories',C:`removed passage in radius${cut[2]}mm around${cut[0]},${cut[1]}`,D:'gratuitous short-wave point displacement'},null,2));
console.log('Calibration variants saved');
