"""Replay the particular edits and verify the saved physical geometry."""
from pathlib import Path
import hashlib, json, subprocess, sys, math
root=Path(__file__).resolve().parent; repo=root.parents[2]
files=list((root/'inputs').glob('*.json'))+list(root.glob('*/S*-stage*.json'))
before={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
commands=[['material/edit.py','stage1'],['material/edit.py','stage2'],['connections/edit.py'],['composition/edit.py','1'],['composition/edit.py','2']]
for cmd in commands:subprocess.run([sys.executable,str(root/cmd[0]),*cmd[1:]],cwd=repo,check=True,capture_output=True)
after={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
assert before==after,'Replay altered saved geometry or inputs'
records=[]
for p in sorted(root.glob('*/S*-stage*.json')):
    d=json.loads(p.read_text()); assert d['strokeMm']==.1 and d['pageMm']==[300,218]
    assert d['parent']==(p.stem[:2] if 'stage1' in p.stem else d['id'].replace('stage2','stage1'))
    maximum=0;ink=0;points=0
    for line in d['strokes']:
        assert len(line)>1;points+=len(line)
        for x,y in line:assert math.isfinite(x) and math.isfinite(y) and 0<=x<=300 and 0<=y<=218
        lengths=[math.dist(a,b) for a,b in zip(line,line[1:])];ink+=sum(lengths);maximum=max(maximum,max(lengths))
    records.append({'file':str(p.relative_to(root)),'id':d['id'],'parent':d['parent'],'points':points,'inkMm':ink,'maxSegmentMm':maximum,'sha256':after[str(p.relative_to(root))]})
assert len(records)==12
sources={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*.py'))}
(root/'evidence/replay-checks.json').write_text(json.dumps({'byteIdenticalReplay':True,'inputsUnchanged':True,'sourceHashes':sources,'records':records,'limits':'Long intentional straight spans are allowed; bounds/replay checks do not judge appearance or establish a general generator.'},indent=2)+'\n')
print('12 edited states replay byte-identically; inputs unchanged; finite/bounds/page/stroke/parents verified.')
