"""Specific continuation edits of frozen S1 and S2; no seeded drawing engine.
Run from repository root with the pinned Python. Stage2 is an inspected revision.
"""
import json, math
from pathlib import Path
import numpy as np
from shapely.geometry import LineString, box

ROOT=Path('tools/territory02/editor-loop'); OUT=ROOT/'connections'

def read(name): return json.loads((ROOT/'inputs'/f'{name}.json').read_text())
def clip(strokes, rect):
    out=[]; region=box(*rect)
    for s in strokes:
        g=LineString(s).intersection(region)
        if g.is_empty: continue
        parts=[g] if g.geom_type=='LineString' else list(g.geoms) if hasattr(g,'geoms') else []
        for p in parts:
            if p.geom_type=='LineString' and p.length>.2: out.append(np.asarray(p.coords))
    return out

def transform(lines, origin, destination, sx=1, sy=1, angle=0):
    r=math.radians(angle); rot=np.array([[math.cos(r),-math.sin(r)],[math.sin(r),math.cos(r)]])
    return [(s-origin)*[sx,sy]@rot.T+destination for s in lines]

def bez(p,n=60):
    p=np.array(p); t=np.linspace(0,1,n)[:,None]
    return (1-t)**3*p[0]+3*(1-t)**2*t*p[1]+3*(1-t)*t*t*p[2]+t**3*p[3]

def course(*sections): return np.concatenate([bez(s) for s in sections])

def save(name,stage,strokes,note):
    data={'id':f'connections-{name}-stage{stage}','parent':name if stage==1 else f'connections-{name}-stage1','maker':'connections','sourceInput':f'../inputs/{name}.json','pageMm':[300,218],'strokeMm':.1,'reproductionCommand':'python tools/territory02/editor-loop/connections/edit.py','editNote':note,'strokes':[np.round(s,5).tolist() for s in strokes]}
    for s in data['strokes']:
        assert len(s)>=2
        assert all(math.isfinite(x) and math.isfinite(y) and 0<=x<=300 and 0<=y<=218 for x,y in s)
    (OUT/f'{name}-stage{stage}.json').write_text(json.dumps(data,separators=(',',':')))

S1=read('S1')['strokes']; S2=read('S2')['strokes']
# Opening: cut continuations at selected material seams and remove the inherited
# radial crossings. The surviving bands are repositioned; new courses imply their continuations.
a=clip(S1,(136,44,197,87)); b=clip(S1,(204,129,263,168)); c=clip(S1,(18,145,51,173))
a=transform(a,np.array([136,44]),np.array([79,53]),1.28,.91,12)
b=transform(b,np.array([204,129]),np.array([177,116]),.9,.56,154)
c=transform(c,np.array([18,145]),np.array([232,170]),.67,.85,-22)
# Dense damaged upper body's continuations stop at an independent narrow sleeve.
s1=a+b+c
s1 += [course([[130,56],[171,42],[185,58],[166,83]],[[166,83],[156,100],[168,110],[189,109]],[[189,109],[206,108],[207,115],[193,119]],[[193,119],[180,124],[182,137],[174,139]]),
       course([[128,61],[172,50],[175,64],[161,83]],[[161,83],[152,100],[159,119],[182,116]],[[182,116],[196,112],[196,117],[185,120]],[[185,120],[178,123],[181,135],[174,139]]),
       course([[175,140],[172,154],[169,166],[147,165]],[[147,165],[127,164],[114,164],[115,149]],[[115,149],[116,141],[116,139],[112,138]]),
       np.array([[112,138],[76,143],[75.6,141],[63,141],[63,114]]),
       course([[234,175],[219,178],[215,184],[194,181]],[[194,181],[181,179],[171,171],[147,165]])]
s1 += [np.array([[60,42],[66,42],[65,63]]),np.array([[227,144],[225,131],[239,130],[239,94]])]
save('S1',1,s1,'Cut inherited radial junctions and reposition and compress two grain bodies; newly authored interrupted courses imply their continuation beside a pinched empty sleeve.')

# S2 opening is removal of the star through its actual centre, and exchanging the
# long sparse skeletal courses with terminations of the lower-right grain bank.
r=clip(S2,(242,100,296,180)); top=clip(S2,(188,1,229,56)); seam=clip(S2,(188,64,218,93))
r=transform(r,np.array([242,100]),np.array([140,84]),.72,.98,-17)
top=transform(top,np.array([188,1]),np.array([73,49]),1.15,.57,9)
seam=transform(seam,np.array([188,64]),np.array([165,75]),.8,.65,67)
s2=r+top+seam
s2 += [course([[74,58],[89,48],[101,57],[110,65]],[[110,65],[130,78],[121,83],[129,95]],[[129,95],[131,97],[139,94],[140,92]]),
       course([[78,60],[91,54],[96,59],[107,68]],[[107,68],[116,76],[113,83],[128,99]],[[128,99],[135,108],[138,109],[146,111]]),
       course([[120,64],[157,43],[190,42],[191,59]],[[191,59],[192,75],[174,72],[173,84]]),
       course([[173,84],[180,93],[186,107],[196,109]],[[196,109],[213,115],[204,133],[191,131]],[[191,131],[180,129],[180,119],[172,124]]),
       np.array([[172,124],[143,171],[143,185],[107,185],[107,146]]),
       course([[107,146],[108,117],[97,126],[91,144]],[[91,144],[78,163],[69,160],[69,151]],[[69,151],[69,141],[81,146],[88,132]]),
       np.array([[57,108],[93,108],[93,112]]),
       course([[188,148],[199,150],[203,157],[225,155]],[[225,155],[242,152],[238,171],[225,171]])]
save('S2',1,s2,'Remove both radial skeleton junctions and relocate their surviving grain into an uneven bank; newly authored long courses stop, double back, or disappear beside that bank.')

# Inspected stage1: its smooth sleeves float beside stickers. Revision compresses
# inherited broad fans into a ragged joined bank and cuts away decorative satellites.
def s1_bank(lines):
    result=[]
    for s in lines:
        u=(s[:,0]-136)/61; v=(s[:,1]-44)/43
        result.append(np.column_stack([74+114*u,65+32*u+13*np.sin(np.pi*u)+19*(v-.5)]))
    return result
rawa=clip(S1,(136,44,197,87)); rawb=clip(S1,(204,129,263,168))
newa=s1_bank(rawa)
# Two layers are offset fragments of the inherited rough material, not parallel
# contour copies; partial paths expose differently broken internal growth.
frayed=[]
for i,s in enumerate(newa):
    if len(s)<7: continue
    q=s[len(s)//4:3*len(s)//4].copy()
    q[:,1]+=1.7*np.sin((q[:,0]-74)*.17+i*.7)
    q[:,0]+=.55*np.sin(q[:,1]*.31+i)
    frayed.append(q)
newb=transform(rawb,np.array([204,129]),np.array([166,104]),.46,.77,105)
# The second bank disappears under the first rather than becoming another island.
s1b=newa+frayed+newb
s1b += [course([[78,62],[100,52],[112,57],[110,67]],[[110,67],[109,75],[119,77],[128,76]]),
        course([[118,64],[125,56],[134,59],[134,68]],[[134,68],[133,76],[140,76],[145,79]]),
        course([[186,101],[199,105],[197,111],[181,116]],[[181,116],[163,123],[170,139],[165,145]]),
        course([[165,145],[164,151],[156,152],[156,144]],[[156,144],[157,135],[161,134],[158,131]]),
        np.array([[151,121],[107,135],[82,167],[186,163],[191,150]]),
        course([[191,150],[193,142],[201,148],[207,149]],[[207,149],[216,151],[219,150],[221,147]])]
# Contradictory narrow angular sliver interrupts lower passage, stopped at its wall.
s1b += [np.array([[103,136],[113,145],[104,159],[91,159]]),np.array([[110,137],[119,145],[110,154]])]
save('S1',2,s1b,'After inspecting stage1, overlap the grain into one ragged diagonal bank, remove satellites and oversized sleeves, and place two compact smooth swellings against the material with an angular lower passage.')

# S2's inherited combs dominate stage1. Compress and kink that actual bank, then
# reconnect its lower terminations to a compact nonparallel return.
rawr=clip(S2,(242,100,296,180)); rawtop=clip(S2,(188,1,229,56))
newr=[]
for s in rawr:
    u=(s[:,0]-242)/54; v=(s[:,1]-100)/80
    newr.append(np.column_stack([137+38*u+15*np.sin(v*4.7),66+91*v+10*u*np.sin(v*6)]))
newtop=transform(rawtop,np.array([188,1]),np.array([83,139]),1.34,.38,-16)
# The compressed lower course now enters the returning bank, with coarse
# fragments interleaved locally to lose the repeated feather edge.
weave=[]
for i,s in enumerate(newr):
    if len(s)<8 or i%3: continue
    q=s[len(s)//3:4*len(s)//5].copy()
    q[:,0]+=2.1*np.sin(q[:,1]*.27+i*.8)
    q[:,1]+=.65*np.sin(q[:,0]*.31+i)
    weave.append(q)
s2b=newr+newtop+weave
s2b += [course([[91,127],[85,120],[87,111],[98,109]],[[98,109],[107,107],[111,113],[105,118]],[[105,118],[101,124],[109,125],[115,128]]),
        np.array([[115,128],[124,112],[125,105],[144,103]]),
        course([[133,64],[124,51],[137,44],[145,57]],[[145,57],[147,63],[147,67],[150,69]]),
        course([[183,97],[192,101],[189,109],[181,115]],[[181,115],[174,121],[188,131],[181,143]]),
        np.array([[181,143],[211,160],[206,181],[144,172],[123,176]]),
        np.array([[201,168],[161,163],[138,166]]),
        course([[84,141],[69,141],[64,148],[68,151]],[[68,151],[74,155],[87,150],[93,146]])]
save('S2',2,s2b,'After inspecting stage1, compress and kink the inherited feather bank and overlap its foot with the upper fan; replace long smooth loops with one small bulb and an unequal angular return.')
