"""Offline layout fixtures from existing pure generators; never starts the app."""
import json, re
from pathlib import Path
from axibridge.sources.second_reading import SecondReading, SecondReadingParams
from axibridge.sources.homeostat import Homeostat, HomeostatParams
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent / 'assets'
ink = re.search(r'--flexoki-950:\s*(#[0-9A-F]+)', (ROOT/'axibridge/static/css/flexoki.css').read_text()).group(1)
def write(name, mod, params):
    doc = mod.generate(params)
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s">' % ((300, 218) if isinstance(params, HomeostatParams) else (params.width, params.height)), f'<g fill="none" stroke="{ink}" stroke-width="0.28" stroke-linejoin="round" stroke-linecap="round">']
    for _, path in doc.iter_paths():
        lines.append('<polyline points="'+' '.join(f'{x:.4f},{y:.4f}' for x,y in path.points)+'"/>')
    (OUT/(name+'.svg')).write_text(''.join(lines)+'</g></svg>')
    (OUT/(name+'.json')).write_text(params.model_dump_json(indent=2))
base=json.loads((ROOT/'shots/second-reading-recovery-final-0906/bench-second-exchange.json').read_text())
for turn in (11,12,13):
    p={**base,'turns':turn}
    write(f'second-{turn}',SecondReading(),SecondReadingParams(**p))
p={**base,'turns':12,'events':base['events']+[{'kind':'branch','turn':12,'seed':91}]}
write('second-alternative',SecondReading(),SecondReadingParams(**p))
for step in (300,450,600):
    write(f'homeostat-{step}',Homeostat(),HomeostatParams(seed=42,steps=step,pens=2,measure='surprise',target=.3,tolerance=.2,variety=.35,escalation=.4))
print('Seven geometry fixtures and exact recipes written.')
# A schematic placement for the Compose layout (not a resolved project).
source=(OUT/'second-11.svg').read_text()
inner=source[source.index('>')+1:source.rindex('</svg>')]
scale=(ROOT/'axibridge/static/css/flexoki.css').read_text()
blue=re.search(r'--flexoki-blue-400:\s*(#[0-9A-F]+)',scale).group(1)
(OUT/'compose.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 218 300"><g transform="translate(15 12) scale(.68) translate(198 0) rotate(90)">'+inner+'</g>'+f'<rect x="15" y="12" width="134.64" height="190.4" fill="none" stroke="{blue}" stroke-width=".4" stroke-dasharray="2 2"/></svg>')
