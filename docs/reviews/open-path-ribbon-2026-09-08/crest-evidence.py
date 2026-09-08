"""Neutral crest population, with regular and ungrouped controls."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
HERE=Path(__file__).resolve().parent
rows=[]
for seed in [7,19,43,81]:
    variants=[dict(rhythm='phrased',phrasing=.75),dict(rhythm='legacy'),dict(rhythm='phrased',phrasing=0)]
    if seed==43: variants=variants[1:]+variants[:1]
    if seed==81: variants[2]=dict(rhythm='phrased',phrasing=1,spacingVariation=0,heightVariation=0)
    for v in variants:
        rows.append(dict(id=f'R{len(rows)+1:02}',seed=seed,shape='straight',**v))
rows += [dict(id='R13',seed=19,shape='sCurve',rhythm='phrased',phrasing=.75),dict(id='R14',seed=43,shape='corner',rhythm='phrased',phrasing=.75),dict(id='R15',seed=7,shape='loop',rhythm='phrased',phrasing=.75)]
(HERE/'crest-review-map.json').write_text(json.dumps(rows,indent=2)+'\n')
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1440,'height':1200})
    page.set_content('<main id="sheet" style="background:#FFFCF0;color:#100F0F;padding:20px;display:grid;grid-template-columns:repeat(3,1fr);gap:20px;font:14px monospace"></main>')
    for file in ['vendor/polygon-clipping-0.15.7.js','corner-envelope.js','masking.js','geometry.js']:
        page.add_script_tag(content=(HERE/file).read_text())
    page.evaluate('''rows=>{
      for(const c of rows){
        const r=RibbonStudy.generate(RibbonStudy.fixtures[c.shape],{width:42,wavelength:110,variation:.85,spacingVariation:.85,heightVariation:.85,steps:10,taper:.07,relation:'related',...c});
        const ps=r.strands.flat(), xs=ps.map(p=>p[0]),ys=ps.map(p=>p[1]);
        const v=[Math.min(...xs)-12,Math.min(...ys)-12,Math.max(...xs)-Math.min(...xs)+24,Math.max(130,Math.max(...ys)-Math.min(...ys)+24)];
        const path=ps=>ps.map((p,i)=>(i?'L':'M')+p.join(' ')).join(' ');
        document.getElementById('sheet').insertAdjacentHTML('beforeend',`<section id="${c.id}"><div>${c.id}</div><svg style="width:100%;height:185px" viewBox="${v.join(' ')}"><g fill="none" stroke="#100F0F" stroke-width=".7" stroke-linejoin="round">${r.strands.map(s=>`<path d="${path(s)}"/>`).join('')}</g></svg></section>`);
      }
    }''',rows)
    page.locator('#sheet').screenshot(path=str(HERE/'crest-population.png'))
    for id in ['R01','R02','R03','R04','R08','R12','R14']:
        el=page.locator('#'+id)
        el.evaluate('(e)=>{e.style.width="1050px";e.querySelector("svg").style.height="340px"}')
        el.screenshot(path=str(HERE/(id+'-crest.png')))
        el.evaluate('(e)=>{e.style.width="";e.querySelector("svg").style.height="185px"}')
    browser.close()
print('Captured 15 neutral crest cases and seven close views.')
