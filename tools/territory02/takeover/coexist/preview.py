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
labels={'rough':'K','smooth':'M','continuity':'N','interference':'S','independent':'W'}
for mode,label in labels.items():
 files=sorted(root.glob(f'*-{mode}.svg'))
 for fresh in [False,True]:
  group=[f for f in files if (int(f.stem.split('-')[0])>=1000)==fresh]
  if not group:continue
  rows=math.ceil(len(group)/3);fig,axes=plt.subplots(rows,3,figsize=(18,4.8*rows),dpi=100,squeeze=False)
  for ax,f in zip(axes.flat,group):
   seed,base,_=f.stem.split('-');draw(ax,f,560);ax.set_title(f'{label} · {seed} · '+{'opening':'a','pressure':'b','unravel':'c'}[base],loc='left',fontsize=11)
  for ax in list(axes.flat)[len(group):]:ax.set_visible(False)
  fig.subplots_adjust(left=.018,right=.991,bottom=.02,top=.95,wspace=.03,hspace=.13);fig.savefig(root/f'{label}-{"heldout" if fresh else "development"}.png');plt.close(fig)
 for f in files:
  seed,base,_=f.stem.split('-');close=root/f'{seed}-{base}-{mode}-close.svg'
  fig,ax=plt.subplots(figsize=(12,8.4),dpi=100);fig.subplots_adjust(left=0,right=1,bottom=0,top=1);draw(ax,close,1200);fig.savefig(root/f'{label}-{seed}-{base}-close.png');plt.close(fig)

for f in root.glob('calibration-*.svg'):
 fig,ax=plt.subplots(figsize=(12,8.72),dpi=100);fig.subplots_adjust(left=0,right=1,bottom=0,top=1);draw(ax,f,1200);fig.savefig(f.with_suffix('.png'));plt.close(fig)

# Matched case for the report; population sheets remain the primary evidence.
fig,axes=plt.subplots(2,2,figsize=(14,10.6),dpi=120)
for ax,mode,title in zip(axes.flat,['rough','continuity','interference','independent'],['Earlier rough drawing','Continuity','Interference','Independent coexistence']):
 draw(ax,root/f'24-unravel-{mode}.svg',660)
 ax.set_title(title,loc='left',fontsize=12)
fig.subplots_adjust(left=.02,right=.985,bottom=.025,top=.95,wspace=.035,hspace=.13)
fig.savefig(root/'comparison-24-unravel.png');plt.close(fig)
