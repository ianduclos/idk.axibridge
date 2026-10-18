"""Study A: real found-ground catches, hand answers, and the R4 contact gate."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import core  # noqa: E402
from gesture.kit import arrangers_found_play as fp  # noqa: E402
from experiments import study_a  # noqa: E402
from experiments.study_a import recipe as _study_recipe  # noqa: E402


def _recipe(seed=1322, lines=4, **arr):
    return _study_recipe(seed, lines=lines, **arr)


def _play(sheet):
    return sheet.marks[0].meta["found_play"]


def _made(sheet):
    return [m for m in sheet.marks if m.meta.get("of_role") == "made"]


def _codes(sheet):
    return set(np.concatenate([np.asarray(m["neg"]).astype(int) for m in _made(sheet)]))


def _digest(sheet):
    """Include categorical channels and the decisions, not only rendered geometry."""
    h = hashlib.sha256()
    for m in sheet.marks:
        h.update(np.round(m.points, 6).tobytes())
        for name in sorted(m.channels):
            h.update(name.encode())
            h.update(np.round(np.asarray(m.channels[name]), 6).tobytes())
    for ink in sheet.inks:
        h.update(np.round(ink.points, 6).tobytes())
    h.update(json.dumps(_play(sheet), sort_keys=True).encode())
    h.update(json.dumps(sheet.marks[0].meta["rules"], sort_keys=True).encode())
    return h.hexdigest()


@pytest.fixture(scope="module")
def piece():
    return kit.run(_recipe())


@pytest.fixture(scope="module")
def answering_piece():
    return kit.run(_recipe(1319, lines=6))


@pytest.fixture(scope="module")
def gated_pair():
    common = {"breaks": False, "listen_k": 2.0}
    return (kit.run(_recipe(**common)),
            kit.run(_recipe(rules="R1,R2,R3,R5", **common)))


def test_registered_and_importable():
    core.discover()
    assert not any("found_play" in k for k in kit.DISCOVERY_ERRORS)
    assert "found_play" in core.registry("arranger")
    kit.validate(_recipe())


def test_real_piece_carries_river_chart_and_hand(piece):
    assert {6, 7, 8, 9} <= _codes(piece)
    caught = {e["caught"] for e in _play(piece)["infections"]}
    assert {"river", "plate"} <= caught
    assert all(e["carried_mm"] > 0 for e in _play(piece)["infections"])
    assert all(len(e[key]) == 2 for e in _play(piece)["infections"]
               for key in ("contact", "onset", "end"))


def test_later_line_catches_an_earlier_lines_hand(piece):
    hands = [e for e in _play(piece)["infections"] if e["caught"].startswith("line")]
    assert hands
    for e in hands:
        assert 0 <= int(e["caught"][4:]) < e["line"]
    assert any(np.any(np.asarray(m["neg"]) == 9)
               for m in _made(piece) if m.meta["line"] in {e["line"] for e in hands})


def test_answers_and_refusals_record_real_decisions(answering_piece):
    play = _play(answering_piece)
    assert play["answers"] and play["refusals"]
    assert len(play["calls"]) == 6
    for e in play["answers"] + play["refusals"]:
        assert 0 <= e["to"] < e["line"] < 6
    answered = {e["line"] for e in play["answers"]}
    assert any(np.any(np.asarray(m["neg"]) == 10)
               for m in _made(answering_piece) if m.meta["line"] in answered)
    assert any(e["rule"] == "CALL" for e in answering_piece.marks[0].meta["rules"]["log"])


def test_chart_needles_are_open_and_keep_both_measured_sides():
    # Two complete out-and-back ticks on a straight carrier. A collapsed base
    # or a fixed side would turn the chart's needles back into a comb.
    points = np.array([[-1, 0], [0, 0], [0, 9], [0, 0], [1, 0],
                       [2, 0], [3, 0], [3, 9], [3, 0], [4, 0]], float)
    codes = np.array([0, 0, 5, 5, 0, 0, 0, 5, 5, 0])
    q = fp.chart_needles(points, codes, {"needle_mm": [-7, 9], "needle_base_mm": 0.8})
    assert np.array_equal(points[[2, 7], 1], [9, 9])  # the source stays immutable
    assert np.array_equal(q[[2, 7], 1], [-7, 9])
    assert np.all(np.linalg.norm(q[[1, 6]] - q[[3, 8]], axis=1) > 0.5)
    assert np.array_equal(q[[0, 4, 5, 9]], points[[0, 4, 5, 9]])


def test_carried_chart_needles_retain_the_chart_hairline(piece):
    needles = [m for m in _made(piece) if np.any(np.asarray(m["neg"])[1:] == 8)]
    assert needles
    assert all(m.meta["pen"] <= piece.recipe["arranger"]["hair_pen"] for m in needles)


def test_answer_touches_callers_endpoint_and_continues_beyond_it():
    sheet = kit.run(_recipe(answer_p=1.0, call_reach=400.0, cover_after=-1, rules="R1,R3,R4"))
    assert len(_play(sheet)["answers"]) == 3
    for answer in _play(sheet)["answers"]:
        caller = [m for m in _made(sheet) if m.meta["line"] == answer["to"]][-1].points[-1]
        trace = np.vstack([m.points[np.asarray(m["neg"]) == 10] for m in _made(sheet)
                           if m.meta["line"] == answer["line"]])
        assert np.min(np.linalg.norm(trace - caller, axis=1)) < 1e-8
        assert np.linalg.norm(np.array(answer["departure"]) - answer["root"]) > 2.0


def test_map_exports_recipe_and_preserves_piece_geometry(piece, tmp_path):
    from PIL import Image
    before = _digest(piece)
    path = study_a.save_map(piece, tmp_path / "map.jpg", px=2)
    with Image.open(path) as im:
        assert im.width == 600 and im.height > 400   # legend is outside the drawing
    assert json.loads(path.with_suffix(".recipe.json").read_text()) == piece.recipe
    assert len({name for _, _, name in study_a.MAP_CODES}) == 8
    assert _digest(piece) == before


def test_r4_closes_contact_gate_and_omitting_it_opens_gate(gated_pair):
    closed, opened = gated_pair
    assert not _play(closed)["infections"]
    assert not (_codes(closed) & {1, 4, 6, 7, 8, 9})
    assert _play(opened)["infections"]
    assert _codes(opened) & {6, 7, 8, 9}


def test_disabling_breaks_also_disables_the_thin_needle_exception():
    sheet = kit.run(_recipe(breaks=False, listen_k=0.0))
    assert 8 in _codes(sheet)
    assert all(e["event"] == "fire" for e in sheet.marks[0].meta["rules"]["log"]
               if e["rule"] in {"R1", "R2", "R3", "R4", "R5"})


def _assert_in_frame(sheet):
    width, height = sheet.recipe["frame"]
    for m in _made(sheet):
        assert np.isfinite(m.points).all()
        assert np.all(m.points >= -1e-6)
        assert np.all(m.points <= np.array([width, height]) + 1e-6)
        raw = np.asarray(m["neg"])
        assert np.array_equal(raw, raw.astype(int))
        assert set(raw.astype(int)) <= {0, 1, 3, 4, 5, 6, 7, 8, 9, 10}


def test_made_points_stay_inside_actual_frame(piece, answering_piece, gated_pair):
    for sheet in (piece, answering_piece, *gated_pair):
        _assert_in_frame(sheet)


@pytest.mark.parametrize("lines", [6, 7, 8])
def test_seed_1339_keeps_answer_bridge_inside_paper(lines):
    _assert_in_frame(kit.run(_recipe(1339, lines)))


@pytest.mark.parametrize("lines", [7, 8])
def test_recipe_supplies_and_draws_requested_lines(lines):
    recipe = _recipe(lines=lines)
    assert len(recipe["parts"]) - recipe["arranger"]["found"] >= lines
    sheet = kit.run(recipe)
    assert {m.meta["line"] for m in _made(sheet)} == set(range(lines))
    assert {e["line"] for e in _play(sheet)["calls"]} == set(range(lines))
    _assert_in_frame(sheet)


def test_deterministic_across_hash_seeds_including_channels_and_decisions(piece):
    code = ("import sys; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
            "from test_kit_found_play import _recipe, _digest\nfrom gesture import kit\n"
            "print(_digest(kit.run(_recipe())))") % (str(HERE), str(HERE / "tests"))
    digests = set()
    for seed in ("1", "77"):
        proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                              env={**os.environ, "PYTHONHASHSEED": seed},
                              capture_output=True, text=True, check=True, timeout=60)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert digests == {_digest(piece)}


@pytest.mark.parametrize("params", [{"lines": 0}, {"lines": 13}, {"listen_k": 2.1},
                                    {"answers": -1}, {"answer_p": 1.1}, {"step": 0.0}])
def test_numeric_controls_are_bounded(params):
    with pytest.raises(ValueError):
        kit.validate(_recipe(**params))


@pytest.mark.parametrize("params", [{"rules": "R9"}, {"made_ink": "unknown"}])
def test_unknown_rules_and_ink_are_refused(params):
    with pytest.raises(ValueError):
        kit.run(_recipe(**params))
