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
import json
import threading
from collections import OrderedDict

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
    return [p for _, p in _inks_to_tagged(inks)]


def ink_name(ink) -> str:
    """The Flexoki pen a kit ink names: meta "ink", else a "colour" given as a name."""
    return str(ink.meta.get("ink") or ink.meta.get("colour") or "black")


INK = "#100f0f"           # Flexoki black: an ink that names no pen


@functools.lru_cache(maxsize=1)
def _flexoki() -> dict[str, str]:
    from .studies import flexoki  # noqa: PLC0415
    return flexoki()


def ink_style(ink) -> tuple[str, float]:
    """(colour, pen width mm) an ink is drawn with, for the bench's preview:
    meta "colour" when it is a hex, else the Flexoki pen its name names."""
    c = ink.meta.get("colour")
    if isinstance(c, str) and c.startswith("#"):
        colour = c
    else:
        colour = _flexoki().get(ink_name(ink), INK)
    return colour, float(ink.pen)


def _tagged(inks, tag=None) -> list[tuple[int, Path, object]]:
    """(part index — or tag(ink) — , Path, ink) per kept ink (see inks_to_paths)."""
    arrs = _simplify([ink.points for ink in inks])
    out = []
    for ink, a, full in zip(inks, arrs, (ink.points for ink in inks)):
        if len(a) < 2:
            continue
        part = int(ink.meta.get("part", 0)) if tag is None else tag(ink)
        if ink.closed:
            ring = a if len(a) >= 4 else np.asarray(full, dtype=np.float64)
            pts = [(float(x), float(y)) for x, y in ring]
            if pts[0] != pts[-1]:
                pts.append(pts[0])
            pts[-1] = pts[0]
            out.append((part, Path(points=pts, filled=bool(ink.filled) and len(pts) >= 4), ink))
        else:
            out.append((part, Path(points=[(float(x), float(y)) for x, y in a], filled=False), ink))
    return out


def _inks_to_tagged(inks, tag=None) -> list[tuple[int, Path]]:
    """(part index — or tag(ink) — , Path) per kept ink (see inks_to_paths)."""
    return [(part, p) for part, p, _ in _tagged(inks, tag)]


# The last few sheets, by recipe + library: the layers of one chorus resolve
# the same recipe and each keeps its own voice, so they share one run.
_SHEETS: "OrderedDict[str, object]" = OrderedDict()
_SHEETS_MAX = 4
_SHEETS_LOCK = threading.Lock()


def _sheet_key(recipe: dict, lib: FL.FrozenLibrary) -> str:
    pins = sorted(f"{k}/{i}@{h}" for (k, i), h in lib.pins.items())
    return json.dumps([recipe, str(FL.ROOT), lib.snapshot_id, pins], sort_keys=True, separators=(",", ":"))


def run_kit(recipe: dict, lib: FL.FrozenLibrary):
    key = _sheet_key(recipe, lib)
    with _SHEETS_LOCK:
        hit = _SHEETS.get(key)
        if hit is not None:
            _SHEETS.move_to_end(key)
            return hit
    report_progress(0.05, "drawing the study")
    sheet = _kit.run(recipe, library=lib)
    report_progress(0.95, f"{len(sheet.inks)} ink paths")
    with _SHEETS_LOCK:
        _SHEETS[key] = sheet
        while len(_SHEETS) > _SHEETS_MAX:
            _SHEETS.popitem(last=False)
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


def render_voices(recipe: dict, lib: FL.FrozenLibrary, inks: list[str] | None = None) -> dict[int, list[Path]]:
    """A kit recipe → its paths per part (voice), or per ink name when `inks`
    names the voices (index in `inks`), fitted inside the frame as ONE drawing
    (so voices kept as separate layers stay in register)."""
    return {k: [p for p, _ in v] for k, v in render_voices_styled(recipe, lib, inks).items()}


def render_voices_styled(recipe: dict, lib: FL.FrozenLibrary,
                         inks: list[str] | None = None) -> dict[int, list[tuple[Path, tuple[str, float]]]]:
    """render_voices with each path's (colour, pen width) — what the bench draws it in."""
    W, H = frame_of("kit", recipe)
    tag = None
    if inks:
        def tag(ink):
            name = ink_name(ink)
            if name not in inks:
                raise ValueError(f"the drawing uses the pen {name!r}, which is not one of this study's inks {inks}")
            return inks.index(name)
    tagged = _tagged(run_kit(recipe, lib).inks, tag)
    fitted = _fit_inside([p for _, p, _ in tagged], W, H)
    out: dict[int, list[tuple[Path, tuple[str, float]]]] = {}
    for (part, _, ink), p in zip(tagged, fitted):
        out.setdefault(part, []).append((p, ink_style(ink)))
    return out


# ---------------------------------------------------------------------------
# measuring devices (study bench v3, move G): laid on the finished sheet
# ---------------------------------------------------------------------------

MEASURE = "measure"       # the tag of a device ink (every other ink is tagged by part / voice)
_MEASURED: "OrderedDict[str, tuple]" = OrderedDict()
_MEASURED_MAX = 4


def drawing_sheet(engine: str, recipe: dict, lib: FL.FrozenLibrary):
    """The finished drawing as a kit Sheet. Kit: its run. Hand Drift: its paths
    as marks + inks in drawing order (one part), so the devices that read the
    pen's order and the finished ink have them; it records no score or clock."""
    if engine != "hand_drift":
        return run_kit(recipe, lib)
    paths = run_hand_drift(recipe, lib)
    pen = float(recipe["pen"])
    marks, inks = [], []
    for i, p in enumerate(paths):
        pts = np.asarray(p.points, dtype=np.float64)
        marks.append(_core.Mark(pts, {}, {"part": 0, "voice": "hand_drift"}))
        inks.append(_core.Ink(pts, closed=len(pts) >= 4 and bool(np.allclose(pts[0], pts[-1])),
                              filled=bool(p.filled), pen=pen, meta={"part": 0, "hd": i}))
    W, H = frame_of(engine, recipe)
    return _core.Sheet((W, H), marks, inks, {"recipe": {"seed": int(recipe["seed"]), "frame": [W, H]},
                                             "library": [], "notes": {}})


def measured_sheet(engine: str, recipe: dict, lib: FL.FrozenLibrary, devices: list[dict]):
    """(sheet with the devices laid on it, a note per device); the last few kept."""
    from . import devices as D  # noqa: PLC0415
    key = json.dumps([engine, _sheet_key(recipe, lib), devices], sort_keys=True, separators=(",", ":"))
    with _SHEETS_LOCK:
        hit = _MEASURED.get(key)
        if hit is not None:
            _MEASURED.move_to_end(key)
            return hit
    base = drawing_sheet(engine, recipe, lib)
    report_progress(0.96, "measuring")
    out = D.apply(base, devices, lib, memo_key=json.dumps([engine, _sheet_key(recipe, lib)]))
    with _SHEETS_LOCK:
        _MEASURED[key] = out
        while len(_MEASURED) > _MEASURED_MAX:
            _MEASURED.popitem(last=False)
    return out


def render_measured(engine: str, recipe: dict, lib: FL.FrozenLibrary, devices: list[dict],
                    inks: list[str] | None = None):
    """A study with devices → ((W, H) grown by any `beside` panel,
    [(tag, Path, (colour, width))] in pen order, the device notes). The tag is
    MEASURE for a device ink, else the part (or, with `inks`, the voice index).
    Drawing and devices are fitted inside the frame as ONE drawing, so the
    drawing and its Measure layer stay in register; Hand Drift's own paths are
    used as they are (not simplified twice)."""
    sheet, notes = measured_sheet(engine, recipe, lib, devices)
    W, H = sheet.frame

    def tag(ink):
        if ink.meta.get("layer") == "device":
            return MEASURE
        if inks:
            name = ink_name(ink)
            if name not in inks:
                raise ValueError(f"the drawing uses the pen {name!r}, which is not one of this study's inks {inks}")
            return inks.index(name)
        return int(ink.meta.get("part", 0))

    if engine == "hand_drift":
        hd = run_hand_drift(recipe, lib)
        pen = float(recipe["pen"])
        dev = _tagged([k for k in sheet.inks if k.meta.get("layer") == "device"], tag)
        it = iter(dev)
        tagged = []
        for k in sheet.inks:
            if k.meta.get("layer") == "device":
                nxt = next((t for t in it if t[2] is k), None)
                if nxt is not None:
                    tagged.append(nxt)
            else:
                tagged.append((0, hd[int(k.meta["hd"])], k))
        styles = [ink_style(k) if t == MEASURE else (INK, pen) for t, _, k in tagged]
    else:
        tagged = _tagged(sheet.inks, tag)
        styles = [ink_style(k) for _, _, k in tagged]
    fitted = _fit_inside([p for _, p, _ in tagged], W, H)
    return (float(W), float(H)), [(t, p, s) for (t, _, _), p, s in zip(tagged, fitted, styles)], notes


def render(engine: str, recipe: dict, lib: FL.FrozenLibrary) -> list[Path]:
    """A resolved, validated recipe → app paths inside its frame."""
    return render_styled(engine, recipe, lib)[0]


def render_styled(engine: str, recipe: dict, lib: FL.FrozenLibrary) -> tuple[list[Path], list[tuple[str, float]]]:
    """render() and each path's (colour, pen width): the bench draws every ink
    in its pen colour at its width (bench v3). The paths are render()'s exactly."""
    if engine == "hand_drift":
        paths = run_hand_drift(recipe, lib)
        return paths, [(INK, float(recipe["pen"]))] * len(paths)
    W, H = frame_of(engine, recipe)
    tagged = _tagged(run_kit(recipe, lib).inks)
    return (_fit_inside([p for _, p, _ in tagged], W, H), [ink_style(ink) for _, _, ink in tagged])
