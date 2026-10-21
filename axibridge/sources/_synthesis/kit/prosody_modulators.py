# FROZEN from research commit 6f96418: tools/gesture/gesture/kit/prosody_modulators.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Prosody thread (round 9): weight as stress, decided by the line's own events.

Round-8 principle 3 ("weight as emphasis: the same utterance quiet and loud;
weight is a decision about stress, not a smooth spatial field") and B
("regimes as prosody"). The `field` modulator asks *where on the sheet* a
point is; `prosody` asks *what just happened in the line*:

  events  (heard on the mark itself, in sheet mm, after placement)
    switch      the hand changes (`voice` channel)            salience 1.0
    corner      tangent turns > ~35° within ±2.5 mm            ∝ turn
    kappa       a local curvature peak (top decile)           ≤ 0.8
    inflection  κ changes sign with real turn on both sides   ≤ 0.5
    token       a grammar token boundary (`token` channel, from the
                `drift_tokens` voice); stronger if a corner opens it
    tempo       a dwell peak, if a dance tempo ran first (`dance_t`)
  coincident events (within 3 mm) merge; each extra kind adds +0.15 (cap 1.5).
  A switch is 0.5 + 0.5·min(1, how long the new hand holds / 40 mm).

  rhythms  (which events carry stress; most of the line stays wire)
    event       the strongest events, at least `gap` apart, `density` per 100 mm
    regular     a metre: beats every 100/density mm snap to the nearest event
                (a beat with no event rests); bar of `metre` beats, downbeat loud
    syncopated  the same metre, but the LOUD stresses fall on off-beat events;
                downbeat events stay quiet (the metre has to be heard to be broken)
    phrase      phrases end at hand switches / strong events; the last event of each
                phrase is loud, the one before it quiet (end-weighted)

  unit: "pulse" = a swell centred on the event; "segment" = the stretch the
  event opens, up to the next event (a stressed syllable). `contrast` makes
  salience relative to its ±60 mm neighbourhood (a corner among corners is
  ordinary; a curvature peak in a smooth hand stands out).
  levels: loud stresses peak at emphasis 1 (r → r_max: mass), quiet ones at
  `quiet` (r → nib). `lead` shifts the swell: < 0 anticipates the event, > 0 lags.

Writes channels `emphasis` (0..1) and `r`, `W`, `M`; meta["prosody"] keeps the
events and stresses (arc-length mm on the written mark) so the `call_response`
arranger can re-decide stress against another voice.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from .core import P, modulator

STEP = 0.4          # mm, analysis/output resampling
MERGE = 3.0         # mm, coincident events merge
KINDS = ("switch", "corner", "kappa", "inflection", "token", "tempo")
RHYTHMS = ("event", "regular", "syncopated", "phrase")


# ---------------------------------------------------------------------------
# hearing the line
# ---------------------------------------------------------------------------

def _theta(points: np.ndarray) -> np.ndarray:
    tg = np.gradient(points, axis=0)
    return np.unwrap(np.arctan2(tg[:, 1], tg[:, 0]))


def line_events(mark, listen=KINDS, step: float = STEP) -> list[tuple[float, float, tuple]]:
    """[(s mm, salience 0..1, kinds)] heard on `mark` (assumed resampled at
    ≈ step). Deterministic; no randomness."""
    n = len(mark)
    if n < 8:
        return []
    s = mark.arclength()
    th = _theta(mark.points)
    raw: list[tuple[float, float, str]] = []
    d = lambda mm: max(int(round(mm / step)), 1)  # noqa: E731
    if "corner" in listen:
        w = 2.5
        T = np.abs(np.interp(s + w, s, th) - np.interp(s - w, s, th))
        pk, _ = find_peaks(T, height=0.6, distance=d(4.0))
        raw += [(s[i], float(np.clip(T[i] / (0.75 * math.pi), 0.2, 1.0)), "corner") for i in pk]
    if "kappa" in listen or "inflection" in listen:
        k1 = gaussian_filter1d(np.gradient(th) / step, 1.5 / step, mode="nearest")
        if "kappa" in listen:
            a = np.abs(k1)
            hi = np.percentile(a, 99) + 1e-9
            pk, _ = find_peaks(a, height=np.percentile(a, 90), distance=d(6.0))
            raw += [(s[i], float(np.clip(0.8 * a[i] / hi, 0.1, 0.8)), "kappa") for i in pk]
        if "inflection" in listen:
            k3 = gaussian_filter1d(np.gradient(th) / step, 3.0 / step, mode="nearest")
            zc = np.nonzero(np.signbit(k3[1:]) != np.signbit(k3[:-1]))[0]
            for i in zc:
                left = abs(th[i] - np.interp(s[i] - 5.0, s, th))
                right = abs(np.interp(s[i] + 5.0, s, th) - th[i])
                m = min(left, right)
                if m > 0.25:
                    raw.append((s[i], float(0.5 * min(1.0, m / 0.8)), "inflection"))
    if "switch" in listen and "voice" in mark.channels:
        v = np.round(mark["voice"])
        sw = np.nonzero(np.diff(v) != 0)[0] + 1
        nxt = np.r_[s[sw[1:]], s[-1]] if len(sw) else np.array([])
        # a decisive change of speaker (the new hand holds the line) is louder than a flicker
        raw += [(s[i], float(0.5 + 0.5 * min(1.0, (b - s[i]) / 40.0)), "switch") for i, b in zip(sw, nxt)]
    if "token" in listen and "token" in mark.channels:
        tk = np.round(mark["token"])
        turn = mark.channel("tok_turn", 0.0)
        raw += [(s[i + 1], float(0.3 + 0.5 * min(1.0, turn[i + 1] / math.pi)), "token")
                for i in np.nonzero(np.diff(tk) != 0)[0]]
    if "tempo" in listen and "dance_t" in mark.channels:
        dw = gaussian_filter1d(np.abs(np.gradient(mark["dance_t"])) / step, 1.0 / step, mode="nearest")
        ratio = dw / (np.median(dw) + 1e-12)
        pk, _ = find_peaks(ratio, height=2.5, distance=d(5.0))
        raw += [(s[i], float(np.clip(math.log(ratio[i]) / math.log(10.0), 0.2, 1.0)), "tempo") for i in pk]
    return merge_events(raw)


def merge_events(raw) -> list[tuple[float, float, tuple]]:
    raw = sorted(raw, key=lambda e: (e[0], e[2]))
    out, cl = [], []

    def flush():
        if not cl:
            return
        best = max(cl, key=lambda e: (e[1], -e[0]))
        kinds = tuple(sorted({e[2] for e in cl}))
        out.append((float(best[0]), float(min(1.5, best[1] + 0.15 * (len(kinds) - 1))), kinds))

    for e in raw:
        if cl and e[0] - cl[0][0] > MERGE:
            flush()
            cl = []
        cl.append(e)
    flush()
    return out


def relative(evs, contrast: float, window: float = 60.0):
    """Stress is relative to its surroundings: salience / (local mean within
    ±window mm)^contrast, rescaled to the original maximum. A corner among
    corners is ordinary; a curvature peak in a smooth hand stands out."""
    if not evs or contrast <= 0:
        return evs
    s = np.array([e[0] for e in evs])
    v = np.array([e[1] for e in evs])
    loc = np.array([v[np.abs(s - si) <= window].mean() for si in s])
    r = v / np.maximum(loc, 1e-3) ** contrast
    r *= v.max() / max(r.max(), 1e-12)
    return [(e[0], float(x), e[2]) for e, x in zip(evs, r)]


# ---------------------------------------------------------------------------
# deciding stress
# ---------------------------------------------------------------------------

def _greedy(cands, gap: float, cap: int):
    """cands [(score, s, ...)] → accepted, best first, ≥ gap apart."""
    acc = []
    for c in sorted(cands, key=lambda c: (-c[0], c[1])):
        if len(acc) >= cap:
            break
        if all(abs(c[1] - a[1]) >= gap for a in acc):
            acc.append(c)
    return acc


def _beats(evs, L: float, period: float):
    """Phase (of 8 tried) whose beats best catch events; beat positions."""
    best = None
    for k in range(8):
        ph = period * k / 8.0
        b = np.arange(ph, L + 1e-9, period)
        sc = 0.0
        for sb in b:
            near = [e[1] for e in evs if abs(e[0] - sb) <= 0.3 * period]
            sc += max(near, default=0.0)
        if best is None or sc > best[0] + 1e-12:
            best = (sc, b)
    return best[1]


def select_stresses(evs, L: float, *, rhythm: str, density: float, gap: float, primary: float, quiet: float,
                    metre: int = 2, phrase_min: float = 60.0) -> list[tuple[float, float]]:
    """[(s mm, level)] — level 1 loud, `quiet` quiet."""
    if not evs or L <= 0:
        return []
    cap = max(1, int(math.ceil(density * L / 100.0)))
    if rhythm == "event":
        acc = _greedy([(e[1], e[0]) for e in evs], gap, cap)
        nl = max(1, int(round(primary * len(acc))))
        return sorted((a[1], 1.0 if i < nl else quiet) for i, a in enumerate(acc))
    period = 100.0 / density
    if rhythm in ("regular", "syncopated"):
        beats = _beats(evs, L, period)
        out = []
        for bi, sb in enumerate(beats):
            down = bi % max(metre, 1) == 0
            near = [(e[1] * (1 - 0.5 * abs(e[0] - sb) / (0.3 * period)), e[0]) for e in evs
                    if abs(e[0] - sb) <= 0.3 * period]
            if rhythm == "regular":
                if near:
                    out.append((max(near)[1], 1.0 if down else quiet))
                continue
            if down and near:                                   # the metre, heard quietly
                out.append((max(near)[1], quiet))
            off = [(e[1], e[0]) for e in evs if 0.3 * period <= e[0] - sb <= 0.7 * period]
            if off:
                out.append((max(off)[1], 1.0))
        out = sorted(set(out))
        keep = []
        for s_, lv in sorted(out, key=lambda x: (-x[1], x[0])):   # loud wins a clash
            if all(abs(s_ - k[0]) >= 0.5 * gap for k in keep):
                keep.append((s_, lv))
        return sorted(keep)
    # phrase
    breaks = [0.0]
    for e in evs:
        if ("switch" in e[2] or e[1] >= 0.85) and e[0] - breaks[-1] >= phrase_min:
            breaks.append(e[0])
    breaks.append(L + 1.0)
    out = []
    for a, b in zip(breaks[:-1], breaks[1:]):
        inner = [e for e in evs if a + 0.5 * gap <= e[0] < b - 1.0 and e[1] >= 0.3]
        if not inner:
            continue
        last = inner[-1]
        out.append((last[0], 1.0))
        prev = [e for e in inner[:-1] if last[0] - e[0] >= gap]
        if prev:
            out.append((max(prev, key=lambda e: (e[1], e[0]))[0], quiet))
    return sorted(out)


def with_ends(stresses, evs, L: float, *, unit: str, span: float) -> list[tuple[float, float, float]]:
    """(s, level) → (s, level, end). unit "pulse": a swell centred on the event
    (end unused); "segment": the stress covers the stretch the event OPENS —
    up to the next event (≥ span, ≤ 4·span): a stressed syllable, not a point."""
    out = []
    ev_s = np.array(sorted(e[0] for e in evs)) if evs else np.array([])
    for sk, lv in stresses:
        if unit == "pulse":
            out.append((sk, lv, sk))
            continue
        nx = ev_s[ev_s > sk + 2.0]
        end = float(nx[0]) if len(nx) else L
        out.append((sk, lv, float(np.clip(end, sk + span, min(sk + 4 * span, L)))))
    return out


def stress_profile(s: np.ndarray, stresses, *, span: float, lead: float, unit: str = "pulse") -> np.ndarray:
    """pulse: emphasis(s) = max_k level_k · raised-cosine((s − s_k − lead) / span);
    segment: level_k on [s_k, end_k] (shifted by lead) with raised-cosine ramps
    of min(2 mm, span/2) at both ends."""
    e = np.zeros(len(s))
    for st in stresses:
        sk, lv = st[0], st[1]
        if unit == "pulse":
            x = (s - sk - lead) / max(span, 1e-6)
            e = np.maximum(e, lv * np.where(np.abs(x) < 1, 0.5 * (1 + np.cos(np.pi * x)), 0.0))
            continue
        a, b = sk + lead, st[2] + lead
        rp = min(2.0, 0.5 * span)
        up = np.clip((s - a + rp) / rp, 0, 1)
        dn = np.clip((b + rp - s) / rp, 0, 1)
        e = np.maximum(e, lv * 0.5 * (1 - np.cos(np.pi * np.minimum(up, dn))))
    return e


def apply_stress(mark, stresses, prm: dict):
    """Write emphasis/r/W/M on an already-resampled mark from (s, level, end) stresses."""
    e = stress_profile(mark.arclength(), stresses, span=prm["span"], lead=prm["lead"], unit=prm["unit"])
    n = len(mark)
    return mark.evolve(channels={"emphasis": e, "r": np.clip(prm["r_max"] * e, 0.0, 2.0),
                                 "W": np.full(n, prm["W"]), "M": np.full(n, prm["M"])})


def _reach(p: dict) -> float:
    return 0.5 * max(p["W"], p["M"] * 1.25 if p["r_max"] > 1 else 0.0) + 0.4


PARAMS = [
    P("rhythm", "choice", "event", "event | regular (metre) | syncopated | phrase (end-weighted)", choices=RHYTHMS),
    P("listen", "str", "switch,corner,kappa,inflection,token,tempo",
      "comma list of events heard: " + ",".join(KINDS)),
    P("contrast", "float", 0.5, "stress is relative: salience / local mean^contrast (0 = absolute)",
      min=0.0, max=2.0),
    P("density", "float", 1.0, "stresses (or beats) per 100 mm of line", min=0.05, max=10.0),
    P("gap", "float", 20.0, "minimum mm between stresses", min=0.0, max=500.0),
    P("unit", "choice", "pulse", "pulse: a swell centred on the event | segment: the stretch the event opens "
      "(to the next event, span..4·span) — a stressed syllable", choices=("pulse", "segment")),
    P("span", "float", 5.0, "pulse half-width / shortest stressed segment, mm", min=0.5, max=60.0),
    P("lead", "float", 0.0, "shift the swell: < 0 anticipates the event, > 0 lags (mm)", min=-60.0, max=60.0),
    P("primary", "float", 0.34, "event rhythm: share of stresses that are loud", min=0.0, max=1.0),
    P("quiet", "float", 0.5, "level of a quiet stress (1 = loud)", min=0.05, max=1.0),
    P("metre", "int", 2, "regular/syncopated: beats per bar (downbeat loud)", min=1, max=7),
    P("phrase_min", "float", 120.0, "phrase rhythm: shortest phrase, mm", min=5.0, max=1000.0),
    P("r_max", "float", 2.0, "regime at a loud stress (2 mass, 1 nib)", min=0.0, max=2.0),
    P("W", "float", 2.5, "nib width mm", min=0.1, max=30.0),
    P("M", "float", 7.0, "mass width mm", min=0.5, max=60.0),
]


def _listen(spec: str) -> tuple:
    got = tuple(k.strip() for k in spec.split(",") if k.strip())
    bad = [k for k in got if k not in KINDS]
    if bad:
        raise ValueError(f"prosody: unknown event kind(s) {bad}; choose from {KINDS}")
    return got


@modulator("prosody", params=PARAMS, reach=_reach,
           doc="weight as stress: emphasis where the line's own events happen (hand switch, corner, "
               "inflection, token, tempo), in a rhythm; most of the line stays wire")
def prosody(ctx, marks, **prm):
    listen = _listen(prm["listen"])
    out = []
    for m in marks:
        if len(m) < 2 or m.length() <= 0:
            out.append(m)
            continue
        q = m.resampled(STEP)
        L = q.length()
        evs = relative(line_events(q, listen), prm["contrast"])
        st = select_stresses(evs, L, rhythm=prm["rhythm"], density=prm["density"], gap=prm["gap"],
                             primary=prm["primary"], quiet=prm["quiet"], metre=prm["metre"],
                             phrase_min=prm["phrase_min"])
        st = with_ends(st, evs, L, unit=prm["unit"], span=prm["span"])
        q = apply_stress(q, st, prm)
        out.append(q.evolve(meta={"prosody": {
            "events": [[round(e[0], 3), round(e[1], 3), "+".join(e[2])] for e in evs],
            "stresses": [[round(v, 3) for v in x] for x in st],
            "length": round(L, 3), "params": {k: v for k, v in prm.items()}}}))
    return out
