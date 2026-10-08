"""Check generated texture artifacts in memory, without browser URL navigation."""

import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


SEEDS = [5, 13, 18, 24, 47, 82, 521, 587, 631, 683]
VARIANTS = ["bare", "led", "opening", "pressure", "unravel"]
TITLES = ["Takeover curves only", "Course-led texture", "Opening", "Pressure", "Unravelling"]


def wait_for_images(page):
    page.wait_for_function("""() => [...document.querySelectorAll('figure img')].every(img => img.complete && img.naturalWidth > 0 && img.naturalHeight > 0)""")


def check_viewer():
    root = Path(__file__).resolve().parent
    evidence = root / "evidence"
    stylesheet = "../../../../axibridge/static/css/flexoki.css"
    css = (root / stylesheet).read_text()
    html = (root / "index.html").read_text()
    html = html.replace(f'<link rel="stylesheet" href="{stylesheet}">', f"<style>{css}</style>")
    assets = {}
    for seed in SEEDS:
        for variant in VARIANTS:
            for suffix in ["", "-close"]:
                relative = f"evidence/{seed}-{variant}{suffix}.svg"
                svg = (root / relative).read_text()
                assets[relative] = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    # The viewer controller runs unchanged. Only image loading is interposed:
    # its relative artifact references resolve to the generated SVG text above.
    embed_script = """<script>
      const embeddedSvgAssets = ASSETS;
      const imageSrcDescriptor = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
      Object.defineProperty(HTMLImageElement.prototype, 'src', {
        configurable: true,
        get() { return imageSrcDescriptor.get.call(this); },
        set(path) {
          if (!Object.prototype.hasOwnProperty.call(embeddedSvgAssets, path)) throw new Error(`Unknown artifact ${path}`);
          this.dataset.artifactSrc = path;
          imageSrcDescriptor.set.call(this, embeddedSvgAssets[path]);
        }
      });
    </script>""".replace("ASSETS", json.dumps(assets))
    html = html.replace("<script>", embed_script + "\n<script>", 1)
    errors = []
    external_requests = []
    checked = []
    screenshots = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        def abort_external(route):
            external_requests.append(route.request.url)
            route.abort()
        page.route("**/*", abort_external)
        page.set_content(html, wait_until="domcontentloaded")
        assert page.url == "about:blank"
        assert page.locator("#seed").input_value() == "13"
        assert not page.locator("#detail").is_checked()
        assert page.locator("select").count() == 1
        assert page.locator("#seed option").evaluate_all("options => options.map(option => Number(option.value))") == SEEDS
        assert page.locator("h2").all_text_contents() == TITLES
        for seed in SEEDS:
            page.locator("#seed").select_option(str(seed))
            for detail in [False, True]:
                page.locator("#detail").set_checked(detail)
                suffix = "-close" if detail else ""
                expected = [f"evidence/{seed}-{variant}{suffix}.svg" for variant in VARIANTS]
                assert page.locator("figure img").evaluate_all("images => images.map(img => img.dataset.artifactSrc)") == expected
                wait_for_images(page)
                assert page.locator("figure img").evaluate_all("images => images.map(img => img.getAttribute('src'))") == [assets[path] for path in expected]
                full = [f"evidence/{seed}-{variant}.svg" for variant in VARIANTS]
                for selector in ["figure .drawing", "figure .full"]:
                    assert page.locator(selector).evaluate_all("links => links.map(link => link.getAttribute('href'))") == full
                for variant in ["opening", "pressure", "unravel"]:
                    for suffix in ["-event", "-event-before"]:
                        assert (evidence / f"{seed}-{variant}{suffix}.svg").exists()
                assert all(page.locator("figure img").evaluate_all("images => images.map(img => img.alt.length > 0)"))
                checked.append({"seed": seed, "view": "detail" if detail else "whole", "images": expected})
        page.locator("#seed").select_option("5")
        page.locator("#previous").click()
        assert page.locator("#seed").input_value() == "683"
        page.locator("#next").click()
        assert page.locator("#seed").input_value() == "5"
        page.locator("#seed").select_option("683")
        page.locator("#next").click()
        assert page.locator("#seed").input_value() == "5"
        page.locator("#seed").select_option("13")
        page.locator("#detail").set_checked(False)
        wait_for_images(page)
        panels = page.locator("figure").evaluate_all("figures => figures.map(figure => ({x: figure.getBoundingClientRect().x, y: figure.getBoundingClientRect().y, width: figure.getBoundingClientRect().width}))")
        assert max(panel["width"] for panel in panels) - min(panel["width"] for panel in panels) < 1
        assert panels[0]["y"] == panels[1]["y"] < panels[2]["y"] == panels[3]["y"]
        assert panels[0]["x"] == panels[2]["x"] < panels[1]["x"] == panels[3]["x"]
        heights = page.locator(".controls button, .controls select, .detail-control").evaluate_all("controls => controls.map(control => control.getBoundingClientRect().height)")
        assert min(heights) >= 44
        assert min(page.locator(".controls button").evaluate_all("buttons => buttons.map(button => button.getBoundingClientRect().width)")) >= 44
        for seed in [13, 587]:
            page.locator("#seed").select_option(str(seed))
            for mobile in [False, True]:
                page.set_viewport_size({"width": 390, "height": 844} if mobile else {"width": 1500, "height": 1000})
                for detail in [False, True]:
                    page.locator("#detail").set_checked(detail)
                    wait_for_images(page)
                    if mobile:
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile layout overflows"
                        positions = page.locator("figure").evaluate_all("figures => figures.map(figure => ({x: figure.getBoundingClientRect().x, y: figure.getBoundingClientRect().y}))")
                        assert len({panel["x"] for panel in positions}) == 1
                        assert all(positions[index]["y"] < positions[index + 1]["y"] for index in range(4))
                    filename = f"comparison-{seed}{'-close' if detail else ''}{'-mobile' if mobile else ''}.png"
                    page.screenshot(path=str(evidence / filename), full_page=True)
                    screenshots.append(filename)
        assert not errors, f"Page errors: {errors}"
        assert not external_requests, f"External requests: {external_requests}"
        assert page.url == "about:blank"
        browser.close()
    result = {
        "scope": "ten seeds, whole and same-framed detail",
        "method": "page.set_content at about:blank with CSS and generated SVG text inlined; viewer controller preserved; no URL navigation",
        "seeds": SEEDS,
        "views_checked": len(checked),
        "images_checked": len(checked) * 5,
        "arrow_wrap": "passed",
        "full_svg_links": "passed in both views",
        "desktop_equal_two_column_panels": "passed",
        "controls_minimum_44px": "passed",
        "mobile_stacking_and_overflow": "passed at 390px for seeds 13 and 587, whole and detail",
        "pageerrors": errors,
        "external_requests": external_requests,
        "screenshots": screenshots,
        "checks": checked,
        "limits": "Mechanical in-memory browser checks only. Actual in-app/file navigation, link opening, aesthetics and paper acceptance unverified.",
    }
    (evidence / "viewer-check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "checks"}, indent=2))


if __name__ == "__main__":
    check_viewer()
