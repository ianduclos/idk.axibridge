"""The Hand effect in the real UI: the form lists library hands by name."""

from test_acceptance_ui import (_get, add_layer, canvas_ink, frontend_mode,  # noqa: F401
                                select_layer, server, ui, wait_for_ink)

PEN = {"subpaths": [{"anchors": [{"x": 20, "y": 40}, {"x": 70, "y": 15},
                                 {"x": 130, "y": 45}, {"x": 180, "y": 20}]}]}


def _hand_select(page):
    field = page.locator("#fx-steps .field").filter(
        has=page.locator("label span", has_text="Hand"))
    return field.locator("select")


def test_hand_dropdown_shows_labels(ui):
    layer_id = add_layer(ui, "pen", PEN)
    select_layer(ui)
    before = wait_for_ink(ui)
    ui.select_option("#fx-select", "hand")
    ui.click("#fx-add")
    ui.wait_for_selector("#fx-steps .step", timeout=20_000)
    ui.wait_for_function(
        "([sel, old]) => Array.from(document.querySelectorAll(sel))"
        ".map(e => e.getAttribute('d') || '').join('|') !== old",
        arg=["#canvas path", before], timeout=20_000)
    # the list arrives from the library: more than the one placeholder option
    ui.wait_for_function(
        "() => [...document.querySelectorAll('#fx-steps .field select')]"
        ".some(s => s.options.length > 10)", timeout=20_000)
    sel = _hand_select(ui)
    assert sel.count() == 1
    value = sel.input_value()
    text = sel.locator("option:checked").text_content()
    assert value == "matisse"
    assert text != value and (" " in text or text != text.lower())
    options = sel.locator("option").evaluate_all(
        "els => els.map(e => [e.value, e.textContent])")
    assert all(v.islower() or "_" in v for v, _ in options)

    hand_ink = canvas_ink(ui)
    other = next(v for v, _ in options if v != "matisse")
    sel.select_option(other)
    ui.wait_for_function(
        "([sel, old]) => Array.from(document.querySelectorAll(sel))"
        ".map(e => e.getAttribute('d') || '').join('|') !== old",
        arg=["#canvas path", hand_ink], timeout=20_000)
    layer = next(l for l in _get(f"{ui.base}/api/project")["layers"] if l["id"] == layer_id)
    params = layer["effects"][0]["params"]
    assert params["hand"] == other
    assert params["pin"].startswith(f"{other}@")
    assert not ui.errors


def test_hand_field_falls_back_to_text_when_the_library_list_fails(ui):
    ui.route("**/api/gesture-studies", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"detail":"down"}'))
    add_layer(ui, "pen", PEN)
    select_layer(ui)
    ui.select_option("#fx-select", "hand")
    ui.click("#fx-add")
    ui.wait_for_selector("#fx-steps .step", timeout=20_000)
    field = ui.locator("#fx-steps .field").filter(
        has=ui.locator("label span", has_text="Hand"))
    field.locator('input[type="text"]').wait_for(state="visible", timeout=20_000)
    assert field.locator('input[type="text"]').input_value() == "matisse"
    assert field.locator("select").count() == 0
