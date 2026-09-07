"""Browser checks for the disconnected design artifact, not application tests."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1500,'height':1160},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto((ROOT/'index.html').as_uri(),wait_until='domcontentloaded')
    page.evaluate('document.fonts.ready')
    checks=[]
    for size in ('desktop','compact','small'):
        page.locator('#size').select_option(size)
        for view in ('compose','second','homeostat'):
            page.locator(f'[data-view="{view}"]').click()
            for presentation in (('embedded',) if view=='compose' else ('embedded','popup')):
                page.locator('#presentation').select_option(presentation)
                page.locator('#window').screenshot(path=str(ROOT/f'assets/{view}-{size}-{presentation}.png'))
                measurement=page.evaluate('''() => {
                  const w=document.querySelector('#window'), stage=document.querySelector('.stage');
                  const paper=document.querySelector('.paper-wrap,.bed-sheet');
                  const a=stage.getBoundingClientRect(),b=paper.getBoundingClientRect();
                  return {windowWidth:w.clientWidth,overflow:w.scrollWidth-w.clientWidth,
                  stage:[a.width,a.height],paper:[b.width,b.height],
                  contained:b.left>=a.left&&b.top>=a.top&&b.right<=a.right+.5&&b.bottom<=a.bottom+.5,
                  images:[...document.querySelectorAll('img')].every(i=>i.complete&&i.naturalWidth>0)};
                }''')
                assert measurement['overflow']==0,(size,view,presentation,measurement)
                assert measurement['contained'] and measurement['images'],(size,view,presentation,measurement)
                ratio={'compose':218/300,'second':280/198,'homeostat':300/218}[view]
                assert abs(measurement['paper'][0]/measurement['paper'][1]-ratio)<.01,measurement
                checks.append({'size':size,'view':view,'presentation':presentation,**measurement})
    page.locator('#size').select_option('compact')
    page.locator('#presentation').select_option('embedded')
    page.locator('[data-view="second"]').click()
    page.get_by_role('button',name='Your turn',exact=True).click()
    assert page.locator('.stage.armed').count()==1
    page.keyboard.press('Escape')
    assert page.locator('.stage.armed').count()==0
    page.get_by_role('button',name='Continue one turn',exact=True).click()
    assert page.locator('#scrub').input_value()=='12'
    page.get_by_role('button',name='Try another',exact=True).click()
    assert page.locator('.bench-state strong').inner_text()=='Reading 2'
    page.locator('#window').screenshot(path=str(ROOT/'assets/second-compact-controls.png'))
    page.get_by_role('button',name='Compare at shared scale',exact=True).click()
    assert page.locator('.compare figure').count()==2
    page.locator('#window').screenshot(path=str(ROOT/'assets/second-compact-compare.png'))
    page.get_by_role('button',name='Show preview failure',exact=True).click()
    assert page.get_by_role('button',name='Keep as layer',exact=True).is_disabled()
    assert page.locator('.compare img').evaluate_all('els=>{const s=document.querySelector(".stage").getBoundingClientRect();return els.every(e=>{const r=e.getBoundingClientRect();return r.top>=s.top&&r.bottom<=s.bottom&&r.left>=s.left&&r.right<=s.right})}')
    page.locator('#window').screenshot(path=str(ROOT/'assets/second-compact-failure.png'))
    page.get_by_role('button',name='Retry this preview',exact=True).click()
    assert page.get_by_role('button',name='Keep as layer',exact=True).is_enabled()
    page.get_by_role('button',name='Keep as layer',exact=True).click()
    page.get_by_role('button',name='← Compose',exact=True).click()
    assert page.locator('.layer-row').count()==3
    page.get_by_role('button',name='Return to bench',exact=True).click()
    assert page.locator('.bench-state strong').inner_text()=='Reading 2'
    page.locator('#presentation').select_option('popup')
    page.get_by_role('button',name='Expand',exact=True).click()
    assert page.locator('.popup-wrap.expanded').count()==1
    assert page.locator('.bench-state strong').inner_text()=='Reading 2'
    page.get_by_role('button',name='← Compose',exact=True).click()
    page.get_by_role('button',name='Expand list',exact=True).click()
    page.locator('#window').screenshot(path=str(ROOT/'assets/compose-compact-expanded-layers.png'))
    page.locator('#picker').select_option('homeostat')
    page.get_by_role('button',name='Open bench ↗',exact=True).click()
    assert page.locator('.bench-head h2').inner_text().startswith('Homeostat')
    page.get_by_role('button',name='Play steps',exact=True).click()
    assert page.locator('#scrub').input_value()=='450'
    # Actual narrower browser, not just the study's width selector.
    page.set_viewport_size({'width':720,'height':900})
    page.locator('#size').select_option('small')
    page.locator('#presentation').select_option('embedded')
    page.locator('[data-view="compose"]').click()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#window').screenshot(path=str(ROOT/'assets/compose-actual-narrow.png'))
    assert not errors,errors
    (ROOT/'assets/browser-checks.json').write_text(json.dumps({'layouts':checks,'page_errors':errors,'flows':'capture cancellation, continue, alternative, comparison, failed-preview keep gate/retry, keep, return/resume, popup expansion, expanded layers, picker discovery, Homeostat sampled playback, actual narrow viewport'},indent=2))
    print(f'{len(checks)} layouts and interaction flow checked; no page errors. Application behaviour remains untested by this study.')
    browser.close()
