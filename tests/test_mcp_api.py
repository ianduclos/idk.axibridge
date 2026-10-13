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


def test_limits_writes_refused_on_live_only():
    from mcp.server.mcpserver.exceptions import ToolError
    from axibridge_mcp.tools_api import check_allowed
    with pytest.raises(ToolError, match="soft limits"):
        check_allowed("PUT", "/api/limits", "live")
    check_allowed("PUT", "/api/limits", "sandbox")
    check_allowed("GET", "/api/limits", "live")


@pytest.mark.parametrize("path", ["/api/Machine/jog", "/api/machine/jog;x"])
def test_case_and_semicolon_spellings_move_nothing(srv, axb, path):
    import httpx
    before = httpx.get(axb + "/api/state").json()["machine"]
    r = call(srv, "call_api", {"method": "POST", "path": path, "body": {"dx": 5, "dy": 5}})
    assert r.is_error or "404" in text(r) or "405" in text(r), text(r)
    after = httpx.get(axb + "/api/state").json()["machine"]
    assert after["job_state"] == "idle" == before["job_state"]
    assert after["position"] == before["position"]


@pytest.mark.parametrize("target", ["live", "sandbox"])
@pytest.mark.parametrize("method", ["PUT", "post", "PATCH"])
def test_call_api_refuses_projects_root_changes(srv, targets, axb, target, method):
    import httpx
    before = httpx.get(axb + "/api/settings").json()["projects_root"]
    r = call(srv, "call_api", {"method": method, "path": "/api/./settings/",
                               "body": {"projects_root": "/Users/ian/AxidrawProjects",
                                        "pen_swing_s": 0.2},
                               "target": target})
    assert r.is_error and "projects_root is fixed" in text(r), text(r)
    assert httpx.get(axb + "/api/settings").json()["projects_root"] == before
    assert not targets.sandbox.running  # refused before a sandbox was even started


def test_call_api_allows_other_settings(srv, axb):
    import httpx
    r = call(srv, "call_api", {"method": "PUT", "path": "/api/settings",
                               "body": {"pen_swing_s": 0.2}})
    assert not r.is_error and text(r).startswith("200"), text(r)
    assert httpx.get(axb + "/api/settings").json()["pen_swing_s"] == 0.2
    r = call(srv, "call_api", {"method": "GET", "path": "/api/settings",
                               "body": {"projects_root": "/x"}})
    assert not r.is_error, text(r)  # GET never sends a body
