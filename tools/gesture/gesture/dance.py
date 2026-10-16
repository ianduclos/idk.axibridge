"""Dance motion → 2D structures for the topology layer (round 8, dance_structure).

Ian (binding): "contemporary dance pose extraction for the topology layer —
get the gestures, then abstract and combine to turn non-human."
docs/research/gesture-corpus/dance-gesture.md (M1 trails, M2b strobe, M5
operators); results/dance_structure-2026-10-16.md.

numpy only (scipy for smoothing / KD-tree). Nothing here touches the hand:
mocap trails carry no sub-σ texture, so dance belongs to the STRUCTURE layer
and the hand comes later from restyle.py / regime_field.compose.

Reading
  load_bvh(path, frames=slice, stride)       BVH (any channel order) → Motion
  load_asf(path) + load_amc(path, asf, ...)  CMU ASF/AMC → Motion
  Motion.pos (T, J, 3) global joint positions (FK), names, parents, fps;
  Motion.find(alias) resolves body-part aliases across skeletons
  ("lhand", "rfoot", "head", "root", "lelbow", ... see ALIASES).

Views (3D → page, y down, `up` auto-detected)
  view_basis(m, "front" | "side" | "top" | "pca") → (3, 2) basis

Structures (all → Drawing in px on a `size` canvas, README contract)
  trails       end-effector trails cut at whole-body stillness (phrases)
  strobe       skeleton time-slices at held poses (Marey stack, M2b)
  relative     a joint's path seen from another joint (moving frame)
Abstraction toward the non-human (M5)
  graft        limbs of dancer B carried on dancer A's root path
  chimera      pieces cut at velocity minima, re-attached end to start
               with sharp deflections, some time-reversed: ONE contiguous
               line built from many limbs / dancers
  impossible_tree  a recursively branching planar skeleton whose joint
               angles at depth k are the dancer's projected joint-angle
               streams (with per-branch canon lags); its tips' trails
Per-point kinematics (meta "speed", "acc": body-heights / s, / s²) ride on
every trail stroke; `kinematic_r` maps them to a regime value
(stillness → mass, acceleration → nib, speed → wire) and `kinematic_field`
turns that into a regime_field.Field for compose().

Purity: inputs are never mutated. Randomness takes a seed / Generator.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d, maximum_filter1d

from .core import Drawing, Stroke

# ---------------------------------------------------------------------------
# Motion
# ---------------------------------------------------------------------------

ALIASES: dict[str, tuple[str, ...]] = {
    "root": ("root", "Hips"),
    "chest": ("thorax", "Spine3", "Spine2"),
    "neck": ("upperneck", "Neck"),
    "head": ("head", "Head_end", "Head"),
    "lshoulder": ("lclavicle", "LeftArm"),
    "lelbow": ("lhumerus", "LeftForeArm"),
    "lwrist": ("lradius", "LeftHand"),
    "lhand": ("lfingers", "LeftHandMiddle3", "LeftHand_end", "LeftHand"),
    "rshoulder": ("rclavicle", "RightArm"),
    "relbow": ("rhumerus", "RightForeArm"),
    "rwrist": ("rradius", "RightHand"),
    "rhand": ("rfingers", "RightHandMiddle3", "RightHand_end", "RightHand"),
    "lhip": ("lhipjoint", "LeftUpLeg"),
    "lknee": ("lfemur", "LeftLeg"),
    "lankle": ("ltibia", "LeftFoot"),
    "lfoot": ("ltoes", "LeftToeBase_end", "LeftToeBase"),
    "rhip": ("rhipjoint", "RightUpLeg"),
    "rknee": ("rfemur", "RightLeg"),
    "rankle": ("rtibia", "RightFoot"),
    "rfoot": ("rtoes", "RightToeBase_end", "RightToeBase"),
}
EFFECTORS = ("lhand", "rhand", "lfoot", "rfoot", "head")
CHAINS = {
    "spine": ("root", "chest", "neck", "head"),
    "larm": ("chest", "lshoulder", "lelbow", "lwrist", "lhand"),
    "rarm": ("chest", "rshoulder", "relbow", "rwrist", "rhand"),
    "lleg": ("root", "lhip", "lknee", "lankle", "lfoot"),
    "rleg": ("root", "rhip", "rknee", "rankle", "rfoot"),
}


@dataclass(frozen=True)
class Motion:
    names: list[str]
    parents: np.ndarray            # (J,) int, −1 = root
    pos: np.ndarray                # (T, J, 3) global positions (file units)
    fps: float
    source: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def T(self) -> int:
        return int(self.pos.shape[0])

    def index(self, name: str) -> int:
        return self.names.index(name)

    def find(self, alias: str) -> int:
        """Joint index for a body-part alias (ALIASES) or an exact name."""
        if alias in self.names:
            return self.names.index(alias)
        for n in ALIASES.get(alias, ()):
            if n in self.names:
                return self.names.index(n)
        raise KeyError(f"{alias!r} not in skeleton ({self.source})")

    def up_axis(self) -> int:
        """Axis along which the head sits above the root on average."""
        d = self.pos[:, self.find("head")] - self.pos[:, self.find("root")]
        return int(np.argmax(np.abs(d.mean(axis=0))))

    def height(self) -> float:
        """Median root→head distance ×2 (a body-height unit, file units)."""
        d = np.linalg.norm(self.pos[:, self.find("head")] - self.pos[:, self.find("root")], axis=1)
        return float(2.0 * np.median(d)) or 1.0

    def window(self, t0: float = 0.0, t1: float | None = None) -> "Motion":
        """Seconds [t0, t1)."""
        a = int(round(t0 * self.fps))
        b = self.T if t1 is None else int(round(t1 * self.fps))
        return Motion(self.names, self.parents, self.pos[a:b].copy(), self.fps, self.source,
                      {**self.meta, "window": [t0, t1]})


def _rot(axis: str, ang: np.ndarray) -> np.ndarray:
    """(T, 3, 3) rotation about x/y/z by ang (rad)."""
    c, s = np.cos(ang), np.sin(ang)
    o, z = np.ones_like(ang), np.zeros_like(ang)
    if axis == "x":
        m = [[o, z, z], [z, c, -s], [z, s, c]]
    elif axis == "y":
        m = [[c, z, s], [z, o, z], [-s, z, c]]
    else:
        m = [[c, -s, z], [s, c, z], [z, z, o]]
    return np.moveaxis(np.array(m), [0, 1], [-2, -1])


# --- BVH -------------------------------------------------------------------

def parse_bvh(text: str, frames: slice | None = None, stride: int = 1) -> Motion:
    """Parse BVH text. Rotations compose in channel order (v' = R1 R2 R3 v);
    joints with position channels take those as their local translation.
    End Sites become joints named '<parent>_end'."""
    head, _, motion = text.partition("MOTION")
    tok = head.split()
    names, parents, offsets, chans = [], [], [], []
    stack: list[int] = []
    i = 0
    pending = None
    while i < len(tok):
        t = tok[i]
        if t in ("ROOT", "JOINT"):
            pending = tok[i + 1]
            i += 2
        elif t == "End":
            pending = names[stack[-1]] + "_end"
            i += 2
        elif t == "{":
            names.append(pending)
            parents.append(stack[-1] if stack else -1)
            offsets.append(np.zeros(3))
            chans.append([])
            stack.append(len(names) - 1)
            i += 1
        elif t == "}":
            stack.pop()
            i += 1
        elif t == "OFFSET":
            offsets[stack[-1]] = np.array([float(x) for x in tok[i + 1:i + 4]])
            i += 4
        elif t == "CHANNELS":
            n = int(tok[i + 1])
            chans[stack[-1]] = tok[i + 2:i + 2 + n]
            i += 2 + n
        else:
            i += 1
    lines = motion.strip().splitlines()
    nfr = int(re.search(r"Frames:\s*(\d+)", lines[0]).group(1))
    ft = float(re.search(r"Frame Time:\s*([\d.eE+-]+)", lines[1]).group(1))
    data_lines = lines[2:2 + nfr]
    sl = frames if frames is not None else slice(None)
    data_lines = data_lines[sl][::max(int(stride), 1)]
    D = np.array([np.array(ln.split(), dtype=np.float64) for ln in data_lines])
    if D.ndim != 2:
        D = D.reshape(len(data_lines), -1)
    T = D.shape[0]
    J = len(names)
    pos = np.zeros((T, J, 3))
    G = [None] * J
    col = 0
    for j in range(J):
        ch = chans[j]
        t_loc = np.broadcast_to(offsets[j], (T, 3)).copy()
        R = np.broadcast_to(np.eye(3), (T, 3, 3)).copy()
        for c in ch:
            v = D[:, col]
            col += 1
            if c.endswith("position"):
                t_loc[:, "XYZ".index(c[0])] = v
            else:
                R = R @ _rot(c[0].lower(), np.deg2rad(v))
        p = parents[j]
        if p < 0:
            pos[:, j] = t_loc
            G[j] = R
        else:
            pos[:, j] = pos[:, p] + np.einsum("tij,tj->ti", G[p], t_loc)
            G[j] = G[p] @ R
    return Motion(names, np.array(parents), pos, 1.0 / ft / max(int(stride), 1), meta={"format": "bvh"})


def load_bvh(path, frames: slice | None = None, stride: int = 1) -> Motion:
    m = parse_bvh(Path(path).read_text(), frames, stride)
    return Motion(m.names, m.parents, m.pos, m.fps, Path(path).stem, m.meta)


# --- ASF / AMC (CMU) -------------------------------------------------------

def _euler_xyz(a: np.ndarray) -> np.ndarray:
    """(…,3) deg → rotation Rz·Ry·Rx (static XYZ, the CMU reader convention)."""
    a = np.deg2rad(np.atleast_2d(a))
    return _rot("z", a[:, 2]) @ _rot("y", a[:, 1]) @ _rot("x", a[:, 0])


def parse_asf(text: str) -> dict:
    bones = {}
    hier: dict[str, list[str]] = {}
    root_order = ["TX", "TY", "TZ", "RX", "RY", "RZ"]
    root_axis = np.zeros(3)
    sec = None
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(":"):
            sec = line.split()[0][1:]
            continue
        w = line.split()
        if sec == "root":
            if w[0] == "order":
                root_order = [x.upper() for x in w[1:]]
            elif w[0] == "orientation":
                root_axis = np.array([float(x) for x in w[1:4]])
        elif sec == "bonedata":
            if w[0] == "begin":
                cur = {"dof": []}
            elif w[0] == "end":
                bones[cur["name"]] = cur
            elif w[0] == "name":
                cur["name"] = w[1]
            elif w[0] == "direction":
                cur["direction"] = np.array([float(x) for x in w[1:4]])
            elif w[0] == "length":
                cur["length"] = float(w[1])
            elif w[0] == "axis":
                cur["axis"] = np.array([float(x) for x in w[1:4]])
            elif w[0] == "dof":
                cur["dof"] = [x.lower() for x in w[1:]]
        elif sec == "hierarchy":
            if w[0] in ("begin", "end"):
                continue
            hier[w[0]] = w[1:]
    order = ["root"]
    parent = {"root": None}
    k = 0
    while k < len(order):
        for c in hier.get(order[k], []):
            parent[c] = order[k]
            order.append(c)
        k += 1
    return {"bones": bones, "order": order, "parent": parent, "root_order": root_order, "root_axis": root_axis}


def parse_amc(text: str, asf: dict, frames: slice | None = None, stride: int = 1, fps: float = 120.0) -> Motion:
    """CMU AMC → Motion. Position of a bone = its END point; 'root' = pelvis.
    FK: M_b = M_parent · C · E(dof) · C⁻¹, p_b = p_parent + len · M_b · dir."""
    recs: list[dict] = []
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#:":
            continue
        if line.isdigit():
            cur = {}
            recs.append(cur)
            continue
        if cur is not None:
            w = line.split()
            cur[w[0]] = np.array([float(x) for x in w[1:]])
    sl = frames if frames is not None else slice(None)
    recs = recs[sl][::max(int(stride), 1)]
    T = len(recs)
    order, parent, bones = asf["order"], asf["parent"], asf["bones"]
    J = len(order)
    pos = np.zeros((T, J, 3))
    M = {}
    ro = asf["root_order"]
    rv = np.array([r.get("root", np.zeros(6)) for r in recs])
    tr = np.column_stack([rv[:, ro.index(k)] for k in ("TX", "TY", "TZ")])
    rr = np.column_stack([rv[:, ro.index(k)] for k in ("RX", "RY", "RZ")])
    C = _euler_xyz(asf["root_axis"])[0]
    M["root"] = C @ _euler_xyz(rr) @ C.T
    pos[:, 0] = tr
    for j, name in enumerate(order[1:], start=1):
        b = bones[name]
        C = _euler_xyz(b.get("axis", np.zeros(3)))[0]
        ang = np.zeros((T, 3))
        for k, d in enumerate(b["dof"]):
            if d in ("rx", "ry", "rz"):
                ang[:, "xyz".index(d[1])] = [r.get(name, np.zeros(len(b["dof"])))[k] for r in recs]
        p = parent[name]
        M[name] = M[p] @ (C @ _euler_xyz(ang) @ C.T)
        pos[:, j] = pos[:, order.index(p)] + b["length"] * np.einsum("tij,j->ti", M[name], b["direction"])
    par = np.array([-1] + [order.index(parent[n]) for n in order[1:]])
    return Motion(list(order), par, pos, fps / max(int(stride), 1), meta={"format": "amc"})


def load_amc(path, asf_path=None, frames: slice | None = None, stride: int = 1, fps: float = 120.0) -> Motion:
    path = Path(path)
    asf_path = asf_path or next(path.parent.glob("*.asf"))
    asf = parse_asf(Path(asf_path).read_text())
    m = parse_amc(path.read_text(), asf, frames, stride, fps)
    return Motion(m.names, m.parents, m.pos, m.fps, path.stem, m.meta)


def load(path, t0: float = 0.0, t1: float | None = None, fps_out: float = 60.0) -> Motion:
    """Either format, window [t0, t1) seconds, resampled to ≈ fps_out by stride."""
    path = Path(path)
    if path.suffix.lower() == ".bvh":
        txt = path.read_text()
        ft = float(re.search(r"Frame Time:\s*([\d.eE+-]+)", txt).group(1))
        fps = 1.0 / ft
        st = max(int(round(fps / fps_out)), 1)
        fr = slice(int(t0 * fps), None if t1 is None else int(t1 * fps))
        m = parse_bvh(txt, fr, st)
        return Motion(m.names, m.parents, m.pos, m.fps, path.stem, {**m.meta, "window": [t0, t1]})
    fps = 120.0
    st = max(int(round(fps / fps_out)), 1)
    fr = slice(int(t0 * fps), None if t1 is None else int(t1 * fps))
    m = load_amc(path, frames=fr, stride=st, fps=fps)
    return Motion(m.names, m.parents, m.pos, m.fps, m.source, {**m.meta, "window": [t0, t1]})


# ---------------------------------------------------------------------------
# views and kinematics
# ---------------------------------------------------------------------------

def view_basis(m: Motion, view: str = "front") -> np.ndarray:
    """(3, 2) basis: page x, page y (y DOWN). front = widest horizontal axis
    × up; side = the other horizontal × up; top = floor plan; pca = the two
    principal axes of all joint positions."""
    up = m.up_axis()
    hz = [a for a in range(3) if a != up]
    P = m.pos.reshape(-1, 3)
    P = P - P.mean(axis=0)
    if view == "pca":
        _, _, vt = np.linalg.svd(P[:: max(len(P) // 20000, 1)], full_matrices=False)
        b = vt[:2].T.copy()
        if b[up, 1] > 0:
            b[:, 1] *= -1
        return b
    H = P[:, hz]
    _, _, vt = np.linalg.svd(H[:: max(len(H) // 20000, 1)], full_matrices=False)
    e1 = np.zeros(3)
    e2 = np.zeros(3)
    e1[hz] = vt[0]
    e2[hz] = vt[1]
    u = np.zeros(3)
    u[up] = -1.0
    if view == "front":
        return np.column_stack([e1, u])
    if view == "side":
        return np.column_stack([e2, u])
    if view == "top":
        return np.column_stack([e1, e2])
    raise ValueError(view)


def kinematics(p3: np.ndarray, fps: float, unit: float, sigma_s: float = 0.04) -> tuple[np.ndarray, np.ndarray]:
    """Speed and acceleration magnitude of a (T, 3) path, in units/s, /s²."""
    q = gaussian_filter1d(p3, max(sigma_s * fps, 0.5), axis=0, mode="nearest") / unit
    v = np.gradient(q, axis=0) * fps
    a = np.gradient(v, axis=0) * fps
    return np.linalg.norm(v, axis=1), np.linalg.norm(a, axis=1)


def energy(m: Motion, sigma_s: float = 0.1) -> np.ndarray:
    """Whole-body kinetic energy proxy per frame (Σ_j |v_j|², body heights/s)."""
    q = gaussian_filter1d(m.pos, max(sigma_s * m.fps, 0.5), axis=0, mode="nearest") / m.height()
    v = np.gradient(q, axis=0) * m.fps
    return np.sum(v ** 2, axis=(1, 2))


def phrase_cuts(m: Motion, *, q: float = 0.3, min_gap_s: float = 1.2) -> np.ndarray:
    """Frame indices of phrase boundaries: local minima of whole-body energy
    below its q-quantile, at least min_gap_s apart (lowest kept first)."""
    e = energy(m)
    thr = np.quantile(e, q)
    loc = np.where((e[1:-1] <= e[:-2]) & (e[1:-1] <= e[2:]) & (e[1:-1] < thr))[0] + 1
    gap = int(min_gap_s * m.fps)
    keep: list[int] = []
    for i in loc[np.argsort(e[loc])]:
        if all(abs(i - k) >= gap for k in keep):
            keep.append(int(i))
    return np.array(sorted(keep), int)


def _dedupe(p: np.ndarray, eps: float, v: np.ndarray | None = None, a: np.ndarray | None = None) -> tuple:
    """Drop points closer than eps to the last kept one. Dropped points are
    folded into the kept one before them: speed by MIN (a pause keeps its
    stillness), acceleration by MAX."""
    keep = [0]
    for i in range(1, len(p)):
        if np.linalg.norm(p[i] - p[keep[-1]]) >= eps:
            keep.append(i)
    k = np.array(keep)
    out = (p[k],)
    if v is not None:
        out += (np.minimum.reduceat(v, k),)
    if a is not None:
        out += (np.maximum.reduceat(a, k),)
    return out


def fit(strokes: list[np.ndarray], size=(840, 1200), margin: float = 0.07) -> tuple[list[np.ndarray], float]:
    """Uniformly scale + centre 2D polylines into the canvas. Returns (out, scale)."""
    W, H = size
    allp = np.vstack([s for s in strokes if len(s)])
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    k = min((W * (1 - 2 * margin)) / span[0], (H * (1 - 2 * margin)) / span[1])
    off = np.array([W, H]) / 2 - (lo + hi) / 2 * k
    return [s * k + off for s in strokes], k


def _drawing(polys, metas, size, source, meta=None, margin=0.07) -> Drawing:
    out, k = fit(polys, size, margin)
    st = [Stroke(p, meta=mt) for p, mt in zip(out, metas) if len(p) >= 3]
    return Drawing(st, source=source, size=tuple(size), meta={**(meta or {}), "px_per_unit": k})


# ---------------------------------------------------------------------------
# structures
# ---------------------------------------------------------------------------

def _effector_trail(m: Motion, j: int, B: np.ndarray, H: float):
    p3 = m.pos[:, j]
    p2 = gaussian_filter1d(p3 @ B, max(0.03 * m.fps, 0.5), axis=0, mode="nearest")
    v, a = kinematics(p3, m.fps, H)
    return p2, v, a


def _split(arrs, cuts):
    bounds = [0] + [int(c) for c in cuts] + [len(arrs[0])]
    return [tuple(x[a:b + 1] for x in arrs) for a, b in zip(bounds[:-1], bounds[1:]) if b - a > 2]


def trails(m: Motion, effectors=EFFECTORS, *, view: str = "front", size=(840, 1200), cut: str = "phrase",
           min_len: float = 0.04, phrase_q: float = 0.3, min_gap_s: float = 1.2) -> Drawing:
    """M1: end-effector trails as strokes, one per effector per phrase
    (cut="phrase") or per effector for the whole window (cut="none").
    Per-point meta "speed"/"acc" in body heights / s (/ s²)."""
    B = view_basis(m, view)
    Hgt = m.height()
    cuts = phrase_cuts(m, q=phrase_q, min_gap_s=min_gap_s) if cut == "phrase" else np.zeros(0, int)
    polys, metas = [], []
    eps = 0.0008 * Hgt
    for name in effectors:
        j = m.find(name)
        p2, v, a = _effector_trail(m, j, B, Hgt)
        for k, (pp, vv, aa) in enumerate(_split((p2, v, a), cuts)):
            pp, vv, aa = _dedupe(pp, eps, vv, aa)
            if len(pp) < 3:
                continue
            polys.append(pp)
            metas.append({"joint": name, "phrase": k, "speed": np.round(vv, 4).tolist(),
                          "acc": np.round(aa, 3).tolist(), "src": m.source})
    d = _drawing(polys, metas, size, f"dance:{m.source}:trails:{view}", {"view": view, "cuts": cuts.tolist()})
    return _min_len(d, min_len)


def _min_len(d: Drawing, min_len: float) -> Drawing:
    R = d.ref_length()
    st = [s for s in d.strokes if s.length() >= min_len * R]
    return Drawing(st, d.source, d.size, d.meta)


def strobe(m: Motion, *, n: int = 10, view: str = "front", size=(840, 1200), chains=tuple(CHAINS),
           spread: float = 0.0) -> Drawing:
    """M2b: the skeleton redrawn at n held poses (phrase cuts, evenly
    thinned); each limb chain is one stroke. spread > 0 unfolds time along
    page x by spread body heights per slice (Marey)."""
    B = view_basis(m, view)
    cuts = phrase_cuts(m, q=0.5, min_gap_s=0.4)
    if len(cuts) < n:
        cuts = np.linspace(0, m.T - 1, n).astype(int)
    fr = cuts[np.linspace(0, len(cuts) - 1, n).astype(int)]
    Hgt = m.height()
    polys, metas = [], []
    for k, f in enumerate(fr):
        dx = np.array([spread * Hgt * k, 0.0])
        for c in chains:
            idx = [m.find(a) for a in CHAINS[c]]
            polys.append(m.pos[f, idx] @ B + dx)
            metas.append({"chain": c, "slice": k, "frame": int(f)})
    return _drawing(polys, metas, size, f"dance:{m.source}:strobe", {"frames": fr.tolist()})


def relative(m: Motion, pairs=(("lhand", "rfoot"), ("rhand", "lfoot")), *, view: str = "front",
             size=(840, 1200), cut: str = "phrase", min_len: float = 0.04) -> Drawing:
    """The path of joint a seen from joint b (p_a − p_b): limb-pair relations
    as single lines, a body-relative frame that already loses the figure."""
    B = view_basis(m, view)
    Hgt = m.height()
    cuts = phrase_cuts(m) if cut == "phrase" else np.zeros(0, int)
    polys, metas = [], []
    for a, b in pairs:
        p3 = m.pos[:, m.find(a)] - m.pos[:, m.find(b)]
        p2 = gaussian_filter1d(p3 @ B, max(0.03 * m.fps, 0.5), axis=0, mode="nearest")
        v, ac = kinematics(p3, m.fps, Hgt)
        for k, (pp, vv, aa) in enumerate(_split((p2, v, ac), cuts)):
            pp, vv, aa = _dedupe(pp, 0.0008 * Hgt, vv, aa)
            if len(pp) >= 3:
                polys.append(pp)
                metas.append({"joint": f"{a}-{b}", "phrase": k, "speed": np.round(vv, 4).tolist(),
                              "acc": np.round(aa, 3).tolist(), "src": m.source})
    return _min_len(_drawing(polys, metas, size, f"dance:{m.source}:relative:{view}"), min_len)


# --- abstraction operators (toward the non-human) ---------------------------

def graft(body: Motion, limbs: Motion, *, take=("lhand", "rhand", "lfoot", "rfoot"), view: str = "front",
          size=(840, 1200), limb_scale: float = 1.0, cut: str = "phrase", min_len: float = 0.04) -> Drawing:
    """M5b/c: dancer `limbs`' effector motion relative to ITS root, carried
    on dancer `body`'s root path (both in body heights, time-truncated to
    the shorter). Two dancers, one impossible trajectory set."""
    T = min(body.T, limbs.T)
    Bb, Bl = view_basis(body, view), view_basis(limbs, view)
    hb, hl = body.height(), limbs.height()
    root_b = body.pos[:T, body.find("root")] @ Bb / hb
    rl = limbs.pos[:T, limbs.find("root")]
    cuts = phrase_cuts(limbs.window(0, T / limbs.fps)) if cut == "phrase" else np.zeros(0, int)
    polys, metas = [], []
    for name in take:
        rel3 = limbs.pos[:T, limbs.find(name)] - rl
        p2 = gaussian_filter1d(root_b + limb_scale * (rel3 @ Bl) / hl, max(0.03 * limbs.fps, 0.5), axis=0,
                               mode="nearest")
        v, a = kinematics(rel3, limbs.fps, hl)
        for k, (pp, vv, aa) in enumerate(_split((p2, v, a), cuts)):
            pp, vv, aa = _dedupe(pp, 0.0008, vv, aa)
            if len(pp) >= 3:
                polys.append(pp)
                metas.append({"joint": name, "phrase": k, "speed": np.round(vv, 4).tolist(),
                              "acc": np.round(aa, 3).tolist(), "src": f"{body.source}+{limbs.source}"})
    return _min_len(_drawing(polys, metas, size, f"dance:graft:{body.source}<{limbs.source}"), min_len)


def pieces_at_minima(d: Drawing, *, min_frac: float = 0.02, q: float = 0.25) -> list[dict]:
    """Cut every trail stroke at its own speed minima (below its q-quantile):
    a list of {points, speed, acc, joint, src} gesture pieces."""
    out = []
    R = d.ref_length()
    for s in d.strokes:
        v = np.asarray(s.meta.get("speed", np.ones(len(s))), float)
        a = np.asarray(s.meta.get("acc", np.zeros(len(s))), float)
        if len(v) != len(s):
            v, a = np.ones(len(s)), np.zeros(len(s))
        thr = np.quantile(v, q)
        loc = np.where((v[1:-1] <= v[:-2]) & (v[1:-1] <= v[2:]) & (v[1:-1] < thr))[0] + 1
        for pp, vv, aa in _split((s.points, v, a), loc):
            L = float(np.sum(np.linalg.norm(np.diff(pp, axis=0), axis=1)))
            if L >= min_frac * R:
                out.append({"points": pp, "speed": vv, "acc": aa, "joint": s.meta.get("joint", ""),
                            "src": s.meta.get("src", d.source), "len": L / R})
    return out


def _heading(p: np.ndarray, back: int = 4, end: bool = True) -> float:
    k = min(back, len(p) - 1)
    d = p[-1] - p[-1 - k] if end else p[k] - p[0]
    return math.atan2(d[1], d[0])


def _rotate(p: np.ndarray, ang: float) -> np.ndarray:
    c, s = math.cos(ang), math.sin(ang)
    return p @ np.array([[c, s], [-s, c]])


def chimera(pieces: list[dict], rng: np.random.Generator, *, n_lines: int = 1, per_line: int = 14,
            defl=(0.5, 1.5), p_reverse: float = 0.4, size=(840, 1200), box: float = 1.0) -> Drawing:
    """M5 "cut and reattach": gesture pieces (from any limbs / dancers)
    chained end to start into n_lines contiguous lines. Each new piece is
    rigidly rotated so it leaves the current end at a SHARP deflection
    (real drawings join at ≈ 1.2 rad, topology-2026-10-16 §2), reversed in
    time with p_reverse (folded time), and steered back toward the origin
    when the line strays beyond `box` × the median piece span."""
    if not pieces:
        return Drawing([], "dance:chimera", tuple(size))
    lens = np.array([max(np.ptp(p["points"], axis=0).max(), 1e-9) for p in pieces])
    unit = float(np.median(lens))
    polys, metas = [], []
    for li in range(n_lines):
        idx = rng.choice(len(pieces), size=min(per_line, len(pieces)), replace=False)
        pts = [np.zeros((1, 2))]
        spd, acc, src = [np.zeros(1)], [np.zeros(1)], []
        head = rng.uniform(-math.pi, math.pi)
        for k in idx:
            pc = pieces[int(k)]
            p = pc["points"] / unit
            v, a = pc["speed"], pc["acc"]
            if rng.random() < p_reverse:
                p, v, a = p[::-1], v[::-1], a[::-1]
            p = p - p[0]
            cur = pts[-1][-1]
            sgn = 1 if rng.random() < 0.5 else -1
            want = head + sgn * rng.uniform(*defl)
            if np.linalg.norm(cur) > box * per_line ** 0.5 * 0.6:      # stray: aim home
                home = math.atan2(-cur[1], -cur[0])
                want = home + rng.normal(0, 0.4)
            p = _rotate(p, want - _heading(p, end=False))
            q = p[1:] + cur
            pts.append(q)
            spd.append(v[1:])
            acc.append(a[1:])
            src.append(f"{pc['src']}:{pc['joint']}")
            head = _heading(np.vstack([cur[None], q]))
        P = np.vstack(pts)
        polys.append(P)
        metas.append({"joint": "chimera", "line": li, "speed": np.round(np.concatenate(spd), 4).tolist(),
                      "acc": np.round(np.concatenate(acc), 3).tolist(), "pieces": src})
    return _drawing(polys, metas, size, "dance:chimera")


def _chain_angles(m: Motion, chain, B: np.ndarray | None = None) -> np.ndarray:
    """(T, K) 3D flexion angles along a chain: angle between bone k and bone
    k−1 (bone 0 vs the up axis), rad. 3D, because projected bone angles flip
    whenever a bone points at the camera (a chord across the sheet)."""
    P = m.pos[:, [m.find(a) for a in chain]]                       # (T, n, 3)
    d = np.diff(P, axis=1)
    d = d / np.maximum(np.linalg.norm(d, axis=-1, keepdims=True), 1e-9)
    up = np.zeros(3)
    up[m.up_axis()] = 1.0
    prev = np.concatenate([np.broadcast_to(up, (d.shape[0], 1, 3)), d[:, :-1]], axis=1)
    c = np.clip(np.sum(prev * d, axis=-1), -1.0, 1.0)
    return gaussian_filter1d(np.arccos(c), max(0.03 * m.fps, 0.5), axis=0, mode="nearest")


def impossible_tree(m: Motion, *, depth: int = 4, branching: int = 2, ratio: float = 0.72, gain: float = 0.3,
                    spread: float = 0.55, lag_s: float = 0.6, view: str = "front", size=(840, 1200),
                    seed: int = 0, trails_of: str = "tips", strobe_n: int = 0, cut: str = "phrase",
                    min_len: float = 0.03, drift: float = 1.0, n_tips: int | None = None) -> Drawing:
    """M5a in the page plane: a branching skeleton (branching^depth tips),
    bone k of every branch bending by the dancer's 3D joint flexion at
    chain depth k (z-scored, × gain rad) (limb chains assigned per branch, each branch lagged by a
    canon offset of up to lag_s seconds), bone length ratio^k. Strokes =
    the trails of its tips (trails_of="tips") or of every node ("nodes"),
    cut at the dancer's phrases; strobe_n > 0 adds the tree itself at
    strobe_n held poses (each bone a stroke from its parent's end → T/L
    junctions)."""
    rng = np.random.default_rng(seed)
    B = view_basis(m, view)
    limbs = ("larm", "rarm", "lleg", "rleg")
    A = {c: _chain_angles(m, CHAINS[c], B) for c in limbs}
    A = {c: (a - np.median(a, axis=0)) / (a.std(axis=0) + 1e-3) for c, a in A.items()}   # z-scored deviations
    T = m.T
    lagmax = int(lag_s * m.fps)
    Hgt = m.height()
    nodes = {(): {"p": np.zeros((T, 2)), "th": np.zeros(T)}}
    level = [()]
    bones = []
    for k in range(depth):
        nxt = []
        for path in level:
            par = nodes[path]
            for b in range(branching):
                ch = path + (b,)
                limb = limbs[int(rng.integers(len(limbs)))]
                lag = int(rng.integers(0, lagmax + 1))
                a_ = A[limb][:, min(k + 1, A[limb].shape[1] - 1)]
                sig = np.concatenate([np.full(lag, a_[0]), a_[:T - lag]]) if lag else a_   # canon delay, no wrap
                base = (b - (branching - 1) / 2) * spread * (1.0 if k else 0.6)
                th = par["th"] + base + gain * sig
                L = ratio ** k
                p = par["p"] + L * np.column_stack([np.sin(th), -np.cos(th)])
                nodes[ch] = {"p": p, "th": th, "limb": limb, "lag": lag, "k": k}
                bones.append((path, ch))
                nxt.append(ch)
        level = nxt
    # carry the whole tree on the dancer's root path (in body heights → tree units)
    root2 = gaussian_filter1d(m.pos[:, m.find("root")] @ B / Hgt, max(0.1 * m.fps, 0.5), axis=0, mode="nearest")
    root2 = (root2 - root2[0]) * drift
    which = level if trails_of == "tips" else [p for p in nodes if p]
    if n_tips is not None and n_tips < len(which):     # all tips together only draw the crown's silhouette
        which = [which[int(i)] for i in sorted(rng.choice(len(which), n_tips, replace=False))]
    cuts = phrase_cuts(m) if cut == "phrase" else np.zeros(0, int)
    polys, metas = [], []
    for path in which:
        p = gaussian_filter1d(nodes[path]["p"] + root2, max(0.03 * m.fps, 0.5), axis=0, mode="nearest")
        v = np.linalg.norm(np.gradient(p, axis=0), axis=1) * m.fps
        a = np.linalg.norm(np.gradient(np.gradient(p, axis=0), axis=0), axis=1) * m.fps ** 2
        for k, (pp, vv, aa) in enumerate(_split((p, v, a), cuts)):
            pp, vv, aa = _dedupe(pp, 0.002, vv, aa)
            if len(pp) >= 3:
                polys.append(pp)
                metas.append({"joint": "tip" + "".join(map(str, path)), "phrase": k,
                              "speed": np.round(vv, 4).tolist(), "acc": np.round(aa, 3).tolist(),
                              "limb": nodes[path].get("limb"), "src": m.source})
    if strobe_n:
        fr = np.linspace(0, T - 1, strobe_n + 2)[1:-1].astype(int)
        for f in fr:
            for par, ch in bones:
                q = np.array([nodes[par]["p"][f], nodes[ch]["p"][f]]) + root2[f]
                q = np.column_stack([np.linspace(q[0, 0], q[1, 0], 12), np.linspace(q[0, 1], q[1, 1], 12)])
                polys.append(q)
                metas.append({"joint": "bone", "frame": int(f), "order": len(ch) - 1})
    d = _drawing(polys, metas, size, f"dance:{m.source}:impossible_tree",
                 {"depth": depth, "branching": branching, "ratio": ratio, "gain": gain})
    return _min_len(d, min_len) if not strobe_n else d


# ---------------------------------------------------------------------------
# regimes from the body
# ---------------------------------------------------------------------------

def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def kinematic_r(speed, acc, *, v_ref: float, a_ref: float, still: float = 0.18, dilate: int = 0) -> np.ndarray:
    """Regime value per point from the body: stillness → mass (2),
    acceleration while not fast → nib (1), speed → wire (0).
    v_ref / a_ref: normalising speeds (e.g. the drawing's 90th percentiles).
    dilate: max-filter the mass term over ±dilate samples so a pause (which
    has almost no arc length) becomes a knot of visible size."""
    vn = np.asarray(speed, float) / max(v_ref, 1e-9)
    an = np.asarray(acc, float) / max(a_ref, 1e-9)
    mass = _smoothstep((still - vn) / (0.6 * still))
    if dilate > 0:
        mass = maximum_filter1d(mass, 2 * dilate + 1, mode="nearest")
    nib = _smoothstep((an - 0.3) / 0.45) * (1 - _smoothstep((vn - 0.75) / 0.35))
    return np.clip(2.0 * mass + nib * (1 - mass), 0.0, 2.0)


def kinematic_samples(d: Drawing, *, step: float = 2.0, still: float = 0.18, dilate_r: float = 0.012,
                      pct: float = 90.0) -> tuple[np.ndarray, np.ndarray]:
    """(points (N, 2) px, r (N,)) along every stroke carrying speed/acc meta,
    resampled at `step` px; the mass term is dilated over ±dilate_r · R of
    arc length."""
    allv = np.concatenate([np.asarray(s.meta["speed"], float) for s in d.strokes if "speed" in s.meta] or [[1.0]])
    alla = np.concatenate([np.asarray(s.meta["acc"], float) for s in d.strokes if "acc" in s.meta] or [[1.0]])
    v_ref, a_ref = np.percentile(allv, pct), np.percentile(alla, pct)
    R = d.ref_length()
    P, Rr = [], []
    for s in d.strokes:
        p = s.points
        if "speed" in s.meta and len(s.meta["speed"]) == len(p):
            v, a = np.asarray(s.meta["speed"], float), np.asarray(s.meta["acc"], float)
        else:
            v, a = np.full(len(p), v_ref), np.zeros(len(p))
        sl = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
        n = max(int(sl[-1] / step), 2)
        t = np.linspace(0, sl[-1], n)
        q = np.column_stack([np.interp(t, sl, p[:, 0]), np.interp(t, sl, p[:, 1])])
        # per arc bin: the slowest / most accelerated original sample in it
        # (a pause sits on ~one arc position and must not be interpolated away)
        b = np.clip(np.round(sl / max(sl[-1], 1e-9) * (n - 1)).astype(int), 0, n - 1)
        vmin = np.interp(t, sl, v)
        amax = np.interp(t, sl, a)
        np.minimum.at(vmin, b, v)
        np.maximum.at(amax, b, a)
        aa = amax
        dil = max(int(dilate_r * R / step), 0)
        P.append(q)
        Rr.append(kinematic_r(vmin, aa, v_ref=v_ref, a_ref=a_ref, still=still, dilate=dil))
    return np.vstack(P), np.concatenate(Rr)


def kinematic_field(d: Drawing, *, background: float = 0.0, reach: float = 0.02, **kw):
    """A regime_field.Field whose value at a point is the kinematic regime of
    the nearest structure sample (stillness → mass, acceleration → nib,
    speed → wire), fading to `background` beyond `reach` sheet widths."""
    from scipy.spatial import cKDTree
    from .regime_field import Field
    P, r = kinematic_samples(d, **kw)
    tree = cKDTree(P)
    W, H = d.size

    def fn(u):
        q = np.asarray(u, float) * np.array([W, H], float)
        dist, i = tree.query(q)
        w = np.exp(-(dist / max(reach * W, 1e-9)) ** 2)
        return background + (r[i] - background) * w

    return Field(fn, "kinematic", H / W, {"family": "dance", "share_mass": float(np.mean(r >= 1.5)),
                                         "share_nib": float(np.mean((r >= 0.5) & (r < 1.5)))})
