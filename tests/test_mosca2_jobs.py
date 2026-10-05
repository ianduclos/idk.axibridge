import json,time,sys
import pytest
from axibridge.mosca2.jobs import JobManager, RunRequest

def wait(manager,id):
    for _ in range(200):
        value=manager.get(id)
        if value['status']!='running':return value
        time.sleep(.02)
    raise AssertionError('worker did not finish')

def test_request_rejects_outside_nonfinite_and_unknown_settings():
    for strokes in [[[[301,10],[20,20]]],[[[float('nan'),10],[20,20]]]]:
        with pytest.raises(ValueError):RunRequest(strokes=strokes)
    with pytest.raises(ValueError):RunRequest(settings={'brain_gain':2})

def test_job_snapshots_input_and_completion(tmp_path):
    script=tmp_path/'worker.py'
    script.write_text('import json,sys; from pathlib import Path; req=json.loads(Path(sys.argv[1]).read_text());Path(sys.argv[2]).write_text(json.dumps({"strokes":req["strokes"],"events":[],"metrics":{},"provenance":"test"}))')
    m=JobManager(command_builder=lambda req,out,progress:[sys.executable,str(script),str(req),str(out)])
    strokes=[[[10,10],[20,20]]];job=m.start(RunRequest(strokes=strokes));strokes[0][0][0]=99
    result=wait(m,job['id']);assert result['status']=='completed'
    assert result['result']['strokes'][0][0][0]==10
    m.shutdown()

def test_cancel_and_concurrent_run_guard(tmp_path):
    m=JobManager(command_builder=lambda req,out,progress:[sys.executable,'-c','import time;time.sleep(30)'])
    job=m.start(RunRequest())
    with pytest.raises(RuntimeError,match='already'):m.start(RunRequest())
    m.cancel(job['id']);assert wait(m,job['id'])['status']=='cancelled';m.shutdown()

def test_worker_failure_is_reported():
    m=JobManager(command_builder=lambda req,out,progress:[sys.executable,'-c','raise RuntimeError("fixture failure")'])
    result=wait(m,m.start(RunRequest())['id']);assert result['status']=='failed'
    assert 'fixture failure' in result['error'];m.shutdown()

@pytest.mark.parametrize('bad', [
    {'events':[{'t_ms':13000,'kind':'drawing'}]},
    {'events':[{'t_ms':100,'kind':'drawing','detail':'x'*201}]},
    {'provenance':'x'*10001},
])
def test_worker_metadata_must_be_keepable(tmp_path,bad):
    result={'strokes':[[[10,10],[20,20]]],'events':[],
            'metrics':{},'provenance':'test',**bad}
    script=tmp_path/'worker.py'
    script.write_text('from pathlib import Path; import sys; '
                      f'Path(sys.argv[1]).write_text({json.dumps(result)!r})')
    m=JobManager(command_builder=lambda req,out,progress:[sys.executable,str(script),str(out)])
    try:
        assert wait(m,m.start(RunRequest())['id'])['status']=='failed'
    finally:
        m.shutdown()
