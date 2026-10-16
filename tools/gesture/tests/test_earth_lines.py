"""gesture/earth_lines.py: hand-parsed shapefile/DBF, hosts, data-born fields."""
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import earth_lines as el  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402


def _write_shp(path, lines):
    recs = b""
    for i, p in enumerate(lines, 1):
        p = np.asarray(p, float)
        body = struct.pack("<i", 3) + struct.pack("<4d", *p.min(0), *p.max(0))
        body += struct.pack("<ii", 1, len(p)) + struct.pack("<i", 0) + p.astype("<f8").tobytes()
        recs += struct.pack(">ii", i, len(body) // 2) + body
    hdr = struct.pack(">i", 9994) + b"\0" * 20 + struct.pack(">i", (100 + len(recs)) // 2)
    hdr += struct.pack("<ii", 1000, 3) + struct.pack("<8d", 0, 0, 1, 1, 0, 0, 0, 0)
    path.write_bytes(hdr + recs)


def _write_dbf(path, cols, rows):
    n = len(rows)
    fields = b""
    rl = 1
    for name, ln in cols:
        fields += name.encode().ljust(11, b"\0") + b"N" + b"\0" * 4 + bytes([ln, 0]) + b"\0" * 14
        rl += ln
    hl = 32 + len(fields) + 1
    head = bytes([3, 26, 10, 16]) + struct.pack("<IHH", n, hl, rl) + b"\0" * 20
    body = b"".join(b" " + b"".join(str(v).rjust(ln).encode() for v, (_, ln) in zip(r, cols)) for r in rows)
    path.write_bytes(head + fields + b"\r" + body + b"\x1a")


def test_shp_dbf_roundtrip(tmp_path):
    lines = [[[0, 0], [1, 1]], [[2, 2], [3, 5], [4, 4]]]
    _write_shp(tmp_path / "a.shp", lines)
    _write_dbf(tmp_path / "a.dbf", [("width_m", 7), ("segmentID", 5)], [(120, 1), ("", 2)])
    P = el.read_shp_polylines(tmp_path / "a.shp")
    assert len(P) == 2 and np.allclose(P[1], lines[1])
    T = el.read_dbf(tmp_path / "a.dbf")
    assert T["width_m"][0] == 120 and np.isnan(T["width_m"][1]) and T["segmentID"][1] == 2


def _tree():
    trunk = np.column_stack([np.full(50, 100.0), np.linspace(400, 100, 50)])
    br = np.column_stack([np.linspace(100, 200, 30), np.linspace(250, 150, 30)])
    tw = np.column_stack([np.linspace(200, 260, 20), np.linspace(150, 120, 20)])
    return Drawing([Stroke(trunk, width=np.full(50, 12.0)), Stroke(br, width=np.full(30, 4.0)),
                    Stroke(tw, width=np.full(20, 1.0))], size=(400, 500))


def test_with_hosts_tree_and_purity():
    d = _tree()
    h = el.with_hosts(d)
    assert h.strokes[0].meta["host"] is None
    assert h.strokes[1].meta["host"] == 0 and h.strokes[2].meta["host"] == 1
    assert "host" not in d.strokes[0].meta            # input untouched
    assert [s.meta["order"] for s in h.strokes] == [0, 1, 2]


def test_data_field_maps_width_to_regimes():
    d = _tree()
    f, r_pt = el.data_field(d, el.width_values(d), levels=(2.0, 8.0), soft=0.1, reach=0.05)
    assert r_pt[:50].min() > 1.9 and r_pt[-20:].max() < 0.1
    assert 0.9 < r_pt[60] < 1.1
    u = np.array([[100 / 400, 300 / 500], [0.95, 0.95]])    # on the trunk; far away
    r = f(u)
    assert r[0] > 1.9 and r[1] < 0.05
    assert f.meta["family"] == "data"


def test_curl_rises_on_a_tightening_spiral():
    t = np.linspace(0, 6 * np.pi, 3000)
    rad = 200 * np.exp(-t / 8)
    p = np.column_stack([300 + rad * np.cos(t), 300 + rad * np.sin(t)])
    d = Drawing([Stroke(p)], size=(600, 600))
    k = el.curl_values(d, sigma_frac=0.003)[0]
    a, b = np.median(k[200:600]), np.median(k[-600:-200])
    assert b > 2 * a                                   # the slowing particle curls up


def test_fit_to_sheet_scales_widths():
    d = _tree()
    f = el.fit_to_sheet(d, (840, 1200))
    k = f.meta["fit_scale"]
    assert np.allclose(f.strokes[0].width, 12.0 * k)
    pts = np.vstack([s.points for s in f.strokes])
    assert pts.min() >= 0 and pts[:, 0].max() <= 840 and pts[:, 1].max() <= 1200


@pytest.mark.skipif(not (el.EARTH / "grwl-vec-SB20" / "SB20.shp").exists(), reason="GRWL tile not on disk")
def test_grwl_window_has_widths():
    d = el.grwl_window("SB20", (-64.3, -5.8, -63.9, -5.4), px=400)
    assert d.strokes and all(s.width is not None for s in d.strokes)
    w_m = np.concatenate([s.width for s in d.strokes]) * d.meta["m_per_px"]
    assert 30 <= np.median(w_m) <= 3000              # Purus-scale channel widths
