"""Rasterize our generated polyline SVGs as drawings; no browser navigation."""
from pathlib import Path
import re,json,math,sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

root=Path(__file__).resolve().parent/'evidence'
records=[]
for f in [root/'checks.json',root/'checks-holdouts.json']:
 if f.exists():records.extend(json.loads(f.read_text()))
assert records, 'Render a complete population before rasterization'
if '--calibration-only' in sys.argv: records=[]
labels={'original':'J','bare':'C','bands':'F','pockets':'S'}

def paths(file):
 text=file.read_text();box=[float(x) for x in re.search(r'viewBox="([^"]+)"',text)[1].split()]
 result=[]
 for match in re.finditer(r'<path d="([^"]+)"',text):
  values=[float(x) for x in re.findall(r'-?\d+(?:\.\d+)?',match[1])]
  result.append(list(zip(values[::2],values[1::2])))
 return box,result

def draw(ax,file,pixel_width):
 box,lines=paths(file);x,y,w,h=box
 ax.set_xlim(x,x+w);ax.set_ylim(y+h,y);ax.set_aspect('equal');ax.set_facecolor('#FFFCF0')
 # Width in physical mm translated into points at this raster's pixels/mm.
 ax.add_collection(LineCollection(lines,colors='#100F0F',linewidths=.1*pixel_width/w*72/100,antialiased=True,capstyle='round',joinstyle='round'))
 ax.set_xticks([]);ax.set_yticks([])
 for spine in ax.spines.values():spine.set_color('#CECDC3');spine.set_linewidth(.5)

for holdout in [False,True]:
 seeds=sorted({r['seed'] for r in records if r['holdout']==holdout})
 if not seeds:continue
 for level in ['light','dense']:
  for mode,label in labels.items():
   fig,axes=plt.subplots(math.ceil(len(seeds)/3),3,figsize=(18,math.ceil(len(seeds)/3)*4.8),dpi=100,squeeze=False);fig.patch.set_facecolor('white')
   for ax,seed in zip(axes.flat,seeds):
    draw(ax,root/f'{seed}-{level}-{mode}.svg',560);ax.set_title(f'{label} · {seed}',loc='left',fontsize=11)
   for ax in list(axes.flat)[len(seeds):]:ax.set_visible(False)
   fig.suptitle(f'{label} · {level} · {"heldout" if holdout else "development"}',x=.025,ha='left',fontsize=13)
   fig.subplots_adjust(left=.018,right=.991,bottom=.02,top=.94,wspace=.03,hspace=.13)
   fig.savefig(root/f'{label}-{level}-{"heldout" if holdout else "development"}.png');plt.close(fig)
 for seed in seeds:
  for level in ['light','dense']:
   for mode,label in labels.items():
    f=root/f'{seed}-{level}-{mode}-close.svg';fig,ax=plt.subplots(figsize=(12,8.4),dpi=100);fig.subplots_adjust(left=0,right=1,bottom=0,top=1);draw(ax,f,1200);fig.savefig(root/f'{label}-{seed}-{level}-close.png');plt.close(fig)
for label in ['D','H','R']:
 f=root/f'calibration-{label}.svg'
 if f.exists():
  fig,ax=plt.subplots(figsize=(12,8.4),dpi=100);fig.subplots_adjust(left=0,right=1,bottom=0,top=1);draw(ax,f,1200);fig.savefig(f.with_suffix('.png'));plt.close(fig)
print('Whole-population sheets and matched details rasterized directly from current vectors.')
