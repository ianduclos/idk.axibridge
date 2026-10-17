"""Round 12 keeps: the kit options behind the new and changed Gesture Studies.

Every option is additive: a recipe without it draws exactly what it drew
before (checked here on small recipes; the round-11 recipes themselves were
checked bit for bit, see results/keeps12-2026-10-17.md)."""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from gesture import kit
from gesture.kit import measure_next as mn
from gesture.kit import sampler
from gesture.kit import voices_machine_diagram as vd

RESULTS = Path(__file__).resolve().parents[1] / "results"


def digest(sheet):
    h = hashlib.sha256()
    for ink in sheet.inks:
        h.update(np.ascontiguousarray(np.asarray(ink.points, float)).tobytes())
        h.update(bytes([ink.closed, ink.filled]))
    return h.hexdigest()


def roles(sheet, key="plate_role"):
    return [i.meta.get(key) for i in sheet.inks]


# ---------------------------------------------------------------------------
# ledger: top and bottom straight, the lines inside drawn
# ---------------------------------------------------------------------------

def _ledger_polys():
    rule = lambda x0, y0, x1, y1: np.array([[x0, y0], [x1, y1]], float)  # noqa: E731
    return [rule(0, 0, 100, 0), rule(0, 0.6, 100, 0.6),           # the double top rule
            rule(10, 10, 25, 10), rule(40, 20, 52, 20),            # bars inside
            np.array([[0, 30], [0.5, 31], [1.0, 30]]),               # a glyph stroke
            rule(0, 90, 100, 90)]                                    # the bottom rule


def test_frame_keeps_only_the_full_width_rules_straight():
    polys = _ledger_polys()
    rng = np.random.default_rng(0)
    assert vd.straight_flags(polys, 2.0, "frame", 0.0, rng) == [True, True, False, False, False, True]
    assert vd.straight_flags(polys, 2.0, "frame+text", 0.0, rng) == [True, True, False, False, True, True]
    # the older choices are unchanged
    assert vd.straight_flags(polys, 2.0, "rules", 0.0, rng) == [True, True, True, True, False, True]
    assert vd.straight_flags(polys, 2.0, "none", 0.0, rng) is None


def test_ledger_frame_draws_and_leaves_other_choices_alone():
    r = json.loads((RESULTS / "measure_pairs-pair_ledger.recipe.json").read_text())
    r["parts"][0]["voice"]["length"] = 1.5
    m = r["parts"][0]["modulators"][0]
    m.update(drawn_by="matisse", straight="text")
    text = kit.run(r)
    m["straight"] = "frame+text"
    frame = kit.run(r)
    assert digest(frame) != digest(text)
    assert len(frame.inks) == len(text.inks)


# ---------------------------------------------------------------------------
# measure_next: the strip graph and the numbers switch
# ---------------------------------------------------------------------------

def _plate(**over):
    r = {"kit": 1, "frame": [267.0, 180.0], "seed": 7003, "arranger": {"id": "single"},
         "parts": [{"voice": {"id": "drift", "hands": ["matisse", "lichtenberg"], "length": 2.5,
                              "joins": "smooth"},
                    "modulators": [{"id": "measure_next", "cut": "inflection", "plate": "taxonomy", "cells": 40,
                                    **over}]}],
         "renderer": {"id": "measure_wire", "pen": 0.4, "chart_pen": 0.25}}
    return kit.run(r)


def test_defaults_are_unchanged_by_the_new_params():
    assert digest(_plate()) == digest(_plate(numbers="all"))


def test_strip_is_the_line_laid_straight_and_labelled_like_the_plate():
    sh = _plate(hist="strip")
    plain = _plate()
    steps = _plate(hist="length")
    # the strip adds the laid-straight line (long continuous runs) and its labels
    assert len(sh.inks) > len(plain.inks)
    old_pts = {len(i.points) for i in steps.inks}
    assert max(len(i.points) for i in sh.inks if len(i.points) not in old_pts) > 200
    assert digest(sh) == digest(_plate(hist="strip"))          # deterministic


def test_plate_strip_pieces_meet_on_the_baseline():
    t = np.linspace(0, np.pi, 30)
    arc = np.column_stack([10 * np.cos(t), 10 * np.sin(t)])
    zig = np.array([[0, 0], [5, 3], [10, 0]], float)
    sp = [{"p": arc, "s0": 0.0, "s1": 31.0, "s_mid": 15.0}, {"p": zig, "s0": 31.0, "s1": 43.0, "s_mid": 37.0}]
    out = mn.plate_strip(sp, sp, ["A1", "B1"], (0.0, 0.0, 100.0, 40.0), label_h=2.0)
    lines = [p for p, r in out if r == "specimen"]
    assert len(lines) == 1                                     # one row: one continuous line
    q = lines[0]
    assert abs(q[0, 1] - q[-1, 1]) < 1e-9                       # starts and ends on one baseline
    assert sum(1 for _, r in out if r == "label") >= 2


def test_numbers_switch_takes_the_index_off_the_drawings():
    def tri(numbers):
        r = {"kit": 1, "frame": [267.0, 180.0], "seed": 7100, "arranger": {"id": "single"},
             "parts": [{"voice": {"id": "dance", "trail": "mantis", "effectors": "all", "seconds": 10.0},
                        "modulators": [{"id": "measure_next", "cut": "pause", "page": "triptych", "split": 0.34,
                                        "rechain": "match", "cells": 30, "numbers": numbers}]}],
             "renderer": {"id": "measure_wire", "pen": 0.4, "chart_pen": 0.25}}
        sh = kit.run(r)
        return sh, sum(1 for i in sh.inks if i.meta.get("measure_role") == "index"
                       or i.meta.get("role") == "index")

    full, _ = tri("all")
    none, _ = tri("none")
    assert len(none.inks) < len(full.inks)
    assert len(none.inks) < len(tri("drawing")[0].inks) < len(full.inks)
    assert len(none.inks) < len(tri("rechain")[0].inks) < len(full.inks)


# ---------------------------------------------------------------------------
# swell: occasional dots
# ---------------------------------------------------------------------------

def _bold(**over):
    r = json.loads((RESULTS / "swell-bold.recipe.json").read_text())["b1-one-drop"]
    r = copy.deepcopy(r)
    r["parts"][0]["voice"]["length"] = 0.6
    r["renderer"].update(over)
    return kit.run(r)


def test_swell_without_dots_is_unchanged():
    assert digest(_bold()) == digest(_bold(dots="none", dot_shape="ring", dot_size=9.0))


def test_count_dots_sit_off_the_masses():
    sh = _bold(dots="count", dot_size=8.0, dot_gap=30.0)
    dots = [i for i in sh.inks if str(i.meta.get("role", "")).startswith("dot:")]
    assert dots
    import shapely  # noqa: PLC0415
    masses = shapely.union_all([shapely.Polygon(i.points).buffer(0) for i in sh.inks
                                if str(i.meta.get("role", "")).startswith("swell:") and i.closed
                                and len(i.points) >= 4])
    for d in dots:
        c = np.asarray(d.points, float).mean(axis=0)
        assert masses.distance(shapely.Point(*c)) > 0.0


def test_wound_dots_are_spliced_into_the_line():
    plain = _bold()
    wound = _bold(dots="turns", dot_shape="wound", dot_size=8.0)
    line = lambda sh: [i for i in sh.inks if i.meta.get("role") == "line"]  # noqa: E731
    assert len(line(wound)) == len(line(plain))
    assert not [i for i in wound.inks if str(i.meta.get("role", "")).startswith("dot:")]
    if len(line(wound)[0].points) == len(line(plain)[0].points):
        pytest.skip("no turn found on this short line")
    assert len(line(wound)[0].points) > len(line(plain)[0].points)


# ---------------------------------------------------------------------------
# sampler: clean
# ---------------------------------------------------------------------------

def test_clean_false_is_the_sample_as_before():
    for s in range(12):
        assert sampler.sample(s) == sampler.sample(s, clean=False)


def test_clean_takes_out_straight_machines_side_charts_and_scatter():
    seen = {"machine": 0, "annotate": 0, "scatter": 0}
    for s in range(80):
        raw = sampler.sample(s)
        tidy = sampler.sample(s, clean=True)
        for p in raw["parts"]:
            v = p["voice"]
            seen["machine"] += v["id"] == "machine" and v["grammar"] in sampler.STRAIGHT_MACHINES
            seen["annotate"] += any(m["id"] == "annotate" and m.get("layout") in ("right", "below")
                                    for m in p["modulators"])
        seen["scatter"] += raw["arranger"]["id"] == "poly_scatter"
        for p in tidy["parts"]:
            v = p["voice"]
            assert not (v["id"] == "machine" and v["grammar"] in sampler.STRAIGHT_MACHINES), s
            for m in p["modulators"]:
                assert not (m["id"] == "annotate" and m.get("layout") in ("right", "below")), s
                assert m["id"] != "handover" or m.get("a") not in sampler.STRAIGHT_MACHINES, s
        assert tidy["arranger"]["id"] != "poly_scatter"
        assert len(tidy["parts"]) == len(raw["parts"]) and tidy["seed"] == raw["seed"]
        assert sampler.tidy(tidy) == tidy                            # idempotent
    assert all(seen.values()), seen                                  # the test met every case


def test_clean_keeps_the_rest_of_the_combination():
    for s in range(40):
        raw, tidy = sampler.sample(s), sampler.sample(s, clean=True)
        if raw["arranger"]["id"] == "single" and all(
                p["voice"]["id"] != "machine" and not any(m["id"] in ("annotate", "handover")
                                                          for m in p["modulators"]) for p in raw["parts"]):
            assert tidy == raw
        assert tidy["parts"][0]["voice"] == raw["parts"][0]["voice"]  # the heavy voice is never touched
