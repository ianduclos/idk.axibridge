"""One isolated, cancellable neural worker; no project or machine mutation."""
from __future__ import annotations
import atexit,copy,json,os,shutil,signal,subprocess,sys,tempfile,threading,time,uuid
from pathlib import Path
from pydantic import BaseModel,ConfigDict,Field,model_validator
from ..sources.mosca2 import Strokes,RunSettings,Mosca2Params,Mosca2History
from ..mosca import DEFAULT_MOSCA_DIR

HERE=Path(__file__).resolve().parent

class RunRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    strokes: Strokes=Field(default_factory=list,max_length=50000)
    settings: RunSettings=Field(default_factory=RunSettings)
    @model_validator(mode='after')
    def budget(self):
        if sum(map(len,self.strokes))>250000:raise ValueError('page point budget exceeded (250000)')
        return self

def mosca_root():
    p=Path(os.environ.get('AXIBRIDGE_MOSCA_DIR',str(DEFAULT_MOSCA_DIR))).expanduser()
    return p.parent if p.name=='out' else p

def runtime():
    root=mosca_root()
    for name in ['src/fly.py','src/body.py','src/senses.py','src/world.py','data/W_signed.npz','data/meta.npz','data/body-annotations-male-cns-v1.0-minconf-0.5.feather']:
        if not (root/name).is_file():return None,None,'Mosca brain data is unavailable. Existing compositions can still be edited and kept.'
    node=os.environ.get('AXIBRIDGE_MOSCA2_NODE') or shutil.which('node')
    if not node:
        node=next((str(p) for p in [Path('/opt/homebrew/bin/node'),Path('/usr/local/bin/node')] if p.is_file()),None)
    if not node:return None,None,'The flowing-line renderer needs Node. Existing drawings remain available.'
    override=os.environ.get('AXIBRIDGE_MOSCA2_PYTHON')
    candidates=[Path(override)] if override else [Path(sys.executable)]
    if not override:
        # Reuse an existing compatible scratch runtime. Never install or resolve packages.
        for site in sorted(Path.home().glob('.cache/uv/environments-v2/*/*/lib/python*/site-packages')):
            if (site/'numpy-2.2.6.dist-info').is_dir() and all((site/n).is_dir() for n in ('numba','pyarrow','shapely','scipy')):
                candidates.append(site.parents[2]/'bin/python')
    for python in candidates:
        if not python.is_file():continue
        try:
            ok=subprocess.run([str(python),'-c','import numpy, scipy, pyarrow, numba, shapely'],capture_output=True,timeout=15)
            if ok.returncode==0:return str(python),str(node),''
        except (OSError,subprocess.TimeoutExpired):pass
    return None,None,'A compatible Mosca runtime is unavailable. Configure AXIBRIDGE_MOSCA2_PYTHON; no packages were changed.'

def status():
    python,node,reason=runtime()
    return {'available':bool(python and node),'reason':reason}

def worker_command(request,output,progress):
    python,node,reason=runtime()
    if not python:raise RuntimeError(reason)
    return [python,str(HERE/'worker.py'),'--root',str(mosca_root()),'--node',node,'--request',str(request),'--output',str(output),'--progress',str(progress)]

class JobManager:
    def __init__(self,command_builder=worker_command):
        self.command_builder=command_builder;self.jobs={};self.lock=threading.RLock()

    def start(self,request:RunRequest):
        with self.lock:
            if any(j['status']=='running' for j in self.jobs.values()):raise RuntimeError('A fly run is already active. Finish or cancel it first.')
            while len(self.jobs)>=12:
                key=next(iter(self.jobs));old=self.jobs.pop(key);shutil.rmtree(old['_dir'],ignore_errors=True)
            folder=Path(tempfile.mkdtemp(prefix='axibridge-mosca2-'));request_path=folder/'request.json'
            request_path.write_text(request.model_dump_json())
            try:command=self.command_builder(request_path,folder/'result.json',folder/'progress.json')
            except Exception:
                shutil.rmtree(folder,ignore_errors=True);raise
            id=uuid.uuid4().hex
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NUMBA_CACHE_DIR':str(folder/'numba')}
            log=(folder/'worker.log').open('w')
            try:process=subprocess.Popen(command,stdout=log,stderr=log,cwd=folder,env=env,start_new_session=True)
            except Exception:
                log.close();shutil.rmtree(folder,ignore_errors=True);raise
            log.close()
            job={'id':id,'status':'running','progress':0,'state':'Preparing brain','_dir':folder,'_process':process,'_start':time.monotonic()}
            self.jobs[id]=job
            thread=threading.Thread(target=self._watch,args=(id,),daemon=True,name='mosca2-job');job['_thread']=thread;thread.start()
            return {'id':id,'status':'running'}

    def _watch(self,id):
        job=self.jobs[id];process=job['_process'];folder=job['_dir']
        try:
            process.wait(timeout=480)
            with self.lock:
                if job['status']=='cancelled':return
                if process.returncode:
                    log=(folder/'worker.log').read_text(errors='replace')[-3000:]
                    raise RuntimeError(log.strip() or 'Fly worker exited without a drawing.')
                result=json.loads((folder/'result.json').read_text())
                # Never let malformed/out-of-frame worker output become kept geometry.
                Mosca2Params(history=[Mosca2History(
                    id='response',label='Response',added=result['strokes'],
                    events=result.get('events',[]),provenance=result.get('provenance',''),
                )])
                job.update(status='completed',state='Finished',progress=1,result=result)
        except Exception as exc:
            with self.lock:
                if job['status']=='cancelled':return
                self._kill(process)
                job.update(status='failed',state='Failed',error=str(exc)[-3000:])

    @staticmethod
    def _kill(process):
        if process.poll() is None:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait(timeout=5)

    def get(self,id):
        with self.lock:
            job=self.jobs[id];data={k:copy.deepcopy(v) for k,v in job.items() if not k.startswith('_')}
            if data['status']=='running':
                try:
                    progress=json.loads((job['_dir']/'progress.json').read_text())
                    data.update({k:progress[k] for k in ('progress','state','preview') if k in progress})
                except (OSError,ValueError):pass
            return data

    def cancel(self,id):
        with self.lock:
            job=self.jobs[id]
            if job['status']=='running':
                job.update(status='cancelled',state='Cancelled');self._kill(job['_process'])
            return self.get(id)

    def shutdown(self):
        with self.lock:ids=list(self.jobs)
        for id in ids:self.cancel(id)
        for id in ids:
            job=self.jobs[id];job['_thread'].join(timeout=2);shutil.rmtree(job['_dir'],ignore_errors=True)
        with self.lock:self.jobs.clear()

manager=JobManager()
atexit.register(manager.shutdown)
