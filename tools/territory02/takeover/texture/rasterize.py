"""Rasterize generated vector drawings directly, without browser navigation."""
from pathlib import Path
import json, math, re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

root=Path(__file__).resolve().parent/'evidence'
records=[]
for f in [root/'checks.json',root/'checks-holdouts.json']:
 if f.exists(): records.extend(json.loads(f.read_text()))
assert records
labels={'baseline':'A','bare':'N','grown':'V','led':'B'}
def draw(ax,file,width):
 text=file.read_text();x,y,w,h=map(float,re.search(r'viewBox="([^"]+)"',text)[1].split());lines=[]
 for m in re.finditer(r'<path d="([^"]+)"',text):
  a=list(map(float,re.findall(r'-?\d+(?:\.\d+)?',m[1])));lines.append(list(zip(a[::2],a[1::2])))
 ax.set_xlim(x,x+w);ax.set_ylim(y+h,y);ax.set_aspect('equal');ax.set_facecolor('#FFFCF0');ax.set_xticks([]);ax.set_yticks([])
 ax.add_collection(LineCollection(lines,colors='#100F0F',linewidths=.1*width/w*72/100,antialiased=True,capstyle='round',joinstyle='round'))
 for s in ax.spines.values():s.set_color('#CECDC3');s.set_linewidth(.5)
for heldout in [False,True]:
 seeds=sorted({r['seed'] for r in records if r['holdout']==heldout})
 if not seeds:continue
 for mode,label in labels.items():
  fig,axes=plt.subplots(math.ceil(len(seeds)/3),3,figsize=(18,math.ceil(len(seeds)/3)*4.8),dpi=100,squeeze=False);fig.patch.set_facecolor('white')
  for ax,seed in zip(axes.flat,seeds):draw(ax,root/f'{seed}-{mode}.svg',560);ax.set_title(f'{label} · {seed}',loc='left',fontsize=11)
  for ax in list(axes.flat)[len(seeds):]:ax.set_visible(False)
  fig.suptitle(f'{label} · {"heldout" if heldout else "development"}',x=.025,ha='left',fontsize=13);fig.subplots_adjust(left=.018,right=.991,bottom=.02,top=.94,wspace=.03,hspace=.13)
  fig.savefig(root/f'{label}-{"heldout" if heldout else "development"}.png');plt.close(fig)
  for seed in seeds:
   fig,ax=plt.subplots(figsize=(12,8.4),dpi=100);fig.subplots_adjust(left=0,right=1,bottom=0,top=1);draw(ax,root/f'{seed}-{mode}-close.svg',1200);fig.savefig(root/f'{label}-{seed}-close.png');plt.close(fig)
for label in ['D','H','R']:
 for suffix in ['', '-close']:
  f=root/f'calibration-{label}{suffix}.svg'
  if f.exists():
   fig,ax=plt.subplots(figsize=(12,8.4),dpi=100);fig.subplots_adjust(left=0,right=1,bottom=0,top=1);draw(ax,f,1200);fig.savefig(f.with_suffix('.png'));plt.close(fig)
print('Vector populations and matched details rasterized with physical 0.1mm stroke width.')
