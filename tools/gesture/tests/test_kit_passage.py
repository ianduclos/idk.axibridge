"""Study B: one line passes through several learned hands, feature by feature."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402

HANDS = ["meander69", "fly_open", "river_belt", "hokusai", "dance_staccato", "mime_roadrunner"]
SMALL = {
    "frame": [140.0, 84.0], "seed": 1384, "margin": 5.0,
    "voice": {"id": "passage", "hands": HANDS, "opening": "none", "rows": 1,
              "R_mm": 75.0, "K": 3, "max_mm": 360.0, "section_length": 5.0,
              "erratic": 0.6, "many": 0.55, "specimen": 0.25, "aware": 0.4},
    "renderer": {"id": "wire", "pen": 0.35},
}


def _run(**voice_params):
    recipe = {**SMALL, "voice": {**SMALL["voice"], **voice_params}}
    return kit.run(recipe)


@pytest.fixture(scope="module")
def small():
    return _run()


def test_passage_voice_is_registered():
    assert "passage" in {entry["id"] for entry in kit.describe()["voice"]}
    assert not {k: v for k, v in kit.DISCOVERY_ERRORS.items() if "passage" in k}


def test_numeric_controls_are_bounded():
    params = next(entry["params"] for entry in kit.describe()["voice"] if entry["id"] == "passage")
    assert all("min" in p and "max" in p for p in params if p["type"] in ("int", "float"))


def test_compose_can_take_four_features_from_four_different_hands():
    from gesture.kit import voices_passage as vp

    source = [
        {"corner": None, "kind": "line", "l": 0.05, "k0": 0.0, "k1": 0.0, "sgn": -1.0},
        {"corner": 1.2, "kind": "arc", "l": 0.04, "k0": 12.0, "k1": 12.0, "sgn": 1.0},
        {"corner": -0.8, "kind": "clothoid", "l": 0.08, "k0": -8.0, "k1": -14.0, "sgn": -1.0},
        {"corner": 0.3, "kind": "arc", "l": 0.02, "k0": 24.0, "k1": 24.0, "sgn": 1.0},
    ]
    segment = vp.compose(source, {"corner": 2, "bend": 1, "turn": 0, "length": 3})
    assert segment["kind"] == "arc"
    assert segment["l"] == pytest.approx(0.02)
    assert segment["corner"] == pytest.approx(-0.8)
    assert segment["sgn"] == -1
    assert segment["k0"] * segment["l"] == pytest.approx(-12.0 * 0.04)
    assert segment["k1"] * segment["l"] == pytest.approx(-12.0 * 0.04)


def test_composed_arc_integrates_to_its_kept_turning_angle():
    from gesture.kit import voices_passage as vp

    segment = {"corner": None, "kind": "arc", "l": 0.02,
               "k0": -24.0, "k1": -24.0, "sgn": -1.0}
    points, _ranges, heading = vp._integrate([segment], (20.0, 20.0), 0.0, 100.0, 0.05)
    curvature = -24.0 / 100.0
    turn = -24.0 * 0.02
    expected = [20.0 + np.sin(turn) / curvature,
                20.0 + (1 - np.cos(turn)) / curvature]
    np.testing.assert_allclose(points[-1], expected, atol=0.01, rtol=0)
    assert heading == pytest.approx(turn)


def test_one_contiguous_wire_line_inside_its_box(small):
    assert len(small.marks) == len(small.inks) == 1
    mark = small.marks[0]
    points = mark.points
    assert len(points) > 100 and np.all(np.isfinite(points))
    assert np.all(np.linalg.norm(np.diff(points, axis=0), axis=1) > 0)
    assert np.all(points[:, 0] >= 5) and np.all(points[:, 0] <= 135)
    assert np.all(points[:, 1] >= 5) and np.all(points[:, 1] <= 79)
    assert np.array_equal(small.inks[0].points, points)
    assert small.inks[0].pen == pytest.approx(0.35)


@pytest.mark.parametrize("hands", [HANDS[:3], HANDS + ["river_bend", "ingres"]])
def test_three_and_eight_hand_lines_keep_valid_sources_and_continuity(hands):
    mark = _run(hands=hands, max_mm=220.0).marks[0]
    points = mark.points
    assert len(points) > 20 and np.all(np.linalg.norm(np.diff(points, axis=0), axis=1) > 0)
    assert np.all((points[:, 0] >= 5) & (points[:, 0] <= 135))
    assert np.all((points[:, 1] >= 5) & (points[:, 1] <= 79))
    assert mark.meta["passage"]["hands"] == hands
    for feature in ("corner", "bend", "turn", "length"):
        values = mark[f"src_{feature}"]
        assert np.all((0 <= values) & (values < len(hands)))
    for entry in mark.meta["passage"]["segment_log"]:
        assert len(entry["sources"]) == len(hands)
        assert all(0 <= int(i) < len(hands) for i in entry["assignment"].values())


def test_duplicate_hands_are_rejected():
    with pytest.raises(ValueError, match="distinct"):
        _run(hands=["meander69", "fly_open", "meander69"])


def test_free_opening_requires_river_belt_among_the_hands():
    recipe = {"frame": [297.0, 210.0], "seed": 1042, "margin": 6.0,
              "voice": {"id": "passage", "opening": "free",
                        "hands": ["meander69", "fly_open", "hokusai"], "K": 2, "max_mm": 80.0}}
    with pytest.raises(ValueError, match="river_belt"):
        kit.run(recipe)


def test_source_channels_are_nearest_and_record_real_hands(small):
    mark = small.marks[0]
    info = mark.meta["passage"]
    assert info["hands"] == HANDS
    used = set()
    for feature in ("corner", "bend", "turn", "length"):
        name = f"src_{feature}"
        values = mark[name]
        assert kit.channel_kind(name) == "nearest"
        assert len(values) == len(mark.points)
        assert np.all(values == np.round(values))
        assert np.all((0 <= values) & (values < len(HANDS)))
        used.update(map(int, values))
    assert len(used) >= 3
    assert kit.channel_kind("section") == kit.channel_kind("n_sources") == "nearest"
    assert set(np.unique(mark["voice"])) <= used
    assert np.all(mark["section"] == np.round(mark["section"]))
    assert np.all(mark["n_sources"] == np.round(mark["n_sources"]))
    assert np.all((mark["n_sources"] >= 1) & (mark["n_sources"] <= 4))


def test_every_composed_feature_comes_whole_from_a_logged_stream(small):
    """Averaged lengths, corners or bend angles must fail this check."""
    log = small.marks[0].meta["passage"]["segment_log"]
    assert len(log) >= 12
    for entry in log:
        src, assignment, out = entry["sources"], entry["assignment"], entry["segment"]
        assert set(assignment) == {"corner", "bend", "turn", "length"}
        assert len(src) == len(HANDS)
        assert all(0 <= assignment[f] < len(HANDS) for f in assignment)
        chosen = {f: src[assignment[f]] for f in assignment}
        assert out["l"] == pytest.approx(chosen["length"]["l"])
        assert out["kind"] == chosen["bend"]["kind"]
        for k in ("k0", "k1"):
            assert abs(out[k] * out["l"]) == pytest.approx(
                abs(chosen["bend"][k] * chosen["bend"]["l"]), abs=1e-8)
        corner = chosen["corner"]["corner"]
        assert (out["corner"] is None) == (corner is None)
        if corner is not None:
            assert abs(out["corner"]) == pytest.approx(abs(corner), abs=1e-8)
            assert np.sign(out["corner"]) == chosen["turn"]["sgn"]
        assert out["sgn"] == chosen["turn"]["sgn"]


def test_many_sections_use_at_least_three_hands(small):
    info = small.marks[0].meta["passage"]
    many_indices = {i for i, s in enumerate(info["sections"]) if s["type"] == "many"}
    assert many_indices
    many_segments = [s for s in info["segment_log"] if s["section"] in many_indices]
    assert many_segments
    assert all(len(set(s["assignment"].values())) >= 3 for s in many_segments)
    assert small.marks[0]["n_sources"].max() >= 3


def test_sections_log_types_and_distance(small):
    sections = small.marks[0].meta["passage"]["sections"]
    assert len(sections) >= 3
    assert [s["start_mm"] for s in sections] == sorted(s["start_mm"] for s in sections)
    assert {s["type"] for s in sections} <= {"hold", "glide", "jolt", "split", "many", "recall"}
    assert all(set(s["assignment"]) == {"corner", "bend", "turn", "length"} for s in sections)


def test_malleable_control_uses_quantile_token_streams():
    plain = _run(malleable=0.0).marks[0].meta["passage"]
    assert plain["morph_batches"] == 0
    assert all(s["dials"] is None for s in plain["sections"])
    malleable = _run(malleable=1.0).marks[0].meta["passage"]
    assert malleable["morph_batches"] > 0
    assert all(set(s["dials"]) == {"turn", "span", "sign"} for s in malleable["sections"])
    assert any(s["dials"]["sign"] != 0 for s in malleable["sections"])


def test_aware_recalls_echo_old_feature_assignment_at_a_joint():
    recipe = {**SMALL, "seed": 1385,
              "voice": {**SMALL["voice"], "aware": 1.0, "recall": 30.0,
                        "recall_gap": 40.0, "clear": 0.3, "max_mm": 700.0}}
    mark = kit.run(recipe).marks[0]
    info = mark.meta["passage"]
    recalls, sections, log = info["recalls"], info["sections"], info["segment_log"]
    assert len(recalls) >= 2
    for event in recalls:
        assert event["s"] - event["from_s"] >= 40.0 - 1e-8
        assert event["distance_mm"] < 30.0
        echoed = next(s for s in sections if s["type"] == "recall"
                      and s["start_mm"] >= event["s"] - 1e-8)
        assert echoed["assignment"] == event["assignment"]
    assert all(b["s"] - a["s"] >= 40.0 - 1e-8 for a, b in zip(recalls, recalls[1:]))
    for i, section in enumerate(sections[1:], 1):
        assert section["boundary"] in {"corner", "turn", "cap"}
        if section["boundary"] == "corner":
            first = next(entry for entry in log if entry["section"] == i)
            assert first["segment"]["corner"] is not None


def test_exact_free_hand_opening_matches_accrue_recipe():
    prior = json.loads((HERE / "results" / "accrue-3-variants.recipe.json").read_text())[2]["recipe"]
    original = kit.run(prior).marks[0].points
    study = kit.run({"frame": [297.0, 210.0], "seed": 1042, "margin": 6.0,
                     "voice": {"id": "passage", "opening": "free", "free_seed": 3966,
                               "hands": HANDS, "rows": 2, "K": 2, "max_mm": 200.0},
                     "renderer": {"id": "wire", "pen": 0.35}})
    mark = study.marks[0]
    n = mark.meta["passage"]["opening"]["points"]
    assert n == len(original)
    np.testing.assert_allclose(mark.points[:n], original, rtol=0, atol=1e-10)
    assert mark.meta["passage"]["opening"]["seed"] == 3966
    assert len(study.marks) == 1
    assert np.all(mark.points[:, 0] >= 6) and np.all(mark.points[:, 0] <= 291)
    assert np.all(mark.points[:, 1] >= 6) and np.all(mark.points[:, 1] <= 204)


def test_free_opening_at_another_origin_is_translation_only():
    from gesture.kit import voices_passage as vp

    prior = json.loads((HERE / "results" / "accrue-3-variants.recipe.json").read_text())[2]["recipe"]
    original = kit.run(prior).marks[0].points
    grammar = kit.library.load("hand", "river_belt")
    translated, info = vp.free_opening(grammar, (17.0, 23.0, 285.0, 198.0), free_seed=3966)
    np.testing.assert_allclose(translated, original + [11.0, 17.0], rtol=0, atol=1e-10)
    assert info["offset"] == [17.0, 23.0]


def test_different_free_seed_changes_the_opening():
    recipe = {"frame": [297.0, 210.0], "seed": 1042, "margin": 6.0,
              "voice": {"id": "passage", "opening": "free", "hands": HANDS,
                        "rows": 2, "K": 2, "max_mm": 80.0}}
    first = kit.run({**recipe, "voice": {**recipe["voice"], "free_seed": 3966}}).marks[0]
    second = kit.run({**recipe, "voice": {**recipe["voice"], "free_seed": 3967}}).marks[0]
    n = min(first.meta["passage"]["opening"]["points"],
            second.meta["passage"]["opening"]["points"])
    assert n > 100
    assert not np.allclose(first.points[:n], second.points[:n])


def test_deterministic_across_hash_seeds():
    code = ("import hashlib,json,sys; sys.path.insert(0,'tools/gesture'); "
            "from gesture import kit; r=json.loads(sys.argv[1]); "
            "m=kit.run(r).marks[0]; "
            "print(hashlib.sha256(m.points.tobytes()+m['src_corner'].tobytes()"
            "+m['src_bend'].tobytes()+m['src_turn'].tobytes()"
            "+m['src_length'].tobytes()).hexdigest())")
    hashes = set()
    for seed in ("1", "77"):
        proc = subprocess.run([sys.executable, "-c", code, json.dumps(SMALL)],
                              cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed},
                              capture_output=True, text=True, check=True)
        hashes.add(proc.stdout.strip().splitlines()[-1])
    assert len(hashes) == 1
