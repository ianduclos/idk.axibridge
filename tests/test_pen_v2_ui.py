"""Browser tests for pen v2: the on-canvas overlay (constant screen size,
point shape shows the point type)."""
import math
import time

from test_acceptance_ui import _get, frontend_mode, server, ui
from test_drawing_tool_completion import _canvas_point, _pen_anchor


def _zoom(page, pct):
    """Set the zoom through the readout box, the way a user types it."""
    page.fill("#zoom-pct", str(pct))
    page.press("#zoom-pct", "Enter")
    page.wait_for_function(
        f"() => Math.abs(Number(document.getElementById('zoom-pct').value) - {pct}) <= 1")


def _draw_three_anchor_path(page):
    """click, drag, click — then reselect the committed layer with the pen
    tool so its anchors and arms are on the overlay."""
    page.click('#tool-toggle button[data-tool="pen"]')
    _pen_anchor(page, -30, 0)
    x, y = _canvas_point(page, 0, 0)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y - 12)
    page.mouse.move(x, y - 25)
    page.mouse.up()
    _pen_anchor(page, 30, 0)
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.querySelector('#tool-toggle [data-tool=select]').classList.contains('on')")
    page.wait_for_function(
        "() => document.querySelectorAll('#layer-list .layer-row.selected').length === 1")
    page.click('#tool-toggle button[data-tool="pen"]')
    page.wait_for_function("() => document.querySelectorAll('.pen-anchor').length === 3")


def _width(page, selector):
    return page.evaluate(
        f"() => document.querySelector({selector!r}).getBoundingClientRect().width")


def _out_arm(page):
    a = _get(f"{page.base}/api/project")["layers"][0]["source"]["params"]["subpaths"][0]["anchors"][1]
    return a["out_handle"]


def test_points_keep_screen_size_across_zoom(ui):
    _draw_three_anchor_path(ui)

    sizes = {}
    for pct in (None, 800, 25):
        if pct is not None:
            _zoom(ui, pct)
        sizes[pct] = (_width(ui, ".pen-anchor"), _width(ui, ".pen-handle-knob"))
    base_anchor, base_knob = sizes[None]
    assert abs(base_anchor - 7) <= 1, sizes
    for anchor_w, knob_w in sizes.values():
        assert abs(anchor_w - base_anchor) <= 1, sizes
        assert abs(knob_w - base_knob) <= 1, sizes

    # zoomed far in, the knob is still where the pointer can grab it: an
    # ⌥-drag on the out arm's knob lengthens the arm
    _zoom(ui, 800)
    before = _out_arm(ui)
    knob = ui.evaluate("""() => {
        const ks = [...document.querySelectorAll('.pen-handle-knob')]
          .map((k) => k.getBoundingClientRect())
          .map((r) => ({ x: r.x + r.width / 2, y: r.y + r.height / 2 }));
        ks.sort((a, b) => a.y - b.y);
        return ks[0];
    }""")  # the out arm points up (drawn by dragging upward)
    wrap = ui.locator("#canvas-wrap").bounding_box()
    assert wrap["x"] < knob["x"] < wrap["x"] + wrap["width"]
    assert wrap["y"] < knob["y"] < wrap["y"] + wrap["height"]
    ui.keyboard.down("Alt")
    ui.mouse.move(knob["x"], knob["y"])
    ui.mouse.down()
    ui.mouse.move(knob["x"], knob["y"] - 20)
    ui.mouse.move(knob["x"], knob["y"] - 40)
    ui.mouse.up()
    ui.keyboard.up("Alt")

    deadline = time.time() + 5
    after = _out_arm(ui)
    while math.hypot(*after) <= math.hypot(*before) + 0.5 and time.time() < deadline:
        time.sleep(0.1)
        after = _out_arm(ui)
    assert math.hypot(*after) > math.hypot(*before) + 0.5, (before, after)
    assert not ui.errors


def test_corner_is_square_smooth_is_round(ui):
    _draw_three_anchor_path(ui)
    assert ui.locator("rect.pen-anchor.corner").count() == 2
    assert ui.locator("circle.pen-anchor.symmetric").count() == 1
    assert ui.locator("circle.pen-anchor").count() == 1
    assert not ui.errors
