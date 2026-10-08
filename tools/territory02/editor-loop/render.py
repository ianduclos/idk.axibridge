"""Render saved editable polylines at the shared physical stroke and page scale."""
from pathlib import Path
import json, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

def render(data, target, box=None):
    strokes=data['strokes']; box=box or [0,0,300,218]
    x,y,w,h=box; target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="'+str(w)+'mm" height="'+str(h)+'mm" viewBox="'+' '.join(map(str,box))+'"><rect x="'+str(x)+'" y="'+str(y)+'" width="'+str(w)+'" height="'+str(h)+'" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round">'
    svg+=''.join('<path d="M'+' L'.join(' '.join(f'{v:.4f}' for v in p) for p in line)+'"/>' for line in strokes)+'</g></svg>'
    target.with_suffix('.svg').write_text(svg)
    fig=plt.figure(figsize=(12,12*h/w),dpi=180,facecolor='#FFFCF0'); ax=fig.add_axes([0,0,1,1]); ax.set_facecolor('#FFFCF0')
    ax.set_xlim(x,x+w); ax.set_ylim(y+h,y); ax.set_aspect('equal'); ax.axis('off')
    ax.add_collection(LineCollection(strokes,colors='#100F0F',linewidths=.1*12*72/w,antialiased=True,capstyle='round',joinstyle='round'))
    fig.savefig(target.with_suffix('.png'),dpi=180); plt.close(fig)
if __name__=='__main__':
    source=Path(sys.argv[1]); target=Path(sys.argv[2]) if len(sys.argv)>2 else source.with_suffix('')
    render(json.loads(source.read_text()),target, list(map(float,sys.argv[3:7])) if len(sys.argv)>=7 else None)
