"""Linedraw bench behavior through the real module picker and app shell."""

import json
from test_acceptance_ui import frontend_mode, server, ui


def open_bench(page):
    page.select_option("#gen-select", "linedraw_v3")
    page.click("#btn-bench")
    page.wait_for_selector("#linedraw-panel:not([hidden])")
    toggle = page.locator("#process-controls-toggle")
    if toggle.is_visible() and toggle.get_attribute("aria-expanded") != "true":
        toggle.click()


def test_regions_are_editable_drafts(ui):
    open_bench(ui)
    ui.get_by_role("button", name="Add face region", exact=True).click()
    x = ui.get_by_label("Face center X (%)")
    x.fill("40")
    x.press("Tab")
    assert x.input_value() == "40"
    ui.get_by_role("button", name="Delete face region", exact=True).click()
    assert x.is_disabled()
    ui.get_by_role("button", name="Cancel draft", exact=True).click()
    assert ui.locator("#process-popup").is_hidden()
    assert not ui.errors


def test_style_and_cancel_preserve_project(ui):
    open_bench(ui)
    for style in ("contours", "light_form", "shadow_shapes", "face_form"):
        ui.get_by_label("Drawing style", exact=True).select_option(style)
    assert ui.get_by_role("button", name="Keep as layer", exact=True).is_disabled()
    ui.get_by_role("button", name="Cancel draft", exact=True).click()
    assert not ui.errors

def test_static_bench_has_no_playback_controls(ui):
    open_bench(ui)
    assert not ui.locator('#process-play').is_visible()
    assert not ui.locator('#process-canvas').is_visible()

def test_preview_uses_current_portrait_view(ui):
    import io
    from PIL import Image
    image=io.BytesIO();Image.new('RGB',(40,60),'white').save(image,format='PNG')
    ui.request.post(ui.base+'/api/assets',multipart={'file':{'name':'paper.png','mimeType':'image/png','buffer':image.getvalue()}})
    ui.reload(wait_until='domcontentloaded')
    ui.wait_for_function("document.querySelectorAll('#gen-select option').length>0")
    ui.route('**/api/linedraw/status',lambda route:route.fulfill(json={'available':True,'faces':True,'detail':'Synthetic models'}))
    def complete(route):
        params=route.request.post_data_json['params']
        params.update(faces=[],image_identity='synthetic',model_identity='synthetic')
        route.fulfill(json={'id':'example','state':'complete','result':{'params':params,'warnings':[],'preview':{'width':40,'height':60,'lines':[[[0,0],[10,0]]]}}})
    ui.route('**/api/linedraw/jobs',complete)
    open_bench(ui)
    ui.locator('#linedraw-form select:has(option[value="paper.png"])').select_option('paper.png')
    ui.click('#linedraw-analyze')
    ui.wait_for_function("document.getElementById('linedraw-message').textContent.startsWith('Drawing ready.')")
    points=ui.locator('#linedraw-drawing path').evaluate('''path => {
      const matrix=path.getScreenCTM();
      return [0,path.getTotalLength()].map(t=>{ const p=path.getPointAtLength(t);return new DOMPoint(p.x,p.y).matrixTransform(matrix); });
    }''')
    assert abs(points[0]['x']-points[1]['x'])<.01
    assert abs(points[0]['y']-points[1]['y'])>1
