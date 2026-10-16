"""Tests for gesture/regime.py — line → nib → shape metamorphosis."""
import numpy as np
import pytest
from shapely import union_all
from shapely.geometry import LineString, Point

from gesture import regime as rg

PEN = 0.35


def _wave(n=300, L=50.0):
    x = np.linspace(0, L, n)
    return np.column_stack([x, 4 * np.sin(x / 8)])


def _circle(n=200, R=10.0):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([R * np.cos(t), R * np.sin(t)])


def _ink(paths, pen=PEN):
    gs = [LineString(p).buffer(pen / 2) if len(p) > 1 else Point(p[0]).buffer(pen / 2) for p in paths]
    return union_all(gs)


def _n_components(g):
    return 1 if g.geom_type == "Polygon" else len(g.geoms)


def _ops():
    W = 2.4
    base = rg.make(_wave(), 0.0, phi=np.deg2rad(50), W=W)
    straight = rg.make(np.column_stack([np.linspace(0, 40, 200), np.zeros(200)]), 0.0, W=W)
    rng = np.random.default_rng(3)
    mass = rg.swell(rg.thicken(straight, 0.1, until=0.95), 0.5, length=25, size=9)
    return {
        "thicken": rg.thicken(base, 0.3, until=0.7),
        "ramp_0_2": rg.replace(base, r=np.linspace(0, 2, len(base))),
        "bead": rg.swell(straight, 0.5, length=12, size=6),
        "vessel": rg.swell(rg.thicken(straight, 0.1, to=0.6), 0.4, kind="vessel", size=7),
        "close_fill": rg.close_fill(straight, radius=3.0, amount=1.0),
        "eye": rg.eye(straight, radius=4.0),
        "lozenge": rg.terminal_drop(rg.thicken(base, 0.2), kind="lozenge", size=3.0),
        "drop": rg.terminal_drop(base, kind="drop", size=4.0),
        "drips": rg.shed(mass, rng, n=4, kind="drips", length=12),
        "hairs": rg.shed(rg.thicken(base, 0.05, to=1.5), rng, n=5, kind="hairs", length=12),
    }


def test_r0_reproduces_input_line():
    p = _wave()
    out = rg.render(rg.make(p, 0.0, W=3.0), PEN)
    assert len(out) == 1
    np.testing.assert_array_equal(out[0], p)
    c = _circle()
    outc = rg.render(rg.make(c, 0.0, W=3.0, closed=True), PEN)
    assert len(outc) == 1
    np.testing.assert_array_equal(outc[0][:-1], c)
    np.testing.assert_array_equal(outc[0][-1], c[0])


@pytest.mark.parametrize("name", list(_ops().keys()))
def test_operators_render_one_connected_mark(name):
    st = _ops()[name]
    paths = rg.render(st, PEN)
    assert paths, name
    for p in paths:
        assert isinstance(p, np.ndarray) and p.ndim == 2 and p.shape[1] == 2 and len(p) >= 2
        assert np.isfinite(p).all()
    # no gaps between regime segments: lines + outlines are ONE connected
    # region (graded fill may pool as a core island INSIDE the outline)
    edge = _ink(rg.render(st, PEN, fill=False))
    assert _n_components(edge) == 1, name
    from shapely import polygonize
    lines = union_all([LineString(p) for p in rg.render(st, PEN, fill=False)])
    hull = union_all([edge, polygonize(list(getattr(lines, "geoms", [lines])))]).buffer(1e-6)
    ink = _ink(paths)
    assert ink.difference(hull).area < 2e-3 * ink.area, name


def test_outlines_are_closed_and_nib_ribbon_is_one_contour():
    st = rg.make(_circle(R=12.0), 1.0, phi=np.deg2rad(45), W=3.0, closed=True)
    paths = rg.render(st, PEN, fill=False)
    assert len(paths) == 2                  # outer and inner edge of the ring-ribbon
    for p in paths:
        np.testing.assert_allclose(p[0], p[-1])
    # an open nib stroke: one closed outline (the line runs have length 0)
    op = rg.render(rg.make(_wave(), 1.0, W=2.0), PEN, fill=False)
    assert len(op) == 1 and np.allclose(op[0][0], op[0][-1])


def test_line_to_nib_is_one_path():
    """A line that thickens: the line run continues round the ribbon's
    outline without a pen lift."""
    st = rg.thicken(rg.make(_wave(), 0.0, W=2.5), 0.5)
    paths = rg.render(st, PEN, fill=False)
    assert len(paths) == 1
    np.testing.assert_allclose(paths[0][0], st.points[0])


def test_width_monotone_in_r_for_every_direction():
    th = np.linspace(0, np.pi, 37)
    pts_dirs = [np.array([[0, 0], [np.cos(t), -np.sin(t)]]) for t in th]
    rs = np.linspace(0, 2, 41)
    for p in pts_dirs:
        w = [rg.ink_width(rg.make(p, r, phi=0.7, W=2.0, mass=6.0, w_min=0.5), PEN)[0] for r in rs]
        assert np.all(np.diff(w) >= -1e-12)
    # r=0 is exactly the pen; r=1 is the nib law; r=2 reaches the mass
    p = pts_dirs[10]
    t = th[10]
    assert rg.ink_width(rg.make(p, 0.0, phi=0.7, W=2.0), PEN)[0] == pytest.approx(PEN)
    assert rg.ink_width(rg.make(p, 1.0, phi=0.7, W=2.0, w_min=0.5), PEN)[0] == pytest.approx(
        2.0 * abs(np.sin(t - 0.7)) + 0.5)
    assert rg.ink_width(rg.make(p, 2.0, phi=0.7, W=2.0, mass=6.0), PEN)[0] >= 6.0


def test_width_has_no_jumps_at_regime_changes():
    p = np.column_stack([np.linspace(0, 60, 1201), np.zeros(1201)])
    st = rg.replace(rg.make(p, 0.0, phi=1.2, W=2.0), r=2.0 * np.clip(np.linspace(-0.2, 1.2, 1201), 0, 1))
    w = rg.ink_width(st, PEN)
    step = 0.05
    slope = np.abs(np.diff(w)) / step
    # bounded slope everywhere (C⁰ with a finite derivative — no seams)
    assert slope.max() < 1.0
    # and the slope itself changes smoothly through r = 1 (smoothstep: C¹)
    i1 = int(np.argmin(np.abs(st.r - 1.0)))
    assert slope[i1 - 2:i1 + 2].max() < 0.05


def test_fill_only_where_mass():
    st = rg.make(_wave(), 1.0, W=2.0)
    assert len(rg.render(st, PEN)) == len(rg.render(st, PEN, fill=False))
    m = rg.make(_wave(), 2.0, W=2.0, mass=5.0)
    assert len(rg.render(m, PEN)) > len(rg.render(m, PEN, fill=False)) + 3


def test_closing_loop_drops_the_counter():
    straight = rg.make(np.column_stack([np.linspace(0, 30, 120), np.zeros(120)]), 0.0, W=2.0)
    open_ring = rg.close_fill(straight, radius=4.0, amount=0.0)
    closed = rg.close_fill(straight, radius=3.0, amount=1.0)
    # amount 0: just a line loop; amount 1: ink covers the loop's disc
    ink = _ink(rg.render(closed, PEN))
    c = closed.points[-len(closed.points) // 6:].mean(0)
    assert ink.contains(Point(c))
    assert len(rg.render(open_ring, PEN)) == 1


def test_determinism_and_purity():
    ops1, ops2 = _ops(), _ops()
    for k in ops1:
        a = rg.render(ops1[k], PEN)
        b = rg.render(ops2[k], PEN)
        assert len(a) == len(b)
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x, y)
    st = rg.make(_wave(), np.linspace(0, 2, 300), W=2.0)
    snap = {f: getattr(st, f).copy() for f in ("points", "r", "phi", "W", "mass")}
    rg.render(st, PEN)
    rg.thicken(st, 0.2)
    rg.swell(st, 0.5)
    rg.close_fill(st)
    rg.eye(st)
    rg.terminal_drop(st)
    rg.shed(st, np.random.default_rng(0))
    rg.resample(st, 0.3)
    for f, v in snap.items():
        np.testing.assert_array_equal(getattr(st, f), v)


def test_from_field():
    p = _wave(400)
    st = rg.from_field(p, lambda x, y: np.where(x > 25, 2.0, 0.0), W=2.0)
    assert st.r.min() >= 0 and st.r.max() <= 2
    assert st.r[0] == pytest.approx(0, abs=1e-6) and st.r[-1] == pytest.approx(2, abs=1e-6)
    assert np.abs(np.diff(st.r)).max() < 0.2          # smoothed: no step
    # a scalar-only field function works too
    st2 = rg.from_field(p, lambda x, y: 1.0 if float(x) > 10 else 0.0, W=2.0, smooth=0)
    assert set(np.unique(st2.r)) <= {0.0, 1.0}
    assert rg.render(st, PEN) and rg.render(st2, PEN)


def test_regime_cost_partitions_pen_length():
    st = rg.replace(rg.make(_wave(), 0.0, W=2.0, mass=5.0), r=np.linspace(0, 2, 300))
    paths = rg.render(st, PEN)
    c = rg.regime_cost(st, paths)
    tot = sum(v["pen_mm"] for v in c.values())
    assert tot == pytest.approx(rg.pen_cost(paths)["length"], rel=1e-6)
    assert c["line"]["per_mm"] < c["nib"]["per_mm"] < c["shape"]["per_mm"]


# ---------------------------------------------------------------------------
# round 7: wet mass edges, rim fix, edge events, spiral fill, drips
# ---------------------------------------------------------------------------

def _oval():
    p = np.column_stack([np.linspace(0, 10, 60), np.zeros(60)])
    return rg.make(p, 2.0, W=1e-3, mass=np.full(60, 9.0))


def _wet_marks():
    W = 2.4
    straight = rg.make(np.column_stack([np.linspace(0, 40, 200), np.zeros(200)]), 0.0, W=W)
    base = rg.make(_wave(), 0.0, phi=np.deg2rad(50), W=W)
    return {
        "bead": rg.swell(straight, 0.5, length=12, size=6),
        "nib_mass": rg.swell(rg.thicken(base, 0.1, until=0.95), 0.35, length=20, size=9),
        "drop": rg.terminal_drop(base, kind="drop", size=4.5),
        "oval": _oval(),
    }


@pytest.mark.parametrize("name", ["bead", "nib_mass", "drop", "oval"])
@pytest.mark.parametrize("wet", [None, "marden"])
def test_fill_reaches_the_edge(name, wet):
    """No white rim wider than the pen between a mass's outline and its fill
    (round 6 left 1.05–1.17 mm on bead / nib-mass / drop)."""
    st = _wet_marks()[name]
    paths = rg.render(st, PEN, wet=wet, seed=3)
    assert rg.rim_gap(st, paths, PEN) <= PEN + 1e-9, (name, wet)


def test_wet_outlines_closed_polylines_and_deterministic():
    st = _wet_marks()["nib_mass"]
    a = rg.render(st, PEN, wet="hokusai", seed=5)
    b = rg.render(st, PEN, wet="hokusai", seed=5)
    c = rg.render(st, PEN, wet="hokusai", seed=6)
    assert len(a) == len(b) and all(np.array_equal(x, y) for x, y in zip(a, b))
    assert not (len(a) == len(c) and all(np.array_equal(x, y) for x, y in zip(a, c)))
    for p in a:
        assert isinstance(p, np.ndarray) and p.ndim == 2 and p.shape[1] == 2 and len(p) >= 2
        assert np.isfinite(p).all()
    outl = rg.render(st, PEN, wet="hokusai", seed=5, fill=False, splice=False)
    rings = [p for p in outl if len(p) > 3 and np.allclose(p[0], p[-1])]
    assert rings, "the mass outline is a closed ring"
    # default seed is a geometry hash: deterministic without a seed too
    d1, d2 = rg.render(st, PEN, wet=True), rg.render(st, PEN, wet=True)
    assert all(np.array_equal(x, y) for x, y in zip(d1, d2))


def test_wet_leaves_lines_and_nibs_untouched():
    for r in (0.0, 1.0):
        st = rg.make(_wave(), r, phi=np.deg2rad(50), W=2.4)
        dry = rg.render(st, PEN)
        wet = rg.render(st, PEN, wet="marden", seed=1)
        assert len(dry) == len(wet) and all(np.allclose(x, y) for x, y in zip(dry, wet)), r


def test_wet_mass_varies_and_stays_one_piece():
    from shapely.geometry import Polygon
    areas = []
    for sd in range(4):
        outl = rg.render(_oval(), PEN, wet="reference", seed=sd, fill=False)
        ring = max(outl, key=len)
        assert np.allclose(ring[0], ring[-1])
        areas.append(Polygon(ring).area)
    assert np.std(areas) > 0.5                       # no two masses alike
    assert min(areas) > 0.6 * max(areas)             # but none eaten away


def test_scallop_and_notch_edge_events():
    from shapely.geometry import Polygon
    vert = rg.make(np.column_stack([np.zeros(240), np.linspace(0, 48, 240)]), 2.0, W=1e-3,
                   mass=np.full(240, 7.0))
    plain = Polygon(max(rg.render(vert, PEN, fill=False), key=len))
    for mode, sign in (("scallop", 1), ("notch", -1)):
        ev = {"mode": mode, "count": 6, "amp": 0.2, "extent": (0.2, 0.8), "side": 1}
        g = Polygon(max(rg.render(vert, PEN, fill=False, edge=ev), key=len))
        assert sign * (g.area - plain.area) > 0.5, mode
        # one side only: the other half-plane is unchanged
        cx = plain.centroid.x
        from shapely.geometry import box
        dl = abs(g.intersection(box(cx - 20, -10, cx, 60)).area - plain.intersection(box(cx - 20, -10, cx, 60)).area)
        dr = abs(g.intersection(box(cx, -10, cx + 20, 60)).area - plain.intersection(box(cx, -10, cx + 20, 60)).area)
        assert min(dl, dr) < 0.05 * max(dl, dr), mode
    # per-stroke meta works like the argument
    m = rg.render(rg.replace(vert, meta={"edge": "scallop"}), PEN, fill=False)
    assert not np.allclose(max(m, key=len)[:50], max(rg.render(vert, PEN, fill=False), key=len)[:50])


def test_spiral_fill_fewer_lifts_same_ink():
    st = _wet_marks()["nib_mass"]
    conc = rg.render(st, PEN, wet="reference", seed=2)
    spir = rg.render(st, PEN, wet="reference", seed=2, fill_style="spiral")
    assert len(spir) < len(conc)
    ic, isp = _ink(conc), _ink(spir)
    assert isp.symmetric_difference(ic).area < 0.03 * ic.area


def test_drips_are_solid_threads_with_variety():
    rng = np.random.default_rng(1)
    st = rg.swell(rg.make(np.column_stack([np.linspace(0, 40, 200), np.zeros(200)]), 1.0, W=2.4), 0.5,
                  length=30, size=10)
    mark = rg.shed(st, rng, n=6, kind="drips", length=14, where=(0.3, 0.7))
    kids = mark[1:]
    assert len(kids) == 6 and all(k.meta.get("shed") == "drip" for k in kids)
    lens = [k.length() for k in kids]
    assert np.std(lens) / np.mean(lens) > 0.15       # irregular lengths
    assert all(k.fill is not None and np.all(k.fill == 1) for k in kids)
    paths = rg.render(mark, PEN)
    assert rg.rim_gap(mark, paths, PEN) <= PEN + 1e-9
    assert _n_components(_ink(rg.render(mark, PEN, fill=False))) == 1


def test_nib_renderer_hook():
    st = _wet_marks()["bead"]
    seen = {}

    def hook(*, strokes, pen, paths, parts):
        seen.update(parts)
        return paths[:1]

    out = rg.render(st, PEN, nib_renderer=hook)
    assert len(out) == 1 and {"G", "F", "runs", "rings", "fill"} <= set(seen)
