"""Responses that use the shape of a passage, rather than follow a noisy guide.

Selection lives in the engine. These constructions can be tested with the same
random stream against different drawings: geometry must account for the change.
"""
from __future__ import annotations
import math
import random
from ..model import Path, Point
from ._second_reading import Passage, add, sub, mul, unit, normal, cubic
from ._second_reading_gestures import sampled


def through(knots: list[Point], corners: tuple[int, ...] = ()) -> list[Point]:
    """Interpolating cubic runs; a retained corner interrupts the tangent."""
    result = [knots[0]]
    for i, (a, b) in enumerate(zip(knots, knots[1:])):
        incoming = sub(b, knots[max(0, i-1)])
        outgoing = sub(knots[min(len(knots)-1, i+2)], a)
        chord = math.dist(a, b)
        left = mul(unit(incoming), min(chord*.38, math.hypot(*incoming)*.16))
        right = mul(unit(outgoing), min(chord*.38, math.hypot(*outgoing)*.16))
        if i in corners:
            left = mul(sub(b, a), .25)
        if i+1 in corners:
            right = mul(sub(b, a), .25)
        result.extend(cubic(a, add(a, left), sub(b, right), b, 18)[1:])
    return result


def transfer(target: Passage, reach: float, side: int, rng: random.Random) -> list[Path]:
    """A whole-passage relative: unequal scale and rotation, one shared map."""
    pivot = target.endpoints[rng.randrange(len(target.endpoints))]
    angle = side*rng.uniform(.3, .95)
    size = rng.choice((rng.uniform(.55, .8), rng.uniform(1.2, 1.65)))
    size *= .8+.5*reach
    along, across = target.direction, normal(target.direction)
    stretch = rng.uniform(.65, 1.6)
    displacement = mul(across, side*(7+reach*20))
    cosine, sine = math.cos(angle), math.sin(angle)
    out = []
    for path in target.paths[:3]:
        moved = []
        for p in sampled(path.points, 80):
            d = sub(p, pivot)
            x, y = d[0]*along[0]+d[1]*along[1], d[0]*across[0]+d[1]*across[1]
            d = add(mul(along, x*size), mul(across, y*size*stretch))
            rotated = (cosine*d[0]-sine*d[1], sine*d[0]+cosine*d[1])
            moved.append(add(add(pivot, displacement), rotated))
        out.append(Path(points=moved))
    return out


def depart(target: Passage, extent: float, side: int, rng: random.Random) -> list[Path]:
    spine = max(target.paths, key=lambda p: p.length())
    profile = sampled(spine.points, 9)
    # Carry forward the target's changes of direction, at a new scale. This
    # answers a hook differently from a straight crossing with the same seed.
    start = profile[-1]
    tangent = unit(sub(profile[-1], profile[-2]))
    across = normal(tangent)
    width = rng.uniform(.18, .48)*extent*side
    knots = [start, add(start, mul(tangent, extent*.25))]
    source_origin = profile[0]
    source_axis = unit(sub(profile[-1], source_origin))
    source_normal = normal(source_axis)
    span = max(5.0, max(math.dist(p, source_origin) for p in profile))
    for j in (3, 5, 7, 8):
        t = j/8
        d = sub(profile[j], source_origin)
        shape = (d[0]*source_normal[0]+d[1]*source_normal[1])/span
        forward = extent*(t*.95 + .12*math.sin(t*math.pi))
        lateral = width*math.sin(t*math.pi*1.35)+shape*extent*.85
        knots.append(add(start, add(mul(tangent, forward), mul(across, lateral))))
    corners = (rng.randrange(2, 5),) if rng.random() < .4 else ()
    return [Path(points=through(knots, corners))]


def surround(target: Passage, reach: float, side: int, rng: random.Random) -> list[Path]:
    """Borrow part of a contour, then return around a substantial open space."""
    spine = sampled(max(target.paths, key=lambda p: p.length()).points, 13)
    start = rng.randint(0, 3)
    stop = rng.randint(9, 12)
    a, b = spine[start], spine[stop]
    axis = unit(sub(b, a))
    across = mul(normal(axis), side)
    width = (12+reach*35)*rng.uniform(.8, 1.5)
    middle = spine[(start+stop)//2]
    # Tangential excess produces lobes rather than evenly offset outlines.
    knots = [a, spine[min(stop, start+2)],
             add(b, mul(across, width*.18)),
             add(add(b, mul(axis, width*.3)), mul(across, width)),
             add(middle, mul(across, width*rng.uniform(.85, 1.65))),
             add(add(a, mul(axis, -width*.25)), mul(across, width*.7)),
             add(a, mul(across, width*.18))]
    corners = (rng.choice((2, 4, 5)),) if rng.random() < .65 else ()
    return [Path(points=through(knots, corners))]


def bridge(first: Passage, second: Passage, reach: float, side: int,
           rng: random.Random) -> list[Path]:
    a_profile = sampled(max(first.paths, key=lambda p: p.length()).points, 9)
    b_profile = sampled(max(second.paths, key=lambda p: p.length()).points, 9)
    a = a_profile[rng.choice((0, 4, 8))]
    b = b_profile[rng.choice((0, 4, 8))]
    axis = unit(sub(b, a)); across = mul(normal(axis), side)
    distance = math.dist(a, b)
    bow = min(65, distance*(.2+reach*.45))
    # The two actual interiors influence the route, as well as its anchors.
    first_bend = sub(a_profile[4], mul(add(a_profile[0], a_profile[-1]), .5))
    second_bend = sub(b_profile[4], mul(add(b_profile[0], b_profile[-1]), .5))
    knots = [a, add(add(a, mul(sub(b, a), .23)), add(mul(across, bow), mul(first_bend, .45))),
             add(add(a, mul(sub(b, a), .7)), add(mul(across, bow*.55), mul(second_bend, .45))), b]
    return [Path(points=through(knots))]


def insist(target: Passage, rng: random.Random, position: float | None = None) -> list[Path]:
    """One short dark assertion, made from physical passes at pen-scale spacing."""
    spine = sampled(max(target.paths, key=lambda p: p.length()).points, 65)
    start = rng.randint(5, 40)
    stop = min(64, start+rng.randint(10, 22))
    if position is not None:
        half = (stop-start)/2
        centre = max(half, min(64-half, position*64))
        start, stop = round(centre-half), round(centre+half)
    interval = sampled(spine[start:stop+1], 48)
    out = []
    for k in range(6):
        points = []
        for i, p in enumerate(interval):
            tangent = unit(sub(interval[min(47, i+1)], interval[max(0, i-1)]))
            taper = .25+.75*math.sin(math.pi*i/47)
            points.append(add(p, mul(normal(tangent), (k-2.5)*.18*taper)))
        out.append(Path(points=points))
    return out
