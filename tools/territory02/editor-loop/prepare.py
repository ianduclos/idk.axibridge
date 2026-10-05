"""Freeze the inspected earlier geometry verbatim at its recorded SVG precision."""
from pathlib import Path
import re,json,hashlib
from render import render
root=Path(__file__).resolve().parent
spec=[('S1',5,'pressure','Dense competing grain bodies, long courses and brittle crossings.'),('S2',24,'unravel','Less resolved: activity concentrated at right, sparse left and inherited radial crossings.')]
manifest=[]
for ident,seed,mode,reason in spec:
    source=root.parent/'takeover/material/evidence'/f'{seed}-{mode}.svg'
    text=source.read_text(); lines=[]
    for d in re.findall(r'<path d="([^"]+)"',text):
        n=list(map(float,re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?',d)));lines.append(list(map(list,zip(n[::2],n[1::2]))))
    data={'id':ident,'parent':None,'pageMm':[300,218],'strokeMm':.1,'strokes':lines,'source':{'seed':seed,'mode':mode,'path':str(source.relative_to(root.parent.parent.parent)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'precisionMm':.001},'selectionReason':reason}
    out=root/'inputs'/f'{ident}.json';out.write_text(json.dumps(data,separators=(',',':'))+'\n')
    render(data,out.with_suffix(''));render(data,root/'inputs'/f'{ident}-close',[100,74,100,70])
    manifest.append({k:v for k,v in data.items() if k!='strokes'}|{'geometrySha256':hashlib.sha256(json.dumps(lines,separators=(',',':')).encode()).hexdigest()})
(root/'inputs/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
