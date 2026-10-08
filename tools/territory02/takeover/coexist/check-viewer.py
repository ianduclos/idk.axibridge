"""Exercise this own-artifact viewer in memory, without URL navigation."""
from pathlib import Path
import base64,json
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent
seeds=[13,24,1009,1061];bases=['opening','pressure','unravel'];modes=['rough','smooth','continuity','interference','independent']
html=(root/'index.html').read_text();css='../../../../axibridge/static/css/flexoki.css';html=html.replace(f'<link rel="stylesheet" href="{css}">',f'<style>{(root/css).read_text()}</style>')
assets={f'evidence/{s}-{b}-{m}{z}.svg':'data:image/svg+xml;base64,'+base64.b64encode((root/f'evidence/{s}-{b}-{m}{z}.svg').read_bytes()).decode() for s in seeds for b in bases for m in modes for z in ['','-close']}
embed='''<script>const assets=ASSETS,desc=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');Object.defineProperty(HTMLImageElement.prototype,'src',{get(){return desc.get.call(this)},set(p){if(!assets[p])throw Error(p);this.dataset.artifact=p;desc.set.call(this,assets[p])}});</script>'''.replace('ASSETS',json.dumps(assets))
html=html.replace('<script>',embed+'<script>',1);errors=[];requests=[];checks=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1500,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
 def block(route):requests.append(route.request.url);route.abort()
 page.route('**/*',block);page.set_content(html,wait_until='domcontentloaded')
 def loaded():page.wait_for_function("() => [...document.querySelectorAll('figure img')].every(i=>i.complete&&i.naturalWidth>0)")
 for s in seeds:
  page.locator('#seed').select_option(str(s))
  for b in bases:
   page.locator('#base').select_option(b)
   for close in [False,True]:
    page.locator('#detail').set_checked(close);loaded();suffix='-close' if close else ''
    expected=[f'evidence/{s}-{b}-{m}{suffix}.svg' for m in modes]
    assert page.locator('figure img').evaluate_all('(xs)=>xs.map(x=>x.dataset.artifact)')==expected
    assert page.locator('figure .full').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("href"))')==[f'evidence/{s}-{b}-{m}.svg' for m in modes]
    assert all(page.locator('figure img').evaluate_all('(xs)=>xs.map(x=>x.alt.length>0)'))
    checks.append([s,b,close])
 page.locator('#seed').select_option('13');page.locator('#previous').click();assert page.locator('#seed').input_value()=='1061'
 page.locator('#next').click();assert page.locator('#seed').input_value()=='13'
 for width in [1500,390]:
  page.set_viewport_size({'width':width,'height':1000});page.locator('#base').select_option('unravel');page.locator('#detail').set_checked(False);loaded()
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  boxes=page.locator('figure').evaluate_all('(xs)=>xs.map(x=>({x:x.getBoundingClientRect().x,y:x.getBoundingClientRect().y,w:x.getBoundingClientRect().width}))')
  assert max(x['w'] for x in boxes)-min(x['w'] for x in boxes)<1
  if width==390:assert len({x['x'] for x in boxes})==1
  else:assert boxes[0]['y']==boxes[1]['y']<boxes[2]['y']
  assert min(page.locator('button,select,.detail-control').evaluate_all('(xs)=>xs.map(x=>x.getBoundingClientRect().height)'))>=44
  page.screenshot(path=str(root/f'evidence/viewer-{width}.png'),full_page=True)
 assert not errors and not requests;assert page.url=='about:blank';browser.close()
result={'cases':len(checks),'images':len(checks)*5,'errors':errors,'external_requests':requests,'method':'in-memory page.set_content at about:blank; own SVG/CSS inline; no URL navigation','limits':'File navigation, link opening, paper and human acceptance unverified.','checks':checks}
(root/'evidence/viewer-check.json').write_text(json.dumps(result,indent=2)+'\n');print({k:v for k,v in result.items() if k!='checks'})
