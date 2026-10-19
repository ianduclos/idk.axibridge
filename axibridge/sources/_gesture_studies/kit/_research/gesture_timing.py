# FROZEN from research commit 9ab70ac: tools/gesture/gesture/gesture_timing.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Gesture timing → line texture: the dance corpus as DYNAMICS, not geometry.

results/gesture_timing-2026-10-16.md. The line hands are geometry only; the
mocap corpus (.local/gesture/corpus/dance/: CMU 05/49/55 ASF+AMC, E2-Create
BVH) has time. This module

1. parses BVH and ASF/AMC and runs forward kinematics (numpy only)
   → `Motion` (joint positions in cm, fps, up axis);
2. measures an end-effector trail: speed, acceleration, jerk, pauses, 3-D and
   drawing-plane curvature, and the two-thirds power law v ∝ κ^(−β), β ≈ 1/3
   (`kinematics`, `pauses`, `power_law`);
3. measures what can stand in for time in the static corpora: width against
   curvature (and, for broad-nib sheets, the residual of the nib law against
   curvature) along extracted strokes (`width_samples_k`, `width_curvature`);
4. maps a dancer's timing onto any centreline (`Timing`, `timing_from_motion`,
   `ink_profile`, `danced_strokes`): the pen travels the line at the
   dancer's speed and ink is deposited per unit TIME, so

     dwell (stillness)  → ink pools → r → 2: a mass, diameter ∝ √(dwell)
     steady flow        → nib ribbon, nib angle held by the dancer's wrist
     fast               → dry monoline (r → 0)
     high-frequency     → the effector's own lateral micro-motion becomes the
       residual            line's tremor (not synthetic noise)
     bursts (jerk peaks → line events (gesture.signs.apply_events): the sign
       after stillness)    grows where the body jolted

Coordinates of generated marks follow the README contract (px or mm, y down);
mocap is cm, y up. Pure and deterministic; nothing here mutates its inputs.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d

__all__ = ["Motion", "parse_bvh", "parse_asf", "parse_amc", "load_motion", "EFFECTORS",
           "kinematics", "pauses", "power_law", "segment_power_law", "drawing_plane",
           "width_samples_k", "width_curvature", "Timing", "timing_from_motion",
           "ink_profile", "line_profiles", "danced_strokes", "bursts"]


# ---------------------------------------------------------------------------
# rotations
# ---------------------------------------------------------------------------

def _rot(axis: str, deg: np.ndarray) -> np.ndarray:
    """(T, 3, 3) rotation about a principal axis, angles in degrees."""
    a = np.deg2rad(np.asarray(deg, dtype=np.float64))
    c, s = np.cos(a), np.sin(a)
    o, z = np.ones_like(a), np.zeros_like(a)
    if axis == "X":
        m = [[o, z, z], [z, c, -s], [z, s, c]]
    elif axis == "Y":
        m = [[c, z, s], [z, o, z], [-s, z, c]]
    elif axis == "Z":
        m = [[c, -s, z], [s, c, z], [z, z, o]]
    else:
        raise ValueError(axis)
    return np.moveaxis(np.array(m), (0, 1), (-2, -1))


# ---------------------------------------------------------------------------
# motion container
# ---------------------------------------------------------------------------

@dataclass
class Motion:
    names: list[str]
    parents: list[int]
    pos: np.ndarray              # (T, J, 3) world positions, cm
    fps: float
    source: str = ""
    rot: dict = field(default_factory=dict)     # name → (T, 3, 3) global rotation (kept joints only)
    up: int = 1

    def __post_init__(self):
        self.up = _up_axis(self)

    @property
    def T(self) -> int:
        return self.pos.shape[0]

    def index(self, name: str) -> int:
        return self.names.index(name)

    def joint(self, name: str) -> np.ndarray:
        return self.pos[:, self.index(name)].copy()

    def duration(self) -> float:
        return self.T / self.fps


def _up_axis(m: Motion) -> int:
    """Axis along which the head sits highest above the lowest joints."""
    hi = [i for i, n in enumerate(m.names) if n.lower() in ("head", "upperneck", "neck")]
    if not hi:
        return 1
    h = m.pos[:, hi[0]]
    lo = m.pos.min(axis=1)
    d = np.mean(h - lo, axis=0)
    return int(np.argmax(d))


# --- BVH -------------------------------------------------------------------

def parse_bvh(path, *, max_frames: int | None = None, start: int = 0, stride: int = 1,
              keep_rot: tuple[str, ...] = ()) -> Motion:
    """BVH → Motion. Local transform = translate(position channels, else
    OFFSET) · R(ch1)·R(ch2)·R(ch3) in channel order; End Sites become joints
    named '<parent>_end'. Frames [start, start + max_frames) every `stride`."""
    lines = Path(path).read_text().splitlines()
    names, parents, offsets, chans = [], [], [], []
    stack: list[int] = []
    i = 0
    pending = None
    while i < len(lines):
        t = lines[i].split()
        i += 1
        if not t:
            continue
        k = t[0]
        if k in ("ROOT", "JOINT"):
            pending = t[1]
        elif k == "End":
            pending = names[stack[-1]] + "_end"
        elif k == "{":
            names.append(pending)
            parents.append(stack[-1] if stack else -1)
            offsets.append(np.zeros(3))
            chans.append([])
            stack.append(len(names) - 1)
        elif k == "}":
            stack.pop()
        elif k == "OFFSET":
            offsets[stack[-1]] = np.array([float(x) for x in t[1:4]])
        elif k == "CHANNELS":
            chans[stack[-1]] = t[2:2 + int(t[1])]
        elif k == "MOTION":
            break
    nfr = int(lines[i].split(":")[1])
    ft = float(lines[i + 1].split(":")[1])
    body = lines[i + 2:i + 2 + nfr]
    stop = len(body) if max_frames is None else min(len(body), start + max_frames * stride)
    sel = body[start:stop:stride]
    data = np.array(" ".join(sel).split(), dtype=np.float64)
    nch = sum(len(c) for c in chans)
    data = data.reshape(len(sel), nch)
    T, J = len(sel), len(names)
    pos = np.zeros((T, J, 3))
    G = np.zeros((J, T, 3, 3))
    col = 0
    for j in range(J):
        ch = chans[j]
        v = data[:, col:col + len(ch)]
        col += len(ch)
        t_loc = np.broadcast_to(offsets[j], (T, 3)).copy()
        R = np.broadcast_to(np.eye(3), (T, 3, 3)).copy()
        for c, name in enumerate(ch):
            if name.endswith("position"):
                t_loc[:, "XYZ".index(name[0])] = v[:, c]
            elif name.endswith("rotation"):
                R = R @ _rot(name[0], v[:, c])
        p = parents[j]
        if p < 0:
            pos[:, j] = t_loc
            G[j] = R
        else:
            pos[:, j] = pos[:, p] + np.einsum("tij,tj->ti", G[p], t_loc)
            G[j] = G[p] @ R
    rot = {n: G[names.index(n)].copy() for n in keep_rot if n in names}
    return Motion(names, parents, pos, fps=1.0 / (ft * stride), source=str(path), rot=rot)


# --- ASF / AMC ---------------------------------------------------------------

def parse_asf(path) -> dict:
    """ASF skeleton → {'length': unit, 'root_order', 'bones': {name: {...}},
    'children': {name: [..]}}. Bone: direction (3,), length, axis (deg, 3),
    axis_order, dof list."""
    txt = Path(path).read_text().splitlines()
    out = {"length": 1.0, "root_order": ["TX", "TY", "TZ", "RX", "RY", "RZ"], "root_axis": "XYZ",
           "bones": {}, "children": {}}
    sec = None
    cur = None
    for raw in txt:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(":"):
            sec = line.split()[0]
            continue
        t = line.split()
        if sec == ":units" and t[0] == "length":
            out["length"] = float(t[1])
        elif sec == ":root":
            if t[0] == "order":
                out["root_order"] = t[1:]
            elif t[0] == "axis":
                out["root_axis"] = t[1]
        elif sec == ":bonedata":
            if t[0] == "begin":
                cur = {"dof": [], "axis": np.zeros(3), "axis_order": "XYZ", "direction": np.zeros(3), "length": 0.0}
            elif t[0] == "end":
                out["bones"][cur["name"]] = cur
            elif t[0] == "name":
                cur["name"] = t[1]
            elif t[0] == "direction":
                cur["direction"] = np.array([float(x) for x in t[1:4]])
            elif t[0] == "length":
                cur["length"] = float(t[1])
            elif t[0] == "axis":
                cur["axis"] = np.array([float(x) for x in t[1:4]])
                cur["axis_order"] = t[4] if len(t) > 4 else "XYZ"
            elif t[0] == "dof":
                cur["dof"] = t[1:]
        elif sec == ":hierarchy":
            if t[0] in ("begin", "end"):
                continue
            out["children"].setdefault(t[0], []).extend(t[1:])
    return out


def _euler(order: str, angles: np.ndarray) -> np.ndarray:
    """Acclaim convention: angles (T, 3) in x, y, z; 'XYZ' applies X first,
    i.e. R = Rz·Ry·Rx."""
    a = np.atleast_2d(angles)
    R = np.broadcast_to(np.eye(3), (len(a), 3, 3)).copy()
    for ax in order:                                  # X first → leftmost multiply later
        R = _rot(ax, a[:, "XYZ".index(ax)]) @ R
    return R


def parse_amc(path, asf: dict, *, max_frames: int | None = None, start: int = 0, stride: int = 1,
              fps: float = 120.0, keep_rot: tuple[str, ...] = ()) -> Motion:
    """AMC frames + ASF skeleton → Motion (positions at each bone's END,
    plus 'root'; units converted to cm: ASF length unit → inches → cm)."""
    bones = asf["bones"]
    frames: list[dict] = []
    cur = None
    with open(path) as f:
        for raw in f:
            s = raw.strip()
            if not s or s.startswith("#") or s.startswith(":"):
                continue
            if s.isdigit():
                cur = {}
                frames.append(cur)
                continue
            t = s.split()
            cur[t[0]] = [float(x) for x in t[1:]]
    stop = len(frames) if max_frames is None else min(len(frames), start + max_frames * stride)
    frames = frames[start:stop:stride]
    T = len(frames)
    k = 2.54 / asf["length"]                          # ASF units → cm
    names, parents = ["root"], [-1]
    order = []

    def walk(n, p):
        for c in asf["children"].get(n, []):
            names.append(c)
            parents.append(p)
            order.append(c)
            walk(c, len(names) - 1)
    walk("root", 0)
    J = len(names)
    pos = np.zeros((T, J, 3))
    G = np.zeros((J, T, 3, 3))
    rv = np.array([fr["root"] for fr in frames])
    ro = asf["root_order"]
    pos[:, 0] = np.column_stack([rv[:, ro.index(c)] for c in ("TX", "TY", "TZ")]) * k
    rang = np.column_stack([rv[:, ro.index(c)] for c in ("RX", "RY", "RZ")])
    G[0] = _euler(asf["root_axis"], rang)
    for j in range(1, J):
        b = bones[names[j]]
        C = _euler(b["axis_order"], b["axis"][None])[0]
        ang = np.zeros((T, 3))
        for c_i, d in enumerate(b["dof"]):
            ax = "xyz".index(d[1])
            ang[:, ax] = [fr.get(names[j], [0.0] * len(b["dof"]))[c_i] for fr in frames]
        M = _euler("XYZ", ang)
        L = C @ M @ C.T
        p = parents[j]
        G[j] = G[p] @ L
        pos[:, j] = pos[:, p] + np.einsum("tij,j->ti", G[j], b["direction"] * b["length"] * k)
    rot = {n: G[names.index(n)].copy() for n in keep_rot if n in names}
    return Motion(names, parents, pos, fps=fps / stride, source=str(path), rot=rot)


def load_motion(path, **kw) -> Motion:
    """BVH or AMC (the ASF is the single *.asf in the same folder)."""
    p = Path(path)
    if p.suffix.lower() == ".bvh":
        return parse_bvh(p, **kw)
    asfs = sorted(p.parent.glob("*.asf"))
    return parse_amc(p, parse_asf(asfs[0]), **kw)


# End effectors per skeleton family: (effector, palm-axis a, palm-axis b) — the
# palm axis (index knuckle → pinky knuckle, or thumb tip → finger tip) is the
# "nib edge" a dancer's hand would hold.
EFFECTORS = {
    "bvh": {"rhand": ("RightHand", "RightHandIndex1", "RightHandPinky1"),
            "lhand": ("LeftHand", "LeftHandIndex1", "LeftHandPinky1"),
            "head": ("Head", None, None), "rfoot": ("RightToeBase", None, None),
            "lfoot": ("LeftToeBase", None, None)},
    "amc": {"rhand": ("rhand", "rthumb", "rfingers"), "lhand": ("lhand", "lthumb", "lfingers"),
            "head": ("head", None, None), "rfoot": ("rtoes", None, None), "lfoot": ("ltoes", None, None)},
}


def _family(m: Motion) -> str:
    return "bvh" if m.source.lower().endswith(".bvh") else "amc"


# ---------------------------------------------------------------------------
# kinematics of a trail
# ---------------------------------------------------------------------------

def kinematics(trail: np.ndarray, fps: float, sigma_s: float = 0.03) -> dict:
    """Speed, acceleration, jerk and curvature of a (T, D) trail (cm), after
    Gaussian smoothing in time at σ = sigma_s seconds (explicit, as the
    README asks of every curvature). κ = |v × a| / |v|³ (any D ≥ 2)."""
    x = np.asarray(trail, dtype=np.float64)
    sd = max(sigma_s * fps, 0.0)
    xs = gaussian_filter1d(x, sd, axis=0, mode="nearest") if sd > 0 else x.copy()
    dt = 1.0 / fps
    v = np.gradient(xs, dt, axis=0)
    a = np.gradient(v, dt, axis=0)
    j = np.gradient(a, dt, axis=0)
    sp = np.linalg.norm(v, axis=1)
    vv = np.einsum("ij,ij->i", v, v)
    aa = np.einsum("ij,ij->i", a, a)
    va = np.einsum("ij,ij->i", v, a)
    cross = np.sqrt(np.maximum(vv * aa - va ** 2, 0.0))
    kappa = cross / np.maximum(sp, 1e-9) ** 3
    at = va / np.maximum(sp, 1e-9)                       # tangential acceleration
    return {"x": xs, "t": np.arange(len(x)) * dt, "v": v, "speed": sp, "acc": np.sqrt(aa), "acc_t": at,
            "jerk": np.linalg.norm(j, axis=1), "kappa": kappa,
            "dist": np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(xs, axis=0), axis=1))])}


def pauses(speed: np.ndarray, fps: float, *, rel: float = 0.08, floor: float = 2.0,
           min_dur: float = 0.12) -> tuple[np.ndarray, list[tuple[int, int]], float]:
    """Stillness: speed below max(rel · p95(speed), floor cm/s) for at least
    min_dur seconds. Returns (mask, [(i0, i1)], threshold)."""
    thr = max(rel * float(np.percentile(speed, 95)), floor)
    below = speed < thr
    runs, i = [], 0
    n = len(speed)
    while i < n:
        if below[i]:
            j = i
            while j < n and below[j]:
                j += 1
            if (j - i) / fps >= min_dur:
                runs.append((i, j))
            i = j
        else:
            i += 1
    mask = np.zeros(n, bool)
    for a, b in runs:
        mask[a:b] = True
    return mask, runs, thr


def power_law(speed: np.ndarray, kappa: np.ndarray, mask: np.ndarray | None = None, *,
              r_min: float = 1.0, r_max: float = 300.0) -> dict:
    """OLS of log v on log κ (v ∝ κ^slope; the two-thirds law predicts
    slope = −1/3). Samples: moving (mask), radius of curvature within
    [r_min, r_max] cm."""
    ok = np.isfinite(kappa) & (kappa > 1.0 / r_max) & (kappa < 1.0 / r_min) & (speed > 0)
    if mask is not None:
        ok &= mask
    if ok.sum() < 20:
        return {"slope": float("nan"), "r2": float("nan"), "n": int(ok.sum())}
    lx, ly = np.log(kappa[ok]), np.log(speed[ok])
    A = np.column_stack([lx, np.ones_like(lx)])
    coef, *_ = np.linalg.lstsq(A, ly, rcond=None)
    res = ly - A @ coef
    r2 = 1.0 - res.var() / max(ly.var(), 1e-12)
    return {"slope": float(coef[0]), "intercept": float(coef[1]), "r2": float(r2), "n": int(ok.sum())}


def segment_power_law(speed, kappa, fps, *, min_dur: float = 0.25, **kw) -> dict:
    """The law per movement unit (between speed minima, each ≥ min_dur s),
    since the velocity gain factor changes between units. Median slope /
    R² over units with ≥ 20 usable samples."""
    sm = gaussian_filter1d(speed, 0.05 * fps)
    mins = np.where((sm[1:-1] < sm[:-2]) & (sm[1:-1] <= sm[2:]))[0] + 1
    cuts = [0]
    for m in mins:
        if (m - cuts[-1]) / fps >= min_dur:
            cuts.append(int(m))
    cuts.append(len(speed))
    res = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        r = power_law(speed[a:b], kappa[a:b], **kw)
        if r["n"] >= 20 and np.isfinite(r["slope"]):
            res.append(r)
    if not res:
        return {"slope": float("nan"), "r2": float("nan"), "units": 0}
    return {"slope": float(np.median([r["slope"] for r in res])),
            "slope_iqr": [float(np.percentile([r["slope"] for r in res], q)) for q in (25, 75)],
            "r2": float(np.median([r["r2"] for r in res])), "units": len(res)}


def drawing_plane(trail: np.ndarray, up: int) -> tuple[np.ndarray, np.ndarray]:
    """Project a 3-D trail onto the vertical plane that holds most of its
    horizontal motion (the 'wall' the gesture draws on). Returns ((T, 2) px-like
    coords, x right / y DOWN, cm), and the 3×2 basis."""
    x = np.asarray(trail, float)
    hz = [i for i in range(3) if i != up]
    h = x[:, hz] - x[:, hz].mean(0)
    w, V = np.linalg.eigh(h.T @ h)
    d = V[:, -1]                                     # main horizontal direction
    e1 = np.zeros(3)
    e1[hz[0]], e1[hz[1]] = d
    e2 = np.zeros(3)
    e2[up] = -1.0                                    # y down
    B = np.column_stack([e1, e2])
    return x @ B, B


# ---------------------------------------------------------------------------
# static stand-ins for time: width vs curvature along drawn strokes
# ---------------------------------------------------------------------------

def width_samples_k(stroke, *, w_ref: float | None = None, sigma_w: float = 1.0, coarse_w: float = 4.0,
                    trim_w: float = 1.5, max_kw: float = 0.35, step_w: float = 0.5) -> dict:
    """Per-sample (θ, width, κ at σ = sigma_w·w, κ at the coarse 'movement'
    scale σ = coarse_w·w, s, end distance) along a stroke with widths.
    Same exclusions as broadnib.width_samples (terminals, junctions, the
    fold zone |κ|·w > max_kw where the swept band's width is geometric, not
    inked) — so any κ–width relation left is not the fold artefact."""
    from .broadnib import _resample  # noqa: PLC0415  (private helper reused read-only)
    empty = {k: np.zeros(0) for k in ("theta", "width", "k_fine", "k_coarse", "s", "end_d")}
    if stroke.width is None or len(stroke) < 4:
        return empty
    p = np.asarray(stroke.points, float)
    wv = np.asarray(stroke.width, float)
    if stroke.closed:
        p, wv = np.vstack([p, p[:1]]), np.concatenate([wv, wv[:1]])
    w = max(float(w_ref if w_ref is not None else np.median(wv)), 1e-6)
    step = max(step_w * w, 0.5)
    q, ww, s = _resample(p, step, wv)
    if len(q) < 8:
        return empty
    mode = "wrap" if stroke.closed else "nearest"

    def kap(sig):
        sd = sig / step
        qs = np.column_stack([gaussian_filter1d(q[:, 0], sd, mode=mode), gaussian_filter1d(q[:, 1], sd, mode=mode)])
        d1 = np.gradient(qs, axis=0) / step
        d2 = np.gradient(d1, axis=0) / step
        sp = np.linalg.norm(d1, axis=1) + 1e-12
        return (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / sp ** 3, d1
    kf, d1 = kap(sigma_w * w)
    kc, _ = kap(coarse_w * w)
    theta = np.arctan2(-d1[:, 1], d1[:, 0])
    keep = np.isfinite(ww) & (ww > 0) & (np.abs(kf) * w <= max_kw)
    end_d = np.minimum(s, s[-1] - s) if not stroke.closed else np.full(len(s), np.inf)
    if not stroke.closed:
        keep &= (s >= trim_w * w) & (s <= s[-1] - trim_w * w)
    js = stroke.meta.get("junctions", []) if isinstance(stroke.meta, dict) else []
    if js:
        Jp = np.asarray(js, float).reshape(-1, 2)
        dmin = np.min(np.linalg.norm(q[:, None, :] - Jp[None], axis=2), axis=1)
        keep &= dmin > 1.5 * np.maximum(ww, w)
    return {"theta": theta[keep], "width": ww[keep] / w, "k_fine": np.abs(kf[keep]) * w,
            "k_coarse": np.abs(kc[keep]) * w, "s": s[keep], "end_d": end_d[keep] / w}


def _spearman(a, b) -> float:
    if len(a) < 10:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def width_curvature(drawings, *, min_len_w: float = 12.0, nib: bool = False, coarse_w: float = 4.0) -> dict:
    """Is there a speed-like signal in drawn widths? Pools strokes of several
    drawings. Width is normalised per STROKE (log w − median log w of that
    stroke), so pressure/tool changes between strokes drop out. Reports the
    Spearman ρ of that residual with |κ|·w at the fine and the coarse
    (movement) scale, the slope of log-width on log-κ (two-thirds-law reading:
    thick where slow ⇒ ρ > 0, slope ≈ +1/3 if ink ∝ dwell ∝ 1/v), and the
    width near stroke ends vs interior. nib=True first divides out a per-sheet
    broad-nib fit W·|sin(θ−φ)| + w_min (broadnib.fit_nib), so direction is
    removed before curvature is asked."""
    from . import broadnib as bn  # noqa: PLC0415
    R, KF, KC, ED = [], [], [], []
    nib_r2 = []
    for d in drawings:
        ws = [float(np.median(st.width)) for st in d.strokes if st.width is not None and len(st.width)]
        if not ws:
            continue
        w_med = float(np.median(ws))
        smp = [width_samples_k(st, coarse_w=coarse_w) for st in d.strokes
               if st.width is not None and st.length() >= min_len_w * w_med]
        smp = [x for x in smp if len(x["width"]) >= 10]
        if not smp:
            continue
        if nib:
            th = np.concatenate([x["theta"] for x in smp])
            wi = np.concatenate([x["width"] for x in smp])
            f = bn.fit_nib(th, wi)
            if not np.isfinite(f.phi):
                continue
            nib_r2.append(f.r2)
        for x in smp:
            lw = np.log(x["width"])
            if nib:
                mw = bn.nib_width(x["theta"], f.phi, f.W, f.w_min)
                lw = lw - np.log(np.maximum(mw, 1e-3))
            R.append(lw - np.median(lw))
            KF.append(x["k_fine"])
            KC.append(x["k_coarse"])
            ED.append(x["end_d"])
    if not R:
        return {"n": 0}
    r, kf, kc, ed = (np.concatenate(v) for v in (R, KF, KC, ED))
    ok = kc > 1e-4
    A = np.column_stack([np.log(kc[ok]), np.ones(ok.sum())])
    slope = float(np.linalg.lstsq(A, r[ok], rcond=None)[0][0])
    q = np.quantile(kc, [0.2, 0.8])
    near_end = ed < 4.0
    return {"n": int(len(r)), "rho_fine": _spearman(r, kf), "rho_coarse": _spearman(r, kc),
            "slope_logw_logk": slope,
            "w_ratio_bend_vs_straight": float(np.exp(np.median(r[kc >= q[1]]) - np.median(r[kc <= q[0]]))),
            "w_ratio_end_vs_interior": float(np.exp(np.median(r[near_end]) - np.median(r[~near_end])))
            if near_end.any() and (~near_end).any() else float("nan"),
            "nib_r2": float(np.median(nib_r2)) if nib_r2 else None, "samples": (r, kc)}


# ---------------------------------------------------------------------------
# timing → line
# ---------------------------------------------------------------------------

@dataclass
class Timing:
    """A dancer's timing over a window: per-frame speed, wrist (nib) angle,
    high-frequency lateral residual and pauses. Time is the only axis;
    geometry of the dance is dropped (except the residual's lateral sign)."""
    t: np.ndarray            # (T,) s
    speed: np.ndarray        # (T,) cm/s (smoothed)
    phi: np.ndarray          # (T,) rad, nib edge angle in the drawing plane, [0, π)
    jitter: np.ndarray       # (T,) cm, signed lateral high-pass residual
    jerk: np.ndarray         # (T,) cm/s³
    pause: np.ndarray        # (T,) bool
    label: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def fps(self) -> float:
        return 1.0 / float(self.t[1] - self.t[0])

    def n_pauses(self) -> int:
        """Stillness runs inside this window."""
        p = self.pause.astype(int)
        return int(np.sum(np.diff(np.concatenate([[0], p])) == 1))

    def window(self, t0: float, dur: float) -> "Timing":
        i0 = int(round(t0 * self.fps))
        i1 = min(len(self.t), i0 + int(round(dur * self.fps)))
        sl = slice(i0, i1)
        return replace(self, t=self.t[sl] - self.t[i0], speed=self.speed[sl], phi=self.phi[sl],
                       jitter=self.jitter[sl], jerk=self.jerk[sl], pause=self.pause[sl],
                       meta={**self.meta, "t0": t0})


def timing_from_motion(m: Motion, effector: str = "rhand", *, sigma_s: float = 0.03, hp_s: float = 0.15,
                       label: str = "") -> Timing:
    """Timing of one end effector. φ: the palm axis (EFFECTORS) projected on
    the drawing plane; if the skeleton has no palm axis, the direction of
    travel (a nib that follows the hand). jitter: trail minus its σ = hp_s
    smoothing, component normal to the motion in the drawing plane."""
    fam = _family(m)
    eff, pa, pb = EFFECTORS[fam][effector]
    x = m.joint(eff)
    k = kinematics(x, m.fps, sigma_s)
    mask, runs, thr = pauses(k["speed"], m.fps)
    p2, B = drawing_plane(x, m.up)
    if pa is not None and pa in m.names and pb in m.names:
        ax = (m.joint(pb) - m.joint(pa)) @ B
    else:
        ax = np.gradient(gaussian_filter1d(p2, 0.1 * m.fps, axis=0, mode="nearest"), axis=0)
    ax = gaussian_filter1d(ax, sigma_s * m.fps, axis=0, mode="nearest")
    phi = np.mod(np.arctan2(-ax[:, 1], ax[:, 0]), np.pi)           # page angle, y down → CCW as seen
    lo = gaussian_filter1d(p2, hp_s * m.fps, axis=0, mode="nearest")
    hp = gaussian_filter1d(p2, 0.5 * sigma_s * m.fps, axis=0, mode="nearest") - lo
    tg = np.gradient(lo, axis=0)
    tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
    nrm = np.column_stack([-tg[:, 1], tg[:, 0]])
    jit = np.einsum("ij,ij->i", hp, nrm)
    return Timing(k["t"], k["speed"], phi, jit, k["jerk"], mask, label=label or Path(m.source).stem,
                  meta={"pause_thr": thr, "n_pauses": len(runs), "effector": eff, "fps": m.fps})


def _unwrap_pi(phi: np.ndarray) -> np.ndarray:
    """Unwrap an axial angle (period π) for interpolation."""
    return np.unwrap(2 * phi) / 2


def ink_profile(tm: Timing, s_grid: np.ndarray, *, sigma_ink: float, v_floor: float = 0.5) -> dict:
    """The pen travels a line of length L = s_grid[-1] in the window's time,
    at a speed ∝ the dancer's (with a crawl floor v_floor cm/s so stillness
    still advances a little). Every frame deposits the same ink at the pen's
    position, spread by a Gaussian of σ = sigma_ink (capillarity); returns
    ink per unit length normalised by its median (q), the time at each s,
    and per-s interpolations of φ, jitter, jerk, pause."""
    sp = np.maximum(tm.speed, v_floor)
    dist = np.concatenate([[0.0], np.cumsum(0.5 * (sp[1:] + sp[:-1]) / tm.fps)])
    L = float(s_grid[-1])
    s_t = dist / max(dist[-1], 1e-9) * L                      # pen position per frame
    step = float(np.median(np.diff(s_grid)))
    hist = np.bincount(np.clip(np.round(s_t / step).astype(int), 0, len(s_grid) - 1),
                       minlength=len(s_grid)).astype(float)
    ink = gaussian_filter1d(hist, sigma_ink / step, mode="nearest")
    q = ink / max(float(np.median(ink)), 1e-12)
    t_s = np.interp(s_grid, s_t, tm.t)
    tt = tm.t
    return {"q": q, "t": t_s, "phi": np.mod(np.interp(t_s, tt, _unwrap_pi(tm.phi)), np.pi),
            "jitter": np.interp(t_s, tt, tm.jitter), "jerk": np.interp(t_s, tt, tm.jerk),
            "pause": np.interp(t_s, tt, tm.pause.astype(float)) > 0.5,
            "speed": np.interp(t_s, tt, tm.speed), "s_t": s_t}


def bursts(tm: Timing, *, q: float = 0.97, min_gap_s: float = 0.6, after_pause_s: float = 0.6,
           n_max: int = 8) -> list[int]:
    """Frame indices of bursts: jerk peaks above its q-quantile, at least
    min_gap_s apart, preferring those within after_pause_s of a stillness
    (the jolt out of stillness). Largest first, at most n_max."""
    j = gaussian_filter1d(tm.jerk, 0.02 * tm.fps)
    thr = np.quantile(j, q)
    pk = np.where((j[1:-1] > j[:-2]) & (j[1:-1] >= j[2:]) & (j[1:-1] > thr))[0] + 1
    if not len(pk):
        return []
    pz = np.where(tm.pause)[0]
    gap = int(after_pause_s * tm.fps)

    def score(i):
        near = bool(len(pz)) and np.min(np.abs(pz - i)) <= gap
        return j[i] * (2.0 if near else 1.0)
    order = sorted(pk, key=score, reverse=True)
    out: list[int] = []
    for i in order:
        if all(abs(i - o) >= min_gap_s * tm.fps for o in out):
            out.append(int(i))
        if len(out) >= n_max:
            break
    return out


def line_profiles(tm: Timing, s_grid: np.ndarray, *, W: float, shape_w: float, pen: float,
                  q_line: float = 1.0, q_mass: float = 6.0, jitter_gain: float = 1.0,
                  sigma_ink: float | None = None, nib_from: str = "wrist", phi_fixed: float = math.radians(60)):
    """Per-s line properties from timing (see module docstring).
    r(s): 0 at q ≤ q_line, 2 at q ≥ q_mass, log-linear between (q = ink per
    length / median). mass(s): shape_w·√(q / q_mass) (area ∝ dwell),
    floored at the nib. phi: the wrist ('wrist'), fixed ('fixed'), or
    'travel'. jitter: lateral offset (same units as s) = jitter_gain × the
    dancer's residual rescaled so its p95 is one pen width."""
    sig = sigma_ink if sigma_ink is not None else 0.6 * W
    ip = ink_profile(tm, s_grid, sigma_ink=sig)
    lq = np.log(np.maximum(ip["q"], 1e-6))
    r = np.clip(2.0 * (lq - math.log(q_line)) / (math.log(q_mass) - math.log(q_line)), 0.0, 2.0)
    mass = np.maximum(shape_w * np.sqrt(np.maximum(ip["q"], 0) / q_mass), W)
    mass = np.minimum(mass, 1.6 * shape_w)
    if nib_from == "wrist":
        phi = ip["phi"]
    elif nib_from == "travel":
        phi = None
    else:
        phi = np.full(len(s_grid), phi_fixed)
    j = ip["jitter"]
    sc = np.percentile(np.abs(tm.jitter), 95) + 1e-9
    jit = jitter_gain * pen * j / sc
    return {"r": r, "mass": mass, "phi": phi, "jitter": jit, **{k: ip[k] for k in ("q", "t", "pause", "speed")}}


def _resample_line(p: np.ndarray, step: float) -> np.ndarray:
    from .curvature import resample  # noqa: PLC0415
    return resample(np.asarray(p, float), step)


def danced_strokes(lines, tm: Timing, *, W: float, shape_w: float, pen: float, step: float | None = None,
                   jitter_gain: float = 1.0, nib_from: str = "wrist", q_line: float = 1.0, q_mass: float = 6.0,
                   phi_fixed: float = math.radians(60), events: bool = True, rng=None, n_events: int = 6,
                   sigma_ink: float | None = None, burst_ops: tuple = ("comb", "drip", "knot", "nib")):
    """RegimeStrokes for `lines` drawn in sequence through one dance window:
    the lines' total length is mapped onto the window by ink_profile (so a
    long line gets a long stretch of the dance), r(s)/mass/φ/tremor from
    line_profiles, and bursts → interior line events (signs.apply_events) at
    the burst's s. Returns (strokes, info)."""
    from . import regime as rg  # noqa: PLC0415
    step = step or max(W / 4.0, 0.05)
    arrs = [_resample_line(np.asarray(q, float), step) for q in lines if len(q) >= 2]
    lens = [float(np.sum(np.linalg.norm(np.diff(a, axis=0), axis=1))) for a in arrs]
    Ltot = sum(lens)
    n = max(int(round(Ltot / step)), 2)
    s_grid = np.linspace(0, Ltot, n + 1)
    pr = line_profiles(tm, s_grid, W=W, shape_w=shape_w, pen=pen, q_line=q_line, q_mass=q_mass,
                       jitter_gain=jitter_gain, nib_from=nib_from, phi_fixed=phi_fixed, sigma_ink=sigma_ink)
    strokes, off = [], 0.0
    cuts = []
    for a, L in zip(arrs, lens):
        sl = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(a, axis=0), axis=1))])
        sg = sl + off
        r = np.interp(sg, s_grid, pr["r"])
        ms = np.interp(sg, s_grid, pr["mass"])
        jit = np.interp(sg, s_grid, pr["jitter"])
        tg = np.gradient(a, axis=0)
        tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
        nrm = np.column_stack([-tg[:, 1], tg[:, 0]])
        pts = a + nrm * jit[:, None]
        if pr["phi"] is None:
            phi = np.mod(np.arctan2(-tg[:, 1], tg[:, 0]) + math.pi / 2, math.pi)
        else:
            phi = np.mod(np.interp(sg, s_grid, _unwrap_pi(pr["phi"])), np.pi)
        strokes.append(rg.make(pts, r, phi=phi, W=W, mass=ms, meta={"t0": float(np.interp(off, s_grid, pr["t"]))}))
        cuts.append((off, off + L))
        off += L
    info = {"profiles": pr, "s_grid": s_grid, "cuts": cuts, "events": []}
    if events:
        from . import signs  # noqa: PLC0415
        rng = rng if rng is not None else np.random.default_rng(0)
        bs = bursts(tm, n_max=n_events)
        evs = []
        ops = burst_ops
        for k_, fi in enumerate(bs):
            t_b = tm.t[fi]
            s_b = float(np.interp(t_b, pr["t"], s_grid))
            li = int(np.searchsorted([c[1] for c in cuts], s_b))
            li = min(li, len(cuts) - 1)
            s_loc = s_b - cuts[li][0]
            if s_loc < 3 * W or s_loc > lens[li] - 3 * W:
                continue
            if float(np.interp(s_b, s_grid, pr["r"])) > 1.4:      # already a mass there
                continue
            size = W * (0.9 + 0.8 * (len(bs) - k_) / max(len(bs), 1))
            evs.append(signs.LineEvent("interior", ops[k_ % len(ops)], li, s_loc, size,
                                       side=1.0 if tm.jitter[fi] >= 0 else -1.0))
        if evs:
            base = [s.points for s in strokes]
            ed = signs.apply_events(base, evs, rng, w=W / 2.6, W=W)
            strokes = _merge_events(strokes, ed)
            info["events"] = [e.to_json() for e in evs]
    return strokes, info


def _merge_events(danced, edited):
    """Carry the danced r/φ/mass onto the event-edited strokes: each edited
    line stroke takes max(r_event, r_dance) and the dance's φ/mass at its
    nearest original sample; child strokes keep their own."""
    from scipy.spatial import cKDTree  # noqa: PLC0415
    from . import regime as rg  # noqa: PLC0415
    out = []
    for st in edited:
        li = st.meta.get("line") if "parent" not in st.meta else None
        if li is None or li >= len(danced):
            out.append(st)
            continue
        d = danced[li]
        _, ix = cKDTree(d.points).query(st.points)
        r = np.maximum(st.r, d.r[ix])
        out.append(rg.RegimeStroke(st.points, r, d.phi[ix], st.W, np.maximum(st.mass, d.mass[ix]),
                                   w_min=st.w_min, closed=st.closed, fill=st.fill, meta=st.meta))
    return out
