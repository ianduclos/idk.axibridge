"""Grouped Compose helper selection and row actions in an isolated browser module."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


SOURCE = Path(__file__).resolve().parent.parent / "axibridge/static/js/group_ui.js"


@pytest.fixture
def group_module():
    modules = {
        "group_ui.js": SOURCE.read_text(),
        "api.js": """export const api = {
          post: async (path, body) => { window.__groupCalls.push(['POST', path, body]); return {}; },
          patch: async (path, body) => { window.__groupCalls.push(['PATCH', path, body]); return {}; },
        };""",
    }

    def serve(route):
        name = route.request.url.rsplit("/", 1)[-1]
        route.fulfill(status=200, content_type="text/javascript", body=modules[name])

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"no chromium: {str(exc)[:120]}")
        ui = browser.new_page()
        ui.route("http://group.test/", lambda route: route.fulfill(
            status=200, content_type="text/html", body="<html><body></body></html>"))
        ui.route("**/test-group-modules/*", serve)
        ui.goto("http://group.test/", wait_until="domcontentloaded")
        ui.evaluate("""async () => {
      window.__groupCalls = [];
      window.__groupEvents = [];
      window.__groupModule = await import('/test-group-modules/group_ui.js');
      window.__groupProject = {
        layers: [
          {id:'a',name:'Outside bottom',group_id:null,visible:true,source:{type:'baked'}},
          {id:'b',name:'Outer child',group_id:'g1',visible:true,source:{type:'baked'}},
          {id:'c',name:'Inner child',group_id:'g2',visible:true,source:{type:'baked'}},
          {id:'d',name:'Animate',group_id:'g2',visible:true,source:{type:'tween',params:{a:'c',b:'e'}}},
          {id:'e',name:'Keyframe',group_id:'g2',animation_owner_id:'d',visible:true,source:{type:'generator'}},
          {id:'f',name:'Outer top',group_id:'g1',visible:true,source:{type:'baked'}},
          {id:'g',name:'Outside top',group_id:null,visible:true,source:{type:'baked'}},
        ],
        groups: [
          {id:'g1',name:'Outer',parent_id:null,visible:true},
          {id:'g2',name:'Inner',parent_id:'g1',visible:true},
        ],
      };
      window.__groupContainer = document.createElement('div');
      window.__groupContainer.id = 'group-ui-test';
      document.body.append(window.__groupContainer);
      window.__renderGroup = (context=null, selection=[]) =>
        window.__groupModule.renderHierarchy(window.__groupContainer, {
          project: window.__groupProject, context, selection,
          onSelect: targets => window.__groupEvents.push(['select', targets]),
          onEnter: id => window.__groupEvents.push(['enter', id]),
          onExit: () => window.__groupEvents.push(['exit']),
          onRefresh: () => window.__groupEvents.push(['refresh']),
        });
        }""")
        yield ui
        browser.close()


def test_selection_maps_to_outermost_group_then_current_context(group_module):
    page = group_module
    result = page.evaluate("""() => {
      const m = window.__groupModule, p = window.__groupProject;
      return {
        root: m.targetsForLayerIds(p, ['c','e','g']),
        outer: m.targetsForLayerIds(p, ['c','e','g'], 'g1'),
        inner: m.targetsForLayerIds(p, ['e','c'], 'g2'),
        normalized: m.normalizeTargets(p, [
          {kind:'layer',id:'c'}, {kind:'group',id:'g2'}, {kind:'group',id:'g1'},
        ]),
        members: m.memberIds(p, [{kind:'group',id:'g1'}]),
        family: m.memberIds(p, [{kind:'layer',id:'e'}]),
      };
    }""")
    assert result == {
        "root": [{"kind": "group", "id": "g1"}, {"kind": "layer", "id": "g"}],
        "outer": [{"kind": "group", "id": "g2"}],
        "inner": [{"kind": "layer", "id": "d"}, {"kind": "layer", "id": "c"}],
        "normalized": [{"kind": "group", "id": "g1"}],
        "members": ["b", "c", "d", "e", "f"],
        "family": ["d", "e"],
    }


def test_render_shows_current_siblings_and_keeps_controls_focusable(group_module):
    page = group_module
    page.evaluate("() => window.__renderGroup(null)")
    assert page.locator("#group-ui-test .layer-row").count() == 3
    assert page.locator("#group-ui-test .layer-row").all_text_contents()[0].find("Outside top") >= 0
    page.get_by_role("button", name="Outer", exact=True).click()
    assert page.evaluate("() => window.__groupEvents.at(-1)") == ["select", [{"kind": "group", "id": "g1"}]]
    page.get_by_role("button", name="Enter Outer").click()
    assert page.evaluate("() => window.__groupEvents.at(-1)") == ["enter", "g1"]

    page.evaluate("() => window.__renderGroup('g1')")
    assert page.locator("#group-ui-test .layer-row").count() == 3
    assert page.get_by_role("button", name="Exit group").count() == 1
    page.get_by_role("button", name="Inner", exact=True).focus()
    assert page.evaluate("() => document.activeElement?.textContent") == "Inner"
    page.get_by_role("button", name="Exit group").click()
    assert page.evaluate("() => window.__groupEvents.at(-1)") == ["exit"]


def test_group_visibility_and_reorder_use_typed_endpoints(group_module):
    page = group_module
    page.evaluate("() => window.__renderGroup(null)")
    page.get_by_role("button", name="Hide Outer").click()
    page.wait_for_function("() => window.__groupCalls.length === 1")
    assert page.evaluate("() => window.__groupCalls[0]") == [
        "PATCH", "/api/compose/groups/g1", {"visible": False}
    ]
    assert page.evaluate("() => window.__groupEvents.at(-1)") == ["refresh"]
    page.get_by_role("button", name="Move Outer up").click()
    page.wait_for_function("() => window.__groupCalls.length === 2")
    assert page.evaluate("() => window.__groupCalls[1]") == [
        "POST", "/api/compose/selection/reparent",
        {"targets": [{"kind": "group", "id": "g1"}], "parent_id": None, "before_id": None},
    ]


def test_siblings_export_and_existing_layer_renderer_are_preserved(group_module):
    page = group_module
    result = page.evaluate("""() => {
      const m = window.__groupModule, p = window.__groupProject;
      const rendered = [];
      m.renderHierarchy(window.__groupContainer, {
        project: p, context: 'g2', selection: [],
        renderLayer(target) {
          rendered.push(target.id);
          const row = document.createElement('div');
          row.className = 'layer-row existing-rich-row';
          row.textContent = `Rich ${target.id}`;
          return row;
        },
      });
      return {siblings:m.siblingTargets(p,'g2'), rendered,
        rich:[...document.querySelectorAll('#group-ui-test .existing-rich-row')].map(x=>x.textContent)};
    }""")
    assert result == {
        "siblings": [{"kind": "layer", "id": "c"}, {"kind": "layer", "id": "d"}],
        "rendered": ["d", "c"],
        "rich": ["Rich d", "Rich c"],
    }


def test_shift_click_adds_typed_target_selection(group_module):
    page = group_module
    page.evaluate("() => window.__renderGroup(null, [{kind:'layer',id:'g'}])")
    page.get_by_role("button", name="Outer", exact=True).click(modifiers=["Shift"])
    assert page.evaluate("() => window.__groupEvents.at(-1)") == [
        "select", [{"kind": "layer", "id": "g"}, {"kind": "group", "id": "g1"}]
    ]


def test_group_ungroup_duplicate_and_confirmed_delete_use_group_target(group_module):
    page = group_module
    page.evaluate("() => window.__renderGroup(null)")
    page.get_by_role("button", name="Ungroup Outer").click()
    page.get_by_role("button", name="Duplicate Outer").click()
    delete = page.get_by_role("button", name="Delete Outer")
    delete.click()
    assert len(page.evaluate("() => window.__groupCalls")) == 2
    delete.click()
    page.wait_for_function("() => window.__groupCalls.length === 3")
    assert page.evaluate("() => window.__groupCalls") == [
        ["POST", "/api/compose/groups/g1/ungroup", {}],
        ["POST", "/api/compose/selection/duplicate", {"targets": [{"kind": "group", "id": "g1"}]}],
        ["POST", "/api/compose/selection/delete", {"targets": [{"kind": "group", "id": "g1"}]}],
    ]
