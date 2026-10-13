import io

import pytest

from _mcp_harness import axb, call, images, srv, targets, text  # noqa: F401

pytest.importorskip("playwright.sync_api")


def test_see_ui_screenshots_a_tab(srv):
    r = call(srv, "see_ui", {"tab": "plot", "width": 1200, "height": 800})
    if r.is_error and "chromium" in text(r):
        pytest.skip(text(r))
    assert not r.is_error, text(r)
    from PIL import Image
    assert Image.open(io.BytesIO(images(r)[0])).size == (1200, 800)


def test_see_ui_reports_a_missing_selector_readably(srv):
    r = call(srv, "see_ui", {"steps": [{"action": "click", "selector": "#does-not-exist"}]})
    if "chromium" in text(r):
        pytest.skip(text(r))
    assert r.is_error and "#does-not-exist" in text(r)


def test_see_ui_rejects_unknown_tabs(srv):
    assert call(srv, "see_ui", {"tab": "kitchen"}).is_error
