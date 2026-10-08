// Shared neutral evidence renderer. Never changes engine files.
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const seeds = [5, 13, 18, 24, 47, 82];
const recipe = JSON.parse(fs.readFileSync(path.join(root, 'full.json'))).prm;
const palette = {paper:'#FFFCF0',ink:'#100F0F',ui:'#CECDC3'};
const svg = (strokes, box=[0,0,300,218]) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box.join(' ')}"><rect x="${box[0]}" y="${box[1]}" width="${box[2]}" height="${box[3]}" fill="${palette.paper}"/><g fill="none" stroke="${palette.ink}" stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round">${strokes.map(st=>`<path d="M${st.map(p=>p.map(n=>n.toFixed(3)).join(' ')).join(' L')}"/>`).join('')}</g></svg>`;
const html = (title,cells,cols=3) => `<!doctype html><meta charset="utf-8"><title>${title}</title><style>body{margin:0;padding:18px;background:#fff;color:${palette.ink};font:13px system-ui}h1{font-size:16px}.grid{display:grid;grid-template-columns:repeat(${cols},1fr);gap:16px}figure{margin:0}svg{display:block;width:100%;border:1px solid ${palette.ui}}figcaption{margin-top:5px}</style><h1>${title}</h1><div class="grid">${cells.map(c=>`<figure>${c.svg}<figcaption>${c.id}</figcaption></figure>`).join('')}</div>`;
const run = (engine, seed, mode) => {const sh=engine.randomSheet(seed);return engine.runTerritory(sh.cores,{...recipe,density:mode==='sparse'?0:1,camps:Math.max(2,sh.camps)},seed,'reversed');};
const round = process.argv[2] || 'round1';
const out = path.join(root,'evidence',round); fs.mkdirSync(out,{recursive:true});
const variants=process.argv.slice(3);
const names=variants.length?variants:['baseline','pace','silhouette','void'];
// Mechanism names live only in the withheld manifest, not on the review sheets.
const labels={baseline:'M',pace:'R',silhouette:'K',void:'P'};
const manifest=[];
for(const name of names){
 const current=path.join(root,'experiments',name);
 const snapshot=name==='baseline'?current:round==='round1'?path.join(current,name==='pace'?'round1':'round1-source'):path.join(current,`${round}-source`);
 const fallback=name!=='baseline'?path.join(root,'experiments','baseline'):current;
 const parts=['t_head.js','t_flood.js','t_body.js','t_hand.js','t_forms.js','t_graph.js','t_v5.js','t_meander.js',...(name==='void'&&round!=='round3'?['t_void.js']:[]),'t_density.js'];
 const source=parts.map(file=>fs.readFileSync(fs.existsSync(path.join(snapshot,file))?path.join(snapshot,file):path.join(fallback,file),'utf8')).join('');
 const compiled={exports:{}};new Function('module',source)(compiled);const engine=compiled.exports;
 const label=labels[name]||name;
 for(const mode of ['sparse','full']){
  const cells=[], metrics=[];
  for(const seed of seeds){
   const res=run(engine,seed,mode), strokes=res.lines.flatMap(l=>l.strokes);
   let mm=0, points=0;for(const st of strokes){points+=st.length;for(let i=0;i<st.length;i++){const p=st[i];if(p.length!==2||!p.every(Number.isFinite)||p[0]<0||p[0]>300||p[1]<0||p[1]>218)throw Error(`Invalid geometry ${name} ${mode} ${seed}: ${p}`);if(i)mm+=Math.hypot(p[0]-st[i-1][0],p[1]-st[i-1][1]);}}
   if(mm>100000.01)throw Error(`Ink exceeds 100m: ${name} ${seed}`);
   metrics.push({seed,points,strokes:strokes.length,mm:Math.round(mm)});
   const picture=svg(strokes); fs.writeFileSync(path.join(out,`${label}-${mode}-${seed}.svg`),picture);
   cells.push({id:`${label}-${mode}-${seed}`,svg:picture});
   if([13,18,47,82].includes(seed)){const box={13:[70,45,100,70],18:[145,95,100,70],47:[65,85,100,70],82:[95,60,100,70]}[seed];fs.writeFileSync(path.join(out,`${label}-${mode}-${seed}-close.html`),html(`${label}-${mode}-${seed}`, [{id:'100 × 70 mm close view',svg:svg(strokes,box)}],1));}
   if(mode==='sparse'&&[18,47].includes(seed)){const box=seed===18?[135,85,160,125]:[45,10,150,90];fs.writeFileSync(path.join(out,`${label}-${mode}-${seed}-course.html`),html(`${label}-${mode}-${seed} · course`, [{id:`${box[2]} × ${box[3]} mm common course window`,svg:svg(strokes,box)}],1));}
  }
  fs.writeFileSync(path.join(out,`${label}-${mode}.html`),html(`${label} · ${mode}`,cells));
  manifest.push({label,name,mode,metrics});
 }
}
fs.writeFileSync(path.join(out,'withheld-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(`Rendered ${manifest.length} matched populations in ${out}`);
