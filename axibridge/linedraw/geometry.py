"""Image-space curve helpers preserved from the local linedraw studies."""

import numpy as np


def arc(p):
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())


def simplify(p, eps=0.45):
    p = np.asarray(p, float)
    if len(p) < 3:
        return p
    d = p[-1] - p[0]
    t = np.clip((p - p[0]) @ d / (d @ d + 1e-12), 0, 1)
    ds = np.linalg.norm(p - (p[0] + t[:, None] * d), axis=1)
    i = int(ds.argmax())
    if ds[i] <= eps:
        return p[[0, -1]]
    return np.vstack([simplify(p[: i + 1], eps)[:-1], simplify(p[i:], eps)])


def samples(p, step=0.9):
    p = np.asarray(p)
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    if d[-1] < 1e-5:
        return p
    t = np.linspace(0, d[-1], max(2, int(d[-1] / step) + 1))
    return np.column_stack([np.interp(t, d, p[:, k]) for k in range(2)])


def line_d(q):
    return "M" + " ".join(f"{x:.1f},{y:.1f}" for x, y in q)


def fit(q, tol, depth=0):
    """Fit new cubic control points, recursively split where evidence departs."""
    q = samples(q, 0.9)
    if len(q) < 4:
        return line_d(q), q
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
    t = s / s[-1]
    a = 1 - t
    basis = np.column_stack([3 * a * a * t, 3 * a * t * t])
    ends = a[:, None] ** 3 * q[0] + t[:, None] ** 3 * q[-1]
    controls = np.linalg.lstsq(basis, q - ends, rcond=None)[0]
    controls = np.clip(controls, q.min(axis=0) - tol * 2, q.max(axis=0) + tol * 2)
    pred = ends + basis @ controls
    err = np.linalg.norm(pred - q, axis=1)
    i = int(err.argmax())
    if err[i] > tol and depth < 7 and i > 1 and i < len(q) - 2:
        d1, p1 = fit(q[: i + 1], tol, depth + 1)
        d2, p2 = fit(q[i:], tol, depth + 1)
        return d1 + " " + d2, np.vstack([p1, p2])
    pts = np.vstack([q[0], controls, q[-1]])
    d = f"M{q[0, 0]:.1f},{q[0, 1]:.1f} C" + " ".join(
        f"{x:.1f},{y:.1f}" for x, y in pts[1:]
    )
    return d, pred
