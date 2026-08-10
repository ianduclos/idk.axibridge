"""``gencache.generate_cached`` — content-keyed memo of SourceModule.generate().

A counting stub source (registered once, module-level, like any real source)
lets these tests assert exactly how many times generate() actually ran,
rather than just that geometry came back right."""

from __future__ import annotations

import random

import pytest
from pydantic import BaseModel, Field

from axibridge import gencache
from axibridge.assets import AssetStore
from axibridge.model import Layer, Path, PathDocument
from axibridge.registry import SourceModule, get_source, register_source
from axibridge.session import session

#: bumped inside StubSource.generate(); reset to 0 at the top of every test
#: that cares about the count (the underlying registry entry is shared across
#: the whole test session, so tests never assume a starting value of 0).
_calls = {"n": 0}


class StubParams(BaseModel):
    n: int = Field(default=5, ge=1, le=100_000, title="point count")
    #: irrelevant to the geometry — lets tests mint distinct cache keys for
    #: an otherwise-identical shape (eviction test).
    tag: int = Field(default=0, ge=0, le=1_000_000)


@register_source
class StubSource(SourceModule):
    id = "gencache_test_stub"
    orientation = "none"  # required by tests/test_orientation.py's guard
    label = "gencache test stub"
    Params = StubParams

    def generate(self, params: StubParams) -> PathDocument:
        _calls["n"] += 1
        pts = [(float(i), float(i)) for i in range(params.n)]
        return PathDocument(layers=[Layer(id=1, paths=[Path(points=pts)])])


@pytest.fixture(autouse=True)
def _reset():
    _calls["n"] = 0
    gencache.clear()
    yield
    gencache.clear()


def _points(doc: PathDocument) -> list:
    return [p.points for lyr in doc.layers for p in lyr.paths]


# -- 1. equivalence -----------------------------------------------------------


def test_generate_cached_matches_direct_call():
    src = get_source("gencache_test_stub")
    direct = src.generate(src.Params(n=7))
    cached = gencache.generate_cached(src, {"n": 7})
    assert _points(cached) == _points(direct)


# -- 2. memo hit + canonicalization -------------------------------------------


def test_memo_hit_canonicalizes_int_float_drift():
    src = get_source("gencache_test_stub")
    r1 = gencache.generate_cached(src, {"n": 5})
    r2 = gencache.generate_cached(src, {"n": 5.0})  # float variant of the same value
    assert _calls["n"] == 1
    assert r1 is r2


# -- 3. session-level: a follow_master tween over identical keyframes --------


def test_session_tween_scrub_does_not_regenerate_identical_keyframes():
    """``animate_layer`` splits a layer into hidden A/B keyframes (B is a
    duplicate of A, so IDENTICAL generator params) plus a visible
    ``follow_master`` tween. Session's own ``_tween_cache`` keys on override_t
    (which changes every scrub tick), so without gencache each
    ``resolved(master_t=...)`` call would regenerate via
    ``tween._source_paths_at``. Since A and B share params, the lerped params
    tween.materialize hands to generate_cached are byte-identical at every
    t — the memo should absorb the whole scrub."""
    layer = session.add_generated_layer("gencache_test_stub", {"n": 9})
    assert _calls["n"] == 1  # the original layer's own generation

    tween_layer = session.animate_layer(layer.id)
    assert tween_layer.source.type == "tween"
    # animate_layer duplicates B's *source_geometry* directly, no generate()
    assert _calls["n"] == 1

    session.resolved(master_t=0.3)
    warm = _calls["n"]
    assert warm == 1, "the tween's lerped params equal the original -> cache hit"

    session.resolved(master_t=0.7)
    assert _calls["n"] == warm, "a different master_t must not force regeneration"


# -- 4. eviction ---------------------------------------------------------------


def test_eviction_keeps_cache_bounded_and_regenerates_after(monkeypatch):
    src = get_source("gencache_test_stub")
    monkeypatch.setattr(gencache, "GENERATE_MEMO_BUDGET_POINTS", 25)
    monkeypatch.setattr(gencache, "GENERATE_MEMO_MAX_ENTRIES", 1000)
    # Deterministic eviction order: candidates come from dict iteration
    # (insertion order), so always evicting candidates[0] evicts the OLDEST
    # surviving entry — turns the random policy into FIFO for this test only,
    # so the assertions below don't depend on random.choice's draw.
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])

    for tag in range(10):  # 10 entries x 10 points = 100 points, budget is 25
        gencache.generate_cached(src, {"n": 10, "tag": tag})

    assert gencache._total_points <= 25
    assert len(gencache._cache) < 10, "eviction must have dropped some entries"

    before = _calls["n"]
    # tag=0 was the very first insert -> deterministically the first evicted
    result = gencache.generate_cached(src, {"n": 10, "tag": 0})
    assert _calls["n"] == before + 1, "an evicted entry must regenerate"
    assert len(result.layers[0].paths[0].points) == 10  # geometry still correct


# -- 5. invalidation on asset change -------------------------------------------


def test_asset_version_bump_invalidates_memo(monkeypatch):
    # A private AssetStore, swapped in for gencache's module-level import, so
    # this test can't leak asset state into the rest of the suite.
    fake_store = AssetStore()
    monkeypatch.setattr(gencache, "asset_store", fake_store)
    src = get_source("gencache_test_stub")

    gencache.generate_cached(src, {"n": 5})
    assert _calls["n"] == 1
    gencache.generate_cached(src, {"n": 5})
    assert _calls["n"] == 1  # cache hit, no version change yet

    fake_store.put("probe.bin", b"anything")  # bumps AssetStore._version
    gencache.generate_cached(src, {"n": 5})
    assert _calls["n"] == 2, "the version bump must orphan the old memo entry"


# -- 6. cacheable=False bypasses the cache entirely ----------------------------


class _NonCacheableParams(BaseModel):
    n: int = Field(default=1, ge=1, le=100)


@register_source
class NonCacheableStubSource(SourceModule):
    id = "gencache_test_stub_noncacheable"
    orientation = "none"
    label = "gencache test stub (non-cacheable)"
    Params = _NonCacheableParams
    cacheable = False

    def generate(self, params: _NonCacheableParams) -> PathDocument:
        _calls["n"] += 1
        return PathDocument(layers=[Layer(id=1, paths=[Path(points=[(0.0, 0.0), (1.0, 1.0)])])])


def test_cacheable_false_never_caches():
    src = get_source("gencache_test_stub_noncacheable")
    gencache.generate_cached(src, {"n": 1})
    gencache.generate_cached(src, {"n": 1})
    gencache.generate_cached(src, {"n": 1})
    assert _calls["n"] == 3
    assert not gencache._cache, "a non-cacheable source must never enter the memo"
