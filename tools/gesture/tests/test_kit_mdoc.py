"""Round 16 thread D (`mdoc`): process documents read the played score."""
import copy
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesture import kit  # noqa: E402
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit import devices_mdoc_ledger as LG  # noqa: E402
from gesture.kit import devices_mdoc_provenance as PV  # noqa: E402
from gesture.kit import devices_mdoc_read as D  # noqa: E402
from gesture.kit import devices_mdoc_staff as ST  # noqa: E402
from gesture.kit import devices_mdoc_sympathy as SY  # noqa: E402
from gesture.kit import devices_mdoc_unheard as UH  # noqa: E402
from gesture.kit._devices import apply_devices, device_list  # noqa: E402
from gesture.kit._relations import relation_list  # noqa: E402
from gesture.kit.core import Sheet  # noqa: E402

FRAME = [200.0, 140.0]
DEVICES = ("mdoc_census", "mdoc_sympathy", "mdoc_ledger", "mdoc_provenance", "mdoc_staff", "mdoc_unheard")


def score(relations, **kw):
    s = {"version": 2, "frame": FRAME, "seed": 16401,
         "layers": [{"id": "A", "pen": "black", "part": {"voice": {"id": "hand", "hand": "marden"}}},
                    {"id": "B", "pen": "red", "part": {"voice": {"id": "hand", "hand": "lichtenberg"}}}],
         "relations": relations}
    s.update(kw)
    return s


MIXED = [{"id": "M", "kind": "mdoc_outcomes", "src": "*", "dst": "*", "params": {"min_sep": 0.0, "streak": 0.0}}]


@pytest.fixture(scope="module")
def mixed():
    return synth.run(score(MIXED))


@pytest.fixture(scope="module")
def yielded():
    return synth.run(score([{"id": "Y", "kind": "yield", "src": "A", "dst": "B"}]))


@pytest.fixture(scope="module")
def v1_sheet():
    return kit.run({"frame": FRAME, "seed": 16401, "parts": [{"voice": {"id": "hand", "hand": "marden"}},
                                                             {"voice": {"id": "hand", "hand": "lichtenberg"}}]})


def without_notes(sh):
    meta = copy.deepcopy(sh.meta)
    meta["notes"] = {}
    return Sheet(sh.frame, list(sh.marks), list(sh.inks), meta)


def test_registered():
    ids = {d["id"] for d in device_list()}
    assert set(DEVICES) <= ids
    assert "mdoc_outcomes" in {r["id"] for r in relation_list()}
    assert not kit.DISCOVERY_ERRORS


def test_test_relation_emits_every_outcome(mixed):
    got = Counter(e["outcome"] for e in synth.played(mixed)["log"])
    assert set(got) == set(D.CROSS_OUTCOMES), got


def test_census_reads_the_log(mixed):
    recs, source = D.crossing_records(mixed)
    assert source == "log"
    n_log = sum(1 for e in synth.played(mixed)["log"] if e["outcome"] in D.CROSS_OUTCOMES)
    assert len(recs) == n_log
    assert {r["src"] for r in recs} == {"A"} and {r["dst"] for r in recs} == {"B"}


def test_census_geometry_finds_the_gaps(yielded):
    n_gaps = sum(1 for m in yielded.marks if m.meta["layer"] == "B") - 1      # B is one line, cut into pieces
    recs, source = D.crossing_records(without_notes(yielded))
    assert source == "geometry"
    found = sum(1 for r in recs if r["outcome"] == "gap_under")
    assert 0.9 * n_gaps <= found <= n_gaps
    assert not any(r["outcome"] == "gap_over" for r in recs)


def test_census_geometry_on_plain_crossings(v1_sheet):
    recs, source = D.crossing_records(v1_sheet)
    assert source == "geometry"
    assert recs and all(r["outcome"] in ("cross", "stop") for r in recs)


@pytest.mark.parametrize("dev", DEVICES)
@pytest.mark.parametrize("which", ["mixed", "v1_sheet"])
def test_every_device_runs_and_degrades(dev, which, request):
    sh = request.getfixturevalue(which)
    for place in ("over", "beside"):
        out = apply_devices(sh, [{"id": dev, "place": place}])
        mine = [i for i in out.inks if (i.meta or {}).get("device") == dev]
        assert mine, f"{dev} drew nothing on {which} ({place}); a missing reading must still say so"
        W, H = out.frame
        for i in mine:
            assert np.all(np.isfinite(i.points))
            assert i.points[:, 0].min() >= -1 and i.points[:, 0].max() <= W + 1
            assert i.points[:, 1].min() >= -1 and i.points[:, 1].max() <= H + 1


def test_devices_deterministic(mixed):
    a = apply_devices(mixed, [{"id": d, "place": "beside"} for d in ("mdoc_census", "mdoc_ledger")])
    b = apply_devices(mixed, [{"id": d, "place": "beside"} for d in ("mdoc_census", "mdoc_ledger")])
    assert len(a.inks) == len(b.inks)
    for x, y in zip(a.inks, b.inks):
        np.testing.assert_array_equal(x.points, y.points)


def test_sympathy_reads_the_lean(mixed, yielded):
    items, why = SY.stretches(mixed)
    assert items and not why
    assert all(it["dst"] == "B" and it["src"] == "A" for it in items)
    assert max(it["max"] for it in items) > 0.1
    items, why = SY.stretches(yielded)
    assert not items and "NO SYMPATHY" in why
    items, why = SY.stretches(without_notes(mixed))
    assert not items and "NO PLAYED LOG" in why


def test_unheard_counts_what_listening_changed(yielded):
    sh_cross = synth.run(score([{"id": "C", "kind": "cross", "src": "*", "dst": "*"}]))
    _, _, ch, tot = UH.changed(sh_cross)
    assert ch == 0.0 and tot > 0
    _, _, ch, tot = UH.changed(yielded)
    assert 0 < ch < 0.2 * tot
    assert UH.changed(without_notes(yielded)) is None


def test_ledger_keeps_silence_and_nothing():
    sh = synth.run(score([{"id": "Q", "kind": "yield", "src": "A", "dst": "B", "p": 0.0},
                          {"id": "Z", "kind": "cross", "src": "A", "dst": "B", "params": {"min_sep": 20.0}}],
                         layers=[{"id": "A", "pen": "black", "region": [5, 5, 60, 60],
                                  "part": {"voice": {"id": "hand", "hand": "marden"}}},
                                 {"id": "B", "pen": "red", "region": [120, 60, 70, 70],
                                  "part": {"voice": {"id": "hand", "hand": "lichtenberg"}}}]))
    rows, source = LG.rows_of(sh)
    assert source == "log"
    by = {r["relation"]: r for r in rows}
    assert set(by["Q"]["outcomes"]) == {"silent"}
    assert set(by["Z"]["outcomes"]) == {"nothing"}             # far apart: played, met nothing
    lays, groups, src = ST.events_by_step(sh)
    assert {g["relation"]: g["state"] for g in groups} == {"Q": "silent", "Z": "nothing"}


def test_provenance_traces_hands_and_sources(mixed):
    d = PV.descent(mixed)
    assert d["layers"]["A"]["hands"].keys() == {"marden"}
    assert d["layers"]["B"]["hands"].keys() == {"lichtenberg"}
    for e in d["hands"].values():
        assert e["source"] and e["source"] != "UNKNOWN" and e["mm"] > 0
