import numpy as np
import pytest

from tools.gesture.gesture import script_syntax as ss
from tools.gesture.gesture.calligraphy import PolicyError
from tools.gesture.gesture.core import Drawing, Stroke


def _synthetic_mask(angle_deg=0.0):
    """Two 'lines' of horizontal bars (bodies, pen 4 px) with a tall
    ascender in each and a dot above every bar."""
    H, W = 260, 600
    m = np.zeros((H, W), bool)
    for base in (90, 200):
        for x0 in range(40, 560, 70):
            m[base - 4:base, x0:x0 + 50] = True             # body along the baseline
            m[base - 40:base, x0 + 20:x0 + 24] = True       # ascender
            m[base - 22:base - 18, x0 + 38:x0 + 42] = True  # dot above
    return m


def test_measure_synthetic_lines_dots_ascenders():
    r = ss.measure_mask(_synthetic_mask(), source="synthetic", w=4.0, angle=0.0)
    assert len(r["lines"]) == 2
    b = [b for ln in r["lines"] for b in ln["bodies"]]
    assert len(b) == 16
    assert all(len(x["asc"]) == 1 for x in b)
    assert np.median([x["asc"][0][1] for x in b]) == pytest.approx(9.5, abs=1.0)
    dots = [d for x in b for d in x["dots"]]
    assert len(dots) == 16 and all(d["dy"] < 0 for d in dots)    # above the baseline
    gaps = [x["gap"] for x in b if x["gap"] is not None]
    assert np.median(gaps) == pytest.approx(5.0, abs=0.6)        # 20 px gap / w 4


def test_rotation_maps_angle_to_horizontal():
    a = 30.0
    d = np.array([[np.cos(np.deg2rad(a)), -np.sin(np.deg2rad(a))]])   # seen-CCW direction, y down
    r = ss._rot(d, a)
    assert r[0, 0] == pytest.approx(1.0) and r[0, 1] == pytest.approx(0.0, abs=1e-12)


def test_policy_gate():
    rec = ss.measure_mask(_synthetic_mask(), source="AL08_p0018", w=4.0, angle=0.0)
    with pytest.raises(PolicyError):
        ss.SyntaxModel.fit([rec], generative=True)             # print = measure-only
    m = ss.SyntaxModel.fit([rec], generative=False)
    with pytest.raises(PolicyError):
        m.sample_line(np.random.default_rng(0), 40)
    rec2 = dict(rec, source="wc-05")                           # diwani document: generative
    g = ss.SyntaxModel.fit([rec2], generative=True)
    slots = g.sample_line(np.random.default_rng(0), 40)
    assert slots and all("width" in s for s in slots)


def _bank():
    rng = np.random.default_rng(1)
    t = np.linspace(0, 6 * np.pi, 400)
    p = np.column_stack([t * 30, 40 * np.sin(t) + 5 * np.sin(3.1 * t)])
    d = Drawing([Stroke(p)], source="toy", size=(600, 100))
    return ss.fragment_bank([d], rng, n=60, len_frac=(0.05, 0.15))


def test_fragments_normalised():
    bank = _bank()
    assert len(bank) >= 30
    for f in bank:
        assert f.pts[0] == pytest.approx([0, 0], abs=1e-9)
        assert f.pts[-1] == pytest.approx([1, 0], abs=1e-9)
        assert f.bulge >= f.depth                              # main bulge up


def test_assemble_and_controls_keep_ink():
    rec = dict(ss.measure_mask(_synthetic_mask(), w=4.0, angle=0.0), source="wc-05")
    model = ss.SyntaxModel.fit([rec], generative=True)
    rng = np.random.default_rng(3)
    bank = _bank()
    slots = model.sample_line(rng, 60)
    pcs = ss.assemble_line(slots, bank, rng, x_right=800, base=100, w=8.0)
    kinds = {p.kind for p in pcs}
    assert {"arch", "dot"} <= kinds
    assert all(p.pts[:, 0].max() <= 800 + 1e-6 for p in pcs if p.kind in ("arch", "conn"))
    sc = ss.scatter_control(pcs, (0, 0, 800, 200), rng)
    assert ss.ink_length(sc) == pytest.approx(ss.ink_length(pcs))
    assert len(sc) == len(pcs)
    ch = ss.chain_control(pcs, (0, 0, 800, 200), rng)
    assert len(ch) == len(pcs)
    img = ss.render(pcs, (820, 200))
    assert img.size == (820, 200)


def test_density_masses_from_overwriting():
    rng = np.random.default_rng(0)
    line = np.column_stack([np.linspace(20, 180, 80), np.full(80, 50.0)])
    pcs = [ss.Piece("arch", line + rng.normal(0, 1.0, 2), 0) for _ in range(20)]
    assert ss.density_masses(pcs[:1], (200, 100), pen=2, sigma=3, thresh=0.3, min_area=50) == []
    assert len(ss.density_masses(pcs, (200, 100), pen=2, sigma=3, thresh=0.3, min_area=50)) >= 1


def test_wc30_excluded_from_generative_pool():
    rec = dict(ss.measure_mask(_synthetic_mask(), w=4.0, angle=0.0), source="wc-30")
    assert not ss.generative_ok("wc-30")
    assert ss.generative_ok("wc-05")
    with pytest.raises(PolicyError):
        ss.SyntaxModel.fit([rec], generative=True)
    with pytest.raises(PolicyError):
        ss.SyntaxModel.fit([rec, dict(rec, source="wc-05")], generative=True)
    ss.SyntaxModel.fit([rec], generative=False)                 # measurement stays allowed


def test_experiment_models_exclude_wc30():
    import json
    from tools.gesture.experiments import script_syntax as ex
    if not (ex.OUT / "records.json").exists():
        pytest.skip("no measured records on this machine")
    recs = json.loads((ex.OUT / "records.json").read_text())
    assert all(not r["generative"] for r in recs if r["source"] == "wc-30")
    for m in ex.models().values():
        assert "wc-30" not in m.sources and m.generative
