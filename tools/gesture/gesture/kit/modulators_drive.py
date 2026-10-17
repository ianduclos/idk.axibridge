"""Round 12, thread `drive` — sources as DRIVERS, not hands.

For eleven rounds every source became a new line grammar. Here a source's
kinematics STEER a drawing that an existing hand makes; the source never
draws its own shape. A driver is a time series (library kind
`drive_signal`, frozen by experiments/drive_sources.py): a window of it is
laid along the part's marks by arc length (the whole window spans the whole
part, marks in order, like `timing`), then mapped to ink channels.

Common params (every drive_* modulator):
  driver     library `drive_signal` id
  channel    the series to read (entry.json lists them)
  transform  value | abs | rate | absrate | envelope | highpass — computed on
             the SOURCE series (seconds), before it is laid on the line
  start/span the window, as shares of the recording
  norm       window (p2..p98 of the window → 0..1) | record (of the whole
             recording) | signed (0 stays 0, p98 |x| → ±1)
  smooth     σ along the line, mm (after mapping onto the line)
  invert, gamma
Mapped value u (0..1, or −1..1 for signed) then becomes:

  drive_width   u → `dw`, the full ink width in mm (lo..hi). `drive_ink`
                sweeps a disc of that width along the line, line-built.
  drive_regime  u → r by thresholds with hysteresis: wire / nib / mass
                (W, M from params); for the `nib` renderer.
  drive_pen     u → `pen_i` (categorical): which pen inks this stretch,
                with hysteresis and a minimum run (pen changes are
                expensive on a plotter; a flicker is a dud).
  drive_knots   pauses (u below thr for at least min_s seconds of DRIVER
                time) → `knot` (0..1 peak at the pause centre, sized by
                the pause's duration) and `emphasis` (so dev_beads / swell
                can ink them too).
  drive_tremor  the signal's own fast part (u − its smooth, band mm) →
                lateral displacement of the line (mm, p95 = amount),
                written to `tremor` as well.

Every modulator records what it did in meta["drive"] (driver, channel,
window in seconds, mm per driver-second, mapping) and writes the
normalised RAW driver value along the line as channel `drv_<target>` (and
the mapped value as `drvm_<target>`), so `drive_beside` can draw the
measurement beside the drawing. Seeds are not needed: drivers are data.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from . import library
from .core import P, channel_kind, modulator

KIND = "drive_signal"
TRANSFORMS = ("value", "abs", "rate", "absrate", "envelope", "highpass")
NORMS = ("window", "record", "signed")

channel_kind("pen_i", "nearest")
channel_kind("drv_pen", "linear")


@library.loader(KIND)
def _load_driver(entry: dict, folder):
    arr = library.read_npz(folder / entry["files"]["series"])
    t = np.asarray(arr.pop("t"), np.float64)
    return {"entry": entry, "t": t, "series": {k: np.asarray(v, np.float64) for k, v in arr.items()}}


def transform(t: np.ndarray, x: np.ndarray, how: str, tau: float) -> np.ndarray:
    """A derived series on the source clock (tau: seconds, for envelope /
    highpass windows and rate smoothing)."""
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 1.0
    sig = max(tau / dt, 0.5)
    if how == "value":
        return x
    if how == "abs":
        return np.abs(x)
    if how in ("rate", "absrate"):
        r = np.gradient(gaussian_filter1d(x, sig), t)
        return np.abs(r) if how == "absrate" else r
    if how == "highpass":
        return x - gaussian_filter1d(x, sig)
    if how == "envelope":
        hp = x - gaussian_filter1d(x, sig)
        return np.sqrt(gaussian_filter1d(hp * hp, sig))
    raise ValueError(how)


COMMON = [
    P("driver", "ref", "drive_mosquito", "the driver (library drive_signal)", kind=KIND),
    P("channel", "str", "steer", "series to read (see the entry's channels)"),
    P("transform", "choice", "value", "value | abs | rate | absrate | envelope | highpass (on the source clock)",
      choices=TRANSFORMS),
    P("tau", "float", 1.0, "transform window, driver seconds (rate smoothing, envelope, highpass)",
      min=1e-3, max=1e7),
    P("start", "float", 0.0, "window start, share of the recording", min=0.0, max=1.0),
    P("span", "float", 0.1, "window length, share of the recording (the whole window spans the part)",
      min=1e-5, max=1.0),
    P("norm", "choice", "window", "window: p2..p98 of the window → 0..1 | record: of the whole recording | "
      "signed: 0 stays 0, p98 |x| → ±1", choices=NORMS),
    P("smooth", "float", 1.0, "σ along the line after mapping, mm", min=0.0, max=300.0),
    P("stretch", "bool", False, "after smoothing, stretch back to the full range (p98 of the smoothed window → 1), "
      "so smoothing a noisy driver does not silence it"),
    P("invert", "bool", False, "u → 1 − u (signed: −u)"),
    P("gamma", "float", 1.0, "u → u^gamma (signed: sign·|u|^gamma)", min=0.1, max=8.0),
    P("step", "float", 0.5, "resampling step along the line, mm", min=0.1, max=5.0),
]


def _live(marks):
    return [i for i, m in enumerate(marks) if len(m) >= 2 and m.length() > 0]


def _resampled(m, step):
    d = np.diff(m.arclength())
    if len(d) and abs(float(np.median(d)) - step) <= 0.15 * step and d.max() <= 2.0 * step:
        return m
    return m.resampled(step)


def lay(ctx, marks, prm: dict, target: str):
    """Lay the driver window along the part's marks.
    → (marks resampled, {i: (raw u, mapped-ready u)}, record)."""
    d = ctx.use(KIND, prm["driver"])
    ser = d["series"]
    if prm["channel"] not in ser:
        raise ValueError(f"driver {prm['driver']!r} has no channel {prm['channel']!r}; it has {sorted(ser)}")
    t = d["t"]
    x = transform(t, ser[prm["channel"]], prm["transform"], prm["tau"])
    T = float(t[-1] - t[0])
    t0 = float(t[0] + prm["start"] * T)
    span = float(prm["span"] * T)
    t0 = min(t0, float(t[-1]) - span) if span < T else float(t[0])
    t1 = t0 + span
    live = _live(marks)
    out = list(marks)
    rs = {i: _resampled(marks[i], prm["step"]) for i in live}
    Ls = {i: rs[i].length() for i in live}
    Ltot = sum(Ls.values()) or 1.0
    win = (t >= t0) & (t <= t1)
    xs = x[win] if win.sum() >= 2 else x
    if prm["norm"] == "record":
        lo, hi = np.percentile(x, [2, 98])
    elif prm["norm"] == "window":
        lo, hi = np.percentile(xs, [2, 98])
    else:
        lo, hi = 0.0, float(np.percentile(np.abs(xs), 98))
    hi = hi if hi > lo else lo + 1e-9
    # anti-alias: average the source over one line step before sampling
    sec_per_mm = span / Ltot
    dts = float(np.median(np.diff(t))) if len(t) > 1 else 1.0
    sig_src = 0.5 * prm["step"] * sec_per_mm / dts
    xa = gaussian_filter1d(x, sig_src) if sig_src > 0.5 else x
    vals = {}
    off = 0.0
    if not live:
        return out, rs, vals, {}, live
    for i in live:
        s = rs[i].arclength()
        ts = t0 + (s + off) / Ltot * span
        raw = np.interp(ts, t, xa)
        if prm["norm"] == "signed":
            u = np.clip(raw / hi, -1.0, 1.0)
        else:
            u = np.clip((raw - lo) / (hi - lo), 0.0, 1.0)
        v = u.copy()
        if prm["smooth"] > 0 and len(v) > 2:
            v = gaussian_filter1d(v, prm["smooth"] / prm["step"], mode="nearest")
        vals[i] = (u, v, ts)
        off += Ls[i]
    if prm["stretch"] and prm["smooth"] > 0:
        allv = np.concatenate([np.abs(vals[i][1]) for i in live])
        k = 1.0 / max(float(np.percentile(allv, 98)), 1e-9)
        vals = {i: (u, np.clip(v * k, -1.0, 1.0), ts) for i, (u, v, ts) in vals.items()}
    for i in live:
        u, v, ts = vals[i]
        if prm["invert"]:
            v = -v if prm["norm"] == "signed" else 1.0 - v
        vals[i] = (u, np.sign(v) * np.abs(v) ** prm["gamma"], ts)
    rec = {"target": target, "driver": prm["driver"], "channel": prm["channel"], "transform": prm["transform"],
           "t0_s": round(t0 - float(t[0]), 3), "span_s": round(span, 3), "line_mm": round(Ltot, 2),
           "mm_per_driver_s": round(Ltot / span, 6) if span > 0 else None, "norm": prm["norm"],
           "lo": float(lo), "hi": float(hi), "signed": prm["norm"] == "signed",
           "smooth_mm": prm["smooth"], "stretch": prm["stretch"], "gamma": prm["gamma"], "invert": prm["invert"]}
    return out, rs, vals, rec, live


def _stamp(m, rec, target, u, v, extra_channels, points=None, extra_meta=None):
    drive = list(m.meta.get("drive", [])) + [rec]
    ch = {f"drv_{target}": u, f"drvm_{target}": v, **extra_channels}
    md = {"drive": drive, **(extra_meta or {})}
    return m.evolve(points=points, channels=ch, meta=md)


def _pick(prm, names):
    return {k: prm[k] for k in names}


# ---------------------------------------------------------------------------
# width
# ---------------------------------------------------------------------------

@modulator("drive_width", params=COMMON + [
    P("lo", "float", 0.4, "ink width at u = 0, mm (≈ the pen: a wire)", min=0.05, max=20.0),
    P("hi", "float", 6.0, "ink width at u = 1, mm", min=0.05, max=40.0),
    P("floor", "float", 0.0, "u below this is held at 0 (a quiet line stays a wire)", min=0.0, max=0.95),
    P("side", "choice", "abs", "signed drivers: abs (both signs swell) | pos (only u > 0, e.g. climbing) | neg",
      choices=("abs", "pos", "neg")),
    P("write", "choice", "dw", "dw: drive_ink's swept width | W: the nib width (nib renderers) | M: the mass width",
      choices=("dw", "W", "M")),
], doc="a driver steers the line's ink width (dw, mm): its speed / climb swells the line",
    reach=lambda p: 0.5 * max(p["hi"], p["lo"]))
def drive_width(ctx, marks, *, lo, hi, floor, side, write, **prm):
    out, rs, vals, rec, live = lay(ctx, marks, prm, "width")
    rec.update(lo_mm=lo, hi_mm=hi, floor=floor, side=side, write=write)
    for i in live:
        u, v, _ = vals[i]
        v = {"abs": np.abs(v), "pos": np.maximum(v, 0.0), "neg": np.maximum(-v, 0.0)}[side]
        v = np.clip(v, 0.0, 1.0)
        v = np.where(v < floor, 0.0, (v - floor) / max(1.0 - floor, 1e-9))
        out[i] = _stamp(rs[i], rec, "width", u, v, {write: lo + (hi - lo) * v})
    return out


# ---------------------------------------------------------------------------
# regime
# ---------------------------------------------------------------------------

def hysteresis_levels(v: np.ndarray, edges: list[float], hyst: float) -> np.ndarray:
    """Quantise v into len(edges)+1 levels; a level changes only when v
    passes an edge by more than hyst (Schmitt trigger)."""
    lev = np.zeros(len(v), dtype=np.int64)
    cur = int(np.searchsorted(edges, v[0])) if len(v) else 0
    for k, x in enumerate(v):
        while cur < len(edges) and x > edges[cur] + hyst:
            cur += 1
        while cur > 0 and x < edges[cur - 1] - hyst:
            cur -= 1
        lev[k] = cur
    return lev


def min_runs(lev: np.ndarray, n_min: int) -> np.ndarray:
    """Absorb runs shorter than n_min samples into the previous run (or the
    next, at the start)."""
    lev = lev.copy()
    if n_min <= 1 or len(lev) == 0:
        return lev
    changed = True
    while changed:
        changed = False
        d = np.nonzero(np.diff(lev))[0] + 1
        starts = np.r_[0, d]
        ends = np.r_[d, len(lev)]
        lens = ends - starts
        if len(lens) <= 1:
            break
        k = int(np.argmin(lens))
        if lens[k] < n_min:
            a, b = starts[k], ends[k]
            lev[a:b] = lev[a - 1] if a > 0 else lev[b]
            changed = True
    return lev


@modulator("drive_regime", params=COMMON + [
    P("nib_at", "float", 0.35, "u above this → nib", min=0.0, max=1.0),
    P("mass_at", "float", 0.8, "u above this → mass", min=0.0, max=1.01),
    P("hyst", "float", 0.05, "hysteresis around the thresholds", min=0.0, max=0.5),
    P("min_run", "float", 4.0, "shortest regime stretch, mm", min=0.0, max=500.0),
    P("W", "float", 2.5, "nib width mm", min=0.1, max=30.0),
    P("M", "float", 7.0, "mass width mm", min=0.5, max=60.0),
    P("ramp", "float", 0.0, "σ of the regime change along the line, mm (0 = a cut; > 0 the ribbon tapers in "
      "and out)", min=0.0, max=100.0),
], doc="a driver steers the regime: quiet → wire, mid → nib, loud → mass (for the nib renderer)",
    reach=lambda p: 0.5 * max(p["W"], p["M"] * 1.25))
def drive_regime(ctx, marks, *, nib_at, mass_at, hyst, min_run, W, M, ramp, **prm):
    out, rs, vals, rec, live = lay(ctx, marks, prm, "regime")
    rec.update(nib_at=nib_at, mass_at=mass_at, hyst=hyst, min_run_mm=min_run, ramp_mm=ramp)
    for i in live:
        u, v, _ = vals[i]
        lev = hysteresis_levels(np.abs(v), [nib_at, mass_at], hyst)
        lev = min_runs(lev, int(round(min_run / prm["step"]))).astype(float)
        if ramp > 0 and len(lev) > 2:
            lev = gaussian_filter1d(lev, ramp / prm["step"], mode="nearest")
        out[i] = _stamp(rs[i], rec, "regime", u, v, {"r": lev, "W": np.full(len(u), W),
                                                     "M": np.full(len(u), M)})
    return out


# ---------------------------------------------------------------------------
# nib angle
# ---------------------------------------------------------------------------

@modulator("drive_phi", params=[p for p in COMMON if p.name not in ("norm", "stretch", "gamma", "invert")] + [
    P("gain", "float", 0.25, "nib turns gain × the driver's angle (degrees); 0 = held at phi0", min=-8.0, max=8.0),
    P("phi0", "float", 35.0, "nib angle at the start, degrees", min=-90.0, max=90.0),
    P("max_rate", "float", 0.0, "soft cap on how fast the nib turns, degrees per mm of line (tanh; 0 = no cap): "
      "a spinning source twists the ribbon steadily instead of barbing it", min=0.0, max=90.0),
], doc="a driver's angle (e.g. a fly's heading) turns the nib: the thick/thin rhythm is the driver's turning")
def drive_phi(ctx, marks, *, gain, phi0, max_rate, **prm):
    prm = {**prm, "norm": "record", "stretch": False, "gamma": 1.0, "invert": False}
    out, rs, vals, rec, live = lay(ctx, marks, prm, "phi")
    d = ctx.use(KIND, prm["driver"])
    x = transform(d["t"], d["series"][prm["channel"]], prm["transform"], prm["tau"])
    rec.update(gain=gain, phi0=phi0, max_rate=max_rate, trace="phi / pi (the nib angle)")
    acc = math.radians(phi0)
    for i in live:
        u, v, ts = vals[i]
        deg = np.interp(ts, d["t"], x)
        if prm["smooth"] > 0 and len(deg) > 2:
            deg = gaussian_filter1d(deg, prm["smooth"] / prm["step"], mode="nearest")
        rate = gain * np.diff(deg) / prm["step"]                      # nib degrees per mm
        if max_rate > 0:
            rate = max_rate * np.tanh(rate / max_rate)
        ang = acc + np.radians(np.r_[0.0, np.cumsum(rate * prm["step"])])
        acc = float(ang[-1])
        phi = np.mod(ang, np.pi)
        out[i] = _stamp(rs[i], rec, "phi", phi / np.pi, phi / np.pi, {"phi": phi})
    return out


# ---------------------------------------------------------------------------
# pens
# ---------------------------------------------------------------------------

PEN_MODES = ("sign", "bands")


@modulator("drive_pen", params=COMMON + [
    P("pens", "str", "black,red,blue", "Flexoki inks (comma list). sign: [quiet, negative, positive]; "
      "bands: low → high"),
    P("mode", "choice", "sign", "sign: |u| below thr = pens[0], else by sign | bands: quantise u into the pens",
      choices=PEN_MODES),
    P("thr", "float", 0.35, "sign: |u| that counts as a turn", min=0.0, max=1.0),
    P("hyst", "float", 0.08, "hysteresis", min=0.0, max=0.5),
    P("min_run", "float", 12.0, "shortest stretch in one pen, mm", min=0.0, max=1000.0),
], doc="a driver decides which pen inks each stretch (multi-pen), with hysteresis and a minimum run")
def drive_pen(ctx, marks, *, pens, mode, thr, hyst, min_run, **prm):
    from .dev_chorus import parse_inks  # noqa: PLC0415
    names = parse_inks(pens)
    out, rs, vals, rec, live = lay(ctx, marks, prm, "pen")
    rec.update(pens=names, mode=mode, thr=thr, hyst=hyst, min_run_mm=min_run)
    for i in live:
        u, v, _ = vals[i]
        if mode == "sign":
            lev3 = hysteresis_levels(v, [-thr, thr], hyst)          # 0 neg, 1 quiet, 2 pos
            lev = np.array([1, 0, 2])[lev3]
        else:
            n = len(names)
            lev = hysteresis_levels(np.abs(v), list(np.arange(1, n) / n), hyst)
        lev = min_runs(lev, int(round(min_run / prm["step"])))
        lev = np.clip(lev, 0, len(names) - 1)
        out[i] = _stamp(rs[i], rec, "pen", u, v, {"pen_i": lev.astype(float)}, extra_meta={"drive_pens": names})
    return out


# ---------------------------------------------------------------------------
# knots at pauses
# ---------------------------------------------------------------------------

@modulator("drive_knots", params=COMMON + [
    P("thr", "float", 0.12, "u below this is a pause", min=0.0, max=1.0),
    P("min_s", "float", 1.0, "shortest pause that earns a knot, DRIVER seconds", min=0.0, max=1e7),
    P("merge_s", "float", 0.5, "pauses closer than this (driver seconds) are one", min=0.0, max=1e7),
    P("full_s", "float", 10.0, "a pause this long (driver s) makes a full-size knot; size ∝ √duration",
      min=1e-3, max=1e8),
    P("width", "float", 1.5, "the knot's emphasis bump half-width along the line, mm", min=0.1, max=50.0),
    P("max_knots", "int", 40, "keep at most this many (the longest pauses)", min=0, max=500),
], doc="the driver's pauses become knots (or beads) on the line, sized by how long the source was still")
def drive_knots(ctx, marks, *, thr, min_s, merge_s, full_s, width, max_knots, **prm):
    out, rs, vals, rec, live = lay(ctx, marks, prm, "knots")
    found = []
    for i in live:
        u, v, ts = vals[i]
        still = np.abs(v) < thr
        d = np.diff(np.r_[0, still.astype(np.int8), 0])
        a, b = list(np.nonzero(d == 1)[0]), list(np.nonzero(d == -1)[0] - 1)
        k = 0
        while k + 1 < len(a):                                       # merge pauses closer than merge_s
            if ts[a[k + 1]] - ts[b[k]] < merge_s:
                b[k] = b.pop(k + 1)
                a.pop(k + 1)
            else:
                k += 1
        for i0, i1 in zip(a, b):
            dur = float(ts[i1] - ts[i0])
            if dur >= min_s:
                found.append((dur, i, (i0 + i1) // 2))
    found.sort(key=lambda f: (-f[0], f[1], f[2]))
    keep = found[:max_knots]
    rec.update(thr=thr, min_s=min_s, full_s=full_s, n_pauses=len(found), n_knots=len(keep),
               knots=[{"mark": i, "dur_s": round(dur, 3)} for dur, i, _ in keep])
    per = {i: [] for i in live}
    for dur, i, c in keep:
        per[i].append((c, min(math.sqrt(dur / full_s), 1.0)))
    for i in live:
        u, v, _ = vals[i]
        s = rs[i].arclength()
        knot = np.zeros(len(s))
        for c, size in per[i]:
            knot = np.maximum(knot, size * np.exp(-0.5 * ((s - s[c]) / width) ** 2))
        e0 = rs[i].channel("emphasis")
        emph = knot if e0 is None else np.maximum(np.asarray(e0), knot)
        out[i] = _stamp(rs[i], rec, "knots", u, v, {"knot": knot, "emphasis": emph})
    return out


# ---------------------------------------------------------------------------
# tremor from the signal's own noise
# ---------------------------------------------------------------------------

@modulator("drive_tremor", params=COMMON + [
    P("amount", "float", 0.6, "p95 lateral displacement, mm", min=0.0, max=10.0),
    P("band", "float", 3.0, "keep only what varies faster than this along the line, mm (σ of the removed "
      "smooth part)", min=0.2, max=200.0),
    P("gate", "float", 1.0, "tremor only where the source is agitated: × (local envelope / p95)^gate "
      "(0 = everywhere alike)", min=0.0, max=6.0),
], doc="the driver's own fast part becomes the line's tremor (lateral displacement, mm)",
    reach=lambda p: 1.5 * p["amount"])
def drive_tremor(ctx, marks, *, amount, band, gate, **prm):
    out, rs, vals, rec, live = lay(ctx, marks, prm, "tremor")
    hp_all = {}
    for i in live:
        u, v, _ = vals[i]
        hp_all[i] = v - gaussian_filter1d(v, band / prm["step"], mode="nearest")
    if gate > 0 and hp_all:
        env = {i: np.sqrt(gaussian_filter1d(h * h, 4 * band / prm["step"], mode="nearest")) for i, h in hp_all.items()}
        e95 = max(float(np.percentile(np.concatenate(list(env.values())), 95)), 1e-12)
        hp_all = {i: h * np.clip(env[i] / e95, 0.0, 1.5) ** gate for i, h in hp_all.items()}
    allv = np.concatenate([np.abs(h) for h in hp_all.values()]) if hp_all else np.zeros(1)
    k = amount / max(float(np.percentile(allv, 95)), 1e-12)
    rec.update(amount_mm=amount, band_mm=band, gate=gate)
    for i in live:
        u, v, _ = vals[i]
        q = rs[i]
        tg = np.gradient(q.points, axis=0)
        tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
        nrm = np.column_stack([-tg[:, 1], tg[:, 0]])
        off = np.clip(k * hp_all[i], -3 * amount, 3 * amount)
        prev = q.channel("tremor")
        trem = off if prev is None else np.asarray(prev) + off
        out[i] = _stamp(q, rec, "tremor", u, v, {"tremor": trem}, points=q.points + nrm * off[:, None])
    return out
