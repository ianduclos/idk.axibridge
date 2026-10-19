# FROZEN from research commit 071aea1: tools/gesture/gesture/kit/devices_meas_read.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Process-correlated measuring devices, round 15 thread D (`meas`): the
shared reader. It registers no device; the `devices_meas_*.py` files do.

What a process device may read, and only this (each is true of the sheet):
- the marks in drawing order (part order, then the arranger's order: the
  renderer inks each part's marks in that order, so it is the pen's order);
- who spoke each line: the `voice` channel + meta["voices"] (drift), the
  ccolour plan (obj → hand), the cimpro log (move → the library ids it
  names), meta["voices"], river_zoom's stem, else the recipe part's voice;
- the source clocks a line carries: `u_km` / `zoom` (river_zoom), `dance_t`
  (the dance voice);
- the score (`notes["score"]`, `_score.py`) or, when a round-14 arranger
  wrote none, a score derived from its own log (ccolour events, cimpro
  moves), marked `"derived": true`.

`units(sheet, by)` groups marks into the drawing's units: by "line" (one
continuous mark, or one ccolour object / cimpro line) or by "step" (one
ccolour object, one cimpro move, one score layer, one part)."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from . import voices_machine_diagram as vd
from ._score import score_of
from .core import Ink

FAMILY_PREFIX = (("river", "river"), ("dancer", "dance"), ("dance", "dance"), ("mime", "mime"),
                 ("trail", "trail"), ("fly", "fly"), ("grwl", "river"))


# ---------------------------------------------------------------------------
# small drawing helpers (one stroke font for every device: vd's 3x5)
# ---------------------------------------------------------------------------

def text(s, x, y, h, anchor="left"):
    return vd.text(str(s), float(x), float(y), float(h), anchor=anchor)


def text_w(s, h):
    return vd.text_width(str(s), h)


def rule(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y1]], float)


def circle(c, r, n=16):
    t = np.linspace(0, 2 * math.pi, n + 1)
    return np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)])


def short(hid: str, n: int = 6) -> str:
    """A hand id as a short label in the stroke font: trail_miner → MINER."""
    hid = str(hid)
    if ":" in hid:                                   # "dance:levitation:lhand" → levitation
        bits = [b for b in hid.split(":") if b]
        hid = bits[1] if len(bits) > 1 else bits[0]
    for pre in ("dancer_", "dance_", "mime_", "trail_", "river_", "fly_"):
        if hid.startswith(pre) and len(hid) > len(pre):
            hid = hid[len(pre):]
            break
    hid = hid.replace("grwl_far_", "").replace("_", "")
    return hid[:n].upper()


def inks(polys, *, pen: float, colour: str, role: str = "", meta: dict | None = None) -> list[Ink]:
    out = []
    for p in polys:
        p = np.asarray(p, float)
        if len(p) >= 2 and np.all(np.isfinite(p)):
            out.append(Ink(p, closed=bool(len(p) >= 4 and np.allclose(p[0], p[-1])), filled=False, pen=float(pen),
                           meta={"colour": colour, "role": role, **(meta or {})}))
    return out


def fit_into(polys, box, *, pad: float = 0.0, align: str = "centre"):
    """Uniform scale + offset taking polys' bbox into box (x0, y0, w, h)."""
    allp = np.vstack([np.asarray(p, float) for p in polys if len(p)])
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    ext = np.maximum(hi - lo, 1e-9)
    x0, y0, w, h = box
    k = min((w - 2 * pad) / ext[0], (h - 2 * pad) / ext[1])
    off = np.array([x0 + w / 2, y0 + h / 2]) - (lo + hi) / 2 * k
    if align == "left":
        off[0] = x0 + pad - lo[0] * k
    return k, off


def chord_frame(p: np.ndarray) -> np.ndarray:
    q = np.asarray(p, float) - p[0]
    a = math.atan2(q[-1, 1], q[-1, 0]) if np.hypot(*q[-1]) > 1e-9 else 0.0
    c, s = math.cos(-a), math.sin(-a)
    return q @ np.array([[c, -s], [s, c]]).T


def nice(x: float) -> float:
    e = 10 ** math.floor(math.log10(max(x, 1e-12)))
    for m in (1, 2, 5, 10):
        if m * e >= x:
            return m * e
    return 10 * e


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------

def _library_ids(sheet) -> list[tuple[str, str]]:
    return [(str(e.get("kind")), str(e.get("id"))) for e in sheet.meta.get("library", [])]


def family(hid: str | None) -> str:
    """The corpus family a library id belongs to (rivers, dance, mime, trails,
    flies by id; else the entry's provenance corpus; else 'machine')."""
    if not hid:
        return "machine"
    for pre, fam in FAMILY_PREFIX:
        if hid.startswith(pre):
            return fam
    try:
        from . import library  # noqa: PLC0415
        for kind in ("hand", "dance_trail", "tempo", "river_stems"):
            try:
                e = library.entry(kind, hid)
            except Exception:  # noqa: BLE001
                continue
            if kind == "dance_trail":
                return "dance"
            c = (e.get("provenance") or {}).get("corpus")
            if c:
                return {"artists": "artist", "hokusai": "artist", "matisse": "artist",
                        "ingres": "artist"}.get(str(c), str(c))
    except Exception:  # noqa: BLE001
        pass
    return "hand"


def _first(meta, key):
    for m in meta:
        if key in m:
            return m[key]
    return None


@dataclass
class Unit:
    index: int                      # drawing order, 0-based
    key: tuple
    marks: list
    hands: list[str]                # who spoke it, most first
    family: str
    role: str                       # found / made / container / … / the voice id
    verb: str                       # what the step did (cimpro verb, score role, …)
    colour: str
    pen: float
    step: int                       # the step (ccolour object / cimpro move / part) it belongs to
    weights: dict = field(default_factory=dict)

    @property
    def length(self) -> float:
        return float(sum(m.length() for m in self.marks))

    @property
    def start(self) -> np.ndarray:
        return np.asarray(self.marks[0].points[0], float)

    @property
    def points(self) -> list[np.ndarray]:
        return [np.asarray(m.points, float) for m in self.marks]

    def label(self, n: int = 6) -> str:
        return short(self.hands[0], n) if self.hands else self.role[:n].upper()


def drawing_marks(sheet) -> list:
    """The drawing's marks in the pen's order (parts in order, marks in the
    arranger's order within a part); devices' own marks never appear here."""
    live = [(int(m.meta.get("part", 0) or 0), i, m) for i, m in enumerate(sheet.marks)
            if len(m) >= 2 and m.meta.get("layer") != "device"]
    return [m for _, _, m in sorted(live, key=lambda t: (t[0], t[1]))]


def _arranger_log(sheet, key):
    for m in sheet.marks:
        if key in m.meta:
            return m.meta[key]
    return None


def _part_colours(sheet) -> dict[int, str]:
    acc: dict[int, Counter] = {}
    for k in sheet.inks:
        if (k.meta or {}).get("layer") == "device" or len(k.points) < 2:
            continue
        c = (k.meta or {}).get("colour") or "black"
        L = float(np.sum(np.linalg.norm(np.diff(k.points, axis=0), axis=1)))
        acc.setdefault(int((k.meta or {}).get("part", 0) or 0), Counter())[c] += L
    return {p: c.most_common(1)[0][0] for p, c in acc.items()}


def _ids_in(textv: str, ids: list[str]) -> list[str]:
    """Library ids named in a log line, in the order they are named."""
    hits = []
    for i in ids:
        for mt in re.finditer(r"(?<![A-Za-z0-9_])" + re.escape(i) + r"(?![A-Za-z0-9_])", textv):
            hits.append((mt.start(), i))
    seen, out = set(), []
    for _, i in sorted(hits):
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _voice_weights(m) -> dict[str, float]:
    voices = list(m.meta.get("voices") or [])
    if "voice" not in m.channels or not voices:
        return {}
    v = np.asarray(m.channels["voice"]).astype(int)
    seg = np.r_[np.linalg.norm(np.diff(m.points, axis=0), axis=1), 0.0]
    out: dict[str, float] = {}
    for vi, L in zip(v, seg):
        if 0 <= vi < len(voices):
            out[voices[vi]] = out.get(voices[vi], 0.0) + float(L)
    return out


def _recipe_hands(sheet, part: int) -> list[str]:
    parts = sheet.meta.get("recipe", {}).get("parts", [])
    if not (0 <= part < len(parts)):
        return []
    v = parts[part].get("voice", {})
    for k in ("hand", "hands", "trail", "stems", "hand_a"):
        if v.get(k):
            got = v[k] if isinstance(v[k], list) else [v[k]]
            if k == "hand_a" and v.get("hand_b"):
                got = got + [v["hand_b"]]
            return [str(x) for x in got]
    return []


def _who(sheet, m, *, cc=None, ci=None, lib_ids=None) -> tuple[dict[str, float], str, str, tuple]:
    """(hand weights, role, verb, step key) of one mark."""
    meta = m.meta
    part = int(meta.get("part", 0) or 0)
    L = max(m.length(), 1e-9)
    if cc is not None and "obj" in meta:                       # ccolour: obj → plan
        obj = tuple(meta["obj"]) if isinstance(meta["obj"], (list, tuple)) else (str(meta["obj"]),)
        plan = cc.get("plan", {})
        kind = str(obj[0])
        hands: list[str] = []
        if kind == "made" and len(obj) > 1 and isinstance(obj[1], int) and obj[1] < len(plan.get("made", [])):
            hands = [plan["made"][obj[1]]["hand"]]
        elif kind in ("traverse", "counter") and (plan.get(kind) or {}).get("hand"):
            hands = [plan[kind]["hand"]]
        elif kind == "found":
            for f in plan.get("found", []):
                if len(obj) > 1 and f.get("kind") == obj[1]:
                    v = f.get("voice", {})
                    hands = list(v.get("hands") or ([v["stems"]] if v.get("stems") else []))
        return ({h: L for h in hands}, str(meta.get("of_role", kind)), kind, ("obj",) + obj)
    if ci is not None and "move" in meta:                      # cimpro: move → its log line
        k = int(meta["move"])
        e = next((e for e in ci.get("log", []) if e.get("k") == k), {})
        hands = _ids_in(str(e.get("what", "")), lib_ids or [])
        if meta.get("reg") == "river" and not hands:
            hands = [i for kd, i in _library_ids(sheet) if kd == "river_stems"][:1]
        return ({h: L / max(len(hands), 1) for h in hands}, str(meta.get("reg", meta.get("of_role", ""))),
                str(e.get("verb", "")), ("move", k))
    w = _voice_weights(m)
    if not w and meta.get("voices"):
        vs = [str(v) for v in meta["voices"]]
        w = {v: L / len(vs) for v in vs}
    if not w and (meta.get("voice_id") == "river_zoom" or str(meta.get("found", "")).startswith("grwl")):
        w = {i: L for kd, i in _library_ids(sheet) if kd == "river_stems"}
    if not w:
        w = {h: L for h in _recipe_hands(sheet, part)}
    role = str(meta.get("of_role") or meta.get("voice_id") or
               sheet.meta.get("recipe", {}).get("parts", [{}] * (part + 1))[part].get("voice", {}).get("id", "line"))
    lay = meta.get("layer") if meta.get("layer") != "device" else None
    return (w, role, role, ("layer", str(lay)) if lay else ("part", part))


def units(sheet, by: str = "line") -> list[Unit]:
    """The drawing's units in the pen's order. by: line | step."""
    ms = drawing_marks(sheet)
    cc = _arranger_log(sheet, "ccolour")
    ci = _arranger_log(sheet, "cimpro")
    lib_ids = sorted({i for _, i in _library_ids(sheet)}, key=lambda s: (-len(s), s))
    pcol = _part_colours(sheet)
    groups: dict[tuple, Unit] = {}
    order: list[tuple] = []
    for i, m in enumerate(ms):
        w, role, verb, step = _who(sheet, m, cc=cc, ci=ci, lib_ids=lib_ids)
        if by == "step":
            key = step
        elif cc is not None and "obj" in m.meta:
            key = step
        elif ci is not None and "line" in m.meta:
            key = ("line", int(m.meta["line"]))
        else:
            key = ("mark", i)
        if key not in groups:
            groups[key] = Unit(len(order), key, [], [], "", role, verb, "black", 0.0, 0, {})
            order.append(key)
        u = groups[key]
        u.marks.append(m)
        for h, x in w.items():
            u.weights[h] = u.weights.get(h, 0.0) + x
        u.colour = u.colour if len(u.marks) > 1 else str(m.meta.get("ink") or pcol.get(int(m.meta.get("part", 0) or 0),
                                                                                          "black"))
        u.pen = max(u.pen, float(m.meta.get("pen", 0.0) or 0.0))
    steps: dict[tuple, int] = {}
    out = []
    for key in order:
        u = groups[key]
        u.hands = [h for h, _ in sorted(u.weights.items(), key=lambda t: (-t[1], t[0]))]
        u.family = family(u.hands[0]) if u.hands else (u.role or "machine")
        if u.key[-1] == "chart" or (u.role in ("chart", "found") and u.verb == "found" and not u.hands):
            u.family = "chart"
        _, _, _, sk = _who(sheet, u.marks[0], cc=cc, ci=ci, lib_ids=lib_ids)
        u.step = steps.setdefault(sk, len(steps))
        lens = Counter()
        for m in u.marks:
            lens[str(m.meta.get("ink") or u.colour)] += m.length()
        u.colour = lens.most_common(1)[0][0] if lens else u.colour
        out.append(u)
    return out


def families_in_order(us: list[Unit]) -> list[str]:
    seen: list[str] = []
    for u in us:
        if u.family not in seen:
            seen.append(u.family)
    return seen


# ---------------------------------------------------------------------------
# the score: recorded, or derived from a round-14 arranger's own log
# ---------------------------------------------------------------------------

_XY = re.compile(r"\[(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\]")


def process_score(sheet) -> dict | None:
    """The sheet's score (`_score.py`), or one derived from the arranger's
    own log: ccolour (objects as layers; carry / spill / answer / catch
    events as relations) or cimpro (moves as layers; cover, cross,
    counterweight, trail, thicken read against the core and the covers they
    name). Derived scores carry "derived": the arranger id."""
    sc = score_of(sheet)
    if sc:
        return sc
    cc = _arranger_log(sheet, "ccolour")
    if cc is not None:
        return _score_ccolour(sheet, cc)
    ci = _arranger_log(sheet, "cimpro")
    if ci is not None:
        return _score_cimpro(sheet, ci)
    return None


def _score_ccolour(sheet, cc) -> dict:
    us = units(sheet, "step")
    layers, ids = [], {}
    for u in us:
        lid = f"L{len(layers)}"
        ids[u.key[1:]] = lid
        layers.append({"id": lid, "role": u.role, "technique": u.verb, "part": 0, "pen": u.colour,
                       "params": {"hands": u.hands}, "label": u.label()})
    rels = []
    for e in cc.get("events", []):
        dst = ids.get(tuple(e.get("obj", ())))
        why = str(e.get("why", ""))
        if dst is None:
            continue
        if e.get("kind") == "carry" or "chart" in why:
            src = ids.get(("found", "chart"))
        elif e.get("kind") == "spill" or "container" in why:
            src = ids.get(("container", 0))
        else:
            src = None
        rels.append({"kind": str(e.get("kind")), "src": src or dst, "dst": dst, "at": None,
                     "s": None if e.get("at_mm") is None else [round(float(e["at_mm"]), 2),
                                                             round(float(e["at_mm"]) + float(e.get("len_mm", 0)), 2)],
                     "note": why})
    return {"version": 1, "derived": "ccolour", "layers": layers, "relations": rels,
            "decisions": {"order": cc.get("order"), "pens": cc.get("pens_used")}}


def _score_cimpro(sheet, ci) -> dict:
    log = [e for e in ci.get("log", []) if e.get("verb") != "stop"]
    drawn = {int(m.meta["move"]) for m in sheet.marks if "move" in m.meta}
    layers, ids = [], {}
    for e in log:
        k = int(e["k"])
        lid = f"L{len(layers)}"
        ids[k] = lid
        hands = _ids_in(str(e.get("what", "")), sorted({i for _, i in _library_ids(sheet)}, key=lambda s: (-len(s), s)))
        layers.append({"id": lid, "role": str(e["verb"]), "technique": "cimpro", "part": 0, "pen": None,
                       "params": {"hands": hands, "drawn": k in drawn}, "label": str(e["verb"])})
    rels = []
    core = None
    covers: list[tuple[int, tuple]] = []
    for e in log:
        k, v, what = int(e["k"]), str(e["verb"]), str(e.get("what", ""))
        xy = _XY.search(what)
        at = [float(xy.group(1)), float(xy.group(2))] if xy else None
        if v in ("thicken", "seed"):
            if core is not None and v == "thicken":
                rels.append({"kind": "thicken", "src": ids[k], "dst": ids[core], "at": at, "s": None,
                             "note": str(e.get("why", ""))})
            core = k
        elif v == "cover":
            if at:
                covers.append((k, tuple(at)))
            if core is not None:
                rels.append({"kind": "cover", "src": ids[k], "dst": ids[core], "at": at, "s": None,
                             "note": str(e.get("why", ""))})
        elif v == "cross" and at:
            hit = min(covers, key=lambda c: math.dist(c[1], at), default=None)
            if hit is not None:
                rels.append({"kind": "cross", "src": ids[k], "dst": ids[hit[0]], "at": at, "s": None,
                             "note": str(e.get("why", ""))})
        elif v in ("counterweight", "trail", "intrude") and core is not None:
            rels.append({"kind": v, "src": ids[k], "dst": ids[core], "at": at, "s": None,
                         "note": str(e.get("why", ""))})
    return {"version": 1, "derived": "cimpro", "layers": layers, "relations": rels,
            "decisions": {"temperament": {k: v for k, v in (ci.get("temperament") or {}).items()
                                          if k in ("appetite", "hands", "found_ink")}}}


def layer_marks(sheet, sc: dict) -> dict[str, list]:
    """Score layer id → the marks it drew (by layer meta, the derived keys, or part)."""
    out: dict[str, list] = {lay["id"]: [] for lay in sc.get("layers", [])}
    der = sc.get("derived")
    if der == "ccolour":
        us = units(sheet, "step")
        for lay, u in zip(sc["layers"], us):
            out[lay["id"]] = list(u.marks)
        return out
    if der == "cimpro":
        k2l = {}
        log = [e for e in (_arranger_log(sheet, "cimpro") or {}).get("log", []) if e.get("verb") != "stop"]
        for lay, e in zip(sc["layers"], log):
            k2l[int(e["k"])] = lay["id"]
        for m in drawing_marks(sheet):
            lid = k2l.get(int(m.meta.get("move", -1)))
            if lid:
                out[lid].append(m)
        return out
    byp: dict[int, list[str]] = {}
    for lay in sc.get("layers", []):
        if lay.get("part") is not None:
            byp.setdefault(int(lay["part"]), []).append(lay["id"])
    for m in drawing_marks(sheet):
        lid = m.meta.get("score_layer") or m.meta.get("layer")
        if lid in out:
            out[lid].append(m)
            continue
        cand = byp.get(int(m.meta.get("part", 0) or 0), [])
        if len(cand) == 1:
            out[cand[0]].append(m)
    return out


def ink_for(ink: str, u: "Unit | None" = None) -> str:
    """'source' → the unit's own ink (its line's colour); anything else as given."""
    if ink == "source":
        return u.colour if u is not None else "black"
    return str(ink)


def side_label(p: np.ndarray, nrm: np.ndarray, lab: str, h: float, others: np.ndarray, gap: float = 1.0):
    """A label beside point p on whichever side of normal nrm is emptier."""
    best = None
    for sg in (1.0, -1.0):
        c = p + sg * nrm * (gap + 0.9 * h)
        d = float(np.min(np.linalg.norm(others - c, axis=1))) if len(others) else 1e9
        if best is None or d > best[0] + 1e-9:
            best = (d, sg)
    c = p + best[1] * nrm * (gap + 0.9 * h)
    return text(lab, c[0], c[1] - h / 2, h, anchor="centre")


def normal_at(p: np.ndarray, i: int) -> np.ndarray:
    a, b = p[max(i - 2, 0)], p[min(i + 2, len(p) - 1)]
    d = b - a
    n = float(np.hypot(*d))
    if n < 1e-12:
        return np.array([0.0, -1.0])
    return np.array([-d[1], d[0]]) / n
