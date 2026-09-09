"""Browser regressions for one-shot Pen and Shape completion."""
from test_acceptance_ui import _get, frontend_mode, server, ui


def _canvas_point(page, dx=0, dy=0):
    box = page.locator("#canvas-wrap").bounding_box()
    return box["x"] + box["width"] / 2 + dx, box["y"] + box["height"] / 2 + dy


def _pen_anchor(page, dx, dy):
    x, y = _canvas_point(page, dx, dy)
    page.mouse.click(x, y)


def _shape_drag(page, dx=100, dy=70):
    x, y = _canvas_point(page, -60, -40)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y + dy)
    page.mouse.up()


def test_pen_enter_commits_selects_and_returns_to_select(ui):
    ui.click('#tool-toggle button[data-tool="pen"]')
    _pen_anchor(ui, -40, 0)
    _pen_anchor(ui, 40, 0)
    ui.keyboard.press("Enter")

    ui.wait_for_function("() => document.querySelector('#tool-toggle [data-tool=select]').classList.contains('on')")
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row.selected').length === 1")
    assert _get(f"{ui.base}/api/project")["layers"][0]["source"]["generator"] == "pen"
    assert not ui.errors


def test_repeat_keeps_shape_active_until_escape(ui):
    ui.click('#tool-toggle button[data-tool="shape"]')
    ui.click("#drawing-repeat")
    _shape_drag(ui)

    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row.selected').length === 1")
    assert ui.locator('#tool-toggle button[data-tool="shape"]').get_attribute("class") == "on"
    ui.keyboard.press("Escape")
    assert "on" in (ui.locator('#tool-toggle button[data-tool="select"]').get_attribute("class") or "")
    assert not ui.errors


def test_shape_defaults_to_one_shot_and_failed_commit_can_retry(ui):
    failed = {"once": False}

    def fail_first(route):
        if not failed["once"]:
            failed["once"] = True
            route.fulfill(status=500, content_type="application/json", body='{"detail":"try again"}')
        else:
            route.continue_()

    ui.route("**/api/layers/generate", fail_first)
    ui.click('#tool-toggle button[data-tool="shape"]')
    _shape_drag(ui)
    ui.wait_for_selector("#global-error:not(:empty)")
    assert ui.locator("#canvas-wrap .pen-pending-path").count() == 1
    assert "on" in (ui.locator('#tool-toggle button[data-tool="shape"]').get_attribute("class") or "")

    ui.keyboard.press("Enter")
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row.selected').length === 1")
    ui.wait_for_function("() => document.querySelector('#tool-toggle [data-tool=select]').classList.contains('on')")
    assert len(_get(f"{ui.base}/api/project")["layers"]) == 1


def test_escape_cancels_pen_trace_and_exits_in_one_press(ui):
    ui.click('#tool-toggle button[data-tool="pen"]')
    _pen_anchor(ui, -40, 0)
    _pen_anchor(ui, 40, 0)
    ui.keyboard.press("Escape")

    assert "on" in (ui.locator('#tool-toggle button[data-tool="select"]').get_attribute("class") or "")
    assert _get(f"{ui.base}/api/project")["layers"] == []
    assert not ui.errors


def test_enter_discards_a_lone_pen_anchor_and_exits(ui):
    ui.click('#tool-toggle button[data-tool="pen"]')
    _pen_anchor(ui, 0, 0)
    ui.keyboard.press("Enter")

    assert "on" in (ui.locator('#tool-toggle button[data-tool="select"]').get_attribute("class") or "")
    assert _get(f"{ui.base}/api/project")["layers"] == []


def test_tiny_shape_does_not_block_the_next_shape(ui):
    ui.click('#tool-toggle button[data-tool="shape"]')
    _shape_drag(ui, 0.1, 0.1)
    _shape_drag(ui, 100, 70)

    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row.selected').length === 1")
    assert len(_get(f"{ui.base}/api/project")["layers"]) == 1


def test_resolve_failure_after_shape_write_does_not_leave_a_duplicate_draft(ui):
    failed = {"once": False}

    def fail_first_resolve(route):
        if not failed["once"]:
            failed["once"] = True
            route.fulfill(status=500, content_type="application/json", body='{"detail":"paint failed"}')
        else:
            route.continue_()

    ui.route("**/api/compose/resolved**", fail_first_resolve)
    ui.click('#tool-toggle button[data-tool="shape"]')
    _shape_drag(ui)
    ui.wait_for_function("() => document.querySelector('#tool-toggle [data-tool=select]').classList.contains('on')")
    assert ui.locator("#canvas-wrap .pen-pending-path").count() == 0
    assert len(_get(f"{ui.base}/api/project")["layers"]) == 1


def test_failed_pen_commit_keeps_draft_for_retry(ui):
    failed = {"once": False}

    def fail_first(route):
        if not failed["once"]:
            failed["once"] = True
            route.fulfill(status=500, content_type="application/json", body='{"detail":"try again"}')
        else:
            route.continue_()

    ui.route("**/api/layers/generate", fail_first)
    ui.click('#tool-toggle button[data-tool="pen"]')
    _pen_anchor(ui, -40, 0)
    _pen_anchor(ui, 40, 0)
    ui.keyboard.press("Enter")
    ui.wait_for_function("() => !document.getElementById('pen-commit').disabled")
    assert "on" in (ui.locator('#tool-toggle button[data-tool="pen"]').get_attribute("class") or "")

    ui.keyboard.press("Enter")
    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row.selected').length === 1")
    ui.wait_for_function("() => document.querySelector('#tool-toggle [data-tool=select]').classList.contains('on')")
    assert len(_get(f"{ui.base}/api/project")["layers"]) == 1


def test_late_pen_commit_does_not_override_a_new_tool_choice(ui):
    ui.evaluate("""() => {
      const realFetch = window.fetch.bind(window);
      window.fetch = async (...args) => {
        const url = String(args[0]?.url || args[0]);
        if (url.includes('/api/layers/generate')) {
          await new Promise(resolve => { window.releasePenCommit = resolve; });
        }
        return realFetch(...args);
      };
    }""")
    ui.click('#tool-toggle button[data-tool="pen"]')
    _pen_anchor(ui, -40, 0)
    _pen_anchor(ui, 40, 0)
    ui.keyboard.press("Enter")
    ui.wait_for_function("() => typeof window.releasePenCommit === 'function'")
    ui.click('#tool-toggle button[data-tool="brush"]')
    ui.evaluate("() => window.releasePenCommit()")

    ui.wait_for_function("() => document.querySelectorAll('#layer-list .layer-row.selected').length === 1")
    assert "on" in (ui.locator('#tool-toggle button[data-tool="brush"]').get_attribute("class") or "")
    assert len(_get(f"{ui.base}/api/project")["layers"]) == 1
