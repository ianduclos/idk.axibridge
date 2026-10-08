const fs=require('fs');
for(const recipe of ['sparse','full']){const cfg=JSON.parse(fs.readFileSync('../../'+recipe+'.json'));cfg.cells.push(...[47,82].map(seed=>({id:String(seed),random:seed,order:'reversed'})));cfg.cols=3;fs.writeFileSync('population-'+recipe+'.json',JSON.stringify(cfg,null,2));}
