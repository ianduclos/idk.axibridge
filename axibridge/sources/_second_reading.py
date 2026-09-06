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
    openness: float
    span: float


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
                   tuple(p for path in paths for p in (path.points[0], path.points[-1])),
                   math.dist(spine.points[0], spine.points[-1])/max(.1, spine.length()),
                   math.hypot(bbox[2]-bbox[0], bbox[3]-bbox[1]))


def opening(width: float, height: float, rng: random.Random) -> list[Passage]:
    from ._second_reading_gestures import opening_gesture, articulated, sampled
    out = []
    for i, scale in enumerate((0.44, 0.23)):
        centre = (width*rng.uniform(.28, .72), height*rng.uniform(.3, .7))
        angle = rng.uniform(-math.pi, math.pi)
        length = min(width, height)*scale
        paths = opening_gesture(centre, angle, length, rng, allow_break=False)
        construction = "organic" if i == 0 else "articulated"
        if construction == "articulated":
            paths = articulated(sampled(paths[0].points, 6), (2,))
        paths = clip_paths(paths, width, height)[:1]
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
    separated = [ab for ab in pairs if math.dist(*ab) >= 0.5]
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
    context_ids: tuple[int, ...] = ()
    response: str | None = None


def action_for(target: Passage, memory: list[Passage], rng: random.Random,
               previous: str | None = None) -> str:
    # Compare the chord to the actual travelled curve. A returning contour
    # offers a different opportunity from a long crossing of the same bbox.
    openness, span = target.openness, target.span
    actions = ("extend", "echo", "traverse", "surround", "concentrate")
    weights = [1+openness*2, 1.5, 1.5, 1+(1-openness)*2, .5 if span > 25 else .1]
    recent = memory[-6:]
    for i, action in enumerate(actions):
        if action == previous:
            weights[i] *= .06
        # Short-term habituation is selective: it concerns this relation,
        # not a global demand that every drawing become balanced or novel.
        replies = sum(p.action == action and target.id in p.targets for p in recent)
        weights[i] /= 1+replies*3
    return rng.choices(actions, weights=weights)[0]


def assign_pair(commitment: Commitment, memory: list[Passage]) -> None:
    target = next(p for p in memory if p.id == commitment.target_ids[0])
    commitment.target_ids = (target.id,)
    if commitment.action == "traverse":
        candidates = [p for p in memory[-12:] if p.id != target.id]
        if candidates:
            other = max(candidates, key=lambda p: math.dist(p.centre, target.centre))
            commitment.target_ids += (other.id,)
        else:
            commitment.action = "extend"


def choose(memory: list[Passage], recurrence: float, persistence: float,
           rng: random.Random) -> Commitment:
    pool = memory[-12:]
    if len(memory) > 12:
        pool = memory[-4:] + rng.sample(memory[:-4], 8)
    target = memory[-1]
    if rng.random() < recurrence:
        older = [p for p in pool if p.id != memory[-1].id] or pool
        # Older material remains eligible; repeatedly answered passages lose
        # urgency. A human mark has no unconditional right to a reply.
        weights = [1/(1+sum(p.id in q.targets for q in memory[-8:])) for p in older]
        target = rng.choices(older, weights=weights)[0]
    commitment = Commitment(action_for(target, memory, rng), (target.id,),
                            2+int(persistence*3+.5), rng.choice((-1, 1)))
    assign_pair(commitment, memory)
    return commitment


def reconsider(commitment: Commitment, memory: list[Passage], rng: random.Random) -> None:
    target = next(p for p in memory if p.id == commitment.target_ids[0])
    commitment.action = action_for(target, memory, rng, commitment.action)
    assign_pair(commitment, memory)


def make_action(commitment: Commitment, memory: list[Passage], reach: float,
                width: float, height: float, rng: random.Random,
                consider_context: bool = True, boundary=None) -> tuple[list[Path], str]:
    from ._second_reading_encounters import encounters, yield_at
    from ._second_reading_responses import transfer, depart, surround, bridge, insist
    by_id = {p.id: p for p in memory}
    target = by_id[commitment.target_ids[0]]
    action = commitment.action
    commitment.context_ids, commitment.response = (), None
    # Context decisions use a copy of the stream. Whether a contact exists
    # cannot consume randomness belonging to geometric construction.
    context_rng = random.Random()
    context_rng.setstate(rng.getstate())
    if action == "echo":
        paths = transfer(target, reach, commitment.side, rng)
    elif action == "extend":
        paths = depart(target, min(width, height)*(.16+.4*reach), commitment.side, rng)
    elif action == "traverse":
        paths = bridge(target, by_id[commitment.target_ids[1]], reach, commitment.side, rng)
    elif action == "concentrate":
        contacts = encounters(max(target.paths, key=lambda p: p.length()).points, memory, (target.id,)) if consider_context else []
        if contacts and context_rng.random() < .8:
            contact = context_rng.choice(contacts)
            paths = insist(target, rng, position=contact.fraction)
            commitment.context_ids = (contact.other_id,)
            commitment.response = "accent encounter"
        else:
            paths = insist(target, rng)
    else:
        paths = surround(target, reach, commitment.side, rng)
    if consider_context and action in ("surround", "traverse") and context_rng.random() < .65:
        contacts = encounters(paths[0].points, memory)
        if contacts:
            contact = context_rng.choice(contacts)
            paths = yield_at(paths[0], contact, gap=context_rng.uniform(2.2, 4.5)) + paths[1:]
            commitment.context_ids = (contact.other_id,)
            commitment.response = "yield at crossing"
    clipped = (boundary(paths) if boundary else clip_paths(paths, width, height))[:6]
    per_path = MAX_MACHINE_POINTS // max(1, len(clipped))
    bounded = [Path(points=resample(p.points, per_path)) for p in clipped]
    return bounded, target.construction
