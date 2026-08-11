"""Keyframe chains (S2 of docs/plans/timeline-v2.md).

A chain is ONE tween layer carrying an ordered ``keys`` list; a global
position ``u`` is reduced to ``(segment, local t)`` with isometric spacing and
the ordinary *pair* machinery runs on that segment. These tests pin the four
promises that make that a generalisation rather than a second feature:

1. **two keys is the pair** — byte-identical geometry, under windows, curves
   and sweep alike;
2. **endpoint fidelity at EVERY key**, not just the two ends;
3. **per-segment easing** (Ian's Q2 ruling) — with ``cosine`` the motion
   settles on each keyframe, while ``cosine_pingpong`` keeps its global
   meaning (out and back over the whole chain);
4. the session verbs are single-checkpoint, the cascade rules already know
   about N refs, and a mid-key edit is visible through the warm caches.
"""

import pytest

from axibridge.compose import Affine
from axibridge.session import Session, session
from axibridge.tween import MAX_CHAIN_KEYS, TweenParams, chain_segment


# -- helpers ------------------------------------------------------------------


def _sig(paths):
    """Exact geometry, not a summary."""
    return [(p.filled, [(x, y) for x, y in p.points]) for p in paths]


def _chain(radii, sides=6):
    """An animated polygon grown to ``len(radii)`` keyframes, one radius each.

    Transforms stay identity on every key, so the tween's materialised source
    geometry is comparable BYTE FOR BYTE against a key's own source geometry
    (``lerp_affine`` of two identities recomposes to exact identity)."""
    layer = session.add_generated_layer("polygon", {"sides": sides, "radius": radii[0]})
    tw = session.animate_layer(layer.id)
    while len(session._chain_keys(session.project.layer(tw.id))) < len(radii):
        session.add_chain_keyframe(tw.id)
    keys = session._chain_keys(session.project.layer(tw.id))
    for kid, radius in zip(keys, radii):
        session.regenerate_layer(kid, {"sides": sides, "radius": radius})
    return session.project.layer(tw.id), keys


def _at(tw_id, master_t):
    session.resolved(master_t=master_t)
    return _sig(session.source_geometry[tw_id])


def _key_sig(key_id):
    return _sig(session.source_geometry[key_id])


def _mean_x(paths):
    pts = [x for p in paths for x, _ in p.points]
    return sum(pts) / len(pts)


# -- 1. two keys IS the pair ---------------------------------------------------


@pytest.mark.parametrize("variant", [
    {},
    {"window_from": 0.25, "window_to": 0.75},
    {"time_curve": "cosine"},
    {"time_curve": "cosine_pingpong"},
    {"time_curve": "cosine", "window_from": 0.2, "window_to": 0.9},
    {"sweep": 3},
    {"sweep": 3, "time_curve": "cosine"},
])
def test_two_key_chain_is_byte_identical_to_the_pair(variant):
    """The whole design rests on this: a ``keys`` list of two is the classic
    A/B tween, not a re-implementation of it. Sampled at 11 master values,
    with the window / curve / sweep variants that each touch a different part
    of the position mapping."""
    tw, keys = _chain([15, 45])
    base = {"window_from": 0.0, "window_to": 1.0, "time_curve": "linear", "sweep": 1}

    session.set_tween_params(tw.id, {**base, **variant, "keys": []})
    classic = [_at(tw.id, i / 10) for i in range(11)]

    session.set_tween_params(tw.id, {**base, **variant, "keys": keys})
    chained = [_at(tw.id, i / 10) for i in range(11)]

    assert chained == classic


# -- 2. endpoint fidelity at every key -----------------------------------------


@pytest.mark.parametrize("n", [3, 4, 5])
def test_master_t_at_every_key_reproduces_that_key_exactly(n):
    radii = [10 + 12 * k for k in range(n)]
    tw, keys = _chain(radii)
    for k, key_id in enumerate(keys):
        assert _at(tw.id, k / (n - 1)) == _key_sig(key_id), (
            f"master_t={k / (n - 1)} did not reproduce key {k} of {n}")


def test_between_keys_is_between_and_isometrically_spaced():
    """Segment k spans [k/(N-1), (k+1)/(N-1)] — derived, never stored.

    Same shape on every key, evenly spaced translations: a linear chain is
    then a straight ramp in x, and any non-isometric spacing shows up as an
    uneven step."""
    tw, keys = _chain([20, 20, 20, 20])
    for kid, off in zip(keys, (0.0, 30.0, 60.0, 90.0)):
        session.update_layer(kid, {"transform": Affine(e=off).model_dump()})
    session.set_tween_params(tw.id, {"keys": keys, "time_curve": "linear"})
    xs = [_mean_x(session.resolved(master_t=i / 12)[tw.id]) for i in range(13)]
    # a linear chain over evenly-offset keys is a straight ramp: equal steps
    steps = [b - a for a, b in zip(xs, xs[1:])]
    assert all(s == pytest.approx(steps[0], abs=1e-6) for s in steps)


# -- 3. window semantics at the outer level ------------------------------------


def test_outside_the_window_a_chain_holds_its_first_and_last_key():
    tw, keys = _chain([10, 40, 70])
    session.set_tween_params(tw.id, {"keys": keys, "window_from": 0.25, "window_to": 0.75})
    for master_t in (0.0, 0.1, 0.25):
        assert _at(tw.id, master_t) == _key_sig(keys[0])
    for master_t in (0.75, 0.9, 1.0):
        assert _at(tw.id, master_t) == _key_sig(keys[-1])
    # ... and the middle key is reached at the window's midpoint
    assert _at(tw.id, 0.5) == _key_sig(keys[1])


# -- 4. per-segment easing (Q2) ------------------------------------------------


def _speed(tw_id, u, h=0.02):
    """|d(mean x)/dt| around ``u`` — an assertable proxy for how fast the
    motion is moving there. Float-valued (a lerped translation), so it is not
    quantized the way an int generator param would be."""
    lo = _mean_x(session.resolved(master_t=u - h)[tw_id])
    hi = _mean_x(session.resolved(master_t=u + h)[tw_id])
    return abs(hi - lo)


def _moving_chain():
    """Three keys at evenly spaced translations: position is a clean function
    of u, so the easing shows up directly in the speed."""
    tw, keys = _chain([20, 20, 20])
    for kid, off in zip(keys, (0.0, 60.0, 120.0)):
        session.update_layer(kid, {"transform": Affine(e=off).model_dump()})
    return tw, keys


def test_cosine_eases_each_segment_and_settles_on_the_interior_key():
    """Ian's Q2 ruling: easing is PER SEGMENT, so the motion settles at every
    checkpoint and pushes off again (pose-to-pose). The interior keyframe of a
    3-key chain sits at u=0.5; with ``cosine`` the speed there must collapse
    relative to mid-segment, and with ``linear`` it must not."""
    tw, keys = _moving_chain()

    session.set_tween_params(tw.id, {"keys": keys, "time_curve": "linear"})
    lin_mid, lin_key = _speed(tw.id, 0.25), _speed(tw.id, 0.5)
    assert lin_key == pytest.approx(lin_mid, rel=0.05)  # constant rate, no settle

    session.set_tween_params(tw.id, {"keys": keys, "time_curve": "cosine"})
    cos_mid, cos_key = _speed(tw.id, 0.25), _speed(tw.id, 0.5)
    assert cos_key < 0.25 * cos_mid, "cosine did not settle on the interior key"
    assert cos_mid > lin_mid, "cosine did not speed up mid-segment"
    # both ends still settle, exactly as on a pair
    assert _speed(tw.id, 0.02, h=0.02) < 0.25 * cos_mid


def test_cosine_pingpong_keeps_its_global_meaning_on_a_chain():
    """``cosine_pingpong`` says "out and back over this timeline" — a
    statement about the WHOLE motion. Bouncing inside every segment would
    never reach the last key. u=0 -> A, u=0.5 -> C, u=1 -> A again."""
    tw, keys = _chain([10, 40, 70])
    session.set_tween_params(tw.id, {"keys": keys, "time_curve": "cosine_pingpong"})
    assert _at(tw.id, 0.0) == _key_sig(keys[0])
    assert _at(tw.id, 0.5) == _key_sig(keys[2])
    assert _at(tw.id, 1.0) == _key_sig(keys[0])
    # and it really passes through B on the way out and back
    assert _at(tw.id, 0.25) == _key_sig(keys[1])
    assert _at(tw.id, 0.75) == _key_sig(keys[1])


def test_chain_segment_mapping_is_isometric_and_snaps_to_keys():
    assert chain_segment(0.0, 4) == (0, 0.0)
    assert chain_segment(1 / 3, 4) == (1, 0.0)
    assert chain_segment(2 / 3, 4) == (2, 0.0)
    assert chain_segment(1.0, 4) == (2, 1.0)
    seg, t = chain_segment(0.5, 4)
    assert (seg, t) == (1, pytest.approx(0.5))
    # a pair is the identity mapping (with the curve applied as it always was)
    assert chain_segment(0.37, 2) == (0, pytest.approx(0.37))
    # global curve maps u first, then segments linearly
    assert chain_segment(0.5, 3, "cosine_pingpong") == (1, 1.0)
    # segment curve eases the LOCAL t
    assert chain_segment(0.25, 3, "cosine")[1] == pytest.approx(0.5)


# -- 5. sweep across the whole motion ------------------------------------------


def test_sweep_stamps_fixed_copies_across_the_whole_chain():
    tw, keys = _chain([10, 30, 50, 70])
    session.set_tween_params(tw.id, {"keys": keys, "sweep": 1})
    single = len(session.resolved(master_t=0.5)[tw.id])
    session.set_tween_params(tw.id, {"keys": keys, "sweep": 3})
    stamped = session.resolved(master_t=0.0)[tw.id]
    assert len(stamped) == single * 3
    # positions are time-invariant: a scrub does not move them
    at_zero = _sig(stamped)
    for master_t in (0.25, 0.5, 0.9, 1.0):
        assert _sig(session.resolved(master_t=master_t)[tw.id]) == at_zero
    # the ladder spreads across the WHOLE motion, not one pair: the three
    # stamps span more than a single segment's worth of radius
    spans = sorted(max(x for x, _ in p.points) - min(x for x, _ in p.points)
                   for p in stamped)
    assert spans[-1] - spans[0] > 20


# -- 6. nesting: a chain can be an endpoint of another tween -------------------


def test_a_chain_reduces_to_its_active_segment_as_a_tween_endpoint():
    tw, keys = _chain([10, 40, 70])
    other = session.add_generated_layer("polygon", {"sides": 6, "radius": 90})
    outer = session.create_tween_layer(tw.id, other.id)  # refused if it can't reduce
    session.set_tween_params(outer.id, {"t": 0.0})
    session.resolved()
    assert session.source_geometry[outer.id], "a chain endpoint resolved empty"


# -- 7. session verbs: add / remove / reorder ----------------------------------


def test_add_keyframe_duplicates_the_last_key_and_leaves_the_look_unchanged():
    """Q6: the appended segment starts static, so pressing '+ keyframe' never
    changes what is on the sheet."""
    tw, keys = _chain([15, 45])
    before = [_at(tw.id, i / 10) for i in range(11)]
    new_key = session.add_chain_keyframe(tw.id)
    assert not new_key.visible and new_key.name.endswith(" ▸ C")
    tw = session.project.layer(tw.id)
    assert tw.source.params["keys"] == [*keys, new_key.id]
    assert tw.source.params["a"] == keys[0]  # a/b mirror keys[0]/keys[-1]
    assert tw.source.params["b"] == new_key.id
    # C duplicates B, so the last segment is static and the first is unchanged
    assert _key_sig(new_key.id) == _key_sig(keys[-1])
    after = [_at(tw.id, i / 10) for i in range(11)]
    assert after[0] == before[0] and after[-1] == before[-1]


def test_add_keyframe_is_one_undo_step():
    tw, keys = _chain([15, 45])
    session.clear_history()
    new_key = session.add_chain_keyframe(tw.id)
    assert session.undo()
    assert session.project.layer(tw.id).source.params["keys"] == []
    with pytest.raises(KeyError):
        session.project.layer(new_key.id)


def test_add_keyframe_is_bounded():
    tw, keys = _chain([15, 45])
    while len(session._chain_keys(session.project.layer(tw.id))) < MAX_CHAIN_KEYS:
        session.add_chain_keyframe(tw.id)
    with pytest.raises(RuntimeError, match="at most"):
        session.add_chain_keyframe(tw.id)


def test_add_keyframe_refuses_a_non_tween_layer():
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    with pytest.raises(RuntimeError, match="not an interpolation layer"):
        session.add_chain_keyframe(layer.id)


def test_remove_keyframe_deletes_the_hidden_layer_and_respaces():
    tw, keys = _chain([10, 40, 70, 100])
    session.remove_chain_keyframe(tw.id, keys[1])
    tw = session.project.layer(tw.id)
    assert tw.source.params["keys"] == [keys[0], keys[2], keys[3]]
    with pytest.raises(KeyError):
        session.project.layer(keys[1])
    # re-spaced: three keys now, so the middle one sits at u=0.5
    assert _at(tw.id, 0.5) == _key_sig(keys[2])


def test_remove_keyframe_down_to_two_restores_a_plain_pair():
    tw, keys = _chain([10, 40, 70])
    session.remove_chain_keyframe(tw.id, keys[1])
    params = session.project.layer(tw.id).source.params
    assert params["keys"] == []  # fully reversible to the classic A/B form
    assert (params["a"], params["b"]) == (keys[0], keys[2])
    with pytest.raises(RuntimeError, match="needs two keyframes"):
        session.remove_chain_keyframe(tw.id, keys[0])


def test_remove_keyframe_rejects_a_stranger():
    tw, keys = _chain([10, 40, 70])
    stranger = session.add_generated_layer("polygon", {"sides": 6, "radius": 5})
    with pytest.raises(KeyError):
        session.remove_chain_keyframe(tw.id, stranger.id)


def test_reorder_keyframes_reverses_the_motion():
    tw, keys = _chain([10, 40, 70])
    session.reorder_chain_keyframes(tw.id, list(reversed(keys)))
    assert session.project.layer(tw.id).source.params["keys"] == list(reversed(keys))
    assert _at(tw.id, 0.0) == _key_sig(keys[2])
    assert _at(tw.id, 1.0) == _key_sig(keys[0])
    with pytest.raises(ValueError, match="exactly"):
        session.reorder_chain_keyframes(tw.id, keys[:2])


# -- 8. cascade + un-animate ---------------------------------------------------


def test_deleting_a_mid_keyframe_cascades_the_whole_chain():
    tw, keys = _chain([10, 40, 70, 100])
    deleted = session.delete_layer(keys[1])
    assert set(deleted) == {tw.id, *keys}
    assert not session.project.layers


def test_deleting_the_chain_restores_key_zero_and_sweeps_the_rest():
    tw, keys = _chain([10, 40, 70])
    deleted = session.delete_layer(tw.id)  # DIRECT delete -> un-animate
    assert set(deleted) == {tw.id, keys[1], keys[2]}
    restored = session.project.layer(keys[0])
    assert restored.visible and not restored.name.endswith(" ▸ A")
    assert session.undo()
    assert not session.project.layer(keys[0]).visible
    assert session.project.layer(tw.id).source.params["keys"] == keys


def test_dragging_the_chain_moves_every_keyframe():
    """The visible tween is the ONE handle for the group — length-agnostic
    since S2, so a chain's mid-keys travel with it like A and B always did."""
    tw, keys = _chain([10, 40, 70])
    session.update_layer(tw.id, {"transform": Affine(e=25, f=10).model_dump()})
    for kid in keys:
        assert session.project.layer(kid).transform.e == pytest.approx(25)
        assert session.project.layer(kid).transform.f == pytest.approx(10)


# -- 9. cache correctness ------------------------------------------------------


def test_a_mid_key_edit_invalidates_the_warm_tween_cache():
    """The tween cache key iterates ``_tween_refs`` (S1), so a chain's mid keys
    and their geometry ids are IN the key — verified, not assumed: warm a
    master value, edit key C, re-resolve the SAME value, and the geometry must
    move (and must match a session that never saw the frame)."""
    import json

    tw, keys = _chain([10, 40, 70, 100])
    warm = _at(tw.id, 0.5)  # lives on segment 1 (keys B..C)
    cache_key = next(iter(session._tween_cache[tw.id]))
    refs = json.loads(cache_key)["refs"]
    assert len(refs) == len(keys), (
        "the tween cache key must name EVERY keyframe — with only the two "
        "ends in it, a mid-key edit is served from a stale entry")

    session.regenerate_layer(keys[2], {"sides": 6, "radius": 200})
    after = _at(tw.id, 0.5)
    assert after != warm, "a mid-key edit was served from a stale cache entry"

    cold = Session()
    cold.project = session.project.model_copy(deep=True)
    cold.source_geometry = {k: list(v) for k, v in session.source_geometry.items()}
    cold.resolved(master_t=0.5)
    assert _sig(cold.source_geometry[tw.id]) == after


def test_revisiting_a_chain_frame_still_hits_the_cache():
    tw, keys = _chain([10, 40, 70])
    session.resolved(master_t=0.4)
    first = session.source_geometry[tw.id]
    session.resolved(master_t=0.9)
    session.resolved(master_t=0.4)
    assert session.source_geometry[tw.id] is first  # same list object: a real hit


# -- 10. params validation -----------------------------------------------------


def test_tween_params_maintain_a_and_b_from_the_keys_list():
    p = TweenParams(a="x", b="y", keys=["k0", "k1", "k2"])
    assert (p.a, p.b) == ("k0", "k2")


def test_tween_params_reject_a_degenerate_chain():
    with pytest.raises(ValueError):
        TweenParams(a="x", b="y", keys=["only"])
    with pytest.raises(ValueError):
        TweenParams(a="x", b="y", keys=["dup", "dup"])
    with pytest.raises(ValueError):
        TweenParams(a="x", b="y", keys=[f"k{i}" for i in range(MAX_CHAIN_KEYS + 1)])


def test_set_tween_params_refuses_an_unknown_or_self_referencing_key():
    tw, keys = _chain([10, 40, 70])
    with pytest.raises(KeyError):
        session.set_tween_params(tw.id, {"keys": [keys[0], keys[1], "nope"]})
    with pytest.raises(RuntimeError, match="its own keyframe"):
        session.set_tween_params(tw.id, {"keys": [keys[0], keys[1], tw.id]})


def test_a_broken_chain_resolves_empty_never_raises():
    """The no-crash contract: a stored project must always resolve."""
    tw, keys = _chain([10, 40, 70])
    stranger = session.add_generated_layer("lissajous", {"size": 40})
    session.set_tween_params(tw.id, {"keys": [keys[0], stranger.id, keys[2]]})
    assert session.resolved(master_t=0.5)[tw.id] == []


# -- 11. the HTTP surface ------------------------------------------------------


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from axibridge.app import create_app

    with TestClient(create_app()) as c:
        yield c


def _api_chain(client, n=3):
    lay = client.post("/api/layers/generate", json={
        "module": "polygon", "params": {"sides": 6, "radius": 15}}).json()
    tw = client.post(f"/api/layers/{lay['id']}/animate").json()
    for _ in range(n - 2):
        assert client.post(f"/api/layers/{tw['id']}/chain/keyframe").status_code == 200
    keys = client.get("/api/project").json()
    keys = [l for l in keys["layers"] if l["id"] == tw["id"]][0]["source"]["params"]["keys"]
    return tw, keys


def test_api_add_keyframe_grows_the_chain(client):
    tw, keys = _api_chain(client, 3)
    assert len(keys) == 3
    key_layers = {l["id"]: l for l in client.get("/api/project").json()["layers"]}
    assert key_layers[keys[-1]]["visible"] is False
    assert key_layers[keys[-1]]["name"].endswith(" ▸ C")


def test_api_add_keyframe_refuses_a_non_tween_and_an_unknown_layer(client):
    lay = client.post("/api/layers/generate", json={
        "module": "polygon", "params": {"sides": 6, "radius": 15}}).json()
    assert client.post(f"/api/layers/{lay['id']}/chain/keyframe").status_code == 409
    assert client.post("/api/layers/nope/chain/keyframe").status_code == 404


def test_api_remove_keyframe_validates(client):
    tw, keys = _api_chain(client, 3)
    assert client.delete(f"/api/layers/{tw['id']}/chain/keyframe/nope").status_code == 404
    r = client.delete(f"/api/layers/{tw['id']}/chain/keyframe/{keys[1]}")
    assert r.status_code == 200
    assert r.json()["source"]["params"]["keys"] == []  # back to a plain pair
    # a pair has no keyframe to give up
    assert client.delete(
        f"/api/layers/{tw['id']}/chain/keyframe/{keys[0]}").status_code == 409


def test_api_reorder_keyframes_validates(client):
    tw, keys = _api_chain(client, 3)
    r = client.put(f"/api/layers/{tw['id']}/chain/order",
                   json={"order": list(reversed(keys))})
    assert r.status_code == 200
    assert r.json()["source"]["params"]["keys"] == list(reversed(keys))
    assert client.put(f"/api/layers/{tw['id']}/chain/order",
                      json={"order": keys[:2]}).status_code == 422
    assert client.put("/api/layers/nope/chain/order",
                      json={"order": keys}).status_code == 404


def test_api_keys_ride_the_tween_params_merge_and_are_bounded(client):
    tw, keys = _api_chain(client, 3)
    r = client.put(f"/api/layers/{tw['id']}/tween",
                   json={"keys": list(reversed(keys)), "time_curve": "cosine"})
    assert r.status_code == 200
    assert r.json()["source"]["params"]["keys"] == list(reversed(keys))
    # bounded: past MAX_CHAIN_KEYS the params model refuses it
    assert client.put(f"/api/layers/{tw['id']}/tween", json={
        "keys": [f"k{i}" for i in range(MAX_CHAIN_KEYS + 1)]}).status_code == 422
    # ... and every id must name a real layer
    assert client.put(f"/api/layers/{tw['id']}/tween",
                      json={"keys": [keys[0], keys[1], "ghost"]}).status_code == 404
