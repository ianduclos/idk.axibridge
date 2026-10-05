// Reproducible neutral images for a bounded second-eye reading.
const fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'evidence'),out=path.join(root,'blind-bulbs');fs.mkdirSync(out,{recursive:true});
const labels={U:2,Q:0,W:1};
const page=(title,cells)=>`<!doctype html><meta charset="utf-8"><title>${title}</title><style>body{margin:18px;font:13px system-ui}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}figure{margin:0}svg{display:block;width:100%;border:1px solid #CECDC3}h1{font-size:16px}</style><h1>${title}</h1><div class="grid">${cells.join('')}</div>`;
for(const [label,stage] of Object.entries(labels)){
 for(const [suffix,seeds] of [['development',[5,13,18,24,47,82]],['heldout',[107,173,227,281]]]){
  const cells=seeds.map(seed=>`<figure>${fs.readFileSync(path.join(root,`${seed}-${stage}.svg`),'utf8')}<figcaption>${label} · ${seed}</figcaption></figure>`);
  fs.writeFileSync(path.join(out,`${label}-${suffix}.html`),page(`${label} · ${suffix}`,cells));
 }
 for(const seed of [13,47,82,107,227])for(const kind of ['','-close'])fs.copyFileSync(path.join(root,`${seed}-${stage}${kind}.svg`),path.join(out,`${label}-${seed}${kind}.svg`));
}
fs.writeFileSync(path.join(root,'blind-bulbs-manifest.json'),JSON.stringify({labels,selectedCloseSeeds:[13,47,82,107,227]},null,2)+'\n');
console.log('Current neutral populations and matched details prepared.');
