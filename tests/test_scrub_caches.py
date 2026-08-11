"""Per-frame caches must be multi-entry AND still honest.

Animation resolves the same project at many master values. Every cache in the
resolve path used to hold ONE slot per layer with the master value folded into
the key, so scrubbing back to a frame (or looping) recomputed everything. These
tests cover the widened caches on both axes:

* **honesty** — the same discipline as ``test_occlusion_cache.py``: never
  inspect a cache to decide whether the output is right, compare the cached
  resolve against one computed by a session that has never seen that frame.
* **cheapness** — revisiting a warm frame must do no mask building, no
  clipping, no shaping, no generating, no tween materialising at all.

The one white-box test here (``test_every_id_key_pins_its_object``) pins the
invariant that makes multi-entry caching safe in the first place: a key that
embeds ``id(x)`` is only meaningful while ``x`` is alive, so its entry must
hold ``x``. With one slot per layer a stale id was overwritten before it could
lie; with many, a collected list's id can be recycled by an unrelated list and
the cache would hand back the wrong geometry.
"""

import json

import pytest

from axibridge import compose, gencache, tween as tween_mod
from axibridge.compose import Affine
from axibridge.registry import get_effect, get_source
from axibridge.session import Session, session


def signature(res):
    """Exact geometry, not a summary."""
    return {k: [(p.filled, [(round(x, 9), round(y, 9)) for x, y in p.points])
                for p in v]
            for k, v in res.items()}


def ground_truth(master_t):
    """Resolve the same project at the same master value in a session with
    completely cold caches — the pre-cache code path, per frame."""
    fresh = Session()
    fresh.project = session.project.model_copy(deep=True)
    fresh.source_geometry = {k: list(v) for k, v in session.source_geometry.items()}
    return fresh.resolved(master_t=master_t)


def assert_honest(master_t, what):
    assert signature(session.resolved(master_t=master_t)) == signature(ground_truth(master_t)), (
        f"cached resolve at master_t={master_t} diverged from a cold one: {what}")


@pytest.fixture()
def animated():
    """Two static receivers under a tween-driven occluder that really moves:
    keyframe B is translated, so every master value is a different mask."""
    low = session.add_generated_layer("lissajous", {"size": 100, "margin": 5})
    high = session.add_generated_layer("lissajous", {"size": 80, "margin": 5})
    occ = session.add_generated_layer("polygon", {"sides": 6, "radius": 30, "filled": True})
    session.update_layer(occ.id, {"transform": Affine(e=20, f=20).model_dump()})
    tw = session.animate_layer(occ.id)
    b_id = tw.source.params["b"]
    session.update_layer(b_id, {"transform": Affine(e=90, f=70).model_dump()})
    session.update_layer(tw.id, {"occluder": True})
    return low, high, tw


# -- 1. honesty under animation ------------------------------------------------


def test_alternating_frames_stay_honest(animated):
    low, high, tw = animated
    seen = {}
    for master_t in (0.0, 0.5, 0.0, 0.5, 1.0, 0.0):
        assert_honest(master_t, f"revisiting master_t={master_t}")
        sig = signature(session.resolved(master_t=master_t))
        if master_t in seen:
            assert sig == seen[master_t], "the same frame resolved two ways"
        seen[master_t] = sig
    assert seen[0.0] != seen[0.5] != seen[1.0], "the tween must actually move"


def test_mutation_between_frames_stays_honest(animated):
    """A cross-frame cache is only safe if an edit still invalidates it."""
    low, high, tw = animated
    session.resolved(master_t=0.0)
    session.resolved(master_t=0.5)
    session.update_layer(low.id, {"transform": Affine(e=25, f=15).model_dump()})
    assert_honest(0.0, "receiver moved after both frames were warm")
    assert_honest(0.5, "receiver moved after both frames were warm")
    session.update_layer(tw.id, {"occlusion_margin_mm": 4.0})
    assert_honest(0.0, "occluder margin changed")
    session.regenerate_layer(low.id, {"size": 60, "margin": 5})
    assert_honest(0.5, "receiver regenerated")
    assert session.undo()
    assert_honest(0.5, "undo")


# -- 2. the composition property: a repeated frame is the SAME objects --------


def test_repeat_frame_returns_the_same_list_objects(animated):
    """Stage 3 → Stage 4 end to end. The tween cache handing back the same
    paths list is what lets the shaped cache re-hit (its key hashes id(src)),
    and the shaped cache handing back the same shaped list is what lets the
    occlusion masks and clips re-hit (their keys embed id(shaped)). If any
    link copies instead of returning its cached object, this fails."""
    low, high, tw = animated
    first = session.resolved(master_t=0.0)
    session.resolved(master_t=0.5)
    again = session.resolved(master_t=0.0)
    for layer_id, paths in first.items():
        assert again[layer_id] is paths, (
            f"layer {layer_id} came back as a different list object on a "
            "revisited frame — the downstream identity-keyed memos cannot hit")


# -- 3. counting: a warm frame costs nothing ----------------------------------


class _Counter:
    def __init__(self, monkeypatch, obj, name):
        self.n = 0
        original = getattr(obj, name)

        def wrapper(*a, **kw):
            self.n += 1
            return original(*a, **kw)

        monkeypatch.setattr(obj, name, wrapper)


def test_revisiting_warm_frames_recomputes_nothing(animated, monkeypatch):
    low, high, tw = animated
    session.update_layer(tw.id, {"effects": [
        {"effect": "hatch_fill", "params": {"spacing": 3.0}, "enabled": True}]})
    gencache.clear()

    session.resolved(master_t=0.0)   # warm both frames
    session.resolved(master_t=0.5)

    counters = {
        "build_mask": _Counter(monkeypatch, compose, "build_mask"),
        "clip_paths": _Counter(monkeypatch, compose, "clip_paths"),
        "shape_layer": _Counter(monkeypatch, compose, "shape_layer"),
        "materialize": _Counter(monkeypatch, tween_mod, "materialize"),
        "generate": _Counter(monkeypatch, get_source("polygon"), "generate"),
        "hatch_fill": _Counter(monkeypatch, get_effect("hatch_fill"), "apply"),
    }

    session.resolved(master_t=0.0)
    session.resolved(master_t=0.5)
    session.resolved(master_t=0.0)

    assert {k: c.n for k, c in counters.items()} == {k: 0 for k in counters}


def test_a_new_frame_still_computes(animated, monkeypatch):
    """The counting test above would also pass if the caches returned stale
    geometry for everything, so pin the other side: an unseen frame works."""
    low, high, tw = animated
    session.resolved(master_t=0.0)
    counters = {
        "build_mask": _Counter(monkeypatch, compose, "build_mask"),
        "clip_paths": _Counter(monkeypatch, compose, "clip_paths"),
    }
    session.resolved(master_t=0.25)
    assert counters["build_mask"].n >= 1 and counters["clip_paths"].n >= 1


# -- 4. the id() discipline ----------------------------------------------------


def _ids_in(sig) -> set[int]:
    """Every ``id()`` embedded in a (possibly nested) occlusion signature."""
    out: set[int] = set()
    stack = [sig]
    while stack:
        el = stack.pop()
        if isinstance(el, tuple):
            stack.extend(el)
        elif isinstance(el, int) and not isinstance(el, bool):
            out.add(el)
    return out


def test_every_id_key_pins_its_object(animated):
    """WHITE BOX, on purpose: an id-keyed entry that does not hold its object
    is a silent-wrong-geometry bug waiting for the garbage collector."""
    low, high, tw = animated
    for master_t in (0.0, 0.3, 0.7, 0.0):
        session.resolved(master_t=master_t)

    page = compose.guide_page(session.project)

    tween_entries = 0
    for layer_id, layer_map in session._tween_cache.items():
        for key, entry in layer_map.items():
            tween_entries += 1
            held = {id(r) for r in entry.refs} | {id(None)}
            for ref in json.loads(key)["refs"]:
                if ref is not None:
                    assert ref["geo"] in held, (
                        "a tween cache key names a geometry list the entry "
                        "does not keep alive")
    assert tween_entries > 1, "the tween cache must hold more than one frame"

    shaped_entries = 0
    for layer_id, layer_map in session._shaped_cache.items():
        layer = session.project.layer(layer_id)
        for key, entry in layer_map.items():
            shaped_entries += 1
            # the held src is provably the one the key names: rebuilding the
            # key from it reproduces the key exactly (it hashes id(src))
            assert compose._shape_key(layer, entry.src, page) == key
    assert shaped_entries > 1, "the shaped cache must hold more than one frame"

    occ = session._occlusion_cache
    assert len(occ._masks) > 1, "the occlusion cache must hold more than one frame"
    for key, entry in occ._masks.items():
        assert key[1] == id(entry.shaped), "a mask key's id() is not pinned"
    for key, entry in occ._clips.items():
        assert key[1][0] == id(entry.subject), "a clip key's subject id is not pinned"
        held = {id(r) for r in entry.refs}
        assert _ids_in(key[1][1]) <= held, "a clip key names unpinned occluders"
    for key, entry in occ._unions.items():
        assert _ids_in(key) <= {id(r) for r in entry.refs}, (
            "a union signature names unpinned occluders")


def test_cascade_delete_after_scrub_unaffected_by_refs_generalisation(animated):
    """S1 (2026-08-11) generalised ``Session._tween_refs`` from a fixed
    2-tuple to an ordered list, threaded through the cascade-delete rules
    (a)/(b) and the un-animate restore (F3's table). Pin that a real
    animate-created A/B tween still cascades and un-animates exactly as
    before, even with a warm, multi-entry tween cache from scrubbing."""
    low, high, tw = animated
    for master_t in (0.0, 0.3, 0.7):
        session.resolved(master_t=master_t)
    assert len(session._tween_cache.get(tw.id, {})) > 1  # warm, multi-entry

    a_id, b_id = tw.source.params["a"], tw.source.params["b"]
    session._history.clear()

    deleted = session.delete_layer(tw.id)  # DIRECT tween delete -> un-animate
    assert set(deleted) == {b_id, tw.id}
    survivors = {l.id for l in session.project.layers}
    assert a_id in survivors and tw.id not in survivors and b_id not in survivors
    a_layer = session.project.layer(a_id)
    assert a_layer.visible and not a_layer.name.endswith(" ▸ A")

    assert session.undo()  # one undo restores the whole group
    assert not session.project.layer(a_id).visible
    assert session.project.layer(a_id).name.endswith(" ▸ A")
    assert session.project.layer(tw.id).visible


# -- 5. eviction ---------------------------------------------------------------


def _shaped_totals():
    entries = [e for m in session._shaped_cache.values() for e in m.values()]
    return sum(e.points for e in entries), max([e.points for e in entries], default=0)


def _tween_totals():
    entries = [e for cache in (session._tween_cache, session._clip_cache)
               for m in cache.values() for e in m.values()]
    return sum(e.points for e in entries), max([e.points for e in entries], default=0)


def test_tiny_budgets_evict_and_stay_correct(animated, monkeypatch):
    low, high, tw = animated
    monkeypatch.setattr(compose, "SHAPED_CACHE_BUDGET_POINTS", 50)
    monkeypatch.setattr(compose, "OCCLUSION_CLIP_BUDGET_POINTS", 50)
    monkeypatch.setattr(compose, "OCCLUSION_MASK_BUDGET_COORDS", 40)
    monkeypatch.setattr("axibridge.session.TWEEN_CACHE_BUDGET_POINTS", 50)

    for master_t in (0.0, 0.25, 0.5, 0.75, 1.0, 0.0, 0.5):
        assert_honest(master_t, f"tiny budgets, master_t={master_t}")

    # an insert is never evicted by its own eviction pass, so the ceiling is
    # the budget plus one entry
    shaped_total, shaped_max = _shaped_totals()
    assert shaped_total <= 50 + shaped_max
    tween_total, tween_max = _tween_totals()
    assert tween_total <= 50 + tween_max
    # the occlusion caches evict at the end of a resolve, protecting nothing
    occ = session._occlusion_cache
    assert sum(e.points for e in occ._clips.values()) <= 50
    assert (sum(e.coords for e in occ._masks.values())
            + sum(e.coords for e in occ._unions.values())) <= 40


def test_generous_budgets_do_not_evict(animated):
    """The mirror image: with the shipped budgets, six frames all stay."""
    low, high, tw = animated
    for master_t in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        session.resolved(master_t=master_t)
    assert len(session._occlusion_cache._clips) >= 6
    assert sum(len(m) for m in session._shaped_cache.values()) >= 6


# -- 6. deleted layers are pruned ---------------------------------------------


def test_deleted_layer_is_pruned_from_the_occlusion_cache(animated):
    low, high, tw = animated
    for master_t in (0.0, 0.5):
        session.resolved(master_t=master_t)
    occ = session._occlusion_cache
    assert any(k[0] == high.id for k in occ._clips)

    session.delete_layer(high.id)
    session.resolved(master_t=0.0)

    assert not any(k[0] == high.id for k in occ._clips)
    assert not any(k[0] == high.id for k in occ._masks)
    assert high.id not in session._shaped_cache
    assert_honest(0.5, "a receiver was deleted")


def test_deleted_occluder_is_pruned_everywhere(animated):
    low, high, tw = animated
    for master_t in (0.0, 0.5):
        session.resolved(master_t=master_t)
    occ = session._occlusion_cache
    assert any(tw.id in compose._sig_layer_ids(k) for k in occ._unions)

    session.delete_layers([tw.id], cascade=True)
    session.resolved(master_t=0.0)

    assert not any(tw.id in compose._sig_layer_ids(k) for k in occ._unions)
    assert not any(k[0] == tw.id for k in occ._masks)
    assert tw.id not in session._tween_cache
    assert_honest(0.5, "the animated occluder was deleted")
