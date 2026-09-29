// node sheet.js config.json out.html  — contact sheet of SVG cells.
const fs=require('fs'); const E=require('./territory-engine.js');
const cfg=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');
const svgOf=(res,opt)=>{
  const paths=res.lines.flatMap(l=>l.strokes).map(st=>`<path d="M${st.map(p=>p[0].toFixed(2)+' '+p[1].toFixed(2)).join(' L')}"/>`).join('');
  let ghosts='';
  if(opt.cores){const col=['#878580','#24837B','#BC5215','#5E409D'];ghosts=res.cores.map(c=>`<path d="M${c.pts.map(p=>p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' L')}" stroke="${col[c.camp]}" stroke-dasharray="${c.camp===0?'0.6 1.4':'2 1.5'}" opacity=".8"/>`).join('');}
  return `<svg viewBox="0 0 300 218" xmlns="http://www.w3.org/2000/svg"><rect width="300" height="218" fill="#FFFCF0"/><g fill="none" stroke-width="0.5" stroke-linecap="round">${ghosts}</g><g fill="none" stroke="#100F0F" stroke-width="${cfg.w||0.45}" stroke-linecap="round" stroke-linejoin="round">${paths}</g></svg>`;
};
let cells='';
for(const c of cfg.cells){
  const prm={...cfg.prm,...(c.prm||{})};
  let cores;
  if(c.random){const sh=E.randomSheet(c.random); cores=sh.cores; if(!c.prm||c.prm.camps===undefined) prm.camps=Math.max(2,sh.camps);}
  else if(c.example) cores=E.exampleSheet();
  else cores=c.cores;
  const res=E.runTerritory(cores,prm,c.seed||c.random||1,c.order||(c.reverse?'reversed':'drawn'));
  cells+=`<figure><div class="svg">${svgOf(res,{cores:cfg.cores})}</div><figcaption><b>${esc(c.id)}</b>${cfg.captions&&c.cap?' · '+esc(c.cap):''}${cfg.flags&&res.meander?' · '+esc(res.meander.flags||'ok')+' · '+res.meander.inkMm+'mm'+(res.meander.white?' · W':''):''}</figcaption></figure>`;
}
fs.writeFileSync(process.argv[3],`<!doctype html><meta charset="utf-8"><style>body{margin:0;padding:18px;background:#fff;font:13px ui-monospace,Menlo,monospace;color:#100F0F}h1{font:600 16px system-ui;margin:0 0 12px}.g{display:grid;grid-template-columns:repeat(${cfg.cols||4},1fr);gap:14px}figure{margin:0}.svg svg{width:100%;display:block;border:1px solid #CECDC3}figcaption{margin-top:4px}</style><h1>${esc(cfg.title||'')}</h1><div class="g">${cells}</div>`);
