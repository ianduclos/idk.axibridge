import json
import time

import httpx

from _mcp_harness import axb, call, free_port, http, srv, targets, text  # noqa: F401

POLY = {"module": "polygon", "params": {"sides": 5, "radius": 20}}


def test_state_summarises_project_layers_and_machine(srv, axb):
    with http(axb) as h:
        lid = h.post("/api/layers/generate", json=POLY).json()["id"]
    r = call(srv, "state")
    assert not r.is_error, text(r)
    data = json.loads(text(r))
    assert data["target"] == "live"
    assert isinstance(data["project"]["edit_rev"], int)
    [layer] = data["layers"]
    assert layer["id"] == lid
    assert layer["source"] == "generator:polygon"
    assert layer["paths"] == 1
    assert data["machine"]["job_state"] == "idle"


def test_state_says_plainly_when_the_live_app_is_down():
    from axibridge_mcp.server import build_server
    from axibridge_mcp.targets import Targets

    t = Targets(live_url=f"http://127.0.0.1:{free_port()}")
    try:
        r = call(build_server(t), "state")
    finally:
        t.close()
    assert r.is_error
    assert "isn't running" in text(r) and "AxiBridge.app" in text(r)


def test_unknown_targets_are_rejected(srv):
    r = call(srv, "state", {"target": "elsewhere"})
    assert r.is_error


def test_the_sandbox_starts_on_demand_and_is_isolated(srv, targets, axb):
    with http(axb) as h:
        h.post("/api/layers/generate", json=POLY)
    r = call(srv, "state", {"target": "sandbox"})
    assert not r.is_error, text(r)
    assert json.loads(text(r))["layers"] == []
    url = targets.sandbox.url
    assert url and url != axb
    targets.close()
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            httpx.get(url + "/api/project", timeout=0.5)
            time.sleep(0.2)
        except httpx.HTTPError:
            break
    else:
        raise AssertionError("sandbox still answering after close()")


def test_api_errors_come_back_as_readable_text(targets):
    from mcp.server.mcpserver.exceptions import ToolError
    import pytest

    with pytest.raises(ToolError, match=r"live: PATCH /api/layers/nope → 404"):
        targets.client("live").patch("/api/layers/nope", {"name": "x"})


def _wait_down(url, seconds=10):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            httpx.get(url + "/api/project", timeout=0.5)
            time.sleep(0.2)
        except httpx.HTTPError:
            return
    raise AssertionError("still answering")


def test_concurrent_first_sandbox_calls_share_one_server(targets):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(2) as ex:
        urls = list(ex.map(lambda _: targets.client("sandbox").base_url, range(2)))
    assert urls[0] == urls[1]
    targets.close()
    _wait_down(urls[0])


def test_sandbox_projects_root_is_inside_its_own_dir(targets):
    from pathlib import Path

    targets.client("sandbox")
    root = targets.client("sandbox").get("/api/settings")["projects_root"]
    assert Path(root).resolve().is_relative_to(targets.sandbox.dir.resolve())


def test_client_transport_and_non_json_errors_are_toolerrors():
    import httpx as hx
    import pytest
    from mcp.server.mcpserver.exceptions import ToolError
    from axibridge_mcp.client import ApiClient

    def handler(req):
        if req.url.path == "/bad":
            return hx.Response(200, content=b"<html>")
        raise hx.ReadError("boom")

    c = ApiClient("http://x", "live", lambda: "down")
    c._http = hx.Client(base_url="http://x", transport=hx.MockTransport(handler))
    with pytest.raises(ToolError, match="non-JSON"):
        c.get("/bad")
    with pytest.raises(ToolError, match="failed: boom"):
        c.get("/other")
