"""Live sync, as the user sees it: a change made outside the window (the MCP,
another window, a script) shows up without a reload — but never yanks the
canvas out from under a gesture in progress."""

import pytest

from test_acceptance_ui import (_post, add_layer, frontend_mode, rows, select_layer,  # noqa: F401
                                server, ui)

POLY = {"sides": 5, "radius": 20}
ROWS_ARE = "n => document.querySelectorAll('#layer-list .layer-row').length === n"


def test_a_layer_added_elsewhere_appears_without_reload(ui):
    assert rows(ui) == 0
    add_layer(ui, "polygon", POLY)
    ui.wait_for_function(ROWS_ARE, arg=1, timeout=10_000)
    assert not ui.errors


def test_an_undo_made_elsewhere_shows_up(ui):
    add_layer(ui, "polygon", POLY)
    ui.wait_for_function(ROWS_ARE, arg=1, timeout=10_000)
    _post(f"{ui.base}/api/undo")
    ui.wait_for_function(ROWS_ARE, arg=0, timeout=10_000)
    assert not ui.errors


def test_the_refresh_waits_while_the_pointer_is_held(ui):
    box = ui.locator("#layer-list").bounding_box()
    ui.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] - 4)
    ui.mouse.down()
    add_layer(ui, "polygon", POLY)
    ui.wait_for_timeout(1200)
    assert rows(ui) == 0, "refetched mid-gesture"
    ui.mouse.up()
    ui.wait_for_function(ROWS_ARE, arg=1, timeout=10_000)
    assert not ui.errors


# A native context menu (WKWebView / Chrome on macOS) can swallow pointerup.
# Each of these stands in for "the gesture is over" without a pointerup ever
# arriving; live sync must not stay stalled behind a latched press.
SWALLOWED_POINTERUP = {
    "contextmenu": "window.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true}))",
    "window blur": "window.dispatchEvent(new Event('blur'))",
    "buttonless move": "document.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, buttons: 0}))",
}


@pytest.mark.parametrize("release", list(SWALLOWED_POINTERUP))
def test_a_swallowed_pointerup_does_not_stall_the_refresh(ui, release):
    box = ui.locator("#layer-list").bounding_box()
    ui.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] - 4)
    ui.mouse.down()
    add_layer(ui, "polygon", POLY)
    ui.wait_for_timeout(800)
    assert rows(ui) == 0, "refetched mid-gesture"
    ui.evaluate(SWALLOWED_POINTERUP[release])  # the press ends; no pointerup follows
    ui.wait_for_function(ROWS_ARE, arg=1, timeout=10_000)
    assert not ui.errors


def test_the_refresh_waits_while_typing_in_a_field(ui):
    add_layer(ui, "polygon", POLY)
    ui.wait_for_function(ROWS_ARE, arg=1, timeout=10_000)
    select_layer(ui)
    field = ui.locator("#tf-x")
    field.click()
    field.press("End")
    field.type("1")  # mid-edit, nothing committed yet
    add_layer(ui, "polygon", POLY)
    ui.wait_for_timeout(1200)
    assert rows(ui) == 1, "refetched while a field was being typed in"
    assert ui.evaluate("document.activeElement && document.activeElement.id") == "tf-x"
    field.blur()
    ui.wait_for_function(ROWS_ARE, arg=2, timeout=10_000)
    assert not ui.errors
