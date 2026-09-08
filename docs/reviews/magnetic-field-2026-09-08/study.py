"""Standalone magnetic drawing study; no axibridge imports or hardware access.

Run from repo root: .venv/bin/python docs/reviews/magnetic-field-2026-09-08/study.py
The softened planar pole field is an artistic approximation, not a material solver.
All three treatments reuse precisely the same traced field for each arrangement.
"""
from pathlib import Path
import hashlib
import json
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon, Circle
import numpy as np

OUT = Path(__file__).resolve().parent
W, H = 240.0, 170.0
STEP = 0.42
PEN = 0.19  # physical mm; every ink mark uses the same nib
SEED = 90826


def bar(cx, cy, angle, flip=False):
    a = math.radians(angle)
    u = np.array([math.cos(a), math.sin(a)])
    v = np.array([-u[1], u[0]])
    c = np.array([cx, cy])
    return dict(c=c, u=u, v=v, poles=[(*(c-24*u), -1 if flip else 1),
                                     (*(c+24*u), 1 if flip else -1)])


SCENES = [
    dict(title="Opposite poles facing", bars=[bar(70, 85, 0), bar(170, 85, 0)], points=[]),
    dict(title="Like poles facing", bars=[bar(70, 85, 0), bar(170, 85, 0, True)], points=[]),
    dict(title="Bar + independent poles", bars=[bar(79, 107, -27)],
         points=[(172., 58., 1.), (184., 122., -1.)]),
]


def inside(p, scene, padding=0.0):
    for b in scene["bars"]:
        d = np.asarray(p)-b["c"]
        if abs(d @ b["u"]) <= 24+padding and abs(d @ b["v"]) <= 6+padding:
            return True
    return any(math.hypot(p[0]-x, p[1]-y) <= 4+padding for x, y, _ in scene["points"])


def field(p, poles):
    bx = by = 0.0
    for x, y, q in poles:
        dx, dy = p[0]-x, p[1]-y
        r2 = dx*dx+dy*dy+0.7**2
        bx += q*dx/r2
        by += q*dy/r2
    n = math.hypot(bx, by)
    return np.array([bx/n, by/n]) if n > 1e-9 else None


def trace(seed, direction, poles, scene):
    p = np.asarray(seed, dtype=float)
    path = [p.copy()]
    for _ in range(2200):
        f = field(p, poles)
        if f is None:
            break
        mid = p + direction*STEP*.5*f
        fmid = field(mid, poles)
        if fmid is None:
            break
        nxt = p + direction*STEP*fmid
        if inside(nxt, scene, .18):
            break
        if not (0 <= nxt[0] <= W and 0 <= nxt[1] <= H):
            # End on the actual boundary, rather than relying on SVG clipping.
            d = nxt-p
            t = 1.0
            for k, bound in [(0, W), (1, H)]:
                if nxt[k] < 0:
                    t = min(t, -p[k]/d[k])
                elif nxt[k] > bound:
                    t = min(t, (bound-p[k])/d[k])
            path.append(np.clip(p+t*d, [0, 0], [W, H]))
            break
        if len(path) > 12 and np.dot(nxt-p, p-path[-2]) < 0:
            break  # approaching a null; never turn back into a doubled segment
        path.append(nxt.copy())
        p = nxt
        if len(path) > 40 and np.linalg.norm(p-path[-30]) < STEP*2:
            break
    return path


def traces(scene):
    poles = [p for b in scene["bars"] for p in b["poles"]] + scene["points"]
    rng = np.random.default_rng(SEED)
    seeds = []
    for x, y, _ in poles:
        for angle in np.linspace(0, 2*math.pi, 92, endpoint=False):
            # Small angular variation prevents a mechanically equal fan.
            a = angle + rng.normal(0, .006)
            seeds.append(np.array([x+9*math.cos(a), y+9*math.sin(a)]))
    for x in np.arange(2, W, 4.4):
        seeds.extend([np.array([x, .02]), np.array([x, H-.02])])
    for y in np.arange(2, H, 4.4):
        seeds.extend([np.array([.02, y]), np.array([W-.02, y])])
    # Fine occupancy grid rejects duplicate routes, without truncating accepted paths.
    pitch = .9
    occupied = np.zeros((int(H/pitch)+2, int(W/pitch)+2), dtype=bool)
    result = []
    for seed in seeds:
        if inside(seed, scene, .3):
            continue
        ix, iy = np.floor(seed/pitch).astype(int)
        if occupied[iy, ix]:
            continue
        left = trace(seed, -1, poles, scene)
        right = trace(seed, 1, poles, scene)
        path = np.array(left[:0:-1]+right)
        if len(path) < 18:
            continue
        ij = np.floor(path/pitch).astype(int)
        # Keep short shared approaches to the poles, reject retraced routes.
        if np.mean(occupied[ij[:, 1], ij[:, 0]]) > .42:
            continue
        occupied[ij[:, 1], ij[:, 0]] = True
        result.append(path)
    return result, poles


def portion(path, arc, start, end):
    keep = (arc > start) & (arc < end)
    ends = np.array([[np.interp(s, arc, path[:, k]) for k in (0, 1)] for s in (start, end)])
    return np.vstack([ends[0], path[keep], ends[1]])


def texture(paths, style, scene, row):
    if style == 0:
        return paths
    rng = np.random.default_rng(SEED + 100*row + style)
    marks = []
    for i, path in enumerate(paths):
        arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
        total = arc[-1]
        pos = rng.uniform(0, 1.8)
        while pos < total-.15:
            x, y = [np.interp(pos, arc, path[:, k]) for k in (0, 1)]
            # Shared smooth modulation creates patches that span neighbouring routes.
            patch = (math.sin(x*.072+y*.043)+math.sin(y*.119-x*.028)+2)/4
            if style == 1:
                length = rng.uniform(.28, 1.8)*(0.55+patch*1.3)
                gap = rng.uniform(.18, .95)*(1.35-patch*.7)
                if rng.random() < .045:
                    length *= 3.8
                p = portion(path, arc, pos, min(total, pos+length))
                # Slow lateral drift keeps the chain irregular without losing its route.
                delta = p[-1]-p[0]
                norm = np.linalg.norm(delta)
                if norm > 0:
                    normal = np.array([-delta[1], delta[0]])/norm
                    shift = .09*math.sin(pos*.65+i*1.7)+rng.normal(0, .045)
                    p += normal*shift
            else:
                length = rng.uniform(.32, 1.32)*(0.8+patch*.8)
                gap = rng.uniform(.6, 1.9)
                p = portion(path, arc, pos, min(total, pos+length))
                delta = p[-1]-p[0]
                norm = np.linalg.norm(delta)
                if norm > 0:
                    normal = np.array([-delta[1], delta[0]])/norm
                    p += normal*rng.normal(0, .58)
                    theta = rng.normal(0, .13)
                    rot = np.array([[math.cos(theta), -math.sin(theta)],
                                    [math.sin(theta), math.cos(theta)]])
                    center = p.mean(axis=0)
                    p = (p-center) @ rot.T+center
            p = np.clip(p, [0, 0], [W, H])
            if not any(inside(pt, scene, .12) for pt in p):
                if np.linalg.norm(np.diff(p, axis=0), axis=1).sum() > .08:
                    marks.append(p)
            pos += length+gap
    return marks


def magnets(ax, scene):
    for b in scene["bars"]:
        c, u, v = b["c"], b["u"], b["v"]
        corners = [c+su*24*u+sv*6*v for su, sv in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        ax.add_patch(Polygon(corners, facecolor="white", edgecolor="black", linewidth=.7, zorder=5))
        for sign, pole in zip([-1,1], b["poles"]):
            p = c+sign*17*u
            ax.text(*p, "N" if pole[2] > 0 else "S", ha="center", va="center",
                    fontfamily="DejaVu Serif", fontstyle="italic", fontsize=10, zorder=6)
    for x, y, q in scene["points"]:
        ax.add_patch(Circle((x, y), 4, facecolor="white", edgecolor="black", linewidth=.7, zorder=5))
        ax.text(x, y, "N" if q > 0 else "S", ha="center", va="center", fontsize=8, zorder=6)


def draw(ax, scene, paths, width_inches):
    # Data-space mm -> physical figure points: identical stroke at all output scales.
    stroke = PEN/W*width_inches*72
    ax.add_collection(LineCollection(paths, colors="black", linewidths=stroke, capstyle="round", joinstyle="round"))
    magnets(ax, scene)
    ax.set(xlim=(0,W), ylim=(H,0), aspect="equal")
    ax.set_axis_off()


def main():
    plt.rcParams.update({"svg.fonttype": "path", "svg.hashsalt": "magnetic-study-0908",
                         "font.family": "DejaVu Sans", "savefig.facecolor": "white"})
    fig = plt.figure(figsize=(18, 14.35), facecolor="white")
    fig.text(.04, .968, "MAGNETIC FIELDS", fontsize=23, weight="bold")
    fig.text(.04, .94, "01 / Visual study     ·     three arrangements × three mark treatments", fontsize=10)
    titles = ["Continuous curves", "Irregular chains", "Loose filings"]
    for col, title in enumerate(titles):
        fig.text(.04+col*.319, .9, f"{chr(65+col)}   {title}", fontsize=13, weight="bold")
    metrics = {}
    neutral = plt.figure(figsize=(18, 13.7), facecolor="white")
    for row, scene in enumerate(SCENES):
        paths, poles = traces(scene)
        digest = hashlib.sha256(b"".join(p.tobytes() for p in paths)).hexdigest()
        top = .872-row*.269
        fig.text(.04, top+.009, f"{row+1:02}   {scene['title']}", fontsize=9)
        for col in range(3):
            ident = f"{chr(65+col)}{row+1}"
            marks = texture(paths, col, scene, row)
            if row == 0 and col == 1:
                regular = []
                for route in paths:
                    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(route,axis=0),axis=1))]
                    for pos in np.arange(0, arc[-1]-.15, 1.8):
                        regular.append(portion(route, arc, pos, min(pos+1.2, arc[-1])))
                calibration = plt.figure(figsize=(16,6), facecolor="white")
                for n, variant in enumerate([regular, marks]):
                    vx = calibration.add_axes([.015+.50*n,.01,.47,.91])
                    draw(vx, scene, variant, 16*.47)
                    calibration.text(.025+.5*n,.945,["X","Y"][n],fontsize=14)
                calibration.savefig(OUT/"review-variants.png",dpi=150)
                plt.close(calibration)
            coords = np.vstack(marks)
            assert np.isfinite(coords).all(), ident
            assert (coords >= 0).all() and (coords <= [W,H]).all(), ident
            assert all(len(p) >= 2 for p in marks), ident
            lengths = [float(np.linalg.norm(np.diff(p,axis=0),axis=1).sum()) for p in marks]
            assert min(lengths) > 0, ident
            metrics[ident] = dict(paths=len(marks), vertices=len(coords), length_mm=sum(lengths),
                                 bounds=[coords.min(axis=0).tolist(),coords.max(axis=0).tolist()],
                                 field_sha256=digest, underlying_routes=len(paths))
            ax = fig.add_axes([.04+col*.319, top-.233, .295, .233])
            draw(ax, scene, marks, 18*.295)
            ax.text(2, 5, ident, fontsize=8, bbox=dict(facecolor="white", edgecolor="none", pad=3), zorder=9)
            bx = neutral.add_axes([.025+col*.326, .686-row*.33, .308, .30])
            draw(bx, scene, marks, 18*.308)
            bx.text(2, 5, ident, fontsize=9, bbox=dict(facecolor="white", edgecolor="none", pad=3), zorder=9)
            close = plt.figure(figsize=(12, 8.5), facecolor="white")
            cx = close.add_axes([0,0,1,1])
            draw(cx, scene, marks, 12)
            close.savefig(OUT/f"{ident}.png", dpi=150)
            close.savefig(OUT/f"{ident}.svg", metadata={"Date":None})
            plt.close(close)
            print(ident, len(paths), "routes /", len(marks), "marks", flush=True)
    fig.text(.04, .038, "Same field within each row · constant pen width · simplified planar pole model · independent poles are compositional controls", fontsize=9)
    fig.text(.04, .02, "Screen study — physical ink, paper and plotting time have not been tested.", fontsize=9)
    fig.savefig(OUT/"comparison.svg", metadata={"Date":None})
    fig.savefig(OUT/"comparison.png", dpi=160)
    neutral.savefig(OUT/"review-neutral.png", dpi=130)
    (OUT/"geometry-checks.json").write_text(json.dumps(metrics, indent=2)+"\n")
    plt.close("all")


if __name__ == "__main__":
    main()
