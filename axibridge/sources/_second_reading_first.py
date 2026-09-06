"""Passages and their relationships, independent of replay and UI.

There is deliberately no composition score. An action honours the relation
it names; the surrounding drawing is allowed to disagree with it. Targets
are bounded whole passages, so attention costs do not grow with pen samples.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

from ..model import Path, Point

MAX_MACHINE_POINTS = 384


def turn_rng(seed: int, turn: int, branch: int) -> random.Random:
    digest = hashlib.blake2b(f"{seed}:{turn}:{branch}".encode(), digest_size=16).digest()
    return random.Random(int.from_bytes(digest, "big"))


def add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def mul(a: Point, k: float) -> Point:
    return a[0] * k, a[1] * k


def sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def unit(v: Point) -> Point:
    d = math.hypot(*v)
    return (v[0] / d, v[1] / d) if d > 1e-10 else (1.0, 0.0)


def normal(v: Point) -> Point:
    return -v[1], v[0]


def cubic(a: Point, b: Point, c: Point, d: Point, count: int = 64) -> list[Point]:
    return [tuple((1-t)**3*a[j] + 3*(1-t)**2*t*b[j] +
                  3*(1-t)*t*t*c[j] + t**3*d[j] for j in (0, 1))
            for t in (i/(count-1) for i in range(count))]


def resample(points: list[Point], count: int = 64) -> list[Point]:
    """Bound derived geometry without privileging pointer event density."""
    if len(points) <= count:
        return list(points)
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    total = sum(lengths)
    if total <= 1e-10:
        return [points[0], points[-1]]
    out = [points[0]]
    index, walked = 0, 0.0
    for i in range(1, count - 1):
        distance = total * i / (count - 1)
        while index < len(lengths) - 1 and walked + lengths[index] < distance:
            walked += lengths[index]
            index += 1
        t = (distance - walked) / max(lengths[index], 1e-10)
        out.append(add(points[index], mul(sub(points[index + 1], points[index]), t)))
    return out + [points[-1]]


def _segment_clip(a: Point, b: Point, width: float, height: float):
    dx, dy = sub(b, a)
    lo, hi = 0.0, 1.0
    for p, q in ((-dx, a[0]), (dx, width-a[0]), (-dy, a[1]), (dy, height-a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return None
        elif p < 0:
            lo = max(lo, q/p)
        else:
            hi = min(hi, q/p)
        if lo > hi:
            return None
    # Rounding drift at a true intersection may exceed a physical bound by
    # an ulp. Only intersection coordinates are guarded, never a travelling pen.
    def at(t):
        x, y = add(a, mul((dx, dy), t))
        return max(0.0, min(width, x)), max(0.0, min(height, y))
    return at(lo), at(hi)


def clip_paths(paths: list[Path], width: float, height: float) -> list[Path]:
    out = []
    for path in paths:
        current = []
        for a, b in zip(path.points, path.points[1:]):
            segment = _segment_clip(a, b, width, height)
            if segment is None:
                if len(current) > 1:
                    out.append(Path(points=current))
                current = []
                continue
            start, end = segment
            if current and math.dist(current[-1], start) > 1e-8:
                if len(current) > 1:
                    out.append(Path(points=current))
                current = []
            if not current:
                current = [start]
            if math.dist(current[-1], end) > 1e-9:
                current.append(end)
        if len(current) > 1:
            out.append(Path(points=current))
    return out


@dataclass(frozen=True)
class Passage:
    id: int
    paths: list[Path]
    construction: str
    action: str
    targets: tuple[int, ...]
    ancestry: tuple[int, ...]
    bbox: tuple[float, float, float, float]
    centre: Point
    direction: Point
    length: float
    endpoints: tuple[Point, ...]


def describe(passage_id: int, paths: list[Path], construction: str,
             action: str, targets: tuple[int, ...] = (),
             ancestry: tuple[int, ...] = ()) -> Passage:
    points = [p for path in paths for p in path.points]
    xs, ys = zip(*points)
    bbox = min(xs), min(ys), max(xs), max(ys)
    spine = max(paths, key=lambda p: p.length())
    direction = sub(spine.points[-1], spine.points[0])
    if math.hypot(*direction) < 1e-8:
        a, b = max(zip(spine.points, spine.points[1:]), key=lambda ab: math.dist(*ab))
        direction = sub(b, a)
    return Passage(passage_id, paths, construction, action, targets, ancestry,
                   bbox, ((bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2),
                   unit(direction), sum(path.length() for path in paths),
                   tuple(p for path in paths for p in (path.points[0], path.points[-1])))


def opening(width: float, height: float, rng: random.Random) -> list[Passage]:
    out = []
    for i, scale in enumerate((0.38, 0.17)):
        centre = (width*rng.uniform(.28, .72), height*rng.uniform(.3, .7))
        angle = rng.uniform(-math.pi, math.pi)
        along = (math.cos(angle), math.sin(angle))
        across = normal(along)
        length = min(width, height)*scale
        a, d = add(centre, mul(along, -length/2)), add(centre, mul(along, length/2))
        b = add(add(a, mul(along, length*.3)), mul(across, length*.4))
        c = add(add(a, mul(along, length*.7)), mul(across, -length*.23))
        construction = "angular" if (rng.random() < .5) else "cubic"
        points = [a, b, c, d] if construction == "angular" else cubic(a, b, c, d)
        paths = clip_paths([Path(points=points)], width, height)
        out.append(describe(i, paths, construction, "opening"))
    return out


def echo(target: Passage, offset: Point, scale: float = 1.0) -> list[Path]:
    """One affine for the entire passage, preserving its internal intervals."""
    return [Path(points=[add(add(target.centre, mul(sub(p, target.centre), scale)), offset)
                         for p in resample(path.points)]) for path in target.paths[:6]]


def extend(target: Passage, distance: float, bend: float) -> list[Path]:
    path = max(target.paths, key=lambda p: p.length())
    a = path.points[-1]
    tangent = unit(sub(a, path.points[-2]))
    across = normal(tangent)
    b = add(a, mul(tangent, distance*.32))
    c = add(add(a, mul(tangent, distance*.62)), mul(across, distance*bend))
    d = add(add(a, mul(tangent, distance)), mul(across, distance*bend*.55))
    return [Path(points=([a, b, c, d] if target.construction == "angular" else cubic(a, b, c, d)))]


def traverse(first: Passage, second: Passage, bend: float) -> list[Path]:
    # Endpoints establish the relationship; intervening passages are not
    # obstacles. That indifference is part of this particular action.
    pairs = [(a, b) for a in first.endpoints for b in second.endpoints]
    # Joined passages may share an endpoint. Traversing that zero interval
    # produces no stroke, and near-zero intervals only make a microscopic knot.
    separated = [ab for ab in pairs if math.dist(*ab) >= 4.0]
    a, d = min(separated or pairs, key=lambda ab: math.dist(*ab))
    delta = sub(d, a)
    across = normal(delta)
    b = add(add(a, mul(delta, .27)), mul(across, bend))
    c = add(add(a, mul(delta, .72)), mul(across, -bend*.5))
    return [Path(points=([a, b, c, d] if first.construction == "angular" else cubic(a, b, c, d)))]


def concentrate(target: Passage, position: float, width: float, spacing: float,
                side: int = 1) -> list[Path]:
    spine = max(target.paths, key=lambda p: p.length())
    # Dense uniform sampling is local to a bounded derived curve, not a scan
    # through all ink. Use arc length so long straight segments can be worked.
    pts = spine.points
    lengths = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    total = sum(lengths)
    def at(f):
        remaining = min(1.0, max(0.0, f))*total
        for j, length in enumerate(lengths):
            if remaining <= length and length > 0:
                return add(pts[j], mul(sub(pts[j+1], pts[j]), remaining/length))
            remaining -= length
        return pts[-1]
    start = max(0.0, min(1.0-width, position-width/2))
    interval = [at(start+width*i/47) for i in range(48)]
    out = []
    for k in range(1, 5):
        shifted = []
        for i, p in enumerate(interval):
            tangent = unit(sub(interval[min(i+1, 47)], interval[max(0, i-1)]))
            shifted.append(add(p, mul(normal(tangent), side*spacing*k)))
        out.append(Path(points=shifted))
    return out


@dataclass
class Commitment:
    action: str
    target_ids: tuple[int, ...]
    remaining: int
    side: int
    iteration: int = 0


def choose(memory: list[Passage], recurrence: float, persistence: float,
           rng: random.Random) -> Commitment:
    # No traversal of points here. Even a 20k-point human stroke counts as
    # one candidate. Sampling keeps the policy bounded if turn limits grow.
    pool = memory[-12:]
    if len(memory) > 12:
        pool = memory[-4:] + rng.sample(memory[:-4], 8)
    target = rng.choice(pool[:-1] or pool) if rng.random() < recurrence else memory[-1]
    action = rng.choice(("extend", "echo", "traverse", "concentrate"))
    if action == "concentrate":
        # Repeatedly taking an interval OF an interval shrinks the activity
        # below pen scale. Return to its material ancestor while allowing ink
        # to accumulate there: a held decision, not an exponential contraction.
        by_id = {p.id: p for p in memory}
        while target.action == "concentrate" and target.targets:
            target = by_id[target.targets[0]]
    targets = (target.id,)
    if action == "traverse":
        candidates = [p for p in pool if p.id != target.id]
        if candidates:
            other = max(candidates, key=lambda p: math.dist(p.centre, target.centre))
            targets += (other.id,)
        else:
            action = "extend"
    return Commitment(action, targets, 2+int(persistence*3+.5), rng.choice((-1, 1)))


def make_action(commitment: Commitment, memory: list[Passage], reach: float,
                width: float, height: float, rng: random.Random, boundary=None) -> tuple[list[Path], str]:
    by_id = {p.id: p for p in memory}
    target = by_id[commitment.target_ids[0]]
    scale = min(width, height)
    n = normal(target.direction)
    iteration = commitment.iteration + 1
    if commitment.action == "echo":
        offset = mul(n, commitment.side*(2+reach*9)*iteration)
        paths = echo(target, offset, 1 + commitment.side*reach*.09*iteration)
    elif commitment.action == "extend":
        paths = extend(target, scale*(.08+.28*reach), commitment.side*rng.uniform(.25, .95))
    elif commitment.action == "traverse":
        other = by_id[commitment.target_ids[1]]
        paths = traverse(target, other, commitment.side*(.08+.3*reach)*iteration)
    else:
        paths = concentrate(target, .25+.5*rng.random(), .25+.45*reach,
                            .24+.45*reach, commitment.side)
    clipped = boundary(paths) if boundary else clip_paths(paths, width, height)
    # Clipping can split one passage into many fragments; bounded output is
    # part of the machine action vocabulary, never a truncation of human ink.
    bounded = [Path(points=resample(p.points, 64)) for p in clipped[:6]]
    return bounded, target.construction
