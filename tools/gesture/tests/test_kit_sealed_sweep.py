"""Every built-in Gesture Study that is a plain kit recipe works as a SEALED layer in a v2 score.

The recipes are read from the app's study data (JSON only; nothing is imported from axibridge/).
Studies that are not a plain kit recipe (engine other than "kit") are skipped with the reason.
"""
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesture.kit import _synth as synth  # noqa: E402

STUDIES = ROOT.parents[1] / "axibridge" / "sources" / "_gesture_studies" / "studies"
FRAME = [250, 175]
REGION = [125, 10, 115, 155]
TOL = 0.5


def _load():
    ok, skipped = [], {}
    order = json.loads((STUDIES / "index.json").read_text())["order"]
    for sid in order:
        d = json.loads((STUDIES / sid / "study.json").read_text())
        if d.get("engine") != "kit":
            skipped[sid] = f"engine {d.get('engine')!r}: not a plain kit recipe"
        else:
            ok.append((sid, d["recipe"]))
    return ok, skipped


STUDY_RECIPES, SKIPPED = _load()


def build(recipe):
    composer = {k: copy.deepcopy(v) for k, v in recipe.items() if k not in ("frame", "seed")}
    return {"version": 2, "frame": FRAME, "seed": 16001,
            "layers": [{"id": "A", "pen": "black", "part": {"voice": {"id": "hand", "hand": "marden"}}},
                       {"id": "S", "role": "sealed", "pen": "blue", "region": REGION, "composer": composer}],
            "relations": [{"id": "X", "kind": "crossing", "src": "*", "dst": "*"}]}


def s_inks(sh):
    return [i for i in sh.inks if i.meta.get("score_layer") == "S"]


def digest(inks):
    return [np.round(i.points, 6).tobytes() for i in inks]


# drawing_and_measure draws ~1.4 mm past its own frame even standalone (its chart labels); a sealed layer
# confines where a composer draws, it doesn't clip what the composer draws, so this stays the study's own.
OVERFLOWS = {"drawing_and_measure": "the study draws past its own frame standalone too (chart labels)"}
CASES = [pytest.param(sid, rec, id=sid,
                      marks=pytest.mark.xfail(raises=AssertionError, strict=True, reason=OVERFLOWS[sid]))
         if sid in OVERFLOWS else pytest.param(sid, rec, id=sid) for sid, rec in STUDY_RECIPES]


@pytest.mark.parametrize("sid,recipe", CASES)
def test_study_as_sealed_layer(sid, recipe):
    t0 = time.time()
    score = build(recipe)
    synth.validate(score)
    sh = synth.run(score, cache=False)

    x, y, w, h = REGION
    pts = [m.points for m in sh.marks if m.meta.get("score_layer") == "S" and len(m.points)]
    assert pts, f"{sid}: no S marks"
    P = np.vstack(pts)
    assert P[:, 0].min() >= x - TOL and P[:, 0].max() <= x + w + TOL, (sid, P[:, 0].min(), P[:, 0].max())
    assert P[:, 1].min() >= y - TOL and P[:, 1].max() <= y + h + TOL, (sid, P[:, 1].min(), P[:, 1].max())
    inks = s_inks(sh)
    assert inks, f"{sid}: S has no inks"

    log = synth.played(sh)["log"]
    xs = [e for e in log if e.get("kind") == "crossing" and {e.get("src"), e.get("dst")} == {"A", "S"}]
    a = np.vstack([m.points for m in sh.marks if m.meta.get("score_layer") == "A"])
    box_overlap = (a[:, 0].max() >= x and a[:, 0].min() <= x + w and a[:, 1].max() >= y and a[:, 1].min() <= y + h)
    if box_overlap:
        # A's extent reaches S's region; whether strokes truly cross is the relation's call, so check the
        # geometry independently where possible.
        from gesture.kit._relations import crossings  # noqa: PLC0415
        am = [m for m in sh.marks if m.meta.get("score_layer") == "A"]
        sm = [m for m in sh.marks if m.meta.get("score_layer") == "S"]
        if crossings(am, sm):
            assert xs, f"{sid}: A and S cross but the crossing relation logged no A/S event"

    pinned = synth.pin(score, ["S"])
    layer = next(L for L in pinned["layers"] if L["id"] == "S")
    assert layer.get("seed") is not None and layer.get("lock")
    again = synth.run(pinned, cache=False)
    assert digest(s_inks(again)) == digest(inks), f"{sid}: pinned replay changed S inks"
    print(f"\n[sealed-sweep] {sid}: {time.time() - t0:.1f}s, {len(inks)} inks, {len(xs)} A/S events")


def test_skipped_studies_are_listed():
    print("\n[sealed-sweep] skipped:", SKIPPED)
    assert set(SKIPPED) == {"hand_drift", "sampler"}
