"""Assemble the first checkpoint from saved states; never regenerate their geometry."""
from pathlib import Path
import json, re, math, hashlib, random, html
from render import render
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
root=Path(__file__).resolve().parent

def read(p): return json.loads(p.read_text())
def save(p,d): p.write_text(json.dumps(d,separators=(',',':'))+'\n')
def stats(d):
    pts=0; ink=0
    assert d.get('pageMm',[300,218])==[300,218]
    assert d.get('strokeMm',.1)==.1
    for line in d['strokes']:
        assert len(line)>=2
        for p in line:
            assert len(p)==2 and all(math.isfinite(x) for x in p)
            assert 0<=p[0]<=300 and 0<=p[1]<=218,p
        pts+=len(line);ink+=sum(math.dist(a,b) for a,b in zip(line,line[1:]))
    return {'points':pts,'strokes':len(d['strokes']),'inkMm':ink,'geometrySha256':hashlib.sha256(json.dumps(d['strokes'],separators=(',',':')).encode()).hexdigest()}
def contact(items,path,cols=2):
    rows=math.ceil(len(items)/cols);fig,axs=plt.subplots(rows,cols,figsize=(cols*7,rows*5.4),dpi=140,squeeze=False)
    fig.set_facecolor('#FFFCF0');fig.subplots_adjust(left=.01,right=.99,top=.98,bottom=.01,hspace=.08,wspace=.035)
    for ax,(label,d) in zip(axs.flat,items):
        ax.set_facecolor('#FFFCF0');ax.set_xlim(0,300);ax.set_ylim(218,0);ax.set_aspect('equal');ax.set_xticks([]);ax.set_yticks([])
        linewidth=.1*ax.get_position().width*fig.get_figwidth()*72/300
        ax.add_collection(LineCollection(d['strokes'],colors='#100F0F',linewidths=linewidth,capstyle='round',joinstyle='round'))
        ax.set_title(label,loc='left',fontsize=12)
        for sp in ax.spines.values(): sp.set_visible(False)
    for ax in list(axs.flat)[len(items):]:ax.axis('off')
    fig.savefig(path);plt.close(fig)
def shell(title,body):
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+title+'</title><style>body{margin:0;background:#FFFCF0;color:#100F0F;font:17px/1.6 system-ui,sans-serif}main{max-width:1500px;margin:auto;padding:28px}h1{font-size:clamp(26px,4vw,42px);line-height:1.1;font-weight:600}a{color:#24837b;text-underline-offset:.2em}nav{display:flex;gap:24px;flex-wrap:wrap}nav a,.links a{display:inline-flex;align-items:center;min-height:44px}p{max-width:78ch}.grid{display:grid;grid-template-columns:1fr 1fr;gap:30px 24px}figure{margin:0}figure img{width:100%;height:auto;display:block}figcaption{font-size:15px}.links{display:flex;gap:20px}summary{cursor:pointer;min-height:44px;display:flex;align-items:center}details{border-top:1px solid #CECDC3;margin-top:30px;padding:18px 0}td,th{text-align:left;padding:8px;border-bottom:1px solid #E6E4D9}table{border-collapse:collapse;font-size:15px}.table{overflow:auto}a:focus-visible{outline:2px solid #24837b} @media(max-width:700px){main{padding:18px}.grid{grid-template-columns:1fr}}</style><main>'+body+'</main></html>'
def card(label,stem):
    return '<figure id="'+label+'"><figcaption><strong>'+label+'</strong></figcaption><a href="'+stem+'.svg" aria-label="Open '+label+' full-size vector"><img src="'+stem+'.png" alt="Whole drawing '+label+'"></a><div class="links"><a href="'+stem+'.svg">Full-size SVG</a><a href="'+stem+'.png">PNG</a></div></figure>'

# Keep exact older weak control, at its published precision.
source=root.parent/'takeover/rupture/evidence/1277-open.svg'
if not (root/'inputs/control-weak.json').exists():
    paths=[]
    for d in re.findall(r'<path d="([^"]+)"',source.read_text()):
        n=list(map(float,re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?',d)));paths.append(list(map(list,zip(n[::2],n[1::2]))))
    save(root/'inputs/control-weak.json',{'id':'control-weak','parent':None,'strokes':paths,'pageMm':[300,218],'strokeMm':.1,'source':str(source.relative_to(root.parent.parent.parent)),'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest()})
# choices.json is written by the primary from returned selections.
choices=read(root/'choices.json')
entries=[{'maker':maker,'input':inp,'stage':stage,'source':f'{maker}/{inp}-stage{stage}.json'} for maker,selected in choices.items() for inp,stage in selected.items()]
entries += [{'maker':'untouched reference','input':'S1','stage':0,'source':'inputs/S1.json'},{'maker':'earlier weak control','input':'rupture open 1277','stage':0,'source':'inputs/control-weak.json'}]
random.Random(20261005).shuffle(entries)
checks=[]; panels=[];cards=[]
for i,e in enumerate(entries,1):
    label=f'N{i}';d=read(root/e['source']);e['label']=label;e['id']=d['id'];e.update(stats(d));stem=f'evidence/{label}'
    save(root/(stem+'.json'),d);render(d,root/stem);render(d,root/(stem+'-close'),[100,74,100,70]);panels.append((label,d));cards.append(card(label,stem));checks.append(e)
contact(panels,root/'evidence/contact.png')
(root/'manifest.json').write_text(json.dumps(checks,indent=2)+'\n')
# History has all four stages per maker plus both originals, full access to each.
history=[];historycards=[]
for inp in ['S1','S2']:
    d=read(root/f'inputs/{inp}.json');history.append((inp+' · input',d));historycards.append(card(inp,'inputs/'+inp))
for inp in ['S1','S2']:
    for stage in [1,2]:
        for maker in choices:
            path=root/f'{maker}/{inp}-stage{stage}.json';d=read(path);stat=stats(d);checks.append({'source':str(path.relative_to(root)),**stat})
            label=f'{maker}-{inp}-{stage}';stem=f'evidence/history-{label}';render(d,root/stem);history.append((label,d));historycards.append(card(label,stem))
contact(history,root/'evidence/history.png',cols=3)
(root/'history.html').write_text(shell('Territory02 · first-round histories','<nav><a href="index.html">Eight drawings</a><a href="../../../docs/reviews/territory02-editor-round1-2026-10-05.html">Reading and limits</a></nav><h1>Starting states and revisions</h1><p>Both inputs, then every maker’s first and second stage. All sheets use 300 × 218 mm and 0.1 mm strokes. A later stage is not assumed to be better.</p><div class="grid">'+''.join(historycards)+'</div>'))
rows=''.join('<tr><td>'+e['label']+'</td><td>'+html.escape(e['maker'])+'</td><td>'+html.escape(e['input'])+'</td><td>'+str(e['stage'])+'</td></tr>' for e in entries)
body='<nav><a href="../../../docs/reviews/territory02-editor-round1-2026-10-05.html">Reading and limits</a><a href="history.html">All revisions</a><a href="evidence/contact.png">Contact sheet PNG</a></nav><h1>Eight drawings. First checkpoint.</h1><p>Six edits and two older references, mixed under neutral labels. Look at the drawings before opening the identities below. Select a drawing for the full-size vector; thin marks can disappear in thumbnails.</p><p>300 × 218 mm · 0.1 mm strokes · screen study. No combined direction selected.</p><div class="grid">'+''.join(cards)+'</div><details><summary>Reveal identities</summary><div class="table"><table><thead><tr><th>Cell</th><th>Maker / reference</th><th>Input</th><th>Chosen stage</th></tr></thead><tbody>'+rows+'</tbody></table></div></details>'
(root/'index.html').write_text(shell('Territory02 · first checkpoint',body))
(root/'evidence/geometry-checks.json').write_text(json.dumps({'finiteAndBounded':True,'pageMm':[300,218],'strokeMm':.1,'records':checks,'limits':'Saved geometry verification; no generalization or paper acceptance.'},indent=2)+'\n')
print('Assembled eight neutral choices and fourteen history states.')
