"""Run a resolved study to app paths (mm, frame origin).

Two engines:

- `kit` — the frozen gesture kit (`kit.run(recipe, library=...)`), inks →
  `Path`s. Closed inks are closed exactly (first == last); `filled` follows
  the kit (outline rings that occlude), only ever on a closed path.
- `hand_drift` — the first study delegates to the Hand Drift generator's own
  frozen engine (`sources/hand_drift.render_paths`), so its output is the
  standalone generator's. Hands and tempos outside that engine's frozen set
  come from the Gesture Studies library (same compact grammar format).

Both simplify at 0.01 mm (sub-visible; the Hand Drift baseline) and keep the
placement contract: ink inside the recipe frame (`_fit_inside` safety net).

Preview cancellation: the frozen kit never calls the app's `checkpoint()`;
`install_hooks()` wraps every registered kit stage and the long research
inner loops (grammar restyle, regime render) with checkpoint calls. The
wrappers only call `checkpoint()` and `report_progress()` and pass every
argument through, so output is unchanged (the parity test runs through them).
"""
from __future__ import annotations

import dataclasses
import functools

import numpy as np

from ...model import Path
from ...registry import report_progress
from ...render_work import checkpoint
from . import frozen_library as FL
from . import kit as _kit
from .kit import core as _core
from .kit._research import grammar as _grammar
from .kit._research import regime as _regime

_HOOKED = False


def _stage(fn):
    @functools.wraps(fn)
    def wrapped(*a, **k):
        checkpoint()
        out = fn(*a, **k)
        checkpoint()
        return out
    wrapped._gs_hooked = True
    return wrapped


def _loop(fn):
    @functools.wraps(fn)
    def wrapped(*a, **k):
        checkpoint()
        return fn(*a, **k)
    wrapped._gs_hooked = True
    return wrapped


def install_hooks() -> None:
    global _HOOKED
    if _HOOKED:
        return
    _kit.discover()
    for mods in _core._REGISTRY.values():
        for mid, m in list(mods.items()):
            if not getattr(m.fn, "_gs_hooked", False):
                mods[mid] = dataclasses.replace(m, fn=_stage(m.fn))
    for mod, name in ((_grammar, "restyle"), (_regime, "render")):
        f = getattr(mod, name)
        if not getattr(f, "_gs_hooked", False):
            setattr(mod, name, _loop(f))
    _HOOKED = True


install_hooks()

SIMPLIFY_MM = 0.01


def _simplify(arrs: list[np.ndarray]) -> list[np.ndarray]:
    import shapely  # noqa: PLC0415
    keep = [np.asarray(a, dtype=np.float64) for a in arrs]
    idx = [i for i, a in enumerate(keep) if len(a) >= 2]
    if not idx:
        return keep
    geoms = shapely.linestrings(np.vstack([keep[i] for i in idx]),
                                indices=np.repeat(np.arange(len(idx)), [len(keep[i]) for i in idx]))
    for i, g in zip(idx, shapely.simplify(geoms, SIMPLIFY_MM, preserve_topology=False)):
        c = shapely.get_coordinates(g)
        if len(c) >= 2:
            keep[i] = c
    return keep


def inks_to_paths(inks) -> list[Path]:
    """Kit inks → Paths: simplified, closed rings closed exactly, `filled`
    only on a closed ring with ≥ 4 points."""
    arrs = _simplify([ink.points for ink in inks])
    out = []
    for ink, a, full in zip(inks, arrs, (ink.points for ink in inks)):
        if len(a) < 2:
            continue
        if ink.closed:
            ring = a if len(a) >= 4 else np.asarray(full, dtype=np.float64)
            pts = [(float(x), float(y)) for x, y in ring]
            if pts[0] != pts[-1]:
                pts.append(pts[0])
            pts[-1] = pts[0]
            out.append(Path(points=pts, filled=bool(ink.filled) and len(pts) >= 4))
        else:
            out.append(Path(points=[(float(x), float(y)) for x, y in a], filled=False))
    return out


def run_kit(recipe: dict, lib: FL.FrozenLibrary):
    report_progress(0.05, "drawing the study")
    sheet = _kit.run(recipe, library=lib)
    report_progress(0.95, f"{len(sheet.inks)} ink paths")
    return sheet


def _fit_inside(paths: list[Path], width: float, height: float) -> list[Path]:
    from ..hand_drift import _fit_inside as fit  # noqa: PLC0415 — one implementation of the contract
    return fit(paths, width, height)


def frame_of(engine: str, recipe: dict) -> tuple[float, float]:
    if engine == "hand_drift":
        return float(recipe["width"]), float(recipe["height"])
    return float(recipe["frame"][0]), float(recipe["frame"][1])


# ---------------------------------------------------------------------------
# Hand Drift engine with library hands
# ---------------------------------------------------------------------------

def _hd_grammar(lib: FL.FrozenLibrary, name: str):
    """A library hand in the Hand Drift engine's compact grammar form."""
    from .._hand_drift.grammar import Grammar  # noqa: PLC0415
    e = lib.entry("hand", name)
    lib.check(e, "generate")
    key = ("hd-grammar", name, lib.hash_of("hand", name))
    with FL._LOAD_LOCK:
        if key in FL._LOADED:
            return FL._LOADED[key]
    folder = lib.folder("hand", name)
    g = _kit.library.decode_hand_json(_kit.library.read_npz(folder / e["files"]["tables"]),
                                      _kit.library.read_json_gz(folder / e["files"]["sheet"]))
    kp = {k: [] for k in ("line", "arc", "clothoid", "corner")}
    for toks in g["strokes"]:
        for t in toks:
            kp[t[0]].append(list(t[1:]))
    gram = Grammar(name, g["trans"], g["stroke_lengths"], dict(g["scale"]), dict(g["spread"]), kp).warm()
    with FL._LOAD_LOCK:
        return FL._LOADED.setdefault(key, gram)


def _hd_timing(lib: FL.FrozenLibrary, name: str) -> dict:
    tm = lib.load("tempo", name)
    t = np.asarray(tm.t, dtype=np.float64)
    fps = float(getattr(tm, "fps", 0.0) or (1.0 / float(np.median(np.diff(t)))))
    out = {"t": t, "speed": np.asarray(tm.speed, np.float64), "phi": np.asarray(tm.phi, np.float64),
           "jitter": np.asarray(tm.jitter, np.float64), "fps": fps, "label": getattr(tm, "label", name)}
    return out


def run_hand_drift(recipe: dict, lib: FL.FrozenLibrary) -> list[Path]:
    from .. import hand_drift as hd  # noqa: PLC0415
    from .._hand_drift import hands as H  # noqa: PLC0415
    names = {k: recipe[k] for k in ("hand_1", "hand_2", "hand_3", "hand_4", "timing")}
    loose = {**recipe, "hand_1": "matisse", "hand_2": "matisse", "hand_3": "none", "hand_4": "none",
             "timing": "staccato"}
    params = hd.HandDriftParams(**loose).model_copy(update=names)

    def load_hand(name: str):
        return H.load_hand(name) if name in H.HAND_IDS else _hd_grammar(lib, name)

    def load_timing(name: str):
        return H.load_timing(name) if name in H.TIMING_IDS else _hd_timing(lib, name)

    return hd.render_paths(params, load_hand=load_hand, load_timing=load_timing)


def render(engine: str, recipe: dict, lib: FL.FrozenLibrary) -> list[Path]:
    """A resolved, validated recipe → app paths inside its frame."""
    if engine == "hand_drift":
        return run_hand_drift(recipe, lib)
    W, H = frame_of(engine, recipe)
    sheet = run_kit(recipe, lib)
    return _fit_inside(inks_to_paths(sheet.inks), W, H)
