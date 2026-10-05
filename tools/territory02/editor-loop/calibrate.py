"""An actual omission counterfactual, separate from the maker population."""
from pathlib import Path
import json
from render import render
root=Path(__file__).resolve().parent
source=json.loads((root/'inputs/S1.json').read_text());kept=[];removed=[]
for i,line in enumerate(source['strokes']):
    cx=sum(p[0] for p in line)/len(line);cy=sum(p[1] for p in line)/len(line)
    if 130<cx<207 and 35<cy<96:removed.append(i)
    else:kept.append(line)
variant={**source,'id':'calibration-omission','parent':'S1','strokes':kept}
for label,data in [('V',variant),('W',source)]:
    render(data,root/f'evidence/calibration-{label}')
    render(data,root/f'evidence/calibration-{label}-close',[115,20,110,85])
(root/'calibration-manifest.json').write_text(json.dumps({'V':'S1 with whole strokes removed by their sampled centroid in [130,35,207,96]','W':'unchanged S1','removedStrokeIndices':removed,'removedCount':len(removed),'limits':'Whole-stroke removal includes portions outside the selection rectangle; no claim of an exact rectangular erasure.'},indent=2)+'\n')
print('Calibration removed',len(removed),'whole strokes.')
