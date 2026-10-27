"""Fill tool acceptance against the real resolver and saved editable geometry."""
import math
import tempfile
from pathlib import Path
import pytest
from test_acceptance_ui import _get, _post, frontend_mode as _built_frontend, server, ui


@pytest.fixture(scope="session", params=["source", "built"])
def frontend_mode(request):
    if request.param == "built":
        yield _built_frontend.__wrapped__()
        return
    # The production server chooses source exactly when no bundle is present.
    dist = Path(__file__).resolve().parents[1] / "axibridge/static_dist"
    with tempfile.TemporaryDirectory(prefix="fill-ui-bundle-") as temp:
        saved = Path(temp) / "static_dist"
        if dist.exists():
            dist.rename(saved)
        try:
            yield "source"
        finally:
            if saved.exists():
                saved.rename(dist)


def seed(page, hole=True, gap=0, contour=False, follow=False):
    def square(x,y,s):
        return {'anchors':[{'x':a,'y':b} for a,b in [(x,y),(x+s,y),(x+s,y+s),(x,y+s)]], 'closed':True}
    paths = [square(70,60,110)] + ([square(110,100,30)] if hole else [])
    if contour:
        paths[0] = {'anchors':[{'x':125+(65+3*math.sin(i*.6))*math.cos(i*math.tau/80),
                                'y':115+(65+3*math.sin(i*.6))*math.sin(i*math.tau/80)} for i in range(80)], 'closed':True}
    if gap:
        paths[0]['closed'] = False
        paths[0]['anchors'].append({'x':70,'y':60+gap})
    created=_post(page.base+'/api/layers/generate', {'module':'pen','params':{'subpaths':paths}})
    if follow:
        from test_acceptance_ui import _patch
        _patch(page.base+'/api/layers/'+created['id'],{'frame_follow':True})
    from test_acceptance_ui import reload_app
    reload_app(page)
    page.wait_for_selector('#layer-list .layer-row')


def point(page, x=90, y=80):
    # The world SVG transform is the public on-screen paper geometry.
    return page.locator('#canvas .bed-rect').evaluate('(e,p) => {const q=new DOMPoint(...p).matrixTransform(e.parentNode.getScreenCTM());return [q.x,q.y]}',[x,y])


def hover(page,x=90,y=80):
    page.mouse.move(*point(page,x,y))
    page.wait_for_selector('.fill-candidate')


def create(page):
    page.click('[data-tool=fill]')
    hover(page)
    page.mouse.click(*point(page))
    page.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 2")


def test_preview_holes_editable_result_default_and_creation_undo(ui):
    seed(ui)
    ui.click('[data-tool=fill]')
    hover(ui)
    assert len(_get(ui.base+'/api/project')['layers']) == 1
    assert ui.locator('.fill-candidate').get_attribute('fill-rule') == 'evenodd'
    ui.mouse.click(*point(ui))
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 2")
    layer = _get(ui.base+'/api/project')['layers'][-1]
    assert layer['source']['generator'] == 'pen'
    assert len(layer['source']['params']['subpaths']) == 2
    assert layer['effects'] == []
    assert ui.locator('#layer-list .selected').count() == 1
    assert ui.locator('#fill-outline').is_disabled()
    ui.keyboard.press('Meta+z')
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 1")
    assert not ui.errors


@pytest.mark.parametrize('effect',['hatch_fill','offset_fill','offset_fill_v2','eigen_fill'])
def test_explicit_effect_and_outline(ui,effect):
    seed(ui)
    create(ui)
    ui.select_option('#fill-effect',effect)
    ui.wait_for_function("() => !document.querySelector('#fill-outline').disabled")
    ui.uncheck('#fill-outline')
    ui.wait_for_timeout(400)
    layer=_get(ui.base+'/api/project')['layers'][-1]
    assert layer['effects'][0]['effect']==effect
    assert layer['effects'][0]['params']['outline'] is False
    ui.select_option('#fill-effect','')
    ui.wait_for_function("() => document.querySelector('#fill-outline').disabled")
    assert _get(ui.base+'/api/project')['layers'][-1]['effects']==[]


def test_escape_and_mode_exit_clear_preview(ui):
    seed(ui)
    ui.click('[data-tool=fill]')
    hover(ui)
    ui.keyboard.press('Escape')
    assert ui.locator('.fill-candidate').count()==0
    assert 'on' in ui.locator('[data-tool=select]').get_attribute('class')
    assert len(_get(ui.base+'/api/project')['layers'])==1


def test_zoom_portrait_hover_uses_paper_coordinates(ui):
    seed(ui)
    # Zoom is user-facing; portrait is persisted through the ordinary project patch.
    from test_acceptance_ui import _put
    _put(ui.base+'/api/project', {'view':'portrait'})
    ui.reload(wait_until='domcontentloaded')
    ui.wait_for_selector('#layer-list .layer-row')
    ui.fill('#zoom-pct','200')
    ui.press('#zoom-pct','Enter')
    requests=[]
    ui.on('request', lambda r: requests.append(r.post_data_json) if '/api/geometry/face' in r.url else None)
    ui.click('[data-tool=fill]')
    hover(ui,125,115)  # hole interior is a different face
    assert requests
    assert requests[-1]['point']==pytest.approx([125,115],abs=.2)


def test_gap_repair_preview_is_required_before_commit(ui):
    seed(ui,hole=False,gap=1)
    ui.click('[data-tool=fill]')
    ui.mouse.move(*point(ui))
    ui.wait_for_timeout(350)
    assert ui.locator('.fill-candidate').count()==0
    ui.fill('#fill-gap','1.2')
    ui.wait_for_selector('.fill-candidate')
    ui.mouse.click(*point(ui))
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 2")


def test_detail_refits_all_rings_one_undo_per_gesture_and_retry(ui):
    seed(ui,contour=True)
    create(ui)
    before=_get(ui.base+'/api/project')['layers'][-1]['source']['params']
    fits=[]
    ui.on('request',lambda r: fits.append(r.post_data_json) if r.url.endswith('/api/geometry/face/fit') else None)
    # One pointer gesture with several live input values.
    ui.locator('#fill-detail').dispatch_event('pointerdown')
    for value in ['0.1','0.3','0.9']:
        ui.locator('#fill-detail').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input",{bubbles:true}));}',value)
        ui.wait_for_timeout(250)
    ui.locator('#fill-detail').dispatch_event('change')
    ui.wait_for_timeout(350)
    assert fits and all(len(f['rings'])==2 for f in fits)
    assert fits[-1]['detail']==.9
    assert _get(ui.base+'/api/project')['layers'][-1]['source']['params'] != before
    ui.keyboard.press('Meta+z')
    ui.wait_for_timeout(300)
    assert _get(ui.base+'/api/project')['layers'][-1]['source']['params']==before
    count=len(fits)
    ui.locator('#fill-detail').evaluate('(e)=>{e.value=.7;e.dispatchEvent(new Event("input",{bubbles:true}));}')
    ui.wait_for_timeout(200)
    assert len(fits)==count  # undo ended ownership


def test_failed_create_can_retry_and_pending_double_click_creates_once(ui):
    seed(ui)
    held=[]
    def hold(route):
        held.append(route)
    ui.route('**/api/layers/fill',hold)
    ui.click('[data-tool=fill]')
    hover(ui)
    ui.mouse.dblclick(*point(ui))
    ui.wait_for_timeout(200)
    assert len(held)==1
    held.pop().fulfill(status=422,content_type='application/json',body='{"detail":"retry fill"}')
    ui.wait_for_selector('#global-error:not(:empty)')
    ui.unroute('**/api/layers/fill',hold)
    ui.mouse.click(*point(ui))
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 2")


def test_abandoned_hover_never_revives_after_switch(ui):
    seed(ui)
    held=[]
    def hold(route):
        response=route.fetch()
        held.append((route,response))
    ui.route('**/api/geometry/face',hold)
    ui.click('[data-tool=fill]')
    ui.mouse.move(*point(ui))
    ui.wait_for_timeout(300)
    assert held
    ui.click('[data-tool=pen]')
    route,response=held.pop()
    route.fulfill(response=response)
    ui.wait_for_timeout(150)
    assert ui.locator('.fill-candidate').count()==0
    assert len(_get(ui.base+'/api/project')['layers'])==1


def test_refit_failure_keeps_geometry_and_current_detail_can_retry(ui):
    seed(ui,contour=True)
    create(ui)
    before=_get(ui.base+'/api/project')['layers'][-1]['source']['params']
    failed=[]
    def fail(route):
        failed.append(route.request.post_data_json)
        route.fulfill(status=422,content_type='application/json',body='{"detail":"refit refused"}')
    ui.route('**/api/geometry/face/fit',fail)
    ui.locator('#fill-detail').evaluate('(e)=>{e.value=.95;e.dispatchEvent(new Event("input",{bubbles:true}));}')
    ui.wait_for_selector('#global-error:not(:empty)')
    assert _get(ui.base+'/api/project')['layers'][-1]['source']['params']==before
    ui.unroute('**/api/geometry/face/fit',fail)
    with ui.expect_response('**/regenerate'):
        ui.locator('#fill-detail').press('Enter')
    assert failed[0]['detail']==.95
    assert _get(ui.base+'/api/project')['layers'][-1]['source']['params']!=before


def test_stale_revision_cannot_commit_then_hover_refreshes(ui):
    seed(ui)
    ui.click('[data-tool=fill]')
    hover(ui)
    # A second client changes geometry while this tab still has its candidate.
    from test_acceptance_ui import _patch
    original=_get(ui.base+'/api/project')['layers'][0]
    _patch(ui.base+'/api/layers/'+original['id'],{'name':'changed elsewhere'})
    ui.mouse.click(*point(ui))
    ui.wait_for_timeout(300)
    assert len(_get(ui.base+'/api/project')['layers'])==1
    ui.mouse.move(*point(ui,92,82))
    ui.wait_for_selector('.fill-candidate')
    ui.mouse.click(*point(ui,92,82))
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 2")


def test_preview_disabled_in_sheet_and_companions_fit_native_width(ui):
    seed(ui)
    from test_acceptance_ui import reload_app
    group=_post(ui.base+'/api/staging/capture',{'kind':'plot','name':'fill test tray'})['group']
    reload_app(ui)
    ui.click('#tabs button[data-tab=plot]')
    ui.wait_for_selector('.stage-group')
    ui.set_viewport_size({'width':1100,'height':800})
    ui.click('[data-tool=fill]')
    bar=ui.locator('#fill-bar').bounding_box()
    wrap=ui.locator('#canvas-toolbar').bounding_box()
    assert bar['x']>=wrap['x'] and bar['x']+bar['width']<=wrap['x']+wrap['width']+1
    ui.click(f'[data-stage-preview="{group["id"]}:{group["sheets"][0]["id"]}"]')
    ui.wait_for_function("()=>document.querySelector('[data-tool=fill]').disabled")
    assert ui.locator('#fill-bar').is_hidden()
    assert 'on' in ui.locator('[data-tool=select]').get_attribute('class')


def test_released_detail_drag_keeps_token_for_pending_final_value(ui):
    seed(ui,contour=True)
    create(ui)
    before=_get(ui.base+'/api/project')['layers'][-1]['source']['params']
    held=[]
    def hold_middle(route):
        if route.request.post_data_json['detail']==.2:
            held.append((route,route.fetch()))
        else:
            route.continue_()
    ui.route('**/api/geometry/face/fit',hold_middle)
    slider=ui.locator('#fill-detail')
    slider.dispatch_event('pointerdown')
    with ui.expect_response('**/regenerate'):
        slider.evaluate('(e)=>{e.value=.1;e.dispatchEvent(new Event("input",{bubbles:true}));}')
    ui.wait_for_function("()=>!document.querySelector('#fill-effect').disabled")
    slider.evaluate('(e)=>{e.value=.2;e.dispatchEvent(new Event("input",{bubbles:true}));}')
    ui.wait_for_timeout(200)
    assert held
    slider.evaluate('(e)=>{e.value=.95;e.dispatchEvent(new Event("input",{bubbles:true}));}')
    slider.dispatch_event('change')
    with ui.expect_response('**/regenerate'):
        route,response=held.pop()
        route.fulfill(response=response)
    ui.wait_for_function("()=>!document.querySelector('#fill-effect').disabled")
    assert _get(ui.base+'/api/project')['layers'][-1]['source']['params']!=before
    ui.keyboard.press('Meta+z')
    ui.wait_for_timeout(250)
    assert _get(ui.base+'/api/project')['layers'][-1]['source']['params']==before


@pytest.mark.parametrize('interruption',['selection','edit','timeline'])
def test_change_during_sync_ends_raw_ring_ownership(ui,interruption):
    seed(ui,contour=True,follow=interruption=='timeline')
    create(ui)
    ui.wait_for_function("()=>!document.querySelector('#fill-effect').disabled")
    held=[]
    fits=[]
    def hold_once(route):
        if not held:
            held.append((route,route.fetch()))
        else:
            route.continue_()
    ui.route('**/api/compose/resolved**',hold_once)
    ui.on('request',lambda r:fits.append(r.url) if r.url.endswith('/api/geometry/face/fit') else None)
    ui.locator('#fill-detail').evaluate('(e)=>{e.value=.1;e.dispatchEvent(new Event("input",{bubbles:true}));}')
    ui.wait_for_timeout(300)
    assert held
    if interruption=='selection':
        ui.locator('#layer-list .layer-row').last.click()
    elif interruption=='edit':
        from test_acceptance_ui import _patch
        source=_get(ui.base+'/api/project')['layers'][0]
        _patch(ui.base+'/api/layers/'+source['id'],{'name':'edited during fill sync'})
        ui.wait_for_timeout(150)
    else:
        ui.locator('#tl-scrub').evaluate('(e)=>{e.value=.8;e.dispatchEvent(new Event("input",{bubbles:true}));}')
    route,response=held.pop()
    route.fulfill(response=response)
    ui.unroute('**/api/compose/resolved**',hold_once)
    ui.wait_for_timeout(200)
    count=len(fits)
    ui.locator('#fill-detail').evaluate('(e)=>{e.value=.95;e.dispatchEvent(new Event("input",{bubbles:true}));}')
    ui.wait_for_timeout(200)
    assert len(fits)==count
    assert ui.locator('#fill-effect').is_disabled()


def test_timeline_scrub_abandons_held_candidate_even_without_edit(ui):
    seed(ui)
    from test_acceptance_ui import _patch, reload_app
    source=_get(ui.base+'/api/project')['layers'][0]
    _patch(ui.base+'/api/layers/'+source['id'],{'frame_follow':True})
    reload_app(ui)
    held=[]
    def hold_once(route):
        if not held:
            held.append((route,route.fetch()))
        else:
            route.continue_()
    ui.route('**/api/geometry/face',hold_once)
    ui.click('[data-tool=fill]')
    ui.mouse.move(*point(ui))
    ui.wait_for_timeout(200)
    assert held
    rev=_get(ui.base+'/api/project')['edit_rev']
    ui.locator('#tl-scrub').evaluate('(e)=>{e.value=.8;e.dispatchEvent(new Event("input",{bubbles:true}));}')
    route,response=held.pop()
    route.fulfill(response=response)
    ui.wait_for_timeout(200)
    assert ui.locator('.fill-candidate').count()==0
    assert _get(ui.base+'/api/project')['edit_rev']==rev


def test_pending_create_finishes_after_exit_without_reopening_controls(ui):
    seed(ui)
    held=[]
    def hold(route):
        held.append(route)
    ui.route('**/api/layers/fill',hold)
    ui.click('[data-tool=fill]')
    hover(ui)
    ui.mouse.click(*point(ui))
    ui.wait_for_timeout(100)
    assert held
    ui.keyboard.press('Escape')
    held.pop().continue_()
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row').length === 2")
    ui.wait_for_timeout(150)
    assert ui.locator('#fill-bar').is_hidden()
    assert 'on' in ui.locator('[data-tool=select]').get_attribute('class')
    assert not ui.errors


def test_separate_detail_gestures_have_separate_undo_steps(ui):
    seed(ui,contour=True)
    create(ui)
    values=[]
    for detail_value in [.1,.95]:
        slider=ui.locator('#fill-detail')
        slider.dispatch_event('pointerdown')
        with ui.expect_response('**/regenerate'):
            slider.evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input",{bubbles:true}));}',detail_value)
            slider.dispatch_event('change')
        ui.wait_for_function("()=>!document.querySelector('#fill-effect').disabled")
        values.append(_get(ui.base+'/api/project')['layers'][-1]['source']['params'])
    assert values[0]!=values[1]
    ui.keyboard.press('Meta+z')
    ui.wait_for_timeout(250)
    assert _get(ui.base+'/api/project')['layers'][-1]['source']['params']==values[0]
