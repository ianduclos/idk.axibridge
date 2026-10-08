"""Four particular revisions of S1/S2. No seeded drawing engine.

Run stage1, inspect its renders, then run stage2. The second edits are recorded
responses to those images, kept separate from their ancestors.
"""
from pathlib import Path
import json, math, sys

HERE=Path(__file__).resolve().parent
INPUT=HERE.parent/'inputs'

def cut(lines, accept):
    """Densify before a cut and split rejected spans; never bridge a removed span."""
    out=[]
    for line in lines:
        sampled=[]
        for a,b in zip(line,line[1:]):
            n=max(1,math.ceil(math.dist(a,b)/.25))
            sampled.extend([[a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n] for i in range(n)])
        sampled.append(line[-1]); run=[]
        for p in sampled:
            if accept(*p): run.append(p)
            else:
                if len(run)>1: out.append(run)
                run=[]
        if len(run)>1: out.append(run)
    return out

def patch(lines, box):
    x,y,w,h=box
    # Reject the short-vertex radial scaffold before editing the real grain.
    return cut([l for l in lines if len(l)>=18],lambda a,b:x<=a<=x+w and y<=b<=y+h)

def bend(start,*segments):
    out=[list(start)]; p=start
    for segment in segments:
        if len(segment)==2:
            q=segment; n=max(2,math.ceil(math.dist(p,q)/.3))
            out.extend([[p[0]+(q[0]-p[0])*i/n,p[1]+(q[1]-p[1])*i/n] for i in range(1,n+1)])
        else:
            a,b,q=segment; n=max(12,math.ceil((math.dist(p,a)+math.dist(a,b)+math.dist(b,q))/.3))
            for i in range(1,n+1):
                t=i/n; s=1-t
                out.append([s*s*s*p[k]+3*s*s*t*a[k]+3*s*t*t*b[k]+t*t*t*q[k] for k in (0,1)])
        p=q
    return out

def save(name,stage,strokes,note):
    d={'id':f'material-{name}-stage{stage}','parent':name if stage==1 else f'material-{name}-stage1',
       'maker':'material','sourceInput':name,'pageMm':[300,218],'strokeMm':.1,
       'strokes':strokes,'editNote':note,'reproduction':'python tools/territory02/editor-loop/material/edit.py stage'+str(stage)}
    for l in strokes:
        assert len(l)>=2
        assert all(math.isfinite(x) and math.isfinite(y) and 0<=x<=300 and 0<=y<=218 for x,y in l)
    (HERE/f'{name}-stage{stage}.json').write_text(json.dumps(d,separators=(',',':')))
    print(name,stage,len(strokes),sum(map(len,strokes)))

def stage1():
    s1=json.loads((INPUT/'S1.json').read_text())['strokes']
    # Opening move: split and compact the actual abrasive central pressure body.
    grain=patch(s1,(133,43,64,47))
    grain=[[[101+1.52*(x-133)+8*math.sin((y-43)/9),45+1.83*(y-43)+.12*(x-133)] for x,y in l] for l in grain]
    grain=cut(grain,lambda x,y: not (80<y<96 and x<158) and not (x>187 and y<74))
    # A second actual rough tongue is cut free and turned against the first.
    tail=patch(s1,(204,137,45,36))
    tail=[[[199+.82*(y-137),153-.63*(x-204)] for x,y in l] for l in tail]
    strokes=grain+tail
    strokes.append(bend((73,130),((89,121),(85,90),(105,77)),((114,72),(120,75),(127,81)),
                        ((153,99),(167,119),(191,133)),((204,138),(219,139),(222,148)),
                        ((226,158),(212,166),(207,159)),((205,155),(216,149),(215,144))))
    strokes.append(bend((150,49),((158,43),(187,33),(199,46)),((209,56),(198,72),(197,86)),
                        ((196,99),(201,103),(211,107)),(225,107),((218,114),(215,121),(223,126))))
    strokes.append(bend((207,159),(190,168),((169,166),(147,169),(130,178)),
                        ((122,182),(116,185),(110,180)),((105,175),(108,169),(119,171)),(135,163)))
    save('S1',1,strokes,'Central rough body split across an open cut, vertically compacted/expanded into unequal lobes; lower rough tongue turned upward. Distributed arcs and radial scaffold removed; three smooth interrupted continuations added.')

    s2=json.loads((INPUT/'S2.json').read_text())['strokes']
    # Opening move: remove the middle of the right-hand grain fan and compress
    # the remaining material laterally. This exposes two torn growth fronts.
    grain=patch(s2,(237,84,60,98))
    grain=cut(grain,lambda x,y: not (122<y<135 and x<278) and not (x>279 and y<108))
    grain=[[[157+.94*(x-237)-.16*(y-84),43+1.27*(y-84)] for x,y in l] for l in grain]
    # Keep the frail upper grain, moved into the central cut rather than scattered.
    frail=patch(s2,(194,41,22,50))
    frail=[[[131+.75*(y-41),79+.57*(x-194)] for x,y in l] for l in frail]
    strokes=grain+frail
    strokes.append(bend((115,55),((125,72),(126,94),(143,102)),((148,105),(151,100),(148,96)),
                        ((143,89),(136,99),(139,107)),((144,122),(151,129),(166,132)),(183,127),
                        ((175,139),(165,148),(162,165)),((160,173),(145,180),(136,176))))
    strokes.append(bend((179,56),((200,48),(222,57),(226,73)),((230,87),(218,91),(220,97)),
                        (232,98),(227,113),((218,132),(214,151),(199,169)),
                        ((185,185),(179,187),(169,181)),((164,178),(165,173),(170,169))))
    strokes.append(bend((74,145),(112,118),((123,110),(132,110),(139,107))))
    save('S2',1,strokes,'Right-hand fan cut into unequal growth fronts and compressed toward the centre; frail grain exposed in the cut. All star scaffolds and remote arc packs removed; a tight internal return and a partly angular exterior course added.')

def stage2():
    s1=json.loads((HERE/'S1-stage1.json').read_text())['strokes']
    # Inspection: the rectangular slot separates two stickers; the turned
    # lower tongue is another comb ornament and the big outer arch goes soft.
    # Remove that tongue, cut a diagonal cap, then push the upper rough lobe
    # bodily into the lower one. Overlap happens in the material, not a bridge.
    body=cut(s1[:-3],lambda x,y:not (x>198 and y>121) and y>56+.2*(x-130))
    upper=cut(body,lambda x,y:y<83)
    lower=cut(body,lambda x,y:y>=83)
    body=[[[x+22,y+34] for x,y in l] for l in upper]+lower
    strokes=body
    strokes.append(bend((74,123),((91,119),(102,91),(121,98)),((133,104),(160,131),(182,128)),
                        ((202,125),(219,125),(222,132)),((225,138),(216,144),(213,140)),
                        ((209,136),(215,129),(219,132)),(225,142),(246,133)))
    strokes.append(bend((172,74),((166,84),(159,97),(159,112)),
                        ((159,132),(163,143),(149,152)),(153,139),(134,155),
                        ((126,163),(115,157),(119,151)),((120,148),(125,147),(128,148))))
    save('S1',2,strokes,'After viewing stage1: its rectangular slot and turned comb tongue read as separate stickers. Removed the tongue and outer arch, cut the rough cap diagonally and shoved the upper material into the lower body; two tighter interrupted smooth paths replace all three broad returns.')

    s2=json.loads((HERE/'S2-stage1.json').read_text())['strokes']
    # Inspection: two long side-by-side courses made an obvious pod. Open
    # the lower right half and leave the material to set the outside edge.
    body=s2[:-3]
    body=cut(body,lambda x,y:not (x>198 and y>127) and not (x<159 and y<75) and not (y<61))
    strokes=body+[s2[-3]]
    strokes.append(bend((179,56),((200,48),(222,57),(226,73)),((230,87),(218,91),(220,97)),
                        (232,98),(227,113)))
    # The isolated left slash was generic. Exchange it for a compact, smooth
    # bend whose cut-off points face the existing torn rough sliver.
    strokes.append(bend((103,128),((95,125),(91,114),(99,112)),((106,110),(107,118),(103,122)),
                        ((100,127),(111,124),(118,119)),(139,107)))
    strokes.append(bend((165,165),(176,174),((180,177),(186,174),(191,170))))
    save('S2',2,strokes,'After viewing stage1: opened the pod-like enclosure by removing its lower smooth flank and cropping the right rough spill. Replaced the isolated left slash with one abrupt smooth return facing the exposed sliver.')

if __name__=='__main__':
    {'stage1':stage1,'stage2':stage2}[sys.argv[1]]()
