import json, sys
from pathlib import Path as File
ROOT=File(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from axibridge.sources.pen import PenSource, PenParams
from axibridge.effects.ribbon import Ribbon
from axibridge.compose import CanvasLayer, shape_layer
HERE=File(__file__).resolve().parent
layer=CanvasLayer(**json.loads((HERE/'input.json').read_text()))
doc=PenSource().generate(PenParams(**layer.source.params))
source=[p for l in doc.layers for p in l.paths]
paths=shape_layer(layer,source)
name=sys.argv[1] if len(sys.argv)>1 else 'candidate'
(HERE/f'{name}.json').write_text(json.dumps([p.model_dump() for p in paths]))
lines=''.join('<polyline points="'+' '.join(f'{220-y:.5f},{x:.5f}' for x,y in p.points)+'"/>' for p in paths)
(HERE/f'{name}.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 10 130 240" width="650" height="1200"><rect x="10" y="10" width="130" height="240" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width=".12">'+lines+'</g></svg>')
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(); page=b.new_page(viewport={'width':650,'height':1200})
 page.goto((HERE/f'{name}.svg').as_uri());page.screenshot(path=str(HERE/f'{name}.png'));b.close()
print(name,len(paths),sum(len(p.points) for p in paths))
