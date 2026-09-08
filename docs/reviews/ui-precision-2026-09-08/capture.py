#!/usr/bin/env python3
"""Capture repeatable UI-precision evidence from an arbitrary static tree.

Runs the real AxiBridge server with an isolated configuration directory, a
random port, simulator-only machine state, and the requested frontend path.
The SSE connection is why this harness waits for DOM readiness rather than
``networkidle``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(base: str, path: str, payload: dict | None = None, method: str | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        base + path, data=data,
        method=method or ("GET" if payload is None else "POST"),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())


def wait_ready(page: Page) -> None:
    page.wait_for_function(
        "document.querySelectorAll('#gen-select option').length > 0",
        timeout=30_000,
    )
    page.evaluate("document.fonts.ready")


def install_determinism(page: Page) -> None:
    page.add_init_script("""(() => {
      let state = 0x41c6ce57;
      const next = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state; };
      Math.random = () => next() / 0x100000000;
      const fill = array => {
        const bytes = new Uint8Array(array.buffer, array.byteOffset, array.byteLength);
        for (let i=0; i<bytes.length; i++) bytes[i] = next() & 255;
        return array;
      };
      try { Object.defineProperty(globalThis.crypto, 'getRandomValues', {value: fill}); }
      catch (_) { globalThis.crypto.getRandomValues = fill; }
    })()""")


def wait_preview(page: Page) -> None:
    page.wait_for_function(
        "document.querySelector('#process-preview-state').textContent === 'rendered'",
        timeout=30_000,
    )


def wait_generic_bench(page: Page) -> None:
    page.wait_for_function("""() =>
      document.querySelector('#process-canvas path') ||
      !document.querySelector('#process-create').disabled ||
      document.querySelector('#process-preview-state').textContent === 'rendered'
    """, timeout=60_000)


def settle_render_frame(page: Page) -> None:
    page.wait_for_function("!document.getElementById('anim-preview-popup-next').disabled", timeout=30_000)
    if page.locator("#anim-preview-popup-toggle").inner_text().strip() == "Pause":
        page.click("#anim-preview-popup-toggle")
    for _ in range(8):
        if page.locator("#anim-preview-popup-label").inner_text().strip().startswith("frame 1/"):
            break
        page.click("#anim-preview-popup-prev")
    else:
        raise RuntimeError("animation render popup did not return to frame 1")
    page.click("#anim-preview-popup-next"); page.click("#anim-preview-popup-next")
    page.wait_for_function(r"""() => /^frame 3\/8/.test(document.getElementById('anim-preview-popup-label').textContent)
      && document.getElementById('anim-preview-img').complete
      && document.getElementById('anim-preview-img').naturalWidth > 0""")


def box(page: Page, selector: str) -> dict | None:
    return page.eval_on_selector(selector, """el => {
      const r=el.getBoundingClientRect(), c=getComputedStyle(el);
      return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom,
        scrollWidth:el.scrollWidth,scrollHeight:el.scrollHeight,
        clientWidth:el.clientWidth,clientHeight:el.clientHeight,
        overflowX:c.overflowX,overflowY:c.overflowY,display:c.display,
        visibility:c.visibility,hidden:el.hidden,
        viewBox:el.getAttribute('viewBox')};
    }""")


def measure(page: Page, scenario: str, selectors: list[str]) -> dict:
    viewport = page.viewport_size
    document = page.evaluate("""() => ({
      scrollWidth:document.documentElement.scrollWidth,
      scrollHeight:document.documentElement.scrollHeight,
      clientWidth:document.documentElement.clientWidth,
      clientHeight:document.documentElement.clientHeight
    })""")
    actions = page.evaluate("""() => [...document.querySelectorAll('button,input,select,summary')]
      .filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
      .map(el => { const r=el.getBoundingClientRect(); return {
        id:el.id||null, text:(el.textContent||el.value||'').trim().slice(0,80),
        tag:el.tagName, disabled:!!el.disabled, x:r.x,y:r.y,width:r.width,height:r.height,
        insidePopup:!!el.closest('#process-popup,#anim-preview-modal'),
        fullyInViewport:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight}; });
    """)
    popup_reachability = page.evaluate("""() => {
      const popup=document.querySelector('#process-popup:not([hidden]),#anim-preview-modal:not([hidden])'); if(!popup)return [];
      return [...popup.querySelectorAll('button,input,select,summary')]
        .filter(el=>el.getClientRects().length&&getComputedStyle(el).visibility!=='hidden')
        .map(el=>{el.scrollIntoView({block:'nearest',inline:'nearest'});const r=el.getBoundingClientRect();
          const x=Math.max(0,Math.min(innerWidth-1,r.left+r.width/2));
          const y=Math.max(0,Math.min(innerHeight-1,r.top+r.height/2));
          const hit=document.elementFromPoint(x,y);return{id:el.id||null,text:(el.textContent||el.value||'').trim().slice(0,80),
          inViewport:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,
          hitTest:!!hit&&(hit===el||el.contains(hit))};});
    }""")
    return {
        "scenario": scenario,
        "viewport": viewport,
        "document": document,
        "horizontalDocumentOverflow": document["scrollWidth"] > document["clientWidth"],
        "elements": {selector: box(page, selector) for selector in selectors
                     if page.locator(selector).count()},
        "visibleActions": actions,
        "clippedVisibleActions": [a for a in actions if not a["fullyInViewport"]],
        "popupVisibleActions": [a for a in actions if a["insidePopup"]],
        "popupActionsOutsideViewport": [a for a in actions if a["insidePopup"] and not a["fullyInViewport"]],
        "popupActionReachabilityAfterScroll": popup_reachability,
    }


def fixture_evidence(page: Page) -> dict:
    project = page.evaluate("async () => await (await fetch('/api/project')).json()")
    ids = {layer.get("id"): f"layer[{index}]" for index, layer in enumerate(project.get("layers", []))}
    def canonical(value):
        if isinstance(value, dict):
            return {key: canonical(item) for key, item in value.items()}
        if isinstance(value, list):
            return [canonical(item) for item in value]
        return ids.get(value, value) if isinstance(value, str) else value
    recipes = [{"name": layer.get("name"), "source": canonical(layer.get("source"))}
               for layer in project.get("layers", [])]
    process_recipe = None
    if page.locator("#process-recipe").count():
        raw = page.locator("#process-recipe").text_content() or ""
        if raw.strip():
            try:
                process_recipe = json.loads(raw)
            except json.JSONDecodeError:
                process_recipe = raw
    geometry = page.evaluate("""async () => {
      const read = selector => [...document.querySelectorAll(selector)]
        .map(el=>({tag:el.tagName.toLowerCase(),d:el.getAttribute('d'),points:el.getAttribute('points'),
          x1:el.getAttribute('x1'),y1:el.getAttribute('y1'),x2:el.getAttribute('x2'),y2:el.getAttribute('y2'),
          cx:el.getAttribute('cx'),cy:el.getAttribute('cy'),r:el.getAttribute('r'),x:el.getAttribute('x'),
          y:el.getAttribute('y'),width:el.getAttribute('width'),height:el.getAttribute('height')}));
      const src=document.querySelector('#anim-preview-img:not([hidden])')?.getAttribute('src')||'';
      let renderImage='';
      if(src){const bytes=await (await fetch(src)).arrayBuffer();const sum=await crypto.subtle.digest('SHA-256',bytes);
        renderImage=[...new Uint8Array(sum)].map(v=>v.toString(16).padStart(2,'0')).join('');}
      const shapes = root => `${root} path,${root} polyline,${root} polygon,${root} line,${root} circle,${root} rect`;
      return {compose:read('#canvas .layer path:not(.layer-hit)'),process:read(shapes('#process-canvas')),reference:read(shapes('#process-reference')),
        renderImage,
        renderedRecipe:document.querySelector('#process-canvas')?.dataset.renderedRecipe||''};
    }""")
    def digest(value) -> str:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()
    return {
        "projectRecipes": recipes,
        "processRecipe": process_recipe,
        "geometryHashes": {name: digest(value) for name, value in geometry.items()},
        "geometryCounts": {name: len(value) if isinstance(value, list) else bool(value)
                           for name, value in geometry.items()},
        "timeDependentUi": page.evaluate("""() => ({
          progress:document.querySelector('#job-progress')?.textContent||'',
          remaining:document.querySelector('#job-remaining')?.textContent||'',
          position:document.querySelector('#pos-xy')?.textContent||''
        })"""),
    }


def contrast_evidence(page: Page) -> dict:
    names = ["bench", "bench-deep", "bench-rise", "bench-edge", "ink", "ink-hi",
             "ink-soft", "live", "live-soft", "live-fill", "live-fill-hi",
             "rust", "fader", "fader-hot"]
    values = page.evaluate("""names => Object.fromEntries(names.map(name => {
      const node=document.createElement('i'); node.style.color=`var(--${name})`;
      document.body.append(node); const value=getComputedStyle(node).color; node.remove();
      return [name,value];
    }))""", names)

    def rgb(name: str) -> tuple[int, int, int]:
        found = re.findall(r"[\d.]+", values[name])
        return tuple(int(round(float(v))) for v in found[:3])  # type: ignore[return-value]

    def luminance(colour: tuple[int, int, int]) -> float:
        channels = []
        for component in colour:
            value = component / 255
            channels.append(value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4)
        return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2]

    def ratio(a: str, b: str) -> float:
        high, low = sorted((luminance(rgb(a)), luminance(rgb(b))), reverse=True)
        return round((high + .05) / (low + .05), 2)

    roles = {
        "body / bench": ("ink", "bench"),
        "secondary / raised": ("ink-soft", "bench-rise"),
        "secondary / selected": ("ink-soft", "bench-edge"),
        "primary text / fill": ("ink-hi", "live-fill"),
        "primary text / hover fill": ("ink-hi", "live-fill-hi"),
        "danger / raised": ("rust", "bench-rise"),
        "focus indicator / background": ("live", "bench-deep"),
        "focus indicator / selected surface": ("live", "bench-edge"),
        "selected indicator / bench": ("live", "bench"),
        "slider thumb / track": ("ink-soft", "bench-deep"),
        "slider fill / track": ("fader", "bench-deep"),
        "slider hover fill / track": ("fader-hot", "bench-deep"),
    }
    return {
        "method": "WCAG relative-luminance contrast from browser-resolved CSS colors",
        "roles": {label: {"foreground": a, "background": b, "ratio": ratio(a, b)}
                  for label, (a, b) in roles.items()},
        "resolvedColors": values,
        "exclusions": ["disabled controls use opacity and are excluded from semantic text contrast claims"],
    }


def capture(page: Page, out: Path, manifest: dict, name: str,
            selectors: list[str], full_page: bool = False) -> None:
    page.wait_for_timeout(180)
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    page.screenshot(path=str(out / f"{name}.png"), full_page=full_page,
                    animations="disabled")
    item = measure(page, name, selectors)
    item["fixtureEvidence"] = fixture_evidence(page)
    manifest["scenarios"].append(item)


def reset(page: Page, base: str, width: int = 1440, height: int = 1000) -> None:
    request(base, "/api/disconnect", {})
    request(base, "/api/project/new", {})
    # Let the current page consume the two SSE-driven refreshes before its
    # reload; aborting those fetches would look like an application error.
    page.wait_for_timeout(350)
    page.set_viewport_size({"width": width, "height": height})
    page.reload(wait_until="domcontentloaded")
    wait_ready(page)


def add_layer(base: str, module: str, params: dict) -> str:
    return request(base, "/api/layers/generate", {"module": module, "params": params})["id"]


def add_animated_polygon(base: str) -> None:
    layer_id = add_layer(base, "polygon", {"sides": 5, "radius": 20})
    request(base, f"/api/layers/{layer_id}/animate", {})
    project = request(base, "/api/project")
    tween = next(layer for layer in project["layers"] if layer["source"]["type"] == "tween")
    b_id = tween["source"]["params"]["b"]
    request(base, f"/api/layers/{b_id}/regenerate",
            {"params": {"sides": 5, "radius": 60}, "coalesce": False})
    request(base, f"/api/layers/{tween['id']}/tween", {"follow_master": True}, method="PUT")


def capture_all(page: Page, base: str, out: Path, manifest: dict) -> None:
    manifest["contrast"] = contrast_evidence(page)
    common = ["#menubar", "#tabs", "#canvas-wrap", "#inspector", "#layers-dock", "#canvas-status"]

    # Dense, deterministic project with a selected source and open inspector.
    reset(page, base)
    fixtures = [
        ("polygon", {"sides": 7, "radius": 48}),
        ("flowfield", {"seed": 31}),
        ("venation", {"steps": 34, "attractors": 130, "seed": 17}),
        ("polygon", {"sides": 4, "radius": 22}),
        ("polygon", {"sides": 9, "radius": 30}),
        ("polygon", {"sides": 5, "radius": 64}),
    ]
    for module, params in fixtures:
        add_layer(base, module, params)
    page.reload(wait_until="domcontentloaded"); wait_ready(page)
    page.wait_for_function("document.querySelectorAll('#layer-list .layer-row').length === 6")
    page.locator("#layer-list .layer-row .lname").nth(2).click()
    page.wait_for_selector("#layer-detail-panel:not([hidden])")
    capture(page, out, manifest, "compose-dense-selected-1440x1000", common + ["#layer-detail-panel"])
    for width, height in ((1100, 750), (900, 650), (700, 650)):
        page.set_viewport_size({"width": width, "height": height})
        capture(page, out, manifest, f"compose-dense-selected-{width}x{height}", common + ["#layer-detail-panel"])

    # CSS zoom is an explicit approximation: Playwright has no browser zoom API.
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.evaluate("document.documentElement.style.zoom='2'")
    capture(page, out, manifest, "compose-css-zoom-200", common, full_page=False)
    manifest["zoomMethod"] = {
        "requested": "200% browser zoom",
        "used": "document.documentElement.style.zoom = '2'",
        "limitation": "Chromium/Playwright exposes no browser UI zoom control; this is a CSS zoom approximation, supplemented by 900x650 and 700x650 CSS viewports.",
    }
    page.evaluate("document.documentElement.style.zoom=''")

    # Shared tabs, a menu, and the app's real destructive confirmation state.
    page.set_viewport_size({"width": 1100, "height": 750})
    for tab in ("plot", "pens", "settings"):
        page.locator(f"#tabs button[data-tab='{tab}']").click()
        capture(page, out, manifest, f"{tab}-1100x750", common + [f"#tab-{tab}"])
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator("[data-menu='machine'] .menu-trigger").click()
    capture(page, out, manifest, "machine-menu-open", ["#menubar", "[data-menu='machine'] .menu-dropdown"])
    page.keyboard.press("Escape")
    page.locator("[data-menu='file'] .menu-trigger").click()
    capture(page, out, manifest, "file-menu-open", ["#menubar", "[data-menu='file'] .menu-dropdown"])
    page.keyboard.press("Escape")
    page.locator("#btn-proj-new").click()
    capture(page, out, manifest, "new-project-armed-confirmation", ["#menubar", "#global-error", "#btn-proj-new"])

    # Shared animation render popup, opened over Compose from a real tween.
    reset(page, base)
    add_animated_polygon(base)
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.reload(wait_until="domcontentloaded"); wait_ready(page)
    page.wait_for_selector("#timeline-bar:not([hidden])")
    page.click("#tl-render")
    page.wait_for_selector("#anim-preview-modal:not([hidden])")
    settle_render_frame(page)
    capture(page, out, manifest, "animation-render-popup-1440x1000",
            ["#anim-preview-modal .preview-modal", "#anim-preview-stage", "#anim-preview-img"])
    page.click("#anim-preview-close")

    # Identical Second Reading recipe, branches, pending control and comparison.
    reset(page, base)
    page.select_option("#gen-select", "second_reading")
    page.click("#btn-bench"); wait_preview(page)
    for _ in range(3):
        page.click("#process-continue"); wait_preview(page)
    page.click("#process-try-another"); wait_preview(page)
    page.fill("#process-attention", "0.8")
    page.dispatch_event("#process-attention", "input")
    page.dispatch_event("#process-attention", "change")
    capture(page, out, manifest, "second-reading-pending-1440x1000",
            ["#process-popup .preview-modal", "#process-popup .preview-stage", "#process-canvas", "#process-second-reading"])
    page.evaluate("document.documentElement.style.zoom='2'")
    capture(page, out, manifest, "second-reading-css-zoom-200",
            ["#process-popup .preview-modal", "#process-popup .preview-stage", "#process-canvas", "#process-controls"])
    page.evaluate("document.documentElement.style.zoom=''")
    page.click("#process-pin-reference")
    page.click("#process-compare")
    page.wait_for_selector("#process-reference:not([hidden])")
    capture(page, out, manifest, "second-reading-comparison-1440x1000",
            ["#process-popup .preview-modal", "#process-popup .preview-stage", "#process-canvas", "#process-reference"])
    page.click("#process-compare")
    page.click("#process-expand")
    for width, height in ((1100, 750), (900, 650), (700, 650)):
        page.set_viewport_size({"width": width, "height": height})
        capture(page, out, manifest, f"second-reading-expanded-{width}x{height}",
                ["#process-popup .preview-modal", "#process-popup .preview-stage", "#process-canvas", "#process-controls"])
    page.click("#process-controls-toggle")
    capture(page, out, manifest, "second-reading-compact-controls-700x650",
            ["#process-popup .preview-modal", "#process-popup .preview-stage", "#process-canvas", "#process-controls"])
    manifest["fixtures"]["secondReading"] = json.loads(page.locator("#process-recipe").text_content())

    # Deliberately injected preview error; identified as injected in manifest/report.
    page.set_viewport_size({"width": 1100, "height": 750})
    page.route("**/api/generators/preview", lambda route: route.fulfill(
        status=503, content_type="application/json",
        body='{"detail":"Precision review injected preview failure"}'))
    page.click("#process-continue")
    page.wait_for_function("document.querySelector('#process-preview-state').textContent === 'not rendered'")
    capture(page, out, manifest, "second-reading-injected-error-1100x750",
            ["#process-popup .preview-modal", "#process-error", "#global-error", "#process-canvas"])
    page.unroute("**/api/generators/preview")
    page.wait_for_timeout(300)
    page.click("#process-close")

    # Generic process bench and Venation's dedicated entry.
    reset(page, base)
    page.select_option("#gen-select", "homeostat"); page.click("#btn-bench")
    wait_generic_bench(page)
    capture(page, out, manifest, "homeostat-1440x1000",
            ["#process-popup .preview-modal", "#process-popup .preview-stage", "#process-canvas", "#process-controls"])
    page.click("#process-close")
    page.select_option("#gen-select", "venation"); page.click("#btn-bench")
    wait_generic_bench(page)
    capture(page, out, manifest, "venation-1440x1000",
            ["#process-popup .preview-modal", "#process-popup .preview-stage", "#process-canvas", "#process-controls"])
    page.click("#process-close")

    # Real simulator state: no app or hardware connection is touched.
    reset(page, base, 1100, 750)
    add_layer(base, "venation", {"steps": 200, "attractors": 600, "seed": 41})
    page.reload(wait_until="domcontentloaded"); wait_ready(page)
    request(base, "/api/backend/select", {"backend": "simulator"})
    request(base, "/api/connect", {})
    page.wait_for_function("!document.querySelector('#machine-state').hidden", timeout=20_000)
    request(base, "/api/plot/start", {"target": "all"})
    page.wait_for_function("document.querySelector('#job-progress').textContent.includes('%')", timeout=30_000)
    page.locator("#tabs button[data-tab='plot']").click()
    capture(page, out, manifest, "simulator-running-1100x750",
            common + ["#machine-state", "#tab-plot"])
    page.click("#btn-pause")
    page.wait_for_timeout(200)
    capture(page, out, manifest, "simulator-paused-1100x750",
            common + ["#machine-state", "#tab-plot"])
    page.click("#btn-stop")
    request(base, "/api/disconnect", {})


def capture_zoom_equivalent(browser, base: str, out: Path, manifest: dict) -> None:
    """A 720×450 CSS viewport at DPR 2, yielding a 1440×900 pixel image.

    This reproduces the layout pressure of 200% zoom much more closely than
    CSS ``zoom`` because media queries and viewport units see the reduced CSS
    viewport. It remains a browser emulation, not the native zoom menu.
    """
    context = browser.new_context(viewport={"width": 720, "height": 450}, device_scale_factor=2)
    page = context.new_page()
    install_determinism(page)
    page.on("pageerror", lambda error: manifest["pageErrors"].append(str(error)))
    page.on("console", lambda msg: manifest["consoleErrors"].append(msg.text)
            if msg.type == "error" else None)
    page.goto(base, wait_until="domcontentloaded"); wait_ready(page)
    reset(page, base, 720, 450)
    for module, params in [
        ("polygon", {"sides": 7, "radius": 48}), ("flowfield", {"seed": 31}),
        ("venation", {"steps": 34, "attractors": 130, "seed": 17}),
        ("polygon", {"sides": 4, "radius": 22}), ("polygon", {"sides": 9, "radius": 30}),
        ("polygon", {"sides": 5, "radius": 64})]:
        add_layer(base, module, params)
    page.reload(wait_until="domcontentloaded"); wait_ready(page)
    page.locator("#layer-list .layer-row .lname").nth(2).click()
    page.wait_for_selector("#layer-detail-panel:not([hidden])")
    capture(page, out, manifest, "compose-zoom-equivalent-720x450-dpr2",
            ["#menubar", "#tabs", "#canvas-wrap", "#inspector", "#layers-dock", "#canvas-status"])
    reset(page, base, 720, 450)
    page.select_option("#gen-select", "second_reading"); page.click("#btn-bench"); wait_preview(page)
    capture(page, out, manifest, "second-reading-zoom-equivalent-720x450-dpr2",
            ["#process-popup .preview-modal", "#process-popup .preview-stage", "#process-canvas", "#process-controls"])
    page.click("#process-close")
    page.select_option("#gen-select", "homeostat"); page.click("#btn-bench"); wait_generic_bench(page)
    capture(page, out, manifest, "homeostat-zoom-equivalent-720x450-dpr2",
            ["#process-popup .preview-modal", "#process-popup .preview-stage", "#process-canvas", "#process-controls"])
    page.click("#process-close")
    reset(page, base, 720, 450)
    add_animated_polygon(base)
    page.reload(wait_until="domcontentloaded"); wait_ready(page)
    page.wait_for_selector("#timeline-bar:not([hidden])")
    page.click("#tl-render")
    page.wait_for_selector("#anim-preview-modal:not([hidden])")
    settle_render_frame(page)
    capture(page, out, manifest, "animation-render-popup-zoom-equivalent-720x450-dpr2",
            ["#anim-preview-modal .preview-modal", "#anim-preview-stage", "#anim-preview-img"])
    manifest["zoomEquivalent"] = {
        "cssViewport": [720, 450], "deviceScaleFactor": 2,
        "outputPixels": [1440, 900],
        "limitation": "layout-pressure/browser emulation; not Chromium's native browser-menu zoom",
    }
    context.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, choices=("before", "after"))
    parser.add_argument("--static", required=True, type=Path)
    args = parser.parse_args()
    static = args.static.resolve()
    if not (static / "index.html").is_file():
        raise SystemExit(f"not a frontend static tree: {static}")
    out = HERE / "captures" / args.label
    out.mkdir(parents=True, exist_ok=True)
    port = free_port()
    config = Path(tempfile.mkdtemp(prefix=f"axb-precision-{args.label}-"))
    projects = config / "projects"
    projects.mkdir()
    (config / "settings.json").write_text(json.dumps({"projects_root": str(projects)}) + "\n")
    env = {**os.environ, "AXIBRIDGE_CONFIG_DIR": str(config), "AXIBRIDGE_NO_AUTOCONNECT": "1"}
    code = (
        "import uvicorn; import axibridge.app as a; from pathlib import Path; "
        f"a.frontend_dir=lambda:Path({str(static)!r}); "
        f"uvicorn.run(a.create_app(),host='127.0.0.1',port={port},log_level='error')"
    )
    proc = subprocess.Popen([str(ROOT / ".venv/bin/python"), "-c", code], cwd=ROOT,
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    manifest = {
        "label": args.label, "staticPath": str(static), "randomPort": port,
        "isolatedConfig": str(config), "noAutoconnect": True,
        "fixtures": {"compose": "polygon/flowfield/venation/polygon/polygon/polygon with fixed parameters"},
        "captureSettling": "180ms, two animation frames, screenshot animations disabled",
        "scenarios": [], "pageErrors": [], "consoleErrors": [],
        "injectedFailures": ["second-reading-injected-error-1100x750"],
    }
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError((proc.stderr.read() or b"").decode()[-3000:])
            try:
                request(base, "/api/state")
                break
            except Exception:
                time.sleep(.12)
        else:
            raise RuntimeError("isolated AxiBridge server did not start")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            install_determinism(page)
            page.on("pageerror", lambda error: manifest["pageErrors"].append(str(error)))
            page.on("console", lambda msg: manifest["consoleErrors"].append(msg.text)
                    if msg.type == "error" else None)
            page.goto(base, wait_until="domcontentloaded")
            wait_ready(page)
            capture_all(page, base, out, manifest)
            capture_zoom_equivalent(browser, base, out, manifest)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=5)
        shutil.rmtree(config, ignore_errors=True)
        manifest["serverClosed"] = proc.poll() is not None
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"captured {len(manifest['scenarios'])} scenarios to {out}")
    if manifest["pageErrors"] or manifest["consoleErrors"]:
        print(json.dumps({"pageErrors": manifest["pageErrors"], "consoleErrors": manifest["consoleErrors"]}, indent=2))


if __name__ == "__main__":
    main()
