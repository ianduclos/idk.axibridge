"""Check saved report pages in memory; no URL navigation or network access."""
from pathlib import Path
from html.parser import HTMLParser
from playwright.sync_api import sync_playwright
import base64,json,re
root=Path(__file__).resolve().parent
pages=[root/'index.html',root/'history.html',root.parents[2]/'docs/reviews/territory02-editor-round1-2026-10-05.html',root.parents[2]/'docs/reviews/territory02-editor-round1-sol.html']
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.ids=set()
    def handle_starttag(self,t,attrs):
        a=dict(attrs)
        if 'href' in a:self.links.append(a['href'])
        if 'id' in a:self.ids.add(a['id'])
results=[];errors=[];requests=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch();page=browser.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    def block(route):requests.append(route.request.url);route.abort()
    page.route('**/*',block)
    for file in pages:
        text=file.read_text();p=Links();p.feed(text)
        for link in p.links:
            if link.startswith('#'):assert link[1:] in p.ids
            elif '://' not in link:assert (file.parent/link.split('#')[0]).exists(),(file,link)
        def inline(m):
            image=(file.parent/m[1]).resolve();assert image.exists(),image
            return 'src="data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode()+'"'
        text=re.sub(r'src="([^"]+\.png)"',inline,text)
        for width in [1440,390]:
            page.set_viewport_size({'width':width,'height':1000});page.set_content(text,wait_until='domcontentloaded')
            page.wait_for_function('Array.from(document.images).every(x=>x.complete&&x.naturalWidth>0)')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            count=page.locator('img').count()
            if file.name=='index.html':
                assert count==8
                assert page.locator('details').get_attribute('open') is None
                page.locator('summary').click();assert page.locator('details').get_attribute('open') is not None
            if file.name=='history.html':assert count==14
            if file.name=='index.html':page.screenshot(path=str(root/f'evidence/page-{width}.png'),full_page=True)
            results.append({'page':file.name,'width':width,'images':count,'noOverflow':True,'linksResolve':True})
    assert not errors and not requests and page.url=='about:blank';browser.close()
(root/'evidence/page-checks.json').write_text(json.dumps({'checks':results,'errors':errors,'externalRequests':requests,'method':'Own artifact HTML with inlined PNGs at about:blank; requests blocked.','limits':'Links resolved on disk; actual link/file navigation and paper not tested.'},indent=2)+'\n')
print('All contact/history/report images load, links resolve and mobile/desktop layouts fit; identity reveal works.')
