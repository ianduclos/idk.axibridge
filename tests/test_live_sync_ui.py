"""Live sync, as the user sees it: a change made outside the window (the MCP,
another window, a script) shows up without a reload — but never yanks the
canvas out from under a gesture in progress."""

from test_acceptance_ui import _post, add_layer, frontend_mode, rows, server, ui  # noqa: F401

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
