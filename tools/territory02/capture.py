"""Capture local evidence HTML with one browser; no app/hardware interactions."""
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright
folder=Path(sys.argv[1]).resolve()
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1800,'height':900},device_scale_factor=1)
    for file in sorted(folder.glob('*.html')):
        page.goto(file.as_uri(),wait_until='domcontentloaded')
        page.screenshot(path=str(file.with_suffix('.png')),full_page=True)
    browser.close()
print(f'Captured {folder}')
