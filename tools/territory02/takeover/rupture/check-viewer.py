"""Exercise this own-artifact viewer at about:blank; never navigate a URL."""
from pathlib import Path
import base64,json,sys
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent
fresh='--holdouts' in sys.argv
seeds=[13,24,47,1151,1213,1277] if fresh else [13,24,47]
modes=['earlier','open','body']
html=(root/'index.html').read_text();css='../../../../axibridge/static/css/flexoki.css'
html=html.replace(f'<link rel="stylesheet" href="{css}">',f'<style>{(root/css).read_text()}</style>')
assets={}
for seed in seeds:
 for mode in modes:
  for lines in ['', '-lines'] if mode!='earlier' else ['']:
   for close in ['', '-close']:
    key=f'evidence/{seed}-{mode}{lines}{close}.svg';assets[key]='data:image/svg+xml;base64,'+base64.b64encode((root/key).read_bytes()).decode()
embed='''<script>const assets=ASSETS,desc=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');Object.defineProperty(HTMLImageElement.prototype,'src',{get(){return desc.get.call(this)},set(p){if(!assets[p])throw Error(p);this.dataset.artifact=p;desc.set.call(this,assets[p])}});</script>'''.replace('ASSETS',json.dumps(assets))
html=html.replace('<script>',embed+'<script>',1);errors=[];requests=[];checks=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1500,'height':1000});page.on('pageerror',lambda error:errors.append(str(error)))
 def block(route):requests.append(route.request.url);route.abort()
 page.route('**/*',block);page.set_content(html,wait_until='domcontentloaded')
 def loaded():page.wait_for_function("() => [...document.querySelectorAll('figure img')].every(i=>i.complete&&i.naturalWidth>0)")
 def selected(seed,lines,close):
  return [f'evidence/{seed}-{mode}{"-lines" if lines and mode!="earlier" else ""}{"-close" if close else ""}.svg' for mode in modes]
 for seed in seeds:
  page.locator('#seed').select_option(str(seed))
  for lines in [False,True]:
   page.locator('#lines').set_checked(lines)
   for close in [False,True]:
    page.locator('#detail').set_checked(close);loaded()
    assert page.locator('figure img').evaluate_all('(xs)=>xs.map(x=>x.dataset.artifact)')==selected(seed,lines,close)
    expected=selected(seed,lines,False)
    for selector in ['figure .full','figure .drawing']:assert page.locator(selector).evaluate_all('(xs)=>xs.map(x=>x.getAttribute("href"))')==expected
    assert all(page.locator('figure img').evaluate_all('(xs)=>xs.map(x=>x.alt.length>0)'))
    checks.append([seed,lines,close])
 page.locator('#seed').select_option('13');page.locator('#next').click();assert page.locator('#seed').input_value()=='24'
 page.locator('#previous').click();assert page.locator('#seed').input_value()=='13'
 if fresh:
  page.locator('#previous').click();assert page.locator('#seed').input_value()=='1277';loaded();page.locator('#next').click();assert page.locator('#seed').input_value()=='13'
 for width in [1500,390]:
  page.set_viewport_size({'width':width,'height':1000});page.locator('#detail').set_checked(False);page.locator('#lines').set_checked(False);loaded()
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  boxes=page.locator('figure').evaluate_all('(xs)=>xs.map(x=>({x:x.getBoundingClientRect().x,y:x.getBoundingClientRect().y,w:x.getBoundingClientRect().width}))')
  assert max(x['w'] for x in boxes)-min(x['w'] for x in boxes)<1
  if width==390:assert len({x['x'] for x in boxes})==1
  else:assert boxes[0]['y']==boxes[1]['y']<boxes[2]['y']
  assert min(page.locator('button,select,.check-control').evaluate_all('(xs)=>xs.map(x=>x.getBoundingClientRect().height)'))>=44
  page.screenshot(path=str(root/f'evidence/viewer-{width}.png'),full_page=True)
 assert page.url=='about:blank';assert not errors and not requests;browser.close()
result={'cases':len(checks),'images':len(checks)*3,'errors':errors,'external_requests':requests,'method':'In-memory page.set_content at about:blank; own SVG/CSS inline; no URL navigation','limits':'File navigation, link opening, paper and human acceptance unverified.','checks':checks}
(root/f'evidence/viewer-check{"-heldout" if fresh else ""}.json').write_text(json.dumps(result,indent=2)+'\n');print({k:v for k,v in result.items() if k!='checks'})
