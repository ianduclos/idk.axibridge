import io
import json

import numpy as np
import pytest

from axibridge import mosca
from axibridge.assets import asset_store
from axibridge.sources.mosca import MoscaParams, MoscaSource


def _write(root, experiment="e1", label="walk", **arrays):
    folder = root / "out" / experiment
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{label}.npz"
    np.savez(target, **arrays)
    return target


def _recording(tmp_path, monkeypatch, *, pen_down=None, dt=10.0, config=True):
    monkeypatch.setenv("AXIBRIDGE_MOSCA_DIR", str(tmp_path))
    arrays = {"path": np.array([[10., 10.], [20., 10.], [30., 20.], [40., 20.]]),
              "dt": np.array(dt)}
    if pen_down is not None:
        arrays["pen_down"] = np.asarray(pen_down)
    if config:
        arrays["config_json"] = np.array(json.dumps({"name": "e1"}))
    _write(tmp_path, **arrays)
    return mosca.prepare_recording("e1/walk")


def test_list_prepare_is_deterministic_and_compact(tmp_path, monkeypatch):
    meta = _recording(tmp_path, monkeypatch, pen_down=[True, True, False, True])
    assert mosca.list_recordings() == [
        {"id": "e1/walk", "experiment": "e1", "label": "walk"}]
    assert meta == {"recording": meta["recording"], "label": "walk",
                    "experiment": "e1", "samples": 4, "duration_ms": 30.0,
                    "width": 40.0, "height": 20.0}
    first = mosca.recording_bytes(meta["recording"])
    assert mosca.prepare_recording("e1/walk")["recording"] == meta["recording"]
    with np.load(io.BytesIO(first), allow_pickle=False) as archive:
        assert archive.files == ["path", "pen_down", "dt", "config_json",
                                 "experiment", "label"]
        assert archive["path"].dtype == np.dtype("<f8")
        assert float(archive["path"][0, 0]) == 10.0


def test_legacy_metadata_is_nullable(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIBRIDGE_MOSCA_DIR", str(tmp_path / "out"))
    _write(tmp_path, path=np.array([[0., 0.], [2., 3.]]))
    meta = mosca.prepare_recording("e1/walk")
    assert meta["duration_ms"] is None
    info = mosca.recording_info(meta["recording"])
    assert info["samples"] == 2
    assert (info["recording"], info["experiment"], info["label"]) == (
        meta["recording"], "e1", "walk")


def test_float64_precision_and_provenance_survive_preparation(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIBRIDGE_MOSCA_DIR", str(tmp_path))
    precise = np.array([[0.123456789012345, 1.987654321098765], [2., 3.]], dtype=np.float64)
    _write(tmp_path, path=precise)
    meta = mosca.prepare_recording("e1/walk")
    with mosca._prepared_lock:
        mosca._decoded.clear()
        mosca._decoded_size = 0
    loaded = mosca.load_recording(meta["recording"])
    np.testing.assert_array_equal(loaded["path"], precise)
    assert not loaded["path"].flags.writeable
    assert mosca.recording_info(meta["recording"])["experiment"] == "e1"


def test_fractional_progress_respects_pen_up_gaps(tmp_path, monkeypatch):
    meta = _recording(tmp_path, monkeypatch, pen_down=[True, True, False, True])
    source = MoscaSource()
    # 5/6 of three edges = 2.5 edges: edge 2 is travel, edge 3 is half ink.
    doc = source.generate(MoscaParams(recording=meta["recording"], progress=5/6,
                                      tolerance=0))
    assert [p.points for p in doc.layers[0].paths] == [
        [(5.0, 15.0), (15.0, 15.0)],
        [(25.0, 5.0), (30.0, 5.0)],
    ]
    assert source.placement_frame({"recording": meta["recording"]}) == (40.0, 20.0)
    assert source.generate(MoscaParams(recording=meta["recording"], progress=0)).stats().paths == 0


def test_simplification_does_not_bridge_passages(tmp_path, monkeypatch):
    meta = _recording(tmp_path, monkeypatch, pen_down=[True, True, False, True])
    doc = MoscaSource().generate(MoscaParams(
        recording=meta["recording"], progress=1, tolerance=5))
    assert len(doc.layers[0].paths) == 2
    assert all(len(path.points) == 2 for path in doc.layers[0].paths)


@pytest.mark.parametrize("recording_id", ["../walk", "e1/../walk", "e1", "/walk"])
def test_unsafe_ids_are_rejected(tmp_path, monkeypatch, recording_id):
    monkeypatch.setenv("AXIBRIDGE_MOSCA_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        mosca.prepare_recording(recording_id)


def test_invalid_files_and_assets_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIBRIDGE_MOSCA_DIR", str(tmp_path))
    _write(tmp_path, path=np.array([1., 2.]))
    with pytest.raises(ValueError, match="Nx2"):
        mosca.prepare_recording("e1/walk")
    with pytest.raises(ValueError, match="invalid Mosca"):
        mosca.recording_bytes("not-an-asset")


def test_missing_root_has_actionable_configuration_error(tmp_path, monkeypatch):
    missing = tmp_path / "missing"
    monkeypatch.setenv("AXIBRIDGE_MOSCA_DIR", str(missing))
    with pytest.raises(ValueError, match="AXIBRIDGE_MOSCA_DIR"):
        mosca.list_recordings()


def test_persisted_asset_resolves_after_prepared_cache_is_cleared(tmp_path, monkeypatch):
    meta = _recording(tmp_path, monkeypatch)
    name = meta["recording"]
    data = mosca.recording_bytes(name)
    asset_store.put(name, data)
    with mosca._prepared_lock:
        mosca._prepared.clear()
        mosca._prepared_size = 0
        mosca._decoded.clear()
        mosca._decoded_size = 0
    assert mosca.recording_bytes(name) == data
    assert mosca.recording_info(name)["width"] == 40.0


def test_thumbnail_does_not_prepare_asset(tmp_path, monkeypatch):
    _recording(tmp_path, monkeypatch, pen_down=[True, True, False, True])
    with mosca._prepared_lock:
        mosca._prepared.clear()
        mosca._prepared_size = 0
        mosca._decoded.clear()
        mosca._decoded_size = 0
    svg = mosca.thumbnail_recording("e1/walk")
    assert svg.startswith('<svg') and svg.count("<polyline") == 2
    assert not mosca._prepared
