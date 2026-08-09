"""Arc-native polyline offsetting — the one idea from cavalier-contours worth porting.

A **bulge polyline**: vertices carrying ``(x, y, bulge)`` where the bulge is
``tan(θ/4)`` for the arc swept from that vertex to the next (0 = a straight
segment, 1 = a semicircle, sign = turn direction). It is the representation
`cavalier_contours <https://github.com/jbuckmccready/cavalier_contours>`_ is
built on, and the reason it is worth the trouble here is narrow and specific:

**an arc offsets exactly.** A circle of radius `r` about `c` offset by `d` is a
circle of radius `r ∓ d` about the same `c` — no approximation, no vertices.
Shapely's ``buffer`` cannot say that, because GEOS has no arc: it tessellates
every curve on the way in and again on the way out, so the fill's fidelity is
capped by whatever segment count was used and the vertex count climbs with it.
Here the geometry stays exact all the way through and is flattened once, at the
end, to whatever tolerance the caller actually wants.

**What this module is NOT.** It is not a replacement for the compositor's
geometry engine and it does not touch the IPR — ``Path.points`` is still a
plain point list, arcs are fitted on the way in and flattened on the way out,
and nothing outside this file ever sees a bulge. That containment is
deliberate: whether the IPR should carry arcs is an open architecture question
(ROADMAP, "Far / undecided"), and this is evidence for it, not a decision on it.

**Why it is not the default.** Step 3 below — pruning the invalid parts of a
raw offset — is where every offsetting library's bug reports live, and a wrong
answer here is not a crash but permanent wrong ink. ``offset_fill_v2`` keeps
``engine="shapely"`` until the differential test in ``tests/test_arcpoly.py``
has been given a lot more shapes than it has today.

The pipeline, and where each piece leans on what we already have:

1. **fit** a polyline to arcs (`fit_contour`) — greedy, tolerance-bounded.
2. **raw offset** every segment and join the ends (`_raw_offset`). Exact.
3. **prune** the self-intersecting parts and stitch what survives
   (`offset_contour`). Cavalier carries its own spatial index for the distance
   test; we hand that to shapely, which is already a dependency and already
   indexed — the port is the algorithm, not the infrastructure.
4. **flatten** to points at a chord tolerance (`flatten`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, Point
from shapely.prepared import prep

Pt = tuple[float, float]

#: below this a bulge is a straight segment. tan(θ/4) < 1e-9 is θ < 4e-9 rad,
#: which over a bed-sized 300 mm span is a sagitta far under a micron.
_STRAIGHT = 1e-9

#: a fitted arc is rejected if its radius exceeds this multiple of the chord —
#: past it the arc IS the chord to well within any tolerance, and the centre
#: runs off to infinity where the arithmetic stops meaning anything.
_MAX_RADIUS_RATIO = 1e4

#: mitre ratio cap, the same number and the same reason as `offset_fill`'s: a
#: sharp corner mitres to an arbitrarily long spike as its angle closes, and
#: past this ratio a round join is the safer answer.
_MITRE_LIMIT = 3.0

#: widest sweep a FITTED arc may span. Nothing about the representation needs
#: this — a bulge describes any sweep up to a full turn — but two things about
#: the rest of the pipeline do. A greedy fit left uncapped eats a circle in one
#: 356° bite and leaves a one-vertex crumb behind it, and offsetting that seam
#: tangles into several near-duplicate faces instead of one ring. And a capped
#: arc is never reflex, which keeps `arc_of`'s centre-side branch off the hot
#: path entirely. 120° fits a circle as three clean thirds.
_MAX_SWEEP = 2.0 * math.pi / 3.0


@dataclass(frozen=True)
class Vertex:
    """A point, plus the bulge of the segment leaving it toward the next."""

    x: float
    y: float
    bulge: float = 0.0

    @property
    def pt(self) -> Pt:
        return (self.x, self.y)


@dataclass
class Contour:
    """A bulge polyline. `closed` means the last vertex's segment wraps to the first."""

    vertices: list[Vertex]
    closed: bool = True

    def __len__(self) -> int:
        return len(self.vertices)

    def segments(self):
        """Consecutive (start, end) vertex pairs, wrapping when closed."""
        n = len(self.vertices)
        last = n if self.closed else n - 1
        for i in range(last):
            yield self.vertices[i], self.vertices[(i + 1) % n]


# -- arcs ----------------------------------------------------------------------

def arc_of(v0: Vertex, v1: Vertex):
    """The circle a bulge segment rides, as (centre, radius, a0, a1, ccw).

    Standard bulge geometry: with ``b = tan(θ/4)`` the swept angle is
    ``θ = 4·atan(b)``, the chord subtends it, and the radius follows from the
    half-chord over ``sin(θ/2)``. Returns None for a straight segment.
    """
    if abs(v0.bulge) < _STRAIGHT:
        return None
    theta = 4.0 * math.atan(v0.bulge)
    dx, dy = v1.x - v0.x, v1.y - v0.y
    chord = math.hypot(dx, dy)
    if chord < _STRAIGHT:
        return None
    radius = chord / (2.0 * math.sin(abs(theta) / 2.0))
    # the centre sits off the chord midpoint along the perpendicular, on the
    # side the sign of the bulge chooses
    mid = ((v0.x + v1.x) / 2.0, (v0.y + v1.y) / 2.0)
    h = math.sqrt(max(radius * radius - (chord / 2.0) ** 2, 0.0))
    ux, uy = -dy / chord, dx / chord   # the chord's left normal
    # A minor CCW arc curves away from its centre on the left; a REFLEX one
    # (|θ| > π) wraps the other way and puts the centre on the right. Getting
    # this backwards is silent — the arc still passes through both endpoints,
    # just on a circle centred somewhere else entirely — and it only shows up
    # once something offsets it.
    sign = 1.0 if theta > 0 else -1.0
    if abs(theta) > math.pi:
        sign = -sign
    cx, cy = mid[0] + sign * h * ux, mid[1] + sign * h * uy
    a0 = math.atan2(v0.y - cy, v0.x - cx)
    a1 = math.atan2(v1.y - cy, v1.x - cx)
    return (cx, cy), radius, a0, a1, theta > 0


def _sweep(a0: float, a1: float, ccw: bool) -> float:
    """Signed angular travel from a0 to a1 in the given direction."""
    d = (a1 - a0) % (2.0 * math.pi) if ccw else -((a0 - a1) % (2.0 * math.pi))
    return d


def flatten_segment(v0: Vertex, v1: Vertex, tol: float) -> list[Pt]:
    """A segment's points, excluding its end vertex, at a chord tolerance.

    The segment count comes from the same sagitta relation `offset_fill_v2`
    uses for buffers — ``r(1−cos(a/2)) ≤ tol`` — so "tolerance" means one thing
    across the whole effect whichever engine produced the geometry.
    """
    arc = arc_of(v0, v1)
    if arc is None:
        return [v0.pt]
    (cx, cy), r, a0, a1, ccw = arc
    total = abs(_sweep(a0, a1, ccw))
    if r <= tol:
        return [v0.pt]
    step = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - tol / r)))
    n = max(1, math.ceil(total / step))
    out = []
    for i in range(n):
        a = a0 + (_sweep(a0, a1, ccw)) * (i / n)
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def flatten(contour: Contour, tol: float) -> list[Pt]:
    """The whole contour as points. Closed contours repeat their first point."""
    pts: list[Pt] = []
    for v0, v1 in contour.segments():
        pts.extend(flatten_segment(v0, v1, tol))
    if contour.closed:
        if pts:
            pts.append(pts[0])
    else:
        pts.append(contour.vertices[-1].pt)
    return pts


# -- fitting -------------------------------------------------------------------

def _circle_through(p0: Pt, p1: Pt, p2: Pt):
    """Centre and radius of the circle through three points, or None if collinear."""
    ax, ay = p0
    bx, by = p1
    cx, cy = p2
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


def _bulge_for(p0: Pt, p1: Pt, centre: Pt, radius: float, through: Pt) -> float:
    """The bulge taking p0 to p1 along the circle, on the side `through` is on."""
    a0 = math.atan2(p0[1] - centre[1], p0[0] - centre[0])
    a1 = math.atan2(p1[1] - centre[1], p1[0] - centre[0])
    am = math.atan2(through[1] - centre[1], through[0] - centre[0])
    ccw = ((am - a0) % (2.0 * math.pi)) < ((a1 - a0) % (2.0 * math.pi))
    theta = _sweep(a0, a1, ccw)
    return math.tan(theta / 4.0)


def fit_contour(points: list[Pt], tol: float, closed: bool = True) -> Contour:
    """Fit arcs to a flattened polyline, greedily, within `tol`.

    This is what recovers a circle from the 96-gon an importer or a generator
    handed us. The run grows while the circle through (first, middle, last)
    stays within tolerance of the polyline — a plain deviation test rather than
    a least-squares fit, because the bound we owe the caller is a maximum and
    not an average. Runs that will not fit an arc stay straight.

    **The test samples segment MIDPOINTS, not just the vertices**, and skipping
    that is the trap: a square's four corners are concyclic, so a vertex-only
    test finds them a perfect circle and quietly turns the square into one. It
    is also what keeps a coarse polygon honest — an arc through the vertices of
    a 24-gon misses its edges by a third of a millimetre, which is deviation
    the caller asked us to bound and a vertex test cannot see.
    """
    pts = list(points)
    if closed and len(pts) > 1 and math.dist(pts[0], pts[-1]) < _STRAIGHT:
        pts.pop()
    n = len(pts)
    if n < 3:
        return Contour([Vertex(x, y) for x, y in pts], closed)

    out: list[Vertex] = []
    i = 0
    limit = n if closed else n - 1
    while i < limit:
        best_j, best_bulge = i + 1, 0.0
        j = i + 2
        # a run may never wrap past the contour's own origin. Letting it try
        # gives a closed shape TWO arcs that each span almost all of it, which
        # describes the same curve twice and offsets into nonsense. The cost is
        # a forced vertex at index 0 — a circle fits as one long arc plus a
        # short closing chord instead of two clean halves, still inside `tol`.
        while j <= (n if closed else n - 1):
            p0, p1 = pts[i % n], pts[j % n]
            mid = pts[((i + j) // 2) % n]
            fit = _circle_through(p0, mid, p1)
            if fit is None:
                break
            centre, radius = fit
            if radius > _MAX_RADIUS_RATIO * max(math.dist(p0, p1), _STRAIGHT):
                break
            probes = []
            for k in range(i, j):
                a, b = pts[k % n], pts[(k + 1) % n]
                if k > i:
                    probes.append(a)
                probes.append(((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0))
            if any(abs(math.hypot(p[0] - centre[0], p[1] - centre[1]) - radius) > tol
                   for p in probes):
                break
            bulge = _bulge_for(p0, p1, centre, radius, mid)
            if abs(4.0 * math.atan(bulge)) > _MAX_SWEEP:
                break
            best_j = j
            best_bulge = bulge
            j += 1
        out.append(Vertex(pts[i % n][0], pts[i % n][1], best_bulge))
        i = best_j
    if not closed:
        out.append(Vertex(pts[-1][0], pts[-1][1]))
    return Contour(out, closed)


# -- offsetting ----------------------------------------------------------------

def _offset_segment(v0: Vertex, v1: Vertex, d: float):
    """One segment moved `d` to the LEFT of its direction of travel. Exact.

    Left of travel, not "inward": a contour has no inside until you know its
    winding. For the CCW exteriors this module is handed, left IS inward, so a
    positive `d` erodes — the opposite of shapely's ``buffer`` sign, and worth
    keeping in mind at the call site.

    A line slides along its normal and keeps its direction. An arc keeps its
    CENTRE and changes radius — that is the whole reason for the bulge
    representation, and it is why offsetting here accumulates no error however
    many times it is repeated. An arc whose radius would go through zero has
    collapsed and is dropped; the pruning pass closes the gap it leaves.
    """
    arc = arc_of(v0, v1)
    if arc is None:
        dx, dy = v1.x - v0.x, v1.y - v0.y
        ln = math.hypot(dx, dy)
        if ln < _STRAIGHT:
            return None
        nx, ny = -dy / ln * d, dx / ln * d
        return Vertex(v0.x + nx, v0.y + ny, 0.0), Vertex(v1.x + nx, v1.y + ny, 0.0)
    (cx, cy), r, a0, a1, ccw = arc
    # a CCW arc keeps its centre on the left, so going left is going toward it
    r2 = r - d if ccw else r + d
    if r2 <= _STRAIGHT:
        return None
    return (Vertex(cx + r2 * math.cos(a0), cy + r2 * math.sin(a0), v0.bulge),
            Vertex(cx + r2 * math.cos(a1), cy + r2 * math.sin(a1), 0.0))


def _raw_offset(contour: Contour, d: float) -> Contour:
    """Every segment offset, ends joined by a round arc where they separate.

    Where consecutive offset segments pull apart (a convex corner going out, a
    reflex one coming in) the gap is bridged by an arc of radius ``|d|`` about
    the ORIGINAL vertex — which is the corner of the true offset curve, not an
    approximation of it. Where they overlap instead, the overlap is left in
    place: sorting out which parts of it are real is the pruning pass's job,
    and doing it here would need the very intersection tests that pass runs.
    """
    pieces = [(off, v1) for off, v1 in
              ((_offset_segment(v0, v1, d), v1) for v0, v1 in contour.segments())
              if off is not None]
    if not pieces:
        return Contour([], contour.closed)
    n = len(pieces)
    starts = [piece[0] for piece, _ in pieces]
    ends = [piece[1] for piece, _ in pieces]
    bridges: list[float | None] = [None] * n

    # resolve every join first, because a mitre TRIMS BOTH SIDES: the crossing
    # point is past the end of one segment and before the start of the next, so
    # deciding it while walking forward and emitting as you go lays down the
    # old end, then the crossing, then the un-trimmed next start — a backwards
    # spike at every corner, which self-intersects and takes the whole ring out
    # in the pruning pass.
    for k in range(n if contour.closed else n - 1):
        j = (k + 1) % n
        if math.dist(ends[k].pt, starts[j].pt) <= _STRAIGHT:
            continue
        hit = _mitre(starts[k], ends[k], starts[j], ends[j], pieces[k][1].pt, abs(d))
        if hit is not None:
            ends[k] = Vertex(hit[0], hit[1], 0.0)
            starts[j] = Vertex(hit[0], hit[1], starts[j].bulge)
        else:
            bridges[k] = _bridge_bulge(pieces[k][1].pt, ends[k].pt, starts[j].pt)

    out: list[Vertex] = []
    for k in range(n):
        out.append(starts[k])
        last = not contour.closed and k == n - 1
        if last or math.dist(ends[k].pt, starts[(k + 1) % n].pt) > _STRAIGHT:
            out.append(Vertex(ends[k].x, ends[k].y, bridges[k] or 0.0))
    return Contour(out, contour.closed)


def _mitre(a: Vertex, b: Vertex, c: Vertex, e: Vertex, corner: Pt, r: float):
    """Where two STRAIGHT offset segments would meet if extended, or None.

    A gap between consecutive offset segments has two honest answers, and the
    shapely engine's `join_style` is the name of that choice: round it with an
    arc about the original vertex, or run both segments out to their crossing
    and keep the corner sharp. `offset_fill` defaults to mitre and this engine
    has to agree, or the two disagree about area, components die at different
    depths, and the differential test lights up for a reason that is not a bug.

    Only line-to-line, on purpose. Extending an ARC to meet its neighbour means
    the general conic-intersection code this module is trying not to need — and
    consecutive fitted arcs are tangent, so they leave no gap to join in the
    first place. Beyond `_MITRE_LIMIT` the spike is longer than it is worth and
    the round bridge takes over, exactly as shapely does.
    """
    if abs(a.bulge) > _STRAIGHT or abs(c.bulge) > _STRAIGHT:
        return None
    d1 = (b.x - a.x, b.y - a.y)
    d2 = (e.x - c.x, e.y - c.y)
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-12:
        return None                       # parallel: nothing to meet
    t = ((c.x - a.x) * d2[1] - (c.y - a.y) * d2[0]) / den
    hit = (a.x + d1[0] * t, a.y + d1[1] * t)
    if r > 0 and math.dist(hit, corner) > _MITRE_LIMIT * r:
        return None                       # a near-cusp: bevel it instead
    return hit


def _bridge_bulge(corner: Pt, p0: Pt, p1: Pt) -> float:
    """Bulge of the arc bridging a corner gap, swept ABOUT the corner itself.

    Both gap ends sit exactly ``|d|`` from the original vertex — that vertex is
    the bridge arc's centre, by construction — so the sweep is just the angle
    between them, taken the short way round. Deriving the bulge from the chord
    instead (asin of half-chord over radius) loses the sign, and a bridge that
    turns the wrong way folds the offset back over itself and takes the whole
    loop out with it in the pruning pass. That cost an afternoon.
    """
    a0 = math.atan2(p0[1] - corner[1], p0[0] - corner[0])
    a1 = math.atan2(p1[1] - corner[1], p1[0] - corner[0])
    sweep = (a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi
    return math.tan(sweep / 4.0)


def offset_contour(contour: Contour, d: float, tol: float,
                   dist_eps: float = 1e-4, join_eps: float = 1e-4) -> list[Contour]:
    """Offset a closed contour by `d`, dropping the parts that are not real.

    A raw offset self-intersects wherever the source curves tighter than the
    offset distance: the segments there fold back over each other and enclose
    loops that are not part of the true offset. The test that finds them is
    local and simple — **a point of the true offset is exactly ``|d|`` from the
    source, never nearer** — so slicing the raw curve at its self-intersections
    and throwing away every slice that comes in closer leaves precisely the
    real thing. That is cavalier's algorithm; the distance query is shapely's.

    Returns however many loops survive, which is how this reports topology: a
    component that split hands back two, one that died hands back none. The
    caller does not have to detect either.
    """
    raw = _raw_offset(contour, d)
    if len(raw) < 2:
        return []
    pts = flatten(raw, tol)
    if len(pts) < 4:
        return []
    line = LineString(pts)
    source = LineString(flatten(contour, tol))
    # The "exactly |d| from the source" test is run against FLATTENED geometry
    # on both sides, and a chord sits up to `tol` inside the curve it replaces —
    # so a perfectly valid offset measures as little as |d| − tol away. Slack
    # under that and the test throws away the entire real offset and keeps the
    # slivers, which is the failure it is supposed to prevent. Invalid parts
    # fold back to nearly zero distance, so `tol` costs nothing to give away.
    keep = abs(d) - tol - dist_eps

    # slice at self-intersections: unary_union nodes the line for us, and each
    # noded piece is either wholly valid or wholly invalid because a crossing is
    # the only place validity can change
    from shapely.geometry.polygon import orient
    from shapely.ops import polygonize, unary_union

    # `polygonize`, not `linemerge`: the raw offset is a set of NODED EDGES and
    # what we want from it is faces. linemerge chains edges end to end, which on
    # a self-touching offset hands the same ring back twice and drops nothing;
    # polygonize already knows an edge set can enclose several regions, and it
    # discards dangling shreds for free.
    faces = list(polygonize(unary_union(line)))
    if not faces:
        return []

    # The validity test runs on whole FACES, not on individual edges. Testing an
    # edge's midpoint passes anything whose middle happens to clear the source,
    # and near a total collapse — a star eroded past its inradius — that leaves
    # a scatter of millimetre slivers where the honest answer is nothing at all.
    # A face is real only if ALL of it stands off the source, which is one
    # distance call and strictly stronger.
    # A symmetric "and no further than |d| either" test looks tempting here and
    # is wrong: a mitre spike at a sharp reflex corner sits legitimately further
    # from the source than |d|, because the perpendicular foot falls off the end
    # of the segment it was measured against. The remaining near-collapse
    # slivers this lets through are caught by the monotonicity clip in
    # `offset_fill_v2._forest`, where the previous level is actually in hand.
    want_ccw = _signed_area(pts) > 0.0
    out = []
    for face in faces:
        if face.area <= tol * tol:
            continue                       # noding debris, not a region
        if source.distance(face.exterior) < keep:
            continue
        # hand back the winding we were given, so a caller may offset the result
        # again and have `d` still mean what it meant the first time
        cs = [(x, y) for x, y in orient(face, 1.0 if want_ccw else -1.0).exterior.coords]
        if len(cs) >= 4:
            out.append(fit_contour(cs, tol, closed=True))
    return out


def _signed_area(pts: list[Pt]) -> float:
    return sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
               for i in range(len(pts) - 1)) / 2.0
