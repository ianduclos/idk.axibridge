import json
from pathlib import Path
from playwright.sync_api import sync_playwright
HERE=Path(__file__).resolve().parent
css=(HERE.parents[2]/'axibridge/static/css/flexoki.css').read_text()
frames=[]
for label,name in [('A','before'),('B','after')]:
 paths=json.loads((HERE/f'{name}.json').read_text())
 lines=''.join('<polyline points="'+' '.join(f'{220-y:.6f},{x:.6f}' for x,y in p['points'])+'"/>' for p in paths)
 frames.append(f'<section><h2>{label}</h2><svg viewBox="10 0 190 250"><g fill="none" stroke="#100F0F" stroke-width=".12">{lines}</g></svg></section>')
(HERE/'comparison.html').write_text('<!doctype html><meta charset="utf-8"><title>Ribbon corner comparison</title><style>'+css+'body{background:var(--flexoki-black);color:var(--flexoki-paper);font:14px system-ui;margin:20px}main{display:grid;grid-template-columns:1fr 1fr;gap:20px}h2{font-size:16px;font-weight:500}svg{display:block;width:100%;background:var(--flexoki-paper)}</style><main>'+''.join(frames)+'</main>')
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':1500,'height':1100})
 page.goto((HERE/'comparison.html').as_uri());page.screenshot(path=str(HERE/'comparison.png'),full_page=True);b.close()
