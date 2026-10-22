"""pen_ops.js — the pure curve-editing math behind the pen v2 gestures.

The module is loaded straight from SOURCE (`axibridge/static/js/pen_ops.js`)
into a blank chromium page as a data: URL module — not through the app
server, whose bundled `static_dist/` folds pen_ops.js into a chunk. No server,
no project, no DOM: just the functions, asserted with numbers.

Skips cleanly without playwright or a chromium binary, like the rest of the
UI suite (the Pi is backend-only).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

sync_playwright = pytest.importorskip(
    "playwright.sync_api", reason="playwright not installed (backend-only machine)"
).sync_playwright

SRC = Path(__file__).resolve().parent.parent / "axibridge" / "static" / "js" / "pen_ops.js"

# Test-side geometry, independent of the module under test.
_HELPERS = r"""
window.H = {
  ctrl(sp, k) {
    const n = sp.anchors.length, a = sp.anchors[k], b = sp.anchors[(k + 1) % n];
    const p0 = [a.x, a.y], p3 = [b.x, b.y];
    const p1 = a.out_handle ? [a.x + a.out_handle[0], a.y + a.out_handle[1]] : p0;
    const p2 = b.in_handle ? [b.x + b.in_handle[0], b.y + b.in_handle[1]] : p3;
    return [p0, p1, p2, p3];
  },
  at(c, t) {
    const u = 1 - t, w = [u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t];
    return [0, 1].map(d => w[0] * c[0][d] + w[1] * c[1][d] + w[2] * c[2][d] + w[3] * c[3][d]);
  },
  nseg(sp) { const n = sp.anchors.length; return sp.closed ? n : n - 1; },
  sample(sp, per) {
    const out = [];
    for (let k = 0; k < H.nseg(sp); k++) {
      const c = H.ctrl(sp, k);
      for (let i = 0; i <= per; i++) out.push(H.at(c, i / per));
    }
    return out;
  },
  dist(p, q) { return Math.hypot(p[0] - q[0], p[1] - q[1]); },
  segDist(p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy;
    let t = L ? ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L : 0;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
  },
  devToPoly(pts, poly) {
    let worst = 0;
    for (const p of pts) {
      let best = Infinity;
      for (let i = 0; i + 1 < poly.length; i++) best = Math.min(best, H.segDist(p, poly[i], poly[i + 1]));
      worst = Math.max(worst, best);
    }
    return worst;
  },
  A(x, y, inH = null, outH = null, join = null) {
    return { x, y, in_handle: inH, out_handle: outH, join };
  },
  freeze(o) {
    if (o && typeof o === "object") { Object.values(o).forEach(H.freeze); Object.freeze(o); }
    return o;
  },
};
"""


@pytest.fixture
def run():
    """Function-scoped on purpose: a long-lived sync_playwright keeps an
    asyncio loop on the main thread and breaks later asyncio.run() calls."""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:  # no browser binary on this machine
            pytest.skip(f"no chromium: {str(e)[:120]}")
        try:
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            b64 = base64.b64encode(SRC.read_bytes()).decode("ascii")
            page.evaluate(
                "async (b64) => { window.M = await import('data:text/javascript;base64,' + b64); }",
                b64,
            )
            page.evaluate(_HELPERS)

            def _run(body: str):
                return page.evaluate(f"() => {{ const M = window.M, H = window.H; {body} }}")

            yield _run
            assert not errors, errors
        finally:
            browser.close()


# A known cubic used by several tests.
_CUBIC = "const sp = {anchors: [H.A(10, 20, null, [30, -15]), H.A(90, 40, [-20, -30], null)], closed: false, kind: 'bezier'};"


def test_classify_join_four_fixtures_and_explicit_wins(run):
    got = run("""
      return [
        M.classifyJoin(H.A(0, 0)),
        M.classifyJoin(H.A(0, 0, [-5, 2], [5, -2])),
        M.classifyJoin(H.A(0, 0, [-10, 4], [5, -2])),
        M.classifyJoin(H.A(0, 0, [-5, 0], [5, 3])),
        M.classifyJoin(H.A(0, 0, [-5, 2], [5, -2], 'corner')),
        M.classifyJoin(H.A(0, 0, null, null, 'smooth')),
      ];""")
    assert got == ["corner", "symmetric", "smooth", "corner", "corner", "smooth"]


def test_apply_arm_drag_mirrors_per_join(run):
    got = run("""
      const sym = M.applyArmDrag(H.A(0, 0, [-5, 0], [5, 0]), 'out', [3, 4], false);
      const smo = M.applyArmDrag(H.A(0, 0, [-2, 0], [5, 0]), 'out', [0, 5], false);
      const cor = M.applyArmDrag(H.A(0, 0, [-2, 1], [5, 0]), 'in', [0, 5], false);
      const brk = M.applyArmDrag(H.A(0, 0, [-5, 0], [5, 0]), 'out', [3, 4], true);
      return {sym, smo, cor, brk};""")
    assert got["sym"]["out_handle"] == [3, 4]
    assert got["sym"]["in_handle"] == [-3, -4]          # symmetric: exact opposite
    ix, iy = got["smo"]["in_handle"]
    assert abs(ix) < 1e-12 and abs(iy - (-2)) < 1e-12    # smooth: opposite angle, own length
    assert got["cor"]["in_handle"] == [0, 5] and got["cor"]["out_handle"] == [5, 0]
    assert got["brk"]["join"] == "corner" and got["brk"]["in_handle"] == [-5, 0]


def test_split_segment_leaves_the_shape_unchanged(run):
    got = run(_CUBIC + """
      const before = JSON.stringify(sp);
      const out = M.splitSegment(sp, 0, 0.3);
      const c = H.ctrl(sp, 0), l = H.ctrl(out, 0), r = H.ctrl(out, 1);
      let dev = 0;
      for (let i = 0; i <= 100; i++) {
        const u = i / 100;
        dev = Math.max(dev, H.dist(H.at(l, u), H.at(c, 0.3 * u)), H.dist(H.at(r, u), H.at(c, 0.3 + 0.7 * u)));
      }
      return {dev, n: out.anchors.length, join: out.anchors[1].join, untouched: JSON.stringify(sp) === before};""")
    assert got["dev"] < 1e-9
    assert got["n"] == 3 and got["join"] == "smooth" and got["untouched"]


def test_split_segment_on_the_closing_segment_appends(run):
    got = run("""
      const sp = {anchors: [H.A(0, 0), H.A(100, 0), H.A(100, 100)], closed: true, kind: 'bezier'};
      const out = M.splitSegment(sp, 2, 0.5);
      return out.anchors.map(a => [a.x, a.y]);""")
    assert got == [[0, 0], [100, 0], [100, 100], [50, 50]]


def test_nearest_on_subpath(run):
    got = run(_CUBIC + """
      const line = {anchors: [H.A(0, 0), H.A(100, 0)], closed: false, kind: 'bezier'};
      const q = H.at(H.ctrl(sp, 0), 0.42);
      const hit = M.nearestOnSubpath(line, 30, 5);
      // t is the CUBIC parameter (null arms make a non-uniform line), so check the point it names
      return [hit, H.at(H.ctrl(line, 0), hit.t), M.nearestOnSubpath(sp, q[0], q[1])];""")
    line, foot, cub = got
    assert line["segIndex"] == 0 and abs(line["dist"] - 5) < 1e-6
    assert foot == pytest.approx([30, 0], abs=1e-6)
    assert cub["segIndex"] == 0 and abs(cub["t"] - 0.42) < 1e-6 and cub["dist"] < 1e-6


def test_bend_segment_hits_the_target_and_remirrors_neighbours(run):
    got = run("""
      const sp = {anchors: [H.A(0, 0, null, [20, 0]), H.A(60, 0, [-10, -10], [10, 10]), H.A(120, 0, [-20, 0], null)],
                  closed: false, kind: 'bezier'};
      const before = JSON.stringify(sp);
      const c0 = H.at(H.ctrl(sp, 0), 0.5);
      const target = [c0[0] + 3, c0[1] + 10];
      const out = M.bendSegment(sp, 0, 0.5, target);
      const hit = H.dist(H.at(H.ctrl(out, 0), 0.5), target);
      return {hit, a: out.anchors, untouched: JSON.stringify(sp) === before};""")
    assert got["hit"] < 1e-9 and got["untouched"]
    a = got["a"]
    assert [(p["x"], p["y"]) for p in a] == [(0, 0), (60, 0), (120, 0)]   # anchors never move
    assert a[1]["in_handle"] != [-10, -10]
    # anchor 1 was symmetric: its out arm follows the bent in arm exactly
    assert a[1]["out_handle"] == [-a[1]["in_handle"][0], -a[1]["in_handle"][1]]
    assert a[2] == {"x": 120, "y": 0, "in_handle": [-20, 0], "out_handle": None, "join": None}


def test_curvature_handles_three_points(run):
    got = run("""
      const sp = {anchors: [H.A(0, 0), H.A(50, 30), H.A(100, 0)], closed: false, kind: 'curvature'};
      return M.curvatureHandles(sp).anchors;""")
    p0, p1, p2 = (0, 0), (50, 30), (100, 0)
    mid = got[1]
    ox, oy = mid["out_handle"]
    tx, ty = p2[0] - p0[0], p2[1] - p0[1]
    assert abs(ox * ty - oy * tx) < 1e-9 and ox * tx + oy * ty > 0     # tangent ∥ (p2 − p0)
    chord_out = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
    chord_in = ((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2) ** 0.5
    assert abs((ox * ox + oy * oy) ** 0.5 - chord_out / 3) < 1e-9
    ix, iy = mid["in_handle"]
    assert abs(ix * ty - iy * tx) < 1e-9 and ix * tx + iy * ty < 0
    assert abs((ix * ix + iy * iy) ** 0.5 - chord_in / 3) < 1e-9
    assert mid["join"] == "smooth"
    # open ends point a third of the way along their own chord
    assert got[0]["out_handle"] == pytest.approx([50 / 3, 10]) and got[0]["in_handle"] is None
    assert got[2]["in_handle"] == pytest.approx([-50 / 3, 10]) and got[2]["out_handle"] is None


def test_delete_anchor_two_anchor_subpath_leaves_one(run):
    got = run("""
      return M.deleteAnchor({anchors: [H.A(0, 0), H.A(10, 0)], closed: false, kind: 'bezier'}, 1).anchors.length;""")
    assert got == 1


def test_delete_anchor_open_end_drops_the_arm_toward_it(run):
    got = run("""
      const sp = {anchors: [H.A(0, 0, null, [5, 5]), H.A(50, 0, [-5, 5], [5, -5]), H.A(100, 0, [-5, -5], null)],
                  closed: false, kind: 'bezier'};
      return M.deleteAnchor(sp, 0).anchors;""")
    assert [(a["x"], a["y"]) for a in got] == [(50, 0), (100, 0)]
    assert got[0]["in_handle"] is None and got[0]["out_handle"] == [5, -5]


def test_delete_middle_anchor_of_a_circle_arc_refits_within_a_millimetre(run):
    got = run("""
      const cx = 100, cy = 100, r = 40, step = Math.PI / 3, k = 4 / 3 * Math.tan(step / 4) * r;
      const anchors = [-1, 0, 1].map(i => {
        const th = i * step, x = cx + r * Math.cos(th), y = cy + r * Math.sin(th);
        const tx = -Math.sin(th) * k, ty = Math.cos(th) * k;
        return H.A(x, y, i > -1 ? [-tx, -ty] : null, i < 1 ? [tx, ty] : null);
      });
      const sp = {anchors, closed: false, kind: 'bezier'};
      const out = M.deleteAnchor(sp, 1);
      const pts = H.sample(out, 200);
      const dev = Math.max(...pts.map(p => Math.abs(H.dist(p, [cx, cy]) - r)));
      // and it really is the arc it replaced (both ends, middle on the circle near angle 0)
      const mid = H.at(H.ctrl(out, 0), 0.5);
      return {n: out.anchors.length, dev, midDev: H.dist(mid, [cx + r, cy])};""")
    assert got["n"] == 2
    assert got["dev"] < 1.0
    assert got["midDev"] < 1.0


def test_delete_anchor_on_a_closed_subpath_wraps(run):
    got = run("""
      const sp = {anchors: [H.A(0, 0), H.A(100, 0), H.A(100, 100), H.A(0, 100)], closed: true, kind: 'bezier'};
      const out = M.deleteAnchor(sp, 0);
      return {pts: out.anchors.map(a => [a.x, a.y]), closed: out.closed};""")
    assert got == {"pts": [[100, 0], [100, 100], [0, 100]], "closed": True}


def test_snap_angle(run):
    got = run("return [M.snapAngle(10, 3), M.snapAngle(0, 0), M.snapAngle(-10, 1, 90)];")
    import math
    (x, y), zero, (x90, y90) = got
    assert abs(math.degrees(math.atan2(y, x)) - 15) < 1e-9
    assert abs(math.hypot(x, y) - math.sqrt(109)) < 1e-9
    assert zero == [0, 0]
    assert abs(x90 + math.sqrt(101)) < 1e-9 and abs(y90) < 1e-9


def test_knife_straight_two_anchor_subpath(run):
    got = run("""
      const sp = {anchors: [H.A(0, 0), H.A(100, 0)], closed: false, kind: 'bezier'};
      return M.knife(sp, [40, -10], [40, 10]);""")
    assert len(got) == 2
    a, b = got
    assert (a["anchors"][-1]["x"], a["anchors"][-1]["y"]) == pytest.approx((40, 0))
    assert (b["anchors"][0]["x"], b["anchors"][0]["y"]) == pytest.approx((40, 0))
    assert (a["anchors"][0]["x"], b["anchors"][-1]["x"]) == (0, 100)
    assert not a["closed"] and not b["closed"]


def test_knife_misses(run):
    got = run("""
      const sp = {anchors: [H.A(0, 0), H.A(100, 0)], closed: false, kind: 'bezier'};
      return M.knife(sp, [40, 5], [40, 10]);""")
    assert len(got) == 1 and len(got[0]["anchors"]) == 2


def test_knife_crosses_a_closed_square_twice(run):
    got = run("""
      const sp = {anchors: [H.A(0, 0), H.A(100, 0), H.A(100, 100), H.A(0, 100)], closed: true, kind: 'bezier'};
      const pieces = M.knife(sp, [-10, 50], [110, 50]);
      return pieces.map(p => ({closed: p.closed, kind: p.kind,
        pts: p.anchors.map(a => [Math.round(a.x * 1e6) / 1e6, Math.round(a.y * 1e6) / 1e6])}));""")
    assert len(got) == 2
    assert all(not p["closed"] and p["kind"] == "bezier" for p in got)
    ends = sorted(tuple(p["pts"][0]) for p in got) + sorted(tuple(p["pts"][-1]) for p in got)
    assert sorted(set(ends)) == [(0, 50), (100, 50)]
    for p in got:   # each piece is one side: three corners' worth of path
        assert len(p["pts"]) == 4


def test_knife_crossing_a_closed_curve_once_opens_it_there(run):
    got = run("""
      const sp = {anchors: [H.A(0, 0), H.A(100, 0), H.A(100, 100), H.A(0, 100)], closed: true, kind: 'bezier'};
      const pieces = M.knife(sp, [50, 50], [50, -20]);
      const p = pieces[0];
      return {n: pieces.length, closed: p.closed, first: [p.anchors[0].x, p.anchors[0].y],
              last: [p.anchors[p.anchors.length - 1].x, p.anchors[p.anchors.length - 1].y],
              count: p.anchors.length};""")
    assert got["n"] == 1 and not got["closed"]
    assert got["first"] == pytest.approx([50, 0]) and got["last"] == pytest.approx([50, 0])
    assert got["count"] == 6


def test_knife_keeps_curved_geometry(run):
    got = run(_CUBIC + """
      const closed = {anchors: [...sp.anchors.map(a => ({...a})), H.A(50, 90, [20, 0], [-20, 0])], closed: true, kind: 'bezier'};
      closed.anchors[0].in_handle = [0, 20]; closed.anchors[1].out_handle = [0, 20];
      const pieces = M.knife(closed, [0, 30], [120, 45]);
      const orig = H.sample(closed, 400);
      let dev = 0;
      for (const p of pieces) dev = Math.max(dev, H.devToPoly(H.sample(p, 50), orig));
      return {n: pieces.length, dev};""")
    assert got["n"] == 2
    assert got["dev"] < 0.05


def test_knife_crossings_are_where_knife_cuts(run):
    got = run(_CUBIC + """
      const line = {anchors: [H.A(0, 0), H.A(100, 0)], closed: false, kind: 'bezier'};
      const square = {anchors: [H.A(0, 0), H.A(100, 0), H.A(100, 100), H.A(0, 100)], closed: true, kind: 'bezier'};
      const curve = M.knifeCrossings(sp, [50, -50], [50, 100]);
      const cut = M.knife(sp, [50, -50], [50, 100]);
      return {line: M.knifeCrossings(line, [40, -10], [40, 10]),
              miss: M.knifeCrossings(line, [40, 5], [40, 10]),
              square: M.knifeCrossings(square, [-10, 50], [110, 50]),
              corner: M.knifeCrossings(square, [-10, -10], [10, 10]),
              curve, cutAt: [cut[0].anchors[cut[0].anchors.length - 1].x, cut[0].anchors[cut[0].anchors.length - 1].y]};""")
    assert got["line"] == [pytest.approx([40, 0])]
    assert got["miss"] == []
    assert sorted(map(tuple, got["square"])) == [pytest.approx((0, 50)), pytest.approx((100, 50))]
    assert got["corner"] == [pytest.approx([0, 0])]       # a cut through a point is one crossing
    assert len(got["curve"]) == 1 and got["curve"][0] == pytest.approx(got["cutAt"])


def test_join_ends(run):
    got = run("""
      const s1 = {anchors: [H.A(0, 0, null, [3, 0]), H.A(10, 0, [-2, 1], null)], closed: false, kind: 'bezier'};
      const s2 = {anchors: [H.A(12, 0, null, [1, 1]), H.A(20, 0)], closed: false, kind: 'bezier'};
      return [M.joinEnds(s1, 'end', s2, 'start'), M.joinEnds(s1, 'start', s2, 'start')];""")
    a, b = got
    assert [(p["x"], p["y"]) for p in a["anchors"]] == [(0, 0), (11, 0), (20, 0)]
    m = a["anchors"][1]
    assert m["join"] == "corner" and m["in_handle"] == [-2, 1] and m["out_handle"] == [1, 1]
    assert not a["closed"]
    # s1 reversed: its old start (out arm [3,0]) is now the meeting end, arm becomes in
    assert [(p["x"], p["y"]) for p in b["anchors"]] == [(10, 0), (6, 0), (20, 0)]
    assert b["anchors"][1]["in_handle"] == [3, 0] and b["anchors"][1]["out_handle"] == [1, 1]
    assert b["anchors"][0]["in_handle"] is None and b["anchors"][0]["out_handle"] == [-2, 1]


def test_every_op_is_pure(run):
    """Deep-frozen inputs: any in-place write throws (module code is strict)."""
    got = run(_CUBIC + """
      const sq = H.freeze({anchors: [H.A(0, 0), H.A(100, 0, [-5, 5], [5, -5]), H.A(100, 100), H.A(0, 100)], closed: true, kind: 'curvature'});
      H.freeze(sp);
      const other = H.freeze({anchors: [H.A(200, 0), H.A(210, 0)], closed: false, kind: 'bezier'});
      M.classifyJoin(sq.anchors[1]);
      M.applyArmDrag(sq.anchors[1], 'out', [1, 2], false);
      M.splitSegment(sq, 1, 0.4);
      M.nearestOnSubpath(sq, 3, 4);
      M.bendSegment(sq, 0, 0.5, [50, 10]);
      M.curvatureHandles(sq);
      M.deleteAnchor(sq, 1);
      M.knife(sq, [-10, 50], [110, 50]);
      M.joinEnds(sp, 'end', other, 'start');
      return true;""")
    assert got is True


# ---- fix round 1 (review): smooth never ends one-armed; refits never reshape untouched segments

def test_smooth_anchor_with_a_null_arm_grows_the_opposite_arm(run):
    got = run("""
      const smo = M.applyArmDrag(H.A(0, 0, null, null, 'smooth'), 'out', [20, 20], false);
      const end = M.applyArmDrag(H.A(0, 0, null, null, 'smooth'), 'out', [20, 20], false, {isEnd: true});
      const sym = M.applyArmDrag(H.A(0, 0, null, null, 'symmetric'), 'in', [3, 4], false, {isEnd: false});
      return {smo, end, sym};""")
    assert got["smo"]["in_handle"] == [-20, -20]
    assert got["end"]["in_handle"] is None           # an open end has no arm outward
    assert got["sym"]["out_handle"] == [-3, -4]


def test_split_a_line_then_bend_keeps_the_new_anchor_smooth(run):
    got = run("""
      const line = {anchors: [H.A(0, 0), H.A(100, 0, null, null, 'smooth')], closed: false, kind: 'bezier'};
      const split = M.splitSegment(line, 0, 0.5);
      const bent = M.bendSegment(split, 0, 0.5, [25, 10]);
      return {mid: bent.anchors[1], last: M.bendSegment(split, 1, 0.5, [75, 10]).anchors[2]};""")
    mid = got["mid"]
    assert mid["in_handle"] is not None and mid["out_handle"] is not None
    (ix, iy), (ox, oy) = mid["in_handle"], mid["out_handle"]
    assert abs(ix * oy - iy * ox) < 1e-9 and ix * ox + iy * oy < 0   # opposite: no kink
    # the open last anchor is explicit smooth but an end: no arm grows outward
    assert got["last"]["in_handle"] is not None and got["last"]["out_handle"] is None


def test_delete_anchor_never_reshapes_the_untouched_neighbour_segment(run):
    got = run("""
      const sp = {anchors: [H.A(0, 0, null, [10, 0]), H.A(50, 0, [-10, 0], [10, 0], 'symmetric'),
                            H.A(100, 20, [-10, -5], [10, 5]), H.A(150, 0, [-10, 0], null)],
                  closed: false, kind: 'bezier'};
      const out = M.deleteAnchor(sp, 2);
      return {before: H.ctrl(sp, 0), after: H.ctrl(out, 0), b: out.anchors[1]};""")
    assert got["after"] == got["before"]            # segment A-B is untouched
    b = got["b"]
    assert b["in_handle"] == [-10, 0] and b["join"] == "smooth"
    ox, oy = b["out_handle"]
    assert abs(oy) < 1e-12 and ox > 0               # the fitted arm kept its direction


def test_split_segment_downgrades_symmetric_neighbours_it_shortened(run):
    got = run("""
      const sp = {anchors: [H.A(0, 0, [-20, 0], [20, 0], 'symmetric'), H.A(100, 0, [-20, 0], [20, 0], 'symmetric')],
                  closed: false, kind: 'bezier'};
      const out = M.splitSegment(sp, 0, 0.3);
      const a = out.anchors[0];
      const dragged = M.applyArmDrag(a, 'out', a.out_handle, false);
      return {ja: a.join, jb: out.anchors[2].join, keptIn: dragged.in_handle};""")
    assert got["ja"] == "smooth" and got["jb"] == "smooth"
    assert got["keptIn"] == pytest.approx([-20, 0])  # the next drag no longer snaps it back
