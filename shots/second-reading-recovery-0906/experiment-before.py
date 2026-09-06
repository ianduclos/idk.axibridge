"""Experimental geometry on the recovered response policy; no composition score.

The first engine stays frozen. Decision and shaping randomness are separate so
shape comparisons keep the original choices. Whole-element fitting happens only
in document(), never to individual additions in the working memory.
"""
import math
import random

from ..model import Path
from . import _second_reading_first as first
from ._second_reading_gestures import articulated, follow, sampled


def frame(width, height, boundary):
    return (-width*.5, -height*.5, width*2, height*2) if boundary == "fit" else (0, 0, width, height)


def fit_transform(paths, width, height):
    points = [p for path in paths for p in path.points]
    if not points:
        return (1., 0., 0.)
    xs, ys = zip(*points)
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    # Never enlarge a small element. One affine preserves all passage ratios.
    scale = min(1., (width-8)/max(1e-9, hi_x-lo_x), (height-8)/max(1e-9, hi_y-lo_y))
    return scale, (width-scale*(lo_x+hi_x))/2, (height-scale*(lo_y+hi_y))/2


def transformed(paths, transform):
    scale, dx, dy = transform
    return [Path(points=[(x*scale+dx, y*scale+dy) for x,y in p.points], filled=p.filled) for p in paths]


def contain(paths, width, height, boundary):
    if boundary == "contain":
        # Bend an overshooting coordinate back progressively, rather than
        # scaling a new answer or laying a long clamped run on the border.
        def bend(v, size):
            margin = min(8., size*.08)
            if v < margin:
                return margin*math.exp(max(-60., (v-margin)/margin))
            if v > size-margin:
                return size-margin*math.exp(max(-60., (size-margin-v)/margin))
            return v
        return [Path(points=[(bend(x,width),bend(y,height)) for x,y in p.points]) for p in paths]
    x,y,w,h = frame(width,height,boundary)
    shifted = transformed(paths,(1,-x,-y))
    return transformed(first.clip_paths(shifted,w,h),(1,x,y))


def choose(memory, controls, rng, relational=False):
    if not relational:
        return first.choose(memory, controls['recurrence'], controls['persistence'], rng)
    # Attention broadens eligible material; the newest human stroke has no
    # guaranteed priority. Keep the baseline action duration and its ancestry.
    c = first.choose(memory, controls['attention'], controls['persistence'], rng)
    if c.action == 'traverse':
        target = next(p for p in memory if p.id == c.target_ids[0])
        others = [p for p in memory if p.id != target.id]
        # Prefer a span of shaped space sharing direction, not merely the
        # farthest centre. No ranking of the whole drawing is implied.
        other = max(others, key=lambda p: math.dist(p.centre,target.centre)*
                    (.35+abs(sum(a*b for a,b in zip(p.direction,target.direction)))))
        c.target_ids = (target.id, other.id)
    return c


def make_action(c, memory, controls, width, height, rng, boundary, relational=False):
    target = next(p for p in memory if p.id == c.target_ids[0])
    reach = controls['reach']
    departure, scale = controls['departure'], controls['scale']
    side, iteration = c.side, c.iteration+1
    # Unequal sizes belong to the geometry stream; they cannot reroll attention.
    extent = min(width,height)*(.04+.38*scale)*rng.uniform(.65,1.35)
    if c.action == 'echo':
        paths = first.echo(target, first.mul(first.normal(target.direction), side*(2+reach*9)*iteration),
                           1+side*departure*.18*iteration)
        if departure:
            paths = [Path(points=[first.add(p, first.mul(target.direction,
                       math.sin(math.pi*i/(len(path.points)-1))*departure*target.length*.12))
                       for i,p in enumerate(path.points)]) for path in paths]
    elif c.action == 'extend':
        paths = first.extend(target, extent, side*(.12+.85*departure))
    elif c.action == 'traverse':
        other = next(p for p in memory if p.id == c.target_ids[1])
        paths = first.traverse(target,other,side*(.04+.42*departure)*iteration)
        if relational:
            # A second answer to the SAME interval: make its empty side into
            # an open pocket, retaining both selected endpoints.
            a,d = paths[0].points[0],paths[0].points[-1]
            delta = first.sub(d,a); n=first.normal(first.unit(delta))
            b=first.add(first.add(a,first.mul(delta,.18)),first.mul(n,side*extent))
            e=first.add(first.add(a,first.mul(delta,.82)),first.mul(n,side*extent*(.35+.6*departure)))
            paths=[Path(points=first.cubic(a,b,e,d))]
    else:
        paths = first.concentrate(target,.25+.5*rng.random(),.15+.45*scale,.24+.45*reach,side)
    # Usually locally soften an angular joint, retaining one hinge. A sparse
    # wandering answer keeps its guide relationship and may arrive broken.
    if c.action in ('extend','traverse') and rng.random() < .16:
        paths = follow(paths[0].points,rng,.3+.5*departure,arrive=c.action=='traverse')
        c.response = 'wandering guide'
    else:
        paths = [articulated(p.points,(1,))[0] if len(p.points)==4 else p for p in paths]
        c.response = 'open interval' if relational and c.action=='traverse' else None
    paths = contain(paths,width,height,boundary)[:6]
    return [Path(points=first.resample(p.points,384//max(1,len(paths)))) for p in paths], target.construction
