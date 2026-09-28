import io, time, threading
import numpy as np
from PIL import Image
from axibridge.assets import asset_store
from axibridge.linedraw.contracts import Evidence, LinedrawV3Params


def wait(manager, job):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = manager.get(job["id"])
        if result["state"] in ("complete", "cancelled", "failed"):
            return result
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_completed_job_contains_exact_recipe(monkeypatch):
    from axibridge.linedraw.jobs import JobManager
    from axibridge.linedraw import runtime

    b = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(b, format="PNG")
    asset_store.put("synthetic.png", b.getvalue())
    e = Evidence(
        np.ones((32, 32, 3)),
        np.zeros((32, 32)),
        None,
        np.ones((32, 32)),
        np.ones((32, 32)),
    )
    monkeypatch.setattr(runtime, "detect_and_analyze", lambda *a, **k: e)
    monkeypatch.setattr(runtime, "model_identity", lambda: "test-model")
    manager = JobManager()
    try:
        job = manager.start(
            "draft-1", LinedrawV3Params(image="synthetic.png"), "analyze"
        )
        result = wait(manager, job)
        assert result["state"] == "complete", result
        assert result["revision"] == "draft-1"
        assert result["result"]["params"]["image_identity"] == runtime.image_identity(
            b.getvalue()
        )
        assert result["result"]["preview"]["lines"] == []
    finally:
        manager.shutdown()


def test_cancelled_job_never_commits(monkeypatch):
    from axibridge.linedraw.jobs import JobManager
    from axibridge.linedraw import runtime
    from axibridge.render_work import RenderCancelled

    b = io.BytesIO()
    Image.new("RGB", (8, 8)).save(b, format="PNG")
    asset_store.put("cancel.png", b.getvalue())

    def analyze(*a, cancel, **kw):
        cancel.wait(3)
        raise RenderCancelled()

    monkeypatch.setattr(runtime, "detect_and_analyze", analyze)
    manager = JobManager()
    try:
        job = manager.start("draft-1", LinedrawV3Params(image="cancel.png"), "analyze")
        manager.cancel(job["id"])
        assert manager.get(job["id"])["state"] == "cancelled"
        assert manager.get(job["id"])["result"] is None
    finally:
        manager.shutdown()
