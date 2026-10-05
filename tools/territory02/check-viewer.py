"""Verify actual comparison images load for every selection; capture two examples."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1450, "height": 1200})
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto((root / "index.html").as_uri())
    cases = 0
    for round_name in ("round1", "round2", "round3"):
        page.select_option("#round", round_name)
        for mode in ("sparse", "full"):
            page.select_option("#mode", mode)
            for seed in (5, 13, 18, 24, 47, 82):
                page.select_option("#seed", str(seed))
                page.wait_for_function("""() => [...document.querySelectorAll('figure img')]
                    .every(img => img.complete && img.naturalWidth > 0)""")
                assert page.locator("figure img").count() == 4
                assert f"seed {seed}" in page.locator("#status").inner_text()
                cases += 1
    page.select_option("#seed", "82")
    page.click("#next")
    assert page.locator("#seed").input_value() == "5"
    page.click("#previous")
    assert page.locator("#seed").input_value() == "82"
    page.select_option("#seed", "18")
    for mode in ("sparse", "full"):
        page.select_option("#mode", mode)
        page.wait_for_function("""() => [...document.querySelectorAll('figure img')]
            .every(img => img.complete && img.naturalWidth > 0)""")
        page.screenshot(path=str(root / "evidence" / f"comparison-{mode}-18.png"), full_page=True)
    browser.close()
assert not errors, errors
summary = {"selections": cases, "loaded_drawings": cases * 4, "arrow_wrap": "passed", "page_errors": errors}
(root / "evidence" / "viewer-check.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
