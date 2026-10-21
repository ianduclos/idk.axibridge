# FROZEN from research commit 6f96418: tools/gesture/gesture/kit/devices_meas_stations.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Device `meas_stations` (round 15, thread D `meas`): the source's own clock
read off the line. A river_zoom line carries `u_km` (km of real river under
each point); a dance carries `dance_t` (seconds into the dance). Stations at
round values of that clock are ticked across the line — they crowd where
the zoom is far (many km per mm) and spread where it is close — and, in a
margin or beside panel, the same line is laid straight with the same
stations: a scale bar whose scale changes, the zoom schedule made legible
without a chart. Lines that carry no clock get nothing (it never invents one)."""
from __future__ import annotations

import numpy as np

from . import devices_meas_read as R
from ._devices import device
from .core import P

CLOCKS = {"km": ("u_km", "KM"), "seconds": ("dance_t", "S")}


def _clocks(marks, which: str):
    """[(channel, unit, marks)] for each clock present (auto: every one, km first)."""
    names = ("km", "seconds") if which == "auto" else (which,)
    out = []
    for name in names:
        ch, unit = CLOCKS[name]
        got = [m for m in marks if ch in m.channels and np.isfinite(np.asarray(m.channels[ch], float)).any()]
        if got:
            out.append((ch, unit, got))
    return out


def crossings(p: np.ndarray, c: np.ndarray, step: float):
    """(point index float, clock value) where c crosses a multiple of step."""
    c = np.asarray(c, float)
    ok = np.isfinite(c)
    out = []
    if ok.sum() < 2:
        return out
    k = np.floor(c / step)
    for i in np.flatnonzero(ok[:-1] & ok[1:] & (k[1:] != k[:-1])):
        lo, hi = sorted((c[i], c[i + 1]))
        for j in range(int(np.floor(lo / step)) + 1, int(np.floor(hi / step)) + 1):
            v = j * step
            t = (v - c[i]) / (c[i + 1] - c[i]) if c[i + 1] != c[i] else 0.0
            out.append((i + float(np.clip(t, 0, 1)), v))
    return out


def _at(p: np.ndarray, fi: float):
    i = int(np.clip(np.floor(fi), 0, len(p) - 2))
    t = fi - i
    return p[i] * (1 - t) + p[i + 1] * t, i


@device("meas_stations", family="process", params=[
    P("clock", "choice", "auto", "which source clock: auto (river km, else dance seconds) | km | seconds",
      choices=("auto", "km", "seconds")),
    P("stations", "int", 28, "about how many stations over the clock's whole range", min=4, max=300),
    P("label_every", "int", 4, "number every n-th station", min=1, max=60),
    P("tick", "float", 1.3, "half-length of a station tick across the line, mm", min=0.2, max=10.0),
    P("label_h", "float", 1.5, "label cap height, mm", min=0.6, max=6.0),
    P("on_line", "bool", True, "margin/beside: also tick the drawing itself"),
    P("pen", "float", 0.18, "pen, mm", min=0.05, max=1.5),
    P("ink", "str", "source", "Flexoki ink name, or 'source' (each line's own ink)"),
], doc="the source's own clock (river km / dance seconds) ticked along the line; laid straight as a "
       "scale bar whose scale changes, in a margin or beside")
def meas_stations(dctx, sheet, *, clock, stations, label_every, tick, label_h, on_line, pen, ink):
    ms = R.drawing_marks(sheet)
    found = _clocks(ms, clock)
    if not found:
        return []
    us = {id(m): u for u in R.units(sheet, "line") for m in u.marks}
    allp = np.vstack([np.asarray(m.points, float) for m in ms])
    out, lay = [], []
    for ch, unit, marks in found:
        vals = np.concatenate([np.asarray(m.channels[ch], float) for m in marks])
        vals = vals[np.isfinite(vals)]
        span = float(np.ptp(vals)) if len(vals) else 0.0
        if span <= 0:
            continue
        step = R.nice(span / stations)
        first_label = True
        for m in marks:
            p = np.asarray(m.points, float)
            s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
            col = R.ink_for(ink, us.get(id(m)))
            polys, labs, st = [], [], []
            for fi, v in crossings(p, m.channels[ch], step):
                q, i = _at(p, fi)
                nrm = R.normal_at(p, i)
                st.append((float(np.interp(fi, np.arange(len(s)), s)), v))
                if dctx.place in ("over", "under") or on_line:
                    polys.append(np.array([q - nrm * tick, q + nrm * tick]))
                    if round(v / step) % label_every == 0:
                        lab = f"{v:g}" + (f" {unit}" if first_label else "")
                        first_label = False
                        labs += R.side_label(q, nrm, lab, label_h, allp, gap=tick + 0.6)
            out += R.inks(polys + labs, pen=pen, colour=col, role="station")
            lay.append((m, s[-1], st, col, ch, step))
    if lay and dctx.place in ("margin", "beside"):
        out += _bar(dctx, lay, label_every=label_every, label_h=label_h, pen=pen)
    return out


def _bar(dctx, lay, *, label_every, label_h, pen):
    """The clocked lines laid straight end to end (drawing order), stations ticked."""
    x0, y0, w, h = dctx.region
    pad = 0.08 * min(w, h) + 2.0
    vertical = h > 1.6 * w
    gap = 3.0
    total = sum(t[1] for t in lay) + gap * (len(lay) - 1)
    span = (h if vertical else w) - 2 * pad
    k = span / max(total, 1e-9)
    out = []
    pos = 0.0
    tk = max(1.2 * label_h, 1.5)
    for m, L, st, col, ch, step in lay:
        polys = []
        a, b = pos, pos + L * k
        if vertical:
            xb = x0 + w * 0.35
            polys.append(np.array([[xb, y0 + pad + a], [xb, y0 + pad + b]]))
        else:
            yb = y0 + h * 0.42
            polys.append(np.array([[x0 + pad + a, yb], [x0 + pad + b, yb]]))
        for sv, v in st:
            t = pos + sv * k
            big = round(v / step) % label_every == 0
            ln = tk * (1.0 if big else 0.55)
            if vertical:
                polys.append(np.array([[xb, y0 + pad + t], [xb + ln, y0 + pad + t]]))
                if big:
                    polys += R.text(f"{v:g}", xb + ln + 0.8, y0 + pad + t - label_h / 2, label_h)
            else:
                polys.append(np.array([[x0 + pad + t, yb], [x0 + pad + t, yb + ln]]))
                if big:
                    polys += R.text(f"{v:g}", x0 + pad + t, yb + ln + 0.8, label_h, anchor="centre")
        out += R.inks(polys, pen=pen, colour=col, role="bar")
        pos = b + gap * k
    drawn = sum(t[1] for t in lay)
    note = f"{drawn:.0f} MM DRAWN"
    for ch, unit in (("u_km", "KM OF RIVER"), ("dance_t", "S OF DANCE")):
        mm = [t[0] for t in lay if t[4] == ch]
        if mm:
            if ch == "u_km":
                v = sum(float(np.nanmax(m.channels[ch]) - np.nanmin(m.channels[ch])) for m in mm)
            else:
                v = max(float(np.nanmax(m.channels[ch])) for m in mm) - min(float(np.nanmin(m.channels[ch]))
                                                                           for m in mm)
            note += f"  {v:.0f} {unit}" if ch == "u_km" else f"  {v:.1f} {unit}"
    z = [np.asarray(t[0].channels["zoom"], float) for t in lay if "zoom" in t[0].channels]
    if z:
        zz = np.concatenate(z)
        note += f"  ZOOM {np.nanmin(zz):.0f}-{np.nanmax(zz):.0f}"
    if vertical:
        polys = R.text(note[:28], x0 + 1.0, y0 + h - pad + 1.0, 0.8 * label_h)
    else:
        polys = R.text(note, x0 + pad, y0 + h * 0.42 - 1.0 - 1.6 * label_h, 0.8 * label_h)
    out += R.inks(polys, pen=pen, colour=lay[0][3], role="bar")
    return out
