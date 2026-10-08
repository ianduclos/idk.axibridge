"""Check the offline comparison page; no server or hardware is involved."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


SEEDS = [5, 13, 18, 24, 47, 82, 107, 173, 227, 281]


def check_viewer(initial_only=False):
    root = Path(__file__).resolve().parent
    evidence = root / "evidence"
    seeds = SEEDS[:6] if initial_only else SEEDS
    errors = []
    checked = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((root / "index.html").as_uri(), wait_until="domcontentloaded")
        assert page.locator("#seed").input_value() == "13"
        assert page.locator("#seed option").evaluate_all("options => options.map(option => Number(option.value))") == SEEDS
        assert page.locator("h2").all_text_contents() == ["Territory input", "First intervention", "Takeover"]
        for seed in seeds:
            page.locator("#seed").select_option(str(seed))
            for detail in [False, True]:
                page.locator("#detail").set_checked(detail)
                suffix = "-close" if detail else ""
                expected = [f"evidence/{seed}-{stage}{suffix}.svg" for stage in range(3)]
                assert page.locator("figure img").evaluate_all("images => images.map(img => img.getAttribute('src'))") == expected
                page.wait_for_function("""() => [...document.querySelectorAll('figure img')].every(img => img.complete)""")
                loaded = page.locator("figure img").evaluate_all("images => images.map(img => img.naturalWidth > 0 && img.naturalHeight > 0)")
                assert all(loaded), f"Missing or unreadable images: seed {seed}, detail {detail}: {loaded}"
                full = [f"evidence/{seed}-{stage}.svg" for stage in range(3)]
                for selector in ["figure .drawing", "figure .full"]:
                    assert page.locator(selector).evaluate_all("links => links.map(link => link.getAttribute('href'))") == full
                assert all(page.locator("figure img").evaluate_all("images => images.map(img => img.alt.length > 0)"))
                checked.append({"seed": seed, "view": "detail" if detail else "whole", "images": expected})
        page.locator("#seed").select_option("5")
        page.locator("#previous").click()
        assert page.locator("#seed").input_value() == "281"
        page.locator("#next").click()
        assert page.locator("#seed").input_value() == "5"
        page.locator("#seed").select_option("281")
        page.locator("#next").click()
        assert page.locator("#seed").input_value() == "5"
        page.locator("#seed").select_option("13")
        for detail, filename in [(False, "comparison-13.png"), (True, "comparison-13-close.png")]:
            page.locator("#detail").set_checked(detail)
            page.wait_for_function("""() => [...document.querySelectorAll('figure img')].every(img => img.complete && img.naturalWidth > 0)""")
            page.screenshot(path=str(evidence / filename), full_page=True)
        widths = page.locator("figure").evaluate_all("figures => figures.map(figure => figure.getBoundingClientRect().width)")
        assert max(widths) - min(widths) < 1, f"Unequal panel widths: {widths}"
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile layout overflows"
        panel_positions = page.locator("figure").evaluate_all("figures => figures.map(figure => ({x: figure.getBoundingClientRect().x, y: figure.getBoundingClientRect().y}))")
        assert len({position["x"] for position in panel_positions}) == 1
        assert panel_positions[0]["y"] < panel_positions[1]["y"] < panel_positions[2]["y"]
        page.locator("#detail").set_checked(False)
        page.wait_for_function("""() => [...document.querySelectorAll('figure img')].every(img => img.complete && img.naturalWidth > 0)""")
        page.screenshot(path=str(evidence / "comparison-13-mobile.png"), full_page=True)
        assert not errors, f"Page errors: {errors}"
        browser.close()
    result = {
        "scope": "initial six seeds" if initial_only else "all ten seeds",
        "seeds": seeds,
        "views_checked": len(checked),
        "images_checked": len(checked) * 3,
        "arrow_wrap": "passed",
        "full_svg_links": "passed in both views",
        "desktop_equal_panels": "passed",
        "mobile_stacking_and_overflow": "passed at 390px",
        "pageerrors": errors,
        "screenshots": ["comparison-13.png", "comparison-13-close.png", "comparison-13-mobile.png"],
        "checks": checked,
        "limits": "Mechanical browser checks only; no aesthetic or paper acceptance.",
    }
    (evidence / "viewer-check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "checks"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-only", action="store_true", help="Check the six available seeds before holdouts are rendered")
    check_viewer(parser.parse_args().initial_only)
