"""Hand effect: a frozen library hand redraws any layer."""

import math

from axibridge import registry
from axibridge.model import Path, is_closed
from axibridge.registry import EffectContext, get_effect


def _square(x0=50.0, y0=50.0, side=60.0):
    pts = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side), (x0, y0)]
    return Path(points=pts, filled=True)


def _run(paths, ctx_seed=1, **kw):
    eff = get_effect("hand")
    return eff.apply(paths, eff.Params(**kw), EffectContext(layer_id="t", translation=(0, 0), seed=ctx_seed))


def test_registered_as_line_effect():
    registry.load_builtin_modules()
    assert "hand" in registry.effects()
    assert registry._EFFECT_LIBRARY_CATEGORIES["hand"] == "line"


def test_filled_square_stays_closed_and_filled():
    out = _run([_square()])
    assert len(out) == 1
    assert out[0].filled is True
    assert is_closed(out[0].points)
    assert len(out[0].points) > 5


def test_each_subpath_gets_its_own_seed():
    a, b = _square(10, 10), _square(110, 110)
    out = _run([a, b])
    da = [(x - 10, y - 10) for x, y in out[0].points]
    db = [(x - 110, y - 110) for x, y in out[1].points]
    assert da != db


def test_seed_and_ctx_seed_change_output():
    base = _run([_square()], seed=0, ctx_seed=1)[0].points
    assert _run([_square()], seed=5, ctx_seed=1)[0].points != base
    assert _run([_square()], seed=0, ctx_seed=2)[0].points != base
    assert _run([_square()], seed=0, ctx_seed=1)[0].points == base


def test_unknown_hand_returns_input_unchanged():
    src = [_square(), Path(points=[(0.0, 0.0), (50.0, 0.0)], filled=False)]
    out = _run(src, hand="no_such_hand_xyz")
    assert [p.points for p in out] == [p.points for p in src]
    assert [p.filled for p in out] == [p.filled for p in src]
    assert out[0] is not src[0]


def test_pin_for_other_hand_is_ignored_and_pin_accepted():
    out = _run([_square()], pin="someone_else@0123456789ab")
    assert is_closed(out[0].points)


def test_bend_lower_bound():
    eff = get_effect("hand")
    props = eff.Params.model_json_schema()["properties"]
    assert props["bend_mm"]["minimum"] == 3 and props["bend_mm"]["maximum"] == 200


# --------------------------------------------------------------------------
# Task 3: kept layers pin the hand; presets never carry the pin
# --------------------------------------------------------------------------

import re  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from axibridge.app import create_app  # noqa: E402
from axibridge.effects import hand as hand_mod  # noqa: E402
from axibridge.session import session  # noqa: E402
from axibridge.sources._gesture_studies import frozen_library as FL  # noqa: E402

PIN = re.compile(r"^[a-z0-9_]{1,64}@[0-9a-f]{12}$")


@pytest.fixture
def client():
    with TestClient(create_app()) as value:
        yield value


def _hash_of(hand_id):
    return next(o["hash"] for o in FL.options("hand") if o["id"] == hand_id)


def _layer_with_hand(client, **params):
    made = client.post("/api/layers/generate", json={
        "module": "polygon", "params": {"sides": 5, "radius": 30}}).json()
    step = {"effect": "hand", "enabled": True, "params": {"hand": "matisse", **params}}
    r = client.patch(f"/api/layers/{made['id']}", json={"effects": [step]})
    assert r.status_code == 200, r.text
    return r.json()


def test_adding_hand_effect_pins_current_hash(client):
    layer = _layer_with_hand(client)
    pin = layer["effects"][0]["params"]["pin"]
    assert PIN.match(pin)
    assert pin == f"matisse@{_hash_of('matisse')}"
    stored = session.project.layer(layer["id"]).effects[0].params["pin"]
    assert stored == pin


def test_changing_hand_repins(client):
    layer = _layer_with_hand(client)
    other = next(o["id"] for o in FL.options("hand") if o["id"] != "matisse")
    step = {**layer["effects"][0], "params": {**layer["effects"][0]["params"], "hand": other}}
    out = client.patch(f"/api/layers/{layer['id']}", json={"effects": [step]}).json()
    assert out["effects"][0]["params"]["pin"] == f"{other}@{_hash_of(other)}"


def test_pinned_hash_survives_snapshot_change(client, monkeypatch):
    layer = _layer_with_hand(client)
    pinned = layer["effects"][0]["params"]["pin"]
    _, _, h = pinned.partition("@")
    before = session.resolved()[layer["id"]]
    # a refreeze: the current snapshot now names another version of matisse
    monkeypatch.setattr(hand_mod, "_current_hash", lambda hand_id: "ffffffffffff")
    step = {**layer["effects"][0],
            "params": {**layer["effects"][0]["params"], "stray_mm": 3.0}}
    out = client.patch(f"/api/layers/{layer['id']}", json={"effects": [step]}).json()
    assert out["effects"][0]["params"]["pin"] == pinned        # an edit never re-pins
    calls = []
    real = hand_mod.load_hand
    monkeypatch.setattr(hand_mod, "load_hand",
                        lambda hid, ph: calls.append((hid, ph)) or real(hid, ph))
    session._shaped_cache.clear()
    after = session.resolved()[layer["id"]]
    assert ("matisse", h) in calls
    assert [p.points for p in after] == [p.points for p in before]


def test_complete_params_is_identity_for_other_effects():
    eff = get_effect("freehand")
    params = {"seed": 3}
    assert eff.complete_params(params) == params


def test_complete_params_unknown_hand_leaves_pin_unset():
    eff = get_effect("hand")
    assert "pin" not in eff.complete_params({"hand": "gone_hand"})
    assert eff.complete_params({"hand": "gone_hand", "pin": "matisse@0123456789ab"}).get("pin") is None
    # a pin that already names the hand is kept, known or not
    kept = eff.complete_params({"hand": "gone_hand", "pin": "gone_hand@0123456789ab"})
    assert kept["pin"] == "gone_hand@0123456789ab"


def test_withdrawn_hand_passes_through(client):
    made = client.post("/api/layers/generate", json={
        "module": "polygon", "params": {"sides": 5, "radius": 30}}).json()
    plain = [p.points for p in session.resolved()[made["id"]]]
    step = {"effect": "hand", "enabled": True,
            "params": {"hand": "gone_hand", "pin": "gone_hand@0123456789ab"}}
    r = client.patch(f"/api/layers/{made['id']}", json={"effects": [step]})
    assert r.status_code == 200, r.text
    assert [p.points for p in session.resolved()[made["id"]]] == plain


def test_stale_pin_of_known_hand_falls_back_to_current():
    current = _run([_square()])[0].points
    assert _run([_square()], pin="matisse@000000000000")[0].points == current


def test_one_and_two_point_paths_through_the_effect():
    dot = Path(points=[(10.0, 10.0)], filled=False)
    out = _run([dot])
    assert out[0].points == dot.points and out[0] is not dot
    seg = Path(points=[(10.0, 10.0), (90.0, 40.0)], filled=False)
    out = _run([seg])
    pts = out[0].points
    assert len(pts) >= 2 and out[0].filled is False
    assert pts[0] == pytest.approx(seg.points[0]) and pts[-1] == pytest.approx(seg.points[-1])
    assert all(math.isfinite(x) and math.isfinite(y) for x, y in pts)


def test_presets_exclude_pin(client):
    layer = _layer_with_hand(client)
    params = layer["effects"][0]["params"]
    assert params["pin"]
    made = client.post("/api/module-library/presets", json={
        "kind": "effect", "module": "hand", "name": "Kept hand", "params": params}).json()
    assert "pin" not in made["params"]
    assert made["params"]["hand"] == "matisse"


def test_tween_of_stray_morphs(client, monkeypatch):
    a = _layer_with_hand(client, stray_mm=2.0, seed=4)
    b = _layer_with_hand(client, stray_mm=10.0, seed=4)
    assert a["effects"][0]["params"]["pin"] == b["effects"][0]["params"]["pin"]
    tw = session.create_tween_layer(a["id"], b["id"])
    session.set_tween_params(tw.id, {"t": 0.5})
    seen = []
    real = hand_mod.HandEffect.apply
    monkeypatch.setattr(hand_mod.HandEffect, "apply",
                        lambda self, paths, params, ctx: seen.append(params) or real(self, paths, params, ctx))
    session._shaped_cache.clear()
    session._tween_cache.clear()
    session.resolved()
    strays = sorted({p.stray_mm for p in seen})
    assert 6.0 in strays
    mid = next(p for p in seen if p.stray_mm == 6.0)
    assert mid.pin == a["effects"][0]["params"]["pin"]
