"""Measuring devices on a study (study bench v3, move G, 2026-10-19).

Ian (round 15): "measuring devices, I felt like they added a lot to drawings
that were a bit too weird … a selection of these to be added as a separate
layer"; the pen's flight: "has to be optional". The devices are the round-15
research devices, frozen with the kit (`kit/_devices.py` is the contract,
`kit/devices_*.py` the 13 devices). This module is the app's side of them:

- `CATALOGUE` — what the bench offers per device: a label, its family, the
  placement it sits best in (from the write-ups `tools/gesture/results/meas-*`),
  the two or three params worth a control, and what to say when the study has
  nothing for it to read;
- `check_specs(specs, lib)` — a layer's `devices` list validated against the
  frozen device registry (ids, placement, every param's type and bounds; string
  params against closed sets), normalised;
- `apply(sheet, specs, lib)` — the frozen `apply_devices` on a finished sheet,
  plus a note per device (how many inks it drew, or why it drew none).

A device that raises a `KitError` (the ruler that cannot fit at true scale)
draws nothing and says why; any other exception is a bug and propagates.
Devices that read the library (the ledger's hand-drawn rules, the corpus family
of a hand) read it through the kit's module-level default, so `apply` points
that default at the layer's own frozen library for the duration (one lock).
"""
from __future__ import annotations

import functools
import math
import re
import threading
import time
from collections import OrderedDict
from typing import Any

from ...render_work import checkpoint

PLACES = ("over", "under", "margin", "beside")
SIDES = {"margin": ("bottom", "top", "left", "right"), "beside": ("right", "bottom")}
SIZE = {"margin": (6.0, 60.0), "beside": (20.0, 240.0)}
DEFAULT_SIZE = {"margin": 22.0, "beside": 60.0}       # apply_devices' own defaults
MAX_DEVICES = 13
_WORDS = re.compile(r"^[a-z_]+(\s*,\s*[a-z_]+)*$")

# The bench's view of each device, in the order it lists them. `shown`: the
# params that get a control (the rest stay at the device's defaults unless a
# spec sets them). `empty`: what the bench says when the device drew nothing.
CATALOGUE: dict[str, dict[str, Any]] = {
    # From the drawing's process (round 15 thread D, meas-2026-10-19.md)
    "meas_air": {"label": "Pen's flight", "place": "over",
                 "shown": [("level", "Lifts between each"), ("min_gap", "Shortest lift, mm"),
                           ("number_every", "Number every n-th landing")],
                 "empty": "Nothing to read: the pen never lifts between lines here."},
    "meas_ledger": {"label": "Ledger", "place": "beside", "side": "right", "size": 110.0,
                    "shown": [("drawn_by", "Rules drawn by"), ("by", "One row per"),
                              ("index", "Ring each row's start on the drawing")],
                    "slow": "slow while a hand draws the rules (about 30 s on a busy study); "
                            "straight rules draw at once",
                    "empty": "Nothing to read: this study has no steps to list."},
    "meas_arcs": {"label": "Arcs of the score", "place": "beside", "side": "bottom", "size": 50.0,
                  "shown": [("style", "Style"), ("crown", "Tallest arc")],
                  "empty": "Nothing to read: this study records no score or arranger log, so there are "
                           "no relations to draw."},
    "meas_inventory": {"label": "Inventory", "place": "beside", "side": "right", "size": 100.0,
                       "shown": [("by", "Items"), ("name", "Named by"), ("index", "Number them on the drawing")],
                       "empty": "Nothing to read: this study has no steps to take apart."},
    "meas_stations": {"label": "Stations (river km / dance seconds)", "place": "beside", "side": "bottom",
                      "size": 40.0, "shown": [("stations", "Stations"), ("label_every", "Number every n-th"),
                                                ("on_line", "Tick the drawing too")],
                      "empty": "Nothing to read: this study's lines carry no source clock "
                               "(river km or dance seconds)."},
    "meas_turning": {"label": "Turning fan", "place": "beside", "side": "bottom", "size": 65.0,
                     "shown": [("x", "Length axis"), ("min_len", "Shortest line, mm"), ("name", "Lines named")],
                     "empty": "Nothing to read: no line is long enough to turn."},
    "meas_roll": {"label": "Roll", "place": "beside", "side": "bottom", "size": 40.0,
                  "shown": [("by", "Notes"), ("lanes", "One lane per"), ("shape", "Note shape")],
                  "empty": "Nothing to read: this study has no lines to lay on a roll."},
    # General (measg1 / measg2): read the finished ink only
    "scale_ruler": {"label": "Scale ruler", "place": "margin", "side": "bottom", "size": 22.0,
                    "shown": [("anchor", "Measures"), ("label_h", "Number height, mm")]},
    "density_isoline": {"label": "Density contours", "place": "over",
                        "shown": [("sigma", "Blur, mm"), ("levels", "Contours"), ("min_length", "Shortest contour, mm")]},
    "heading_rose": {"label": "Heading rose", "place": "beside", "side": "right", "size": 60.0,
                     "shown": [("bins", "Bins over 180 degrees"), ("smooth", "Smoothing, bins")]},
    "arc_ticks": {"label": "Arc-length ticks", "place": "over",
                  "shown": [("which", "Lines"), ("every", "Tick every, mm"), ("major_every", "Number every n-th tick")]},
    "survey_marks": {"label": "Survey marks", "place": "over",
                     "shown": [("principal_axis", "Principal axis"), ("cross", "Crosshair size, mm")]},
    "misfit_grid": {"label": "Misfit grid", "place": "under", "params": {"strength": 2.0},
                    "shown": [("pitch", "Grid pitch, mm"), ("strength", "Pull toward the ink, mm"),
                              ("clear", "Clearance from the ink, mm")],
                    "slow": "slow: 1 to 15 s, most of it keeping the grid clear of the ink (clearance 0 is quicker)"},
}
GENERAL_EMPTY = "Drew nothing on this drawing."
# `slow` (measured 2026-10-19 on listen / danced_chain / river_zoom at the bench
# defaults, this Mac): a device past ~2 s on a typical study is badged in the
# bench. Every other device takes under 0.25 s.


class DeviceError(ValueError):
    pass


@functools.lru_cache(maxsize=1)
def _registry() -> dict:
    # numpy-only imports here: the freeze script runs this module in the research venv
    from . import kit as _kit  # noqa: PLC0415
    _kit.discover()
    from .kit import _devices  # noqa: PLC0415
    missing = sorted(set(CATALOGUE) - set(_devices._DEVICES))
    if missing:
        raise RuntimeError(f"frozen kit lacks devices {missing}; refreeze (tools/gesture_studies/freeze.py)")
    return _devices._DEVICES


def _flexoki() -> dict[str, str]:
    from .kit import arrangers_oehlen_found  # noqa: PLC0415 — the same table as studies.flexoki()
    return dict(arrangers_oehlen_found.FLEXOKI)


def _param_doc(p) -> dict[str, Any]:
    out = {"name": p.name, "type": p.type, "default": p.default, "help": p.doc}
    if p.type in ("int", "float"):
        out.update(min=p.min, max=p.max)
    if p.type == "choice":
        out["choices"] = list(p.choices)
    return out


def catalogue() -> list[dict[str, Any]]:
    """The devices the bench offers, in its order, with their default spec
    (placement + any param override) and the params it shows as controls."""
    reg = _registry()
    out = []
    for did, c in CATALOGUE.items():
        d = reg[did]
        params = {p.name: p for p in d.params}
        spec = {"id": did, "place": c["place"]}
        if c["place"] in SIDES:
            spec.update(side=c.get("side", SIDES[c["place"]][0]), size=c.get("size", DEFAULT_SIZE[c["place"]]))
        spec.update(c.get("params", {}))
        out.append({"id": did, "label": c["label"], "family": d.family, "doc": d.doc,
                    "default": spec, "shown": [{**_param_doc(params[n]), "label": lab} for n, lab in c["shown"]],
                    "params": [_param_doc(p) for p in d.params],
                    "empty": c.get("empty", GENERAL_EMPTY), "slow": c.get("slow", "")})
    return out


def default_spec(did: str) -> dict[str, Any]:
    return next(c["default"] for c in catalogue() if c["id"] == did)


def _num(v, kind: str, where: str):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise DeviceError(f"{where} must be a number")
    if not math.isfinite(float(v)):
        raise DeviceError(f"{where} must be finite")
    if kind == "int":
        if float(v) != int(v):
            raise DeviceError(f"{where} must be a whole number")
        return int(v)
    return float(v)


def _string(did: str, p, v, lib) -> str:
    where = f"{did}.{p.name}"
    if not isinstance(v, str) or len(v) > 120:
        raise DeviceError(f"{where} must be a short string")
    if p.name in ("ink", "bars"):
        if v not in set(_flexoki()) | {"source"}:
            raise DeviceError(f"{where} must be a Flexoki ink name or 'source' (each line's own ink)")
        return v
    if p.name in ("kinds", "exclude"):
        if v.strip() and not _WORDS.match(v.strip()):
            raise DeviceError(f"{where} must be words separated by commas")
        return v.strip()
    if p.name == "drawn_by":
        if v and (lib is None or v not in lib.ids("hand")):
            raise DeviceError(f"{where}: {v!r} is not a hand in this library")
        return v
    raise DeviceError(f"{where} is not settable here")


def check_specs(specs: Any, lib=None) -> list[dict[str, Any]]:
    """A layer's `devices` list, validated and normalised (numbers bounded,
    choices closed, unknown keys refused). `lib`: the layer's frozen library
    (the ledger's `drawn_by` must be one of its hands)."""
    if specs is None:
        return []
    if not isinstance(specs, list):
        raise DeviceError("devices must be a list")
    if len(specs) > MAX_DEVICES:
        raise DeviceError(f"at most {MAX_DEVICES} devices")
    reg = _registry()
    out, seen = [], set()
    for spec in specs:
        if not isinstance(spec, dict) or not isinstance(spec.get("id"), str):
            raise DeviceError("each device is an object with an id")
        did = spec["id"]
        if did not in reg or did not in CATALOGUE:
            raise DeviceError(f"unknown device {did!r}; known: {sorted(CATALOGUE)}")
        if did in seen:
            raise DeviceError(f"device {did!r} is listed twice")
        seen.add(did)
        place = spec.get("place", CATALOGUE[did]["place"])
        if place not in PLACES:
            raise DeviceError(f"{did}.place must be one of {list(PLACES)}")
        norm: dict[str, Any] = {"id": did, "place": place}
        if place in SIDES:
            side = spec.get("side", SIDES[place][0])
            if side not in SIDES[place]:
                raise DeviceError(f"{did}.side must be one of {list(SIDES[place])} when {place}")
            lo, hi = SIZE[place]
            size = _num(spec.get("size", DEFAULT_SIZE[place]), "float", f"{did}.size")
            if not lo <= size <= hi:
                raise DeviceError(f"{did}.size={size} outside [{lo}, {hi}] mm")
            norm.update(side=side, size=size)
        params = {p.name: p for p in reg[did].params}
        for k, v in spec.items():
            if k in ("id", "place", "side", "size"):
                continue
            p = params.get(k)
            if p is None:
                raise DeviceError(f"{did} has no param {k!r}")
            where = f"{did}.{k}"
            if p.type in ("int", "float"):
                v = _num(v, p.type, where)
                if (p.min is not None and v < p.min) or (p.max is not None and v > p.max):
                    raise DeviceError(f"{where}={v} outside [{p.min}, {p.max}]")
            elif p.type == "bool":
                if not isinstance(v, bool):
                    raise DeviceError(f"{where} must be true or false")
            elif p.type == "choice":
                if v not in p.choices:
                    raise DeviceError(f"{where} must be one of {list(p.choices)}")
            else:
                v = _string(did, p, v, lib)
            norm[k] = v
        out.append(norm)
    return out


def grown_frame(frame: tuple[float, float], specs: list[dict]) -> tuple[float, float]:
    """The frame after `apply_devices` (each `beside` panel grows it), without
    running anything: the arithmetic of `_devices.apply_devices`."""
    W, H = float(frame[0]), float(frame[1])
    for s in specs:
        if s.get("place") == "beside":
            size = float(s.get("size", DEFAULT_SIZE["beside"]))
            if s.get("side", "right") == "right":
                W += size
            else:
                H += size
    return W, H


def named_hands(specs: list[dict]) -> list[str]:
    """Library hands the devices name (the ledger's hand-drawn rules), so a
    kept layer pins them like the study's own hands."""
    out = []
    for s in specs:
        if s["id"] == "meas_ledger":
            hand = s.get("drawn_by", next(p.default for p in _registry()["meas_ledger"].params
                                          if p.name == "drawn_by"))
            if hand:
                out.append(hand)
    return out


# ---------------------------------------------------------------------------
# applying
# ---------------------------------------------------------------------------

_LOCK = threading.RLock()
_NOTES: dict[str, dict[str, Any]] = {}
# one device's inks by (sheet, device, its context, its params): toggling a quick
# device beside a slow one (the hand-drawn ledger) never redraws the slow one
_MEMO: "OrderedDict[tuple, tuple]" = OrderedDict()
_MEMO_MAX = 48


def _guarded(did: str, fn, memo_key: str | None):
    """The frozen device with the app around it: cancellable, timed, memoised
    per sheet, and a KitError (a device refusing this drawing) becomes a note,
    not a failure."""
    from .kit.core import KitError  # noqa: PLC0415

    @functools.wraps(fn)
    def wrapped(dctx, sheet, **kw):
        key = None if memo_key is None else (memo_key, did, repr(dctx), repr(sorted(kw.items())))
        if key is not None and key in _MEMO:
            _MEMO.move_to_end(key)
            out, note = _MEMO[key]
            _NOTES[did] = dict(note)
            return list(out)
        checkpoint()
        t0 = time.perf_counter()
        try:
            out = fn(dctx, sheet, **kw)
        except KitError as e:
            _NOTES[did] = {"error": str(e)}
            out = []
        _NOTES.setdefault(did, {})["seconds"] = round(time.perf_counter() - t0, 3)
        if key is not None:
            _MEMO[key] = (tuple(out), dict(_NOTES[did]))
            while len(_MEMO) > _MEMO_MAX:
                _MEMO.popitem(last=False)
        checkpoint()
        return out
    wrapped._gs_device = True
    return wrapped


def apply(sheet, specs: list[dict], lib, memo_key: str | None = None) -> tuple[Any, list[dict[str, Any]]]:
    """`specs` (checked) laid on `sheet` → (new sheet, one note per spec:
    {"id", "inks", "seconds", "error"?}). The input sheet is unchanged.
    `memo_key` names the sheet (and library) for the per-device memo; None = no memo."""
    import dataclasses  # noqa: PLC0415

    from .kit import _devices  # noqa: PLC0415
    from .kit import library as _kl  # noqa: PLC0415
    reg = _registry()
    with _LOCK:
        saved = {did: reg[did] for did in (s["id"] for s in specs)}
        old_default, old_root = _kl._DEFAULT, _kl.ROOT
        try:
            for did, d in saved.items():
                reg[did] = dataclasses.replace(d, fn=_guarded(did, d.fn, memo_key))
            # the layer's own library (see the module doc); ROOT too, or `default()` would swap it out
            _kl._DEFAULT, _kl.ROOT = lib, lib.root
            _NOTES.clear()
            out = _devices.apply_devices(sheet, specs)
            notes = []
            counts: dict[str, int] = {}
            for ink in out.inks:
                m = ink.meta or {}
                if m.get("layer") == "device":
                    counts[m.get("device")] = counts.get(m.get("device"), 0) + 1
            for s in specs:
                n = {"id": s["id"], "inks": counts.get(s["id"], 0), **_NOTES.get(s["id"], {})}
                notes.append(n)
            return out, notes
        finally:
            reg.update(saved)
            _kl._DEFAULT, _kl.ROOT = old_default, old_root
            _NOTES.clear()
