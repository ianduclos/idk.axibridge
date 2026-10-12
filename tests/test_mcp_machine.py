import json
import re
import time

from _mcp_harness import axb, call, http, srv, targets, text  # noqa: F401


def connect(axb):
    with http(axb) as h:
        h.post("/api/connect", json={}).raise_for_status()


def wait_idle(axb, timeout=60):
    deadline = time.time() + timeout
    with http(axb) as h:
        while time.time() < deadline:
            if h.get("/api/state").json()["machine"]["job_state"] == "idle":
                return
            time.sleep(0.2)
    raise AssertionError("job never finished")


def rev_of(estimate_text: str) -> int:
    return int(re.search(r"revision (\d+)", estimate_text).group(1))


def test_estimate_states_time_and_the_revision_to_plot(srv, axb):
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 5, "radius": 20}})
    out = text(call(srv, "estimate"))
    assert "pen-down" in out and "revision" in out
    with http(axb) as h:
        assert rev_of(out) == h.get("/api/project").json()["edit_rev"]


def test_plot_runs_what_was_estimated(srv, axb):
    connect(axb)
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 5, "radius": 10}})
    rev = rev_of(text(call(srv, "estimate")))
    r = call(srv, "plot", {"revision": rev})
    assert not r.is_error, text(r)
    wait_idle(axb)


def test_plot_refuses_after_an_edit(srv, axb):
    # Review Focus 4: an edit between estimate and plot means nobody saw this
    connect(axb)
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 5, "radius": 10}})
    rev = rev_of(text(call(srv, "estimate")))
    with http(axb) as h:  # Ian nudges something in the UI
        lid = h.get("/api/project").json()["layers"][0]["id"]
        h.patch(f"/api/layers/{lid}", json={"name": "changed"})
    r = call(srv, "plot", {"revision": rev})
    assert r.is_error and "changed since" in text(r)
    with http(axb) as h:
        assert h.get("/api/state").json()["machine"]["job_state"] == "idle"


def test_motion_tools_refuse_the_sandbox_without_starting_it(srv, targets):
    for name, args in [("plot", {"revision": 1}), ("pen", {"down": False}),
                       ("jog", {"dx": 1}), ("go_home", {})]:
        r = call(srv, name, {**args, "target": "sandbox"})
        assert r.is_error and "only drive the live app" in text(r), name
    assert not targets.sandbox.running


def test_jog_is_bounded(srv):
    assert call(srv, "jog", {"dx": 500}).is_error


def test_jog_then_go_home(srv, axb):
    connect(axb)
    assert "position" in text(call(srv, "jog", {"dx": 5, "dy": 3}))
    out = text(call(srv, "go_home"))
    assert "0.0, 0.0" in out or "[0.0, 0.0]" in out


def test_stop_halts_a_running_plot(srv, axb):
    connect(axb)
    call(srv, "add_layer", {"module": "polygon", "params": {"sides": 40, "radius": 90}})
    rev = rev_of(text(call(srv, "estimate")))
    assert not call(srv, "plot", {"revision": rev}).is_error
    r = call(srv, "stop")
    assert not r.is_error, text(r)
    wait_idle(axb, timeout=20)


def test_stop_when_idle_is_harmless(srv):
    assert not call(srv, "stop").is_error
