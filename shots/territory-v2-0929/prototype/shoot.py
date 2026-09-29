import sys, pathlib
from playwright.sync_api import sync_playwright
src, out, w = sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv)>3 else 1600
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':w,'height':800}, device_scale_factor=1.5)
    pg.goto(pathlib.Path(src).resolve().as_uri()); pg.wait_for_timeout(200)
    pg.screenshot(path=out, full_page=True); b.close()
