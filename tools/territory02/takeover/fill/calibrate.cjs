const fs=require('fs'),path=require('path');const root=path.join(__dirname,'evidence'),records=require('./evidence/checks.json'),record=records.find(r=>r.seed===13&&r.level==='light'&&r.mode==='bands'),bare=records.find(r=>r.seed===13&&r.level==='light'&&r.mode==='bare');
const source=fs.readFileSync(path.join(root,'13-light-bands-close.svg'),'utf8'),paths=[...source.matchAll(/<path[^>]*\/>/g)].map(m=>m[0]);
const remove=(a,b)=>{let text=source;for(let i=a;i<b;i++)text=text.replace(paths[i],'');return text;};
fs.writeFileSync(path.join(root,'calibration-D.svg'),remove(bare.strokes,bare.strokes+record.regions[0].strokes));
fs.writeFileSync(path.join(root,'calibration-H.svg'),source);
fs.writeFileSync(path.join(root,'calibration-R.svg'),remove(bare.strokes,paths.length));
fs.writeFileSync(path.join(root,'calibration-manifest.json'),JSON.stringify({D:'Band fill13 light without principal region',H:'Band fill13 light unchanged',R:'Same courses without any fill',baseStrokes:bare.strokes,removedPrincipalFillStrokes:record.regions[0].strokes},null,2)+'\n');
