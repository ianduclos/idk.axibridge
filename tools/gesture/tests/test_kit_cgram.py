"""Round 14 b3 `cgram`: compositions as a grammar (kit/arrangers_cgram.py)."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_cgram as cg  # noqa: E402

SHORT = (1460, 1462, 1468, 1463)          # short sentences: quick to play


def _digest(sheet) -> str:
    h = hashlib.sha1()
    for ink in sheet.inks:
        h.update(np.round(ink.points, 4).tobytes())
        h.update(str((ink.pen, ink.meta.get("colour"))).encode())
    return h.hexdigest()


def test_registered():
    kit.core.discover()
    assert "cgram" in kit.core.registry("arranger")
    assert "cgram_free" in kit.core.registry("voice")
    assert not kit.DISCOVERY_ERRORS


def test_parse_speak_roundtrip():
    s = "reserve x=0.2 y=0.8 w=0.3 h=0.3 ; seed p=fly x=0.6 y=0.3 r=0.2 n=3 ; intrude kind=bar at=@1 len=40"
    mv = cg.parse(s)
    assert [m["move"] for m in mv] == ["reserve", "seed", "intrude"]
    assert mv[2]["at"] == ("ref", 1) and mv[1]["n"] == 3 and mv[1]["p"] == "fly"
    assert cg.parse(cg.speak(mv)) == mv
    with pytest.raises(ValueError):
        cg.parse("dance x=1")


def test_sampler_deterministic_and_valid():
    for s in (1460, 1464, 1471):
        a, b = cg.recipe(s), cg.recipe(s)
        assert a == b
        kit.validate(a)
        for m in cg.parse(a["arranger"]["sentence"]):
            for v in m.values():
                if isinstance(v, tuple):         # every reference points back, never forward
                    assert v[1] < cg.parse(a["arranger"]["sentence"]).index(m)


def test_temperament_varies_the_sentence():
    """Different every time: sentence length spans short to long, and the dominant move changes."""
    lens, dom = [], []
    for s in range(1460, 1484):
        mv = cg.parse(cg.sample_sentence(s)[0])
        lens.append(len(mv))
        c = Counter(m["move"] for m in mv if m["move"] != "reserve")
        dom.append(c.most_common(1)[0][0])
    assert min(lens) <= 5 and max(lens) >= 30
    assert len(set(dom)) >= 5
    # the uniform control is one length every time
    assert {len(cg.parse(cg.sample_sentence(s, uniform=True)[0])) for s in range(1460, 1470)} == {14}


def test_prerequisites_hold():
    for s in range(1460, 1490):
        mv = cg.parse(cg.sample_sentence(s)[0])
        kinds = [m["move"] for m in mv]
        for i, m in enumerate(mv):
            if m["move"] == "cross":
                assert "cover" in kinds[:i]
            if m["move"] == "spill":
                assert "contain" in kinds[:i]
            if m["move"] in ("answer", "trail", "stop", "contaminate"):
                assert any(k in kinds[:i] for k in ("seed", "line", "morph", "traverse", "spill", "cross",
                                                     "answer", "counter"))


@pytest.mark.parametrize("seed", SHORT)
def test_every_move_does_something(seed):
    sheet = kit.run(cg.recipe(seed))
    log = sheet.marks[0].meta["cgram"]["moves"]
    for rec in log:
        assert "error" not in rec, rec
        if rec["move"] == "reserve" and rec["touched_mm"] == 0:
            # a blank decided first acts by absence: it holds less than its share of the ink
            assert rec["ink_share_inside"] < rec["area_share"], rec
        else:
            assert rec["touched_mm"] > 1.0, rec


def test_marks_stay_on_the_sheet():
    sheet = kit.run(cg.recipe(1463))
    W, H = sheet.frame
    for m in sheet.marks:
        assert m.points[:, 0].min() >= -1e-6 and m.points[:, 0].max() <= W + 1e-6
        assert m.points[:, 1].min() >= -1e-6 and m.points[:, 1].max() <= H + 1e-6


def test_self_crossing_line_is_not_noded():
    """shapely's intersection nodes a line that crosses itself into fragments; the mask clip does not."""
    t = np.linspace(0, 12 * np.pi, 3000)
    p = np.c_[50 + 20 * np.cos(t) + 2 * t, 50 + 20 * np.sin(1.3 * t)]
    big = np.array([[0, 0], [300, 0], [300, 200], [0, 200], [0, 0]], float)
    assert len(cg.clip_keep(p, big, 12.0)) == 1
    far = np.array([[200, 150], [210, 150], [210, 160], [200, 160], [200, 150]], float)
    assert len(cg.cover_split(p, far, 4.0, "cut")) == 1
    edge = np.array([[60, 0], [300, 0], [300, 200], [60, 200], [60, 0]], float)
    runs = cg.clip_keep(p, edge, 4.0)
    assert len(runs) <= 4                    # cut where it leaves the rectangle, not at every self-crossing


def test_free_hand_never_small():
    from gesture.kit.core import Ctx, _Run  # noqa: PLC0415
    from gesture.kit import library as L  # noqa: PLC0415
    rec = kit.validate(cg.recipe(1460))
    run = _Run(L.default())
    parts = [kit.core.Part(i, p, p.get("renderer", rec["renderer"]), rec["frame"], 1460, run, (6, 6, 208, 288))
             for i, p in enumerate(rec["parts"])]
    ctx = Ctx(tuple(rec["frame"]), (6.0, 6.0, 208.0, 288.0), 1460, 1460, -1, "arranger", "cgram", run)
    S = cg.Comp(ctx, parts, step=0.4, found_ink="blue", chart_ink="red", made_ink="black", tint_ink="green",
                tint_found_ink="green-400", min_stub=6.0)
    (p, _), = S.lines_of("free", (80.0, 80.0, 30.0, 20.0), 0)
    assert np.ptp(p[:, 0]) >= 140.0


def test_deterministic_across_processes():
    code = ("import sys,hashlib,numpy as np; sys.path.insert(0, %r)\n"
            "from gesture import kit\nfrom gesture.kit import arrangers_cgram as cg\n"
            "s = kit.run(cg.recipe(1468)); h = hashlib.sha1()\n"
            "[h.update(np.round(i.points, 4).tobytes()) for i in s.inks]\nprint(h.hexdigest())" % str(HERE))
    outs = set()
    for hs in ("1", "777"):
        env = {**os.environ, "PYTHONHASHSEED": hs}
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
        outs.add(r.stdout.strip().splitlines()[-1])
    assert len(outs) == 1
    sheet = kit.run(cg.recipe(1468))
    h = hashlib.sha1()
    for i in sheet.inks:
        h.update(np.round(i.points, 4).tobytes())
    assert outs == {h.hexdigest()}
