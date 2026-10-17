"""Tests for the polyphonic-sheets kit modules (kit/poly_sheets.py,
kit/poly_converse.py): clipping, band warp, the three arrangers,
annotation and determinism. Small recipes; < 30 s."""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

from gesture import kit
from gesture.kit import core
from gesture.kit.core import Mark, RecipeError
from gesture.kit.poly_converse import line_stats
from gesture.kit.poly_sheets import band_warp, clip_marks, cut_marks

POOL = "bubble lichtenberg marden matisse shikasta"
W = {"id": "wire", "pen": 0.35}


def digest(sheet) -> str:
    h = hashlib.sha256()
    for m in sheet.marks:
        h.update(np.ascontiguousarray(m.points).tobytes())
    return h.hexdigest()


def scatter(**arr):
    return {"seed": 41, "frame": [200, 140],
            "arranger": {"id": "poly_scatter", "counts": [1, 3, 1], "sizes": [0.5, 0.2], "mode": "restate", **arr},
            "parts": [{"voice": {"id": "hand", "hand": "matisse", "length": 0.8}},
                      {"voice": {"id": "hand", "hand": "marden", "length": 0.5}},
                      {"voice": {"id": "hand", "hand": "lichtenberg", "length": 0.4}}],
            "renderer": W}


def test_registered():
    reg = core.registry("arranger")
    for i in ("poly_scatter", "poly_page", "poly_converse"):
        assert i in reg
    assert not [k for k in core.DISCOVERY_ERRORS if k.startswith("poly")]


def test_clip_splits_at_boundary_and_carries_channels():
    x = np.linspace(-10, 30, 81)
    m = Mark(np.column_stack([x, np.full_like(x, 5.0)]), {"tremor": x * 0.1, "voice": np.zeros_like(x)})
    out = clip_marks([m], (0.0, 0.0, 20.0, 10.0))
    assert len(out) == 1
    p = out[0].points
    assert p[0, 0] == pytest.approx(0.0, abs=1e-5) and p[-1, 0] == pytest.approx(20.0, abs=1e-5)
    assert "tremor" in out[0].channels and out[0].meta["edge"] is True
    assert out[0]["tremor"][0] == pytest.approx(0.0, abs=1e-4)
    # a line leaving and re-entering splits in two
    t = np.linspace(0, 2 * np.pi, 200)
    w = Mark(np.column_stack([10 + 15 * np.cos(t), 5 + 3 * np.sin(t)]))
    assert len(clip_marks([w], (0.0, 0.0, 20.0, 10.0))) == 2


def test_cut_marks_covers_the_line():
    x = np.linspace(0, 100, 201)
    m = Mark(np.column_stack([x, np.zeros_like(x)]))
    pcs = cut_marks([m], [25.0, 60.0])
    assert [round(sum(mm.length() for mm in pc), 6) for pc in pcs] == [25.0, 35.0, 40.0]


def test_band_warp_follows_route():
    rng = np.random.default_rng(0)
    q = np.cumsum(rng.normal(size=(300, 2)), axis=0)
    path = np.array([[0.0, 50.0], [100.0, 50.0]])
    (p,) = band_warp([q], path, 2.0)
    assert p.shape == q.shape
    assert p[:, 0].min() >= -1e-6 and p[:, 0].max() <= 100 + 1e-6
    assert np.percentile(np.abs(p[:, 1] - 50.0), 95) <= 2.0 + 1e-6


def test_scatter_units_bleed_and_determinism():
    s = kit.run(scatter(bleed=1.0))
    parts = {m.meta["part"] for m in s.marks}
    assert parts == {0, 1, 2}
    assert any(m.meta.get("edge") for m in s.marks)          # units reach the sheet edge
    x0 = s.meta["inset"]
    allp = np.vstack([m.points for m in s.marks])
    assert allp.min() >= x0 - 1e-6 and allp[:, 0].max() <= 200 - x0 + 1e-6
    assert digest(s) == digest(kit.run(scatter(bleed=1.0)))


def test_scatter_annotation_modes():
    for mode in ("underline", "bracket", "encircle", "tether", "point", "echo"):
        s = kit.run(scatter(annotate=mode, n_annot=2, counts=[1, 3, 1]))
        ann = [m for m in s.marks if "annotation" in m.meta]
        assert ann, mode
        assert all(m.meta["part"] == 2 and m.meta["annotation"] == mode for m in ann)


def test_annotation_needs_two_parts():
    r = scatter(annotate="underline")
    r["parts"] = r["parts"][:1]
    with pytest.raises(RecipeError):
        kit.run(r)


def test_page_rows_glosses_annotation():
    r = {"seed": 5, "frame": [200, 140],
         "arranger": {"id": "poly_page", "roles": "body gloss", "rows": 4, "words": 12,
                      "annotate": "bracket", "n_annot": 2},
         "parts": [{"voice": {"id": "hand", "hand": "shikasta", "length": 1.5}},
                   {"voice": {"id": "hand", "hand": "bubble", "length": 1.0}},
                   {"voice": {"id": "hand", "hand": "lichtenberg", "length": 0.3}}],
         "renderer": W}
    s = kit.run(r)
    body = [m for m in s.marks if m.meta["part"] == 0]
    assert len(body) >= 8                                    # words, not one line
    assert any(m.meta["part"] == 1 for m in s.marks)
    assert any(m.meta.get("annotation") == "bracket" for m in s.marks)
    with pytest.raises(RecipeError):
        kit.run({**r, "arranger": {**r["arranger"], "roles": "body nonsense"}})


def test_converse_replies_change_hand():
    r = {"seed": 77, "frame": [200, 140],
         "arranger": {"id": "poly_converse", "turns": 5, "pool": POOL, "reply": "contrast", "memory": 1},
         "parts": [{"voice": {"id": "hand", "hand": "matisse", "length": 0.6}},
                   {"voice": {"id": "drift", "hands": ["marden"], "length": 0.6}}],
         "renderer": W}
    s = kit.run(r)
    log = s.marks[0].meta["converse_log"]
    assert len(log) == 5 and log[0]["hand"] == "matisse"
    for a, b in zip(log, log[1:]):
        assert b["hand"] != a["hand"] and b["hand"] in POOL.split()
    assert digest(s) == digest(kit.run(r))
    used = {e["id"] for e in s.meta["library"] if e["kind"] == "hand"}
    assert {e["hand"] for e in log} <= used


def test_line_stats_scale_free():
    t = np.linspace(0, 6 * np.pi, 600)
    q = np.column_stack([t * np.cos(t), t * np.sin(t)])
    a = line_stats([Mark(q)])
    b = line_stats([Mark(q * 7.3 + 4)])
    assert np.allclose(a, b, atol=1e-6)
