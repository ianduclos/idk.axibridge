"""Check generated fill artifacts in an in-memory page, without URL navigation."""

import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


SEEDS = [5, 13, 18, 24, 47, 82, 113, 179, 233, 293]
DENSITIES = ["light", "dense"]
VARIANTS = ["original", "bare", "bands", "pockets"]


def check_viewer():
    root = Path(__file__).resolve().parent
    evidence = root / "evidence"
    stylesheet = "../../../../axibridge/static/css/flexoki.css"
    css = (root / stylesheet).read_text()
    html = (root / "index.html").read_text()
    html = html.replace(f'<link rel="stylesheet" href="{stylesheet}">', f"<style>{css}</style>")
    assets = {}
    for seed in SEEDS:
        for density in DENSITIES:
            for variant in VARIANTS:
                for suffix in ["", "-close"]:
                    relative = f"evidence/{seed}-{density}-{variant}{suffix}.svg"
                    svg = (root / relative).read_text()
                    assets[relative] = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    # Preserve the viewer controller. Interpose only image loading so each
    # relative artifact reference resolves to its inlined generated SVG text.
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
        assert page.locator("#density").input_value() == "light"
        assert not page.locator("#detail").is_checked()
        assert page.locator("#seed option").evaluate_all("options => options.map(option => Number(option.value))") == SEEDS
        assert page.locator("h2").all_text_contents() == ["Original filled Territory", "Takeover curves only", "Shared bands", "Shared pockets"]
        for seed in SEEDS:
            page.locator("#seed").select_option(str(seed))
            for density in DENSITIES:
                page.locator("#density").select_option(density)
                for detail in [False, True]:
                    page.locator("#detail").set_checked(detail)
                    suffix = "-close" if detail else ""
                    expected = [f"evidence/{seed}-{density}-{variant}{suffix}.svg" for variant in VARIANTS]
                    assert page.locator("figure img").evaluate_all("images => images.map(img => img.dataset.artifactSrc)") == expected
                    page.wait_for_function("""() => [...document.querySelectorAll('figure img')].every(img => img.complete)""")
                    loaded = page.locator("figure img").evaluate_all("images => images.map(img => img.naturalWidth > 0 && img.naturalHeight > 0)")
                    assert all(loaded), f"Unreadable SVG images: {expected}: {loaded}"
                    assert page.locator("figure img").evaluate_all("images => images.map(img => img.getAttribute('src'))") == [assets[path] for path in expected]
                    full = [f"evidence/{seed}-{density}-{variant}.svg" for variant in VARIANTS]
                    for selector in ["figure .drawing", "figure .full"]:
                        assert page.locator(selector).evaluate_all("links => links.map(link => link.getAttribute('href'))") == full
                    assert all(page.locator("figure img").evaluate_all("images => images.map(img => img.alt.length > 0)"))
                    checked.append({"seed": seed, "density": density, "view": "detail" if detail else "whole", "images": expected})
        page.locator("#seed").select_option("5")
        page.locator("#previous").click()
        assert page.locator("#seed").input_value() == "293"
        page.locator("#next").click()
        assert page.locator("#seed").input_value() == "5"
        page.locator("#seed").select_option("293")
        page.locator("#next").click()
        assert page.locator("#seed").input_value() == "5"
        page.locator("#seed").select_option("13")
        for density in DENSITIES:
            page.locator("#density").select_option(density)
            for detail in [False, True]:
                page.locator("#detail").set_checked(detail)
                page.wait_for_function("""() => [...document.querySelectorAll('figure img')].every(img => img.complete && img.naturalWidth > 0)""")
                filename = f"comparison-13-{density}{'-close' if detail else ''}.png"
                page.screenshot(path=str(evidence / filename), full_page=True)
                screenshots.append(filename)
        panels = page.locator("figure").evaluate_all("figures => figures.map(figure => ({x: figure.getBoundingClientRect().x, y: figure.getBoundingClientRect().y, width: figure.getBoundingClientRect().width}))")
        assert max(panel["width"] for panel in panels) - min(panel["width"] for panel in panels) < 1
        assert panels[0]["y"] == panels[1]["y"] < panels[2]["y"] == panels[3]["y"]
        assert panels[0]["x"] == panels[2]["x"] < panels[1]["x"] == panels[3]["x"]
        heights = page.locator(".controls button, .controls select, .detail-control").evaluate_all("controls => controls.map(control => control.getBoundingClientRect().height)")
        assert min(heights) >= 44
        button_widths = page.locator(".controls button").evaluate_all("buttons => buttons.map(button => button.getBoundingClientRect().width)")
        assert min(button_widths) >= 44
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#density").select_option("light")
        page.locator("#detail").set_checked(False)
        page.wait_for_function("""() => [...document.querySelectorAll('figure img')].every(img => img.complete && img.naturalWidth > 0)""")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile layout overflows"
        panels = page.locator("figure").evaluate_all("figures => figures.map(figure => ({x: figure.getBoundingClientRect().x, y: figure.getBoundingClientRect().y}))")
        assert len({panel["x"] for panel in panels}) == 1
        assert all(panels[index]["y"] < panels[index + 1]["y"] for index in range(3))
        filename = "comparison-13-light-mobile.png"
        page.screenshot(path=str(evidence / filename), full_page=True)
        screenshots.append(filename)
        assert not errors, f"Page errors: {errors}"
        assert not external_requests, f"External requests: {external_requests}"
        browser.close()
    result = {
        "scope": "ten seeds, both densities, whole and same-framed detail",
        "method": "page.set_content with CSS and generated SVG text inlined; controller preserved; no URL navigation",
        "seeds": SEEDS,
        "views_checked": len(checked),
        "images_checked": len(checked) * 4,
        "arrow_wrap": "passed",
        "full_svg_links": "passed in both views",
        "desktop_equal_2_by_2_panels": "passed",
        "controls_minimum_44px": "passed",
        "mobile_stacking_and_overflow": "passed at 390px",
        "pageerrors": errors,
        "external_requests": external_requests,
        "screenshots": screenshots,
        "checks": checked,
        "limits": "Mechanical in-memory browser checks only. File URL navigation, link opening, aesthetics and paper acceptance unverified.",
    }
    (evidence / "viewer-check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "checks"}, indent=2))


if __name__ == "__main__":
    check_viewer()
