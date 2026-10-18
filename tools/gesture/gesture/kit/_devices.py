"""Measuring devices (round 15 contract, lead-owned): layers that read a
finished drawing and lay their reading beside, over, under or in the margin
of it. Ian, 2026-10-19: "a selection of these to be added as a separate
layer"; he likes the ones with "direct correlations to your process, corpuses
used", and general ones "if they are interesting".

A device is a function of the finished `Sheet` (its marks with channels, its
inks, its meta: recipe, library ids, `notes["score"]` from `_score.py`) and a
`region` it draws into. It returns `Ink`s in sheet mm. It must read something
true about the drawing (its process or its geometry), never decorate.

    from ._devices import device, apply_devices
    from .core import P, Ink

    @device("heading_rose", params=[P("bins", "int", 24, "…", min=6, max=72)],
            family="general", doc="…")
    def heading_rose(dctx, sheet, *, bins):
        x0, y0, w, h = dctx.region
        ...
        return [Ink(points, closed=False, filled=False, pen=0.2, meta={"device": "heading_rose"})]

    out = apply_devices(sheet, [{"id": "heading_rose", "place": "margin", "bins": 36}])
    kit.preview(out, "…jpg")      # works: `out` is an ordinary Sheet

Placement (`place`), decided by `apply_devices`, never by the device:
- "over":   region = the drawing's box; device inks sit on the drawing.
- "under":  same region; device inks come first, so pens draw them first.
- "margin": a strip along one side inside the frame (`side` top|bottom|left|right, `size` mm).
- "beside": the frame grows by a panel (`side` right|bottom, `size` mm); the
            region is that panel. This is the round-10 pairing.
Every device ink carries meta {"layer": "device", "device": id}.

Devices register in files named `devices_<prefix>_*.py` that import this
module; they are discovered with the rest of the kit (the module import runs
the decorator). Ids are global; `device_list()` shows them.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Callable

import numpy as np

from .core import Ink, KitError, P, Param, Sheet, tag

_DEVICES: dict[str, "Device"] = {}


@dataclass(frozen=True)
class Device:
    id: str
    fn: Callable
    params: tuple
    family: str          # "process" | "general"
    doc: str


@dataclass(frozen=True)
class DCtx:
    frame: tuple[float, float]
    region: tuple[float, float, float, float]
    drawing_box: tuple[float, float, float, float]
    place: str
    seed: int
    device: str

    def rng(self, *tags) -> np.random.Generator:
        return np.random.default_rng([tag(self.seed), tag("device"), tag(self.device), *map(tag, tags)])


def device(id: str, *, params=(), family: str = "general", doc: str = ""):
    if family not in ("process", "general"):
        raise KitError(f"device {id!r}: family must be 'process' or 'general'")
    for p in params:
        if not isinstance(p, Param):
            raise KitError(f"device {id!r}: params must be P(...)")

    def wrap(fn):
        if id in _DEVICES and _DEVICES[id].fn is not fn:
            raise KitError(f"device id {id!r} is already registered")
        _DEVICES[id] = Device(id, fn, tuple(params), family, doc)
        return fn
    return wrap


def device_list() -> list[dict]:
    return [{"id": d.id, "family": d.family, "doc": d.doc,
             "params": [{"name": p.name, "type": p.type, "default": p.default} for p in d.params]}
            for d in sorted(_DEVICES.values(), key=lambda d: d.id)]


def _params(d: Device, spec: dict) -> dict:
    out = {}
    for p in d.params:
        v = spec.get(p.name, p.default)
        if p.type in ("int", "float") and v is not None:
            lo, hi = p.min, p.max
            v = (int if p.type == "int" else float)(v)
            if lo is not None and v < lo or hi is not None and v > hi:
                raise KitError(f"device {d.id!r}: {p.name}={v} outside [{lo}, {hi}]")
        out[p.name] = v
    return out


def _drawing_box(sheet: Sheet) -> tuple[float, float, float, float]:
    pts = [k.points for k in sheet.inks if (k.meta or {}).get("layer") != "device" and len(k.points)]
    if not pts:
        W, H = sheet.frame
        return (0.0, 0.0, W, H)
    a = np.concatenate(pts)
    lo, hi = a.min(axis=0), a.max(axis=0)
    return (float(lo[0]), float(lo[1]), float(hi[0] - lo[0]), float(hi[1] - lo[1]))


def apply_devices(sheet: Sheet, specs: list[dict]) -> Sheet:
    """Lay devices on a finished sheet → a new Sheet (the input is unchanged).
    Each spec: {"id", "place": over|under|margin|beside, "side", "size", **params}."""
    W, H = sheet.frame
    inks_under: list[Ink] = []
    inks_over: list[Ink] = []
    applied = []
    seed = int(sheet.meta["recipe"]["seed"])
    for i, spec in enumerate(specs):
        if spec["id"] not in _DEVICES:
            raise KitError(f"unknown device {spec['id']!r}; known: {sorted(_DEVICES)}")
        d = _DEVICES[spec["id"]]
        place = spec.get("place", "over")
        side = spec.get("side", "right" if place == "beside" else "bottom")
        size = float(spec.get("size", 60.0 if place == "beside" else 22.0))
        box = _drawing_box(sheet)
        if place in ("over", "under"):
            region = box
        elif place == "margin":
            region = {"top": (0.0, 0.0, W, size), "bottom": (0.0, H - size, W, size),
                      "left": (0.0, 0.0, size, H), "right": (W - size, 0.0, size, H)}[side]
        elif place == "beside":
            if side == "right":
                region = (W, 0.0, size, H)
                W = W + size
            else:
                region = (0.0, H, W, size)
                H = H + size
        else:
            raise KitError(f"device {d.id!r}: unknown place {place!r}")
        dctx = DCtx((W, H), tuple(float(v) for v in region), box, place, seed + 1000 * (i + 1), d.id)
        out = d.fn(dctx, sheet, **_params(d, spec))
        tagged = [Ink(k.points, k.closed, k.filled, k.pen,
                      {**(k.meta or {}), "layer": "device", "device": d.id}) for k in out]
        (inks_under if place == "under" else inks_over).extend(tagged)
        applied.append({**copy.deepcopy(spec), "place": place, "region": list(region)})
    meta = copy.deepcopy(sheet.meta)
    meta["devices"] = meta.get("devices", []) + applied
    return Sheet((W, H), list(sheet.marks), inks_under + list(sheet.inks) + inks_over, meta)
