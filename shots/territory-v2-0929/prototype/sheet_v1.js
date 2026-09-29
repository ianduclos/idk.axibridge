// v1 Territory (B) on the same random sheets, as a control. Voids ignored (v1 had none).
const fs=require('fs'); const V1=require('./engine.js'); const E=require('./territory-engine.js');
const [,,label,out,title]=process.argv;
let cells='';
for(let i=1;i<=12;i++){
  const sh=E.randomSheet(i); const cores=sh.cores.filter(c=>c.kind!=='void').map(c=>c.pts);
  const res=V1.runProposal('B',cores,{loose:.5,dep:.35,yieldP:.5,wander:1,reach:9,attend:.5},i);
  const paths=res.skins.flatMap(s=>s.strokes).map(st=>`<path d="M${st.map(p=>p[0].toFixed(2)+' '+p[1].toFixed(2)).join(' L')}"/>`).join('');
  cells+=`<figure><div class="svg"><svg viewBox="0 0 300 218" xmlns="http://www.w3.org/2000/svg"><rect width="300" height="218" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width="0.45" stroke-linecap="round" stroke-linejoin="round">${paths}</g></svg></div><figcaption><b>${label}${i}</b></figcaption></figure>`;
}
fs.writeFileSync(out,`<!doctype html><meta charset="utf-8"><style>body{margin:0;padding:18px;background:#fff;font:13px ui-monospace,Menlo,monospace;color:#100F0F}h1{font:600 16px system-ui;margin:0 0 12px}.g{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}figure{margin:0}.svg svg{width:100%;display:block;border:1px solid #CECDC3}figcaption{margin-top:4px}</style><h1>${title}</h1><div class="g">${cells}</div>`);
