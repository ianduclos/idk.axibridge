"""Regression checks for the visual-precision pass.

These stay at the UI boundary: a person can see keyboard focus, read and use
controls without page-wide clipping, and reach the working frame/actions in a
popup.  The established acceptance module supplies the real server and built
frontend fixture; this module deliberately adds no alternate browser harness.
"""

from __future__ import annotations

from test_acceptance_ui import (  # re-export fixtures for pytest discovery
    add_layer,
    animate_and_follow,
    frontend_mode,
    reload_app,
    server,
    ui,
    wait_for_ink,
)


def _open_bench(page, source: str) -> None:
    page.select_option("#gen-select", source)
    page.wait_for_selector("#btn-bench:not([hidden])", timeout=10_000)
    page.click("#btn-bench")
    page.wait_for_selector("#process-popup:not([hidden])", timeout=20_000)


def _rect_within(inner: dict, outer: dict, tolerance: float = 1.0) -> bool:
    return (inner["x"] >= outer["x"] - tolerance
            and inner["y"] >= outer["y"] - tolerance
            and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + tolerance
            and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + tolerance)


def test_keyboard_focus_is_visible_on_regular_and_compact_controls(ui):
    """Keyboard users need an obvious current control in both UI densities."""
    add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    reload_app(ui)
    ui.wait_for_selector("#layer-list .layer-row", timeout=15_000)

    result = ui.evaluate("""() => {
      const regular = document.querySelector('#btn-generate');
      const compact = document.querySelector('#layer-list .eye');
      const inspect = (el) => {
        el.focus();
        const s = getComputedStyle(el), r = el.getBoundingClientRect();
        return { active: document.activeElement === el, outline: s.outlineStyle,
                 outlineWidth: parseFloat(s.outlineWidth), height: r.height };
      };
      return { regular: inspect(regular), compact: inspect(compact) };
    }""")
    for name, minimum in (("regular", 30), ("compact", 24)):
        control = result[name]
        assert control["active"], f"{name} control cannot receive keyboard focus"
        assert control["outline"] != "none" and control["outlineWidth"] >= 2, \
            f"{name} keyboard focus has no visible outline: {control}"
        assert control["height"] >= minimum, f"{name} control is too small: {control}"
    assert not ui.errors


def test_plot_pens_and_settings_do_not_create_horizontal_page_overflow(ui):
    """At compact desktop widths, each main panel keeps labels and values usable.

    The canvas toolbar intentionally has its own horizontal scrolling; these
    assertions cover the Plot, Pens, and Settings panels, where clipping would
    hide a field or action instead of offering that deliberate escape hatch.
    """
    for width in (700, 900):
        ui.set_viewport_size({"width": width, "height": 760})
        for tab in ("plot", "pens", "settings"):
            ui.click(f'#tabs button[data-tab="{tab}"]')
            ui.wait_for_selector(f"#tab-{tab}:not([hidden])", timeout=10_000)
            overflow = ui.evaluate("""tab => {
              const body = document.querySelector(`#tab-${tab}`);
              const page = document.documentElement;
              const escaped = [...body.querySelectorAll('button, input, select')]
                .filter(el => el.getClientRects().length)
                .some(el => {
                  const r = el.getBoundingClientRect(), b = body.getBoundingClientRect();
                  return r.left < b.left - 1 || r.right > b.right + 1;
                });
              const wide = [...body.querySelectorAll('*')]
                .filter(el => el.scrollWidth > el.clientWidth + 1)
                .map(el => `${el.tagName.toLowerCase()}#${el.id}.${el.className}`)
                .slice(0, 8);
              const widest = [...body.querySelectorAll('*')]
                .map(el => ({ el: `${el.tagName.toLowerCase()}#${el.id}.${el.className}`,
                              text: el.textContent.trim().slice(0, 100),
                              scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }))
                .sort((a, b) => b.scrollWidth - a.scrollWidth).slice(0, 8);
              return { page: page.scrollWidth > page.clientWidth + 1,
                       panel: body.scrollWidth > body.clientWidth + 1, escaped, wide, widest };
            }""", tab)
            assert not (overflow["page"] or overflow["panel"] or overflow["escaped"]), \
                f"{width}px {tab} panel clips a control: {overflow}"
            if width == 700 and tab == "settings":
                ruler = ui.evaluate("""() => {
                  const viewport = document.querySelector('.ruler-viewport');
                  const ruler = document.querySelector('#cal-bar');
                  const style = getComputedStyle(viewport);
                  return { ruler: ruler.getBoundingClientRect().width,
                           viewport: viewport.clientWidth,
                           scroll: viewport.scrollWidth,
                           overflowX: style.overflowX };
                }""")
                assert ruler["ruler"] > ruler["viewport"] and ruler["scroll"] >= ruler["ruler"], \
                    f"the fixed 100 mm ruler unexpectedly shrank: {ruler}"
                assert ruler["overflowX"] in ("auto", "scroll"), \
                    f"the ruler lost its deliberate local scroll viewport: {ruler}"
                # A long but ordinary machine number must fit in the visible
                # edit field, rather than relying on a clipped tail/spinner.
                numeric = ui.locator("#guide-w")
                numeric.fill("12345.67")
                readable = ui.evaluate("""() => {
                  const input = document.querySelector('#guide-w'), s = getComputedStyle(input);
                  const canvas = document.createElement('canvas'), ctx = canvas.getContext('2d');
                  ctx.font = `${s.fontWeight} ${s.fontSize} ${s.fontFamily}`;
                  const edges = parseFloat(s.paddingLeft) + parseFloat(s.paddingRight) + 22;
                  return { text: ctx.measureText(input.value).width,
                           usable: input.clientWidth - edges, value: input.value };
                }""")
                assert readable["text"] <= readable["usable"], \
                    f"long numeric value is clipped in its edit field: {readable}"
    assert not ui.errors


def test_generic_bench_keeps_its_full_working_frame_inside_the_popup(ui):
    """A process bench must show the whole drawing rather than crop its paper."""
    ui.set_viewport_size({"width": 900, "height": 700})
    _open_bench(ui, "homeostat")
    ui.wait_for_function(
        "() => document.querySelector('#process-create')?.disabled === false", timeout=20_000)
    frame = ui.locator("#process-canvas").bounding_box()
    stage = ui.locator("#process-popup .preview-stage").bounding_box()
    popup = ui.locator("#process-popup .preview-modal").bounding_box()
    assert frame and stage and popup
    assert _rect_within(frame, stage), f"working frame is cropped by its stage: {frame} vs {stage}"
    assert _rect_within(stage, popup), f"working stage escapes the popup: {stage} vs {popup}"
    assert not ui.errors


def test_popup_actions_remain_reachable_at_two_x_css_zoom_approximation(ui):
    """Approximate browser 200% zoom without relying on host zoom settings."""
    ui.set_viewport_size({"width": 1440, "height": 900})
    _open_bench(ui, "second_reading")
    ui.wait_for_function(
        "() => document.querySelector('#process-preview-state')?.textContent === 'rendered'",
        timeout=20_000)
    ui.evaluate("() => { document.documentElement.style.zoom = '2'; }")
    try:
        frame = ui.locator("#process-canvas").bounding_box()
        stage = ui.locator(".second-reading .preview-stage").bounding_box()
        assert frame and stage and _rect_within(frame, stage), \
            "working frame is cropped at the 200% CSS zoom approximation"
        for selector in ("#process-close", "#process-keep"):
            ui.locator(selector).scroll_into_view_if_needed()
            reachable = ui.evaluate("""selector => {
              const control = document.querySelector(selector);
              const r = control.getBoundingClientRect();
              const x = r.left + r.width / 2, y = r.top + r.height / 2;
              const hit = document.elementFromPoint(x, y);
              return x >= 0 && x <= innerWidth && y >= 0 && y <= innerHeight
                && (hit === control || control.contains(hit));
            }""", selector)
            assert reachable, f"{selector} is unreachable at the 200% CSS zoom approximation"
    finally:
        ui.evaluate("() => { document.documentElement.style.zoom = ''; }")
    # A real reduced CSS viewport catches responsive rules that a visual zoom
    # transform cannot exercise (the effective 720×450 workspace above).
    ui.set_viewport_size({"width": 720, "height": 450})
    for selector in ("#process-close", "#process-keep"):
        ui.locator(selector).scroll_into_view_if_needed()
        reachable = ui.evaluate("""selector => {
          const control = document.querySelector(selector), r = control.getBoundingClientRect();
          const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight
            && (hit === control || control.contains(hit));
        }""", selector)
        assert reachable, f"{selector} is unreachable in the reduced 720×450 CSS viewport"
    assert not ui.errors


def test_animation_preview_keeps_its_frame_and_actions_reachable_at_720_by_450(ui):
    """The shared popup must not crop a render or strand its export controls."""
    layer_id = add_layer(ui, "polygon", {"sides": 5, "radius": 20})
    animate_and_follow(ui, layer_id, b_radius=80)
    reload_app(ui)
    wait_for_ink(ui)
    ui.set_viewport_size({"width": 720, "height": 450})
    ui.wait_for_selector("#timeline-bar:not([hidden])", timeout=10_000)
    ui.click("#tl-render")
    ui.wait_for_selector("#anim-preview-modal:not([hidden])", timeout=10_000)
    ui.wait_for_function(
        "() => !document.getElementById('anim-preview-img').hidden", timeout=30_000)

    image = ui.locator("#anim-preview-img").bounding_box()
    stage = ui.locator("#anim-preview-stage").bounding_box()
    assert image and stage and _rect_within(image, stage), \
        f"render preview is cropped by its stage: {image} vs {stage}"
    for selector in ("#anim-preview-export-mp4", "#anim-preview-close"):
        ui.locator(selector).scroll_into_view_if_needed()
        reachable = ui.evaluate("""selector => {
          const control = document.querySelector(selector), r = control.getBoundingClientRect();
          const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight
            && (hit === control || control.contains(hit));
        }""", selector)
        assert reachable, f"{selector} is unreachable in the 720×450 render popup"
    assert not ui.errors
