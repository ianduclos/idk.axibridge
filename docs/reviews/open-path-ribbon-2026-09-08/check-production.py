"""Render the actual Python effect on the original study's source fixtures."""
import json
from pathlib import Path as File
import subprocess
import sys

ROOT = File(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from axibridge.effects.ribbon import Ribbon, RibbonParams
from axibridge.model import Path
from axibridge.registry import EffectContext

HERE = File(__file__).resolve().parent
fixtures = json.loads(subprocess.check_output([
    'node', '-e', 'require(process.argv[1]); console.log(JSON.stringify(globalThis.RibbonStudy.fixtures))',
    str(HERE / 'geometry.js')], text=True))
rows = []
for name in ('straight', 'corner', 'loop'):
    cells = []
    for label, extra in (
        ('Accepted smoothing', {}),
        ('More softening', {'crest_softening': .16}),
        ('Uneven softening', {'crest_softening': .16, 'smoothing_variation': 1}),
    ):
        params = RibbonParams(width=12, wavelength=31, seed=7, spacing_variation=1,
                              height_variation=1, mask_overlaps=True, **extra)
        source = Path(points=[(x/4,y/4) for x,y in fixtures[name]])
        paths = Ribbon().apply([source], params, EffectContext())
        lines = ''.join('<polyline points="'+ ' '.join(f'{x*4:.4f},{y*4:.4f}' for x,y in p.points)
                        +'"/>' for p in paths)
        cells.append(f'<section><p>{name} · {label}</p><svg viewBox="0 -10 770 260"><g fill="none" stroke="#100F0F" stroke-width=".65">{lines}</g></svg></section>')
    rows.append(''.join(cells))
css = (ROOT / 'axibridge/static/css/flexoki.css').read_text()
html = '<!doctype html><meta charset="utf-8"><title>Ribbon production review</title><style>'+css+'''
body{background:var(--flexoki-black);color:var(--flexoki-paper);font:14px system-ui;margin:24px}
h1{font-size:20px;font-weight:500}main{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
svg{display:block;width:100%;background:var(--flexoki-paper)}p{margin:0 0 8px}footer{margin-top:20px;color:var(--flexoki-400)}
</style><h1>Ribbon · Python production geometry</h1><main>'''+''.join(rows)+'''</main><footer>Same seeds and amplitude, maximum height/spacing variation. All images use the registered Python effect. Corners and self-crossings masked.</footer>'''
(HERE/'production-review.html').write_text(html)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width':1800,'height':900}, device_scale_factor=1)
    page.goto((HERE/'production-review.html').as_uri())
    page.screenshot(path=str(HERE/'production-review.png'), full_page=True)
    browser.close()
print('Rendered 9 production fixtures to production-review.html / .png')
