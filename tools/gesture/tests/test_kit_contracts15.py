"""Round-15 shared contracts: ctx.note → sheet.meta["notes"], Score, measuring devices."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesture import kit  # noqa: E402
from gesture.kit import core  # noqa: E402
from gesture.kit._devices import apply_devices, device  # noqa: E402
from gesture.kit._score import Score, score_of  # noqa: E402

BASE = {"seed": 4242, "voice": {"id": "hand", "hand": "marden"}}


@core.arranger("_t15_scored", params=[], doc="test: records a score")
def _t15_scored(ctx, parts):
    s = Score()
    a = s.layer("line", "hand", part=0)
    b = s.layer("mask", "none")
    s.relate("refuse", a, b, at=(10, 20), note="test")
    s.decide(density=0.4)
    ctx.note("score", s.to_json())
    out = []
    for p in parts:
        out += p.run(ctx.box)
    return out


@device("_t15_bar", params=[core.P("n", "int", 3, "n", min=1, max=9)], family="general", doc="test")
def _t15_bar(dctx, sheet, *, n):
    x0, y0, w, h = dctx.region
    return [core.Ink(np.array([[x0, y0 + h / 2], [x0 + w, y0 + h / 2]]), False, False, 0.2, {})]


def test_meta_unchanged_without_notes():
    assert "notes" not in kit.run(BASE).meta


def test_score_roundtrip():
    s = kit.run({**BASE, "arranger": {"id": "_t15_scored"}})
    sc = score_of(s)
    assert sc["version"] == 1 and [l["id"] for l in sc["layers"]] == ["L0", "L1"]
    assert sc["relations"][0]["kind"] == "refuse" and sc["decisions"]["density"] == 0.4


def test_devices_place():
    s = kit.run(BASE)
    W, H = s.frame
    over = apply_devices(s, [{"id": "_t15_bar", "place": "over"}])
    beside = apply_devices(s, [{"id": "_t15_bar", "place": "beside", "size": 50}])
    under = apply_devices(s, [{"id": "_t15_bar", "place": "under"}])
    assert over.frame == (W, H) and over.inks[-1].meta["device"] == "_t15_bar"
    assert beside.frame == (W + 50, H)
    assert under.inks[0].meta["layer"] == "device"
    assert len(s.inks) == len(over.inks) - 1          # input untouched
