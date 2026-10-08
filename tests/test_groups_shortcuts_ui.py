"""Real-browser acceptance for grouped editing and everyday shortcuts."""

from test_acceptance_ui import (_get, _patch, add_layer, frontend_mode,
                                reload_app, server, ui)


def project(page):
    return _get(f"{page.base}/api/project")


def two_layers(page):
    first = add_layer(page, "polygon", {"sides": 5, "radius": 12})
    second = add_layer(page, "polygon", {"sides": 5, "radius": 12})
    _patch(f"{page.base}/api/layers/{second}", {"transform": {
        "a": 1, "b": 0, "c": 0, "d": 1, "e": 50, "f": 0}})
    reload_app(page)
    return first, second


def select_both_rows(page):
    rows = page.locator("#layer-list .layer-row .lname")
    rows.first.click()
    rows.last.click(modifiers=["Shift"])
    page.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row.selected').length === 2")


def make_group(page):
    first, second = two_layers(page)
    select_both_rows(page)
    page.get_by_role("button", name="Group", exact=True).click()
    page.wait_for_function("() => document.querySelectorAll('#layer-list .group-row').length === 1")
    group = project(page)["groups"][0]
    assert {layer["group_id"] for layer in project(page)["layers"]} == {group["id"]}
    return first, second, group["id"]


def path_screen_point(page, layer_id):
    return page.locator(f'#canvas .layer-hit[data-id="{layer_id}"]').evaluate("""path => {
      const p = path.getPointAtLength(path.getTotalLength() / 8);
      const screen = p.matrixTransform(path.getScreenCTM());
      return {x: screen.x, y: screen.y};
    }""")


def test_toolbar_grouping_keeps_flat_order_and_selects_group(ui):
    first, second, group_id = make_group(ui)
    state = project(ui)
    assert [layer["id"] for layer in state["layers"]] == [first, second]
    assert [group["id"] for group in state["groups"]] == [group_id]
    assert ui.locator("#layer-list .group-row.selected").count() == 1
    assert ui.locator("#layer-list .layer-row").count() == 1
    assert not ui.errors


def test_canvas_click_selects_outer_group_doubleclick_enters_escape_exits(ui):
    first, second, group_id = make_group(ui)
    ui.locator("#canvas").click(position={"x": 4, "y": 4})
    point = path_screen_point(ui, first)
    ui.mouse.click(point["x"], point["y"])
    ui.wait_for_function("(gid) => document.querySelector('#layer-list .group-row.selected')?.dataset.id === gid",
                         arg=group_id)
    ui.locator("#canvas").click(position={"x": 4, "y": 4})
    ui.mouse.dblclick(point["x"], point["y"])
    ui.get_by_role("button", name="Exit group").wait_for(state="visible", timeout=2000)
    assert ui.locator(f'#layer-list .layer-row[data-layer-id="{first}"]').count() == 1
    assert ui.locator(f'#layer-list .layer-row[data-layer-id="{second}"]').count() == 1
    ui.keyboard.press("Escape")
    ui.wait_for_function("(gid) => document.querySelector('#layer-list .group-row.selected')?.dataset.id === gid",
                         arg=group_id)
    assert ui.get_by_role("button", name="Exit group").count() == 0
    assert not ui.errors


def test_group_nudges_are_millimetres_and_one_undo_each(ui):
    _, _, group_id = make_group(ui)
    with ui.expect_response(lambda response: response.request.method == "POST" and
            response.url.endswith("/api/compose/selection/transform")):
        ui.keyboard.press("ArrowRight")
    assert next(g for g in project(ui)["groups"] if g["id"] == group_id)["transform"]["e"] == 1
    with ui.expect_response(lambda response: response.request.method == "POST" and
            response.url.endswith("/api/compose/selection/transform")):
        ui.keyboard.press("Shift+ArrowUp")
    state = project(ui)
    moved = next(g for g in state["groups"] if g["id"] == group_id)["transform"]
    assert moved["e"] == 1 and moved["f"] == -10
    ui.keyboard.press("Meta+z")
    ui.wait_for_function("(gid) => document.querySelector('#layer-list .group-row.selected')?.dataset.id === gid",
                         arg=group_id)
    undone = next(g for g in project(ui)["groups"] if g["id"] == group_id)["transform"]
    assert undone["e"] == 1 and undone["f"] == 0
    assert not ui.errors


def test_group_duplicate_and_shortcut_ungroup_keep_original_members(ui):
    first, second, group_id = make_group(ui)
    ui.keyboard.press("Meta+d")
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .group-row').length === 2")
    state = project(ui)
    assert len(state["layers"]) == 4 and len(state["groups"]) == 2
    assert {layer["group_id"] for layer in state["layers"] if layer["id"] in (first, second)} == {group_id}
    ui.keyboard.press("Meta+Shift+g")
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .group-row').length === 1")
    result = project(ui)
    assert len(result["layers"]) == 4 and [g["id"] for g in result["groups"]] == [group_id]
    assert sum(layer["group_id"] is None for layer in result["layers"]) == 2
    assert not ui.errors


def test_group_keyboard_shortcut_and_five_tab_keys(ui):
    two_layers(ui)
    select_both_rows(ui)
    ui.keyboard.press("Meta+g")
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .group-row').length === 1")
    for digit, tab in enumerate(("compose", "assets", "plot", "pens", "settings"), 1):
        ui.keyboard.press(str(digit))
        assert ui.locator(f'#tabs button[data-tab="{tab}"]').get_attribute("class") == "on"
    assert not ui.errors


def test_tab_shortcuts_respect_field_tool_and_modal_focus(ui):
    ui.locator("#gen-select").focus()
    ui.keyboard.press("2")
    assert ui.locator('#tabs button[data-tab="compose"]').get_attribute("class") == "on"
    ui.locator('button[data-tool="shape"]').click()
    ui.keyboard.press("2")
    assert ui.locator('#tabs button[data-tab="compose"]').get_attribute("class") == "on"
    ui.locator('button[data-tool="select"]').click()
    ui.click("#gen-browse")
    ui.get_by_role("dialog", name="Generators").wait_for(state="visible")
    ui.keyboard.press("2")
    assert ui.locator('#tabs button[data-tab="compose"]').get_attribute("class") == "on"
    assert not ui.errors
