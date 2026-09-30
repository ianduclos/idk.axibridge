"""Linedraw bench behavior through the real module picker and app shell."""

import json
import io

import pytest
from PIL import Image
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
    _upload_image(ui, 'paper.png', size=(40, 60))
    ui.route('**/api/linedraw/status',lambda route:route.fulfill(json={'available':True,'faces':True,'detail':'Synthetic models'}))
    def complete(route):
        params=route.request.post_data_json['params']
        params.update(faces=[],image_identity='synthetic',model_identity='synthetic')
        route.fulfill(json={'id':'example','state':'complete','result':{'params':params,'warnings':[],'preview':{'width':40,'height':60,'lines':[[[0,0],[10,0]]]}}})
    ui.route('**/api/linedraw/jobs',complete)
    open_bench(ui)
    ui.locator('#linedraw-image-form select:has(option[value="paper.png"])').select_option('paper.png')
    ui.click('#linedraw-analyze')
    ui.wait_for_function("document.getElementById('linedraw-message').textContent.startsWith('Drawing ready.')")
    points=ui.locator('#linedraw-drawing path').evaluate('''path => {
      const matrix=path.getScreenCTM();
      return [0,path.getTotalLength()].map(t=>{ const p=path.getPointAtLength(t);return new DOMPoint(p.x,p.y).matrixTransform(matrix); });
    }''')
    assert abs(points[0]['x']-points[1]['x'])<.01
    assert abs(points[0]['y']-points[1]['y'])>1


def _upload_image(page, name, size=(40, 60), *, exif_orientation=None):
    image = io.BytesIO()
    picture = Image.new('RGB', size, 'white')
    if exif_orientation is None:
        picture.save(image, format='PNG')
        mime = 'image/png'
    else:
        exif = Image.Exif()
        exif[274] = exif_orientation
        picture.save(image, format='JPEG', exif=exif)
        mime = 'image/jpeg'
    file = page.locator('#asset-file')
    if not file.is_visible():
        page.locator('#tabs button[data-tab="assets"]').click()
    file.set_input_files({'name': name, 'mimeType': mime, 'buffer': image.getvalue()})
    with page.expect_response(lambda response: response.url.endswith('/api/assets')
                              and response.request.method == 'POST') as upload:
        page.get_by_role('button', name='Add image asset').click()
    assert upload.value.ok
    page.wait_for_function(
        '(name) => document.getElementById("asset-list").textContent.includes(name)', arg=name)
    page.locator('#tabs button[data-tab="compose"]').click()


def _load_images(page, *names):
    for name in names:
        _upload_image(page, name)


def _synthetic_jobs(page):
    page.route('**/api/linedraw/status', lambda route: route.fulfill(json={
        'available': True, 'faces': True, 'detail': 'Synthetic models',
    }))

    def complete(route):
        params = route.request.post_data_json['params']
        image = params['image']
        params.update(
            faces=[{'id': image, 'cx': .25 if image == 'first.png' else .75,
                    'cy': .5, 'rx': .1, 'ry': .1, 'enabled': True, 'origin': 'automatic'}],
            image_identity='synthetic-' + image, model_identity='synthetic',
        )
        route.fulfill(json={
            'id': 'job-' + image, 'state': 'complete',
            'result': {'params': params, 'warnings': [],
                       'preview': {'width': 40, 'height': 60,
                                   'lines': [[[0, 0], [10, 0]]]}},
        })

    page.route('**/api/linedraw/jobs', complete)
    page.route('**/api/linedraw/jobs/job-*', lambda route: route.fulfill(json={}))
    # Hold the first POST response at the browser fetch boundary. The route
    # still returns a realistic completed job; the UI can change while its
    # original await remains pending.
    page.evaluate('''() => {
      const original = window.fetch.bind(window);
      window.__releaseLinedraw = null;
      window.__heldLinedraw = false;
      window.fetch = async (url, opts) => {
        const response = await original(url, opts);
        if (String(url).endsWith('/api/linedraw/jobs') && opts?.method === 'POST'
            && !window.__heldLinedraw) {
          window.__heldLinedraw = true;
          return new Promise(resolve => { window.__releaseLinedraw = () => resolve(response); });
        }
        return response;
      };
    }''')


@pytest.mark.parametrize('leave_first_draft', [False, True], ids=['change-image', 'cancel-draft'])
def test_late_analysis_cannot_replace_current_draft(ui, leave_first_draft):
    _load_images(ui, 'first.png', 'second.png')
    _synthetic_jobs(ui)
    open_bench(ui)
    image = ui.locator('#linedraw-image-form select:has(option[value="first.png"])')
    image.select_option('first.png')
    ui.click('#linedraw-analyze')
    ui.wait_for_function('window.__releaseLinedraw !== null')

    if leave_first_draft:
        ui.get_by_role('button', name='Cancel draft', exact=True).click()
        assert ui.locator('#process-popup').is_hidden()
        open_bench(ui)
        image = ui.locator('#linedraw-image-form select:has(option[value="second.png"])')
    image.select_option('second.png')
    ui.click('#linedraw-analyze')
    ui.wait_for_function("document.getElementById('linedraw-message').textContent.startsWith('Drawing ready.')")
    assert ui.get_by_label('Face center X (%)').input_value() == '75'

    with ui.expect_request('**/api/linedraw/jobs/job-first.png'):
        ui.evaluate('window.__releaseLinedraw()')
    assert image.input_value() == 'second.png'
    assert ui.get_by_label('Face center X (%)').input_value() == '75'
    assert ui.get_by_role('button', name='Keep as layer', exact=True).is_enabled()
    assert not ui.errors


def test_exif_oriented_source_and_face_region_share_coordinates(ui):
    _upload_image(ui, 'portrait.jpg', size=(40, 20), exif_orientation=6)
    ui.route('**/api/linedraw/status', lambda route: route.fulfill(json={
        'available': True, 'faces': True, 'detail': 'Synthetic models',
    }))
    open_bench(ui)
    ui.locator('#linedraw-image-form select:has(option[value="portrait.jpg"])').select_option('portrait.jpg')
    ui.wait_for_function("document.getElementById('linedraw-source').getAttribute('viewBox') === '0 0 20 40'")
    ui.get_by_role('button', name='Add face region', exact=True).click()
    source = ui.locator('#linedraw-source')
    assert source.locator('image').get_attribute('width') == '20'
    assert source.locator('image').get_attribute('height') == '40'
    assert source.locator('ellipse').get_attribute('cx') == '10'
    assert source.locator('ellipse').get_attribute('cy') == '12'
    assert not ui.errors
