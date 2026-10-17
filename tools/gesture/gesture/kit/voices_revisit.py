"""Where one limb stops, the line writes what the rest of the body did
(round 12, thread `revisit`, 2026-10-17).

Round 7 grew signs out of the line (`gesture/signs.py`), but every sign was
one of 17 fixed operators sampled from a grammar, and the blind judge showed
their placement statistics meant nothing. Round 8 found that a dancer's
pauses carry masses at the right places (`own_tempo`), and Ian later asked
for kinematics "to drive other stuff" rather than to become yet another hand.

voice `revisit_glyph`: ONE limb's trail (the host) over a dance window, as
one contiguous line. Wherever the host holds still, the line leaves its
path, draws a small figure and comes back to where it stopped: the figure is
what the OTHER limbs did during that hold, seen from the host (their motion
relative to it), drawn small and closed into an excursion that starts and
ends on the stopped point. So each sign is different and none is invented;
they are one family because they are one body. Channels:
- `r` / `W` / `M` / `phi`: the host stays wire; the excursion rises into a
  nib (and, where the watched limb was slowest, toward mass) and falls back
  to wire before it rejoins;
- `glyph`: 0 on the host, k + 1 on the k-th excursion (categorical);
- `dance_t`: dance seconds (the excursion keeps the time of its frames), and
  `dance_speed` / `dance_acc` (host or watched limb), so `revisit_notate` /
  `own_tempo` still read it.

`limbs`: "loudest" (only the limb that moved most during the hold) or "all"
(one petal per other limb, loudest first, each returning to the stop).
"""
from __future__ import annotations

import numpy as np

from .core import P, channel_kind, fitted, voice
from .voices_corpus import EFFECTORS

channel_kind("glyph", "nearest")


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _arc(p):
    return np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])


def holds(v: np.ndarray, t: np.ndarray, *, still: float, min_s: float, merge_s: float) -> list[tuple[int, int, int]]:
    """(i0, i1, slowest) index runs where v < still, merged across gaps <
    merge_s, kept if they last ≥ min_s. Deterministic."""
    idx = np.flatnonzero(v < still)
    if not len(idx):
        return []
    runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    merged = [runs[0]]
    for r in runs[1:]:
        if t[r[0]] - t[merged[-1][-1]] < merge_s:
            merged[-1] = np.r_[merged[-1][0]:r[-1] + 1]
        else:
            merged.append(r)
    out = []
    for r in merged:
        if t[r[-1]] - t[r[0]] >= min_s:
            out.append((int(r[0]), int(r[-1]), int(r[int(np.argmin(v[r]))])))
    return out


def turning(path: np.ndarray, step: float | None = None) -> float:
    """Total absolute turning (radians) of a path resampled at `step` (default
    1/40 of its length): how eventful a motion is, independent of its size."""
    p = np.asarray(path, float)
    s = _arc(p)
    if s[-1] <= 1e-12 or len(p) < 3:
        return 0.0
    step = step or s[-1] / 40
    u = np.arange(0.0, s[-1], step)
    q = np.c_[np.interp(u, s, p[:, 0]), np.interp(u, s, p[:, 1])]
    d = np.diff(q, axis=0)
    h = np.arctan2(d[:, 1], d[:, 0])
    return float(np.abs(np.angle(np.exp(1j * np.diff(h)))).sum())


def excursion(path: np.ndarray) -> np.ndarray:
    """The path moved to start at 0 and detrended so it also ENDS at 0 (a
    closed excursion from the stop point and back)."""
    p = np.asarray(path, float) - path[0]
    s = _arc(p)
    u = s / s[-1] if s[-1] > 0 else np.linspace(0, 1, len(p))
    return p - np.outer(u, p[-1])


def _dedupe(p, keep_first=True, eps=1e-4):
    k = [0]
    for i in range(1, len(p)):
        if np.hypot(*(p[i] - p[k[-1]])) >= eps:
            k.append(i)
    return np.array(k)


def host_line(tr, host, a0, a1, *, draw="figures", pick="path", spread=0.4, slow_at=0.35, still, min_hold_s, merge_s, pad_s, max_fig_s, size, scale, fig, limbs,
              close, max_glyphs, r_glyph, slow_mass, ramp, diag=None):
    """One host's line in the trail's native units (body heights): points and
    channels (dance_t, dance_speed, dance_acc, glyph, r) plus meta (`figures`:
    per figure the hold, the watched limb(s) and the stop point)."""
    fps = tr["fps"]
    t = np.arange(a0, a1) / fps
    hp = np.asarray(tr[f"{host}_xy"][a0:a1], float)
    hv = np.asarray(tr[f"{host}_v"][a0:a1], float)
    ha = np.asarray(tr[f"{host}_a"][a0:a1], float)
    vref = float(np.percentile(hv, 90)) or 1.0
    hs = holds(hv / vref, t, still=still, min_s=min_hold_s, merge_s=merge_s)
    hs = sorted(sorted(hs, key=lambda h: (-(h[1] - h[0]), h[0]))[:max_glyphs], key=lambda h: h[0])
    others = [e for e in EFFECTORS if e != host]
    pad = int(round(pad_s * fps))
    half = int(round(0.5 * max_fig_s * fps))
    diag = float(np.hypot(*(hp.max(0) - hp.min(0)))) if diag is None else diag

    def window(i0, i1, j):
        return max(i0 - pad, 0, j - half), min(i1 + pad + 1, a1 - a0, j + half + 1)

    acts = []
    for i0, i1, j in hs:
        w0, w1 = window(i0, i1, j)
        for o in others:
            acts.append(float(_arc(np.asarray(tr[f"{o}_xy"][a0 + w0:a0 + w1], float) - hp[w0:w1])[-1]))
    med_act = float(np.median(acts)) if acts else 0.0
    vref_o = {o: float(np.percentile(tr[f"{o}_v"][a0:a1], 90)) or 1.0 for o in others}
    pts, ch_t, ch_v, ch_a, ch_g, ch_r = [], [], [], [], [], []
    figures = []
    cur = 0
    off = np.zeros(2)
    for g, (i0, i1, j) in enumerate(hs):
        pts.append(hp[cur:j + 1] + off); ch_t.append(t[cur:j + 1]); ch_v.append(hv[cur:j + 1])
        ch_a.append(ha[cur:j + 1]); ch_g.append(np.zeros(j + 1 - cur)); ch_r.append(np.zeros(j + 1 - cur))
        w0, w1 = window(i0, i1, j)
        petals = []
        for o in others:
            rel = np.asarray(tr[f"{o}_xy"][a0 + w0:a0 + w1], float) - hp[w0:w1]
            petals.append((float(_arc(rel)[-1]), o, rel))
        key = (lambda x: (-x[0], x[1])) if pick == "path" else (lambda x: (-turning(x[2]), x[1]))
        petals.sort(key=key)
        if limbs == "loudest":
            petals = petals[:1]
        watched = []
        for act, o, rel in petals:
            if draw == "stops":
                watched.append(o)
                continue
            if act <= 1e-9 or len(rel) < 3:
                continue
            ex = excursion(rel) if close == "excursion" else np.asarray(rel, float) - rel[0]
            if size == "true":
                ex = ex * scale
            else:
                ext = float(np.hypot(*(ex.max(0) - ex.min(0))))
                k_act = float(np.clip((act / med_act) ** spread, 0.3, 3.0)) if med_act > 0 else 1.0
                ex = ex * (fig * diag * k_act / max(ext, 1e-12))
            q = hp[j] + off + ex[1:]
            ov = np.asarray(tr[f"{o}_v"][a0 + w0:a0 + w1], float)[1:] / vref_o[o]
            u = _arc(ex)[1:] / max(_arc(ex)[-1], 1e-12)
            env = (_smoothstep(u / max(ramp, 1e-6)) * _smoothstep((1 - u) / max(ramp, 1e-6))) if ramp > 0 \
                else np.ones(len(u))
            slow = _smoothstep((slow_at - ov) / max(0.85 * slow_at, 1e-6))   # where the watched limb nearly stopped
            r = np.clip(env * (r_glyph + slow_mass * slow), 0.0, 2.0)
            pts.append(q); ch_t.append(t[w0:w1][1:]); ch_v.append(ov * vref_o[o])
            ch_a.append(np.asarray(tr[f"{o}_a"][a0 + w0:a0 + w1], float)[1:])
            ch_g.append(np.full(len(q), g + 1.0)); ch_r.append(r)
            off = off + ex[-1]
            watched.append(o)
        figures.append({"glyph": g + 1, "t0": round(float(t[i0]), 3), "t1": round(float(t[i1]), 3),
                        "t_stop": round(float(t[j]), 3), "w0": round(float(t[w0]), 3),
                        "w1": round(float(t[w1 - 1]), 3), "watched": watched})
        cur = j + 1
    pts.append(hp[cur:] + off); ch_t.append(t[cur:]); ch_v.append(hv[cur:]); ch_a.append(ha[cur:])
    ch_g.append(np.zeros(len(hp) - cur)); ch_r.append(np.zeros(len(hp) - cur))
    P_ = np.vstack([p for p in pts if len(p)])
    cat = lambda xs: np.concatenate([x for x in xs if len(x)])           # noqa: E731
    T, V, A, G, R = cat(ch_t), cat(ch_v), cat(ch_a), cat(ch_g), cat(ch_r)
    k = _dedupe(P_, eps=4e-4)
    return P_[k], {"dance_t": T[k], "dance_speed": V[k], "dance_acc": A[k], "glyph": G[k], "r": R[k]}, \
        {"joint": host, "figures": figures}


@voice("revisit_glyph", params=[
    P("trail", "ref", "levitation", "the frozen dance window", kind="dance_trail"),
    P("host", "choice", "head", "the limb whose trail is the line", choices=EFFECTORS),
    P("with_", "choice", "none", "a second host on the same surface, at the same scale (its own line and figures)",
      choices=("none", "others") + EFFECTORS),
    P("layout", "choice", "body", "body: hosts where the body put them | rows: each host in its own band, "
      "stacked in host order at one scale (a score)", choices=("body", "rows")),
    P("row_gap", "float", 0.25, "rows: empty space between bands, × the tallest band", min=0.0, max=3.0),
    P("t0", "float", 0.0, "start, seconds into the frozen window", min=0.0, max=60.0),
    P("seconds", "float", 30.0, "how much of the dance the host line covers", min=1.0, max=60.0),
    P("still", "float", 0.15, "host holds: speed below this share of the host's p90", min=0.01, max=0.8),
    P("min_hold_s", "float", 0.35, "shortest host hold that writes a figure (dance seconds)", min=0.05, max=5.0),
    P("merge_s", "float", 0.3, "holds closer than this are one", min=0.0, max=3.0),
    P("pad_s", "float", 0.5, "the figure also takes this much time before and after the hold", min=0.0, max=3.0),
    P("draw", "choice", "figures", "figures: splice each figure into the line | stops: the plain host line, the "
      "stops only recorded in meta['figures'] (for comparing other answers at the same places)",
      choices=("figures", "stops")),
    P("pick", "choice", "path", "loudest limb = the longest motion (path) or the most eventful one (turning)",
      choices=("path", "turning")),
    P("limbs", "choice", "loudest", "loudest: the limb that moved most during the hold | all: one petal per limb",
      choices=("loudest", "all")),
    P("max_fig_s", "float", 1.6, "a figure covers at most this many dance seconds, centred on the stop",
      min=0.2, max=10.0),
    P("size", "choice", "fit", "true: the watched motion × scale (honest sizes) | fit: every figure about "
      "`fig` of the host line's extent, a little larger where more happened", choices=("true", "fit")),
    P("spread", "float", 0.4, "size=fit: how much more happening makes a figure larger (exponent on the "
      "motion's length relative to the median; 0 = all figures one size)", min=0.0, max=1.5),
    P("scale", "float", 0.35, "size=true: the watched limbs' motion × this, in the host line's units",
      min=0.02, max=3.0),
    P("fig", "float", 0.07, "size=fit: figure extent as a share of the host line's bbox diagonal",
      min=0.005, max=0.5),
    P("close", "choice", "excursion", "excursion: each figure is closed back onto the stop point | carry: the "
      "figure stays open and the rest of the host line goes on from where it ends (displaced)",
      choices=("excursion", "carry")),
    P("max_glyphs", "int", 12, "most figures (longest holds first)", min=0, max=80),
    P("r_glyph", "float", 1.15, "regime of a figure (1 nib … 2 mass); the host is wire", min=0.0, max=2.0),
    P("slow_mass", "float", 0.6, "extra regime where the watched limb was slowest (toward mass)",
      min=0.0, max=2.0),
    P("slow_at", "float", 0.35, "the watched limb counts as slow below this share of its p90 speed",
      min=0.02, max=1.0),
    P("ramp", "float", 0.15, "share of each figure over which it rises from / falls back to wire",
      min=0.0, max=0.5),
    P("nib_mm", "float", 0.9, "nib width of the figures, mm", min=0.1, max=12.0),
    P("mass_mm", "float", 1.6, "mass width of the figures, mm", min=0.2, max=30.0),
    P("nib_deg", "float", 40.0, "nib angle, degrees", min=-90.0, max=90.0),
], doc="one limb's line; where it holds still it writes, small, what the other limbs did meanwhile")
def revisit_glyph(ctx, *, trail, host, with_, layout, row_gap, draw, pick, spread, slow_at, t0, seconds, still, min_hold_s, merge_s, pad_s, max_fig_s, size,
                  scale, fig, limbs, close, max_glyphs, r_glyph, slow_mass, ramp, nib_mm, mass_mm, nib_deg):
    tr = ctx.use("dance_trail", trail)
    fps = tr["fps"]
    n = len(tr["energy"])
    a0 = min(int(round(t0 * fps)), max(n - 3, 0))
    a1 = min(a0 + max(int(round(seconds * fps)), 3), n)
    if with_ == "others":
        hosts = [host] + [e for e in EFFECTORS if e != host]
    else:
        hosts = [host] + ([with_] if with_ not in ("none", host) else [])
    allp = np.vstack([np.asarray(tr[f"{h}_xy"][a0:a1], float) for h in hosts])
    diag = float(np.hypot(*(allp.max(0) - allp.min(0))))        # figures sized on the shared extent
    polys, chans, metas = [], [], []
    for h in hosts:
        P_, ch, meta = host_line(tr, h, a0, a1, draw=draw, pick=pick, spread=spread, slow_at=slow_at, still=still, min_hold_s=min_hold_s, merge_s=merge_s, pad_s=pad_s,
                                 max_fig_s=max_fig_s, size=size, scale=scale, fig=fig, limbs=limbs, close=close,
                                 max_glyphs=max_glyphs, r_glyph=r_glyph, slow_mass=slow_mass, ramp=ramp, diag=diag)
        N = len(P_)
        ch.update({"W": np.full(N, float(nib_mm)), "M": np.full(N, float(mass_mm)),
                   "phi": np.full(N, float(np.radians(nib_deg)))})
        polys.append(P_)
        chans.append(ch)
        metas.append({**meta, "voices": [f"dance:{trail}"], "trail": trail})
    if layout == "rows" and len(polys) > 1:
        hts = [float(np.ptp(p[:, 1])) for p in polys]
        band = max(hts) * (1 + row_gap)
        polys = [p - np.array([0.0, float(np.mean([p[:, 1].min(), p[:, 1].max()])) - k * band])
                 for k, p in enumerate(polys)]
        for k, md in enumerate(metas):
            md["row"] = k
    return fitted(polys, ctx.box, chans, metas)
