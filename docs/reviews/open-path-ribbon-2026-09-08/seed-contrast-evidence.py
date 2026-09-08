"""Neutral crest population, with regular and ungrouped controls."""
from pathlib import Path
import json
import subprocess
from playwright.sync_api import sync_playwright
HERE=Path(__file__).resolve().parent
rows=[dict(id=f'S{i+1:02}',seed=seed,shape='straight',rhythm='phrased',phrasing=.7,variant=variant) for i,(variant,seed) in enumerate((v,s) for v in ['before','after'] for s in [7,19,43])]
(HERE/'seed-contrast-map.json').write_text(json.dumps(rows,indent=2)+'\n')
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1440,'height':1200})
    page.set_content('<main id="sheet" style="background:#FFFCF0;color:#100F0F;padding:20px;display:grid;grid-template-columns:repeat(3,1fr);gap:20px;font:14px monospace"></main>')
    for file in ['vendor/polygon-clipping-0.15.7.js','corner-envelope.js','masking.js','geometry.js']:
        page.add_script_tag(content=(HERE/file).read_text())
    page.add_script_tag(content=subprocess.check_output(['git','show','10713ec:docs/reviews/open-path-ribbon-2026-09-08/geometry.js'],text=True).replace('root.RibbonStudy = api;', 'root.RibbonBefore = api;'))
    page.evaluate('''rows=>{
      for(const c of rows){
        const engine=c.variant==='before'?RibbonBefore:RibbonStudy;
        const r=engine.generate(engine.fixtures[c.shape],{width:42,wavelength:120,variation:.75,spacingVariation:.75,heightVariation:.75,steps:10,taper:.07,relation:'related',...c});
        const ps=r.strands.flat(), xs=ps.map(p=>p[0]),ys=ps.map(p=>p[1]);
        const v=[Math.min(...xs)-12,Math.min(...ys)-12,Math.max(...xs)-Math.min(...xs)+24,Math.max(130,Math.max(...ys)-Math.min(...ys)+24)];
        const path=ps=>ps.map((p,i)=>(i?'L':'M')+p.join(' ')).join(' ');
        document.getElementById('sheet').insertAdjacentHTML('beforeend',`<section id="${c.id}"><div>${c.id}</div><svg style="width:100%;height:185px" viewBox="${v.join(' ')}"><g fill="none" stroke="#100F0F" stroke-width=".7" stroke-linejoin="round">${r.strands.map(s=>`<path d="${path(s)}"/>`).join('')}</g></svg></section>`);
      }
    }''',rows)
    page.locator('#sheet').screenshot(path=str(HERE/'seed-contrast.png'))
    for id in []:
        el=page.locator('#'+id)
        el.evaluate('(e)=>{e.style.width="1050px";e.querySelector("svg").style.height="340px"}')
        el.screenshot(path=str(HERE/(id+'-crest.png')))
        el.evaluate('(e)=>{e.style.width="";e.querySelector("svg").style.height="185px"}')
    browser.close()
print('Captured matched seed comparison: before S01–03, after S04–06.')
