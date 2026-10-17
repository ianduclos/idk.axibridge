"""Round-12 deliverable checks: physical paths and exact image rebuilds."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / 'experiments/outsider_rooms.py'
spec = importlib.util.spec_from_file_location('outsider_rooms_tested', SCRIPT)
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)


def test_motion_transfer_has_no_dependence_on_source_translation_or_units():
    t = np.linspace(0, 9, 700)
    p = np.column_stack([np.cos(t) + .1 * t, np.sin(.7 * t)])
    a = o.arm_trace(p, gear=.37)
    b = o.arm_trace(13.4 * p + [120, -370], gear=.37)
    np.testing.assert_allclose(a, b, atol=1e-12, rtol=1e-12)


def test_review_metadata_rebuilds_the_actual_pen_geometry():
    manifest = o.review_manifest()
    assert len(manifest['images']) == 4
    for record in manifest['images']:
        params = record['parameters']
        paths = o.process_geometry(params) if record['kind'] == 'process' else [o.geometry(params)]
        assert len(paths) == (3 if record['kind'] == 'process' else 1)
        with Image.open(o.ROOT/'tools/gesture/results'/record['file']) as im:
            assert im.format == 'JPEG'
            assert max(im.size) == record['long_side_px'] <= 2400
            saved = json.loads(im.getexif()[270])
        assert saved['geometry_sha256'] == o.geometry_digest(paths)
        assert saved['path_count'] == len(paths)
        assert saved['frozen_commit'] == manifest['frozen_commit']
        for key, value in params.items():
            assert saved[key] == value
        for p in paths:
            assert p.shape == (3600, 2)
            assert np.isfinite(p).all()
            assert (p >= params.get('pen', .5) / 2).all()
            assert (p <= np.array(params['frame']) - params.get('pen', .5) / 2).all()
            # A contiguous pen-down line, with no inter-panel jumps or closure.
            assert np.linalg.norm(p[-1] - p[0]) > 1
            assert np.linalg.norm(np.diff(p, axis=0), axis=1).max() < 3


def test_process_end_is_exactly_the_finished_piece():
    records = o.review_manifest()['images']
    final = o.geometry(records[0]['parameters'])
    process = o.process_geometry(records[1]['parameters'])
    # Compare in the translated frame: subtracting 388 loses low float bits.
    np.testing.assert_array_equal(process[-1], final + [388, 0])


def test_fresh_processes_and_hash_seeds_produce_identical_geometry():
    code = ("import sys; sys.path.insert(0,'tools/gesture/experiments'); "
            "import outsider_rooms as o; "
            "p=o.review_manifest()['images'][0]['parameters']; "
            "print(o.geometry_digest([o.geometry(p)]))")
    results = [subprocess.check_output([sys.executable, '-c', code], cwd=o.ROOT,
               env=dict(os.environ, PYTHONHASHSEED=str(s)), text=True).strip() for s in [17, 91]]
    assert results[0] == results[1]
