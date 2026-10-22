"""Browser tests for pen v2: the on-canvas overlay (constant screen size,
point shape shows the point type)."""
import math
import time

import pytest

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


# ---------------------------------------------------------------- editing gestures (E1–E6)

def _layer(page):
    return _get(f"{page.base}/api/project")["layers"][0]


def _subpaths(page):
    return _layer(page)["source"]["params"]["subpaths"]


def _wait_api(page, pred, what, timeout=8.0):
    """Poll the project until `pred(subpaths)` holds — committed edits land
    through an async regenerate."""
    def ok(sps):
        try:
            return sps is not None and pred(sps)
        except (IndexError, KeyError):
            return False

    def read():
        layers = _get(f"{page.base}/api/project")["layers"]
        return layers[0]["source"]["params"]["subpaths"] if layers else None

    deadline = time.time() + timeout
    sps = read()
    while not ok(sps) and time.time() < deadline:
        time.sleep(0.1)
        sps = read()
    assert ok(sps), (what, sps)
    return sps


def _mm_to_screen(page, x, y):
    return page.evaluate("""([x, y]) => {
        const world = document.querySelector('.pen-overlay').parentNode;
        const p = document.getElementById('canvas').createSVGPoint();
        p.x = x; p.y = y;
        const s = p.matrixTransform(world.getScreenCTM());
        return [s.x, s.y];
    }""", [x, y])


def _bez(sp, k, t):
    """Point at parameter t of segment k (mm), the same cubic pen.py flattens."""
    A = sp["anchors"]
    a, b = A[k], A[(k + 1) % len(A)]
    p0 = (a["x"], a["y"])
    p1 = (a["x"] + a["out_handle"][0], a["y"] + a["out_handle"][1]) if a["out_handle"] else p0
    p3 = (b["x"], b["y"])
    p2 = (b["x"] + b["in_handle"][0], b["y"] + b["in_handle"][1]) if b["in_handle"] else p3
    u = 1 - t
    w = (u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t)
    return (sum(wi * p[0] for wi, p in zip(w, (p0, p1, p2, p3))),
            sum(wi * p[1] for wi, p in zip(w, (p0, p1, p2, p3))))


def _anchor_screen(page, si, ai):
    a = _subpaths(page)[si]["anchors"][ai]
    return _mm_to_screen(page, a["x"], a["y"])


def _resolved_points(page):
    layer = _get(f"{page.base}/api/compose/resolved?stats=false")["layers"][0]
    return [pt for p in layer["paths"] for pt in p["points"]]


def _dist_to_polyline(p, pts):
    best = math.inf
    for a, b in zip(pts, pts[1:]):
        ab = (b[0] - a[0], b[1] - a[1])
        L2 = ab[0] ** 2 + ab[1] ** 2
        s = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / L2))
        q = (a[0] + ab[0] * s, a[1] + ab[1] * s)
        best = min(best, math.hypot(p[0] - q[0], p[1] - q[1]))
    return best


def _approx(v):
    return pytest.approx(v, abs=1e-6)


def _undo(page):
    page.click('.menu[data-menu="edit"] .menu-trigger')
    page.click("#btn-undo")


def _pen_active(page):
    return "on" in (page.locator('#tool-toggle button[data-tool="pen"]').get_attribute("class") or "")


def _reselect_pen(page, anchors):
    page.wait_for_function(
        "() => document.querySelector('#tool-toggle [data-tool=select]').classList.contains('on')")
    page.wait_for_function(
        "() => document.querySelectorAll('#layer-list .layer-row.selected').length === 1")
    page.click('#tool-toggle button[data-tool="pen"]')
    page.wait_for_function(f"() => document.querySelectorAll('.pen-anchor').length === {anchors}")


def test_click_on_line_adds_point_without_moving_it(ui):
    _draw_three_anchor_path(ui)
    before_pts = _resolved_points(ui)
    sp = _subpaths(ui)[0]
    mid = _bez(sp, 1, 0.5)  # the curved segment from the middle anchor
    ui.mouse.click(*_mm_to_screen(ui, *mid))

    sps = _wait_api(ui, lambda s: len(s[0]["anchors"]) == 4, "a fourth anchor")
    added = sps[0]["anchors"][2]
    assert math.hypot(added["x"] - mid[0], added["y"] - mid[1]) < 0.3, (added, mid)
    deadline = time.time() + 5
    after_pts = _resolved_points(ui)
    while after_pts == before_pts and time.time() < deadline:
        time.sleep(0.1)
        after_pts = _resolved_points(ui)
    assert after_pts != before_pts  # the layer was regenerated
    assert max(_dist_to_polyline(p, before_pts) for p in after_pts) <= 0.05
    assert max(_dist_to_polyline(p, after_pts) for p in before_pts) <= 0.05
    assert len(_get(f"{ui.base}/api/project")["layers"]) == 1
    assert _pen_active(ui)  # an edit, not a new drawing: the tool stays
    assert not ui.errors


def test_double_click_flips_corner_and_smooth(ui):
    _draw_three_anchor_path(ui)
    # the middle anchor was dragged out: symmetric → double-click → corner
    ui.mouse.dblclick(*_anchor_screen(ui, 0, 1))
    _wait_api(ui, lambda s: s[0]["anchors"][1].get("join") == "corner", "middle is a corner")
    ui.wait_for_function("() => document.querySelectorAll('rect.pen-anchor.corner').length === 3")
    assert len(_subpaths(ui)[0]["anchors"]) == 3  # flipping never adds a point

    # corner → smooth: arms from the neighbours, tangent ∥ next − prev, a
    # third of each side's chord
    ui.mouse.dblclick(*_anchor_screen(ui, 0, 1))
    sps = _wait_api(ui, lambda s: s[0]["anchors"][1].get("join") == "smooth", "middle is smooth")
    p, a, n = sps[0]["anchors"]
    tan = (n["x"] - p["x"], n["y"] - p["y"])
    tl = math.hypot(*tan)
    lo = math.hypot(n["x"] - a["x"], n["y"] - a["y"]) / 3
    li = math.hypot(p["x"] - a["x"], p["y"] - a["y"]) / 3
    assert a["out_handle"] == [_approx(tan[0] / tl * lo), _approx(tan[1] / tl * lo)]
    assert a["in_handle"] == [_approx(-tan[0] / tl * li), _approx(-tan[1] / tl * li)]

    # an open end gets one arm, along its chord
    ui.mouse.dblclick(*_anchor_screen(ui, 0, 0))
    sps = _wait_api(ui, lambda s: s[0]["anchors"][0].get("join") == "smooth", "first is smooth")
    f, s1 = sps[0]["anchors"][0], sps[0]["anchors"][1]
    assert f["in_handle"] is None
    assert f["out_handle"] == [_approx((s1["x"] - f["x"]) / 3), _approx((s1["y"] - f["y"]) / 3)]
    assert ui.locator(".pen-pending-anchor").count() == 0  # no continue left armed

    # a double-click on a LINE adds one point (the first click), never two.
    # Zoomed in, so the line's middle is clear of the arm knobs (a knob
    # under the pointer wins over the line, by design)
    _zoom(ui, 400)
    ui.mouse.dblclick(*_mm_to_screen(ui, *_bez(sps[0], 1, 0.5)))
    _wait_api(ui, lambda s: len(s[0]["anchors"]) == 4, "one point added")
    time.sleep(0.5)
    assert len(_subpaths(ui)[0]["anchors"]) == 4
    assert not ui.errors


def test_drag_on_line_bends_it_one_undo(ui):
    _draw_three_anchor_path(ui)
    before = _subpaths(ui)
    grab = _mm_to_screen(ui, *_bez(before[0], 1, 0.5))
    ui.mouse.move(*grab)
    ui.mouse.down()
    for k in range(1, 9):
        ui.mouse.move(grab[0] + 2 * k, grab[1] + 5 * k)
    ui.mouse.up()

    sps = _wait_api(ui, lambda s: s != before, "the segment bent")
    deadline = time.time() + 5
    while time.time() < deadline:  # let the trailing frames land
        time.sleep(0.3)
        nxt = _subpaths(ui)
        if nxt == sps:
            break
        sps = nxt
    assert len(sps[0]["anchors"]) == 3  # a bend, never an insert
    geom = lambda a: (a["x"], a["y"], a["in_handle"], a["out_handle"])
    assert geom(sps[0]["anchors"][0]) == geom(before[0]["anchors"][0])  # outside the segment: untouched
    assert (sps[0]["anchors"][1]["x"], sps[0]["anchors"][1]["y"]) == (
        before[0]["anchors"][1]["x"], before[0]["anchors"][1]["y"])  # anchors stay put
    new_mid = _bez(sps[0], 1, 0.5)
    old_mid = _bez(before[0], 1, 0.5)
    assert math.hypot(new_mid[0] - old_mid[0], new_mid[1] - old_mid[1]) > 1.0

    _undo(ui)
    after = _wait_api(ui, lambda s: s == before, "one undo restores the pre-bend path")
    assert after == before
    assert not ui.errors


def test_j_cycles_join_and_glyph(ui):
    _draw_three_anchor_path(ui)
    ui.mouse.click(*_anchor_screen(ui, 0, 1))
    ui.wait_for_function("() => document.querySelectorAll('.pen-selected-ring').length === 1")
    # selecting is not an edit
    assert _subpaths(ui)[0]["anchors"][1].get("join") is None

    ui.keyboard.press("j")  # symmetric → corner
    _wait_api(ui, lambda s: s[0]["anchors"][1].get("join") == "corner", "corner")
    ui.wait_for_function("() => document.querySelectorAll('rect.pen-anchor.corner').length === 3")

    ui.keyboard.press("j")  # corner → smooth
    _wait_api(ui, lambda s: s[0]["anchors"][1].get("join") == "smooth", "smooth")
    ui.wait_for_function("() => document.querySelectorAll('circle.pen-anchor.smooth').length === 1")

    ui.keyboard.press("j")  # smooth → symmetric: arms re-mirrored to match
    sps = _wait_api(ui, lambda s: s[0]["anchors"][1].get("join") == "symmetric", "symmetric")
    ui.wait_for_function("() => document.querySelectorAll('circle.pen-anchor.symmetric').length === 1")
    a = sps[0]["anchors"][1]
    assert a["in_handle"] == [_approx(-a["out_handle"][0]), _approx(-a["out_handle"][1])]
    assert ui.locator(".pen-selected-ring").count() == 1

    ui.keyboard.press("Escape")  # Escape clears the selection (and leaves the tool)
    assert ui.locator(".pen-selected-ring").count() == 0
    assert not ui.errors


def test_delete_point_refits_and_last_points_remove_subpath(ui):
    _draw_three_anchor_path(ui)
    ui.mouse.click(*_anchor_screen(ui, 0, 1))
    ui.wait_for_function("() => document.querySelectorAll('.pen-selected-ring').length === 1")
    ui.keyboard.press("Backspace")
    sps = _wait_api(ui, lambda s: len(s[0]["anchors"]) == 2, "the middle point is gone")
    first, last = sps[0]["anchors"]
    # refit: the two remaining points carry arms so the curve stays close
    assert first["out_handle"] is not None and last["in_handle"] is not None
    assert len(_get(f"{ui.base}/api/project")["layers"]) == 1  # never the layer-delete shortcut
    assert _pen_active(ui)
    ui.wait_for_function("() => document.querySelectorAll('.pen-anchor').length === 2")

    ui.mouse.click(*_anchor_screen(ui, 0, 1))
    ui.wait_for_function("() => document.querySelectorAll('.pen-selected-ring').length === 1")
    ui.keyboard.press("Delete")
    _wait_api(ui, lambda s: s == [], "a one-point subpath is removed")
    layers = _get(f"{ui.base}/api/project")["layers"]
    assert len(layers) == 1 and layers[0]["source"]["generator"] == "pen"  # empty pen layer stays
    assert not ui.errors


def test_continue_open_line_from_its_end(ui):
    _draw_three_anchor_path(ui)
    before = _subpaths(ui)[0]["anchors"]
    ui.mouse.click(*_anchor_screen(ui, 0, 2))   # the end
    _pen_anchor(ui, 70, 30)
    ui.keyboard.press("Enter")
    sps = _wait_api(ui, lambda s: len(s[0]["anchors"]) == 4, "appended at the end")
    assert len(sps) == 1
    assert sps[0]["anchors"][:2] == before[:2]
    assert (sps[0]["anchors"][2]["x"], sps[0]["anchors"][2]["y"]) == (before[2]["x"], before[2]["y"])

    _reselect_pen(ui, 4)
    end_mm = (sps[0]["anchors"][3]["x"], sps[0]["anchors"][3]["y"])
    ui.mouse.click(*_anchor_screen(ui, 0, 0))   # the start: prepends
    _pen_anchor(ui, -70, 30)
    ui.keyboard.press("Enter")
    sps = _wait_api(ui, lambda s: len(s[0]["anchors"]) == 5, "prepended at the start")
    assert len(sps) == 1 and not sps[0]["closed"]
    assert (sps[0]["anchors"][1]["x"], sps[0]["anchors"][1]["y"]) == (before[0]["x"], before[0]["y"])
    assert (sps[0]["anchors"][4]["x"], sps[0]["anchors"][4]["y"]) == end_mm
    assert (sps[0]["anchors"][0]["x"], sps[0]["anchors"][0]["y"]) != (before[0]["x"], before[0]["y"])

    # joining a line's own other end closes it
    _reselect_pen(ui, 5)
    ui.mouse.click(*_anchor_screen(ui, 0, 4))
    ui.mouse.click(*_anchor_screen(ui, 0, 0))
    sps = _wait_api(ui, lambda s: s[0]["closed"], "closed by its own ends")
    assert len(sps) == 1 and len(sps[0]["anchors"]) == 5
    assert len(_get(f"{ui.base}/api/project")["layers"]) == 1
    assert not ui.errors


def test_join_two_open_lines(ui):
    ui.click('#tool-toggle button[data-tool="pen"]')
    _pen_anchor(ui, -80, -40)
    _pen_anchor(ui, -20, -40)
    ui.keyboard.press("Enter")
    ui.wait_for_function(
        "() => document.querySelectorAll('#layer-list .layer-row.selected').length === 1")
    ui.click('#tool-toggle button[data-tool="pen"]')
    ui.wait_for_function("() => document.querySelectorAll('.pen-anchor').length === 2")
    _pen_anchor(ui, 20, 40)
    _pen_anchor(ui, 80, 40)
    ui.keyboard.press("Enter")
    two = _wait_api(ui, lambda s: len(s) == 2, "two lines in one layer")
    _reselect_pen(ui, 4)

    ui.mouse.click(*_anchor_screen(ui, 0, 1))   # continue line 1 from its end…
    ui.mouse.click(*_anchor_screen(ui, 1, 0))   # …into line 2's start
    sps = _wait_api(ui, lambda s: len(s) == 1, "joined into one line")
    got = [(round(a["x"], 3), round(a["y"], 3)) for a in sps[0]["anchors"]]
    want = [(round(a["x"], 3), round(a["y"], 3)) for sp in two for a in sp["anchors"]]
    assert got in (want, want[::-1]), (got, want)  # A → B → C → D, nothing merged away
    assert not sps[0]["closed"]
    assert len(_get(f"{ui.base}/api/project")["layers"]) == 1
    assert not ui.errors


# ---------------------------------------------------------------- fix round 1

def _settled(page, what, timeout=8.0):
    """Wait until the project stops changing (queued edits have all landed)."""
    deadline = time.time() + timeout
    last = _subpaths(page)
    while time.time() < deadline:
        time.sleep(0.4)
        cur = _subpaths(page)
        if cur == last:
            return cur
        last = cur
    raise AssertionError(f"{what}: never settled")


def _slow_network(page, project_ms=300, regen_ms=200):
    """Delay the project refresh and every regenerate in the page's own
    fetch, so key presses land while an earlier edit's refresh is in flight —
    the window where a refresh could swap stale state in under a newer edit."""
    page.evaluate("""([pm, rm]) => {
        const orig = window.fetch;
        const wait = (ms) => new Promise((r) => setTimeout(r, ms));
        window.fetch = async (url, opts) => {
            const u = String(url), get = !opts || !opts.method || opts.method === 'GET';
            if (get && /\/api\/project$/.test(u)) await wait(pm);
            if (u.includes('/regenerate')) await wait(rm);
            return orig(url, opts);
        };
    }""", [project_ms, regen_ms])


def test_rapid_j_presses_all_land(ui):
    _draw_three_anchor_path(ui)
    ui.mouse.click(*_anchor_screen(ui, 0, 1))
    ui.wait_for_function("() => document.querySelectorAll('.pen-selected-ring').length === 1")
    for _ in range(4):  # symmetric → corner → smooth → symmetric → corner, no waiting
        ui.keyboard.press("j")
    _wait_api(ui, lambda s: s[0]["anchors"][1].get("join") == "corner", "four presses land on corner")
    sps = _settled(ui, "J run")
    assert sps[0]["anchors"][1]["join"] == "corner"
    ui.wait_for_function("() => document.querySelectorAll('rect.pen-anchor.corner').length === 3")

    # presses spaced to land inside the previous edit's refresh: four more
    # (corner → smooth → symmetric → corner → smooth), every one counted
    _slow_network(ui)
    for _ in range(4):
        ui.keyboard.press("j")
        ui.wait_for_timeout(300)
    _wait_api(ui, lambda s: s[0]["anchors"][1].get("join") == "smooth", "slow presses land on smooth")
    sps = _settled(ui, "slow J run")
    assert sps[0]["anchors"][1]["join"] == "smooth", sps
    ui.wait_for_function("() => document.querySelectorAll('circle.pen-anchor.smooth').length === 1")
    # an edit landing while a repaint is still being read cancels that read
    # by design (409 render_cancelled, handled silently by main.js); the
    # browser still logs the status line — anything else is a real error
    assert not [e for e in ui.errors if "status of 409" not in e]


def test_two_bends_are_two_undo_steps(ui):
    _draw_three_anchor_path(ui)
    _zoom(ui, 300)
    before = _subpaths(ui)

    def bend(dx):
        grab = _mm_to_screen(ui, *_bez(_subpaths(ui)[0], 1, 0.5))
        ui.mouse.move(*grab)
        ui.mouse.down()
        for k in range(1, 7):
            ui.mouse.move(grab[0] + dx * k, grab[1])
        ui.mouse.up()

    bend(5)
    first = _wait_api(ui, lambda s: s != before, "first bend")
    first = _settled(ui, "first bend")
    bend(-5)
    _wait_api(ui, lambda s: s != first, "second bend")
    _settled(ui, "second bend")

    _undo(ui)
    _wait_api(ui, lambda s: s == first, "one undo takes back only the second bend")
    _undo(ui)
    _wait_api(ui, lambda s: s == before, "a second undo takes back the first")
    assert not ui.errors


def test_cmd_z_under_the_pen(ui):
    _draw_three_anchor_path(ui)
    _zoom(ui, 300)
    ui.mouse.click(*_mm_to_screen(ui, *_bez(_subpaths(ui)[0], 1, 0.5)))
    _wait_api(ui, lambda s: len(s[0]["anchors"]) == 4, "inserted")
    _settled(ui, "insert")
    ui.keyboard.press("Meta+z")
    _wait_api(ui, lambda s: len(s[0]["anchors"]) == 3, "⌘Z undid the insert")
    assert _pen_active(ui)
    ui.keyboard.press("Meta+Shift+z")
    _wait_api(ui, lambda s: len(s[0]["anchors"]) == 4, "⇧⌘Z redid it")

    # while placing, ⌘Z drops the last placed point — and ⌘Backspace is not
    # a plain Backspace
    _pen_anchor(ui, -200, -150)
    _pen_anchor(ui, -150, -150)
    _pen_anchor(ui, -100, -150)
    ui.wait_for_function("() => document.querySelectorAll('.pen-pending-anchor').length === 3")
    ui.keyboard.press("Meta+Backspace")
    time.sleep(0.2)
    assert ui.locator(".pen-pending-anchor").count() == 3
    ui.keyboard.press("Meta+z")
    ui.wait_for_function("() => document.querySelectorAll('.pen-pending-anchor').length === 2")
    assert len(_subpaths(ui)[0]["anchors"]) == 4  # the layer was not undone
    ui.keyboard.press("Escape")

    # continuing: ⌘Z drops placed points but never the line's own end
    _reselect_pen(ui, 4)
    ui.mouse.click(*_anchor_screen(ui, 0, 3))
    _pen_anchor(ui, 120, 100)
    ui.wait_for_function("() => document.querySelectorAll('.pen-pending-anchor').length === 2")
    ui.keyboard.press("Meta+z")
    ui.wait_for_function("() => document.querySelectorAll('.pen-pending-anchor').length === 1")
    assert len(_subpaths(ui)[0]["anchors"]) == 4
    assert not ui.errors


def test_deselecting_the_layer_drops_the_point_selection(ui):
    _draw_three_anchor_path(ui)
    ui.mouse.click(*_anchor_screen(ui, 0, 1))
    ui.wait_for_function("() => document.querySelectorAll('.pen-selected-ring').length === 1")
    ui.locator("#layer-list .layer-row.selected .lname").click(modifiers=["Meta"])  # ⌘-click: deselect
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row.selected').length === 0")
    ui.wait_for_function("() => document.querySelectorAll('.pen-selected-ring').length === 0")
    ui.keyboard.press("j")
    ui.keyboard.press("Backspace")
    time.sleep(0.5)
    a = _subpaths(ui)[0]["anchors"]
    assert len(a) == 3 and a[1].get("join") is None
    assert len(_get(f"{ui.base}/api/project")["layers"]) == 1
    assert not ui.errors


def test_deleting_an_open_end_leaves_the_far_end_alone(ui):
    _draw_three_anchor_path(ui)
    ui.mouse.click(*_anchor_screen(ui, 0, 0))
    ui.wait_for_function("() => document.querySelectorAll('.pen-selected-ring').length === 1")
    ui.keyboard.press("Backspace")
    sps = _wait_api(ui, lambda s: len(s[0]["anchors"]) == 2, "first point gone")
    assert sps[0]["anchors"][1].get("join") is None  # untouched: no join written
    assert not ui.errors


def test_a_two_point_line_does_not_close_on_itself(ui):
    ui.click('#tool-toggle button[data-tool="pen"]')
    _pen_anchor(ui, -40, 0)
    _pen_anchor(ui, 40, 0)
    ui.keyboard.press("Enter")
    _reselect_pen(ui, 2)
    before = _subpaths(ui)
    ui.mouse.click(*_anchor_screen(ui, 0, 1))
    ui.mouse.click(*_anchor_screen(ui, 0, 0))
    time.sleep(0.6)
    sps = _subpaths(ui)
    assert not sps[0]["closed"] and len(sps[0]["anchors"]) == 2
    assert [(a["x"], a["y"]) for a in sps[0]["anchors"]] == [(a["x"], a["y"]) for a in before[0]["anchors"]]
    assert not ui.errors


def test_join_into_an_earlier_line_keeps_the_others(ui):
    ui.click('#tool-toggle button[data-tool="pen"]')
    lines = [((-90, -60), (-30, -60)), ((-90, 0), (-30, 0)), ((30, 60), (90, 60))]
    for i, (p, q) in enumerate(lines):
        if i:
            ui.click('#tool-toggle button[data-tool="pen"]')
            ui.wait_for_function(f"() => document.querySelectorAll('.pen-anchor').length === {2 * i}")
        _pen_anchor(ui, *p)
        _pen_anchor(ui, *q)
        ui.keyboard.press("Enter")
        _wait_api(ui, lambda s, n=i + 1: len(s) == n, f"{i + 1} lines")
        ui.wait_for_function(
            "() => document.querySelector('#tool-toggle [data-tool=select]').classList.contains('on')")
    three = _subpaths(ui)
    _reselect_pen(ui, 6)

    ui.mouse.click(*_anchor_screen(ui, 2, 0))   # continue line 3 from its start…
    ui.mouse.click(*_anchor_screen(ui, 0, 1))   # …into line 1's end
    sps = _wait_api(ui, lambda s: len(s) == 2, "lines 1 and 3 joined")
    assert sps[1] == three[1] or [(a["x"], a["y"]) for a in sps[1]["anchors"]] == \
        [(a["x"], a["y"]) for a in three[1]["anchors"]]  # line 2 untouched
    got = [(round(a["x"], 3), round(a["y"], 3)) for a in sps[0]["anchors"]]
    want = [(round(a["x"], 3), round(a["y"], 3)) for a in three[0]["anchors"] + three[2]["anchors"]]
    assert got in (want, want[::-1]), (got, want)
    assert not ui.errors


# ---------------------------------------------------------------- stale sync

def _ink_signature(page):
    return page.evaluate("""() => [...document.querySelectorAll('#canvas path')]
        .filter((p) => !p.closest('.pen-overlay'))
        .map((p) => p.getAttribute('d')).join('|')""")


def test_ink_syncs_when_a_gesture_ends_during_a_regenerate(ui):
    _draw_three_anchor_path(ui)
    time.sleep(0.5)
    before = _ink_signature(ui)
    _slow_network(ui, project_ms=0, regen_ms=800)
    ui.mouse.click(*_anchor_screen(ui, 0, 1))
    ui.wait_for_function("() => document.querySelectorAll('.pen-selected-ring').length === 1")
    ui.keyboard.press("Delete")
    time.sleep(0.2)  # the regenerate is in flight...
    ui.mouse.move(*_canvas_point(ui, -100, -80))
    ui.mouse.down()  # ...a gesture is held while it lands, so the drain parks
    time.sleep(1.2)
    ui.mouse.up()    # and only the gesture's end can run the owed sync
    _wait_api(ui, lambda s: len(s[0]["anchors"]) == 2, "the point is gone")
    deadline = time.time() + 6
    while _ink_signature(ui) == before and time.time() < deadline:
        time.sleep(0.1)
    assert _ink_signature(ui) != before, "the ink never caught up with the edit"
    assert not ui.errors


# ---------------------------------------------------------------- placement aids (P4, P5)

def _mm_mapper(page):
    """screen px -> mm from the bed rectangle. The view may be portrait
    (display-only rotate(90), origin top-right), so read it off the rect."""
    x, y, w, h = page.evaluate("""() => { const b = document.querySelector('.bed-rect').getBoundingClientRect();
        return [b.x, b.y, b.width, b.height]; }""")
    if h > w:
        k = h / 300
        return lambda sx, sy: ((sy - y) / k, (x + w - sx) / k)
    k = w / 300
    return lambda sx, sy: ((sx - x) / k, (sy - y) / k)


def _angle_deg(dx, dy):
    return math.degrees(math.atan2(dy, dx))


def _is_15(deg):
    return abs(deg / 15 - round(deg / 15)) * 15 < 1e-6


def test_space_slides_anchor_while_placing(ui):
    ui.click('#tool-toggle button[data-tool="pen"]')
    _pen_anchor(ui, -60, 0)
    ax, ay = _canvas_point(ui, 0, 0)
    bx, by = ax, ay - 40           # the arm is pulled up 40 px
    cx, cy = ax + 70, by + 25      # then Space carries the whole point
    ui.mouse.move(ax, ay)
    ui.mouse.down()
    ui.mouse.move(bx, by - 10)
    ui.mouse.move(bx, by)
    ui.keyboard.down("Space")
    ui.mouse.move(bx + 30, by + 10)
    ui.mouse.move(cx, cy)
    ui.keyboard.up("Space")
    ui.mouse.up()
    assert ui.evaluate("() => window.scrollY") == 0
    to_mm = _mm_mapper(ui)
    ui.keyboard.press("Enter")
    sps = _wait_api(ui, lambda s: len(s[0]["anchors"]) == 2, "committed")
    a = sps[0]["anchors"][1]
    want = to_mm(ax + (cx - bx), ay + (cy - by))
    assert (a["x"], a["y"]) == (pytest.approx(want[0], abs=0.05), pytest.approx(want[1], abs=0.05))
    arm = to_mm(bx, by)
    o = to_mm(ax, ay)
    assert a["out_handle"] == [pytest.approx(arm[0] - o[0], abs=0.05),
                               pytest.approx(arm[1] - o[1], abs=0.05)]
    assert not ui.errors


def test_arm_pulls_again_after_space_is_released(ui):
    ui.click('#tool-toggle button[data-tool="pen"]')
    _pen_anchor(ui, -60, 0)
    ax, ay = _canvas_point(ui, 0, 0)
    ui.mouse.move(ax, ay)
    ui.mouse.down()
    ui.mouse.move(ax, ay - 20)
    ui.keyboard.down("Space")
    ui.mouse.move(ax + 40, ay + 20)   # point slides by (40, 40)
    ui.keyboard.up("Space")
    ui.mouse.move(ax + 40, ay - 10)   # arm now pulls from the moved point
    ui.mouse.up()
    to_mm = _mm_mapper(ui)
    ui.keyboard.press("Enter")
    sps = _wait_api(ui, lambda s: len(s[0]["anchors"]) == 2, "committed")
    a = sps[0]["anchors"][1]
    want = to_mm(ax + 40, ay + 40)
    assert a["x"] == pytest.approx(want[0], abs=0.05) and a["y"] == pytest.approx(want[1], abs=0.05)
    o = to_mm(ax + 40, ay + 40)
    tip = to_mm(ax + 40, ay - 10)
    assert a["out_handle"] == [pytest.approx(tip[0] - o[0], abs=0.05),
                               pytest.approx(tip[1] - o[1], abs=0.05)]


def test_shift_snaps_new_point_to_15_degrees(ui):
    ui.click('#tool-toggle button[data-tool="pen"]')
    _pen_anchor(ui, -60, 0)
    x, y = _canvas_point(ui, 50, 37)   # an off-grid direction from the first point
    ui.keyboard.down("Shift")
    ui.mouse.move(x, y)
    ui.mouse.down()
    ui.mouse.move(x + 20, y + 3)
    ui.mouse.move(x + 41, y - 13)      # an off-grid arm
    ui.mouse.up()
    ui.keyboard.up("Shift")
    to_mm = _mm_mapper(ui)
    ui.keyboard.press("Enter")
    sps = _wait_api(ui, lambda s: len(s[0]["anchors"]) == 2, "committed")
    p, q = sps[0]["anchors"]
    assert _is_15(_angle_deg(q["x"] - p["x"], q["y"] - p["y"])), (p, q)
    raw = to_mm(x, y)
    assert math.hypot(q["x"] - p["x"], q["y"] - p["y"]) == pytest.approx(
        math.hypot(raw[0] - p["x"], raw[1] - p["y"]), abs=0.05)  # length kept
    assert _is_15(_angle_deg(*q["out_handle"])), q["out_handle"]
    assert not ui.errors


def test_shift_leaves_the_first_point_in_place_and_snaps_its_arm(ui):
    ui.click('#tool-toggle button[data-tool="pen"]')
    x, y = _canvas_point(ui, -20, 10)
    ui.keyboard.down("Shift")
    ui.mouse.move(x, y)
    ui.mouse.down()
    ui.mouse.move(x + 10, y - 4)
    ui.mouse.move(x + 33, y - 11)
    ui.mouse.up()
    ui.keyboard.up("Shift")
    _pen_anchor(ui, 60, 0)
    to_mm = _mm_mapper(ui)
    ui.keyboard.press("Enter")
    sps = _wait_api(ui, lambda s: len(s[0]["anchors"]) == 2, "committed")
    first = sps[0]["anchors"][0]
    want = to_mm(x, y)
    assert first["x"] == pytest.approx(want[0], abs=0.05) and first["y"] == pytest.approx(want[1], abs=0.05)
    assert _is_15(_angle_deg(*first["out_handle"]))
