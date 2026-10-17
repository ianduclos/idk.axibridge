"""Solid abstract script (round 11, exploration 3).

Ian on the round-10 shikasta rows: "my problem more than the scriptlike thing
is that it looks a bit boring and blocky, not solid enough to register as
abstract script." Legibility is not the issue; weight and solidity are. This
module writes rows that should read at a glance as WRITING — dense, black,
rhythmic, with body — and never as any real script.

How a script is made from a hand (the grammar, not a font):

  1. The hand (any library hand) draws one long line (`hybrid.drift_line`
     with that hand alone, as the `hand` voice does).
  2. The line is cut into **glyph windows by turning budget**: a window runs
     until it has turned `turn` × π (a bowl, a loop, a zig-zag, a corner
     pair), so a smooth hand and a cornered hand both give glyph-sized
     pieces, each in its own manner. Each window is turned so its chord runs
     along the writing direction and scaled to the x-height (tall windows
     become ascenders / descenders, the smoothest become swashes).
  3. A small **inventory** (`inventory` glyphs) is drawn from the windows and
     reused with Zipf frequencies and a seeded bigram table, so shapes recur
     the way letters do — the alphabet feel comes from recurrence, not from
     any letter form.
  4. **Words** are runs of glyphs joined by smooth Bezier ligatures into ONE
     path; word lengths and gaps are lognormal; the row sits on a baseline
     (`ruled`, `hanging` (each word slopes down along the writing, words
     cascade), `wander`) and sometimes ignores it (`ignore`). Line ends
     compress and climb (`compress`) and/or end in a swash.
  5. `join: row` (the radical move) bridges words with hairline kashidas so a
     whole row is ONE continuous line.

Channels written: r = 1 (nib), phi (nib edge page angle, rad), W (nib width
mm, per point: tapers, light ligatures, hairline kashidas). Meta: row, word,
kind (word | row | dot), x_height, dot shape.

Renderers:
  script_solid_nib  broad-nib sweep (width = W·|sin(θ − φ)|, set by stroke
                    direction as a real nib does) + the centreline as the
                    hairline; the thick parts are FILLED line-built:
                    contour-parallel insets (holes/counters kept white)
                    joined into as few paths as possible (one per blob where
                    the jump stays inside the ink). Never hatching.
  script_solid_bar  the radical negative: words (or whole rows) close into
                    round black slugs and the writing is CARVED out of them
                    as white counters; filled the same line-built way.

Arranger:
  script_solid_page part 0 is a drawing (any voice); script parts fill a
                    margin column beside it (`margin`), flow around it
                    (`wrap`: the script answers the drawing, words only where
                    the paper is free), or run as a rotated marginal block
                    (`diagonal`, the hashiya habit of turning the page).

Policy: hands come through ctx.use (library gate). No calligraphy sheet is a
generation source here; scans are only MEASURED (script_solid_measure).
"""
from __future__ import annotations

import math

import numpy as np

from .. import hybrid as hy
from .core import Ink, Mark, P, arranger, renderer, voice

RESEARCH_SIZE = (1000.0, 1200.0)
STEP_MM = 0.15


# ---------------------------------------------------------------------------
# small geometry helpers
# ---------------------------------------------------------------------------

def _arcl(p: np.ndarray) -> np.ndarray:
    if len(p) < 2:
        return np.zeros(len(p))
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]


def _resample(p: np.ndarray, step: float) -> np.ndarray:
    s = _arcl(p)
    if len(p) < 2 or s[-1] <= 1e-9:
        return np.asarray(p, float).copy()
    n = max(int(math.ceil(s[-1] / step)), 2)
    t = np.linspace(0.0, s[-1], n + 1)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def _smooth(p: np.ndarray, sd: float) -> np.ndarray:
    from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415
    if sd <= 0 or len(p) < 5:
        return p
    return np.column_stack([gaussian_filter1d(p[:, 0], sd, mode="nearest"),
                            gaussian_filter1d(p[:, 1], sd, mode="nearest")])


def _rot2(p: np.ndarray, a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return p @ np.array([[c, s], [-s, c]])


def _tangent(p: np.ndarray, end: bool, span: float) -> np.ndarray:
    s = _arcl(p)
    if end:
        j = int(np.searchsorted(s, s[-1] - span))
        v = p[-1] - p[min(j, len(p) - 2)]
    else:
        j = int(np.searchsorted(s, span))
        v = p[max(j, 1)] - p[0]
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([1.0, 0.0])


def bezier(a, ta, b, tb, k: float, n: int = 24) -> np.ndarray:
    a, b = np.asarray(a, float), np.asarray(b, float)
    p1, p2 = a + ta * k, b - tb * k
    t = np.linspace(0.0, 1.0, n)[:, None]
    return (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * b


# ---------------------------------------------------------------------------
# 1–3: the hand's line → glyph windows → an inventory
# ---------------------------------------------------------------------------

def hand_line(ctx, hand: str, length: float) -> np.ndarray:
    g = ctx.use("hand", hand)
    st, _ = hy.drift_line([g], np.random.default_rng([ctx.seed, 11]), total=float(length), mode="mixture",
                          size=RESEARCH_SIZE, plateau=0.12, context="kappa")
    return np.asarray(st.points, float)


def _turning(p: np.ndarray) -> np.ndarray:
    d = np.diff(p, axis=0)
    th = np.arctan2(d[:, 1], d[:, 0])
    dt = np.abs(np.angle(np.exp(1j * np.diff(th))))
    return np.r_[0.0, 0.0, np.cumsum(dt)]          # per point (len p)


def _is_simple(q: np.ndarray) -> bool:
    from shapely.geometry import LineString  # noqa: PLC0415
    return LineString(q[:: max(1, len(q) // 200)]).is_simple


def glyph_windows(line_px: np.ndarray, rng, *, n: int, turn_lo: float, turn_hi: float) -> list[dict]:
    """Cut `n` windows from the hand's line, each running until it has turned
    U(turn_lo, turn_hi)·π. Returns normalised windows: chord along +x from the
    origin, y down, native px scale, with shape stats."""
    p = _resample(line_px, 1.0)
    p = _smooth(p, 1.2)
    T = _turning(p)
    s = _arcl(p)
    out = []
    tries = 0
    while len(out) < n and tries < 20 * n:
        tries += 1
        i = int(rng.integers(0, max(len(p) - 20, 1)))
        budget = float(rng.uniform(turn_lo, turn_hi)) * math.pi
        j = int(np.searchsorted(T, T[i] + budget))
        if j >= len(p) - 1 or j - i < 12:
            continue
        q = p[i:j + 1] - p[i]
        L = s[j] - s[i]
        c = q[-1]
        if np.linalg.norm(c) < 0.18 * L:
            continue
        q = _rot2(q, -math.atan2(c[1], c[0]))     # chord → +x
        if rng.random() < 0.5:                     # bulge up or down: both are the hand's
            q[:, 1] = -q[:, 1]
        lo, hi = q.min(axis=0), q.max(axis=0)
        w, h = hi - lo
        if h < 1e-6 or w < 1e-6:
            continue
        simple = bool(_is_simple(q))
        out.append({"q": q, "w": float(w), "h": float(h), "chord": float(np.linalg.norm(c)), "L": float(L),
                    "simple": simple,
                    "turn": budget / math.pi, "aspect": float(h / w), "density": float(budget / max(L, 1e-9))})
    return out


def build_inventory(wins: list[dict], rng, *, inventory: int, glyph_w: float, asc_h: float,
                    simple_only: bool = False) -> dict:
    """Body glyphs, tall glyphs and swash windows, scaled to x-height 1
    (baseline y = 0, up is −y), entry at x = 0. simple_only drops windows
    that cross themselves (a cornered hand's crossings read as X)."""
    if simple_only and sum(w["simple"] for w in wins) >= 12:
        wins = [w for w in wins if w["simple"]]
    body, tall, flat = [], [], []
    for wd in wins:
        q = wd["q"]
        ok_chord = wd["chord"] >= 0.3 * wd["w"]
        if wd["aspect"] > 1.5 and ok_chord:
            tall.append(wd)
        elif wd["aspect"] < 0.22:
            flat.append(wd)
        elif ok_chord:
            body.append(wd)
    order = rng.permutation(len(body))
    glyphs = []
    for k in order[:inventory]:
        wd = body[int(k)]
        q = wd["q"].copy()
        s = 1.0 / wd["h"]
        if wd["w"] * s > glyph_w:
            s = glyph_w / wd["w"]
        q = q * s
        q[:, 1] -= q[:, 1].max()
        glyphs.append(q)
    if len(glyphs) < 3:                            # a hand with no glyph-like windows: take what there is
        for wd in (body + tall + flat)[:max(3, inventory)]:
            q = wd["q"] / max(wd["h"], wd["w"] / glyph_w)
            q[:, 1] -= q[:, 1].max()
            glyphs.append(q)
    talls = []
    src = tall if len(tall) >= 2 else body
    for k in rng.permutation(len(src))[:4]:
        wd = src[int(k)]
        q = wd["q"].copy()
        # tall: rotate so the long axis is vertical-ish (an upstroke-downstroke), keep entry at origin
        if wd["aspect"] <= 1.5:
            q = _rot2(q, -math.pi / 2 * (1 if rng.random() < 0.5 else -1))
            q = q - q[0]
        lo, hi = q.min(axis=0), q.max(axis=0)
        h, w = hi[1] - lo[1], hi[0] - lo[0]
        s = asc_h / max(h, 1e-9)
        if w * s > 0.9 * glyph_w:
            s = 0.9 * glyph_w / max(w, 1e-9)
        q = q * s
        q[:, 1] -= q[:, 1].max()
        talls.append(q)
    swash = sorted(flat or body, key=lambda wd: wd["density"])[:3]
    sw = []
    for wd in swash:
        q = wd["q"] / max(wd["w"], 1e-9)          # unit length along x
        sw.append(q)
    return {"glyphs": glyphs, "talls": talls, "swash": sw}


# ---------------------------------------------------------------------------
# 4: words and rows
# ---------------------------------------------------------------------------

class Writer:
    """Writes rows of one abstract script into a box, in writing coordinates
    (u along the writing from the row start, y down, baseline y = 0, x-height 1)."""

    def __init__(self, inv: dict, rng, P_: dict):
        self.inv, self.rng, self.p = inv, rng, P_
        n = len(inv["glyphs"])
        z = 1.0 / np.arange(1, n + 1) ** P_["zipf"]
        self.freq = z / z.sum()
        T = rng.dirichlet(np.full(n, 0.35), size=n)
        self.T = 0.55 * T + 0.45 * self.freq[None, :]
        self.T /= self.T.sum(axis=1, keepdims=True)

    def _glyph(self, prev: int | None) -> tuple[np.ndarray, int, str]:
        p, rng = self.p, self.rng
        r = rng.random()
        if r < p["asc_rate"] and self.inv["talls"]:
            q = self.inv["talls"][int(rng.integers(len(self.inv["talls"])))].copy()
            return q, -1, "asc"
        if r < p["asc_rate"] + p["desc_rate"] and self.inv["talls"]:
            q = self.inv["talls"][int(rng.integers(len(self.inv["talls"])))].copy()
            h = -q[:, 1].min()
            q[:, 1] += h - 1.0                    # top at the x-height: hangs below the baseline
            return q, -1, "desc"
        pr = self.freq if prev is None or prev < 0 else self.T[prev]
        k = int(rng.choice(len(pr), p=pr))
        return self.inv["glyphs"][k].copy(), k, "body"

    def _jitter(self, q: np.ndarray) -> np.ndarray:
        j = self.p["jitter"]
        if j <= 0:
            return q
        rng = self.rng
        q = q * np.array([1 + j * rng.normal(0, 0.10), 1 + j * rng.normal(0, 0.06)])
        return _rot2(q, j * rng.normal(0, 0.05))

    def word(self, n_glyphs: int) -> dict:
        """One word: a single joined path (u, y) + per-point W factor + dot sites."""
        p, rng = self.p, self.rng
        pts, wf, dots = [], [], []
        u = 0.0
        prev = None
        cur_end, cur_t = None, None
        for gi in range(n_glyphs):
            q, k, kind = self._glyph(prev)
            q = self._jitter(q)
            q = _smooth(_resample(q, 0.04), self.p["smooth"] / 0.04) if self.p["smooth"] > 0 else _resample(q, 0.04)
            prev = k
            if cur_end is None:
                q = q - np.array([q[0, 0], 0.0]) + np.array([u, 0.0])
            else:
                gap = p["join_gap"] * (0.6 + 0.8 * rng.random())
                start = np.array([cur_end[0] + gap, q[0, 1]])
                q = q - q[0] + start
                t0 = _tangent(q, False, 0.15)
                k_ = 0.45 * max(np.linalg.norm(start - cur_end), 0.25)
                lig = bezier(cur_end, cur_t, start, t0, k_, n=max(int(np.linalg.norm(start - cur_end) / 0.04), 6))
                pts.append(lig[1:-1])
                wf.append(np.full(len(lig) - 2, p["connector_w"]))
            pts.append(q)
            fw = np.ones(len(q))
            wf.append(fw)
            if kind == "body" and rng.random() < p["dots"]:
                dots.append((float(np.mean(q[:, 0])), float(q[:, 1].min()), float(q[:, 1].max())))
            cur_end, cur_t = q[-1], _tangent(q, True, 0.15)
        P_ = np.vstack(pts)
        F = np.concatenate(wf)
        # entry / exit taper (the nib touching down and lifting)
        s = _arcl(P_)
        ramp = np.clip(np.minimum(s, s[-1] - s) / 0.25, 0, 1)
        F = F * (0.45 + 0.55 * ramp)
        return {"pts": P_, "wf": F, "dots": dots, "width": float(P_[:, 0].max() - P_[:, 0].min()),
                "u0": float(P_[:, 0].min())}

    def swash(self, length: float) -> np.ndarray:
        """A long final stroke: the hand's smoothest window, flattened, dropping
        below the baseline and trailing on (unit x-height coords, starts at 0)."""
        rng = self.rng
        sw = self.inv["swash"]
        q = sw[int(rng.integers(len(sw)))].copy() if sw else np.column_stack([np.linspace(0, 1, 20),
                                                                                np.zeros(20)])
        q = q * np.array([length, 0.35 * length])
        q = q - q[0]
        a = math.radians(float(rng.uniform(8, 20)))
        q = _rot2(q, -a)                        # slopes down along the writing (y down = +)
        q[:, 1] = np.abs(q[:, 1]) * 0.6 + q[:, 1] * 0.4
        return _resample(q, 0.04)


def _free_intervals(obstacle, x0, x1, y_top, y_bot, step: float = 0.6, min_len: float = 4.0):
    """x-intervals of [x0, x1] where the band [y_top, y_bot] misses `obstacle`."""
    if obstacle is None:
        return [(x0, x1)]
    from shapely.geometry import box as sbox  # noqa: PLC0415
    from shapely.prepared import prep  # noqa: PLC0415
    pg = prep(obstacle)
    xs = np.arange(x0, x1, step)
    free = np.array([not pg.intersects(sbox(x, y_top, x + step, y_bot)) for x in xs])
    out, a = [], None
    for x, f in zip(xs, free):
        if f and a is None:
            a = x
        if not f and a is not None:
            out.append((a, x))
            a = None
    if a is not None:
        out.append((a, x1))
    return [(a, b) for a, b in out if b - a >= min_len]


def write_block(ctx, *, box=None, obstacle=None, **P_) -> list[Mark]:
    """The script voice proper (`script_solid` calls this; arrangers call it
    with an obstacle to write around a drawing)."""
    x0, y0, bw, bh = box if box is not None else ctx.box
    X = float(P_["x_height"])
    rng_bank = ctx.rng("bank")
    line = hand_line(ctx, P_["hand"], P_["length"])
    wins = glyph_windows(line, rng_bank, n=420, turn_lo=P_["turn_lo"], turn_hi=P_["turn_hi"])
    inv = build_inventory(wins, rng_bank, inventory=int(P_["inventory"]), glyph_w=P_["glyph_w"],
                          asc_h=P_["asc_h"], simple_only=P_["simple_only"])
    rng = ctx.rng("text")
    wr = Writer(inv, rng, P_)
    lead = P_["leading"] * X
    top = (0.85 * P_["asc_h"] + 0.15) * X if P_["asc_rate"] > 0 else 1.5 * X
    n_rows = int(P_["rows"]) or max(int((bh - top - 0.8 * X) / lead) + 1, 1)
    phi = math.radians(P_["nib_angle"])
    W0 = P_["nib_w"] * X
    sl = math.tan(math.radians(P_["slant"]))
    marks: list[Mark] = []
    word_id = 0
    rtl = P_["direction"] == "rtl"
    mu = math.log(max(P_["word_mean"], 1.0))

    def to_page(uv: np.ndarray, row_y: float) -> np.ndarray:
        u = uv[:, 0] - sl * uv[:, 1]
        x = (x0 + bw - u * X) if rtl else (x0 + u * X)
        return np.column_stack([x, row_y + uv[:, 1] * X])

    def emit(uv, wf, row, kind, row_y, extra=None):
        nonlocal word_id
        pts = to_page(uv, row_y)
        pts_r = _resample(pts, STEP_MM)
        s_old = _arcl(pts)
        s_new = _arcl(pts_r) * (s_old[-1] / max(_arcl(pts_r)[-1], 1e-9))
        wfr = np.interp(s_new, s_old, wf)
        md = {"row": row, "word": word_id, "kind": kind, "x_height": X, "fit": {"scale": 1.0, "offset": [0.0, 0.0]},
              "voices": [P_["hand"]], "script_hand": P_["hand"]}
        md.update(extra or {})
        marks.append(Mark(pts_r, {"r": np.ones(len(pts_r)), "phi": np.full(len(pts_r), phi),
                                  "W": W0 * wfr, "M": np.full(len(pts_r), 9.0),
                                  "voice": np.zeros(len(pts_r))}, md))
        word_id += 1

    def emit_dots(uv, us, row_y, row):
        for u in us:
            near = uv[np.abs(uv[:, 0] - u) < 0.35]
            if not len(near):
                continue
            top, bot = float(near[:, 1].min()), float(near[:, 1].max())
            n = int(rng.choice([1, 2, 3], p=[0.55, 0.3, 0.15]))
            below = rng.random() < 0.35
            yc = (bot + 0.55) if below else (top - 0.42)
            for k in range(n):
                off = (k - (n - 1) / 2) * 0.42
                yy = yc - (0.38 if (n == 3 and k == 1) else 0.0)
                c = np.array([u + off * (0.0 if n == 3 and k == 1 else 1.0), yy])
                if P_["dot_shape"] == "bead":
                    pts = c[None, :] + np.array([[0.0, 0.0], [1e-3, 0.0]])
                    pc = to_page(pts, row_y)
                    md = {"row": row, "word": -1, "kind": "dot", "x_height": X, "dot_shape": "bead",
                          "dot_d": 0.36 * X, "fit": {"scale": 1.0, "offset": [0.0, 0.0]}, "voices": [P_["hand"]]}
                    marks.append(Mark(pc, {"r": np.ones(2), "phi": np.full(2, phi), "W": np.full(2, W0),
                                           "M": np.full(2, 9.0), "voice": np.zeros(2)}, md))
                else:
                    # a nib dot: a short stroke across the edge (thick direction), as the reed makes a nuqta
                    th = phi + math.pi / 2
                    v = np.array([math.cos(th), -math.sin(th)]) * 0.16
                    pts = np.vstack([c - v, c + v])
                    pc = _resample(to_page(pts, row_y), STEP_MM / 2)
                    md = {"row": row, "word": -1, "kind": "dot", "x_height": X, "dot_shape": "nib",
                          "fit": {"scale": 1.0, "offset": [0.0, 0.0]}, "voices": [P_["hand"]]}
                    marks.append(Mark(pc, {"r": np.ones(len(pc)), "phi": np.full(len(pc), phi),
                                           "W": np.full(len(pc), W0 * 1.1), "M": np.full(len(pc), 9.0),
                                           "voice": np.zeros(len(pc))}, md))

    for row in range(n_rows):
        row_y = y0 + top + row * lead
        if row and row_y + 0.6 * X > y0 + bh:
            break
        span_u = bw / X
        ivs = _free_intervals(obstacle, x0, x0 + bw, row_y - 1.35 * X, row_y + 0.75 * X)
        # intervals in writing coordinates
        ivu = sorted(((x0 + bw - b) / X, (x0 + bw - a) / X) if rtl else ((a - x0) / X, (b - x0) / X)
                     for a, b in ivs)
        ivu = [(a + 0.1, b - 0.1) for a, b in ivu if b - a > 1.5]
        row_uv, row_wf = [], []
        last_word = None
        for ii, (ua, ub) in enumerate(ivu):
            u = ua + (rng.uniform(0, 0.6) if row and P_["indent"] else 0.0)
            last_iv = ii == len(ivu) - 1
            while True:
                ng = max(int(P_["min_glyphs"]), int(round(math.exp(rng.normal(mu, P_["word_sd"])))))
                ng = min(ng, int(3 * P_["word_mean"]) + 1)
                w = wr.word(ng)
                ww = w["width"]
                room = ub - u
                f = 1.0
                tries = 0
                while ww > room and not (P_["line_end"] in ("compress", "both") and last_iv
                                         and room >= 0.5 * ww and room > 1.2) and tries < 3 and room > 1.5:
                    ng = max(int(P_["min_glyphs"]), ng // 2)      # a writer fits a shorter word in
                    w = wr.word(ng)
                    ww = w["width"]
                    tries += 1
                if ww > room:
                    if (P_["line_end"] in ("compress", "both") and last_iv and room >= 0.5 * ww and room > 1.2):
                        f = room / ww
                    else:
                        break
                uv = w["pts"].copy()
                uv[:, 0] = (uv[:, 0] - w["u0"]) * f + u
                ybias = 0.0
                if f < 1.0:                       # line-end: compressed and climbing
                    uv[:, 1] = uv[:, 1] * (0.7 + 0.3 * f)
                    climb = (1 - f) * 1.8 * (uv[:, 0] - u) / max(ww * f, 1e-9)
                    uv[:, 1] -= climb
                base = P_["baseline"]
                if base == "hanging":
                    t = math.tan(math.radians(P_["tilt"] * rng.uniform(0.6, 1.2)))
                    uv[:, 1] += t * (uv[:, 0] - u) - t * 0.5 * ww * f
                elif base == "wander":
                    uv[:, 1] += P_["tilt"] / 30.0 * 0.5 * math.sin(0.35 * u + row * 1.7)
                if rng.random() < P_["ignore"]:          # the word leaves the baseline
                    ybias = float(rng.uniform(-1.3, 0.5))
                    piv = np.array([u, 0.0])
                    uv = piv + _rot2(uv - piv, float(rng.normal(0, 0.12)))
                    uv[:, 1] += ybias
                du = u - w["u0"]
                if P_["join"] == "row" and row_uv:
                    a_end, b_st = row_uv[-1][-1], uv[0]
                    ta, tb = _tangent(row_uv[-1], True, 0.2), _tangent(uv, False, 0.2)
                    dist = float(np.linalg.norm(b_st - a_end))
                    # a kashida: the line dips to the baseline and runs on as a hairline
                    mid = np.array([(a_end[0] + b_st[0]) / 2, 0.15 + 0.1 * rng.random()])
                    c1 = bezier(a_end, ta, mid, np.array([1.0, 0.0]), 0.35 * dist, n=max(int(dist / 0.08), 6))
                    c2 = bezier(mid, np.array([1.0, 0.0]), b_st, tb, 0.35 * dist, n=max(int(dist / 0.08), 6))
                    k = np.vstack([c1[1:], c2[1:-1]])
                    row_uv.append(k)
                    row_wf.append(np.full(len(k), P_["kashida_w"]))
                if P_["join"] == "row":
                    row_uv.append(uv)
                    row_wf.append(w["wf"])
                else:
                    emit(uv, w["wf"], row, "word", row_y)
                if w["dots"]:
                    emit_dots(uv, [(d[0] - w["u0"]) * f + u for d in w["dots"]], row_y, row)
                last_word = (uv, w["wf"])
                gap = P_["word_gap"] * math.exp(rng.normal(0, P_["gap_sd"]))
                u = u + ww * f + gap
                if f < 1.0:
                    break
        # final swash (paragraph end or chance)
        is_last = row == n_rows - 1 or (row_y + lead + 0.5 * X > y0 + bh)
        if last_word is not None and P_["line_end"] in ("swash", "both") and (is_last or rng.random() < P_["swash_rate"]):
            uv_last = row_uv[-1] if P_["join"] == "row" else last_word[0]
            end = uv_last[-1]
            room = (span_u - 0.2) - end[0]
            if room > 1.2:
                sw = wr.swash(min(room, float(rng.uniform(2.5, 4.5))))
                ta = _tangent(uv_last, True, 0.2)
                sw = sw + end + np.array([0.0, 0.0])
                link = bezier(end, ta, sw[0] + np.array([0.3, 0.2]), _tangent(sw, False, 0.2), 0.3, n=10)
                tail = np.vstack([link[1:], sw + np.array([0.3, 0.2])])
                s = _arcl(tail)
                wft = np.clip(1.0 - s / max(s[-1], 1e-9), 0.08, 1.0) ** 0.7
                if P_["join"] == "row":
                    row_uv.append(tail)
                    row_wf.append(wft)
                else:
                    emit(tail, wft, row, "swash", row_y)
        if P_["join"] == "row" and row_uv:
            emit(np.vstack(row_uv), np.concatenate(row_wf), row, "row", row_y)
    return marks


_SCRIPT_PARAMS = [
    P("hand", "ref", "shikasta", "the hand the script's glyphs are cut from", kind="hand"),
    P("length", "float", 8.0, "the hand's source line, in reference lengths", min=1.0, max=16.0),
    P("x_height", "float", 6.0, "x-height (mm)", min=1.5, max=30.0),
    P("rows", "int", 0, "rows (0 = fill the box)", min=0, max=60),
    P("leading", "float", 2.6, "row spacing in x-heights", min=1.2, max=8.0),
    P("direction", "choice", "rtl", "writing direction", choices=("rtl", "ltr")),
    P("slant", "float", 0.0, "slant (deg, + leans forward)", min=-45.0, max=45.0),
    P("inventory", "int", 16, "glyphs in the script's inventory", min=3, max=48),
    P("zipf", "float", 1.0, "glyph frequency skew (0 = uniform)", min=0.0, max=2.5),
    P("turn_lo", "float", 1.2, "glyph turning budget, low (× π)", min=0.2, max=6.0),
    P("turn_hi", "float", 2.6, "glyph turning budget, high (× π)", min=0.3, max=8.0),
    P("glyph_w", "float", 1.3, "widest glyph advance (x-heights)", min=0.3, max=4.0),
    P("asc_h", "float", 2.3, "ascender / descender height (x-heights)", min=1.1, max=5.0),
    P("asc_rate", "float", 0.12, "share of glyphs that rise", min=0.0, max=0.8),
    P("desc_rate", "float", 0.06, "share of glyphs that hang below", min=0.0, max=0.8),
    P("word_mean", "float", 3.2, "median glyphs per word", min=1.0, max=12.0),
    P("min_glyphs", "int", 2, "fewest glyphs in a word (1 lets lone glyphs stand: letter-like)", min=1, max=6),
    P("simple_only", "bool", False, "drop glyph windows that cross themselves"),
    P("word_sd", "float", 0.45, "lognormal spread of word length", min=0.0, max=1.2),
    P("join_gap", "float", 0.22, "ligature length inside words (x-heights)", min=0.0, max=2.0),
    P("word_gap", "float", 0.9, "median space between words (x-heights)", min=0.05, max=4.0),
    P("gap_sd", "float", 0.35, "lognormal spread of word spaces", min=0.0, max=1.2),
    P("baseline", "choice", "ruled", "ruled | hanging (words slope and cascade) | wander",
      choices=("ruled", "hanging", "wander")),
    P("tilt", "float", 12.0, "hanging slope / wander amount (deg)", min=0.0, max=40.0),
    P("ignore", "float", 0.05, "chance a word leaves the baseline", min=0.0, max=1.0),
    P("line_end", "choice", "both", "line ends: compress (climb) / swash / both / none",
      choices=("none", "compress", "swash", "both")),
    P("swash_rate", "float", 0.15, "chance of a swash at a row end (always at the last row)", min=0.0, max=1.0),
    P("dots", "float", 0.15, "chance a glyph carries a dot group", min=0.0, max=1.0),
    P("dot_shape", "choice", "nib", "nib (a short stroke across the edge) or bead (round)",
      choices=("nib", "bead")),
    P("join", "choice", "word", "word: one path per word; row: the whole row is ONE line (hairline kashidas)",
      choices=("word", "row")),
    P("kashida_w", "float", 0.12, "nib share on the row-joining kashidas", min=0.0, max=1.0),
    P("connector_w", "float", 0.7, "nib share on ligatures inside words", min=0.0, max=1.5),
    P("nib_angle", "float", 35.0, "nib edge page angle (deg)", min=0.0, max=180.0),
    P("nib_w", "float", 0.3, "nib width in x-heights (weight)", min=0.03, max=0.9),
    P("jitter", "float", 0.6, "glyph-to-glyph variation", min=0.0, max=2.0),
    P("smooth", "float", 0.05, "glyph smoothing (x-heights; 0 keeps corners sharp)", min=0.0, max=0.4),
    P("indent", "bool", False, "rows start with a small random indent"),
]


@voice("script_solid", params=_SCRIPT_PARAMS,
       doc="rows of abstract script cut from one hand: inventory + words + baseline + line ends",
       reach=lambda p: 0.0)
def script_solid(ctx, **P_):
    return write_block(ctx, **P_)


# ---------------------------------------------------------------------------
# rendering: broad-nib sweep, line-built solid fills
# ---------------------------------------------------------------------------

def sweep(points: np.ndarray, phi: np.ndarray, W: np.ndarray):
    """Shapely area of a flat nib (edge W at page angle φ) dragged along points."""
    from shapely.geometry import Polygon  # noqa: PLC0415
    from shapely.ops import unary_union  # noqa: PLC0415
    p = np.asarray(points, float)
    h = 0.5 * np.asarray(W)[:, None] * np.column_stack([np.cos(phi), -np.sin(phi)])
    a, b = p - h, p + h
    quads = []
    for i in range(len(p) - 1):
        q = Polygon([a[i], b[i], b[i + 1], a[i + 1]])
        if not q.is_valid:
            q = q.buffer(0)
        if q.area > 1e-6:
            quads.append(q)
    if not quads:
        return Polygon()
    return unary_union(quads)


def _rings(g) -> list[np.ndarray]:
    out = []
    geoms = getattr(g, "geoms", [g])
    for q in geoms:
        if q.is_empty or q.geom_type != "Polygon":
            continue
        out.append(np.asarray(q.exterior.coords))
        out += [np.asarray(r.coords) for r in q.interiors]
    return out


def line_built(g, pen: float, pitch: float, *, join: bool = True) -> list[tuple[np.ndarray, bool]]:
    """A (multi)polygon filled with contour-parallel insets (holes respected),
    ink kept inside the shape; rings chained into one path wherever the jump
    to the next ring stays inside the ink. → [(points, closed)]."""
    from shapely.geometry import LineString  # noqa: PLC0415
    from shapely.prepared import prep  # noqa: PLC0415
    if g.is_empty:
        return []
    cur = g.buffer(-0.5 * pen, quad_segs=6)
    step = max(pitch * pen, 0.05)
    levels = []
    guard = 0
    while not cur.is_empty and guard < 200:
        rs = [r for r in _rings(cur) if len(r) >= 4]
        if not rs:
            break
        levels.append(rs)
        cur = cur.buffer(-step, quad_segs=6)
        guard += 1
    rings = [r for lv in levels for r in lv]
    if not rings:
        return []
    if not join:
        return [(r, True) for r in rings]
    inside = prep(g.buffer(0.15 * pen))
    out, path = [], None
    left = list(range(len(rings)))
    here = None
    while left:
        if here is None:
            k = left.pop(0)
            r = rings[k]
            path = [r]
            here = r[-1]
            continue
        # the nearest ring start from here
        best, bj, bi = None, None, None
        for j in left:
            r = rings[j]
            d = np.linalg.norm(r[:-1] - here, axis=1)
            i = int(np.argmin(d))
            if best is None or d[i] < best:
                best, bj, bi = float(d[i]), j, i
        r = rings[bj]
        body = np.roll(r[:-1], -bi, axis=0)
        r2 = np.vstack([body, body[:1]])
        if best <= 2.5 * step and inside.contains(LineString([here, r2[0]])):
            path.append(r2)
            left.remove(bj)
            here = r2[-1]
        else:
            out.append((np.vstack(path), len(path) == 1))
            path = [r2]
            left.remove(bj)
            here = r2[-1]
    if path:
        out.append((np.vstack(path), len(path) == 1))
    return out


def _ink_area(m: Mark, contrast: float):
    from shapely.geometry import Point  # noqa: PLC0415
    if m.meta.get("kind") == "dot" and m.meta.get("dot_shape") == "bead":
        return Point(m.points[0]).buffer(0.5 * float(m.meta.get("dot_d", 1.0)), quad_segs=10)
    return sweep(m.points, np.asarray(m["phi"]), np.asarray(m["W"]) * contrast)


@renderer("script_solid_nib", params=[
    P("pen", "float", 0.3, "pen width (mm): the hairline", min=0.05, max=3.0),
    P("pitch", "float", 0.75, "inset spacing in pen widths (≤ 1 reads solid)", min=0.3, max=2.0),
    P("contrast", "float", 1.0, "nib width multiplier", min=0.0, max=3.0),
    P("hairline", "bool", True, "draw the centreline (the nib's thin edge) too"),
], doc="broad-nib sweep, thick parts filled line-built (insets joined, counters kept), centreline hairline",
    reach=lambda p: 2.0)
def script_solid_nib(ctx, marks, *, pen, pitch, contrast, hairline):
    inks = []
    for m in marks:
        g = _ink_area(m, contrast)
        md = {"kind": m.meta.get("kind"), "row": m.meta.get("row"), "word": m.meta.get("word")}
        for pts, closed in line_built(g, pen, pitch):
            inks.append(Ink(pts, closed=closed, filled=closed, pen=pen, meta={**md, "fill": True}))
        if hairline and m.meta.get("dot_shape") != "bead":
            inks.append(Ink(m.points, pen=pen, meta={**md, "hairline": True}))
    return inks


@renderer("script_solid_bar", params=[
    P("pen", "float", 0.3, "pen width (mm)", min=0.05, max=3.0),
    P("pitch", "float", 0.75, "inset spacing in pen widths", min=0.3, max=2.0),
    P("merge", "choice", "word", "word: each word closes into a round slug; row: the row becomes one bar",
      choices=("word", "row")),
    P("swell", "float", 0.45, "how far the slug swells past the writing (x-heights)", min=0.05, max=2.0),
    P("carve", "float", 0.45, "the carved (white) writing's nib share", min=0.05, max=1.5),
    P("carve_min", "float", 1.6, "narrowest carved line, in pen widths", min=0.5, max=6.0),
], doc="negative script: words/rows close into round black slugs, the writing carved out white",
    reach=lambda p: 3.0)
def script_solid_bar(ctx, marks, *, pen, pitch, merge, swell, carve, carve_min):
    from shapely.ops import unary_union  # noqa: PLC0415
    groups: dict = {}
    for m in marks:
        key = (m.meta.get("row"), m.meta.get("word") if merge == "word" else 0)
        if m.meta.get("kind") == "dot":
            key = (m.meta.get("row"), "dots")
        groups.setdefault(key, []).append(m)
    inks = []
    for key in sorted(groups, key=lambda k: (k[0] if k[0] is not None else -1, str(k[1]))):
        ms = groups[key]
        X = float(ms[0].meta.get("x_height", 6.0))
        writing = unary_union([_ink_area(m, 1.0) for m in ms])
        if key[1] == "dots":                              # dots stay positive (black beads)
            for pts, closed in line_built(writing, pen, pitch):
                inks.append(Ink(pts, closed=closed, filled=closed, pen=pen, meta={"kind": "dot"}))
            continue
        d = swell * X
        slug = writing.buffer(d, quad_segs=12).buffer(-0.45 * d, quad_segs=12)
        cut = unary_union([_ink_area(m, carve).union(_buffer_line(m.points, 0.5 * carve_min * pen))
                           for m in ms])
        neg = slug.difference(cut)
        for pts, closed in line_built(neg, pen, pitch):
            inks.append(Ink(pts, closed=closed, filled=closed, pen=pen, meta={"kind": "bar", "row": key[0]}))
    return inks


def _buffer_line(points, r):
    from shapely.geometry import LineString  # noqa: PLC0415
    if len(points) < 2:
        from shapely.geometry import Point  # noqa: PLC0415
        return Point(points[0]).buffer(r)
    return LineString(points).buffer(r, quad_segs=4)


# ---------------------------------------------------------------------------
# arranger: a drawing with its script
# ---------------------------------------------------------------------------

@arranger("script_solid_page", params=[
    P("layout", "choice", "margin", "margin: script column beside the drawing; wrap: the script flows around "
      "the drawing (answers it); diagonal: a rotated marginal block", choices=("margin", "wrap", "diagonal")),
    P("split", "float", 0.64, "drawing share of the width (margin / diagonal)", min=0.3, max=0.85),
    P("side", "choice", "right", "which side the script column sits", choices=("left", "right")),
    P("clear", "float", 4.0, "clearance between drawing and script (mm)", min=0.0, max=20.0),
    P("drawing_box", "floats", [0.08, 0.1, 0.6, 0.75], "wrap: the drawing's box as fractions (x, y, w, h)"),
    P("angle", "float", 35.0, "diagonal: block angle (deg)", min=-80.0, max=80.0),
], doc="part 0 is a drawing; script_solid parts write beside / around it")
def script_solid_page(ctx, parts, *, layout, split, side, clear, drawing_box, angle):
    from shapely.geometry import LineString  # noqa: PLC0415
    from shapely.ops import unary_union  # noqa: PLC0415
    x0, y0, w, h = ctx.box
    out: list[Mark] = []
    draw, scripts = parts[0], parts[1:]
    if layout == "wrap":
        fx, fy, fw, fh = (list(drawing_box) + [0.08, 0.1, 0.6, 0.75])[:4]
        dbox = (x0 + fx * w, y0 + fy * h, fw * w, fh * h)
        dm = draw.run(dbox)
        out += dm
        obst = unary_union([LineString(m.points).buffer(clear + 0.5, quad_segs=4) for m in dm if len(m) > 1])
        for p in scripts:
            out += _script_part(p, ctx.box, obst)
        return out
    dw = split * w
    if side == "right":
        dbox, sbox = (x0, y0, dw - clear, h), (x0 + dw, y0, w - dw, h)
    else:
        dbox, sbox = (x0 + w - dw + clear, y0, dw - clear, h), (x0, y0, w - dw, h)
    out += draw.run(dbox)
    if layout == "margin":
        n = max(len(scripts), 1)
        for i, p in enumerate(scripts):
            b = (sbox[0], sbox[1] + i * sbox[3] / n, sbox[2], sbox[3] / n)
            out += _script_part(p, b, None)
        return out
    # diagonal: write in an unrotated block sized so that, rotated, it fits the margin (the scribe
    # turns the page); whatever still pokes out is cut at the margin's edge
    from .poly_sheets import clip_marks  # noqa: PLC0415
    a = math.radians(angle)
    ca, sa = abs(math.cos(a)), abs(math.sin(a))
    ws, hs = sbox[2], sbox[3]
    Wd = 0.42 * ws
    L = max(min((ws - Wd * sa) / max(ca, 1e-3), (hs - Wd * ca) / max(sa, 1e-3)), 10.0)
    cx, cy = sbox[0] + ws / 2, sbox[1] + hs / 2
    for p in scripts:
        b = (cx - L / 2, cy - Wd / 2, L, Wd)
        ms = _script_part(p, b, None)
        rot = []
        for m in ms:
            q = _rot2(m.points - [cx, cy], a) + [cx, cy]
            rot.append(m.evolve(points=q, channels={"phi": np.asarray(m["phi"]) + a}))
        out += clip_marks(rot, sbox, min_len=0.0) + [m for m in rot if len(m) < 2]
    return out


def _script_part(p, box, obstacle) -> list[Mark]:
    spec = p.spec["voice"]
    if spec["id"] != "script_solid":
        return p.run(box)
    params = {k: v for k, v in spec.items() if k != "id"}
    ctx = p.ctx("voice", "script_solid", box)
    ms = write_block(ctx, box=box, obstacle=obstacle, **params)
    ms = [m.evolve(meta={"part": p.index, "voice_id": "script_solid"}) for m in ms]
    return p.modulate(ms, box)


@arranger("script_solid_stack", params=[
    P("heights", "floats", [0.14, 0.7, 0.16], "each part's share of the height, top to bottom"),
    P("insets", "floats", [0.0, 0.0, 0.5], "each part's left inset (share of the width)"),
    P("right", "floats", [0.0, 0.0, 0.0], "each part's right inset (share of the width)"),
], doc="parts stacked top to bottom in bands (a letter: heading, body, closing)")
def script_solid_stack(ctx, parts, *, heights, insets, right):
    x0, y0, w, h = ctx.box
    hs = (list(heights) + [1.0] * len(parts))[:len(parts)]
    tot = sum(hs) or 1.0
    out, y = [], y0
    for i, p in enumerate(parts):
        hh = h * hs[i] / tot
        li = (list(insets) + [0.0] * len(parts))[i]
        ri = (list(right) + [0.0] * len(parts))[i]
        b = (x0 + li * w, y, w * (1 - li - ri), hh)
        out += _script_part(p, b, None)
        y += hh
    return out
