"""Render generated polylines without browser navigation; same physical weight."""
from pathlib import Path
import re, math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
root=Path(__file__).resolve().parent/'evidence'
labels={'bare':'C','led':'T','opening':'L','pressure':'F','unravel':'R'}
def draw(ax,file,width):
 text=file.read_text(); x,y,w,h=map(float,re.search(r'viewBox="([^"]+)"',text)[1].split()); lines=[]
 for m in re.finditer(r'<path d="([^"]+)"',text):
  a=list(map(float,re.findall(r'-?\d+(?:\.\d+)?',m[1])));lines.append(list(zip(a[::2],a[1::2])))
 ax.set_xlim(x,x+w);ax.set_ylim(y+h,y);ax.set_aspect('equal');ax.set_facecolor('#FFFCF0');ax.set_xticks([]);ax.set_yticks([])
 ax.add_collection(LineCollection(lines,colors='#100F0F',linewidths=.1*width/w*72/100,antialiased=True,capstyle='round',joinstyle='round'))
 for s in ax.spines.values():s.set_color('#CECDC3');s.set_linewidth(.5)
for mode,label in labels.items():
 seeds=sorted(int(f.stem.split('-')[0]) for f in root.glob(f'*-{mode}.svg'))
 for fresh in [False,True]:
  group=[s for s in seeds if (s>=500)==fresh]
  if not group:continue
  rows=math.ceil(len(group)/3);fig,axes=plt.subplots(rows,3,figsize=(18,rows*4.8),dpi=100,squeeze=False);fig.patch.set_facecolor('white')
  for ax,seed in zip(axes.flat,group):draw(ax,root/f'{seed}-{mode}.svg',560);ax.set_title(f'{label} · {seed}',loc='left',fontsize=11)
  for ax in list(axes.flat)[len(group):]:ax.set_visible(False)
  fig.subplots_adjust(left=.018,right=.991,bottom=.02,top=.94,wspace=.03,hspace=.13);fig.savefig(root/f'{label}-{"heldout" if fresh else "development"}.png');plt.close(fig)
 for seed in seeds:
  f=root/f'{seed}-{mode}-close.svg';target=root/f'{label}-{seed}-close.png'
  if target.exists() and target.stat().st_mtime>f.stat().st_mtime:continue
  fig,ax=plt.subplots(figsize=(12,8.4),dpi=100);fig.subplots_adjust(left=0,right=1,bottom=0,top=1);draw(ax,f,1200);fig.savefig(target);plt.close(fig)
for f in list(root.glob('calibration-*.svg'))+list(root.glob('*-event*.svg')):
 fig,ax=plt.subplots(figsize=(12,8.4),dpi=100);fig.subplots_adjust(left=0,right=1,bottom=0,top=1);draw(ax,f,1200);fig.savefig(f.with_suffix('.png'));plt.close(fig)
print('Population sheets and matched details rendered.')
