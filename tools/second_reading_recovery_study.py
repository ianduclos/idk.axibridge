"""Recovered-baseline checks and fixed-prefix experiments; no hardware access."""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from axibridge.sources.second_reading import SecondReading,SecondReadingParams
from axibridge.sources._second_reading_experiment import fit_transform,transformed
from axibridge.model import Path as InkPath

import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,default=Path('shots/second-reading-recovery-final-0906'))
parser.add_argument('--before',action='store_true',help='Load the preserved pre-review geometry experiment')
args=parser.parse_args()
if args.before:
    import importlib.util
    import axibridge.sources as sources
    spec=importlib.util.spec_from_file_location('axibridge.sources._second_reading_experiment',
        Path(__file__).resolve().parents[1]/'shots/second-reading-recovery-0906/experiment-before.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    sys.modules[spec.name]=old;sources._second_reading_experiment=old
OUT=args.output
OUT.mkdir(parents=True,exist_ok=True)
module=SecondReading()
seeds=(1,4,12,23,42,91)

def draw(ax,paths,title,frame=(0,0,280,198)):
    for p in paths:
        x,y=zip(*p.points);ax.plot(x,y,color='#26241f',lw=.65)
    x,y,w,h=frame;ax.set(xlim=(x,x+w),ylim=(y+h,y),aspect='equal',title=title)
    ax.set_facecolor('#f7f4ee');ax.set_xticks([]);ax.set_yticks([])

def save(paths,name):
    lines=''.join('<polyline points="'+' '.join(f'{x:.6f},{y:.6f}' for x,y in p.points)+'"/>' for p in paths)
    (OUT/f'{name}.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 198"><g fill="none" stroke="#26241f" stroke-width="0.3">'+lines+'</g></svg>')

checks=[]
for f in sorted(Path('shots/second-reading-0905').glob('seed-*.json')):
    for i,r in enumerate(json.loads(f.read_text())):
        p=SecondReadingParams(**r['params'],reading='first',historical_stacks=True);new=module.generate(p).layers[0].paths
        old=[[(float(a),float(b)) for a,b in (v.split(',') for v in e.attrib['points'].split())] for e in ET.parse(f.with_name(f.stem+f'-{i}.svg')).getroot().iter() if e.tag.endswith('polyline')]
        assert len(new)==len(old) and all(len(a.points)==len(b) for a,b in zip(new,old))
        error=max(abs(x-y) for a,b in zip(new,old) for u,v in zip(a.points,b) for x,y in zip(u,v))
        assert error<=.00000051
        actual=module.trajectory(p).metadata[:p.turns+1]
        assert all(all(a.get(k)==v for k,v in b.items()) for a,b in zip(actual,r['decisions']))
        checks.append(dict(cell=f'{f.stem}-{i}',max_coordinate_error=error,decisions_match=True))
(OUT/'recovery-checks.json').write_text(json.dumps(checks,indent=2))
recipes=[]
for label,mode in [('A','first'),('B','shapes'),('C','relations')]:
    fig,axs=plt.subplots(6,4,figsize=(15,17))
    for row,seed in enumerate(seeds):
        events=[dict(kind='stroke',turn=5,points=[[42,147],[112,120],[184,138],[242,72]],smoothing=.6),dict(kind='controls',turn=6,reading=mode)]
        for col,turn in enumerate((5,6,8,12)):
            p=SecondReadingParams(seed=seed,turns=turn,events=events,reading='first',historical_stacks=True)
            paths=module.generate(p).layers[0].paths;cell=f'{label}{row+1}-{col+1}'
            draw(axs[row,col],paths,cell);save(paths,cell)
            recipes.append(dict(cell=cell,params=p.model_dump(),decisions=module.trajectory(p).metadata[:turn+1]))
            if row in (1,2,4) and col in (1,3):
                close,ax=plt.subplots(figsize=(8,6));draw(ax,paths,cell);close.savefig(OUT/f'{cell}.png',dpi=150);plt.close(close)
    fig.tight_layout();fig.savefig(OUT/f'sheet-{label}.png',dpi=120);plt.close(fig)
# Isolated human and exact before/input/answer views; gray prefix, black answer.
fig,axs=plt.subplots(6,5,figsize=(18,17))
for row,seed in enumerate(seeds):
    draw(axs[row,0],module.generate(SecondReadingParams(seed=seed,turns=4,reading='first',historical_stacks=True)).layers[0].paths,f'E{row+1}-before')
    human=[InkPath(points=[[42,147],[112,120],[184,138],[242,72]])]
    draw(axs[row,1],human,f'E{row+1}-input (raw)')
    for col,label in enumerate('ABC',2):
        r=next(r for r in recipes if r['cell']==f'{label}{row+1}-2');p=SecondReadingParams(**r['params'])
        draw(axs[row,col],module.trajectory(p).steps[6],f'E{row+1}-{label} answer')
fig.tight_layout();fig.savefig(OUT/'exchanges.png',dpi=120);plt.close(fig)
# Neutral calibration mapping deliberately kept in a separate file.
r=next(r for r in recipes if r['cell']=='B3-4');p=SecondReadingParams(**r['params']);tr=module.trajectory(p);raw=tr.state(12)
variants={'K':raw,'L':[InkPath(points=[(round(x/5)*5,round(y/5)*5) for x,y in p.points]) for p in raw],
          'M':[InkPath(points=[(x+(12 if i%2 else -12),y) for x,y in p.points]) for i,p in enumerate(raw)],
          'N':tr.state(5)+[p for chunk in tr.steps[7:13] for p in chunk]}
fig,axs=plt.subplots(2,2,figsize=(12,9))
for ax,(key,paths) in zip(axs.flat,variants.items()):
    draw(ax,paths,key);save(paths,key)
    close,a=plt.subplots(figsize=(8,6));draw(a,paths,key);close.savefig(OUT/f'{key}.png',dpi=140);plt.close(close)
fig.tight_layout();fig.savefig(OUT/'calibration.png',dpi=140);plt.close(fig)
(OUT/'calibration-key.json').write_text(json.dumps({'K':'B3-4 unchanged','L':'vertices snapped to 5mm grid','M':'successive paths translated alternately -12/+12mm in x','N':'turn 6 removed; later paths unchanged'},indent=2))
(OUT/'recipes.json').write_text(json.dumps(recipes,indent=2))
# Boundary comparison: same recipe, different boundaries. Whole-fit keeps raw ratios.
fig,axs=plt.subplots(3,3,figsize=(12,10))
for row,seed in enumerate((4,12,42)):
    for col,boundary in enumerate(('clip','contain','fit')):
        p=SecondReadingParams(seed=seed,turns=16,reading='shapes',boundary=boundary,scale=.9,historical_stacks=True)
        paths=module.generate(p).layers[0].paths;draw(axs[row,col],paths,f'F{row+1}-{col+1}');save(paths,f'F{row+1}-{col+1}')
fig.tight_layout();fig.savefig(OUT/'boundaries.png',dpi=140);plt.close(fig)
print(f'{len(checks)} historical cells verified; study written to {OUT}')
