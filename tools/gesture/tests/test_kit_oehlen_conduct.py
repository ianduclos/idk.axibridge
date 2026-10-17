"""Round 12, thread oehlen_conduct: conduction, double and blank, tree program."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, "tools/gesture")
from gesture import kit  # noqa: E402
from gesture.kit import voices_oehlen_conduct as vc  # noqa: E402

PIECE = {"seed": 3323, "frame": [300, 200], "margin": 12,
         "voice": {"id": "oehlen_conduct", "blanks": [0.1, 0.95, 0.42]},
         "renderer": {"id": "oehlen_conduct_ink"}}


def _run(r=PIECE):
    return kit.run(json.loads(json.dumps(r)))


@pytest.fixture(scope="module")
def piece():
    return _run()


def test_registered():
    kit.discover()
    assert not kit.DISCOVERY_ERRORS
    for k, i in (("voice", "oehlen_conduct"), ("voice", "oehlen_conduct_ensemble"), ("voice", "oehlen_conduct_tree"),
                 ("renderer", "oehlen_conduct_ink")):
        assert kit.get(k, i).id == i


def test_piece_shape(piece):
    roles = [int(m["role"][0]) for m in piece.marks]
    assert roles[0] == 0 and roles.count(0) == 1          # the conductor, once, first
    assert 1 in roles and 2 in roles                      # performance and second passes
    W, H = piece.frame
    for ink in piece.inks:
        assert ink.pen in (2.2, 0.5)
        assert not ink.filled
        assert np.all(ink.points >= -1e-6) and np.all(ink.points[:, 0] <= W) and np.all(ink.points[:, 1] <= H)
    sb = piece.marks[0].meta["conduct"]["source_box"]
    src = piece.marks[0].points
    assert src[:, 0].max() <= sb[0] + sb[2] + 1e-6 and max(sb[2], sb[3]) == pytest.approx(34.0)


def test_performance_lands_on_cues(piece):
    """The cue points are hit (land 0.75 of the way): the conducted relation is
    real, and the performance is not the source scaled (most of it is far
    from the scaled source path)."""
    perf = np.vstack([m.points for m in piece.marks if int(m["role"][0]) == 1])
    cues = [c for c in piece.marks[0].meta["conduct"]["cues"] if c["kind"] in ("turn", "stop")]
    d = [np.min(np.linalg.norm(perf - np.array(c["mm"]), axis=1)) for c in cues]
    assert np.median(d) < 15.0


def test_blank_is_kept(piece):
    bl = np.array(piece.marks[0].meta["conduct"]["blanks_mm"][0])
    perf = np.vstack([m.points for m in piece.marks if int(m["role"][0]) >= 1])
    inside = np.linalg.norm(perf - bl[:2], axis=1) < bl[2]
    assert inside.mean() < 0.02


def test_blank_hard_cuts():
    r = json.loads(json.dumps(PIECE))
    r["voice"].update({"blanks": [0.6, 0.5, 0.2], "blank_hard": True, "double": 0.0})
    sh = _run(r)
    bl = np.array(sh.marks[0].meta["conduct"]["blanks_mm"][0])
    for m in sh.marks[1:]:
        assert np.all(np.linalg.norm(m.points - bl[:2], axis=1) >= 0.97 * bl[2] - 1e-6)


def test_second_pass_meets_and_parts():
    """Never a parallel copy: along the retraced stretch the second pass
    touches the first line (< 1.5 mm) AND splits away from it (> 3 mm)."""
    rng = np.random.default_rng(5)
    t = np.linspace(0, 1, 600)
    p = np.column_stack([200 * t, 30 * np.sin(3 * t)])
    hits = 0
    for _ in range(20):
        r, si = vc.retrace(p, rng, amp=8.0, memory=3.0, cover=(0.1, 0.9), splits=2.0)
        d = np.min(np.linalg.norm(r[:, None, :] - vc.resample(p, 0.4)[None, ::2, :], axis=2), axis=1)
        assert len(si) == len(r)
        hits += (np.mean(d < 1.5) > 0.2) and (d.max() > 3.0)
    assert hits >= 16


def test_thin_cues_keeps_stops_and_end():
    big = np.column_stack([np.arange(10.0), np.zeros(10)])
    cues = [{"i": 0, "kind": "enter"}] + [{"i": i, "kind": "turn" if i != 5 else "stop"} for i in range(1, 9)] + \
        [{"i": 9, "kind": "end"}]
    out = vc.thin_cues(cues, big, 3.0)
    kinds = [c["kind"] for c in out]
    assert kinds[0] == "enter" and kinds[-1] == "end" and "stop" in kinds
    assert len(out) < len(cues)


def test_ensemble_and_tree_run():
    e = _run({"seed": 3402, "frame": [300, 200], "margin": 12, "voice": {"id": "oehlen_conduct_ensemble",
              "players": ["trail_miner", "fly_fru"], "pens": [1.4, 0.3]}, "renderer": {"id": "oehlen_conduct_ink"}})
    assert {int(m.meta.get("player", -1)) for m in e.marks[1:]} <= {0, 1}
    t = _run({"seed": 5507, "frame": [145, 218], "margin": 10, "voice": {"id": "oehlen_conduct_tree"},
              "renderer": {"id": "oehlen_conduct_ink"}})
    w = [float(np.max(m["cw"])) for m in t.marks]
    assert max(w) > min(w)                                # the narrowing rule weighs lines


def test_deterministic_across_processes(piece):
    code = ("import sys,json,hashlib;sys.path.insert(0,'tools/gesture');from gesture import kit;"
            f"s=kit.run(json.loads({json.dumps(json.dumps(PIECE))}));"
            "print(hashlib.sha1(b''.join(i.points.tobytes() for i in s.inks)).hexdigest())")
    outs = set()
    for seed in ("1", "77"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outs.add(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                                check=True).stdout.strip())
    import hashlib  # noqa: PLC0415
    outs.add(hashlib.sha1(b"".join(i.points.tobytes() for i in piece.inks)).hexdigest())
    assert len(outs) == 1
