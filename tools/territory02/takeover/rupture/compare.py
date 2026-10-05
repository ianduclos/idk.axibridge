"""A matched whole-sheet comparison, without changing drawn line weight."""
from pathlib import Path
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
root=Path(__file__).resolve().parent
css=(root/'../../../../axibridge/static/css/flexoki.css').read_text()
def c(n):return re.search(r'--flexoki-'+n+r':\s*(#[\da-fA-F]+)',css)[1]
for seed in [47,1213]:
 fig,axes=plt.subplots(1,3,figsize=(21,5.4),dpi=110);fig.set_facecolor(c('paper'));fig.subplots_adjust(left=.015,right=.99,bottom=.025,top=.92,wspace=.04)
 for ax,mode,title in zip(axes,['earlier','open','body'],['Earlier coexistence','Open construction','Folded body']):
  text=(root/'evidence'/f'{seed}-{mode}.svg').read_text();paths=[]
  for m in re.finditer(r'<path d="([^"]+)"',text):
   a=list(map(float,re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?',m[1])));paths.append(list(zip(a[::2],a[1::2])))
  ax.set(xlim=(0,300),ylim=(218,0),aspect='equal',xticks=[],yticks=[]);ax.set_facecolor(c('paper'))
  ax.add_collection(LineCollection(paths,colors=c('black'),linewidths=.1*ax.get_position().width*21*72/300,capstyle='round',joinstyle='round'));ax.set_title(title,loc='left',fontsize=12)
  for spine in ax.spines.values():spine.set_color(c('200'));spine.set_linewidth(.5)
 fig.savefig(root/'evidence'/f'comparison-{seed}.png');plt.close(fig)
