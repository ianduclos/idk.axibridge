"""Render only the requested population; fresh seeds require --holdouts."""
from pathlib import Path
import re,sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
root=Path(__file__).resolve().parent
evidence=root/'evidence'
fresh='--holdouts' in sys.argv
seeds=[1151,1213,1277] if fresh else [13,24,47]
palette=(root/'../../../../axibridge/static/css/flexoki.css').read_text()
def color(name):return re.search(r'--flexoki-'+name+r':\s*(#[\da-fA-F]+)',palette)[1]
def draw(ax,file):
 text=file.read_text();x,y,w,h=map(float,re.search(r'viewBox="([^"]+)"',text)[1].split());paths=[]
 for match in re.finditer(r'<path d="([^"]+)"',text):
  values=list(map(float,re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?',match[1])));paths.append(list(zip(values[::2],values[1::2])))
 ax.set_xlim(x,x+w);ax.set_ylim(y+h,y);ax.set_aspect('equal');ax.set_facecolor(color('paper'));ax.set_xticks([]);ax.set_yticks([])
 # Compute point width from the actual axes size, preserving 0.1 mm ink.
 linewidth=.1*ax.get_position().width*ax.figure.get_figwidth()*72/w
 ax.add_collection(LineCollection(paths,colors=color('black'),linewidths=linewidth,antialiased=True,capstyle='round',joinstyle='round'))
 for spine in ax.spines.values():spine.set_color(color('200'));spine.set_linewidth(.5)
def figure(rows,cols,size):
 fig,axes=plt.subplots(rows,cols,figsize=size,dpi=120,squeeze=False);fig.set_facecolor(color('paper'));return fig,axes
for mode,label in [('earlier','K'),('open','P'),('body','T')]:
 for lines in [False,True] if mode!='earlier' else [False]:
  tail='-lines' if lines else ''
  fig,axes=figure(len(seeds),2,(16,6*len(seeds)))
  fig.subplots_adjust(left=.018,right=.99,bottom=.018,top=.95,wspace=.03,hspace=.12)
  for row,seed in enumerate(seeds):
   for col,close in enumerate([False,True]):
    ax=axes[row,col];draw(ax,evidence/f'{seed}-{mode}{tail}{"-close" if close else ""}.svg');ax.set_title(f'{label} · seed {seed} · {"central detail" if close else "whole sheet"}',loc='left',fontsize=11)
  fig.savefig(evidence/f'{label}-{"heldout" if fresh else "development"}{tail}.png');plt.close(fig)
  for seed in seeds:
   for close in [False,True]:
    fig,axes=figure(1,1,(12,8.4 if close else 8.72));fig.subplots_adjust(left=0,right=1,bottom=0,top=.955)
    draw(axes[0,0],evidence/f'{seed}-{mode}{tail}{"-close" if close else ""}.svg');axes[0,0].set_title(f'{label} · seed {seed}',loc='left',fontsize=11)
    fig.savefig(evidence/f'{label}-{seed}{tail}{"-close" if close else ""}.png');plt.close(fig)
print(f'{"Fresh" if fresh else "Development"} population PNGs rendered for {seeds}.')
