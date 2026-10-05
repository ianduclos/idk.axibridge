import json
import math
import subprocess
import os
from pathlib import Path
from decoder import Decoder

ROOT=Path(__file__).resolve().parent
_renderer=None
def render(data):
    global _renderer
    if _renderer is None:
        _renderer=subprocess.Popen([os.environ['MOSCA2_NODE'],str(ROOT/'renderer.mjs')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    _renderer.stdin.write(json.dumps(data)+'\n');_renderer.stdin.flush()
    result=json.loads(_renderer.stdout.readline())
    if 'error' in result: raise RuntimeError(result['error'])
    return result

def length(points): return sum(math.dist(a,b) for a,b in zip(points,points[1:]))

class DrawingBody:
    def __init__(self,seed,renderer=True,ink_budget_mm=12000):
        self.seed=seed;self.renderer=renderer;self.budget=ink_budget_mm
        self.decoder=Decoder(); self.action=0;self.strokes=[];self.events=[];self.passages=[]
        self.pending=[];self.previous=None;self.last_flush=0;self.batch=0;self.used=0;self.limited=False
        self.trace=[];self.features=[]
        self.events.append(dict(t_ms=0,kind='initialization',after='continue',action_id='a0'))

    def return_target(self,point,heading):
        self.events.append(dict(kind='return_unsupported',reason='only two calibrated modes'))
        return None

    def _emit(self,points,t_ms,kind):
        if self.limited: return False
        if len(points)<2 or length(points)<=1e-10:
            self.events.append(dict(t_ms=t_ms,kind='degenerate',source=kind));return False
        if self.used+length(points)>self.budget:
            if not self.limited: self.events.append(dict(t_ms=t_ms,kind='budget',reason='ink ceiling reached'));self.limited=True
            return False
        self.used+=length(points)
        self.strokes.append(dict(points=points,t_ms=t_ms,kind=kind,action_id=f'a{self.action}',spine_id=self.passages[-1]['id']))
        return True

    def flush(self,t_ms):
        if len(self.pending)>1 and self.renderer:
            P=self.pending[::100]
            if P[-1]!=self.pending[-1]: P=P+[self.pending[-1]]
            data=render(dict(seed=self.seed,batch=self.batch,points=P,cap_mm=max(0,self.budget-self.used)))
            self.batch+=1
            for P in data['bands']: self._emit(P,t_ms,'band')
            for P in data['echoes']: self._emit(P,t_ms,'echo')
            self.events.append(dict(t_ms=t_ms,kind='render',spine_id=self.passages[-1]['id'],action_id=f'a{self.action}',**data['metrics']))
        self.pending=[self.pending[-1]] if self.pending else []
        self.last_flush=t_ms

    def accept(self,t_ms,point,hz,path=None):
        before_count=len(self.strokes); previous=self.previous; self.previous=list(point)
        self.trace.append([t_ms,*point,self.decoder.mode]);self.features.append([t_ms,hz])
        if not (2<=point[0]<=298 and 2<=point[1]<=216):
            self.events.append(dict(t_ms=t_ms,kind='boundary',reason='outside paper margin'))
        elif self.decoder.mode=='continue' and not self.limited:
            if not self.passages or self.passages[-1]['closed']:
                self.passages.append(dict(id=f'p{len(self.passages)}',closed=False,action_id=f'a{self.action}'))
                previous=None;self.pending=[]
            P=path if path is not None else ([previous,point] if previous else [point])
            committed=self._emit(P,t_ms,'spine')
            if committed or len(P)==1:
                if not self.pending: self.pending=list(P)
                else: self.pending.extend(P[1:])
            if t_ms-self.last_flush>=500: self.flush(t_ms)
        event=self.decoder.step(t_ms,hz)
        if event:
            if event['before']=='continue':
                self.flush(t_ms)
                if self.passages: self.passages[-1]['closed']=True
                self.pending=[]
            self.action+=1;event['action_id']=f'a{self.action}';event['point']=list(point);self.events.append(event)
        return self.strokes[before_count:]


def shutdown_renderer():
    global _renderer
    if _renderer is not None:
        _renderer.terminate()
        try: _renderer.wait(timeout=2)
        except subprocess.TimeoutExpired: _renderer.kill(); _renderer.wait()
        _renderer=None
