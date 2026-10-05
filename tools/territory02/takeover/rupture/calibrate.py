"""Same generated case, with either family omitted; neutral review controls."""
from pathlib import Path
import json,subprocess,re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
root=Path(__file__).resolve().parent
D=json.loads(subprocess.check_output(['node','-e',"process.stdout.write(JSON.stringify(require('./generate.cjs').generate(13,'body')))"],cwd=root))
css=(root/'../../../../axibridge/static/css/flexoki.css').read_text()
def color(n):return re.search(r'--flexoki-'+n+r':\s*(#[\da-fA-F]+)',css)[1]
for label,key in [('D','strokes'),('E','lines'),('F','material')]:
 for close in [False,True]:
  x,y,w,h=[100,74,100,70] if close else [0,0,300,218]
  fig,ax=plt.subplots(figsize=(12,8.4 if close else 8.72),dpi=100)
  fig.subplots_adjust(left=0,right=1,bottom=0,top=1)
  ax.set(xlim=(x,x+w),ylim=(y+h,y),aspect='equal',xticks=[],yticks=[]);ax.set_facecolor(color('paper'))
  ax.add_collection(LineCollection(D[key],colors=color('black'),linewidths=.1*12*72/w,capstyle='round',joinstyle='round'))
  for spine in ax.spines.values():spine.set_visible(False)
  fig.savefig(root/'evidence'/f'calibration-{label}{"-close" if close else ""}.png');plt.close(fig)
