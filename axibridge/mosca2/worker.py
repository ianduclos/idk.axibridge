"""Full Mosca brain; original flowing body with paper-space tactile feedback.

Standalone subprocess: imports Mosca's unchanged Fly/Body/Registry, never the
AxiBridge application, hardware or its environment. Each job is a fresh bout.
"""
import argparse,hashlib,json,math,os,sys,time
from pathlib import Path
import numpy as np
from shapely.geometry import LineString,box
from drawing import DrawingBody,shutdown_renderer,render
from geometry import paper_pose,sensor_points,simplify_runs

PAGE=box(2,2,298,216)

def line_parts(g):
    if g.is_empty:return []
    if g.geom_type=='LineString':return [list(g.coords)]
    return [p for child in getattr(g,'geoms',[]) for p in line_parts(child)]

class FlowingBody(DrawingBody):
    def __init__(self,seed,start,scale):
        super().__init__(seed)
        self.start=start;self.scale=scale

    def flush(self,t_ms):
        if len(self.pending)>1:
            p=self.pending[::100]
            if p[-1]!=self.pending[-1]:p=p+[self.pending[-1]]
            local=[[(x-self.start[0])/self.scale+150,(y-self.start[1])/self.scale+109] for x,y in p]
            data=render(dict(seed=self.seed,batch=self.batch,points=local,cap_mm=max(0,(self.budget-self.used)/self.scale)))
            self.batch+=1
            for kind,key in [('band','bands'),('echo','echoes')]:
                for stroke in data[key]:
                    placed=[[self.start[0]+self.scale*(x-150),self.start[1]+self.scale*(y-109)] for x,y in stroke]
                    self._emit(placed,t_ms,kind)
        self.pending=[self.pending[-1]] if self.pending else []
        self.last_flush=t_ms

    def _emit(self,points,t_ms,kind):
        if len(points)<2:return False
        pieces=[points] if all(2<=x<=298 and 2<=y<=216 for x,y in points) else line_parts(LineString(points).intersection(PAGE))
        emitted=False
        for p in pieces:emitted=super()._emit(p,t_ms,kind) or emitted
        return emitted

    def accept(self,t_ms,point,hz,path=None):
        # Preserve real pen-up gaps across excursions outside the paper. Do not
        # join a departure and later re-entry with an invented connector.
        if not all(2<=x<=298 and 2<=y<=216 for x,y in path):
            before=len(self.strokes)
            self.flush(t_ms)
            if self.passages:self.passages[-1]['closed']=True
            self.pending=[];self.previous=None
            event=self.decoder.step(t_ms,hz)
            if event:self.events.append(event)
            return self.strokes[before:]
        return super().accept(t_ms,point,hz,path)

def atomic(path,data):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,separators=(',',':'),allow_nan=False));temporary.replace(path)

def run(args):
    os.environ['MOSCA2_NODE']=args.node
    sys.path.insert(0,str(args.root/'src'))
    import fly,body,senses,world
    fly.assert_brain_untouched()
    request=json.loads(args.request.read_text());settings=request['settings'];scale=settings['gesture_scale'];factor=3*scale
    seed=settings['seed'];duration=settings['duration_s']*1000;dt=.1;steps=round(duration/dt)
    reg=senses.Registry(args.root/'data',side_source='anno')
    animal=fly.Fly(args.root/'data',dt=dt,seed=seed)
    leg=[senses.leg_motor(reg,side) for side in ('L','R')]
    feedback=reg.pair('class=olfactory');tonic=reg.select('frudsx=fru_high')
    tactile=[reg.select('class=mechanosensory_tactile,nerve=ProLN,side='+side) for side in ('L','R')]
    feature=np.unique(np.concatenate([reg.select('type=DNg13,side='+side) for side in ('L','R')]))
    if any(not len(p) for p in [*leg,*feedback,*tactile,tonic,feature]):raise ValueError('A required Mosca neural population is empty.')
    masks=[]
    for pool in [*leg,feature]:
        mask=np.zeros(animal.n,bool);mask[pool]=True;masks.append(mask)
    # Exact earlier flowing kinematics, without the later broad-arc substitution.
    bod=body.Body(dt=dt,n_left=len(leg[0]),n_right=len(leg[1]),speed_per_hz=.0009,turn_per_hz=.0064,trace_tau=20.)
    bod.heading=-math.radians(settings['heading_deg'])
    base=world.PageInk(.2*factor,.8*factor,0);own=world.PageInk(.2*factor,.8*factor,200)
    for stroke in request['strokes']:
        for a,b in zip(stroke,stroke[1:]):base.deposit(a,b,-1000)
    start=(settings['start_x'],settings['start_y'])
    drawing=FlowingBody(seed,start,scale);ink_rng=np.random.default_rng(seed+2909)
    relation=[0.,0.];counts=np.zeros(steps,np.int32);motor_hash=hashlib.sha256();spike_hash=hashlib.sha256()
    x,y,h=paper_pose(0,0,bod.heading,*start,scale)
    chunk=[[x,y]];events=[];last_state=None;contact_ticks=0;outside_ms=0;pen_up_ms=0;started=time.monotonic();trace=[]
    def state_event(state,t):
        nonlocal last_state
        if state!=last_state:
            events.append({'t_ms':float(t),'kind':state,'detail':{'drawing':'Pen down','lifted':'DNg13 decoder lifted the pen','outside':'Outside paper; mechanical pen lift'}[state]});last_state=state
    for step in range(steps):
        t=step*dt
        if step%100==0:
            x,y,h=paper_pose(bod.x,bod.y,bod.heading,*start,scale)
            probes=sensor_points(x,y,math.degrees(h),scale)
            relation=[max(base.sense(px,py,h,t)[0],own.sense(px,py,h,t)[0]) for px,py in probes]
            if max(relation)>0:contact_ticks+=1
        forced=[]
        if settings['contact_hz']:
            for pool,near in zip(tactile,relation):
                chance=settings['contact_hz']*near*dt/1000
                if chance>0:forced.append(pool[ink_rng.random(len(pool))<min(chance,1.)])
        dl,dr=bod.proprioceptive_drive()
        if t<100:dl=dr=100
        forced.extend([animal.poisson(feedback[0],dl),animal.poisson(feedback[1],dr),animal.poisson(tonic,40)])
        fired=animal.step(np.concatenate(forced));nL=int(np.count_nonzero(masks[0][fired]));nR=int(np.count_nonzero(masks[1][fired]));counts[step]=np.count_nonzero(masks[2][fired])
        motor_hash.update(np.array([nL,nR],dtype='<i4').tobytes());spike_hash.update(np.array([step,len(fired)],dtype='<i8').tobytes()+fired.astype('<i8',copy=False).tobytes())
        bod.update(nL,nR);x,y,h=paper_pose(bod.x,bod.y,bod.heading,*start,scale);chunk.append([x,y])
        outside=not(2<=x<=298 and 2<=y<=216)
        outside_ms+=dt if outside else 0;pen_up_ms+=dt if drawing.decoder.mode!='continue' else 0
        if (step+1)%1000==0 or step==steps-1:
            now=(step+1)*dt;hz=float(counts[max(0,step+1-2000):step+1].sum())/(len(feature)*.2)
            drawn=drawing.accept(now,[x,y],hz,path=chunk)
            for stroke in drawn:
                for a,b in zip(stroke['points'],stroke['points'][1:]):own.deposit(a,b,now)
            chunk=[[x,y]];state='outside' if outside else ('drawing' if drawing.decoder.mode=='continue' else 'lifted');state_event(state,now)
            trace.append([now,x,y,h,hz])
            if (step+1)%5000==0 or step==steps-1:
                atomic(args.progress,{'progress':(step+1)/steps,'state':state,'preview':simplify_runs([s['points'] for s in drawing.strokes],.02)})
    drawing.flush(duration)
    strokes=simplify_runs([s['points'] for s in drawing.strokes])
    weight_hash=hashlib.sha256(animal.W.data.tobytes()+animal.W.indices.tobytes()+animal.W.indptr.tobytes()).hexdigest()
    provenance={'engine':'mosca2-v1','brain':fly._fingerprint(),'weight_sha256':weight_hash,'input_sha256':hashlib.sha256(json.dumps(request['strokes'],separators=(',',':')).encode()).hexdigest(),'settings':settings,'body':{'speed_per_hz':.0009,'turn_per_hz':.0064,'trace_tau':20.},'decoder':'DNg13 45 Hz, 300 ms persistence, 1000 ms hold','renderer':'original bundleGeom + growField, 500 ms batches','sensing':'paper mm; original .55/±.42 front sensors, scaled uniformly with gesture; recent own ink excluded 200 ms','fresh_neural_bout':True,'source_sha256':{name:hashlib.sha256((args.root/'src'/name).read_bytes()).hexdigest() for name in ('fly.py','body.py','senses.py','world.py')}}
    return {'strokes':strokes,'events':events,'metrics':{'contact_samples':contact_ticks,'outside_ms':round(outside_ms,1),'pen_up_ms':round(pen_up_ms,1),'ink_mm':drawing.used,'elapsed_s':time.monotonic()-started,'motor_sha256':motor_hash.hexdigest(),'spike_sha256':spike_hash.hexdigest(),'brain_fingerprint':fly._fingerprint(),'weight_sha256':weight_hash},'provenance':json.dumps(provenance,separators=(',',':'))}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('root','request','output','progress'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--node',required=True);args=parser.parse_args()
    try:atomic(args.output,run(args))
    finally:shutdown_renderer()
