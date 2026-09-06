"""A hand that follows passages with momentum, and light capture smoothing.

The guide is a relationship, not the final curve. Correlated steering changes
make departures grow over a passage; occasional heading changes break them.
Raw pointer input stays in the recipe, separate from its softened rendering.
"""

from __future__ import annotations

import bisect
import math
import random

from shapely.geometry import LineString

from ..model import Path, Point
from ._second_reading import add, cubic, mul, normal, resample, sub, unit


def sampled(points: list[Point], count: int) -> list[Point]:
    distances = [0.0]
    for a, b in zip(points, points[1:]):
        distances.append(distances[-1] + math.dist(a, b))
    if distances[-1] < 1e-9:
        return [points[0]]*count
    out = []
    for i in range(count):
        at = distances[-1]*i/(count-1)
        j = min(len(points)-2, max(0, bisect.bisect_right(distances, at)-1))
        t = (at-distances[j])/max(1e-10, distances[j+1]-distances[j])
        out.append(add(points[j], mul(sub(points[j+1], points[j]), t)))
    out[0], out[-1] = points[0], points[-1]
    return out


def smooth_capture(points: list[Point], amount: float = .6) -> list[Point]:
    if amount <= 0 or len(points) < 3:
        return list(points)
    # Sub-pen-scale simplification removes sampling chatter before deciding
    # where a corner is. A 55-degree change must also persist across 2 mm,
    # otherwise high-frequency pointer noise would be mistaken for intention.
    clean = list(LineString(points).simplify(.22*amount, preserve_topology=False).coords)
    if len(clean) < 3:
        return clean
    cum = [0.0]
    for a, b in zip(clean, clean[1:]):
        cum.append(cum[-1]+math.dist(a, b))
    corners = [0]
    for i in range(1, len(clean)-1):
        left = max(0, bisect.bisect_right(cum, cum[i]-2.0)-1)
        right = min(len(clean)-1, bisect.bisect_left(cum, cum[i]+2.0))
        a, b = unit(sub(clean[i], clean[i-1])), unit(sub(clean[i+1], clean[i]))
        wide_a, wide_b = unit(sub(clean[i], clean[left])), unit(sub(clean[right], clean[i]))
        if a[0]*b[0]+a[1]*b[1] < math.cos(math.radians(55)) and \
                wide_a[0]*wide_b[0]+wide_a[1]*wide_b[1] < math.cos(math.radians(50)):
            corners.append(i)
    corners.append(len(clean)-1)
    out = []
    # Chaikin's convex construction cannot overshoot a paper edge. Split at
    # detected corners so those vertices and open endpoints survive exactly.
    budget = max(len(points), 384)
    extra = max(0, budget-len(clean))
    for start, end in zip(corners, corners[1:]):
        segment = clean[start:end+1]
        if len(segment) > 2:
            cut = .25*amount
            for _ in range(3):
                nxt = [segment[0]]
                for a, b in zip(segment, segment[1:]):
                    nxt.extend((add(mul(a, 1-cut), mul(b, cut)),
                                add(mul(a, cut), mul(b, 1-cut))))
                segment = nxt + [segment[-1]]
            allowance = end-start+1 + int(extra*(end-start)/(len(clean)-1))
            segment = resample(segment, max(2, allowance))
        out.extend(segment if not out else segment[1:])
    out[0], out[-1] = points[0], points[-1]
    return out


def follow(guide: list[Point], rng: random.Random, freedom: float = .5,
           arrive: bool = False, allow_break: bool = True) -> list[Path]:
    length = sum(math.dist(a, b) for a, b in zip(guide, guide[1:]))
    if length < .5:
        return [Path(points=list(guide))]
    count = min(280, max(48, math.ceil(length/.6)))
    guide = sampled(guide, count)
    heading = math.atan2(*reversed(sub(guide[1], guide[0])))
    position = guide[0]
    chunks = [[position]]
    speed = length/(count-1)
    curvature = 0.0
    bias = 0.0
    held = 0
    # A single irreversible change during a passage can leave a real hinge.
    # Its location varies independently of the sampling rate and path length.
    break_at = rng.randrange(count//3, count*4//5) if allow_break and rng.random() < .32 else -1
    lookahead = rng.randint(4, 14)
    gain = rng.uniform(.075, .16)
    stride = 1.0
    for i in range(1, count):
        if held <= 0:
            held = rng.randint(9, 28)
            bias = rng.uniform(-.07, .07)*freedom
            stride = rng.uniform(.82, 1.22)
        held -= 1
        aim = guide[min(count-1, i+lookahead)]
        delta = sub(aim, position)
        desired = math.atan2(delta[1], delta[0])
        error = (desired-heading+math.pi) % math.tau-math.pi
        wanted = max(-.32, min(.32, error*gain + bias))
        curvature += .22*(wanted-curvature)
        if i == break_at:
            heading += rng.choice((-1, 1))*rng.uniform(.7, 1.5)
            curvature *= .15
            if rng.random() < .22:
                position = add(position, (math.cos(heading)*speed*2, math.sin(heading)*speed*2))
                chunks.append([position])
        heading += curvature
        position = add(position, (math.cos(heading)*speed*stride, math.sin(heading)*speed*stride))
        chunks[-1].append(position)
    if arrive:
        destination = guide[-1]
        distance = math.dist(position, destination)
        if distance > .01:
            tangent = unit(sub(guide[-1], guide[-2]))
            b = add(position, (math.cos(heading)*distance*.35, math.sin(heading)*distance*.35))
            c = sub(destination, mul(tangent, distance*.3))
            chunks[-1].extend(cubic(position, b, c, destination, 24)[1:])
    return [Path(points=p) for p in chunks if len(p) > 1]


def opening_gesture(start: Point, heading: float, extent: float,
                    rng: random.Random, allow_break: bool = True) -> list[Path]:
    guide = [start, add(start, (math.cos(heading)*extent*.18, math.sin(heading)*extent*.18))]
    for _ in range(rng.randint(3, 5)):
        heading += rng.uniform(-1.05, 1.2)
        stride = extent*rng.uniform(.18, .4)
        guide.append(add(guide[-1], (math.cos(heading)*stride, math.sin(heading)*stride)))
    return follow(guide, rng, .35, allow_break=allow_break)


def articulated(knots: list[Point], hinges: tuple[int, ...] = ()) -> list[Path]:
    """Long runs with locally rounded joints and a few unrepaired corners."""
    points = [knots[0]]
    for i in range(1, len(knots)-1):
        a, b, c = knots[i-1:i+2]
        if i in hinges:
            points.append(b)
        else:
            before = add(b, mul(sub(a, b), .23))
            after = add(b, mul(sub(c, b), .31))
            points.append(before)
            points.extend(cubic(before, b, b, after, 14)[1:])
    points.append(knots[-1])
    return [Path(points=points)]
