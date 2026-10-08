from pathlib import Path
import re,math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
root=Path(__file__).resolve().parent/'evidence'
def draw(ax,f,width):
 s=f.read_text();x,y,w,h=map(float,re.search(r'viewBox="([^"]+)"',s)[1].split());lines=[]
 for m in re.finditer(r'<path d="([^"]+)"',s):
  a=list(map(float,re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?',m[1])));lines.append(list(zip(a[::2],a[1::2])))
 ax.set_xlim(x,x+w);ax.set_ylim(y+h,y);ax.set_aspect('equal');ax.set_facecolor('#FFFCF0');ax.set_xticks([]);ax.set_yticks([])
 ax.add_collection(LineCollection(lines,colors='#100F0F',linewidths=.1*width/w*72/100,antialiased=True,capstyle='round',joinstyle='round'))
 for spine in ax.spines.values():spine.set_color('#CECDC3');spine.set_linewidth(.5)
for mode,label in [('prior','A'),('reference','B'),('stripped','D'),('bare','Q'),('led','V')]:
 seeds=sorted(int(f.stem.split('-')[0]) for f in root.glob(f'*-{mode}.svg'))
 for heldout in [False,True]:
  group=[s for s in seeds if (s>=700)==heldout]
  if not group:continue
  rows=math.ceil(len(group)/3);fig,axes=plt.subplots(rows,3,figsize=(18,4.8*rows),dpi=100,squeeze=False)
  for ax,seed in zip(axes.flat,group):draw(ax,root/f'{seed}-{mode}.svg',560);ax.set_title(f'{label} · {seed}',loc='left')
  for ax in list(axes.flat)[len(group):]:ax.set_visible(False)
  fig.subplots_adjust(left=.018,right=.991,bottom=.02,top=.94,wspace=.03,hspace=.12);fig.savefig(root/f'{label}-{"heldout" if heldout else "development"}.png');plt.close(fig)
 for seed in seeds:
  f=root/f'{seed}-{mode}-close.svg'
  if not f.exists():continue
  fig,ax=plt.subplots(figsize=(12,8.4),dpi=100);fig.subplots_adjust(left=0,right=1,bottom=0,top=1);draw(ax,f,1200);fig.savefig(root/f'{label}-{seed}-close.png');plt.close(fig)
# Paired whole/detail preview of one fresh case; population sheets remain primary.
if (root/'797-bare-close.svg').exists():
 fig,axes=plt.subplots(2,2,figsize=(16,11.8),dpi=100)
 for row,suffix in enumerate(['','-close']):
  for col,(mode,label) in enumerate([('bare','New paths'),('led','Coarse material')]):
   draw(axes[row,col],root/f'797-{mode}{suffix}.svg',770);axes[row,col].set_title(f'{label} · 797 · {"detail" if row else "whole"}',loc='left',fontsize=12)
 fig.subplots_adjust(left=.015,right=.99,bottom=.018,top=.96,wspace=.04,hspace=.12);fig.savefig(root/'preview-797.png');plt.close(fig)
