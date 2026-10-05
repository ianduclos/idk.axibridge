"""Particular composition edits of the two frozen drawings, no generative seeds."""
from pathlib import Path
import json, math, sys
BASE=Path(__file__).resolve().parent
INPUT=BASE.parent/'inputs'

def sample(line, step=.25):
    out=[line[0]]
    for a,b in zip(line,line[1:]):
        n=max(1,math.ceil(math.dist(a,b)/step))
        out.extend([[a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n] for i in range(1,n+1)])
    return out

def cut(strokes,predicate):
    out=[]
    for line in strokes:
        part=[]
        for p in sample(line):
            if predicate(*p): part.append(p)
            else:
                if len(part)>1:out.append(part)
                part=[]
        if len(part)>1:out.append(part)
    return out

def crop(strokes,box):
    x,y,w,h=box
    return cut(strokes,lambda a,b:x<=a<=x+w and y<=b<=y+h)

def move(strokes,center,target,sx,sy,angle):
    c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
    out=[]
    for line in strokes:
        row=[]
        for x,y in line:
            u=(x-center[0])*sx; v=(y-center[1])*sy
            row.append([target[0]+u*c-v*s,target[1]+u*s+v*c])
        out.append(row)
    return cut(out,lambda x,y:3<=x<=297 and 3<=y<=215)

def bez(start,segments):
    out=[start]; a=start
    for b,c,d in segments:
        n=max(12,int((math.dist(a,b)+math.dist(b,c)+math.dist(c,d))*2))
        for i in range(1,n+1):
            t=i/n; z=1-t
            out.append([z**3*a[0]+3*z*z*t*b[0]+3*z*t*t*c[0]+t**3*d[0],z**3*a[1]+3*z*z*t*b[1]+3*z*t*t*c[1]+t**3*d[1]])
        a=d
    return out

def save(name,stage,strokes,note):
    parent=name if stage==1 else f'composition-{name}-stage1'
    data={'id':f'composition-{name}-stage{stage}','parent':parent,'maker':'composition','sourceInput':name,'pageMm':[300,218],'strokeMm':.1,'strokes':strokes,'editNote':note,'reproductionCommand':f'python tools/territory02/editor-loop/composition/edit.py {stage}'}
    (BASE/f'{name}-stage{stage}.json').write_text(json.dumps(data,separators=(',',':')))
    print(name,stage,len(strokes),sum(map(len,strokes)))

def stages1():
    s1=json.loads((INPUT/'S1.json').read_text())['strokes']
    # Opening: omit peripheral rings; stretch the central course into a heavy sloping wall.
    a=move(crop(s1,[133,41,72,49]),[169,65],[139,112],1.45,1.15,49)
    # Compress the bottom-right rough grain into the same wall rather than making a second emblem.
    b=move(crop(s1,[198,109,61,58]),[228,138],[158,130],.76,.52,-20)
    body=a+b
    # The empty contour crosses the material and makes a narrow folded chamber.
    chamber=bez([55,36],[([74,35],[85,39],[87,62]),([90,85],[102,94],[122,88]),([139,83],[148,82],[147,97]),([146,110],[151,119],[169,122]),([182,125],[189,124],[191,138]),([193,160],[208,178],[236,172]),([213,195],[184,194],[173,174]),([162,152],[149,157],[142,155]),([126,152],[126,145],[132,137]),([139,128],[137,125],[123,121]),([92,113],[86,85],[79,60]),([74,47],[68,44],[55,36])])
    body=cut(body,lambda x,y:not (100<x<128 and 102<y<122))
    # One angular continuation into the same body, with a very tight hooked end.
    corner=bez([240,35],[([218,48],[212,51],[212,51]),([212,51],[217,67],[217,67]),([213,70],[174,84],[164,103]),([163,105],[166,111],[169,109])])
    tail=bez([87,168],[([84,176],[82,182],[84,190]),([86,198],[91,197],[93,191]),([94,185],[94,177],[93,172])])
    save('S1',1,body+[chamber,corner,tail],'Omit the discs and star crossings; stretch the middle grain, compact the lower-right grain into it, and oppose this oblique body with a tight folded chamber.')
    s2=json.loads((INPUT/'S2.json').read_text())['strokes']
    # Opening: rotate the actual lower-right group into a wide low field with unequal weight.
    a=move(crop(s2,[237,85,58,95]),[267,132],[118,142],1.15,1.08,71)
    # Inherited upper courses now press into the field, highly compressed, breaking their fan silhouette.
    b=move(crop(s2,[185,15,50,42]),[210,36],[152,133],1.10,.55,-29)
    body=a+b
    spine=bez([47,61],[([51,69],[53,82],[66,79]),([83,77],[85,88],[77,96]),([68,106],[70,117],[92,117]),([133,117],[146,105],[163,109]),([179,113],[174,99],[170,79]),([167,59],[173,45],[184,44]),([198,43],[199,52],[193,58]),([186,65],[189,70],[203,71]),([221,74],[227,82],[223,94]),([218,106],[213,120],[214,133]),([214,143],[209,146],[199,143]),([166,132],[140,146],[119,147]),([98,149],[88,142],[76,145]),([61,150],[43,140],[41,122]),([38,102],[39,78],[47,61])])
    ridge=[[217,42],[242,42],[242,100],[235,103],[249,165],[212,184]]
    save('S2',1,body+[spine,ridge],'Move the right fan into a broad low oblique body and compress the upper course into it; a narrow doubled-back chamber and angular flank occupy the vacated sheet.')

def stages2():
    s1=json.loads((BASE/'S1-stage1.json').read_text())['strokes']
    body=s1[:-3]
    # Inspection response: lose floating upper comb; break the grain course with diagonal slits.
    def keep1(x,y):
        if y<80 and x<146:return False
        # Two asymmetric cuts, intentionally not holes with decorative outlines.
        if 92<x<151 and abs(y-(.43*x+57))<1.6:return False
        if 124<x<176 and abs(y-(-.70*x+224))<.75:return False
        return True
    body=cut(body,keep1)
    # Turn a little lower-right inherited grain back into the body; sharp density seam remains.
    rem=crop(body,[146,121,34,27])
    rem=move(rem,[162,134],[145,115],.74,.90,-68)
    body+=rem
    tight=bez([49,47],[([62,47],[78,46],[78,46]),([78,47],[76,57],[81,60]),([88,65],[90,61],[88,58]),([87,55],[95,59],[99,66]),([103,74],[103,86],[112,92]),([123,99],[134,98],[141,108]),([150,121],[169,124],[177,134]),([183,142],[183,151],[192,153]),([201,155],[216,162],[219,161]),([217,170],[208,174],[203,169]),([197,164],[198,158],[185,158]),([171,158],[164,149],[160,140]),([154,130],[143,129],[137,123]),([125,117],[119,112],[111,113]),([96,114],[94,99],[88,88]),([81,75],[82,70],[73,67]),([62,63],[62,59],[62,57]),([58,57],[52,52],[49,47])])
    # Sparse hard-edged counterweight directly enters the rough mass, rather than floating beside it.
    corner=bez([251,44],[([219,59],[215,62],[215,62]),([215,62],[220,70],[220,70]),([210,73],[174,79],[158,95]),([154,99],[157,108],[152,112]),([147,115],[142,114],[145,111])])
    inside=[[107,105],[116,104],[115,110],[126,118],[131,116]]
    save('S1',2,body+[tight,corner,inside],'After viewing inflated smooth ends and a stray droplet: tighten the folded contour, remove the upper floaters, interrupt inherited rhythm with unequal slits, and turn one grain segment into the body.')
    s2=json.loads((BASE/'S2-stage1.json').read_text())['strokes']
    body=s2[:-2]
    # Comb rhythm dominated stage1: lose most hanging arcs and the isolated straight inherited crossing.
    body=cut(body,lambda x,y:y<158 and not (x<126 and y>139) and not (111<x<151 and 121<y<133))
    # Grown rough fan is pressed into a long crooked bed; no repeated new offset curves.
    body=move(body,[122,136],[130,130],1.25,.83,-8)
    # A dense narrow bed from the actual upper-course patch makes the lower field behave as a fill.
    src=json.loads((INPUT/'S2.json').read_text())['strokes']
    bed=move(crop(src,[195,19,35,33]),[212,36],[157,151],1.45,.26,7)
    body+=bed
    tight=bez([54,79],[([52,84],[50,96],[57,98]),([67,102],[70,94],[65,91]),([60,89],[68,89],[74,94]),([88,102],[102,110],[119,107]),([151,103],[160,109],[177,105]),([187,103],[185,91],[183,82]),([181,71],[183,62],[189,62]),([197,62],[196,70],[191,72]),([187,75],[194,79],[199,82]),([205,85],[203,96],[199,101]),([193,107],[195,114],[205,118]),([224,126],[226,137],[216,142]),([203,149],[197,150],[180,147]),([158,143],[153,146],[144,149]),([130,152],[124,157],[115,154]),([105,151],[104,148],[106,145]),([113,136],[112,130],[98,127]),([79,124],[72,116],[64,113]),([53,109],[48,114],[46,107]),([42,100],[49,85],[54,79])])
    # The formerly detached angular flank now slices the body and folds at its foot.
    edge=[[221,39],[233,39],[233,95],[203,107],[207,137],[184,159],[185,179],[174,179],[174,161],[183,151]]
    seam=bez([123,148],[([129,138],[138,141],[142,136]),([145,132],[141,127],[139,128])])
    save('S2',2,body+[tight,edge,seam],'After viewing an empty U frame and dominating fan: tighten the curved construction, remove the hanging comb arcs, widen and flatten the rough material, and bring the angular flank into its bed.')

if __name__=='__main__':
    if sys.argv[1]=='1':stages1()
    elif sys.argv[1]=='2':stages2()
