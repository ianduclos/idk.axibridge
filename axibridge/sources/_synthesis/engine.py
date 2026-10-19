"""Play a synthesis score into app paths (S4).

The score executor is the frozen kit's (`kit/_synth.py`): `play(score, lib)`
runs it once per (score, library) and keeps the last few sheets, so every
member of a kept group (one app layer per score layer, plus a Measure layer)
resolves the very same sheet and keeps only its own inks. Devices are laid on
with the app's device layer (`devices.apply`: cancellable, memoised, a note
per device), never inside the executor.

Preview cancellation: Gesture Studies' engine, loaded over this kit
(`_shared.load`), wraps every technique stage with `checkpoint()`; this module
wraps the relations and the writers the same way. The wrappers pass every
argument through, so output is unchanged (the parity test runs through them).

One synthesis plays at a time (`_PLAY`): the executor's per-layer cache is a
plain OrderedDict shared by the process.
"""
from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import threading
from collections import OrderedDict
from typing import Any

from ...model import Path
from ...registry import report_progress
from ...render_work import checkpoint
from . import devices as DV
from . import frozen_library as FL
from ._shared import load
from .kit import _relations, _synth, _writers
from .kit import arrangers_oehlen_found as _aof
from .kit import library as _kl

_gse = load("engine")          # installs the stage hooks on THIS kit's technique registry
INK = _gse.INK
MEASURE = "measure"


def flexoki() -> dict[str, str]:
    """Flexoki pen name -> hex (the 600 accents + black, and the 400 accents)."""
    return dict(_aof.FLEXOKI)


_gse._flexoki = flexoki        # the loaded engine's colour table (Gesture Studies reads it from its studies)
_HOOKED = False


def _hooked(fn):
    @functools.wraps(fn)
    def wrapped(*a, **k):
        checkpoint()
        out = fn(*a, **k)
        checkpoint()
        return out
    wrapped._syn_hooked = True
    return wrapped


def install_hooks() -> None:
    global _HOOKED
    if _HOOKED:
        return
    _gse.install_hooks()
    for reg in (_relations._RELATIONS, _writers._WRITERS):
        for rid, r in list(reg.items()):
            if not getattr(r.fn, "_syn_hooked", False):
                reg[rid] = dataclasses.replace(r, fn=_hooked(r.fn))
    # a stray `library.default()` inside the kit must reach the frozen library, never a research path
    _kl._DEFAULT = FL.FrozenLibrary()
    _HOOKED = True


install_hooks()

_PLAY = threading.RLock()
_SHEETS: "OrderedDict[str, tuple]" = OrderedDict()
_SHEETS_MAX = 6


def lib_key(lib: FL.FrozenLibrary) -> list:
    return [lib.snapshot_id, sorted(f"{k}/{i}@{h}" for (k, i), h in lib.pins.items())]


def score_hash(score: dict) -> str:
    return hashlib.sha1(json.dumps(score, sort_keys=True, separators=(",", ":"), default=float).encode()).hexdigest()


def play(score: dict, lib: FL.FrozenLibrary) -> tuple[Any, list[dict] | None]:
    """A validated score → (the played Sheet with its devices laid on, a note per device or None)."""
    key = json.dumps([score_hash(score), lib_key(lib)])
    with _PLAY:
        hit = _SHEETS.get(key)
        if hit is not None:
            _SHEETS.move_to_end(key)
            return hit
        report_progress(0.05, "playing the score")
        bare = {**score, "devices": []}
        sheet = _synth.run(bare, library=lib)
        notes = None
        if score.get("devices"):
            report_progress(0.9, "measuring")
            specs = DV.check_specs(score["devices"], lib)
            sheet, notes = DV.apply(sheet, specs, lib, memo_key=json.dumps([score_hash(bare), lib_key(lib)]))
        report_progress(0.97, f"{len(sheet.inks)} ink paths")
        _SHEETS[key] = (sheet, notes)
        while len(_SHEETS) > _SHEETS_MAX:
            _SHEETS.popitem(last=False)
        return sheet, notes


def clear() -> None:
    with _PLAY:
        _SHEETS.clear()
        _synth.clear_cache()


def compose(writer: str, *, lib: FL.FrozenLibrary, **kw) -> dict:
    with _PLAY:
        return _writers.compose(writer, library=lib, **kw)


def recompose(score: dict, *, lib: FL.FrozenLibrary, **kw) -> dict:
    with _PLAY:
        return _writers.recompose(score, library=lib, **kw)


def pin(score: dict, ids, *, lib: FL.FrozenLibrary) -> dict:
    with _PLAY:
        return _synth.pin(score, ids, library=lib)


def validate(score: dict, lib: FL.FrozenLibrary) -> dict:
    with _PLAY:
        out = _synth.validate(score, library=lib)
    out.pop("parts", None)
    return out


def clip_to_frame(p: Path, W: float, H: float) -> list[Path]:
    """The placement contract (ink inside the frame), path by path: a path inside stays as it is; one
    that overhangs is clipped at the frame. Not Gesture Studies' shrink-everything safety net, which
    would move every layer (held ones too) when one edited line overhangs."""
    pts = p.points
    if all(0.0 <= x <= W and 0.0 <= y <= H for x, y in pts):
        return [p]
    import shapely  # noqa: PLC0415
    box = shapely.box(0.0, 0.0, W, H)
    if p.filled and len(pts) >= 4:
        geom = shapely.Polygon(pts).buffer(0).intersection(box)
        rings = [g.exterior for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and not g.is_empty]
        return [Path(points=[(float(x), float(y)) for x, y in r.coords], filled=True) for r in rings
                if len(r.coords) >= 4]
    geom = shapely.LineString(pts).intersection(box)
    parts = [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "LineString" and not g.is_empty]
    return [Path(points=[(float(x), float(y)) for x, y in g.coords], filled=False) for g in parts
            if len(g.coords) >= 2]


def layer_paths(sheet, score: dict) -> tuple[tuple[float, float], list[dict]]:
    """The played sheet → ((W, H), groups in pen order): one group per visible score layer that drew
    something ({"id", "label", "pen", "role", "items": [(Path, (colour, width))]}) and, when devices
    drew, one Measure group (id MEASURE; first when every device sits under). Ink is clipped at the frame
    path by path (`clip_to_frame`), never rescaled, so the groups stay in register and a held layer stays
    where it was."""
    W, H = sheet.frame

    def tag(ink):
        if (ink.meta or {}).get("layer") == "device":
            return MEASURE
        return str((ink.meta or {}).get("score_layer") or "")

    by: dict[str, list] = {}
    for t, p, ink in _gse._tagged(sheet.inks, tag):
        style = _gse.ink_style(ink)
        for q in clip_to_frame(p, W, H):
            by.setdefault(t, []).append((q, style))
    groups = []
    for L in score["layers"]:
        if L["role"] == _synth.UNSEEN or not by.get(L["id"]):
            continue
        groups.append({"id": L["id"], "label": L.get("label") or L["id"], "pen": L["pen"], "role": L["role"],
                       "items": by[L["id"]]})
    if by.get(MEASURE):
        m = {"id": MEASURE, "label": "Measure", "pen": None, "role": "measure", "items": by[MEASURE]}
        under = bool(score.get("devices")) and all(d.get("place") == "under" for d in score["devices"])
        groups = [m, *groups] if under else [*groups, m]
    return (float(W), float(H)), groups


def played_summary(sheet, score: dict) -> dict:
    """What the bench overlays on its two editors: per relation, how often it fired and how
    (outcomes; a relation that never changed a line is drawn dashed), per layer whether it drew."""
    pl = _synth.played(sheet) or {}
    rel: dict[str, dict] = {R["id"]: {"fired": 0, "applied": 0, "outcomes": {}} for R in score["relations"]}
    for ev in pl.get("log", []):
        r = rel.setdefault(ev["relation"], {"fired": 0, "applied": 0, "outcomes": {}})
        r["applied"] += 1
        o = ev.get("outcome", "fired")
        r["outcomes"][o] = r["outcomes"].get(o, 0) + 1
        if o not in _synth.NEUTRAL:
            r["fired"] += 1
    pairs: dict[str, set] = {}
    for ev in pl.get("log", []):
        if ev.get("outcome") not in _synth.NEUTRAL:
            pairs.setdefault(ev["relation"], set()).add((ev["src"], ev["dst"]))
    for rid, ps in pairs.items():
        rel[rid]["pairs"] = sorted([list(p) for p in ps])[:64]
    return {"relations": rel, "decisions": pl.get("decisions", {}),
            "seconds": sheet.meta.get("seconds"), "cache_hits": sheet.meta.get("cache_hits")}


def paths_only(groups: list[dict]) -> list[Path]:
    return [p for g in groups for p, _ in g["items"]]
