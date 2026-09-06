"""Second Reading: an intervention-recorded process, not a live drawing tool.

These assertions deliberately use the public module and project APIs.  The
important promise is replay: an old moment remains exactly drawable while a
later choice changes only the continuation.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from axibridge.model import Path
from axibridge.registry import describe_modules, get_source, load_builtin_modules
from axibridge.sources.second_reading import SecondReadingParams
from axibridge.sources import _second_reading as engine
from axibridge import trajectory


load_builtin_modules()


def _source():
    return get_source("second_reading")


def _paths(**params):
    doc = _source().generate(SecondReadingParams(**params))
    return [path for layer in doc.layers for path in layer.paths]


def _points(**params):
    return [tuple(path.points) for path in _paths(**params)]


def _state(turn: int, **params):
    return _points(turns=turn, **params)


def _event(kind: str, turn: int, **data):
    return {"kind": kind, "turn": turn, **data}


def test_it_is_a_bounded_accumulative_process_with_the_interactive_descriptor():
    src = _source()
    assert src.time_axis == "turns"
    assert src.accumulative is True
    assert src.orientation == "geometry"
    assert src.bench_capabilities == ("intervene", "branch")

    item = next(s for s in describe_modules()["sources"] if s["id"] == "second_reading")
    assert item["time_axis"] == "turns"
    assert item["bench_capabilities"] == ["intervene", "branch"]

    schema = item["schema"]["properties"]
    assert (schema["turns"]["minimum"], schema["turns"]["maximum"],
            item["defaults"]["turns"]) == (0, 64, 12)
    assert (schema["width"]["minimum"], schema["width"]["maximum"],
            item["defaults"]["width"]) == (40, 300, 280)
    assert (schema["height"]["minimum"], schema["height"]["maximum"],
            item["defaults"]["height"]) == (40, 218, 198)
    assert (schema["seed"]["minimum"], schema["seed"]["maximum"],
            item["defaults"]["seed"]) == (0, 2_147_483_647, 0)
    for name in ("persistence", "reach", "recurrence"):
        assert (schema[name]["minimum"], schema[name]["maximum"],
                item["defaults"][name]) == (0, 1, 0.5)
    events = schema["events"]
    assert events["hidden"] is True
    assert events["items"]["discriminator"]["propertyName"] == "kind"
    assert len(events["items"]["oneOf"]) == 3


def test_turn_zero_establishes_two_unequal_opening_passages():
    opening = _state(0, seed=8)
    assert len(opening) == 2
    assert all(len(path) >= 2 for path in opening)
    assert opening[0] != opening[1], "the opening needs unequal commitments"


def test_each_machine_turn_adds_a_passage_and_later_states_keep_an_exact_prefix():
    src = _source()
    traj = src.trajectory(SecondReadingParams(turns=64, seed=13))
    assert len(traj.steps[0]) == 2
    assert all(traj.steps[n] for n in range(1, 65))

    full = _state(64, seed=13)
    for turn in (0, 1, 2, 7, 21, 64):
        assert _state(turn, seed=13) == full[:len(_state(turn, seed=13))]


def test_future_choices_cannot_rewrite_the_visible_past():
    """A branch is a continuation choice, not a new random seed for turn 0."""
    plain = _state(18, seed=4)
    future = [
        _event("controls", 19, persistence=0.9, reach=0.1, recurrence=0.8),
        _event("branch", 20, seed=99),
        _event("stroke", 21, points=[[24.0, 31.0], [70.0, 42.0], [91.0, 75.0]]),
    ]
    assert _state(18, seed=4, events=future) == plain


def test_same_active_branch_and_turn_are_cache_cold_deterministic():
    params = dict(
        turns=31, seed=7,
        events=[_event("branch", 9, seed=91)],
    )
    trajectory.clear_cache()
    first = _points(**params)
    trajectory.clear_cache()
    second = _points(**params)
    assert first == second

    # This event is beyond the current turn.  It must not affect the active
    # branch's random stream while the past is being replayed.
    later = {**params, "events": [*params["events"], _event("branch", 44, seed=1234)]}
    assert _points(**later) == first


def test_a_branch_preserves_its_exact_prefix_then_changes_its_continuation():
    base = _state(29, seed=3)
    branched = _state(29, seed=3, events=[_event("branch", 11, seed=71)])
    assert branched[:len(_state(10, seed=3))] == _state(10, seed=3)
    assert branched != base, "a branch needs to offer a real alternative"


def test_a_human_stroke_occupies_its_turn_and_is_directly_targetable():
    stroke = [[33.0, 44.0], [88.0, 52.0], [117.0, 96.0]]
    traj = _source().trajectory(SecondReadingParams(
        turns=16, seed=6, recurrence=0, events=[
            _event("stroke", 8, points=stroke),
        ]))
    assert tuple(map(tuple, stroke)) in [tuple(path.points) for path in traj.steps[8]]
    assert len(traj.steps[8]) == 1, "the human passage owns its turn"

    assert traj.metadata[8]["action"] == "human"
    human_id = traj.metadata[8]["passage_id"]
    # Recurrence zero explicitly attends the latest passage, independent of
    # the gesture's geometry and of arbitrary branch seed coincidences.
    target_ids = traj.metadata[9].get("target_passage_ids", [])
    assert human_id in target_ids, "a later machine turn must be able to target a human passage"
    assert all(isinstance(passage_id, int) and passage_id >= 0 for passage_id in target_ids)


def test_capture_smoothing_removes_chatter_but_pins_real_corners_and_endpoints():
    from axibridge.sources._second_reading_gestures import smooth_capture

    raw = [(float(i), 30.0 + (.1 if i % 2 else -.1)) for i in range(101)]
    raw[0], raw[-1] = (0.0, 30.0), (100.0, 30.0)
    smoothed = smooth_capture(raw)
    assert sum(abs(y-30) for _, y in smoothed)/len(smoothed) < .025
    assert smoothed[0] == raw[0] and smoothed[-1] == raw[-1]

    corner = [(float(i), 20.0) for i in range(21)] + [(20.0, float(i)) for i in range(21, 41)]
    result = smooth_capture(corner)
    assert (20.0, 20.0) in result
    assert all(y == 20 or x == 20 for x, y in result)
    assert result[0] == corner[0] and result[-1] == corner[-1]


def test_soft_bends_are_rounded_without_changing_the_recorded_human_input():
    raw = [(20.0, 40.0), (70.0, 40.0), (110.0, 65.0)]
    params = SecondReadingParams(turns=5, events=[
        _event("stroke", 5, points=raw, smoothing=.6)])
    before = params.model_dump()
    curve = _source().trajectory(params).steps[5][0].points
    assert len(curve) > len(raw)
    assert raw[1] not in curve, "a soft bend is rounded, not falsely pinned as a corner"
    assert curve[0] == raw[0] and curve[-1] == raw[-1]
    assert params.model_dump() == before
    assert all(20 <= x <= 110 and 40 <= y <= 65 for x, y in curve)
    earlier = _state(4, seed=0)
    assert _source().trajectory(params).state(4) == _paths(turns=4, seed=0)
    assert earlier


def test_organic_echo_develops_a_curve_and_still_tracks_the_actual_passage():
    import random
    target = engine.describe(0, [Path(points=[(80, 100), (150, 100)])], "organic", "human")
    moved = engine.describe(0, [Path(points=[(88, 107), (158, 107)])], "organic", "human")
    commitment = engine.Commitment("echo", (0,), 3, 1)
    paths, construction = engine.make_action(commitment, [target], .5, 300, 218, random.Random(4))
    shifted, _ = engine.make_action(commitment, [moved], .5, 300, 218, random.Random(4))
    assert construction == "organic"
    points = [p for path in paths for p in path.points]
    moved_points = [p for path in shifted for p in path.points]
    assert max(y for _, y in points)-min(y for _, y in points) > 1.0
    assert len(points) == len(moved_points)
    for (x, y), (mx, my) in zip(points, moved_points):
        assert (mx, my) == pytest.approx((x+8, y+7), abs=1e-8)


def test_organic_hand_can_break_a_curve_without_making_every_sample_jitter():
    import random
    from axibridge.sources._second_reading_gestures import follow

    def turns(paths):
        result = []
        for path in paths:
            for a, b, c in zip(path.points, path.points[1:], path.points[2:]):
                u, v = engine.unit(engine.sub(b, a)), engine.unit(engine.sub(c, b))
                result.append(math.acos(max(-1, min(1, u[0]*v[0]+u[1]*v[1]))))
        return result

    guide = [(30.0, 40.0), (100.0, 80.0), (200.0, 60.0)]
    flowing = follow(guide, random.Random(1), allow_break=False)
    broken = follow(guide, random.Random(1), allow_break=True)
    assert max(turns(flowing)) <= .33
    assert len(broken) > 1 or max(turns(broken)) > .6


def test_smoothing_is_bounded_and_legacy_strokes_stay_verbatim():
    from axibridge.sources._second_reading_gestures import smooth_capture
    raw = [(float(i % 200), 70.0 + 10*math.sin(i*.08)) for i in range(20_000)]
    assert len(smooth_capture(raw)) <= 20_000
    assert smooth_capture(raw, 0) == raw
    with pytest.raises(ValidationError):
        SecondReadingParams(events=[_event("stroke", 1, points=[[1, 1], [2, 2]], smoothing=1.1)])


def test_a_noop_control_event_is_observationally_inert():
    base = dict(turns=27, seed=12, persistence=0.5, reach=0.5, recurrence=0.5)
    assert _points(**base) == _points(
        **base,
        events=[_event("controls", 9, persistence=0.5, reach=0.5, recurrence=0.5)],
    )


@pytest.mark.parametrize("bad", [
    [_event("stroke", 1, points=[[1.0, 1.0]])],
    [_event("stroke", 1, points=[[1.0, 1.0], [float("nan"), 2.0]])],
    [_event("stroke", 1, points=[[1.0, 1.0], [float("inf"), 2.0]])],
    [_event("stroke", 1, points=[[-0.1, 1.0], [2.0, 2.0]])],
    [_event("stroke", 1, points=[[1.0, 1.0], [301.0, 2.0]])],
    [_event("controls", 1)],
    [_event("controls", 1, persistence=1.1)],
    [_event("branch", 1, seed=-1)],
    [_event("branch", 1, seed=2_147_483_648)],
    [_event("stroke", 2, points=[[1.0, 1.0], [2.0, 2.0]]),
     _event("stroke", 2, points=[[3.0, 3.0], [4.0, 4.0]])],
    [_event("stroke", 2, points=[[1.0, 1.0], [2.0, 2.0]]),
     _event("branch", 2, seed=4)],
    [_event("controls", 0, reach=0.2)],
    [_event("branch", 65, seed=4)],
])
def test_event_model_refuses_non_actionable_or_unsafe_records(bad):
    with pytest.raises((ValidationError, ValueError)):
        SecondReadingParams(events=bad)


def test_event_order_is_explicit_and_controls_then_branch_precede_stroke():
    valid = [
        _event("controls", 7, reach=0.2),
        _event("branch", 7, seed=9),
        _event("stroke", 7, points=[[10.0, 20.0], [20.0, 30.0]]),
    ]
    SecondReadingParams(events=valid)

    # Controls and branch are independent state changes at the same turn, so
    # either order is the same recipe.  Only their position before the human
    # passage is significant.
    assert _points(turns=16, seed=4, events=valid) == _points(
        turns=16, seed=4, events=[valid[1], valid[0], valid[2]])

    for reordered in (
        [valid[0], valid[2], valid[1]],
        [valid[0], _event("branch", 6, seed=9)],
    ):
        with pytest.raises((ValidationError, ValueError)):
            SecondReadingParams(events=reordered)


def test_event_count_and_total_input_density_are_bounded():
    events = [event for turn in range(1, 65) for event in (
        _event("controls", turn, persistence=0.25),
        _event("branch", turn, seed=turn),
    )]
    assert len(events) == 128
    SecondReadingParams(events=events)
    with pytest.raises((ValidationError, ValueError)):
        SecondReadingParams(events=events + [
            _event("stroke", 64, points=[[1.0, 1.0], [2.0, 2.0]])])

    # The 64 legal turns cannot by themselves exercise the global point cap,
    # so use one otherwise legal event whose captured density exceeds it.
    too_dense = [[float(i % 300), float((i // 300) % 218)] for i in range(20_001)]
    with pytest.raises((ValidationError, ValueError)):
        SecondReadingParams(events=[_event("stroke", 1, points=too_dense)])


def test_extreme_legal_parameters_stay_finite_and_on_the_requested_sheet():
    for params in (
        dict(turns=64, width=40, height=40, seed=0,
             persistence=0, reach=0, recurrence=0),
        dict(turns=64, width=300, height=218, seed=2_147_483_647,
             persistence=1, reach=1, recurrence=1),
    ):
        for path in _paths(**params):
            for x, y in path.points:
                assert math.isfinite(x) and math.isfinite(y)
                assert 0.0 <= x <= params["width"]
                assert 0.0 <= y <= params["height"]


def _passage(passage_id, points, construction="angular"):
    return engine.describe(passage_id, [Path(points=points)], construction, "opening")


def test_engine_describe_records_the_geometric_handle_without_retaining_a_point_index():
    passage = _passage(4, [(2.0, 3.0), (6.0, 3.0), (6.0, 9.0)])
    assert passage.id == 4
    assert passage.bbox == (2.0, 3.0, 6.0, 9.0)
    assert passage.centre == (4.0, 6.0)
    assert passage.endpoints == ((2.0, 3.0), (6.0, 9.0))
    assert passage.length == pytest.approx(10.0)
    assert passage.direction == pytest.approx(engine.unit((4.0, 6.0)))


def test_engine_echo_applies_one_affine_to_a_whole_passage():
    target = engine.describe(4, [
        Path(points=[(2.0, 2.0), (6.0, 2.0)]),
        Path(points=[(2.0, 5.0), (6.0, 5.0)]),
    ], "angular", "opening")
    echoed = engine.echo(target, offset=(8.0, -3.0), scale=1.5)
    # Centre is (4, 3.5), so each component moves by the same affine map.
    assert [path.points for path in echoed] == [
        [(9.0, -1.75), (15.0, -1.75)],
        [(9.0, 2.75), (15.0, 2.75)],
    ]


def test_engine_extend_starts_at_the_exact_terminal_endpoint_and_follows_its_tangent():
    target = _passage(4, [(1.0, 1.0), (5.0, 1.0), (9.0, 4.0)])
    extension = engine.extend(target, distance=20.0, bend=0.5)[0].points
    assert extension[0] == (9.0, 4.0)
    step = engine.unit(engine.sub(extension[1], extension[0]))
    assert step == pytest.approx(engine.unit((4.0, 3.0)))


def test_engine_traverse_joins_the_closest_pair_of_passage_endpoints():
    first = _passage(1, [(0.0, 0.0), (10.0, 0.0)])
    second = _passage(2, [(13.0, 0.0), (40.0, 0.0)])
    route = engine.traverse(first, second, bend=2.0)[0].points
    assert route[0] == (10.0, 0.0)
    assert route[-1] == (13.0, 0.0)


def test_engine_concentrate_is_a_bounded_local_family_not_a_sheet_scan():
    target = _passage(3, [(0.0, 40.0), (100.0, 40.0)])
    marks = engine.concentrate(target, position=.5, width=.2, spacing=1.5)
    assert len(marks) == 4
    assert all(len(mark.points) == 48 for mark in marks)
    # The selected fifth of a 100-mm spine is 40..60 mm.  Offsets are normal
    # to it, so the action remains locally bounded in x while separating in y.
    assert all(39.9 <= x <= 60.1 for mark in marks for x, _y in mark.points)
    assert [mark.points[0][1] for mark in marks] == pytest.approx([41.5, 43.0, 44.5, 46.0])


def test_engine_clipping_is_pure_and_keeps_every_visible_segment_on_the_sheet():
    raw = [Path(points=[(-5.0, 5.0), (5.0, 5.0), (15.0, 5.0), (5.0, 5.0),
                        (-5.0, 5.0)])]
    original = [list(path.points) for path in raw]
    clipped = engine.clip_paths(raw, width=10.0, height=10.0)
    assert [path.points for path in raw] == original
    assert clipped and all(0.0 <= x <= 10.0 and 0.0 <= y <= 10.0
                           for path in clipped for x, y in path.points)
    assert clipped[0].points[0] == (0.0, 5.0)
    assert clipped[-1].points[-1] == (0.0, 5.0)


def _resolved_coordinates(layers):
    return [point for layer in layers for path in layer["paths"]
            for point in path["points"]]


def test_recorded_interventions_survive_save_load_and_resolve_identically():
    """A kept/branched moment must remain reproducible after a cold reload."""
    from fastapi.testclient import TestClient

    from axibridge.app import create_app

    params = {
        "turns": 24, "seed": 2,
        "events": [
            _event("controls", 5, persistence=0.8),
            _event("branch", 8, seed=18),
            _event("stroke", 12, points=[[35.0, 55.0], [72.0, 79.0]]),
        ],
    }
    # Project storage already uses the isolated test configuration.  The name
    # is intentionally unusual so this test never claims a user's folder.
    with TestClient(create_app()) as client:
        layer = client.post("/api/layers/generate", json={
            "module": "second_reading", "params": params}).json()
        before = client.get("/api/compose/resolved").json()["layers"]
        replay_before = _points(**params)
        assert client.post("/api/project/save", json={
            "name": "second-reading-replay"}).status_code == 200
        assert client.post("/api/project/new").status_code == 200
        trajectory.clear_cache()
        assert client.post("/api/project/load", json={
            "name": "second-reading-replay"}).status_code == 200

        after = client.get("/api/compose/resolved").json()["layers"]
        # Project snapshots are SVG with the repository-wide six-decimal
        # precision.  The on-paper snapshot therefore has only that bounded
        # quantisation difference after load; it is not a different drawing.
        assert len(_resolved_coordinates(after)) == len(_resolved_coordinates(before))
        for actual, expected in zip(_resolved_coordinates(after), _resolved_coordinates(before)):
            assert actual == pytest.approx(expected, abs=1e-6)
        saved = client.get("/api/project").json()
        restored = next(item for item in saved["layers"] if item["id"] == layer["id"])
        assert restored["source"]["params"]["events"] == params["events"]
        trajectory.clear_cache()
        assert _points(**restored["source"]["params"]) == replay_before


def test_departure_changes_with_interior_shape_even_when_endpoints_match():
    import random
    from axibridge.sources._second_reading_responses import depart
    straight = engine.describe(0, [Path(points=[(60,100),(150,100),(160,100)])], 'organic','human')
    hooked = engine.describe(0, [Path(points=[(60,100),(75,70),(120,135),(150,100),(160,100)])], 'organic','human')
    a = depart(straight, 65, 1, random.Random(4))[0].points
    b = depart(hooked, 65, 1, random.Random(4))[0].points
    assert a[0] == b[0] == (160,100)
    assert max(math.dist(x,y) for x,y in zip(a,b)) > 15


def test_bridge_uses_both_interiors_and_preserves_its_selected_anchors():
    import random
    from axibridge.sources._second_reading_responses import bridge
    first = engine.describe(0,[Path(points=[(30,40),(60,55),(80,40)])],'organic','opening')
    second = engine.describe(1,[Path(points=[(170,130),(200,150),(240,130)])],'organic','human')
    moved = engine.describe(1,[Path(points=[(170,130),(200,100),(240,130)])],'organic','human')
    a = bridge(first,second,.5,1,random.Random(1))[0].points
    b = bridge(first,moved,.5,1,random.Random(1))[0].points
    assert a[0] == b[0]
    assert max(math.dist(x,y) for x,y in zip(a,b)) > 5
    assert a[0] in (first.paths[0].points[0], first.paths[0].points[-1])


def test_attention_can_answer_or_leave_the_latest_human_passage():
    import random
    older = engine.describe(0,[Path(points=[(30,40),(90,70)])],'organic','opening')
    human = engine.describe(1,[Path(points=[(130,100),(170,60),(210,100)])],'organic','human')
    latest = engine.choose([older,human],0,.5,random.Random(2))
    revisit = engine.choose([older,human],1,.5,random.Random(2))
    assert latest.target_ids[0] == human.id
    assert revisit.target_ids[0] == older.id
    # A non-traversal answer to old material is independent of ignored ink.
    changed_human = engine.describe(1,[Path(points=[(180,170),(210,160)])],'organic','human')
    held = engine.Commitment('echo',(0,),3,1)
    a,_ = engine.make_action(held,[older,human],.5,300,218,random.Random(7))
    b,_ = engine.make_action(held,[older,changed_human],.5,300,218,random.Random(7))
    assert a == b


def test_repeated_answer_loses_preference_without_forcing_a_cycle():
    import random
    target = engine.describe(0,[Path(points=[(70,70),(130,90)])],'organic','human')
    history = [target] + [engine.describe(i,[Path(points=[(70,70+i),(130,90+i)])],
                'organic','echo',(0,)) for i in range(1,5)]
    plain = sum(engine.action_for(target,[target],random.Random(i)) == 'echo' for i in range(200))
    answered = sum(engine.action_for(target,history,random.Random(i)) == 'echo' for i in range(200))
    assert answered < plain/3
    # Attention can persist while the next operation changes.
    c = engine.Commitment('echo',(0,),3,1,1)
    engine.reconsider(c,history,random.Random(4))
    assert c.target_ids[0] == 0 and c.remaining == 3
    assert c.action != 'echo'


def test_surround_opens_space_and_insistence_is_pen_scale_not_a_parallel_field():
    import random
    from axibridge.sources._second_reading_responses import surround, insist
    target = engine.describe(0,[Path(points=[(70,70),(160,70)])],'organic','human')
    body = surround(target,.5,1,random.Random(3))[0].points
    assert body[0][1] == 70
    assert max(y for x,y in body)-min(y for x,y in body) > 25
    assert body[0] != body[-1]
    weight = insist(target,random.Random(4))
    points = [p for path in weight for p in path.points]
    assert len(weight) == 6
    assert max(y for x,y in points)-min(y for x,y in points) < 1
    assert max(x for x,y in points)-min(x for x,y in points) < 40


def test_encounter_detection_ignores_shared_ends_and_coincident_runs():
    from axibridge.sources._second_reading_encounters import encounters
    def passage(i, points):
        return engine.describe(i,[Path(points=points)],'organic','human')
    memory = [passage(0,[(50,20),(50,80)]),
              passage(1,[(20,50),(20,80)]), passage(2,[(30,50),(80,50)])]
    contacts = encounters([(20,50),(90,50)],memory)
    assert len(contacts) == 1
    assert contacts[0].other_id == 0
    assert contacts[0].point == (50,50)
    assert contacts[0].fraction == pytest.approx(30/70)


def test_yielding_changes_only_the_new_line_and_preserves_the_rest_exactly():
    from axibridge.sources._second_reading_encounters import encounters, yield_at
    from shapely.geometry import LineString
    old = engine.describe(0,[Path(points=[(50,20),(50,80)])],'organic','human')
    new = Path(points=[(20,50),(90,50)])
    before = list(old.paths[0].points)
    contact = encounters(new.points,[old])[0]
    result = yield_at(new,contact,4)
    assert [p.points for p in result] == [[(20,50),(48,50)],[(52,50),(90,50)]]
    assert old.paths[0].points == before
    assert new.points == [(20,50),(90,50)]
    assert all(not LineString(p.points).intersects(LineString(before)) for p in result)


def test_context_can_move_an_accent_without_changing_its_random_geometry():
    import random
    target = engine.describe(0,[Path(points=[(20,70),(180,70)])],'organic','human')
    left = engine.describe(1,[Path(points=[(65,30),(65,110)])],'organic','opening')
    right = engine.describe(1,[Path(points=[(125,30),(125,110)])],'organic','opening')
    def answer(other):
        c = engine.Commitment('concentrate',(0,),3,1)
        paths,_ = engine.make_action(c,[other,target],.5,300,218,random.Random(1))
        return c, paths
    a, left_paths = answer(left); b, right_paths = answer(right)
    assert a.response == b.response == 'accent encounter'
    assert a.context_ids == b.context_ids == (1,)
    for p, q in zip(left_paths,right_paths):
        assert p.length() == pytest.approx(q.length())
        assert all(x < 100 for x,y in p.points)
        assert all(x > 90 for x,y in q.points)
    c = engine.Commitment('concentrate',(0,),3,1)
    ignored,_ = engine.make_action(c,[left,target],.5,300,218,random.Random(1),consider_context=False)
    d = engine.Commitment('concentrate',(0,),3,1)
    ignored_other,_ = engine.make_action(d,[right,target],.5,300,218,random.Random(1),consider_context=False)
    assert ignored == ignored_other
    assert c.context_ids == () and c.response is None


def test_encounter_context_is_declared_in_replay_metadata():
    params = SecondReadingParams(seed=12,turns=32)
    traj = _source().trajectory(params)
    responses = [m for m in traj.metadata[:33] if m.get('response')]
    assert responses
    assert all(m['target_passage_ids'] for m in responses)
    assert {m['response'] for m in responses} <= {'yield at crossing','accent encounter'}
