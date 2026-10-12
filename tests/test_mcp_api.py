import pytest

from _mcp_harness import axb, call, images, srv, targets, text  # noqa: F401

BLOCKED = ["/api/machine/jog", "/api/machine/pen", "/api/machine/goto", "/api/machine/origin",
           "/api/machine/raw", "/api/machine/block", "/api/plot/start", "/api/plot/resume",
           "/api/calibration/teststroke", "/api/calibration/holder/mark"]
# Review Focus 2: spellings that reach the same route
SNEAKY = ["/api/machine/%6Aog", "/api/machine/jog/", "//api/machine/jog",
          "/api/layers/../machine/jog", "/api/machine/jog?x=1", "/api/machine/%2E%2E/machine/jog"]


@pytest.mark.parametrize("path", BLOCKED + SNEAKY)
def test_motion_paths_are_refused_on_every_target(path):
    from mcp.server.mcpserver.exceptions import ToolError
    from axibridge_mcp.tools_api import check_allowed
    for target in ("live", "sandbox"):
        with pytest.raises(ToolError, match="refused"):
            check_allowed("POST", path, target)


def test_restart_is_refused_on_live_only():
    from mcp.server.mcpserver.exceptions import ToolError
    from axibridge_mcp.tools_api import check_allowed
    with pytest.raises(ToolError):
        check_allowed("POST", "/api/server/restart", "live")
    check_allowed("POST", "/api/server/restart", "sandbox")


def test_paths_must_be_api_paths():
    from mcp.server.mcpserver.exceptions import ToolError
    from axibridge_mcp.tools_api import check_allowed
    with pytest.raises(ToolError):
        check_allowed("GET", "/index.html", "live")


def test_call_api_get_returns_json_text(srv):
    r = call(srv, "call_api", {"method": "GET", "path": "/api/pens"})
    assert not r.is_error, text(r)
    assert text(r).startswith("200")


def test_call_api_lowercase_method_is_still_checked(srv):
    r = call(srv, "call_api", {"method": "post", "path": "/api/machine/jog", "body": {"dx": 1}})
    assert r.is_error and "refused" in text(r)


def test_call_api_truncates_big_responses(srv):
    r = call(srv, "call_api", {"method": "GET", "path": "/api/state", "max_chars": 500})
    assert "truncated" in text(r)


def test_call_api_passes_png_through_as_an_image(srv, axb):
    import httpx
    httpx.post(axb + "/api/layers/generate", json={"module": "polygon", "params": {}})
    r = call(srv, "call_api", {"method": "GET", "path": "/api/animation/preview.png"})
    if r.is_error:
        pytest.skip(f"preview.png needs an animation here: {text(r)[:120]}")
    assert images(r)
