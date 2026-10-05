"""Capture generated current evidence with an existing Playwright runtime."""
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent / "evidence"
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1800, "height": 900}, device_scale_factor=1)
    for folder in [root, root / "blind-bulbs"]:
        for file in sorted(folder.glob("*.html")):
            page.goto(file.as_uri(), wait_until="domcontentloaded")
            page.screenshot(path=str(file.with_suffix(".png")), full_page=True)
    page.set_viewport_size({"width": 1200, "height": 840})
    for folder in [root, root / "blind-bulbs"]:
        for file in sorted(folder.glob("*-close.svg")):
            page.goto(file.as_uri(), wait_until="domcontentloaded")
            page.screenshot(path=str(file.with_suffix(".png")))
    browser.close()
print("Current whole populations and same-framed details captured.")
