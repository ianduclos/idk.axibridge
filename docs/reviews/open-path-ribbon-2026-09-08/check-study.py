"""Rebuild the exploratory fragment and verify it without running the app."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
KIT = Path('/Users/ianduclos/.codex/plugins/cache/openai-bundled/visualize/1.0.29/skills/visualize')
OUT = Path('/Users/ianduclos/.codex/visualizations/2026/09/08/01a0829a-4f4d-7ca2-9598-db957c16b868/open-path-ribbon.html')


def run():
    fragment = (HERE / 'study-template.html').read_text().replace('/* GEOMETRY_INSERT */', (HERE / 'geometry.js').read_text())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(fragment)
    css = (KIT / 'assets/visualize.css').read_text()
    kit = (KIT / 'assets/visualize.html').read_text()
    document = '<!doctype html><html><head><style>' + css + '</style></head><body>' + kit.replace('<!--__INLINE_VISUALIZATION_FRAGMENT__-->',fragment) + '</body></html>'
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width':736,'height':1100}, device_scale_factor=1)
        page.on('pageerror',lambda e: errors.append(str(e)))
        page.set_content(document,wait_until='domcontentloaded')
        page.wait_for_selector('#ribbon-study[data-rendered="true"]')
        assert page.locator('.ribbon-drawing').count() == 3
        before = page.locator('.ribbon-ink').first.inner_html()
        page.locator('#ribbon-next').click()
        assert page.locator('#ribbon-study').get_attribute('data-seed') == '8'
        assert page.locator('.ribbon-ink').first.inner_html() != before
        for shape in ['straight','arch','sCurve','corner','hairpin']:
            page.select_option('#ribbon-shape',shape)
            for width in [24,90]:
                page.locator('#ribbon-width').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input"));}',width)
                assert page.locator('.ribbon-ink path').count() == 63
                assert not page.locator('#ribbon-drawings').evaluate('(e)=>/NaN|Infinity/.test(e.innerHTML)')
        page.locator('#ribbon-steps').evaluate('(e)=>{e.value=1;e.dispatchEvent(new Event("input"));}')
        assert page.locator('.ribbon-ink path').count() == 9
        page.locator('#ribbon-guide').check()
        assert page.locator('.ribbon-guide').count() == 3
        page.select_option('#ribbon-shape','sCurve')
        for id,value in [('width',24),('steps',10)]:
            page.locator('#ribbon-'+id).evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input"));}',value)
        page.locator('#ribbon-guide').uncheck()
        for size in [736,360]:
            page.set_viewport_size({'width':size,'height':1200})
            for theme in ['light','dark']:
                page.emulate_media(color_scheme=theme)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'horizontal overflow'
                page.locator('#ribbon-study').screenshot(path=str(HERE / f'preview-{size}-{theme}.png'))
        # Neutral labels: mechanisms are kept in review-map.json, not on sheets.
        page.set_viewport_size({'width':1140,'height':1400})
        page.emulate_media(color_scheme='light')
        cases = []
        relations = ['independent','mirrored','related']
        for shape in ['straight','arch','sCurve','corner','hairpin']:
            for relation in relations:
                cases.append(dict(id=f'F{len(cases)+1:02}',shape=shape,relation=relation,seed=7,width=32))
        population=[]
        for seed in [8,19,43]:
            for relation in relations:
                population.append(dict(id=f'P{len(population)+1:02}',shape='sCurve',relation=relation,seed=seed,width=32))
        # Same bend at two widths; rejected narrowing evidence is archived separately.
        population += [dict(id='P10',shape='hairpin',relation='related',seed=7,width=85),
                       dict(id='P11',shape='hairpin',relation='related',seed=7,width=42),
                       dict(id='P12',shape='sCurve',relation='related',seed=7,width=32,variation=0)]
        (HERE/'review-map.json').write_text(json.dumps(cases+population,indent=2)+'\n')
        for name,rows in [('fixtures',cases),('population',population)]:
            page.evaluate('''rows => {
              const path=ps=>ps.map((p,i)=>(i?'L':'M')+p.join(' ')).join(' ');
              const fixtures=typeof RibbonStudy.fixtures==='function'?RibbonStudy.fixtures():RibbonStudy.fixtures;
              document.body.innerHTML='<main id="sheet" style="background:#FFFCF0;color:#100F0F;padding:20px;display:grid;grid-template-columns:repeat(3,1fr);gap:14px;font:14px monospace"></main>';
              const sheet=document.getElementById('sheet');
              for(const c of rows) {
                const r=RibbonStudy.generate(fixtures[c.shape],{...c,wavelength:120,variation:c.variation??.55,steps:10,taper:.12});
                const ps=r.strands.flat();let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
                for(const [x,y] of ps){x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y);}
                const v=[x0-12,y0-12,x1-x0+24,y1-y0+24];
                sheet.insertAdjacentHTML('beforeend',`<section id="${c.id}" style="background:#FFFCF0"><div>${c.id}</div><svg style="width:100%;height:175px" viewBox="${v.join(' ')}"><g fill="none" stroke="#100F0F" stroke-width=".7" stroke-linejoin="round">${r.strands.map(s=>`<path d="${path(s)}"/>`).join('')}</g></svg></section>`);
              }
            }''',rows)
            page.locator('#sheet').screenshot(path=str(HERE/f'{name}.png'))
            for c in rows:
                if c['id'] in ['F03','F10','F12','F15','P10','P11']:
                    page.locator('#'+c['id']).evaluate('(e)=>e.style.width="950px"')
                    page.locator('#'+c['id']+' svg').evaluate('(e)=>e.style.height="420px"')
                    page.locator('#'+c['id']).screenshot(path=str(HERE/(c['id']+'.png')))
                    page.locator('#'+c['id']).evaluate('(e)=>e.style.width=""')
                    page.locator('#'+c['id']+' svg').evaluate('(e)=>e.style.height="175px"')
        browser.close()
    assert not errors, errors
    print('PASS: controls, 10 shape/width states, strand counts, seed changes, finite SVG, 360/736 layouts in light/dark; captured 27 neutral study cells.')
    print(OUT)


if __name__ == '__main__':
    run()
