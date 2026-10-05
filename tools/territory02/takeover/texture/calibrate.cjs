const fs=require('node:fs'),path=require('node:path'),root=path.join(__dirname,'evidence'),records=require('./evidence/checks.json');
const record=records.find(r=>r.seed===13&&r.mode==='grown'),bare=records.find(r=>r.seed===13&&r.mode==='bare');
const grow=record.layers.findIndex(l=>l.kind==='d-grow'),start=bare.strokes+record.layers.slice(0,grow).reduce((n,l)=>n+l.strokes,0),count=record.layers[grow].strokes;
for(const suffix of ['', '-close']){
 const source=fs.readFileSync(path.join(root,`13-grown${suffix}.svg`),'utf8'),paths=[...source.matchAll(/<path[^>]*\/>/g)].map(m=>m[0]);
 let removed=source;for(let i=start;i<start+count;i++)removed=removed.replace(paths[i],'');
 fs.writeFileSync(path.join(root,`calibration-D${suffix}.svg`),removed);fs.writeFileSync(path.join(root,`calibration-H${suffix}.svg`),source);fs.writeFileSync(path.join(root,`calibration-R${suffix}.svg`),fs.readFileSync(path.join(root,`13-bare${suffix}.svg`)));
}
fs.writeFileSync(path.join(root,'calibration-manifest.json'),JSON.stringify({D:'Seed13 regrown texture without d-grow layer',H:'Full regrown texture13',R:'All texture removed, same base curves',removedGrowStrokes:count},null,2)+'\n');
