import subprocess
import threading
import numpy as np
import pytest


def test_status_never_spawns(monkeypatch, tmp_path):
    from axibridge.linedraw import runtime

    monkeypatch.setenv("AXIBRIDGE_LINEDRAW_CONFIG", str(tmp_path / "missing.json"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("spawn"))
    assert not runtime.status()["available"]


def test_cancel_before_worker(monkeypatch):
    from axibridge.linedraw import runtime
    from axibridge.render_work import RenderCancelled

    event = threading.Event()
    event.set()
    with pytest.raises(RenderCancelled):
        runtime.detect_and_analyze(b"", {}, cancel=event, progress=lambda *a: None)


def test_invalid_evidence_rejected():
    from axibridge.linedraw.runtime import validate_arrays

    with pytest.raises(ValueError):
        validate_arrays({"rgb": np.full((4, 4, 3), np.nan)}, 4, 4)


def test_worker_process_is_reaped_on_cancel(tmp_path):
    from axibridge.linedraw.runtime import _run
    from axibridge.render_work import RenderCancelled
    import sys, time

    # A separate Python wrapper sleeps instead of importing heavy models.
    wrapper = tmp_path / "slow"
    wrapper.write_text("#!/bin/sh\nsleep 60\n")
    wrapper.chmod(0o700)
    event = threading.Event()
    timer = threading.Timer(0.2, event.set)
    timer.start()
    start = time.monotonic()
    with pytest.raises(RenderCancelled):
        _run({"python": str(wrapper)}, {}, tmp_path, event, lambda *a: None)
    timer.join()
    assert time.monotonic() - start < 4


def test_model_import_roots_do_not_shadow_namespaces(tmp_path):
    import sys, importlib.util
    from axibridge.linedraw.worker import release_import_root

    root = tmp_path / "lines"
    root.mkdir()
    (root / "unique_linedraw_utils.py").write_text("")
    sys.path.insert(0, str(root))
    assert importlib.util.find_spec("unique_linedraw_utils") is not None
    release_import_root(str(root))
    assert importlib.util.find_spec("unique_linedraw_utils") is None


def test_native_trace_preserves_thin_line_before_coordinate_mapping():
    from axibridge.linedraw.runtime import native_candidates

    line_map = np.ones((768, 768), dtype=np.float32)
    line_map[100:650, 384] = 0
    candidates = native_candidates(
        line_map, [2, 3, 26, 15], 30, 20, "crop", lambda: None
    )
    assert len(candidates) == 1
    points = candidates[0].points
    assert np.allclose(points[:, 0], 14, atol=0.1)
    assert points[:, 1].min() >= 3 and points[:, 1].max() <= 15
    assert np.ptp(points[:, 1]) > 8


@pytest.mark.parametrize(
    "bounds", [[0, 0, 40, 10], [4, 0, 2, 10], [0, float("nan"), 10, 10]]
)
def test_native_trace_rejects_invalid_crop(bounds):
    from axibridge.linedraw.runtime import native_candidates

    with pytest.raises(ValueError):
        native_candidates(np.ones((8, 8)), bounds, 20, 20, "crop", lambda: None)
